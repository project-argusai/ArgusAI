"""
Event-Driven Processing Pipeline

This module implements an asynchronous event processing pipeline that orchestrates
motion detection, AI analysis, and event storage.

Architecture (after Phase 6 decomposition):
    - asyncio.Queue for event buffering
    - Per-camera motion detection tasks
    - AIProcessingWorker pool (extracted workers)
    - Focused helper methods extracted from the original _process_event
    - Improved dependency injection for ai_service, camera_service, motion_service
    - Graceful shutdown with queue draining

Key extractions:
    - AIProcessingWorker (worker loop + metrics)
    - Multiple focused helpers from _process_event (cost caps, embeddings, AI calls,
      push notifications, MQTT, HomeKit, entity linking, alerts, storage)

Performance Targets:
    - End-to-end latency: <5s p95 (motion → stored event)
    - Throughput: 10+ events per minute
"""
import asyncio
import logging
import time
import random
import httpx
import numpy as np
import uuid

from app.core.metrics import ai_concurrent_in_flight
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from contextlib import asynccontextmanager
import os
import json

from typing import TYPE_CHECKING

from app.models.camera import Camera
from app.models.event import Event
from app.models.system_setting import SystemSetting
from app.services.ai_service import AIService
from app.services.ai_processing_worker import AIProcessingWorker
from app.services.ai_worker_pool import AIWorkerPool
from app.services.ai_processing_coordinator import AIProcessingCoordinator
from app.services.ai_types import (
    FACE_RECOGNITION_ENABLED,
    VEHICLE_RECOGNITION_ENABLED,
    PERSON_MATCH_THRESHOLD,
    AUTO_CREATE_PERSONS,
    UPDATE_APPEARANCE_ON_HIGH_MATCH,
    VEHICLE_MATCH_THRESHOLD,
    AUTO_CREATE_VEHICLES,
)
from app.services.camera_service import CameraService
from app.services.motion_detection_service import MotionDetectionService, motion_detection_service
from app.services.cost_cap_service import get_cost_cap_service
from app.services.cost_alert_service import get_cost_alert_service
from app.services.carrier_extractor import extract_carrier
from app.core.database import get_db_session
from app.services.camera_task_manager import CameraTaskManager

if TYPE_CHECKING:
    from app.services.mqtt_service import MQTTService

logger = logging.getLogger(__name__)


def _get_container():
    """Lazy getter for the service container.

    Avoids circular import between event_processor <-> service_container
    (service_container imports the get_event_processor/reset functions).
    """
    from app.services.service_container import container
    return container



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
    Main event processing pipeline orchestrator.

    Responsibilities:
    - Per-camera motion detection task management
    - AI worker pool (using AIProcessingWorker instances)
    - Event queue management
    - Graceful shutdown and metrics

    Services can be injected for better testability and architecture
    (ai_service, camera_service, motion_service).

    Usage:
        processor = EventProcessor(worker_count=2)
        await processor.start()
        ...
        await processor.stop(timeout=30.0)
    """

    def __init__(
        self,
        worker_count: Optional[int] = None,
        queue_maxsize: int = 50,
        ai_service: Optional[AIService] = None,
        camera_service: Optional[CameraService] = None,
        motion_service: Optional[MotionDetectionService] = None,
    ):
        """
        Initialize EventProcessor

        Args:
            worker_count: Number of AI workers (default from env, fallback to 2)
            queue_maxsize: Maximum queue size (default 50)
            ai_service: Optional injected AIService (for testing and better architecture).
                        If not provided, one will be created on start().
            camera_service: Optional injected CameraService.
            motion_service: Optional injected MotionDetectionService.
        """
        self.worker_count = worker_count or int(os.getenv("EVENT_WORKER_COUNT", "2"))
        if self.worker_count < 2 or self.worker_count > 5:
            logger.warning(f"Worker count {self.worker_count} out of range [2-5], clamping")
            self.worker_count = max(2, min(5, self.worker_count))

        self.queue_maxsize = queue_maxsize
        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)

        # AI worker pool (now owns concurrency control + worker tasks)
        self.ai_worker_pool: Optional[AIWorkerPool] = None
        self.ai_processing_coordinator: Optional[AIProcessingCoordinator] = None

        # Temporary early semaphore (only used before pool is created, which is rare)
        self._early_ai_semaphore: Optional[asyncio.Semaphore] = None

        # CameraTaskManager owns per-camera monitoring tasks, stats, cooldowns, recovery, and health monitor
        self.camera_task_manager: Optional[CameraTaskManager] = None

        # Services (can be injected for better testability and architecture)
        self.ai_service: Optional[AIService] = ai_service
        self.camera_service: Optional[CameraService] = camera_service
        self.motion_service: Optional[MotionDetectionService] = motion_service
        self.http_client: Optional[httpx.AsyncClient] = None

        # State tracking
        self.running = False
        self.shutdown_event = asyncio.Event()

        # Metrics
        self.metrics = ProcessingMetrics()

        logger.info(f"EventProcessor initialized: {self.worker_count} workers, queue max {self.queue_maxsize}")

    @property
    def ai_semaphore(self) -> asyncio.Semaphore:
        """Concurrency limiter for AI calls (owned by AIWorkerPool)."""
        if self.ai_worker_pool:
            return self.ai_worker_pool.ai_semaphore
        # Fallback only before the pool is created (very early in startup)
        if self._early_ai_semaphore is None:
            ai_limit = int(os.getenv("AI_CONCURRENT_LIMIT", "8"))
            self._early_ai_semaphore = asyncio.Semaphore(ai_limit)
        return self._early_ai_semaphore

    @property
    def worker_tasks(self) -> List[asyncio.Task]:
        """Return active AI worker tasks (delegated to AIWorkerPool)."""
        if self.ai_worker_pool:
            return self.ai_worker_pool.worker_tasks
        return []

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

        # Initialize services (use injected ones if provided)
        if self.ai_service is None:
            self.ai_service = _get_container().ai_service
        if self.camera_service is None:
            self.camera_service = _get_container().camera_service
        if self.motion_service is None:
            self.motion_service = _get_container().motion_detection_service
        self.http_client = httpx.AsyncClient(timeout=10.0)

        # Create the CameraTaskManager (owns per-camera monitoring tasks + recovery)
        if self.camera_task_manager is None:
            self.camera_task_manager = CameraTaskManager(
                camera_service=self.camera_service,
                motion_service=self.motion_service,
                queue_event_callback=self.queue_event,
                health_check_interval=30.0,  # seconds
            )

        # Aliases removed - all access now goes through camera_task_manager

        # Load AI API keys from database
        with get_db_session() as db:
            await self.ai_service.load_api_keys_from_db(db)
            logger.info("AI service API keys loaded from database")

        # Start AI worker pool (now managed by AIWorkerPool)
        if self.ai_worker_pool is None:
            ai_limit = int(os.getenv("AI_CONCURRENT_LIMIT", "8"))

            self.ai_processing_coordinator = AIProcessingCoordinator(
                ai_service=self.ai_service,
                metrics=self.metrics,
                context_prompt_service=_get_container().context_prompt_service,
                cost_alert_service=_get_container().cost_alert_service,
                embedding_service=_get_container().embedding_service,
                mqtt_service=_get_container().mqtt_service,
                homekit_service=_get_container().homekit_service,
                face_embedding_service=_get_container().face_embedding_service,
                vehicle_embedding_service=_get_container().vehicle_embedding_service,
                entity_service=_get_container().entity_service,
                ai_semaphore=self.ai_worker_pool.ai_semaphore if self.ai_worker_pool else None,
            )

            self.ai_worker_pool = AIWorkerPool(
                worker_count=self.worker_count,
                event_queue=self.event_queue,
                process_event=self.ai_processing_coordinator.process_event,
                metrics=self.metrics,
                is_running=lambda: self.running,
                ai_concurrent_limit=ai_limit,
            )
        await self.ai_worker_pool.start()

        logger.info(f"Started {self.worker_count} AI workers via AIWorkerPool")

        # Start motion detection tasks for enabled cameras
        # Note: This will be called from FastAPI lifespan after camera service is initialized
        # For now, we'll load cameras from database
        try:
            with get_db_session() as db:
                enabled_cameras = db.query(Camera).filter(
                    Camera.is_enabled == True,
                    Camera.motion_enabled == True
                ).all()

                for camera in enabled_cameras:
                    await self.start_camera_monitoring(camera)

                logger.info(f"Started monitoring {len(enabled_cameras)} enabled cameras")

                # Start the camera health monitor for self-healing (now owned by CameraTaskManager)
                if self.camera_task_manager:
                    self.camera_task_manager.start_health_monitor()
        except Exception as e:
            logger.error(f"Failed to load enabled cameras: {e}", exc_info=True)

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

        # Stop motion detection tasks via CameraTaskManager
        logger.info("Stopping motion detection tasks...")
        if self.camera_task_manager:
            self.camera_task_manager.shutdown()
            await self.camera_task_manager.stop_all()

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

        # Stop AI workers (now fully owned by AIWorkerPool)
        logger.info("Stopping AI workers...")
        if self.ai_worker_pool:
            await self.ai_worker_pool.stop()
        # No more direct worker_tasks management on EventProcessor

        # Stop camera health monitor (now owned by CameraTaskManager)
        if self.camera_task_manager:
            await self.camera_task_manager.stop_health_monitor()

        # Close HTTP client
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None

        logger.info("EventProcessor stopped")

    async def start_camera_monitoring(self, camera: Camera):
        """
        Start motion detection task for a specific camera (delegated to CameraTaskManager).
        """
        if self.camera_task_manager:
            await self.camera_task_manager.start_monitoring(camera)

    async def stop_camera_monitoring(self, camera_id: str):
        """
        Stop motion detection task for a specific camera (delegated to CameraTaskManager).
        """
        if self.camera_task_manager:
            await self.camera_task_manager.stop_monitoring(camera_id)

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

            # Update cooldown via manager
            if self.camera_task_manager:
                self.camera_task_manager.update_cooldown(event.camera_id, time.time())

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
                if self.camera_task_manager:
                    self.camera_task_manager.update_cooldown(event.camera_id, time.time())
                self.metrics.queue_depth = self.event_queue.qsize()

            except Exception as e:
                logger.error(f"Failed to handle queue overflow: {e}", exc_info=True)
                self.metrics.increment_error("queue_overflow_handling_failed")

    async def _handle_cost_cap_skip(self, event: ProcessingEvent) -> bool:
        """
        Check cost caps before AI analysis.

        If analysis should be skipped due to cost caps, stores a minimal event
        and returns True. Otherwise returns False so normal processing can continue.

        Story P3-7.3
        """
        cost_cap_service = _get_container().cost_cap_service
        with get_db_session() as db:
            can_analyze, skip_reason = cost_cap_service.can_analyze(db)

        if can_analyze:
            return False

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
            "description_retry_needed": True,
            "analysis_skipped_reason": skip_reason,
        }

        success = await self._store_event_with_retry(event_data, max_retries=3)
        return success

    async def _process_event(self, event: ProcessingEvent, worker_id: int) -> bool:
        """
        Process a single event through the pipeline.

        This method orchestrates the core flow after an event has been queued:
        1. Cost cap check (early exit if needed)
        2. Thumbnail generation
        3. Early embedding + entity matching (for context)
        4. AI description generation (with context + OCR)
        5. Storage of the processed event
        6. Post-processing (push notifications, MQTT, HomeKit, entity alerts, face/vehicle processing)

        Most responsibilities have been extracted into focused helper methods
        for better maintainability and testability.

        Args:
            event: ProcessingEvent to process
            worker_id: Worker identifier for logging

        Returns:
            True if processing succeeded, False otherwise
        """
        try:
            # Story P3-7.3: Check cost caps before AI analysis
            handled = await self._handle_cost_cap_skip(event)
            if handled:
                return handled

            # Generate thumbnail
            thumbnail_base64 = self._generate_thumbnail(event.frame)

            # Early embedding + entity matching for context (Story P4-3.4)
            embedding_vector = None
            entity_result = None

            try:
                embedding_vector, entity_result = await self._generate_and_match_entity(thumbnail_base64)
            except Exception as context_error:
                logger.debug(
                    f"Early context generation failed (will skip): {context_error}",
                    extra={"camera_id": event.camera_id}
                )

            # Build context-enhanced prompt (Story P4-3.4)
            context_enhanced_prompt = None
            context_result = None

            try:
                context_service = _get_container().context_prompt_service

                # Build default base prompt
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

            # Generate AI description (with context if available)
            ai_result = await self._generate_ai_description(
                event=event,
                worker_id=worker_id,
                context_enhanced_prompt=context_enhanced_prompt,
                thumbnail_base64=thumbnail_base64,
            )

            if ai_result is None:
                # AI failed and we already stored a retry event
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

            # Story P15-5.3: Prepare bounding box annotation data
            has_annotations = False
            bounding_boxes_json = None
            if ai_result.bounding_boxes:
                import json
                has_annotations = True
                bounding_boxes_json = json.dumps(ai_result.bounding_boxes)
                logger.info(
                    f"Event has {len(ai_result.bounding_boxes)} bounding box annotations",
                    extra={
                        "camera_id": event.camera_id,
                        "box_count": len(ai_result.bounding_boxes)
                    }
                )

            # Store the successfully processed event (extracted)
            event_id = await self._store_processed_event(
                event=event,
                ai_result=ai_result,
                thumbnail_base64=thumbnail_base64,
                delivery_carrier=delivery_carrier,
                has_annotations=has_annotations,
                bounding_boxes_json=bounding_boxes_json,
            )

            if not event_id:
                return False

            # Evaluate alert rules (stub / Epic 5)

            # Check cost thresholds and send alerts (Story P3-7.4)
            try:
                cost_alert_service = _get_container().cost_alert_service
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

            # Send push notifications (extracted)
            await self._send_push_notification(
                event=event,
                event_id=event_id,
                ai_result=ai_result,
                thumbnail_base64=thumbnail_base64,
            )

            # Publish event to MQTT for Home Assistant (Story P4-2.3)
            try:
                from app.services.mqtt_service import get_mqtt_service, serialize_event_for_mqtt

                mqtt_service = _get_container().mqtt_service

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

            # Publish camera status sensors to MQTT (extracted)
            await self._publish_camera_status_sensors(event=event, event_id=event_id, ai_result=ai_result)

            # Store embedding for this event (Story P4-3.1, P4-3.4)
            # Note: Embedding was already generated earlier (Step 2) for context building
            # Here we just need to store it linked to the actual event_id
            # AC2: Embedding generated for each new event thumbnail
            # AC7: Graceful fallback if embedding generation fails
            try:
                if embedding_vector:
                    embedding_service = _get_container().embedding_service

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

            # Step 10: Trigger HomeKit sensors (extracted)
            await self._run_homekit_triggers(event=event, event_id=event_id, smart_detection_type=smart_detection_type)

            # Entity linking (extracted)
            await self._link_entity_to_event(event=event, event_id=event_id, embedding_vector=embedding_vector)

            # Face embeddings (privacy-gated, extracted)
            await self._process_face_embeddings(
                event=event,
                event_id=event_id,
                thumbnail_base64=thumbnail_base64,
            )

            # Vehicle embeddings (privacy-gated, extracted)
            await self._process_vehicle_embeddings(
                event=event,
                event_id=event_id,
                objects_json=objects_json,
                thumbnail_base64=thumbnail_base64,
                ai_result=ai_result,
                smart_detection_type=smart_detection_type,
            )
            # Entity alerts (privacy-gated, extracted)
            await self._process_entity_alerts(
                event=event,
                event_id=event_id,
                ai_result=ai_result,
                objects_detected=objects_detected,
            )

            # Audio Event Enrichment (Story P6-3.2)
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
            try:
                with get_db_session() as db:
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

                    # Story P15-5.3: Generate annotated thumbnail if bounding boxes available
                    has_annotations = event_data.get("has_annotations", False)
                    bounding_boxes_json = event_data.get("bounding_boxes")
                    # thumbnail_full_path is defined above when thumbnail_base64 is provided
                    if has_annotations and bounding_boxes_json and 'thumbnail_full_path' in locals() and thumbnail_full_path:
                        try:
                            annotation_service = _get_container().frame_annotation_service
                            parsed_boxes = json.loads(bounding_boxes_json)
                            annotated_path = annotation_service.annotate_frame(
                                thumbnail_full_path,
                                parsed_boxes
                            )
                            if annotated_path:
                                logger.debug(
                                    f"Annotated thumbnail generated: {annotated_path}",
                                    extra={"event_id": event_id}
                                )
                        except Exception as annotation_error:
                            # Annotation failures should not block event storage
                            logger.warning(
                                f"Failed to generate annotated thumbnail: {annotation_error}",
                                extra={"event_id": event_id, "error": str(annotation_error)}
                            )

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
                        # Story P15-5.1: AI Visual Annotations
                        has_annotations=has_annotations,
                        bounding_boxes=bounding_boxes_json,
                    )

                    db.add(event)
                    db.commit()

                    logger.info(
                        f"Event {event_id} stored successfully",
                        extra={"event_id": event_id, "camera_id": event_data["camera_id"]}
                    )

                    # Story P4-7.1 / P4-7.2: incremental activity baseline + anomaly
                    # scoring (non-blocking, own session). Delegated to
                    # EventAnomalyScorer (extracted during #530 / #443 decomposition).
                    from app.services.event_anomaly_scorer import get_event_anomaly_scorer
                    _anomaly_scorer = get_event_anomaly_scorer()
                    asyncio.create_task(
                        _anomaly_scorer.update_activity_baseline(event_data["camera_id"], event)
                    )
                    asyncio.create_task(
                        _anomaly_scorer.calculate_anomaly_score(event)
                    )

                    return event_id  # Return event_id instead of True

            except Exception as e:
                logger.error(
                    f"Event storage attempt {attempt + 1} failed: {e}",
                    exc_info=True,
                    extra={"attempt": attempt + 1, "max_retries": max_retries}
                )

            # Retry with exponential backoff
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait_time)

        logger.error(f"Event storage failed after {max_retries + 1} attempts")
        return None

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
            import base64

            face_service = _get_container().face_embedding_service
            person_service = _get_container().person_matching_service

            # Strip data URI prefix if present
            b64_str = thumbnail_base64
            if b64_str.startswith("data:"):
                comma_idx = b64_str.find(",")
                if comma_idx != -1:
                    b64_str = b64_str[comma_idx + 1:]

            thumbnail_bytes = base64.b64decode(b64_str)

            # Use own session since caller's may be closed
            with get_db_session() as db:
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
                    # Get settings for person matching (standardized in Phase B Slice 3)
                    threshold_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == PERSON_MATCH_THRESHOLD
                    ).first()
                    auto_create_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == AUTO_CREATE_PERSONS
                    ).first()
                    update_appearance_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == UPDATE_APPEARANCE_ON_HIGH_MATCH
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
            import base64

            vehicle_service = _get_container().vehicle_embedding_service
            matching_service = _get_container().vehicle_matching_service

            # Strip data URI prefix if present
            b64_str = thumbnail_base64
            if b64_str.startswith("data:"):
                comma_idx = b64_str.find(",")
                if comma_idx != -1:
                    b64_str = b64_str[comma_idx + 1:]

            thumbnail_bytes = base64.b64decode(b64_str)

            # Use own session since caller's may be closed
            with get_db_session() as db:
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
                    # Get settings for vehicle matching (standardized in Phase B Slice 3)
                    threshold_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == VEHICLE_MATCH_THRESHOLD
                    ).first()
                    auto_create_setting = db.query(SystemSetting).filter(
                        SystemSetting.key == AUTO_CREATE_VEHICLES
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

    async def _execute_entity_alerts(
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

            entity_service = _get_container().entity_alert_service

            # Create new database session for background task
            with get_db_session() as db:
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
            with get_db_session() as db:
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

    async def _generate_early_embedding(self, thumbnail_base64: Optional[str]) -> Optional[bytes]:
        """
        Generate an embedding vector from a thumbnail for early entity matching.

        This is done *before* the AI description so we can provide entity context
        to the vision model (Story P4-3.4).

        Returns the raw embedding bytes, or None on failure.
        """
        if not thumbnail_base64:
            return None

        try:
            import base64 as b64

            embedding_service = _get_container().embedding_service

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
                f"Early embedding generated (dim={len(embedding_vector) if embedding_vector else 0})",
                extra={"embedding_dim": len(embedding_vector) if embedding_vector else 0}
            )

            return embedding_vector

        except Exception as e:
            logger.debug(f"Early embedding generation failed: {e}")
            return None

    async def _generate_and_match_entity(
        self, thumbnail_base64: Optional[str]
    ) -> tuple[Optional[bytes], Optional[Any]]:
        """
        Generate embedding from thumbnail and attempt to match an existing entity.

        Returns (embedding_vector, entity_result) where either or both can be None.
        """
        embedding_vector = await self._generate_early_embedding(thumbnail_base64)
        if not embedding_vector:
            return None, None

        try:
            from app.core.database import SessionLocal

            entity_service = _get_container().entity_service

            with SessionLocal() as entity_db:
                entity_result = await entity_service.match_entity_only(
                    db=entity_db,
                    embedding=embedding_vector,
                    threshold=0.75,
                )

            if entity_result:
                logger.debug(
                    f"Entity matched for context",
                    extra={
                        "entity_id": entity_result.entity_id,
                        "entity_name": entity_result.name,
                        "similarity_score": entity_result.similarity_score,
                    }
                )
            else:
                logger.debug("No entity match for context")

            return embedding_vector, entity_result

        except Exception as e:
            logger.debug(f"Entity matching for context failed: {e}")
            return embedding_vector, None

    async def _send_push_notification(
        self,
        event: ProcessingEvent,
        event_id: str,
        ai_result: Any,
        thumbnail_base64: Optional[str],
    ) -> None:
        """Fire-and-forget push notification for a processed event."""
        try:
            from app.services.push_notification_service import send_event_notification

            push_thumbnail_url = None
            if thumbnail_base64:
                date_str = event.timestamp.strftime("%Y-%m-%d")
                push_thumbnail_url = f"/api/v1/thumbnails/{date_str}/{event_id}.jpg"

            smart_detection_type = event.metadata.get("smart_detection_type")
            if not smart_detection_type and event.detected_objects:
                obj = event.detected_objects[0].lower() if event.detected_objects else None
                if obj in ("person", "vehicle", "package", "animal"):
                    smart_detection_type = obj

            asyncio.create_task(
                send_event_notification(
                    event_id=event_id,
                    camera_name=event.camera_name,
                    description=ai_result.description,
                    thumbnail_url=push_thumbnail_url,
                    camera_id=event.camera_id,
                    smart_detection_type=smart_detection_type,
                )
            )
            logger.debug(
                f"Push notification task created for event {event_id}",
                extra={"event_id": event_id, "camera_name": event.camera_name}
            )
        except Exception as push_error:
            logger.warning(
                f"Failed to create push notification task: {push_error}",
                extra={"error": str(push_error)}
            )

    async def _publish_camera_status_sensors(
        self, event: ProcessingEvent, event_id: str, ai_result: Any
    ) -> None:
        """Publish last event timestamp, activity state, and event counts to MQTT."""
        try:
            from app.services.mqtt_status_service import get_camera_event_counts

            mqtt_service = _get_container().mqtt_service

            if not mqtt_service.is_connected:
                return

            with SessionLocal() as sensor_db:
                stored_event = sensor_db.query(Event).filter(Event.id == event_id).first()
                if not stored_event:
                    return

                # Publish last event timestamp
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

                # Publish activity state ON
                asyncio.create_task(
                    mqtt_service.publish_activity_state(
                        camera_id=event.camera_id,
                        state="ON",
                        last_event_at=stored_event.timestamp
                    )
                )

                # Publish updated event counts
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
                    extra={"event_id": event_id, "camera_id": event.camera_id}
                )
        except Exception as status_error:
            logger.warning(
                f"Failed to publish status sensors: {status_error}",
                extra={"error": str(status_error), "event_id": event_id}
            )

    async def _run_homekit_triggers(
        self, event: ProcessingEvent, event_id: str, smart_detection_type: Optional[str]
    ) -> None:
        """Trigger appropriate HomeKit sensors based on detection type.

        Delegates to EventHomeKitDispatcher (extracted during the #443 Phase B
        decomposition); the dispatcher owns the routing and per-sensor error
        containment.
        """
        from app.services.event_homekit_dispatcher import get_event_homekit_dispatcher

        await get_event_homekit_dispatcher().dispatch(event, event_id, smart_detection_type)

    async def _link_entity_to_event(
        self, event: ProcessingEvent, event_id: str, embedding_vector: Optional[bytes]
    ) -> None:
        """Match or create entity and link it to the event."""
        if not embedding_vector:
            logger.debug(
                f"Skipping entity matching - no embedding available for event {event_id}",
                extra={"event_id": event_id}
            )
            return

        try:
            entity_service = _get_container().entity_service

            # Determine entity type
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
        except Exception as entity_error:
            logger.warning(
                f"Entity linking failed for event {event_id}: {entity_error}",
                extra={"error": str(entity_error), "event_id": event_id}
            )

    async def _process_entity_alerts(
        self,
        event: ProcessingEvent,
        event_id: str,
        ai_result: Any,
        objects_detected: Optional[List[str]],
    ) -> None:
        """Privacy-gated entity alert processing (fire-and-forget)."""
        try:
            face_recognition_enabled = False
            vehicle_recognition_enabled = False

            with get_db_session() as db:
                # Use standardized constants (Phase B Slice 2)
                face_setting = db.query(SystemSetting).filter(
                    SystemSetting.key == FACE_RECOGNITION_ENABLED
                ).first()
                if face_setting and face_setting.value.lower() == "true":
                    face_recognition_enabled = True

                vehicle_setting = db.query(SystemSetting).filter(
                    SystemSetting.key == VEHICLE_RECOGNITION_ENABLED
                ).first()
                if vehicle_setting and vehicle_setting.value.lower() == "true":
                    vehicle_recognition_enabled = True

            if face_recognition_enabled or vehicle_recognition_enabled:
                has_person = "person" in objects_detected if objects_detected else False
                has_vehicle = "vehicle" in objects_detected if objects_detected else False

                if has_person or has_vehicle:
                    asyncio.create_task(
                        self._execute_entity_alerts(
                            event_id=event_id,
                            description=ai_result.description,
                            has_person_or_vehicle=True
                        )
                    )
                    logger.debug(
                        f"Entity alert task created for event {event_id}",
                        extra={"event_id": event_id, "camera_id": event.camera_id}
                    )
        except Exception as entity_alert_error:
            logger.warning(
                f"Failed to create entity alert task: {entity_alert_error}",
                extra={"error": str(entity_alert_error), "event_id": event_id}
            )

    async def _store_processed_event(
        self,
        event: ProcessingEvent,
        ai_result: Any,
        thumbnail_base64: Optional[str],
        delivery_carrier: Optional[str] = None,
        has_annotations: bool = False,
        bounding_boxes_json: Optional[str] = None,
    ) -> Optional[str]:
        """Build the rich event payload and store it after successful AI processing."""
        event_data = {
            "camera_id": event.camera_id,
            "timestamp": event.timestamp.isoformat(),
            "description": ai_result.description,
            "confidence": ai_result.confidence,
            "objects_detected": ai_result.objects_detected,
            "thumbnail_base64": thumbnail_base64,
            "alert_triggered": False,
            "provider_used": ai_result.provider,
            "description_retry_needed": False,
            "ai_cost": ai_result.cost_estimate,
            "delivery_carrier": delivery_carrier,
            "has_annotations": has_annotations,
            "bounding_boxes": bounding_boxes_json,
        }

        logger.info(f"Storing event for camera {event.camera_name}: {ai_result.description[:50]}...")
        event_id = await self._store_event_with_retry(event_data, max_retries=3)

        if not event_id:
            logger.error(
                f"Failed to store event for camera {event.camera_name}",
                extra={"camera_id": event.camera_id}
            )
            self.metrics.increment_error("event_storage_failed")

        return event_id

    async def _process_face_embeddings(
        self, event: ProcessingEvent, event_id: str, thumbnail_base64: Optional[str]
    ) -> None:
        """Privacy-gated face processing (fire-and-forget)."""
        try:
            from app.services.face_embedding_service import get_face_embedding_service

            face_recognition_enabled = False
            with get_db_session() as db:
                # Use standardized constant (Phase B Slice 2)
                setting = db.query(SystemSetting).filter(
                    SystemSetting.key == FACE_RECOGNITION_ENABLED
                ).first()
                if setting and setting.value.lower() == "true":
                    face_recognition_enabled = True

            if face_recognition_enabled and thumbnail_base64:
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
                        f"Face recognition disabled, skipping for event {event_id}",
                        extra={"event_id": event_id}
                    )
                elif not thumbnail_base64:
                    logger.debug(
                        f"No thumbnail available, skipping for event {event_id}",
                        extra={"event_id": event_id}
                    )
        except Exception as face_error:
            logger.warning(
                f"Failed to create face processing task: {face_error}",
                extra={"error": str(face_error), "event_id": event_id}
            )

    def get_metrics(self) -> Dict:
        """
        Get current pipeline metrics

        Returns:
            Dictionary with metrics data for /api/v1/metrics endpoint
        """
        data = self.metrics.to_dict()

        # Include camera health summary (from CameraService if available)
        if self.camera_service:
            try:
                all_status = self.camera_service.get_all_camera_status()
                data["cameras"] = {
                    cam_id: {
                        "status": status.get("status"),
                        "worker_alive": status.get("worker_alive", False),
                        "thread_alive": status.get("thread_alive", False),
                        "reconnections": status.get("reconnection_count", 0),
                    }
                    for cam_id, status in all_status.items()
                }
            except Exception:
                pass

        # Include motion task stats summary
        data["motion_tasks"] = self.get_motion_task_stats()
        data["health_monitor_running"] = self.is_health_monitor_running()
        data["ai_pool_running"] = self.is_ai_pool_running()
        data["active_ai_workers"] = self.active_ai_workers()

        return data

    def get_motion_task_stats(self) -> Dict[str, dict]:
        """Return per-camera motion detection task statistics (delegated to CameraTaskManager)."""
        if self.camera_task_manager:
            return self.camera_task_manager.get_motion_task_stats()
        return {}

    def is_health_monitor_running(self) -> bool:
        """Return whether the background camera health monitor is currently active."""
        if self.camera_task_manager:
            return self.camera_task_manager.is_health_monitor_running()
        return False

    def is_ai_pool_running(self) -> bool:
        """Return whether the AI worker pool is currently running."""
        if self.ai_worker_pool:
            return self.ai_worker_pool.is_running
        return False

    def active_ai_workers(self) -> int:
        """Return the number of currently active AI workers."""
        if self.ai_worker_pool:
            return self.ai_worker_pool.active_worker_count()
        return 0


# Global instance (initialized in FastAPI lifespan)
_event_processor: Optional[EventProcessor] = None


def get_event_processor() -> Optional[EventProcessor]:
    """
    Get the global EventProcessor instance

    Returns:
        EventProcessor instance or None if not initialized
    """
    return _event_processor


def reset_event_processor() -> None:
    """Reset the global EventProcessor instance (for testing)."""
    global _event_processor
    _event_processor = None


async def initialize_event_processor(
    worker_count: Optional[int] = None,
    ai_service: Optional[AIService] = None,
    camera_service: Optional[CameraService] = None,
    motion_service: Optional[MotionDetectionService] = None,
):
    """
    Initialize and start the global EventProcessor instance

    Called from FastAPI lifespan startup.

    Args:
        worker_count: Number of AI workers (default from env or 2)
        ai_service: Optional injected AIService
        camera_service: Optional injected CameraService
        motion_service: Optional injected MotionDetectionService
    """
    global _event_processor

    if _event_processor is not None:
        logger.warning("EventProcessor already initialized")
        return

    _event_processor = EventProcessor(
        worker_count=worker_count,
        ai_service=ai_service,
        camera_service=camera_service,
        motion_service=motion_service,
    )
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
