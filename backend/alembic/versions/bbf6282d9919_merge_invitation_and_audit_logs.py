"""merge_invitation_and_audit_logs

Revision ID: bbf6282d9919
Revises: 72193d1b9979, i1a2b3c4d5e8
Create Date: 2026-01-01 14:33:20.728010

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bbf6282d9919'
down_revision = ('72193d1b9979', 'i1a2b3c4d5e8')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
