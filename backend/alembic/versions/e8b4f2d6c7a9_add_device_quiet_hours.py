"""add_device_quiet_hours

Revision ID: e8b4f2d6c7a9
Revises: d7a2e1c4f5b3
Create Date: 2025-12-26 12:00:00.000000

Story P11-2.5: Add Mobile Push Preferences (Quiet Hours)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8b4f2d6c7a9'
down_revision = 'd7a2e1c4f5b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add quiet hours columns to devices table."""
    # Add quiet hours configuration columns
    op.add_column('devices', sa.Column('quiet_hours_enabled', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('devices', sa.Column('quiet_hours_start', sa.String(5), nullable=True))
    op.add_column('devices', sa.Column('quiet_hours_end', sa.String(5), nullable=True))
    op.add_column('devices', sa.Column('quiet_hours_timezone', sa.String(64), nullable=False, server_default='UTC'))
    op.add_column('devices', sa.Column('quiet_hours_override_critical', sa.Boolean(), nullable=False, server_default='1'))


def downgrade() -> None:
    """Remove quiet hours columns from devices table."""
    op.drop_column('devices', 'quiet_hours_override_critical')
    op.drop_column('devices', 'quiet_hours_timezone')
    op.drop_column('devices', 'quiet_hours_end')
    op.drop_column('devices', 'quiet_hours_start')
    op.drop_column('devices', 'quiet_hours_enabled')
