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
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, Awaitable

from app.models.camera import Camera
from app.services.camera_service import CameraService
from app.services.motion_detection_service import MotionDetectionService

# Forward import to avoid circular dependency
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.event_processor import ProcessingEvent

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
        # Callback to queue a ProcessingEvent back to the main processor
        queue_event_callback: Callable[["ProcessingEvent"], Awaitable[None]],
    ):
        self.camera_service = camera_service
        self.motion_service = motion_service
        self._queue_event = queue_event_callback

        # Internal state (private)
        self._motion_tasks: Dict[str, asyncio.Task] = {}  # camera_id -> task
        self._motion_task_stats: Dict[str, dict] = {}
        self._camera_cooldowns: Dict[str, float] = {}  # camera_id -> last_event_time

        # Shutdown coordination (replaces reliance on external self.running)
        self._shutdown_event = asyncio.Event()

    async def start_monitoring(self, camera: Camera):
        """
        Start a motion detection task for the given camera.
        The actual loop now lives inside this class.
        """
        if camera.id in self._motion_tasks:
            logger.warning(f"Camera {camera.id} already being monitored")
            return

        task = asyncio.create_task(
            self._run_motion_detection_loop(camera),
            name=f"motion_task_{camera.id}"
        )
        self._motion_tasks[camera.id] = task

        logger.info(f"Started monitoring camera: {camera.name} ({camera.id})")

    async def stop_monitoring(self, camera_id: str):
        """
        Stop motion detection task for a specific camera.
        """
        if camera_id not in self._motion_tasks:
            logger.warning(f"Camera {camera_id} not being monitored")
            return

        task = self._motion_tasks.pop(camera_id)
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
        return self._motion_task_stats.copy()

    def is_monitoring(self, camera_id: str) -> bool:
        """Check if a camera is currently being monitored."""
        return camera_id in self._motion_tasks

    def get_monitored_cameras(self) -> list[str]:
        """Return list of camera IDs currently being monitored."""
        return list(self._motion_tasks.keys())

    def record_frame_pulled(self, camera_id: str):
        """Helper for motion tasks to update stats."""
        stats = self._motion_task_stats.setdefault(camera_id, {})
        stats["frames_pulled"] = stats.get("frames_pulled", 0) + 1
        stats["last_frame_time"] = time.time()

    def record_motion_check(self, camera_id: str):
        stats = self._motion_task_stats.setdefault(camera_id, {})
        stats["motion_checks"] = stats.get("motion_checks", 0) + 1

    def record_error(self, camera_id: str):
        stats = self._motion_task_stats.setdefault(camera_id, {})
        stats["errors"] = stats.get("errors", 0) + 1

    def get_cooldown(self, camera_id: str) -> float:
        return self._camera_cooldowns.get(camera_id, 0.0)

    def update_cooldown(self, camera_id: str, timestamp: float):
        self._camera_cooldowns[camera_id] = timestamp

    def shutdown(self):
        """Signal all per-camera loops and health monitor to stop gracefully."""
        self._shutdown_event.set()

        if self._health_monitor_task and not self._health_monitor_task.done():
            self._health_monitor_task.cancel()

    async def stop_all(self):
        self.shutdown()  # Signal loops + health monitor to exit

        await self.stop_health_monitor()

        tasks = list(self._motion_tasks.values())
        self._motion_tasks.clear()

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._camera_cooldowns.clear()
        # Note: we intentionally keep motion_task_stats for observability after shutdown
        """Stop all active motion monitoring tasks (used during shutdown)."""
        tasks = list(self._motion_tasks.values())
        self._motion_tasks.clear()

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._camera_cooldowns.clear()
        # Note: we intentionally keep motion_task_stats for observability after shutdown

    async def _run_motion_detection_loop(self, camera: Camera):
        """
        Core per-camera motion detection loop (moved from EventProcessor).

        This method now lives fully inside CameraTaskManager.
        """
        logger.info(f"Motion detection task started for camera: {camera.name}")

        frame_interval = 1.0 / camera.frame_rate if camera.frame_rate > 0 else 0.2

        while not self._shutdown_event.is_set():
            try:
                # Check cooldown
                last_event_time = self.get_cooldown(camera.id)
                time_since_last_event = time.time() - last_event_time

                if time_since_last_event < camera.motion_cooldown:
                    await self._sleep_respecting_shutdown(frame_interval)
                    continue

                # === Real frame acquisition via CameraCaptureWorker (with backpressure) ===
                frame = None

                if self.camera_service:
                    worker_status = self.camera_service.get_camera_status(camera.id)
                    worker_alive = worker_status.get("worker_alive", False) if worker_status else False

                    if not worker_alive:
                        await self.handle_unhealthy_camera_worker(camera, context="motion_task")
                        continue

                    try:
                        frame = self.camera_service.get_frame(camera.id, timeout=0.2)
                    except Exception as e:
                        logger.debug(f"Failed to get frame from camera_service for {camera.id}: {e}")

                if frame is None:
                    await self._sleep_respecting_shutdown(frame_interval * 0.5)
                    continue

                # === Run motion detection ===
                try:
                    motion_result = self.motion_service.process_frame(
                        frame, camera_id=camera.id
                    )
                except Exception as e:
                    logger.warning(f"Motion detection failed for camera {camera.name}: {e}")
                    await asyncio.sleep(frame_interval)
                    continue

                if motion_result and motion_result.get("motion_detected"):
                    from app.services.event_processor import ProcessingEvent  # local import to avoid cycles

                    processing_event = ProcessingEvent(
                        camera_id=str(camera.id),
                        camera_name=camera.name,
                        frame=frame,
                        timestamp=datetime.now(timezone.utc),
                        detected_objects=motion_result.get("detected_objects", ["unknown"]),
                        metadata={
                            "motion_confidence": motion_result.get("confidence", 0.0),
                            "source": "camera_capture_worker",
                        },
                    )
                    await self._queue_event(processing_event)
                    logger.info(f"Motion event queued for camera {camera.name}")

                # Stats
                self.record_frame_pulled(camera.id)
                self.record_motion_check(camera.id)
                if frame is not None:
                    stats = self._motion_task_stats.get(camera.id, {})
                    if stats.get("recovery_attempts", 0) > 0:
                        stats["recovery_attempts"] = 0

                await asyncio.sleep(frame_interval)

            except asyncio.CancelledError:
                logger.info(f"Motion detection task cancelled for camera: {camera.name}")
                raise
            except Exception as e:
                logger.error(
                    f"Error in motion detection task for camera {camera.name}: {e}",
                    exc_info=True,
                    extra={"camera_id": camera.id, "camera_name": camera.name}
                )
                self.record_error(camera.id)
                await self._sleep_respecting_shutdown(10.0)

    async def _sleep_respecting_shutdown(self, seconds: float):
        """Sleep up to `seconds`, but return early if shutdown has been signaled."""
        if seconds <= 0:
            return
        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass  # normal expiration — continue the loop

    # ------------------------------------------------------------------
    # Health Monitor (moved from EventProcessor)
    # ------------------------------------------------------------------

    _health_monitor_task: Optional[asyncio.Task] = None

    def start_health_monitor(self):
        """Start the background camera health monitor task."""
        if self._health_monitor_task and not self._health_monitor_task.done():
            logger.warning("Health monitor already running")
            return

        self._health_monitor_task = asyncio.create_task(
            self._run_health_monitor(),
            name="camera_health_monitor"
        )
        logger.info("Camera health monitor started via CameraTaskManager")

    async def _run_health_monitor(self):
        """
        Background task that periodically checks camera capture workers
        and attempts to restart any that have died.

        This provides self-healing for camera connectivity issues.
        """
        logger.info("Camera health monitor started")

        while not self._shutdown_event.is_set():
            try:
                if self.camera_service:
                    all_status = self.camera_service.get_all_camera_status()

                    for camera_id, status in all_status.items():
                        if status.get("capture_disabled"):
                            continue  # Respect the stronger recovery policy

                        if not status.get("worker_alive", True):
                            try:
                                camera = self.camera_service.get_camera(camera_id)
                                if camera:
                                    await self.handle_unhealthy_camera_worker(
                                        camera, context="health_monitor"
                                    )
                            except Exception as e:
                                logger.error(
                                    f"Health monitor failed to handle unhealthy camera {camera_id}: {e}"
                                )

                await self._sleep_respecting_shutdown(30.0)

            except asyncio.CancelledError:
                logger.info("Camera health monitor cancelled")
                raise
            except Exception as e:
                logger.error(f"Error in camera health monitor: {e}")
                await self._sleep_respecting_shutdown(30.0)

    async def stop_health_monitor(self):
        """Stop the health monitor task."""
        if self._health_monitor_task and not self._health_monitor_task.done():
            self._health_monitor_task.cancel()
            try:
                await asyncio.wait_for(self._health_monitor_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._health_monitor_task = None
            logger.info("Camera health monitor stopped")
