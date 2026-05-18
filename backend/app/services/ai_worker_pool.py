"""
AIWorkerPool

Manages a pool of AIProcessingWorker instances.

Extracted as part of Phase B (#443) to reduce the size and complexity
of EventProcessor.
"""

import asyncio
import logging
from typing import List, Optional, Callable, Awaitable

from app.services.ai_processing_worker import AIProcessingWorker

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
        # Callback that the workers will use to process events
        # (currently provided by EventProcessor)
        process_event_callback: Callable[[object, int], Awaitable[None]],
        ai_concurrent_limit: Optional[int] = None,
    ):
        self.worker_count = max(1, worker_count)
        self.event_queue = event_queue
        self._process_event = process_event_callback

        # Concurrency control for AI calls (can be moved here later)
        self.ai_semaphore = asyncio.Semaphore(
            ai_concurrent_limit or int(8)  # default, will be improved
        )

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
                processor=self,  # temporary until we fully decouple
            )
            # Note: AIProcessingWorker currently expects a 'processor' with
            # certain methods. We pass self for now during transition.
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

    # Temporary compatibility for AIProcessingWorker which still calls back
    # into the "processor". We forward the semaphore for now.
    @property
    def ai_semaphore(self):
        return self.ai_semaphore  # type: ignore[return-value]