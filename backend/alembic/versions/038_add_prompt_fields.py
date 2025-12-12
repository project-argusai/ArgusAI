"""Add camera_prompt_override to cameras and prompt_variant to events

Story P4-5.4: Feedback-Informed Prompts

Revision ID: 038_add_prompt_fields
Revises: 037_add_prompt_history_table
Create Date: 2025-12-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '038_add_prompt_fields'
down_revision = '037_add_prompt_history_table'
branch_labels = None
depends_on = None


def upgrade():
    """Add camera_prompt_override to cameras and prompt_variant to events."""
    # Add camera_prompt_override column to cameras table
    # Allows per-camera custom prompts based on feedback analysis
    op.add_column(
        'cameras',
        sa.Column('prompt_override', sa.Text(), nullable=True)
    )

    # Add prompt_variant column to events table for A/B testing
    # Values: 'control', 'experiment', or NULL if no A/B test active
    op.add_column(
        'events',
        sa.Column('prompt_variant', sa.String(20), nullable=True)
    )

    # Index for filtering events by prompt variant (A/B test analysis)
    op.create_index(
        'ix_events_prompt_variant',
        'events',
        ['prompt_variant']
    )


def downgrade():
    """Remove prompt-related fields."""
    op.drop_index('ix_events_prompt_variant', table_name='events')
    op.drop_column('events', 'prompt_variant')
    op.drop_column('cameras', 'prompt_override')
