"""Device Pydantic schemas for request/response validation (Story P11-2.4)"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum


class DevicePlatform(str, Enum):
    """Supported device platforms."""
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class DeviceCreate(BaseModel):
    """Schema for device registration request."""
    device_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Unique device identifier from mobile app"
    )
    platform: DevicePlatform = Field(
        ...,
        description="Device platform (ios, android, web)"
    )
    name: Optional[str] = Field(
        None,
        max_length=100,
        description="User-friendly device name (e.g., 'iPhone 15 Pro')"
    )
    push_token: Optional[str] = Field(
        None,
        description="Push notification token from APNS/FCM"
    )

    @field_validator('device_id')
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        """Validate device_id is not empty and reasonable format."""
        v = v.strip()
        if not v:
            raise ValueError("device_id cannot be empty")
        return v


class DeviceTokenUpdate(BaseModel):
    """Schema for updating device push token."""
    push_token: str = Field(
        ...,
        min_length=1,
        description="New push notification token"
    )


class DeviceResponse(BaseModel):
    """Schema for device response (excludes push_token for security)."""
    id: str = Field(..., description="Device UUID")
    user_id: str = Field(..., description="Owner user UUID")
    device_id: str = Field(..., description="Device identifier")
    platform: str = Field(..., description="Device platform")
    name: Optional[str] = Field(None, description="Device name")
    last_seen_at: Optional[datetime] = Field(None, description="Last activity timestamp")
    created_at: datetime = Field(..., description="Registration timestamp")

    class Config:
        from_attributes = True


class DeviceListResponse(BaseModel):
    """Schema for listing user's devices."""
    devices: List[DeviceResponse] = Field(
        default_factory=list,
        description="List of user's registered devices"
    )
    total: int = Field(
        ...,
        description="Total number of devices"
    )


class DeviceRegistrationResponse(BaseModel):
    """Schema for device registration response."""
    id: str = Field(..., description="Device UUID")
    device_id: str = Field(..., description="Device identifier")
    platform: str = Field(..., description="Device platform")
    created_at: datetime = Field(..., description="Registration timestamp")
    is_new: bool = Field(..., description="True if new device, False if updated existing")

    class Config:
        from_attributes = True
