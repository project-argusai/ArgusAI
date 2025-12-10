"""Add ai_cost field to events table

Story P3-7.1: Implement Cost Tracking Service

This migration adds:
- ai_cost: Estimated cost in USD for AI analysis (nullable Float)

Revision ID: 023_add_ai_cost
Revises: 022_add_image_count
Create Date: 2025-12-09
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '023_add_ai_cost'
down_revision = '022_add_image_count'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ai_cost column (nullable Float for cost in USD)
    op.add_column('events', sa.Column('ai_cost', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'ai_cost')
