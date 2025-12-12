"""Add prompt_history table for tracking AI prompt evolution

Story P4-5.4: Feedback-Informed Prompts

Revision ID: 037_add_prompt_history_table
Revises: 036_add_camera_id_to_feedback
Create Date: 2025-12-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '037_add_prompt_history_table'
down_revision = '036_add_camera_id_to_feedback'
branch_labels = None
depends_on = None


def upgrade():
    """Create prompt_history table for tracking AI prompt evolution."""
    op.create_table(
        'prompt_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('prompt_version', sa.Integer(), nullable=False),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),  # 'manual', 'suggestion', 'ab_test'
        sa.Column('applied_suggestions', sa.Text(), nullable=True),  # JSON array of suggestion IDs
        sa.Column('accuracy_before', sa.Float(), nullable=True),
        sa.Column('accuracy_after', sa.Float(), nullable=True),
        sa.Column('camera_id', sa.String(), sa.ForeignKey('cameras.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    # Index for quick lookup by camera
    op.create_index(
        'ix_prompt_history_camera_id',
        'prompt_history',
        ['camera_id']
    )

    # Index for version ordering
    op.create_index(
        'ix_prompt_history_version',
        'prompt_history',
        ['prompt_version']
    )


def downgrade():
    """Remove prompt_history table."""
    op.drop_index('ix_prompt_history_version', table_name='prompt_history')
    op.drop_index('ix_prompt_history_camera_id', table_name='prompt_history')
    op.drop_table('prompt_history')
