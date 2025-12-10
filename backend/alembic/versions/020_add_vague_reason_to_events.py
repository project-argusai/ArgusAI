"""add_vague_reason_to_events

Revision ID: 020_add_vague_reason
Revises: 019_add_ai_confidence
Create Date: 2025-12-08

Story P3-6.2: Add vague_reason column to events table for storing
human-readable explanations of why descriptions were flagged as vague.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '020_add_vague_reason'
down_revision = '019_add_ai_confidence'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Story P3-6.2 AC4: Track vagueness reason
    op.add_column('events', sa.Column('vague_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'vague_reason')
