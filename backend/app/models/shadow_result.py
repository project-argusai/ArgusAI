"""Cloud-audit shadow tables (#735, #691 Phase 1 S1).

``shadow_results``: one row per audited event. Frozen JSON copies of the
local and cloud results, a source (``audit`` or a free ``fallback`` pair) and
the owner's verdict. After 30 days the paired text (``local_result`` and
``cloud_result``) is nulled; the row keeps its source, verdict and
timestamps until it is deleted at 365 days.

``shadow_daily_summary``: numbers only, one row per (day, source), kept
365 days.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base

SHADOW_SOURCES = ("audit", "fallback")
SHADOW_VERDICTS = ("agree", "disagree", "unsure")  # matches #734 API and #739 UI


def _now():
    return datetime.now(timezone.utc)


class ShadowResult(Base):
    __tablename__ = "shadow_results"
    __table_args__ = (
        Index("idx_shadow_results_created_at", "created_at"),
        Index("idx_shadow_results_source_created", "source", "created_at"),
        CheckConstraint("source IN ('audit', 'fallback')", name="ck_shadow_results_source"),
        CheckConstraint("verdict IS NULL OR verdict IN ('agree', 'disagree', 'unsure')",
                        name="ck_shadow_results_verdict"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("events.id", ondelete="CASCADE"), nullable=False,
                      unique=True)
    source = Column(String(16), nullable=False)
    local_result = Column(Text, nullable=True)   # JSON, numpy-safe
    cloud_result = Column(Text, nullable=True)   # JSON, numpy-safe
    local_provider = Column(String(32), nullable=True)
    cloud_provider = Column(String(32), nullable=True)
    verdict = Column(String(16), nullable=True)
    verdict_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    def __repr__(self):
        return f"<ShadowResult(id={self.id}, source={self.source})>"


class ShadowDailySummary(Base):
    __tablename__ = "shadow_daily_summary"
    __table_args__ = (
        UniqueConstraint("day", "source", name="uq_shadow_daily_summary_day_source"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Date, nullable=False, index=True)
    source = Column(String(16), nullable=False)
    metrics = Column(Text, nullable=False)  # JSON, numbers only
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    def __repr__(self):
        return f"<ShadowDailySummary(day={self.day}, source={self.source})>"
