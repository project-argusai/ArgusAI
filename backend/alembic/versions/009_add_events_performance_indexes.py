"""Add performance indexes for events filtering

Revision ID: 009
Revises: 008
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    """Add indexes for common filtering patterns"""

    # Index for confidence filtering (min_confidence queries)
    op.create_index('idx_events_confidence', 'events', ['confidence'], unique=False)

    # Index for alert filtering
    op.create_index('idx_events_alert_triggered', 'events', ['alert_triggered'], unique=False)

    # Composite index for alert + timestamp (common pattern: recent alerts)
    op.create_index('idx_events_alert_timestamp', 'events', ['alert_triggered', 'timestamp'], unique=False)


def downgrade():
    """Drop performance indexes"""
    op.drop_index('idx_events_alert_timestamp', 'events')
    op.drop_index('idx_events_alert_triggered', 'events')
    op.drop_index('idx_events_confidence', 'events')
