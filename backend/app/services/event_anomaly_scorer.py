"""
EventAnomalyScorer

Owns the two fire-and-forget, post-storage tasks for a processed event:
- incremental activity-baseline updates (Story P4-7.1)
- per-event anomaly scoring (Story P4-7.2)

Both run as background tasks with their own DB session (the caller's session is
already closed by the time these run) and contain their own errors so they can
never fail or block event processing.

Extracted from EventProcessor during the Phase B decomposition (#530 / #443).
"""

import logging

from app.core.database import get_db_session
from app.core.decorators import singleton
from app.models.event import Event

logger = logging.getLogger(__name__)


def _get_container():
    """Lazy getter for the service container (avoids circular imports)."""
    from app.services.service_container import container
    return container


@singleton
class EventAnomalyScorer:
    """Post-storage activity-baseline and anomaly-scoring for events."""

    async def update_activity_baseline(self, camera_id: str, event: Event) -> None:
        """
        Update activity baseline for a camera (Story P4-7.1).

        Fire-and-forget; uses its own DB session; errors are logged, not propagated.
        """
        try:
            pattern_service = _get_container().pattern_service

            # Use own session since caller's may be closed
            with get_db_session() as db:
                await pattern_service.update_baseline_incremental(db, camera_id, event)

        except Exception as e:
            # Baseline errors must not propagate (AC3)
            logger.warning(
                f"Activity baseline update failed for camera {camera_id}: {e}",
                extra={
                    "event_type": "baseline_update_error",
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )

    async def calculate_anomaly_score(self, event: Event) -> None:
        """
        Calculate and persist anomaly score for an event (Story P4-7.2).

        Fire-and-forget; uses its own DB session; errors are logged, not propagated.
        Re-fetches the event in the new session before scoring.
        """
        try:
            anomaly_service = _get_container().anomaly_scoring_service

            # Use own session since caller's may be closed
            with get_db_session() as db:
                # Re-fetch event in new session
                event_in_session = db.query(Event).filter_by(id=event.id).first()
                if event_in_session:
                    await anomaly_service.score_event(db, event_in_session)

        except Exception as e:
            # Anomaly scoring errors must not propagate (AC7)
            logger.warning(
                f"Anomaly scoring failed for event {event.id}: {e}",
                extra={
                    "event_type": "anomaly_scoring_error",
                    "event_id": event.id,
                    "error": str(e)
                }
            )


# Backward compatible getter (delegates to @singleton decorator)
def get_event_anomaly_scorer() -> "EventAnomalyScorer":
    return EventAnomalyScorer()


def reset_event_anomaly_scorer() -> None:
    EventAnomalyScorer._reset_instance()
