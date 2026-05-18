"""
AIWorkerPool

Manages a pool of AIProcessingWorker instances.

Extracted as part of Phase B (#443) to reduce the size and complexity
of EventProcessor.
"""

import asyncio
import logging
import os
from typing import List, Optional, Callable, Awaitable, TYPE_CHECKING

from app.services.ai_processing_worker import AIProcessingWorker

if TYPE_CHECKING:
    from app.services.event_processor import ProcessingMetrics, ProcessingEvent

logger = logging.getLogger(__name__)


class AIWorkerPool:
    """
    Manages the lifecycle of AI processing workers.

    Responsibilities:
    - Creating and starting a configured number of AIProcessingWorker tasks
    - Graceful shutdown of all workers
    - Tracking worker tasks
    """

    def __init__(
        self,
        worker_count: int,
        event_queue: asyncio.Queue,
        *,
        # Callback for processing a single event (replaces passing the whole processor)
        process_event: Callable[["ProcessingEvent", int], Awaitable[bool]],
        metrics: "ProcessingMetrics",
        is_running: Callable[[], bool],
        ai_concurrent_limit: Optional[int] = None,
    ):
        self.worker_count = max(1, worker_count)
        self.event_queue = event_queue
        self._process_event = process_event
        self.metrics = metrics
        self._is_running = is_running

        # Concurrency control for AI calls (owned by the pool)
        ai_limit = ai_concurrent_limit or int(os.getenv("AI_CONCURRENT_LIMIT", "8"))
        self.ai_semaphore = asyncio.Semaphore(ai_limit)

        self._worker_tasks: List[asyncio.Task] = []
        self._running = False

    async def start(self):
        """Start all AI workers."""
        if self._running:
            logger.warning("AIWorkerPool already running")
            return

        self._worker_tasks = []
        for i in range(self.worker_count):
            worker = AIProcessingWorker(
                worker_id=i,
                event_queue=self.event_queue,
                process_event=self._process_event,
                metrics=self.metrics,
                is_running=self._is_running,
            )
            task = asyncio.create_task(worker.run(), name=f"ai_worker_{i}")
            self._worker_tasks.append(task)

        self._running = True
        logger.info(f"Started {self.worker_count} AI workers")

    async def stop(self, timeout: float = 30.0):
        """Stop all AI workers gracefully."""
        if not self._worker_tasks:
            return

        logger.info("Stopping AI workers...")

        for task in self._worker_tasks:
            if not task.done():
                task.cancel()

        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        self._worker_tasks.clear()
        self._running = False
        logger.info("AI workers stopped")

    @property
    def worker_tasks(self) -> List[asyncio.Task]:
        """Return the list of active worker tasks (for observability)."""
        return self._worker_tasks

    @property
    def is_running(self) -> bool:
        return self._running

    def active_worker_count(self) -> int:
        """Return how many worker tasks are currently alive (not done)."""
        return sum(1 for t in self._worker_tasks if not t.done())

    # Public attribute: concurrency semaphore for AI calls (owned by the pool).
    # Exposed so EventProcessor can do `async with self.ai_worker_pool.ai_semaphore:`
    ai_semaphore: asyncio.Semaphore