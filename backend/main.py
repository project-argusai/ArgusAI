"""
FastAPI application entry point for ArgusAI

Initializes the FastAPI app, registers routers, and sets up startup/shutdown events.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import engine, Base
from app.core.logging_config import setup_logging, get_logger
from app.core.metrics import init_metrics, get_metrics, get_content_type, update_system_metrics
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.auth_middleware import AuthMiddleware
from app.api.v1.cameras import router as cameras_router, camera_service
from app.api.v1.motion_events import router as motion_events_router
from app.api.v1.ai import router as ai_router
from app.api.v1.events import router as events_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.system import router as system_router, get_retention_policy_from_db
from app.services.backup_service import get_backup_service
from app.api.v1.alert_rules import router as alert_rules_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.websocket import router as websocket_router
from app.api.v1.logs import router as logs_router
from app.api.v1.auth import router as auth_router, ensure_admin_exists, limiter
from app.api.v1.protect import router as protect_router  # Story P2-1.1: UniFi Protect
from app.api.v1.system_notifications import router as system_notifications_router  # Story P3-7.4: Cost Alerts
from app.api.v1.push import router as push_router  # Story P4-1.1: Web Push
from app.api.v1.integrations import router as integrations_router  # Story P4-2.1: MQTT
from app.api.v1.context import router as context_router  # Story P4-3.1: Embeddings
from app.api.v1.summaries import router as summaries_router  # Story P4-4.1: Activity Summaries
from app.api.v1.digests import router as digests_router  # Story P4-4.2: Daily Digest Scheduler
from app.api.v1.feedback import router as feedback_router  # Story P4-5.2: Feedback Statistics
from app.services.event_processor import initialize_event_processor, shutdown_event_processor
from app.services.cleanup_service import get_cleanup_service
from app.services.protect_service import get_protect_service  # Story P2-1.4: Protect WebSocket
from app.services.mqtt_service import initialize_mqtt_service, shutdown_mqtt_service  # Story P4-2.1: MQTT
from app.services.mqtt_discovery_service import initialize_discovery_service, get_discovery_service  # Story P4-2.2: HA Discovery
from app.services.mqtt_status_service import initialize_status_sensors  # Story P4-2.5: Camera Status Sensors
from app.services.pattern_service import get_pattern_service  # Story P4-3.5: Pattern Detection
from app.services.digest_scheduler import initialize_digest_scheduler, shutdown_digest_scheduler  # Story P4-4.2: Digest Scheduler
from app.services.homekit_service import get_homekit_service, initialize_homekit_service, shutdown_homekit_service  # Story P4-6.1: HomeKit

# Application version
APP_VERSION = "1.0.0"

# Initialize structured JSON logging (Story 6.2)
setup_logging(app_version=APP_VERSION)
logger = get_logger(__name__)

# Initialize Prometheus metrics
init_metrics(version=APP_VERSION)

# Global scheduler instance
scheduler: AsyncIOScheduler = None


async def scheduled_cleanup_job():
    """
    Scheduled cleanup job that runs daily at 2:00 AM

    Deletes old events based on retention policy from system_settings table.
    Only runs if retention policy is not set to "forever" (retention_days > 0).
    """
    try:
        # Get retention policy from database
        retention_days = get_retention_policy_from_db()

        # Skip cleanup if retention is set to forever
        if retention_days <= 0:
            logger.info("Scheduled cleanup skipped (retention policy set to forever)")
            return

        logger.info(f"Starting scheduled cleanup (retention: {retention_days} days)")

        # Execute cleanup
        cleanup_service = get_cleanup_service()
        stats = await cleanup_service.cleanup_old_events(retention_days=retention_days)

        logger.info(
            f"Scheduled cleanup complete: {stats['events_deleted']} events deleted, "
            f"{stats['space_freed_mb']} MB freed",
            extra=stats
        )

    except Exception as e:
        logger.error(f"Scheduled cleanup failed: {e}", exc_info=True)


async def scheduled_backup_job():
    """
    Scheduled backup job that runs daily at 3:00 AM (configurable)

    Creates automatic backups and maintains retention policy (keeps last N backups).
    Only runs if automatic backups are enabled in system_settings.
    """
    try:
        # Check if automatic backups are enabled
        from app.core.database import SessionLocal
        from app.models.system_setting import SystemSetting

        db = SessionLocal()
        try:
            auto_backup_setting = db.query(SystemSetting).filter(
                SystemSetting.key == "settings_auto_backup_enabled"
            ).first()

            # Skip if auto-backup is not enabled (default: disabled)
            if not auto_backup_setting or auto_backup_setting.value.lower() not in ('true', '1', 'yes'):
                logger.debug("Scheduled backup skipped (auto-backup not enabled)")
                return

            # Get retention count setting
            retention_setting = db.query(SystemSetting).filter(
                SystemSetting.key == "settings_backup_retention_count"
            ).first()
            keep_count = int(retention_setting.value) if retention_setting else 7

        finally:
            db.close()

        logger.info("Starting scheduled automatic backup")

        # Create backup
        backup_service = get_backup_service()
        result = await backup_service.create_backup()

        if result.success:
            logger.info(
                f"Scheduled backup complete: {result.timestamp}",
                extra={
                    "event_type": "scheduled_backup_complete",
                    "timestamp": result.timestamp,
                    "size_bytes": result.size_bytes
                }
            )

            # Cleanup old backups based on retention
            deleted = backup_service.cleanup_old_backups(keep_count=keep_count)
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old backups (keeping {keep_count})")
        else:
            logger.error(f"Scheduled backup failed: {result.message}")

    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}", exc_info=True)


async def scheduled_pattern_calculation_job():
    """
    Scheduled pattern calculation job that runs hourly (Story P4-3.5)

    Recalculates activity patterns for all enabled cameras based on their
    historical event data. Patterns are used to provide timing context in AI descriptions.
    """
    try:
        logger.info("Starting scheduled pattern calculation")

        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            # Get pattern service and recalculate all patterns
            pattern_service = get_pattern_service()
            result = await pattern_service.recalculate_all_patterns(db)

            logger.info(
                f"Scheduled pattern calculation complete: {result['patterns_calculated']} patterns updated, "
                f"{result['patterns_skipped']} skipped",
                extra={
                    "event_type": "scheduled_pattern_calculation_complete",
                    **result
                }
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Scheduled pattern calculation failed: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler for startup and shutdown events.

    Manages the application lifecycle:
    - Startup: Creates database tables and initializes resources
    - Shutdown: Stops camera threads and cleans up resources
    """
    global scheduler

    # Startup logic with structured logging (Story 6.2)
    logger.info(
        "Application starting",
        extra={
            "event_type": "app_startup",
            "version": APP_VERSION,
            "log_level": settings.LOG_LEVEL,
            "debug_mode": settings.DEBUG,
        }
    )

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info(
        "Database initialized",
        extra={"event_type": "database_init", "status": "success"}
    )

    # Ensure admin user exists (Story 6.3)
    from app.core.database import get_db
    setup_db = next(get_db())
    try:
        created, password = ensure_admin_exists(setup_db)
        if created:
            logger.info(
                "Default admin user created - SAVE THIS PASSWORD",
                extra={
                    "event_type": "admin_setup",
                    "username": "admin",
                    "password": password,  # Only logged on first creation
                }
            )
            print(f"\n{'='*60}")
            print("INITIAL SETUP - SAVE THIS INFORMATION")
            print(f"{'='*60}")
            print(f"Username: admin")
            print(f"Password: {password}")
            print(f"{'='*60}\n")
    finally:
        setup_db.close()

    # Create thumbnails directory
    thumbnail_dir = os.path.join(os.path.dirname(__file__), 'data', 'thumbnails')
    os.makedirs(thumbnail_dir, exist_ok=True)
    logger.info(
        "Thumbnails directory ready",
        extra={"event_type": "directory_init", "path": thumbnail_dir}
    )

    # Initialize Event Processor (Story 3.3)
    await initialize_event_processor()
    logger.info(
        "Event processor started",
        extra={"event_type": "event_processor_init", "status": "running"}
    )

    # Initialize APScheduler for daily cleanup (Story 3.4)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_cleanup_job,
        trigger=CronTrigger(hour=2, minute=0),  # Daily at 2:00 AM
        id="daily_cleanup",
        name="Daily event cleanup based on retention policy",
        replace_existing=True
    )

    # Add system metrics update job (every minute)
    scheduler.add_job(
        update_system_metrics,
        trigger=CronTrigger(minute="*"),  # Every minute
        id="system_metrics_update",
        name="Update system resource metrics",
        replace_existing=True
    )

    # Add automatic backup job (Story 6.4) - Daily at 3:00 AM
    scheduler.add_job(
        scheduled_backup_job,
        trigger=CronTrigger(hour=3, minute=0),  # Daily at 3:00 AM
        id="daily_backup",
        name="Daily automatic backup (if enabled)",
        replace_existing=True
    )

    # Add pattern calculation job (Story P4-3.5) - Hourly
    scheduler.add_job(
        scheduled_pattern_calculation_job,
        trigger=CronTrigger(minute=0),  # Every hour at :00
        id="hourly_pattern_calculation",
        name="Hourly activity pattern calculation",
        replace_existing=True
    )

    scheduler.start()
    logger.info(
        "Scheduler started",
        extra={
            "event_type": "scheduler_init",
            "jobs": ["daily_cleanup", "system_metrics_update", "daily_backup", "hourly_pattern_calculation"]
        }
    )

    # Start enabled cameras on startup (Story 4.3)
    from app.core.database import get_db
    from app.models.camera import Camera
    from app.core.metrics import record_camera_status
    import asyncio

    # Set the main event loop for camera service (needed for thread-safe async calls)
    camera_service.set_event_loop(asyncio.get_running_loop())

    db = next(get_db())
    try:
        enabled_cameras = db.query(Camera).filter(Camera.is_enabled == True).all()
        total_cameras = db.query(Camera).count()
        started_count = 0

        logger.info(
            "Starting cameras",
            extra={
                "event_type": "camera_startup",
                "enabled_count": len(enabled_cameras),
                "total_count": total_cameras
            }
        )

        # Small delay to ensure network stack is ready (helps with immediate RTSP connections)
        import time
        time.sleep(1)

        for camera in enabled_cameras:
            success = camera_service.start_camera(camera)
            if success:
                started_count += 1
                logger.info(
                    "Camera started",
                    extra={
                        "event_type": "camera_connected",
                        "camera_id": str(camera.id),
                        "camera_name": camera.name
                    }
                )
            else:
                logger.warning(
                    "Camera failed to start",
                    extra={
                        "event_type": "camera_connection_failed",
                        "camera_id": str(camera.id),
                        "camera_name": camera.name
                    }
                )

        # Update camera metrics
        record_camera_status(started_count, total_cameras)

    finally:
        db.close()

    # Connect to Protect controllers on startup (Story P2-1.4, AC1)
    from app.models.protect_controller import ProtectController
    protect_service = get_protect_service()

    db = next(get_db())
    try:
        # Initialize app.state.protect_connections (AC9)
        # Note: app is not in scope here yet, so we store in service

        protect_controllers = db.query(ProtectController).all()
        protect_started_count = 0

        if protect_controllers:
            logger.info(
                "Starting Protect controllers",
                extra={
                    "event_type": "protect_startup",
                    "controller_count": len(protect_controllers)
                }
            )

            for controller in protect_controllers:
                try:
                    success = await protect_service.connect(controller)
                    if success:
                        protect_started_count += 1
                        logger.info(
                            "Protect controller connected",
                            extra={
                                "event_type": "protect_controller_connected",
                                "controller_id": str(controller.id),
                                "controller_name": controller.name
                            }
                        )
                    else:
                        logger.warning(
                            "Protect controller failed to connect",
                            extra={
                                "event_type": "protect_controller_connection_failed",
                                "controller_id": str(controller.id),
                                "controller_name": controller.name
                            }
                        )
                except Exception as e:
                    # AC8: One failing controller doesn't affect others
                    logger.error(
                        f"Exception connecting Protect controller: {e}",
                        extra={
                            "event_type": "protect_controller_connection_error",
                            "controller_id": str(controller.id),
                            "error": str(e)
                        }
                    )

            logger.info(
                "Protect controllers startup complete",
                extra={
                    "event_type": "protect_startup_complete",
                    "started_count": protect_started_count,
                    "total_count": len(protect_controllers)
                }
            )
    finally:
        db.close()

    # Initialize MQTT service (Story P4-2.1, AC1, AC2)
    try:
        await initialize_mqtt_service()
        logger.info(
            "MQTT service initialized",
            extra={"event_type": "mqtt_init_complete"}
        )

        # Initialize MQTT discovery service (Story P4-2.2)
        # Must be after MQTT service to register on_connect callback
        await initialize_discovery_service()
        logger.info(
            "MQTT discovery service initialized",
            extra={"event_type": "mqtt_discovery_init_complete"}
        )

        # Initialize MQTT status sensors (Story P4-2.5)
        # Publishes initial camera statuses and sets up scheduler for count updates
        await initialize_status_sensors()
        logger.info(
            "MQTT status sensors initialized",
            extra={"event_type": "mqtt_status_sensors_init_complete"}
        )
    except Exception as e:
        # MQTT failure should not prevent app startup
        logger.warning(
            f"MQTT initialization failed (non-fatal): {e}",
            extra={"event_type": "mqtt_init_failed", "error": str(e)}
        )

    # Initialize Digest Scheduler (Story P4-4.2)
    try:
        await initialize_digest_scheduler()
        logger.info(
            "Digest scheduler initialized",
            extra={"event_type": "digest_scheduler_init_complete"}
        )
    except Exception as e:
        # Digest scheduler failure should not prevent app startup
        logger.warning(
            f"Digest scheduler initialization failed (non-fatal): {e}",
            extra={"event_type": "digest_scheduler_init_failed", "error": str(e)}
        )

    # Initialize HomeKit service (Story P4-6.1)
    # Only starts if HOMEKIT_ENABLED=true or homekit_enabled setting is true
    try:
        from app.models.system_setting import SystemSetting

        homekit_db = next(get_db())
        try:
            # Check database setting (takes precedence over env var)
            homekit_setting = homekit_db.query(SystemSetting).filter(
                SystemSetting.key == "homekit_enabled"
            ).first()

            homekit_service = get_homekit_service()

            # Use database setting if exists, otherwise env var
            if homekit_setting:
                homekit_enabled = homekit_setting.value.lower() in ('true', '1', 'yes')
                homekit_service.config.enabled = homekit_enabled
            else:
                homekit_enabled = homekit_service.config.enabled

            if homekit_enabled:
                # Get enabled cameras for HomeKit
                homekit_cameras = homekit_db.query(Camera).filter(Camera.is_enabled == True).all()
                success = await homekit_service.start(homekit_cameras)

                if success:
                    logger.info(
                        "HomeKit service started",
                        extra={
                            "event_type": "homekit_init_complete",
                            "camera_count": len(homekit_cameras),
                            "port": homekit_service.config.port
                        }
                    )
                else:
                    logger.warning(
                        f"HomeKit service failed to start: {homekit_service._error}",
                        extra={"event_type": "homekit_init_failed", "error": homekit_service._error}
                    )
            else:
                logger.debug(
                    "HomeKit service disabled",
                    extra={"event_type": "homekit_disabled"}
                )
        finally:
            homekit_db.close()
    except Exception as e:
        # HomeKit failure should not prevent app startup
        logger.warning(
            f"HomeKit initialization failed (non-fatal): {e}",
            extra={"event_type": "homekit_init_failed", "error": str(e)}
        )

    logger.info(
        "Application startup complete",
        extra={
            "event_type": "app_startup_complete",
            "version": APP_VERSION,
            "cameras_started": started_count if 'started_count' in dir() else 0
        }
    )

    yield  # Application runs here

    # Shutdown logic with structured logging
    logger.info(
        "Application shutting down",
        extra={"event_type": "app_shutdown_start", "version": APP_VERSION}
    )

    # Shutdown Digest Scheduler (Story P4-4.2)
    try:
        await shutdown_digest_scheduler()
        logger.info(
            "Digest scheduler stopped",
            extra={"event_type": "digest_scheduler_shutdown_complete"}
        )
    except Exception as e:
        logger.error(
            f"Error stopping digest scheduler: {e}",
            extra={"event_type": "digest_scheduler_shutdown_error", "error": str(e)}
        )

    # Shutdown HomeKit service (Story P4-6.1)
    try:
        homekit_service = get_homekit_service()
        if homekit_service.is_running:
            await homekit_service.stop()
            logger.info(
                "HomeKit service stopped",
                extra={"event_type": "homekit_shutdown_complete"}
            )
    except Exception as e:
        logger.error(
            f"Error stopping HomeKit service: {e}",
            extra={"event_type": "homekit_shutdown_error", "error": str(e)}
        )

    # Disconnect MQTT service (Story P4-2.1)
    try:
        await shutdown_mqtt_service()
        logger.info(
            "MQTT service disconnected",
            extra={"event_type": "mqtt_shutdown_complete"}
        )
    except Exception as e:
        logger.error(
            f"Error disconnecting MQTT: {e}",
            extra={"event_type": "mqtt_shutdown_error", "error": str(e)}
        )

    # Disconnect Protect controllers (Story P2-1.4, AC5)
    # Must happen before other services shutdown
    try:
        await protect_service.disconnect_all(timeout=10.0)
        logger.info(
            "Protect controllers disconnected",
            extra={"event_type": "protect_shutdown_complete"}
        )
    except Exception as e:
        logger.error(
            f"Error disconnecting Protect controllers: {e}",
            extra={"event_type": "protect_shutdown_error", "error": str(e)}
        )

    # Stop scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info(
            "Scheduler stopped",
            extra={"event_type": "scheduler_shutdown"}
        )

    # Stop Event Processor (Story 3.3)
    await shutdown_event_processor(timeout=30.0)
    logger.info(
        "Event processor stopped",
        extra={"event_type": "event_processor_shutdown"}
    )

    # Stop all camera threads
    camera_service.stop_all_cameras(timeout=5.0)
    logger.info(
        "Cameras stopped",
        extra={"event_type": "cameras_shutdown"}
    )

    logger.info(
        "Application shutdown complete",
        extra={"event_type": "app_shutdown_complete", "version": APP_VERSION}
    )


# Create FastAPI app
app = FastAPI(
    title="ArgusAI API",
    description="API for camera-based motion detection and AI-powered object description",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add rate limiter state (Story 6.3)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom exception handler to ensure CORS headers on HTTPException responses
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

@app.exception_handler(HTTPException)
async def cors_http_exception_handler(request: Request, exc: HTTPException):
    """
    Custom HTTPException handler that ensures CORS headers are included.
    This is needed because HTTPException responses bypass CORS middleware.
    """
    # Get origin from request
    origin = request.headers.get("origin", "")

    # Build CORS headers if origin is allowed
    cors_headers = {}
    if origin in settings.CORS_ORIGINS or "*" in settings.CORS_ORIGINS:
        cors_headers = {
            "Access-Control-Allow-Origin": origin or settings.CORS_ORIGINS[0],
            "Access-Control-Allow-Credentials": "true",
        }

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=cors_headers,
    )

# Add request logging middleware (Story 6.2, AC: #2)
app.add_middleware(RequestLoggingMiddleware)

# Add authentication middleware (Story 6.3, AC: #6)
# Note: Auth middleware runs after logging middleware (LIFO order)
app.add_middleware(AuthMiddleware)

# Register API routers
# Note: Register motion_events before cameras to ensure proper route precedence
app.include_router(motion_events_router, prefix=settings.API_V1_PREFIX)
app.include_router(cameras_router, prefix=settings.API_V1_PREFIX)
app.include_router(ai_router, prefix=settings.API_V1_PREFIX)
app.include_router(events_router, prefix=settings.API_V1_PREFIX)
app.include_router(metrics_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)  # Story 3.4
app.include_router(alert_rules_router, prefix=settings.API_V1_PREFIX)  # Story 5.1
app.include_router(webhooks_router, prefix=settings.API_V1_PREFIX)  # Story 5.3
app.include_router(notifications_router, prefix=settings.API_V1_PREFIX)  # Story 5.4
app.include_router(websocket_router)  # Story 5.4 - WebSocket at /ws (no prefix)
app.include_router(logs_router, prefix=settings.API_V1_PREFIX)  # Story 6.2 - Log retrieval
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)  # Story 6.3 - Authentication
app.include_router(protect_router, prefix=settings.API_V1_PREFIX)  # Story P2-1.1 - UniFi Protect
app.include_router(system_notifications_router, prefix=settings.API_V1_PREFIX)  # Story P3-7.4 - Cost Alerts
app.include_router(push_router, prefix=settings.API_V1_PREFIX)  # Story P4-1.1 - Web Push
app.include_router(integrations_router, prefix=settings.API_V1_PREFIX)  # Story P4-2.1 - MQTT
app.include_router(context_router, prefix=settings.API_V1_PREFIX)  # Story P4-3.1 - Embeddings
app.include_router(summaries_router, prefix=settings.API_V1_PREFIX)  # Story P4-4.1 - Activity Summaries
app.include_router(digests_router, prefix=settings.API_V1_PREFIX)  # Story P4-4.2 - Daily Digest Scheduler
app.include_router(feedback_router, prefix=settings.API_V1_PREFIX)  # Story P4-5.2 - Feedback Statistics

# Thumbnail serving endpoint (with CORS support)
from fastapi.responses import FileResponse, Response as FastAPIResponse

@app.get("/api/v1/thumbnails/{date}/{filename}")
async def get_thumbnail(date: str, filename: str):
    """Serve thumbnail images (CORS handled by middleware)"""
    thumbnail_dir = os.path.join(os.path.dirname(__file__), 'data', 'thumbnails')
    file_path = os.path.join(thumbnail_dir, date, filename)

    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            content = f.read()
        return FastAPIResponse(
            content=content,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400"
            }
        )

    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Thumbnail not found")


@app.get("/")
async def root():
    """Root endpoint - API status check"""
    return {
        "name": "ArgusAI API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint (no authentication required)"""
    return {
        "status": "healthy",
        "camera_count": len(camera_service.get_all_camera_status())
    }


@app.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics endpoint (Story 6.2, AC: #6)

    Returns Prometheus-compatible metrics for scraping.
    """
    return Response(
        content=get_metrics(),
        media_type=get_content_type()
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
