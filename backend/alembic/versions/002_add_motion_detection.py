"""Add motion detection fields and events table

Revision ID: 002
Revises: 001
Create Date: 2025-11-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add motion detection configuration fields to cameras and create motion_events table"""

    # Add motion configuration fields to cameras table (if they don't exist)
    # Note: SQLite doesn't support adding check constraints to existing tables
    # Validation will be enforced at application level via Pydantic

    # Check if columns already exist (from partial migration run)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('cameras')]

    if 'motion_enabled' not in columns:
        op.add_column('cameras', sa.Column('motion_enabled', sa.Boolean(), nullable=False, server_default='true'))
    if 'motion_algorithm' not in columns:
        op.add_column('cameras', sa.Column('motion_algorithm', sa.String(length=20), nullable=False, server_default='mog2'))

    # Create motion_events table
    op.create_table(
        'motion_events',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('camera_id', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('motion_intensity', sa.Float(), nullable=True),
        sa.Column('algorithm_used', sa.String(length=20), nullable=False),
        sa.Column('bounding_box', sa.Text(), nullable=True),  # JSON string
        sa.Column('frame_thumbnail', sa.Text(), nullable=True),  # Base64 JPEG
        sa.Column('ai_event_id', sa.String(), nullable=True),  # Foreign key for F3
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
        sa.CheckConstraint('confidence >= 0.0 AND confidence <= 1.0', name='check_confidence_range'),
    )

    # Create indexes for performance
    op.create_index('idx_motion_events_camera_id', 'motion_events', ['camera_id'])
    op.create_index('idx_motion_events_timestamp', 'motion_events', ['timestamp'])
    op.create_index('idx_motion_events_camera_timestamp', 'motion_events', ['camera_id', 'timestamp'])


def downgrade() -> None:
    """Remove motion detection fields and events table"""

    # Drop indexes
    op.drop_index('idx_motion_events_camera_timestamp', table_name='motion_events')
    op.drop_index('idx_motion_events_timestamp', table_name='motion_events')
    op.drop_index('idx_motion_events_camera_id', table_name='motion_events')

    # Drop motion_events table
    op.drop_table('motion_events')

    # Drop motion fields from cameras table
    op.drop_column('cameras', 'motion_algorithm')
    op.drop_column('cameras', 'motion_enabled')
