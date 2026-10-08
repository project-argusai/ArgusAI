"""
Shared pre-AI context gathering for Protect and RTSP vision paths.

Builds a context-enhanced prompt *before* the first vision call so descriptions
can name known people/vehicles and reuse similar past events. Both pipelines
must call this helper so they cannot drift again.

Fail-open and bounded: embedding / face / MCP failures never block analysis.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional
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

# Upper bound for per-object analysis (YuNet/SFace faces, vehicle detection,
# CLIP on up to three vehicle crops) before the vision call. It runs on the
# full-resolution snapshot; on the M4 this is tens of milliseconds once CLIP
# is warm. On timeout the event is described without object identity.
OBJECT_ANALYSIS_TIMEOUT_S = float(os.environ.get("ARGUS_OBJECT_ANALYSIS_TIMEOUT_S", "2.5") or 2.5)


DEFAULT_BASE_PROMPT = (
    "Describe what you see in this image. Include: "
    "WHO (people, their appearance, clothing), "
    "WHAT (objects, vehicles, packages), "
    "WHERE (location in frame), "
    "and ACTIONS (what is happening). "
    "Be specific and detailed. "
    "If HISTORICAL CONTEXT names a person and the image matches, use that name. "
    "Describe a vehicle's visible color, make, and model. A known-entity name is a label only. "
    "Mention that label only when it matches what you see, and do not treat a label "
    "with no stored color, make, or model as the vehicle's make or model. "
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
    # Per-object face/vehicle crops (ObjectAnalysis). Used after the vision
    # call to verify vehicles and stored as observations once the event exists.
    object_analysis: Optional[Any] = None


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
        object_analysis = None

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
            want_faces = looks_like_person and _privacy_flag_enabled(db, FACE_RECOGNITION_ENABLED)
            want_vehicles = looks_like_vehicle and _privacy_flag_enabled(db, VEHICLE_RECOGNITION_ENABLED)

            if (want_faces or want_vehicles) and thumbnail_base64:
                object_analysis = await self._safe_object_analysis(
                    thumbnail_base64,
                    faces=want_faces,
                    vehicles=want_vehicles,
                    plates=want_vehicles and self._plates_enabled(),
                )
                self._mark_parked(db, camera_id, object_analysis, event_id)
                self._resolve_plates(db, object_analysis)

            # Face match (named persons only): SFace face vs per-person face galleries.
            if want_faces:
                face_match = await self._safe_named_face_match(
                    db, thumbnail_base64, analysis=object_analysis
                )
                if _is_named(face_match):
                    named_identities.append(face_match)

            # Named vehicle hint for the prompt, only when this event is a vehicle.
            if want_vehicles:
                vehicle_match = self._gallery_vehicle_hint(db, object_analysis)
                if vehicle_match is None and not self._has_vehicle_galleries(db):
                    # No vehicle gallery enrolled yet: keep the earlier scene-level
                    # hint. It only shapes the prompt; links are verified after
                    # the vision call (event_entity_linking).
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
            object_analysis=object_analysis,
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

    async def _safe_object_analysis(
        self,
        thumbnail_base64: str,
        *,
        faces: bool,
        vehicles: bool,
        plates: bool = False,
    ):
        """Faces and vehicles as crops from the snapshot. Bounded; None on failure."""
        try:
            from app.services.object_identity_service import analyze_image_bytes

            raw = thumbnail_base64
            if raw.startswith("data:"):
                raw = raw.split(",", 1)[1]
            image_bytes = base64.b64decode(raw)
            if not image_bytes:
                return None
            return await asyncio.wait_for(
                analyze_image_bytes(image_bytes, faces=faces, vehicles=vehicles, plates=plates),
                OBJECT_ANALYSIS_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Object analysis timed out; describing without object identity",
                extra={"event_type": "object_analysis_timeout", "timeout_s": OBJECT_ANALYSIS_TIMEOUT_S},
            )
            return None
        except Exception as e:
            logger.debug(
                f"Object analysis failed open: {e}",
                extra={"event_type": "object_analysis_fail_open"},
            )
            return None

    def _mark_parked(self, db: Session, camera_id: str, analysis, event_id: Optional[str]) -> None:
        """Flag vehicle crops that are parked (seen in place on recent events). Never raises."""
        if analysis is None or not getattr(analysis, "vehicles", None):
            return
        try:
            from app.services.entity_gallery_service import mark_parked_vehicles

            flagged = mark_parked_vehicles(db, camera_id, analysis.vehicles, exclude_event_id=event_id)
            if flagged:
                logger.debug(
                    "Parked vehicles in view",
                    extra={"event_type": "parked_vehicles_flagged", "camera_id": camera_id, "count": flagged},
                )
        except Exception as e:
            logger.debug(f"Parked-vehicle check failed open: {e}")

    def _plates_enabled(self) -> bool:
        try:
            from app.services.plate_reader import plates_enabled

            return plates_enabled()
        except Exception:  # noqa: BLE001
            return False

    def _resolve_plates(self, db: Session, analysis) -> None:
        """Compare plate reads with saved vehicles and drop the hashes. Never raises."""
        if analysis is None or not getattr(analysis, "vehicles", None):
            return
        try:
            from app.services.entity_plate_service import resolve_plate_evidence

            resolve_plate_evidence(db, analysis)
        except Exception as e:
            logger.debug(f"Plate evidence failed open: {e}")
            for obs in analysis.vehicles:
                obs.plate_reads = []

    def _has_vehicle_galleries(self, db: Session) -> bool:
        try:
            from app.services.entity_gallery_service import get_entity_gallery_service

            return bool(get_entity_gallery_service().get_index(db).vehicles)
        except Exception:
            return False

    def _gallery_vehicle_hint(self, db: Session, analysis) -> Optional[EntityMatchResult]:
        """A vehicle the crop alone already identifies (strong crop score + colour)."""
        if analysis is None or not getattr(analysis, "vehicles", None):
            return None
        try:
            from app.models.recognized_entity import RecognizedEntity
            from app.services.entity_gallery_service import (
                evaluate_vehicle_candidates,
                get_entity_gallery_service,
                pick_vehicle,
            )
            from app.services.entity_service import _match_result
            from app.services.event_entity_linking import as_named_identity

            index = get_entity_gallery_service().get_index(db)
            plate_matched = set()
            for obs in analysis.vehicles:
                ev = getattr(obs, "plate_evidence", None)
                if ev is not None:
                    plate_matched |= set(ev.matched_entity_ids)
            candidate_ids = set(index.vehicles) | plate_matched
            if not candidate_ids:
                return None
            rows = db.query(RecognizedEntity).filter(
                RecognizedEntity.id.in_(list(candidate_ids))
            ).all()
            identities = [i for i in (as_named_identity(r) for r in rows) if i is not None]
            evidence = evaluate_vehicle_candidates(None, identities, analysis.vehicles, index.vehicles)
            winner, _ = pick_vehicle(evidence)
            # Only evidence that needs no description may shape the prompt:
            # a strong crop + colour, or a saved plate read on a moving car.
            if winner is None or winner.signal not in ("crop+color", "plate"):
                return None
            entity = next(r for r in rows if r.id == winner.entity_id)
            return _match_result(entity, similarity_score=round(winner.crop_score or 0.0, 4), is_new=False)
        except Exception as e:
            logger.debug(f"Pre-AI vehicle gallery hint failed open: {e}")
            return None

    async def _safe_named_face_match(
        self,
        db: Session,
        thumbnail_base64: Optional[str],
        analysis=None,
    ) -> Optional[EntityMatchResult]:
        """Named person whose face gallery matches a face in the snapshot.

        Face-to-face SFace comparison against per-person galleries (see
        ``entity_gallery_service.match_face``). A person with no enrolled
        face is never named. Never raises.
        """
        if analysis is None or not getattr(analysis, "faces", None):
            return None
        try:
            from app.models.recognized_entity import RecognizedEntity
            from app.services.entity_gallery_service import get_entity_gallery_service, match_face
            from app.services.entity_service import _match_result

            index = get_entity_gallery_service().get_index(db)
            if not index.faces:
                return None
            match = match_face(index, [f.embedding for f in analysis.faces])
            if match is None:
                return None
            face = analysis.faces[match.face_index]
            face.match_entity_id, face.match_score = match.entity_id, match.score
            entity = db.query(RecognizedEntity).filter(RecognizedEntity.id == match.entity_id).first()
            if entity is None:
                return None
            logger.info(
                "Face matched a saved person",
                extra={
                    "event_type": "pre_ai_face_matched",
                    "entity_id": match.entity_id,
                    "score": match.score,
                    "runner_up": None if match.runner_up is None else round(match.runner_up, 4),
                },
            )
            return _match_result(entity, similarity_score=match.score, is_new=False)
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
