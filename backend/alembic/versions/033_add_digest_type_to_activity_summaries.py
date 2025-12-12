"""add_digest_type_to_activity_summaries

Story P4-4.2: Daily Digest Scheduler

Adds digest_type column to activity_summaries table to distinguish
between on-demand summaries and scheduled digests.

Revision ID: 033_add_digest_type
Revises: 032_add_activity_summaries
Create Date: 2025-12-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '033_add_digest_type'
down_revision = '032_add_activity_summaries'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add digest_type column to activity_summaries table."""
    op.add_column(
        'activity_summaries',
        sa.Column('digest_type', sa.String(length=20), nullable=True)
    )

    # Create index for efficient digest type queries
    op.create_index(
        'idx_activity_summaries_digest_type',
        'activity_summaries',
        ['digest_type']
    )


def downgrade() -> None:
    """Remove digest_type column from activity_summaries table."""
    op.drop_index('idx_activity_summaries_digest_type', table_name='activity_summaries')
    op.drop_column('activity_summaries', 'digest_type')
