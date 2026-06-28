"""
AI Processing Worker

Extracted from EventProcessor during Phase 6 decomposition.

Each worker pulls events from the shared queue and processes them through
the AI pipeline (_process_event).
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from app.services.event_processor import EventProcessor, ProcessingEvent

logger = logging.getLogger(__name__)


class AIProcessingWorker:
    """
    A single AI processing worker.

    Responsibilities:
    - Pull events from the shared asyncio.Queue
    - Call the processor's _process_event method
    - Update processing metrics
    - Handle errors with auto-restart (except CancelledError)
    - Respect the processor's running flag

    This class was extracted to make EventProcessor thinner and to make
    the worker logic easier to test and reason about in isolation.
    """

    def __init__(
        self,
        worker_id: int,
        event_queue: asyncio.Queue,
        *,
        process_event: Callable[["ProcessingEvent", int], Awaitable[bool]],
        metrics: "ProcessingMetrics",
        is_running: Callable[[], bool],
    ):
        self.worker_id = worker_id
        self.event_queue = event_queue
        self._process_event = process_event
        self.metrics = metrics
        self._is_running = is_running
        self.logger = logging.getLogger(__name__)

    async def run(self) -> None:
        """Main worker loop. Runs until the processor is no longer running."""
        self.logger.info(f"AI Worker {self.worker_id} started")

        while self._is_running():
            try:
                # Get event from queue (wait up to 1 second)
                try:
                    event: "ProcessingEvent" = await asyncio.wait_for(
                        self.event_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # No events available, continue polling
                    continue

                # Update queue depth metric
                self.metrics.queue_depth = self.event_queue.qsize()

                # Process the event
                start_time = time.time()
                success = await self._process_event(event, self.worker_id)
                duration_ms = (time.time() - start_time) * 1000

                # Record metrics
                self.metrics.record_processing_time(duration_ms)
                if success:
                    self.metrics.events_processed_success += 1
                else:
                    self.metrics.events_processed_failure += 1

                # Signal that the queue item has been fully processed
                self.event_queue.task_done()

                self.logger.info(
                    f"Worker {self.worker_id} processed event from {event.camera_name}",
                    extra={
                        "worker_id": self.worker_id,
                        "camera_id": event.camera_id,
                        "duration_ms": duration_ms,
                        "success": success,
                        "queue_depth": self.metrics.queue_depth,
                    },
                )

            except asyncio.CancelledError:
                self.logger.info(f"AI Worker {self.worker_id} cancelled")
                raise
            except Exception as e:
                self.logger.error(
                    f"AI Worker {self.worker_id} exception: {e}",
                    exc_info=True,
                    extra={"worker_id": self.worker_id},
                )
                self.metrics.increment_error("worker_exception")
                # Brief pause before retrying to avoid tight error loops
                await asyncio.sleep(1.0)

        self.logger.info(f"AI Worker {self.worker_id} stopped")
