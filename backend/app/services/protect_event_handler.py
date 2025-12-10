"""
UniFi Protect Event Handler Service (Story P2-3.1, P2-3.3)

Handles real-time motion/smart detection events from Protect WebSocket.
Implements event filtering based on per-camera configuration and
deduplication with cooldown logic. Submits events to AI pipeline and
stores results in database.

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
    6. Check deduplication cooldown
            ↓ (if duplicate → discard)
    7. Retrieve snapshot (Story P2-3.2)
            ↓
    8. Submit to AI pipeline (Story P2-3.3)
            ↓
    9. Store event in database (Story P2-3.3)
            ↓
    10. Broadcast EVENT_CREATED via WebSocket (Story P2-3.3)
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

from app.core.database import SessionLocal
from app.models.camera import Camera
from app.models.event import Event
from app.services.snapshot_service import get_snapshot_service, SnapshotResult
from app.services.clip_service import get_clip_service
from app.services.frame_extractor import get_frame_extractor

if TYPE_CHECKING:
    from app.services.ai_service import AIResult

logger = logging.getLogger(__name__)

# Event deduplication cooldown in seconds (Story P2-3.1 AC10)
# Default 60 seconds, matches motion_cooldown from Camera model
EVENT_COOLDOWN_SECONDS = 60

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
        # Track last event time per camera for deduplication (AC9)
        self._last_event_times: Dict[str, datetime] = {}
        # Story P3-5.3: Track last audio transcription for passing to event storage
        self._last_audio_transcription: Optional[str] = None

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
        try:
            # Extract new_obj from message
            new_obj = getattr(msg, 'new_obj', None)
            if not new_obj:
                return False

            # Only process Camera or Doorbell events
            model_type = type(new_obj).__name__
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
            db = SessionLocal()
            try:
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

                for event_type in event_types:
                    # Map event type to filter type
                    filter_type = EVENT_TYPE_MAPPING.get(event_type)
                    if not filter_type:
                        continue

                    # Check if event should be processed
                    if not self._should_process_event(filter_type, smart_detection_types, camera.name):
                        continue

                    # Check deduplication cooldown (AC9, AC10)
                    if self._is_duplicate_event(camera.id, camera.name):
                        continue

                    # Event passed all filters - update tracking and proceed
                    self._last_event_times[camera.id] = datetime.now(timezone.utc)
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

                    # Story P3-1.4 AC1, AC2, AC4: Attempt clip download for Protect events
                    # This is async and doesn't block other event processing
                    clip_path, fallback_reason = await self._download_clip_for_event(
                        controller_id=controller_id,
                        protect_camera_id=camera.protect_camera_id,
                        camera_id=camera.id,
                        camera_name=camera.name,
                        event_id=generated_event_id,
                        event_timestamp=event_timestamp
                    )

                    # Story P2-3.2: Retrieve snapshot for AI processing
                    # (Always needed - even if clip download succeeded, we use snapshot for thumbnail)
                    snapshot_result = await self._retrieve_snapshot(
                        controller_id,
                        camera.protect_camera_id,
                        camera.id,
                        camera.name,
                        event_type
                    )

                    if not snapshot_result:
                        # Story P3-1.4 AC3: Clean up clip if snapshot retrieval failed
                        if clip_path:
                            try:
                                clip_service = get_clip_service()
                                clip_service.cleanup_clip(generated_event_id)
                            except Exception:
                                pass  # Best effort cleanup
                        return False

                    # Story P2-3.3: Submit to AI pipeline
                    # Extract protect_event_id from WebSocket message
                    protect_event_id = self._extract_protect_event_id(msg)

                    # Story P2-4.1 AC6: For doorbell rings, broadcast DOORBELL_RING immediately
                    # before AI processing for fast notification
                    if is_doorbell_ring:
                        await self._broadcast_doorbell_ring(
                            camera_id=camera.id,
                            camera_name=camera.name,
                            thumbnail_url=snapshot_result.thumbnail_path,
                            timestamp=snapshot_result.timestamp
                        )

                    # Track total processing time (AC10, AC11)
                    pipeline_start = time.time()

                    # Story P3-1.4 AC1: Pass clip_path to AI pipeline (for future multi-frame analysis)
                    ai_result = await self._submit_to_ai_pipeline(
                        snapshot_result,
                        camera,
                        filter_type,  # Use mapped type (person, vehicle, ring, etc.)
                        is_doorbell_ring=is_doorbell_ring,  # Story P2-4.1: Use doorbell prompt
                        clip_path=clip_path  # Story P3-1.4: Video clip for future use
                    )

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
                        logger.error(
                            f"AI pipeline completely failed for camera '{camera.name}' - saving event without description",
                            extra={
                                "event_type": "protect_ai_complete_failure",
                                "camera_id": camera.id,
                                "camera_name": camera.name,
                                "event_id": generated_event_id,
                                "error": ai_result.error if ai_result else "No result",
                                "fallback_chain": getattr(self, '_fallback_chain', [])
                            }
                        )

                        # Story P3-3.5 AC3: Store event with "AI analysis unavailable" description
                        stored_event = await self._store_event_without_ai(
                            db,
                            snapshot_result,
                            camera,
                            filter_type,
                            protect_event_id,
                            is_doorbell_ring=is_doorbell_ring,
                            event_id_override=generated_event_id
                        )

                        if stored_event:
                            # Broadcast the event even without AI description
                            await self._broadcast_event_created(stored_event, camera)
                            asyncio.create_task(self._process_correlation(stored_event))
                            return True

                        return False

                    # Story P2-3.3: Store event in database
                    # Story P3-1.4 AC2: Include fallback_reason if clip download failed
                    stored_event = await self._store_protect_event(
                        db,
                        ai_result,
                        snapshot_result,
                        camera,
                        filter_type,
                        protect_event_id,
                        is_doorbell_ring=is_doorbell_ring,  # Story P2-4.1 AC3, AC5
                        fallback_reason=fallback_reason,  # Story P3-1.4 AC2
                        event_id_override=generated_event_id  # Use pre-generated ID
                    )

                    if not stored_event:
                        return False

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

                    # Story P2-3.3: Broadcast EVENT_CREATED via WebSocket (AC12)
                    await self._broadcast_event_created(stored_event, camera)

                    # Story P2-4.3: Fire-and-forget correlation processing (AC6)
                    # Doesn't block event creation - runs asynchronously
                    asyncio.create_task(self._process_correlation(stored_event))

                    return True

                return False

            finally:
                db.close()

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

    def _should_process_event(
        self,
        filter_type: str,
        smart_detection_types: List[str],
        camera_name: str
    ) -> bool:
        """
        Check if event type should be processed based on filter config (Story P2-3.1 AC6, AC7, AC8).

        "All Motion" mode (AC8): Empty array or ["motion"] processes all event types.

        Args:
            filter_type: Mapped filter type (e.g., "person", "vehicle")
            smart_detection_types: Camera's configured filter types
            camera_name: Camera name for logging

        Returns:
            True if event should proceed, False if filtered out
        """
        # AC8: Empty array means "all motion" mode - process everything
        if not smart_detection_types:
            logger.debug(
                f"Event passed filter for camera '{camera_name}': all-motion mode (empty config)",
                extra={
                    "event_type": "protect_filter_passed",
                    "camera_name": camera_name,
                    "filter_type": filter_type,
                    "filter_reason": "all_motion_mode"
                }
            )
            return True

        # AC8: ["motion"] also means process all event types
        if smart_detection_types == ["motion"]:
            logger.debug(
                f"Event passed filter for camera '{camera_name}': all-motion mode ([\"motion\"])",
                extra={
                    "event_type": "protect_filter_passed",
                    "camera_name": camera_name,
                    "filter_type": filter_type,
                    "filter_reason": "all_motion_mode"
                }
            )
            return True

        # AC6: Check if event type is in configured filters
        if filter_type in smart_detection_types:
            logger.debug(
                f"Event passed filter for camera '{camera_name}': {filter_type} in filters",
                extra={
                    "event_type": "protect_filter_passed",
                    "camera_name": camera_name,
                    "filter_type": filter_type,
                    "configured_filters": smart_detection_types
                }
            )
            return True

        # AC7: Event type not in filters - discard silently
        logger.debug(
            f"Event filtered for camera '{camera_name}': {filter_type} not in {smart_detection_types}",
            extra={
                "event_type": "protect_filter_rejected",
                "camera_name": camera_name,
                "filter_type": filter_type,
                "configured_filters": smart_detection_types,
                "filter_reason": "type_not_configured"
            }
        )
        return False

    def _is_duplicate_event(self, camera_id: str, camera_name: str) -> bool:
        """
        Check if event is a duplicate based on cooldown (Story P2-3.1 AC9, AC10).

        Uses configurable cooldown period (default 60 seconds) to prevent
        duplicate event processing for the same camera.

        Args:
            camera_id: Camera UUID
            camera_name: Camera name for logging

        Returns:
            True if event should be skipped (duplicate), False if should proceed
        """
        last_event_time = self._last_event_times.get(camera_id)

        if last_event_time is None:
            # First event for this camera
            return False

        elapsed = (datetime.now(timezone.utc) - last_event_time).total_seconds()

        if elapsed < EVENT_COOLDOWN_SECONDS:
            logger.debug(
                f"Event deduplicated for camera '{camera_name}': {elapsed:.1f}s since last event (cooldown: {EVENT_COOLDOWN_SECONDS}s)",
                extra={
                    "event_type": "protect_event_deduplicated",
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "seconds_since_last": elapsed,
                    "cooldown_seconds": EVENT_COOLDOWN_SECONDS
                }
            )
            return True

        return False

    async def _download_clip_for_event(
        self,
        controller_id: str,
        protect_camera_id: str,
        camera_id: str,
        camera_name: str,
        event_id: str,
        event_timestamp: datetime
    ) -> tuple[Optional[Path], Optional[str]]:
        """
        Download video clip for Protect event (Story P3-1.4 AC1, AC2, AC4).

        Attempts to download a 30-second clip centered on the event timestamp.
        Returns clip path if successful, or fallback_reason if failed.

        Args:
            controller_id: Controller UUID
            protect_camera_id: Native Protect camera ID
            camera_id: Internal camera UUID
            camera_name: Camera name for logging
            event_id: Unique event ID for clip filename
            event_timestamp: Event timestamp for clip time range

        Returns:
            Tuple of (clip_path, fallback_reason):
            - (Path, None) if download succeeded
            - (None, "clip_download_failed") if download failed
        """
        try:
            clip_service = get_clip_service()

            # Calculate clip time range (15 seconds before, 15 seconds after)
            clip_start = event_timestamp - timedelta(seconds=15)
            clip_end = event_timestamp + timedelta(seconds=15)

            logger.info(
                f"Attempting clip download for camera '{camera_name}' event {event_id[:8]}...",
                extra={
                    "event_type": "clip_download_attempt",
                    "controller_id": controller_id,
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "clip_start": clip_start.isoformat(),
                    "clip_end": clip_end.isoformat()
                }
            )

            # AC1, AC4: Download clip asynchronously (doesn't block other events)
            clip_path = await clip_service.download_clip(
                controller_id=controller_id,
                camera_id=protect_camera_id,
                event_start=clip_start,
                event_end=clip_end,
                event_id=event_id
            )

            if clip_path:
                logger.info(
                    f"Clip downloaded successfully for camera '{camera_name}': {clip_path}",
                    extra={
                        "event_type": "clip_download_success",
                        "camera_id": camera_id,
                        "event_id": event_id,
                        "clip_path": str(clip_path)
                    }
                )
                return clip_path, None
            else:
                # AC2: Download failed, set fallback reason
                logger.warning(
                    f"Clip download failed for camera '{camera_name}', falling back to snapshot",
                    extra={
                        "event_type": "clip_download_fallback",
                        "camera_id": camera_id,
                        "event_id": event_id,
                        "fallback_reason": "clip_download_failed"
                    }
                )
                return None, "clip_download_failed"

        except Exception as e:
            # AC2: Handle any unexpected errors gracefully
            logger.error(
                f"Clip download error for camera '{camera_name}': {e}",
                extra={
                    "event_type": "clip_download_error",
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None, "clip_download_failed"

    async def _retrieve_snapshot(
        self,
        controller_id: str,
        protect_camera_id: str,
        camera_id: str,
        camera_name: str,
        event_type: str
    ) -> Optional[SnapshotResult]:
        """
        Retrieve snapshot from Protect camera (Story P2-3.2).

        Args:
            controller_id: Controller UUID
            protect_camera_id: Native Protect camera ID
            camera_id: Internal camera UUID
            camera_name: Camera name for logging
            event_type: Type of event that triggered snapshot

        Returns:
            SnapshotResult if successful, None otherwise
        """
        try:
            snapshot_service = get_snapshot_service()
            result = await snapshot_service.get_snapshot(
                controller_id=controller_id,
                protect_camera_id=protect_camera_id,
                camera_id=camera_id,
                camera_name=camera_name,
                timestamp=datetime.now(timezone.utc)
            )

            if result:
                logger.info(
                    f"Snapshot retrieved for camera '{camera_name}' ({event_type})",
                    extra={
                        "event_type": "protect_snapshot_retrieved",
                        "controller_id": controller_id,
                        "camera_id": camera_id,
                        "camera_name": camera_name,
                        "detected_type": event_type,
                        "thumbnail_path": result.thumbnail_path,
                        "image_dimensions": f"{result.width}x{result.height}"
                    }
                )
            else:
                logger.warning(
                    f"Snapshot retrieval failed for camera '{camera_name}' ({event_type})",
                    extra={
                        "event_type": "protect_snapshot_failed",
                        "controller_id": controller_id,
                        "camera_id": camera_id,
                        "camera_name": camera_name,
                        "detected_type": event_type
                    }
                )

            return result

        except Exception as e:
            logger.error(
                f"Snapshot retrieval error for camera '{camera_name}': {e}",
                extra={
                    "event_type": "protect_snapshot_error",
                    "controller_id": controller_id,
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

    def clear_event_tracking(self, camera_id: Optional[str] = None) -> None:
        """
        Clear event tracking data (useful for testing).

        Args:
            camera_id: Specific camera to clear, or None to clear all
        """
        if camera_id:
            self._last_event_times.pop(camera_id, None)
        else:
            self._last_event_times.clear()

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

    async def _submit_to_ai_pipeline(
        self,
        snapshot_result: SnapshotResult,
        camera: Camera,
        event_type: str,
        is_doorbell_ring: bool = False,
        clip_path: Optional[Path] = None
    ) -> Optional["AIResult"]:
        """
        Submit snapshot to AI pipeline for description generation (Story P2-3.3 AC1-3, P2-4.1 AC4, P3-2.6, P3-3.5).

        Implements automatic fallback chain: video_native -> multi_frame -> single_frame -> no description.
        Each failure reason is tracked in comma-separated format (Story P3-3.5 AC1, AC4).

        Converts base64 image to numpy array and calls AIService.generate_description().
        Uses doorbell-specific prompt for ring events (Story P2-4.1).

        Story P3-2.6: When camera.analysis_mode == "multi_frame" and clip is available,
        extracts frames from clip and uses AIService.describe_images() for richer descriptions.
        Falls back to single-frame on any failure.

        Story P3-3.5: Full fallback chain with reason tracking.

        Args:
            snapshot_result: Snapshot with base64-encoded image
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            is_doorbell_ring: If True, use doorbell-specific AI prompt (Story P2-4.1)
            clip_path: Optional path to video clip for multi-frame analysis (Story P3-1.4, P3-2.6)

        Returns:
            AIResult with description, or None on complete failure
            Also sets self._last_analysis_mode, self._last_frame_count, self._last_fallback_reason, and self._last_audio_transcription for event storage
        """
        # Story P3-3.5: Track analysis mode, frame count, and fallback chain for event storage
        self._last_analysis_mode: Optional[str] = None
        self._last_frame_count: Optional[int] = None
        self._last_fallback_reason: Optional[str] = None
        self._fallback_chain: List[str] = []  # Track each failure: ["video_native:provider_unsupported", ...]
        # Story P3-5.3: Reset audio transcription for this event
        self._last_audio_transcription: Optional[str] = None
        # Story P3-7.5: Track extracted frames and timestamps for gallery storage
        self._last_extracted_frames: List[bytes] = []
        self._last_frame_timestamps: List[float] = []

        try:
            # Lazy import to avoid circular imports (same pattern as snapshot_service)
            from app.services.ai_service import ai_service
            from app.core.database import SessionLocal

            # Ensure AI service has API keys loaded from database
            # (The global ai_service singleton may not have keys loaded yet)
            db = SessionLocal()
            try:
                await ai_service.load_api_keys_from_db(db)
            finally:
                db.close()

            # Get camera's configured analysis mode
            # camera.analysis_mode may not exist yet (added in P3-3.1), so use getattr with default
            configured_mode = getattr(camera, 'analysis_mode', None) or 'single_frame'

            # Story P3-3.5, P3-4.4 AC5: Non-Protect cameras (RTSP/USB) always use single_frame regardless of config
            # They have no clip source, so video_native and multi_frame are not applicable
            if camera.source_type != 'protect':
                if configured_mode == 'video_native':
                    # Story P3-4.4 AC5: Set fallback_reason for non-Protect cameras with video_native mode
                    self._fallback_chain.append("video_native:no_clip_source")
                    logger.info(
                        f"Camera '{camera.name}' has video_native mode but source_type='{camera.source_type}', "
                        "using single_frame (no clip source available for non-Protect cameras)",
                        extra={
                            "event_type": "non_protect_video_native_fallback",
                            "camera_id": camera.id,
                            "source_type": camera.source_type,
                            "configured_mode": configured_mode,
                            "effective_mode": "single_frame",
                            "fallback_reason": "video_native:no_clip_source"
                        }
                    )
                elif configured_mode == 'multi_frame':
                    # Track multi_frame fallback for non-Protect cameras
                    self._fallback_chain.append("multi_frame:no_clip_source")
                    logger.info(
                        f"Camera '{camera.name}' has multi_frame mode but source_type='{camera.source_type}', "
                        "using single_frame (no clip source available for non-Protect cameras)",
                        extra={
                            "event_type": "non_protect_multi_frame_fallback",
                            "camera_id": camera.id,
                            "source_type": camera.source_type,
                            "configured_mode": configured_mode,
                            "effective_mode": "single_frame",
                            "fallback_reason": "multi_frame:no_clip_source"
                        }
                    )
                # For non-Protect cameras, go directly to single-frame
                return await self._single_frame_analysis(
                    snapshot_result=snapshot_result,
                    camera=camera,
                    event_type=event_type,
                    is_doorbell_ring=is_doorbell_ring
                )

            # Story P3-3.5: Implement fallback chain for Protect cameras
            # Chain: video_native -> multi_frame -> single_frame

            # Step 1: Try video_native if configured
            if configured_mode == 'video_native':
                result = await self._try_video_native_analysis(
                    clip_path=clip_path,
                    snapshot_result=snapshot_result,
                    camera=camera,
                    event_type=event_type,
                    is_doorbell_ring=is_doorbell_ring
                )
                if result:
                    return result
                # video_native failed, continue to multi_frame

            # Step 2: Try multi_frame if configured OR as fallback from video_native
            if configured_mode in ('video_native', 'multi_frame'):
                if clip_path and clip_path.exists():
                    result = await self._try_multi_frame_analysis(
                        clip_path=clip_path,
                        snapshot_result=snapshot_result,
                        camera=camera,
                        event_type=event_type,
                        is_doorbell_ring=is_doorbell_ring
                    )
                    if result:
                        return result
                    # multi_frame failed, continue to single_frame
                else:
                    # No clip available, record why we're skipping multi_frame
                    self._fallback_chain.append("multi_frame:no_clip_available")
                    logger.info(
                        f"Skipping multi_frame for camera '{camera.name}': no clip available",
                        extra={
                            "event_type": "multi_frame_skip",
                            "camera_id": camera.id,
                            "configured_mode": configured_mode,
                            "reason": "no_clip_available"
                        }
                    )

            # Step 3: Try single_frame (final fallback or configured mode)
            result = await self._single_frame_analysis(
                snapshot_result=snapshot_result,
                camera=camera,
                event_type=event_type,
                is_doorbell_ring=is_doorbell_ring
            )
            if result:
                return result

            # Step 4: Complete failure - all modes exhausted
            # This is handled by returning None, and handle_event will create event with "AI analysis unavailable"
            self._fallback_chain.append("single_frame:ai_failed")
            self._last_fallback_reason = ",".join(self._fallback_chain)

            logger.error(
                f"All analysis modes failed for camera '{camera.name}', fallback chain exhausted",
                extra={
                    "event_type": "fallback_chain_exhausted",
                    "camera_id": camera.id,
                    "configured_mode": configured_mode,
                    "fallback_chain": self._fallback_chain
                }
            )
            return None

        except Exception as e:
            logger.error(
                f"AI pipeline error for camera '{camera.name}': {e}",
                extra={
                    "event_type": "protect_ai_error",
                    "camera_id": camera.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

    async def _try_video_native_analysis(
        self,
        clip_path: Optional[Path],
        snapshot_result: SnapshotResult,
        camera: Camera,
        event_type: str,
        is_doorbell_ring: bool = False
    ) -> Optional["AIResult"]:
        """
        Attempt video native analysis (Story P3-4.1 AC2, AC3).

        Checks if any configured providers support video input before attempting.
        If no video-capable providers are available, immediately falls back to multi_frame
        with appropriate logging.

        Args:
            clip_path: Path to video clip file (may be None)
            snapshot_result: Snapshot with base64-encoded image (for fallback)
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            is_doorbell_ring: If True, use doorbell-specific AI prompt

        Returns:
            AIResult if video_native succeeded, None if should fall back to multi_frame
        """
        from app.services.ai_service import ai_service

        # Story P3-4.1 AC3: Check if clip is available first
        if not clip_path or not clip_path.exists():
            reason = "no_clip_available"
            self._fallback_chain.append(f"video_native:{reason}")
            logger.info(
                f"video_native analysis not available for camera '{camera.name}': {reason}",
                extra={
                    "event_type": "video_native_fallback",
                    "camera_id": camera.id,
                    "reason": reason,
                    "clip_available": False
                }
            )
            return None

        # Story P3-4.1 AC2, AC3: Check which providers support video
        video_capable_providers = ai_service.get_video_capable_providers()

        if not video_capable_providers:
            # AC3: No video-capable providers configured, fall back to multi_frame
            reason = "no_video_providers_available"
            self._fallback_chain.append(f"video_native:{reason}")
            logger.warning(
                "No video-capable providers available - falling back to multi_frame",
                extra={
                    "event_type": "video_native_fallback",
                    "camera_id": camera.id,
                    "camera_name": camera.name,
                    "reason": reason,
                    "video_capable_count": 0
                }
            )
            return None

        # Log which providers support video for debugging
        all_providers = ai_service.get_all_capabilities()
        skipped_providers = [
            p for p, caps in all_providers.items()
            if not caps.get("video") and caps.get("configured")
        ]

        if skipped_providers:
            logger.info(
                f"Skipping non-video providers for video_native: {skipped_providers}",
                extra={
                    "event_type": "video_native_provider_filter",
                    "camera_id": camera.id,
                    "skipped_providers": skipped_providers,
                    "video_capable_providers": video_capable_providers
                }
            )

        # Story P3-4.2: Route to appropriate video analysis method based on video_method
        # - frame_extraction: OpenAI, Grok - extract frames and send as images
        # - native_upload: Gemini - upload video file directly (P3-4.3)

        # Determine which provider to use and its video method
        # Priority: OpenAI (frame_extraction) -> Grok (frame_extraction) -> Gemini (native_upload)
        provider_order = ai_service.get_provider_order()
        selected_provider = None
        video_method = None

        for provider_name in provider_order:
            if provider_name in video_capable_providers:
                caps = ai_service.get_provider_capabilities(provider_name)
                video_method = caps.get("video_method")
                selected_provider = provider_name
                break

        if not selected_provider:
            reason = "no_suitable_video_provider"
            self._fallback_chain.append(f"video_native:{reason}")
            logger.warning(
                "No suitable video provider found in fallback order",
                extra={
                    "event_type": "video_native_fallback",
                    "camera_id": camera.id,
                    "reason": reason,
                    "video_capable_providers": video_capable_providers
                }
            )
            return None

        logger.info(
            f"Using {selected_provider} for video_native analysis (method: {video_method})",
            extra={
                "event_type": "video_native_provider_selected",
                "camera_id": camera.id,
                "provider": selected_provider,
                "video_method": video_method,
                "clip_path": str(clip_path)
            }
        )

        # Route based on video method
        if video_method == "frame_extraction":
            # Story P3-4.2: OpenAI/Grok use frame extraction + multi-image
            return await self._try_video_frame_extraction(
                clip_path=clip_path,
                camera=camera,
                event_type=event_type,
                is_doorbell_ring=is_doorbell_ring,
                provider_name=selected_provider
            )

        elif video_method == "native_upload":
            # Story P3-4.3: Gemini uses native video upload
            return await self._try_video_native_upload(
                clip_path=clip_path,
                camera=camera,
                event_type=event_type,
                is_doorbell_ring=is_doorbell_ring,
                provider_name=selected_provider
            )

        else:
            reason = f"unknown_video_method:{video_method}"
            self._fallback_chain.append(f"video_native:{reason}")
            logger.warning(
                f"Unknown video method '{video_method}' for {selected_provider}",
                extra={
                    "event_type": "video_native_fallback",
                    "camera_id": camera.id,
                    "provider": selected_provider,
                    "video_method": video_method,
                    "reason": reason
                }
            )
            return None

    async def _try_video_frame_extraction(
        self,
        clip_path: Path,
        camera: "Camera",
        event_type: str,
        is_doorbell_ring: bool,
        provider_name: str
    ) -> Optional["AIResult"]:
        """
        Perform video analysis via frame extraction (Story P3-4.2).

        Uses provider's describe_video() method which extracts frames and optionally
        transcribes audio, then sends to AI for analysis.

        Args:
            clip_path: Path to video clip file
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            is_doorbell_ring: If True, use doorbell-specific prompt
            provider_name: Provider to use (openai, grok)

        Returns:
            AIResult if successful, None to trigger fallback
        """
        from app.services.ai_service import ai_service, AIProvider, PROVIDER_CAPABILITIES
        from datetime import datetime

        try:
            # Get provider instance
            provider_enum = AIProvider(provider_name)
            provider = ai_service.providers.get(provider_enum)

            if not provider or not hasattr(provider, 'describe_video'):
                reason = f"provider_missing_describe_video:{provider_name}"
                self._fallback_chain.append(f"video_native:{reason}")
                logger.warning(
                    f"Provider {provider_name} does not have describe_video method",
                    extra={
                        "event_type": "video_native_fallback",
                        "camera_id": camera.id,
                        "provider": provider_name,
                        "reason": reason
                    }
                )
                return None

            # Check if audio transcription is supported and enabled
            caps = PROVIDER_CAPABILITIES.get(provider_name, {})
            include_audio = caps.get("supports_audio_transcription", False)

            # Build custom prompt for event context
            custom_prompt = None
            if is_doorbell_ring:
                custom_prompt = (
                    "This is a doorbell ring event. Describe who is at the door, "
                    "their appearance, what they might want, and any packages or items visible."
                )

            # Story P3-4.4 AC3: 30 second timeout for video analysis
            VIDEO_ANALYSIS_TIMEOUT_SECONDS = 30

            logger.info(
                f"Calling describe_video for camera '{camera.name}'",
                extra={
                    "event_type": "video_frame_extraction_start",
                    "camera_id": camera.id,
                    "provider": provider_name,
                    "clip_path": str(clip_path),
                    "include_audio": include_audio,
                    "is_doorbell_ring": is_doorbell_ring,
                    "timeout_seconds": VIDEO_ANALYSIS_TIMEOUT_SECONDS
                }
            )

            # Call describe_video with timeout (Story P3-4.4 Task 5)
            result = await asyncio.wait_for(
                provider.describe_video(
                    video_path=clip_path,
                    camera_name=camera.name,
                    timestamp=datetime.now().isoformat(),
                    detected_objects=[event_type] if event_type else [],
                    include_audio=include_audio,
                    custom_prompt=custom_prompt
                ),
                timeout=VIDEO_ANALYSIS_TIMEOUT_SECONDS
            )

            if result.success:
                # Story P3-4.4 AC2: Set analysis_mode = 'video_native' and frame_count_used = None on success
                self._last_analysis_mode = "video_native"
                self._last_frame_count = None  # Video native uses full video, not frames

                logger.info(
                    f"video_native analysis (frame_extraction) succeeded for camera '{camera.name}'",
                    extra={
                        "event_type": "video_native_success",
                        "camera_id": camera.id,
                        "provider": provider_name,
                        "video_method": "frame_extraction",
                        "tokens_used": result.tokens_used,
                        "response_time_ms": result.response_time_ms,
                        "audio_included": include_audio,
                        "analysis_mode": "video_native"
                    }
                )
                return result
            else:
                reason = f"describe_video_failed:{result.error}"
                self._fallback_chain.append(f"video_native:{reason}")
                logger.warning(
                    f"describe_video returned failure for camera '{camera.name}': {result.error}",
                    extra={
                        "event_type": "video_native_fallback",
                        "camera_id": camera.id,
                        "provider": provider_name,
                        "reason": reason,
                        "error": result.error
                    }
                )
                return None

        except asyncio.TimeoutError:
            # Story P3-4.4 AC3: Handle timeout with proper fallback reason
            reason = "timeout"
            self._fallback_chain.append(f"video_native:{reason}")
            logger.warning(
                f"Video frame extraction timed out for camera '{camera.name}' after 30s",
                extra={
                    "event_type": "video_native_timeout",
                    "camera_id": camera.id,
                    "provider": provider_name,
                    "reason": reason,
                    "timeout_seconds": 30
                }
            )
            return None

        except Exception as e:
            reason = f"exception:{type(e).__name__}"
            self._fallback_chain.append(f"video_native:{reason}")
            logger.error(
                f"Exception during video frame extraction for camera '{camera.name}': {e}",
                extra={
                    "event_type": "video_native_error",
                    "camera_id": camera.id,
                    "provider": provider_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

    async def _try_video_native_upload(
        self,
        clip_path: Path,
        camera: "Camera",
        event_type: str,
        is_doorbell_ring: bool,
        provider_name: str
    ) -> Optional["AIResult"]:
        """
        Perform video analysis via native video upload (Story P3-4.3).

        Uses provider's describe_video() method which uploads the video directly
        to the AI provider (e.g., Gemini) for native video analysis.

        Args:
            clip_path: Path to video clip file
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            is_doorbell_ring: If True, use doorbell-specific prompt
            provider_name: Provider to use (gemini)

        Returns:
            AIResult if successful, None to trigger fallback
        """
        from app.services.ai_service import ai_service, AIProvider, PROVIDER_CAPABILITIES
        from datetime import datetime

        try:
            # Get provider instance
            provider_enum = AIProvider(provider_name)
            provider = ai_service.providers.get(provider_enum)

            if not provider or not hasattr(provider, 'describe_video'):
                reason = f"provider_missing_describe_video:{provider_name}"
                self._fallback_chain.append(f"video_native:{reason}")
                logger.warning(
                    f"Provider {provider_name} does not have describe_video method",
                    extra={
                        "event_type": "video_native_fallback",
                        "camera_id": camera.id,
                        "provider": provider_name,
                        "reason": reason
                    }
                )
                return None

            # Build custom prompt for event context
            custom_prompt = None
            if is_doorbell_ring:
                custom_prompt = (
                    "This is a doorbell ring event. Describe who is at the door, "
                    "their appearance, what they might want, and any packages or items visible."
                )

            # Story P3-4.4 AC3: 30 second timeout for video analysis
            VIDEO_ANALYSIS_TIMEOUT_SECONDS = 30

            logger.info(
                f"Calling describe_video (native upload) for camera '{camera.name}'",
                extra={
                    "event_type": "video_native_upload_start",
                    "camera_id": camera.id,
                    "provider": provider_name,
                    "clip_path": str(clip_path),
                    "is_doorbell_ring": is_doorbell_ring,
                    "timeout_seconds": VIDEO_ANALYSIS_TIMEOUT_SECONDS
                }
            )

            # Call describe_video with timeout (Story P3-4.4 Task 5)
            result = await asyncio.wait_for(
                provider.describe_video(
                    video_path=clip_path,
                    camera_name=camera.name,
                    timestamp=datetime.now().isoformat(),
                    detected_objects=[event_type] if event_type else [],
                    custom_prompt=custom_prompt
                ),
                timeout=VIDEO_ANALYSIS_TIMEOUT_SECONDS
            )

            if result.success:
                # Story P3-4.4 AC2: Set analysis_mode = 'video_native' and frame_count_used = None on success
                self._last_analysis_mode = "video_native"
                self._last_frame_count = None  # Video native uses full video, not frames

                logger.info(
                    f"video_native analysis (native_upload) succeeded for camera '{camera.name}'",
                    extra={
                        "event_type": "video_native_success",
                        "camera_id": camera.id,
                        "provider": provider_name,
                        "video_method": "native_upload",
                        "tokens_used": result.tokens_used,
                        "response_time_ms": result.response_time_ms,
                        "analysis_mode": "video_native"
                    }
                )
                return result
            else:
                reason = f"describe_video_failed:{result.error}"
                self._fallback_chain.append(f"video_native:{reason}")
                logger.warning(
                    f"describe_video returned failure for camera '{camera.name}': {result.error}",
                    extra={
                        "event_type": "video_native_fallback",
                        "camera_id": camera.id,
                        "provider": provider_name,
                        "reason": reason,
                        "error": result.error
                    }
                )
                return None

        except asyncio.TimeoutError:
            # Story P3-4.4 AC3: Handle timeout with proper fallback reason
            reason = "timeout"
            self._fallback_chain.append(f"video_native:{reason}")
            logger.warning(
                f"Video native upload timed out for camera '{camera.name}' after 30s",
                extra={
                    "event_type": "video_native_timeout",
                    "camera_id": camera.id,
                    "provider": provider_name,
                    "reason": reason,
                    "timeout_seconds": 30
                }
            )
            return None

        except Exception as e:
            reason = f"exception:{type(e).__name__}"
            self._fallback_chain.append(f"video_native:{reason}")
            logger.error(
                f"Exception during video native upload for camera '{camera.name}': {e}",
                extra={
                    "event_type": "video_native_error",
                    "camera_id": camera.id,
                    "provider": provider_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

    async def _try_multi_frame_analysis(
        self,
        clip_path: Path,
        snapshot_result: SnapshotResult,
        camera: Camera,
        event_type: str,
        is_doorbell_ring: bool = False
    ) -> Optional["AIResult"]:
        """
        Attempt multi-frame analysis from video clip (Story P3-2.6 AC1, AC2, AC3).

        Extracts frames from clip and uses AIService.describe_images() for richer descriptions.
        Falls back to single-frame on any failure, setting appropriate fallback_reason.

        Args:
            clip_path: Path to video clip file
            snapshot_result: Snapshot with base64-encoded image (for fallback)
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            is_doorbell_ring: If True, use doorbell-specific AI prompt

        Returns:
            AIResult if multi-frame succeeded, None if should fallback to single-frame
        """
        from app.services.ai_service import ai_service

        try:
            # Story P3-2.6 AC1: Extract frames from clip
            frame_extractor = get_frame_extractor()

            logger.info(
                f"Attempting multi-frame analysis for camera '{camera.name}' from clip: {clip_path}",
                extra={
                    "event_type": "multi_frame_attempt",
                    "camera_id": camera.id,
                    "clip_path": str(clip_path)
                }
            )

            # Story P3-7.5: Use extract_frames_with_timestamps to get both frames and timestamps
            frames, timestamps = await frame_extractor.extract_frames_with_timestamps(
                clip_path=clip_path,
                frame_count=5,  # Default frame count
                strategy="evenly_spaced",
                filter_blur=True
            )

            # Story P3-2.6 AC2: Check if frame extraction succeeded
            if not frames or len(frames) == 0:
                logger.warning(
                    f"Frame extraction returned no frames for camera '{camera.name}', falling back to single-frame",
                    extra={
                        "event_type": "multi_frame_extraction_failed",
                        "camera_id": camera.id,
                        "clip_path": str(clip_path),
                        "fallback_reason": "frame_extraction_failed"
                    }
                )
                # Story P3-3.5: Track failure in fallback chain
                self._fallback_chain.append("multi_frame:frame_extraction_failed")
                return None

            logger.info(
                f"Extracted {len(frames)} frames from clip for camera '{camera.name}'",
                extra={
                    "event_type": "multi_frame_extracted",
                    "camera_id": camera.id,
                    "frame_count": len(frames),
                    "total_bytes": sum(len(f) for f in frames)
                }
            )

            # Story P3-2.6 AC1: Call AIService.describe_images() with extracted frames
            try:
                # Story P2-4.1: Use doorbell-specific prompt for ring events
                custom_prompt = DOORBELL_RING_PROMPT if is_doorbell_ring else None

                # Story P3-5.3: Extract audio and transcribe for doorbell cameras
                audio_transcription = None
                if camera.is_doorbell:
                    audio_transcription = await self._extract_and_transcribe_audio(clip_path, camera)

                result = await ai_service.describe_images(
                    images=frames,
                    camera_name=camera.name,
                    timestamp=snapshot_result.timestamp.isoformat(),
                    detected_objects=[event_type],
                    sla_timeout_ms=10000,  # 10s SLA for multi-frame (higher than single-frame)
                    custom_prompt=custom_prompt,
                    audio_transcription=audio_transcription  # Story P3-5.3
                )
                # Store transcription for later use when saving event
                self._last_audio_transcription = audio_transcription

                if result and result.success:
                    # Story P3-2.6 AC4: Record analysis mode and frame count
                    self._last_analysis_mode = "multi_frame"
                    self._last_frame_count = len(frames)
                    # Story P3-7.5: Store frames and timestamps for gallery storage
                    self._last_extracted_frames = frames
                    self._last_frame_timestamps = timestamps

                    logger.info(
                        f"Multi-frame AI description generated for camera '{camera.name}': {result.description[:50]}...",
                        extra={
                            "event_type": "multi_frame_ai_success",
                            "camera_id": camera.id,
                            "ai_provider": result.provider,
                            "confidence": result.confidence,
                            "response_time_ms": result.response_time_ms,
                            "frame_count": len(frames),
                            "analysis_mode": "multi_frame",
                            "is_doorbell_ring": is_doorbell_ring
                        }
                    )
                    return result
                else:
                    # Story P3-2.6 AC3: Multi-frame AI request failed
                    logger.warning(
                        f"Multi-frame AI request failed for camera '{camera.name}', falling back to single-frame",
                        extra={
                            "event_type": "multi_frame_ai_failed",
                            "camera_id": camera.id,
                            "error": result.error if result else "No result",
                            "fallback_reason": "multi_frame_ai_failed"
                        }
                    )
                    # Story P3-3.5: Track failure in fallback chain
                    self._fallback_chain.append("multi_frame:ai_failed")
                    return None

            except Exception as e:
                # Story P3-2.6 AC3: Multi-frame AI exception
                logger.warning(
                    f"Multi-frame AI exception for camera '{camera.name}': {e}, falling back to single-frame",
                    extra={
                        "event_type": "multi_frame_ai_exception",
                        "camera_id": camera.id,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "fallback_reason": "multi_frame_ai_failed"
                    }
                )
                # Story P3-3.5: Track failure in fallback chain
                self._fallback_chain.append("multi_frame:ai_failed")
                return None

        except Exception as e:
            # Story P3-2.6 AC2: Frame extraction exception
            logger.warning(
                f"Frame extraction exception for camera '{camera.name}': {e}, falling back to single-frame",
                extra={
                    "event_type": "multi_frame_extraction_exception",
                    "camera_id": camera.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "fallback_reason": "frame_extraction_failed"
                }
            )
            # Story P3-3.5: Track failure in fallback chain
            self._fallback_chain.append("multi_frame:frame_extraction_failed")
            return None

    async def _single_frame_analysis(
        self,
        snapshot_result: SnapshotResult,
        camera: Camera,
        event_type: str,
        is_doorbell_ring: bool = False
    ) -> Optional["AIResult"]:
        """
        Perform single-frame analysis using snapshot (existing behavior).

        Story P3-2.6 AC4: Records analysis_mode as "single_frame".
        Story P3-3.5: Sets fallback_reason if this was reached via fallback chain.

        Args:
            snapshot_result: Snapshot with base64-encoded image
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            is_doorbell_ring: If True, use doorbell-specific AI prompt

        Returns:
            AIResult with description, or None on failure
        """
        from app.services.ai_service import ai_service

        try:
            # Convert base64 to numpy array (BGR format for OpenCV/AI)
            image_bytes = base64.b64decode(snapshot_result.image_base64)
            image = Image.open(io.BytesIO(image_bytes))

            # Convert PIL to numpy array and then RGB->BGR for OpenCV convention
            frame_rgb = np.array(image)
            if len(frame_rgb.shape) == 3 and frame_rgb.shape[2] == 3:
                frame_bgr = frame_rgb[:, :, ::-1]  # RGB to BGR
            else:
                frame_bgr = frame_rgb

            # Story P2-4.1: Use doorbell-specific prompt for ring events (AC4)
            custom_prompt = DOORBELL_RING_PROMPT if is_doorbell_ring else None

            # Call AI service (AC1, AC2, AC3)
            result = await ai_service.generate_description(
                frame=frame_bgr,
                camera_name=camera.name,
                timestamp=snapshot_result.timestamp.isoformat(),
                detected_objects=[event_type],
                sla_timeout_ms=5000,  # 5s SLA target
                custom_prompt=custom_prompt
            )

            # Check if AI succeeded
            if not result or not result.success:
                logger.warning(
                    f"Single-frame AI request failed for camera '{camera.name}'",
                    extra={
                        "event_type": "single_frame_ai_failed",
                        "camera_id": camera.id,
                        "error": result.error if result else "No result"
                    }
                )
                return None

            # Story P3-2.6 AC4: Record analysis mode (single_frame)
            self._last_analysis_mode = "single_frame"
            self._last_frame_count = 1

            # Story P3-3.5 AC4: Set fallback_reason if we had prior failures in the chain
            if hasattr(self, '_fallback_chain') and self._fallback_chain:
                self._last_fallback_reason = ",".join(self._fallback_chain)

            logger.info(
                f"AI description generated for camera '{camera.name}': {result.description[:50]}...",
                extra={
                    "event_type": "protect_ai_success",
                    "camera_id": camera.id,
                    "ai_provider": result.provider,
                    "confidence": result.confidence,
                    "response_time_ms": result.response_time_ms,
                    "analysis_mode": "single_frame",
                    "is_doorbell_ring": is_doorbell_ring,
                    "fallback_reason": self._last_fallback_reason
                }
            )

            return result

        except Exception as e:
            logger.error(
                f"Single-frame analysis error for camera '{camera.name}': {e}",
                extra={
                    "event_type": "single_frame_error",
                    "camera_id": camera.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

    async def _store_protect_event(
        self,
        db: Session,
        ai_result: "AIResult",
        snapshot_result: SnapshotResult,
        camera: Camera,
        event_type: str,
        protect_event_id: Optional[str],
        is_doorbell_ring: bool = False,
        fallback_reason: Optional[str] = None,
        event_id_override: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> Optional[Event]:
        """
        Store Protect event in database (Story P2-3.3 AC5-9, P2-4.1 AC3, AC5, P3-1.4 AC2, P3-2.6 AC4, P3-5.3 AC6).

        Creates Event record with source_type='protect' and all AI/snapshot fields.

        Args:
            db: Database session
            ai_result: AI description result
            snapshot_result: Snapshot with thumbnail path
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            protect_event_id: Protect's native event ID
            is_doorbell_ring: Whether this is a doorbell ring event (Story P2-4.1)
            fallback_reason: Reason for fallback to snapshot (Story P3-1.4, e.g., "clip_download_failed")
            event_id_override: Pre-generated event ID to use (Story P3-1.4)
            audio_transcription: Transcribed speech from doorbell audio (Story P3-5.3)

        Returns:
            Stored Event model or None on failure
        """
        try:
            # Story P3-2.6 AC4: Combine clip download fallback with multi-frame fallback
            # Use existing fallback_reason if provided (from clip download), otherwise use AI fallback
            effective_fallback_reason = fallback_reason or getattr(self, '_last_fallback_reason', None)

            # Story P3-5.3 AC6: Get audio transcription from instance or parameter
            effective_audio_transcription = audio_transcription or getattr(self, '_last_audio_transcription', None)

            # Story P3-6.1: Determine low_confidence flag from AI confidence
            ai_confidence = getattr(ai_result, 'ai_confidence', None)
            low_confidence_from_ai = ai_confidence is not None and ai_confidence < 50

            # Story P3-6.2 AC3, AC6: Detect vague descriptions (supplements AI confidence)
            vague_reason = None
            low_confidence_from_vague = False
            try:
                from app.services.description_quality import detect_vague_description
                is_vague, vague_reason = detect_vague_description(ai_result.description)
                if is_vague:
                    low_confidence_from_vague = True
                    logger.info(
                        f"Vague description detected for camera '{camera.name}': {vague_reason}",
                        extra={
                            "event_type": "vague_description_detected",
                            "camera_id": camera.id,
                            "camera_name": camera.name,
                            "vague_reason": vague_reason,
                            "description_preview": ai_result.description[:50] if ai_result.description else None
                        }
                    )
            except Exception as e:
                # AC6: Detection errors must NOT block event processing
                logger.warning(
                    f"Vagueness detection error for camera '{camera.name}': {e}",
                    extra={
                        "event_type": "vagueness_detection_error",
                        "camera_id": camera.id,
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                )
                # Default to not-vague if detection fails (benefit of doubt)
                vague_reason = None
                low_confidence_from_vague = False

            # Story P3-6.1/P3-6.2 AC3: Combine AI confidence AND vagueness for final low_confidence flag
            low_confidence = low_confidence_from_ai or low_confidence_from_vague

            # Story P3-7.5: Check if we should store key frames for gallery display
            key_frames_base64 = None
            frame_timestamps = None
            extracted_frames = getattr(self, '_last_extracted_frames', [])
            extracted_timestamps = getattr(self, '_last_frame_timestamps', [])

            if extracted_frames:
                # Check store_analysis_frames setting (default: true)
                from app.models.system_setting import SystemSetting
                store_frames_setting = db.query(SystemSetting).filter(
                    SystemSetting.key == 'store_analysis_frames'
                ).first()
                # Default to True if setting doesn't exist
                store_frames = store_frames_setting is None or store_frames_setting.value.lower() == 'true'

                if store_frames:
                    try:
                        frame_extractor = get_frame_extractor()
                        # Encode frames as smaller thumbnails (320px max width, 70% quality)
                        encoded_frames = []
                        for frame_bytes in extracted_frames:
                            encoded = frame_extractor.encode_frame_for_storage(frame_bytes)
                            if encoded:
                                encoded_frames.append(encoded)

                        if encoded_frames:
                            key_frames_base64 = json.dumps(encoded_frames)
                            frame_timestamps = json.dumps(extracted_timestamps)
                            logger.info(
                                f"Stored {len(encoded_frames)} key frames for event on camera '{camera.name}'",
                                extra={
                                    "event_type": "key_frames_stored",
                                    "camera_id": camera.id,
                                    "frame_count": len(encoded_frames),
                                    "timestamps": extracted_timestamps
                                }
                            )
                    except Exception as e:
                        # Don't fail event storage if frame encoding fails
                        logger.warning(
                            f"Failed to encode key frames for storage: {e}",
                            extra={
                                "event_type": "key_frames_encode_error",
                                "camera_id": camera.id,
                                "error_type": type(e).__name__,
                                "error_message": str(e)
                            }
                        )

            # Create Event record (AC5-9, P2-4.1 AC3, AC5, P3-1.4 AC2, P3-2.6 AC4, P3-5.3 AC6, P3-6.1 AC3/AC6, P3-6.2 AC3/AC4, P3-7.1 AC6, P3-7.5 AC4)
            event = Event(
                camera_id=camera.id,
                timestamp=snapshot_result.timestamp,
                description=ai_result.description,  # AC8
                confidence=ai_result.confidence,  # AC8
                objects_detected=json.dumps(ai_result.objects_detected),  # AC8
                thumbnail_path=snapshot_result.thumbnail_path,  # AC9
                thumbnail_base64=None,  # We use filesystem storage
                alert_triggered=False,  # Will be evaluated by alert engine
                source_type='protect',  # AC5
                protect_event_id=protect_event_id,  # AC6
                smart_detection_type=event_type,  # AC7 (will be 'ring' for doorbell events)
                is_doorbell_ring=is_doorbell_ring,  # Story P2-4.1 AC3, AC5
                provider_used=ai_result.provider,  # Story P2-5.3: AI provider tracking
                fallback_reason=effective_fallback_reason,  # Story P3-1.4 AC2, P3-2.6 AC2/AC3
                # Story P3-2.6 AC4: Record analysis mode and frame count
                analysis_mode=getattr(self, '_last_analysis_mode', 'single_frame'),
                frame_count_used=getattr(self, '_last_frame_count', None),
                # Story P3-5.3 AC6: Store audio transcription
                audio_transcription=effective_audio_transcription,
                # Story P3-6.1 AC3/AC6: Store AI confidence scoring
                ai_confidence=ai_confidence,
                low_confidence=low_confidence,
                # Story P3-6.2 AC4: Store vagueness detection reason
                vague_reason=vague_reason,
                # Story P3-7.1 AC6: Store AI cost estimate
                ai_cost=ai_result.cost_estimate,
                # Story P3-7.5 AC4: Store key frames for gallery display
                key_frames_base64=key_frames_base64,
                frame_timestamps=frame_timestamps
            )

            # Story P3-1.4: Use pre-generated event ID if provided
            if event_id_override:
                event.id = event_id_override

            db.add(event)
            db.commit()
            db.refresh(event)

            logger.info(
                f"Protect event stored: {event.id} for camera '{camera.name}'",
                extra={
                    "event_type": "protect_event_stored",
                    "event_id": event.id,
                    "camera_id": camera.id,
                    "source_type": event.source_type,
                    "smart_detection_type": event.smart_detection_type,
                    "is_doorbell_ring": event.is_doorbell_ring,
                    # Story P3-2.6: Log analysis mode info
                    "analysis_mode": event.analysis_mode,
                    "frame_count_used": event.frame_count_used,
                    "fallback_reason": event.fallback_reason,
                    # Story P3-5.3: Log audio transcription info
                    "has_audio_transcription": bool(event.audio_transcription),
                    # Story P3-6.1: Log AI confidence info
                    "ai_confidence": event.ai_confidence,
                    "low_confidence": event.low_confidence,
                    # Story P3-6.2: Log vagueness detection info
                    "vague_reason": event.vague_reason,
                    # Story P3-7.5: Log key frames info
                    "has_key_frames": bool(event.key_frames_base64)
                }
            )

            return event

        except Exception as e:
            logger.error(
                f"Database error storing event for camera '{camera.name}': {e}",
                extra={
                    "event_type": "protect_event_store_error",
                    "camera_id": camera.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            db.rollback()
            return None

    async def _store_event_without_ai(
        self,
        db: Session,
        snapshot_result: SnapshotResult,
        camera: Camera,
        event_type: str,
        protect_event_id: Optional[str],
        is_doorbell_ring: bool = False,
        event_id_override: Optional[str] = None
    ) -> Optional[Event]:
        """
        Store Protect event without AI description (Story P3-3.5 AC3).

        Creates Event record with description = "AI analysis unavailable" when
        all AI analysis modes have failed.

        Args:
            db: Database session
            snapshot_result: Snapshot with thumbnail path
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            protect_event_id: Protect's native event ID
            is_doorbell_ring: Whether this is a doorbell ring event
            event_id_override: Pre-generated event ID to use

        Returns:
            Stored Event model or None on failure
        """
        try:
            # Story P3-3.5 AC3: Build complete fallback reason
            fallback_chain = getattr(self, '_fallback_chain', [])
            fallback_reason = ",".join(fallback_chain) if fallback_chain else "ai_unavailable"

            # Create Event record with "AI analysis unavailable" description
            event = Event(
                camera_id=camera.id,
                timestamp=snapshot_result.timestamp,
                description="AI analysis unavailable",  # Story P3-3.5 AC3
                confidence=0.0,  # No AI confidence available
                objects_detected=json.dumps([event_type]),
                thumbnail_path=snapshot_result.thumbnail_path,
                thumbnail_base64=None,
                alert_triggered=False,
                source_type='protect',
                protect_event_id=protect_event_id,
                smart_detection_type=event_type,
                is_doorbell_ring=is_doorbell_ring,
                provider_used=None,  # No provider was successful
                fallback_reason=fallback_reason,  # Full failure chain
                analysis_mode=None,  # No analysis mode succeeded
                frame_count_used=None,
                description_retry_needed=True  # Flag for potential retry
            )

            if event_id_override:
                event.id = event_id_override

            db.add(event)
            db.commit()
            db.refresh(event)

            logger.warning(
                f"Protect event stored WITHOUT AI description: {event.id} for camera '{camera.name}'",
                extra={
                    "event_type": "protect_event_stored_no_ai",
                    "event_id": event.id,
                    "camera_id": camera.id,
                    "camera_name": camera.name,
                    "smart_detection_type": event.smart_detection_type,
                    "is_doorbell_ring": event.is_doorbell_ring,
                    "fallback_reason": event.fallback_reason,
                    "description_retry_needed": event.description_retry_needed
                }
            )

            return event

        except Exception as e:
            logger.error(
                f"Database error storing event without AI for camera '{camera.name}': {e}",
                extra={
                    "event_type": "protect_event_store_no_ai_error",
                    "camera_id": camera.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            db.rollback()
            return None

    async def _extract_and_transcribe_audio(
        self,
        clip_path: Path,
        camera: Camera
    ) -> Optional[str]:
        """
        Extract audio from video clip and transcribe speech (Story P3-5.3 AC4).

        Only runs for doorbell cameras. Audio extraction/transcription failures
        do NOT block event processing - we simply return None and continue
        with video-only description.

        Args:
            clip_path: Path to video clip file
            camera: Camera that captured the event

        Returns:
            Transcribed speech text, or None if extraction/transcription failed
            or no speech detected
        """
        try:
            from app.services.audio_extractor import get_audio_extractor

            audio_extractor = get_audio_extractor()

            logger.info(
                f"Extracting audio from clip for doorbell camera '{camera.name}'",
                extra={
                    "event_type": "audio_extraction_start",
                    "camera_id": camera.id,
                    "clip_path": str(clip_path)
                }
            )

            # Extract audio from clip (returns WAV bytes or None)
            audio_bytes = await audio_extractor.extract_audio(clip_path)

            if not audio_bytes:
                logger.debug(
                    f"No audio extracted from clip for camera '{camera.name}' (no audio track or error)",
                    extra={
                        "event_type": "audio_extraction_no_audio",
                        "camera_id": camera.id
                    }
                )
                return None

            logger.info(
                f"Audio extracted ({len(audio_bytes)} bytes), transcribing for camera '{camera.name}'",
                extra={
                    "event_type": "audio_transcription_start",
                    "camera_id": camera.id,
                    "audio_bytes": len(audio_bytes)
                }
            )

            # Transcribe audio (returns text, empty string for silent audio, or None on error)
            transcription = await audio_extractor.transcribe(audio_bytes)

            if transcription is None:
                logger.warning(
                    f"Audio transcription failed for camera '{camera.name}'",
                    extra={
                        "event_type": "audio_transcription_failed",
                        "camera_id": camera.id
                    }
                )
                return None

            if not transcription.strip():
                logger.debug(
                    f"Silent audio detected for camera '{camera.name}' (no speech)",
                    extra={
                        "event_type": "audio_transcription_silent",
                        "camera_id": camera.id
                    }
                )
                return None  # Don't pass empty transcription to AI

            logger.info(
                f"Audio transcription successful for camera '{camera.name}': '{transcription[:50]}...'",
                extra={
                    "event_type": "audio_transcription_success",
                    "camera_id": camera.id,
                    "transcription_preview": transcription[:100]
                }
            )

            return transcription

        except Exception as e:
            # Audio failures should NEVER block event processing (Story P3-5.3 constraint)
            logger.warning(
                f"Audio extraction/transcription error for camera '{camera.name}': {e}",
                extra={
                    "event_type": "audio_extraction_error",
                    "camera_id": camera.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

    async def _broadcast_doorbell_ring(
        self,
        camera_id: str,
        camera_name: str,
        thumbnail_url: str,
        timestamp: datetime
    ) -> int:
        """
        Broadcast DOORBELL_RING message for immediate notification (Story P2-4.1 AC6).

        Sends priority notification before AI processing completes for fast alerting.

        Args:
            camera_id: Camera UUID
            camera_name: Camera display name
            thumbnail_url: URL/path to thumbnail image
            timestamp: Event timestamp

        Returns:
            Number of clients notified
        """
        try:
            # Lazy import to avoid circular imports
            from app.services.websocket_manager import get_websocket_manager

            websocket_manager = get_websocket_manager()

            # Story P2-4.1 AC6: DOORBELL_RING message format
            message = {
                "type": "DOORBELL_RING",
                "data": {
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "thumbnail_url": thumbnail_url,
                    "timestamp": timestamp.isoformat()
                }
            }

            clients_notified = await websocket_manager.broadcast(message)

            logger.info(
                f"DOORBELL_RING broadcast: {clients_notified} clients notified for '{camera_name}'",
                extra={
                    "event_type": "doorbell_ring_broadcast",
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "clients_notified": clients_notified
                }
            )

            return clients_notified

        except Exception as e:
            logger.warning(
                f"DOORBELL_RING broadcast error: {e}",
                extra={
                    "event_type": "doorbell_ring_broadcast_error",
                    "camera_id": camera_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return 0

    async def _broadcast_event_created(
        self,
        event: Event,
        camera: Camera
    ) -> int:
        """
        Broadcast EVENT_CREATED message via WebSocket (Story P2-3.3 AC12).

        Broadcasts event details to all connected frontend clients.

        Args:
            event: Stored Event model
            camera: Camera that captured the event

        Returns:
            Number of clients notified
        """
        try:
            # Lazy import to avoid circular imports
            from app.services.websocket_manager import get_websocket_manager

            websocket_manager = get_websocket_manager()

            # Parse objects_detected from JSON string
            try:
                objects_detected = json.loads(event.objects_detected)
            except (json.JSONDecodeError, TypeError):
                objects_detected = []

            # Broadcast EVENT_CREATED with all event details (AC12)
            message = {
                "type": "EVENT_CREATED",
                "data": {
                    "id": event.id,
                    "camera_id": event.camera_id,
                    "camera_name": camera.name,
                    "timestamp": event.timestamp.isoformat(),
                    "description": event.description,
                    "confidence": event.confidence,
                    "objects_detected": objects_detected,
                    "thumbnail_path": event.thumbnail_path,
                    "source_type": event.source_type,
                    "smart_detection_type": event.smart_detection_type,
                    "protect_event_id": event.protect_event_id,
                    "is_doorbell_ring": event.is_doorbell_ring  # Story P2-4.1
                }
            }

            clients_notified = await websocket_manager.broadcast(message)

            logger.debug(
                f"EVENT_CREATED broadcast: {clients_notified} clients notified",
                extra={
                    "event_type": "protect_event_broadcast",
                    "event_id": event.id,
                    "clients_notified": clients_notified
                }
            )

            return clients_notified

        except Exception as e:
            logger.warning(
                f"WebSocket broadcast error: {e}",
                extra={
                    "event_type": "protect_broadcast_error",
                    "event_id": event.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return 0

    async def _process_correlation(self, event: Event) -> None:
        """
        Process event for multi-camera correlation (Story P2-4.3 AC6).

        Fire-and-forget pattern - called via asyncio.create_task() so it
        doesn't block event creation.

        Args:
            event: Event to process for correlation
        """
        try:
            # Lazy import to avoid circular imports
            from app.services.correlation_service import get_correlation_service

            correlation_service = get_correlation_service()
            group_id = await correlation_service.process_event(event)

            if group_id:
                logger.info(
                    f"Event {event.id[:8]}... correlated to group {group_id[:8]}...",
                    extra={
                        "event_type": "protect_event_correlated",
                        "event_id": event.id,
                        "correlation_group_id": group_id
                    }
                )

        except Exception as e:
            # Log but don't fail - correlation is non-critical
            logger.warning(
                f"Correlation processing error for event {event.id[:8]}...: {e}",
                extra={
                    "event_type": "protect_correlation_error",
                    "event_id": event.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )


# Global singleton instance
_protect_event_handler: Optional[ProtectEventHandler] = None


def get_protect_event_handler() -> ProtectEventHandler:
    """Get the global ProtectEventHandler singleton instance."""
    global _protect_event_handler
    if _protect_event_handler is None:
        _protect_event_handler = ProtectEventHandler()
    return _protect_event_handler
