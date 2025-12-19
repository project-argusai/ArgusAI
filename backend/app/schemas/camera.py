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
