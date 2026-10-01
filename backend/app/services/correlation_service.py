"""
Multi-Camera Event Correlation Service (Story P2-4.3)

Detects when multiple cameras capture the same real-world event by
correlating events within a configurable time window.

Persisted grouping (issue #642) uses ``assign_group`` after the event row
is committed. It queries other cameras by detection timestamp. It does not
wait for more cameras, does not call the vision model, and does not delete
or rewrite the per-camera rows.

The in-memory buffer and ``process_event`` remain for the original
single-process scan. The Protect handler used to call
``correlation_service.process``, which was never a method on this class
(the method is ``process_event``). That call was commented out in the May
2026 decomposition (``1af9f8a``) and is not the production path.

Correlation criteria:
- Time window: configurable seconds (default 2, env ``CORRELATION_WINDOW_SECONDS``)
- Different cameras only (same-camera Protect dedup is unchanged)
- Detection type is not a join key: one activity is often labeled differently
  on each camera (vehicle on the driveway, motion at the garage)

# Migrated to @singleton: Story P14-5.3
"""

import asyncio
import json
import logging
import os
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.decorators import singleton

if TYPE_CHECKING:
    from app.models.event import Event

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_TIME_WINDOW_SECONDS = 2  # Cross-camera incident window (issue #642)
MAX_CORRELATION_WINDOW_SECONDS = 30  # Cap so a bad config cannot glue the day together
DEFAULT_BUFFER_MAX_AGE_SECONDS = 60  # Buffer retention period (AC5)


def clamp_correlation_window(value: float) -> float:
    """Return a window in (0, MAX]. Non-positive values use the default."""
    if value <= 0:
        return float(DEFAULT_TIME_WINDOW_SECONDS)
    if value > MAX_CORRELATION_WINDOW_SECONDS:
        return float(MAX_CORRELATION_WINDOW_SECONDS)
    return float(value)


def resolve_correlation_window(explicit: Optional[float] = None) -> float:
    """Window from an explicit argument, else ``CORRELATION_WINDOW_SECONDS``.

    A missing or non-numeric environment value uses the default. The service
    keeps running; it does not open an unbounded window.
    """
    if explicit is not None:
        return clamp_correlation_window(explicit)
    raw = os.environ.get("CORRELATION_WINDOW_SECONDS", "").strip()
    if not raw:
        return float(DEFAULT_TIME_WINDOW_SECONDS)
    try:
        parsed = float(raw)
    except ValueError:
        logger.warning(
            "Invalid CORRELATION_WINDOW_SECONDS; using the default window",
            extra={"event_type": "correlation_window_invalid"},
        )
        return float(DEFAULT_TIME_WINDOW_SECONDS)
    return clamp_correlation_window(parsed)


def _as_utc(ts: datetime) -> datetime:
    """Normalize a stored timestamp to timezone-aware UTC."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


@dataclass
class BufferedEvent:
    """
    Lightweight event data stored in the correlation buffer.

    Only stores fields needed for correlation matching to minimize memory usage.
    """
    id: str
    camera_id: str
    timestamp: datetime
    smart_detection_type: Optional[str]
    correlation_group_id: Optional[str]
    # Optional: controller_id for future multi-controller correlation
    protect_controller_id: Optional[str] = None


@singleton
class CorrelationService:
    """
    Multi-camera event correlation service (Story P2-4.3).

    Maintains an in-memory buffer of recent events and correlates new events
    with existing ones based on time window and detection type.

    Thread Safety:
        Buffer operations are not thread-safe. In production, events are
        processed sequentially through the async event loop.

    Performance:
        - Buffer cleanup: O(k) where k = expired events
        - Candidate search: O(n) where n = events in buffer
        - Target: < 10ms for 1000 events in buffer (AC5)

    Attributes:
            time_window_seconds: Time window for correlation matching (default 2s)
        buffer_max_age_seconds: How long to keep events in buffer
        _buffer: Deque of (timestamp, BufferedEvent) tuples
    """

    def __init__(
        self,
        time_window_seconds: Optional[float] = None,
        buffer_max_age_seconds: int = DEFAULT_BUFFER_MAX_AGE_SECONDS
    ):
        """
        Initialize correlation service.

        Args:
            time_window_seconds: Time window for correlation. None reads
                CORRELATION_WINDOW_SECONDS (default 2s).
            buffer_max_age_seconds: Buffer retention period (default 60s, AC5)
        """
        self.time_window_seconds = resolve_correlation_window(time_window_seconds)
        self.buffer_max_age_seconds = buffer_max_age_seconds
        self._buffer: deque[Tuple[datetime, BufferedEvent]] = deque()
        self._lock = asyncio.Lock()

        logger.info(
            f"CorrelationService initialized: time_window={self.time_window_seconds}s, "
            f"buffer_max_age={buffer_max_age_seconds}s",
            extra={
                "event_type": "correlation_service_init",
                "time_window_seconds": self.time_window_seconds,
                "buffer_max_age_seconds": buffer_max_age_seconds
            }
        )

    def _cleanup_buffer(self) -> int:
        """
        Remove expired events from buffer (AC5).

        Events older than buffer_max_age_seconds are removed from the front
        of the deque (oldest first).

        Returns:
            Number of events removed
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.buffer_max_age_seconds)
        removed = 0

        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()
            removed += 1

        if removed > 0:
            logger.debug(
                f"Buffer cleanup: removed {removed} expired events",
                extra={
                    "event_type": "correlation_buffer_cleanup",
                    "removed_count": removed,
                    "buffer_size": len(self._buffer)
                }
            )

        return removed

    def add_to_buffer(self, event: "Event") -> BufferedEvent:
        """
        Add event to correlation buffer (AC5).

        Performs cleanup before adding to prevent unbounded growth.

        Args:
            event: Event model to buffer

        Returns:
            BufferedEvent representation added to buffer
        """
        self._cleanup_buffer()

        buffered = BufferedEvent(
            id=event.id,
            camera_id=event.camera_id,
            timestamp=event.timestamp,
            smart_detection_type=event.smart_detection_type,
            correlation_group_id=event.correlation_group_id,
            # Get controller_id from camera relationship if available
            protect_controller_id=getattr(event.camera, 'protect_controller_id', None) if hasattr(event, 'camera') else None
        )

        # Use event timestamp for buffer ordering, fallback to now
        buffer_time = event.timestamp if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)
        self._buffer.append((buffer_time, buffered))

        logger.debug(
            f"Event added to buffer: {event.id[:8]}...",
            extra={
                "event_type": "correlation_event_buffered",
                "event_id": event.id,
                "camera_id": event.camera_id,
                "detection_type": event.smart_detection_type,
                "buffer_size": len(self._buffer)
            }
        )

        return buffered

    def find_correlation_candidates(self, event: BufferedEvent) -> List[BufferedEvent]:
        """
        Find events that correlate with the given event (AC1, AC2, AC5).

        Correlation criteria:
        - Within time_window_seconds of the event timestamp (inclusive)
        - Different camera (same camera events never correlate)

        Args:
            event: Event to find correlations for

        Returns:
            List of BufferedEvents that correlate with the input event
        """
        candidates = []
        event_time = _as_utc(event.timestamp)

        for _, buffered in self._buffer:
            # Skip self
            if buffered.id == event.id:
                continue

            # Different cameras only (same camera never correlates)
            if buffered.camera_id == event.camera_id:
                continue

            time_diff = abs((_as_utc(buffered.timestamp) - event_time).total_seconds())
            if time_diff > self.time_window_seconds:
                continue

            candidates.append(buffered)

        logger.debug(
            f"Found {len(candidates)} correlation candidates for event {event.id[:8]}...",
            extra={
                "event_type": "correlation_candidates_found",
                "event_id": event.id,
                "candidate_count": len(candidates),
                "detection_type": event.smart_detection_type
            }
        )

        return candidates

    def _candidate_rows(self, db: Session, event: "Event") -> List["Event"]:
        """Other cameras' events whose detection time is inside the window."""
        from app.models.event import Event

        timestamp = _as_utc(event.timestamp)
        window = timedelta(seconds=self.time_window_seconds)
        rows = (
            db.query(Event)
            .filter(
                Event.id != event.id,
                Event.camera_id != event.camera_id,
                Event.timestamp >= timestamp - window,
                Event.timestamp <= timestamp + window,
            )
            .all()
        )
        return [
            row
            for row in rows
            if abs((_as_utc(row.timestamp) - timestamp).total_seconds())
            <= self.time_window_seconds
        ]

    def _assign_group_locked(self, db: Session, event: "Event") -> Optional[str]:
        """Link ``event`` to other cameras inside the window. Caller holds the lock.

        Writes only ``correlation_group_id`` and ``correlated_event_ids``.
        Per-camera descriptions, frames, and thumbnails stay as stored.
        Returns the group id, or None when this event stands alone.
        """
        from app.models.event import Event

        if event.timestamp is None or not event.id or not event.camera_id:
            return None

        candidates = self._candidate_rows(db, event)
        if not candidates:
            return event.correlation_group_id

        ordered = sorted(
            candidates,
            key=lambda row: (_as_utc(row.timestamp), row.id),
        )
        group_id = next(
            (row.correlation_group_id for row in ordered if row.correlation_group_id),
            None,
        )
        if group_id is None:
            group_id = event.correlation_group_id or str(uuid.uuid4())

        member_ids = {event.id}
        member_ids.update(row.id for row in candidates)
        group_ids = {group_id}
        group_ids.update(
            row.correlation_group_id
            for row in candidates
            if row.correlation_group_id
        )
        existing = (
            db.query(Event.id)
            .filter(Event.correlation_group_id.in_(group_ids))
            .all()
        )
        member_ids.update(row_id for (row_id,) in existing)

        member_list = sorted(member_ids)
        db.execute(
            update(Event)
            .where(Event.id.in_(member_list))
            .values(
                correlation_group_id=group_id,
                correlated_event_ids=json.dumps(member_list),
            )
        )
        db.commit()
        event.correlation_group_id = group_id
        event.correlated_event_ids = json.dumps(member_list)
        return group_id

    async def assign_group(self, db: Session, event: "Event") -> Optional[str]:
        """Persist a cross-camera incident id for an already-stored event.

        Serialized with an asyncio lock so two cameras that finish AI at the
        same time join one group. This does not perform AI work.
        """
        async with self._lock:
            try:
                return self._assign_group_locked(db, event)
            except Exception as exc:
                db.rollback()
                logger.warning(
                    "Failed to assign correlation group",
                    extra={
                        "event_type": "correlation_assign_failed",
                        "event_id": getattr(event, "id", None),
                        "error_type": type(exc).__name__,
                    },
                )
                return None

    def determine_correlation_group(
        self,
        event: BufferedEvent,
        candidates: List[BufferedEvent]
    ) -> Tuple[str, List[str]]:
        """
        Determine correlation group ID and member list (AC3, AC4, AC7, AC8).

        Logic:
        - If any candidate has a group_id, join that group (AC7)
        - If no candidates have group_id, create new group (AC3)
        - Build list of all correlated event IDs (AC4)

        Args:
            event: The new event being processed
            candidates: Events that correlate with this event

        Returns:
            Tuple of (group_id, list of all event IDs in group)
        """
        # Collect all event IDs including the new event
        all_event_ids = [event.id] + [c.id for c in candidates]

        # Check if any candidate already has a correlation group (AC7)
        existing_group_id = None
        for candidate in candidates:
            if candidate.correlation_group_id:
                existing_group_id = candidate.correlation_group_id
                break

        # Use existing group or create new one (AC3, AC8)
        group_id = existing_group_id or str(uuid.uuid4())

        logger.info(
            f"Correlation group determined: {group_id[:8]}... with {len(all_event_ids)} events",
            extra={
                "event_type": "correlation_group_determined",
                "group_id": group_id,
                "event_count": len(all_event_ids),
                "is_new_group": existing_group_id is None
            }
        )

        return group_id, all_event_ids

    async def update_correlation_in_db(
        self,
        event_ids: List[str],
        group_id: str
    ) -> int:
        """
        Update database records with correlation data (AC3, AC4, AC7).

        Updates all events in the correlation group with:
        - correlation_group_id: The shared group UUID
        - correlated_event_ids: JSON array of all related event IDs

        Args:
            event_ids: List of event IDs in the correlation group
            group_id: UUID for the correlation group

        Returns:
            Number of events updated
        """
        from app.models.event import Event

        # Build the correlated_event_ids JSON array
        correlated_ids_json = json.dumps(event_ids)

        db: Session = SessionLocal()
        try:
            # Update all events in the group (AC3, AC4)
            result = db.execute(
                update(Event)
                .where(Event.id.in_(event_ids))
                .values(
                    correlation_group_id=group_id,
                    correlated_event_ids=correlated_ids_json
                )
            )
            db.commit()

            updated_count = result.rowcount

            logger.info(
                f"Updated {updated_count} events with correlation group {group_id[:8]}...",
                extra={
                    "event_type": "correlation_db_updated",
                    "group_id": group_id,
                    "event_ids": event_ids,
                    "updated_count": updated_count
                }
            )

            return updated_count

        except Exception as e:
            db.rollback()
            logger.error(
                f"Failed to update correlation in database: {e}",
                extra={
                    "event_type": "correlation_db_error",
                    "group_id": group_id,
                    "event_ids": event_ids,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            raise
        finally:
            db.close()

    def update_buffer_with_correlation(self, event_id: str, group_id: str) -> None:
        """
        Update buffered event with correlation group ID.

        This ensures subsequent events can join an existing group
        even before the database update completes.

        Args:
            event_id: Event ID to update
            group_id: Correlation group ID to set
        """
        for _, buffered in self._buffer:
            if buffered.id == event_id:
                buffered.correlation_group_id = group_id
                break

    async def process_event(self, event: "Event") -> Optional[str]:
        """
        Process an event for correlation (AC1, AC6).

        This is the main entry point called after event storage.
        Uses fire-and-forget pattern - caller should use asyncio.create_task().

        Process:
        1. Add event to buffer
        2. Find correlation candidates
        3. If candidates found, determine group and update database
        4. Update buffer with correlation info

        Args:
            event: Event model to process

        Returns:
            Correlation group ID if correlated, None otherwise
        """
        try:
            # Add to buffer
            buffered = self.add_to_buffer(event)

            # Find candidates
            candidates = self.find_correlation_candidates(buffered)

            if not candidates:
                logger.debug(
                    f"No correlations found for event {event.id[:8]}...",
                    extra={
                        "event_type": "correlation_none_found",
                        "event_id": event.id,
                        "camera_id": event.camera_id
                    }
                )
                return None

            # Determine group
            group_id, all_event_ids = self.determine_correlation_group(buffered, candidates)

            # Update buffer immediately for subsequent correlations
            for eid in all_event_ids:
                self.update_buffer_with_correlation(eid, group_id)

            # Update database asynchronously
            await self.update_correlation_in_db(all_event_ids, group_id)

            logger.info(
                f"Event {event.id[:8]}... correlated with {len(candidates)} other events",
                extra={
                    "event_type": "correlation_completed",
                    "event_id": event.id,
                    "group_id": group_id,
                    "correlated_count": len(candidates)
                }
            )

            return group_id

        except Exception as e:
            logger.error(
                f"Error processing event for correlation: {e}",
                extra={
                    "event_type": "correlation_process_error",
                    "event_id": event.id if event else "unknown",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

    def get_buffer_stats(self) -> Dict:
        """
        Get buffer statistics for monitoring.

        Returns:
            Dict with buffer stats (size, oldest event age, etc.)
        """
        self._cleanup_buffer()

        if not self._buffer:
            return {
                "buffer_size": 0,
                "oldest_event_age_seconds": None,
                "newest_event_age_seconds": None
            }

        now = datetime.now(timezone.utc)
        oldest_time, _ = self._buffer[0]
        newest_time, _ = self._buffer[-1]

        return {
            "buffer_size": len(self._buffer),
            "oldest_event_age_seconds": (now - oldest_time).total_seconds(),
            "newest_event_age_seconds": (now - newest_time).total_seconds(),
            "time_window_seconds": self.time_window_seconds,
            "buffer_max_age_seconds": self.buffer_max_age_seconds
        }

    def clear_buffer(self) -> int:
        """
        Clear the correlation buffer (useful for testing).

        Returns:
            Number of events cleared
        """
        if self._buffer is None:
            self._buffer = deque()
            return 0
        count = len(self._buffer)
        self._buffer.clear()
        return count


# Backward compatible getter (delegates to @singleton decorator)
def get_correlation_service() -> CorrelationService:
    """
    Get the global CorrelationService singleton instance.

    Returns:
        CorrelationService instance

    Note: This is a backward-compatible wrapper. New code should use
          CorrelationService() directly, which returns the singleton instance.
    """
    return CorrelationService()


def reset_correlation_service() -> None:
    """
    Reset the correlation service singleton (for testing).

    Note: This is a backward-compatible wrapper. New code should use
          CorrelationService._reset_instance() directly.
    """
    instance = CorrelationService._get_instance()
    if instance is not None:
        instance.clear_buffer()
    CorrelationService._reset_instance()
