"""Add entity_gallery_items and crop paths on face/vehicle observations

Per-object galleries for entity matching. ``entity_gallery_items`` holds
confirmed reference crops (SFace face embeddings, CLIP vehicle-crop
embeddings) owned by an entity, so references survive event retention and
are only changed by explicit enrollment. ``face_embeddings`` and
``vehicle_embeddings`` stay per-event observations and gain ``crop_path``
(plus ``dominant_color`` for vehicles) so a gallery can be built and
re-embedded later without full-resolution frames. All new columns are
nullable; existing rows are untouched.

Revision ID: m0a433bf4f9c
Revises: l9d322ae3e8b
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "m0a433bf4f9c"
down_revision = "l9d322ae3e8b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_gallery_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("crop_path", sa.String(length=512), nullable=True),
        sa.Column("dominant_color", sa.String(length=20), nullable=True),
        sa.Column("bounding_box", sa.Text(), nullable=True),
        sa.Column("source_event_id", sa.String(), nullable=True),
        sa.Column("source_observation_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["recognized_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "source_observation_id", name="uq_entity_gallery_observation"),
    )
    op.create_index("idx_entity_gallery_entity_kind", "entity_gallery_items", ["entity_id", "kind"])
    op.create_index("idx_entity_gallery_source_event", "entity_gallery_items", ["source_event_id"])

    op.add_column("face_embeddings", sa.Column("crop_path", sa.String(length=512), nullable=True))
    op.add_column("vehicle_embeddings", sa.Column("crop_path", sa.String(length=512), nullable=True))
    op.add_column("vehicle_embeddings", sa.Column("dominant_color", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("vehicle_embeddings") as batch:
        batch.drop_column("dominant_color")
        batch.drop_column("crop_path")
    with op.batch_alter_table("face_embeddings") as batch:
        batch.drop_column("crop_path")
    op.drop_index("idx_entity_gallery_source_event", table_name="entity_gallery_items")
    op.drop_index("idx_entity_gallery_entity_kind", table_name="entity_gallery_items")
    op.drop_table("entity_gallery_items")
