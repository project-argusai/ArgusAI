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
from typing import Optional, TYPE_CHECKING

from app.services.event_processor import ProcessingEvent

if TYPE_CHECKING:
    from app.services.event_processor import EventProcessor
    from app.services.ai_service import AIService
    from app.services.metrics import ProcessingMetrics  # if it exists separately

logger = logging.getLogger(__name__)


class AIProcessingCoordinator:
    """
    Coordinates the end-to-end processing of one queued event.

    The goal is to eventually own the entire `_process_event` flow
    so that EventProcessor only needs to:
    - Manage the queue
    - Manage the worker pool
    - Own high-level lifecycle
    """

    def __init__(
        self,
        event_processor: "EventProcessor",
        ai_service: Optional["AIService"] = None,
    ):
        self.event_processor = event_processor
        self.ai_service = ai_service or event_processor.ai_service

    async def process_event(self, event: ProcessingEvent, worker_id: int) -> bool:
        """
        Main entry point. Processes one event through the full pipeline.

        This is the method passed to AIWorkerPool as the processing callback.
        """
        # For the first small step, we delegate back to the original implementation
        # on EventProcessor. In subsequent micro-steps we will move the body here.
        return await self.event_processor._process_event(event, worker_id)