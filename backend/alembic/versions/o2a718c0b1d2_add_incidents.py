"""Add incidents (combined result per multi-camera correlation group)

New table only. Existing event rows and per-camera descriptions are unchanged.

Revision ID: o2a718c0b1d2
Revises: n1b544c05a1d
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa


revision = "o2a718c0b1d2"
down_revision = "n1b544c05a1d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("combined_description", sa.Text(), nullable=True),
        sa.Column("combined_identification", sa.Text(), nullable=True),
        sa.Column("matched_entity_ids", sa.Text(), nullable=True),
        sa.Column("primary_event_id", sa.String(), nullable=True),
        sa.Column("notified_event_id", sa.String(), nullable=True),
        sa.Column("update_pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_used", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["primary_event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_incidents_status", "incidents", ["status"])


def downgrade() -> None:
    op.drop_index("idx_incidents_status", table_name="incidents")
    op.drop_table("incidents")
