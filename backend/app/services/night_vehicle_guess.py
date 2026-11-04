"""Context guess for unidentified night vehicle arrivals.

When a vehicle arrives after dark and nothing identifies it, suggest the
most likely saved household vehicle from two soft signals:

* it left on the same camera within ``NIGHT_VEHICLE_GUESS_LOOKBACK_HOURS``
  and has not been seen arriving since, and
* it usually arrives around this hour (linked arrivals over
  ``NIGHT_VEHICLE_GUESS_HISTORY_DAYS``).

A vehicle whose stored traits contradict the frame (for example a reported
split-headlight pattern against a saved full-width light bar) is excluded;
agreeing traits add a little support.

The result is stored only as ``identification["likely_vehicle"]`` with
``is_guess: true`` and the label "likely <name> (guess)". It is never an
entity link, never sets ``matched_entity_ids``, and runs after alert rules,
so it cannot trigger an alert or count as a sighting. Never logs names or
description text.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, ContextManager, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MIN_SCORE = 2.0
DEPARTURE_WEIGHT = 2.0
ARRIVAL_HOUR_WEIGHT = 1.0
TRAITS_AGREE_WEIGHT = 1.0
ARRIVAL_HOUR_WINDOW = 1  # +/- hours
MIN_ARRIVALS_FOR_PATTERN = 2


@dataclass(frozen=True)
class GuessConfig:
    enabled: bool = True
    lookback_hours: int = 18
    history_days: int = 30
    night_start_hour: int = 18
    night_end_hour: int = 7

    @classmethod
    def from_settings(cls) -> "GuessConfig":
        from app.core.config import settings

        return cls(
            enabled=bool(getattr(settings, "NIGHT_VEHICLE_GUESS_ENABLED", True)),
            lookback_hours=int(getattr(settings, "NIGHT_VEHICLE_GUESS_LOOKBACK_HOURS", 18)),
            history_days=int(getattr(settings, "NIGHT_VEHICLE_GUESS_HISTORY_DAYS", 30)),
            night_start_hour=int(getattr(settings, "NIGHT_VEHICLE_NIGHT_START_HOUR", 18)),
            night_end_hour=int(getattr(settings, "NIGHT_VEHICLE_NIGHT_END_HOUR", 7)),
        )


@dataclass
class Sighting:
    """One linked event of a saved vehicle (what the guess reads)."""

    entity_id: str
    camera_id: str
    when: datetime
    direction: str  # "arrival", "departure" or "other"


@dataclass
class Candidate:
    entity: Any
    score: float = 0.0
    basis: List[str] = field(default_factory=list)


def direction_kind(direction: Optional[str]) -> str:
    text = (direction or "").strip().lower()
    if not text or text in ("cannot_tell", "unknown"):
        return "other"
    if "away" in text or "leav" in text or "depart" in text or "exit" in text:
        return "departure"
    if "toward" in text or "arriv" in text or "approach" in text or "enter" in text:
        return "arrival"
    return "other"


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)


def _local_hour(when: datetime) -> int:
    return _aware(when).astimezone().hour


def _hour_distance(a: int, b: int) -> int:
    d = abs(a - b) % 24
    return min(d, 24 - d)


def score_candidates(
    *,
    event_time: datetime,
    camera_id: str,
    identification: Optional[Dict[str, Any]],
    vehicles: Sequence[Any],
    sightings: Sequence[Sighting],
    config: GuessConfig,
) -> List[Candidate]:
    """Pure scoring. Returns candidates with a positive score, best first."""
    from app.services.entity_alert_service import vehicle_traits_signal

    event_time = _aware(event_time)
    event_hour = _local_hour(event_time)
    lookback = timedelta(hours=config.lookback_hours)
    by_entity: Dict[str, List[Sighting]] = {}
    for s in sightings:
        by_entity.setdefault(s.entity_id, []).append(s)

    out: List[Candidate] = []
    for vehicle in vehicles:
        entity_id = getattr(vehicle, "id", None)
        if not entity_id or getattr(vehicle, "is_blocked", False):
            continue
        signal = vehicle_traits_signal(vehicle, identification)
        if signal == "contradict":
            continue
        cand = Candidate(entity=vehicle)
        past = sorted(
            (s for s in by_entity.get(entity_id, []) if _aware(s.when) < event_time),
            key=lambda s: _aware(s.when),
        )
        same_camera = [s for s in past if s.camera_id == camera_id]
        if same_camera:
            last = same_camera[-1]
            if last.direction == "departure" and event_time - _aware(last.when) <= lookback:
                hours = (event_time - _aware(last.when)).total_seconds() / 3600.0
                cand.score += DEPARTURE_WEIGHT
                cand.basis.append(f"left {hours:.0f}h earlier and not seen returning")
        arrivals = [
            s for s in past
            if s.direction == "arrival"
            and event_time - _aware(s.when) <= timedelta(days=config.history_days)
        ]
        near = [s for s in arrivals if _hour_distance(_local_hour(s.when), event_hour) <= ARRIVAL_HOUR_WINDOW]
        if len(near) >= MIN_ARRIVALS_FOR_PATTERN:
            cand.score += ARRIVAL_HOUR_WEIGHT
            cand.basis.append(f"usually arrives around this time ({len(near)} recent arrivals)")
        if signal == "agree" and cand.score > 0:
            cand.score += TRAITS_AGREE_WEIGHT
            cand.basis.append("lighting / front traits match")
        if cand.score > 0:
            out.append(cand)
    out.sort(key=lambda c: c.score, reverse=True)
    return out


def pick_guess(candidates: Sequence[Candidate]) -> Optional[Candidate]:
    """The single best candidate at or above MIN_SCORE; None on a tie."""
    if not candidates or candidates[0].score < MIN_SCORE:
        return None
    if len(candidates) > 1 and candidates[1].score == candidates[0].score:
        return None
    return candidates[0]


def guess_payload(candidate: Candidate) -> Dict[str, Any]:
    name = str(getattr(candidate.entity, "name", "") or "").strip()
    return {
        "entity_id": str(candidate.entity.id),
        "name": name,
        "label": f"likely {name} (guess)",
        "basis": list(candidate.basis),
        "score": round(candidate.score, 2),
        "is_guess": True,
    }


def is_unidentified_night_arrival(event: Any, identification: Optional[Dict[str, Any]], config: GuessConfig) -> bool:
    from app.services.night_vision import identification_is_night, is_night_hour

    ident = identification or {}
    object_type = ident.get("object_type")
    smart = (getattr(event, "smart_detection_type", None) or "").lower()
    if object_type != "vehicle" and not (smart == "vehicle" and object_type in (None, "unknown")):
        return False
    identity = str(ident.get("identity") or "unknown").strip().lower()
    if identity not in ("unknown", "cannot_tell", ""):
        return False
    if direction_kind(ident.get("direction")) == "departure":
        return False
    when = getattr(event, "timestamp", None)
    night = identification_is_night(ident) or (
        isinstance(when, datetime)
        and is_night_hour(_aware(when), config.night_start_hour, config.night_end_hour)
    )
    return bool(night)


def _load_sightings(db: Session, entity_ids: Sequence[str], since: datetime) -> List[Sighting]:
    from app.models.event import Event
    from app.models.recognized_entity import EntityEvent
    from app.services.identification import loads_identification

    if not entity_ids:
        return []
    rows = (
        db.query(EntityEvent.entity_id, Event.camera_id, Event.timestamp, Event.identification)
        .join(Event, Event.id == EntityEvent.event_id)
        .filter(EntityEvent.entity_id.in_(list(entity_ids)), Event.timestamp >= since)
        .all()
    )
    out = []
    for entity_id, camera_id, when, raw in rows:
        ident = loads_identification(raw) or {}
        out.append(Sighting(entity_id, camera_id, when, direction_kind(ident.get("direction"))))
    return out


def suggest_for_event(db: Session, event_id: str, config: Optional[GuessConfig] = None) -> Optional[Dict[str, Any]]:
    """Store a likely-vehicle guess on an unidentified night arrival.

    Returns the stored payload, or None when nothing was stored. Only the
    event's identification JSON is written.
    """
    from app.models.event import Event
    from app.models.recognized_entity import EntityEvent, RecognizedEntity
    from app.services.identification import loads_identification

    config = config or GuessConfig.from_settings()
    if not config.enabled:
        return None
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None or not isinstance(event.timestamp, datetime):
        return None
    ident = loads_identification(event.identification)
    if not is_unidentified_night_arrival(event, ident, config):
        return None
    if (event.matched_entity_ids or "").strip() not in ("", "[]"):
        return None
    if db.query(EntityEvent).filter(EntityEvent.event_id == event_id).first() is not None:
        return None
    vehicles = (
        db.query(RecognizedEntity)
        .filter(RecognizedEntity.entity_type == "vehicle", RecognizedEntity.name.isnot(None))
        .all()
    )
    vehicles = [v for v in vehicles if (v.name or "").strip()]
    if not vehicles:
        return None
    since = _aware(event.timestamp).astimezone(timezone.utc) - timedelta(days=config.history_days)
    sightings = _load_sightings(db, [v.id for v in vehicles], since.replace(tzinfo=None))
    choice = pick_guess(
        score_candidates(
            event_time=event.timestamp,
            camera_id=event.camera_id,
            identification=ident,
            vehicles=vehicles,
            sightings=sightings,
            config=config,
        )
    )
    if choice is None:
        return None
    payload = guess_payload(choice)
    try:
        stored = json.loads(event.identification) if event.identification else {}
    except (TypeError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    stored["likely_vehicle"] = payload
    event.identification = json.dumps(stored)
    db.commit()
    logger.info(
        "Stored a likely-vehicle guess for a night arrival",
        extra={"event_type": "night_vehicle_guess_stored", "event_id": event_id, "score": payload["score"]},
    )
    return payload


async def suggest_likely_vehicle(event_id: str, session_factory: Callable[[], ContextManager[Session]]) -> Optional[Dict[str, Any]]:
    with session_factory() as db:
        return suggest_for_event(db, event_id)
