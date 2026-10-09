"""Add entity_plates (keyed licence-plate hashes for known vehicles)

Stores HMAC-SHA256 hashes of plates on saved vehicle entities only; there is
no plain-text plate column. Plates read on events that match no saved
vehicle are never stored. New table only; nothing existing changes.

Revision ID: n1b544c05a1d
Revises: m0a433bf4f9c
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "n1b544c05a1d"
down_revision = "m0a433bf4f9c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_plates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("plate_hash", sa.String(length=64), nullable=False),
        sa.Column("hash_version", sa.String(length=32), nullable=False),
        sa.Column("key_id", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_event_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["recognized_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "plate_hash", name="uq_entity_plate_hash"),
    )
    op.create_index("idx_entity_plates_hash", "entity_plates", ["plate_hash"])
    op.create_index("idx_entity_plates_source_event", "entity_plates", ["source_event_id"])


def downgrade() -> None:
    op.drop_index("idx_entity_plates_source_event", table_name="entity_plates")
    op.drop_index("idx_entity_plates_hash", table_name="entity_plates")
    op.drop_table("entity_plates")
