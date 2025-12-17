"""Add message_expiry_seconds to mqtt_config for MQTT 5.0 support (P5-6.1)

Revision ID: 046_add_mqtt_message_expiry
Revises: 045_add_homekit_setup_id
Create Date: 2025-12-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '046_add_mqtt_message_expiry'
down_revision = '045_add_homekit_setup_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add message_expiry_seconds column to mqtt_config table."""
    op.add_column(
        'mqtt_config',
        sa.Column('message_expiry_seconds', sa.Integer(), nullable=False, server_default='300')
    )


def downgrade() -> None:
    """Remove message_expiry_seconds column from mqtt_config table."""
    op.drop_column('mqtt_config', 'message_expiry_seconds')
