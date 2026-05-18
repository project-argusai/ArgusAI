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
    handle_cost_cap_skip: Callable[[ProcessingEvent], Awaitable[bool | None]]
    generate_thumbnail: Callable[[Any], Optional[str]]
    generate_and_match_entity: Callable[[Optional[str]], Awaitable[tuple[Any, Any]]]
    store_processed_event: Callable[..., Awaitable[Optional[str]]]
    send_push_notification: Callable[..., Awaitable[None]]
    publish_camera_status_sensors: Callable[..., Awaitable[None]]
    run_homekit_triggers: Callable[..., Awaitable[None]]
    link_entity_to_event: Callable[..., Awaitable[None]]
    process_face_embeddings: Callable[..., Awaitable[None]]
    process_vehicle_embeddings: Callable[..., Awaitable[None]]
    process_entity_alerts: Callable[..., Awaitable[None]]
    enrich_event_with_audio: Callable[[str, str], Awaitable[None]]
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
            handled = await self.context.handle_cost_cap_skip(event)
            if handled:
                return handled

            # Generate thumbnail
            thumbnail_base64 = self.context.generate_thumbnail(event.frame)

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
            event_id = await self.context.store_processed_event(
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
            await self.context.send_push_notification(
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
            await self.context.publish_camera_status_sensors(event=event, event_id=event_id, ai_result=ai_result)

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
            await self.context.run_homekit_triggers(
                event=event, event_id=event_id, smart_detection_type=smart_detection_type
            )
            await self.context.link_entity_to_event(
                event=event, event_id=event_id, embedding_vector=embedding_vector
            )
            await self.context.process_face_embeddings(
                event=event, event_id=event_id, thumbnail_base64=thumbnail_base64
            )
            await self.context.process_vehicle_embeddings(
                event=event, event_id=event_id, objects_json=objects_json,
                thumbnail_base64=thumbnail_base64, ai_result=ai_result,
                smart_detection_type=smart_detection_type
            )
            await self.context.process_entity_alerts(
                event=event, event_id=event_id, ai_result=ai_result, objects_detected=objects_detected
            )

            # Audio enrichment (fire and forget)
            try:
                asyncio.create_task(
                    self.context.enrich_event_with_audio(event_id, event.camera_id)
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
            success = await self.context.store_processed_event(event_data)
            if success:
                logger.info(
                    f"Event stored for retry: camera {event.camera_name}",
                    extra={"camera_id": event.camera_id, "description_retry_needed": True}
                )
            return None

        return ai_result
