"""User management service (Story P15-2.3, P15-2.5, P16-1.2)

Provides user CRUD operations, invitation flow, and password reset functionality.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.exc import IntegrityError
import secrets
import logging

from app.models.user import User, UserRole
from app.utils.auth import hash_password

logger = logging.getLogger(__name__)

# Temporary password expires after 72 hours
TEMP_PASSWORD_EXPIRY_HOURS = 72

# Password length for generated passwords
GENERATED_PASSWORD_LENGTH = 16


class UserService:
    """
    Service for managing users (Story P15-2.3, P15-2.5)

    Responsibilities:
    - Create users with temporary passwords (invitation flow)
    - Update user details (admin operations)
    - Reset passwords
    - Enable/disable accounts
    - Delete users
    """

    def __init__(self, db: DBSession):
        self.db = db

    def create_user(
        self,
        username: str,
        role: str = "viewer",
        email: Optional[str] = None,
        send_email: bool = False,
        invited_by: Optional[str] = None,
    ) -> Tuple[User, str]:
        """
        Create a new user with temporary password.

        Args:
            username: Unique username
            role: User role (admin, operator, viewer)
            email: Optional email address
            send_email: Whether to send invitation email (future feature)
            invited_by: User ID of the admin who created this user (Story P16-1.2)

        Returns:
            Tuple of (User, temporary_password)

        Raises:
            ValueError: If username already exists
        """
        # Generate secure random password
        temp_password = self._generate_password()
        password_hash = hash_password(temp_password)

        # Calculate password expiry (72 hours)
        password_expires_at = datetime.now(timezone.utc) + timedelta(hours=TEMP_PASSWORD_EXPIRY_HOURS)

        # Create user with must_change_password flag
        # Story P16-1.2: Track who created this user and when
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role=UserRole(role),
            is_active=True,
            must_change_password=True,
            password_expires_at=password_expires_at,
            invited_by=invited_by,
            invited_at=datetime.now(timezone.utc) if invited_by else None,
        )

        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        except IntegrityError as e:
            self.db.rollback()
            if "username" in str(e).lower():
                raise ValueError(f"Username '{username}' already exists")
            if "email" in str(e).lower():
                raise ValueError(f"Email '{email}' already exists")
            raise ValueError("Failed to create user")

        logger.info(
            "User created",
            extra={
                "event_type": "user_created",
                "user_id": user.id,
                "username": username,
                "role": role,
                "has_email": email is not None,
            }
        )

        # TODO: If send_email and email is configured, send invitation email
        # For now, we just return the password for display

        return user, temp_password

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.db.query(User).filter(User.username == username.lower()).first()

    def list_users(self) -> List[User]:
        """List all users"""
        return self.db.query(User).order_by(User.created_at.desc()).all()

    def update_user(
        self,
        user_id: str,
        email: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Optional[User]:
        """
        Update user details.

        Args:
            user_id: User ID to update
            email: New email address
            role: New role (admin, operator, viewer)
            is_active: New active status

        Returns:
            Updated User or None if not found
        """
        user = self.get_user(user_id)
        if not user:
            return None

        if email is not None:
            user.email = email

        if role is not None:
            user.role = UserRole(role)

        if is_active is not None:
            user.is_active = is_active
            # If disabling user, invalidate all their sessions
            if not is_active:
                self._invalidate_user_sessions(user_id)

        try:
            self.db.commit()
            self.db.refresh(user)
        except IntegrityError:
            self.db.rollback()
            raise ValueError("Email already exists")

        logger.info(
            "User updated",
            extra={
                "event_type": "user_updated",
                "user_id": user_id,
                "changes": {
                    "email": email is not None,
                    "role": role,
                    "is_active": is_active,
                }
            }
        )

        return user

    def delete_user(self, user_id: str) -> bool:
        """
        Delete a user.

        Cascade deletes all associated sessions and devices.

        Args:
            user_id: User ID to delete

        Returns:
            True if deleted, False if not found
        """
        user = self.get_user(user_id)
        if not user:
            return False

        username = user.username
        self.db.delete(user)
        self.db.commit()

        logger.info(
            "User deleted",
            extra={
                "event_type": "user_deleted",
                "user_id": user_id,
                "username": username,
            }
        )

        return True

    def reset_password(self, user_id: str) -> Tuple[Optional[str], Optional[datetime]]:
        """
        Reset user password to a temporary password.

        Args:
            user_id: User ID

        Returns:
            Tuple of (temp_password, expires_at) or (None, None) if user not found
        """
        user = self.get_user(user_id)
        if not user:
            return None, None

        # Generate new temporary password
        temp_password = self._generate_password()
        password_hash = hash_password(temp_password)

        # Set expiry (72 hours)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=TEMP_PASSWORD_EXPIRY_HOURS)

        # Update user
        user.password_hash = password_hash
        user.must_change_password = True
        user.password_expires_at = expires_at

        # Invalidate all existing sessions
        self._invalidate_user_sessions(user_id)

        self.db.commit()
        self.db.refresh(user)

        logger.info(
            "Password reset",
            extra={
                "event_type": "password_reset",
                "user_id": user_id,
                "username": user.username,
            }
        )

        return temp_password, expires_at

    def change_password(
        self,
        user: User,
        new_password: str,
        clear_must_change: bool = True
    ) -> None:
        """
        Change user's password.

        Args:
            user: User object
            new_password: New password (already validated)
            clear_must_change: Whether to clear must_change_password flag
        """
        user.password_hash = hash_password(new_password)

        if clear_must_change:
            user.must_change_password = False
            user.password_expires_at = None

        self.db.commit()
        self.db.refresh(user)

        logger.info(
            "Password changed",
            extra={
                "event_type": "password_changed",
                "user_id": user.id,
                "username": user.username,
            }
        )

    def _generate_password(self) -> str:
        """Generate a secure random password"""
        return secrets.token_urlsafe(GENERATED_PASSWORD_LENGTH)

    def _invalidate_user_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a user"""
        from app.models.session import Session

        sessions = self.db.query(Session).filter(Session.user_id == user_id).all()
        count = len(sessions)

        for session in sessions:
            self.db.delete(session)

        return count

    def ensure_admin_exists(self) -> Tuple[bool, str]:
        """
        Ensure at least one admin user exists.

        Creates default admin if no users exist.

        Returns:
            Tuple of (created, password) - password only if newly created
        """
        existing_users = self.db.query(User).count()
        if existing_users > 0:
            return False, ""

        # Create default admin
        user, password = self.create_user(
            username="admin",
            role="admin",
            email=None,
            send_email=False
        )

        # Admin doesn't need to change password on first login
        user.must_change_password = False
        user.password_expires_at = None
        self.db.commit()

        logger.info(
            "Default admin created",
            extra={
                "event_type": "default_admin_created",
                "user_id": user.id,
            }
        )

        return True, password
