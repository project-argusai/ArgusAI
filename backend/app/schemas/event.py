"""Event API Pydantic schemas for request/response validation"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import List, Optional, Literal


class EventCreate(BaseModel):
    """Schema for creating a new event via POST /api/v1/events"""
    camera_id: str = Field(..., description="UUID of the camera that triggered the event")
    timestamp: datetime = Field(..., description="When the event occurred (UTC with timezone)")
    description: str = Field(..., min_length=1, max_length=5000, description="AI-generated natural language description")
    confidence: int = Field(..., ge=0, le=100, description="AI confidence score (0-100)")
    objects_detected: List[Literal["person", "vehicle", "animal", "package", "unknown"]] = Field(
        ...,
        min_length=1,
        description="List of detected object types"
    )
    thumbnail_path: Optional[str] = Field(None, max_length=500, description="Relative path to thumbnail image (filesystem mode)")
    thumbnail_base64: Optional[str] = Field(None, description="Base64-encoded JPEG thumbnail (database mode)")
    alert_triggered: bool = Field(default=False, description="Whether alert rules were triggered")

    @field_validator('objects_detected')
    @classmethod
    def validate_objects_detected(cls, v):
        """Ensure objects_detected is not empty and contains valid values"""
        if not v:
            raise ValueError("objects_detected must contain at least one object type")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "camera_id": "550e8400-e29b-41d4-a716-446655440000",
                    "timestamp": "2025-11-17T14:30:00Z",
                    "description": "Person walking towards front door carrying a package",
                    "confidence": 85,
                    "objects_detected": ["person", "package"],
                    "thumbnail_base64": "/9j/4AAQSkZJRgABAQEAAA...",
                    "alert_triggered": True
                }
            ]
        }
    }


class EventResponse(BaseModel):
    """Schema for event API responses"""
    id: str = Field(..., description="Event UUID")
    camera_id: str = Field(..., description="Camera UUID")
    timestamp: datetime = Field(..., description="Event timestamp (UTC with timezone)")
    description: str = Field(..., description="AI-generated description")
    confidence: int = Field(..., ge=0, le=100, description="AI confidence score (0-100)")
    objects_detected: List[str] = Field(..., description="Detected object types")
    thumbnail_path: Optional[str] = Field(None, description="Relative thumbnail path")
    thumbnail_base64: Optional[str] = Field(None, description="Base64-encoded thumbnail")
    alert_triggered: bool = Field(..., description="Whether alert was triggered")
    created_at: datetime = Field(..., description="Record creation timestamp (UTC)")

    @field_validator('objects_detected', mode='before')
    @classmethod
    def parse_objects_detected(cls, v):
        """Parse JSON string into list if needed"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    model_config = {
        "from_attributes": True,  # Enable ORM mode for SQLAlchemy models
        "json_schema_extra": {
            "examples": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "camera_id": "550e8400-e29b-41d4-a716-446655440000",
                    "timestamp": "2025-11-17T14:30:00Z",
                    "description": "Person walking towards front door carrying a package",
                    "confidence": 85,
                    "objects_detected": ["person", "package"],
                    "thumbnail_path": "thumbnails/2025-11-17/event_123e4567.jpg",
                    "thumbnail_base64": None,
                    "alert_triggered": True,
                    "created_at": "2025-11-17T14:30:01Z"
                }
            ]
        }
    }


class EventListResponse(BaseModel):
    """Schema for paginated event list responses"""
    events: List[EventResponse] = Field(..., description="List of events in current page")
    total_count: int = Field(..., ge=0, description="Total number of events matching filters")
    has_more: bool = Field(..., description="Whether more results are available")
    next_offset: Optional[int] = Field(None, description="Offset for next page (None if no more results)")
    limit: int = Field(..., ge=1, le=500, description="Number of events per page")
    offset: int = Field(..., ge=0, description="Current offset")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "events": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "camera_id": "550e8400-e29b-41d4-a716-446655440000",
                            "timestamp": "2025-11-17T14:30:00Z",
                            "description": "Person walking towards front door",
                            "confidence": 85,
                            "objects_detected": ["person"],
                            "thumbnail_path": "thumbnails/2025-11-17/event_123e4567.jpg",
                            "thumbnail_base64": None,
                            "alert_triggered": False,
                            "created_at": "2025-11-17T14:30:01Z"
                        }
                    ],
                    "total_count": 150,
                    "has_more": True,
                    "next_offset": 50,
                    "limit": 50,
                    "offset": 0
                }
            ]
        }
    }


class EventStatsResponse(BaseModel):
    """Schema for event statistics aggregation"""
    total_events: int = Field(..., ge=0, description="Total number of events in time range")
    events_by_camera: dict[str, int] = Field(..., description="Event count grouped by camera_id")
    events_by_object_type: dict[str, int] = Field(..., description="Event count grouped by detected object type")
    average_confidence: float = Field(..., ge=0, le=100, description="Average confidence score")
    alerts_triggered: int = Field(..., ge=0, description="Number of events that triggered alerts")
    time_range: dict[str, Optional[datetime]] = Field(
        ...,
        description="Time range of queried events (start, end)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_events": 1247,
                    "events_by_camera": {
                        "550e8400-e29b-41d4-a716-446655440000": 823,
                        "660e8400-e29b-41d4-a716-446655440001": 424
                    },
                    "events_by_object_type": {
                        "person": 892,
                        "vehicle": 245,
                        "animal": 78,
                        "package": 32
                    },
                    "average_confidence": 78.4,
                    "alerts_triggered": 45,
                    "time_range": {
                        "start": "2025-11-10T00:00:00Z",
                        "end": "2025-11-17T23:59:59Z"
                    }
                }
            ]
        }
    }


class EventFilterParams(BaseModel):
    """Query parameters for filtering events"""
    camera_id: Optional[str] = Field(None, description="Filter by camera UUID")
    start_time: Optional[datetime] = Field(None, description="Filter events after this timestamp")
    end_time: Optional[datetime] = Field(None, description="Filter events before this timestamp")
    min_confidence: Optional[int] = Field(None, ge=0, le=100, description="Minimum confidence score")
    object_types: Optional[List[str]] = Field(None, description="Filter by detected object types")
    alert_triggered: Optional[bool] = Field(None, description="Filter by alert status")
    search_query: Optional[str] = Field(None, min_length=1, max_length=500, description="Full-text search in descriptions")
    limit: int = Field(50, ge=1, le=500, description="Number of results per page")
    offset: int = Field(0, ge=0, description="Pagination offset")
    sort_order: Literal["asc", "desc"] = Field("desc", description="Sort by timestamp (newest first by default)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "camera_id": "550e8400-e29b-41d4-a716-446655440000",
                    "start_time": "2025-11-10T00:00:00Z",
                    "end_time": "2025-11-17T23:59:59Z",
                    "min_confidence": 70,
                    "object_types": ["person", "vehicle"],
                    "alert_triggered": True,
                    "search_query": "front door",
                    "limit": 50,
                    "offset": 0,
                    "sort_order": "desc"
                }
            ]
        }
    }
