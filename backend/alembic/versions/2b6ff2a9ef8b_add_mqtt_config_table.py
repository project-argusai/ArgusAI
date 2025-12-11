"""add_mqtt_config_table

Revision ID: 2b6ff2a9ef8b
Revises: 028_add_notification_prefs
Create Date: 2025-12-10 17:44:52.668689

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2b6ff2a9ef8b'
down_revision = '028_add_notification_prefs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('mqtt_config',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('broker_host', sa.String(length=255), nullable=False),
    sa.Column('broker_port', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=100), nullable=True),
    sa.Column('password', sa.String(length=500), nullable=True),
    sa.Column('topic_prefix', sa.String(length=100), nullable=False),
    sa.Column('discovery_prefix', sa.String(length=100), nullable=False),
    sa.Column('discovery_enabled', sa.Boolean(), nullable=False),
    sa.Column('qos', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('retain_messages', sa.Boolean(), nullable=False),
    sa.Column('use_tls', sa.Boolean(), nullable=False),
    sa.Column('is_connected', sa.Boolean(), nullable=False),
    sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('messages_published', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('mqtt_config')
