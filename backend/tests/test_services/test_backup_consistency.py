"""SQLite consistent backup/restore drills (CR-007 / #597)."""
import asyncio
import sqlite3
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.backup_service import (
    BackupService,
    UnsupportedDatabaseBackupError,
    configured_database_engine,
)


@pytest.fixture
def backup_harness(tmp_path):
    service = BackupService()
    service.backup_dir = tmp_path / "backups"
    service.backup_dir.mkdir()
    service.data_dir = tmp_path
    service.database_path = tmp_path / "app.db"
    service.thumbnails_dir = tmp_path / "thumbnails"
    service.thumbnails_dir.mkdir()
    # Seed a small SQLite DB with a committed row
    conn = sqlite3.connect(service.database_path)
    conn.execute("CREATE TABLE events (id TEXT PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO events (id, note) VALUES ('e1', 'before')")
    conn.commit()
    conn.close()
    return service


def test_configured_database_engine_detection():
    assert configured_database_engine("sqlite:///./data/app.db") == "sqlite"
    assert configured_database_engine("postgresql://user:pass@host/db") == "postgresql"
    assert configured_database_engine("mysql://x") == "unsupported"


@pytest.mark.asyncio
async def test_sqlite_backup_uses_online_api_and_integrity(backup_harness, tmp_path):
    with patch(
        "app.services.backup_service.configured_database_engine",
        return_value="sqlite",
    ):
        result = await backup_harness.create_backup(
            include_database=True,
            include_thumbnails=False,
            include_settings=False,
        )
    assert result.success, result.message
    zip_path = backup_harness.backup_dir / f"backup-{result.timestamp}.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        meta = zf.read("metadata.json").decode()
        assert '"database_engine": "sqlite"' in meta
        zf.extract("database.db", path=tmp_path)
    check = sqlite3.connect(tmp_path / "database.db")
    try:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        rows = check.execute("SELECT id, note FROM events").fetchall()
        assert rows == [("e1", "before")]
    finally:
        check.close()


@pytest.mark.asyncio
async def test_postgresql_backup_fails_closed(backup_harness):
    with patch(
        "app.services.backup_service.configured_database_engine",
        return_value="postgresql",
    ):
        result = await backup_harness.create_backup()
    assert result.success is False
    assert "PostgreSQL" in result.message


@pytest.mark.asyncio
async def test_sqlite_restore_drill_round_trip(backup_harness, tmp_path):
    with patch(
        "app.services.backup_service.configured_database_engine",
        return_value="sqlite",
    ), patch("app.core.database.dispose_engine") as dispose:
        created = await backup_harness.create_backup(
            include_database=True,
            include_thumbnails=False,
            include_settings=False,
        )
        assert created.success
        zip_path = backup_harness.backup_dir / f"backup-{created.timestamp}.zip"

        # Corrupt live DB after backup
        live = sqlite3.connect(backup_harness.database_path)
        live.execute("DELETE FROM events")
        live.execute("INSERT INTO events (id, note) VALUES ('e2', 'after')")
        live.commit()
        live.close()

        restored = await backup_harness.restore_from_backup(
            zip_path,
            restore_database=True,
            restore_thumbnails=False,
            restore_settings=False,
        )
        assert restored.success, restored.message
        dispose.assert_called()

    live = sqlite3.connect(backup_harness.database_path)
    try:
        rows = live.execute("SELECT id, note FROM events ORDER BY id").fetchall()
        assert rows == [("e1", "before")]
    finally:
        live.close()


@pytest.mark.asyncio
async def test_postgresql_restore_fails_closed(backup_harness, tmp_path):
    # Build a valid zip first under sqlite mode
    with patch(
        "app.services.backup_service.configured_database_engine",
        return_value="sqlite",
    ):
        created = await backup_harness.create_backup(
            include_database=True,
            include_thumbnails=False,
            include_settings=False,
        )
    zip_path = backup_harness.backup_dir / f"backup-{created.timestamp}.zip"
    with patch(
        "app.services.backup_service.configured_database_engine",
        return_value="postgresql",
    ):
        restored = await backup_harness.restore_from_backup(
            zip_path,
            restore_database=True,
            restore_thumbnails=False,
            restore_settings=False,
        )
    assert restored.success is False
    assert restored.http_status == 400
    assert "PostgreSQL" in restored.message or "pg_restore" in restored.message
