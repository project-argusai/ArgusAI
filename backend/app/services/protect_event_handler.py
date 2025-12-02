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
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, TYPE_CHECKING

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.camera import Camera
from app.models.event import Event
from app.services.snapshot_service import get_snapshot_service, SnapshotResult

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
            active_smart = getattr(new_obj, 'active_smart_detect_types', None)
            logger.debug(
                f"WebSocket update for {model_type} {protect_camera_id[:8]}...: "
                f"motion={is_motion}, smart_detect={active_smart}",
                extra={
                    "event_type": "protect_ws_update",
                    "model_type": model_type,
                    "protect_camera_id": protect_camera_id,
                    "is_motion_currently_detected": is_motion,
                    "active_smart_detect_types": str(active_smart) if active_smart else None
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

                    # Story P2-3.2: Retrieve snapshot for AI processing
                    snapshot_result = await self._retrieve_snapshot(
                        controller_id,
                        camera.protect_camera_id,
                        camera.id,
                        camera.name,
                        event_type
                    )

                    if not snapshot_result:
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

                    ai_result = await self._submit_to_ai_pipeline(
                        snapshot_result,
                        camera,
                        filter_type,  # Use mapped type (person, vehicle, ring, etc.)
                        is_doorbell_ring=is_doorbell_ring  # Story P2-4.1: Use doorbell prompt
                    )

                    if not ai_result or not ai_result.success:
                        logger.warning(
                            f"AI pipeline failed for camera '{camera.name}'",
                            extra={
                                "event_type": "protect_ai_failed",
                                "camera_id": camera.id,
                                "error": ai_result.error if ai_result else "No result"
                            }
                        )
                        return False

                    # Story P2-3.3: Store event in database
                    stored_event = await self._store_protect_event(
                        db,
                        ai_result,
                        snapshot_result,
                        camera,
                        filter_type,
                        protect_event_id,
                        is_doorbell_ring=is_doorbell_ring  # Story P2-4.1 AC3, AC5
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

        # Check for smart detection types
        # uiprotect uses 'active_smart_detect_types' (not 'smart_detect_types')
        # This returns a list of SmartDetectObjectType enums when smart detection is active
        smart_detect_types = getattr(obj, 'active_smart_detect_types', None)
        if smart_detect_types:
            for detect_type in smart_detect_types:
                # SmartDetectObjectType enum has .value attribute (e.g., 'person', 'vehicle')
                detect_value = getattr(detect_type, 'value', str(detect_type)).lower()
                # Convert to our event type format
                event_key = f"smart_detect_{detect_value}"
                if event_key in VALID_EVENT_TYPES:
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
        is_doorbell_ring: bool = False
    ) -> Optional["AIResult"]:
        """
        Submit snapshot to AI pipeline for description generation (Story P2-3.3 AC1-3, P2-4.1 AC4).

        Converts base64 image to numpy array and calls AIService.generate_description().
        Uses doorbell-specific prompt for ring events (Story P2-4.1).

        Args:
            snapshot_result: Snapshot with base64-encoded image
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            is_doorbell_ring: If True, use doorbell-specific AI prompt (Story P2-4.1)

        Returns:
            AIResult with description, or None on failure
        """
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

            # Convert base64 to numpy array (BGR format for OpenCV/AI)
            # (AC2: Use existing AIService.generate_description with image)
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
            # detected_objects provides context about what was detected
            result = await ai_service.generate_description(
                frame=frame_bgr,
                camera_name=camera.name,
                timestamp=snapshot_result.timestamp.isoformat(),
                detected_objects=[event_type],  # AC3: Include event type
                sla_timeout_ms=5000,  # 5s SLA target
                custom_prompt=custom_prompt  # Story P2-4.1: Doorbell prompt
            )

            logger.info(
                f"AI description generated for camera '{camera.name}': {result.description[:50]}...",
                extra={
                    "event_type": "protect_ai_success",
                    "camera_id": camera.id,
                    "ai_provider": result.provider,
                    "confidence": result.confidence,
                    "response_time_ms": result.response_time_ms,
                    "is_doorbell_ring": is_doorbell_ring
                }
            )

            return result

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

    async def _store_protect_event(
        self,
        db: Session,
        ai_result: "AIResult",
        snapshot_result: SnapshotResult,
        camera: Camera,
        event_type: str,
        protect_event_id: Optional[str],
        is_doorbell_ring: bool = False
    ) -> Optional[Event]:
        """
        Store Protect event in database (Story P2-3.3 AC5-9, P2-4.1 AC3, AC5).

        Creates Event record with source_type='protect' and all AI/snapshot fields.

        Args:
            db: Database session
            ai_result: AI description result
            snapshot_result: Snapshot with thumbnail path
            camera: Camera that captured the event
            event_type: Detection type (person, vehicle, ring, etc.)
            protect_event_id: Protect's native event ID
            is_doorbell_ring: Whether this is a doorbell ring event (Story P2-4.1)

        Returns:
            Stored Event model or None on failure
        """
        try:
            # Create Event record (AC5-9, P2-4.1 AC3, AC5)
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
                is_doorbell_ring=is_doorbell_ring  # Story P2-4.1 AC3, AC5
            )

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
                    "is_doorbell_ring": event.is_doorbell_ring
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
