"""
ONVIF Camera Discovery Schemas (Stories P5-2.1, P5-2.2)

Pydantic models for ONVIF WS-Discovery and device details endpoints.

P5-2.1: Basic discovery (DiscoveredDevice, DiscoveryRequest/Response)
P5-2.2: Device details (StreamProfile, DeviceInfo, DiscoveredCameraDetails)
"""
from typing import List, Optional
from datetime import datetime
from app.schemas.types import UTCDateTime
from pydantic import BaseModel, Field, ConfigDict


class DiscoveredDevice(BaseModel):
    """
    Represents a device discovered via WS-Discovery.

    Contains the minimal information extracted from ProbeMatch responses.
    Full device details (manufacturer, model, RTSP URLs) are retrieved
    in Story P5-2.2 via GetDeviceInformation.
    """
    endpoint_url: str = Field(
        ...,
        description="XAddrs service URL from ProbeMatch response"
    )
    scopes: List[str] = Field(
        default_factory=list,
        description="Device scopes (e.g., onvif://www.onvif.org/type/NetworkVideoTransmitter)"
    )
    types: List[str] = Field(
        default_factory=list,
        description="Device types from ProbeMatch (e.g., tdn:NetworkVideoTransmitter)"
    )
    metadata_version: Optional[str] = Field(
        None,
        description="Metadata version from ProbeMatch if available"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "endpoint_url": "http://192.168.1.100:80/onvif/device_service",
                "scopes": [
                    "onvif://www.onvif.org/type/NetworkVideoTransmitter",
                    "onvif://www.onvif.org/Profile/Streaming"
                ],
                "types": ["tdn:NetworkVideoTransmitter"],
                "metadata_version": "1"
            }
        }
    )


class DiscoveryRequest(BaseModel):
    """Request body for camera discovery endpoint."""
    timeout: int = Field(
        10,
        ge=1,
        le=60,
        description="Discovery timeout in seconds (default: 10, max: 60)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timeout": 10
            }
        }
    )


class DiscoveryResponse(BaseModel):
    """Response from camera discovery endpoint."""
    status: str = Field(
        ...,
        description="Discovery status: 'complete', 'timeout', or 'error'"
    )
    duration_ms: int = Field(
        ...,
        description="Time taken for discovery scan in milliseconds"
    )
    devices: List[DiscoveredDevice] = Field(
        default_factory=list,
        description="List of discovered ONVIF devices"
    )
    device_count: int = Field(
        ...,
        description="Number of devices discovered"
    )
    error_message: Optional[str] = Field(
        None,
        description="Error message if status is 'error'"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "complete",
                "duration_ms": 8234,
                "devices": [
                    {
                        "endpoint_url": "http://192.168.1.100:80/onvif/device_service",
                        "scopes": ["onvif://www.onvif.org/type/NetworkVideoTransmitter"],
                        "types": ["tdn:NetworkVideoTransmitter"],
                        "metadata_version": "1"
                    }
                ],
                "device_count": 1,
                "error_message": None
            }
        }
    )


# ============================================================================
# Story P5-2.2: Device Details Schemas
# ============================================================================


class StreamProfile(BaseModel):
    """
    Represents a video stream profile from an ONVIF camera.

    Contains profile name, resolution, frame rate, and RTSP URL.
    """
    name: str = Field(
        ...,
        description="Profile name (e.g., 'mainStream', 'subStream')"
    )
    token: str = Field(
        ...,
        description="Profile token used for ONVIF API calls"
    )
    resolution: str = Field(
        ...,
        description="Resolution as string (e.g., '1920x1080')"
    )
    width: int = Field(
        ...,
        ge=1,
        description="Video width in pixels"
    )
    height: int = Field(
        ...,
        ge=1,
        description="Video height in pixels"
    )
    fps: int = Field(
        ...,
        ge=1,
        description="Frame rate (frames per second)"
    )
    rtsp_url: str = Field(
        ...,
        description="RTSP URL for this profile's stream"
    )
    encoding: Optional[str] = Field(
        None,
        description="Video encoding (e.g., 'H264', 'H265', 'JPEG')"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "mainStream",
                "token": "profile_token_1",
                "resolution": "1920x1080",
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "rtsp_url": "rtsp://192.168.1.100:554/stream1",
                "encoding": "H264"
            }
        }
    )


class DeviceInfo(BaseModel):
    """
    Device information from ONVIF GetDeviceInformation response.
    """
    name: str = Field(
        ...,
        description="Device name (from GetDeviceInformation or derived from model)"
    )
    manufacturer: str = Field(
        ...,
        description="Device manufacturer"
    )
    model: str = Field(
        ...,
        description="Device model"
    )
    firmware_version: Optional[str] = Field(
        None,
        description="Firmware version"
    )
    serial_number: Optional[str] = Field(
        None,
        description="Device serial number"
    )
    hardware_id: Optional[str] = Field(
        None,
        description="Hardware identifier"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "IPC-HDW2431T",
                "manufacturer": "Dahua",
                "model": "IPC-HDW2431T-AS-S2",
                "firmware_version": "2.800.0000000.44.R",
                "serial_number": "6G12345678",
                "hardware_id": "1.0"
            }
        }
    )


class DiscoveredCameraDetails(BaseModel):
    """
    Full camera details retrieved via ONVIF GetDeviceInformation and GetProfiles.

    This is the comprehensive model returned when querying a specific device.
    """
    id: str = Field(
        ...,
        description="Unique identifier for this camera (generated from endpoint URL)"
    )
    endpoint_url: str = Field(
        ...,
        description="ONVIF device service URL"
    )
    ip_address: str = Field(
        ...,
        description="IP address extracted from endpoint URL"
    )
    port: int = Field(
        ...,
        description="Port number extracted from endpoint URL"
    )
    device_info: DeviceInfo = Field(
        ...,
        description="Device information from GetDeviceInformation"
    )
    profiles: List[StreamProfile] = Field(
        default_factory=list,
        description="Available stream profiles"
    )
    primary_rtsp_url: str = Field(
        ...,
        description="Primary/best quality RTSP URL (highest resolution profile)"
    )
    requires_auth: bool = Field(
        False,
        description="Whether the device requires authentication for ONVIF queries"
    )
    discovered_at: UTCDateTime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when device details were retrieved"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "camera-192-168-1-100-80",
                "endpoint_url": "http://192.168.1.100:80/onvif/device_service",
                "ip_address": "192.168.1.100",
                "port": 80,
                "device_info": {
                    "name": "IPC-HDW2431T",
                    "manufacturer": "Dahua",
                    "model": "IPC-HDW2431T-AS-S2",
                    "firmware_version": "2.800.0000000.44.R",
                    "serial_number": "6G12345678",
                    "hardware_id": "1.0"
                },
                "profiles": [
                    {
                        "name": "mainStream",
                        "token": "profile_token_1",
                        "resolution": "2688x1520",
                        "width": 2688,
                        "height": 1520,
                        "fps": 25,
                        "rtsp_url": "rtsp://192.168.1.100:554/cam/realmonitor?channel=1&subtype=0",
                        "encoding": "H264"
                    },
                    {
                        "name": "subStream",
                        "token": "profile_token_2",
                        "resolution": "704x480",
                        "width": 704,
                        "height": 480,
                        "fps": 25,
                        "rtsp_url": "rtsp://192.168.1.100:554/cam/realmonitor?channel=1&subtype=1",
                        "encoding": "H264"
                    }
                ],
                "primary_rtsp_url": "rtsp://192.168.1.100:554/cam/realmonitor?channel=1&subtype=0",
                "requires_auth": False,
                "discovered_at": "2025-12-14T10:30:00Z"
            }
        }
    )


class DeviceDetailsRequest(BaseModel):
    """
    Request to fetch detailed information from a discovered ONVIF device.
    """
    endpoint_url: str = Field(
        ...,
        description="ONVIF device service URL from discovery"
    )
    username: Optional[str] = Field(
        None,
        description="Username for ONVIF authentication (if required)"
    )
    password: Optional[str] = Field(
        None,
        description="Password for ONVIF authentication (if required)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "endpoint_url": "http://192.168.1.100:80/onvif/device_service",
                "username": "admin",
                "password": "password123"
            }
        }
    )


class DeviceDetailsResponse(BaseModel):
    """
    Response from device details endpoint.
    """
    status: str = Field(
        ...,
        description="Status: 'success', 'auth_required', or 'error'"
    )
    device: Optional[DiscoveredCameraDetails] = Field(
        None,
        description="Device details if successful"
    )
    error_message: Optional[str] = Field(
        None,
        description="Error message if status is 'error' or 'auth_required'"
    )
    duration_ms: int = Field(
        0,
        description="Time taken to query device in milliseconds"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "device": {
                    "id": "camera-192-168-1-100-80",
                    "endpoint_url": "http://192.168.1.100:80/onvif/device_service",
                    "ip_address": "192.168.1.100",
                    "port": 80,
                    "device_info": {
                        "name": "IPC-HDW2431T",
                        "manufacturer": "Dahua",
                        "model": "IPC-HDW2431T-AS-S2"
                    },
                    "profiles": [],
                    "primary_rtsp_url": "rtsp://192.168.1.100:554/stream",
                    "requires_auth": False
                },
                "error_message": None,
                "duration_ms": 1234
            }
        }
    )


# ============================================================================
# Story P5-2.4: Test Connection Schemas
# ============================================================================


class TestConnectionRequest(BaseModel):
    """
    Request to test an RTSP connection without saving the camera.

    Validates the RTSP URL format and optionally includes credentials
    for authenticated streams.
    """
    rtsp_url: str = Field(
        ...,
        description="RTSP URL to test (must start with rtsp:// or rtsps://)",
        min_length=10
    )
    username: Optional[str] = Field(
        None,
        description="Username for RTSP authentication (if required)"
    )
    password: Optional[str] = Field(
        None,
        description="Password for RTSP authentication (if required)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rtsp_url": "rtsp://192.168.1.100:554/stream",
                "username": "admin",
                "password": "password123"
            }
        }
    )

    def model_post_init(self, __context) -> None:
        """Validate RTSP URL scheme after model creation."""
        url_lower = self.rtsp_url.lower()
        if not url_lower.startswith("rtsp://") and not url_lower.startswith("rtsps://"):
            raise ValueError(
                "Invalid RTSP URL format - must start with rtsp:// or rtsps://"
            )


class TestConnectionResponse(BaseModel):
    """
    Response from RTSP connection test endpoint.

    Returns stream metadata on success, or error details on failure.
    """
    success: bool = Field(
        ...,
        description="Whether the connection test was successful"
    )
    latency_ms: Optional[int] = Field(
        None,
        description="Time to establish connection and receive first frame (ms)"
    )
    resolution: Optional[str] = Field(
        None,
        description="Video resolution (e.g., '1920x1080')"
    )
    fps: Optional[int] = Field(
        None,
        description="Frame rate (frames per second)"
    )
    codec: Optional[str] = Field(
        None,
        description="Video codec (e.g., 'H.264', 'H.265')"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if test failed"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "success": True,
                    "latency_ms": 234,
                    "resolution": "1920x1080",
                    "fps": 30,
                    "codec": "H.264",
                    "error": None
                },
                {
                    "success": False,
                    "latency_ms": None,
                    "resolution": None,
                    "fps": None,
                    "codec": None,
                    "error": "Authentication failed - check username/password"
                }
            ]
        }
    )
