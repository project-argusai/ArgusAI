"""Add consumed_refresh_tokens ledger for web refresh reuse detection

Revision ID: k8c211fd2d7a
Revises: a1b2c3d4e5f6
Create Date: 2026-08-13

Issue #520: refresh-token reuse-detection was dead because rotation overwrote
refresh_token_hash in place on the same session row. This ledger keeps consumed
hashes recognizable so a stolen-token replay can revoke the whole family.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "k8c211fd2d7a"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consumed_refresh_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_family", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(
        "idx_consumed_refresh_family",
        "consumed_refresh_tokens",
        ["token_family"],
    )
    op.create_index(
        "idx_consumed_refresh_session",
        "consumed_refresh_tokens",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_consumed_refresh_session", table_name="consumed_refresh_tokens")
    op.drop_index("idx_consumed_refresh_family", table_name="consumed_refresh_tokens")
    op.drop_table("consumed_refresh_tokens")
