"""Pair-comparison metrics for a local/cloud analysis result (#730, #691 P1 S3).

Pure functions, no I/O. ``score_pair(local, cloud)`` returns a flat dict of
plain ``int``/``float`` values with a fixed key set (``METRIC_KEYS``): no
text, no ``None``, no numpy. That makes the output JSON-safe and suitable for
the numbers-only ``shadow_daily_summary`` (#735).

A result may be a dict, an ``AIResult``-like object, or ``None``.
- Missing: ``None``, an empty dict, or ``success`` is False. When either side
  is missing, ``pair_complete`` is 0 and every comparison metric is 0.
- Blank: an explicit ``blank`` flag, an empty description, or a "nothing
  happened" description with no meaningful objects (``unknown`` ignored).
- Entities come from ``matched_entity_ids`` (top level or inside
  ``identification``; a JSON string is accepted). Never from description text.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable, Optional, Set

METRIC_KEYS = (
    "pair_complete",
    "local_missing",
    "cloud_missing",
    "local_blank",
    "cloud_blank",
    "blank_agree",
    "objects_jaccard",
    "objects_local_only",
    "objects_cloud_only",
    "entities_jaccard",
    "description_similarity",
    "confidence_delta",
)

_BLANK_PREFIXES = ("no activity", "no motion", "nothing", "no one", "no people",
                   "no objects", "empty scene", "no notable")
_IGNORED_OBJECTS = {"unknown", ""}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _get(result: Any, key: str, default: Any = None) -> Any:
    if result is None:
        return default
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def _is_missing(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, dict) and not result:
        return True
    return _get(result, "success", True) is False


def _labels(values: Any) -> Set[str]:
    if values is None or isinstance(values, (str, bytes)):
        return set()
    try:
        items = list(values)
    except TypeError:
        return set()
    return {str(v).strip().lower() for v in items} - _IGNORED_OBJECTS


def _entity_ids(result: Any) -> Set[str]:
    raw = _get(result, "matched_entity_ids")
    if raw is None:
        ident = _get(result, "identification")
        if isinstance(ident, dict):
            raw = ident.get("matched_entity_ids")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return set()
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {str(v) for v in raw}


def _tokens(text: Optional[str]) -> Set[str]:
    return set(_TOKEN_RE.findall(str(text or "").lower()))


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Jaccard similarity; two empty sets agree (1.0)."""
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return float(len(a & b)) / float(len(a | b))


def description_similarity(a: Optional[str], b: Optional[str]) -> float:
    """Token-set Jaccard over lowercase alphanumeric tokens, 0.0-1.0."""
    return jaccard(_tokens(a), _tokens(b))


def is_blank(result: Any) -> bool:
    if _get(result, "blank") is True or str(_get(result, "blank", "")).lower() == "true":
        return True
    description = str(_get(result, "description") or "").strip().lower()
    if not description:
        return True
    if not _labels(_get(result, "objects_detected")):
        return description.startswith(_BLANK_PREFIXES)
    return False


def score_pair(local: Any, cloud: Any) -> dict:
    """Score one local/cloud pair. Returns plain numbers only (see module doc)."""
    local_missing = _is_missing(local)
    cloud_missing = _is_missing(cloud)
    metrics = {key: 0 for key in METRIC_KEYS}
    metrics.update({
        "objects_jaccard": 0.0,
        "entities_jaccard": 0.0,
        "description_similarity": 0.0,
        "local_missing": int(local_missing),
        "cloud_missing": int(cloud_missing),
        "local_blank": int(not local_missing and is_blank(local)),
        "cloud_blank": int(not cloud_missing and is_blank(cloud)),
    })
    if local_missing or cloud_missing:
        return metrics

    local_objects = _labels(_get(local, "objects_detected"))
    cloud_objects = _labels(_get(cloud, "objects_detected"))
    local_conf = _number(_get(local, "confidence"))
    cloud_conf = _number(_get(cloud, "confidence"))

    metrics.update({
        "pair_complete": 1,
        "blank_agree": int(metrics["local_blank"] == metrics["cloud_blank"]),
        "objects_jaccard": jaccard(local_objects, cloud_objects),
        "objects_local_only": len(local_objects - cloud_objects),
        "objects_cloud_only": len(cloud_objects - local_objects),
        "entities_jaccard": jaccard(_entity_ids(local), _entity_ids(cloud)),
        "description_similarity": description_similarity(
            _get(local, "description"), _get(cloud, "description")),
        "confidence_delta": (
            int(round(local_conf - cloud_conf))
            if local_conf is not None and cloud_conf is not None else 0
        ),
    })
    return metrics
