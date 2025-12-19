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
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
from contextlib import asynccontextmanager
import os
import json

from typing import TYPE_CHECKING

from app.models.camera import Camera
from app.models.event import Event
from app.services.ai_service import AIService
from app.services.camera_service import CameraService
from app.services.motion_detection_service import MotionDetectionService
from app.services.cost_cap_service import get_cost_cap_service
from app.services.cost_alert_service import get_cost_alert_service
from app.services.carrier_extractor import extract_carrier
from app.core.database import SessionLocal

if TYPE_CHECKING:
    from app.services.mqtt_service import MQTTService

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
        clip_path: Path to downloaded video clip (Story P3-1.4, None if not available)
        fallback_reason: Reason for fallback to snapshot analysis (Story P3-1.4)
    """
    camera_id: str
    camera_name: str
    frame: np.ndarray
    timestamp: datetime
    detected_objects: List[str] = field(default_factory=lambda: ["unknown"])
    metadata: Dict = field(default_factory=dict)
    # Story P3-1.4: Video clip context for Protect events
    clip_path: Optional[Path] = None
    fallback_reason: Optional[str] = None


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

        Story P2-6.3 AC13: If all AI providers fail, store event without description
        and flag for retry.

        Args:
            event: ProcessingEvent to process
            worker_id: Worker identifier for logging

        Returns:
            True if processing succeeded, False otherwise
        """
        try:
            # Story P3-7.3: Check cost caps before AI analysis
            cost_cap_service = get_cost_cap_service()
            db = SessionLocal()
            try:
                can_analyze, skip_reason = cost_cap_service.can_analyze(db)
            finally:
                db.close()

            if not can_analyze:
                logger.info(
                    f"AI analysis skipped for camera {event.camera_name} due to {skip_reason}",
                    extra={"camera_id": event.camera_id, "skip_reason": skip_reason}
                )
                self.metrics.increment_error(f"cost_cap_{skip_reason}")

                # Store event without AI description, with skip reason
                thumbnail_base64 = self._generate_thumbnail(event.frame)
                event_data = {
                    "camera_id": event.camera_id,
                    "timestamp": event.timestamp.isoformat(),
                    "description": f"AI analysis paused - {skip_reason.replace('_', ' ')}",
                    "confidence": 0,
                    "objects_detected": event.detected_objects,
                    "thumbnail_base64": thumbnail_base64,
                    "alert_triggered": False,
                    "provider_used": None,
                    "description_retry_needed": True,  # Can retry when cap resets
                    "analysis_skipped_reason": skip_reason  # Story P3-7.3: Track skip reason
                }

                success = await self._store_event_with_retry(event_data, max_retries=3)
                return success

            # Step 1: Generate thumbnail from frame (needed for embedding)
            thumbnail_base64 = self._generate_thumbnail(event.frame)

            # Step 2: Generate embedding early for entity matching (Story P4-3.4)
            # This allows us to match entities BEFORE generating AI description
            embedding_vector = None
            entity_result = None

            try:
                if thumbnail_base64:
                    from app.services.embedding_service import get_embedding_service
                    import base64 as b64

                    embedding_service = get_embedding_service()

                    # Strip data URI prefix if present
                    b64_str = thumbnail_base64
                    if b64_str.startswith("data:"):
                        comma_idx = b64_str.find(",")
                        if comma_idx != -1:
                            b64_str = b64_str[comma_idx + 1:]
                    embedding_bytes = b64.b64decode(b64_str)

                    # Generate embedding
                    embedding_vector = await embedding_service.generate_embedding(embedding_bytes)

                    logger.debug(
                        f"Early embedding generated for context (camera {event.camera_name})",
                        extra={
                            "camera_id": event.camera_id,
                            "embedding_dim": len(embedding_vector) if embedding_vector else 0,
                        }
                    )

            except Exception as embed_error:
                logger.debug(
                    f"Early embedding generation failed (will skip context): {embed_error}",
                    extra={"camera_id": event.camera_id}
                )

            # Step 3: Match entity for context building (Story P4-3.4)
            # Uses read-only match_entity_only() - does NOT create entities or links
            if embedding_vector:
                try:
                    from app.services.entity_service import get_entity_service

                    entity_service = get_entity_service()

                    with SessionLocal() as entity_db:
                        entity_result = await entity_service.match_entity_only(
                            db=entity_db,
                            embedding=embedding_vector,
                            threshold=0.75,
                        )

                    if entity_result:
                        logger.debug(
                            f"Entity matched for context (camera {event.camera_name})",
                            extra={
                                "camera_id": event.camera_id,
                                "entity_id": entity_result.entity_id,
                                "entity_name": entity_result.name,
                                "similarity_score": entity_result.similarity_score,
                            }
                        )
                    else:
                        logger.debug(
                            f"No entity match for context (camera {event.camera_name})",
                            extra={"camera_id": event.camera_id}
                        )

                except Exception as entity_error:
                    logger.debug(
                        f"Entity matching for context failed (will skip context): {entity_error}",
                        extra={"camera_id": event.camera_id}
                    )

            # Step 4: Build context-enhanced prompt (Story P4-3.4)
            # Uses historical context from similar events and matched entity
            context_enhanced_prompt = None
            context_result = None

            try:
                from app.services.context_prompt_service import get_context_prompt_service

                context_service = get_context_prompt_service()

                # Build default base prompt (same as AI service would use)
                base_prompt = (
                    "Describe what you see in this image. Include: "
                    "WHO (people, their appearance, clothing), "
                    "WHAT (objects, vehicles, packages), "
                    "WHERE (location in frame), "
                    "and ACTIONS (what is happening). "
                    "Be specific and detailed."
                )

                # Use a temporary event ID for context lookup
                # We're looking up HISTORICAL context, not the current event
                temp_event_id = str(uuid.uuid4())

                with SessionLocal() as context_db:
                    context_result = await context_service.build_context_enhanced_prompt(
                        db=context_db,
                        event_id=temp_event_id,
                        base_prompt=base_prompt,
                        camera_id=event.camera_id,
                        event_time=event.timestamp,
                        matched_entity=entity_result,  # From Step 3
                    )

                if context_result and context_result.context_included:
                    context_enhanced_prompt = context_result.prompt
                    logger.info(
                        f"Context-enhanced prompt built for camera {event.camera_name}",
                        extra={
                            "camera_id": event.camera_id,
                            "entity_context": context_result.entity_context_included,
                            "similar_events": context_result.similar_events_count,
                            "time_pattern": context_result.time_pattern_included,
                            "context_gather_time_ms": round(context_result.context_gather_time_ms, 2),
                        }
                    )

            except Exception as context_error:
                # Graceful degradation - context failures don't block AI description (AC10)
                logger.warning(
                    f"Context building failed (proceeding without context): {context_error}",
                    extra={"camera_id": event.camera_id, "error": str(context_error)}
                )

            # Step 5: Generate AI description (with context if available)
            logger.debug(f"Worker {worker_id}: Calling AI service for camera {event.camera_name}")

            ai_result = await self.ai_service.generate_description(
                frame=event.frame,
                camera_name=event.camera_name,
                timestamp=event.timestamp.isoformat(),
                detected_objects=event.detected_objects,
                sla_timeout_ms=5000,
                custom_prompt=context_enhanced_prompt,  # Story P4-3.4: Pass enhanced prompt
            )

            # Story P2-6.3 AC13: If all AI providers fail, store event without description
            # and flag for retry instead of failing completely
            if not ai_result.success:
                logger.warning(
                    f"All AI providers failed for camera {event.camera_name}, storing event for retry",
                    extra={
                        "camera_id": event.camera_id,
                        "error": "All AI providers down"
                    }
                )
                self.metrics.increment_error("ai_service_failed")

                # Store event without description, flagged for retry (AC13)
                event_data = {
                    "camera_id": event.camera_id,
                    "timestamp": event.timestamp.isoformat(),
                    "description": "[AI description pending - providers unavailable]",
                    "confidence": 0,  # 0 confidence indicates no AI analysis
                    "objects_detected": event.detected_objects,
                    "thumbnail_base64": thumbnail_base64,
                    "alert_triggered": False,
                    "provider_used": None,
                    "description_retry_needed": True  # Flag for retry (AC13)
                }

                success = await self._store_event_with_retry(event_data, max_retries=3)
                if success:
                    logger.info(
                        f"Event stored for retry: camera {event.camera_name}",
                        extra={"camera_id": event.camera_id, "description_retry_needed": True}
                    )
                return success

            logger.debug(
                f"Worker {worker_id}: AI description generated",
                extra={
                    "camera_id": event.camera_id,
                    "confidence": ai_result.confidence,
                    "provider": ai_result.provider,
                    "response_time_ms": ai_result.response_time_ms
                }
            )

            # Story P7-2.1: Extract delivery carrier from AI description
            # Best-effort extraction - failures don't block event processing
            delivery_carrier = None
            try:
                delivery_carrier = extract_carrier(ai_result.description)
                if delivery_carrier:
                    logger.info(
                        f"Delivery carrier detected for camera {event.camera_name}: {delivery_carrier}",
                        extra={
                            "camera_id": event.camera_id,
                            "carrier": delivery_carrier,
                        }
                    )
            except Exception as carrier_error:
                # Carrier extraction failures should NOT block event processing
                logger.warning(
                    f"Carrier extraction failed for camera {event.camera_name}: {carrier_error}",
                    extra={"camera_id": event.camera_id, "error": str(carrier_error)}
                )

            # Step 3: Store event in database
            event_data = {
                "camera_id": event.camera_id,
                "timestamp": event.timestamp.isoformat(),
                "description": ai_result.description,
                "confidence": ai_result.confidence,
                "objects_detected": ai_result.objects_detected,
                "thumbnail_base64": thumbnail_base64,
                "alert_triggered": False,  # Will be set by alert evaluation (Epic 5)
                "provider_used": ai_result.provider,  # Story P2-5.3: Track AI provider
                "description_retry_needed": False,  # Successfully processed
                "ai_cost": ai_result.cost_estimate,  # Story P3-7.1: Track AI cost
                "delivery_carrier": delivery_carrier,  # Story P7-2.1: Carrier detection
            }

            logger.info(f"Storing event for camera {event.camera_name}: {ai_result.description[:50]}...")
            event_id = await self._store_event_with_retry(event_data, max_retries=3)

            if not event_id:
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

            # Step 5: Check cost thresholds and send alerts (Story P3-7.4)
            try:
                cost_alert_service = get_cost_alert_service()
                with SessionLocal() as db:
                    alerts = await cost_alert_service.check_and_notify(db)
                    if alerts:
                        logger.info(
                            f"Cost alerts triggered: {len(alerts)} notifications sent",
                            extra={"alert_count": len(alerts)}
                        )
            except Exception as alert_error:
                # Cost alert failures should not block event processing
                logger.warning(
                    f"Failed to check cost alerts: {alert_error}",
                    extra={"error": str(alert_error)}
                )

            # Step 6: Send push notifications (Story P4-1.1, P4-1.3)
            try:
                from app.services.push_notification_service import send_event_notification

                # Construct thumbnail URL if we have a thumbnail
                push_thumbnail_url = None
                if thumbnail_base64:
                    date_str = event.timestamp.strftime("%Y-%m-%d")
                    push_thumbnail_url = f"/api/v1/thumbnails/{date_str}/{event_id}.jpg"

                # P4-1.3: Extract smart detection type from metadata or detected objects
                smart_detection_type = event.metadata.get("smart_detection_type")
                if not smart_detection_type and event.detected_objects:
                    # Map detected objects to smart detection type
                    obj = event.detected_objects[0].lower() if event.detected_objects else None
                    if obj in ("person", "vehicle", "package", "animal"):
                        smart_detection_type = obj

                # Fire and forget - don't await to avoid blocking
                asyncio.create_task(
                    send_event_notification(
                        event_id=event_id,
                        camera_name=event.camera_name,
                        description=ai_result.description,
                        thumbnail_url=push_thumbnail_url,
                        camera_id=event.camera_id,  # P4-1.3: For notification collapse
                        smart_detection_type=smart_detection_type,  # P4-1.3: For better title
                    )
                )
                logger.debug(
                    f"Push notification task created for event {event_id}",
                    extra={"event_id": event_id, "camera_name": event.camera_name}
                )
            except Exception as push_error:
                # Push notification failures should not block event processing
                logger.warning(
                    f"Failed to create push notification task: {push_error}",
                    extra={"error": str(push_error)}
                )

            # Step 7: Publish event to MQTT for Home Assistant (Story P4-2.3)
            try:
                from app.services.mqtt_service import get_mqtt_service, serialize_event_for_mqtt

                mqtt_service = get_mqtt_service()

                # Only publish if MQTT is enabled and connected (AC6)
                if mqtt_service.is_connected:
                    # Build MQTT payload using event data from database
                    # We need to fetch the stored event to get all fields
                    with SessionLocal() as mqtt_db:
                        stored_event = mqtt_db.query(Event).filter(Event.id == event_id).first()
                        if stored_event:
                            # Get API base URL for thumbnail URLs (AC3)
                            api_base_url = mqtt_service.get_api_base_url()

                            # Serialize event to MQTT payload (AC2, AC7)
                            mqtt_payload = serialize_event_for_mqtt(
                                stored_event,
                                event.camera_name,
                                api_base_url=api_base_url
                            )

                            # Get topic for this camera (AC1)
                            topic = mqtt_service.get_event_topic(event.camera_id)

                            # Fire and forget - use asyncio.create_task for non-blocking (AC5)
                            asyncio.create_task(
                                self._publish_event_to_mqtt(mqtt_service, topic, mqtt_payload, event_id)
                            )

                            logger.debug(
                                f"MQTT publish task created for event {event_id}",
                                extra={
                                    "event_id": event_id,
                                    "topic": topic,
                                    "camera_id": event.camera_id
                                }
                            )
            except Exception as mqtt_error:
                # MQTT failures must not block event processing (AC5, AC6)
                logger.warning(
                    f"Failed to create MQTT publish task: {mqtt_error}",
                    extra={"error": str(mqtt_error), "event_id": event_id}
                )

            # Step 8: Publish camera status sensors to MQTT (Story P4-2.5)
            try:
                from app.services.mqtt_service import get_mqtt_service

                mqtt_service = get_mqtt_service()

                if mqtt_service.is_connected:
                    # Get stored event for full details
                    with SessionLocal() as sensor_db:
                        stored_event = sensor_db.query(Event).filter(Event.id == event_id).first()
                        if stored_event:
                            # Publish last event timestamp (AC2, AC8)
                            asyncio.create_task(
                                mqtt_service.publish_last_event_timestamp(
                                    camera_id=event.camera_id,
                                    camera_name=event.camera_name,
                                    event_id=str(event_id),
                                    timestamp=stored_event.timestamp,
                                    description=ai_result.description,
                                    smart_detection_type=stored_event.smart_detection_type
                                )
                            )

                            # Publish activity state ON (AC4)
                            asyncio.create_task(
                                mqtt_service.publish_activity_state(
                                    camera_id=event.camera_id,
                                    state="ON",
                                    last_event_at=stored_event.timestamp
                                )
                            )

                            # Publish updated event counts (AC3)
                            # Import the helper function for count calculation
                            from app.services.mqtt_status_service import get_camera_event_counts
                            counts = await get_camera_event_counts(event.camera_id)
                            asyncio.create_task(
                                mqtt_service.publish_event_counts(
                                    camera_id=event.camera_id,
                                    camera_name=event.camera_name,
                                    events_today=counts["events_today"],
                                    events_this_week=counts["events_this_week"]
                                )
                            )

                            logger.debug(
                                f"Status sensor publish tasks created for event {event_id}",
                                extra={
                                    "event_id": event_id,
                                    "camera_id": event.camera_id
                                }
                            )
            except Exception as status_error:
                # Status sensor failures must not block event processing
                logger.warning(
                    f"Failed to publish status sensors: {status_error}",
                    extra={"error": str(status_error), "event_id": event_id}
                )

            # Step 9: Store embedding for this event (Story P4-3.1, P4-3.4)
            # Note: Embedding was already generated earlier (Step 2) for context building
            # Here we just need to store it linked to the actual event_id
            # AC2: Embedding generated for each new event thumbnail
            # AC7: Graceful fallback if embedding generation fails
            try:
                if embedding_vector:
                    from app.services.embedding_service import get_embedding_service

                    embedding_service = get_embedding_service()

                    # Store embedding in database (AC3: stored in event_embeddings table)
                    with SessionLocal() as embed_db:
                        await embedding_service.store_embedding(
                            db=embed_db,
                            event_id=event_id,
                            embedding=embedding_vector,
                        )

                    logger.debug(
                        f"Embedding stored for event {event_id}",
                        extra={
                            "event_id": event_id,
                            "camera_id": event.camera_id,
                            "embedding_dim": len(embedding_vector),
                        }
                    )
                else:
                    logger.debug(
                        f"No embedding available for event {event_id} (will be generated later if needed)",
                        extra={"event_id": event_id}
                    )

            except Exception as embedding_error:
                # AC7: Graceful fallback - embedding failures must not block event creation
                logger.warning(
                    f"Embedding storage failed for event {event_id}: {embedding_error}",
                    extra={
                        "event_id": event_id,
                        "camera_id": event.camera_id,
                        "error": str(embedding_error),
                    }
                )

            # Step 10: Trigger HomeKit motion sensor (Story P4-6.2)
            try:
                from app.services.homekit_service import get_homekit_service

                homekit_service = get_homekit_service()

                # Only trigger if HomeKit is running (AC6: error resilience)
                if homekit_service.is_running:
                    # Fire and forget - use asyncio.create_task for non-blocking (AC1: <1s)
                    asyncio.create_task(
                        self._trigger_homekit_motion(homekit_service, event.camera_id, event_id)
                    )
                    logger.debug(
                        f"HomeKit motion trigger task created for event {event_id}",
                        extra={"event_id": event_id, "camera_id": event.camera_id}
                    )

                    # Story P5-1.5: Trigger occupancy sensor ONLY for person detection
                    # AC2: Only smart_detection_type == 'person' triggers occupancy
                    if smart_detection_type == "person":
                        asyncio.create_task(
                            self._trigger_homekit_occupancy(homekit_service, event.camera_id, event_id)
                        )
                        logger.debug(
                            f"HomeKit occupancy trigger task created for person event {event_id}",
                            extra={"event_id": event_id, "camera_id": event.camera_id, "smart_detection_type": smart_detection_type}
                        )

                    # Story P5-1.6: Trigger detection-type-specific sensors
                    # AC1: Vehicle detection triggers only vehicle sensor
                    if smart_detection_type == "vehicle":
                        asyncio.create_task(
                            self._trigger_homekit_vehicle(homekit_service, event.camera_id, event_id)
                        )
                        logger.debug(
                            f"HomeKit vehicle trigger task created for event {event_id}",
                            extra={"event_id": event_id, "camera_id": event.camera_id, "smart_detection_type": smart_detection_type}
                        )

                    # AC2: Animal detection triggers only animal sensor
                    if smart_detection_type == "animal":
                        asyncio.create_task(
                            self._trigger_homekit_animal(homekit_service, event.camera_id, event_id)
                        )
                        logger.debug(
                            f"HomeKit animal trigger task created for event {event_id}",
                            extra={"event_id": event_id, "camera_id": event.camera_id, "smart_detection_type": smart_detection_type}
                        )

                    # AC3: Package detection triggers only package sensor
                    # Story P7-2.3: Pass carrier to HomeKit for logging
                    if smart_detection_type == "package":
                        delivery_carrier = getattr(event, 'delivery_carrier', None)
                        asyncio.create_task(
                            self._trigger_homekit_package(
                                homekit_service, event.camera_id, event_id, delivery_carrier
                            )
                        )
                        logger.debug(
                            f"HomeKit package trigger task created for event {event_id}",
                            extra={
                                "event_id": event_id,
                                "camera_id": event.camera_id,
                                "smart_detection_type": smart_detection_type,
                                "delivery_carrier": delivery_carrier
                            }
                        )
            except Exception as homekit_error:
                # HomeKit failures must not block event processing (AC6)
                logger.warning(
                    f"Failed to create HomeKit motion trigger task: {homekit_error}",
                    extra={"error": str(homekit_error), "event_id": event_id}
                )

            # Step 11: Match or create entity and link to event (Story P4-3.3, P4-3.4)
            # Note: Step 3 did a read-only match for context. Now we do the full
            # match_or_create_entity to actually link/create the entity-event relationship.
            # AC11: Entity matching integrated into event pipeline
            # AC14: Graceful handling when embedding service unavailable
            try:
                if embedding_vector:
                    from app.services.entity_service import get_entity_service

                    entity_service = get_entity_service()

                    # Determine entity type from smart detection or objects detected
                    entity_type = "unknown"
                    if hasattr(event, 'smart_detection_type') and event.smart_detection_type in ("person", "vehicle"):
                        entity_type = event.smart_detection_type
                    elif event.detected_objects:
                        objects_list = event.detected_objects if isinstance(event.detected_objects, list) else json.loads(event.detected_objects)
                        if "person" in [o.lower() for o in objects_list]:
                            entity_type = "person"
                        elif "vehicle" in [o.lower() for o in objects_list]:
                            entity_type = "vehicle"

                    with SessionLocal() as entity_db:
                        final_entity_result = await entity_service.match_or_create_entity(
                            db=entity_db,
                            event_id=event_id,
                            embedding=embedding_vector,
                            entity_type=entity_type,
                            threshold=0.75,
                        )

                    logger.info(
                        f"Entity {'created' if final_entity_result.is_new else 'matched'} for event {event_id}",
                        extra={
                            "event_id": event_id,
                            "entity_id": final_entity_result.entity_id,
                            "entity_type": final_entity_result.entity_type,
                            "is_new": final_entity_result.is_new,
                            "similarity_score": final_entity_result.similarity_score,
                            "occurrence_count": final_entity_result.occurrence_count,
                        }
                    )
                else:
                    logger.debug(
                        f"Skipping entity matching - no embedding available for event {event_id}",
                        extra={"event_id": event_id}
                    )

            except Exception as entity_error:
                # AC14: Graceful fallback - entity matching failures must not block event processing
                logger.warning(
                    f"Entity matching failed for event {event_id}: {entity_error}",
                    extra={
                        "event_id": event_id,
                        "camera_id": event.camera_id,
                        "error": str(entity_error),
                    }
                )

            # Step 12: Process face embeddings (Story P4-8.1)
            # Only process faces if face_recognition_enabled is true (privacy control)
            try:
                from app.models.system_setting import SystemSetting
                from app.services.face_embedding_service import get_face_embedding_service
                import base64 as b64

                # Check if face recognition is enabled (AC5: privacy controls)
                with SessionLocal() as settings_db:
                    setting = settings_db.query(SystemSetting).filter(
                        SystemSetting.key == "face_recognition_enabled"
                    ).first()
                    face_recognition_enabled = (
                        setting.value.lower() == "true" if setting else False
                    )

                if face_recognition_enabled and thumbnail_base64:
                    # Fire and forget - use asyncio.create_task for non-blocking (AC6)
                    asyncio.create_task(
                        self._process_faces(event_id, thumbnail_base64)
                    )
                    logger.debug(
                        f"Face processing task created for event {event_id}",
                        extra={"event_id": event_id, "camera_id": event.camera_id}
                    )
                else:
                    if not face_recognition_enabled:
                        logger.debug(
                            f"Face recognition disabled, skipping face processing for event {event_id}",
                            extra={"event_id": event_id}
                        )

            except Exception as face_error:
                # Face processing failures must not block event processing (AC6)
                logger.warning(
                    f"Failed to create face processing task: {face_error}",
                    extra={"error": str(face_error), "event_id": event_id}
                )

            # Step 14: Process vehicle embeddings (Story P4-8.3)
            # Only process vehicles if vehicle_recognition_enabled is true (privacy control)
            # Also check if event contains vehicle detections
            try:
                from app.models.system_setting import SystemSetting

                # Check if vehicle recognition is enabled
                with SessionLocal() as settings_db:
                    setting = settings_db.query(SystemSetting).filter(
                        SystemSetting.key == "vehicle_recognition_enabled"
                    ).first()
                    vehicle_recognition_enabled = (
                        setting.value.lower() == "true" if setting else False
                    )

                # Check if this event might contain vehicles
                has_vehicle = False
                if objects_json:
                    try:
                        objects_list = json.loads(objects_json)
                        has_vehicle = "vehicle" in objects_list
                    except json.JSONDecodeError:
                        pass
                # Also check smart detection type for Protect events
                if smart_detection_type == "vehicle":
                    has_vehicle = True

                if vehicle_recognition_enabled and thumbnail_base64 and has_vehicle:
                    # Fire and forget - use asyncio.create_task for non-blocking
                    asyncio.create_task(
                        self._process_vehicles(
                            event_id,
                            thumbnail_base64,
                            ai_result.description if ai_result else None
                        )
                    )
                    logger.debug(
                        f"Vehicle processing task created for event {event_id}",
                        extra={"event_id": event_id, "camera_id": event.camera_id}
                    )
                else:
                    if not vehicle_recognition_enabled:
                        logger.debug(
                            f"Vehicle recognition disabled, skipping vehicle processing for event {event_id}",
                            extra={"event_id": event_id}
                        )
                    elif not has_vehicle:
                        logger.debug(
                            f"No vehicle detected, skipping vehicle processing for event {event_id}",
                            extra={"event_id": event_id}
                        )

            except Exception as vehicle_error:
                # Vehicle processing failures must not block event processing
                logger.warning(
                    f"Failed to create vehicle processing task: {vehicle_error}",
                    extra={"error": str(vehicle_error), "event_id": event_id}
                )

            # Step 15: Entity Alert Processing (Story P4-8.4)
            # Process entity alerts for personalized notifications
            # This runs after face (Step 13) and vehicle (Step 14) matching completes
            try:
                from app.models.system_setting import SystemSetting

                # Check if entity alerts are enabled (tied to recognition settings)
                face_recognition_enabled = False
                vehicle_recognition_enabled = False

                face_setting = db.query(SystemSetting).filter(
                    SystemSetting.key == "face_recognition_enabled"
                ).first()
                if face_setting and face_setting.value.lower() == "true":
                    face_recognition_enabled = True

                vehicle_setting = db.query(SystemSetting).filter(
                    SystemSetting.key == "vehicle_recognition_enabled"
                ).first()
                if vehicle_setting and vehicle_setting.value.lower() == "true":
                    vehicle_recognition_enabled = True

                # Only process if at least one recognition type is enabled
                if face_recognition_enabled or vehicle_recognition_enabled:
                    # Check if event has person or vehicle
                    has_person = "person" in objects_detected if objects_detected else False
                    has_vehicle = "vehicle" in objects_detected if objects_detected else False

                    if has_person or has_vehicle:
                        # Run entity alert processing asynchronously
                        asyncio.create_task(
                            self._process_entity_alerts(
                                event_id=event_id,
                                description=ai_result.description,
                                has_person_or_vehicle=True
                            )
                        )

            except Exception as entity_alert_error:
                # Entity alert failures must not block event processing
                logger.warning(
                    f"Failed to create entity alert task: {entity_alert_error}",
                    extra={"error": str(entity_alert_error), "event_id": event_id}
                )

            # Step 16: Audio Event Enrichment (Story P6-3.2)
            # Check for audio events and enrich the stored event with audio info
            # This runs asynchronously to not block event processing (AC graceful degradation)
            try:
                asyncio.create_task(
                    self._enrich_event_with_audio(event_id, event.camera_id)
                )
                logger.debug(
                    f"Audio enrichment task created for event {event_id}",
                    extra={"event_id": event_id, "camera_id": event.camera_id}
                )
            except Exception as audio_error:
                # Audio enrichment failures must not block event processing
                logger.warning(
                    f"Failed to create audio enrichment task: {audio_error}",
                    extra={"error": str(audio_error), "event_id": event_id}
                )

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
    ) -> Optional[str]:
        """
        Store event directly to database (bypasses HTTP auth)

        Args:
            event_data: Event payload
            max_retries: Maximum number of retry attempts

        Returns:
            Event ID string if stored successfully, None otherwise
        """
        import uuid
        from datetime import datetime

        for attempt in range(max_retries + 1):
            db = SessionLocal()
            try:
                # Parse timestamp if string
                timestamp = event_data.get("timestamp")
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                # Handle thumbnail - save to file if base64 provided
                thumbnail_path = None
                thumbnail_base64 = event_data.get("thumbnail_base64")
                if thumbnail_base64:
                    import base64

                    # Strip data URI prefix if present (e.g., "data:image/jpeg;base64,")
                    if thumbnail_base64.startswith('data:'):
                        comma_idx = thumbnail_base64.find(',')
                        if comma_idx != -1:
                            thumbnail_base64 = thumbnail_base64[comma_idx + 1:]

                    # Create thumbnails directory structure
                    date_str = timestamp.strftime("%Y-%m-%d")
                    thumbnail_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "data", "thumbnails", date_str
                    )
                    os.makedirs(thumbnail_dir, exist_ok=True)

                    # Save thumbnail
                    event_id = str(uuid.uuid4())
                    thumbnail_filename = f"{event_id}.jpg"
                    thumbnail_full_path = os.path.join(thumbnail_dir, thumbnail_filename)

                    with open(thumbnail_full_path, "wb") as f:
                        f.write(base64.b64decode(thumbnail_base64))

                    thumbnail_path = f"/api/v1/thumbnails/{date_str}/{thumbnail_filename}"
                else:
                    event_id = str(uuid.uuid4())

                # Create event record
                # Convert confidence from 0.0-1.0 to 0-100 integer
                confidence_float = event_data.get("confidence", 0.0)
                confidence_int = int(confidence_float * 100) if confidence_float <= 1.0 else int(confidence_float)

                # Convert objects_detected list to JSON string
                objects_detected = event_data.get("objects_detected", [])
                if isinstance(objects_detected, list):
                    objects_detected = json.dumps(objects_detected)

                event = Event(
                    id=event_id,
                    camera_id=event_data["camera_id"],
                    timestamp=timestamp,
                    description=event_data.get("description", ""),
                    confidence=confidence_int,
                    objects_detected=objects_detected,
                    thumbnail_path=thumbnail_path,
                    alert_triggered=event_data.get("alert_triggered", False),
                    provider_used=event_data.get("provider_used"),  # Story P2-5.3: AI provider tracking
                    description_retry_needed=event_data.get("description_retry_needed", False),  # Story P2-6.3 AC13
                    ai_cost=event_data.get("ai_cost"),  # Story P3-7.1: AI cost tracking
                    delivery_carrier=event_data.get("delivery_carrier"),  # Story P7-2.1: Carrier detection
                )

                db.add(event)
                db.commit()

                logger.info(
                    f"Event {event_id} stored successfully",
                    extra={"event_id": event_id, "camera_id": event_data["camera_id"]}
                )

                # Story P4-7.1: Update activity baseline incrementally (non-blocking)
                # Spawn as background task with its own session since this db will be closed
                asyncio.create_task(
                    self._update_activity_baseline(event_data["camera_id"], event)
                )

                # Story P4-7.2: Calculate and persist anomaly score (non-blocking)
                asyncio.create_task(
                    self._calculate_anomaly_score(event)
                )

                return event_id  # Return event_id instead of True

            except Exception as e:
                db.rollback()
                logger.error(
                    f"Event storage attempt {attempt + 1} failed: {e}",
                    exc_info=True,
                    extra={"attempt": attempt + 1, "max_retries": max_retries}
                )

            finally:
                db.close()

            # Retry with exponential backoff
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait_time)

        logger.error(f"Event storage failed after {max_retries + 1} attempts")
        return None

    async def _trigger_homekit_motion(
        self,
        homekit_service,
        camera_id: str,
        event_id: str
    ) -> None:
        """
        Trigger HomeKit motion sensor (Story P4-6.2).

        This is a fire-and-forget async task. Errors are logged but not propagated.

        Args:
            homekit_service: HomekitService instance
            camera_id: Camera identifier
            event_id: Event ID for logging

        Note:
            - Trigger happens within 1s of event creation (AC1)
            - Non-blocking, runs as background task (AC6)
            - Errors don't propagate to caller (AC6)
        """
        try:
            # trigger_motion handles timer reset internally (AC2, AC3)
            success = homekit_service.trigger_motion(camera_id, event_id=event_id)

            if success:
                logger.info(
                    f"HomeKit motion triggered for event",
                    extra={
                        "event_type": "homekit_motion_triggered",
                        "event_id": event_id,
                        "camera_id": camera_id
                    }
                )
            else:
                logger.debug(
                    f"HomeKit motion trigger returned False (no sensor for camera)",
                    extra={
                        "event_type": "homekit_motion_no_sensor",
                        "event_id": event_id,
                        "camera_id": camera_id
                    }
                )
        except Exception as e:
            # HomeKit errors must not propagate (AC6)
            logger.warning(
                f"HomeKit motion trigger failed for event {event_id}: {e}",
                extra={
                    "event_type": "homekit_motion_error",
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )

    async def _trigger_homekit_occupancy(
        self,
        homekit_service,
        camera_id: str,
        event_id: str
    ) -> None:
        """
        Trigger HomeKit occupancy sensor for person detection (Story P5-1.5).

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Only called when smart_detection_type == 'person'.

        Args:
            homekit_service: HomekitService instance
            camera_id: Camera identifier
            event_id: Event ID for logging

        Note:
            - Only triggered for person detections (AC2)
            - Occupancy has 5-minute timeout (AC3)
            - Non-blocking, runs as background task
            - Errors don't propagate to caller
        """
        try:
            # trigger_occupancy handles timer reset internally (AC3)
            success = homekit_service.trigger_occupancy(camera_id, event_id=event_id)

            if success:
                logger.info(
                    f"HomeKit occupancy triggered for person detection",
                    extra={
                        "event_type": "homekit_occupancy_triggered",
                        "event_id": event_id,
                        "camera_id": camera_id
                    }
                )
            else:
                logger.debug(
                    f"HomeKit occupancy trigger returned False (no sensor for camera)",
                    extra={
                        "event_type": "homekit_occupancy_no_sensor",
                        "event_id": event_id,
                        "camera_id": camera_id
                    }
                )
        except Exception as e:
            # HomeKit errors must not propagate
            logger.warning(
                f"HomeKit occupancy trigger failed for event {event_id}: {e}",
                extra={
                    "event_type": "homekit_occupancy_error",
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )

    async def _trigger_homekit_vehicle(
        self,
        homekit_service,
        camera_id: str,
        event_id: str
    ) -> None:
        """
        Trigger HomeKit vehicle sensor for vehicle detection (Story P5-1.6 AC1).

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Only called when smart_detection_type == 'vehicle'.

        Args:
            homekit_service: HomekitService instance
            camera_id: Camera identifier
            event_id: Event ID for logging
        """
        try:
            success = homekit_service.trigger_vehicle(camera_id, event_id=event_id)

            if success:
                logger.info(
                    f"HomeKit vehicle triggered for vehicle detection",
                    extra={
                        "event_type": "homekit_vehicle_triggered",
                        "event_id": event_id,
                        "camera_id": camera_id
                    }
                )
            else:
                logger.debug(
                    f"HomeKit vehicle trigger returned False (no sensor for camera)",
                    extra={
                        "event_type": "homekit_vehicle_no_sensor",
                        "event_id": event_id,
                        "camera_id": camera_id
                    }
                )
        except Exception as e:
            logger.warning(
                f"HomeKit vehicle trigger failed for event {event_id}: {e}",
                extra={
                    "event_type": "homekit_vehicle_error",
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )

    async def _trigger_homekit_animal(
        self,
        homekit_service,
        camera_id: str,
        event_id: str
    ) -> None:
        """
        Trigger HomeKit animal sensor for animal detection (Story P5-1.6 AC2).

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Only called when smart_detection_type == 'animal'.

        Args:
            homekit_service: HomekitService instance
            camera_id: Camera identifier
            event_id: Event ID for logging
        """
        try:
            success = homekit_service.trigger_animal(camera_id, event_id=event_id)

            if success:
                logger.info(
                    f"HomeKit animal triggered for animal detection",
                    extra={
                        "event_type": "homekit_animal_triggered",
                        "event_id": event_id,
                        "camera_id": camera_id
                    }
                )
            else:
                logger.debug(
                    f"HomeKit animal trigger returned False (no sensor for camera)",
                    extra={
                        "event_type": "homekit_animal_no_sensor",
                        "event_id": event_id,
                        "camera_id": camera_id
                    }
                )
        except Exception as e:
            logger.warning(
                f"HomeKit animal trigger failed for event {event_id}: {e}",
                extra={
                    "event_type": "homekit_animal_error",
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )

    async def _trigger_homekit_package(
        self,
        homekit_service,
        camera_id: str,
        event_id: str,
        delivery_carrier: Optional[str] = None
    ) -> None:
        """
        Trigger HomeKit package sensor for package detection (Story P5-1.6 AC3, P7-2.3).

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Only called when smart_detection_type == 'package'.
        Package sensor has a longer timeout (60s) since packages persist.

        Story P7-2.3: Pass carrier info to HomeKit service for logging.

        Args:
            homekit_service: HomekitService instance
            camera_id: Camera identifier
            event_id: Event ID for logging
            delivery_carrier: Optional carrier name (fedex, ups, usps, amazon, dhl)
        """
        try:
            # Story P7-2.3: Pass carrier to trigger_package for logging
            success = homekit_service.trigger_package(
                camera_id, event_id=event_id, delivery_carrier=delivery_carrier
            )

            if success:
                # Story P7-2.3 AC2, AC4: Log carrier info for debugging
                logger.info(
                    f"HomeKit package triggered for package detection"
                    + (f" (carrier: {delivery_carrier})" if delivery_carrier else ""),
                    extra={
                        "event_type": "homekit_package_triggered",
                        "event_id": event_id,
                        "camera_id": camera_id,
                        "delivery_carrier": delivery_carrier
                    }
                )
            else:
                logger.debug(
                    f"HomeKit package trigger returned False (no sensor for camera)",
                    extra={
                        "event_type": "homekit_package_no_sensor",
                        "event_id": event_id,
                        "camera_id": camera_id,
                        "delivery_carrier": delivery_carrier
                    }
                )
        except Exception as e:
            logger.warning(
                f"HomeKit package trigger failed for event {event_id}: {e}",
                extra={
                    "event_type": "homekit_package_error",
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "delivery_carrier": delivery_carrier,
                    "error": str(e)
                }
            )

    async def _publish_event_to_mqtt(
        self,
        mqtt_service: "MQTTService",
        topic: str,
        payload: dict,
        event_id: str
    ) -> None:
        """
        Publish event to MQTT (Story P4-2.3).

        This is a fire-and-forget async task. Errors are logged but not propagated.

        Args:
            mqtt_service: MQTTService instance
            topic: MQTT topic to publish to
            payload: Serialized event payload
            event_id: Event ID for logging

        Note:
            - Uses QoS from MQTTConfig (AC4)
            - Non-blocking, runs as background task (AC5)
            - Errors don't propagate to caller (AC6)
        """
        try:
            # Use QoS from config (AC4)
            success = await mqtt_service.publish(topic, payload)

            if success:
                logger.info(
                    f"Event published to MQTT",
                    extra={
                        "event_type": "mqtt_event_published",
                        "event_id": event_id,
                        "topic": topic
                    }
                )
            else:
                logger.warning(
                    f"MQTT publish returned False for event {event_id}",
                    extra={
                        "event_type": "mqtt_event_publish_failed",
                        "event_id": event_id,
                        "topic": topic
                    }
                )
        except Exception as e:
            # MQTT errors must not propagate (AC5, AC6)
            logger.warning(
                f"MQTT publish failed for event {event_id}: {e}",
                extra={
                    "event_type": "mqtt_event_publish_error",
                    "event_id": event_id,
                    "topic": topic,
                    "error": str(e)
                }
            )

    async def _update_activity_baseline(
        self,
        camera_id: str,
        event: Event
    ) -> None:
        """
        Update activity baseline for a camera (Story P4-7.1).

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Uses its own database session since the caller's session may be closed.

        Args:
            camera_id: Camera identifier
            event: Event that triggered this update

        Note:
            - Non-blocking, runs as background task (AC3)
            - Target completion time <50ms (AC2)
            - Errors don't propagate to caller (AC3)
        """
        try:
            from app.services.pattern_service import get_pattern_service
            pattern_service = get_pattern_service()

            # Use own session since caller's may be closed
            db = SessionLocal()
            try:
                await pattern_service.update_baseline_incremental(db, camera_id, event)
            finally:
                db.close()

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

    async def _calculate_anomaly_score(
        self,
        event: Event
    ) -> None:
        """
        Calculate and persist anomaly score for an event (Story P4-7.2).

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Uses its own database session since the caller's session may be closed.

        Args:
            event: Event to score

        Note:
            - Non-blocking, runs as background task (AC7)
            - Errors don't propagate to caller (AC7)
            - Uses AnomalyScoringService for calculation (AC2)
        """
        try:
            from app.services.anomaly_scoring_service import get_anomaly_scoring_service
            anomaly_service = get_anomaly_scoring_service()

            # Use own session since caller's may be closed
            db = SessionLocal()
            try:
                # Re-fetch event in new session
                event_in_session = db.query(Event).filter_by(id=event.id).first()
                if event_in_session:
                    await anomaly_service.score_event(db, event_in_session)
            finally:
                db.close()

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

    async def _process_faces(
        self,
        event_id: str,
        thumbnail_base64: str
    ) -> None:
        """
        Process face detection, embedding, and person matching for an event.

        Story P4-8.1: Face detection and embedding storage
        Story P4-8.2: Person matching (Step 13)

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Uses its own database session since the caller's session may be closed.

        Args:
            event_id: UUID of the event to process
            thumbnail_base64: Base64-encoded thumbnail image

        Note:
            - Non-blocking, runs as background task (AC6)
            - Only runs when face_recognition_enabled is true (AC5)
            - Errors don't propagate to caller (AC6)
        """
        try:
            from app.services.face_embedding_service import get_face_embedding_service
            from app.services.person_matching_service import get_person_matching_service
            from app.models.system_setting import SystemSetting
            import base64

            face_service = get_face_embedding_service()
            person_service = get_person_matching_service()

            # Strip data URI prefix if present
            b64_str = thumbnail_base64
            if b64_str.startswith("data:"):
                comma_idx = b64_str.find(",")
                if comma_idx != -1:
                    b64_str = b64_str[comma_idx + 1:]

            thumbnail_bytes = base64.b64decode(b64_str)

            # Use own session since caller's may be closed
            db = SessionLocal()
            try:
                # Step 12: Face Detection and Embedding Storage (P4-8.1)
                face_ids = await face_service.process_event_faces(
                    db=db,
                    event_id=event_id,
                    thumbnail_bytes=thumbnail_bytes,
                )

                if face_ids:
                    logger.info(
                        f"Face processing complete for event {event_id}",
                        extra={
                            "event_type": "face_processing_complete",
                            "event_id": event_id,
                            "face_count": len(face_ids),
                        }
                    )

                    # Step 13: Person Matching (P4-8.2)
                    # Get settings for person matching
                    threshold_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == "person_match_threshold"
                    ).first()
                    auto_create_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == "auto_create_persons"
                    ).first()
                    update_appearance_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == "update_appearance_on_high_match"
                    ).first()

                    threshold = float(threshold_setting.value) if threshold_setting else 0.70
                    auto_create = auto_create_setting.value.lower() == "true" if auto_create_setting else True
                    update_appearance = update_appearance_setting.value.lower() == "true" if update_appearance_setting else True

                    match_results = await person_service.match_faces_to_persons(
                        db=db,
                        face_embedding_ids=face_ids,
                        auto_create=auto_create,
                        threshold=threshold,
                        update_appearance=update_appearance,
                    )

                    # Log person matches
                    matched = [r for r in match_results if r.person_id]
                    named = [r for r in matched if r.person_name]

                    if named:
                        logger.info(
                            f"Person matching complete for event {event_id}: {[r.person_name for r in named]}",
                            extra={
                                "event_type": "person_matching_complete",
                                "event_id": event_id,
                                "matched_persons": len(matched),
                                "named_persons": [r.person_name for r in named],
                                "new_persons": sum(1 for r in matched if r.is_new_person),
                            }
                        )
                    elif matched:
                        logger.debug(
                            f"Person matching complete for event {event_id}: {len(matched)} unnamed matches",
                            extra={
                                "event_type": "person_matching_complete",
                                "event_id": event_id,
                                "matched_persons": len(matched),
                                "new_persons": sum(1 for r in matched if r.is_new_person),
                            }
                        )
                else:
                    logger.debug(
                        f"No faces found in event {event_id}",
                        extra={
                            "event_type": "no_faces_found",
                            "event_id": event_id,
                        }
                    )
            finally:
                db.close()

        except Exception as e:
            # Face/person processing errors must not propagate (AC6)
            logger.warning(
                f"Face/person processing failed for event {event_id}: {e}",
                extra={
                    "event_type": "face_person_processing_error",
                    "event_id": event_id,
                    "error": str(e)
                }
            )

    async def _process_vehicles(
        self,
        event_id: str,
        thumbnail_base64: str,
        event_description: Optional[str] = None
    ) -> None:
        """
        Process vehicle detection, embedding, and matching for an event.

        Story P4-8.3: Vehicle detection and embedding storage with matching

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Uses its own database session since the caller's session may be closed.

        Args:
            event_id: UUID of the event to process
            thumbnail_base64: Base64-encoded thumbnail image
            event_description: AI-generated description for characteristics extraction

        Note:
            - Non-blocking, runs as background task
            - Only runs when vehicle_recognition_enabled is true
            - Errors don't propagate to caller
        """
        try:
            from app.services.vehicle_embedding_service import get_vehicle_embedding_service
            from app.services.vehicle_matching_service import get_vehicle_matching_service
            from app.models.system_setting import SystemSetting
            import base64

            vehicle_service = get_vehicle_embedding_service()
            matching_service = get_vehicle_matching_service()

            # Strip data URI prefix if present
            b64_str = thumbnail_base64
            if b64_str.startswith("data:"):
                comma_idx = b64_str.find(",")
                if comma_idx != -1:
                    b64_str = b64_str[comma_idx + 1:]

            thumbnail_bytes = base64.b64decode(b64_str)

            # Use own session since caller's may be closed
            db = SessionLocal()
            try:
                # Step 14a: Vehicle Detection and Embedding Storage (P4-8.3)
                vehicle_ids = await vehicle_service.process_event_vehicles(
                    db=db,
                    event_id=event_id,
                    thumbnail_bytes=thumbnail_bytes,
                )

                if vehicle_ids:
                    logger.info(
                        f"Vehicle processing complete for event {event_id}",
                        extra={
                            "event_type": "vehicle_processing_complete",
                            "event_id": event_id,
                            "vehicle_count": len(vehicle_ids),
                        }
                    )

                    # Step 14b: Vehicle Matching (P4-8.3)
                    # Get settings for vehicle matching
                    threshold_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == "vehicle_match_threshold"
                    ).first()
                    auto_create_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == "auto_create_vehicles"
                    ).first()

                    threshold = float(threshold_setting.value) if threshold_setting else 0.65
                    auto_create = auto_create_setting.value.lower() == "true" if auto_create_setting else True

                    match_results = await matching_service.match_vehicles_to_entities(
                        db=db,
                        vehicle_embedding_ids=vehicle_ids,
                        event_description=event_description,
                        auto_create=auto_create,
                        threshold=threshold,
                    )

                    # Log vehicle matches
                    matched = [r for r in match_results if r.vehicle_id]
                    named = [r for r in matched if r.vehicle_name]

                    if named:
                        logger.info(
                            f"Vehicle matching complete for event {event_id}: {[r.vehicle_name for r in named]}",
                            extra={
                                "event_type": "vehicle_matching_complete",
                                "event_id": event_id,
                                "matched_vehicles": len(matched),
                                "named_vehicles": [r.vehicle_name for r in named],
                                "new_vehicles": sum(1 for r in matched if r.is_new_vehicle),
                            }
                        )
                    elif matched:
                        logger.debug(
                            f"Vehicle matching complete for event {event_id}: {len(matched)} unnamed matches",
                            extra={
                                "event_type": "vehicle_matching_complete",
                                "event_id": event_id,
                                "matched_vehicles": len(matched),
                                "new_vehicles": sum(1 for r in matched if r.is_new_vehicle),
                            }
                        )
                else:
                    logger.debug(
                        f"No vehicles found in event {event_id}",
                        extra={
                            "event_type": "no_vehicles_found",
                            "event_id": event_id,
                        }
                    )
            finally:
                db.close()

        except Exception as e:
            # Vehicle processing errors must not propagate
            logger.warning(
                f"Vehicle processing failed for event {event_id}: {e}",
                extra={
                    "event_type": "vehicle_processing_error",
                    "event_id": event_id,
                    "error": str(e)
                }
            )

    async def _process_entity_alerts(
        self,
        event_id: str,
        description: str,
        has_person_or_vehicle: bool = True
    ) -> None:
        """
        Process entity alert enrichment for an event.

        Story P4-8.4: Named Entity Alerts

        This runs after face and vehicle matching to:
        1. Collect matched entity IDs from face and vehicle embeddings
        2. Enrich the description with entity names
        3. Set recognition status (known/stranger/unknown)
        4. Check for VIP entities

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Uses its own database session since the caller's session may be closed.

        Args:
            event_id: UUID of the event to process
            description: AI-generated description to enrich
            has_person_or_vehicle: Whether event has person/vehicle detection
        """
        try:
            from app.services.entity_alert_service import get_entity_alert_service
            from app.models.face_embedding import FaceEmbedding
            from app.models.vehicle_embedding import VehicleEmbedding
            import json

            entity_service = get_entity_alert_service()

            # Create new database session for background task
            db = SessionLocal()
            try:
                # Collect matched entity IDs from face and vehicle embeddings
                matched_entity_ids = []

                # Get entity IDs from face embeddings
                face_embeddings = db.query(FaceEmbedding).filter(
                    FaceEmbedding.event_id == event_id,
                    FaceEmbedding.entity_id.isnot(None)
                ).all()
                matched_entity_ids.extend([fe.entity_id for fe in face_embeddings])

                # Get entity IDs from vehicle embeddings
                vehicle_embeddings = db.query(VehicleEmbedding).filter(
                    VehicleEmbedding.event_id == event_id,
                    VehicleEmbedding.entity_id.isnot(None)
                ).all()
                matched_entity_ids.extend([ve.entity_id for ve in vehicle_embeddings])

                # Remove duplicates while preserving order
                matched_entity_ids = list(dict.fromkeys(matched_entity_ids))

                # Process entity alerts
                result = await entity_service.process_event_entities(
                    db=db,
                    event_id=event_id,
                    matched_entity_ids=matched_entity_ids,
                    original_description=description,
                    has_person_or_vehicle=has_person_or_vehicle
                )

                # Update event with entity information
                await entity_service.update_event_with_entity_info(
                    db=db,
                    event_id=event_id,
                    result=result
                )

                # Story P4-8.4: Send VIP notification if VIP entities detected
                # Only send if not suppressed (blocked entity takes precedence)
                if result.has_vip and not result.should_suppress and result.entity_names:
                    try:
                        from app.services.push_notification_service import send_event_notification
                        from app.models.event import Event

                        # Get event details for notification
                        event = db.query(Event).filter(Event.id == event_id).first()
                        if event:
                            # Get camera name
                            from app.models.camera import Camera
                            camera = db.query(Camera).filter(Camera.id == event.camera_id).first()
                            camera_name = camera.name if camera else "Unknown Camera"

                            # Use enriched description if available
                            notification_description = result.enriched_description or description

                            # Construct thumbnail URL
                            push_thumbnail_url = None
                            if event.thumbnail_path or event.thumbnail_base64:
                                date_str = event.timestamp.strftime("%Y-%m-%d")
                                push_thumbnail_url = f"/api/v1/thumbnails/{date_str}/{event_id}.jpg"

                            # Get smart detection type
                            smart_detection_type = event.smart_detection_type

                            # Fire and forget - VIP notification with entity info
                            asyncio.create_task(
                                send_event_notification(
                                    event_id=event_id,
                                    camera_name=camera_name,
                                    description=notification_description,
                                    thumbnail_url=push_thumbnail_url,
                                    camera_id=event.camera_id,
                                    smart_detection_type=smart_detection_type,
                                    anomaly_score=event.anomaly_score,
                                    entity_names=result.entity_names,
                                    is_vip=True,
                                    recognition_status=result.recognition_status,
                                )
                            )
                            logger.info(
                                f"VIP notification sent for event {event_id}: {result.entity_names}",
                                extra={
                                    "event_type": "vip_notification_sent",
                                    "event_id": event_id,
                                    "entity_names": result.entity_names,
                                    "vip_count": len(result.vip_entity_ids)
                                }
                            )
                    except Exception as notify_error:
                        # VIP notification failures should not block processing
                        logger.warning(
                            f"Failed to send VIP notification for event {event_id}: {notify_error}",
                            extra={"error": str(notify_error), "event_id": event_id}
                        )

                logger.info(
                    f"Entity alert processing complete for event {event_id}: "
                    f"status={result.recognition_status}, entities={len(matched_entity_ids)}",
                    extra={
                        "event_type": "entity_alert_complete",
                        "event_id": event_id,
                        "recognition_status": result.recognition_status,
                        "entity_count": len(matched_entity_ids),
                        "has_vip": result.has_vip,
                        "suppressed": result.should_suppress
                    }
                )

            finally:
                db.close()

        except Exception as e:
            # Entity alert errors must not propagate
            logger.warning(
                f"Entity alert processing failed for event {event_id}: {e}",
                extra={
                    "event_type": "entity_alert_error",
                    "event_id": event_id,
                    "error": str(e)
                }
            )

    async def _enrich_event_with_audio(
        self,
        event_id: str,
        camera_id: str,
    ) -> None:
        """
        Enrich a stored event with audio detection information (Story P6-3.2).

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Uses its own database session since the caller's session may be closed.

        Args:
            event_id: UUID of the event to enrich
            camera_id: Camera identifier

        Note:
            - Non-blocking, runs as background task
            - Only runs if camera has audio_enabled=True
            - Errors don't propagate to caller
            - Audio detection is configured via system settings thresholds
        """
        try:
            from app.services.audio_event_handler import get_audio_event_handler
            from app.models.event import Event

            audio_handler = get_audio_event_handler()

            # Use own session since caller's may be closed
            db = SessionLocal()
            try:
                # Get the stored event
                event = db.query(Event).filter(Event.id == event_id).first()
                if event is None:
                    logger.warning(
                        f"Event {event_id} not found for audio enrichment",
                        extra={"event_id": event_id, "camera_id": camera_id}
                    )
                    return

                # Enrich event with audio information
                enriched = await audio_handler.enrich_event_with_audio(
                    db=db,
                    event=event,
                    camera_id=camera_id,
                    audio_duration_seconds=2.0,
                )

                if enriched:
                    logger.info(
                        f"Event {event_id} enriched with audio",
                        extra={
                            "event_type": "audio_enrichment_complete",
                            "event_id": event_id,
                            "camera_id": camera_id,
                            "audio_event_type": event.audio_event_type,
                            "audio_confidence": event.audio_confidence,
                        }
                    )
                else:
                    logger.debug(
                        f"No audio events detected for event {event_id}",
                        extra={"event_id": event_id, "camera_id": camera_id}
                    )

            finally:
                db.close()

        except Exception as e:
            # Audio enrichment errors must not propagate
            logger.warning(
                f"Audio enrichment failed for event {event_id}: {e}",
                extra={
                    "event_type": "audio_enrichment_error",
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )

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

    def _generate_thumbnail(self, frame: np.ndarray, max_width: int = 320, max_height: int = 180) -> Optional[str]:
        """
        Generate a base64-encoded JPEG thumbnail from a frame.

        Args:
            frame: OpenCV frame (numpy array in BGR format)
            max_width: Maximum thumbnail width (default 320px)
            max_height: Maximum thumbnail height (default 180px)

        Returns:
            Base64-encoded JPEG string with data URI prefix, or None on error
        """
        try:
            import cv2
            import base64

            if frame is None:
                logger.warning("Cannot generate thumbnail: frame is None")
                return None

            # Calculate aspect-preserving resize
            height, width = frame.shape[:2]
            scale = min(max_width / width, max_height / height)

            if scale < 1:
                new_width = int(width * scale)
                new_height = int(height * scale)
                resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
            else:
                resized = frame

            # Encode as JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]
            success, buffer = cv2.imencode('.jpg', resized, encode_params)

            if not success:
                logger.warning("Failed to encode thumbnail as JPEG")
                return None

            # Convert to base64 with data URI prefix
            b64_str = base64.b64encode(buffer).decode('utf-8')
            return f"data:image/jpeg;base64,{b64_str}"

        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}", exc_info=True)
            return None

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
