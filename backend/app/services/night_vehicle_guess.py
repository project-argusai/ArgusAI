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
# Weaker signal when the last same-cam sighting had unclear direction
# (cannot_tell / other). Combined with hour or trait agreement can still
# reach MIN_SCORE.
LAST_SEEN_AMBIGUOUS_WEIGHT = 1.0
ARRIVAL_HOUR_WEIGHT = 1.0
TRAITS_AGREE_WEIGHT = 1.0
ARRIVAL_HOUR_WINDOW = 1  # +/- hours
MIN_ARRIVALS_FOR_PATTERN = 2

_APPROACH_ACTION_MARKERS = (
    "approach",
    "arriv",
    "enter",
    "pull in",
    "pulling in",
    "pulls in",
    "toward",
    "coming in",
    "coming home",
)


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
    """Classify a free-text or schema direction value.

    Schema values are toward camera / away / left / right / cannot_tell.
    ``left`` and ``going left`` are treated as departure: the model often
    writes ``left`` for "left the scene", and ``"leav" not in "left"`` used
    to leave those as ``other``. Lateral ``right`` stays ``other``.
    """
    text = (direction or "").strip().lower()
    if not text or text in ("cannot_tell", "unknown"):
        return "other"
    # Exact / phrase match before substring checks so "left" counts.
    if text == "left" or "going left" in text:
        return "departure"
    if "away" in text or "leav" in text or "depart" in text or "exit" in text:
        return "departure"
    if "toward" in text or "arriv" in text or "approach" in text or "enter" in text:
        return "arrival"
    return "other"


def action_indicates_approach(action: Optional[str]) -> bool:
    """True when the action text suggests approaching / arriving."""
    text = (action or "").strip().lower()
    if not text or text in ("cannot_tell", "unknown"):
        return False
    return any(marker in text for marker in _APPROACH_ACTION_MARKERS)


def _log_guess_skip(event_id: str, reason: str) -> None:
    """Debug-only skip log. reason is a short code; never names or PII."""
    logger.debug(
        "Night vehicle guess skipped",
        extra={
            "event_type": "night_vehicle_guess_skipped",
            "event_id": event_id,
            "reason": reason,
        },
    )


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
            age = event_time - _aware(last.when)
            if age <= lookback:
                hours = age.total_seconds() / 3600.0
                # last is the newest same-cam sighting before this event, so
                # there is no later arrival on this camera by construction.
                if last.direction == "departure":
                    cand.score += DEPARTURE_WEIGHT
                    cand.basis.append(f"left {hours:.0f}h earlier and not seen returning")
                elif last.direction == "other":
                    cand.score += LAST_SEEN_AMBIGUOUS_WEIGHT
                    cand.basis.append(
                        f"last seen {hours:.0f}h earlier (direction unclear) and not seen returning"
                    )
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


def pick_guess_skip_reason(candidates: Sequence[Candidate]) -> str:
    """Why pick_guess returned None: ``score`` (too low / empty) or ``tie``."""
    if not candidates or candidates[0].score < MIN_SCORE:
        return "score"
    if len(candidates) > 1 and candidates[1].score == candidates[0].score:
        return "tie"
    return "score"


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
    """True when the event is eligible for a night context guess.

    Soft departure gate: skip only when direction is clearly leaving *and*
    the action does not indicate approaching / arrival. ``cannot_tell`` and
    other unclear directions stay eligible.
    """
    return night_arrival_skip_reason(event, identification, config) is None


def night_arrival_skip_reason(
    event: Any, identification: Optional[Dict[str, Any]], config: GuessConfig
) -> Optional[str]:
    """Return a short skip code, or None when the event may be scored.

    Codes used here: ``departure`` (clear leave without approach action).
    Other gates (vehicle type, identity, night) return ``score``-adjacent
    reasons only from suggest_for_event; this helper returns ``None`` when
    the event is simply not a night unidentified vehicle candidate without
    a named skip code callers care about, except ``departure``.
    """
    from app.services.night_vision import identification_is_night, is_night_hour

    ident = identification or {}
    object_type = ident.get("object_type")
    smart = (getattr(event, "smart_detection_type", None) or "").lower()
    if object_type != "vehicle" and not (smart == "vehicle" and object_type in (None, "unknown")):
        return "score"
    identity = str(ident.get("identity") or "unknown").strip().lower()
    if identity not in ("unknown", "cannot_tell", ""):
        return "score"
    if direction_kind(ident.get("direction")) == "departure":
        if not action_indicates_approach(ident.get("action")):
            return "departure"
    when = getattr(event, "timestamp", None)
    night = identification_is_night(ident) or (
        isinstance(when, datetime)
        and is_night_hour(_aware(when), config.night_start_hour, config.night_end_hour)
    )
    if not night:
        return "score"
    return None


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


def _already_linked(db: Session, event: Any, event_id: str) -> bool:
    from app.models.recognized_entity import EntityEvent

    if (event.matched_entity_ids or "").strip() not in ("", "[]"):
        return True
    return db.query(EntityEvent).filter(EntityEvent.event_id == event_id).first() is not None


def suggest_for_event(db: Session, event_id: str, config: Optional[GuessConfig] = None) -> Optional[Dict[str, Any]]:
    """Store a likely-vehicle guess on an unidentified night arrival.

    Returns the stored payload, or None when nothing was stored. Only the
    event's identification JSON is written. Skip reasons are debug-logged
    as ``night_vehicle_guess_skipped`` with a short ``reason`` code and no
    names or description text.
    """
    from app.models.event import Event
    from app.models.recognized_entity import RecognizedEntity
    from app.services.identification import loads_identification

    config = config or GuessConfig.from_settings()
    if not config.enabled:
        _log_guess_skip(event_id, "disabled")
        return None
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None or not isinstance(event.timestamp, datetime):
        _log_guess_skip(event_id, "score")
        return None
    ident = loads_identification(event.identification)
    gate_reason = night_arrival_skip_reason(event, ident, config)
    if gate_reason is not None:
        _log_guess_skip(event_id, gate_reason)
        return None
    if _already_linked(db, event, event_id):
        _log_guess_skip(event_id, "already_linked")
        return None
    vehicles = (
        db.query(RecognizedEntity)
        .filter(RecognizedEntity.entity_type == "vehicle", RecognizedEntity.name.isnot(None))
        .all()
    )
    vehicles = [v for v in vehicles if (v.name or "").strip()]
    if not vehicles:
        _log_guess_skip(event_id, "score")
        return None
    since = _aware(event.timestamp).astimezone(timezone.utc) - timedelta(days=config.history_days)
    sightings = _load_sightings(db, [v.id for v in vehicles], since.replace(tzinfo=None))
    candidates = score_candidates(
        event_time=event.timestamp,
        camera_id=event.camera_id,
        identification=ident,
        vehicles=vehicles,
        sightings=sightings,
        config=config,
    )
    choice = pick_guess(candidates)
    if choice is None:
        _log_guess_skip(event_id, pick_guess_skip_reason(candidates))
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
