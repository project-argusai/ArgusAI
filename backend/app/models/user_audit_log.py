"""User Audit Log SQLAlchemy ORM model (Story P16-1.6)

Tracks all user management actions for security audit trail.
"""
from sqlalchemy import Column, String, DateTime, Text, Index, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone
from enum import Enum


class AuditAction(str, Enum):
    """User management audit actions"""
    CREATE_USER = "create_user"
    UPDATE_USER = "update_user"
    DELETE_USER = "delete_user"
    CHANGE_ROLE = "change_role"
    RESET_PASSWORD = "reset_password"
    CHANGE_PASSWORD = "change_password"
    DISABLE_USER = "disable_user"
    ENABLE_USER = "enable_user"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"


class UserAuditLog(Base):
    """
    User audit log model for tracking user management actions (Story P16-1.6)

    Attributes:
        id: UUID primary key
        action: The action performed (create_user, update_user, etc.)
        user_id: UUID of the user who performed the action (actor)
        target_user_id: UUID of the user affected by the action (optional)
        details: JSON containing action-specific details
        ip_address: IP address of the request
        user_agent: User agent string from the request
        created_at: Timestamp when the action occurred (UTC)

    Security:
        - Audit logs cannot be modified or deleted via API
        - All entries are append-only
        - IP addresses are stored for security tracing
    """

    __tablename__ = "user_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    action = Column(String(50), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    target_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    details = Column(JSON, nullable=True)  # Action-specific details (old_role, new_role, etc.)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    user_agent = Column(String(500), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )

    # Relationships
    actor = relationship("User", foreign_keys=[user_id], lazy="joined")
    target = relationship("User", foreign_keys=[target_user_id], lazy="joined")

    # Indexes for common queries
    __table_args__ = (
        Index('idx_audit_action_created', 'action', 'created_at'),
        Index('idx_audit_target_created', 'target_user_id', 'created_at'),
    )

    def __repr__(self):
        return f"<UserAuditLog(id={self.id}, action={self.action}, user_id={self.user_id}, target={self.target_user_id})>"
