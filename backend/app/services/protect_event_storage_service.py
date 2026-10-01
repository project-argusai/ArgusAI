"""
ProtectEventStorageService

Responsible for creating, enriching, persisting, and (optionally) broadcasting
Protect events after AI analysis has completed.

This service owns the complex Event model construction that pulls together:
- AI results (description, confidence, objects, provider, cost, bounding boxes)
- Analysis metadata (analysis_mode, frame_count, fallback_reason, key frames)
- Audio transcription
- Doorbell / ring flags
- Source information (protect_event_id, etc.)

Extracted from ProtectEventHandler during Phase 4 decomposition.

# Migrated to @singleton decorator as part of #450 (Lightweight DI Container).
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.camera import Camera
from app.services.ai_service import AIResult
from app.services.identification import dumps_identification
from app.services.snapshot_service import SnapshotResult
from app.core.decorators import singleton

logger = logging.getLogger(__name__)

# smart_detection_type is a single token (String(20)) matched with equality by
# filters, HomeKit, and the event badge. Added types from a Protect update are
# unioned into objects_detected instead of rewriting that token.
_KNOWN_DETECTION_TYPES = frozenset(
    {"person", "vehicle", "package", "animal", "motion", "ring"}
)


def ai_response_time_ms_from_result(ai_result: Optional[object]) -> Optional[int]:
    """Milliseconds recorded on an AI result, or None when it was not set."""
    raw = getattr(ai_result, "response_time_ms", None) if ai_result is not None else None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if raw < 0:
        return None
    return int(raw)


@singleton
class ProtectEventStorageService:
    """
    Service that handles the final creation and persistence of Protect events.
    """

    def __init__(self):
        pass

    async def persist_protect_event(
        self,
        db: Session,
        camera: Camera,
        snapshot_result: SnapshotResult,
        ai_result: Optional[AIResult],
        protect_event_id: Optional[str],
        event_type: str,
        is_doorbell_ring: bool = False,
        analysis_mode: str = "single_frame",
        frame_count_used: Optional[int] = None,
        fallback_reason: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        key_frames_base64: Optional[List[str]] = None,
        frame_timestamps: Optional[List[float]] = None,
        bounding_boxes: Optional[List[Dict[str, Any]]] = None,
        event_id_override: Optional[str] = None,
        delivery_carrier: Optional[str] = None,
        context_included: bool = False,
        context_stats: Optional[str] = None,
        recognition_status: Optional[str] = None,
        enriched_description: Optional[str] = None,
        matched_entity_ids: Optional[str] = None,
        detection_start: Optional[datetime] = None,
        detection_end: Optional[datetime] = None,
        detection_peak: Optional[datetime] = None,
        subject_box: Optional[str] = None,
        ai_response_time_ms: Optional[int] = None,
    ) -> Event:
        """
        Construct and persist a fully enriched Protect Event record.
        """
        event = Event(
            camera_id=camera.id,
            timestamp=snapshot_result.timestamp,
            description=ai_result.description if ai_result else "AI analysis unavailable",
            confidence=ai_result.confidence if ai_result else 0.0,
            objects_detected=json.dumps(ai_result.objects_detected) if ai_result else json.dumps([event_type]),
            thumbnail_path=snapshot_result.thumbnail_path,
            thumbnail_base64=None,
            alert_triggered=False,
            source_type='protect',
            protect_event_id=protect_event_id,
            smart_detection_type=event_type,
            is_doorbell_ring=is_doorbell_ring,
            provider_used=ai_result.provider if ai_result else None,
            fallback_reason=fallback_reason,
            analysis_mode=analysis_mode,
            frame_count_used=frame_count_used,
            audio_transcription=audio_transcription,
            ai_confidence=ai_result.ai_confidence if ai_result else None,
            low_confidence=False,
            vague_reason=None,
            ai_cost=ai_result.cost_estimate if ai_result else 0.0,
            key_frames_base64=key_frames_base64,
            frame_timestamps=frame_timestamps,
            bounding_boxes=json.dumps(bounding_boxes) if bounding_boxes else None,
            has_annotations=bool(bounding_boxes),
            delivery_carrier=delivery_carrier,
            context_included=context_included,
            context_stats=context_stats,
            recognition_status=recognition_status,
            enriched_description=enriched_description,
            matched_entity_ids=matched_entity_ids,
            identification=(
                dumps_identification(getattr(ai_result, "identification", None))
                if ai_result
                else None
            ),
            detection_start=detection_start,
            detection_end=detection_end,
            detection_peak=detection_peak,
            subject_box=subject_box,
            ai_response_time_ms=(
                ai_response_time_ms
                if ai_response_time_ms is not None
                else ai_response_time_ms_from_result(ai_result)
            ),
        )

        if event_id_override:
            event.id = event_id_override

        db.add(event)
        db.commit()
        db.refresh(event)

        logger.info(
            f"Event persisted for camera '{camera.name}'",
            extra={
                "event_type": "protect_event_persisted",
                "camera_id": camera.id,
                "event_id": event.id,
                "provider": getattr(ai_result, 'provider', None),
                "analysis_mode": analysis_mode,
            }
        )

        return event

    def find_by_protect_event_id(
        self, db: Session, protect_event_id: Optional[str]
    ) -> Optional[Event]:
        """Return the earliest stored row for this Protect id, if any.

        Historical duplicates are left in place. Callers update the earliest
        row and do not insert another one.
        """
        if not protect_event_id:
            return None
        row = (
            db.query(Event)
            .filter(
                Event.protect_event_id == str(protect_event_id),
                Event.source_type == "protect",
            )
            .order_by(Event.timestamp.asc(), Event.id.asc())
            .first()
        )
        # A non-Event result is not a stored Protect event. Fail closed rather
        # than merging into an unexpected object.
        if not isinstance(row, Event):
            return None
        return row

    def merge_detection_types(
        self,
        db: Session,
        event: Event,
        detection_types: Optional[List[str]],
        is_doorbell_ring: bool = False,
    ) -> bool:
        """Union newly reported smart-detect types into an existing Protect row.

        Does not change an existing smart_detection_type. That column is a
        single token used by exact-match filters. The original description,
        thumbnail, and alert state are left alone. Returns True when a column
        changed.
        """
        if event is None:
            return False

        allowed: List[str] = []
        for detection_type in detection_types or []:
            if (
                isinstance(detection_type, str)
                and detection_type in _KNOWN_DETECTION_TYPES
                and detection_type not in allowed
            ):
                allowed.append(detection_type)

        changed = False
        parsed: Any
        try:
            parsed = json.loads(event.objects_detected) if event.objects_detected else []
        except (json.JSONDecodeError, TypeError):
            parsed = None

        if isinstance(parsed, list):
            for detection_type in allowed:
                if detection_type not in parsed:
                    parsed.append(detection_type)
                    changed = True
            if changed:
                event.objects_detected = json.dumps(parsed)
        elif allowed:
            logger.warning(
                "Skipping detection-type merge because objects_detected is not a JSON list",
                extra={
                    "event_type": "protect_event_merge_skipped",
                    "event_id": event.id,
                },
            )

        if is_doorbell_ring and not event.is_doorbell_ring:
            event.is_doorbell_ring = True
            changed = True

        if not event.smart_detection_type and allowed:
            event.smart_detection_type = allowed[0]
            changed = True

        if changed:
            db.commit()
            db.refresh(event)
            logger.info(
                "Merged Protect detection update into existing event",
                extra={
                    "event_type": "protect_event_types_merged",
                    "event_id": event.id,
                    "protect_event_id": event.protect_event_id,
                    "detection_types": allowed,
                    "is_doorbell_ring": bool(event.is_doorbell_ring),
                },
            )
        return changed


# Backward compatible getter (delegates to @singleton decorator)
def get_protect_event_storage_service() -> "ProtectEventStorageService":
    return ProtectEventStorageService()


def reset_protect_event_storage_service() -> None:
    ProtectEventStorageService._reset_instance()