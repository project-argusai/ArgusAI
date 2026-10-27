"""Incident ORM model: one row per multi-camera correlation group.

``id`` equals ``events.correlation_group_id``. Member events keep their own
per-camera descriptions; this row only adds the combined result.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base

INCIDENT_STATUSES = ("pending", "done", "fallback", "failed")


def _now():
    return datetime.now(timezone.utc)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("idx_incidents_status", "status"),)

    id = Column(String, primary_key=True)  # == events.correlation_group_id
    status = Column(String(16), nullable=False, default="pending")
    combined_description = Column(Text, nullable=True)
    combined_identification = Column(Text, nullable=True)  # JSON
    # Ordered union of member events' matched_entity_ids (JSON). Never
    # derived from description or identification text.
    matched_entity_ids = Column(Text, nullable=True)
    primary_event_id = Column(String, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    # Reserved for one-notification-per-incident delivery claims.
    notified_event_id = Column(String, nullable=True)
    update_pushed_at = Column(DateTime(timezone=True), nullable=True)
    member_count = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    provider_used = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    def __repr__(self):
        return f"<Incident(id={self.id}, status={self.status})>"


class IncidentDelivery(Base):
    """One delivered notification channel per incident (or per lone event).

    ``group_key`` is the correlation_group_id, or the event id when the event
    had no group yet when it alerted. ``channel`` is ``push`` or
    ``rule:<rule_id>``. The unique constraint is the atomic dedup claim.
    """

    __tablename__ = "incident_deliveries"
    __table_args__ = (UniqueConstraint("group_key", "channel", name="uq_incident_delivery"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_key = Column(String, nullable=False, index=True)
    channel = Column(String(64), nullable=False)
    event_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
