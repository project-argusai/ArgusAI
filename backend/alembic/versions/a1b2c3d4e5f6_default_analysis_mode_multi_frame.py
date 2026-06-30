"""default analysis_mode to multi_frame and backfill existing Protect cameras

The live Protect AI pipeline now treats ``Camera.analysis_mode`` as authoritative
(it no longer opportunistically upgrades/downgrades based on clip availability).
To make multi-frame the project default for clip-capable cameras, this migration:

  1. Changes the ``cameras.analysis_mode`` server default to ``'multi_frame'``.
  2. Backfills existing **Protect** cameras still on ``'single_frame'`` to
     ``'multi_frame'``.

The backfill is deliberately scoped to ``source_type = 'protect'``. RTSP/USB
cameras cannot supply a motion clip, so they must remain ``'single_frame'`` —
flipping them would only force a pointless clip-download attempt that always
falls back to single-frame. The existing CHECK constraint already restricts the
column to the three valid modes, so no constraint change is required.

Idempotent: a re-run's UPDATE selects nothing once the rows are already
multi_frame.

Revision ID: a1b2c3d4e5f6
Revises: f3a2c1d4e5b6
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f3a2c1d4e5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. New rows default to multi_frame at the DB level.
    with op.batch_alter_table("cameras") as batch_op:
        batch_op.alter_column(
            "analysis_mode",
            existing_type=sa.String(length=20),
            server_default="multi_frame",
            existing_nullable=False,
        )

    # 2. Backfill existing Protect cameras still on the old single_frame default.
    #    RTSP/USB cameras are intentionally left untouched (no clip source).
    op.execute(
        sa.text(
            "UPDATE cameras SET analysis_mode = 'multi_frame' "
            "WHERE source_type = 'protect' AND analysis_mode = 'single_frame'"
        )
    )


def downgrade() -> None:
    # Revert the server default only. The data backfill is intentionally NOT
    # reversed: once cameras are multi_frame we cannot know which Protect cameras
    # were originally single_frame, and reverting blindly would be lossy.
    with op.batch_alter_table("cameras") as batch_op:
        batch_op.alter_column(
            "analysis_mode",
            existing_type=sa.String(length=20),
            server_default="single_frame",
            existing_nullable=False,
        )
