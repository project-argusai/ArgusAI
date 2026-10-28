"""#757: after `alembic upgrade head` on a fresh SQLite DB, new events are searchable."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _upgrade_head(db_path: Path) -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env.setdefault("ENCRYPTION_KEY", "YhLHon9m3QOhb394b-Qa761Vgj9ij3oLlT-moS2oRcg=")
    env.setdefault("JWT_SECRET_KEY", "test-secret-not-for-production")
    env["PYTHONPATH"] = str(BACKEND_DIR)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR, env=env, check=True, capture_output=True,
    )


def _dummy(col_type: str):
    t = (col_type or "").upper()
    if any(k in t for k in ("INT", "BOOL")):
        return 0
    if any(k in t for k in ("REAL", "FLOA", "NUM", "DEC")):
        return 0.0
    if "DATE" in t or "TIME" in t:
        return "2026-01-01 00:00:00"
    return "x"


def _insert_event(conn: sqlite3.Connection, event_id: str, description: str) -> None:
    cols = conn.execute("PRAGMA table_info(events)").fetchall()
    values = {"id": event_id, "description": description}
    for _cid, name, col_type, notnull, default, _pk in cols:
        if name in values:
            continue
        if notnull and default is None:
            values[name] = _dummy(col_type)
    names = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    conn.execute(f"INSERT INTO events ({names}) VALUES ({marks})", list(values.values()))


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("fts757") / "fresh.db"
    _upgrade_head(db_path)
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


def test_fts_triggers_exist_after_upgrade_head(migrated_db):
    names = {
        row[0]
        for row in migrated_db.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    }
    assert {"events_ai", "events_au", "events_ad"} <= names


def test_new_event_is_found_by_search_after_upgrade_head(migrated_db):
    _insert_event(migrated_db, "evt-757-a", "a zebra crossed the driveway")
    migrated_db.commit()
    # Same query the events API uses for ?search=
    hits = [r[0] for r in migrated_db.execute(
        "SELECT id FROM events_fts WHERE description MATCH ?", ("zebra",)
    )]
    assert hits == ["evt-757-a"]

    migrated_db.execute(
        "UPDATE events SET description = ? WHERE id = ?", ("a giraffe waited", "evt-757-a")
    )
    migrated_db.commit()
    assert [r[0] for r in migrated_db.execute(
        "SELECT id FROM events_fts WHERE description MATCH ?", ("giraffe",)
    )] == ["evt-757-a"]
    assert not migrated_db.execute(
        "SELECT id FROM events_fts WHERE description MATCH ?", ("zebra",)
    ).fetchall()

    migrated_db.execute("DELETE FROM events WHERE id = ?", ("evt-757-a",))
    migrated_db.commit()
    assert not migrated_db.execute(
        "SELECT id FROM events_fts WHERE description MATCH ?", ("giraffe",)
    ).fetchall()
