"""
Multi-Camera Event Correlation Service (Story P2-4.3)

Detects when multiple cameras capture the same real-world event by
correlating events within a configurable time window.

Correlation Algorithm:
1. Event arrives → Add to 60-second buffer
2. Scan buffer for candidates (O(n) where n = events in last 60s)
3. If candidates found:
   - Check if any have correlation_group_id
   - If yes: join that group
   - If no: generate new group_id for all
4. Update all correlated events in database
5. Remove old events from buffer (>60 seconds old)

Event Flow Integration:
    _store_protect_event() completes
            ↓
    asyncio.create_task(correlation_service.process_event(event))
            ↓
    Fire-and-forget: doesn't block event creation

Correlation Criteria (AC2):
- Time window: within configurable seconds (default 10)
- Same or similar smart_detection_type (person→person, vehicle→vehicle)
- Different cameras (exclude same camera)
- Same controller (for stricter correlation, future enhancement)

Migrated to @singleton: Story P14-5.3
"""

import asyncio
import json
import logging
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
DEFAULT_TIME_WINDOW_SECONDS = 10  # Correlation window (AC2)
DEFAULT_BUFFER_MAX_AGE_SECONDS = 60  # Buffer retention period (AC5)


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
        time_window_seconds: Time window for correlation matching
        buffer_max_age_seconds: How long to keep events in buffer
        _buffer: Deque of (timestamp, BufferedEvent) tuples
    """

    def __init__(
        self,
        time_window_seconds: int = DEFAULT_TIME_WINDOW_SECONDS,
        buffer_max_age_seconds: int = DEFAULT_BUFFER_MAX_AGE_SECONDS
    ):
        """
        Initialize correlation service.

        Args:
            time_window_seconds: Time window for correlation (default 10s, AC2)
            buffer_max_age_seconds: Buffer retention period (default 60s, AC5)
        """
        self.time_window_seconds = time_window_seconds
        self.buffer_max_age_seconds = buffer_max_age_seconds
        self._buffer: deque[Tuple[datetime, BufferedEvent]] = deque()

        logger.info(
            f"CorrelationService initialized: time_window={time_window_seconds}s, "
            f"buffer_max_age={buffer_max_age_seconds}s",
            extra={
                "event_type": "correlation_service_init",
                "time_window_seconds": time_window_seconds,
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
        - Within time_window_seconds of the event timestamp
        - Same or similar smart_detection_type
        - Different camera (same camera events never correlate)
        - (Future: Same controller for stricter correlation)

        Args:
            event: Event to find correlations for

        Returns:
            List of BufferedEvents that correlate with the input event
        """
        candidates = []
        event_time = event.timestamp
        window = timedelta(seconds=self.time_window_seconds)

        for _, buffered in self._buffer:
            # Skip self
            if buffered.id == event.id:
                continue

            # AC2: Different cameras only (same camera never correlates)
            if buffered.camera_id == event.camera_id:
                continue

            # AC2: Time window check
            time_diff = abs((buffered.timestamp - event_time).total_seconds())
            if time_diff > self.time_window_seconds:
                continue

            # AC2: Same or similar detection type
            if not self._detection_types_match(event.smart_detection_type, buffered.smart_detection_type):
                continue

            # (Future: Same controller check for stricter correlation)
            # if event.protect_controller_id and buffered.protect_controller_id:
            #     if event.protect_controller_id != buffered.protect_controller_id:
            #         continue

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

    def _detection_types_match(self, type1: Optional[str], type2: Optional[str]) -> bool:
        """
        Check if two detection types are compatible for correlation (AC2).

        Currently requires exact match. Future enhancement could allow
        related types (e.g., person correlates with package for delivery).

        Args:
            type1: First detection type
            type2: Second detection type

        Returns:
            True if types match for correlation purposes
        """
        # Null types don't correlate (motion-only events)
        if type1 is None or type2 is None:
            return False

        # Exact match for now
        return type1.lower() == type2.lower()

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
