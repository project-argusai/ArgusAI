"""Add provider_used field to events table

Story P2-5.3: AI provider tracking

Adds:
- provider_used: String field to track which AI provider (openai/grok/claude/gemini)
  generated the event description. Nullable for backwards compatibility with
  legacy events.

Revision ID: 015
Revises: 014_correlation
Create Date: 2025-12-05
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '015_provider_used'
down_revision = '014_correlation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add provider_used column to events table."""
    op.add_column(
        'events',
        sa.Column('provider_used', sa.String(20), nullable=True)
    )


def downgrade() -> None:
    """Remove provider_used column from events table."""
    op.drop_column('events', 'provider_used')
