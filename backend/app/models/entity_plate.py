"""EntityPlate: a keyed hash of a licence plate on a KNOWN vehicle.

Minimal storage by design:

* Only plates of saved vehicle entities are stored. A plate read on an
  event that matches no saved vehicle is never written anywhere.
* ``plate_hash`` is HMAC-SHA256 over the normalised plate, keyed with the
  ``PLATE_HASH_SALT`` secret (``plate_reader.hash_plate``). There is no
  plain-text plate column, and the API never returns the hash.
* ``key_id`` is a short fingerprint of the salt used, so rows made with an
  older salt are recognised as unusable instead of silently never matching.

Rows belong to the entity (CASCADE) and are removed with it. A row learned
from an event keeps ``source_event_id`` (SET NULL when the event goes) so a
corrected assignment can take it back.

Attributes:
    id: UUID primary key
    entity_id: Owning vehicle entity (CASCADE delete)
    plate_hash: 64-char hex HMAC
    hash_version: Hash scheme, e.g. "hmac-sha256-v1"
    key_id: Fingerprint of the salt the hash was made with
    source: "manual" (typed by a user) or "event" (read on an assigned event)
    source_event_id: Event a read came from (SET NULL on delete)
    created_at: When it was saved (UTC)
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class EntityPlate(Base):
    __tablename__ = "entity_plates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(
        String,
        ForeignKey("recognized_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    plate_hash = Column(String(64), nullable=False)
    hash_version = Column(String(32), nullable=False)
    key_id = Column(String(16), nullable=False)
    source = Column(String(16), nullable=False)
    source_event_id = Column(
        String,
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    entity = relationship("RecognizedEntity", back_populates="plates")

    __table_args__ = (
        UniqueConstraint("entity_id", "plate_hash", name="uq_entity_plate_hash"),
        Index("idx_entity_plates_hash", "plate_hash"),
        Index("idx_entity_plates_source_event", "source_event_id"),
    )

    def __repr__(self):
        return f"<EntityPlate(id={self.id}, entity_id={self.entity_id}, source={self.source})>"
