"""Add structured identification JSON to events

The human-readable description stays in events.description. This column stores
the parsed identification object (object type, count, identity, action,
direction, package or carrier). Null for events analyzed before this change.

Revision ID: l9d322ae3e8b
Revises: k8c211fd2d7a
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa


revision = "l9d322ae3e8b"
down_revision = "k8c211fd2d7a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("identification", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "identification")
