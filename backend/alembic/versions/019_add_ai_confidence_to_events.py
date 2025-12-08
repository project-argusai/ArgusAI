"""add_ai_confidence_to_events

Revision ID: 019_add_ai_confidence
Revises: 018_add_audio_transcription
Create Date: 2025-12-08

Story P3-6.1: Add ai_confidence and low_confidence columns to events table
for storing AI self-reported confidence scores and flagging uncertain descriptions.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '019_add_ai_confidence'
down_revision = '018_add_audio_transcription'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Story P3-6.1: Add AI confidence scoring fields
    op.add_column('events', sa.Column('ai_confidence', sa.Integer(), nullable=True))
    op.add_column('events', sa.Column('low_confidence', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('events', 'low_confidence')
    op.drop_column('events', 'ai_confidence')
