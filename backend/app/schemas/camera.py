"""Pydantic schemas for camera API endpoints"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal, Any, List
from datetime import datetime
import json


class CameraBase(BaseModel):
    """Base camera schema with common fields"""

    name: str = Field(..., min_length=1, max_length=100, description="User-friendly camera name")
    type: Literal['rtsp', 'usb'] = Field(..., description="Camera type: rtsp or usb")
    frame_rate: int = Field(default=5, ge=1, le=30, description="Target frames per second")
    is_enabled: bool = Field(default=True, description="Whether camera capture is active")
    motion_enabled: bool = Field(default=True, description="Whether motion detection is active")
    motion_sensitivity: Literal['low', 'medium', 'high'] = Field(
        default='medium',
        description="Motion detection sensitivity level"
    )
    motion_cooldown: int = Field(
        default=60,
        ge=0,
        le=300,
        description="Seconds between motion triggers"
    )
    motion_algorithm: Literal['mog2', 'knn', 'frame_diff'] = Field(
        default='mog2',
        description="Motion detection algorithm"
    )
    # Phase 3: Analysis mode for AI processing
    analysis_mode: Literal['single_frame', 'multi_frame', 'video_native'] = Field(
        default='single_frame',
        description="AI analysis mode: single_frame (fast, low cost), multi_frame (balanced), video_native (best quality, highest cost)"
    )
    # Phase 7: HomeKit streaming quality
    homekit_stream_quality: Literal['low', 'medium', 'high'] = Field(
        default='medium',
        description="HomeKit stream quality: low (480p, 15fps), medium (720p, 25fps), high (1080p, 30fps)"
    )


class CameraCreate(CameraBase):
    """Schema for creating a new camera"""

    rtsp_url: Optional[str] = Field(None, max_length=500, description="Full RTSP URL")
    username: Optional[str] = Field(None, max_length=100, description="RTSP authentication username")
    password: Optional[str] = Field(None, max_length=100, description="RTSP password (will be encrypted)")
    device_index: Optional[int] = Field(None, ge=0, description="USB camera device index (0, 1, 2, ...)")
    # Phase 6 (P6-3.3): Audio settings
    audio_enabled: bool = Field(default=False, description="Whether audio stream extraction is enabled")
    audio_event_types: Optional[Any] = Field(None, description="JSON array of audio event types to detect: glass_break, gunshot, scream, doorbell")
    audio_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Per-camera confidence threshold override (0.0-1.0)")

    @field_validator('audio_event_types', mode='before')
    @classmethod
    def serialize_audio_event_types_create(cls, v):
        """Convert audio_event_types from list to JSON string if needed"""
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return json.dumps(v)

    @model_validator(mode='after')
    def validate_camera_fields(self):
        """Validate camera-type-specific required fields"""
        if self.type == 'rtsp':
            if not self.rtsp_url:
                raise ValueError("RTSP URL required for RTSP cameras")
            if not self.rtsp_url.startswith(('rtsp://', 'rtsps://')):
                raise ValueError("RTSP URL must start with rtsp:// or rtsps://")

        if self.type == 'usb':
            if self.device_index is None:
                raise ValueError("Device index required for USB cameras")

        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Front Door Camera",
                    "type": "rtsp",
                    "rtsp_url": "rtsp://192.168.1.50:554/stream1",
                    "username": "admin",
                    "password": "secret123",
                    "frame_rate": 5,
                    "is_enabled": True,
                    "motion_sensitivity": "medium",
                    "motion_cooldown": 60
                },
                {
                    "name": "Webcam",
                    "type": "usb",
                    "device_index": 0,
                    "frame_rate": 15,
                    "is_enabled": True
                }
            ]
        }
    }


class CameraUpdate(BaseModel):
    """Schema for updating an existing camera (all fields optional)"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    rtsp_url: Optional[str] = Field(None, max_length=500)
    username: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, max_length=100)
    frame_rate: Optional[int] = Field(None, ge=1, le=30)
    is_enabled: Optional[bool] = None
    motion_enabled: Optional[bool] = None
    motion_sensitivity: Optional[Literal['low', 'medium', 'high']] = None
    motion_cooldown: Optional[int] = Field(None, ge=0, le=300)
    motion_algorithm: Optional[Literal['mog2', 'knn', 'frame_diff']] = None
    detection_zones: Optional[Any] = Field(None, description="JSON array of DetectionZone objects (accepts object or string)")
    detection_schedule: Optional[Any] = Field(None, description="JSON object: DetectionSchedule schema (accepts object or string)")
    # Phase 3: Analysis mode for AI processing
    analysis_mode: Optional[Literal['single_frame', 'multi_frame', 'video_native']] = Field(
        None,
        description="AI analysis mode: single_frame (fast, low cost), multi_frame (balanced), video_native (best quality, highest cost)"
    )
    # Phase 7: HomeKit streaming quality
    homekit_stream_quality: Optional[Literal['low', 'medium', 'high']] = Field(
        None,
        description="HomeKit stream quality: low (480p, 15fps), medium (720p, 25fps), high (1080p, 30fps)"
    )
    # Phase 6 (P6-3.1): Audio stream extraction
    audio_enabled: Optional[bool] = Field(None, description="Whether audio stream extraction is enabled")
    # Phase 6 (P6-3.3): Per-camera audio event settings
    audio_event_types: Optional[Any] = Field(None, description="JSON array of audio event types to detect: glass_break, gunshot, scream, doorbell")
    audio_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Per-camera confidence threshold override (0.0-1.0)")

    @field_validator('audio_event_types', mode='before')
    @classmethod
    def serialize_audio_event_types(cls, v):
        """Convert audio_event_types from list to JSON string if needed"""
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return json.dumps(v)

    @field_validator('detection_zones', mode='before')
    @classmethod
    def serialize_detection_zones(cls, v):
        """Convert detection_zones from object to JSON string if needed"""
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return json.dumps(v)

    @field_validator('detection_schedule', mode='before')
    @classmethod
    def serialize_detection_schedule(cls, v):
        """Convert detection_schedule from object to JSON string if needed"""
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return json.dumps(v)


class CameraResponse(CameraBase):
    """Schema for camera API responses"""

    id: str = Field(..., description="Camera UUID")
    rtsp_url: Optional[str] = Field(None, description="RTSP URL (credentials removed)")
    username: Optional[str] = None
    device_index: Optional[int] = None
    detection_zones: Optional[Any] = Field(None, description="JSON array of DetectionZone objects")
    detection_schedule: Optional[Any] = Field(None, description="JSON object: DetectionSchedule schema")
    created_at: datetime
    updated_at: datetime

    # Phase 2: Source type and Protect integration fields
    source_type: Optional[Literal['rtsp', 'usb', 'protect']] = Field(None, description="Camera source: rtsp, usb, or protect")
    protect_controller_id: Optional[str] = Field(None, description="UniFi Protect controller ID")
    protect_camera_id: Optional[str] = Field(None, description="Camera ID in Protect system")
    protect_camera_type: Optional[str] = Field(None, description="Protect camera model type")
    smart_detection_types: Optional[Any] = Field(None, description="Enabled smart detection types")
    is_doorbell: Optional[bool] = Field(None, description="Whether camera is a doorbell")

    # Phase 6 (P6-3.1): Audio stream extraction fields
    audio_enabled: bool = Field(default=False, description="Whether audio stream extraction is enabled")
    audio_codec: Optional[str] = Field(None, description="Detected audio codec: 'aac', 'pcmu', 'opus', etc.")
    # Phase 6 (P6-3.3): Per-camera audio event settings
    audio_event_types: Optional[Any] = Field(None, description="JSON array of audio event types to detect")
    audio_threshold: Optional[float] = Field(None, description="Per-camera confidence threshold override (0.0-1.0)")

    # Note: password field is intentionally omitted (write-only field)
    # Note: analysis_mode and homekit_stream_quality are inherited from CameraBase

    # Runtime capture health (populated by CameraService when available)
    capture_disabled: Optional[bool] = Field(None, description="Whether capture has been disabled (manually or by recovery policy)")
    restart_attempts: Optional[int] = Field(None, description="Number of recent automatic restart attempts")
    worker_status: Optional[str] = Field(None, description="Current worker status (connected, dead, reconnecting, etc.)")
    worker_alive: Optional[bool] = Field(None, description="Whether the capture worker is currently considered alive")

    @field_validator('audio_event_types', mode='before')
    @classmethod
    def deserialize_audio_event_types(cls, v):
        """Convert audio_event_types from JSON string to list"""
        if v is None or v == '':
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @field_validator('detection_zones', mode='before')
    @classmethod
    def deserialize_detection_zones(cls, v):
        """Convert detection_zones from JSON string to object"""
        if v is None or v == '':
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @field_validator('detection_schedule', mode='before')
    @classmethod
    def deserialize_detection_schedule(cls, v):
        """Convert detection_schedule from JSON string to object"""
        if v is None or v == '':
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    model_config = {
        "from_attributes": True,  # Enable ORM mode for SQLAlchemy models
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Front Door Camera",
                    "type": "rtsp",
                    "rtsp_url": "rtsp://192.168.1.50:554/stream1",
                    "username": "admin",
                    "frame_rate": 5,
                    "is_enabled": True,
                    "motion_sensitivity": "medium",
                    "motion_cooldown": 60,
                    "created_at": "2025-11-15T10:30:00Z",
                    "updated_at": "2025-11-15T10:30:00Z"
                }
            ]
        }
    }


class CameraTestResponse(BaseModel):
    """Schema for camera connection test response"""

    success: bool = Field(..., description="Whether connection test succeeded")
    message: str = Field(..., description="Human-readable result message")
    thumbnail: Optional[str] = Field(None, description="Base64-encoded JPEG thumbnail (if successful)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "message": "Connection successful",
                    "thumbnail": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
                },
                {
                    "success": False,
                    "message": "Authentication failed. Check username and password."
                }
            ]
        }
    }


class CameraTestRequest(BaseModel):
    """Schema for testing camera connection before saving (no database record created)"""

    type: Literal['rtsp', 'usb'] = Field(..., description="Camera type: rtsp or usb")
    rtsp_url: Optional[str] = Field(None, max_length=500, description="Full RTSP URL")
    username: Optional[str] = Field(None, max_length=100, description="RTSP authentication username")
    password: Optional[str] = Field(None, max_length=100, description="RTSP password (plain text, not persisted)")
    device_index: Optional[int] = Field(None, ge=0, description="USB camera device index (0, 1, 2, ...)")

    @model_validator(mode='after')
    def validate_camera_fields(self):
        """Validate camera-type-specific required fields"""
        if self.type == 'rtsp':
            if not self.rtsp_url:
                raise ValueError("RTSP URL required for RTSP cameras")
            if not self.rtsp_url.startswith(('rtsp://', 'rtsps://')):
                raise ValueError("RTSP URL must start with rtsp:// or rtsps://")

        if self.type == 'usb':
            if self.device_index is None:
                raise ValueError("Device index required for USB cameras")

        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "rtsp",
                    "rtsp_url": "rtsp://192.168.1.50:554/stream1",
                    "username": "admin",
                    "password": "secret123"
                },
                {
                    "type": "usb",
                    "device_index": 0
                }
            ]
        }
    }


class CameraTestDetailedResponse(BaseModel):
    """Schema for pre-save camera connection test response with stream info"""

    success: bool = Field(..., description="Whether connection test succeeded")
    message: str = Field(..., description="Human-readable result message")
    thumbnail: Optional[str] = Field(None, description="Base64-encoded JPEG thumbnail with data URI prefix")
    resolution: Optional[str] = Field(None, description="Stream resolution (e.g., '1920x1080')")
    fps: Optional[float] = Field(None, description="Frames per second")
    codec: Optional[str] = Field(None, description="Video codec (e.g., 'h264', 'MJPG')")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "message": "Connection successful",
                    "thumbnail": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
                    "resolution": "1920x1080",
                    "fps": 30.0,
                    "codec": "h264"
                },
                {
                    "success": False,
                    "message": "Authentication failed. Check username and password."
                }
            ]
        }
    }


# ============================================================================
# Live Streaming Schemas (Story P16-2.2)
# ============================================================================

class StreamQualityOption(BaseModel):
    """Schema for a single stream quality option"""

    id: str = Field(..., description="Quality level identifier: low, medium, high")
    label: str = Field(..., description="Human-readable label (e.g., '720p @ 10fps')")
    resolution: str = Field(..., description="Resolution string (e.g., '1280x720')")
    fps: int = Field(..., description="Frames per second for this quality level")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "medium",
                    "label": "720p @ 10fps",
                    "resolution": "1280x720",
                    "fps": 10
                }
            ]
        }
    }


class StreamInfoResponse(BaseModel):
    """Schema for stream information response (GET /cameras/{id}/stream/info)"""

    camera_id: str = Field(..., description="Camera UUID")
    type: str = Field(default="websocket", description="Stream type: websocket")
    websocket_path: str = Field(..., description="WebSocket path for stream connection")
    snapshot_path: str = Field(..., description="Path to get current snapshot")
    quality_options: List[StreamQualityOption] = Field(..., description="Available quality levels")
    default_quality: str = Field(..., description="Default quality level")
    current_clients: int = Field(..., description="Number of currently connected clients")
    max_clients_available: int = Field(..., description="Remaining client slots available")
    is_available: bool = Field(..., description="Whether streaming is available for this camera")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "camera_id": "550e8400-e29b-41d4-a716-446655440000",
                    "type": "websocket",
                    "websocket_path": "/api/v1/cameras/550e8400-e29b-41d4-a716-446655440000/stream",
                    "snapshot_path": "/api/v1/cameras/550e8400-e29b-41d4-a716-446655440000/stream/snapshot",
                    "quality_options": [
                        {"id": "low", "label": "360p @ 5fps", "resolution": "640x360", "fps": 5},
                        {"id": "medium", "label": "720p @ 10fps", "resolution": "1280x720", "fps": 10},
                        {"id": "high", "label": "1080p @ 15fps", "resolution": "1920x1080", "fps": 15}
                    ],
                    "default_quality": "medium",
                    "current_clients": 2,
                    "max_clients_available": 8,
                    "is_available": True
                }
            ]
        }
    }


class StreamSnapshotResponse(BaseModel):
    """Schema for stream snapshot response (GET /cameras/{id}/stream/snapshot)"""

    success: bool = Field(..., description="Whether snapshot capture succeeded")
    timestamp: datetime = Field(..., description="Timestamp of snapshot capture")
    quality: str = Field(..., description="Quality level used for snapshot")
    image_base64: Optional[str] = Field(None, description="Base64-encoded JPEG image data")
    error: Optional[str] = Field(None, description="Error message if capture failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "timestamp": "2026-01-01T12:00:00Z",
                    "quality": "medium",
                    "image_base64": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
                },
                {
                    "success": False,
                    "timestamp": "2026-01-01T12:00:00Z",
                    "quality": "medium",
                    "error": "Camera not connected"
                }
            ]
        }
    }


class StreamMetricsResponse(BaseModel):
    """Schema for stream metrics response (GET /cameras/stream/metrics)"""

    active_streams: int = Field(..., description="Number of active camera streams")
    total_clients: int = Field(..., description="Total connected WebSocket clients")
    max_concurrent: int = Field(..., description="Maximum concurrent streams allowed")
    streams_started_total: int = Field(..., description="Total streams started since server start")
    streams_stopped_total: int = Field(..., description="Total streams stopped since server start")
    connection_errors_total: int = Field(..., description="Total connection errors since server start")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "active_streams": 3,
                    "total_clients": 5,
                    "max_concurrent": 10,
                    "streams_started_total": 42,
                    "streams_stopped_total": 39,
                    "connection_errors_total": 2
                }
            ]
        }
    }


class StreamWebSocketMessage(BaseModel):
    """Schema for WebSocket control messages (sent by client)"""

    type: Literal["quality_change", "ping"] = Field(..., description="Message type")
    quality: Optional[str] = Field(None, description="New quality level (for quality_change)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"type": "quality_change", "quality": "high"},
                {"type": "ping"}
            ]
        }
    }


class StreamWebSocketResponse(BaseModel):
    """Schema for WebSocket control responses (sent by server)"""

    type: Literal["quality_changed", "pong", "error", "info"] = Field(..., description="Response type")
    quality: Optional[str] = Field(None, description="Current quality level")
    message: Optional[str] = Field(None, description="Info or error message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"type": "quality_changed", "quality": "high", "timestamp": "2026-01-01T12:00:00Z"},
                {"type": "pong", "timestamp": "2026-01-01T12:00:00Z"},
                {"type": "error", "message": "Invalid quality level", "timestamp": "2026-01-01T12:00:00Z"}
            ]
        }
    }
