"""
CameraTaskManager

Owns the lifecycle of per-camera motion detection tasks, stats,
cooldowns, and recovery logic.

Extracted as part of Phase B (#443) to reduce the size and complexity
of EventProcessor.
"""

import asyncio
import logging
import random
import time
from typing import Dict, Optional, Callable, Awaitable

from app.models.camera import Camera
from app.services.camera_service import CameraService
from app.services.motion_detection_service import MotionDetectionService

logger = logging.getLogger(__name__)


class CameraTaskManager:
    """
    Manages monitoring tasks for individual cameras.

    Responsibilities:
    - Starting and stopping per-camera motion detection tasks
    - Tracking per-camera stats (frames, errors, recovery attempts)
    - Cooldown enforcement between events
    - Centralized recovery for unhealthy camera workers
    """

    def __init__(
        self,
        camera_service: CameraService,
        motion_service: MotionDetectionService,
        # Factory provided by the owner (currently EventProcessor) that
        # runs the actual motion detection loop for one camera.
        motion_task_factory: Callable[[Camera], Awaitable[None]],
    ):
        self.camera_service = camera_service
        self.motion_service = motion_service
        self._motion_task_factory = motion_task_factory

        # Internal state (was previously on EventProcessor)
        self.motion_tasks: Dict[str, asyncio.Task] = {}  # camera_id -> task
        self.motion_task_stats: Dict[str, dict] = {}
        self.camera_cooldowns: Dict[str, float] = {}  # camera_id -> last_event_time

    async def start_monitoring(self, camera: Camera):
        """
        Start a motion detection task for the given camera.
        """
        if camera.id in self.motion_tasks:
            logger.warning(f"Camera {camera.id} already being monitored")
            return

        task = asyncio.create_task(
            self._motion_task_factory(camera),
            name=f"motion_task_{camera.id}"
        )
        self.motion_tasks[camera.id] = task

        logger.info(f"Started monitoring camera: {camera.name} ({camera.id})")

    async def stop_monitoring(self, camera_id: str):
        """
        Stop motion detection task for a specific camera.
        """
        if camera_id not in self.motion_tasks:
            logger.warning(f"Camera {camera_id} not being monitored")
            return

        task = self.motion_tasks.pop(camera_id)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Clean up cooldown as well
        self.camera_cooldowns.pop(camera_id, None)

        logger.info(f"Stopped monitoring camera: {camera_id}")

    async def handle_unhealthy_camera_worker(self, camera: Camera, context: str = "motion_task"):
        """
        Centralized logic for handling a camera whose capture worker is unhealthy.

        Shared between per-camera motion tasks and the background health monitor.
        """
        stats = self.motion_task_stats.setdefault(camera.id, {})
        recovery_attempts = stats.get("recovery_attempts", 0) + 1
        stats["recovery_attempts"] = recovery_attempts

        logger.warning(
            f"Camera {camera.name} has no healthy capture worker (context={context}, attempt={recovery_attempts})"
        )

        if recovery_attempts <= 5:  # Align with CameraService.MAX_RESTART_ATTEMPTS
            try:
                self.camera_service.restart_camera(camera)
                logger.info(f"Recovery restart triggered for {camera.name} (attempt {recovery_attempts})")
            except Exception as e:
                logger.error(f"Recovery restart failed for {camera.name}: {e}")

        # Exponential backoff with jitter (capped)
        backoff = min(4.0 * (2 ** min(recovery_attempts - 1, 5)), 90)
        jitter = random.uniform(0, 2.0)
        await asyncio.sleep(backoff + jitter)

    def get_motion_task_stats(self) -> Dict[str, dict]:
        """Return a copy of per-camera motion task statistics."""
        return self.motion_task_stats.copy()

    def record_frame_pulled(self, camera_id: str):
        """Helper for motion tasks to update stats."""
        stats = self.motion_task_stats.setdefault(camera_id, {})
        stats["frames_pulled"] = stats.get("frames_pulled", 0) + 1
        stats["last_frame_time"] = time.time()

    def record_motion_check(self, camera_id: str):
        stats = self.motion_task_stats.setdefault(camera_id, {})
        stats["motion_checks"] = stats.get("motion_checks", 0) + 1

    def record_error(self, camera_id: str):
        stats = self.motion_task_stats.setdefault(camera_id, {})
        stats["errors"] = stats.get("errors", 0) + 1

    def get_cooldown(self, camera_id: str) -> float:
        return self.camera_cooldowns.get(camera_id, 0.0)

    def update_cooldown(self, camera_id: str, timestamp: float):
        self.camera_cooldowns[camera_id] = timestamp

    async def stop_all(self):
        """Stop all active motion monitoring tasks (used during shutdown)."""
        tasks = list(self.motion_tasks.values())
        self.motion_tasks.clear()

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.camera_cooldowns.clear()
        # Note: we intentionally keep motion_task_stats for observability after shutdown
