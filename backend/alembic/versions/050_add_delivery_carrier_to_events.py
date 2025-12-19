"""Add delivery_carrier to events

Story P7-2.1: Add Carrier Detection to AI Analysis

Revision ID: 050_delivery_carrier
Revises: 049_add_camera_audio_settings
Create Date: 2025-12-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '050_delivery_carrier'
down_revision: Union[str, None] = '049_add_camera_audio_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add delivery_carrier column for carrier detection
    # Values: 'fedex', 'ups', 'usps', 'amazon', 'dhl' or NULL (not detected)
    op.add_column('events', sa.Column('delivery_carrier', sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'delivery_carrier')
