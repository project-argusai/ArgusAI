"""
AI Processing Coordinator

Orchestrates the processing of a single event through the AI pipeline.

Extracted from EventProcessor as part of Phase B (#443) to further
reduce the size and responsibility of the main EventProcessor class.

This coordinator owns the high-level flow:
- Cost cap checks
- Context / embedding generation
- AI description generation
- Storage
- Post-processing (alerts, notifications, entity updates, etc.)

Individual steps are still delegated to focused helper methods (many of which
remain on EventProcessor during the transition).
"""

import logging
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Callable, Awaitable, Any

from app.services.event_processor import ProcessingEvent

if TYPE_CHECKING:
    from app.services.ai_service import AIService
    from app.services.metrics import ProcessingMetrics

logger = logging.getLogger(__name__)


@dataclass
class ProcessingContext:
    """
    Explicit dependencies needed by AIProcessingCoordinator.

    This allows the coordinator to depend on a narrow interface instead of
    the entire EventProcessor, significantly improving decoupling and testability.
    """
    # Core services
    ai_service: "AIService"
    metrics: "ProcessingMetrics"

    # Focused helper methods (bound methods from EventProcessor)
    handle_cost_cap_skip: Callable[[ProcessingEvent], Awaitable[bool | None]]
    generate_thumbnail: Callable[[Any], Optional[str]]
    generate_and_match_entity: Callable[[Optional[str]], Awaitable[tuple[Any, Any]]]
    generate_ai_description: Callable[..., Awaitable[Any]]
    store_processed_event: Callable[..., Awaitable[Optional[str]]]
    send_push_notification: Callable[..., Awaitable[None]]
    publish_camera_status_sensors: Callable[..., Awaitable[None]]
    run_homekit_triggers: Callable[..., Awaitable[None]]
    link_entity_to_event: Callable[..., Awaitable[None]]
    process_face_embeddings: Callable[..., Awaitable[None]]
    process_vehicle_embeddings: Callable[..., Awaitable[None]]
    process_entity_alerts: Callable[..., Awaitable[None]]
    enrich_event_with_audio: Callable[[str, str], Awaitable[None]]
    publish_event_to_mqtt: Callable[..., Awaitable[None]]

    # Access to global services container (temporary during transition)
    get_container: Callable[[], Any]


class AIProcessingCoordinator:
    """
    Coordinates the end-to-end processing of one queued event.

    The goal is to eventually own the entire `_process_event` flow
    so that EventProcessor only needs to:
    - Manage the queue
    - Manage the worker pool
    - Own high-level lifecycle
    """

    def __init__(self, context: ProcessingContext):
        self.context = context
        self.ai_service = context.ai_service

    async def process_event(self, event: ProcessingEvent, worker_id: int) -> bool:
        """
        Main entry point. Processes one event through the full pipeline.

        During the transition, this delegates to EventProcessor's _process_event.
        Once the orchestration is fully moved here, it will use self.context directly.
        """
        # Temporary during transition — the real body will move into this method
        # in the next micro-step(s).
        # We still go through the processor so all existing helper methods continue to work.
        return await self.context.event_processor._process_event(event, worker_id)  # type: ignore[attr-defined]

