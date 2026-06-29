"""
Mobile Authentication Schemas (Story P12-3.1)

Pydantic schemas for mobile device pairing and token management.
"""
from datetime import datetime
from app.schemas.types import UTCDateTime
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ============================================================================
# Pairing Schemas
# ============================================================================

class PairingRequest(BaseModel):
    """Request to generate a new pairing code."""
    device_id: str = Field(..., min_length=1, max_length=255, description="Hardware device identifier")
    platform: Literal['ios', 'android'] = Field(..., description="Mobile platform")
    device_name: Optional[str] = Field(None, max_length=100, description="User-friendly device name")
    device_model: Optional[str] = Field(None, max_length=100, description="Device hardware model")


class PairingCodeResponse(BaseModel):
    """Response containing the generated pairing code."""
    code: str = Field(..., description="6-digit pairing code to display")
    expires_in: int = Field(..., description="Seconds until code expires")
    expires_at: UTCDateTime = Field(..., description="Absolute expiration time")


class PairingConfirmRequest(BaseModel):
    """Request to confirm a pairing code from web dashboard."""
    code: str = Field(..., min_length=6, max_length=6, description="6-digit code entered by user")


class PairingConfirmResponse(BaseModel):
    """Response after confirming a pairing code."""
    confirmed: bool = Field(..., description="Whether confirmation was successful")
    device_name: Optional[str] = Field(None, description="Device name if available")
    device_model: Optional[str] = Field(None, description="Device model if available")
    platform: str = Field(..., description="Device platform (ios/android)")


class PairingStatusRequest(BaseModel):
    """Request to check pairing status (polled by mobile app)."""
    code: str = Field(..., min_length=6, max_length=6, description="6-digit code to check")


class PairingStatusResponse(BaseModel):
    """Response with current pairing status."""
    confirmed: bool = Field(..., description="Whether code has been confirmed")
    expired: bool = Field(..., description="Whether code has expired")


# ============================================================================
# Token Schemas
# ============================================================================

class TokenExchangeRequest(BaseModel):
    """Request to exchange confirmed pairing code for tokens."""
    code: str = Field(..., min_length=6, max_length=6, description="Confirmed pairing code")


class TokenPair(BaseModel):
    """JWT access and refresh token pair."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Refresh token for obtaining new access tokens")
    token_type: str = Field("bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(..., description="Access token TTL in seconds")
    device_id: str = Field(..., description="Associated device UUID")


class TokenRefreshRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str = Field(..., description="Current refresh token")
    device_id: str = Field(..., description="Device UUID for validation")


class TokenRevokeRequest(BaseModel):
    """Request to revoke a refresh token."""
    refresh_token: Optional[str] = Field(None, description="Specific token to revoke")
    device_id: Optional[str] = Field(None, description="Revoke all tokens for device")
    revoke_all: bool = Field(False, description="Revoke all user's mobile tokens")


class TokenRevokeResponse(BaseModel):
    """Response after revoking tokens."""
    revoked_count: int = Field(..., description="Number of tokens revoked")


# ============================================================================
# Device Token Info Schemas
# ============================================================================

class DeviceTokenInfo(BaseModel):
    """Information about tokens for a device."""
    device_id: str = Field(..., description="Device UUID")
    device_name: Optional[str] = Field(None, description="Device name")
    platform: str = Field(..., description="Device platform")
    has_valid_token: bool = Field(..., description="Whether device has valid refresh token")
    token_expires_at: Optional[UTCDateTime] = Field(None, description="Token expiration time")
    last_used_at: Optional[UTCDateTime] = Field(None, description="Last token use time")


class PendingPairingInfo(BaseModel):
    """Information about a pending pairing request."""
    code: str = Field(..., description="Pairing code")
    device_name: Optional[str] = Field(None, description="Requesting device name")
    device_model: Optional[str] = Field(None, description="Requesting device model")
    platform: str = Field(..., description="Requesting device platform")
    expires_at: UTCDateTime = Field(..., description="Code expiration time")
    created_at: UTCDateTime = Field(..., description="Request creation time")


class PendingPairingsResponse(BaseModel):
    """Response listing pending pairing requests."""
    pairings: list[PendingPairingInfo] = Field(..., description="Pending pairing codes")
    total: int = Field(..., description="Total count")
