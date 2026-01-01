"""User Audit Service (Story P16-1.6)

Provides audit logging for all user management actions.
Audit logs are append-only and cannot be modified or deleted via API.
"""
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import desc
import logging

from app.models.user_audit_log import UserAuditLog, AuditAction

logger = logging.getLogger(__name__)


class UserAuditService:
    """
    Service for logging user management audit events (Story P16-1.6)

    All audit logs include:
    - action: The action performed
    - user_id: Who performed the action (actor)
    - target_user_id: Who was affected (optional)
    - details: Action-specific data (JSON)
    - ip_address: Request IP
    - user_agent: Request User-Agent

    Security:
    - Logs cannot be modified or deleted
    - All writes are append-only
    """

    def __init__(self, db: DBSession):
        self.db = db

    def log(
        self,
        action: str,
        user_id: Optional[str] = None,
        target_user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """
        Log a user management action.

        Args:
            action: The action performed (from AuditAction enum or string)
            user_id: UUID of the user performing the action
            target_user_id: UUID of the affected user (if applicable)
            details: Action-specific details as JSON-serializable dict
            ip_address: Request IP address
            user_agent: Request User-Agent string

        Returns:
            The created UserAuditLog entry
        """
        # Convert enum to string if needed
        action_str = action.value if hasattr(action, 'value') else str(action)

        audit_log = UserAuditLog(
            action=action_str,
            user_id=user_id,
            target_user_id=target_user_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)

        logger.info(
            "Audit log created",
            extra={
                "event_type": "audit_log_created",
                "action": action_str,
                "user_id": user_id,
                "target_user_id": target_user_id,
            }
        )

        return audit_log

    def log_create_user(
        self,
        actor_id: str,
        target_user_id: str,
        username: str,
        role: str,
        email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log user creation"""
        return self.log(
            action=AuditAction.CREATE_USER,
            user_id=actor_id,
            target_user_id=target_user_id,
            details={
                "username": username,
                "role": role,
                "email": email,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_update_user(
        self,
        actor_id: str,
        target_user_id: str,
        changes: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log user update"""
        return self.log(
            action=AuditAction.UPDATE_USER,
            user_id=actor_id,
            target_user_id=target_user_id,
            details={"changes": changes},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_delete_user(
        self,
        actor_id: str,
        target_user_id: str,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log user deletion"""
        return self.log(
            action=AuditAction.DELETE_USER,
            user_id=actor_id,
            target_user_id=target_user_id,
            details={"username": username},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_change_role(
        self,
        actor_id: str,
        target_user_id: str,
        old_role: str,
        new_role: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log role change"""
        return self.log(
            action=AuditAction.CHANGE_ROLE,
            user_id=actor_id,
            target_user_id=target_user_id,
            details={"old_role": old_role, "new_role": new_role},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_reset_password(
        self,
        actor_id: str,
        target_user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log password reset (admin-initiated)"""
        return self.log(
            action=AuditAction.RESET_PASSWORD,
            user_id=actor_id,
            target_user_id=target_user_id,
            details={},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_change_password(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log password change (user-initiated)"""
        return self.log(
            action=AuditAction.CHANGE_PASSWORD,
            user_id=user_id,
            target_user_id=user_id,  # User changed their own password
            details={},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_disable_user(
        self,
        actor_id: str,
        target_user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log user account disable"""
        return self.log(
            action=AuditAction.DISABLE_USER,
            user_id=actor_id,
            target_user_id=target_user_id,
            details={},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_enable_user(
        self,
        actor_id: str,
        target_user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log user account enable"""
        return self.log(
            action=AuditAction.ENABLE_USER,
            user_id=actor_id,
            target_user_id=target_user_id,
            details={},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_login_success(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log successful login"""
        return self.log(
            action=AuditAction.LOGIN_SUCCESS,
            user_id=user_id,
            target_user_id=user_id,
            details={},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_login_failed(
        self,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserAuditLog:
        """Log failed login attempt"""
        return self.log(
            action=AuditAction.LOGIN_FAILED,
            user_id=None,  # User not authenticated
            target_user_id=None,
            details={"username": username},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def get_audit_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        target_user_id: Optional[str] = None,
    ) -> List[UserAuditLog]:
        """
        Get audit logs with optional filtering.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            action: Filter by action type
            user_id: Filter by actor
            target_user_id: Filter by target user

        Returns:
            List of UserAuditLog entries, newest first
        """
        query = self.db.query(UserAuditLog)

        if action:
            query = query.filter(UserAuditLog.action == action)
        if user_id:
            query = query.filter(UserAuditLog.user_id == user_id)
        if target_user_id:
            query = query.filter(UserAuditLog.target_user_id == target_user_id)

        return query.order_by(desc(UserAuditLog.created_at)).offset(offset).limit(limit).all()

    def get_user_audit_history(
        self,
        target_user_id: str,
        limit: int = 50,
    ) -> List[UserAuditLog]:
        """
        Get audit history for a specific user.

        Args:
            target_user_id: The user to get history for
            limit: Maximum number of records

        Returns:
            List of audit events affecting this user
        """
        return (
            self.db.query(UserAuditLog)
            .filter(UserAuditLog.target_user_id == target_user_id)
            .order_by(desc(UserAuditLog.created_at))
            .limit(limit)
            .all()
        )
