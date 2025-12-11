"""
MQTT Payload Schemas for Camera Status Sensors (Story P4-2.5)

Defines Pydantic schemas for MQTT payloads:
- CameraStatusPayload: Online/offline/unavailable status
- CameraCountsPayload: Event counts (today/week)
- CameraActivityPayload: Binary activity sensor (ON/OFF)
- LastEventPayload: Last event timestamp and details

All schemas serialize to JSON for MQTT publishing.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CameraStatusPayload(BaseModel):
    """
    Camera status payload for MQTT publishing (AC1, AC9).

    Published to: {topic_prefix}/camera/{camera_id}/status

    Attributes:
        camera_id: Camera UUID
        camera_name: Human-readable camera name
        status: Current status (online, offline, unavailable)
        source_type: Camera source type (rtsp, usb, protect)
        last_updated: ISO timestamp of status update
    """
    camera_id: str
    camera_name: str
    status: Literal["online", "offline", "unavailable"]
    source_type: str = Field(description="Camera type: rtsp, usb, or protect")
    last_updated: datetime


class CameraCountsPayload(BaseModel):
    """
    Event counts payload for MQTT publishing (AC3, AC10).

    Published to: {topic_prefix}/camera/{camera_id}/counts

    Attributes:
        camera_id: Camera UUID
        camera_name: Human-readable camera name
        events_today: Number of events since midnight local time
        events_this_week: Number of events since Monday 00:00 local time
        last_updated: ISO timestamp of count update
    """
    camera_id: str
    camera_name: str
    events_today: int = Field(ge=0, description="Events since midnight")
    events_this_week: int = Field(ge=0, description="Events since Monday")
    last_updated: datetime


class CameraActivityPayload(BaseModel):
    """
    Binary activity sensor payload for MQTT publishing (AC4).

    Published to: {topic_prefix}/camera/{camera_id}/activity

    Activity is ON when an event occurred in the last 5 minutes.

    Attributes:
        camera_id: Camera UUID
        state: Activity state (ON or OFF)
        last_event_at: ISO timestamp of most recent event (if any)
    """
    camera_id: str
    state: Literal["ON", "OFF"]
    last_event_at: Optional[datetime] = None


class LastEventPayload(BaseModel):
    """
    Last event timestamp payload for MQTT publishing (AC2).

    Published to: {topic_prefix}/camera/{camera_id}/last_event

    Attributes:
        camera_id: Camera UUID
        camera_name: Human-readable camera name
        event_id: UUID of the most recent event
        timestamp: ISO timestamp when the event occurred
        description_snippet: First 100 chars of event description
        smart_detection_type: Detection type if available (person, vehicle, etc.)
    """
    camera_id: str
    camera_name: str
    event_id: str
    timestamp: datetime
    description_snippet: str = Field(max_length=100, description="First 100 chars of description")
    smart_detection_type: Optional[str] = None
