"""add_devices_table

Revision ID: d7a2e1c4f5b3
Revises: c941f8a3e7d2
Create Date: 2025-12-26 10:00:00.000000

Story P11-2.4: Implement Device Registration and Token Management
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7a2e1c4f5b3'
down_revision = 'c941f8a3e7d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create devices table for mobile push notification tokens."""
    op.create_table(
        'devices',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_id', sa.String(255), nullable=False, unique=True),
        sa.Column('platform', sa.String(20), nullable=False),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('push_token', sa.Text(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create indexes
    op.create_index('idx_devices_user', 'devices', ['user_id'])
    op.create_index('idx_devices_device_id', 'devices', ['device_id'])
    op.create_index('idx_devices_platform', 'devices', ['platform'])


def downgrade() -> None:
    """Drop devices table."""
    op.drop_index('idx_devices_platform', 'devices')
    op.drop_index('idx_devices_device_id', 'devices')
    op.drop_index('idx_devices_user', 'devices')
    op.drop_table('devices')
