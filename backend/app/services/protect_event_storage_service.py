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

Migrated to @singleton decorator as part of #450 (Lightweight DI Container).
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.camera import Camera
from app.services.ai_service import AIResult
from app.services.snapshot_service import SnapshotResult
from app.core.decorators import singleton

logger = logging.getLogger(__name__)


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


# Backward compatible getter (delegates to @singleton decorator)
def get_protect_event_storage_service() -> "ProtectEventStorageService":
    return ProtectEventStorageService()


def reset_protect_event_storage_service() -> None:
    ProtectEventStorageService._reset_instance()