"""add_event_embeddings_table

Story P4-3.1: Event Embedding Generation

Adds event_embeddings table for storing CLIP ViT-B/32 image embeddings
to enable similarity search and recurring visitor detection.

Revision ID: 029_add_event_embeddings
Revises: 2b6ff2a9ef8b
Create Date: 2025-12-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '029_add_event_embeddings'
down_revision = '2b6ff2a9ef8b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create event_embeddings table for storing CLIP embeddings."""
    op.create_table(
        'event_embeddings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('event_id', sa.String(length=36), nullable=False),
        sa.Column('embedding', sa.Text(), nullable=False),  # JSON array of 512 floats
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', name='uq_event_embeddings_event_id'),
    )

    # Create indexes for efficient queries
    op.create_index('idx_event_embeddings_event_id', 'event_embeddings', ['event_id'])
    op.create_index('idx_event_embeddings_model_version', 'event_embeddings', ['model_version'])


def downgrade() -> None:
    """Drop event_embeddings table."""
    op.drop_index('idx_event_embeddings_model_version', table_name='event_embeddings')
    op.drop_index('idx_event_embeddings_event_id', table_name='event_embeddings')
    op.drop_table('event_embeddings')
