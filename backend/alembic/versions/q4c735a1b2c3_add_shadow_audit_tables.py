"""Add shadow_results and shadow_daily_summary (#735, cloud-audit tables)

New tables only. shadow_results.event_id cascades on event delete.

Revision ID: q4c735a1b2c3
Revises: p3b719d1c2e3
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa


revision = "q4c735a1b2c3"
down_revision = "p3b719d1c2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shadow_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("local_result", sa.Text(), nullable=True),
        sa.Column("cloud_result", sa.Text(), nullable=True),
        sa.Column("local_provider", sa.String(length=32), nullable=True),
        sa.Column("cloud_provider", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="complete"),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("verdict", sa.String(length=16), nullable=True),
        sa.Column("verdict_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
        sa.CheckConstraint("source IN ('audit', 'fallback')", name="ck_shadow_results_source"),
        sa.CheckConstraint("status IN ('claimed', 'complete', 'failed')",
                           name="ck_shadow_results_status"),
        sa.CheckConstraint("verdict IS NULL OR verdict IN ('agree', 'disagree', 'unsure')",
                           name="ck_shadow_results_verdict"),
    )
    op.create_index("idx_shadow_results_created_at", "shadow_results", ["created_at"])
    op.create_index("idx_shadow_results_source_created", "shadow_results", ["source", "created_at"])
    op.create_table(
        "shadow_daily_summary",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("metrics", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day", "source", name="uq_shadow_daily_summary_day_source"),
    )
    op.create_index("ix_shadow_daily_summary_day", "shadow_daily_summary", ["day"])


def downgrade() -> None:
    op.drop_index("ix_shadow_daily_summary_day", table_name="shadow_daily_summary")
    op.drop_table("shadow_daily_summary")
    op.drop_index("idx_shadow_results_source_created", table_name="shadow_results")
    op.drop_index("idx_shadow_results_created_at", table_name="shadow_results")
    op.drop_table("shadow_results")
