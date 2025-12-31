"""Add multi-user auth tables (Story P15-2.1, P15-2.2)

Revision ID: g1a2b3c4d5e6
Revises: 059
Create Date: 2025-12-30 10:00:00.000000

Story P15-2.1: User model and database schema
- Add email column to users table
- Add role column (enum: admin, operator, viewer)
- Add must_change_password column
- Add password_expires_at column
- Add updated_at column

Story P15-2.2: Session model and tracking
- Create sessions table for session tracking
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = 'g1a2b3c4d5e6'
down_revision = '059'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create sessions table first (before adding relationships to users)
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('device_info', sa.String(255), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Create indexes for sessions table
    op.create_index('idx_sessions_user_id', 'sessions', ['user_id'])
    op.create_index('idx_sessions_token_hash', 'sessions', ['token_hash'])
    op.create_index('idx_sessions_expires_at', 'sessions', ['expires_at'])
    op.create_index('idx_sessions_user_expires', 'sessions', ['user_id', 'expires_at'])
    op.create_index('idx_sessions_user_created', 'sessions', ['user_id', 'created_at'])

    # Add new columns to users table
    # Note: For SQLite, we need to handle existing NULL values properly

    # Add email column (nullable for backwards compatibility)
    # Note: SQLite doesn't support adding column with unique constraint, so we add
    # a unique index separately
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    op.create_index('idx_users_email', 'users', ['email'], unique=True)

    # Add role column with default 'admin' for existing users
    op.add_column('users', sa.Column('role', sa.String(20), nullable=False, server_default='admin'))
    op.create_index('idx_users_role', 'users', ['role'])

    # Add must_change_password column
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='0'))

    # Add password_expires_at column
    op.add_column('users', sa.Column('password_expires_at', sa.DateTime(timezone=True), nullable=True))

    # Add updated_at column with current timestamp as default
    op.add_column('users', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    # Update existing users to have updated_at = created_at
    op.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL")

    # Create composite index for common queries
    op.create_index('idx_users_active_role', 'users', ['is_active', 'role'])


def downgrade() -> None:
    # Drop indexes and columns from users table
    op.drop_index('idx_users_active_role', table_name='users')
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'password_expires_at')
    op.drop_column('users', 'must_change_password')
    op.drop_index('idx_users_role', table_name='users')
    op.drop_column('users', 'role')
    op.drop_index('idx_users_email', table_name='users')  # unique index
    op.drop_column('users', 'email')

    # Drop sessions table and indexes
    op.drop_index('idx_sessions_user_created', table_name='sessions')
    op.drop_index('idx_sessions_user_expires', table_name='sessions')
    op.drop_index('idx_sessions_expires_at', table_name='sessions')
    op.drop_index('idx_sessions_token_hash', table_name='sessions')
    op.drop_index('idx_sessions_user_id', table_name='sessions')
    op.drop_table('sessions')
