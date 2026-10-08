"""
Licence plates of KNOWN vehicles: storage, live matching, and the vehicle signal.

How a plate takes part in a vehicle decision
--------------------------------------------
1. ``object_identity_service`` reads plates on each detected vehicle crop
   (``plate_reader.read_vehicle_plates``) and keeps only keyed hashes on the
   observation (``VehicleObservation.plate_reads``).
2. ``resolve_plate_evidence`` (pre-AI, right after the analysis) compares
   those hashes with the saved ones and replaces them with a
   ``PlateEvidence``: which saved vehicles the reads matched and whether a
   confident read was made. The hashes themselves are dropped there, so a
   plate that matches no saved vehicle is gone before the vision call.
3. ``PlateSignal`` (a ``VehicleSignal`` for ``evaluate_vehicle_candidates``)
   turns the evidence into a verdict per saved vehicle:

   * ``agree`` (tier 4, above crop+description): a moving vehicle's plate
     matches one saved on this vehicle;
   * ``contradict``: the only moving vehicle has a confident read of another
     plate (``PLATE_VETO_ENABLED``), or this vehicle's plate is read on a
     parked car while nothing moving matches it;
   * ``none``: no read, or the vehicle has no saved plate.

   The built-in vetoes (description, parked, colour) still apply to an
   ``agree``, and any error counts as ``none``.

Storage is in ``entity_plates`` (see the model): keyed hashes only, only on
saved vehicles, added by a user action (typing the plate, or assigning an
event whose crop shows a confidently read plate).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.services import plate_reader as pr

logger = logging.getLogger(__name__)

PLATE_SIGNAL_NAME = "plate"
PLATE_SIGNAL_TIER = 4
# A read used to veto, or saved from an event, must be at least this long.
STRICT_MIN_LENGTH = 5
ENROLL_READ_TIMEOUT_S = 5.0


def _settings():
    from app.core.config import settings

    return settings


def _strict_confidence() -> float:
    return float(getattr(_settings(), "PLATE_STRICT_CONFIDENCE", 0.85))


def _min_confidence() -> float:
    return float(getattr(_settings(), "PLATE_MIN_CONFIDENCE", 0.5))


# ---------------------------------------------------------------------------
# Known-plate index (in memory; hashes of saved vehicles only)
# ---------------------------------------------------------------------------

@dataclass
class PlateIndex:
    by_hash: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    entities: FrozenSet[str] = frozenset()
    stale: int = 0  # rows made with another salt (cannot match)
    loaded_at: float = 0.0


def load_plate_index(db: Session) -> PlateIndex:
    from app.models.entity_plate import EntityPlate
    from app.models.recognized_entity import RecognizedEntity

    current = pr.key_id()
    rows = (
        db.query(EntityPlate.entity_id, EntityPlate.plate_hash, EntityPlate.key_id)
        .join(RecognizedEntity, RecognizedEntity.id == EntityPlate.entity_id)
        .filter(RecognizedEntity.entity_type == "vehicle")
        .all()
    )
    by_hash: Dict[str, set] = {}
    entities = set()
    stale = 0
    for entity_id, plate_hash, row_key in rows:
        if current is None or row_key != current:
            stale += 1
            continue
        by_hash.setdefault(plate_hash, set()).add(entity_id)
        entities.add(entity_id)
    return PlateIndex(
        by_hash={h: frozenset(ids) for h, ids in by_hash.items()},
        entities=frozenset(entities),
        stale=stale,
        loaded_at=time.monotonic(),
    )


class _IndexCache:
    TTL_S = 300.0

    def __init__(self):
        self._index: Optional[PlateIndex] = None
        self._lock = threading.Lock()

    def get(self, db: Session) -> PlateIndex:
        with self._lock:
            cached = self._index
        if cached is not None and time.monotonic() - cached.loaded_at < self.TTL_S:
            return cached
        index = load_plate_index(db)
        with self._lock:
            self._index = index
        return index

    def invalidate(self) -> None:
        with self._lock:
            self._index = None


_cache = _IndexCache()


def get_plate_index(db: Session) -> PlateIndex:
    return _cache.get(db)


def invalidate_plate_index() -> None:
    _cache.invalidate()


# ---------------------------------------------------------------------------
# Live evidence
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlateEvidence:
    """What the plate reads on one vehicle crop say, without any hash."""

    matched_entity_ids: FrozenSet[str] = frozenset()
    confident_read: bool = False  # a strict-confidence read was made
    entities_with_plates: FrozenSet[str] = frozenset()


def resolve_plate_evidence(db: Session, analysis: Any) -> int:
    """Swap each vehicle's plate hashes for ``PlateEvidence``. Never raises.

    Returns how many vehicles matched a saved plate. Every hash is removed
    from the observations here, matched or not.
    """
    vehicles = list(getattr(analysis, "vehicles", None) or [])
    pending = [v for v in vehicles if getattr(v, "plate_reads", None)]
    if not pending:
        return 0
    matched_count = 0
    try:
        index = get_plate_index(db)
        min_conf, strict = _min_confidence(), _strict_confidence()
        for obs in pending:
            matched = set()
            confident = False
            for read in obs.plate_reads:
                if read.confidence >= min_conf:
                    matched |= index.by_hash.get(read.plate_hash, frozenset())
                if read.confidence >= strict and read.length >= STRICT_MIN_LENGTH:
                    confident = True
            obs.plate_evidence = PlateEvidence(frozenset(matched), confident, index.entities)
            matched_count += 1 if matched else 0
        logger.info(
            "Plate reads compared with saved vehicles",
            extra={
                "event_type": "plate_evidence",
                "vehicles_with_reads": len(pending),
                "vehicles_matched": matched_count,
            },
        )
    except Exception as exc:  # noqa: BLE001 - plates are optional evidence
        logger.debug("Plate evidence failed open", extra={"event_type": "plate_evidence_failed", "error_type": type(exc).__name__})
    finally:
        for obs in pending:
            obs.plate_reads = []
    return matched_count


class PlateSignal:
    """``VehicleSignal`` backed by ``PlateEvidence`` on the observations."""

    name = PLATE_SIGNAL_NAME
    tier = PLATE_SIGNAL_TIER

    def __init__(self, veto: Optional[bool] = None):
        self._veto = veto

    def _veto_enabled(self) -> bool:
        if self._veto is not None:
            return self._veto
        return bool(getattr(_settings(), "PLATE_VETO_ENABLED", True))

    def evaluate(self, identity: Any, observations: Sequence[Any], description: Optional[str]):
        from app.services.entity_gallery_service import SignalVerdict

        entity_id = getattr(identity, "entity_id", None)
        present = [o for o in observations or [] if o is not None]
        moving = [o for o in present if not getattr(o, "stationary", False)]
        parked = [o for o in present if getattr(o, "stationary", False)]
        evidence = [getattr(o, "plate_evidence", None) for o in moving]
        if any(e is not None and entity_id in e.matched_entity_ids for e in evidence):
            return SignalVerdict("agree", 1.0)
        known = next((e.entities_with_plates for e in (getattr(o, "plate_evidence", None) for o in present) if e), frozenset())
        if entity_id not in known:
            return SignalVerdict()
        if any(
            (e := getattr(o, "plate_evidence", None)) is not None and entity_id in e.matched_entity_ids
            for o in parked
        ):
            # Its plate is on a parked car; the event is about something else.
            return SignalVerdict("contradict")
        if self._veto_enabled() and len(moving) == 1 and evidence[0] is not None and evidence[0].confident_read:
            return SignalVerdict("contradict")
        return SignalVerdict()


def install_plate_signal() -> bool:
    """Register ``PlateSignal`` when plate matching is enabled. Returns whether it did."""
    from app.services.entity_gallery_service import register_vehicle_signal, unregister_vehicle_signal

    if not pr.plates_enabled():
        unregister_vehicle_signal(PLATE_SIGNAL_NAME)
        return False
    register_vehicle_signal(PlateSignal())
    pr.get_plate_reader().ensure_loading()
    logger.info("Plate matching enabled for saved vehicles", extra={"event_type": "plate_signal_installed"})
    return True


# ---------------------------------------------------------------------------
# Storage: add / list / remove / move
# ---------------------------------------------------------------------------

@dataclass
class PlateEnrollResult:
    status: str  # enrolled | already_enrolled | invalid | disabled | not_vehicle | no_read | low_confidence | unavailable | error
    plate: Any = None
    message: str = ""


def plate_to_dict(row) -> dict:
    current = pr.key_id()
    return {
        "id": row.id,
        "entity_id": row.entity_id,
        "source": row.source,
        "source_event_id": row.source_event_id,
        "usable": current is not None and row.key_id == current,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _store_hash(db: Session, entity, plate_hash: str, *, source: str, event_id: Optional[str]) -> PlateEnrollResult:
    from app.models.entity_plate import EntityPlate

    existing = db.query(EntityPlate).filter(
        EntityPlate.entity_id == entity.id, EntityPlate.plate_hash == plate_hash
    ).first()
    if existing is not None:
        return PlateEnrollResult("already_enrolled", existing)
    row = EntityPlate(
        id=str(uuid.uuid4()),
        entity_id=entity.id,
        plate_hash=plate_hash,
        hash_version=pr.HASH_VERSION,
        key_id=pr.key_id() or "",
        source=source,
        source_event_id=event_id,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    invalidate_plate_index()
    logger.info(
        "Plate saved on a vehicle",
        extra={"event_type": "entity_plate_saved", "entity_id": entity.id, "source": source},
    )
    return PlateEnrollResult("enrolled", row)


def set_plate(db: Session, entity, plate_text: str) -> PlateEnrollResult:
    """Save a user-typed plate on a vehicle, hashed at once. Commits.

    Works whenever a salt is configured, even with live reading off, so
    plates can be saved before the feature is switched on.
    """
    if getattr(entity, "entity_type", None) != "vehicle":
        return PlateEnrollResult("not_vehicle", message="Plates can only be saved on vehicles")
    key = pr.hash_key()
    if key is None:
        return PlateEnrollResult("disabled", message="Plate matching is not configured (PLATE_HASH_SALT)")
    digest = pr.hash_plate(plate_text, key)
    if digest is None:
        return PlateEnrollResult("invalid", message="A plate is 2-10 letters or digits")
    return _store_hash(db, entity, digest, source="manual", event_id=None)


def _read_best(image_bytes: bytes, key: bytes) -> Optional[pr.PlateRead]:
    from app.services.object_identity_service import decode_image

    reader = pr.get_plate_reader()
    if not reader.load():
        return None
    image = decode_image(image_bytes)
    if image is None:
        return None
    reads = reader.read(image, key, min_length=STRICT_MIN_LENGTH)
    return max(reads, key=lambda r: r.confidence) if reads else None


async def enroll_plate_from_crop(db: Session, entity, crop_bytes: Optional[bytes], event_id: str) -> PlateEnrollResult:
    """Save the plate read on an assigned event's vehicle crop. Never raises.

    Only a strict-confidence read is saved: a misread saved here would veto
    the right car later. Nothing is stored when no plate is read.
    """
    try:
        if getattr(entity, "entity_type", None) != "vehicle":
            return PlateEnrollResult("not_vehicle")
        if not pr.plates_enabled():
            return PlateEnrollResult("disabled")
        if not crop_bytes:
            return PlateEnrollResult("no_read")
        key = pr.hash_key()
        loop = asyncio.get_running_loop()
        read = await asyncio.wait_for(
            loop.run_in_executor(None, _read_best, crop_bytes, key), ENROLL_READ_TIMEOUT_S
        )
        if pr.get_plate_reader().state == "unavailable":
            return PlateEnrollResult("unavailable")
        if read is None:
            return PlateEnrollResult("no_read")
        if read.confidence < _strict_confidence():
            return PlateEnrollResult("low_confidence")
        return _store_hash(db, entity, read.plate_hash, source="event", event_id=event_id)
    except Exception as exc:  # noqa: BLE001 - the gallery enrollment already succeeded
        db.rollback()
        logger.info(
            "Plate enrollment failed open",
            extra={"event_type": "entity_plate_enroll_failed", "error_type": type(exc).__name__},
        )
        return PlateEnrollResult("error")


def list_plates(db: Session, entity_id: str) -> List[Any]:
    from app.models.entity_plate import EntityPlate

    return (
        db.query(EntityPlate)
        .filter(EntityPlate.entity_id == entity_id)
        .order_by(EntityPlate.created_at.desc())
        .all()
    )


def remove_plate(db: Session, entity_id: str, plate_id: str) -> bool:
    from app.models.entity_plate import EntityPlate

    row = db.query(EntityPlate).filter(EntityPlate.entity_id == entity_id, EntityPlate.id == plate_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    invalidate_plate_index()
    return True


def clear_plates(db: Session, entity_id: Optional[str] = None) -> int:
    """Delete one vehicle's plates, or every saved plate (``entity_id=None``). Commits."""
    from app.models.entity_plate import EntityPlate

    q = db.query(EntityPlate)
    if entity_id is not None:
        q = q.filter(EntityPlate.entity_id == entity_id)
    count = q.delete(synchronize_session=False)
    db.commit()
    invalidate_plate_index()
    return int(count or 0)


def unenroll_event_plates(db: Session, entity_id: str, event_id: str) -> int:
    """Drop plates a vehicle learned from this event (a corrected link). Commits."""
    from app.models.entity_plate import EntityPlate

    count = db.query(EntityPlate).filter(
        EntityPlate.entity_id == entity_id,
        EntityPlate.source_event_id == event_id,
        EntityPlate.source == "event",
    ).delete(synchronize_session=False)
    db.commit()
    if count:
        invalidate_plate_index()
    return int(count or 0)


def move_plates(db: Session, from_entity_id: str, to_entity_id: str) -> int:
    """Re-own plates on an entity merge (duplicates dropped). Does not commit."""
    from app.models.entity_plate import EntityPlate

    taken = {
        h for (h,) in db.query(EntityPlate.plate_hash).filter(EntityPlate.entity_id == to_entity_id).all()
    }
    moved = 0
    for row in db.query(EntityPlate).filter(EntityPlate.entity_id == from_entity_id).all():
        if row.plate_hash in taken:
            db.delete(row)
            continue
        row.entity_id = to_entity_id
        taken.add(row.plate_hash)
        moved += 1
    invalidate_plate_index()
    return moved


def plate_status(db: Session) -> dict:
    """Feature state for the API (no hashes, no plates)."""
    from app.models.entity_plate import EntityPlate

    index = load_plate_index(db)
    return {
        "enabled": bool(getattr(_settings(), "PLATE_RECOGNITION_ENABLED", False)),
        "salt_configured": pr.hash_key() is not None,
        "active": pr.plates_enabled(),
        "model_state": pr.get_plate_reader().state,
        "veto_enabled": bool(getattr(_settings(), "PLATE_VETO_ENABLED", True)),
        "vehicles_with_plates": len(index.entities),
        "saved_plates": db.query(EntityPlate.id).count(),
        "unusable_plates": index.stale,
    }
