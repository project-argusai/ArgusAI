"""Add ai_usage table for tracking AI API usage

Revision ID: 006
Revises: 005
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    """Create ai_usage table for tracking API calls, tokens, and costs"""
    op.create_table(
        'ai_usage',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('provider', sa.String(50), nullable=False, index=True),
        sa.Column('success', sa.Boolean(), nullable=False, index=True),
        sa.Column('tokens_used', sa.Integer(), nullable=False, default=0),
        sa.Column('response_time_ms', sa.Integer(), nullable=False, default=0),
        sa.Column('cost_estimate', sa.Float(), nullable=False, default=0.0),
        sa.Column('error', sa.String(500), nullable=True)
    )

    # Create indexes for common query patterns
    op.create_index('idx_ai_usage_timestamp_provider', 'ai_usage', ['timestamp', 'provider'])
    op.create_index('idx_ai_usage_success_provider', 'ai_usage', ['success', 'provider'])


def downgrade():
    """Drop ai_usage table"""
    op.drop_index('idx_ai_usage_success_provider', 'ai_usage')
    op.drop_index('idx_ai_usage_timestamp_provider', 'ai_usage')
    op.drop_table('ai_usage')
