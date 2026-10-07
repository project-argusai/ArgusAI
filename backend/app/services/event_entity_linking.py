"""
Verified named-entity linking for live events.

Live Protect ingest names people and vehicles before the first notification
(``PreAIContextService``). This module decides which of those names the
event actually supports, stores them as entity links, and then runs alert
rules so an entity rule ("Alert: BMW X3 detected") can fire on the event.

Why a verification step: entity reference embeddings are whole-scene CLIP
vectors. On a fixed camera the scene dominates that vector, so an empty
porch or a passing truck scores 0.8+ against every saved entity seen on the
same camera, and the closest one is close to random. People are named only
from a face match upstream. A vehicle is linked only when the AI's own
description shows the entity's make (and does not contradict its model or
color), using the same ``vehicle_label_agrees`` rule as the description
rewrite. CLIP similarity only breaks a tie between vehicles that both agree.

Fail-open and bounded: nothing here may drop, delay, or fail an event.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, ContextManager, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.entity_alert_service import (
    vehicle_label_agrees,
    visible_vehicle_details,
)

logger = logging.getLogger(__name__)

# Upper bounds for the post-persist steps. They run after the event is stored
# and broadcast, so they never hold up the event itself. The bound only
# applies at await points; the DB work in between is a few small queries.
ENTITY_LINK_TIMEOUT_S = 5.0
ALERT_RULES_TIMEOUT_S = 10.0

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


def _has_make_hint(identity: NamedIdentity) -> bool:
    """A make the description can confirm, from the stored make or the name."""
    if identity.vehicle_make:
        return True
    return visible_vehicle_details(identity.name)[1] is not None


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


def _named_vehicle_rows(db: Optional[Session]) -> List[NamedIdentity]:
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
    out = []
    for row in rows:
        identity = as_named_identity(row)
        if identity is not None and _has_make_hint(identity):
            out.append(identity)
    return out


def verify_named_identities(
    db: Optional[Session],
    *,
    description: Optional[str],
    candidates: Iterable[Any],
    looks_like_vehicle: bool,
    embedding: Optional[Sequence[float]] = None,
) -> List[NamedIdentity]:
    """The named people and vehicles this event supports, people first.

    ``candidates`` are the pre-AI named identities (face-matched people and
    the CLIP-picked vehicle). People pass through; there is no second
    signal to check a face match against. Vehicles are chosen by
    ``select_named_vehicles`` from every saved, named vehicle with a make,
    plus the CLIP pick, and only on vehicle events.
    """
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
    if looks_like_vehicle and description:
        pool = _named_vehicle_rows(db) + clip_vehicles
        vehicles = select_named_vehicles(
            description,
            pool,
            preferred_ids=[v.entity_id for v in clip_vehicles],
            embedding=embedding,
        )

    rejected = [v.name for v in clip_vehicles if all(v.entity_id != k.entity_id for k in vehicles)]
    if rejected:
        logger.info(
            "Dropped a CLIP vehicle match the description does not support",
            extra={"event_type": "vehicle_clip_match_rejected", "rejected": rejected},
        )
    return people + vehicles


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
) -> None:
    """Link verified entities, then evaluate alert rules. Never raises.

    Order matters: entity rules read ``matched_entity_ids``, which are on the
    row from the first persist, so the rules see the same names the user
    sees. A link failure or timeout is logged and alert rules still run.
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
