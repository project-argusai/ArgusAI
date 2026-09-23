"""Hostile backup archives and bounded upload regressions."""

from io import BytesIO
from pathlib import Path
import asyncio
import stat
import tempfile
import zipfile
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1.system import _staged_backup_upload
from app.core.config import settings
from app.services.backup_service import BackupService


@pytest.fixture
def backup_service(tmp_path):
    service = BackupService()
    service.backup_dir = tmp_path / "backups"
    service.backup_dir.mkdir()
    service.data_dir = tmp_path
    service.database_path = tmp_path / "app.db"
    service.thumbnails_dir = tmp_path / "thumbnails"
    return service


def make_zip(path: Path, extras=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("database.db", b"SQLite format 3\x00")
        archive.writestr("metadata.json", '{"app_version":"1.0.0","timestamp":"test"}')
        for name, data in extras or []:
            archive.writestr(name, data)
    return path


@pytest.mark.parametrize("extras,reason", [
    ([("../escape.jpg", b"image")], "invalid path"),
    ([("thumbnails/../../escape.jpg", b"image")], "invalid path"),
    ([("other.txt", b"data")], "unexpected file"),
    ([("thumbnails/script.py", b"print(1)")], "unexpected file"),
    ([("metadata.json", b"{}")], "duplicate paths"),
])
def test_rejects_unsafe_archive_topology(backup_service, tmp_path, extras, reason):
    archive = make_zip(tmp_path / "bad.zip", extras)
    result = backup_service.validate_backup(archive)
    assert not result.valid
    assert reason in result.message


def test_rejects_symlink(backup_service, tmp_path):
    archive = make_zip(tmp_path / "link.zip")
    link = zipfile.ZipInfo("thumbnails/link.jpg")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as zf:
        zf.writestr(link, "../../escape")
    assert "special file" in backup_service.validate_backup(archive).message


def test_limits_member_count_expansion_and_ratio(backup_service, tmp_path, monkeypatch):
    archive = make_zip(tmp_path / "many.zip", [("thumbnails/a.jpg", b"a")])
    monkeypatch.setattr(settings, "BACKUP_MAX_MEMBERS", 2)
    assert "too many files" in backup_service.validate_backup(archive).message
    monkeypatch.setattr(settings, "BACKUP_MAX_MEMBERS", 100)
    monkeypatch.setattr(settings, "BACKUP_MAX_EXPANDED_BYTES", 4)
    assert "expands beyond" in backup_service.validate_backup(archive).message
    monkeypatch.setattr(settings, "BACKUP_MAX_EXPANDED_BYTES", 1000)
    monkeypatch.setattr(settings, "BACKUP_MAX_COMPRESSION_RATIO", 1)
    compressed = make_zip(tmp_path / "compressed.zip", [("thumbnails/a.jpg", b"0" * 500)])
    assert "compression ratio" in backup_service.validate_backup(compressed).message


def test_corrupt_archive_is_rejected_without_extraction(backup_service, tmp_path):
    archive = tmp_path / "broken.zip"
    archive.write_bytes(b"not a zip")
    assert not backup_service.validate_backup(archive).valid
    assert not list(backup_service.backup_dir.glob("restore-*"))


def test_invalid_metadata_types_are_rejected(backup_service, tmp_path):
    archive = tmp_path / "metadata.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("database.db", b"SQLite format 3\x00")
        zf.writestr("metadata.json", '{"app_version":{},"timestamp":"test"}')
    result = backup_service.validate_backup(archive)
    assert not result.valid
    assert "invalid version" in result.message


def test_member_size_limit_is_checked_before_decompression(backup_service, tmp_path, monkeypatch):
    archive = make_zip(tmp_path / "large.zip", [("thumbnails/a.jpg", b"123456")])
    monkeypatch.setattr(settings, "BACKUP_MAX_MEMBER_BYTES", 5)
    assert "oversized file" in backup_service.validate_backup(archive).message


@pytest.mark.asyncio
async def test_valid_archive_restores_only_approved_members(backup_service, tmp_path):
    archive = make_zip(tmp_path / "good.zip", [("thumbnails/day/event.jpg", b"image")])
    assert backup_service.validate_backup(archive).valid
    result = await backup_service.restore_from_backup(
        archive, restore_database=False, restore_thumbnails=True, restore_settings=False
    )
    assert result.success
    assert (backup_service.thumbnails_dir / "day" / "event.jpg").read_bytes() == b"image"
    assert not list(backup_service.backup_dir.glob("restore-*"))


@pytest.mark.asyncio
async def test_low_disk_rejects_before_live_data_changes(backup_service, tmp_path, monkeypatch):
    archive = make_zip(tmp_path / "good.zip")
    backup_service.database_path.write_bytes(b"original-db")
    monkeypatch.setattr("app.services.backup_service.shutil.disk_usage", lambda _: SimpleNamespace(free=0))
    result = await backup_service.restore_from_backup(archive)
    assert not result.success
    assert result.message == "Insufficient free disk space for restore"
    assert backup_service.database_path.read_bytes() == b"original-db"
    assert not list(backup_service.backup_dir.glob("restore-*"))


@pytest.mark.asyncio
async def test_upload_limit_cleans_staged_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_MAX_UPLOAD_BYTES", 4)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    upload = UploadFile(file=BytesIO(b"12345"), filename="backup.zip")
    with pytest.raises(HTTPException) as error:
        async with _staged_backup_upload(upload):
            pass
    assert error.value.status_code == 413
    assert not list(tmp_path.glob("*.zip"))


@pytest.mark.asyncio
async def test_disconnected_upload_cleans_staged_file(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    upload = UploadFile(file=BytesIO(), filename="backup.zip")
    upload.read = AsyncMock(side_effect=[b"partial", asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        async with _staged_backup_upload(upload):
            pass
    assert not list(tmp_path.glob("*.zip"))
