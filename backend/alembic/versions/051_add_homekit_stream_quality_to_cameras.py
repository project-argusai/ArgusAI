"""Add homekit_stream_quality to cameras

Story P7-3.1: Verify RTSP-to-SRTP Streaming Works

Adds stream quality configuration for HomeKit camera streaming.
Quality options: 'low' (480p), 'medium' (720p), 'high' (1080p)

Revision ID: 051_homekit_stream_quality
Revises: 050_delivery_carrier
Create Date: 2025-12-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '051_homekit_stream_quality'
down_revision: Union[str, None] = '050_delivery_carrier'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add homekit_stream_quality column with default 'medium'
    # Values: 'low', 'medium', 'high'
    op.add_column(
        'cameras',
        sa.Column(
            'homekit_stream_quality',
            sa.String(20),
            nullable=False,
            server_default='medium'
        )
    )


def downgrade() -> None:
    op.drop_column('cameras', 'homekit_stream_quality')
