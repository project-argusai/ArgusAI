"""
HomeKit Diagnostics Pydantic Schemas (Story P7-1.1)

Defines schemas for diagnostic logging and monitoring of the HomeKit bridge.
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
    sensor_type: str = Field(..., description="Type of sensor (motion, occupancy, vehicle, etc.)")
    timestamp: datetime = Field(..., description="When the event was delivered")
    delivered: bool = Field(..., description="Whether delivery was successful")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "camera_id": "abc-123",
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
                    "sensor_type": "motion",
                    "timestamp": "2025-12-17T10:30:00Z",
                    "delivered": True
                },
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
