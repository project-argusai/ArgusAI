"""add_summary_feedback_table

Revision ID: 19df889882ef
Revises: b875e9bd8602
Create Date: 2025-12-22 16:11:28.045294

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '19df889882ef'
down_revision = 'b875e9bd8602'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create summary_feedback table for Story P9-3.4"""
    op.create_table(
        'summary_feedback',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('summary_id', sa.String(), nullable=False),
        sa.Column('rating', sa.String(20), nullable=False),
        sa.Column('correction_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['summary_id'], ['activity_summaries.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('summary_id', name='uq_summary_feedback_summary_id')
    )
    op.create_index('ix_summary_feedback_summary_id', 'summary_feedback', ['summary_id'], unique=True)


def downgrade() -> None:
    """Drop summary_feedback table"""
    op.drop_index('ix_summary_feedback_summary_id', table_name='summary_feedback')
    op.drop_table('summary_feedback')
