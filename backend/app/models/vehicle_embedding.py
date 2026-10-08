"""VehicleEmbedding SQLAlchemy ORM model for vehicle-specific embeddings (Story P4-8.3)

Stores vehicle embeddings extracted from event thumbnails for vehicle recognition.
Each vehicle detected in an event thumbnail gets its own embedding record.

Attributes:
    id: UUID primary key
    event_id: Foreign key to events table (CASCADE delete)
    entity_id: Optional foreign key to recognized_entities (SET NULL on delete)
    embedding: JSON array of 512 floats (stored as Text for SQLite compatibility)
    bounding_box: JSON object with x, y, width, height
    confidence: Detection confidence score (0.0-1.0)
    vehicle_type: Detected vehicle type (car, truck, motorcycle, bus)
    model_version: Version string for the embedding model
    created_at: Timestamp when embedding was generated (UTC)

Privacy:
    - Vehicle embeddings are stored locally only
    - Users can delete individual or all vehicle embeddings
    - CASCADE delete ensures cleanup when events are deleted
"""
from datetime import datetime, timezone

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class VehicleEmbedding(Base):
    """
    Vehicle embedding model for vehicle recognition.

    Stores 512-dimensional embeddings of detected vehicles from event thumbnails.
    Multiple vehicles can be detected in a single event, so this is a one-to-many
    relationship with events.

    Relationships:
        event: Many-to-one relationship with Event model
        entity: Many-to-one relationship with RecognizedEntity (optional)
    """

    __tablename__ = "vehicle_embeddings"

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="UUID primary key"
    )
    event_id = Column(
        String,
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to events table (one event can have multiple vehicle embeddings)"
    )
    entity_id = Column(
        String,
        ForeignKey("recognized_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Optional foreign key to recognized_entities for linking to known vehicles"
    )
    embedding = Column(
        Text,
        nullable=False,
        doc="JSON array of 512 floats representing the vehicle embedding"
    )
    bounding_box = Column(
        Text,
        nullable=False,
        doc="JSON object with x, y, width, height coordinates"
    )
    confidence = Column(
        Float,
        nullable=False,
        doc="Vehicle detection confidence score (0.0-1.0)"
    )
    vehicle_type = Column(
        String(50),
        nullable=True,
        doc="Detected vehicle type: car, truck, motorcycle, bus, etc."
    )
    model_version = Column(
        String(50),
        nullable=False,
        doc="Model version string for compatibility tracking (e.g., clip-ViT-B-32-v1)"
    )
    crop_path = Column(
        String(512),
        nullable=True,
        doc="Crop JPEG relative to the entity-crops media root (aligned 112x112 face / padded vehicle)"
    )
    dominant_color = Column(
        String(20),
        nullable=True,
        doc="Coarse colour family of the crop (None for IR/greyscale frames)"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="Timestamp when vehicle embedding was generated"
    )

    # Relationships
    event = relationship("Event", back_populates="vehicle_embeddings")
    # P14-5.5: Use back_populates for consistency (reverse rel on RecognizedEntity)
    entity = relationship("RecognizedEntity", back_populates="vehicle_embeddings")

    __table_args__ = (
        Index("idx_vehicle_embeddings_event_id", "event_id"),
        Index("idx_vehicle_embeddings_entity_id", "entity_id"),
        Index("idx_vehicle_embeddings_model_version", "model_version"),
    )

    def __repr__(self):
        return (
            f"<VehicleEmbedding(id={self.id}, event_id={self.event_id}, "
            f"entity_id={self.entity_id}, vehicle_type={self.vehicle_type}, "
            f"confidence={self.confidence:.2f})>"
        )
