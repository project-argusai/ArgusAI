"""add_audio_fields_to_camera

Revision ID: 817c9e3ec7f6
Revises: 047_add_mqtt_birth_will_messages
Create Date: 2025-12-17 10:19:17.801976

Story: P6-3.1 - Add Audio Stream Extraction from RTSP
Adds audio_enabled and audio_codec fields to cameras table for
optional audio stream extraction from RTSP cameras.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '817c9e3ec7f6'
down_revision = '047_add_mqtt_birth_will_messages'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add audio configuration fields to cameras table
    # audio_enabled: Boolean flag to enable/disable audio extraction per camera
    # audio_codec: Detected codec type ('aac', 'pcmu', 'opus', etc.)
    op.add_column('cameras', sa.Column('audio_enabled', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('cameras', sa.Column('audio_codec', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('cameras', 'audio_codec')
    op.drop_column('cameras', 'audio_enabled')
