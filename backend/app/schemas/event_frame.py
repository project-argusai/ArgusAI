"""
Pydantic schemas for EventFrame API responses

Story P8-2.1: Store All Analysis Frames During Event Processing
"""
from datetime import datetime
from app.schemas.types import UTCDateTime
from typing import Optional
from pydantic import BaseModel, Field


class EventFrameResponse(BaseModel):
    """
    Response schema for event frame data.

    Used in API responses when retrieving frame information for events.
    """
    id: str = Field(..., description="UUID of the frame record")
    event_id: str = Field(..., description="UUID of the parent event")
    frame_number: int = Field(..., ge=1, description="1-indexed frame number within the event")
    frame_path: str = Field(..., description="Relative path to the frame file")
    timestamp_offset_ms: int = Field(..., ge=0, description="Milliseconds from video start")
    width: Optional[int] = Field(None, ge=1, description="Frame width in pixels")
    height: Optional[int] = Field(None, ge=1, description="Frame height in pixels")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="Frame file size in bytes")
    created_at: UTCDateTime = Field(..., description="Record creation timestamp")

    # Computed URL for frontend access
    url: Optional[str] = Field(None, description="URL to access the frame image")

    class Config:
        from_attributes = True


class EventFrameListResponse(BaseModel):
    """
    Response schema for listing frames for an event.
    """
    event_id: str = Field(..., description="UUID of the parent event")
    frames: list[EventFrameResponse] = Field(default_factory=list, description="List of frames")
    total_count: int = Field(..., ge=0, description="Total number of frames")
    total_size_bytes: int = Field(..., ge=0, description="Total size of all frames in bytes")


class EventFrameCreate(BaseModel):
    """
    Schema for creating an event frame record.
    Used internally by FrameStorageService.
    """
    event_id: str = Field(..., description="UUID of the parent event")
    frame_number: int = Field(..., ge=1, description="1-indexed frame number")
    frame_path: str = Field(..., description="Relative path to the frame file")
    timestamp_offset_ms: int = Field(..., ge=0, description="Milliseconds from video start")
    width: Optional[int] = Field(None, ge=1, description="Frame width in pixels")
    height: Optional[int] = Field(None, ge=1, description="Frame height in pixels")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="Frame file size in bytes")
