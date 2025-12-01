"""Add source_type, protect_event_id, smart_detection_type to events table (Story P2-3.3)

Revision ID: 013
Revises: 012
Create Date: 2025-12-01

Phase 2: UniFi Protect event integration fields
- source_type: Identifies event source ('rtsp', 'usb', 'protect'), defaults to 'rtsp' for backward compatibility
- protect_event_id: Stores Protect's native event ID for correlation
- smart_detection_type: Stores Protect smart detection type (person/vehicle/package/animal/motion)

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    """Add Phase 2 Protect event fields to events table"""

    # Add source_type column with default 'rtsp' for backward compatibility
    op.add_column(
        'events',
        sa.Column('source_type', sa.String(20), nullable=False, server_default='rtsp')
    )

    # Add protect_event_id column (nullable, only populated for Protect events)
    op.add_column(
        'events',
        sa.Column('protect_event_id', sa.String(100), nullable=True)
    )

    # Add smart_detection_type column (nullable, only populated for Protect events)
    op.add_column(
        'events',
        sa.Column('smart_detection_type', sa.String(20), nullable=True)
    )

    # Add index on source_type for filtering by event source
    op.create_index('idx_events_source_type', 'events', ['source_type'])

    # Add index on protect_event_id for correlation lookups
    op.create_index('idx_events_protect_event_id', 'events', ['protect_event_id'])


def downgrade():
    """Remove Phase 2 Protect event fields from events table"""

    # Drop indexes first
    op.drop_index('idx_events_protect_event_id', table_name='events')
    op.drop_index('idx_events_source_type', table_name='events')

    # Drop columns
    op.drop_column('events', 'smart_detection_type')
    op.drop_column('events', 'protect_event_id')
    op.drop_column('events', 'source_type')
