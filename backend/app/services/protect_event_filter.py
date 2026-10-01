"""
ProtectEventFilter

Responsible for filtering and deduplicating Protect events before they reach the AI pipeline.

Handles:
- Per-camera smart detection type filtering ("person", "vehicle", etc.)
- "All motion" mode (empty filter or ["motion"])
- Deduplication using per-camera cooldown window
- In-memory reservation of a Protect event id so a later update of the same
  id cannot start a second analysis while the first is still in flight

Extracted from ProtectEventHandler during Phase 4 of the decomposition.

# Migrated to @singleton decorator (core.decorators) as part of #450 (Lightweight DI Container).
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from app.core.decorators import singleton

logger = logging.getLogger(__name__)

# Default cooldown to prevent duplicate processing for the same camera.
# This window is per camera, not per Protect event. A WebSocket update for an
# event that is still open lands at about this boundary and must be deduped
# by protect_event_id (see ProtectEventHandler), not by extending this timer.
EVENT_COOLDOWN_SECONDS = 60

# Bound the in-memory id set. Rows in the database remain the source of truth
# after a restart or after this window; 24h covers a Protect event's updates.
PROTECT_EVENT_ID_MEMORY_SECONDS = 24 * 60 * 60


@singleton
class ProtectEventFilter:
    """
    Filters and deduplicates UniFi Protect events.

    This class owns the filtering rules and deduplication state so that
    ProtectEventHandler can focus on event parsing, snapshot retrieval,
    and pipeline submission.
    """

    def __init__(self, cooldown_seconds: int = EVENT_COOLDOWN_SECONDS):
        self.cooldown_seconds = cooldown_seconds
        # Track last processed event time per camera for deduplication
        self._last_event_times: Dict[str, datetime] = {}
        # protect_event_id -> monotonic time it was reserved or last refreshed.
        self._seen_protect_event_ids: Dict[str, float] = {}
        # Detection types reported for an id whose row is not committed yet.
        self._pending_types: Dict[str, List[str]] = {}
        self._pending_ring: Dict[str, bool] = {}
        self._pending_at: Dict[str, float] = {}

    def should_process_event(
        self,
        filter_type: str,
        smart_detection_types: List[str],
        camera_name: str
    ) -> bool:
        """
        Check if event type should be processed based on camera filter config.

        Supports "all motion" mode when the filter list is empty or contains only "motion".
        """
        if not smart_detection_types or smart_detection_types == ["motion"]:
            logger.debug(
                f"Event passed filter for camera '{camera_name}': all-motion mode",
                extra={
                    "event_type": "protect_filter_passed",
                    "camera_name": camera_name,
                    "filter_type": filter_type,
                    "filter_reason": "all_motion_mode"
                }
            )
            return True

        if filter_type in smart_detection_types:
            logger.debug(
                f"Event passed filter for camera '{camera_name}': {filter_type} in filters",
                extra={
                    "event_type": "protect_filter_passed",
                    "camera_name": camera_name,
                    "filter_type": filter_type,
                    "configured_filters": smart_detection_types
                }
            )
            return True

        logger.debug(
            f"Event filtered for camera '{camera_name}': {filter_type} not in {smart_detection_types}",
            extra={
                "event_type": "protect_filter_rejected",
                "camera_name": camera_name,
                "filter_type": filter_type,
                "configured_filters": smart_detection_types,
                "filter_reason": "type_not_configured"
            }
        )
        return False

    def is_duplicate_event(self, camera_id: str, camera_name: str) -> bool:
        """
        Returns True if an event for this camera was processed too recently (within cooldown).
        """
        last_event_time = self._last_event_times.get(camera_id)
        if last_event_time is None:
            return False

        elapsed = (datetime.now(timezone.utc) - last_event_time).total_seconds()

        if elapsed < self.cooldown_seconds:
            logger.debug(
                f"Event deduplicated for camera '{camera_name}': {elapsed:.1f}s since last (cooldown: {self.cooldown_seconds}s)",
                extra={
                    "event_type": "protect_event_deduplicated",
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "seconds_since_last": elapsed,
                    "cooldown_seconds": self.cooldown_seconds
                }
            )
            return True

        return False

    def record_event(self, camera_id: str) -> None:
        """Record that an event was successfully processed for this camera (updates cooldown timer)."""
        self._last_event_times[camera_id] = datetime.now(timezone.utc)

    def clear_camera(self, camera_id: str) -> None:
        """Clear deduplication state for a camera (useful for testing or manual reset)."""
        self._last_event_times.pop(camera_id, None)

    def clear(self) -> None:
        """Clear cooldown timers and in-memory Protect event id reservations."""
        self._last_event_times.clear()
        self._seen_protect_event_ids.clear()
        self._pending_types.clear()
        self._pending_ring.clear()
        self._pending_at.clear()

    def _prune_protect_event_ids(self, now: float) -> None:
        cutoff = now - PROTECT_EVENT_ID_MEMORY_SECONDS
        stale_ids = [
            protect_event_id
            for protect_event_id, seen_at in self._seen_protect_event_ids.items()
            if seen_at < cutoff
        ]
        for protect_event_id in stale_ids:
            self._seen_protect_event_ids.pop(protect_event_id, None)
        stale_pending = [
            protect_event_id
            for protect_event_id, noted_at in self._pending_at.items()
            if noted_at < cutoff
        ]
        for protect_event_id in stale_pending:
            self._pending_types.pop(protect_event_id, None)
            self._pending_ring.pop(protect_event_id, None)
            self._pending_at.pop(protect_event_id, None)

    def is_protect_event_known(self, protect_event_id: str) -> bool:
        """Return True if this Protect id is reserved or was recently accepted."""
        if not protect_event_id:
            return False
        now = time.monotonic()
        self._prune_protect_event_ids(now)
        return str(protect_event_id) in self._seen_protect_event_ids

    def remember_protect_event_id(self, protect_event_id: str) -> None:
        """Refresh the in-memory reservation after the row is found in the database."""
        if not protect_event_id:
            return
        now = time.monotonic()
        self._prune_protect_event_ids(now)
        self._seen_protect_event_ids[str(protect_event_id)] = now

    def try_begin_protect_event(self, protect_event_id: str) -> bool:
        """Reserve a Protect id before AI work. False if it is already reserved.

        The check and insert happen with no await between them so two websocket
        tasks on the same loop cannot both win.
        """
        if not protect_event_id:
            return True
        now = time.monotonic()
        self._prune_protect_event_ids(now)
        key = str(protect_event_id)
        if key in self._seen_protect_event_ids:
            return False
        self._seen_protect_event_ids[key] = now
        return True

    def abandon_protect_event(self, protect_event_id: str) -> None:
        """Drop a reservation when no row was stored, so a later update can retry.

        Pending detection types are left in place. The retry applies them if it
        stores a row. They expire with PROTECT_EVENT_ID_MEMORY_SECONDS.
        """
        if not protect_event_id:
            return
        self._seen_protect_event_ids.pop(str(protect_event_id), None)

    def note_pending_protect_update(
        self,
        protect_event_id: str,
        detection_types: List[str],
        is_doorbell_ring: bool,
    ) -> None:
        """Remember types from an update that arrived before the row was committed."""
        if not protect_event_id:
            return
        key = str(protect_event_id)
        current = self._pending_types.setdefault(key, [])
        for detection_type in detection_types:
            if detection_type and detection_type not in current:
                current.append(detection_type)
        if is_doorbell_ring:
            self._pending_ring[key] = True
        self._pending_at[key] = time.monotonic()

    def take_pending_protect_update(
        self, protect_event_id: str
    ) -> Tuple[List[str], bool]:
        """Pop types queued for this id. Returns (types, is_doorbell_ring)."""
        if not protect_event_id:
            return [], False
        key = str(protect_event_id)
        types = self._pending_types.pop(key, [])
        is_ring = self._pending_ring.pop(key, False)
        self._pending_at.pop(key, None)
        return list(types), bool(is_ring)


# Backward compatible getter (delegates to @singleton decorator)
def get_protect_event_filter() -> "ProtectEventFilter":
    """
    Get the global ProtectEventFilter instance.

    Returns:
        ProtectEventFilter singleton instance

    Note: This is a backward-compatible wrapper. New code should prefer
          ProtectEventFilter() directly (the @singleton decorator guarantees
          the same instance).
    """
    return ProtectEventFilter()


def reset_protect_event_filter() -> None:
    """
    Reset the global ProtectEventFilter instance.

    Useful for testing to clear deduplication state.
    """
    ProtectEventFilter._reset_instance()