"""
UniFi Protect Event Handler Service (Story P2-3.1, P2-3.3, P5-1.7)

Handles real-time motion/smart detection events from Protect WebSocket.
Implements event filtering based on per-camera configuration and
deduplication with cooldown logic. Submits events to AI pipeline and
stores results in database.

Story P5-1.7 adds HomeKit doorbell trigger for ring events.

Event Flow:
    uiprotect WebSocket Event
            ↓
    ProtectEventHandler.handle_event()
            ↓
    1. Parse event type (motion, smart_detect_*, ring)
            ↓
    2. Look up camera by protect_camera_id
            ↓
    3. Check camera.is_enabled
            ↓ (if not enabled → discard)
    4. Load smart_detection_types filter
            ↓
    5. Check event type matches filter
            ↓ (if not matching → discard)
    6. If this protect_event_id is already stored or in flight, merge new
       detection types and skip AI / notification (the 60s camera cooldown
       expires before Protect's update for the same event)
            ↓ (if known id → discard)
    7. Check deduplication cooldown
            ↓ (if duplicate → discard)
    8. Retrieve snapshot (Story P2-3.2)
            ↓
    9. Submit to AI pipeline (Story P2-3.3)
            ↓
    10. Store event in database (Story P2-3.3)
            ↓
    11. Broadcast EVENT_CREATED via WebSocket (Story P2-3.3)
    12. Trigger HomeKit doorbell if ring event (Story P5-1.7)
"""
import asyncio
import base64
import io
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, TYPE_CHECKING
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from uiprotect.data.types import EventType as ProtectEventType

from app.core.database import get_db_session
from app.models.camera import Camera
from app.models.event import Event
from app.services.snapshot_service import get_snapshot_service, SnapshotResult
from app.services.clip_service import get_clip_service
from app.services.frame_extractor import get_frame_extractor
from app.services.frame_storage_service import get_frame_storage_service
from app.services.video_storage_service import get_video_storage_service
from app.services.push_notification_service import send_event_notification
from app.core.decorators import singleton
from app.services.protect_event_filter import (
    ProtectEventFilter,
    get_protect_event_filter,
    EVENT_COOLDOWN_SECONDS,
)
from app.services.protect_ai_pipeline import ProtectAIPipeline, get_protect_ai_pipeline
from app.services.protect_media_service import ProtectMediaService, get_protect_media_service, MediaBundle
from app.services.protect_event_storage_service import ProtectEventStorageService, get_protect_event_storage_service
from app.services.protect_event_broadcaster import ProtectEventBroadcaster, get_protect_event_broadcaster

if TYPE_CHECKING:
    from app.services.ai_service import AIResult

logger = logging.getLogger(__name__)


def _format_timestamp_for_ai(timestamp: datetime, db: Session) -> str:
    """
    Format a timestamp for AI prompt using user's configured timezone.

    Delegates to the shared pre-AI helper so Protect and RTSP stay aligned.
    """
    from app.services.pre_ai_context_service import format_timestamp_for_ai

    return format_timestamp_for_ai(timestamp, db)


# EVENT_COOLDOWN_SECONDS moved to ProtectEventFilter (Phase 4)

# WebSocket message type for motion events (for future broadcast to frontend)
PROTECT_MOTION_EVENT = "PROTECT_MOTION_EVENT"

# Event type mapping from Protect to filter types (Story P2-3.1 AC2)
# Protect sends: motion, smart_detect_person, smart_detect_vehicle, etc.
# Filters use: motion, person, vehicle, package, animal, ring
EVENT_TYPE_MAPPING = {
    "motion": "motion",
    "smart_detect_person": "person",
    "smart_detect_vehicle": "vehicle",
    "smart_detect_package": "package",
    "smart_detect_animal": "animal",
    "ring": "ring",
}

# Valid event types we process
VALID_EVENT_TYPES = set(EVENT_TYPE_MAPPING.keys())

# Story P2-4.1: Doorbell-specific AI prompt for describing visitors
DOORBELL_RING_PROMPT = (
    "Describe who is at the front door. Include their appearance, what they're wearing, "
    "and if they appear to be a delivery person, visitor, or solicitor."
)


@singleton
class ProtectEventHandler:
    """
    Handles real-time events from UniFi Protect WebSocket (Story P2-3.1).

    Responsibilities:
    - Parse event types from uiprotect WSMessage
    - Look up camera by protect_camera_id and check if enabled
    - Filter events based on camera's smart_detection_types configuration
    - Deduplicate events using per-camera cooldown
    - Pass qualifying events to snapshot retrieval (Story P2-3.2)

    Attributes:
        _last_event_times: Dict tracking last event timestamp per camera
    """

    def __init__(self):
        """Initialize event handler with empty event tracking."""
        # Use the dedicated ProtectEventFilter for filtering + deduplication (Phase 4)
        self.event_filter: ProtectEventFilter = get_protect_event_filter()

        # AI analysis pipeline for Protect events (Phase 4)
        self.ai_pipeline: ProtectAIPipeline = get_protect_ai_pipeline()

        # Media retrieval coordination for Protect events (Phase 4)
        self.media_service: ProtectMediaService = get_protect_media_service()

        # Event storage service (Phase 4)
        self.storage_service: ProtectEventStorageService = get_protect_event_storage_service()

        # Event broadcasting (WebSocket + HomeKit) (Phase 4)
        self.broadcaster: ProtectEventBroadcaster = get_protect_event_broadcaster()

        # Push + MQTT for stored events (dropped in Phase B, restored here)
        from app.services.protect_event_notifications import get_protect_event_notifier

        self.notifier = get_protect_event_notifier()

        # Story P3-5.3: Track last audio transcription for passing to event storage
        self._last_audio_transcription: Optional[str] = None

    async def _link_cross_camera_incident(self, db: Session, stored_event: Event) -> None:
        """Group this stored event with other cameras inside the correlation window.

        Runs only after the row is committed, so it adds no time to AI description
        generation. Notifications are left unchanged: each camera still alerts on
        its own event.
        """
        try:
            from app.services.correlation_service import get_correlation_service

            await get_correlation_service().assign_group(db, stored_event)
        except Exception as exc:
            logger.warning(
                "Cross-camera correlation failed",
                extra={
                    "event_type": "correlation_link_failed",
                    "event_id": getattr(stored_event, "id", None),
                    "error_type": type(exc).__name__,
                },
            )

    def _persist_tracking_kwargs(self, media_fallback: Optional[str] = None) -> dict:
        """Assemble the analysis-mode tracking fields for event persistence from the
        AI pipeline's per-event state.

        The Phase-4 decomposition dropped this wiring: persist_protect_event was
        called without analysis_mode / frame_count_used, so every live event was
        stored as single_frame regardless of what the pipeline actually did, and
        pipeline-level fallback reasons (e.g. ``multi_frame_failed:...``) were never
        persisted — only the media-layer reason (clip download) was.

        The pipeline's own fallback reason takes precedence over the media-layer
        reason because it is the most proximate explanation for the analysis outcome.
        Capture this immediately after submit_snapshot_for_analysis returns, before
        any further awaits, since ProtectAIPipeline tracks state on a singleton.
        """
        return {
            "analysis_mode": self.ai_pipeline.last_analysis_mode or "single_frame",
            "frame_count_used": self.ai_pipeline.last_frame_count,
            "fallback_reason": self.ai_pipeline.last_fallback_reason or media_fallback,
        }

    def _post_ai_context_fields(
        self,
        ai_result: Optional["AIResult"],
        event_type: str,
        db: Optional[Session] = None,
        bundle: Any = None,
    ) -> dict:
        """Carrier extract, verified entity names, and named rewrite before first persist/notify.

        ``matched_entity_ids`` only carries entities the event supports (see
        ``event_entity_linking``): face-matched people, and a named vehicle
        backed by its crop gallery and/or a description that shows its make.
        A vehicle hint the evidence does not support is dropped instead of
        being stored.

        ``bundle`` is the pre-AI context captured right after the vision call;
        when omitted it is read from the pipeline.
        """
        import json
        from app.services.carrier_extractor import extract_carrier

        if bundle is None:
            bundle = getattr(self.ai_pipeline, "last_context_bundle", None)
        delivery_carrier = None
        description = getattr(ai_result, "description", None) if ai_result else None

        if description:
            try:
                delivery_carrier = extract_carrier(description)
            except Exception as e:
                logger.debug(f"Carrier extraction failed: {e}")
        if not delivery_carrier and ai_result is not None:
            from app.services.identification import carrier_from_identification
            delivery_carrier = carrier_from_identification(
                getattr(ai_result, "identification", None)
            )

        identity = self._verified_identity_fields(ai_result, event_type, db, bundle)
        matched_ids = identity["matched_ids"]
        enriched = identity["enriched"]
        recognition_status = identity["recognition_status"]

        context_stats = None
        if getattr(bundle, "context_stats", None):
            context_stats = json.dumps(bundle.context_stats)

        return {
            "delivery_carrier": delivery_carrier,
            "context_included": bool(getattr(bundle, "context_included", False)),
            "context_stats": context_stats,
            "recognition_status": recognition_status,
            "enriched_description": enriched or description,
            "matched_entity_ids": json.dumps(matched_ids) if matched_ids else None,
        }

    def _verified_identity_fields(
        self,
        ai_result: Optional["AIResult"],
        event_type: str,
        db: Optional[Session],
        bundle: Any,
    ) -> dict:
        """Verified entity ids (+ named rewrite when there is a description).

        Runs without a description too (the vision call failed): a
        face-matched person, or a vehicle its crop gallery and colour
        identify, is still linked. Never raises.
        """
        from app.services.entity_alert_service import (
            get_entity_alert_service,
            suppress_inconsistent_vehicle_identity,
        )
        from app.services.event_entity_linking import (
            event_looks_like_vehicle,
            verify_named_identities,
        )

        out = {"matched_ids": [], "enriched": None, "recognition_status": None}
        description = getattr(ai_result, "description", None) if ai_result else None
        candidates = list(getattr(bundle, "named_identities", None) or [])
        analysis = getattr(bundle, "object_analysis", None)
        if not (description or candidates or getattr(analysis, "vehicles", None)):
            return out
        try:
            entities = verify_named_identities(
                db,
                description=description,
                candidates=candidates,
                looks_like_vehicle=event_looks_like_vehicle(event_type, ai_result),
                embedding=getattr(bundle, "embedding_vector", None),
                object_analysis=analysis,
            )
            if entities:
                out["matched_ids"] = [e.entity_id for e in entities]
                out["recognition_status"] = "known"
                if description:
                    suppress_inconsistent_vehicle_identity(
                        description,
                        getattr(ai_result, "identification", None) if ai_result is not None else None,
                        entities,
                    )
                    enriched = get_entity_alert_service().enrich_description(description, entities)
                    if enriched and enriched != description and ai_result is not None:
                        ai_result.description = enriched
                    out["enriched"] = enriched
        except Exception as e:
            # Naming is best-effort: the event still stores unnamed.
            logger.warning(
                "Entity naming failed; storing event without names",
                extra={
                    "event_type": "protect_entity_naming_failed",
                    "error_type": type(e).__name__,
                },
            )
            out = {"matched_ids": [], "enriched": None, "recognition_status": None}
        return out

    def _identity_only_fields(self, event_type: str, db: Optional[Session], bundle: Any) -> dict:
        """Entity fields for an event stored without an AI description."""
        import json

        identity = self._verified_identity_fields(None, event_type, db, bundle)
        ids = identity["matched_ids"]
        return {
            "recognition_status": identity["recognition_status"],
            "matched_entity_ids": json.dumps(ids) if ids else None,
        }

    async def _run_entity_post_persist(self, stored_event: Any, bundle: Any = None) -> None:
        """Link the stored event's verified entities, run alert rules, store crops.

        Runs after the row is committed and broadcast, so it adds nothing to
        the time before the event appears. ``run_post_persist_entity_steps``
        bounds each step and never raises.
        """
        from app.services.event_entity_linking import run_post_persist_entity_steps

        await run_post_persist_entity_steps(
            getattr(stored_event, "id", None),
            session_factory=get_db_session,
            object_analysis=getattr(bundle, "object_analysis", None),
        )

    def _dispatch_notifications(self, stored_event: Any) -> None:
        """Start push + MQTT for the stored event in the background.

        Runs after the event is broadcast and its entities linked, so the push
        title can carry verified names. The notifier bounds and swallows every
        failure; this wrapper only guards the scheduling itself.
        """
        try:
            self.notifier.schedule(
                getattr(stored_event, "id", None), session_factory=get_db_session
            )
        except Exception as exc:
            logger.warning(
                "Protect notification dispatch failed",
                extra={
                    "event_type": "protect_notify_dispatch_failed",
                    "event_id": getattr(stored_event, "id", None),
                    "error_type": type(exc).__name__,
                },
            )

    def _schedule_local_redescribe(
        self,
        stored_event: Any,
        snapshot_result: Any,
        camera: Any,
        event_type: str,
        bundle: Any,
    ) -> None:
        """Hand a failed event to the local vision model, in the background.

        Called last on the AI-failure path, after the row is stored, linked,
        broadcast, and notified. Off unless LOCAL_VLM_ENABLED; scheduling
        never blocks and never raises (see ``local_vlm_fallback``).
        """
        try:
            from app.services.local_vlm_fallback import (
                RedescribeJob,
                get_local_vlm_fallback_service,
            )

            service = get_local_vlm_fallback_service()
            if not service.enabled:
                return

            def _fields(ai_result, db, _bundle=bundle, _type=event_type):
                return self._post_ai_context_fields(ai_result, _type, db, bundle=_bundle)

            service.schedule(
                RedescribeJob(
                    event_id=getattr(stored_event, "id", None),
                    image_base64=getattr(snapshot_result, "image_base64", None) or "",
                    camera_id=getattr(camera, "id", None),
                    camera_name=getattr(camera, "name", "") or "",
                    event_type=event_type,
                    local_timestamp=getattr(bundle, "local_timestamp", None),
                    custom_prompt=getattr(bundle, "custom_prompt", None),
                    fields_builder=_fields,
                )
            )
        except Exception as exc:
            logger.warning(
                "Local VLM fallback scheduling failed",
                extra={
                    "event_type": "local_vlm_schedule_failed",
                    "event_id": getattr(stored_event, "id", None),
                    "error_type": type(exc).__name__,
                },
            )

    async def _store_protect_embedding(self, event_id: str) -> None:
        """Persist the in-memory CLIP vector so Protect events become RAG candidates."""
        bundle = getattr(self.ai_pipeline, "last_context_bundle", None)
        embedding = getattr(bundle, "embedding_vector", None)
        if not embedding or not event_id:
            return
        try:
            from app.services.embedding_service import get_embedding_service

            with get_db_session() as embed_db:
                await get_embedding_service().store_embedding(embed_db, event_id, embedding)
        except Exception as e:
            logger.warning(
                f"Protect embedding store failed for event {event_id}: {e}",
                extra={"event_id": event_id, "error": str(e)},
            )

    def _try_ocr_extraction(self, frame, db) -> Optional[str]:
        """Extract overlay text from a frame via OCR, if enabled in settings.

        Returns the extracted text, or None when OCR is disabled or unavailable.

        NOTE: This method's `def` line was accidentally dropped in a refactor,
        leaving the body orphaned inside __init__ and crashing handler
        construction with `NameError: name 'db' is not defined`. Restoring the
        signature (frame, db) — matching the existing tests — fixes startup.
        """
        from app.models.system_setting import SystemSetting
        from app.services.ocr_service import extract_overlay_text, is_ocr_available

        # Check if OCR is enabled in settings
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == 'settings_attempt_ocr_extraction'
        ).first()
        if not (setting and setting.value.lower() == 'true'):
            return None

        # Check if tesseract is available
        if not is_ocr_available():
            return None

        try:
            return extract_overlay_text(frame)
        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")
            return None

    async def handle_event(
        self,
        controller_id: str,
        msg: Any
    ) -> bool:
        """
        Handle a WebSocket event from uiprotect (Story P2-3.1 AC1).

        Processes motion/smart detection events through filtering and
        deduplication before passing to next stage.

        Args:
            controller_id: Controller UUID
            msg: WebSocket message from uiprotect (WSSubscriptionMessage)

        Returns:
            True if event was processed, False if filtered/skipped
        """
        reservation_pid: Optional[str] = None
        keep_reservation = False
        try:
            # Extract new_obj from message
            new_obj = getattr(msg, 'new_obj', None)
            if not new_obj:
                return False

            # Process Camera, Doorbell, or native Event objects
            model_type = type(new_obj).__name__

            # Handle native Event objects from uiprotect (motion, smart detection, ring)
            if model_type == 'Event':
                return await self._handle_native_event(controller_id, new_obj)

            # Only process Camera or Doorbell state updates (legacy path)
            if model_type not in ('Camera', 'Doorbell'):
                return False

            # Extract protect_camera_id
            protect_camera_id = str(getattr(new_obj, 'id', ''))
            if not protect_camera_id:
                return False

            # Debug: Log raw motion/smart detection state for troubleshooting
            is_motion = getattr(new_obj, 'is_motion_currently_detected', None)
            is_smart_detected = getattr(new_obj, 'is_smart_currently_detected', None)
            is_person = getattr(new_obj, 'is_person_currently_detected', None)
            is_vehicle = getattr(new_obj, 'is_vehicle_currently_detected', None)
            is_package = getattr(new_obj, 'is_package_currently_detected', None)
            is_animal = getattr(new_obj, 'is_animal_currently_detected', None)
            last_smart_event_ids = getattr(new_obj, 'last_smart_detect_event_ids', None)
            active_smart_types = getattr(new_obj, 'active_smart_detect_types', None)
            logger.debug(
                f"WebSocket update for {model_type} {protect_camera_id[:8]}...: "
                f"motion={is_motion}, smart={is_smart_detected}, "
                f"person={is_person}, vehicle={is_vehicle}, package={is_package}, animal={is_animal}",
                extra={
                    "event_type": "protect_ws_update",
                    "model_type": model_type,
                    "protect_camera_id": protect_camera_id,
                    "is_motion_currently_detected": is_motion,
                    "is_smart_currently_detected": is_smart_detected,
                    "is_person_currently_detected": is_person,
                    "is_vehicle_currently_detected": is_vehicle,
                    "is_package_currently_detected": is_package,
                    "is_animal_currently_detected": is_animal,
                    "last_smart_detect_event_ids": str(last_smart_event_ids) if last_smart_event_ids else None,
                    "active_smart_detect_types": str(active_smart_types) if active_smart_types else None
                }
            )

            # Parse event types from the message (AC2)
            event_types = self._parse_event_types(new_obj, model_type)
            if not event_types:
                return False

            # Look up camera in database (AC3)
            with get_db_session() as db:
                camera = self._get_camera_by_protect_id(db, protect_camera_id)

                # Check if camera is enabled for AI analysis (AC3, AC4)
                if not camera:
                    logger.debug(
                        "Event from unregistered camera - discarding",
                        extra={
                            "event_type": "protect_event_unknown_camera",
                            "controller_id": controller_id,
                            "protect_camera_id": protect_camera_id
                        }
                    )
                    return False

                if not camera.is_enabled or camera.source_type != 'protect':
                    logger.debug(
                        f"Event from disabled camera '{camera.name}' - discarding",
                        extra={
                            "event_type": "protect_event_disabled_camera",
                            "controller_id": controller_id,
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                            "is_enabled": camera.is_enabled,
                            "source_type": camera.source_type
                        }
                    )
                    return False

                # Log event received (AC11)
                logger.info(
                    f"Event received from camera '{camera.name}': {', '.join(event_types)}",
                    extra={
                        "event_type": "protect_event_received",
                        "controller_id": controller_id,
                        "camera_id": camera.id,
                        "camera_name": camera.name,
                        "detected_types": event_types,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )

                # Load and check smart_detection_types filter (AC5, AC6, AC7, AC8)
                smart_detection_types = self._load_smart_detection_types(camera)
                protect_event_id = self._extract_protect_event_id(msg)
                accepted_types = self._accepted_filter_types(
                    event_types, smart_detection_types, camera.name
                )
                # Same Protect id (a type added later, or the event ending) must
                # not start a second analysis once the 60s camera cooldown ends.
                if accepted_types and self._absorb_known_protect_event(
                    db,
                    camera,
                    protect_event_id,
                    accepted_types,
                    is_doorbell_ring="ring" in accepted_types,
                ):
                    return False

                for event_type in event_types:
                    # Map event type to filter type
                    filter_type = EVENT_TYPE_MAPPING.get(event_type)
                    if not filter_type:
                        continue

                    # Check if event should be processed (delegated to ProtectEventFilter)
                    if not self.event_filter.should_process_event(filter_type, smart_detection_types, camera.name):
                        continue

                    # Check deduplication cooldown (delegated to ProtectEventFilter)
                    if self.event_filter.is_duplicate_event(camera.id, camera.name):
                        continue

                    # Reserve the Protect id before any await so a concurrent
                    # update cannot also pass the database lookup.
                    if protect_event_id and not self.event_filter.try_begin_protect_event(
                        protect_event_id
                    ):
                        self._absorb_known_protect_event(
                            db,
                            camera,
                            protect_event_id,
                            accepted_types,
                            is_doorbell_ring="ring" in accepted_types,
                        )
                        return False
                    reservation_pid = protect_event_id

                    # Event passed all filters - record it in the filter for cooldown tracking
                    self.event_filter.record_event(camera.id)
                    event_timestamp = datetime.now(timezone.utc)

                    # Generate event ID early for clip download filename
                    generated_event_id = str(uuid.uuid4())

                    logger.info(
                        f"Event passed filters for camera '{camera.name}': {event_type}",
                        extra={
                            "event_type": "protect_event_passed",
                            "controller_id": controller_id,
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                            "detected_type": event_type,
                            "filter_type": filter_type
                        }
                    )

                    # Story P2-4.1: Check if this is a doorbell ring event
                    is_doorbell_ring = (filter_type == "ring")

                    # Retrieve appropriate media (snapshot + optional clip) via dedicated service (Phase 4)
                    media = await self.media_service.get_media_for_event(
                        controller_id=controller_id,
                        protect_camera_id=camera.protect_camera_id,
                        camera_id=camera.id,
                        camera_name=camera.name,
                        event_id=generated_event_id,
                        event_timestamp=event_timestamp,
                        is_doorbell_ring=is_doorbell_ring,
                        analysis_mode=camera.analysis_mode,
                    )

                    snapshot_result = media.snapshot_result
                    clip_path = media.clip_path
                    media_fallback = media.fallback_reason

                    if not snapshot_result:
                        # Story P3-1.4 AC3: Clean up clip if snapshot retrieval failed
                        if clip_path:
                            try:
                                clip_service = get_clip_service()
                                clip_service.cleanup_clip(generated_event_id)
                            except Exception:
                                pass  # Best effort cleanup
                        return False

                    # Story P2-4.1 AC6: For doorbell rings, broadcast DOORBELL_RING immediately
                    # before AI processing for fast notification
                    if is_doorbell_ring:
                        await self.broadcaster.broadcast_doorbell_ring(
                            camera_id=camera.id,
                            camera_name=camera.name,
                            thumbnail_url=snapshot_result.thumbnail_path,
                            timestamp=snapshot_result.timestamp
                        )

                        # Story P5-1.7: Trigger HomeKit doorbell notification
                        self.broadcaster.trigger_homekit_doorbell(camera.id, generated_event_id)

                    # Track total processing time (AC10, AC11)
                    pipeline_start = time.time()

                    # Story P3-1.4 AC1: Pass clip_path to AI pipeline (for future multi-frame analysis)
                    ai_result = await self.ai_pipeline.submit_snapshot_for_analysis(
                        snapshot_result,
                        camera,
                        filter_type,
                        is_doorbell_ring=is_doorbell_ring,
                        clip_path=clip_path,
                        clip_plan=getattr(media, "clip_plan", None),
                    )

                    # Capture the pipeline's ACTUAL analysis outcome now — singleton
                    # state is per-event and must be read before any further awaits.
                    persist_tracking = self._persist_tracking_kwargs(media_fallback)
                    context_bundle = getattr(self.ai_pipeline, "last_context_bundle", None)

                    # Story P3-1.4 AC3: Always cleanup clip after AI processing
                    if clip_path:
                        try:
                            clip_service = get_clip_service()
                            cleanup_success = clip_service.cleanup_clip(generated_event_id)
                            logger.debug(
                                f"Clip cleanup {'succeeded' if cleanup_success else 'failed'} for event {generated_event_id[:8]}...",
                                extra={
                                    "event_type": "clip_cleanup",
                                    "event_id": generated_event_id,
                                    "cleanup_success": cleanup_success
                                }
                            )
                        except Exception as e:
                            logger.warning(
                                f"Clip cleanup error for event {generated_event_id[:8]}...: {e}",
                                extra={
                                    "event_type": "clip_cleanup_error",
                                    "event_id": generated_event_id,
                                    "error_type": type(e).__name__
                                }
                            )

                    if not ai_result or not ai_result.success:
                        # Story P3-3.5 AC3: Complete failure - all analysis modes exhausted
                        # Create event with "AI analysis unavailable" instead of returning False
                        from app.services.ai_provider_order import analysis_failure_log_detail
                        from app.services.protect_event_storage_service import (
                            ai_response_time_ms_from_result,
                        )

                        logger.error(
                            "AI pipeline completely failed for camera '%s' - saving event without description",
                            camera.name,
                            extra={
                                "event_type": "protect_ai_complete_failure",
                                "camera_id": camera.id,
                                "camera_name": camera.name,
                                "event_id": generated_event_id,
                                "error": (
                                    analysis_failure_log_detail(ai_result.error)
                                    if ai_result and ai_result.error
                                    else "no_result"
                                ),
                                "fallback_chain": getattr(self, '_fallback_chain', [])
                            }
                        )

                        # Store via new service (no AI result). Keep the vision-call
                        # duration even though the description itself was not saved.
                        stored_event = await self.storage_service.persist_protect_event(
                            db=db,
                            camera=camera,
                            snapshot_result=snapshot_result,
                            ai_result=None,
                            protect_event_id=protect_event_id,
                            event_type=filter_type,
                            is_doorbell_ring=is_doorbell_ring,
                            event_id_override=generated_event_id,
                            ai_response_time_ms=ai_response_time_ms_from_result(ai_result),
                            **persist_tracking,
                            **self._identity_only_fields(filter_type, db, context_bundle),
                        )

                        if stored_event:
                            keep_reservation = True
                            self._apply_pending_protect_update(
                                db, stored_event, protect_event_id
                            )
                            # Broadcast the event even without AI description
                            await self._link_cross_camera_incident(db, stored_event)
                            await self.broadcaster.broadcast_event_created(stored_event, camera)
                            await self._run_entity_post_persist(stored_event, context_bundle)
                            # Push + MQTT (even without AI)
                            self._dispatch_notifications(stored_event)
                            self._schedule_local_redescribe(
                                stored_event, snapshot_result, camera, filter_type, context_bundle
                            )
                            return True

                        return False

                    # Story P2-3.3: Store event in database via storage service (Phase 4)
                    stored_event = await self.storage_service.persist_protect_event(
                        db=db,
                        camera=camera,
                        snapshot_result=snapshot_result,
                        ai_result=ai_result,
                        protect_event_id=str(protect_event_id) if protect_event_id else None,
                        event_type=filter_type,
                        is_doorbell_ring=is_doorbell_ring,
                        event_id_override=generated_event_id,
                        **persist_tracking,
                        **self._post_ai_context_fields(ai_result, filter_type, db, context_bundle),
                    )

                    if not stored_event:
                        return False

                    keep_reservation = True
                    self._apply_pending_protect_update(db, stored_event, protect_event_id)

                    await self._store_protect_embedding(stored_event.id)

                    # Track and log processing time (AC10, AC11)
                    processing_time_ms = int((time.time() - pipeline_start) * 1000)
                    if processing_time_ms > 2000:  # NFR2: 2 second target
                        logger.warning(
                            f"Processing time {processing_time_ms}ms exceeds 2s target for camera '{camera.name}'",
                            extra={
                                "event_type": "protect_latency_warning",
                                "camera_id": camera.id,
                                "processing_time_ms": processing_time_ms
                            }
                        )
                    else:
                        logger.info(
                            f"Event processed in {processing_time_ms}ms for camera '{camera.name}'",
                            extra={
                                "event_type": "protect_event_processed",
                                "camera_id": camera.id,
                                "processing_time_ms": processing_time_ms
                            }
                        )

                    # Group with other cameras before the live update so the payload
                    # carries correlation_group_id. MQTT stays on its existing path.
                    await self._link_cross_camera_incident(db, stored_event)

                    # Story P2-3.3: Broadcast EVENT_CREATED via WebSocket (AC12)
                    await self.broadcaster.broadcast_event_created(stored_event, camera)
                    await self._run_entity_post_persist(stored_event, context_bundle)
                    self._dispatch_notifications(stored_event)

                    return True

                return False

        except Exception as e:
            logger.warning(
                f"Error handling Protect event: {e}",
                extra={
                    "event_type": "protect_event_handler_error",
                    "controller_id": controller_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return False
        finally:
            if reservation_pid and not keep_reservation:
                self.event_filter.abandon_protect_event(reservation_pid)

    def _parse_event_types(self, obj: Any, model_type: str) -> List[str]:
        """
        Parse event types from uiprotect object (Story P2-3.1 AC2).

        Extracts motion and smart detection types from the camera object.

        Args:
            obj: Camera or Doorbell object from uiprotect
            model_type: "Camera" or "Doorbell"

        Returns:
            List of event type strings (e.g., ["motion", "smart_detect_person"])
        """
        event_types = []

        # Check for motion detection
        # uiprotect uses 'is_motion_currently_detected' (not 'is_motion_detected')
        is_motion_detected = getattr(obj, 'is_motion_currently_detected', False)
        if is_motion_detected:
            event_types.append("motion")

        # Check for smart detection types using individual detection flags
        # These are the most reliable indicators of what was actually detected
        smart_detect_checks = [
            ('is_person_currently_detected', 'smart_detect_person'),
            ('is_vehicle_currently_detected', 'smart_detect_vehicle'),
            ('is_package_currently_detected', 'smart_detect_package'),
            ('is_animal_currently_detected', 'smart_detect_animal'),
        ]

        for attr_name, event_key in smart_detect_checks:
            if getattr(obj, attr_name, False):
                if event_key in VALID_EVENT_TYPES:
                    event_types.append(event_key)

        # Also check is_smart_currently_detected as a fallback for other smart detection types
        # This catches any smart detections not covered by the individual checks above
        is_smart_detected = getattr(obj, 'is_smart_currently_detected', False)
        if is_smart_detected and not any(e.startswith('smart_detect_') for e in event_types):
            # No specific smart detection found yet, try to extract from last_smart_detect_event_ids
            last_smart_event_ids = getattr(obj, 'last_smart_detect_event_ids', {})
            if last_smart_event_ids:
                for detect_type in last_smart_event_ids.keys():
                    detect_value = getattr(detect_type, 'value', str(detect_type)).lower()
                    event_key = f"smart_detect_{detect_value}"
                    if event_key in VALID_EVENT_TYPES and event_key not in event_types:
                        event_types.append(event_key)
            else:
                # Final fallback: use active_smart_detect_types
                active_types = getattr(obj, 'active_smart_detect_types', set())
                for detect_type in active_types:
                    detect_value = getattr(detect_type, 'value', str(detect_type)).lower()
                    event_key = f"smart_detect_{detect_value}"
                    if event_key in VALID_EVENT_TYPES and event_key not in event_types:
                        event_types.append(event_key)

        # Check for doorbell ring (specific to doorbells)
        if model_type == 'Doorbell':
            is_ringing = getattr(obj, 'is_ringing', False)
            if is_ringing:
                event_types.append("ring")

        return event_types

    async def _handle_native_event(self, controller_id: str, event_obj: Any) -> bool:
        """
        Handle native uiprotect Event objects.

        These are direct event notifications from Protect (MOTION, SMART_DETECT, RING)
        rather than Camera state updates.

        Args:
            controller_id: Controller UUID
            event_obj: Native Event object from uiprotect

        Returns:
            True if event was processed, False if filtered/skipped
        """
        reservation_pid: Optional[str] = None
        keep_reservation = False
        try:
            # Get event properties
            event_type = getattr(event_obj, 'type', None)
            protect_camera_id = getattr(event_obj, 'camera_id', None)
            smart_detect_types = getattr(event_obj, 'smart_detect_types', []) or []
            event_start = getattr(event_obj, 'start', None)
            protect_event_id = getattr(event_obj, 'id', None)

            # Only process motion, smart detection, and ring events
            if event_type not in (ProtectEventType.MOTION, ProtectEventType.SMART_DETECT, ProtectEventType.RING):
                logger.debug(
                    f"Native Event type {event_type} not processable - skipping",
                    extra={
                        "event_type": "protect_native_event_skipped",
                        "protect_event_type": str(event_type) if event_type else None,
                    }
                )
                return False

            if not protect_camera_id:
                logger.debug(
                    f"Native event has no camera_id - skipping",
                    extra={
                        "event_type": "protect_native_event_no_camera",
                        "protect_event_type": str(event_type),
                        "protect_event_id": str(protect_event_id) if protect_event_id else None,
                    }
                )
                return False

            # Convert to our event type format
            event_types = []
            if event_type == ProtectEventType.MOTION:
                event_types.append("motion")
            elif event_type == ProtectEventType.RING:
                event_types.append("ring")
            elif event_type == ProtectEventType.SMART_DETECT:
                # Convert smart_detect_types to our format
                for smart_type in smart_detect_types:
                    smart_value = getattr(smart_type, 'value', str(smart_type)).lower()
                    event_key = f"smart_detect_{smart_value}"
                    if event_key in VALID_EVENT_TYPES:
                        event_types.append(event_key)
                # If no specific smart type found, fall back to motion
                if not event_types:
                    event_types.append("motion")

            logger.info(
                f"Native Protect event received: {event_type.value}, types={event_types}",
                extra={
                    "event_type": "protect_native_event_received",
                    "controller_id": controller_id,
                    "protect_camera_id": protect_camera_id,
                    "protect_event_type": event_type.value,
                    "detected_types": event_types,
                    "smart_detect_types": [str(t) for t in smart_detect_types],
                    "protect_event_id": str(protect_event_id) if protect_event_id else None,
                }
            )

            # Look up camera and process
            with get_db_session() as db:
                camera = self._get_camera_by_protect_id(db, protect_camera_id)

                if not camera:
                    logger.debug(
                        f"Native event from unregistered camera - discarding",
                        extra={
                            "event_type": "protect_native_event_unknown_camera",
                            "controller_id": controller_id,
                            "protect_camera_id": protect_camera_id
                        }
                    )
                    return False

                if not camera.is_enabled or camera.source_type != 'protect':
                    logger.debug(
                        f"Native event from disabled camera '{camera.name}' - discarding",
                        extra={
                            "event_type": "protect_native_event_disabled_camera",
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                        }
                    )
                    return False

                # Filter based on camera's smart_detection_types configuration
                smart_detection_types = self._load_smart_detection_types(camera)
                matching_types = []

                for evt_type in event_types:
                    # Map event type to filter type (e.g., "smart_detect_person" -> "person")
                    filter_type = EVENT_TYPE_MAPPING.get(evt_type)
                    if not filter_type:
                        continue

                    # Check if event should be processed based on camera config (via filter)
                    if self.event_filter.should_process_event(filter_type, smart_detection_types, camera.name):
                        matching_types.append(evt_type)

                if not matching_types:
                    logger.debug(
                        f"Native event types {event_types} not in camera filter {smart_detection_types} - discarding",
                        extra={
                            "event_type": "protect_native_event_filtered",
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                            "detected_types": event_types,
                            "allowed_types": smart_detection_types,
                        }
                    )
                    return False

                filter_types = []
                for evt_type in matching_types:
                    mapped = EVENT_TYPE_MAPPING.get(evt_type)
                    if mapped and mapped not in filter_types:
                        filter_types.append(mapped)

                # Determine if this is a doorbell ring before the id check so a
                # ring update can set the flag without sending a second alert.
                is_doorbell_ring = event_type == ProtectEventType.RING
                protect_event_id = str(protect_event_id) if protect_event_id else None

                # A Protect update for an id we already stored (often ~60s later,
                # when a smart-detect type is added or the event ends) must not
                # run AI or send another notification.
                if self._absorb_known_protect_event(
                    db,
                    camera,
                    protect_event_id,
                    filter_types,
                    is_doorbell_ring,
                ):
                    return False

                # Check deduplication cooldown (via filter)
                if self.event_filter.is_duplicate_event(camera.id, camera.name):
                    logger.debug(
                        f"Native event deduplicated for camera '{camera.name}'",
                        extra={
                            "event_type": "protect_native_event_deduplicated",
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                        }
                    )
                    return False

                if protect_event_id and not self.event_filter.try_begin_protect_event(
                    protect_event_id
                ):
                    self._absorb_known_protect_event(
                        db,
                        camera,
                        protect_event_id,
                        filter_types,
                        is_doorbell_ring,
                    )
                    return False
                reservation_pid = protect_event_id

                # Record the event for cooldown tracking
                self.event_filter.record_event(camera.id)

                # Get timestamp
                event_timestamp = event_start or datetime.now(timezone.utc)

                # Generate event ID for clip filename
                generated_event_id = str(uuid.uuid4())

                # Get primary filter type for AI
                primary_event_type = matching_types[0] if matching_types else "motion"
                filter_type = EVENT_TYPE_MAPPING.get(primary_event_type, "motion")

                logger.info(
                    f"Processing native event from camera '{camera.name}': {matching_types}",
                    extra={
                        "event_type": "protect_native_event_processing",
                        "controller_id": controller_id,
                        "camera_id": camera.id,
                        "camera_name": camera.name,
                        "detected_types": matching_types,
                        "filter_type": filter_type,
                        "is_doorbell_ring": is_doorbell_ring,
                        "protect_event_id": str(protect_event_id) if protect_event_id else None,
                    }
                )

                # Retrieve media using the new service (Phase 4)
                from app.services.protect_detection_hints import (
                    detection_column_values,
                    extract_detection_hints,
                    fetch_event_thumbnail_bytes,
                )
                detection_hints = extract_detection_hints(event_obj)
                detection_columns = detection_column_values(detection_hints)
                anchor_jpeg = await fetch_event_thumbnail_bytes(event_obj)
                media = await self.media_service.get_media_for_event(
                    controller_id=controller_id,
                    protect_camera_id=camera.protect_camera_id,
                    camera_id=camera.id,
                    camera_name=camera.name,
                    event_id=generated_event_id,
                    event_timestamp=event_timestamp,
                    is_doorbell_ring=is_doorbell_ring,
                    analysis_mode=camera.analysis_mode,
                    detection=detection_hints,
                    anchor_jpeg=anchor_jpeg,
                )
                snapshot_result = media.snapshot_result
                clip_path = media.clip_path
                fallback_reason = media.fallback_reason

                if not snapshot_result:
                    # Clean up clip if snapshot failed
                    if clip_path:
                        try:
                            clip_service = get_clip_service()
                            clip_service.cleanup_clip(generated_event_id)
                        except Exception:
                            pass
                    return False

                # For doorbell rings, broadcast immediately
                if is_doorbell_ring:
                    await self.broadcaster.broadcast_doorbell_ring(
                        camera_id=camera.id,
                        camera_name=camera.name,
                        thumbnail_url=snapshot_result.thumbnail_path,
                        timestamp=snapshot_result.timestamp
                    )
                    self.broadcaster.trigger_homekit_doorbell(camera.id, generated_event_id)

                # Track processing time
                pipeline_start = time.time()

                # Submit to AI pipeline (via ProtectAIPipeline)
                ai_result = await self.ai_pipeline.submit_snapshot_for_analysis(
                    snapshot_result,
                    camera,
                    filter_type,
                    is_doorbell_ring=is_doorbell_ring,
                    clip_path=clip_path,
                    detection=detection_hints,
                    clip_plan=media.clip_plan,
                )

                # Capture the pipeline's ACTUAL analysis outcome now (singleton state
                # is per-event and must be read before any further awaits).
                persist_tracking = self._persist_tracking_kwargs(fallback_reason)
                context_bundle = getattr(self.ai_pipeline, "last_context_bundle", None)

                # Cleanup clip after AI processing
                if clip_path:
                    try:
                        clip_service = get_clip_service()
                        clip_service.cleanup_clip(generated_event_id)
                    except Exception as e:
                        logger.warning(f"Clip cleanup error: {e}")

                if not ai_result or not ai_result.success:
                    from app.services.protect_event_storage_service import (
                        ai_response_time_ms_from_result,
                    )

                    # Store event without AI description
                    stored_event = await self.storage_service.persist_protect_event(
                        db=db,
                        camera=camera,
                        snapshot_result=snapshot_result,
                        ai_result=None,
                        protect_event_id=str(protect_event_id) if protect_event_id else None,
                        event_type=filter_type,
                        is_doorbell_ring=is_doorbell_ring,
                        event_id_override=generated_event_id,
                        ai_response_time_ms=ai_response_time_ms_from_result(ai_result),
                        **persist_tracking,
                        **detection_columns,
                        **self._identity_only_fields(filter_type, db, context_bundle),
                    )
                    if stored_event:
                        keep_reservation = True
                        self._apply_pending_protect_update(
                            db, stored_event, protect_event_id
                        )
                        await self._link_cross_camera_incident(db, stored_event)
                        await self.broadcaster.broadcast_event_created(stored_event, camera)
                        await self._run_entity_post_persist(stored_event, context_bundle)
                        self._dispatch_notifications(stored_event)
                        self._schedule_local_redescribe(
                            stored_event, snapshot_result, camera, filter_type, context_bundle
                        )
                        return True
                    return False

                # Store event with AI result
                # Persist via new storage service (Phase 4)
                stored_event = await self.storage_service.persist_protect_event(
                    db=db,
                    camera=camera,
                    snapshot_result=snapshot_result,
                    ai_result=ai_result,
                    protect_event_id=str(protect_event_id) if protect_event_id else None,
                    event_type=filter_type,
                    is_doorbell_ring=is_doorbell_ring,
                    event_id_override=generated_event_id,
                    **persist_tracking,
                    **detection_columns,
                    **self._post_ai_context_fields(ai_result, filter_type, db, context_bundle),
                )

                if not stored_event:
                    return False

                keep_reservation = True
                self._apply_pending_protect_update(db, stored_event, protect_event_id)

                await self._store_protect_embedding(stored_event.id)

                # Log processing time
                processing_time_ms = int((time.time() - pipeline_start) * 1000)
                if processing_time_ms > 2000:
                    logger.warning(
                        f"Processing time {processing_time_ms}ms exceeds 2s target for camera '{camera.name}'",
                        extra={
                            "event_type": "protect_latency_warning",
                            "camera_id": camera.id,
                            "processing_time_ms": processing_time_ms
                        }
                    )

                await self._link_cross_camera_incident(db, stored_event)
                # Broadcast and publish event
                await self.broadcaster.broadcast_event_created(stored_event, camera)
                # Entity links + alert rules, after the event is already visible.
                await self._run_entity_post_persist(stored_event, context_bundle)
                # Push + MQTT in the background
                self._dispatch_notifications(stored_event)

                return True

        except Exception as e:
            logger.error(
                f"Error handling native Protect event: {e}",
                extra={
                    "event_type": "protect_native_event_error",
                    "controller_id": controller_id,
                    "error": str(e),
                },
                exc_info=True
            )
            return False
        finally:
            if reservation_pid and not keep_reservation:
                self.event_filter.abandon_protect_event(reservation_pid)

    def _accepted_filter_types(
        self,
        event_types: List[str],
        smart_detection_types: List[str],
        camera_name: str,
    ) -> List[str]:
        """Filter types from this message that the camera is configured to keep."""
        accepted: List[str] = []
        for event_type in event_types:
            filter_type = EVENT_TYPE_MAPPING.get(event_type)
            if not filter_type or filter_type in accepted:
                continue
            if self.event_filter.should_process_event(
                filter_type, smart_detection_types, camera_name
            ):
                accepted.append(filter_type)
        return accepted

    def _absorb_known_protect_event(
        self,
        db: Session,
        camera: Camera,
        protect_event_id: Optional[str],
        detection_types: List[str],
        is_doorbell_ring: bool,
    ) -> bool:
        """Skip AI and notification when this Protect id is already ours.

        A stored row gets any newly reported detection types merged in.
        An in-flight id (reserved, row not committed yet) queues those types
        for the task that is creating the row. Returns True when the caller
        must not start a new analysis.
        """
        if not protect_event_id:
            return False
        pid = str(protect_event_id)
        existing = self.storage_service.find_by_protect_event_id(db, pid)
        if existing is not None:
            self.event_filter.remember_protect_event_id(pid)
            pending_types, pending_ring = self.event_filter.take_pending_protect_update(pid)
            merged_types = list(detection_types)
            for detection_type in pending_types:
                if detection_type not in merged_types:
                    merged_types.append(detection_type)
            self.storage_service.merge_detection_types(
                db,
                existing,
                merged_types,
                is_doorbell_ring or pending_ring,
            )
            logger.info(
                "Protect update for an existing event skipped AI and notification",
                extra={
                    "event_type": "protect_event_id_deduplicated",
                    "protect_event_id": pid,
                    "event_id": existing.id,
                    "camera_id": camera.id,
                    "detection_types": merged_types,
                },
            )
            return True

        if self.event_filter.is_protect_event_known(pid):
            # The row may have committed between the lookup above and here.
            existing = self.storage_service.find_by_protect_event_id(db, pid)
            if existing is not None:
                return self._absorb_known_protect_event(
                    db, camera, pid, detection_types, is_doorbell_ring
                )
            self.event_filter.note_pending_protect_update(
                pid, detection_types, is_doorbell_ring
            )
            logger.info(
                "Protect update for an in-flight event skipped AI and notification",
                extra={
                    "event_type": "protect_event_id_deduplicated",
                    "protect_event_id": pid,
                    "camera_id": camera.id,
                    "detection_types": detection_types,
                },
            )
            return True
        return False

    def _apply_pending_protect_update(
        self,
        db: Session,
        event: Event,
        protect_event_id: Optional[str],
    ) -> None:
        """Fold detection types that arrived while this row was being created."""
        if event is None or not protect_event_id:
            return
        pending_types, pending_ring = self.event_filter.take_pending_protect_update(
            str(protect_event_id)
        )
        if pending_types or pending_ring:
            self.storage_service.merge_detection_types(
                db, event, pending_types, pending_ring
            )

    def _get_camera_by_protect_id(
        self,
        db: Session,
        protect_camera_id: str
    ) -> Optional[Camera]:
        """
        Look up camera by protect_camera_id (Story P2-3.1 AC3).

        Args:
            db: Database session
            protect_camera_id: Native Protect camera ID

        Returns:
            Camera model or None if not found
        """
        return db.query(Camera).filter(
            Camera.protect_camera_id == protect_camera_id
        ).first()

    def _load_smart_detection_types(self, camera: Camera) -> List[str]:
        """
        Load smart_detection_types from camera record (Story P2-3.1 AC5).

        Parses JSON array from camera.smart_detection_types field.

        Args:
            camera: Camera model instance

        Returns:
            List of filter types (e.g., ["person", "vehicle"])
            Empty list if not configured (enables "all motion" mode)
        """
        if not camera.smart_detection_types:
            return []

        try:
            types = json.loads(camera.smart_detection_types)
            if isinstance(types, list):
                return types
            return []
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"Invalid smart_detection_types JSON for camera '{camera.name}'",
                extra={
                    "event_type": "protect_invalid_filter_config",
                    "camera_id": camera.id,
                    "camera_name": camera.name
                }
            )
            return []

    # Filtering and deduplication logic moved to ProtectEventFilter (Phase 4)
    # Use self.event_filter.should_process_event(...) and .is_duplicate_event(...)

    # _download_clip_for_event and _retrieve_snapshot removed — logic moved to ProtectMediaService (Phase 4)

    def clear_event_tracking(self, camera_id: Optional[str] = None) -> None:
        """
        Clear deduplication tracking data (delegated to ProtectEventFilter).
        """
        if camera_id:
            self.event_filter.clear_camera(camera_id)
        else:
            self.event_filter.clear()

    def _extract_protect_event_id(self, msg: Any) -> Optional[str]:
        """
        Extract Protect's native event ID from WebSocket message (Story P2-3.3 AC6).

        Args:
            msg: WebSocket message from uiprotect

        Returns:
            Protect event ID string or None if not available
        """
        try:
            new_obj = getattr(msg, 'new_obj', None)
            if new_obj:
                # Try to get last_motion event ID
                last_motion = getattr(new_obj, 'last_motion', None)
                if last_motion:
                    event_id = getattr(last_motion, 'id', None)
                    if event_id:
                        return str(event_id)

                # Fallback to last_smart_detect
                last_smart = getattr(new_obj, 'last_smart_detect', None)
                if last_smart:
                    event_id = getattr(last_smart, 'id', None)
                    if event_id:
                        return str(event_id)

            return None
        except Exception:
            return None

    # _submit_to_ai_pipeline moved to ProtectAIPipeline (Phase 4)

    
    # _try_video_frame_extraction removed — logic moved to ProtectAIPipeline (Phase 4)


    # Broadcast shims removed (Phase 4) — call self.broadcaster.* directly

    # _download_and_store_video removed — logic moved to ProtectMediaService (Phase 4)


# -------------------------------------------------------------------------
# Singleton accessors (added to fix ImportError after #450 migration)
# -------------------------------------------------------------------------

def get_protect_event_handler() -> "ProtectEventHandler":
    """Get the global ProtectEventHandler singleton instance."""
    return ProtectEventHandler()


def reset_protect_event_handler() -> None:
    """Reset the global ProtectEventHandler singleton (for tests)."""
    ProtectEventHandler._reset_instance()

