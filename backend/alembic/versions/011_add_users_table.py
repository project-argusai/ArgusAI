"""Add users table for authentication (Story 6.3)

Revision ID: 011
Revises: 010
Create Date: 2025-11-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    """Create users table for authentication"""

    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('password_hash', sa.String(60), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    )

    # Create unique index on username
    op.create_index('idx_users_username', 'users', ['username'], unique=True)


def downgrade():
    """Drop users table"""

    op.drop_index('idx_users_username', 'users')
    op.drop_table('users')
