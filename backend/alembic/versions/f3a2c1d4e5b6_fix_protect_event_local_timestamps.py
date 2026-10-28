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

The gap test uses julianday() on SQLite and EXTRACT(EPOCH ...) on Postgres;
other dialects skip (#756).

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
# target a tz offset specifically: 4h..7h. The interval maths is dialect
# specific (#756): julianday() exists only on SQLite.
_WHERE = """
    FROM events
    WHERE source_type = 'protect'
      AND created_at >= '2026-06-28'
"""

_SELECT_SQLITE = sa.text(
    "SELECT id, timestamp" + _WHERE
    + "  AND (julianday(created_at) - julianday(timestamp)) BETWEEN (4.0/24.0) AND (7.0/24.0)"
)

# The bad rows came from app code (ProtectMediaService passing naive
# datetime.now()), not from anything SQLite-specific, so a Postgres install
# running that build could hold them too. The column is timestamptz, so the
# naive local value was interpreted in the session TimeZone when written; read
# it back as naive wall-clock in that same zone so the America/Chicago
# localisation below recovers the real instant, then write an aware UTC value.
_SELECT_POSTGRES = sa.text(
    "SELECT id, (events.timestamp AT TIME ZONE current_setting('TimeZone')) AS timestamp" + _WHERE
    + "  AND EXTRACT(EPOCH FROM (events.created_at - events.timestamp)) BETWEEN 4 * 3600 AND 7 * 3600"
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
    dialect = bind.dialect.name
    if dialect == "sqlite":
        select = _SELECT_SQLITE
    elif dialect == "postgresql":
        select = _SELECT_POSTGRES
    else:
        print(f"[f3a2c1d4e5b6] No interval query for dialect {dialect!r}; skipping")
        return
    rows = bind.execute(select).fetchall()
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
        )
        if dialect == "sqlite":
            utc_naive = utc_naive.replace(tzinfo=None)
        bind.execute(update, {"ts": utc_naive, "id": row.id})
        fixed += 1

    print(f"[f3a2c1d4e5b6] Converted {fixed} protect event timestamp(s) local -> UTC")


def downgrade() -> None:
    # No-op: reversing would re-introduce incorrect local timestamps. The forward
    # data is correct UTC; there is nothing safe to undo.
    pass
