"""Authentication API endpoints (Story 6.3, P15-2)"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import datetime, timezone
from typing import List
import secrets
import logging

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User, UserRole
from app.models.session import Session as SessionModel
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    ChangePasswordRequest,
    MessageResponse,
    SessionResponse,
    SessionRevokeResponse,
)
from app.utils.auth import hash_password, verify_password, validate_password_strength
from app.utils.jwt import create_access_token, decode_access_token, TokenError
from app.services.session_service import SessionService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Rate limiter (5 attempts per 15 minutes)
limiter = Limiter(key_func=get_remote_address)

# Cookie settings
COOKIE_NAME = "access_token"
COOKIE_MAX_AGE = settings.JWT_EXPIRATION_HOURS * 60 * 60  # 24 hours in seconds


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Dependency to get current authenticated user from JWT token

    Checks both cookie and Authorization header for JWT token.

    Raises:
        HTTPException: 401 if not authenticated
    """
    token = None

    # Check cookie first
    token = request.cookies.get(COOKIE_NAME)

    # Fallback to Authorization header
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account disabled",
        )

    return user


def ensure_admin_exists(db: Session) -> tuple[bool, str]:
    """
    Ensure default admin user exists on first startup

    Creates admin user with random password if no users exist.

    Returns:
        Tuple of (created, password) - password only returned if newly created
    """
    user_service = UserService(db)
    return user_service.ensure_admin_exists()


def get_current_token(request: Request) -> str | None:
    """Extract current JWT token from request"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate user",
    description="Login with username and password. Returns JWT token in response body and sets HTTP-only cookie. Rate limited to 5 attempts per 15 minutes per IP.",
    response_description="JWT access token and user information",
    responses={
        401: {"description": "Invalid credentials or account disabled"},
        429: {"description": "Rate limit exceeded - try again later"},
    },
)
@limiter.limit("5/15minutes")
async def login(
    request: Request,
    response: Response,
    credentials: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Login with username and password (Story P15-2.6)

    Returns JWT token in response body and sets HTTP-only cookie.
    Rate limited to 5 attempts per 15 minutes per IP.

    If must_change_password is true, user should be redirected to
    password change screen before accessing other pages.
    """
    # Find user
    user = db.query(User).filter(User.username == credentials.username.lower()).first()

    if not user:
        logger.warning(
            "Login failed - user not found",
            extra={
                "event_type": "login_failed",
                "reason": "user_not_found",
                "username": credentials.username,
                "ip_address": get_remote_address(request),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        logger.warning(
            "Login failed - invalid password",
            extra={
                "event_type": "login_failed",
                "reason": "invalid_password",
                "username": credentials.username,
                "ip_address": get_remote_address(request),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check if user is active
    if not user.is_active:
        logger.warning(
            "Login failed - account disabled",
            extra={
                "event_type": "login_failed",
                "reason": "account_disabled",
                "username": credentials.username,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account disabled",
        )

    # Check if temporary password has expired (Story P15-2.5)
    if user.password_is_expired():
        logger.warning(
            "Login failed - temporary password expired",
            extra={
                "event_type": "login_failed",
                "reason": "password_expired",
                "username": credentials.username,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Temporary password has expired. Please contact an administrator.",
        )

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # Create JWT token
    access_token = create_access_token(user.id, user.username)

    # Create server-side session (Story P15-2.7)
    session_service = SessionService(db)
    session_service.create_session(user, access_token, request)

    # Set HTTP-only cookie
    # Cookie settings configurable via COOKIE_SECURE and COOKIE_SAMESITE env vars
    # For HTTPS: COOKIE_SECURE=true, COOKIE_SAMESITE=none
    # For HTTP:  COOKIE_SECURE=false, COOKIE_SAMESITE=lax
    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )

    logger.info(
        "Login successful",
        extra={
            "event_type": "login_success",
            "user_id": user.id,
            "username": user.username,
            "ip_address": get_remote_address(request),
            "must_change_password": user.must_change_password,
        }
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role.value if hasattr(user.role, 'value') else str(user.role),
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            last_login=user.last_login,
        ),
        must_change_password=user.must_change_password,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="End user session",
    description="Logout by clearing the JWT cookie and invalidating server-side session.",
    response_description="Logout confirmation message",
)
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Logout by clearing JWT cookie and invalidating server-side session (Story P15-2.7)
    """
    # Invalidate server-side session
    token = get_current_token(request)
    if token:
        session_service = SessionService(db)
        session = session_service.get_session_by_token(token)
        if session:
            session_service.revoke_session(session.id, session.user_id)

    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )

    logger.info(
        "Logout successful",
        extra={"event_type": "logout"}
    )

    return MessageResponse(message="Logged out successfully")


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change user password",
    description="Change password for current authenticated user. For regular changes, requires current password verification. For forced password changes (must_change_password=true), current password is optional. New password must be at least 8 characters with 1 uppercase, 1 lowercase, 1 number, and 1 special character.",
    response_description="Password change confirmation",
    responses={
        400: {"description": "New password doesn't meet requirements or current password is incorrect"},
        401: {"description": "Not authenticated"},
    },
)
async def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change password for current user (Story P15-2.6)

    For forced password changes (must_change_password=true):
    - Current password verification is optional (can skip)

    For regular password changes:
    - Requires current password verification

    New password must meet security requirements:
    - At least 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 number
    - At least 1 special character
    """
    # Re-fetch user with this session to ensure proper tracking
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # For forced password changes, current password verification is optional
    # For regular changes, require current password
    if not user.must_change_password:
        # Regular change - require current password
        if not password_data.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required",
            )

        if not verify_password(password_data.current_password, user.password_hash):
            logger.warning(
                "Password change failed - incorrect current password",
                extra={
                    "event_type": "password_change_failed",
                    "reason": "incorrect_password",
                    "user_id": user.id,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

    # Validate new password strength
    is_valid, error_message = validate_password_strength(password_data.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    # Update password using UserService
    # Story P16-1.6: Pass request info for audit logging
    user_service = UserService(db)
    user_service.change_password(
        user=user,
        new_password=password_data.new_password,
        clear_must_change=True,  # Always clear the flag after successful change
        ip_address=get_remote_address(request),
        user_agent=request.headers.get("User-Agent", ""),
    )

    logger.info(
        "Password changed successfully",
        extra={
            "event_type": "password_changed",
            "user_id": user.id,
            "was_forced": current_user.must_change_password,
        }
    )

    return MessageResponse(message="Password changed successfully")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Returns information about the currently authenticated user based on the JWT token.",
    response_description="Current user profile information",
    responses={
        401: {"description": "Not authenticated or token expired"},
    },
)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """
    Get current authenticated user information
    """
    return UserResponse.model_validate(current_user)


@router.get("/setup-status")
async def get_setup_status(db: Session = Depends(get_db)):
    """
    Check if initial setup is complete (admin user exists)

    Used by frontend to determine if first-time setup is needed.
    """
    user_count = db.query(User).count()
    return {
        "setup_complete": user_count > 0,
        "user_count": user_count,
    }


# Session Management Endpoints (Story P15-2.7)

@router.get(
    "/sessions",
    response_model=List[SessionResponse],
    summary="List active sessions",
    description="Get list of all active sessions for the current user. Current session is marked with is_current=true.",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all active sessions for current user (Story P15-2.7)

    Returns sessions with device info, IP address, and timestamps.
    Current session is marked with is_current=true.
    """
    session_service = SessionService(db)
    token = get_current_token(request)
    sessions = session_service.get_user_sessions(current_user.id, token)

    return [SessionResponse(**session) for session in sessions]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke specific session",
    description="Revoke a specific session by ID. Cannot revoke the current session.",
    responses={
        400: {"description": "Cannot revoke current session"},
        401: {"description": "Not authenticated"},
        404: {"description": "Session not found"},
    },
)
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Revoke a specific session (Story P15-2.7)

    Cannot revoke the current session - use logout instead.
    """
    session_service = SessionService(db)

    # Check if trying to revoke current session
    token = get_current_token(request)
    if token:
        current_session = session_service.get_session_by_token(token)
        if current_session and current_session.id == session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot revoke current session. Use logout instead.",
            )

    if not session_service.revoke_session(session_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return None


@router.delete(
    "/sessions",
    response_model=SessionRevokeResponse,
    summary="Revoke all other sessions",
    description="Revoke all sessions except the current one.",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def revoke_all_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Revoke all sessions except current (Story P15-2.7)
    """
    session_service = SessionService(db)

    # Get current session ID to exclude
    token = get_current_token(request)
    current_session_id = None
    if token:
        current_session = session_service.get_session_by_token(token)
        if current_session:
            current_session_id = current_session.id

    count = session_service.revoke_all_sessions(
        current_user.id,
        except_session_id=current_session_id
    )

    return SessionRevokeResponse(revoked_count=count)
