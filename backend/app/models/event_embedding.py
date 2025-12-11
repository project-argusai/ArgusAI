"""EventEmbedding SQLAlchemy ORM model for image embeddings (Story P4-3.1)

Stores CLIP ViT-B/32 embeddings (512-dim) for event thumbnails to enable
similarity search and recurring visitor detection in the Temporal Context Engine.

Attributes:
    id: UUID primary key
    event_id: Foreign key to events table (unique, one embedding per event)
    embedding: JSON array of 512 floats (stored as Text for SQLite compatibility)
    model_version: Version string for the embedding model (e.g., "clip-ViT-B-32-v1")
    created_at: Timestamp when embedding was generated (UTC)

Note:
    Embeddings are stored as JSON arrays in a Text column for SQLite compatibility.
    For PostgreSQL with pgvector, this could be migrated to a VECTOR(512) column.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class EventEmbedding(Base):
    """
    Image embedding model for event thumbnails.

    Stores 512-dimensional CLIP embeddings as JSON arrays for
    SQLite compatibility (no pgvector required).

    Relationships:
        event: One-to-one relationship with Event model
    """

    __tablename__ = "event_embeddings"

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
        unique=True,
        index=True,
        doc="Foreign key to events table (one embedding per event)"
    )
    embedding = Column(
        Text,
        nullable=False,
        doc="JSON array of 512 floats representing the CLIP embedding"
    )
    model_version = Column(
        String(50),
        nullable=False,
        doc="Model version string for compatibility tracking (e.g., clip-ViT-B-32-v1)"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="Timestamp when embedding was generated"
    )

    # Relationship to Event model
    event = relationship("Event", back_populates="embedding")

    __table_args__ = (
        Index("idx_event_embeddings_model_version", "model_version"),
    )

    def __repr__(self):
        return (
            f"<EventEmbedding(id={self.id}, event_id={self.event_id}, "
            f"model_version={self.model_version})>"
        )
