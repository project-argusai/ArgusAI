"""RecognizedEntity and EntityEvent SQLAlchemy ORM models (Story P4-3.3)

Stores recurring visitor entities and their associations with events for the
Temporal Context Engine. Enables tracking of familiar faces/vehicles with
"first seen", "last seen", and visit count.

RecognizedEntity:
    - Represents a recurring visitor (person, vehicle, or unknown)
    - Stores reference embedding for similarity matching
    - Tracks occurrence count and temporal metadata

EntityEvent:
    - Junction table linking entities to their associated events
    - Stores similarity score for each match
    - Enables efficient queries for entity event history
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Integer, Float, ForeignKey, Index, Boolean
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


def _title_words(value: str) -> str:
    """Capitalize each whitespace-separated word. 'model y' -> 'Model Y'."""
    return " ".join(
        f"{word[:1].upper()}{word[1:].lower()}"
        for word in value.split()
        if word
    )


class RecognizedEntity(Base):
    """
    Recurring visitor entity model.

    Represents a person, vehicle, or other entity that has been seen
    multiple times. The reference_embedding is used to match new events
    against this entity.

    Attributes:
        id: UUID primary key
        entity_type: Type of entity (person, vehicle, unknown)
        name: User-assigned name (nullable, e.g., "Mail Carrier")
        reference_embedding: JSON array of floats (512-dim CLIP embedding)
        first_seen_at: Timestamp of first occurrence
        last_seen_at: Timestamp of most recent occurrence
        occurrence_count: Number of times this entity has been seen
        is_vip: VIP entities trigger high-priority notifications (Story P4-8.4)
        is_blocked: Blocked entities suppress notifications (Story P4-8.4)
        entity_metadata: JSON object for additional entity data (color, make, etc.)
        created_at: Record creation timestamp
        updated_at: Record last update timestamp

    Relationships:
        entity_events: One-to-many relationship with EntityEvent junction
    """

    __tablename__ = "recognized_entities"

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="UUID primary key"
    )
    entity_type = Column(
        String(50),
        nullable=False,
        default="unknown",
        doc="Entity type: person, vehicle, or unknown"
    )
    name = Column(
        String(255),
        nullable=True,
        doc="User-assigned name for the entity"
    )
    reference_embedding = Column(
        Text,
        nullable=False,
        doc="JSON array of 512 floats representing the CLIP embedding"
    )
    first_seen_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="Timestamp of first occurrence"
    )
    last_seen_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="Timestamp of most recent occurrence"
    )
    occurrence_count = Column(
        Integer,
        nullable=False,
        default=1,
        doc="Number of times this entity has been seen"
    )
    # Story P4-8.4: Named Entity Alerts - VIP and blocklist support
    is_vip = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="VIP entities trigger high-priority notifications"
    )
    is_blocked = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="Blocked entities suppress notifications (events still recorded)"
    )
    entity_metadata = Column(
        Text,
        nullable=True,
        doc="JSON object for additional entity data (color, make, vehicle type, etc.)"
    )
    # Story P7-4.1: Additional fields for entities page
    thumbnail_path = Column(
        String(512),
        nullable=True,
        doc="Path to thumbnail image for this entity"
    )
    notes = Column(
        Text,
        nullable=True,
        doc="User notes about this entity"
    )
    # Story P9-4.1: Vehicle-specific fields for signature-based matching
    vehicle_color = Column(
        String(50),
        nullable=True,
        doc="Extracted vehicle color (e.g., 'white', 'black', 'silver')"
    )
    vehicle_make = Column(
        String(50),
        nullable=True,
        doc="Extracted vehicle make (e.g., 'toyota', 'ford', 'honda')"
    )
    vehicle_model = Column(
        String(50),
        nullable=True,
        doc="Extracted vehicle model (e.g., 'camry', 'f150', 'civic')"
    )
    vehicle_signature = Column(
        String(150),
        nullable=True,
        doc="Normalized signature for matching (e.g., 'white-toyota-camry')"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="Record creation timestamp"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        doc="Record last update timestamp"
    )

    # Relationship to EntityEvent junction table
    entity_events = relationship(
        "EntityEvent",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    # P14-5.5: Bidirectional relationships with embedding tables
    # Using back_populates instead of backref for consistency
    face_embeddings = relationship(
        "FaceEmbedding",
        back_populates="entity",
        lazy="dynamic"
    )
    vehicle_embeddings = relationship(
        "VehicleEmbedding",
        back_populates="entity",
        lazy="dynamic"
    )
    # Confirmed reference crops (face / vehicle galleries). Owned by the entity.
    gallery_items = relationship(
        "EntityGalleryItem",
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="dynamic"
    )
    # Keyed plate hashes of a known vehicle (no plain text). Owned by the entity.
    plates = relationship(
        "EntityPlate",
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="dynamic"
    )

    __table_args__ = (
        Index("idx_recognized_entities_last_seen", "last_seen_at"),
        Index("idx_recognized_entities_entity_type", "entity_type"),
        Index("idx_recognized_entities_vehicle_signature", "vehicle_signature"),
    )

    @property
    def display_name(self) -> str:
        """
        Generate a human-readable display name for the entity.

        Priority:
        1. User-assigned name
        2. Vehicle color, make, and model (any subset), title-cased
        3. Vehicle signature formatted as title case
        4. Entity type with ID prefix
        """
        name = self.name.strip() if isinstance(self.name, str) else ""
        if name:
            return name
        if self.entity_type == "vehicle":
            parts = []
            for value in (self.vehicle_color, self.vehicle_make, self.vehicle_model):
                text = value.strip() if isinstance(value, str) else ""
                if text:
                    parts.append(_title_words(text))
            if parts:
                return " ".join(parts)
            signature = self.vehicle_signature.strip() if isinstance(self.vehicle_signature, str) else ""
            if signature:
                return _title_words(signature.replace("-", " "))
        entity_type = self.entity_type if isinstance(self.entity_type, str) and self.entity_type.strip() else "unknown"
        type_label = entity_type[:1].upper() + entity_type[1:]
        return f"{type_label} #{str(self.id)[:8]}"

    def __repr__(self):
        return (
            f"<RecognizedEntity(id={self.id}, type={self.entity_type}, "
            f"name={self.name}, count={self.occurrence_count})>"
        )


class EntityEvent(Base):
    """
    Junction table linking recognized entities to their associated events.

    Stores the similarity score for each match, enabling queries like
    "show all events for this entity" or "which entity does this event
    belong to".

    Attributes:
        entity_id: Foreign key to recognized_entities (part of composite PK)
        event_id: Foreign key to events (part of composite PK)
        similarity_score: Cosine similarity score when matched (0.0-1.0)
        created_at: When the link was created

    Note:
        Uses CASCADE delete so that:
        - When an entity is deleted, all its EntityEvent links are deleted
        - When an event is deleted, all its EntityEvent links are deleted
    """

    __tablename__ = "entity_events"

    entity_id = Column(
        String,
        ForeignKey("recognized_entities.id", ondelete="CASCADE"),
        primary_key=True,
        doc="Foreign key to recognized_entities"
    )
    event_id = Column(
        String,
        ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
        doc="Foreign key to events"
    )
    similarity_score = Column(
        Float,
        nullable=False,
        doc="Cosine similarity score when matched (0.0-1.0, 1.0 for first occurrence)"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="When the entity-event link was created"
    )

    # Relationships
    entity = relationship(
        "RecognizedEntity",
        back_populates="entity_events"
    )
    event = relationship("Event")

    __table_args__ = (
        Index("idx_entity_events_event_id", "event_id"),
    )

    def __repr__(self):
        return (
            f"<EntityEvent(entity_id={self.entity_id}, event_id={self.event_id}, "
            f"similarity={self.similarity_score:.3f})>"
        )
