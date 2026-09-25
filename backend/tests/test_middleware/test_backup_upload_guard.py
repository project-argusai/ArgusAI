"""Backup upload bodies are capped before the multipart parser can spool them."""

import asyncio
import json
import tempfile
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.middleware.backup_upload_guard import BackupUploadGuard
from app.services.backup_limits import UPLOAD_NO_SPACE, UPLOAD_TIMED_OUT, UPLOAD_TOO_LARGE, upload_body_limit


def _recording_app(store):
    async def app(scope, receive, send):
        store["called"] = True
        parts = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            parts.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        store["body"] = b"".join(parts)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


async def _invoke(guard, path, *, body=b"", headers=None, receive=None):
    sent = []

    async def default_receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "root_path": "",
        "headers": headers if headers is not None else [(b"content-length", str(len(body)).encode())],
    }
    await guard(scope, receive or default_receive, send)
    return sent


def _status(sent):
    return next(message["status"] for message in sent if message["type"] == "http.response.start")


def _detail(sent):
    payload = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return json.loads(payload)["detail"]


@pytest.fixture
def guarded(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    store = {"called": False, "body": b""}
    return BackupUploadGuard(_recording_app(store)), store, tmp_path


@pytest.mark.asyncio
async def test_declared_oversize_is_rejected_without_reading(guarded, monkeypatch):
    guard, store, tmp_path = guarded
    monkeypatch.setattr(settings, "BACKUP_MAX_UPLOAD_BYTES", 1024)

    async def receive():
        raise AssertionError("oversized body was read")

    sent = await _invoke(
        guard,
        "/api/v1/system/restore",
        headers=[(b"content-length", str(upload_body_limit() + 1).encode())],
        receive=receive,
    )
    assert _status(sent) == 413
    assert _detail(sent) == UPLOAD_TOO_LARGE
    assert store["called"] is False
    assert list(tmp_path.glob("backup-upload-*")) == []


@pytest.mark.asyncio
async def test_streamed_oversize_stops_and_cleans_temp(guarded, monkeypatch):
    guard, store, tmp_path = guarded
    monkeypatch.setattr(settings, "BACKUP_MAX_UPLOAD_BYTES", 1000)
    cap = upload_body_limit()
    chunks = [b"a" * 1000, b"b" * cap]
    calls = {"n": 0}

    async def receive():
        calls["n"] += 1
        index = calls["n"] - 1
        if index >= len(chunks):
            raise AssertionError("body was read past the cap")
        return {"type": "http.request", "body": chunks[index], "more_body": True}

    sent = await _invoke(
        guard,
        "/api/v1/system/backup/validate",
        headers=[],
        receive=receive,
    )
    assert _status(sent) == 413
    assert _detail(sent) == UPLOAD_TOO_LARGE
    assert store["called"] is False
    assert calls["n"] == 2
    assert list(tmp_path.glob("backup-upload-*")) == []


@pytest.mark.asyncio
async def test_slow_upload_times_out_and_cleans_temp(guarded, monkeypatch):
    guard, _store, tmp_path = guarded
    monkeypatch.setattr(settings, "BACKUP_UPLOAD_TIMEOUT_SECONDS", 0.05)

    async def receive():
        await asyncio.sleep(0.3)
        return {"type": "http.request", "body": b"late", "more_body": False}

    sent = await _invoke(guard, "/api/v1/system/restore", headers=[], receive=receive)
    assert _status(sent) == 408
    assert _detail(sent) == UPLOAD_TIMED_OUT
    assert list(tmp_path.glob("backup-upload-*")) == []


@pytest.mark.asyncio
async def test_disconnect_cleans_temp_without_a_response(guarded):
    guard, store, tmp_path = guarded

    async def receive():
        return {"type": "http.disconnect"}

    sent = await _invoke(guard, "/api/v1/system/restore", headers=[], receive=receive)
    assert sent == []
    assert store["called"] is False
    assert list(tmp_path.glob("backup-upload-*")) == []


@pytest.mark.asyncio
async def test_low_disk_rejects_before_reading(guarded, monkeypatch):
    guard, store, tmp_path = guarded
    monkeypatch.setattr(
        "app.middleware.backup_upload_guard.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=0),
    )

    async def receive():
        raise AssertionError("body was read")

    sent = await _invoke(
        guard,
        "/api/v1/system/restore",
        body=b"small",
        receive=receive,
    )
    assert _status(sent) == 507
    assert _detail(sent) == UPLOAD_NO_SPACE
    assert store["called"] is False
    assert list(tmp_path.glob("backup-upload-*")) == []


@pytest.mark.asyncio
async def test_within_limit_replays_body_and_cleans_temp(guarded):
    guard, store, tmp_path = guarded
    payload = b"PK\x03\x04valid-backup"
    chunks = [payload[:4], payload[4:]]
    index = {"n": 0}

    async def receive():
        current = index["n"]
        index["n"] += 1
        return {
            "type": "http.request",
            "body": chunks[current],
            "more_body": current == 0,
        }

    sent = await _invoke(
        guard,
        "/api/v1/system/backup/validate",
        headers=[(b"content-length", str(len(payload)).encode())],
        receive=receive,
    )
    assert _status(sent) == 200
    assert store["called"] is True
    assert store["body"] == payload
    assert list(tmp_path.glob("backup-upload-*")) == []


@pytest.mark.asyncio
async def test_other_routes_are_not_buffered(guarded):
    guard, store, tmp_path = guarded
    payload = b"z" * 50

    sent = await _invoke(guard, "/api/v1/events", body=payload)
    assert _status(sent) == 200
    assert store["body"] == payload
    assert list(tmp_path.glob("backup-upload-*")) == []


def test_guard_is_inside_auth_and_csrf():
    from main import app

    names = [middleware.cls.__name__ for middleware in app.user_middleware]
    assert names.index("AuthMiddleware") < names.index("BackupUploadGuard")
    assert names.index("CSRFMiddleware") < names.index("BackupUploadGuard")
