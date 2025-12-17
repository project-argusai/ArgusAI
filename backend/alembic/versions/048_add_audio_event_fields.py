"""add_audio_event_fields_to_events

Revision ID: 048_add_audio_event_fields
Revises: 817c9e3ec7f6
Create Date: 2025-12-17

Story: P6-3.2 - Implement Audio Event Detection Pipeline
Adds audio_event_type, audio_confidence, and audio_duration_ms fields
to events table for storing detected audio events.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '048_add_audio_event_fields'
down_revision = '817c9e3ec7f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add audio event detection fields to events table
    # audio_event_type: Type of detected audio event (glass_break, gunshot, scream, doorbell, other)
    # audio_confidence: Confidence score (0.0-1.0) for the audio detection
    # audio_duration_ms: Duration of the audio event in milliseconds
    op.add_column('events', sa.Column('audio_event_type', sa.String(length=30), nullable=True))
    op.add_column('events', sa.Column('audio_confidence', sa.Float(), nullable=True))
    op.add_column('events', sa.Column('audio_duration_ms', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'audio_duration_ms')
    op.drop_column('events', 'audio_confidence')
    op.drop_column('events', 'audio_event_type')
