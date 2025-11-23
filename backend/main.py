"""
FastAPI application entry point for Live Object AI Classifier

Initializes the FastAPI app, registers routers, and sets up startup/shutdown events.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1.cameras import router as cameras_router, camera_service
from app.api.v1.motion_events import router as motion_events_router
from app.api.v1.ai import router as ai_router
from app.api.v1.events import router as events_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.system import router as system_router, get_retention_policy_from_db
from app.api.v1.alert_rules import router as alert_rules_router
from app.services.event_processor import initialize_event_processor, shutdown_event_processor
from app.services.cleanup_service import get_cleanup_service

# Configure logging
import os
from logging.handlers import RotatingFileHandler

# Ensure log directory exists
log_dir = os.path.join(os.path.dirname(__file__), 'data', 'logs')
os.makedirs(log_dir, exist_ok=True)

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add file handler for AI service logs
ai_service_logger = logging.getLogger('app.services.ai_service')
ai_service_log_file = os.path.join(log_dir, 'ai_service.log')
ai_file_handler = RotatingFileHandler(
    ai_service_log_file,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
ai_file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)
ai_service_logger.addHandler(ai_file_handler)

logger = logging.getLogger(__name__)

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

    # Startup logic
    logger.info("Application starting up...")

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Create thumbnails directory
    thumbnail_dir = os.path.join(os.path.dirname(__file__), 'data', 'thumbnails')
    os.makedirs(thumbnail_dir, exist_ok=True)
    logger.info(f"Thumbnails directory: {thumbnail_dir}")

    # Initialize Event Processor (Story 3.3)
    await initialize_event_processor()
    logger.info("Event processor initialized and started")

    # Initialize APScheduler for daily cleanup (Story 3.4)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_cleanup_job,
        trigger=CronTrigger(hour=2, minute=0),  # Daily at 2:00 AM
        id="daily_cleanup",
        name="Daily event cleanup based on retention policy",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Cleanup scheduler initialized (daily at 2:00 AM)")

    # Start enabled cameras on startup (Story 4.3)
    from app.core.database import get_db
    from app.models.camera import Camera
    db = next(get_db())
    try:
        enabled_cameras = db.query(Camera).filter(Camera.is_enabled == True).all()
        logger.info(f"Starting {len(enabled_cameras)} enabled cameras...")
        for camera in enabled_cameras:
            success = camera_service.start_camera(camera)
            if success:
                logger.info(f"Started camera: {camera.name} ({camera.id})")
            else:
                logger.warning(f"Failed to start camera: {camera.name} ({camera.id})")
    finally:
        db.close()

    logger.info("Application startup complete")

    yield  # Application runs here

    # Shutdown logic
    logger.info("Application shutting down...")

    # Stop scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Cleanup scheduler stopped")

    # Stop Event Processor (Story 3.3)
    await shutdown_event_processor(timeout=30.0)
    logger.info("Event processor stopped")

    # Stop all camera threads
    camera_service.stop_all_cameras(timeout=5.0)

    logger.info("Application shutdown complete")


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

# Register API routers
# Note: Register motion_events before cameras to ensure proper route precedence
app.include_router(motion_events_router, prefix=settings.API_V1_PREFIX)
app.include_router(cameras_router, prefix=settings.API_V1_PREFIX)
app.include_router(ai_router, prefix=settings.API_V1_PREFIX)
app.include_router(events_router, prefix=settings.API_V1_PREFIX)
app.include_router(metrics_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)  # Story 3.4
app.include_router(alert_rules_router, prefix=settings.API_V1_PREFIX)  # Story 5.1


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
