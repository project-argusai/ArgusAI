"""Add delivery_status to activity_summaries table

Revision ID: 034_add_delivery_status
Revises: 033_add_digest_type_to_activity_summaries
Create Date: 2025-12-12

Story P4-4.3: Digest Delivery
AC11: Delivery status tracked and returned via GET /api/v1/digests/{id}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '034_add_delivery_status'
down_revision: Union[str, None] = '033_add_digest_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add delivery_status column to activity_summaries table."""
    op.add_column(
        'activity_summaries',
        sa.Column(
            'delivery_status',
            sa.Text(),
            nullable=True,
            comment='JSON object with delivery status per channel'
        )
    )


def downgrade() -> None:
    """Remove delivery_status column from activity_summaries table."""
    op.drop_column('activity_summaries', 'delivery_status')
