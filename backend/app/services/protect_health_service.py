"""
Protect WebSocket Health Service (Story #437)

Tracks the health and connection state of the UniFi Protect WebSocket.
This allows us to expose proper health information for monitoring and the UI.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import logging

from app.core.metrics import protect_ws_connected, protect_ws_last_message_age_seconds

logger = logging.getLogger(__name__)


class ProtectConnectionState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


@dataclass
class ProtectHealthStatus:
    state: ProtectConnectionState = ProtectConnectionState.DISCONNECTED
    last_message_at: Optional[float] = None
    reconnect_attempts: int = 0
    controller_name: Optional[str] = None
    last_error: Optional[str] = None

    @property
    def is_healthy(self) -> bool:
        if self.state != ProtectConnectionState.CONNECTED:
            return False
        if self.last_message_at is None:
            return False
        # Consider unhealthy if no message in last 90 seconds
        return (time.time() - self.last_message_at) < 90

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "is_healthy": self.is_healthy,
            "last_message_at": self.last_message_at,
            "reconnect_attempts": self.reconnect_attempts,
            "controller_name": self.controller_name,
            "last_error": self.last_error,
            "last_message_age_seconds": int(time.time() - self.last_message_at) if self.last_message_at else None,
        }


class ProtectHealthService:
    _instance: Optional["ProtectHealthService"] = None
    _status: ProtectHealthStatus = field(default_factory=ProtectHealthStatus)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._status = ProtectHealthStatus()
        return cls._instance

    @classmethod
    def get_instance(cls) -> "ProtectHealthService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def update_connection_state(self, state: ProtectConnectionState, controller_name: Optional[str] = None):
        self._status.state = state
        if controller_name:
            self._status.controller_name = controller_name

        # Update Prometheus metrics
        protect_ws_connected.set(1 if state == ProtectConnectionState.CONNECTED else 0)

        if state == ProtectConnectionState.CONNECTED:
            self._status.last_message_at = time.time()
            self._status.reconnect_attempts = 0
            self._status.last_error = None
            protect_ws_last_message_age_seconds.set(0)
        else:
            # Update age metric
            if self._status.last_message_at:
                protect_ws_last_message_age_seconds.set(time.time() - self._status.last_message_at)

    def record_message_received(self):
        self._status.last_message_at = time.time()
        protect_ws_last_message_age_seconds.set(0)

    def record_reconnect_attempt(self):
        self._status.reconnect_attempts += 1
        self._status.state = ProtectConnectionState.RECONNECTING
        protect_ws_connected.set(0)

        if self._status.last_message_at:
            protect_ws_last_message_age_seconds.set(time.time() - self._status.last_message_at)

    def record_error(self, error: str):
        self._status.last_error = error
        self._status.state = ProtectConnectionState.DISCONNECTED
        protect_ws_connected.set(0)

        if self._status.last_message_at:
            protect_ws_last_message_age_seconds.set(time.time() - self._status.last_message_at)

    def get_status(self) -> ProtectHealthStatus:
        # Keep age metric fresh
        if self._status.last_message_at and self._status.state != ProtectConnectionState.CONNECTED:
            protect_ws_last_message_age_seconds.set(time.time() - self._status.last_message_at)
        return self._status

    def reset(self):
        self._status = ProtectHealthStatus()
        protect_ws_connected.set(0)
        protect_ws_last_message_age_seconds.set(0)


# Global singleton accessor
def get_protect_health_service() -> ProtectHealthService:
    return ProtectHealthService.get_instance()
