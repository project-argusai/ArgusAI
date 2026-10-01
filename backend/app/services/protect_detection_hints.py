"""Read Protect smart-detect timing, boxes, and the detection-time thumbnail.

Field names follow uiprotect's private Event model (``start``, ``end``,
``metadata.detected_thumbnails``). The public integration stream often omits
``detected_thumbnails``, so every lookup is defensive and a miss falls back to
the live snapshot and the fixed clip window. This was checked against the
uiprotect models and UniFi's thumbnail metadata shape, not against a live
controller in this change.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional

from app.services.event_sampling import SubjectBox, coerce_protect_coord

logger = logging.getLogger(__name__)


@dataclass
class DetectionHints:
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    peak: Optional[datetime] = None
    boxes: List[SubjectBox] = field(default_factory=list)
    thumbnail_id: Optional[str] = None

    def has_timing(self) -> bool:
        return any(value is not None for value in (self.start, self.end, self.peak))

    def has_signal(self) -> bool:
        return self.has_timing() or bool(self.boxes)


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Protect clocks are epoch milliseconds. Seconds are smaller than 1e12.
        seconds = float(value) / 1000.0 if float(value) > 1_000_000_000_000 else float(value)
        if seconds <= 0:
            return None
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _mapping_get(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        for name in names:
            if name in obj and obj[name] is not None:
                return obj[name]
        return None
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _thumbnails(event_obj: Any) -> list:
    metadata = _mapping_get(event_obj, "metadata")
    thumbs = _mapping_get(metadata, "detected_thumbnails", "detectedThumbnails")
    if isinstance(thumbs, (list, tuple)):
        return list(thumbs)
    return []


def _thumb_confidence(thumb: Any) -> float:
    value = _mapping_get(thumb, "confidence")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def extract_detection_hints(event_obj: Any) -> DetectionHints:
    """Pull timing and boxes off a Protect event object. Never raises."""
    hints = DetectionHints()
    if event_obj is None:
        return hints
    try:
        hints.start = _as_datetime(_mapping_get(event_obj, "start"))
        hints.end = _as_datetime(_mapping_get(event_obj, "end"))
        thumb_id = _mapping_get(event_obj, "thumbnail_id", "thumbnailId")
        if isinstance(thumb_id, str) and thumb_id:
            hints.thumbnail_id = thumb_id

        best_thumb = None
        best_score = -1.0
        for thumb in _thumbnails(event_obj):
            score = _thumb_confidence(thumb)
            clock = _as_datetime(_mapping_get(thumb, "clock_best_wall", "clockBestWall"))
            if clock is not None and (hints.peak is None or score >= best_score):
                hints.peak = clock
            if score >= best_score:
                best_score = score
                best_thumb = thumb
            label = _mapping_get(thumb, "type", "object_type")
            label_text = getattr(label, "value", label)
            box = coerce_protect_coord(
                _mapping_get(thumb, "coord"),
                label=str(label_text) if label_text else None,
            )
            if box is not None:
                hints.boxes.append(box)

        if best_thumb is not None and hints.boxes:
            # Keep the highest-confidence box first for choose_subject_box.
            label = _mapping_get(best_thumb, "type", "object_type")
            label_text = getattr(label, "value", label)
            primary = coerce_protect_coord(
                _mapping_get(best_thumb, "coord"),
                label=str(label_text) if label_text else None,
            )
            if primary is not None:
                hints.boxes = [primary] + [b for b in hints.boxes if b is not primary]
    except Exception as exc:
        logger.warning(
            "Protect detection hints could not be read: %s",
            type(exc).__name__,
            extra={"event_type": "protect_detection_hints_failed"},
        )
        return DetectionHints()
    return hints


async def fetch_event_thumbnail_bytes(event_obj: Any) -> Optional[bytes]:
    """Return Protect's detection-time event thumbnail, or None.

    A missing method or a failed fetch is a normal fallback, not an error.
    Bytes are never logged.
    """
    if event_obj is None:
        return None
    getter = getattr(event_obj, "get_thumbnail", None)
    if not callable(getter):
        return None
    try:
        result = getter()
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        logger.warning(
            "Protect event thumbnail fetch failed; using a snapshot taken at processing time: %s",
            type(exc).__name__,
            extra={"event_type": "protect_event_thumbnail_unavailable"},
        )
        return None
    if isinstance(result, (bytes, bytearray)) and result:
        return bytes(result)
    return None
