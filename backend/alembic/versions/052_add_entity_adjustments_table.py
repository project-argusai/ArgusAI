"""add_entity_adjustments_table

Story P9-4.3: Implement Event-Entity Unlinking

Create entity_adjustments table to track manual entity-event corrections
for future ML training. Records unlink, assign, move, and merge operations.

Revision ID: 052_entity_adjustments
Revises: 7a41a23f2156
Create Date: 2025-12-22 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '052_entity_adjustments'
down_revision = '7a41a23f2156'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create entity_adjustments table
    op.create_table(
        'entity_adjustments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('old_entity_id', sa.String(), nullable=True),
        sa.Column('new_entity_id', sa.String(), nullable=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('event_description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['old_entity_id'], ['recognized_entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['new_entity_id'], ['recognized_entities.id'], ondelete='SET NULL'),
    )
    # Create indexes for efficient lookups
    op.create_index('idx_entity_adjustments_event_id', 'entity_adjustments', ['event_id'])
    op.create_index('idx_entity_adjustments_old_entity_id', 'entity_adjustments', ['old_entity_id'])
    op.create_index('idx_entity_adjustments_action', 'entity_adjustments', ['action'])
    op.create_index('idx_entity_adjustments_created_at', 'entity_adjustments', ['created_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_entity_adjustments_created_at', table_name='entity_adjustments')
    op.drop_index('idx_entity_adjustments_action', table_name='entity_adjustments')
    op.drop_index('idx_entity_adjustments_old_entity_id', table_name='entity_adjustments')
    op.drop_index('idx_entity_adjustments_event_id', table_name='entity_adjustments')
    # Drop table
    op.drop_table('entity_adjustments')
