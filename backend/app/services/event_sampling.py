"""Event-aligned clip windows, frame times, and subject crops.

Pure functions. No database, network, or provider calls.

Protect timing is optional. When start/end/peak are missing the window matches
the previous fixed policy (15s before and after the anchor) so callers can keep
the existing extractor path.

Bounding boxes are normalized to 0-1 before a crop is taken. Protect's
``detected_thumbnails[].coord`` is not verified against a live controller; see
``coerce_protect_coord``.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

FALLBACK_BEFORE_S = 15.0
FALLBACK_AFTER_S = 15.0
PAD_BEFORE_S = 3.0
PAD_AFTER_S = 3.0
MIN_WINDOW_S = 6.0
MAX_WINDOW_S = 30.0
DENSE_FRACTION = 0.7
CROP_PAD_FRACTION = 0.15
MIN_CROP_SIDE_PX = 32


@dataclass(frozen=True)
class SubjectBox:
    """A subject rectangle. ``normalized`` boxes are 0-1 fractions of the frame."""

    x: float
    y: float
    width: float
    height: float
    source: str
    label: Optional[str] = None
    normalized: bool = True
    space_width: Optional[int] = None
    space_height: Optional[int] = None


@dataclass(frozen=True)
class DetectionTiming:
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    peak: Optional[datetime] = None
    anchor: Optional[datetime] = None


@dataclass(frozen=True)
class ClipPlan:
    start: datetime
    end: datetime
    source: str  # "smart_detect" or "fallback"
    duration_s: float
    detection_start_s: Optional[float]
    detection_end_s: Optional[float]
    peak_s: Optional[float]


@dataclass(frozen=True)
class FrameSample:
    offset_seconds: float
    kind: str  # "dense", "sparse", "peak", "uniform"


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp_window(start: datetime, end: datetime, center: datetime) -> Tuple[datetime, datetime]:
    duration = (end - start).total_seconds()
    if duration > MAX_WINDOW_S:
        half = MAX_WINDOW_S / 2.0
        start = center - timedelta(seconds=half)
        end = center + timedelta(seconds=half)
    duration = (end - start).total_seconds()
    if duration < MIN_WINDOW_S:
        half = MIN_WINDOW_S / 2.0
        start = min(start, center - timedelta(seconds=half))
        end = max(end, center + timedelta(seconds=half))
    if end <= start:
        end = start + timedelta(seconds=MIN_WINDOW_S)
    return start, end


def plan_clip_window(
    timing: Optional[DetectionTiming],
    *,
    now: Optional[datetime] = None,
    fallback_before_s: float = FALLBACK_BEFORE_S,
    fallback_after_s: float = FALLBACK_AFTER_S,
) -> ClipPlan:
    """Choose the clip start/end from smart-detect timing, or the fixed fallback."""
    timing = timing or DetectionTiming()
    start_t = _aware(timing.start)
    end_t = _aware(timing.end)
    peak_t = _aware(timing.peak)
    anchor = _aware(timing.anchor) or peak_t or start_t or _aware(now) or datetime.now(timezone.utc)

    source = "fallback"
    if start_t and end_t and end_t > start_t:
        clip_start = start_t - timedelta(seconds=PAD_BEFORE_S)
        clip_end = end_t + timedelta(seconds=PAD_AFTER_S)
        center = peak_t or start_t + (end_t - start_t) / 2
        source = "smart_detect"
    elif start_t and peak_t and peak_t >= start_t:
        clip_start = start_t - timedelta(seconds=PAD_BEFORE_S)
        clip_end = peak_t + timedelta(seconds=PAD_AFTER_S)
        center = peak_t
        source = "smart_detect"
    elif start_t:
        clip_start = start_t - timedelta(seconds=PAD_BEFORE_S)
        clip_end = start_t + timedelta(seconds=max(PAD_AFTER_S, MIN_WINDOW_S - PAD_BEFORE_S))
        center = peak_t or start_t
        source = "smart_detect"
    elif peak_t:
        clip_start = peak_t - timedelta(seconds=max(PAD_BEFORE_S, MIN_WINDOW_S / 2))
        clip_end = peak_t + timedelta(seconds=max(PAD_AFTER_S, MIN_WINDOW_S / 2))
        center = peak_t
        source = "smart_detect"
    else:
        clip_start = anchor - timedelta(seconds=fallback_before_s)
        clip_end = anchor + timedelta(seconds=fallback_after_s)
        center = anchor

    if source == "smart_detect":
        clip_start, clip_end = _clamp_window(clip_start, clip_end, center)

    def _offset(moment: Optional[datetime]) -> Optional[float]:
        if moment is None:
            return None
        rel = (moment - clip_start).total_seconds()
        duration = (clip_end - clip_start).total_seconds()
        if rel < 0 or rel > duration:
            return min(max(0.0, rel), max(0.0, duration))
        return rel

    return ClipPlan(
        start=clip_start,
        end=clip_end,
        source=source,
        duration_s=(clip_end - clip_start).total_seconds(),
        detection_start_s=_offset(start_t) if source == "smart_detect" else None,
        detection_end_s=_offset(end_t) if source == "smart_detect" and end_t else None,
        peak_s=_offset(peak_t) if source == "smart_detect" else None,
    )


def _even_times(start: float, end: float, count: int, kind: str) -> List[FrameSample]:
    if count <= 0:
        return []
    start = float(start)
    end = float(end)
    if end < start:
        start, end = end, start
    if count == 1:
        return [FrameSample((start + end) / 2.0, kind)]
    span = end - start
    return [
        FrameSample(start + span * i / (count - 1), kind)
        for i in range(count)
    ]


def legacy_uniform_offsets(
    duration_s: float,
    frame_count: int,
    offset_ms: int = 2000,
) -> List[FrameSample]:
    """Previous policy: skip ``offset_ms`` from the start, then space frames evenly."""
    duration_s = max(0.0, float(duration_s))
    frame_count = max(1, int(frame_count))
    skip = max(0.0, offset_ms / 1000.0)
    if skip >= duration_s:
        skip = 0.0
    return _even_times(skip, duration_s, frame_count, "uniform")


def plan_frame_offsets(
    duration_s: float,
    frame_count: int,
    detection_start_s: Optional[float],
    detection_end_s: Optional[float],
    peak_s: Optional[float],
    *,
    offset_ms: int = 2000,
) -> List[FrameSample]:
    """Dense samples inside the detection, sparse samples outside it.

    With no detection times this matches ``legacy_uniform_offsets``.
    """
    duration_s = max(0.0, float(duration_s))
    frame_count = max(1, int(frame_count))
    if duration_s <= 0:
        return [FrameSample(0.0, "uniform")]

    if detection_start_s is None and detection_end_s is None and peak_s is None:
        return legacy_uniform_offsets(duration_s, frame_count, offset_ms)

    peak = None if peak_s is None else min(max(0.0, float(peak_s)), duration_s)
    if detection_start_s is None and peak is not None:
        det_start = max(0.0, peak - 1.5)
    else:
        det_start = 0.0 if detection_start_s is None else float(detection_start_s)
    if detection_end_s is None and peak is not None:
        det_end = min(duration_s, peak + 1.5)
    else:
        det_end = duration_s if detection_end_s is None else float(detection_end_s)

    det_start = min(max(0.0, det_start), duration_s)
    det_end = min(max(det_start, det_end), duration_s)
    if det_end - det_start < 0.2:
        center = peak if peak is not None else det_start
        det_start = max(0.0, center - 1.0)
        det_end = min(duration_s, center + 1.0)

    dense_n = min(frame_count, max(1, round(frame_count * DENSE_FRACTION)))
    sparse_n = frame_count - dense_n
    dense = _even_times(det_start, det_end, dense_n, "dense")

    if peak is not None and dense:
        nearest = min(range(len(dense)), key=lambda i: abs(dense[i].offset_seconds - peak))
        dense[nearest] = FrameSample(peak, "peak")

    sparse: List[FrameSample] = []
    if sparse_n:
        left = max(0.0, det_start)
        right = max(0.0, duration_s - det_end)
        outside = left + right
        if outside <= 0.05:
            sparse = []
            # Put the leftover budget into the detection instead.
            dense = _even_times(det_start, det_end, frame_count, "dense")
            if peak is not None:
                nearest = min(range(len(dense)), key=lambda i: abs(dense[i].offset_seconds - peak))
                dense[nearest] = FrameSample(peak, "peak")
        else:
            left_n = int(round(sparse_n * (left / outside))) if left > 0 else 0
            left_n = min(max(0, left_n), sparse_n)
            right_n = sparse_n - left_n
            if left <= 0:
                right_n = sparse_n
                left_n = 0
            if right <= 0:
                left_n = sparse_n
                right_n = 0
            if left_n:
                sparse.extend(_even_times(0.0, max(0.0, det_start), left_n, "sparse"))
            if right_n:
                sparse.extend(_even_times(det_end, duration_s, right_n, "sparse"))

    merged = _unique_sorted(dense + sparse)
    if len(merged) > frame_count:
        merged = _prefer(merged, frame_count, peak)
    elif len(merged) < frame_count:
        extra = _even_times(det_start, det_end, frame_count - len(merged), "dense")
        merged = _unique_sorted(merged + extra)
        if len(merged) > frame_count:
            merged = _prefer(merged, frame_count, peak)
    return _fill_to_count(merged, frame_count, duration_s)


def _fill_to_count(samples: Sequence[FrameSample], count: int, duration_s: float) -> List[FrameSample]:
    """Add mid-gap samples until ``count`` or the clip has no room left."""
    filled = _unique_sorted(samples)
    guard = 0
    while len(filled) < count and guard < count * 3:
        guard += 1
        points = [0.0] + [sample.offset_seconds for sample in filled] + [duration_s]
        gaps = [
            (points[i + 1] - points[i], points[i], points[i + 1])
            for i in range(len(points) - 1)
        ]
        span, left, right = max(gaps, key=lambda item: item[0])
        if span < 0.05:
            break
        filled = _unique_sorted(filled + [FrameSample(round((left + right) / 2.0, 3), "dense")])
    if len(filled) > count:
        return _prefer(filled, count, None)
    return filled


def _unique_sorted(samples: Sequence[FrameSample]) -> List[FrameSample]:
    best = {}
    rank = {"peak": 3, "dense": 2, "sparse": 1, "uniform": 0}
    for sample in samples:
        key = round(sample.offset_seconds, 3)
        current = best.get(key)
        if current is None or rank.get(sample.kind, 0) > rank.get(current.kind, 0):
            best[key] = FrameSample(key, sample.kind)
    return [best[k] for k in sorted(best)]


def _prefer(samples: Sequence[FrameSample], count: int, peak: Optional[float]) -> List[FrameSample]:
    def sort_key(sample: FrameSample) -> Tuple[int, float]:
        kind_rank = 0 if sample.kind == "peak" else 1 if sample.kind == "dense" else 2
        distance = 0.0 if peak is None else abs(sample.offset_seconds - peak)
        return (kind_rank, distance)

    chosen = sorted(samples, key=sort_key)[:count]
    return sorted(chosen, key=lambda s: s.offset_seconds)


def allocate_subject_crops(
    samples: Sequence[FrameSample],
    crop_count: int,
    peak_s: Optional[float],
) -> Tuple[List[FrameSample], List[float]]:
    """Keep the image budget: crops replace the frames farthest from the peak.

    At least one full frame is always kept. The peak full frame is never the
    one replaced, so the model still sees the wide shot plus the zoom.
    """
    samples = list(samples)
    if crop_count <= 0 or len(samples) < 2:
        return samples, []
    crop_count = min(int(crop_count), len(samples) - 1)
    peak = peak_s
    if peak is None:
        peak = samples[len(samples) // 2].offset_seconds

    def drop_rank(sample: FrameSample) -> Tuple[int, float]:
        # Drop sparse frames first, then those farthest from the peak.
        # Peak frames sort last so they are kept.
        sparse_first = 0 if sample.kind == "sparse" else 1 if sample.kind != "peak" else 2
        return (sparse_first, -abs(sample.offset_seconds - peak))

    ranked = sorted(samples, key=drop_rank)
    drop_ids = set()
    for sample in ranked:
        if len(drop_ids) >= crop_count:
            break
        if sample.kind == "peak":
            continue
        drop_ids.add(id(sample))
    kept = [s for s in samples if id(s) not in drop_ids]

    crop_times = [peak]
    for sample in samples:
        if len(crop_times) >= crop_count:
            break
        if abs(sample.offset_seconds - peak) < 0.05:
            continue
        crop_times.append(sample.offset_seconds)
    while len(crop_times) < crop_count:
        crop_times.append(peak)
    return kept, crop_times[:crop_count]


def coerce_protect_coord(coord, *, label: Optional[str] = None) -> Optional[SubjectBox]:
    """Turn a Protect coord into a SubjectBox.

    Assumed layout is ``[x, y, width, height]`` (UniFi thumbnail metadata).
    Values in 0-1 are fractions. Values that fit in 0-1000 are thousandths of
    the frame. Anything larger is pixels.
    """
    if coord is None:
        return None
    try:
        values = [float(v) for v in list(coord)[:4]]
    except (TypeError, ValueError):
        return None
    if len(values) < 4:
        return None
    x, y, w, h = values
    if w <= 0 or h <= 0:
        return None
    if max(x, y, w, h) <= 1.0 and min(x, y, w, h) >= 0.0:
        return SubjectBox(x, y, w, h, source="protect", label=label, normalized=True)
    if max(x, y, x + w, y + h) <= 1000.0 and min(x, y) >= 0.0:
        return SubjectBox(
            x / 1000.0,
            y / 1000.0,
            w / 1000.0,
            h / 1000.0,
            source="protect",
            label=label,
            normalized=True,
        )
    return SubjectBox(x, y, w, h, source="protect", label=label, normalized=False)


def box_from_mapping(raw: dict, *, source: str) -> Optional[SubjectBox]:
    """Read x/y/width/height from a stored detection record."""
    if not isinstance(raw, dict):
        return None
    try:
        x = float(raw.get("x"))
        y = float(raw.get("y"))
        width = float(raw.get("width"))
        height = float(raw.get("height"))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    label = raw.get("entity_type") or raw.get("label") or raw.get("type")
    normalized = max(x, y, width, height) <= 1.0 and min(x, y, width, height) >= 0.0
    return SubjectBox(
        x=x,
        y=y,
        width=width,
        height=height,
        source=source,
        label=str(label) if label else None,
        normalized=normalized,
    )


def choose_subject_box(
    protect_boxes: Sequence[SubjectBox],
    fallback_boxes: Sequence[SubjectBox],
) -> Optional[SubjectBox]:
    """Prefer a Protect smart-detect box, then any stored detection box."""
    for box in protect_boxes:
        if box is not None:
            return box
    for box in fallback_boxes:
        if box is not None:
            return box
    return None


def _to_normalized(box: SubjectBox, frame_w: int, frame_h: int) -> Optional[Tuple[float, float, float, float]]:
    if frame_w <= 0 or frame_h <= 0:
        return None
    if box.normalized:
        return box.x, box.y, box.width, box.height
    space_w = box.space_width or frame_w
    space_h = box.space_height or frame_h
    if space_w <= 0 or space_h <= 0:
        return None
    if box.space_width is None and (box.x + box.width > frame_w + 1 or box.y + box.height > frame_h + 1):
        return None
    return (
        box.x / space_w,
        box.y / space_h,
        box.width / space_w,
        box.height / space_h,
    )


def crop_jpeg(
    image_bytes: bytes,
    box: SubjectBox,
    *,
    pad_fraction: float = CROP_PAD_FRACTION,
    quality: int = 90,
) -> Optional[bytes]:
    """Crop ``image_bytes`` to ``box`` at the source resolution.

    Returns None when the box is missing or the crop would be empty. The crop
    is not downscaled; callers already resize full frames separately.
    """
    if not image_bytes or box is None:
        return None
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        logger.debug("Subject crop skipped; image could not be opened: %s", type(exc).__name__)
        return None

    norm = _to_normalized(box, image.width, image.height)
    if norm is None:
        return None
    x, y, w, h = norm
    if w <= 0 or h <= 0:
        return None

    pad_w = w * pad_fraction
    pad_h = h * pad_fraction
    left = max(0.0, x - pad_w)
    top = max(0.0, y - pad_h)
    right = min(1.0, x + w + pad_w)
    bottom = min(1.0, y + h + pad_h)
    if right <= left or bottom <= top:
        return None

    px_left = int(round(left * image.width))
    px_top = int(round(top * image.height))
    px_right = int(round(right * image.width))
    px_bottom = int(round(bottom * image.height))
    px_left = min(max(0, px_left), image.width - 1)
    px_top = min(max(0, px_top), image.height - 1)
    px_right = min(max(px_left + 1, px_right), image.width)
    px_bottom = min(max(px_top + 1, px_bottom), image.height)

    crop_w = px_right - px_left
    crop_h = px_bottom - px_top
    if crop_w < MIN_CROP_SIDE_PX or crop_h < MIN_CROP_SIDE_PX:
        # Expand around the center up to the minimum, still inside the frame.
        cx = (px_left + px_right) / 2.0
        cy = (px_top + px_bottom) / 2.0
        half_w = max(crop_w, MIN_CROP_SIDE_PX) / 2.0
        half_h = max(crop_h, MIN_CROP_SIDE_PX) / 2.0
        px_left = int(max(0, cx - half_w))
        px_top = int(max(0, cy - half_h))
        px_right = int(min(image.width, cx + half_w))
        px_bottom = int(min(image.height, cy + half_h))
        if px_right - px_left < 8 or px_bottom - px_top < 8:
            return None

    cropped = image.crop((px_left, px_top, px_right, px_bottom))
    buffer = io.BytesIO()
    cropped.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()
