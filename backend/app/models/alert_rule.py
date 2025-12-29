"""AlertRule SQLAlchemy ORM model for alert rule engine (Epic 5)"""
from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, Index, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone


class AlertRule(Base):
    """
    Alert rule model for event-based notifications.

    Represents a user-defined rule that triggers alerts when events match
    specified conditions. Supports dashboard notifications and webhook actions.

    Attributes:
        id: UUID primary key
        name: Human-readable rule name
        is_enabled: Whether rule is active (default True)
        conditions: JSON object defining match criteria:
            - object_types: List of object types to match (OR logic within)
            - cameras: List of camera IDs (empty = any camera)
            - time_of_day: {"start": "HH:MM", "end": "HH:MM"} (optional)
            - days_of_week: List of 1-7 (Monday=1, Sunday=7) (optional)
            - min_confidence: Minimum confidence threshold (optional)
        actions: JSON object defining triggered actions:
            - dashboard_notification: bool (create in-app notification)
            - webhook: {"url": str, "headers": dict} (HTTP POST)
        cooldown_minutes: Minimum time between triggers for this rule
        last_triggered_at: Timestamp of last trigger (for cooldown)
        trigger_count: Total number of times rule has triggered
        created_at: Record creation timestamp (UTC)
        updated_at: Record last update timestamp (UTC)
    """

    __tablename__ = "alert_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)

    # JSON fields for flexible conditions and actions
    conditions = Column(Text, nullable=False, default='{}')
    # Expected structure: {
    #     "object_types": ["person", "vehicle", ...],
    #     "cameras": ["camera-uuid-1", ...] or [] for any,
    #     "time_of_day": {"start": "09:00", "end": "17:00"} or null,
    #     "days_of_week": [1, 2, 3, 4, 5] or null (1=Mon, 7=Sun),
    #     "min_confidence": 80 or null,
    #     "audio_event_types": ["glass_break", "gunshot", "scream", "doorbell"] or null (Story P6-3.2)
    # }

    actions = Column(Text, nullable=False, default='{}')
    # Expected structure: {
    #     "dashboard_notification": true,
    #     "webhook": {
    #         "url": "https://example.com/webhook",
    #         "headers": {"Authorization": "Bearer ..."}
    #     } or null
    # }

    # Story P4-8.4: Entity-based matching (list-based, for complex rules)
    entity_ids = Column(Text, nullable=True)
    # Expected structure: ["entity-uuid-1", "entity-uuid-2", ...] or null (any entity)
    entity_names = Column(Text, nullable=True)
    # Expected structure: ["John*", "Mail Carrier", ...] or null (any name)
    # Supports wildcard matching with fnmatch patterns

    # Story P12-1.1: Simplified entity-based filtering (single entity selection)
    entity_id = Column(
        String(36),
        ForeignKey("recognized_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    # entity_match_mode values:
    #   'any' - No entity filter (default, existing behavior)
    #   'specific' - Trigger only for rule.entity_id match
    #   'unknown' - Trigger only for events with NO matched entity (stranger detection)
    entity_match_mode = Column(
        String(20),
        nullable=False,
        default='any'
    )

    # Relationship for eager loading entity name
    entity = relationship(
        "RecognizedEntity",
        foreign_keys=[entity_id],
        lazy="joined"
    )

    # Story P14-2.2: Relationship to webhook logs for CASCADE delete
    webhook_logs = relationship("WebhookLog", back_populates="alert_rule", cascade="all, delete-orphan")

    cooldown_minutes = Column(Integer, nullable=False, default=5)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    trigger_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_alert_rules_is_enabled', 'is_enabled'),
        Index('idx_alert_rules_last_triggered', 'last_triggered_at'),
        Index('idx_alert_rules_entity_id', 'entity_id'),
    )

    def __repr__(self):
        return f"<AlertRule(id={self.id}, name={self.name}, is_enabled={self.is_enabled})>"


class WebhookLog(Base):
    """
    Webhook execution log for audit trail and debugging.

    Records each webhook execution attempt with status and timing information.

    Attributes:
        id: Auto-increment primary key
        alert_rule_id: UUID of the alert rule that triggered the webhook
        event_id: UUID of the event that matched the rule
        url: Target webhook URL
        status_code: HTTP response status code (or 0 for connection errors)
        response_time_ms: Time to receive response in milliseconds
        retry_count: Number of retry attempts (0 = first try)
        success: Whether webhook succeeded (2xx status)
        error_message: Error details if failed (optional)
        created_at: Execution timestamp (UTC)
    """

    __tablename__ = "webhook_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_rule_id = Column(
        String,
        ForeignKey('alert_rules.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    event_id = Column(
        String,
        ForeignKey('events.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    url = Column(String(2000), nullable=False)
    status_code = Column(Integer, nullable=False, default=0)
    response_time_ms = Column(Integer, nullable=False, default=0)
    retry_count = Column(Integer, nullable=False, default=0)
    success = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Story P14-2.2: Add relationships for ORM navigation and CASCADE delete enforcement
    alert_rule = relationship("AlertRule", back_populates="webhook_logs")
    event = relationship("Event", back_populates="webhook_logs")

    __table_args__ = (
        Index('idx_webhook_logs_rule_event', 'alert_rule_id', 'event_id'),
        Index('idx_webhook_logs_created', 'created_at'),
    )

    def __repr__(self):
        return f"<WebhookLog(id={self.id}, rule_id={self.alert_rule_id}, status={self.status_code}, success={self.success})>"
