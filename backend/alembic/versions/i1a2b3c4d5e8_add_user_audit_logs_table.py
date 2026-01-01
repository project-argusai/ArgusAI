"""Add user_audit_logs table (Story P16-1.6)

Revision ID: i1a2b3c4d5e8
Revises: h1a2b3c4d5e7
Create Date: 2026-01-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i1a2b3c4d5e8'
down_revision = 'h1a2b3c4d5e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_audit_logs table for tracking user management actions"""
    op.create_table(
        'user_audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('action', sa.String(50), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('target_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # Create composite indexes for common queries
    op.create_index('idx_audit_action_created', 'user_audit_logs', ['action', 'created_at'])
    op.create_index('idx_audit_target_created', 'user_audit_logs', ['target_user_id', 'created_at'])


def downgrade() -> None:
    """Drop user_audit_logs table"""
    op.drop_index('idx_audit_target_created', table_name='user_audit_logs')
    op.drop_index('idx_audit_action_created', table_name='user_audit_logs')
    op.drop_table('user_audit_logs')
