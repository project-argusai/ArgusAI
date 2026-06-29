"""fix protect event timestamps stored in server-local time

A refactor of ProtectMediaService (~2026-06-28 16:35 UTC) made
``_retrieve_snapshot`` pass ``datetime.now()`` (server-LOCAL, US/Central) as the
snapshot timestamp, which becomes ``Event.timestamp``. Every other timestamp in
the app (``created_at``, RTSP/USB events) is UTC, so these Protect events were
stored 5–6 hours off and rendered inconsistently in the UI.

The code is fixed forward (``datetime.now(timezone.utc)``). This migration repairs
the rows already written with a local timestamp.

Selection is deliberately narrow and self-validating so it can never touch
correctly-stored rows or be applied twice:
  * source_type = 'protect'                       (only path with the bug)
  * created_at >= 2026-06-28                       (the regression window)
  * 4h < (created_at - timestamp) < 7h            (a US/Central tz offset, not a
                                                    seconds-level normal gap nor a
                                                    multi-day backfill gap)

Conversion uses DST-aware zoneinfo localisation (America/Chicago -> UTC), so it is
correct for both CDT (-5) and CST (-6). After conversion the gap collapses to ~0,
so a re-run selects nothing (idempotent).

Revision ID: f3a2c1d4e5b6
Revises: e7c9a1b3d5f2
Create Date: 2026-06-29
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f3a2c1d4e5b6"
down_revision = "e7c9a1b3d5f2"
branch_labels = None
depends_on = None

_SERVER_TZ = ZoneInfo("America/Chicago")

# Rows whose stored `timestamp` is server-local instead of UTC. The gap bounds
# (in days, for julianday math) target a tz offset specifically: 4h..7h.
_SELECT = sa.text(
    """
    SELECT id, timestamp
    FROM events
    WHERE source_type = 'protect'
      AND created_at >= '2026-06-28'
      AND (julianday(created_at) - julianday(timestamp)) BETWEEN (4.0/24.0) AND (7.0/24.0)
    """
)


def _parse(ts):
    """Parse a stored naive datetime string/obj into a naive datetime."""
    if isinstance(ts, datetime):
        return ts
    s = str(ts)
    # SQLite stores 'YYYY-MM-DD HH:MM:SS[.ffffff]'
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Last resort: ISO-ish
    return datetime.fromisoformat(s.replace("Z", ""))


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(_SELECT).fetchall()
    if not rows:
        return

    update = sa.text("UPDATE events SET timestamp = :ts WHERE id = :id")
    fixed = 0
    for row in rows:
        local_naive = _parse(row.timestamp)
        # Interpret the stored value as server-local, convert to UTC, store naive
        # UTC to match the rest of the schema.
        utc_naive = (
            local_naive.replace(tzinfo=_SERVER_TZ)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        bind.execute(update, {"ts": utc_naive, "id": row.id})
        fixed += 1

    print(f"[f3a2c1d4e5b6] Converted {fixed} protect event timestamp(s) local -> UTC")


def downgrade() -> None:
    # No-op: reversing would re-introduce incorrect local timestamps. The forward
    # data is correct UTC; there is nothing safe to undo.
    pass
