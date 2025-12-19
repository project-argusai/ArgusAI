"""
HomeKit Diagnostics Pydantic Schemas (Story P7-1.1, P7-1.2, P7-3.3)

Defines schemas for diagnostic logging and monitoring of the HomeKit bridge.
Story P7-1.2 adds connectivity test response schema.
Story P7-3.3 adds camera streaming diagnostics schemas.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class HomeKitDiagnosticEntry(BaseModel):
    """
    A single diagnostic log entry for HomeKit operations (Story P7-1.1 AC1-4, P7-1.3 AC2).

    Categories:
    - lifecycle: Bridge start/stop, driver events
    - pairing: Pairing attempts, success/failure
    - event: Characteristic updates (motion, occupancy, etc.)
    - delivery: Event delivery confirmation logs (Story P7-1.3)
    - network: IP binding, port info
    - mdns: mDNS/Bonjour advertisement status
    """
    timestamp: datetime = Field(..., description="When the event occurred")
    level: str = Field(
        ...,
        description="Log level: debug, info, warning, error",
        pattern="^(debug|info|warning|error)$"
    )
    category: str = Field(
        ...,
        description="Event category: lifecycle, pairing, event, delivery, network, mdns",
        pattern="^(lifecycle|pairing|event|delivery|network|mdns)$"
    )
    message: str = Field(..., description="Human-readable log message")
    details: Optional[dict] = Field(
        None,
        description="Additional structured data (camera_id, sensor_type, etc.)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2025-12-17T10:30:00Z",
                "level": "info",
                "category": "event",
                "message": "Motion triggered for Front Door",
                "details": {"camera_id": "abc-123", "sensor_type": "motion", "reset_seconds": 30}
            }
        }
    )


class NetworkBindingInfo(BaseModel):
    """Network binding information for the HomeKit bridge."""
    ip: str = Field(..., description="IP address the bridge is bound to")
    port: int = Field(..., description="Port number")
    interface: Optional[str] = Field(None, description="Network interface name if specific")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ip": "192.168.1.100",
                "port": 51826,
                "interface": "en0"
            }
        }
    )


class LastEventDeliveryInfo(BaseModel):
    """Information about the most recent event delivery."""
    camera_id: str = Field(..., description="Camera that triggered the event")
    camera_name: Optional[str] = Field(None, description="Human-readable camera name (Story P7-1.4)")
    sensor_type: str = Field(..., description="Type of sensor (motion, occupancy, vehicle, etc.)")
    timestamp: datetime = Field(..., description="When the event was delivered")
    delivered: bool = Field(..., description="Whether delivery was successful")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "camera_id": "abc-123",
                "camera_name": "Front Door",
                "sensor_type": "motion",
                "timestamp": "2025-12-17T10:30:00Z",
                "delivered": True
            }
        }
    )


class HomeKitDiagnosticsResponse(BaseModel):
    """
    Complete diagnostic information for HomeKit troubleshooting (Story P7-1.1 AC5).

    Returned by GET /api/v1/homekit/diagnostics endpoint.
    """
    bridge_running: bool = Field(..., description="Whether the HAP server is running")
    mdns_advertising: bool = Field(
        ...,
        description="Whether mDNS/Bonjour service is advertising"
    )
    network_binding: Optional[NetworkBindingInfo] = Field(
        None,
        description="IP/port binding information"
    )
    connected_clients: int = Field(
        0,
        description="Number of currently connected HomeKit clients"
    )
    last_event_delivery: Optional[LastEventDeliveryInfo] = Field(
        None,
        description="Information about the most recent event delivery"
    )
    sensor_deliveries: List[LastEventDeliveryInfo] = Field(
        default_factory=list,
        description="Per-sensor delivery history (Story P7-1.4 AC3)"
    )
    recent_logs: List[HomeKitDiagnosticEntry] = Field(
        default_factory=list,
        description="Recent diagnostic log entries (newest first)"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Current warning messages"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Current error messages"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "bridge_running": True,
                "mdns_advertising": True,
                "network_binding": {
                    "ip": "192.168.1.100",
                    "port": 51826,
                    "interface": "en0"
                },
                "connected_clients": 2,
                "last_event_delivery": {
                    "camera_id": "abc-123",
                    "camera_name": "Front Door",
                    "sensor_type": "motion",
                    "timestamp": "2025-12-17T10:30:00Z",
                    "delivered": True
                },
                "sensor_deliveries": [
                    {
                        "camera_id": "abc-123",
                        "camera_name": "Front Door",
                        "sensor_type": "motion",
                        "timestamp": "2025-12-17T10:30:00Z",
                        "delivered": True
                    },
                    {
                        "camera_id": "def-456",
                        "camera_name": "Backyard",
                        "sensor_type": "occupancy",
                        "timestamp": "2025-12-17T10:25:00Z",
                        "delivered": True
                    }
                ],
                "recent_logs": [
                    {
                        "timestamp": "2025-12-17T10:30:00Z",
                        "level": "info",
                        "category": "event",
                        "message": "Motion triggered for Front Door",
                        "details": {"camera_id": "abc-123", "reset_seconds": 30}
                    }
                ],
                "warnings": [],
                "errors": []
            }
        }
    )


# ============================================================================
# Stream Diagnostics Schemas (Story P7-3.3)
# ============================================================================


class CameraStreamInfo(BaseModel):
    """
    Per-camera streaming status information (Story P7-3.3 AC2).
    """
    camera_id: str = Field(..., description="Camera unique identifier")
    camera_name: str = Field(..., description="Human-readable camera name")
    streaming_enabled: bool = Field(
        ...,
        description="Whether camera streaming is enabled in HomeKit"
    )
    snapshot_supported: bool = Field(
        True,
        description="Whether snapshot capture is supported"
    )
    last_snapshot: Optional[datetime] = Field(
        None,
        description="Timestamp of last snapshot capture"
    )
    active_streams: int = Field(
        0,
        description="Number of currently active streams (max 2)"
    )
    quality: Optional[str] = Field(
        None,
        description="Current stream quality level (low/medium/high)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "camera_id": "abc-123",
                "camera_name": "Front Door",
                "streaming_enabled": True,
                "snapshot_supported": True,
                "last_snapshot": "2025-12-19T14:30:00Z",
                "active_streams": 1,
                "quality": "medium"
            }
        }
    )


class StreamDiagnostics(BaseModel):
    """
    Aggregated camera streaming diagnostics (Story P7-3.3 AC2).
    """
    cameras: List[CameraStreamInfo] = Field(
        default_factory=list,
        description="Per-camera streaming status"
    )
    total_active_streams: int = Field(
        0,
        description="Total active streams across all cameras"
    )
    ffmpeg_available: bool = Field(
        False,
        description="Whether ffmpeg is available for streaming"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "cameras": [
                    {
                        "camera_id": "abc-123",
                        "camera_name": "Front Door",
                        "streaming_enabled": True,
                        "snapshot_supported": True,
                        "last_snapshot": "2025-12-19T14:30:00Z",
                        "active_streams": 1,
                        "quality": "medium"
                    }
                ],
                "total_active_streams": 1,
                "ffmpeg_available": True
            }
        }
    )


class StreamTestResponse(BaseModel):
    """
    Response from camera stream test endpoint (Story P7-3.3 AC3).

    Validates RTSP connectivity and ffmpeg compatibility for HomeKit streaming.
    """
    success: bool = Field(
        ...,
        description="Whether the stream test passed all checks"
    )
    rtsp_accessible: bool = Field(
        ...,
        description="Whether the camera RTSP stream is accessible"
    )
    ffmpeg_compatible: bool = Field(
        ...,
        description="Whether ffmpeg can process the stream"
    )
    source_resolution: Optional[str] = Field(
        None,
        description="Detected source resolution (e.g., '1920x1080')"
    )
    source_fps: Optional[int] = Field(
        None,
        description="Detected source frame rate"
    )
    source_codec: Optional[str] = Field(
        None,
        description="Detected source video codec (e.g., 'h264')"
    )
    target_resolution: Optional[str] = Field(
        None,
        description="Target resolution for HomeKit (e.g., '1280x720')"
    )
    target_fps: Optional[int] = Field(
        None,
        description="Target frame rate for HomeKit"
    )
    target_bitrate: Optional[int] = Field(
        None,
        description="Target bitrate in kbps"
    )
    estimated_latency_ms: Optional[int] = Field(
        None,
        description="Estimated stream latency in milliseconds"
    )
    ffmpeg_command: Optional[str] = Field(
        None,
        description="Sanitized ffmpeg command for debugging (SRTP keys removed)"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if test failed"
    )
    test_duration_ms: int = Field(
        ...,
        description="Time taken to complete the test in milliseconds"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "rtsp_accessible": True,
                "ffmpeg_compatible": True,
                "source_resolution": "1920x1080",
                "source_fps": 30,
                "source_codec": "h264",
                "target_resolution": "1280x720",
                "target_fps": 25,
                "target_bitrate": 1500,
                "estimated_latency_ms": 500,
                "ffmpeg_command": "ffmpeg -rtsp_transport tcp -i rtsp://... -vcodec libx264 ...",
                "error": None,
                "test_duration_ms": 3500
            }
        }
    )


class HomeKitConnectivityTestResponse(BaseModel):
    """
    Response from HomeKit connectivity test endpoint (Story P7-1.2 AC1, AC2, AC6).

    Tests mDNS visibility and port accessibility for troubleshooting discovery issues.
    """
    mdns_visible: bool = Field(
        ...,
        description="Whether the _hap._tcp service is visible via mDNS"
    )
    discovered_as: Optional[str] = Field(
        None,
        description="Service name as discovered (e.g., 'ArgusAI._hap._tcp.local')"
    )
    port_accessible: bool = Field(
        ...,
        description="Whether the HAP port (TCP) is accessible"
    )
    network_binding: Optional[NetworkBindingInfo] = Field(
        None,
        description="Current network binding configuration"
    )
    firewall_issues: List[str] = Field(
        default_factory=list,
        description="Detected firewall or network issues"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Troubleshooting recommendations based on test results"
    )
    test_duration_ms: int = Field(
        ...,
        description="Time taken to complete the test in milliseconds"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mdns_visible": True,
                "discovered_as": "ArgusAI._hap._tcp.local",
                "port_accessible": True,
                "network_binding": {
                    "ip": "192.168.1.100",
                    "port": 51826,
                    "interface": None
                },
                "firewall_issues": [],
                "recommendations": [],
                "test_duration_ms": 1250
            }
        }
    )
