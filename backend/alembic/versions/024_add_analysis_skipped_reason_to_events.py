"""Add analysis_skipped_reason to events

Story P3-7.3: Implement Daily/Monthly Cost Caps
Adds field to track when AI analysis is skipped due to cost cap.

Revision ID: 024
Revises: 023_add_ai_cost_to_events
Create Date: 2025-12-09
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '024_add_analysis_skipped_reason'
down_revision = '023_add_ai_cost'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add analysis_skipped_reason column to events table
    # Values: null (not skipped), "cost_cap_daily", "cost_cap_monthly"
    op.add_column('events', sa.Column('analysis_skipped_reason', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'analysis_skipped_reason')
