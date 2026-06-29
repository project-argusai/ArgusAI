"""
Pydantic schemas for API Key management.

Story P13-1.2: Implement API Key Generation Endpoint
Story P13-1.3: Implement API Key List and Revoke Endpoints
"""
from pydantic import BaseModel, Field
from datetime import datetime
from app.schemas.types import UTCDateTime
from typing import Optional


# Valid scopes for API keys
VALID_SCOPES = {"read:events", "read:cameras", "write:cameras", "admin"}


class APIKeyCreateRequest(BaseModel):
    """Request to create a new API key."""
    name: str = Field(..., min_length=1, max_length=255, description="Descriptive name for the key")
    scopes: list[str] = Field(
        default=["read:events"],
        description="Permission scopes: read:events, read:cameras, write:cameras, admin"
    )
    expires_at: Optional[UTCDateTime] = Field(
        None,
        description="Optional expiration date for the key"
    )
    rate_limit_per_minute: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum requests per minute (1-10000)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Home Assistant Integration",
                "scopes": ["read:events", "read:cameras"],
                "expires_at": None,
                "rate_limit_per_minute": 100
            }
        }


class APIKeyCreateResponse(BaseModel):
    """Response after creating a new API key.

    IMPORTANT: The 'key' field contains the full API key and is ONLY
    returned in this response. It is never stored and cannot be retrieved again.
    """
    id: str
    name: str
    key: str = Field(..., description="Full API key - ONLY shown once, save it now!")
    prefix: str = Field(..., description="Key prefix for identification")
    scopes: list[str]
    expires_at: Optional[UTCDateTime]
    rate_limit_per_minute: int
    created_at: UTCDateTime

    class Config:
        from_attributes = True


class APIKeyListResponse(BaseModel):
    """API key summary for list views (no full key exposed)."""
    id: str
    name: str
    prefix: str = Field(..., description="Partial key for identification (argus_xxxxxxxx...)")
    scopes: list[str]
    is_active: bool
    expires_at: Optional[UTCDateTime]
    last_used_at: Optional[UTCDateTime]
    usage_count: int
    rate_limit_per_minute: int
    created_at: UTCDateTime
    revoked_at: Optional[UTCDateTime]

    class Config:
        from_attributes = True


class APIKeyUsageResponse(BaseModel):
    """API key usage statistics."""
    id: str
    name: str
    prefix: str
    usage_count: int
    last_used_at: Optional[UTCDateTime]
    last_used_ip: Optional[str]
    rate_limit_per_minute: int
    created_at: UTCDateTime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str
