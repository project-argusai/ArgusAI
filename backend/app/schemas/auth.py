"""Authentication Pydantic schemas for request/response validation (Story P15-2)"""
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import Optional, Literal


class LoginRequest(BaseModel):
    """Login request body"""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class LoginResponse(BaseModel):
    """Login response with user info"""
    access_token: str = Field(..., description="JWT access token (short-lived)")
    refresh_token: Optional[str] = Field(None, description="Opaque refresh token (long-lived, use for /auth/refresh)")
    token_type: str = Field(default="bearer", description="Token type")
    user: "UserResponse" = Field(..., description="User information")
    must_change_password: bool = Field(default=False, description="Requires password change")


class RefreshRequest(BaseModel):
    """Request body for refreshing access token"""
    refresh_token: str = Field(..., description="Valid refresh token from previous login or refresh")


class RefreshResponse(BaseModel):
    """Response after successful token refresh"""
    access_token: str = Field(..., description="New short-lived JWT access token")
    refresh_token: str = Field(..., description="New rotated refresh token")
    token_type: str = Field(default="bearer", description="Token type")


class UserResponse(BaseModel):
    """User information response (Story P15-2.1, P16-1.1)"""
    id: str = Field(..., description="User UUID")
    username: str = Field(..., description="Username")
    email: Optional[str] = Field(None, description="Email address")
    role: str = Field(..., description="User role (admin, operator, viewer)")
    is_active: bool = Field(..., description="Account active status")
    must_change_password: bool = Field(default=False, description="Force password change on next login")
    created_at: datetime = Field(..., description="Account creation timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    # Story P16-1.1: Invitation tracking fields
    invited_by: Optional[str] = Field(None, description="User ID who created this account")
    invited_at: Optional[datetime] = Field(None, description="Timestamp when user was invited")

    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    """Change password request body"""
    current_password: Optional[str] = Field(None, min_length=1, description="Current password (optional for forced change)")
    new_password: str = Field(..., min_length=8, description="New password (8+ chars, uppercase, number, special)")


class MessageResponse(BaseModel):
    """Simple message response"""
    message: str = Field(..., description="Response message")


# User Management Schemas (Story P15-2.3)
class UserCreate(BaseModel):
    """Create user request (admin only)"""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: Optional[EmailStr] = Field(None, description="Email address for notifications")
    role: Literal["admin", "operator", "viewer"] = Field(default="viewer", description="User role")
    send_email: bool = Field(default=False, description="Send invitation email")


class UserCreateResponse(BaseModel):
    """Create user response with temporary password (Story P15-2.3, P16-1.1, P16-1.7)"""
    id: str = Field(..., description="User UUID")
    username: str = Field(..., description="Username")
    email: Optional[str] = Field(None, description="Email address")
    role: str = Field(..., description="User role")
    temporary_password: Optional[str] = Field(None, description="Temporary password (if not sent via email)")
    password_expires_at: Optional[datetime] = Field(None, description="Temporary password expiration")
    created_at: datetime = Field(..., description="Account creation timestamp")
    # Story P16-1.1: Invitation tracking fields
    invited_by: Optional[str] = Field(None, description="User ID who created this account")
    invited_at: Optional[datetime] = Field(None, description="Timestamp when user was invited")
    # Story P16-1.7: Email sent indicator
    email_sent: bool = Field(default=False, description="Whether invitation email was sent")

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Update user request (admin only)"""
    email: Optional[EmailStr] = Field(None, description="Email address")
    role: Optional[Literal["admin", "operator", "viewer"]] = Field(None, description="User role")
    is_active: Optional[bool] = Field(None, description="Account active status")


class PasswordResetResponse(BaseModel):
    """Password reset response"""
    temporary_password: str = Field(..., description="New temporary password")
    expires_at: datetime = Field(..., description="Temporary password expiration")


# Session Management Schemas (Story P15-2.7)
class SessionResponse(BaseModel):
    """Session information response"""
    id: str = Field(..., description="Session UUID")
    device_info: Optional[str] = Field(None, description="Device description")
    ip_address: Optional[str] = Field(None, description="Client IP address")
    created_at: datetime = Field(..., description="Session creation timestamp")
    last_active_at: datetime = Field(..., description="Last activity timestamp")
    is_current: bool = Field(default=False, description="Is this the current session")

    class Config:
        from_attributes = True


class SessionRevokeResponse(BaseModel):
    """Response when revoking multiple sessions"""
    revoked_count: int = Field(..., description="Number of sessions revoked")


# Forward reference resolution
LoginResponse.model_rebuild()
