"""PromptHistory SQLAlchemy ORM model for tracking AI prompt evolution

Story P4-5.4: Feedback-Informed Prompts
"""
from sqlalchemy import Column, String, Integer, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone


class PromptHistory(Base):
    """
    Tracks the evolution of AI description prompts over time.

    Records each prompt version with its source (manual edit, suggestion,
    A/B test winner) and accuracy metrics before/after application.

    Attributes:
        id: UUID primary key
        prompt_version: Sequential version number
        prompt_text: Full prompt text
        source: How this prompt was created ('manual', 'suggestion', 'ab_test')
        applied_suggestions: JSON array of suggestion IDs that were applied
        accuracy_before: Accuracy rate before this prompt was applied
        accuracy_after: Accuracy rate after this prompt was applied
        camera_id: Camera ID if this is a camera-specific prompt
        created_at: When this version was created
    """

    __tablename__ = "prompt_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    prompt_version = Column(Integer, nullable=False)
    prompt_text = Column(Text, nullable=False)
    source = Column(String(50), nullable=False)  # 'manual', 'suggestion', 'ab_test'
    applied_suggestions = Column(Text, nullable=True)  # JSON array of suggestion IDs
    accuracy_before = Column(Float, nullable=True)
    accuracy_after = Column(Float, nullable=True)
    camera_id = Column(
        String,
        ForeignKey('cameras.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationship to Camera
    camera = relationship("Camera", foreign_keys=[camera_id])

    def __repr__(self):
        return (
            f"<PromptHistory(id={self.id}, version={self.prompt_version}, "
            f"source={self.source}, camera_id={self.camera_id})>"
        )
