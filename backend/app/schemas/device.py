"""Device Pydantic schemas for request/response validation (Story P11-2.4, P11-2.5)"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum
import re


class DevicePlatform(str, Enum):
    """Supported device platforms."""
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


# Time format regex for HH:MM validation
TIME_FORMAT_REGEX = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')


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
    # Optional quiet hours configuration on initial registration (Story P11-2.5)
    quiet_hours_enabled: Optional[bool] = Field(
        None,
        description="Enable quiet hours for this device"
    )
    quiet_hours_start: Optional[str] = Field(
        None,
        description="Start time in HH:MM format (e.g., '22:00')"
    )
    quiet_hours_end: Optional[str] = Field(
        None,
        description="End time in HH:MM format (e.g., '07:00')"
    )
    quiet_hours_timezone: Optional[str] = Field(
        None,
        description="IANA timezone (e.g., 'America/New_York')"
    )
    quiet_hours_override_critical: Optional[bool] = Field(
        None,
        description="Allow critical alerts during quiet hours"
    )

    @field_validator('device_id')
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        """Validate device_id is not empty and reasonable format."""
        v = v.strip()
        if not v:
            raise ValueError("device_id cannot be empty")
        return v

    @field_validator('quiet_hours_start', 'quiet_hours_end')
    @classmethod
    def validate_time_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate time is in HH:MM format."""
        if v is None:
            return v
        if not TIME_FORMAT_REGEX.match(v):
            raise ValueError("Time must be in HH:MM format (e.g., '22:00')")
        return v

    @field_validator('quiet_hours_timezone')
    @classmethod
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        """Validate timezone is a valid IANA timezone."""
        if v is None:
            return v
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(v)
            return v
        except Exception:
            raise ValueError(f"Invalid timezone: {v}")


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
    # Quiet hours fields (Story P11-2.5)
    quiet_hours_enabled: bool = Field(False, description="Quiet hours enabled")
    quiet_hours_start: Optional[str] = Field(None, description="Quiet hours start (HH:MM)")
    quiet_hours_end: Optional[str] = Field(None, description="Quiet hours end (HH:MM)")
    quiet_hours_timezone: str = Field("UTC", description="Timezone for quiet hours")
    quiet_hours_override_critical: bool = Field(True, description="Allow critical alerts during quiet hours")

    class Config:
        from_attributes = True


class DevicePreferencesUpdate(BaseModel):
    """Schema for updating device preferences (quiet hours) - Story P11-2.5."""
    quiet_hours_enabled: Optional[bool] = Field(
        None,
        description="Enable or disable quiet hours"
    )
    quiet_hours_start: Optional[str] = Field(
        None,
        description="Start time in HH:MM format (e.g., '22:00')"
    )
    quiet_hours_end: Optional[str] = Field(
        None,
        description="End time in HH:MM format (e.g., '07:00')"
    )
    quiet_hours_timezone: Optional[str] = Field(
        None,
        description="IANA timezone (e.g., 'America/New_York')"
    )
    quiet_hours_override_critical: Optional[bool] = Field(
        None,
        description="Allow critical alerts during quiet hours"
    )

    @field_validator('quiet_hours_start', 'quiet_hours_end')
    @classmethod
    def validate_time_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate time is in HH:MM format."""
        if v is None:
            return v
        if not TIME_FORMAT_REGEX.match(v):
            raise ValueError("Time must be in HH:MM format (e.g., '22:00')")
        return v

    @field_validator('quiet_hours_timezone')
    @classmethod
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        """Validate timezone is a valid IANA timezone."""
        if v is None:
            return v
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(v)
            return v
        except Exception:
            raise ValueError(f"Invalid timezone: {v}")


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
