"""User management service (Story P15-2.3, P15-2.5, P16-1.2, P16-1.6)

Provides user CRUD operations, invitation flow, and password reset functionality.
Includes audit logging for all user management actions (P16-1.6).
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.exc import IntegrityError
import secrets
import logging

from app.models.user import User, UserRole
from app.utils.auth import hash_password
from app.services.user_audit_service import UserAuditService

logger = logging.getLogger(__name__)

# Temporary password expires after 72 hours
TEMP_PASSWORD_EXPIRY_HOURS = 72

# Password length for generated passwords
GENERATED_PASSWORD_LENGTH = 16


class UserService:
    """
    Service for managing users (Story P15-2.3, P15-2.5, P16-1.6)

    Responsibilities:
    - Create users with temporary passwords (invitation flow)
    - Update user details (admin operations)
    - Reset passwords
    - Enable/disable accounts
    - Delete users
    - Log all actions to audit trail (P16-1.6)
    """

    def __init__(self, db: DBSession):
        self.db = db
        self.audit_service = UserAuditService(db)

    def create_user(
        self,
        username: str,
        role: str = "viewer",
        email: Optional[str] = None,
        send_email: bool = False,
        invited_by: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str]:
        """
        Create a new user with temporary password.

        Args:
            username: Unique username
            role: User role (admin, operator, viewer)
            email: Optional email address
            send_email: Whether to send invitation email (future feature)
            invited_by: User ID of the admin who created this user (Story P16-1.2)
            ip_address: Request IP address for audit logging (P16-1.6)
            user_agent: Request User-Agent for audit logging (P16-1.6)

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

        # Story P16-1.6: Log user creation to audit trail
        self.audit_service.log_create_user(
            actor_id=invited_by,
            target_user_id=user.id,
            username=username,
            role=role,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
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
        is_active: Optional[bool] = None,
        actor_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[User]:
        """
        Update user details.

        Args:
            user_id: User ID to update
            email: New email address
            role: New role (admin, operator, viewer)
            is_active: New active status
            actor_id: ID of user performing the update (P16-1.6)
            ip_address: Request IP address for audit logging (P16-1.6)
            user_agent: Request User-Agent for audit logging (P16-1.6)

        Returns:
            Updated User or None if not found
        """
        user = self.get_user(user_id)
        if not user:
            return None

        # Track changes for audit logging (P16-1.6)
        old_role = user.role.value if user.role else None
        old_is_active = user.is_active

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

        # Story P16-1.6: Log user update to audit trail
        changes = {}
        if email is not None:
            changes["email"] = email
        if role is not None and role != old_role:
            changes["old_role"] = old_role
            changes["new_role"] = role
            # Also log as separate change_role action for role changes
            self.audit_service.log_change_role(
                actor_id=actor_id,
                target_user_id=user_id,
                old_role=old_role,
                new_role=role,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        if is_active is not None and is_active != old_is_active:
            if is_active:
                self.audit_service.log_enable_user(
                    actor_id=actor_id,
                    target_user_id=user_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            else:
                self.audit_service.log_disable_user(
                    actor_id=actor_id,
                    target_user_id=user_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

        # Log general update if there are non-role, non-active changes
        if changes:
            self.audit_service.log_update_user(
                actor_id=actor_id,
                target_user_id=user_id,
                changes=changes,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return user

    def delete_user(
        self,
        user_id: str,
        actor_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Delete a user.

        Cascade deletes all associated sessions and devices.

        Args:
            user_id: User ID to delete
            actor_id: ID of user performing the deletion (P16-1.6)
            ip_address: Request IP address for audit logging (P16-1.6)
            user_agent: Request User-Agent for audit logging (P16-1.6)

        Returns:
            True if deleted, False if not found
        """
        user = self.get_user(user_id)
        if not user:
            return False

        username = user.username

        # Story P16-1.6: Log deletion before actually deleting
        # (so we have the user info still available)
        self.audit_service.log_delete_user(
            actor_id=actor_id,
            target_user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
        )

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

    def reset_password(
        self,
        user_id: str,
        actor_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[datetime]]:
        """
        Reset user password to a temporary password.

        Args:
            user_id: User ID
            actor_id: ID of admin performing the reset (P16-1.6)
            ip_address: Request IP address for audit logging (P16-1.6)
            user_agent: Request User-Agent for audit logging (P16-1.6)

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

        # Story P16-1.6: Log password reset to audit trail
        self.audit_service.log_reset_password(
            actor_id=actor_id,
            target_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return temp_password, expires_at

    def change_password(
        self,
        user: User,
        new_password: str,
        clear_must_change: bool = True,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Change user's password.

        Args:
            user: User object
            new_password: New password (already validated)
            clear_must_change: Whether to clear must_change_password flag
            ip_address: Request IP address for audit logging (P16-1.6)
            user_agent: Request User-Agent for audit logging (P16-1.6)
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

        # Story P16-1.6: Log password change to audit trail
        self.audit_service.log_change_password(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
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
