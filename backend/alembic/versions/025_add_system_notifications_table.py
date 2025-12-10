"""Add system_notifications table for cost alerts

Story P3-7.4: Add Cost Alerts and Notifications

Revision ID: 025
Revises: 024
Create Date: 2025-12-10

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '025_add_system_notifications'
down_revision = '024_add_analysis_skipped_reason'
branch_labels = None
depends_on = None


def upgrade():
    """Create system_notifications table for application-level alerts."""
    op.create_table(
        'system_notifications',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='info'),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('action_url', sa.String(500), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('read', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('dismissed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for common queries
    op.create_index('idx_system_notifications_type', 'system_notifications', ['notification_type'])
    op.create_index('idx_system_notifications_read', 'system_notifications', ['read'])
    op.create_index('idx_system_notifications_created', 'system_notifications', ['created_at'])
    op.create_index('idx_system_notifications_severity', 'system_notifications', ['severity'])


def downgrade():
    """Drop system_notifications table."""
    op.drop_index('idx_system_notifications_severity', 'system_notifications')
    op.drop_index('idx_system_notifications_created', 'system_notifications')
    op.drop_index('idx_system_notifications_read', 'system_notifications')
    op.drop_index('idx_system_notifications_type', 'system_notifications')
    op.drop_table('system_notifications')
