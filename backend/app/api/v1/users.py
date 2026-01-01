"""User management API endpoints (Story P15-2.3, P16-1.2)

Admin-only endpoints for managing user accounts.

Permission Matrix:
- All endpoints require admin role
- Regular users can only manage their own profile via /auth endpoints

Story P16-1.2: Added invited_by/invited_at tracking for user creation.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging

from app.core.database import get_db
from app.core.permissions import require_role
from app.models.user import User, UserRole
from app.schemas.auth import (
    UserResponse,
    UserCreate,
    UserCreateResponse,
    UserUpdate,
    PasswordResetResponse,
)
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["User Management"])


@router.post(
    "",
    response_model=UserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new user",
    description="Create a new user account with temporary password. Admin only. "
                "Returns temporary password that must be changed on first login.",
    responses={
        400: {"description": "Username or email already exists"},
        403: {"description": "Not authorized - admin role required"},
    },
)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Create a new user account (Admin only)

    - Generates secure temporary password
    - Sets must_change_password flag
    - Password expires in 72 hours if not changed
    """
    service = UserService(db)

    try:
        # Story P16-1.2: Track who created this user
        user, temp_password = service.create_user(
            username=user_data.username,
            role=user_data.role,
            email=user_data.email,
            send_email=user_data.send_email,
            invited_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return UserCreateResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.value if hasattr(user.role, 'value') else str(user.role),
        temporary_password=temp_password if not user_data.send_email else None,
        password_expires_at=user.password_expires_at,
        created_at=user.created_at,
        invited_by=user.invited_by,
        invited_at=user.invited_at,
    )


@router.get(
    "",
    response_model=List[UserResponse],
    summary="List all users",
    description="Get list of all user accounts. Admin only.",
    responses={
        403: {"description": "Not authorized - admin role required"},
    },
)
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """List all users (Admin only)"""
    service = UserService(db)
    users = service.list_users()

    return [
        UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role.value if hasattr(user.role, 'value') else str(user.role),
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            last_login=user.last_login,
            invited_by=user.invited_by,
            invited_at=user.invited_at,
        )
        for user in users
    ]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user details",
    description="Get details for a specific user. Admin only.",
    responses={
        403: {"description": "Not authorized - admin role required"},
        404: {"description": "User not found"},
    },
)
async def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Get user by ID (Admin only)"""
    service = UserService(db)
    user = service.get_user(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.value if hasattr(user.role, 'value') else str(user.role),
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        last_login=user.last_login,
        invited_by=user.invited_by,
        invited_at=user.invited_at,
    )


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user",
    description="Update user details. Admin only. Cannot update username.",
    responses={
        400: {"description": "Invalid data or email already exists"},
        403: {"description": "Not authorized - admin role required"},
        404: {"description": "User not found"},
    },
)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Update user details (Admin only)"""
    service = UserService(db)

    try:
        user = service.update_user(
            user_id=user_id,
            email=user_data.email,
            role=user_data.role,
            is_active=user_data.is_active,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.value if hasattr(user.role, 'value') else str(user.role),
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        last_login=user.last_login,
        invited_by=user.invited_by,
        invited_at=user.invited_at,
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete a user account. Admin only. Cannot delete yourself.",
    responses={
        400: {"description": "Cannot delete yourself"},
        403: {"description": "Not authorized - admin role required"},
        404: {"description": "User not found"},
    },
)
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Delete user (Admin only)"""
    # Prevent self-deletion
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    service = UserService(db)
    if not service.delete_user(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return None


@router.post(
    "/{user_id}/reset",
    response_model=PasswordResetResponse,
    summary="Reset user password",
    description="Reset user password to a new temporary password. Admin only. "
                "Invalidates all existing sessions.",
    responses={
        403: {"description": "Not authorized - admin role required"},
        404: {"description": "User not found"},
    },
)
async def reset_password(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Reset user password (Admin only)"""
    service = UserService(db)
    temp_password, expires_at = service.reset_password(user_id)

    if not temp_password:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return PasswordResetResponse(
        temporary_password=temp_password,
        expires_at=expires_at,
    )
