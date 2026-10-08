"""EntityGalleryItem: a confirmed reference crop for a person or vehicle.

A gallery holds several small crops per entity (day/night, front/back) and
matching takes the best score over them, instead of one averaged
whole-frame reference.

Items are only ever added by an explicit user action (assigning an event to
the entity, or "use as reference"). Automatic matches never add items, so a
wrong match cannot drift the reference.

Unlike ``face_embeddings`` / ``vehicle_embeddings`` (per-event observations
that are deleted with their event), gallery items belong to the entity: they
survive event retention, and ``source_event_id`` is cleared when the source
event is deleted. They are removed with the entity.

Attributes:
    id: UUID primary key
    entity_id: Owning entity (CASCADE delete)
    kind: "face" or "vehicle"
    model_version: Embedding model, e.g. "sface-2021dec-v1"; only items of the
        current version are compared
    embedding: JSON float array (128-d SFace or 512-d CLIP)
    crop_path: Crop JPEG, relative to the entity-crops media root
    dominant_color: Coarse colour family of a vehicle crop (None at night)
    bounding_box: JSON box in the source frame
    source_event_id: Event the crop came from (SET NULL on delete)
    source_observation_id: The face/vehicle observation row it was copied from
    created_at: When the item was enrolled (UTC)
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class EntityGalleryItem(Base):
    __tablename__ = "entity_gallery_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(
        String,
        ForeignKey("recognized_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(String(16), nullable=False)
    model_version = Column(String(50), nullable=False)
    embedding = Column(Text, nullable=False)
    crop_path = Column(String(512), nullable=True)
    dominant_color = Column(String(20), nullable=True)
    bounding_box = Column(Text, nullable=True)
    source_event_id = Column(
        String,
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_observation_id = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    entity = relationship("RecognizedEntity", back_populates="gallery_items")

    __table_args__ = (
        Index("idx_entity_gallery_entity_kind", "entity_id", "kind"),
        Index("idx_entity_gallery_source_event", "source_event_id"),
        UniqueConstraint("entity_id", "source_observation_id", name="uq_entity_gallery_observation"),
    )

    def __repr__(self):
        return f"<EntityGalleryItem(id={self.id}, entity_id={self.entity_id}, kind={self.kind})>"
