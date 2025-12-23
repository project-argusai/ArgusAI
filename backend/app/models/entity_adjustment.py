"""EntityAdjustment SQLAlchemy ORM model (Story P9-4.3)

Tracks manual entity-event corrections for future ML training.
When users unlink, assign, move, or merge entity-event associations,
this table records the correction for model improvement.

This is the foundation for Story P9-4.6 and IMP-016 (MCP server context).
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
import uuid

from app.core.database import Base


class EntityAdjustment(Base):
    """
    Manual entity-event correction record.

    Tracks all manual corrections to entity-event associations for future
    ML training. Stores the original and new entity assignments along with
    a snapshot of the event description at the time of adjustment.

    Attributes:
        id: UUID primary key
        event_id: Foreign key to events table
        old_entity_id: Previous entity assignment (NULL for new assignment)
        new_entity_id: New entity assignment (NULL for unlink)
        action: Type of adjustment (unlink, assign, move, merge)
        event_description: Snapshot of event description for ML training
        created_at: When the adjustment was made

    Actions:
        - unlink: Remove event from entity (old_entity_id set, new_entity_id NULL)
        - assign: Assign event to entity (old_entity_id NULL, new_entity_id set)
        - move: Move event from one entity to another (both set)
        - merge: Entity was merged into another (both set, old deleted)
    """

    __tablename__ = "entity_adjustments"

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
        doc="Foreign key to events table"
    )
    old_entity_id = Column(
        String,
        ForeignKey("recognized_entities.id", ondelete="SET NULL"),
        nullable=True,
        doc="Previous entity assignment (NULL for new assignment)"
    )
    new_entity_id = Column(
        String,
        ForeignKey("recognized_entities.id", ondelete="SET NULL"),
        nullable=True,
        doc="New entity assignment (NULL for unlink)"
    )
    action = Column(
        String(20),
        nullable=False,
        doc="Type of adjustment: unlink, assign, move, merge"
    )
    event_description = Column(
        Text,
        nullable=True,
        doc="Snapshot of event description at time of adjustment for ML training"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="When the adjustment was made"
    )

    __table_args__ = (
        Index("idx_entity_adjustments_event_id", "event_id"),
        Index("idx_entity_adjustments_old_entity_id", "old_entity_id"),
        Index("idx_entity_adjustments_action", "action"),
        Index("idx_entity_adjustments_created_at", "created_at"),
    )

    def __repr__(self):
        return (
            f"<EntityAdjustment(id={self.id[:8]}, action={self.action}, "
            f"event={self.event_id[:8]}, old={self.old_entity_id[:8] if self.old_entity_id else None}, "
            f"new={self.new_entity_id[:8] if self.new_entity_id else None})>"
        )
