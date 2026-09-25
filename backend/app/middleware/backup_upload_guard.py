"""Stop oversized backup uploads before the multipart parser spools them.

The guard runs only for admin backup validate/restore POSTs, and only after
authentication and CSRF have accepted the request. It streams the body to a
temporary file with a byte cap, a time cap, and a free-space check, then
replays that file to the application. Over-limit, timed-out, and out-of-space
uploads are rejected without calling the route, and the temp file is removed
on every path.
"""
import asyncio
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

from app.core.config import settings
from app.services.backup_limits import (
    INVALID_CONTENT_LENGTH,
    UPLOAD_NO_SPACE,
    UPLOAD_TIMED_OUT,
    UPLOAD_TOO_LARGE,
    disk_required_for,
    upload_body_limit,
)

logger = logging.getLogger(__name__)

_CHUNK_BYTES = 1024 * 1024


class _UploadRejected(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


class _ClientGone(Exception):
    pass


class _BodyReplay:
    """Replay a spooled body in fixed-size chunks."""

    def __init__(self, path: Path):
        self._file = path.open("rb")
        self._remaining = path.stat().st_size
        self._done = False

    async def __call__(self):
        if self._done:
            return {"type": "http.disconnect"}
        chunk = self._file.read(min(_CHUNK_BYTES, self._remaining))
        self._remaining -= len(chunk)
        if self._remaining <= 0:
            self._done = True
        return {"type": "http.request", "body": chunk, "more_body": self._remaining > 0}

    def close(self) -> None:
        self._file.close()


def _guarded_paths() -> frozenset[str]:
    prefix = settings.API_V1_PREFIX.rstrip("/")
    return frozenset({
        f"{prefix}/system/backup/validate",
        f"{prefix}/system/restore",
    })


def _request_path(scope) -> str:
    path = scope.get("path") or ""
    root = scope.get("root_path") or ""
    if root and path.startswith(root):
        path = path[len(root):] or "/"
    return path


def _header_values(scope, name: str) -> list[str]:
    target = name.lower().encode("latin-1")
    values = []
    for key, value in scope.get("headers") or []:
        if key.lower() == target:
            values.append(value.decode("latin-1").strip())
    return values


def _content_length(scope) -> int | None:
    values = _header_values(scope, "content-length")
    if not values:
        return None
    parsed = []
    for value in values:
        try:
            number = int(value)
        except ValueError:
            raise _UploadRejected(400, INVALID_CONTENT_LENGTH) from None
        if number < 0:
            raise _UploadRejected(400, INVALID_CONTENT_LENGTH)
        parsed.append(number)
    if any(number != parsed[0] for number in parsed):
        raise _UploadRejected(400, INVALID_CONTENT_LENGTH)
    return parsed[0]


def _has_room(num_bytes: int) -> bool:
    try:
        free = shutil.disk_usage(tempfile.gettempdir()).free
    except OSError:
        return False
    return free >= disk_required_for(num_bytes)


class BackupUploadGuard:
    """ASGI middleware that bounds backup validate/restore request bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        if _request_path(scope) not in _guarded_paths():
            await self.app(scope, receive, send)
            return

        path: Path | None = None
        try:
            content_length = _content_length(scope)
            cap = upload_body_limit()
            if content_length is not None and content_length > cap:
                raise _UploadRejected(413, UPLOAD_TOO_LARGE)
            if content_length is not None and not _has_room(content_length):
                raise _UploadRejected(507, UPLOAD_NO_SPACE)
            path = await _spool_body(receive, cap)
            replay = _BodyReplay(path)
            try:
                await self.app(scope, replay, send)
            finally:
                replay.close()
        except _UploadRejected as exc:
            _log_rejection(exc)
            await _send_json(send, scope, exc.status_code, exc.detail)
        except _ClientGone:
            logger.info(
                "Backup upload disconnected",
                extra={"event_type": "backup_upload_disconnected"},
            )
        finally:
            if path is not None:
                path.unlink(missing_ok=True)


def _log_rejection(exc: _UploadRejected) -> None:
    logger.warning(
        "Backup upload rejected",
        extra={
            "event_type": "backup_upload_rejected",
            "status_code": exc.status_code,
            "reason": exc.detail,
        },
    )


async def _spool_body(receive, cap: int) -> Path:
    """Copy the request body to disk, refusing to store more than ``cap`` bytes."""
    deadline = time.monotonic() + settings.BACKUP_UPLOAD_TIMEOUT_SECONDS
    handle = tempfile.NamedTemporaryFile(
        delete=False, prefix="backup-upload-", suffix=".part"
    )
    path = Path(handle.name)
    written = 0
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _UploadRejected(408, UPLOAD_TIMED_OUT)
            try:
                message = await asyncio.wait_for(receive(), timeout=remaining)
            except TimeoutError:
                raise _UploadRejected(408, UPLOAD_TIMED_OUT) from None
            if message["type"] == "http.disconnect":
                raise _ClientGone()
            if message["type"] != "http.request":
                continue
            body = message.get("body", b"")
            if written + len(body) > cap:
                raise _UploadRejected(413, UPLOAD_TOO_LARGE)
            if body and not _has_room(written + len(body)):
                raise _UploadRejected(507, UPLOAD_NO_SPACE)
            if body:
                handle.write(body)
                written += len(body)
            if not message.get("more_body", False):
                handle.close()
                return path
    except BaseException:
        handle.close()
        path.unlink(missing_ok=True)
        raise


async def _send_json(send, scope, status_code: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"connection", b"close"),
    ]
    origin = ""
    for value in _header_values(scope, "origin"):
        origin = value
        break
    if origin and origin in settings.cors_origins_list:
        headers.append((b"access-control-allow-origin", origin.encode("latin-1")))
        headers.append((b"access-control-allow-credentials", b"true"))
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})
