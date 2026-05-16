"""
MQTT Status Service for Camera Status Sensors (Story P4-2.5)

Provides helper functions and scheduled tasks for camera status sensors:
- Event count calculations (daily/weekly)
- Activity sensor timeout management
- Scheduled count updates
- Count reset at midnight/Monday

Uses APScheduler for background tasks.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Set

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.event import Event
from app.models.camera import Camera

logger = logging.getLogger(__name__)

# Activity timeout in minutes (AC4)
ACTIVITY_TIMEOUT_MINUTES = 5

# Scheduled update interval in minutes (AC3)
COUNT_UPDATE_INTERVAL_MINUTES = 5

# Track cameras with active activity (for timeout management)
_active_cameras: Dict[str, datetime] = {}  # camera_id -> last_event_timestamp

# Lock for activity state
_activity_lock = asyncio.Lock()


async def get_camera_event_counts(camera_id: str) -> Dict[str, int]:
    """
    Calculate event counts for a camera (AC3, AC10).

    Returns daily and weekly event counts based on local server time.
    Daily resets at midnight, weekly resets at Monday 00:00.

    Args:
        camera_id: Camera UUID

    Returns:
        Dict with events_today and events_this_week counts
    """
    now = datetime.now(timezone.utc)

    # Calculate start of today (midnight UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Calculate start of week (Monday 00:00 UTC)
    # weekday() returns 0 for Monday, 6 for Sunday
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    with SessionLocal() as db:
        # Count events today
        events_today = db.query(func.count(Event.id)).filter(
            Event.camera_id == camera_id,
            Event.timestamp >= today_start
        ).scalar() or 0

        # Count events this week
        events_this_week = db.query(func.count(Event.id)).filter(
            Event.camera_id == camera_id,
            Event.timestamp >= week_start
        ).scalar() or 0

    return {
        "events_today": events_today,
        "events_this_week": events_this_week
    }


async def publish_all_camera_counts() -> int:
    """
    Publish event counts for all enabled cameras (scheduled task).

    Returns:
        Number of cameras updated
    """
    from app.services.mqtt_service import get_mqtt_service

    mqtt_service = get_mqtt_service()
    if not mqtt_service.is_connected:
        logger.debug("Cannot publish camera counts: MQTT not connected")
        return 0

    with SessionLocal() as db:
        cameras = db.query(Camera).filter(Camera.is_enabled == True).all()

        updated_count = 0
        for camera in cameras:
            try:
                counts = await get_camera_event_counts(str(camera.id))
                success = await mqtt_service.publish_event_counts(
                    camera_id=str(camera.id),
                    camera_name=camera.name,
                    events_today=counts["events_today"],
                    events_this_week=counts["events_this_week"]
                )
                if success:
                    updated_count += 1
            except Exception as e:
                logger.warning(
                    f"Failed to publish counts for camera {camera.id}: {e}",
                    extra={"camera_id": str(camera.id), "error": str(e)}
                )

        logger.debug(
            f"Published event counts for {updated_count}/{len(cameras)} cameras",
            extra={"event_type": "mqtt_counts_scheduled_update"}
        )

        return updated_count


async def set_activity_on(camera_id: str, last_event_at: datetime) -> None:
    """
    Mark camera as having recent activity (AC4).

    Sets activity sensor to ON and schedules timeout.

    Args:
        camera_id: Camera UUID
        last_event_at: Timestamp of the triggering event
    """
    async with _activity_lock:
        _active_cameras[camera_id] = last_event_at

    logger.debug(
        f"Camera {camera_id} activity set to ON",
        extra={"camera_id": camera_id, "last_event_at": last_event_at.isoformat()}
    )


async def check_activity_timeouts() -> int:
    """
    Check for cameras that should have activity set to OFF (scheduled task).

    Cameras with no events in the last 5 minutes are set to OFF.

    Returns:
        Number of cameras set to OFF
    """
    from app.services.mqtt_service import get_mqtt_service

    mqtt_service = get_mqtt_service()
    if not mqtt_service.is_connected:
        return 0

    now = datetime.now(timezone.utc)
    timeout_threshold = now - timedelta(minutes=ACTIVITY_TIMEOUT_MINUTES)

    cameras_to_deactivate = []

    async with _activity_lock:
        for camera_id, last_event_at in list(_active_cameras.items()):
            # Ensure last_event_at is timezone-aware for comparison
            if last_event_at.tzinfo is None:
                last_event_at = last_event_at.replace(tzinfo=timezone.utc)
            if last_event_at < timeout_threshold:
                cameras_to_deactivate.append(camera_id)

        # Remove from active set
        for camera_id in cameras_to_deactivate:
            del _active_cameras[camera_id]

    # Publish OFF state for each camera
    off_count = 0
    for camera_id in cameras_to_deactivate:
        try:
            success = await mqtt_service.publish_activity_state(
                camera_id=camera_id,
                state="OFF",
                last_event_at=None
            )
            if success:
                off_count += 1
                logger.debug(
                    f"Camera {camera_id} activity set to OFF (timeout)",
                    extra={"camera_id": camera_id}
                )
        except Exception as e:
            logger.warning(
                f"Failed to publish activity OFF for camera {camera_id}: {e}",
                extra={"camera_id": camera_id, "error": str(e)}
            )

    return off_count


async def publish_all_camera_statuses() -> int:
    """
    Publish status for all enabled cameras.

    Used on MQTT reconnect and initial startup.

    Returns:
        Number of cameras updated
    """
    from app.services.mqtt_service import get_mqtt_service
    from app.services.camera_service import CameraService

    mqtt_service = get_mqtt_service()
    camera_service = CameraService()  # @singleton pattern
    if not mqtt_service.is_connected:
        return 0

    with SessionLocal() as db:
        cameras = db.query(Camera).filter(Camera.is_enabled == True).all()

        updated_count = 0
        for camera in cameras:
            try:
                # Get camera status from camera service
                camera_status = camera_service.get_camera_status(str(camera.id))

                # Determine MQTT status
                if camera_status:
                    status = camera_status.get("status", "unavailable")
                else:
                    # No status means camera isn't running
                    status = "unavailable"

                # Get source type
                source_type = camera.source_type or camera.type or "rtsp"

                success = await mqtt_service.publish_camera_status(
                    camera_id=str(camera.id),
                    camera_name=camera.name,
                    status=status,
                    source_type=source_type
                )
                if success:
                    updated_count += 1
            except Exception as e:
                logger.warning(
                    f"Failed to publish status for camera {camera.id}: {e}",
                    extra={"camera_id": str(camera.id), "error": str(e)}
                )

        logger.info(
            f"Published status for {updated_count}/{len(cameras)} cameras",
            extra={"event_type": "mqtt_status_all_published"}
        )

        return updated_count


async def publish_camera_status_update(
    camera_id: str,
    camera_name: str,
    status: str,
    source_type: str
) -> bool:
    """
    Publish a single camera status update.

    Convenience wrapper for use from camera lifecycle hooks.

    Args:
        camera_id: Camera UUID
        camera_name: Human-readable camera name
        status: Status string
        source_type: Camera type

    Returns:
        True if published successfully
    """
    from app.services.mqtt_service import get_mqtt_service

    mqtt_service = get_mqtt_service()
    if not mqtt_service.is_connected:
        return False

    return await mqtt_service.publish_camera_status(
        camera_id=camera_id,
        camera_name=camera_name,
        status=status,
        source_type=source_type
    )


# ===========================================================================
# Scheduled Task Setup (APScheduler integration)
# ===========================================================================

_scheduler_initialized = False


def setup_status_sensor_scheduler() -> None:
    """
    Set up scheduled tasks for status sensor updates.

    Schedules:
    - Event count updates every 5 minutes
    - Activity timeout checks every 1 minute

    Should be called during app startup after MQTT service is initialized.
    """
    global _scheduler_initialized

    if _scheduler_initialized:
        logger.debug("Status sensor scheduler already initialized")
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = AsyncIOScheduler()

        # Schedule count updates every 5 minutes (AC3)
        scheduler.add_job(
            publish_all_camera_counts,
            trigger=IntervalTrigger(minutes=COUNT_UPDATE_INTERVAL_MINUTES),
            id="mqtt_count_updates",
            name="MQTT Event Count Updates",
            replace_existing=True
        )

        # Schedule activity timeout checks every 1 minute (AC4)
        scheduler.add_job(
            check_activity_timeouts,
            trigger=IntervalTrigger(minutes=1),
            id="mqtt_activity_timeout",
            name="MQTT Activity Timeout Check",
            replace_existing=True
        )

        scheduler.start()
        _scheduler_initialized = True

        logger.info(
            "MQTT status sensor scheduler started",
            extra={
                "event_type": "mqtt_status_scheduler_started",
                "count_interval_minutes": COUNT_UPDATE_INTERVAL_MINUTES,
                "activity_timeout_minutes": ACTIVITY_TIMEOUT_MINUTES
            }
        )

    except ImportError:
        logger.warning(
            "APScheduler not available, status sensor scheduled updates disabled"
        )
    except Exception as e:
        logger.error(f"Failed to initialize status sensor scheduler: {e}")


async def initialize_status_sensors() -> None:
    """
    Initialize status sensors on app startup.

    Publishes initial status and counts for all cameras.
    Sets up scheduled tasks.
    """
    try:
        # Set up scheduler for periodic updates
        setup_status_sensor_scheduler()

        # Wait a moment for MQTT to stabilize
        await asyncio.sleep(1.0)

        # Publish initial statuses
        await publish_all_camera_statuses()

        # Publish initial counts
        await publish_all_camera_counts()

        logger.info(
            "MQTT status sensors initialized",
            extra={"event_type": "mqtt_status_sensors_initialized"}
        )

    except Exception as e:
        logger.error(f"Failed to initialize status sensors: {e}")
