"""Add description_retry_needed to events

Story P2-6.3: Phase 2 Error Handling
AC13: All AI providers down stores event without description, flags for retry

Revision ID: 016_retry_flag
Revises: 015_provider_used
Create Date: 2025-12-05

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '016_retry_flag'
down_revision = '015_provider_used'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add description_retry_needed column to events table"""
    # Add description_retry_needed column with default False
    # Note: SQLite doesn't support ALTER COLUMN, so we keep server_default
    # for SQLite compatibility. The ORM handles defaults for new rows.
    op.add_column(
        'events',
        sa.Column('description_retry_needed', sa.Boolean(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    """Remove description_retry_needed column from events table"""
    op.drop_column('events', 'description_retry_needed')
