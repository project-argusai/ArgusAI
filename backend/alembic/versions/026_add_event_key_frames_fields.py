"""Add key_frames_base64 and frame_timestamps to events

Story P3-7.5: Display Key Frames Gallery on Event Detail
Adds fields to store key frames used for AI analysis for gallery display.

Revision ID: 026
Revises: 025
Create Date: 2025-12-10

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '026_add_key_frames'
down_revision = '025_add_system_notifications'
branch_labels = None
depends_on = None


def upgrade():
    """Add key_frames_base64 and frame_timestamps columns to events table."""
    # key_frames_base64: JSON array of base64-encoded frame thumbnails
    op.add_column('events', sa.Column('key_frames_base64', sa.Text(), nullable=True))
    # frame_timestamps: JSON array of float seconds from video start
    op.add_column('events', sa.Column('frame_timestamps', sa.Text(), nullable=True))


def downgrade():
    """Remove key frames fields from events table."""
    op.drop_column('events', 'frame_timestamps')
    op.drop_column('events', 'key_frames_base64')
