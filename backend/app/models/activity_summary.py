"""
ActivitySummary Model (Story P4-4.1, P4-4.2, P9-3.4)

Stores generated activity summaries for caching and historical access.
Summaries can be generated on-demand or scheduled via DigestScheduler.

Story P4-4.2: Added digest_type column to distinguish scheduled digests.
Story P9-3.4: Added feedback relationship for summary feedback.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, Integer, Float
from sqlalchemy.orm import relationship

from app.core.database import Base


class ActivitySummary(Base):
    """
    Database model for storing generated activity summaries.

    Attributes:
        id: Unique identifier (UUID)
        summary_text: The generated natural language summary
        period_start: Start of the summarized time period
        period_end: End of the summarized time period
        event_count: Number of events included in summary
        camera_ids: JSON array of camera IDs (null = all cameras)
        generated_at: When the summary was generated
        ai_cost: Cost of AI generation (USD)
        provider_used: Which AI provider generated the summary
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens generated
        digest_type: Type of digest ('daily', 'weekly', 'manual', null for on-demand)

    Story: P4-4.1 - Summary Generation Service
    Story: P4-4.2 - Daily Digest Scheduler (added digest_type)
    """

    __tablename__ = "activity_summaries"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="Unique identifier (UUID)"
    )

    summary_text = Column(
        Text,
        nullable=False,
        doc="Generated natural language summary"
    )

    period_start = Column(
        DateTime,
        nullable=False,
        index=True,
        doc="Start of summarized time period"
    )

    period_end = Column(
        DateTime,
        nullable=False,
        index=True,
        doc="End of summarized time period"
    )

    event_count = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of events in summary"
    )

    camera_ids = Column(
        Text,
        nullable=True,
        doc="JSON array of camera IDs, null for all cameras"
    )

    generated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="When summary was generated"
    )

    ai_cost = Column(
        Float,
        nullable=False,
        default=0.0,
        doc="Cost of AI generation in USD"
    )

    provider_used = Column(
        String(50),
        nullable=True,
        doc="AI provider that generated summary (openai, grok, claude, gemini)"
    )

    input_tokens = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of input tokens used"
    )

    output_tokens = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of output tokens generated"
    )

    digest_type = Column(
        String(20),
        nullable=True,
        index=True,
        doc="Type of digest: 'daily', 'weekly', 'manual', or null for on-demand"
    )

    delivery_status = Column(
        Text,
        nullable=True,
        doc="JSON object with delivery status per channel: {channels_succeeded: [], errors: {}, delivery_time_ms: int}"
    )

    # Story P9-3.4: Relationship to SummaryFeedback
    feedback = relationship(
        "SummaryFeedback",
        back_populates="summary",
        uselist=False,
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<ActivitySummary(id={self.id}, "
            f"period={self.period_start.date()} to {self.period_end.date()}, "
            f"events={self.event_count})>"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        import json as json_lib
        delivery_status_parsed = None
        if self.delivery_status:
            try:
                delivery_status_parsed = json_lib.loads(self.delivery_status)
            except (json_lib.JSONDecodeError, TypeError):
                delivery_status_parsed = self.delivery_status

        return {
            "id": self.id,
            "summary_text": self.summary_text,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "event_count": self.event_count,
            "camera_ids": self.camera_ids,
            "generated_at": self.generated_at.isoformat(),
            "ai_cost": self.ai_cost,
            "provider_used": self.provider_used,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "digest_type": self.digest_type,
            "delivery_status": delivery_status_parsed,
        }
