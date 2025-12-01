"""Pydantic schemas for UniFi Protect controller API endpoints"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
import uuid


class ProtectControllerBase(BaseModel):
    """Base schema with common fields"""

    name: str = Field(..., min_length=1, max_length=100, description="User-friendly controller name")
    host: str = Field(..., min_length=1, max_length=255, description="IP address or hostname")
    port: int = Field(default=443, ge=1, le=65535, description="HTTPS port")
    verify_ssl: bool = Field(default=False, description="Whether to verify SSL certificates")


class ProtectControllerCreate(ProtectControllerBase):
    """Schema for creating a new Protect controller"""

    username: str = Field(..., min_length=1, max_length=100, description="Protect authentication username")
    password: str = Field(..., min_length=1, max_length=100, description="Protect password (will be encrypted)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Home UDM Pro",
                    "host": "192.168.1.1",
                    "port": 443,
                    "username": "admin",
                    "password": "secretpassword",
                    "verify_ssl": False
                }
            ]
        }
    }


class ProtectControllerUpdate(BaseModel):
    """Schema for updating an existing controller (all fields optional)"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=1, max_length=100)
    verify_ssl: Optional[bool] = None


class ProtectControllerResponse(ProtectControllerBase):
    """Schema for controller API responses"""

    id: str = Field(..., description="Controller UUID")
    username: str = Field(..., description="Protect authentication username")
    is_connected: bool = Field(..., description="Current connection status")
    last_connected_at: Optional[datetime] = Field(None, description="Last successful connection timestamp")
    last_error: Optional[str] = Field(None, description="Last connection error message")
    created_at: datetime
    updated_at: datetime

    # Note: password field is intentionally omitted (write-only field)

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Home UDM Pro",
                    "host": "192.168.1.1",
                    "port": 443,
                    "username": "admin",
                    "verify_ssl": False,
                    "is_connected": True,
                    "last_connected_at": "2025-11-30T10:30:00Z",
                    "last_error": None,
                    "created_at": "2025-11-30T10:00:00Z",
                    "updated_at": "2025-11-30T10:30:00Z"
                }
            ]
        }
    }


class MetaResponse(BaseModel):
    """Standard meta response object"""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique request identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Response timestamp")
    count: Optional[int] = Field(None, description="Number of items (for list responses)")


class ProtectControllerSingleResponse(BaseModel):
    """Single controller response with meta"""

    data: ProtectControllerResponse
    meta: MetaResponse


class ProtectControllerListResponse(BaseModel):
    """List of controllers response with meta"""

    data: List[ProtectControllerResponse]
    meta: MetaResponse


class ProtectControllerDeleteResponse(BaseModel):
    """Delete operation response"""

    data: dict = Field(default={"deleted": True})
    meta: MetaResponse


# Story P2-1.2: Connection Test Schemas

class ProtectControllerTest(BaseModel):
    """Schema for testing controller connection (no name required)"""

    host: str = Field(..., min_length=1, max_length=255, description="IP address or hostname")
    port: int = Field(default=443, ge=1, le=65535, description="HTTPS port")
    username: str = Field(..., min_length=1, max_length=100, description="Protect authentication username")
    password: str = Field(..., min_length=1, max_length=100, description="Protect password")
    verify_ssl: bool = Field(default=False, description="Whether to verify SSL certificates")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "host": "192.168.1.1",
                    "port": 443,
                    "username": "admin",
                    "password": "secretpassword",
                    "verify_ssl": False
                }
            ]
        }
    }


class ProtectTestResultData(BaseModel):
    """Connection test result data"""

    success: bool = Field(..., description="Whether connection was successful")
    message: str = Field(..., description="Human-readable result message")
    firmware_version: Optional[str] = Field(None, description="Controller firmware version (on success)")
    camera_count: Optional[int] = Field(None, description="Number of cameras discovered (on success)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "message": "Connected successfully",
                    "firmware_version": "3.0.16",
                    "camera_count": 6
                }
            ]
        }
    }


class ProtectTestResponse(BaseModel):
    """Connection test response with meta"""

    data: ProtectTestResultData
    meta: MetaResponse


# Story P2-1.4: Connection Management Schemas

class ProtectConnectionStatusData(BaseModel):
    """Connection status result data (AC10)"""

    controller_id: str = Field(..., description="Controller UUID")
    status: str = Field(..., description="Connection status: connected, disconnected, connecting, reconnecting, error")
    error: Optional[str] = Field(None, description="Error message if status is 'error'")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "controller_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "connected",
                    "error": None
                }
            ]
        }
    }


class ProtectConnectionResponse(BaseModel):
    """Connection/disconnect response with meta (AC10)"""

    data: ProtectConnectionStatusData
    meta: MetaResponse


# Story P2-2.1: Camera Discovery Schemas

class ProtectDiscoveredCamera(BaseModel):
    """Schema for a camera discovered from a Protect controller (AC2, AC5)"""

    protect_camera_id: str = Field(..., description="Native Protect camera ID")
    name: str = Field(..., description="Camera name from Protect")
    type: str = Field(..., description="Camera type: 'camera' or 'doorbell'")
    model: str = Field(..., description="Camera model (e.g., 'G4 Doorbell Pro', 'G4 Pro')")
    is_online: bool = Field(..., description="Whether camera is currently online")
    is_doorbell: bool = Field(..., description="Whether camera is a doorbell")
    is_enabled_for_ai: bool = Field(default=False, description="Whether camera is enabled for AI processing")
    smart_detection_capabilities: List[str] = Field(
        default_factory=list,
        description="Smart detection types the camera supports (e.g., ['person', 'vehicle', 'package'])"
    )
    smart_detection_types: Optional[List[str]] = Field(
        default=None,
        description="Configured filter types for enabled cameras (Story P2-2.3)"
    )
    is_new: bool = Field(
        default=False,
        description="Whether this camera was newly discovered (not in database) (Story P2-2.4 AC11)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "protect_camera_id": "abc123def456",
                    "name": "Front Door",
                    "type": "doorbell",
                    "model": "G4 Doorbell Pro",
                    "is_online": True,
                    "is_doorbell": True,
                    "is_enabled_for_ai": False,
                    "smart_detection_capabilities": ["person", "vehicle", "package"],
                    "smart_detection_types": None,
                    "is_new": True
                },
                {
                    "protect_camera_id": "xyz789",
                    "name": "Driveway",
                    "type": "camera",
                    "model": "G4 Pro",
                    "is_online": True,
                    "is_doorbell": False,
                    "is_enabled_for_ai": True,
                    "smart_detection_capabilities": ["person", "vehicle"],
                    "smart_detection_types": ["person", "vehicle", "package"],
                    "is_new": False
                }
            ]
        }
    }


class ProtectCameraDiscoveryMeta(BaseModel):
    """Meta response for camera discovery (AC6)"""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique request identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Response timestamp")
    count: int = Field(..., description="Number of cameras discovered")
    controller_id: str = Field(..., description="Controller ID that was queried")
    cached: bool = Field(..., description="Whether results were returned from cache")
    cached_at: Optional[datetime] = Field(None, description="When results were cached (if cached)")
    warning: Optional[str] = Field(None, description="Warning message if any issues occurred")


class ProtectCamerasResponse(BaseModel):
    """Camera discovery response with meta (AC5, AC6)"""

    data: List[ProtectDiscoveredCamera]
    meta: ProtectCameraDiscoveryMeta

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "data": [
                        {
                            "protect_camera_id": "abc123def456",
                            "name": "Front Door",
                            "type": "doorbell",
                            "model": "G4 Doorbell Pro",
                            "is_online": True,
                            "is_doorbell": True,
                            "is_enabled_for_ai": True,
                            "smart_detection_capabilities": ["person", "vehicle", "package"]
                        },
                        {
                            "protect_camera_id": "xyz789ghi012",
                            "name": "Backyard",
                            "type": "camera",
                            "model": "G4 Pro",
                            "is_online": True,
                            "is_doorbell": False,
                            "is_enabled_for_ai": False,
                            "smart_detection_capabilities": ["person", "vehicle"]
                        }
                    ],
                    "meta": {
                        "request_id": "550e8400-e29b-41d4-a716-446655440000",
                        "timestamp": "2025-11-30T10:30:00Z",
                        "count": 2,
                        "controller_id": "660e8400-e29b-41d4-a716-446655440001",
                        "cached": False,
                        "cached_at": None,
                        "warning": None
                    }
                }
            ]
        }
    }


# Story P2-2.2: Camera Enable/Disable Schemas

class ProtectCameraEnableRequest(BaseModel):
    """Request body for enabling a camera for AI analysis (AC6)"""

    name: Optional[str] = Field(None, description="Override camera name (optional)")
    smart_detection_types: List[str] = Field(
        default_factory=lambda: ["person", "vehicle", "package"],
        description="Smart detection types to filter (default: person, vehicle, package)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "smart_detection_types": ["person", "vehicle", "package"]
                }
            ]
        }
    }


class ProtectCameraEnableData(BaseModel):
    """Data returned when camera is enabled (AC6)"""

    camera_id: str = Field(..., description="Database camera ID")
    protect_camera_id: str = Field(..., description="Native Protect camera ID")
    name: str = Field(..., description="Camera name")
    is_enabled_for_ai: bool = Field(True, description="Always true for enable response")
    smart_detection_types: List[str] = Field(..., description="Configured smart detection types")


class ProtectCameraEnableResponse(BaseModel):
    """Response for camera enable endpoint (AC6)"""

    data: ProtectCameraEnableData
    meta: MetaResponse


class ProtectCameraDisableData(BaseModel):
    """Data returned when camera is disabled (AC7)"""

    protect_camera_id: str = Field(..., description="Native Protect camera ID")
    is_enabled_for_ai: bool = Field(False, description="Always false for disable response")


class ProtectCameraDisableResponse(BaseModel):
    """Response for camera disable endpoint (AC7)"""

    data: ProtectCameraDisableData
    meta: MetaResponse


# Story P2-2.3: Camera Filter Schemas

# Allowed filter values for validation
ALLOWED_FILTER_TYPES = {"person", "vehicle", "package", "animal", "motion"}


class ProtectCameraFiltersRequest(BaseModel):
    """Request body for updating camera filters (Story P2-2.3, AC7)"""

    smart_detection_types: List[str] = Field(
        ...,
        description="Smart detection types to filter. Use ['motion'] for all motion mode."
    )

    @field_validator('smart_detection_types')
    @classmethod
    def validate_filter_types(cls, v: List[str]) -> List[str]:
        """Validate that all filter types are in the allowed list (AC7)"""
        invalid_types = set(v) - ALLOWED_FILTER_TYPES
        if invalid_types:
            raise ValueError(
                f"Invalid filter types: {invalid_types}. "
                f"Allowed types: {ALLOWED_FILTER_TYPES}"
            )
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "smart_detection_types": ["person", "vehicle", "package"]
                },
                {
                    "smart_detection_types": ["motion"]
                }
            ]
        }
    }


class ProtectCameraFiltersData(BaseModel):
    """Data returned when camera filters are updated (Story P2-2.3, AC7)"""

    protect_camera_id: str = Field(..., description="Native Protect camera ID")
    name: str = Field(..., description="Camera name")
    smart_detection_types: List[str] = Field(..., description="Updated smart detection types")
    is_enabled_for_ai: bool = Field(..., description="Whether camera is enabled for AI analysis")


class ProtectCameraFiltersResponse(BaseModel):
    """Response for camera filters endpoint (Story P2-2.3, AC7)"""

    data: ProtectCameraFiltersData
    meta: MetaResponse
