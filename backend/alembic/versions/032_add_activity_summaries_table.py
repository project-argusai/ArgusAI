"""add_activity_summaries_table

Story P4-4.1: Summary Generation Service

Adds activity_summaries table for storing generated activity summaries
for the Activity Summaries & Digests feature.

Revision ID: 032_add_activity_summaries
Revises: 031_add_camera_activity_patterns
Create Date: 2025-12-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '032_add_activity_summaries'
down_revision = '031_add_camera_activity_patterns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create activity_summaries table."""
    op.create_table(
        'activity_summaries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('event_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('camera_ids', sa.Text(), nullable=True),  # JSON array
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('ai_cost', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('provider_used', sa.String(length=50), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes for efficient date range lookups
    op.create_index('idx_activity_summaries_period_start', 'activity_summaries', ['period_start'])
    op.create_index('idx_activity_summaries_period_end', 'activity_summaries', ['period_end'])
    op.create_index('idx_activity_summaries_generated_at', 'activity_summaries', ['generated_at'])


def downgrade() -> None:
    """Drop activity_summaries table."""
    op.drop_index('idx_activity_summaries_generated_at', table_name='activity_summaries')
    op.drop_index('idx_activity_summaries_period_end', table_name='activity_summaries')
    op.drop_index('idx_activity_summaries_period_start', table_name='activity_summaries')
    op.drop_table('activity_summaries')
