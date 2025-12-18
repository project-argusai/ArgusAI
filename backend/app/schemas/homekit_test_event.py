"""
HomeKit Test Event Pydantic Schemas (Story P7-1.3)

Defines schemas for the manual test event trigger endpoint.
Allows triggering motion/occupancy/vehicle/animal/package/doorbell events
from the diagnostics UI to verify HomeKit event delivery.
"""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# Valid event types that can be triggered
EventType = Literal["motion", "occupancy", "vehicle", "animal", "package", "doorbell"]


class HomeKitTestEventRequest(BaseModel):
    """
    Request body for triggering a test HomeKit event (Story P7-1.3 AC5).

    Used by POST /api/v1/homekit/test-event to manually trigger events
    for testing HomeKit integration and event delivery.
    """
    camera_id: str = Field(
        ...,
        description="Camera identifier (UUID) to trigger the event for",
        min_length=1,
        max_length=100
    )
    event_type: EventType = Field(
        default="motion",
        description="Type of event to trigger: motion, occupancy, vehicle, animal, package, or doorbell"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "camera_id": "abc-123-def-456",
                "event_type": "motion"
            }
        }
    )


class HomeKitTestEventResponse(BaseModel):
    """
    Response from test event trigger (Story P7-1.3 AC5).

    Confirms whether the test event was successfully triggered and
    provides details about delivery to connected HomeKit clients.
    """
    success: bool = Field(
        ...,
        description="Whether the event was triggered successfully"
    )
    message: str = Field(
        ...,
        description="Human-readable result message"
    )
    camera_id: str = Field(
        ...,
        description="Camera identifier that was triggered"
    )
    event_type: str = Field(
        ...,
        description="Type of event that was triggered"
    )
    sensor_name: Optional[str] = Field(
        None,
        description="Name of the HomeKit sensor that was triggered"
    )
    delivered_to_clients: int = Field(
        0,
        description="Number of connected HomeKit clients that received the event"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the event was triggered"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Motion event triggered for Front Door Motion",
                "camera_id": "abc-123-def-456",
                "event_type": "motion",
                "sensor_name": "Front Door Motion",
                "delivered_to_clients": 2,
                "timestamp": "2025-12-18T10:30:00Z"
            }
        }
    )
