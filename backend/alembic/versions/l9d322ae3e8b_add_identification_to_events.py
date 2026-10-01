"""Add identification JSON and Protect detection timing to events

The human-readable description stays in events.description. ``identification``
stores the parsed identification object. ``detection_start``, ``detection_end``,
``detection_peak``, and ``subject_box`` store Protect smart-detect timing and
the subject rectangle so a later reanalysis can sample the real window. All
five columns are nullable. Events analyzed before this change stay null.

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
    op.add_column("events", sa.Column("detection_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("detection_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("detection_peak", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("subject_box", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "subject_box")
    op.drop_column("events", "detection_peak")
    op.drop_column("events", "detection_end")
    op.drop_column("events", "detection_start")
    op.drop_column("events", "identification")
