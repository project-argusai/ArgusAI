"""
Shared pre-AI context gathering for Protect and RTSP vision paths.

Builds a context-enhanced prompt *before* the first vision call so descriptions
can name known people/vehicles and reuse similar past events. Both pipelines
must call this helper so they cannot drift again.

Fail-open and bounded: embedding / face / MCP failures never block analysis.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.decorators import singleton
from app.services.ai_types import FACE_RECOGNITION_ENABLED, VEHICLE_RECOGNITION_ENABLED
from app.services.context_prompt_service import (
    ContextEnhancedPromptResult,
    get_context_prompt_service,
)
from app.services.entity_service import EntityMatchResult

logger = logging.getLogger(__name__)


DEFAULT_BASE_PROMPT = (
    "Describe what you see in this image. Include: "
    "WHO (people, their appearance, clothing), "
    "WHAT (objects, vehicles, packages), "
    "WHERE (location in frame), "
    "and ACTIONS (what is happening). "
    "Be specific and detailed. "
    "If HISTORICAL CONTEXT names a person or vehicle and the image matches, use that name. "
    "If a vehicle is listed, use its color/make/model. "
    "If a delivery uniform or logo is visible, name the carrier "
    "(UPS, FedEx, USPS, Amazon, or DHL). "
    "State the local time and camera/location naturally."
)

DOORBELL_BASE_PROMPT = (
    "Describe who is at the front door. Include their appearance, what they're wearing, "
    "and if they appear to be a delivery person, visitor, or solicitor. "
    "If HISTORICAL CONTEXT names a person and the image matches, use that name. "
    "If a delivery uniform or logo is visible, name the carrier "
    "(UPS, FedEx, USPS, Amazon, or DHL). "
    "State the local time naturally."
)


@dataclass
class PreAIContextBundle:
    """Everything the vision call and later persist/notify steps need."""
    custom_prompt: Optional[str]
    context_result: Optional[ContextEnhancedPromptResult]
    embedding_vector: Optional[list]
    named_identities: List[EntityMatchResult] = field(default_factory=list)
    local_timestamp: str = ""
    matched_entity_ids: List[str] = field(default_factory=list)
    context_included: bool = False
    context_stats: Optional[dict] = None


def format_timestamp_for_ai(timestamp: datetime, db: Session) -> str:
    """
    Format a timestamp for the AI prompt using the user's configured timezone.

    Reads ``settings_timezone`` and converts UTC to local wall-clock time.
    """
    try:
        from app.models.system_setting import SystemSetting

        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "settings_timezone"
        ).first()
        tz_name = setting.value if setting else "UTC"

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        try:
            local_time = timestamp.astimezone(ZoneInfo(tz_name))
            return local_time.isoformat()
        except Exception:
            logger.warning(f"Invalid timezone '{tz_name}', using UTC")
            return timestamp.isoformat()
    except Exception as e:
        logger.warning(f"Error formatting timestamp for AI: {e}")
        return timestamp.isoformat()


def _is_named(entity: Optional[EntityMatchResult]) -> bool:
    return bool(entity and entity.name and str(entity.name).strip())


def _privacy_flag_enabled(db: Session, key: str) -> bool:
    from app.models.system_setting import SystemSetting

    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return bool(setting and str(setting.value).lower() == "true")


@singleton
class PreAIContextService:
    """Gather named-entity, similar-event, and MCP context before vision."""

    async def gather(
        self,
        db: Session,
        camera_id: str,
        camera_name: str,
        event_time: datetime,
        detected_objects: Optional[List[str]] = None,
        thumbnail_base64: Optional[str] = None,
        embedding_vector: Optional[list] = None,
        event_type: Optional[str] = None,
        is_doorbell_ring: bool = False,
        clip_scene_entity: Optional[EntityMatchResult] = None,
        event_id: Optional[str] = None,
        context_service=None,
    ) -> PreAIContextBundle:
        """
        Build a context-enhanced prompt for the upcoming vision call.

        CLIP-scene matches are used for similar-event RAG only. Person *names*
        are injected only from face matching (when enabled). Vehicle names are
        injected only when the event looks like a vehicle and the matched
        entity is a named vehicle.
        """
        try:
            local_timestamp = format_timestamp_for_ai(event_time, db)
        except Exception:
            iso = getattr(event_time, "isoformat", None)
            local_timestamp = iso() if callable(iso) else str(event_time)
        named_identities: List[EntityMatchResult] = []

        if embedding_vector is None and thumbnail_base64:
            embedding_vector = await self._safe_embedding(thumbnail_base64)

        try:
            objects = [o.lower() for o in (detected_objects or []) if o]
            if event_type:
                objects.append(str(event_type).lower())
            looks_like_vehicle = any(o in ("vehicle", "car", "truck", "van") for o in objects)
            looks_like_person = any(
                o in ("person", "people", "ring", "package") for o in objects
            ) or is_doorbell_ring

            # Face match (named persons only). Fail-open if model files are missing.
            if looks_like_person and _privacy_flag_enabled(db, FACE_RECOGNITION_ENABLED):
                face_match = await self._safe_named_face_match(db, thumbnail_base64)
                if _is_named(face_match):
                    named_identities.append(face_match)

            # Named vehicle from CLIP only when this event is actually a vehicle.
            if looks_like_vehicle and _privacy_flag_enabled(db, VEHICLE_RECOGNITION_ENABLED):
                vehicle_match = clip_scene_entity
                if vehicle_match is None and embedding_vector is not None:
                    vehicle_match = await self._safe_clip_match(db, embedding_vector)
                if (
                    _is_named(vehicle_match)
                    and vehicle_match.entity_type == "vehicle"
                ):
                    named_identities.append(vehicle_match)
            # CLIP-scene person matches are intentionally ignored for naming.
        except Exception as e:
            logger.debug(f"Pre-AI identity matching failed open: {e}")

        prompt_entity = next(
            (e for e in named_identities if _is_named(e)),
            None,
        )

        base_prompt = DOORBELL_BASE_PROMPT if is_doorbell_ring else DEFAULT_BASE_PROMPT
        context_result = None
        custom_prompt = base_prompt

        try:
            context_service = context_service or get_context_prompt_service()
            context_result = await context_service.build_context_enhanced_prompt(
                db=db,
                event_id=event_id or "pre-persist",
                base_prompt=base_prompt,
                camera_id=camera_id,
                event_time=event_time,
                matched_entity=prompt_entity,
                query_embedding=embedding_vector,
            )
            if context_result and context_result.prompt:
                custom_prompt = context_result.prompt
        except Exception as e:
            logger.warning(
                f"Pre-AI context build failed (proceeding without context): {e}",
                extra={"camera_id": camera_id, "error": str(e)},
            )

        context_included = bool(context_result and context_result.context_included)
        context_stats = None
        if context_result:
            try:
                gather_ms = getattr(context_result, "context_gather_time_ms", 0.0) or 0.0
                context_stats = {
                    "entity_context_included": bool(getattr(context_result, "entity_context_included", False)),
                    "similar_events_count": int(getattr(context_result, "similar_events_count", 0) or 0),
                    "time_pattern_included": bool(getattr(context_result, "time_pattern_included", False)),
                    "context_gather_time_ms": round(float(gather_ms), 2),
                    "mcp_context_included": bool(getattr(context_result, "mcp_context_included", False)),
                    "entity_name": getattr(context_result, "entity_name", None),
                }
            except (TypeError, ValueError):
                context_stats = {"entity_context_included": False}

        return PreAIContextBundle(
            custom_prompt=custom_prompt,
            context_result=context_result,
            embedding_vector=embedding_vector,
            named_identities=named_identities,
            local_timestamp=local_timestamp,
            matched_entity_ids=[e.entity_id for e in named_identities],
            context_included=context_included,
            context_stats=context_stats,
        )

    async def _safe_embedding(self, thumbnail_base64: str) -> Optional[list]:
        try:
            from app.services.embedding_service import get_embedding_service

            return await get_embedding_service().generate_embedding_from_base64(
                thumbnail_base64
            )
        except Exception as e:
            logger.debug(f"Pre-AI embedding generation failed: {e}")
            return None

    async def _safe_clip_match(
        self, db: Session, embedding_vector: list
    ) -> Optional[EntityMatchResult]:
        try:
            from app.services.entity_service import get_entity_service

            return await get_entity_service().match_entity_only(
                db=db,
                embedding=embedding_vector,
                threshold=0.75,
            )
        except Exception as e:
            logger.debug(f"Pre-AI CLIP entity match failed: {e}")
            return None

    async def _safe_named_face_match(
        self,
        db: Session,
        thumbnail_base64: Optional[str],
    ) -> Optional[EntityMatchResult]:
        if not thumbnail_base64:
            return None
        try:
            from app.services.face_detection_service import get_face_detection_service
            from app.services.embedding_service import get_embedding_service
            from app.services.person_matching_service import get_person_matching_service

            raw = thumbnail_base64
            if raw.startswith("data:"):
                raw = raw.split(",", 1)[1]
            thumbnail_bytes = base64.b64decode(raw)
            if not thumbnail_bytes:
                return None

            detector = get_face_detection_service()
            faces = await detector.detect_faces(thumbnail_bytes)
            if not faces:
                return None

            best = max(faces, key=lambda f: f.confidence)
            face_bytes = await detector.extract_face_region(thumbnail_bytes, best.bbox)
            face_embedding = await get_embedding_service().generate_embedding(face_bytes)
            return await get_person_matching_service().match_named_person_by_embedding(
                db, face_embedding
            )
        except FileNotFoundError as e:
            logger.info(
                f"Face model files missing; skipping pre-AI face match: {e}",
                extra={"event_type": "pre_ai_face_model_missing"},
            )
            return None
        except Exception as e:
            logger.debug(
                f"Pre-AI face match failed open: {e}",
                extra={"event_type": "pre_ai_face_match_fail_open"},
            )
            return None


def get_pre_ai_context_service() -> PreAIContextService:
    return PreAIContextService()


def reset_pre_ai_context_service() -> None:
    PreAIContextService._reset_instance()
