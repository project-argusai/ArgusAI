"""add_audio_transcription_to_events

Revision ID: 018_add_audio_transcription
Revises: 2d5158847bc1
Create Date: 2025-12-08

Story P3-5.3: Add audio_transcription column to events table for storing
transcribed speech from doorbell camera audio.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '018_add_audio_transcription'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Story P3-5.3: Add audio_transcription column for doorbell speech transcription
    op.add_column('events', sa.Column('audio_transcription', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'audio_transcription')
