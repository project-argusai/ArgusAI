"""Pydantic schemas for motion detection API endpoints"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, List, Dict
from datetime import datetime


class BoundingBox(BaseModel):
    """Bounding box coordinates for detected motion"""
    x: int = Field(..., ge=0, description="X coordinate of top-left corner")
    y: int = Field(..., ge=0, description="Y coordinate of top-left corner")
    width: int = Field(..., gt=0, description="Width of bounding box")
    height: int = Field(..., gt=0, description="Height of bounding box")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"x": 100, "y": 50, "width": 200, "height": 300}
            ]
        }
    }


class MotionConfigUpdate(BaseModel):
    """Schema for updating motion detection configuration"""
    motion_enabled: Optional[bool] = Field(None, description="Whether motion detection is active")
    motion_sensitivity: Optional[Literal['low', 'medium', 'high']] = Field(
        None,
        description="Motion detection sensitivity level"
    )
    motion_cooldown: Optional[int] = Field(
        None,
        ge=0,
        le=300,
        description="Seconds between motion triggers (0-300)"
    )
    motion_algorithm: Optional[Literal['mog2', 'knn', 'frame_diff']] = Field(
        None,
        description="Motion detection algorithm"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "motion_enabled": True,
                    "motion_sensitivity": "medium",
                    "motion_cooldown": 60,
                    "motion_algorithm": "mog2"
                }
            ]
        }
    }


class MotionConfigResponse(BaseModel):
    """Schema for motion configuration response"""
    motion_enabled: bool
    motion_sensitivity: Literal['low', 'medium', 'high']
    motion_cooldown: int
    motion_algorithm: Literal['mog2', 'knn', 'frame_diff']

    model_config = {
        "from_attributes": True
    }


class MotionTestRequest(BaseModel):
    """Schema for motion test endpoint request"""
    sensitivity: Optional[Literal['low', 'medium', 'high']] = Field(
        None,
        description="Override sensitivity for test"
    )
    algorithm: Optional[Literal['mog2', 'knn', 'frame_diff']] = Field(
        None,
        description="Override algorithm for test"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"sensitivity": "high", "algorithm": "mog2"}
            ]
        }
    }


class MotionTestResponse(BaseModel):
    """Schema for motion test endpoint response"""
    motion_detected: bool = Field(..., description="Whether motion was detected")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    bounding_box: Optional[BoundingBox] = Field(None, description="Motion bounding box")
    preview_image: str = Field(..., description="Base64-encoded preview image with overlay")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "motion_detected": True,
                    "confidence": 0.85,
                    "bounding_box": {"x": 100, "y": 50, "width": 200, "height": 300},
                    "preview_image": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
                }
            ]
        }
    }


class MotionEventResponse(BaseModel):
    """Schema for motion event API response"""
    id: str = Field(..., description="Event UUID")
    camera_id: str = Field(..., description="Camera UUID")
    timestamp: datetime = Field(..., description="Motion detection timestamp")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    motion_intensity: Optional[float] = Field(None, description="Motion intensity metric")
    algorithm_used: str = Field(..., description="Algorithm that detected motion")
    bounding_box: Optional[Dict] = Field(None, description="Motion bounding box (JSON)")
    frame_thumbnail: Optional[str] = Field(None, description="Base64-encoded JPEG thumbnail")
    ai_event_id: Optional[str] = Field(None, description="Linked AI event ID (F3)")
    created_at: datetime = Field(..., description="Record creation timestamp")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "camera_id": "660e8400-e29b-41d4-a716-446655440000",
                    "timestamp": "2025-11-15T14:30:00Z",
                    "confidence": 0.92,
                    "motion_intensity": 15.5,
                    "algorithm_used": "mog2",
                    "bounding_box": {"x": 150, "y": 75, "width": 250, "height": 400},
                    "frame_thumbnail": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
                    "ai_event_id": None,
                    "created_at": "2025-11-15T14:30:01Z"
                }
            ]
        }
    }


class MotionEventStatsResponse(BaseModel):
    """Schema for motion event statistics response"""
    total_events: int = Field(..., description="Total number of motion events")
    events_by_camera: Dict[str, int] = Field(..., description="Event counts by camera ID")
    events_by_hour: Dict[int, int] = Field(..., description="Event counts by hour (0-23)")
    average_confidence: float = Field(..., ge=0.0, le=1.0, description="Average confidence score")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_events": 157,
                    "events_by_camera": {
                        "camera-1": 89,
                        "camera-2": 68
                    },
                    "events_by_hour": {
                        "0": 2, "1": 1, "2": 0, "3": 0, "4": 0, "5": 3,
                        "6": 12, "7": 18, "8": 15, "9": 10, "10": 8,
                        "11": 7, "12": 9, "13": 11, "14": 14, "15": 13,
                        "16": 9, "17": 7, "18": 8, "19": 5, "20": 3,
                        "21": 1, "22": 1, "23": 0
                    },
                    "average_confidence": 0.87
                }
            ]
        }
    }


# Future F2.2: Detection Zones (polygon-based)
class DetectionZone(BaseModel):
    """Schema for polygon detection zone (future F2.2)"""
    id: str = Field(..., description="Zone UUID")
    name: str = Field(..., min_length=1, max_length=100, description="Zone name")
    vertices: List[Dict[str, int]] = Field(..., min_length=3, description="Polygon vertices [{x, y}, ...]")
    enabled: bool = Field(default=True, description="Whether zone is active")

    @field_validator('vertices')
    @classmethod
    def validate_polygon(cls, v):
        """Validate polygon has at least 3 vertices and auto-close if needed"""
        if len(v) < 3:
            raise ValueError("Polygon must have at least 3 vertices")

        # Check each vertex has x and y
        for vertex in v:
            if 'x' not in vertex or 'y' not in vertex:
                raise ValueError("Each vertex must have 'x' and 'y' coordinates")

        # Auto-close polygon if not already closed
        if v[0] != v[-1]:
            v.append(v[0].copy())

        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "zone-1",
                    "name": "Front Yard",
                    "vertices": [
                        {"x": 100, "y": 100},
                        {"x": 500, "y": 100},
                        {"x": 500, "y": 400},
                        {"x": 100, "y": 400}
                    ],
                    "enabled": True
                }
            ]
        }
    }


# Future F2.3: Detection Schedules
class DetectionSchedule(BaseModel):
    """Schema for detection schedule (future F2.3)"""
    id: str = Field(..., description="Schedule UUID")
    name: str = Field(..., min_length=1, max_length=100, description="Schedule name")
    days_of_week: List[int] = Field(..., description="Days active (0=Mon, 6=Sun)")
    start_time: str = Field(..., pattern=r'^([01]\d|2[0-3]):([0-5]\d)$', description="Start time (HH:MM)")
    end_time: str = Field(..., pattern=r'^([01]\d|2[0-3]):([0-5]\d)$', description="End time (HH:MM)")
    enabled: bool = Field(default=True, description="Whether schedule is active")

    @field_validator('days_of_week')
    @classmethod
    def validate_days(cls, v):
        """Validate days are 0-6 (Monday-Sunday)"""
        if not all(0 <= day <= 6 for day in v):
            raise ValueError("Days must be 0-6 (0=Monday, 6=Sunday)")
        if len(v) == 0:
            raise ValueError("At least one day must be selected")
        return sorted(list(set(v)))  # Remove duplicates and sort

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "schedule-1",
                    "name": "Weekday Daytime",
                    "days_of_week": [0, 1, 2, 3, 4],
                    "start_time": "08:00",
                    "end_time": "18:00",
                    "enabled": True
                }
            ]
        }
    }
