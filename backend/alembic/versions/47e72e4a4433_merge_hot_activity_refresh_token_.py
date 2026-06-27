"""merge hot-activity + refresh-token branches

Revision ID: 47e72e4a4433
Revises: bbf6282d9919, j7b100ecf1c6
Create Date: 2026-05-19 06:41:54.338269

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '47e72e4a4433'
down_revision = ('bbf6282d9919', 'j7b100ecf1c6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
