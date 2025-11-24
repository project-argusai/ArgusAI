"""Event SQLAlchemy ORM model for AI-generated semantic events"""
from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, ForeignKey, CheckConstraint, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone


class Event(Base):
    """
    AI-generated semantic event model.

    Represents motion events enriched with AI vision analysis, including
    natural language descriptions and detected objects.

    Attributes:
        id: UUID primary key
        camera_id: Foreign key to cameras table
        timestamp: When event occurred (UTC with timezone, indexed)
        description: AI-generated natural language description (FTS5 indexed)
        confidence: AI confidence score (0-100, CHECK constraint)
        objects_detected: JSON array of detected objects ["person", "vehicle", etc.]
        thumbnail_path: Optional file path to thumbnail (filesystem mode)
        thumbnail_base64: Optional base64-encoded thumbnail (database mode)
        alert_triggered: Whether alert rules were triggered (Epic 5)
        created_at: Record creation timestamp (UTC with timezone)
    """

    __tablename__ = "events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id = Column(String, ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    description = Column(Text, nullable=False)  # AI-generated description
    confidence = Column(Integer, nullable=False)  # 0-100
    objects_detected = Column(Text, nullable=False)  # JSON array: ["person", "vehicle", "animal", "package", "unknown"]
    thumbnail_path = Column(String(500), nullable=True)  # Filesystem mode: relative path
    thumbnail_base64 = Column(Text, nullable=True)  # Database mode: base64 JPEG
    alert_triggered = Column(Boolean, nullable=False, default=False)  # Epic 5 feature
    alert_rule_ids = Column(Text, nullable=True)  # JSON array of triggered rule UUIDs (Epic 5)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    camera = relationship("Camera", back_populates="events")

    __table_args__ = (
        CheckConstraint('confidence >= 0 AND confidence <= 100', name='check_confidence_range'),
        Index('idx_events_timestamp_desc', 'timestamp', postgresql_ops={'timestamp': 'DESC'}),
        Index('idx_events_camera_timestamp', 'camera_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<Event(id={self.id}, camera_id={self.camera_id}, timestamp={self.timestamp}, confidence={self.confidence})>"
