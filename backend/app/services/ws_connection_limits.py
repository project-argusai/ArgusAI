"""Bounds for authenticated notification and camera WebSockets.

Rejected handshakes are not admitted, so they do not occupy a slot or start a
capture worker. HomeKit HAP streaming is a separate ffmpeg path and is not
counted here.
"""
import asyncio
import logging
from dataclasses import dataclass

from app.core.config import settings
from app.core.decorators import singleton

logger = logging.getLogger(__name__)


@dataclass
class WsAdmission:
    """One admitted socket. ``release`` is safe to call more than once."""

    user_id: str
    camera_id: str | None = None
    released: bool = False


@singleton
class WebSocketConnectionLimits:
    """In-memory per-user and per-camera caps for live WebSockets."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._users: dict[str, int] = {}
        self._cameras: dict[str, int] = {}

    async def try_admit(
        self, user_id: str, *, camera_id: str | None = None
    ) -> WsAdmission | None:
        """Reserve a slot. Returns None when a configured cap is already full."""
        async with self._lock:
            user_limit = settings.WS_MAX_CONNECTIONS_PER_USER
            user_count = self._users.get(user_id, 0)
            if user_count >= user_limit:
                self._log_rejection(user_id, camera_id, "user", user_limit)
                return None

            if camera_id is not None:
                camera_limit = settings.ws_max_connections_per_camera
                camera_count = self._cameras.get(camera_id, 0)
                if camera_count >= camera_limit:
                    self._log_rejection(user_id, camera_id, "camera", camera_limit)
                    return None
                self._cameras[camera_id] = camera_count + 1

            self._users[user_id] = user_count + 1
            return WsAdmission(user_id=user_id, camera_id=camera_id)

    async def release(self, admission: WsAdmission | None) -> None:
        """Return a slot reserved by ``try_admit``."""
        if admission is None or admission.released:
            return
        async with self._lock:
            if admission.released:
                return
            admission.released = True
            self._decrement(self._users, admission.user_id)
            if admission.camera_id is not None:
                self._decrement(self._cameras, admission.camera_id)

    @staticmethod
    def _decrement(counts: dict[str, int], key: str) -> None:
        remaining = counts.get(key, 0) - 1
        if remaining <= 0:
            counts.pop(key, None)
        else:
            counts[key] = remaining

    @staticmethod
    def _log_rejection(
        user_id: str, camera_id: str | None, scope: str, limit: int
    ) -> None:
        logger.warning(
            "WebSocket connection limit reached",
            extra={
                "event_type": "ws_connection_limit_rejected",
                "user_id": user_id,
                "camera_id": camera_id,
                "limit_scope": scope,
                "limit": limit,
            },
        )


def websocket_connection_limits() -> WebSocketConnectionLimits:
    """Return the process-wide limiter."""
    return WebSocketConnectionLimits()
