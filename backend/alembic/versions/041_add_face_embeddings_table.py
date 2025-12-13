"""Add face_embeddings table (Story P4-8.1)

Revision ID: 041_add_face_embeddings
Revises: 040_add_anomaly_score_to_events
Create Date: 2025-12-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '041_add_face_embeddings'
down_revision = '040_add_anomaly_score_to_events'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create face_embeddings table for person recognition (Story P4-8.1)."""
    op.create_table(
        'face_embeddings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=True),
        sa.Column('embedding', sa.Text(), nullable=False),
        sa.Column('bounding_box', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('model_version', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['recognized_entities.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes for efficient querying
    op.create_index('idx_face_embeddings_event_id', 'face_embeddings', ['event_id'])
    op.create_index('idx_face_embeddings_entity_id', 'face_embeddings', ['entity_id'])
    op.create_index('idx_face_embeddings_model_version', 'face_embeddings', ['model_version'])


def downgrade() -> None:
    """Drop face_embeddings table."""
    op.drop_index('idx_face_embeddings_model_version', table_name='face_embeddings')
    op.drop_index('idx_face_embeddings_entity_id', table_name='face_embeddings')
    op.drop_index('idx_face_embeddings_event_id', table_name='face_embeddings')
    op.drop_table('face_embeddings')
