"""Add shadow_results.was_audit_claim (#746)

Set when the cloud audit claims a row and never cleared, so the daily audit
cap keeps counting a claim that a fallback later filled in.

Revision ID: r5d746a1b2c3
Revises: q4c735a1b2c3
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa


revision = "r5d746a1b2c3"
down_revision = "q4c735a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("shadow_results") as batch:
        batch.add_column(sa.Column("was_audit_claim", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
    # Rows written before this column: audit-sourced rows were audit claims.
    # sa.true() renders TRUE on Postgres booleans and 1 on SQLite.
    shadow_results = sa.table(
        "shadow_results",
        sa.column("was_audit_claim", sa.Boolean()),
        sa.column("source", sa.String()),
    )
    op.execute(
        shadow_results.update()
        .where(shadow_results.c.source == "audit")
        .values(was_audit_claim=sa.true())
    )
    op.create_index("idx_shadow_results_claim_created", "shadow_results",
                    ["was_audit_claim", "created_at"])
    op.create_index("idx_shadow_results_status_created", "shadow_results",
                    ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_shadow_results_status_created", table_name="shadow_results")
    op.drop_index("idx_shadow_results_claim_created", table_name="shadow_results")
    with op.batch_alter_table("shadow_results") as batch:
        batch.drop_column("was_audit_claim")
