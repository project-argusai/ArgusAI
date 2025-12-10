"""Add reanalyzed_at and reanalysis_count fields to events table

Story P3-6.4: Add Re-Analyze Action for Low-Confidence Events

This migration adds:
- reanalyzed_at: Timestamp of last re-analysis (null = never re-analyzed)
- reanalysis_count: Number of re-analyses performed (for rate limiting, default 0)

Revision ID: 021_add_reanalysis_fields
Revises: 020_add_vague_reason
Create Date: 2025-12-09
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '021_add_reanalysis_fields'
down_revision = '020_add_vague_reason'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add reanalyzed_at column (nullable DateTime with timezone)
    op.add_column('events', sa.Column('reanalyzed_at', sa.DateTime(timezone=True), nullable=True))

    # Add reanalysis_count column (non-nullable Integer with default 0)
    op.add_column('events', sa.Column('reanalysis_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('events', 'reanalysis_count')
    op.drop_column('events', 'reanalyzed_at')
