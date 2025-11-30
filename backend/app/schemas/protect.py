"""Pydantic schemas for UniFi Protect controller API endpoints"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
import uuid


class ProtectControllerBase(BaseModel):
    """Base schema with common fields"""

    name: str = Field(..., min_length=1, max_length=100, description="User-friendly controller name")
    host: str = Field(..., min_length=1, max_length=255, description="IP address or hostname")
    port: int = Field(default=443, ge=1, le=65535, description="HTTPS port")
    verify_ssl: bool = Field(default=False, description="Whether to verify SSL certificates")


class ProtectControllerCreate(ProtectControllerBase):
    """Schema for creating a new Protect controller"""

    username: str = Field(..., min_length=1, max_length=100, description="Protect authentication username")
    password: str = Field(..., min_length=1, max_length=100, description="Protect password (will be encrypted)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Home UDM Pro",
                    "host": "192.168.1.1",
                    "port": 443,
                    "username": "admin",
                    "password": "secretpassword",
                    "verify_ssl": False
                }
            ]
        }
    }


class ProtectControllerUpdate(BaseModel):
    """Schema for updating an existing controller (all fields optional)"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=1, max_length=100)
    verify_ssl: Optional[bool] = None


class ProtectControllerResponse(ProtectControllerBase):
    """Schema for controller API responses"""

    id: str = Field(..., description="Controller UUID")
    username: str = Field(..., description="Protect authentication username")
    is_connected: bool = Field(..., description="Current connection status")
    last_connected_at: Optional[datetime] = Field(None, description="Last successful connection timestamp")
    last_error: Optional[str] = Field(None, description="Last connection error message")
    created_at: datetime
    updated_at: datetime

    # Note: password field is intentionally omitted (write-only field)

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Home UDM Pro",
                    "host": "192.168.1.1",
                    "port": 443,
                    "username": "admin",
                    "verify_ssl": False,
                    "is_connected": True,
                    "last_connected_at": "2025-11-30T10:30:00Z",
                    "last_error": None,
                    "created_at": "2025-11-30T10:00:00Z",
                    "updated_at": "2025-11-30T10:30:00Z"
                }
            ]
        }
    }


class MetaResponse(BaseModel):
    """Standard meta response object"""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique request identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Response timestamp")
    count: Optional[int] = Field(None, description="Number of items (for list responses)")


class ProtectControllerSingleResponse(BaseModel):
    """Single controller response with meta"""

    data: ProtectControllerResponse
    meta: MetaResponse


class ProtectControllerListResponse(BaseModel):
    """List of controllers response with meta"""

    data: List[ProtectControllerResponse]
    meta: MetaResponse


class ProtectControllerDeleteResponse(BaseModel):
    """Delete operation response"""

    data: dict = Field(default={"deleted": True})
    meta: MetaResponse
