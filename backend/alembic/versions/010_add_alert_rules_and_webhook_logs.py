"""Add alert_rules and webhook_logs tables for Epic 5 Alert Engine

Revision ID: 010
Revises: 009
Create Date: 2025-11-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    """Create alert_rules and webhook_logs tables, add alert_rule_ids to events"""

    # Create alert_rules table
    op.create_table(
        'alert_rules',
        sa.Column('id', sa.String(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('conditions', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('actions', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('cooldown_minutes', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trigger_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for alert_rules
    op.create_index('idx_alert_rules_is_enabled', 'alert_rules', ['is_enabled'], unique=False)
    op.create_index('idx_alert_rules_last_triggered', 'alert_rules', ['last_triggered_at'], unique=False)

    # Create webhook_logs table for audit trail
    op.create_table(
        'webhook_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('alert_rule_id', sa.String(), nullable=False),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('url', sa.String(2000), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('response_time_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for webhook_logs
    op.create_index('idx_webhook_logs_alert_rule', 'webhook_logs', ['alert_rule_id'], unique=False)
    op.create_index('idx_webhook_logs_event', 'webhook_logs', ['event_id'], unique=False)
    op.create_index('idx_webhook_logs_rule_event', 'webhook_logs', ['alert_rule_id', 'event_id'], unique=False)
    op.create_index('idx_webhook_logs_created', 'webhook_logs', ['created_at'], unique=False)

    # Add alert_rule_ids column to events table
    op.add_column('events', sa.Column('alert_rule_ids', sa.Text(), nullable=True))


def downgrade():
    """Drop alert_rules and webhook_logs tables, remove alert_rule_ids from events"""

    # Remove alert_rule_ids column from events
    op.drop_column('events', 'alert_rule_ids')

    # Drop webhook_logs indexes and table
    op.drop_index('idx_webhook_logs_created', 'webhook_logs')
    op.drop_index('idx_webhook_logs_rule_event', 'webhook_logs')
    op.drop_index('idx_webhook_logs_event', 'webhook_logs')
    op.drop_index('idx_webhook_logs_alert_rule', 'webhook_logs')
    op.drop_table('webhook_logs')

    # Drop alert_rules indexes and table
    op.drop_index('idx_alert_rules_last_triggered', 'alert_rules')
    op.drop_index('idx_alert_rules_is_enabled', 'alert_rules')
    op.drop_table('alert_rules')
