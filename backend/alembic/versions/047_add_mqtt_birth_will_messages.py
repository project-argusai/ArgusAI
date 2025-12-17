"""Add availability_topic, birth_message, will_message to mqtt_config (P5-6.2)

Revision ID: 047_add_mqtt_birth_will_messages
Revises: 046_add_mqtt_message_expiry
Create Date: 2025-12-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '047_add_mqtt_birth_will_messages'
down_revision = '046_add_mqtt_message_expiry'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add birth/will message columns to mqtt_config table."""
    # Add availability_topic - defaults to empty string, service will fallback to {topic_prefix}/status
    op.add_column(
        'mqtt_config',
        sa.Column('availability_topic', sa.String(255), nullable=False, server_default='')
    )

    # Add birth_message - defaults to "online"
    op.add_column(
        'mqtt_config',
        sa.Column('birth_message', sa.String(100), nullable=False, server_default='online')
    )

    # Add will_message - defaults to "offline"
    op.add_column(
        'mqtt_config',
        sa.Column('will_message', sa.String(100), nullable=False, server_default='offline')
    )


def downgrade() -> None:
    """Remove birth/will message columns from mqtt_config table."""
    op.drop_column('mqtt_config', 'will_message')
    op.drop_column('mqtt_config', 'birth_message')
    op.drop_column('mqtt_config', 'availability_topic')
