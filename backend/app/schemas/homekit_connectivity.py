"""
HomeKit Connectivity Test schemas (Story P7-1.2)

Pydantic schemas for the connectivity test endpoint that checks
mDNS visibility and port accessibility for troubleshooting HomeKit discovery issues.
"""
from datetime import datetime
from app.schemas.types import UTCDateTime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class HomeKitConnectivityResponse(BaseModel):
    """
    Response from the HomeKit connectivity test endpoint (Story P7-1.2 AC6).

    Provides diagnostic information about HomeKit bridge discoverability:
    - mDNS service visibility (Bonjour/Avahi)
    - HAP port accessibility
    - Detected firewall or network issues
    """
    mdns_visible: bool = Field(
        ...,
        description="Whether the HomeKit service is visible via mDNS/Bonjour"
    )
    discovered_as: Optional[str] = Field(
        None,
        description="The mDNS service name discovered (e.g., 'ArgusAI._hap._tcp.local')"
    )
    port_accessible: bool = Field(
        ...,
        description="Whether the HAP port (default 51826) is accessible"
    )
    firewall_issues: List[str] = Field(
        default_factory=list,
        description="List of detected firewall or network configuration issues"
    )
    bind_address: str = Field(
        ...,
        description="Configured bind address for the HAP server"
    )
    port: int = Field(
        ...,
        description="Configured HAP server port"
    )
    bridge_name: str = Field(
        ...,
        description="Configured bridge name"
    )
    test_timestamp: UTCDateTime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the connectivity test was performed"
    )
    troubleshooting_hints: List[str] = Field(
        default_factory=list,
        description="Suggestions for resolving connectivity issues"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mdns_visible": True,
                "discovered_as": "ArgusAI._hap._tcp.local",
                "port_accessible": True,
                "firewall_issues": [],
                "bind_address": "0.0.0.0",
                "port": 51826,
                "bridge_name": "ArgusAI",
                "test_timestamp": "2025-12-17T10:30:00Z",
                "troubleshooting_hints": []
            }
        }
    )


class HomeKitTestEventRequest(BaseModel):
    """
    Request body for manually triggering a test HomeKit event.

    Used for testing event delivery to paired HomeKit devices.
    """
    camera_id: str = Field(
        ...,
        description="Camera ID to trigger the test event for"
    )
    event_type: str = Field(
        "motion",
        description="Type of event to trigger: motion, occupancy, vehicle, animal, package, doorbell"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "camera_id": "abc-123",
                "event_type": "motion"
            }
        }
    )


class HomeKitTestEventResponse(BaseModel):
    """
    Response from the test event endpoint.
    """
    success: bool = Field(..., description="Whether the test event was triggered successfully")
    message: str = Field(..., description="Status message")
    delivered_to_clients: int = Field(
        0,
        description="Number of connected clients the event was delivered to"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Motion event triggered for Front Door",
                "delivered_to_clients": 2
            }
        }
    )
