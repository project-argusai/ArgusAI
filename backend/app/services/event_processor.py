"""
Event-Driven Processing Pipeline

This module implements an asynchronous event processing pipeline that orchestrates
motion detection, AI analysis, and event storage with a queue-based worker pattern.

Architecture:
    - asyncio.Queue (maxsize=50) for event buffering
    - Separate async tasks for each enabled camera (motion detection)
    - Configurable worker pool (2-5 workers) for AI processing
    - Non-blocking database operations via httpx AsyncClient
    - Graceful shutdown with queue draining (30s timeout)

Flow:
    Motion detected → Frame captured → Event queued →
    Worker picks event → AI API call → Description received →
    Event stored in database → Alert rules evaluated (stub) →
    WebSocket broadcast (stub) → Worker ready for next

Performance Targets:
    - End-to-end latency: <5s p95 (motion → stored event)
    - Throughput: 10+ events per minute
    - Queue depth: Typically <5 events under normal load
"""
import asyncio
import logging
import time
import httpx
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from contextlib import asynccontextmanager
import os
import json

from app.models.camera import Camera
from app.services.ai_service import AIService
from app.services.camera_service import CameraService
from app.services.motion_detection_service import MotionDetectionService
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


@dataclass
class ProcessingEvent:
    """
    Event data structure for queue processing

    Attributes:
        camera_id: UUID of camera that detected motion
        camera_name: Human-readable camera name
        frame: OpenCV frame (numpy array BGR format)
        timestamp: When motion was detected (UTC)
        detected_objects: List of detected object types (from motion detection)
        metadata: Additional context (motion confidence, zone, etc.)
    """
    camera_id: str
    camera_name: str
    frame: np.ndarray
    timestamp: datetime
    detected_objects: List[str] = field(default_factory=lambda: ["unknown"])
    metadata: Dict = field(default_factory=dict)


@dataclass
class ProcessingMetrics:
    """
    Metrics tracking for pipeline monitoring

    Tracks:
        - Queue depth (current size)
        - Events processed (success/failure counts)
        - Processing time distribution (p50, p95, p99)
        - Error counts by type
    """
    queue_depth: int = 0
    events_processed_success: int = 0
    events_processed_failure: int = 0
    processing_times_ms: List[float] = field(default_factory=list)
    pipeline_errors: Dict[str, int] = field(default_factory=dict)

    def record_processing_time(self, duration_ms: float):
        """Record processing time and maintain last 1000 samples"""
        self.processing_times_ms.append(duration_ms)
        if len(self.processing_times_ms) > 1000:
            self.processing_times_ms = self.processing_times_ms[-1000:]

    def get_percentiles(self) -> Dict[str, float]:
        """Calculate p50, p95, p99 percentiles"""
        if not self.processing_times_ms:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_times = sorted(self.processing_times_ms)
        n = len(sorted_times)

        return {
            "p50": sorted_times[int(n * 0.50)] if n > 0 else 0.0,
            "p95": sorted_times[int(n * 0.95)] if n > 0 else 0.0,
            "p99": sorted_times[int(n * 0.99)] if n > 0 else 0.0,
        }

    def increment_error(self, error_type: str):
        """Increment error counter for specific error type"""
        self.pipeline_errors[error_type] = self.pipeline_errors.get(error_type, 0) + 1

    def to_dict(self) -> Dict:
        """Export metrics as dictionary for API response"""
        percentiles = self.get_percentiles()
        return {
            "queue_depth": self.queue_depth,
            "events_processed": {
                "success": self.events_processed_success,
                "failure": self.events_processed_failure,
                "total": self.events_processed_success + self.events_processed_failure
            },
            "processing_time_ms": percentiles,
            "pipeline_errors": self.pipeline_errors
        }


class EventProcessor:
    """
    Main event processing pipeline orchestrator

    Manages:
        - Event queue (asyncio.Queue with maxsize=50)
        - Motion detection tasks (one per enabled camera)
        - AI worker pool (configurable 2-5 workers)
        - Graceful shutdown with queue draining
        - Metrics tracking

    Usage:
        processor = EventProcessor(worker_count=2)
        await processor.start()
        # ... application runs ...
        await processor.stop(timeout=30.0)
    """

    def __init__(
        self,
        worker_count: Optional[int] = None,
        queue_maxsize: int = 50,
    ):
        """
        Initialize EventProcessor

        Args:
            worker_count: Number of AI workers (default from env, fallback to 2)
            queue_maxsize: Maximum queue size (default 50)
        """
        self.worker_count = worker_count or int(os.getenv("EVENT_WORKER_COUNT", "2"))
        if self.worker_count < 2 or self.worker_count > 5:
            logger.warning(f"Worker count {self.worker_count} out of range [2-5], clamping")
            self.worker_count = max(2, min(5, self.worker_count))

        self.queue_maxsize = queue_maxsize
        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)

        # Task tracking
        self.motion_tasks: Dict[str, asyncio.Task] = {}  # camera_id -> task
        self.worker_tasks: List[asyncio.Task] = []
        self.camera_cooldowns: Dict[str, float] = {}  # camera_id -> last_event_time

        # Services
        self.ai_service: Optional[AIService] = None
        self.camera_service: Optional[CameraService] = None
        self.motion_service: Optional[MotionDetectionService] = None
        self.http_client: Optional[httpx.AsyncClient] = None

        # State tracking
        self.running = False
        self.shutdown_event = asyncio.Event()

        # Metrics
        self.metrics = ProcessingMetrics()

        logger.info(f"EventProcessor initialized: {self.worker_count} workers, queue max {self.queue_maxsize}")

    async def start(self):
        """
        Start the event processing pipeline

        - Initializes AI service and HTTP client
        - Starts AI worker pool
        - Starts motion detection tasks for enabled cameras
        """
        if self.running:
            logger.warning("EventProcessor already running")
            return

        logger.info("Starting EventProcessor...")
        self.running = True
        self.shutdown_event.clear()

        # Initialize services
        self.ai_service = AIService()
        self.http_client = httpx.AsyncClient(timeout=10.0)

        # Load AI API keys from database
        db = SessionLocal()
        try:
            await self.ai_service.load_api_keys_from_db(db)
            logger.info("AI service API keys loaded from database")
        finally:
            db.close()

        # Start AI worker pool
        for i in range(self.worker_count):
            worker_task = asyncio.create_task(
                self._ai_worker(worker_id=i),
                name=f"ai_worker_{i}"
            )
            self.worker_tasks.append(worker_task)

        logger.info(f"Started {self.worker_count} AI workers")

        # Start motion detection tasks for enabled cameras
        # Note: This will be called from FastAPI lifespan after camera service is initialized
        # For now, we'll load cameras from database
        db = SessionLocal()
        try:
            enabled_cameras = db.query(Camera).filter(
                Camera.is_enabled == True,
                Camera.motion_enabled == True
            ).all()

            for camera in enabled_cameras:
                await self.start_camera_monitoring(camera)

            logger.info(f"Started monitoring {len(enabled_cameras)} enabled cameras")
        except Exception as e:
            logger.error(f"Failed to load enabled cameras: {e}", exc_info=True)
        finally:
            db.close()

        logger.info("EventProcessor started successfully")

    async def stop(self, timeout: float = 30.0):
        """
        Stop the event processing pipeline with graceful shutdown

        - Stops accepting new events (cancel motion tasks)
        - Drains remaining events in queue (up to timeout)
        - Stops all workers
        - Closes HTTP client

        Args:
            timeout: Maximum time to wait for queue draining (seconds)
        """
        if not self.running:
            logger.warning("EventProcessor not running")
            return

        logger.info(f"Stopping EventProcessor (timeout: {timeout}s)...")
        self.running = False
        self.shutdown_event.set()

        # Stop motion detection tasks (stop accepting new events)
        logger.info("Stopping motion detection tasks...")
        for camera_id, task in self.motion_tasks.items():
            task.cancel()

        # Wait for motion tasks to finish
        if self.motion_tasks:
            await asyncio.gather(*self.motion_tasks.values(), return_exceptions=True)
        self.motion_tasks.clear()

        # Drain queue with timeout
        queue_size = self.event_queue.qsize()
        if queue_size > 0:
            logger.info(f"Draining {queue_size} events from queue (timeout: {timeout}s)...")

            try:
                await asyncio.wait_for(
                    self._drain_queue(),
                    timeout=timeout
                )
                logger.info("Queue drained successfully")
            except asyncio.TimeoutError:
                remaining = self.event_queue.qsize()
                logger.warning(f"Queue drain timeout - {remaining} events remaining")

        # Stop AI workers
        logger.info("Stopping AI workers...")
        for task in self.worker_tasks:
            task.cancel()

        # Wait for workers to finish
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks.clear()

        # Close HTTP client
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None

        logger.info("EventProcessor stopped")

    async def start_camera_monitoring(self, camera: Camera):
        """
        Start motion detection task for a specific camera

        Args:
            camera: Camera model instance
        """
        if camera.id in self.motion_tasks:
            logger.warning(f"Camera {camera.id} already being monitored")
            return

        task = asyncio.create_task(
            self._motion_detection_task(camera),
            name=f"motion_task_{camera.id}"
        )
        self.motion_tasks[camera.id] = task

        logger.info(f"Started monitoring camera: {camera.name} ({camera.id})")

    async def stop_camera_monitoring(self, camera_id: str):
        """
        Stop motion detection task for a specific camera

        Args:
            camera_id: UUID of camera to stop monitoring
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

        logger.info(f"Stopped monitoring camera: {camera_id}")

    async def _motion_detection_task(self, camera: Camera):
        """
        Continuous motion detection loop for a single camera

        - Runs at camera.frame_rate FPS
        - Captures frame on motion detection
        - Enforces cooldown (camera.motion_cooldown seconds)
        - Handles camera disconnections with retry

        Args:
            camera: Camera model instance
        """
        logger.info(f"Motion detection task started for camera: {camera.name}")

        frame_interval = 1.0 / camera.frame_rate if camera.frame_rate > 0 else 0.2

        while self.running:
            try:
                # Check cooldown
                last_event_time = self.camera_cooldowns.get(camera.id, 0)
                time_since_last_event = time.time() - last_event_time

                if time_since_last_event < camera.motion_cooldown:
                    # Still in cooldown, wait
                    await asyncio.sleep(frame_interval)
                    continue

                # TODO: Integrate with actual camera service to get frames
                # For now, this is a stub that simulates motion detection
                # In real implementation, this would:
                # 1. Get frame from camera service
                # 2. Run motion detection algorithm
                # 3. If motion detected, capture best frame

                # Simulate frame capture delay
                await asyncio.sleep(frame_interval)

                # Placeholder: Skip actual motion detection for now
                # This will be integrated with camera_service and motion_detection_service
                # once those services are updated to support async frame capture

            except asyncio.CancelledError:
                logger.info(f"Motion detection task cancelled for camera: {camera.name}")
                raise
            except Exception as e:
                logger.error(
                    f"Error in motion detection task for camera {camera.name}: {e}",
                    exc_info=True,
                    extra={"camera_id": camera.id, "camera_name": camera.name}
                )
                # Wait before retry
                await asyncio.sleep(10.0)

    async def queue_event(self, event: ProcessingEvent):
        """
        Add event to processing queue

        - Enforces queue maxsize (drops oldest if full)
        - Updates metrics
        - Logs queue depth

        Args:
            event: ProcessingEvent to queue
        """
        try:
            # Non-blocking put (raises QueueFull if full)
            self.event_queue.put_nowait(event)

            # Update cooldown
            self.camera_cooldowns[event.camera_id] = time.time()

            # Update metrics
            self.metrics.queue_depth = self.event_queue.qsize()

            logger.info(
                f"Event queued for camera: {event.camera_name}",
                extra={
                    "camera_id": event.camera_id,
                    "queue_depth": self.metrics.queue_depth,
                    "timestamp": event.timestamp.isoformat()
                }
            )

        except asyncio.QueueFull:
            # Queue overflow - drop oldest event
            logger.warning(
                f"Queue full ({self.queue_maxsize}) - dropping oldest event",
                extra={
                    "camera_id": event.camera_id,
                    "camera_name": event.camera_name,
                    "new_event_timestamp": event.timestamp.isoformat()
                }
            )

            try:
                # Get and discard oldest event
                dropped_event = self.event_queue.get_nowait()
                logger.warning(
                    f"Dropped event from camera: {dropped_event.camera_name}",
                    extra={
                        "dropped_camera_id": dropped_event.camera_id,
                        "dropped_timestamp": dropped_event.timestamp.isoformat()
                    }
                )

                # Now put the new event
                self.event_queue.put_nowait(event)
                self.camera_cooldowns[event.camera_id] = time.time()
                self.metrics.queue_depth = self.event_queue.qsize()

            except Exception as e:
                logger.error(f"Failed to handle queue overflow: {e}", exc_info=True)
                self.metrics.increment_error("queue_overflow_handling_failed")

    async def _ai_worker(self, worker_id: int):
        """
        AI processing worker loop

        - Pulls events from queue (FIFO)
        - Calls AI service to generate description
        - Posts event to /api/v1/events endpoint
        - Handles errors with retry logic
        - Auto-restarts on exception

        Args:
            worker_id: Worker identifier (0-4)
        """
        logger.info(f"AI Worker {worker_id} started")

        while self.running:
            try:
                # Get event from queue (wait up to 1 second)
                try:
                    event = await asyncio.wait_for(
                        self.event_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # No events, continue loop
                    continue

                # Update queue depth metric
                self.metrics.queue_depth = self.event_queue.qsize()

                # Process event
                start_time = time.time()
                success = await self._process_event(event, worker_id)
                duration_ms = (time.time() - start_time) * 1000

                # Update metrics
                self.metrics.record_processing_time(duration_ms)
                if success:
                    self.metrics.events_processed_success += 1
                else:
                    self.metrics.events_processed_failure += 1

                # Mark task done
                self.event_queue.task_done()

                logger.info(
                    f"Worker {worker_id} processed event from {event.camera_name}",
                    extra={
                        "worker_id": worker_id,
                        "camera_id": event.camera_id,
                        "duration_ms": duration_ms,
                        "success": success,
                        "queue_depth": self.metrics.queue_depth
                    }
                )

            except asyncio.CancelledError:
                logger.info(f"AI Worker {worker_id} cancelled")
                raise
            except Exception as e:
                logger.error(
                    f"AI Worker {worker_id} exception: {e}",
                    exc_info=True,
                    extra={"worker_id": worker_id}
                )
                self.metrics.increment_error("worker_exception")
                # Auto-restart: continue loop
                await asyncio.sleep(1.0)

        logger.info(f"AI Worker {worker_id} stopped")

    async def _process_event(self, event: ProcessingEvent, worker_id: int) -> bool:
        """
        Process a single event through the pipeline

        Pipeline:
            1. Call AI service to generate description
            2. POST event to /api/v1/events endpoint
            3. (Stub) Evaluate alert rules
            4. (Stub) WebSocket broadcast

        Args:
            event: ProcessingEvent to process
            worker_id: Worker identifier for logging

        Returns:
            True if processing succeeded, False otherwise
        """
        try:
            # Step 1: Generate AI description
            logger.debug(f"Worker {worker_id}: Calling AI service for camera {event.camera_name}")

            ai_result = await self.ai_service.generate_description(
                frame=event.frame,
                camera_name=event.camera_name,
                timestamp=event.timestamp.isoformat(),
                detected_objects=event.detected_objects,
                sla_timeout_ms=5000
            )

            if not ai_result.success:
                logger.error(
                    f"AI service failed for camera {event.camera_name}",
                    extra={
                        "camera_id": event.camera_id,
                        "error": "AI generation failed"
                    }
                )
                self.metrics.increment_error("ai_service_failed")
                return False

            logger.debug(
                f"Worker {worker_id}: AI description generated",
                extra={
                    "camera_id": event.camera_id,
                    "confidence": ai_result.confidence,
                    "provider": ai_result.provider,
                    "response_time_ms": ai_result.response_time_ms
                }
            )

            # Step 2: Store event via POST /api/v1/events
            event_data = {
                "camera_id": event.camera_id,
                "timestamp": event.timestamp.isoformat(),
                "description": ai_result.description,
                "confidence": ai_result.confidence,
                "objects_detected": ai_result.objects_detected,
                "thumbnail_base64": None,  # TODO: Generate thumbnail from frame
                "alert_triggered": False  # Will be set by alert evaluation (Epic 5)
            }

            success = await self._store_event_with_retry(event_data, max_retries=3)

            if not success:
                logger.error(
                    f"Failed to store event for camera {event.camera_name}",
                    extra={"camera_id": event.camera_id}
                )
                self.metrics.increment_error("event_storage_failed")
                return False

            # Step 3 (Stub): Evaluate alert rules (Epic 5 feature)
            # TODO: Integrate with alert_service.evaluate_rules(event)

            # Step 4 (Stub): WebSocket broadcast (Epic 4 feature)
            # TODO: Integrate with websocket_manager.broadcast_event(event)

            logger.info(
                f"Event processed successfully for camera {event.camera_name}",
                extra={
                    "camera_id": event.camera_id,
                    "description": ai_result.description[:100],  # First 100 chars
                    "confidence": ai_result.confidence,
                    "ai_provider": ai_result.provider
                }
            )

            return True

        except Exception as e:
            logger.error(
                f"Event processing failed: {e}",
                exc_info=True,
                extra={
                    "camera_id": event.camera_id,
                    "camera_name": event.camera_name,
                    "worker_id": worker_id
                }
            )
            self.metrics.increment_error("processing_exception")
            return False

    async def _store_event_with_retry(
        self,
        event_data: Dict,
        max_retries: int = 3
    ) -> bool:
        """
        Store event via POST /api/v1/events with exponential backoff retry

        Retry logic:
            - Attempt 1: Immediate
            - Attempt 2: Wait 2s
            - Attempt 3: Wait 4s
            - Attempt 4: Wait 8s

        Args:
            event_data: Event payload for POST request
            max_retries: Maximum number of retry attempts

        Returns:
            True if event stored successfully, False otherwise
        """
        base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        url = f"{base_url}/api/v1/events"

        for attempt in range(max_retries + 1):
            try:
                response = await self.http_client.post(
                    url,
                    json=event_data
                )

                if response.status_code == 201:
                    logger.debug(f"Event stored successfully (attempt {attempt + 1})")
                    return True
                else:
                    logger.warning(
                        f"Event storage returned status {response.status_code} (attempt {attempt + 1})",
                        extra={"status_code": response.status_code, "response": response.text[:200]}
                    )

            except Exception as e:
                logger.warning(
                    f"Event storage attempt {attempt + 1} failed: {e}",
                    extra={"attempt": attempt + 1, "max_retries": max_retries}
                )

            # Retry with exponential backoff
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 2s, 4s, 8s
                logger.debug(f"Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

        logger.error(f"Event storage failed after {max_retries + 1} attempts")
        return False

    async def _drain_queue(self):
        """
        Drain remaining events in queue during shutdown

        Processes all events currently in queue, blocking until complete.
        Used during graceful shutdown to ensure no events are lost.
        """
        while not self.event_queue.empty():
            try:
                event = self.event_queue.get_nowait()

                # Process event (simplified, no worker assignment)
                await self._process_event(event, worker_id=-1)  # -1 indicates shutdown processing

                self.event_queue.task_done()
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"Error draining queue: {e}", exc_info=True)
                self.event_queue.task_done()

    def get_metrics(self) -> Dict:
        """
        Get current pipeline metrics

        Returns:
            Dictionary with metrics data for /api/v1/metrics endpoint
        """
        return self.metrics.to_dict()


# Global instance (initialized in FastAPI lifespan)
_event_processor: Optional[EventProcessor] = None


def get_event_processor() -> Optional[EventProcessor]:
    """
    Get the global EventProcessor instance

    Returns:
        EventProcessor instance or None if not initialized
    """
    return _event_processor


async def initialize_event_processor(worker_count: Optional[int] = None):
    """
    Initialize and start the global EventProcessor instance

    Called from FastAPI lifespan startup.

    Args:
        worker_count: Number of AI workers (default from env or 2)
    """
    global _event_processor

    if _event_processor is not None:
        logger.warning("EventProcessor already initialized")
        return

    _event_processor = EventProcessor(worker_count=worker_count)
    await _event_processor.start()
    logger.info("Global EventProcessor initialized and started")


async def shutdown_event_processor(timeout: float = 30.0):
    """
    Stop and cleanup the global EventProcessor instance

    Called from FastAPI lifespan shutdown.

    Args:
        timeout: Maximum time to wait for graceful shutdown (seconds)
    """
    global _event_processor

    if _event_processor is None:
        logger.warning("EventProcessor not initialized")
        return

    await _event_processor.stop(timeout=timeout)
    _event_processor = None
    logger.info("Global EventProcessor shutdown complete")
