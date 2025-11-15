"""MotionEvent SQLAlchemy ORM model"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, CheckConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class MotionEvent(Base):
    """
    Motion event model representing detected motion from camera feeds

    Attributes:
        id: UUID primary key
        camera_id: Foreign key to cameras table
        timestamp: When motion was detected (UTC with timezone)
        confidence: Motion confidence score (0.0-1.0)
        motion_intensity: Optional motion intensity metric
        algorithm_used: Algorithm that detected motion ('mog2', 'knn', 'frame_diff')
        bounding_box: JSON string with motion bounding box {x, y, width, height}
        frame_thumbnail: Base64-encoded JPEG thumbnail of full frame (~50KB)
        ai_event_id: Optional foreign key to AI events (for F3 integration)
        created_at: Record creation timestamp (UTC with timezone)
    """

    __tablename__ = "motion_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id = Column(String, ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    motion_intensity = Column(Float, nullable=True)
    algorithm_used = Column(String(20), nullable=False)
    bounding_box = Column(Text, nullable=True)  # JSON: {"x": int, "y": int, "width": int, "height": int}
    frame_thumbnail = Column(Text, nullable=True)  # Base64 JPEG
    ai_event_id = Column(String, nullable=True)  # Future F3 integration
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    camera = relationship("Camera", back_populates="motion_events")

    __table_args__ = (
        CheckConstraint('confidence >= 0.0 AND confidence <= 1.0', name='check_confidence_range'),
    )

    def __repr__(self):
        return f"<MotionEvent(id={self.id}, camera_id={self.camera_id}, timestamp={self.timestamp}, confidence={self.confidence:.2f})>"
