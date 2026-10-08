"""
Verified named-entity linking for live events.

Live Protect ingest names people and vehicles before the first notification
(``PreAIContextService``). This module decides which of those names the
event actually supports, stores them as entity links, and then runs alert
rules so an entity rule ("Alert: BMW X3 detected") can fire on the event.

Why a verification step: entity reference embeddings are whole-scene CLIP
vectors. On a fixed camera the scene dominates that vector, so an empty
porch or a passing truck scores 0.8+ against every saved entity seen on the
same camera, and the closest one is close to random. Whole-scene vectors are
no longer used to link anything.

People are named only from a face match upstream (SFace face crop against
the person's face gallery, ``entity_gallery_service.match_face``).

Vehicles combine three signals (``entity_gallery_service.
evaluate_vehicle_candidates``): the detected vehicle *crop* against the
vehicle's crop gallery, the crop's colour, and whether the AI description
shows the vehicle's make (#679, ``vehicle_label_agrees``). A vehicle with an
enrolled gallery needs crop support; without a gallery, or when no vehicle
was detected in the frame, the #679 description rule applies unchanged.

Fail-open and bounded: nothing here may drop, delay, or fail an event.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, ContextManager, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.entity_alert_service import vehicle_label_agrees

logger = logging.getLogger(__name__)

# Upper bounds for the post-persist steps. They run after the event is stored
# and broadcast, so they never hold up the event itself. The bound only
# applies at await points; the DB work in between is a few small queries.
ENTITY_LINK_TIMEOUT_S = 5.0
ALERT_RULES_TIMEOUT_S = 10.0
OBSERVATION_SAVE_TIMEOUT_S = 5.0

_VEHICLE_WORDS = frozenset({"vehicle", "car", "truck", "van", "suv"})


@dataclass
class NamedIdentity:
    """A named entity an event shows, in the shape ``enrich_description`` reads."""

    entity_id: str
    name: str
    entity_type: str
    vehicle_color: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    similarity_score: Optional[float] = None
    reference_embedding: Optional[list] = None


def _text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def as_named_identity(obj: Any) -> Optional[NamedIdentity]:
    """Build a NamedIdentity from an EntityMatchResult or a RecognizedEntity row."""
    if obj is None:
        return None
    entity_id = _text(getattr(obj, "entity_id", None)) or _text(getattr(obj, "id", None))
    name = _text(getattr(obj, "name", None))
    entity_type = _text(getattr(obj, "entity_type", None))
    if not entity_id or not name or not entity_type:
        return None
    reference = None
    raw = getattr(obj, "reference_embedding", None)
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                reference = parsed
        except (TypeError, ValueError):
            reference = None
    score = getattr(obj, "similarity_score", None)
    return NamedIdentity(
        entity_id=entity_id,
        name=name,
        entity_type=entity_type,
        vehicle_color=_text(getattr(obj, "vehicle_color", None)),
        vehicle_make=_text(getattr(obj, "vehicle_make", None)),
        vehicle_model=_text(getattr(obj, "vehicle_model", None)),
        similarity_score=score if isinstance(score, (int, float)) and not isinstance(score, bool) else None,
        reference_embedding=reference,
    )


def event_looks_like_vehicle(event_type: Optional[str], ai_result: Any = None) -> bool:
    """Same scope rule as pre-AI naming: vehicles only on vehicle events.

    True when Protect called it a vehicle event, or the AI's structured
    identification / detected objects say the subject is a vehicle. A car
    parked in the background of a person event is not linked.
    """
    if isinstance(event_type, str) and event_type.lower() in _VEHICLE_WORDS:
        return True
    if ai_result is None:
        return False
    ident = getattr(ai_result, "identification", None)
    if isinstance(ident, dict):
        object_type = ident.get("object_type")
        if isinstance(object_type, str) and object_type.lower() == "vehicle":
            return True
    objects = getattr(ai_result, "objects_detected", None)
    if isinstance(objects, (list, tuple)):
        return any(isinstance(o, str) and o.lower() in _VEHICLE_WORDS for o in objects)
    return False


def _cosine(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    try:
        if len(a) != len(b) or not a:
            return None
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if not na or not nb:
            return None
        return dot / (na * nb)
    except TypeError:
        return None


def select_named_vehicles(
    description: str,
    vehicles: Iterable[NamedIdentity],
    *,
    preferred_ids: Iterable[str] = (),
    embedding: Optional[Sequence[float]] = None,
) -> List[NamedIdentity]:
    """Named vehicles the description supports. At most one is returned.

    A vehicle qualifies when ``vehicle_label_agrees`` accepts it. With
    several candidates, the upstream CLIP pick wins if it is one of them,
    then the highest CLIP similarity. With no way to choose, nothing is
    linked rather than guessing.
    """
    seen = set()
    agreeing: List[NamedIdentity] = []
    for vehicle in vehicles:
        if vehicle is None or vehicle.entity_type != "vehicle" or vehicle.entity_id in seen:
            continue
        seen.add(vehicle.entity_id)
        if vehicle_label_agrees(description or "", vehicle):
            agreeing.append(vehicle)
    if len(agreeing) <= 1:
        return agreeing

    preferred = set(preferred_ids or ())
    picked = [v for v in agreeing if v.entity_id in preferred]
    if len(picked) == 1:
        return picked

    if embedding:
        scored = [
            (score, v)
            for v in agreeing
            if v.reference_embedding
            and (score := _cosine(embedding, v.reference_embedding)) is not None
        ]
        if scored:
            scored.sort(key=lambda item: item[0], reverse=True)
            best_score, best = scored[0]
            best.similarity_score = round(float(best_score), 4)
            return [best]

    logger.info(
        "Several saved vehicles fit the description; not linking any",
        extra={
            "event_type": "vehicle_link_ambiguous",
            "candidate_count": len(agreeing),
        },
    )
    return []


def _all_named_vehicle_rows(db: Optional[Session]) -> List[NamedIdentity]:
    if db is None:
        return []
    from app.models.recognized_entity import RecognizedEntity

    rows = (
        db.query(RecognizedEntity)
        .filter(
            RecognizedEntity.entity_type == "vehicle",
            RecognizedEntity.name.isnot(None),
        )
        .all()
    )
    return [i for i in (as_named_identity(r) for r in rows) if i is not None]


def _vehicle_gallery(db: Optional[Session]) -> dict:
    if db is None:
        return {}
    try:
        from app.services.entity_gallery_service import get_entity_gallery_service

        return get_entity_gallery_service().get_index(db).vehicles
    except Exception as exc:  # noqa: BLE001 - fall back to the description rule
        logger.info(
            "Vehicle gallery unavailable; using the description rule only",
            extra={"event_type": "vehicle_gallery_unavailable", "error_type": type(exc).__name__},
        )
        return {}


def verify_named_identities(
    db: Optional[Session],
    *,
    description: Optional[str],
    candidates: Iterable[Any],
    looks_like_vehicle: bool,
    embedding: Optional[Sequence[float]] = None,
    object_analysis: Any = None,
) -> List[NamedIdentity]:
    """The named people and vehicles this event supports, people first.

    ``candidates`` are the pre-AI named identities (face-matched people and
    the vehicle hint). People pass through: they were named from a face
    gallery match, which is its own verification. Vehicles are chosen only on
    vehicle events, from every saved named vehicle plus the hint, by
    ``evaluate_vehicle_candidates`` / ``pick_vehicle`` using the event's
    vehicle crops (``object_analysis``), their colour, and the description.
    ``description`` may be None (the vision call failed); then only crop
    evidence can link a vehicle.
    """
    from app.services.entity_gallery_service import (
        evaluate_vehicle_candidates,
        pick_vehicle,
    )

    people: List[NamedIdentity] = []
    clip_vehicles: List[NamedIdentity] = []
    for candidate in candidates or []:
        identity = as_named_identity(candidate)
        if identity is None:
            continue
        if identity.entity_type == "person":
            if all(p.entity_id != identity.entity_id for p in people):
                people.append(identity)
        elif identity.entity_type == "vehicle":
            clip_vehicles.append(identity)

    vehicles: List[NamedIdentity] = []
    observed = list(getattr(object_analysis, "vehicles", None) or [])
    if looks_like_vehicle and (description or observed):
        pool: List[NamedIdentity] = []
        seen = set()
        for identity in _all_named_vehicle_rows(db) + clip_vehicles:
            if identity.entity_id not in seen:
                seen.add(identity.entity_id)
                pool.append(identity)
        gallery = _vehicle_gallery(db)
        evidence = evaluate_vehicle_candidates(description, pool, observed, gallery)
        winner, tied = pick_vehicle(evidence)
        by_id = {i.entity_id: i for i in pool}
        if winner is not None:
            chosen = by_id[winner.entity_id]
            if winner.crop_score is not None:
                chosen.similarity_score = round(float(winner.crop_score), 4)
            vehicles = [chosen]
        elif tied:
            vehicles = select_named_vehicles(
                description or "",
                [by_id[e.entity_id] for e in tied],
                preferred_ids=[v.entity_id for v in clip_vehicles],
                embedding=embedding,
            )
        if evidence and (observed or gallery):
            logger.info(
                "Vehicle identity evidence",
                extra={
                    "event_type": "vehicle_identity_evidence",
                    "vehicles_detected": len(observed),
                    "linked": [v.entity_id for v in vehicles],
                    "candidates": [e.as_log() for e in evidence if e.has_gallery or e.accepted],
                },
            )

    rejected = [v.name for v in clip_vehicles if all(v.entity_id != k.entity_id for k in vehicles)]
    if rejected:
        logger.info(
            "Dropped a vehicle hint the event does not support",
            extra={"event_type": "vehicle_clip_match_rejected", "rejected": rejected},
        )
    return people + vehicles


async def save_event_observations(
    event_id: str,
    object_analysis: Any,
    session_factory: "SessionFactory",
    *,
    when: Any = None,
) -> None:
    """Store the event's face/vehicle crops as unconfirmed observations.

    Observations never change a gallery by themselves; they are what a later
    "assign" or "use as reference" enrolls. Errors are logged, not raised.
    """
    if object_analysis is None or getattr(object_analysis, "is_empty", True):
        return
    from app.services.entity_gallery_service import get_entity_gallery_service

    with session_factory() as db:
        created = get_entity_gallery_service().save_observations(db, event_id, object_analysis, when=when)
    logger.debug(
        "Stored event object observations",
        extra={
            "event_type": "object_observations_stored",
            "event_id": event_id,
            "faces": len(created.get("face", [])),
            "vehicles": len(created.get("vehicle", [])),
        },
    )


SessionFactory = Callable[[], ContextManager[Session]]


async def link_stored_matches(event_id: str, session_factory: SessionFactory) -> List[str]:
    """Write entity links for the ids already stored on the event."""
    from app.models.event import Event
    from app.services.entity_service import get_entity_service, parse_entity_id_list

    with session_factory() as db:
        event = db.query(Event).filter(Event.id == event_id).first()
        if event is None:
            return []
        ids = parse_entity_id_list(event.matched_entity_ids)
        if not ids:
            return []
        return await get_entity_service().link_matched_entities(db, event_id, ids)


async def evaluate_alert_rules(event_id: str, session_factory: SessionFactory):
    from app.services.alert_engine import process_event_alerts

    with session_factory() as db:
        return await process_event_alerts(event_id, db)


async def run_post_persist_entity_steps(
    event_id: Optional[str],
    *,
    session_factory: SessionFactory,
    link_timeout_s: float = ENTITY_LINK_TIMEOUT_S,
    alert_timeout_s: float = ALERT_RULES_TIMEOUT_S,
    object_analysis: Any = None,
    observation_timeout_s: float = OBSERVATION_SAVE_TIMEOUT_S,
) -> None:
    """Link verified entities, then evaluate alert rules, then store crops. Never raises.

    Order matters: entity rules read ``matched_entity_ids``, which are on the
    row from the first persist, so the rules see the same names the user
    sees. A link failure or timeout is logged and alert rules still run.
    Crop observations are stored last; they only matter for later enrollment.
    """
    if not isinstance(event_id, str) or not event_id:
        return

    try:
        await asyncio.wait_for(link_stored_matches(event_id, session_factory), link_timeout_s)
    except asyncio.TimeoutError:
        logger.warning(
            "Entity linking timed out; event kept without entity links",
            extra={"event_type": "entity_link_timeout", "event_id": event_id},
        )
    except Exception as exc:  # noqa: BLE001 - must never fail the event
        logger.warning(
            "Entity linking failed; event kept without entity links",
            extra={
                "event_type": "entity_link_failed",
                "event_id": event_id,
                "error_type": type(exc).__name__,
            },
        )

    try:
        await asyncio.wait_for(evaluate_alert_rules(event_id, session_factory), alert_timeout_s)
    except asyncio.TimeoutError:
        logger.warning(
            "Alert rule evaluation timed out",
            extra={"event_type": "alert_rules_timeout", "event_id": event_id},
        )
    except Exception as exc:  # noqa: BLE001 - must never fail the event
        logger.warning(
            "Alert rule evaluation failed",
            extra={
                "event_type": "alert_rules_failed",
                "event_id": event_id,
                "error_type": type(exc).__name__,
            },
        )

    if object_analysis is None:
        return
    try:
        await asyncio.wait_for(
            save_event_observations(event_id, object_analysis, session_factory),
            observation_timeout_s,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Storing object observations timed out",
            extra={"event_type": "object_observations_timeout", "event_id": event_id},
        )
    except Exception as exc:  # noqa: BLE001 - must never fail the event
        logger.warning(
            "Storing object observations failed",
            extra={
                "event_type": "object_observations_failed",
                "event_id": event_id,
                "error_type": type(exc).__name__,
            },
        )
