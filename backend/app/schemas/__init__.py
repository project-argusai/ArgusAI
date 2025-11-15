"""Pydantic schemas for request/response validation"""
from app.schemas.camera import (
    CameraBase,
    CameraCreate,
    CameraUpdate,
    CameraResponse,
    CameraTestResponse,
)
from app.schemas.motion import (
    BoundingBox,
    MotionConfigUpdate,
    MotionConfigResponse,
    MotionTestRequest,
    MotionTestResponse,
    MotionEventResponse,
    MotionEventStatsResponse,
    DetectionZone,
    DetectionSchedule,
)

__all__ = [
    "CameraBase",
    "CameraCreate",
    "CameraUpdate",
    "CameraResponse",
    "CameraTestResponse",
    "BoundingBox",
    "MotionConfigUpdate",
    "MotionConfigResponse",
    "MotionTestRequest",
    "MotionTestResponse",
    "MotionEventResponse",
    "MotionEventStatsResponse",
    "DetectionZone",
    "DetectionSchedule",
]
