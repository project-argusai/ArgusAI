"""#756: f3a2c1d4e5b6 repairs local-time Protect timestamps on SQLite and Postgres.

Runs on SQLite (temp file) in the normal backend suite. For the Postgres
migrations job, set ``ARGUS_PG_MIGRATION_TEST_URL`` to a THROWAWAY database:
the test drops and recreates its ``public`` schema.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

BACKEND_DIR = Path(__file__).resolve().parents[1]
BEFORE = "e7c9a1b3d5f2"
TARGET = "f3a2c1d4e5b6"
PG_URL = os.environ.get("ARGUS_PG_MIGRATION_TEST_URL")


def _alembic(url: str, *args: str) -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = url
    env.setdefault("ENCRYPTION_KEY", "YhLHon9m3QOhb394b-Qa761Vgj9ij3oLlT-moS2oRcg=")
    env.setdefault("JWT_SECRET_KEY", "test-secret-not-for-production")
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]


def _dummy(col):
    t = str(col["type"]).upper()
    if "BOOL" in t:
        return False
    if "INT" in t:
        return 0
    if any(k in t for k in ("REAL", "FLOA", "NUM", "DEC", "DOUBLE")):
        return 0.0
    if "DATE" in t or "TIME" in t:
        return datetime(2026, 1, 1)
    if "JSON" in t:
        return "{}"
    return "x"


def _insert(conn, table, **values):
    cols = sa.inspect(conn).get_columns(table)
    for col in cols:
        if col["name"] in values:
            continue
        if not col["nullable"] and col.get("default") is None and not col.get("autoincrement") is True:
            values[col["name"]] = _dummy(col)
    names = ", ".join(f'"{k}"' for k in values)
    marks = ", ".join(f":{k}" for k in values)
    conn.execute(sa.text(f"INSERT INTO {table} ({names}) VALUES ({marks})"), values)


def _insert_event(conn, **values):
    _insert(conn, "events", camera_id="cam-1", **values)


def _naive_utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _urls():
    yield pytest.param("sqlite", id="sqlite")
    yield pytest.param(
        "postgresql", id="postgresql",
        marks=pytest.mark.skipif(not PG_URL, reason="ARGUS_PG_MIGRATION_TEST_URL not set"),
    )


@pytest.mark.parametrize("dialect", list(_urls()))
def test_local_protect_timestamps_repaired(dialect, tmp_path):
    if dialect == "sqlite":
        url = f"sqlite:///{tmp_path / 'f3a2.db'}"
    else:
        url = PG_URL
        eng = sa.create_engine(url)
        with eng.begin() as c:
            c.execute(sa.text("DROP SCHEMA public CASCADE"))
            c.execute(sa.text("CREATE SCHEMA public"))
        eng.dispose()

    _alembic(url, "upgrade", BEFORE)

    created = datetime(2026, 6, 28, 18, 0, 0)          # UTC (CDT, offset -5)
    local_ts = created - timedelta(hours=5)             # stored as Chicago wall time
    ok_ts = created - timedelta(seconds=3)              # correctly stored UTC
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _insert(conn, "cameras", id="cam-1")
        _insert_event(conn, id="evt-bad", source_type="protect",
                      timestamp=local_ts, created_at=created)
        _insert_event(conn, id="evt-ok", source_type="protect",
                      timestamp=ok_ts, created_at=created)
        _insert_event(conn, id="evt-rtsp", source_type="rtsp",
                      timestamp=local_ts, created_at=created)

    _alembic(url, "upgrade", TARGET)

    with eng.connect() as conn:
        rows = dict(conn.execute(sa.text("SELECT id, timestamp FROM events")).fetchall())
    eng.dispose()
    assert _naive_utc(rows["evt-bad"]) == created
    assert _naive_utc(rows["evt-ok"]) == ok_ts
    assert _naive_utc(rows["evt-rtsp"]) == local_ts
