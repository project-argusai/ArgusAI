"""Pydantic schemas for camera API endpoints"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal, Any
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


class CameraCreate(CameraBase):
    """Schema for creating a new camera"""

    rtsp_url: Optional[str] = Field(None, max_length=500, description="Full RTSP URL")
    username: Optional[str] = Field(None, max_length=100, description="RTSP authentication username")
    password: Optional[str] = Field(None, max_length=100, description="RTSP password (will be encrypted)")
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

    # Note: password field is intentionally omitted (write-only field)

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
