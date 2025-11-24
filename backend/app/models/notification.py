"""Notification SQLAlchemy ORM model for dashboard notifications (Story 5.4)"""
from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, Index, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone


class Notification(Base):
    """
    Dashboard notification model for real-time alerts.

    Represents an in-dashboard notification created when an alert rule triggers
    with dashboard_notification action enabled.

    Attributes:
        id: UUID primary key
        event_id: UUID of the triggering event (FK to events)
        rule_id: UUID of the alert rule that triggered (FK to alert_rules)
        rule_name: Cached rule name for display (denormalized for performance)
        event_description: Cached event description (truncated, max 200 chars)
        thumbnail_url: URL path to event thumbnail
        read: Whether notification has been read by user
        created_at: Notification creation timestamp (UTC)
    """

    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(String, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True)

    # Denormalized fields for fast display without joins
    rule_name = Column(String(200), nullable=False)
    event_description = Column(String(200), nullable=True)  # Truncated for display
    thumbnail_url = Column(String(500), nullable=True)

    read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_notifications_read', 'read'),
        Index('idx_notifications_created', 'created_at'),
        Index('idx_notifications_rule_event', 'rule_id', 'event_id'),
    )

    def __repr__(self):
        return f"<Notification(id={self.id}, rule={self.rule_name}, read={self.read})>"

    def to_dict(self):
        """Convert notification to dictionary for API responses."""
        return {
            "id": self.id,
            "event_id": self.event_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "event_description": self.event_description,
            "thumbnail_url": self.thumbnail_url,
            "read": self.read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
