"""Add incident_deliveries (one notification per incident dedup claims)

New table only. Unique (group_key, channel) is the atomic claim.

Revision ID: p3b719d1c2e3
Revises: o2a718c0b1d2
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa


revision = "p3b719d1c2e3"
down_revision = "o2a718c0b1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_key", sa.String(), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_key", "channel", name="uq_incident_delivery"),
    )
    op.create_index("ix_incident_deliveries_group_key", "incident_deliveries", ["group_key"])


def downgrade() -> None:
    op.drop_index("ix_incident_deliveries_group_key", table_name="incident_deliveries")
    op.drop_table("incident_deliveries")
