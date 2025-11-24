"""
FastAPI application entry point for Live Object AI Classifier

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
from app.api.v1.cameras import router as cameras_router, camera_service
from app.api.v1.motion_events import router as motion_events_router
from app.api.v1.ai import router as ai_router
from app.api.v1.events import router as events_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.system import router as system_router, get_retention_policy_from_db
from app.api.v1.alert_rules import router as alert_rules_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.websocket import router as websocket_router
from app.api.v1.logs import router as logs_router
from app.services.event_processor import initialize_event_processor, shutdown_event_processor
from app.services.cleanup_service import get_cleanup_service

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

    scheduler.start()
    logger.info(
        "Scheduler started",
        extra={
            "event_type": "scheduler_init",
            "jobs": ["daily_cleanup", "system_metrics_update"]
        }
    )

    # Start enabled cameras on startup (Story 4.3)
    from app.core.database import get_db
    from app.models.camera import Camera
    from app.core.metrics import record_camera_status

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
    title="Live Object AI Classifier API",
    description="API for camera-based motion detection and AI-powered object description",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request logging middleware (Story 6.2, AC: #2)
app.add_middleware(RequestLoggingMiddleware)

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

# Thumbnail serving endpoint (with CORS support)
from fastapi.responses import FileResponse, Response as FastAPIResponse

@app.get("/api/v1/thumbnails/{date}/{filename}")
async def get_thumbnail(date: str, filename: str):
    """Serve thumbnail images with CORS support"""
    thumbnail_dir = os.path.join(os.path.dirname(__file__), 'data', 'thumbnails')
    file_path = os.path.join(thumbnail_dir, date, filename)

    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            content = f.read()
        return FastAPIResponse(
            content=content,
            media_type="image/jpeg",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=86400"
            }
        )

    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Thumbnail not found")


@app.get("/")
async def root():
    """Root endpoint - API status check"""
    return {
        "name": "Live Object AI Classifier API",
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
