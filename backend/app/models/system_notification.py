"""
System Notification SQLAlchemy ORM model for system-level alerts (Story P3-7.4)

Unlike the Notification model which is tied to events/rules, SystemNotification
is for application-level alerts like cost warnings, system status, etc.
"""
from sqlalchemy import Column, String, Text, DateTime, Boolean, Index, JSON
from sqlalchemy.sql import func
from app.core.database import Base
import uuid
from datetime import datetime, timezone


class SystemNotification(Base):
    """
    System notification model for application-level alerts.

    Used for notifications not tied to specific events, such as:
    - Cost cap alerts (50%, 80%, 100% thresholds)
    - System status notifications
    - Maintenance alerts

    Attributes:
        id: UUID primary key
        notification_type: Type of notification (cost_alert, system_status, etc.)
        severity: Notification severity (info, warning, error)
        title: Short notification title
        message: Full notification message
        action_url: Optional URL for user action (e.g., settings page)
        extra_data: JSON field for additional context
        read: Whether notification has been read
        dismissed: Whether notification has been dismissed
        created_at: Notification creation timestamp (UTC)
    """

    __tablename__ = "system_notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    notification_type = Column(String(50), nullable=False, index=True)  # cost_alert, system_status
    severity = Column(String(20), nullable=False, default="info")  # info, warning, error
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    action_url = Column(String(500), nullable=True)  # URL for action button
    extra_data = Column(JSON, nullable=True)  # Additional context (renamed from metadata, which is reserved)

    read = Column(Boolean, nullable=False, default=False)
    dismissed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_system_notifications_type', 'notification_type'),
        Index('idx_system_notifications_read', 'read'),
        Index('idx_system_notifications_created', 'created_at'),
        Index('idx_system_notifications_severity', 'severity'),
    )

    def __repr__(self):
        return f"<SystemNotification(id={self.id}, type={self.notification_type}, severity={self.severity})>"

    def to_dict(self):
        """Convert notification to dictionary for API responses."""
        return {
            "id": self.id,
            "notification_type": self.notification_type,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "action_url": self.action_url,
            "extra_data": self.extra_data,
            "read": self.read,
            "dismissed": self.dismissed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
