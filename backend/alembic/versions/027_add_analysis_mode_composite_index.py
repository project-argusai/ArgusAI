"""Add composite index for analysis_mode filtering (Story P3-7.6)

Adds composite index on (analysis_mode, timestamp) for efficient queries
when filtering events by analysis mode and sorting by timestamp.

Revision ID: 027_add_analysis_mode_index
Revises: 026_add_key_frames
Create Date: 2025-12-10
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '027_add_analysis_mode_index'
down_revision = '026_add_key_frames'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add composite index on (analysis_mode, timestamp) for efficient filtered queries
    # This optimizes queries like: WHERE analysis_mode = 'multi_frame' ORDER BY timestamp DESC
    op.create_index(
        'idx_events_analysis_mode_timestamp',
        'events',
        ['analysis_mode', 'timestamp'],
        unique=False
    )

    # Add index on low_confidence for filtering uncertain descriptions
    op.create_index(
        'idx_events_low_confidence',
        'events',
        ['low_confidence'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_events_low_confidence', table_name='events')
    op.drop_index('idx_events_analysis_mode_timestamp', table_name='events')
