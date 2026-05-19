"""
ProtectEventFilter

Responsible for filtering and deduplicating Protect events before they reach the AI pipeline.

Handles:
- Per-camera smart detection type filtering ("person", "vehicle", etc.)
- "All motion" mode (empty filter or ["motion"])
- Deduplication using per-camera cooldown window

Extracted from ProtectEventHandler during Phase 4 of the decomposition.

# Migrated to @singleton decorator (core.decorators) as part of #450 (Lightweight DI Container).
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List

from app.core.decorators import singleton

logger = logging.getLogger(__name__)

# Default cooldown to prevent duplicate processing for the same camera
EVENT_COOLDOWN_SECONDS = 60


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