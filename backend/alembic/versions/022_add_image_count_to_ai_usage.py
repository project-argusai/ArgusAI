"""Add image_count field to ai_usage table

Story P3-7.1: Implement Cost Tracking Service

This migration adds:
- image_count: Number of images in multi-image requests (for cost tracking)
- Index on (timestamp, provider) for aggregation queries

Revision ID: 022_add_image_count
Revises: 021_add_reanalysis_fields
Create Date: 2025-12-09
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '022_add_image_count'
down_revision = '021_add_reanalysis_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add image_count column (nullable Integer for multi-image tracking)
    op.add_column('ai_usage', sa.Column('image_count', sa.Integer(), nullable=True))

    # Add composite index for aggregation queries (timestamp, provider)
    # This supports efficient queries like: costs by date and provider
    op.create_index(
        'ix_ai_usage_timestamp_provider',
        'ai_usage',
        ['timestamp', 'provider'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_ai_usage_timestamp_provider', table_name='ai_usage')
    op.drop_column('ai_usage', 'image_count')
