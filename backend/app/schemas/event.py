"""Event API Pydantic schemas for request/response validation"""
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
from typing import List, Optional, Literal
from app.schemas.feedback import FeedbackResponse

# Story P7-2.1: Human-readable display names for carriers
CARRIER_DISPLAY_NAMES = {
    'fedex': 'FedEx',
    'ups': 'UPS',
    'usps': 'USPS',
    'amazon': 'Amazon',
    'dhl': 'DHL',
}


class MatchedEntitySummary(BaseModel):
    """Summary of a matched entity for event responses (Story P4-3.3)"""
    id: str = Field(..., description="Entity UUID")
    entity_type: str = Field(..., description="Entity type: person, vehicle, or unknown")
    name: Optional[str] = Field(None, description="User-assigned name for the entity")
    first_seen_at: datetime = Field(..., description="Timestamp of first occurrence")
    occurrence_count: int = Field(..., ge=1, description="Number of times this entity has been seen")
    similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Match similarity score")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440123",
                    "entity_type": "person",
                    "name": "Mail Carrier",
                    "first_seen_at": "2025-11-01T10:30:00Z",
                    "occurrence_count": 15,
                    "similarity_score": 0.87
                }
            ]
        }
    }


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
    # Phase 2: UniFi Protect event source fields
    source_type: Literal["rtsp", "usb", "protect"] = Field(default="rtsp", description="Event source type")
    protect_event_id: Optional[str] = Field(None, max_length=100, description="UniFi Protect's native event ID")
    smart_detection_type: Optional[Literal["person", "vehicle", "package", "animal", "motion", "ring"]] = Field(
        None, description="Protect smart detection type"
    )
    is_doorbell_ring: bool = Field(default=False, description="Whether event was triggered by doorbell ring")
    # Story P3-1.4: Fallback reason tracking
    fallback_reason: Optional[str] = Field(None, max_length=100, description="Reason for fallback to snapshot analysis (e.g., 'clip_download_failed')")
    # Story P3-2.6: Multi-frame analysis tracking
    analysis_mode: Optional[str] = Field(None, max_length=20, description="Analysis mode used (single_frame/multi_frame/video_native)")
    frame_count_used: Optional[int] = Field(None, ge=1, le=10, description="Number of frames sent to AI for multi-frame analysis")
    # Story P3-5.3: Audio transcription for doorbell cameras
    audio_transcription: Optional[str] = Field(None, description="Transcribed speech from doorbell audio")
    # Story P3-6.1: AI confidence scoring
    ai_confidence: Optional[int] = Field(None, ge=0, le=100, description="AI self-reported confidence score (0-100)")
    low_confidence: bool = Field(default=False, description="True if ai_confidence < 50 or vague description, flagging uncertain descriptions")
    # Story P3-6.2: Vagueness detection
    vague_reason: Optional[str] = Field(None, description="Human-readable explanation of why description was flagged as vague")

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


class CorrelatedEventResponse(BaseModel):
    """Schema for correlated events in multi-camera event display (Story P2-4.4)"""
    id: str = Field(..., description="Event UUID")
    camera_name: str = Field(..., description="Camera name for display")
    thumbnail_url: Optional[str] = Field(None, description="Full URL to thumbnail image")
    timestamp: datetime = Field(..., description="Event timestamp (UTC)")

    model_config = {
        "from_attributes": True,
    }


class EventResponse(BaseModel):
    """Schema for event API responses"""
    id: str = Field(..., description="Event UUID")
    camera_id: str = Field(..., description="Camera UUID")
    camera_name: Optional[str] = Field(None, description="Human-readable camera name for display")
    timestamp: datetime = Field(..., description="Event timestamp (UTC with timezone)")
    description: str = Field(..., description="AI-generated description")
    confidence: int = Field(..., ge=0, le=100, description="AI confidence score (0-100)")
    objects_detected: List[str] = Field(..., description="Detected object types")
    thumbnail_path: Optional[str] = Field(None, description="Relative thumbnail path")
    thumbnail_base64: Optional[str] = Field(None, description="Base64-encoded thumbnail")
    alert_triggered: bool = Field(..., description="Whether alert was triggered")
    # Phase 2: UniFi Protect event source fields
    source_type: str = Field(default="rtsp", description="Event source type (rtsp, usb, protect)")
    protect_event_id: Optional[str] = Field(None, description="UniFi Protect's native event ID")
    smart_detection_type: Optional[str] = Field(None, description="Protect smart detection type (person/vehicle/package/animal/motion/ring)")
    is_doorbell_ring: bool = Field(default=False, description="Whether event was triggered by doorbell ring")
    created_at: datetime = Field(..., description="Record creation timestamp (UTC)")
    # Story P2-4.4: Multi-camera event correlation
    correlation_group_id: Optional[str] = Field(None, description="UUID linking correlated events across cameras")
    correlated_events: Optional[List["CorrelatedEventResponse"]] = Field(None, description="Related events from same correlation group")
    # Story P2-5.3: AI provider tracking
    provider_used: Optional[str] = Field(None, description="AI provider that generated description (openai/grok/claude/gemini)")
    # Story P3-1.4: Fallback reason tracking
    fallback_reason: Optional[str] = Field(None, description="Reason for fallback to snapshot analysis (e.g., 'clip_download_failed')")
    # Story P3-2.6: Multi-frame analysis tracking
    analysis_mode: Optional[str] = Field(None, description="Analysis mode used (single_frame/multi_frame/video_native)")
    frame_count_used: Optional[int] = Field(None, description="Number of frames sent to AI for multi-frame analysis")
    # Story P3-5.3: Audio transcription for doorbell cameras
    audio_transcription: Optional[str] = Field(None, description="Transcribed speech from doorbell audio")
    # Story P3-6.1: AI confidence scoring
    ai_confidence: Optional[int] = Field(None, ge=0, le=100, description="AI self-reported confidence score (0-100)")
    low_confidence: bool = Field(default=False, description="True if ai_confidence < 50 or vague description, flagging uncertain descriptions")
    # Story P3-6.2: Vagueness detection
    vague_reason: Optional[str] = Field(None, description="Human-readable explanation of why description was flagged as vague")
    # Story P3-6.4: Re-analysis tracking
    reanalyzed_at: Optional[datetime] = Field(None, description="Timestamp of last re-analysis (null = never re-analyzed)")
    reanalysis_count: int = Field(default=0, ge=0, description="Number of re-analyses performed")
    # Story P3-7.1: AI cost tracking
    ai_cost: Optional[float] = Field(None, description="Estimated cost in USD for AI analysis")
    # Story P3-7.5: Key frames gallery display
    key_frames_base64: Optional[List[str]] = Field(None, description="Base64-encoded key frames used for AI analysis")
    frame_timestamps: Optional[List[float]] = Field(None, description="Timestamps in seconds for each key frame")
    # Story P4-3.3: Recurring Visitor Detection
    matched_entity: Optional["MatchedEntitySummary"] = Field(None, description="Matched recurring entity, if any")
    # Story P4-5.1: User Feedback
    feedback: Optional[FeedbackResponse] = Field(None, description="User feedback on this event's description")
    # Story P6-3.2: Audio event detection
    audio_event_type: Optional[str] = Field(None, description="Detected audio event type (glass_break/gunshot/scream/doorbell/other)")
    audio_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Audio event detection confidence score (0.0-1.0)")
    audio_duration_ms: Optional[int] = Field(None, ge=0, description="Duration of audio event in milliseconds")
    # Story P7-2.1: Delivery carrier detection
    delivery_carrier: Optional[str] = Field(None, description="Detected delivery carrier (fedex/ups/usps/amazon/dhl)")
    delivery_carrier_display: Optional[str] = Field(None, description="Human-readable carrier name (FedEx/UPS/USPS/Amazon/DHL)")

    @field_validator('objects_detected', mode='before')
    @classmethod
    def parse_objects_detected(cls, v):
        """Parse JSON string into list if needed"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @field_validator('key_frames_base64', mode='before')
    @classmethod
    def parse_key_frames_base64(cls, v):
        """Parse JSON string into list if needed (Story P3-7.5)"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @field_validator('frame_timestamps', mode='before')
    @classmethod
    def parse_frame_timestamps(cls, v):
        """Parse JSON string into list if needed (Story P3-7.5)"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @model_validator(mode='after')
    def compute_delivery_carrier_display(self) -> 'EventResponse':
        """Compute human-readable carrier display name from carrier code (Story P7-2.1)"""
        if self.delivery_carrier:
            self.delivery_carrier_display = CARRIER_DISPLAY_NAMES.get(
                self.delivery_carrier,
                self.delivery_carrier.upper()  # Fallback: uppercase the code
            )
        return self

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
    # Story P3-7.6: Analysis mode filtering
    analysis_mode: Optional[str] = Field(None, description="Filter by analysis mode (single_frame, multi_frame, video_native - comma-separated for multiple)")
    has_fallback: Optional[bool] = Field(None, description="Filter events with non-null fallback_reason (True = has fallback)")
    low_confidence: Optional[bool] = Field(None, description="Filter events with low_confidence flag (True = uncertain descriptions)")
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


class ReanalyzeRequest(BaseModel):
    """Schema for event re-analysis request (Story P3-6.4)

    Used by POST /api/v1/events/{id}/reanalyze endpoint.
    """
    analysis_mode: Literal["single_frame", "multi_frame", "video_native"] = Field(
        ...,
        description="Analysis mode to use for re-analysis: single_frame, multi_frame, or video_native"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "analysis_mode": "multi_frame"
                }
            ]
        }
    }


# Story P7-2.4: Package Delivery Dashboard Widget Schemas
class PackageEventSummary(BaseModel):
    """Summary of a package delivery event for dashboard widget"""
    id: str = Field(..., description="Event UUID")
    timestamp: datetime = Field(..., description="Event timestamp (UTC)")
    delivery_carrier: Optional[str] = Field(None, description="Detected carrier code (fedex/ups/usps/amazon/dhl)")
    delivery_carrier_display: str = Field(..., description="Human-readable carrier name")
    camera_name: str = Field(..., description="Camera name for display")
    thumbnail_path: Optional[str] = Field(None, description="Relative path to thumbnail")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "timestamp": "2025-12-19T14:30:00Z",
                    "delivery_carrier": "fedex",
                    "delivery_carrier_display": "FedEx",
                    "camera_name": "Front Door",
                    "thumbnail_path": "thumbnails/2025-12-19/event_123.jpg"
                }
            ]
        }
    }


class PackageDeliveriesTodayResponse(BaseModel):
    """Response schema for GET /api/v1/events/packages/today (Story P7-2.4)"""
    total_count: int = Field(..., ge=0, description="Total package deliveries today")
    by_carrier: dict[str, int] = Field(..., description="Package count by carrier code")
    recent_events: List[PackageEventSummary] = Field(..., description="Recent 5 package delivery events")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_count": 5,
                    "by_carrier": {"fedex": 2, "ups": 1, "amazon": 1, "unknown": 1},
                    "recent_events": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "timestamp": "2025-12-19T14:30:00Z",
                            "delivery_carrier": "fedex",
                            "delivery_carrier_display": "FedEx",
                            "camera_name": "Front Door",
                            "thumbnail_path": "thumbnails/2025-12-19/event_123.jpg"
                        }
                    ]
                }
            ]
        }
    }
