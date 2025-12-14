"""
HomeKit API endpoints (Story P5-1.1)

Endpoints for HomeKit bridge configuration and management:
- GET /api/v1/homekit/status - Get HomeKit bridge status
- POST /api/v1/homekit/enable - Enable HomeKit bridge
- POST /api/v1/homekit/disable - Disable HomeKit bridge
- GET /api/v1/homekit/qrcode - Get pairing QR code (PNG image)
- POST /api/v1/homekit/reset - Reset pairing state
"""
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict

from app.core.database import get_db
from app.models.homekit import HomeKitConfig, HomeKitAccessory
from app.models.camera import Camera
from app.services.homekit_service import get_homekit_service, HomekitStatus
from app.config.homekit import generate_pincode

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/homekit",
    tags=["homekit"]
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class HomeKitStatusResponse(BaseModel):
    """HomeKit bridge status response."""
    enabled: bool = Field(..., description="Whether HomeKit is enabled in config")
    running: bool = Field(..., description="Whether bridge is currently running")
    paired: bool = Field(..., description="Whether any iOS devices are paired")
    accessory_count: int = Field(..., description="Number of motion sensor accessories in bridge")
    camera_count: int = Field(0, description="Number of camera accessories (Story P5-1.3)")
    active_streams: int = Field(0, description="Currently active camera streams (Story P5-1.3)")
    bridge_name: str = Field(..., description="Bridge name shown in Apple Home")
    setup_code: Optional[str] = Field(None, description="Pairing code (hidden if paired)")
    setup_uri: Optional[str] = Field(None, description="X-HM:// Setup URI for QR code (Story P5-1.2)")
    port: int = Field(..., description="HAP server port")
    ffmpeg_available: bool = Field(False, description="Whether ffmpeg is available for streaming (Story P5-1.3)")
    error: Optional[str] = Field(None, description="Error message if any")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": True,
                "running": True,
                "paired": False,
                "accessory_count": 3,
                "camera_count": 3,
                "active_streams": 1,
                "bridge_name": "ArgusAI",
                "setup_code": "123-45-678",
                "setup_uri": "X-HM://0023B6WQLAB1C",
                "port": 51826,
                "ffmpeg_available": True,
                "error": None
            }
        }
    )


class HomeKitEnableRequest(BaseModel):
    """Request body for enabling HomeKit."""
    bridge_name: Optional[str] = Field("ArgusAI", max_length=64, description="Bridge display name")
    port: Optional[int] = Field(51826, ge=1024, le=65535, description="HAP server port")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "bridge_name": "ArgusAI",
                "port": 51826
            }
        }
    )


class HomeKitEnableResponse(BaseModel):
    """Response after enabling HomeKit."""
    enabled: bool = True
    running: bool
    port: int
    setup_code: str = Field(..., description="Pairing code in XXX-XX-XXX format")
    setup_uri: Optional[str] = Field(None, description="X-HM:// Setup URI for QR code (Story P5-1.2)")
    qr_code_data: Optional[str] = Field(None, description="Base64 PNG QR code for pairing")
    bridge_name: str
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": True,
                "running": True,
                "port": 51826,
                "setup_code": "123-45-678",
                "setup_uri": "X-HM://0023B6WQLAB1C",
                "qr_code_data": "data:image/png;base64,...",
                "bridge_name": "ArgusAI",
                "message": "HomeKit bridge enabled successfully"
            }
        }
    )


class HomeKitDisableResponse(BaseModel):
    """Response after disabling HomeKit."""
    enabled: bool = False
    running: bool = False
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": False,
                "running": False,
                "message": "HomeKit bridge disabled"
            }
        }
    )


class HomeKitConfigResponse(BaseModel):
    """HomeKit configuration response."""
    id: int
    enabled: bool
    bridge_name: str
    port: int
    motion_reset_seconds: int
    max_motion_duration: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "enabled": True,
                "bridge_name": "ArgusAI",
                "port": 51826,
                "motion_reset_seconds": 30,
                "max_motion_duration": 300,
                "created_at": "2025-12-14T10:00:00Z",
                "updated_at": "2025-12-14T10:00:00Z"
            }
        }
    )


# ============================================================================
# Helper Functions
# ============================================================================


def get_or_create_config(db: Session) -> HomeKitConfig:
    """
    Get or create the singleton HomeKit config row.

    Returns:
        HomeKitConfig instance (creates with defaults if not exists)
    """
    config = db.query(HomeKitConfig).filter(HomeKitConfig.id == 1).first()

    if not config:
        # Create default config with generated PIN
        config = HomeKitConfig(
            id=1,
            enabled=False,
            bridge_name="ArgusAI",
            port=51826,
            motion_reset_seconds=30,
            max_motion_duration=300
        )
        # Generate and encrypt PIN code
        pin_code = generate_pincode()
        config.set_pin_code(pin_code)

        db.add(config)
        db.commit()
        db.refresh(config)

        logger.info(
            "Created default HomeKit config",
            extra={"event_type": "homekit_config_created", "port": config.port}
        )

    return config


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/status", response_model=HomeKitStatusResponse)
async def get_homekit_status(db: Session = Depends(get_db)):
    """
    Get HomeKit bridge status.

    Returns current status including:
    - Whether HomeKit is enabled and running
    - Pairing status
    - Number of accessories
    - Setup code and URI (hidden if already paired) - Story P5-1.2
    """
    try:
        # Get config from database
        config = get_or_create_config(db)

        # Get service status
        service = get_homekit_service()
        service_status = service.get_status()

        # Merge database config with runtime status
        # Story P5-1.2 AC4: Hide setup_code and setup_uri when paired
        return HomeKitStatusResponse(
            enabled=config.enabled,
            running=service_status.running,
            paired=service_status.paired,
            accessory_count=service_status.accessory_count,
            camera_count=service_status.camera_count,  # Story P5-1.3
            active_streams=service_status.active_streams,  # Story P5-1.3
            bridge_name=config.bridge_name,
            setup_code=config.get_pin_code() if not service_status.paired else None,
            setup_uri=service_status.setup_uri,  # Story P5-1.2: Include X-HM:// URI
            port=config.port,
            ffmpeg_available=service_status.ffmpeg_available,  # Story P5-1.3
            error=service_status.error
        )

    except Exception as e:
        logger.error(f"Failed to get HomeKit status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get HomeKit status: {str(e)}"
        )


@router.post("/enable", response_model=HomeKitEnableResponse)
async def enable_homekit(
    request: HomeKitEnableRequest = None,
    db: Session = Depends(get_db)
):
    """
    Enable the HomeKit bridge.

    Creates or updates the HomeKit configuration and starts the bridge.
    Returns the setup code and QR code for pairing with Apple Home.
    """
    try:
        # Get or create config
        config = get_or_create_config(db)

        # Update config from request
        if request:
            if request.bridge_name:
                config.bridge_name = request.bridge_name
            if request.port:
                config.port = request.port

        # Generate PIN code if not set
        if not config.pin_code:
            pin_code = generate_pincode()
            config.set_pin_code(pin_code)

        # Mark as enabled
        config.enabled = True
        db.commit()
        db.refresh(config)

        # Update service config and start
        service = get_homekit_service()

        # Update service config from database
        service.config.enabled = True
        service.config.bridge_name = config.bridge_name
        service.config.port = config.port
        service._pincode = config.get_pin_code()

        # Get cameras and start service
        cameras = db.query(Camera).filter(Camera.is_enabled == True).all()
        success = await service.start(cameras)

        if not success:
            error_msg = service._error or "Failed to start HomeKit bridge"
            logger.error(f"HomeKit enable failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )

        logger.info(
            "HomeKit bridge enabled",
            extra={
                "event_type": "homekit_enabled",
                "port": config.port,
                "camera_count": len(cameras)
            }
        )

        # Story P5-1.2: Include setup_uri in response
        return HomeKitEnableResponse(
            enabled=True,
            running=service.is_running,
            port=config.port,
            setup_code=config.get_pin_code(),
            setup_uri=service.get_setup_uri(),
            qr_code_data=service.get_qr_code_data(),
            bridge_name=config.bridge_name,
            message=f"HomeKit bridge enabled with {len(cameras)} cameras"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable HomeKit: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable HomeKit: {str(e)}"
        )


@router.post("/disable", response_model=HomeKitDisableResponse)
async def disable_homekit(db: Session = Depends(get_db)):
    """
    Disable the HomeKit bridge.

    Stops the bridge and marks it as disabled in the database.
    Existing pairings are preserved for when HomeKit is re-enabled.
    """
    try:
        # Get config
        config = db.query(HomeKitConfig).filter(HomeKitConfig.id == 1).first()

        if config:
            config.enabled = False
            db.commit()

        # Stop service
        service = get_homekit_service()
        await service.stop()

        logger.info(
            "HomeKit bridge disabled",
            extra={"event_type": "homekit_disabled"}
        )

        return HomeKitDisableResponse(
            enabled=False,
            running=False,
            message="HomeKit bridge disabled"
        )

    except Exception as e:
        logger.error(f"Failed to disable HomeKit: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable HomeKit: {str(e)}"
        )


@router.get("/qrcode")
async def get_qrcode(db: Session = Depends(get_db)):
    """
    Get the pairing QR code as a PNG image.

    Returns a PNG image that can be scanned in the Apple Home app
    to pair with the HomeKit bridge.
    """
    try:
        service = get_homekit_service()

        if not service.is_available:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="HAP-python not installed. Install with: pip install HAP-python"
            )

        qr_data = service.get_qr_code_data()

        if not qr_data:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="QR code generation not available. Install qrcode package."
            )

        # Parse base64 data URL and return as PNG
        if qr_data.startswith("data:image/png;base64,"):
            import base64
            png_data = base64.b64decode(qr_data.split(",")[1])
            return Response(
                content=png_data,
                media_type="image/png",
                headers={"Content-Disposition": "inline; filename=homekit-pairing.png"}
            )

        # Fallback - return as is
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected QR code format"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate QR code: {str(e)}"
        )


@router.post("/reset")
async def reset_pairing(db: Session = Depends(get_db)):
    """
    Reset HomeKit pairing state.

    This removes all paired devices and generates a new PIN code.
    The bridge will need to be re-paired with Apple Home after reset.
    """
    try:
        service = get_homekit_service()

        # Reset pairing in service
        success = await service.reset_pairing()

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset HomeKit pairing"
            )

        # Generate new PIN code and save to database
        config = get_or_create_config(db)
        new_pin = generate_pincode()
        config.set_pin_code(new_pin)
        db.commit()

        # Update service with new PIN
        service._pincode = new_pin

        logger.info(
            "HomeKit pairing reset",
            extra={"event_type": "homekit_pairing_reset"}
        )

        return {
            "success": True,
            "message": "HomeKit pairing reset. All devices unpaired.",
            "new_setup_code": new_pin
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset HomeKit pairing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset pairing: {str(e)}"
        )


@router.get("/config", response_model=HomeKitConfigResponse)
async def get_homekit_config(db: Session = Depends(get_db)):
    """
    Get HomeKit configuration (without sensitive data).

    Returns the current configuration settings for the HomeKit bridge.
    PIN code is not included in the response.
    """
    try:
        config = get_or_create_config(db)

        return HomeKitConfigResponse(
            id=config.id,
            enabled=config.enabled,
            bridge_name=config.bridge_name,
            port=config.port,
            motion_reset_seconds=config.motion_reset_seconds,
            max_motion_duration=config.max_motion_duration,
            created_at=config.created_at.isoformat() if config.created_at else None,
            updated_at=config.updated_at.isoformat() if config.updated_at else None
        )

    except Exception as e:
        logger.error(f"Failed to get HomeKit config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get config: {str(e)}"
        )
