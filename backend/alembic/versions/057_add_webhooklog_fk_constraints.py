"""add_webhooklog_fk_constraints

Revision ID: 057
Revises: 056
Create Date: 2025-12-29 10:30:00.000000

Story P14-2.2: Add Missing Foreign Key Constraint
- Add FK constraint from WebhookLog.alert_rule_id to AlertRule.id
- Add FK constraint from WebhookLog.event_id to Event.id
- Both with CASCADE delete to automatically clean up orphans
- First cleans up any existing orphaned records
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '057'
down_revision = '056'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add foreign key constraints to webhook_logs table."""
    # First, clean up any orphaned records that would violate FK constraints
    # This handles existing data integrity issues before adding constraints
    op.execute("""
        DELETE FROM webhook_logs
        WHERE alert_rule_id NOT IN (SELECT id FROM alert_rules)
    """)
    op.execute("""
        DELETE FROM webhook_logs
        WHERE event_id NOT IN (SELECT id FROM events)
    """)

    # SQLite requires batch mode for schema changes on existing tables
    with op.batch_alter_table('webhook_logs', schema=None) as batch_op:
        # Add foreign key constraint to alert_rules table
        batch_op.create_foreign_key(
            'fk_webhook_logs_alert_rule',
            'alert_rules',
            ['alert_rule_id'],
            ['id'],
            ondelete='CASCADE'
        )
        # Add foreign key constraint to events table
        batch_op.create_foreign_key(
            'fk_webhook_logs_event',
            'events',
            ['event_id'],
            ['id'],
            ondelete='CASCADE'
        )


def downgrade() -> None:
    """Remove foreign key constraints from webhook_logs table."""
    with op.batch_alter_table('webhook_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_webhook_logs_alert_rule', type_='foreignkey')
        batch_op.drop_constraint('fk_webhook_logs_event', type_='foreignkey')
