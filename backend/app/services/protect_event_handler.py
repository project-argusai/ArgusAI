"""
UniFi Protect Event Handler Service (Story P2-3.1, P2-3.3, P5-1.7)

Handles real-time motion/smart detection events from Protect WebSocket.
Implements event filtering based on per-camera configuration and
deduplication with cooldown logic. Submits events to AI pipeline and
stores results in database.

Story P5-1.7 adds HomeKit doorbell trigger for ring events.

Event Flow:
    uiprotect WebSocket Event
            ↓
    ProtectEventHandler.handle_event()
            ↓
    1. Parse event type (motion, smart_detect_*, ring)
            ↓
    2. Look up camera by protect_camera_id
            ↓
    3. Check camera.is_enabled
            ↓ (if not enabled → discard)
    4. Load smart_detection_types filter
            ↓
    5. Check event type matches filter
            ↓ (if not matching → discard)
    6. Check deduplication cooldown
            ↓ (if duplicate → discard)
    7. Retrieve snapshot (Story P2-3.2)
            ↓
    8. Submit to AI pipeline (Story P2-3.3)
            ↓
    9. Store event in database (Story P2-3.3)
            ↓
    10. Broadcast EVENT_CREATED via WebSocket (Story P2-3.3)
    11. Trigger HomeKit doorbell if ring event (Story P5-1.7)
"""
import asyncio
import base64
import io
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from uiprotect.data.types import EventType as ProtectEventType

from app.core.database import get_db_session
from app.models.camera import Camera
from app.models.event import Event
from app.services.snapshot_service import get_snapshot_service, SnapshotResult
from app.services.clip_service import get_clip_service
from app.services.frame_extractor import get_frame_extractor
from app.services.frame_storage_service import get_frame_storage_service
from app.services.video_storage_service import get_video_storage_service
from app.services.context_prompt_service import get_context_prompt_service
from app.services.push_notification_service import send_event_notification
from app.core.decorators import singleton
from app.services.protect_event_filter import (
    ProtectEventFilter,
    get_protect_event_filter,
    EVENT_COOLDOWN_SECONDS,
)
from app.services.protect_ai_pipeline import ProtectAIPipeline, get_protect_ai_pipeline
from app.services.protect_media_service import ProtectMediaService, get_protect_media_service, MediaBundle
from app.services.protect_event_storage_service import ProtectEventStorageService, get_protect_event_storage_service
from app.services.protect_event_broadcaster import ProtectEventBroadcaster, get_protect_event_broadcaster

if TYPE_CHECKING:
    from app.services.ai_service import AIResult

logger = logging.getLogger(__name__)


def _format_timestamp_for_ai(timestamp: datetime, db: Session) -> str:
    """
    Format a timestamp for AI prompt using user's configured timezone.

    Reads the timezone setting from system settings and converts the UTC
    timestamp to local time for more natural AI descriptions.

    Args:
        timestamp: UTC datetime to format
        db: Database session for reading settings

    Returns:
        ISO format string in user's local timezone
    """
    try:
        from app.models.system_setting import SystemSetting

        # Get timezone from system settings (key: settings_timezone)
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "settings_timezone"
        ).first()

        tz_name = setting.value if setting else "UTC"

        # Ensure timestamp is timezone-aware (assume UTC if naive)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Convert to user's timezone
        try:
            user_tz = ZoneInfo(tz_name)
            local_time = timestamp.astimezone(user_tz)
            return local_time.isoformat()
        except Exception:
            # Invalid timezone, fall back to UTC
            logger.warning(f"Invalid timezone '{tz_name}', using UTC")
            return timestamp.isoformat()

    except Exception as e:
        logger.warning(f"Error formatting timestamp for AI: {e}")
        return timestamp.isoformat()


# EVENT_COOLDOWN_SECONDS moved to ProtectEventFilter (Phase 4)

# WebSocket message type for motion events (for future broadcast to frontend)
PROTECT_MOTION_EVENT = "PROTECT_MOTION_EVENT"

# Event type mapping from Protect to filter types (Story P2-3.1 AC2)
# Protect sends: motion, smart_detect_person, smart_detect_vehicle, etc.
# Filters use: motion, person, vehicle, package, animal, ring
EVENT_TYPE_MAPPING = {
    "motion": "motion",
    "smart_detect_person": "person",
    "smart_detect_vehicle": "vehicle",
    "smart_detect_package": "package",
    "smart_detect_animal": "animal",
    "ring": "ring",
}

# Valid event types we process
VALID_EVENT_TYPES = set(EVENT_TYPE_MAPPING.keys())

# Story P2-4.1: Doorbell-specific AI prompt for describing visitors
DOORBELL_RING_PROMPT = (
    "Describe who is at the front door. Include their appearance, what they're wearing, "
    "and if they appear to be a delivery person, visitor, or solicitor."
)


@singleton
class ProtectEventHandler:
    """
    Handles real-time events from UniFi Protect WebSocket (Story P2-3.1).

    Responsibilities:
    - Parse event types from uiprotect WSMessage
    - Look up camera by protect_camera_id and check if enabled
    - Filter events based on camera's smart_detection_types configuration
    - Deduplicate events using per-camera cooldown
    - Pass qualifying events to snapshot retrieval (Story P2-3.2)

    Attributes:
        _last_event_times: Dict tracking last event timestamp per camera
    """

    def __init__(self):
        """Initialize event handler with empty event tracking."""
        # Use the dedicated ProtectEventFilter for filtering + deduplication (Phase 4)
        self.event_filter: ProtectEventFilter = get_protect_event_filter()

        # AI analysis pipeline for Protect events (Phase 4)
        self.ai_pipeline: ProtectAIPipeline = get_protect_ai_pipeline()

        # Media retrieval coordination for Protect events (Phase 4)
        self.media_service: ProtectMediaService = get_protect_media_service()

        # Event storage service (Phase 4)
        self.storage_service: ProtectEventStorageService = get_protect_event_storage_service()

        # Event broadcasting (WebSocket + HomeKit) (Phase 4)
        self.broadcaster: ProtectEventBroadcaster = get_protect_event_broadcaster()

        # Story P3-5.3: Track last audio transcription for passing to event storage
        self._last_audio_transcription: Optional[str] = None

    def _try_ocr_extraction(self, frame, db) -> Optional[str]:
        """Extract overlay text from a frame via OCR, if enabled in settings.

        Returns the extracted text, or None when OCR is disabled or unavailable.

        NOTE: This method's `def` line was accidentally dropped in a refactor,
        leaving the body orphaned inside __init__ and crashing handler
        construction with `NameError: name 'db' is not defined`. Restoring the
        signature (frame, db) — matching the existing tests — fixes startup.
        """
        from app.models.system_setting import SystemSetting
        from app.services.ocr_service import extract_overlay_text, is_ocr_available

        # Check if OCR is enabled in settings
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == 'settings_attempt_ocr_extraction'
        ).first()
        if not (setting and setting.value.lower() == 'true'):
            return None

        # Check if tesseract is available
        if not is_ocr_available():
            return None

        try:
            return extract_overlay_text(frame)
        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")
            return None

    async def handle_event(
        self,
        controller_id: str,
        msg: Any
    ) -> bool:
        """
        Handle a WebSocket event from uiprotect (Story P2-3.1 AC1).

        Processes motion/smart detection events through filtering and
        deduplication before passing to next stage.

        Args:
            controller_id: Controller UUID
            msg: WebSocket message from uiprotect (WSSubscriptionMessage)

        Returns:
            True if event was processed, False if filtered/skipped
        """
        try:
            # Extract new_obj from message
            new_obj = getattr(msg, 'new_obj', None)
            if not new_obj:
                return False

            # Process Camera, Doorbell, or native Event objects
            model_type = type(new_obj).__name__

            # Handle native Event objects from uiprotect (motion, smart detection, ring)
            if model_type == 'Event':
                return await self._handle_native_event(controller_id, new_obj)

            # Only process Camera or Doorbell state updates (legacy path)
            if model_type not in ('Camera', 'Doorbell'):
                return False

            # Extract protect_camera_id
            protect_camera_id = str(getattr(new_obj, 'id', ''))
            if not protect_camera_id:
                return False

            # Debug: Log raw motion/smart detection state for troubleshooting
            is_motion = getattr(new_obj, 'is_motion_currently_detected', None)
            is_smart_detected = getattr(new_obj, 'is_smart_currently_detected', None)
            is_person = getattr(new_obj, 'is_person_currently_detected', None)
            is_vehicle = getattr(new_obj, 'is_vehicle_currently_detected', None)
            is_package = getattr(new_obj, 'is_package_currently_detected', None)
            is_animal = getattr(new_obj, 'is_animal_currently_detected', None)
            last_smart_event_ids = getattr(new_obj, 'last_smart_detect_event_ids', None)
            active_smart_types = getattr(new_obj, 'active_smart_detect_types', None)
            logger.debug(
                f"WebSocket update for {model_type} {protect_camera_id[:8]}...: "
                f"motion={is_motion}, smart={is_smart_detected}, "
                f"person={is_person}, vehicle={is_vehicle}, package={is_package}, animal={is_animal}",
                extra={
                    "event_type": "protect_ws_update",
                    "model_type": model_type,
                    "protect_camera_id": protect_camera_id,
                    "is_motion_currently_detected": is_motion,
                    "is_smart_currently_detected": is_smart_detected,
                    "is_person_currently_detected": is_person,
                    "is_vehicle_currently_detected": is_vehicle,
                    "is_package_currently_detected": is_package,
                    "is_animal_currently_detected": is_animal,
                    "last_smart_detect_event_ids": str(last_smart_event_ids) if last_smart_event_ids else None,
                    "active_smart_detect_types": str(active_smart_types) if active_smart_types else None
                }
            )

            # Parse event types from the message (AC2)
            event_types = self._parse_event_types(new_obj, model_type)
            if not event_types:
                return False

            # Look up camera in database (AC3)
            with get_db_session() as db:
                camera = self._get_camera_by_protect_id(db, protect_camera_id)

                # Check if camera is enabled for AI analysis (AC3, AC4)
                if not camera:
                    logger.debug(
                        "Event from unregistered camera - discarding",
                        extra={
                            "event_type": "protect_event_unknown_camera",
                            "controller_id": controller_id,
                            "protect_camera_id": protect_camera_id
                        }
                    )
                    return False

                if not camera.is_enabled or camera.source_type != 'protect':
                    logger.debug(
                        f"Event from disabled camera '{camera.name}' - discarding",
                        extra={
                            "event_type": "protect_event_disabled_camera",
                            "controller_id": controller_id,
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                            "is_enabled": camera.is_enabled,
                            "source_type": camera.source_type
                        }
                    )
                    return False

                # Log event received (AC11)
                logger.info(
                    f"Event received from camera '{camera.name}': {', '.join(event_types)}",
                    extra={
                        "event_type": "protect_event_received",
                        "controller_id": controller_id,
                        "camera_id": camera.id,
                        "camera_name": camera.name,
                        "detected_types": event_types,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )

                # Load and check smart_detection_types filter (AC5, AC6, AC7, AC8)
                smart_detection_types = self._load_smart_detection_types(camera)

                for event_type in event_types:
                    # Map event type to filter type
                    filter_type = EVENT_TYPE_MAPPING.get(event_type)
                    if not filter_type:
                        continue

                    # Check if event should be processed (delegated to ProtectEventFilter)
                    if not self.event_filter.should_process_event(filter_type, smart_detection_types, camera.name):
                        continue

                    # Check deduplication cooldown (delegated to ProtectEventFilter)
                    if self.event_filter.is_duplicate_event(camera.id, camera.name):
                        continue

                    # Event passed all filters - record it in the filter for cooldown tracking
                    self.event_filter.record_event(camera.id)
                    event_timestamp = datetime.now(timezone.utc)

                    # Generate event ID early for clip download filename
                    generated_event_id = str(uuid.uuid4())

                    logger.info(
                        f"Event passed filters for camera '{camera.name}': {event_type}",
                        extra={
                            "event_type": "protect_event_passed",
                            "controller_id": controller_id,
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                            "detected_type": event_type,
                            "filter_type": filter_type
                        }
                    )

                    # Story P2-4.1: Check if this is a doorbell ring event
                    is_doorbell_ring = (filter_type == "ring")

                    # Retrieve appropriate media (snapshot + optional clip) via dedicated service (Phase 4)
                    media = await self.media_service.get_media_for_event(
                        controller_id=controller_id,
                        protect_camera_id=camera.protect_camera_id,
                        camera_id=camera.id,
                        camera_name=camera.name,
                        event_id=generated_event_id,
                        event_timestamp=event_timestamp,
                        is_doorbell_ring=is_doorbell_ring,
                        analysis_mode=camera.analysis_mode,
                    )

                    snapshot_result = media.snapshot_result
                    clip_path = media.clip_path
                    media_fallback = media.fallback_reason

                    if not snapshot_result:
                        # Story P3-1.4 AC3: Clean up clip if snapshot retrieval failed
                        if clip_path:
                            try:
                                clip_service = get_clip_service()
                                clip_service.cleanup_clip(generated_event_id)
                            except Exception:
                                pass  # Best effort cleanup
                        return False

                    # Story P2-3.3: Submit to AI pipeline
                    # Extract protect_event_id from WebSocket message
                    protect_event_id = self._extract_protect_event_id(msg)

                    # Story P2-4.1 AC6: For doorbell rings, broadcast DOORBELL_RING immediately
                    # before AI processing for fast notification
                    if is_doorbell_ring:
                        await self.broadcaster.broadcast_doorbell_ring(
                            camera_id=camera.id,
                            camera_name=camera.name,
                            thumbnail_url=snapshot_result.thumbnail_path,
                            timestamp=snapshot_result.timestamp
                        )

                        # Story P5-1.7: Trigger HomeKit doorbell notification
                        self.broadcaster.trigger_homekit_doorbell(camera.id, generated_event_id)

                    # Track total processing time (AC10, AC11)
                    pipeline_start = time.time()

                    # Story P3-1.4 AC1: Pass clip_path to AI pipeline (for future multi-frame analysis)
                    ai_result = await self.ai_pipeline.submit_snapshot_for_analysis(
                        snapshot_result,
                        camera,
                        filter_type,
                        is_doorbell_ring=is_doorbell_ring,
                        clip_path=clip_path
                    )

                    # Story P3-1.4 AC3: Always cleanup clip after AI processing
                    if clip_path:
                        try:
                            clip_service = get_clip_service()
                            cleanup_success = clip_service.cleanup_clip(generated_event_id)
                            logger.debug(
                                f"Clip cleanup {'succeeded' if cleanup_success else 'failed'} for event {generated_event_id[:8]}...",
                                extra={
                                    "event_type": "clip_cleanup",
                                    "event_id": generated_event_id,
                                    "cleanup_success": cleanup_success
                                }
                            )
                        except Exception as e:
                            logger.warning(
                                f"Clip cleanup error for event {generated_event_id[:8]}...: {e}",
                                extra={
                                    "event_type": "clip_cleanup_error",
                                    "event_id": generated_event_id,
                                    "error_type": type(e).__name__
                                }
                            )

                    if not ai_result or not ai_result.success:
                        # Story P3-3.5 AC3: Complete failure - all analysis modes exhausted
                        # Create event with "AI analysis unavailable" instead of returning False
                        logger.error(
                            f"AI pipeline completely failed for camera '{camera.name}' - saving event without description",
                            extra={
                                "event_type": "protect_ai_complete_failure",
                                "camera_id": camera.id,
                                "camera_name": camera.name,
                                "event_id": generated_event_id,
                                "error": ai_result.error if ai_result else "No result",
                                "fallback_chain": getattr(self, '_fallback_chain', [])
                            }
                        )

                        # Store via new service (no AI result)
                        stored_event = await self.storage_service.persist_protect_event(
                            db=db,
                            camera=camera,
                            snapshot_result=snapshot_result,
                            ai_result=None,
                            protect_event_id=protect_event_id,
                            event_type=filter_type,
                            is_doorbell_ring=is_doorbell_ring,
                            event_id_override=generated_event_id,
                        )

                        if stored_event:
                            # Broadcast the event even without AI description
                            await self.broadcaster.broadcast_event_created(stored_event, camera)
                            asyncio.create_task(self._process_correlation(stored_event))
                            # Publish to MQTT for Home Assistant (even without AI)
                            await self._publish_event_to_mqtt(stored_event, camera, None)
                            return True

                        return False

                    # Story P2-3.3: Store event in database via storage service (Phase 4)
                    stored_event = await self.storage_service.persist_protect_event(
                        db=db,
                        camera=camera,
                        snapshot_result=snapshot_result,
                        ai_result=ai_result,
                        protect_event_id=str(protect_event_id) if protect_event_id else None,
                        event_type=filter_type,
                        is_doorbell_ring=is_doorbell_ring,
                        fallback_reason=media_fallback,
                        event_id_override=generated_event_id
                    )

                    if not stored_event:
                        return False

                    # Track and log processing time (AC10, AC11)
                    processing_time_ms = int((time.time() - pipeline_start) * 1000)
                    if processing_time_ms > 2000:  # NFR2: 2 second target
                        logger.warning(
                            f"Processing time {processing_time_ms}ms exceeds 2s target for camera '{camera.name}'",
                            extra={
                                "event_type": "protect_latency_warning",
                                "camera_id": camera.id,
                                "processing_time_ms": processing_time_ms
                            }
                        )
                    else:
                        logger.info(
                            f"Event processed in {processing_time_ms}ms for camera '{camera.name}'",
                            extra={
                                "event_type": "protect_event_processed",
                                "camera_id": camera.id,
                                "processing_time_ms": processing_time_ms
                            }
                        )

                    # Story P2-3.3: Broadcast EVENT_CREATED via WebSocket (AC12)
                    await self.broadcaster.broadcast_event_created(stored_event, camera)

                    # TODO(Phase 4): Re-enable correlation + MQTT via dedicated services
                    # asyncio.create_task(self.correlation_service.process(stored_event))
                    # await self.mqtt_service.publish_event(stored_event, camera, ai_result)

                    return True

                return False

        except Exception as e:
            logger.warning(
                f"Error handling Protect event: {e}",
                extra={
                    "event_type": "protect_event_handler_error",
                    "controller_id": controller_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return False

    def _parse_event_types(self, obj: Any, model_type: str) -> List[str]:
        """
        Parse event types from uiprotect object (Story P2-3.1 AC2).

        Extracts motion and smart detection types from the camera object.

        Args:
            obj: Camera or Doorbell object from uiprotect
            model_type: "Camera" or "Doorbell"

        Returns:
            List of event type strings (e.g., ["motion", "smart_detect_person"])
        """
        event_types = []

        # Check for motion detection
        # uiprotect uses 'is_motion_currently_detected' (not 'is_motion_detected')
        is_motion_detected = getattr(obj, 'is_motion_currently_detected', False)
        if is_motion_detected:
            event_types.append("motion")

        # Check for smart detection types using individual detection flags
        # These are the most reliable indicators of what was actually detected
        smart_detect_checks = [
            ('is_person_currently_detected', 'smart_detect_person'),
            ('is_vehicle_currently_detected', 'smart_detect_vehicle'),
            ('is_package_currently_detected', 'smart_detect_package'),
            ('is_animal_currently_detected', 'smart_detect_animal'),
        ]

        for attr_name, event_key in smart_detect_checks:
            if getattr(obj, attr_name, False):
                if event_key in VALID_EVENT_TYPES:
                    event_types.append(event_key)

        # Also check is_smart_currently_detected as a fallback for other smart detection types
        # This catches any smart detections not covered by the individual checks above
        is_smart_detected = getattr(obj, 'is_smart_currently_detected', False)
        if is_smart_detected and not any(e.startswith('smart_detect_') for e in event_types):
            # No specific smart detection found yet, try to extract from last_smart_detect_event_ids
            last_smart_event_ids = getattr(obj, 'last_smart_detect_event_ids', {})
            if last_smart_event_ids:
                for detect_type in last_smart_event_ids.keys():
                    detect_value = getattr(detect_type, 'value', str(detect_type)).lower()
                    event_key = f"smart_detect_{detect_value}"
                    if event_key in VALID_EVENT_TYPES and event_key not in event_types:
                        event_types.append(event_key)
            else:
                # Final fallback: use active_smart_detect_types
                active_types = getattr(obj, 'active_smart_detect_types', set())
                for detect_type in active_types:
                    detect_value = getattr(detect_type, 'value', str(detect_type)).lower()
                    event_key = f"smart_detect_{detect_value}"
                    if event_key in VALID_EVENT_TYPES and event_key not in event_types:
                        event_types.append(event_key)

        # Check for doorbell ring (specific to doorbells)
        if model_type == 'Doorbell':
            is_ringing = getattr(obj, 'is_ringing', False)
            if is_ringing:
                event_types.append("ring")

        return event_types

    async def _handle_native_event(self, controller_id: str, event_obj: Any) -> bool:
        """
        Handle native uiprotect Event objects.

        These are direct event notifications from Protect (MOTION, SMART_DETECT, RING)
        rather than Camera state updates.

        Args:
            controller_id: Controller UUID
            event_obj: Native Event object from uiprotect

        Returns:
            True if event was processed, False if filtered/skipped
        """
        try:
            # Get event properties
            event_type = getattr(event_obj, 'type', None)
            protect_camera_id = getattr(event_obj, 'camera_id', None)
            smart_detect_types = getattr(event_obj, 'smart_detect_types', []) or []
            event_start = getattr(event_obj, 'start', None)
            protect_event_id = getattr(event_obj, 'id', None)

            # Only process motion, smart detection, and ring events
            if event_type not in (ProtectEventType.MOTION, ProtectEventType.SMART_DETECT, ProtectEventType.RING):
                logger.debug(
                    f"Native Event type {event_type} not processable - skipping",
                    extra={
                        "event_type": "protect_native_event_skipped",
                        "protect_event_type": str(event_type) if event_type else None,
                    }
                )
                return False

            if not protect_camera_id:
                logger.debug(
                    f"Native event has no camera_id - skipping",
                    extra={
                        "event_type": "protect_native_event_no_camera",
                        "protect_event_type": str(event_type),
                        "protect_event_id": str(protect_event_id) if protect_event_id else None,
                    }
                )
                return False

            # Convert to our event type format
            event_types = []
            if event_type == ProtectEventType.MOTION:
                event_types.append("motion")
            elif event_type == ProtectEventType.RING:
                event_types.append("ring")
            elif event_type == ProtectEventType.SMART_DETECT:
                # Convert smart_detect_types to our format
                for smart_type in smart_detect_types:
                    smart_value = getattr(smart_type, 'value', str(smart_type)).lower()
                    event_key = f"smart_detect_{smart_value}"
                    if event_key in VALID_EVENT_TYPES:
                        event_types.append(event_key)
                # If no specific smart type found, fall back to motion
                if not event_types:
                    event_types.append("motion")

            logger.info(
                f"Native Protect event received: {event_type.value}, types={event_types}",
                extra={
                    "event_type": "protect_native_event_received",
                    "controller_id": controller_id,
                    "protect_camera_id": protect_camera_id,
                    "protect_event_type": event_type.value,
                    "detected_types": event_types,
                    "smart_detect_types": [str(t) for t in smart_detect_types],
                    "protect_event_id": str(protect_event_id) if protect_event_id else None,
                }
            )

            # Look up camera and process
            with get_db_session() as db:
                camera = self._get_camera_by_protect_id(db, protect_camera_id)

                if not camera:
                    logger.debug(
                        f"Native event from unregistered camera - discarding",
                        extra={
                            "event_type": "protect_native_event_unknown_camera",
                            "controller_id": controller_id,
                            "protect_camera_id": protect_camera_id
                        }
                    )
                    return False

                if not camera.is_enabled or camera.source_type != 'protect':
                    logger.debug(
                        f"Native event from disabled camera '{camera.name}' - discarding",
                        extra={
                            "event_type": "protect_native_event_disabled_camera",
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                        }
                    )
                    return False

                # Filter based on camera's smart_detection_types configuration
                smart_detection_types = self._load_smart_detection_types(camera)
                matching_types = []

                for evt_type in event_types:
                    # Map event type to filter type (e.g., "smart_detect_person" -> "person")
                    filter_type = EVENT_TYPE_MAPPING.get(evt_type)
                    if not filter_type:
                        continue

                    # Check if event should be processed based on camera config (via filter)
                    if self.event_filter.should_process_event(filter_type, smart_detection_types, camera.name):
                        matching_types.append(evt_type)

                if not matching_types:
                    logger.debug(
                        f"Native event types {event_types} not in camera filter {smart_detection_types} - discarding",
                        extra={
                            "event_type": "protect_native_event_filtered",
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                            "detected_types": event_types,
                            "allowed_types": smart_detection_types,
                        }
                    )
                    return False

                # Check deduplication cooldown (via filter)
                if self.event_filter.is_duplicate_event(camera.id, camera.name):
                    logger.debug(
                        f"Native event deduplicated for camera '{camera.name}'",
                        extra={
                            "event_type": "protect_native_event_deduplicated",
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                        }
                    )
                    return False

                # Record the event for cooldown tracking
                self.event_filter.record_event(camera.id)

                # Determine if this is a doorbell ring
                is_doorbell_ring = event_type == ProtectEventType.RING

                # Get timestamp
                event_timestamp = event_start or datetime.now(timezone.utc)

                # Generate event ID for clip filename
                generated_event_id = str(uuid.uuid4())

                # Get primary filter type for AI
                primary_event_type = matching_types[0] if matching_types else "motion"
                filter_type = EVENT_TYPE_MAPPING.get(primary_event_type, "motion")

                logger.info(
                    f"Processing native event from camera '{camera.name}': {matching_types}",
                    extra={
                        "event_type": "protect_native_event_processing",
                        "controller_id": controller_id,
                        "camera_id": camera.id,
                        "camera_name": camera.name,
                        "detected_types": matching_types,
                        "filter_type": filter_type,
                        "is_doorbell_ring": is_doorbell_ring,
                        "protect_event_id": str(protect_event_id) if protect_event_id else None,
                    }
                )

                # Retrieve media using the new service (Phase 4)
                media = await self.media_service.get_media_for_event(
                    controller_id=controller_id,
                    protect_camera_id=camera.protect_camera_id,
                    camera_id=camera.id,
                    camera_name=camera.name,
                    event_id=generated_event_id,
                    event_timestamp=event_timestamp,
                    is_doorbell_ring=is_doorbell_ring,
                    analysis_mode=camera.analysis_mode,
                )
                snapshot_result = media.snapshot_result
                clip_path = media.clip_path
                fallback_reason = media.fallback_reason

                if not snapshot_result:
                    # Clean up clip if snapshot failed
                    if clip_path:
                        try:
                            clip_service = get_clip_service()
                            clip_service.cleanup_clip(generated_event_id)
                        except Exception:
                            pass
                    return False

                # For doorbell rings, broadcast immediately
                if is_doorbell_ring:
                    await self._broadcast_doorbell_ring(
                        camera_id=camera.id,
                        camera_name=camera.name,
                        thumbnail_url=snapshot_result.thumbnail_path,
                        timestamp=snapshot_result.timestamp
                    )
                    self.broadcaster.trigger_homekit_doorbell(camera.id, generated_event_id)

                # Track processing time
                pipeline_start = time.time()

                # Submit to AI pipeline (via ProtectAIPipeline)
                ai_result = await self.ai_pipeline.submit_snapshot_for_analysis(
                    snapshot_result,
                    camera,
                    filter_type,
                    is_doorbell_ring=is_doorbell_ring,
                    clip_path=clip_path
                )

                # Cleanup clip after AI processing
                if clip_path:
                    try:
                        clip_service = get_clip_service()
                        clip_service.cleanup_clip(generated_event_id)
                    except Exception as e:
                        logger.warning(f"Clip cleanup error: {e}")

                if not ai_result or not ai_result.success:
                    # Store event without AI description
                    stored_event = await self.storage_service.persist_protect_event(
                        db=db,
                        camera=camera,
                        snapshot_result=snapshot_result,
                        ai_result=None,
                        protect_event_id=str(protect_event_id) if protect_event_id else None,
                        event_type=filter_type,
                        is_doorbell_ring=is_doorbell_ring,
                        event_id_override=generated_event_id,
                    )
                    if stored_event:
                        await self.broadcaster.broadcast_event_created(stored_event, camera)
                        # TODO(Phase 4): Correlation + MQTT
                        return True
                    return False

                # Store event with AI result
                # Persist via new storage service (Phase 4)
                stored_event = await self.storage_service.persist_protect_event(
                    db=db,
                    camera=camera,
                    snapshot_result=snapshot_result,
                    ai_result=ai_result,
                    protect_event_id=str(protect_event_id) if protect_event_id else None,
                    event_type=filter_type,
                    is_doorbell_ring=is_doorbell_ring,
                    fallback_reason=fallback_reason,
                    event_id_override=generated_event_id,
                )

                if not stored_event:
                    return False

                # Log processing time
                processing_time_ms = int((time.time() - pipeline_start) * 1000)
                if processing_time_ms > 2000:
                    logger.warning(
                        f"Processing time {processing_time_ms}ms exceeds 2s target for camera '{camera.name}'",
                        extra={
                            "event_type": "protect_latency_warning",
                            "camera_id": camera.id,
                            "processing_time_ms": processing_time_ms
                        }
                    )

                # Broadcast and publish event
                await self.broadcaster.broadcast_event_created(stored_event, camera)
                # TODO(Phase 4): Correlation + MQTT via dedicated services

                return True

        except Exception as e:
            logger.error(
                f"Error handling native Protect event: {e}",
                extra={
                    "event_type": "protect_native_event_error",
                    "controller_id": controller_id,
                    "error": str(e),
                },
                exc_info=True
            )
            return False

    def _get_camera_by_protect_id(
        self,
        db: Session,
        protect_camera_id: str
    ) -> Optional[Camera]:
        """
        Look up camera by protect_camera_id (Story P2-3.1 AC3).

        Args:
            db: Database session
            protect_camera_id: Native Protect camera ID

        Returns:
            Camera model or None if not found
        """
        return db.query(Camera).filter(
            Camera.protect_camera_id == protect_camera_id
        ).first()

    def _load_smart_detection_types(self, camera: Camera) -> List[str]:
        """
        Load smart_detection_types from camera record (Story P2-3.1 AC5).

        Parses JSON array from camera.smart_detection_types field.

        Args:
            camera: Camera model instance

        Returns:
            List of filter types (e.g., ["person", "vehicle"])
            Empty list if not configured (enables "all motion" mode)
        """
        if not camera.smart_detection_types:
            return []

        try:
            types = json.loads(camera.smart_detection_types)
            if isinstance(types, list):
                return types
            return []
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"Invalid smart_detection_types JSON for camera '{camera.name}'",
                extra={
                    "event_type": "protect_invalid_filter_config",
                    "camera_id": camera.id,
                    "camera_name": camera.name
                }
            )
            return []

    # Filtering and deduplication logic moved to ProtectEventFilter (Phase 4)
    # Use self.event_filter.should_process_event(...) and .is_duplicate_event(...)

    # _download_clip_for_event and _retrieve_snapshot removed — logic moved to ProtectMediaService (Phase 4)

    def clear_event_tracking(self, camera_id: Optional[str] = None) -> None:
        """
        Clear deduplication tracking data (delegated to ProtectEventFilter).
        """
        if camera_id:
            self.event_filter.clear_camera(camera_id)
        else:
            # Note: full clear would need to be added to the filter if required
            self.event_filter._last_event_times.clear()  # temporary direct access for full reset

    def _extract_protect_event_id(self, msg: Any) -> Optional[str]:
        """
        Extract Protect's native event ID from WebSocket message (Story P2-3.3 AC6).

        Args:
            msg: WebSocket message from uiprotect

        Returns:
            Protect event ID string or None if not available
        """
        try:
            new_obj = getattr(msg, 'new_obj', None)
            if new_obj:
                # Try to get last_motion event ID
                last_motion = getattr(new_obj, 'last_motion', None)
                if last_motion:
                    event_id = getattr(last_motion, 'id', None)
                    if event_id:
                        return str(event_id)

                # Fallback to last_smart_detect
                last_smart = getattr(new_obj, 'last_smart_detect', None)
                if last_smart:
                    event_id = getattr(last_smart, 'id', None)
                    if event_id:
                        return str(event_id)

            return None
        except Exception:
            return None

    # _submit_to_ai_pipeline moved to ProtectAIPipeline (Phase 4)

    
    # _try_video_frame_extraction removed — logic moved to ProtectAIPipeline (Phase 4)


    # Broadcast shims removed (Phase 4) — call self.broadcaster.* directly

    # _download_and_store_video removed — logic moved to ProtectMediaService (Phase 4)


# -------------------------------------------------------------------------
# Singleton accessors (added to fix ImportError after #450 migration)
# -------------------------------------------------------------------------

def get_protect_event_handler() -> "ProtectEventHandler":
    """Get the global ProtectEventHandler singleton instance."""
    return ProtectEventHandler()


def reset_protect_event_handler() -> None:
    """Reset the global ProtectEventHandler singleton (for tests)."""
    ProtectEventHandler._reset_instance()

