"""
FastAPI application entry point for Live Object AI Classifier

Initializes the FastAPI app, registers routers, and sets up startup/shutdown events.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1.cameras import router as cameras_router, camera_service
from app.api.v1.motion_events import router as motion_events_router

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Live Object AI Classifier API",
    description="API for camera-based motion detection and AI-powered object description",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
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


@app.on_event("startup")
async def startup_event():
    """
    Application startup event handler

    - Creates database tables if they don't exist
    - Loads enabled cameras and starts capture threads
    """
    logger.info("Application starting up...")

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # TODO: Load enabled cameras and start capture threads
    # from app.core.database import SessionLocal
    # from app.models.camera import Camera
    #
    # db = SessionLocal()
    # try:
    #     enabled_cameras = db.query(Camera).filter(Camera.is_enabled == True).all()
    #     for camera in enabled_cameras:
    #         camera_service.start_camera(camera)
    #     logger.info(f"Started {len(enabled_cameras)} enabled cameras")
    # finally:
    #     db.close()

    logger.info("Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Application shutdown event handler

    - Stops all running camera capture threads
    - Cleans up resources
    """
    logger.info("Application shutting down...")

    # Stop all camera threads
    camera_service.stop_all_cameras(timeout=5.0)

    logger.info("Application shutdown complete")


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
