"""SummaryFeedback SQLAlchemy ORM model for user feedback on activity summaries

Story P9-3.4: Add Summary Feedback Buttons
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone


class SummaryFeedback(Base):
    """
    User feedback on AI-generated activity summaries.

    Allows users to rate summaries as positive/negative and provide
    optional correction text to improve AI summarization accuracy over time.

    Attributes:
        id: UUID primary key
        summary_id: Foreign key to activity_summaries table (unique - one feedback per summary)
        rating: User rating - 'positive' or 'negative'
        correction_text: Optional correction text (max 500 chars enforced at API level)
        created_at: When feedback was submitted
        updated_at: When feedback was last modified
    """

    __tablename__ = "summary_feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    summary_id = Column(
        String,
        ForeignKey('activity_summaries.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,  # One feedback per summary
        index=True
    )
    rating = Column(String(20), nullable=False)  # 'positive' or 'negative'
    correction_text = Column(Text, nullable=True)  # Optional correction text
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationship back to ActivitySummary
    summary = relationship("ActivitySummary", back_populates="feedback")

    __table_args__ = (
        UniqueConstraint('summary_id', name='uq_summary_feedback_summary_id'),
    )

    def __repr__(self):
        return f"<SummaryFeedback(id={self.id}, summary_id={self.summary_id}, rating={self.rating})>"
