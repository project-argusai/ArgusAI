"""
Per-entity reference galleries, crop storage, enrollment, and matching rules.

Data model
----------
* ``face_embeddings`` / ``vehicle_embeddings``: per-event *observations*.
  Every live event with a usable face or vehicle gets rows here (embedding,
  box, small crop JPEG). ``entity_id`` stays NULL: an observation is never a
  reference by itself. Rows go away with their event.
* ``entity_gallery_items``: confirmed references, owned by the entity. An
  item is created only by an explicit user action: assigning an event to an
  entity, or "use as reference". Automatic matches never add items, so a
  wrong match cannot drift a reference.

Matching (see ``match_face`` and ``decide_vehicle_links``)
----------------------------------------------------------
* Faces: SFace cosine, max over the person's gallery. A match needs
  ``FACE_MATCH_THRESHOLD`` and must beat the next person by
  ``FACE_MATCH_MARGIN``.
* Vehicles: CLIP cosine of the detected crop, max over the vehicle's gallery,
  combined with a crop colour check and the description make check (#679).
  See ``decide_vehicle_links`` for the exact rule.

Every threshold can be tuned with an env var without a code change.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

import numpy as np
from sqlalchemy.orm import Session

from app.core.decorators import singleton
from app.services.ai_types import FACE_RECOGNITION_ENABLED, VEHICLE_RECOGNITION_ENABLED
from app.services.face_recognition_service import active_face_model, normalize
from app.services.object_identity_service import (
    VEHICLE_CROP_MODEL_VERSION,
    ObjectAnalysis,
)
from app.services.vehicle_color import color_agreement, normalize_color_name

logger = logging.getLogger(__name__)

FACE = "face"
VEHICLE = "vehicle"
VEHICLE_CROP_DIM = 512


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring non-numeric %s", name)
        return default
    return value if -1.0 <= value <= 1.0 else default


@dataclass(frozen=True)
class MatchThresholds:
    # SFace: OpenCV's published cosine threshold is 0.363 (LFW). We start a
    # little stricter, since a false name on a doorbell alert is worse than
    # a missed one, and require a margin over the next person. ``from_env``
    # takes the active face backend's ``default_match_threshold``.
    face_match: float = 0.40
    face_margin: float = 0.05
    # CLIP B/32 crop vs crop. "strong" may link with colour alone (no
    # description); "support" needs the description to name the make too.
    vehicle_strong: float = 0.92
    vehicle_support: float = 0.80
    vehicle_margin: float = 0.03

    @classmethod
    def from_env(cls) -> "MatchThresholds":
        d = cls()
        face_default = d.face_match
        try:
            from app.services.face_recognition_service import get_face_recognition_service

            face_default = float(getattr(get_face_recognition_service(), "default_match_threshold", face_default))
        except Exception:  # noqa: BLE001
            pass
        return cls(
            face_match=_env_float("ARGUS_FACE_MATCH_THRESHOLD", face_default),
            face_margin=_env_float("ARGUS_FACE_MATCH_MARGIN", d.face_margin),
            vehicle_strong=_env_float("ARGUS_VEHICLE_CROP_STRONG", d.vehicle_strong),
            vehicle_support=_env_float("ARGUS_VEHICLE_CROP_SUPPORT", d.vehicle_support),
            vehicle_margin=_env_float("ARGUS_VEHICLE_CROP_MARGIN", d.vehicle_margin),
        )


# ---------------------------------------------------------------------------
# Crop storage
# ---------------------------------------------------------------------------

def crops_root() -> str:
    from app.core.config import settings

    configured = getattr(settings, "MEDIA_ENTITY_CROPS_DIR", None)
    if configured is not None and str(configured).strip():
        return os.path.abspath(str(configured).strip())
    backend = Path(__file__).resolve().parent.parent.parent
    return str(backend / "data" / "entity_crops")


def resolve_crop_path(relative: Optional[str]) -> Optional[str]:
    """Absolute path for a stored crop, or None if it escapes the crops root."""
    if not relative:
        return None
    from app.services.cleanup_service import _safe_join

    return _safe_join(crops_root(), relative)


def write_crop(relative: str, data: bytes) -> Optional[str]:
    target = resolve_crop_path(relative)
    if not target or not data:
        return None
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = f"{target}.part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, target)
    return relative


def read_crop(relative: Optional[str]) -> Optional[bytes]:
    target = resolve_crop_path(relative)
    if not target or not os.path.isfile(target):
        return None
    with open(target, "rb") as fh:
        return fh.read()


def delete_crop(relative: Optional[str]) -> bool:
    target = resolve_crop_path(relative)
    if not target or not os.path.isfile(target) or os.path.islink(target):
        return False
    try:
        os.remove(target)
        return True
    except OSError:
        return False


def _observation_rel(kind: str, when: datetime, row_id: str) -> str:
    return f"observations/{kind}/{when.strftime('%Y-%m-%d')}/{row_id}.jpg"


def _gallery_rel(entity_id: str, item_id: str) -> str:
    return f"gallery/{entity_id}/{item_id}.jpg"


# ---------------------------------------------------------------------------
# Gallery index (in-memory, per model version)
# ---------------------------------------------------------------------------

@dataclass
class GalleryEntry:
    entity_id: str
    name: str
    entity_type: str
    vectors: np.ndarray
    colors: List[Optional[str]] = field(default_factory=list)
    vehicle_color: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None

    def reference_color(self) -> Optional[str]:
        """Stored colour, else the majority colour of the enrolled crops."""
        stored = normalize_color_name(self.vehicle_color)
        if stored:
            return stored
        seen = [c for c in (normalize_color_name(c) for c in self.colors) if c]
        if not seen:
            return None
        best = max(set(seen), key=seen.count)
        return best if seen.count(best) * 2 > len(seen) else None


@dataclass
class GalleryIndex:
    faces: Dict[str, GalleryEntry] = field(default_factory=dict)
    vehicles: Dict[str, GalleryEntry] = field(default_factory=dict)
    loaded_at: float = 0.0


def _parse_vec(raw: Any, dim: int) -> Optional[np.ndarray]:
    try:
        values = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    if not isinstance(values, list) or len(values) != dim:
        return None
    return normalize(values)


def load_gallery_index(db: Session) -> GalleryIndex:
    """Named entities with at least one gallery item of the current model."""
    from app.models.entity_gallery_item import EntityGalleryItem
    from app.models.recognized_entity import RecognizedEntity

    face_version, face_dim = active_face_model()
    rows = (
        db.query(EntityGalleryItem, RecognizedEntity)
        .join(RecognizedEntity, RecognizedEntity.id == EntityGalleryItem.entity_id)
        .filter(
            ((EntityGalleryItem.kind == FACE) & (EntityGalleryItem.model_version == face_version))
            | (
                (EntityGalleryItem.kind == VEHICLE)
                & (EntityGalleryItem.model_version == VEHICLE_CROP_MODEL_VERSION)
            )
        )
        .all()
    )
    grouped: Dict[Tuple[str, str], dict] = {}
    for item, entity in rows:
        name = entity.name.strip() if isinstance(entity.name, str) else ""
        if not name:
            continue
        expected_type = "person" if item.kind == FACE else "vehicle"
        if entity.entity_type != expected_type:
            continue
        vec = _parse_vec(item.embedding, face_dim if item.kind == FACE else VEHICLE_CROP_DIM)
        if vec is None:
            continue
        slot = grouped.setdefault((item.kind, entity.id), {"entity": entity, "vecs": [], "colors": []})
        slot["vecs"].append(vec)
        slot["colors"].append(item.dominant_color)

    index = GalleryIndex(loaded_at=time.monotonic())
    for (kind, entity_id), slot in grouped.items():
        entity = slot["entity"]
        entry = GalleryEntry(
            entity_id=entity_id,
            name=entity.name.strip(),
            entity_type=entity.entity_type,
            vectors=np.vstack(slot["vecs"]),
            colors=slot["colors"],
            vehicle_color=getattr(entity, "vehicle_color", None),
            vehicle_make=getattr(entity, "vehicle_make", None),
            vehicle_model=getattr(entity, "vehicle_model", None),
        )
        (index.faces if kind == FACE else index.vehicles)[entity_id] = entry
    return index


# ---------------------------------------------------------------------------
# Matching rules (pure functions; unit-tested without models)
# ---------------------------------------------------------------------------

def gallery_score(entry: GalleryEntry, embedding: Optional[np.ndarray]) -> Optional[float]:
    """Max cosine between an L2-normalised embedding and the gallery."""
    if embedding is None or entry.vectors.size == 0:
        return None
    if entry.vectors.shape[1] != embedding.shape[0]:
        return None
    return float(np.max(entry.vectors @ embedding))


@dataclass
class FaceMatch:
    entity_id: str
    name: str
    score: float
    runner_up: Optional[float]
    face_index: int


def match_face(
    index: GalleryIndex,
    embeddings: Sequence[Optional[np.ndarray]],
    thresholds: Optional[MatchThresholds] = None,
) -> Optional[FaceMatch]:
    """Best confident person across the event's faces, or None.

    Per face: best person must reach ``face_match`` and beat the next person
    by ``face_margin``. Across faces the highest-scoring confident face wins
    (one named person per event, as before).
    """
    t = thresholds or MatchThresholds.from_env()
    best: Optional[FaceMatch] = None
    for i, emb in enumerate(embeddings):
        scored = sorted(
            (
                (s, entry)
                for entry in index.faces.values()
                if (s := gallery_score(entry, emb)) is not None
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        if not scored:
            continue
        top_score, top = scored[0]
        runner = scored[1][0] if len(scored) > 1 else None
        logger.debug(
            "Face gallery scores",
            extra={
                "event_type": "face_gallery_scores",
                "face_index": i,
                "scores": {e.entity_id: round(s, 4) for s, e in scored[:3]},
            },
        )
        if top_score < t.face_match:
            continue
        if runner is not None and top_score - runner < t.face_margin:
            continue
        if best is None or top_score > best.score:
            best = FaceMatch(top.entity_id, top.name, round(top_score, 4), runner, i)
    return best


@dataclass
class VehicleEvidence:
    entity_id: str
    name: str
    has_gallery: bool
    crop_score: Optional[float]
    color_status: str
    description_status: str
    accepted: bool = False
    signal: Optional[str] = None
    reason: str = ""
    parked_score: Optional[float] = None
    # Rank of the link (see ``_TIER`` / ``VehicleSignal.tier``) and the score
    # that orders links within a tier.
    tier: int = 0
    rank_score: Optional[float] = None
    # Verdicts of registered extra signals (e.g. a plate reader), by name.
    signals: Dict[str, str] = field(default_factory=dict)

    def as_log(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "crop_score": None if self.crop_score is None else round(self.crop_score, 4),
            "parked_score": None if self.parked_score is None else round(self.parked_score, 4),
            "color": self.color_status,
            "description": self.description_status,
            "accepted": self.accepted,
            "signal": self.signal,
            "reason": self.reason,
            **({"signals": dict(self.signals)} if self.signals else {}),
        }


# Built-in link kinds, strongest first. Extra signals declare their own tier.
_TIER = {"crop+description": 3, "crop+color": 2, "description": 1}


# ---------------------------------------------------------------------------
# Extra vehicle signals (extension point, e.g. a licence-plate reader)
# ---------------------------------------------------------------------------

@dataclass
class SignalVerdict:
    status: str = "none"  # agree | contradict | none
    score: Optional[float] = None


@runtime_checkable
class VehicleSignal(Protocol):
    """An extra, independent piece of evidence about one saved vehicle.

    ``evaluate`` sees the saved vehicle (``NamedIdentity``-like), the event's
    vehicle observations and the description, and answers:

    * ``contradict``: veto this vehicle (e.g. a different plate was read);
    * ``agree``: link it on this signal alone, ranked at ``tier``
      (``crop+description`` is 3; a confident plate read would sit above);
    * ``none``: no opinion (no plate visible).

    The built-in vetoes (description, parked, colour) still apply to an
    ``agree``. A signal that raises counts as ``none``.
    """

    name: str
    tier: int

    def evaluate(self, identity: Any, observations: Sequence[Any], description: Optional[str]) -> SignalVerdict: ...


_VEHICLE_SIGNALS: List[VehicleSignal] = []


def register_vehicle_signal(signal: VehicleSignal) -> None:
    """Add an extra signal to every vehicle decision (replaces one of the same name)."""
    _VEHICLE_SIGNALS[:] = [s for s in _VEHICLE_SIGNALS if s.name != signal.name] + [signal]


def unregister_vehicle_signal(name: str) -> None:
    _VEHICLE_SIGNALS[:] = [s for s in _VEHICLE_SIGNALS if s.name != name]


def registered_vehicle_signals() -> List[VehicleSignal]:
    return list(_VEHICLE_SIGNALS)


def _run_signal(signal: VehicleSignal, ident: Any, observations: Sequence[Any], description: Optional[str]) -> SignalVerdict:
    try:
        verdict = signal.evaluate(ident, observations, description)
    except Exception as exc:  # noqa: BLE001 - an extra signal must never break linking
        logger.debug(
            "Vehicle signal failed open",
            extra={"event_type": "vehicle_signal_failed", "signal": signal.name, "error_type": type(exc).__name__},
        )
        return SignalVerdict()
    if not isinstance(verdict, SignalVerdict) or verdict.status not in ("agree", "contradict", "none"):
        return SignalVerdict()
    return verdict


def _color_status_for(expected: Optional[str], colors: Iterable[Optional[str]]) -> str:
    statuses = [color_agreement(c, expected) for c in colors]
    if not statuses:
        return "unknown"
    if "agree" in statuses:
        return "agree"
    if all(s == "conflict" for s in statuses):
        return "conflict"
    return "unknown"


def evaluate_vehicle_candidates(
    description: Optional[str],
    identities: Sequence[Any],
    vehicles: Sequence[Any],
    gallery: Dict[str, GalleryEntry],
    thresholds: Optional[MatchThresholds] = None,
    extra_signals: Optional[Sequence[VehicleSignal]] = None,
) -> List[VehicleEvidence]:
    """Score each named vehicle against the event's evidence.

    ``identities``: named vehicle entities (``NamedIdentity``-like: entity_id,
    name, vehicle_color/make/model). ``vehicles``: the event's vehicle
    observations (``embedding``, ``color``). ``gallery``: vehicle galleries.

    The rule, per saved vehicle:

    1. Veto when the description contradicts it (other make/model/colour).
    2. Veto when the crop colour conflicts with its colour (red vs black).
       At night the colour is unknown and never vetoes.
    3. With an enrolled gallery and at least one detected vehicle crop:
       * crop score >= support and description shows its make
                                                  -> link ("crop+description")
       * crop score >= strong and colour agrees  -> link ("crop+color")
       * otherwise no link: the detected vehicle does not look like it.
    4. Without a gallery, or with no vehicle crop at all (detector miss or
       model missing): the #679 rule, description shows its make
       -> link ("description").

    Crops marked ``stationary`` (parked: same place and look as a recent
    observation on the camera) never count as evidence for a link. When a
    parked crop is the saved vehicle and nothing moving matches it, the
    vehicle is not linked at all ("parked_in_view"), which also blocks the
    description rule from naming a car that is just parked in the frame.

    ``extra_signals`` (default: ``registered_vehicle_signals()``) plug in
    more evidence, e.g. a plate reader: a ``contradict`` vetoes right after
    the description veto; an ``agree`` links at the signal's tier once the
    built-in vetoes have passed. None are registered by default.
    """
    from app.services.entity_alert_service import vehicle_description_signal, vehicle_label_agrees

    t = thresholds or MatchThresholds.from_env()
    present = [v for v in vehicles or [] if v is not None]
    observed = [v for v in present if not getattr(v, "stationary", False)]
    parked = [
        v for v in present
        if getattr(v, "stationary", False) and getattr(v, "embedding", None) is not None
    ]
    with_embedding = [v for v in observed if getattr(v, "embedding", None) is not None]
    extras = list(registered_vehicle_signals() if extra_signals is None else extra_signals)
    out: List[VehicleEvidence] = []
    for ident in identities:
        entry = gallery.get(ident.entity_id)
        has_gallery = entry is not None
        expected_color = (
            entry.reference_color() if entry is not None
            else normalize_color_name(getattr(ident, "vehicle_color", None))
        )
        crop_score = None
        best_obs = None
        if entry is not None:
            for obs in with_embedding:
                score = gallery_score(entry, obs.embedding)
                if score is not None and (crop_score is None or score > crop_score):
                    crop_score, best_obs = score, obs
        parked_score = None
        if entry is not None:
            for obs in parked:
                score = gallery_score(entry, obs.embedding)
                if score is not None and (parked_score is None or score > parked_score):
                    parked_score = score
        if best_obs is not None:
            color_status = color_agreement(best_obs.color, expected_color)
        else:
            color_status = _color_status_for(expected_color, [v.color for v in observed])
        desc = vehicle_description_signal(description, ident)
        ev = VehicleEvidence(
            entity_id=ident.entity_id,
            name=ident.name,
            has_gallery=has_gallery,
            crop_score=crop_score,
            color_status=color_status,
            description_status=desc,
            parked_score=parked_score,
        )
        verdicts = {sig.name: (sig, _run_signal(sig, ident, present, description)) for sig in extras}
        ev.signals = {name: v.status for name, (_, v) in verdicts.items()}
        contradicting = [name for name, (_, v) in verdicts.items() if v.status == "contradict"]
        agreeing = sorted(
            ((sig, v) for sig, v in verdicts.values() if v.status == "agree"),
            key=lambda sv: (sv[0].tier, sv[1].score or 0.0),
            reverse=True,
        )
        if desc == "contradict":
            ev.reason = "description_contradicts"
        elif contradicting:
            ev.reason = f"{contradicting[0]}_contradicts"
        elif (
            parked_score is not None
            and parked_score >= t.vehicle_support
            and (crop_score is None or crop_score < t.vehicle_support)
        ):
            # It is parked in view, and nothing moving looks like it: the
            # event is about something else, even if the description names it.
            ev.reason = "parked_in_view"
        elif color_status == "conflict":
            ev.reason = "color_conflict"
        elif agreeing:
            sig, verdict = agreeing[0]
            ev.accepted, ev.signal, ev.tier, ev.rank_score = True, sig.name, int(sig.tier), verdict.score
        elif has_gallery and with_embedding:
            if crop_score is not None and crop_score >= t.vehicle_support and desc == "agree":
                ev.accepted, ev.signal = True, "crop+description"
            elif crop_score is not None and crop_score >= t.vehicle_strong and color_status == "agree":
                ev.accepted, ev.signal = True, "crop+color"
            else:
                ev.reason = "crop_disagrees"
        elif desc == "agree" and vehicle_label_agrees(description or "", ident):
            # Description only: the #679 rule exactly (stricter than "agree").
            ev.accepted, ev.signal = True, "description"
        else:
            ev.reason = "no_signal"
        if ev.accepted and ev.signal in _TIER:
            ev.tier, ev.rank_score = _TIER[ev.signal], crop_score
        out.append(ev)
    return out


def pick_vehicle(
    evidence: Sequence[VehicleEvidence],
    thresholds: Optional[MatchThresholds] = None,
) -> Tuple[Optional[VehicleEvidence], List[VehicleEvidence]]:
    """(winner, description-tier candidates still tied). At most one winner.

    Crop-backed links outrank description-only ones. Two crop-backed links of
    the same tier closer than ``vehicle_margin`` are ambiguous: nothing is
    linked. Several description-only candidates are returned for the
    caller's existing tie-break (#679 ``select_named_vehicles``).
    """
    t = thresholds or MatchThresholds.from_env()
    accepted = [e for e in evidence if e.accepted]
    if not accepted:
        return None, []
    accepted.sort(key=lambda e: (e.tier, e.rank_score or 0.0), reverse=True)
    top = accepted[0]
    if top.signal == "description":
        tied = [e for e in accepted if e.signal == "description"]
        return (top, []) if len(tied) == 1 else (None, tied)
    same_tier = [e for e in accepted[1:] if e.tier == top.tier]
    if same_tier and (top.rank_score or 0.0) - (same_tier[0].rank_score or 0.0) < t.vehicle_margin:
        logger.info(
            "Two saved vehicles match the crop equally well; not linking either",
            extra={"event_type": "vehicle_crop_ambiguous", "candidates": [top.entity_id, same_tier[0].entity_id]},
        )
        return None, []
    return top, []


# ---------------------------------------------------------------------------
# Parked vehicles
# ---------------------------------------------------------------------------

PARKED_LOOKBACK_H = 72.0
PARKED_LOOKBACK_ROWS = 40
PARKED_IOU = 0.85
PARKED_COSINE = 0.95


def box_iou(a: Optional[dict], b: Optional[dict]) -> float:
    try:
        ax0, ay0, aw, ah = (float(a[k]) for k in ("x", "y", "width", "height"))
        bx0, by0, bw, bh = (float(b[k]) for k in ("x", "y", "width", "height"))
    except (TypeError, KeyError, ValueError):
        return 0.0
    ix = max(0.0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0.0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def mark_parked_vehicles(
    db: Session,
    camera_id: Optional[str],
    vehicles: Sequence[Any],
    *,
    now: Optional[datetime] = None,
    exclude_event_id: Optional[str] = None,
) -> int:
    """Flag crops that sit where a near-identical crop sat recently on this camera.

    A car parked in the driveway shows up in every event on that camera.
    Without this, its crop would match its own gallery on every passing
    delivery van. Compares against the camera's recent observations
    (box IoU >= ``PARKED_IOU`` and crop cosine >= ``PARKED_COSINE``).
    Sets ``stationary`` in place; returns how many were flagged.
    """
    from app.models.event import Event
    from app.models.vehicle_embedding import VehicleEmbedding

    pending = [v for v in vehicles or [] if getattr(v, "embedding", None) is not None]
    if not camera_id or not pending:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=PARKED_LOOKBACK_H)
    q = (
        db.query(VehicleEmbedding.embedding, VehicleEmbedding.bounding_box)
        .join(Event, Event.id == VehicleEmbedding.event_id)
        .filter(
            Event.camera_id == camera_id,
            Event.timestamp >= cutoff,
            VehicleEmbedding.model_version == VEHICLE_CROP_MODEL_VERSION,
        )
    )
    if exclude_event_id:
        q = q.filter(VehicleEmbedding.event_id != exclude_event_id)
    recent = []
    for raw_vec, raw_box in q.order_by(Event.timestamp.desc()).limit(PARKED_LOOKBACK_ROWS).all():
        vec = _parse_vec(raw_vec, VEHICLE_CROP_DIM)
        try:
            box = json.loads(raw_box) if raw_box else None
        except (TypeError, ValueError):
            box = None
        if vec is not None and box:
            recent.append((vec, box))
    flagged = 0
    for obs in pending:
        for vec, box in recent:
            if box_iou(obs.bbox, box) >= PARKED_IOU and float(vec @ obs.embedding) >= PARKED_COSINE:
                obs.stationary = True
                flagged += 1
                break
    return flagged


# ---------------------------------------------------------------------------
# Service: index cache, observation persistence, enrollment
# ---------------------------------------------------------------------------

@dataclass
class EnrollResult:
    status: str  # enrolled | already_enrolled | ambiguous | no_observation | disabled | unsupported
    items: List[Any] = field(default_factory=list)
    candidates: List[dict] = field(default_factory=list)
    message: str = ""


def _kind_for_entity(entity) -> Optional[str]:
    etype = getattr(entity, "entity_type", None)
    if etype == "person":
        return FACE
    if etype == "vehicle":
        return VEHICLE
    return None


def observation_to_dict(row, kind: str) -> dict:
    try:
        bbox = json.loads(row.bounding_box) if row.bounding_box else None
    except (TypeError, ValueError):
        bbox = None
    return {
        "id": row.id,
        "kind": kind,
        "event_id": row.event_id,
        "bounding_box": bbox,
        "confidence": row.confidence,
        "model_version": row.model_version,
        "dominant_color": getattr(row, "dominant_color", None),
        "vehicle_type": getattr(row, "vehicle_type", None),
        "has_crop": bool(row.crop_path),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def gallery_item_to_dict(item) -> dict:
    return {
        "id": item.id,
        "entity_id": item.entity_id,
        "kind": item.kind,
        "model_version": item.model_version,
        "dominant_color": item.dominant_color,
        "source_event_id": item.source_event_id,
        "source_observation_id": item.source_observation_id,
        "has_crop": bool(item.crop_path),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@singleton
class EntityGalleryService:
    INDEX_TTL_S = 300.0

    def __init__(self):
        self._index: Optional[GalleryIndex] = None
        self._lock = threading.Lock()

    # -- index -------------------------------------------------------------

    def invalidate(self) -> None:
        with self._lock:
            self._index = None

    def get_index(self, db: Session) -> GalleryIndex:
        with self._lock:
            cached = self._index
        if cached is not None and time.monotonic() - cached.loaded_at < self.INDEX_TTL_S:
            return cached
        index = load_gallery_index(db)
        with self._lock:
            self._index = index
        return index

    # -- observations ------------------------------------------------------

    def save_observations(
        self,
        db: Session,
        event_id: str,
        analysis: Optional[ObjectAnalysis],
        *,
        when: Optional[datetime] = None,
    ) -> Dict[str, List[str]]:
        """Store the event's face/vehicle crops as unconfirmed observations.

        Idempotent per event (skips when the event already has rows of the
        current model). Commits. Returns created ids per kind.
        """
        from app.models.face_embedding import FaceEmbedding
        from app.models.vehicle_embedding import VehicleEmbedding

        created: Dict[str, List[str]] = {FACE: [], VEHICLE: []}
        if analysis is None or analysis.is_empty:
            return created
        when = when or datetime.now(timezone.utc)
        written: List[str] = []
        try:
            if analysis.faces and not db.query(FaceEmbedding.id).filter(
                FaceEmbedding.event_id == event_id,
                FaceEmbedding.model_version == active_face_model()[0],
            ).first():
                for obs in analysis.faces:
                    row_id = str(uuid.uuid4())
                    rel = write_crop(_observation_rel(FACE, when, row_id), obs.crop_jpeg)
                    if rel:
                        written.append(rel)
                    db.add(FaceEmbedding(
                        id=row_id,
                        event_id=event_id,
                        embedding=json.dumps([round(float(x), 6) for x in obs.embedding]),
                        bounding_box=json.dumps(obs.bbox),
                        confidence=float(obs.score),
                        model_version=obs.model_version,
                        crop_path=rel,
                    ))
                    created[FACE].append(row_id)
            usable = [v for v in analysis.vehicles if v.embedding is not None]
            if usable and not db.query(VehicleEmbedding.id).filter(
                VehicleEmbedding.event_id == event_id,
                VehicleEmbedding.model_version == VEHICLE_CROP_MODEL_VERSION,
            ).first():
                for obs in usable:
                    row_id = str(uuid.uuid4())
                    rel = write_crop(_observation_rel(VEHICLE, when, row_id), obs.crop_jpeg)
                    if rel:
                        written.append(rel)
                    db.add(VehicleEmbedding(
                        id=row_id,
                        event_id=event_id,
                        embedding=json.dumps([round(float(x), 6) for x in obs.embedding]),
                        bounding_box=json.dumps(obs.bbox),
                        confidence=float(obs.score),
                        vehicle_type=obs.vehicle_type,
                        model_version=obs.model_version,
                        crop_path=rel,
                        dominant_color=obs.color,
                    ))
                    created[VEHICLE].append(row_id)
            db.commit()
        except Exception:
            db.rollback()
            for rel in written:
                delete_crop(rel)
            raise
        return created

    def event_observations(self, db: Session, event_id: str, kind: Optional[str] = None) -> List[Tuple[str, Any]]:
        """Current-model observations for an event as (kind, row)."""
        from app.models.face_embedding import FaceEmbedding
        from app.models.vehicle_embedding import VehicleEmbedding

        out: List[Tuple[str, Any]] = []
        if kind in (None, FACE):
            out += [(FACE, r) for r in db.query(FaceEmbedding).filter(
                FaceEmbedding.event_id == event_id,
                FaceEmbedding.model_version == active_face_model()[0],
            ).all()]
        if kind in (None, VEHICLE):
            out += [(VEHICLE, r) for r in db.query(VehicleEmbedding).filter(
                VehicleEmbedding.event_id == event_id,
                VehicleEmbedding.model_version == VEHICLE_CROP_MODEL_VERSION,
            ).all()]
        return out

    def get_observation(self, db: Session, kind: str, observation_id: str):
        from app.models.face_embedding import FaceEmbedding
        from app.models.vehicle_embedding import VehicleEmbedding

        model = FaceEmbedding if kind == FACE else VehicleEmbedding if kind == VEHICLE else None
        if model is None:
            return None
        return db.query(model).filter(model.id == observation_id).first()

    async def observe_stored_event(self, db: Session, event) -> Dict[str, List[str]]:
        """Build observations for an older event from its stored thumbnail.

        Only used when an event has no observations yet (events from before
        this change). Thumbnails are small, so faces rarely survive
        ``MIN_FACE_PX``; vehicles often do.
        """
        from app.services.cleanup_service import resolve_thumbnail_fs_path
        from app.services.event_media_deletion import default_media_roots
        from app.services.object_identity_service import analyze_image_bytes

        path = resolve_thumbnail_fs_path(getattr(event, "thumbnail_path", None), default_media_roots()["thumbnail_root"])
        data = None
        if path and os.path.isfile(path):
            with open(path, "rb") as fh:
                data = fh.read()
        elif getattr(event, "thumbnail_base64", None):
            import base64

            raw = event.thumbnail_base64
            if raw.startswith("data:"):
                raw = raw.split(",", 1)[1]
            try:
                data = base64.b64decode(raw)
            except (ValueError, TypeError):
                data = None
        if not data:
            return {FACE: [], VEHICLE: []}
        analysis = await analyze_image_bytes(
            data,
            faces=_privacy_flag(db, FACE_RECOGNITION_ENABLED),
            vehicles=_privacy_flag(db, VEHICLE_RECOGNITION_ENABLED),
        )
        return self.save_observations(db, event.id, analysis, when=getattr(event, "timestamp", None))

    # -- enrollment --------------------------------------------------------

    def _pick_observation(self, entity, kind: str, rows: List[Any]) -> Tuple[Optional[Any], List[Any]]:
        """Auto-pick the subject crop, or (None, candidates) when unsure."""
        if kind == VEHICLE:
            expected = normalize_color_name(getattr(entity, "vehicle_color", None))
            if expected:
                rows = [r for r in rows if color_agreement(r.dominant_color, expected) != "conflict"]
        if not rows:
            return None, []
        if len(rows) == 1:
            return rows[0], rows

        def area(r) -> int:
            try:
                b = json.loads(r.bounding_box)
                return int(b["width"]) * int(b["height"])
            except (TypeError, ValueError, KeyError):
                return 0

        ranked = sorted(rows, key=area, reverse=True)
        # Clearly the largest (the subject close to the camera): take it.
        if area(ranked[0]) >= 2 * max(area(ranked[1]), 1):
            return ranked[0], ranked
        return None, ranked

    async def enroll_from_event(
        self,
        db: Session,
        entity,
        event_id: str,
        *,
        observation_id: Optional[str] = None,
        observe_if_missing: bool = True,
    ) -> EnrollResult:
        """Add the event's face/vehicle crop to the entity's gallery.

        With ``observation_id`` that exact crop is used. Otherwise the crop is
        picked automatically when there is one plausible candidate; with
        several similar-sized candidates nothing is enrolled and the
        candidates are returned so the user can choose. Commits.
        """
        from app.models.entity_gallery_item import EntityGalleryItem
        from app.models.event import Event

        kind = _kind_for_entity(entity)
        if kind is None:
            return EnrollResult("unsupported", message="Only people and vehicles have galleries")
        if kind == FACE and not _privacy_flag(db, FACE_RECOGNITION_ENABLED):
            return EnrollResult("disabled", message="Face recognition is turned off")
        if kind == VEHICLE and not _privacy_flag(db, VEHICLE_RECOGNITION_ENABLED):
            return EnrollResult("disabled", message="Vehicle recognition is turned off")

        rows = [r for k, r in self.event_observations(db, event_id, kind)]
        if not rows and observe_if_missing and observation_id is None:
            event = db.query(Event).filter(Event.id == event_id).first()
            if event is not None:
                await self.observe_stored_event(db, event)
                rows = [r for k, r in self.event_observations(db, event_id, kind)]

        if observation_id is not None:
            chosen = next((r for r in rows if r.id == observation_id), None)
            if chosen is None:
                return EnrollResult("no_observation", message="That crop is not on this event")
            candidates = [chosen]
        else:
            chosen, candidates = self._pick_observation(entity, kind, rows)
            if chosen is None:
                if candidates:
                    return EnrollResult(
                        "ambiguous",
                        candidates=[observation_to_dict(r, kind) for r in candidates],
                        message="Several crops fit; pick one with observation_id",
                    )
                return EnrollResult("no_observation", message=f"No usable {kind} crop on this event")

        existing = db.query(EntityGalleryItem).filter(
            EntityGalleryItem.entity_id == entity.id,
            EntityGalleryItem.source_observation_id == chosen.id,
        ).first()
        if existing is not None:
            return EnrollResult("already_enrolled", items=[existing])

        item_id = str(uuid.uuid4())
        rel = None
        data = read_crop(chosen.crop_path)
        if data:
            rel = write_crop(_gallery_rel(entity.id, item_id), data)
        item = EntityGalleryItem(
            id=item_id,
            entity_id=entity.id,
            kind=kind,
            model_version=chosen.model_version,
            embedding=chosen.embedding,
            crop_path=rel,
            dominant_color=getattr(chosen, "dominant_color", None),
            bounding_box=chosen.bounding_box,
            source_event_id=event_id,
            source_observation_id=chosen.id,
        )
        db.add(item)
        try:
            db.commit()
        except Exception:
            db.rollback()
            delete_crop(rel)
            raise
        self.invalidate()
        logger.info(
            "Gallery item enrolled",
            extra={
                "event_type": "entity_gallery_enrolled",
                "entity_id": entity.id,
                "event_id": event_id,
                "kind": kind,
            },
        )
        return EnrollResult("enrolled", items=[item])

    def unenroll_event(self, db: Session, entity_id: str, event_id: str) -> int:
        """Drop gallery items that came from this event (a corrected link). Commits."""
        from app.models.entity_gallery_item import EntityGalleryItem

        items = db.query(EntityGalleryItem).filter(
            EntityGalleryItem.entity_id == entity_id,
            EntityGalleryItem.source_event_id == event_id,
        ).all()
        return self._delete_items(db, items)

    def remove_item(self, db: Session, entity_id: str, item_id: str) -> bool:
        from app.models.entity_gallery_item import EntityGalleryItem

        item = db.query(EntityGalleryItem).filter(
            EntityGalleryItem.entity_id == entity_id,
            EntityGalleryItem.id == item_id,
        ).first()
        return bool(item) and self._delete_items(db, [item]) == 1

    def reset_entity(self, db: Session, entity_id: str, kind: Optional[str] = None) -> int:
        """Remove every gallery item of an entity (optionally one kind). Commits."""
        from app.models.entity_gallery_item import EntityGalleryItem

        q = db.query(EntityGalleryItem).filter(EntityGalleryItem.entity_id == entity_id)
        if kind:
            q = q.filter(EntityGalleryItem.kind == kind)
        return self._delete_items(db, q.all())

    def delete_all_faces(self, db: Session) -> int:
        """Privacy control: every face gallery item and its crop. Commits."""
        from app.models.entity_gallery_item import EntityGalleryItem

        return self._delete_items(db, db.query(EntityGalleryItem).filter(EntityGalleryItem.kind == FACE).all())

    def _delete_items(self, db: Session, items: List[Any]) -> int:
        if not items:
            return 0
        paths = [i.crop_path for i in items]
        for item in items:
            db.delete(item)
        db.commit()
        for rel in paths:
            delete_crop(rel)
        self.invalidate()
        return len(items)

    def move_items(self, db: Session, from_entity_id: str, to_entity_id: str) -> int:
        """Re-own gallery items on an entity merge. Does not commit."""
        from app.models.entity_gallery_item import EntityGalleryItem

        items = db.query(EntityGalleryItem).filter(EntityGalleryItem.entity_id == from_entity_id).all()
        taken = {
            r.source_observation_id
            for r in db.query(EntityGalleryItem.source_observation_id).filter(
                EntityGalleryItem.entity_id == to_entity_id
            ).all()
        }
        moved = 0
        for item in items:
            if item.source_observation_id and item.source_observation_id in taken:
                continue  # the target already has this crop; cascade drops the copy
            item.entity_id = to_entity_id
            moved += 1
        self.invalidate()
        return moved

    def list_items(self, db: Session, entity_id: str) -> List[Any]:
        from app.models.entity_gallery_item import EntityGalleryItem

        return (
            db.query(EntityGalleryItem)
            .filter(EntityGalleryItem.entity_id == entity_id)
            .order_by(EntityGalleryItem.created_at.desc())
            .all()
        )

    # -- housekeeping ------------------------------------------------------

    def prune_orphan_crops(self, db: Session, *, min_age_s: float = 3600.0) -> int:
        """Delete crop files no row points at (deleted events/entities).

        Files younger than ``min_age_s`` are kept so an in-flight write is
        never raced.
        """
        from app.models.entity_gallery_item import EntityGalleryItem
        from app.models.face_embedding import FaceEmbedding
        from app.models.vehicle_embedding import VehicleEmbedding

        root = crops_root()
        if not os.path.isdir(root):
            return 0
        referenced = set()
        for model in (FaceEmbedding, VehicleEmbedding, EntityGalleryItem):
            referenced.update(p for (p,) in db.query(model.crop_path).filter(model.crop_path.isnot(None)).all())
        now = time.time()
        removed = 0
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                if rel in referenced or os.path.islink(full):
                    continue
                try:
                    if now - os.path.getmtime(full) < min_age_s:
                        continue
                    os.remove(full)
                    removed += 1
                except OSError:
                    continue
        for dirpath, dirs, files in os.walk(root, topdown=False):
            if dirpath != root and not dirs and not files:
                try:
                    os.rmdir(dirpath)
                except OSError:
                    pass
        if removed:
            logger.info("Pruned orphan entity crops", extra={"event_type": "entity_crops_pruned", "count": removed})
        return removed


def _privacy_flag(db: Session, key: str) -> bool:
    from app.models.system_setting import SystemSetting

    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    except Exception:  # noqa: BLE001
        return False
    return bool(row and str(row.value).lower() == "true")


def get_entity_gallery_service() -> EntityGalleryService:
    return EntityGalleryService()


def reset_entity_gallery_service() -> None:
    EntityGalleryService._reset_instance()
