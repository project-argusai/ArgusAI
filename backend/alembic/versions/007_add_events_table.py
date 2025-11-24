"""Add events table for AI-generated semantic events

Revision ID: 007
Revises: 006
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    """Create events table for AI-enriched motion events"""
    op.create_table(
        'events',
        sa.Column('id', sa.String(), primary_key=True, nullable=False),
        sa.Column('camera_id', sa.String(), sa.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=False),
        sa.Column('objects_detected', sa.Text(), nullable=False),  # JSON array
        sa.Column('thumbnail_path', sa.String(500), nullable=True),
        sa.Column('thumbnail_base64', sa.Text(), nullable=True),
        sa.Column('alert_triggered', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('confidence >= 0 AND confidence <= 100', name='check_confidence_range')
    )

    # Create indexes for query performance
    op.create_index('idx_events_timestamp_desc', 'events', ['timestamp'], unique=False)
    op.create_index('idx_events_camera', 'events', ['camera_id'], unique=False)
    op.create_index('idx_events_camera_timestamp', 'events', ['camera_id', 'timestamp'], unique=False)


def downgrade():
    """Drop events table"""
    op.drop_index('idx_events_camera_timestamp', 'events')
    op.drop_index('idx_events_camera', 'events')
    op.drop_index('idx_events_timestamp_desc', 'events')
    op.drop_table('events')
