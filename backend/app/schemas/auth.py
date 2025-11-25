"""Authentication Pydantic schemas for request/response validation"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class LoginRequest(BaseModel):
    """Login request body"""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class LoginResponse(BaseModel):
    """Login response with user info"""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user: "UserResponse" = Field(..., description="User information")


class UserResponse(BaseModel):
    """User information response"""
    id: str = Field(..., description="User UUID")
    username: str = Field(..., description="Username")
    is_active: bool = Field(..., description="Account active status")
    created_at: datetime = Field(..., description="Account creation timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")

    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    """Change password request body"""
    current_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=8, description="New password (8+ chars, uppercase, number, special)")


class MessageResponse(BaseModel):
    """Simple message response"""
    message: str = Field(..., description="Response message")


# Forward reference resolution
LoginResponse.model_rebuild()
