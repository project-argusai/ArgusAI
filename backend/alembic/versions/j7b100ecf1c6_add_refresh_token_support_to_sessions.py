"""Add refresh token support to sessions table (Phase A - Web Auth Refresh)

Revision ID: j7b100ecf1c6
Revises: i1a2b3c4d5e8
Create Date: 2026-05-15

Phase A - Web Authentication Refresh Tokens:
- Add columns to support refresh tokens on web sessions
- Aligns web auth with mobile TokenService patterns (rotation, family, revocation)
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = 'j7b100ecf1c6'
down_revision = 'i1a2b3c4d5e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add refresh token columns to sessions table
    op.add_column('sessions', sa.Column('refresh_token_hash', sa.String(64), nullable=True))
    op.add_column('sessions', sa.Column('refresh_token_family', sa.String(36), nullable=True))
    op.add_column('sessions', sa.Column('refresh_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sessions', sa.Column('refresh_revoked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sessions', sa.Column('refresh_revoked_reason', sa.String(50), nullable=True))

    # Create indexes for refresh token lookups and family revocation
    op.create_index('idx_sessions_refresh_hash', 'sessions', ['refresh_token_hash'])
    op.create_index('idx_sessions_refresh_family', 'sessions', ['refresh_token_family'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_sessions_refresh_family', table_name='sessions')
    op.drop_index('idx_sessions_refresh_hash', table_name='sessions')

    # Drop columns
    op.drop_column('sessions', 'refresh_revoked_reason')
    op.drop_column('sessions', 'refresh_revoked_at')
    op.drop_column('sessions', 'refresh_expires_at')
    op.drop_column('sessions', 'refresh_token_family')
    op.drop_column('sessions', 'refresh_token_hash')