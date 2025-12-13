"""
Integrations API endpoints (Story P4-2.1)

Endpoints for MQTT and other external integrations:
- GET /api/v1/integrations/mqtt/config - Get MQTT configuration
- PUT /api/v1/integrations/mqtt/config - Update MQTT configuration
- GET /api/v1/integrations/mqtt/status - Get connection status
- POST /api/v1/integrations/mqtt/test - Test connection
- POST /api/v1/integrations/mqtt/publish-discovery - Publish HA discovery
"""
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator

from app.core.database import get_db
from app.models.mqtt_config import MQTTConfig
from app.services.mqtt_service import get_mqtt_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/integrations",
    tags=["integrations"]
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class MQTTConfigResponse(BaseModel):
    """MQTT configuration response (password omitted)."""
    id: str
    broker_host: str
    broker_port: int
    username: Optional[str] = None
    topic_prefix: str
    discovery_prefix: str
    discovery_enabled: bool
    qos: int
    enabled: bool
    retain_messages: bool
    use_tls: bool
    has_password: bool = Field(..., description="Whether password is configured")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "broker_host": "192.168.1.100",
                "broker_port": 1883,
                "username": "homeassistant",
                "topic_prefix": "liveobject",
                "discovery_prefix": "homeassistant",
                "discovery_enabled": True,
                "qos": 1,
                "enabled": True,
                "retain_messages": True,
                "use_tls": False,
                "has_password": True,
                "created_at": "2025-12-10T10:00:00Z",
                "updated_at": "2025-12-10T10:00:00Z"
            }
        }


class MQTTConfigUpdate(BaseModel):
    """Request body for updating MQTT configuration."""
    broker_host: str = Field(..., min_length=1, max_length=255, description="MQTT broker hostname or IP")
    broker_port: int = Field(1883, ge=1, le=65535, description="MQTT broker port")
    username: Optional[str] = Field(None, max_length=100, description="Authentication username")
    password: Optional[str] = Field(None, max_length=500, description="Authentication password (plain text)")
    topic_prefix: str = Field("liveobject", max_length=100, description="MQTT topic prefix")
    discovery_prefix: str = Field("homeassistant", max_length=100, description="Home Assistant discovery prefix")
    discovery_enabled: bool = Field(True, description="Enable Home Assistant discovery")
    qos: int = Field(1, ge=0, le=2, description="Quality of Service level (0, 1, or 2)")
    enabled: bool = Field(True, description="Enable MQTT publishing")
    retain_messages: bool = Field(True, description="Retain messages on broker")
    use_tls: bool = Field(False, description="Use TLS/SSL connection")

    @field_validator('qos')
    @classmethod
    def validate_qos(cls, v: int) -> int:
        if v not in (0, 1, 2):
            raise ValueError('QoS must be 0, 1, or 2')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "broker_host": "192.168.1.100",
                "broker_port": 1883,
                "username": "homeassistant",
                "password": "mqtt_password",
                "topic_prefix": "liveobject",
                "discovery_prefix": "homeassistant",
                "discovery_enabled": True,
                "qos": 1,
                "enabled": True,
                "retain_messages": True,
                "use_tls": False
            }
        }


class MQTTTestRequest(BaseModel):
    """Request body for testing MQTT connection."""
    broker_host: str = Field(..., min_length=1, max_length=255)
    broker_port: int = Field(1883, ge=1, le=65535)
    username: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, max_length=500)
    use_tls: bool = Field(False)

    class Config:
        json_schema_extra = {
            "example": {
                "broker_host": "192.168.1.100",
                "broker_port": 1883,
                "username": "homeassistant",
                "password": "mqtt_password",
                "use_tls": False
            }
        }


class MQTTTestResponse(BaseModel):
    """Response for MQTT connection test."""
    success: bool
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Connected to 192.168.1.100:1883"
            }
        }


class MQTTStatusResponse(BaseModel):
    """MQTT connection status response."""
    connected: bool
    broker: Optional[str] = None
    last_connected_at: Optional[str] = None
    messages_published: int
    last_error: Optional[str] = None
    reconnect_attempt: int = 0

    class Config:
        json_schema_extra = {
            "example": {
                "connected": True,
                "broker": "192.168.1.100:1883",
                "last_connected_at": "2025-12-10T10:00:00Z",
                "messages_published": 1234,
                "last_error": None,
                "reconnect_attempt": 0
            }
        }


class PublishDiscoveryResponse(BaseModel):
    """Response for publishing discovery configs."""
    success: bool
    message: str
    cameras_published: int = 0

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Published discovery for 5 cameras",
                "cameras_published": 5
            }
        }


# ============================================================================
# MQTT Configuration Endpoints
# ============================================================================


@router.get("/mqtt/config", response_model=MQTTConfigResponse)
async def get_mqtt_config(db: Session = Depends(get_db)):
    """
    Get current MQTT configuration (AC5: Status queryable).

    Returns the MQTT broker configuration with password omitted for security.
    If no configuration exists, returns a default configuration.
    """
    config = db.query(MQTTConfig).first()

    if not config:
        # Return default config if none exists
        return MQTTConfigResponse(
            id="",
            broker_host="",
            broker_port=1883,
            username=None,
            topic_prefix="liveobject",
            discovery_prefix="homeassistant",
            discovery_enabled=True,
            qos=1,
            enabled=False,
            retain_messages=True,
            use_tls=False,
            has_password=False,
            created_at=None,
            updated_at=None
        )

    return MQTTConfigResponse(
        id=config.id,
        broker_host=config.broker_host,
        broker_port=config.broker_port,
        username=config.username,
        topic_prefix=config.topic_prefix,
        discovery_prefix=config.discovery_prefix,
        discovery_enabled=config.discovery_enabled,
        qos=config.qos,
        enabled=config.enabled,
        retain_messages=config.retain_messages,
        use_tls=config.use_tls,
        has_password=bool(config.password),
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None
    )


@router.put("/mqtt/config", response_model=MQTTConfigResponse)
async def update_mqtt_config(
    config_update: MQTTConfigUpdate,
    db: Session = Depends(get_db)
):
    """
    Update MQTT configuration and reconnect if enabled (AC6: Encrypted credentials).

    If MQTT is enabled, triggers a reconnect with the new configuration.
    Credentials are encrypted before storage using Fernet AES-256.
    """
    config = db.query(MQTTConfig).first()

    if not config:
        # Create new config
        config = MQTTConfig(
            broker_host=config_update.broker_host,
            broker_port=config_update.broker_port,
            username=config_update.username,
            password=config_update.password,  # @validates will encrypt
            topic_prefix=config_update.topic_prefix,
            discovery_prefix=config_update.discovery_prefix,
            discovery_enabled=config_update.discovery_enabled,
            qos=config_update.qos,
            enabled=config_update.enabled,
            retain_messages=config_update.retain_messages,
            use_tls=config_update.use_tls
        )
        db.add(config)
    else:
        # Update existing config
        config.broker_host = config_update.broker_host
        config.broker_port = config_update.broker_port
        config.username = config_update.username
        # Only update password if provided (not empty string)
        if config_update.password:
            config.password = config_update.password  # @validates will encrypt
        config.topic_prefix = config_update.topic_prefix
        config.discovery_prefix = config_update.discovery_prefix
        config.discovery_enabled = config_update.discovery_enabled
        config.qos = config_update.qos
        config.enabled = config_update.enabled
        config.retain_messages = config_update.retain_messages
        config.use_tls = config_update.use_tls

    db.commit()
    db.refresh(config)

    logger.info(
        "MQTT configuration updated",
        extra={
            "event_type": "mqtt_config_updated",
            "broker": f"{config.broker_host}:{config.broker_port}",
            "enabled": config.enabled
        }
    )

    # Update MQTT service with new config
    mqtt_service = get_mqtt_service()
    try:
        await mqtt_service.update_config(config)
    except Exception as e:
        logger.warning(f"MQTT reconnect failed after config update: {e}")
        # Don't fail the API call, the reconnect loop will retry

    return MQTTConfigResponse(
        id=config.id,
        broker_host=config.broker_host,
        broker_port=config.broker_port,
        username=config.username,
        topic_prefix=config.topic_prefix,
        discovery_prefix=config.discovery_prefix,
        discovery_enabled=config.discovery_enabled,
        qos=config.qos,
        enabled=config.enabled,
        retain_messages=config.retain_messages,
        use_tls=config.use_tls,
        has_password=bool(config.password),
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None
    )


@router.get("/mqtt/status", response_model=MQTTStatusResponse)
async def get_mqtt_status():
    """
    Get current MQTT connection status (AC5: Connection status tracked).

    Returns connection status, statistics, and any error messages.
    """
    mqtt_service = get_mqtt_service()
    status = mqtt_service.get_status()

    return MQTTStatusResponse(
        connected=status["connected"],
        broker=status["broker"],
        last_connected_at=status["last_connected_at"],
        messages_published=status["messages_published"],
        last_error=status["last_error"],
        reconnect_attempt=status["reconnect_attempt"]
    )


@router.post("/mqtt/test", response_model=MQTTTestResponse)
async def test_mqtt_connection(test_request: MQTTTestRequest):
    """
    Test MQTT connection without persisting configuration (AC1: Connect with auth).

    Attempts to connect to the specified broker with the provided credentials.
    Connection is closed after test regardless of outcome.
    """
    mqtt_service = get_mqtt_service()

    result = await mqtt_service.test_connection(
        broker_host=test_request.broker_host,
        broker_port=test_request.broker_port,
        username=test_request.username,
        password=test_request.password,
        use_tls=test_request.use_tls
    )

    logger.info(
        f"MQTT connection test: {'success' if result['success'] else 'failed'}",
        extra={
            "event_type": "mqtt_test_connection",
            "broker": f"{test_request.broker_host}:{test_request.broker_port}",
            "success": result["success"],
            "message": result["message"]
        }
    )

    return MQTTTestResponse(
        success=result["success"],
        message=result["message"]
    )


@router.post("/mqtt/publish-discovery", response_model=PublishDiscoveryResponse)
async def publish_discovery(db: Session = Depends(get_db)):
    """
    Manually trigger Home Assistant discovery publishing (Story P4-2.2, AC1).

    Publishes discovery configuration for all enabled cameras.
    Use after adding new cameras or when discovery messages need refresh.

    Requires MQTT to be connected and discovery to be enabled.
    """
    from app.services.mqtt_discovery_service import get_discovery_service

    mqtt_service = get_mqtt_service()

    if not mqtt_service.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MQTT not connected. Configure and enable MQTT first."
        )

    # Check if discovery is enabled
    config = db.query(MQTTConfig).first()
    if config and not config.discovery_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MQTT discovery is disabled. Enable it in MQTT settings."
        )

    # Publish discovery for all cameras
    discovery_service = get_discovery_service()
    cameras_published = await discovery_service.publish_all_discovery_configs()

    logger.info(
        "Manual discovery publish completed",
        extra={
            "event_type": "mqtt_discovery_manual_publish",
            "cameras_published": cameras_published
        }
    )

    return PublishDiscoveryResponse(
        success=True,
        message=f"Published discovery for {cameras_published} cameras",
        cameras_published=cameras_published
    )


# ============================================================================
# HomeKit Integration Endpoints (Story P4-6.1)
# ============================================================================


class HomekitStatusResponse(BaseModel):
    """HomeKit integration status response."""
    enabled: bool
    running: bool
    paired: bool
    accessory_count: int
    bridge_name: str
    setup_code: Optional[str] = None
    qr_code_data: Optional[str] = None
    port: int
    error: Optional[str] = None
    available: bool = Field(..., description="Whether HAP-python is installed")

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "running": True,
                "paired": False,
                "accessory_count": 3,
                "bridge_name": "ArgusAI",
                "setup_code": "031-45-154",
                "qr_code_data": "data:image/png;base64,...",
                "port": 51826,
                "error": None,
                "available": True
            }
        }


class HomekitResetResponse(BaseModel):
    """Response for HomeKit pairing reset."""
    success: bool
    message: str
    new_setup_code: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "HomeKit pairing reset. Please re-pair with the Home app.",
                "new_setup_code": "123-45-678"
            }
        }


class HomekitEnableRequest(BaseModel):
    """Request to enable/disable HomeKit integration."""
    enabled: bool = Field(..., description="Whether to enable HomeKit integration")

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True
            }
        }


@router.get("/homekit/status", response_model=HomekitStatusResponse)
async def get_homekit_status():
    """
    Get current HomeKit integration status (AC8: Status endpoint).

    Returns enabled/running state, pairing info, and setup code if not paired.
    """
    from app.services.homekit_service import get_homekit_service

    service = get_homekit_service()
    status = service.get_status()

    return HomekitStatusResponse(
        enabled=status.enabled,
        running=status.running,
        paired=status.paired,
        accessory_count=status.accessory_count,
        bridge_name=status.bridge_name,
        setup_code=status.setup_code,
        qr_code_data=status.qr_code_data,
        port=status.port,
        error=status.error,
        available=service.is_available,
    )


@router.post("/homekit/reset", response_model=HomekitResetResponse)
async def reset_homekit_pairing():
    """
    Reset HomeKit pairing (AC10: Reset functionality).

    Removes existing pairing state, requiring re-pairing with the Home app.
    Generates a new pairing code.
    """
    from app.services.homekit_service import get_homekit_service

    service = get_homekit_service()

    if not service.is_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HAP-python not installed. HomeKit integration not available."
        )

    success = await service.reset_pairing()

    if success:
        new_status = service.get_status()
        logger.info(
            "HomeKit pairing reset",
            extra={
                "event_type": "homekit_pairing_reset",
                "new_setup_code": service.pincode
            }
        )
        return HomekitResetResponse(
            success=True,
            message="HomeKit pairing reset. Please re-pair with the Home app.",
            new_setup_code=service.pincode
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset HomeKit pairing"
        )


@router.put("/homekit/enable", response_model=HomekitStatusResponse)
async def update_homekit_enabled(
    request: HomekitEnableRequest,
    db: Session = Depends(get_db)
):
    """
    Enable or disable HomeKit integration (AC6: Toggle in settings).

    When enabled, starts the HomeKit accessory server.
    When disabled, stops the server but preserves pairing state.
    """
    from app.services.homekit_service import get_homekit_service, initialize_homekit_service, shutdown_homekit_service
    from app.models.system_setting import SystemSetting
    from app.models.camera import Camera

    # Update setting in database
    setting = db.query(SystemSetting).filter(
        SystemSetting.key == "homekit_enabled"
    ).first()

    if setting:
        setting.value = str(request.enabled).lower()
    else:
        setting = SystemSetting(
            key="homekit_enabled",
            value=str(request.enabled).lower()
        )
        db.add(setting)

    db.commit()

    service = get_homekit_service()

    if request.enabled:
        # Start HomeKit service
        if not service.is_available:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="HAP-python not installed. Cannot enable HomeKit integration."
            )

        # Update config
        service.config.enabled = True

        # Get cameras and start service
        cameras = db.query(Camera).filter(Camera.is_enabled == True).all()
        success = await service.start(cameras)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start HomeKit service: {service._error}"
            )

        logger.info(
            "HomeKit integration enabled",
            extra={
                "event_type": "homekit_enabled",
                "camera_count": len(cameras)
            }
        )
    else:
        # Stop HomeKit service
        await service.stop()
        service.config.enabled = False

        logger.info(
            "HomeKit integration disabled",
            extra={"event_type": "homekit_disabled"}
        )

    # Return updated status
    status_result = service.get_status()
    return HomekitStatusResponse(
        enabled=status_result.enabled,
        running=status_result.running,
        paired=status_result.paired,
        accessory_count=status_result.accessory_count,
        bridge_name=status_result.bridge_name,
        setup_code=status_result.setup_code,
        qr_code_data=status_result.qr_code_data,
        port=status_result.port,
        error=status_result.error,
        available=service.is_available,
    )
