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

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Callable, Awaitable, Any

import numpy as np

from app.core.database import SessionLocal
from app.services.event_processor import ProcessingEvent, Event

if TYPE_CHECKING:
    from app.services.ai_service import AIService
    from app.services.metrics import ProcessingMetrics

logger = logging.getLogger(__name__)


@dataclass
class ProcessingContext:
    """
    Explicit dependencies needed by AIProcessingCoordinator.

    Goal: Depend on real services and focused helpers rather than the entire EventProcessor.
    This is an incremental improvement toward full decoupling.
    """
    # Core services
    ai_service: "AIService"
    metrics: "ProcessingMetrics"

    # Services obtained via container (preferred over bound methods where possible)
    context_prompt_service: Any
    cost_alert_service: Any
    embedding_service: Any
    mqtt_service: Any

    # Still-bound helper methods from EventProcessor (to be further extracted in future steps)
    generate_and_match_entity: Callable[[Optional[str]], Awaitable[tuple[Any, Any]]]
    # store_processed_event and send_push_notification have been moved into the coordinator
    store_event_with_retry: Callable[..., Awaitable[Optional[str]]]
    publish_camera_status_sensors: Callable[..., Awaitable[None]]
    # run_homekit_triggers has been moved into the coordinator
    link_entity_to_event: Callable[..., Awaitable[None]]
    process_face_embeddings: Callable[..., Awaitable[None]]
    # process_vehicle_embeddings has been moved into the coordinator
    # process_entity_alerts has been moved into the coordinator
    # enrich_event_with_audio has been moved into the coordinator
    publish_event_to_mqtt: Callable[..., Awaitable[None]]


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
        Process a single event through the pipeline.

        This method now owns the orchestration (moved from EventProcessor._process_event).
        Small helper methods are still called via the context.
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
                embedding_vector, entity_result = await self.context.generate_and_match_entity(thumbnail_base64)
            except Exception as context_error:
                logger.debug(
                    f"Early context generation failed (will skip): {context_error}",
                    extra={"camera_id": event.camera_id}
                )

            # Build context-enhanced prompt (Story P4-3.4)
            context_enhanced_prompt = None
            context_result = None

            try:
                context_service = self.context.context_prompt_service

                base_prompt = (
                    "Describe what you see in this image. Include: "
                    "WHO (people, their appearance, clothing), "
                    "WHAT (objects, vehicles, packages), "
                    "WHERE (location in frame), "
                    "and ACTIONS (what is happening). "
                    "Be specific and detailed."
                )

                temp_event_id = str(uuid.uuid4())

                with SessionLocal() as context_db:
                    context_result = await context_service.build_context_enhanced_prompt(
                        db=context_db,
                        event_id=temp_event_id,
                        base_prompt=base_prompt,
                        camera_id=event.camera_id,
                        event_time=event.timestamp,
                        matched_entity=entity_result,
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
            delivery_carrier = None
            try:
                delivery_carrier = extract_carrier(ai_result.description)
                if delivery_carrier:
                    logger.info(
                        f"Delivery carrier detected for camera {event.camera_name}: {delivery_carrier}",
                        extra={"camera_id": event.camera_id, "carrier": delivery_carrier},
                    )
            except Exception as carrier_error:
                logger.warning(
                    f"Carrier extraction failed for camera {event.camera_name}: {carrier_error}",
                    extra={"camera_id": event.camera_id, "error": str(carrier_error)}
                )

            # Prepare bounding box annotation data
            has_annotations = False
            bounding_boxes_json = None
            if ai_result.bounding_boxes:
                import json
                has_annotations = True
                bounding_boxes_json = json.dumps(ai_result.bounding_boxes)

            # Store the successfully processed event
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

            # Cost alerts
            try:
                cost_alert_service = self.context.cost_alert_service
                with SessionLocal() as db:
                    alerts = await cost_alert_service.check_and_notify(db)
                    if alerts:
                        logger.info(f"Cost alerts triggered: {len(alerts)} notifications sent")
            except Exception as alert_error:
                logger.warning(f"Failed to check cost alerts: {alert_error}")

            # Push notifications
            await self._send_push_notification(
                event=event,
                event_id=event_id,
                ai_result=ai_result,
                thumbnail_base64=thumbnail_base64,
            )

            # MQTT
            try:
                from app.services.mqtt_service import get_mqtt_service, serialize_event_for_mqtt
                mqtt_service = self.context.mqtt_service
                if mqtt_service.is_connected:
                    with SessionLocal() as mqtt_db:
                        stored_event = mqtt_db.query(Event).filter(Event.id == event_id).first()
                        if stored_event:
                            api_base_url = mqtt_service.get_api_base_url()
                            mqtt_payload = serialize_event_for_mqtt(
                                stored_event, event.camera_name, api_base_url=api_base_url
                            )
                            topic = mqtt_service.get_event_topic(event.camera_id)
                            asyncio.create_task(
                                self.context.publish_event_to_mqtt(mqtt_service, topic, mqtt_payload, event_id)
                            )
            except Exception as mqtt_error:
                logger.warning(f"Failed to create MQTT publish task: {mqtt_error}")

            # Camera status sensors
            await self._publish_camera_status_sensors(event=event, event_id=event_id, ai_result=ai_result)

            # Store embedding
            try:
                if embedding_vector:
                    embedding_service = self.context.embedding_service
                    with SessionLocal() as embed_db:
                        await embedding_service.store_embedding(
                            db=embed_db,
                            event_id=event_id,
                            embedding=embedding_vector,
                        )
            except Exception as embedding_error:
                logger.warning(f"Embedding storage failed for event {event_id}: {embedding_error}")

            # Determine smart_detection_type and objects for post-processing helpers
            smart_detection_type = getattr(event, 'smart_detection_type', None) or \
                                   (event.detected_objects[0].lower() if event.detected_objects else None)
            objects_detected = event.detected_objects or []
            objects_json = json.dumps(objects_detected) if objects_detected else None

            # Post-processing helpers (still on EventProcessor via context)
            await self._run_homekit_triggers(
                event=event, event_id=event_id, smart_detection_type=smart_detection_type
            )
            await self.context.link_entity_to_event(
                event=event, event_id=event_id, embedding_vector=embedding_vector
            )
            await self._process_face_embeddings(
                event=event, event_id=event_id, thumbnail_base64=thumbnail_base64
            )
            await self._process_vehicle_embeddings(
                event=event, event_id=event_id, objects_json=objects_json,
                thumbnail_base64=thumbnail_base64, ai_result=ai_result,
                smart_detection_type=smart_detection_type
            )
            await self._process_entity_alerts(
                event=event, event_id=event_id, ai_result=ai_result, objects_detected=objects_detected
            )

            # Audio enrichment (fire and forget)
            try:
                asyncio.create_task(
                    self._enrich_event_with_audio(event_id, event.camera_id)
                )
            except Exception as audio_error:
                logger.warning(f"Failed to create audio enrichment task: {audio_error}")

            logger.info(
                f"Event processed successfully for camera {event.camera_name}",
                extra={
                    "camera_id": event.camera_id,
                    "description": ai_result.description[:100],
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
            self.context.metrics.increment_error("processing_exception")
            return False

    async def _handle_cost_cap_skip(self, event: ProcessingEvent) -> bool:
        """
        Check cost caps before AI analysis.

        If analysis should be skipped due to cost caps, stores a minimal event
        and returns True. Otherwise returns False so normal processing can continue.

        Story P3-7.3
        """
        from app.services.service_container import container
        from app.core.database import get_db_session

        cost_cap_service = container.cost_cap_service
        with get_db_session() as db:
            can_analyze, skip_reason = cost_cap_service.can_analyze(db)

        if can_analyze:
            return False

        logger.info(
            f"AI analysis skipped for camera {event.camera_name} due to {skip_reason}",
            extra={"camera_id": event.camera_id, "skip_reason": skip_reason}
        )
        self.context.metrics.increment_error(f"cost_cap_{skip_reason}")

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

        success = await self.context.store_processed_event(event_data)
        return success

    async def _generate_ai_description(
        self,
        event: ProcessingEvent,
        worker_id: int,
        context_enhanced_prompt: Optional[str],
        thumbnail_base64: Optional[str],
    ) -> Optional[Any]:
        """
        Call the AI service to generate a description, with OCR and concurrency control.

        Returns the AIResult on success, or None if all providers failed
        (in which case a retry event has already been stored).
        """
        # Story P9-3.2: Extract OCR from frame overlay if enabled
        ocr_result = None
        try:
            from app.models.system_setting import SystemSetting
            from app.services.ocr_service import extract_overlay_text, is_ocr_available

            with SessionLocal() as ocr_db:
                setting = ocr_db.query(SystemSetting).filter(
                    SystemSetting.key == 'settings_attempt_ocr_extraction'
                ).first()
                if setting and setting.value.lower() == 'true' and is_ocr_available():
                    try:
                        ocr_result = extract_overlay_text(event.frame)
                    except Exception as ocr_err:
                        logger.warning(f"OCR extraction failed: {ocr_err}")
        except Exception as ocr_setup_err:
            logger.debug(f"OCR setup failed (non-critical): {ocr_setup_err}")

        # Limit concurrent AI calls (Phase A.5)
        # The semaphore is owned by the AIWorkerPool and exposed via the ai_service for now.
        semaphore = getattr(self.ai_service, 'ai_semaphore', None) or asyncio.Semaphore(8)
        async with semaphore:
            ai_concurrent_in_flight.inc()
            try:
                ai_result = await self.ai_service.generate_description(
                    frame=event.frame,
                    camera_name=event.camera_name,
                    timestamp=event.timestamp.isoformat(),
                    detected_objects=event.detected_objects,
                    sla_timeout_ms=5000,
                    custom_prompt=context_enhanced_prompt,
                    ocr_result=ocr_result,
                )
            finally:
                ai_concurrent_in_flight.dec()

        if not ai_result.success:
            logger.warning(
                f"All AI providers failed for camera {event.camera_name}, storing event for retry",
                extra={"camera_id": event.camera_id, "error": "All AI providers down"}
            )
            self.context.metrics.increment_error("ai_service_failed")

            event_data = {
                "camera_id": event.camera_id,
                "timestamp": event.timestamp.isoformat(),
                "description": "[AI description pending - providers unavailable]",
                "confidence": 0,
                "objects_detected": event.detected_objects,
                "thumbnail_base64": thumbnail_base64,
                "alert_triggered": False,
                "provider_used": None,
                "description_retry_needed": True,
            }

            # Use the store helper from the context for the retry case
            success = await self.context.store_event_with_retry(event_data, max_retries=3)
            if success:
                logger.info(
                    f"Event stored for retry: camera {event.camera_name}",
                    extra={"camera_id": event.camera_id, "description_retry_needed": True}
                )
            return None

        return ai_result

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
        event_id = await self.context.store_event_with_retry(event_data, max_retries=3)

        if not event_id:
            logger.error(
                f"Failed to store event for camera {event.camera_name}",
                extra={"camera_id": event.camera_id}
            )
            self.context.metrics.increment_error("event_storage_failed")

        return event_id

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

    async def _process_vehicle_embeddings(
        self,
        event: ProcessingEvent,
        event_id: str,
        objects_json: Optional[str],
        thumbnail_base64: Optional[str],
        ai_result: Any,
        smart_detection_type: Optional[str],
    ) -> None:
        """Privacy-gated vehicle embedding processing (fire-and-forget)."""
        try:
            # The heavy lifting is still in EventProcessor._process_vehicles for this step
            await self.event_processor._process_vehicles(
                event_id=event_id,
                thumbnail_base64=thumbnail_base64,
                event_description=ai_result.description
            )
            logger.debug(
                f"Vehicle embeddings task created for event {event_id}",
                extra={"event_id": event_id, "camera_id": event.camera_id}
            )
        except Exception as vehicle_error:
            logger.warning(
                f"Failed to create vehicle embeddings task: {vehicle_error}",
                extra={"error": str(vehicle_error), "event_id": event_id}
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

    async def _run_homekit_triggers(
        self, event: ProcessingEvent, event_id: str, smart_detection_type: Optional[str]
    ) -> None:
        """Trigger appropriate HomeKit sensors based on detection type."""
        try:
            from app.services.homekit_service import get_homekit_service

            homekit_service = self.context.mqtt_service  # Note: using mqtt_service temporarily; actual homekit_service should be added to context if needed
            # The original uses container.homekit_service. For consistency, we use context if available.

            # To keep this micro-step small, we delegate to the EventProcessor's version for now
            # (the heavy _trigger_homekit_* methods stay on EP).
            # In a follow-up we can move the full logic.
            await self.event_processor._run_homekit_triggers(
                event=event, event_id=event_id, smart_detection_type=smart_detection_type
            )
        except Exception as homekit_error:
            logger.warning(
                f"Failed to trigger HomeKit sensors: {homekit_error}",
                extra={"error": str(homekit_error), "event_id": event_id}
            )
