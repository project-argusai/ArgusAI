"""Build the image list sent to vision providers for one Protect clip.

Full frames stay on the existing resize path. A subject crop, when a box
exists, replaces the frames farthest from the detection so the image count
stays at the configured budget.

When Protect has no smart-detect box, local vehicle/face detectors run once
on the peak (or middle) frame to supply a fallback crop box.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from app.services.event_sampling import (
    FrameSample,
    SubjectBox,
    allocate_subject_crops,
    choose_subject_box,
    plan_frame_offsets,
    rank_fallback_boxes,
    subject_box_from_pixel_bbox,
)

logger = logging.getLogger(__name__)


@dataclass
class FrameAssembly:
    images: List[bytes] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)
    offsets: List[float] = field(default_factory=list)
    subject_crop_used: bool = False
    crop_count: int = 0
    full_count: int = 0
    sampling: str = "uniform"


async def _legacy_extract(extractor, clip_path, frame_cfg):
    frames, timestamps = await extractor.extract_frames_with_timestamps(
        clip_path=clip_path,
        frame_count=frame_cfg["frame_count"],
        sampling_strategy=frame_cfg["sampling_strategy"],
        offset_ms=frame_cfg["offset_ms"],
    )
    return frames, timestamps


def _as_jpeg_list(frames) -> List[bytes]:
    import numpy as np

    converted = []
    for frame in frames or []:
        if isinstance(frame, np.ndarray):
            import cv2
            ok, buffer = cv2.imencode(".jpg", frame)
            if ok:
                converted.append(buffer.tobytes())
        elif isinstance(frame, (bytes, bytearray)):
            converted.append(bytes(frame))
    return converted


def _image_size(image_bytes: bytes) -> tuple[Optional[int], Optional[int]]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None, None


def _pick_probe_image(
    images: List[bytes],
    samples: List[FrameSample],
    peak_s: Optional[float],
) -> Optional[bytes]:
    """Peak frame when known; otherwise the middle extracted frame."""
    if not images:
        return None
    if peak_s is not None and samples:
        nearest = min(
            range(min(len(images), len(samples))),
            key=lambda i: abs(samples[i].offset_seconds - peak_s),
        )
        return images[nearest]
    return images[len(images) // 2]


async def detect_fallback_subject_boxes(image_bytes: bytes) -> List[SubjectBox]:
    """Run local vehicle and face detectors once; return boxes best-first.

    Failures (missing models, bad bytes) yield an empty list so assembly can
    continue without crops. Does not invent subjects.
    """
    if not image_bytes:
        return []

    space_w, space_h = _image_size(image_bytes)
    ranked: List[tuple] = []

    try:
        from app.services.vehicle_detection_service import VehicleDetectionService

        vehicles = await VehicleDetectionService().detect_vehicles(image_bytes)
        for vehicle in vehicles or []:
            box = subject_box_from_pixel_bbox(
                vehicle.bbox,
                source="vehicle",
                label=getattr(vehicle, "vehicle_type", None) or "vehicle",
                space_width=space_w,
                space_height=space_h,
            )
            if box is not None:
                ranked.append((getattr(vehicle, "confidence", 0.0), box))
    except Exception as exc:
        logger.debug(
            "Vehicle fallback detection skipped: %s",
            type(exc).__name__,
            extra={"event_type": "subject_crop_fallback_vehicle_skip"},
        )

    try:
        from app.services.face_detection_service import FaceDetectionService

        faces = await FaceDetectionService().detect_faces(image_bytes)
        for face in faces or []:
            box = subject_box_from_pixel_bbox(
                face.bbox,
                source="face",
                label="face",
                space_width=space_w,
                space_height=space_h,
            )
            if box is not None:
                ranked.append((getattr(face, "confidence", 0.0), box))
    except Exception as exc:
        logger.debug(
            "Face fallback detection skipped: %s",
            type(exc).__name__,
            extra={"event_type": "subject_crop_fallback_face_skip"},
        )

    return rank_fallback_boxes(ranked)


async def _resolve_subject_box(
    box: Optional[SubjectBox],
    *,
    images: List[bytes],
    samples: List[FrameSample],
    peak_s: Optional[float],
    crop_budget: int,
) -> Optional[SubjectBox]:
    """Prefer the caller box (Protect); else detect once on a probe frame."""
    if box is not None or crop_budget <= 0:
        return box
    probe = _pick_probe_image(images, samples, peak_s)
    if not probe:
        return None
    fallback = await detect_fallback_subject_boxes(probe)
    chosen = choose_subject_box([], fallback)
    if chosen is not None:
        logger.info(
            "Subject crop using local %s fallback box",
            chosen.source,
            extra={
                "event_type": "subject_crop_fallback_used",
                "source": chosen.source,
                "label": chosen.label,
            },
        )
    return chosen


async def assemble_event_frames(
    clip_path,
    *,
    frame_cfg: dict,
    detection: Optional[Any] = None,
    clip_duration_s: Optional[float] = None,
    detection_start_s: Optional[float] = None,
    detection_end_s: Optional[float] = None,
    peak_s: Optional[float] = None,
    timing_source: str = "fallback",
    box: Optional[SubjectBox] = None,
) -> FrameAssembly:
    """Return full frames plus optional subject crops.

    ``timing_source="fallback"`` keeps the historical extractor call, including
    its offset and blur filter. When no Protect box is supplied and crops are
    enabled, local vehicle/face detectors run once on the peak/middle frame.
    """
    from app.services.frame_extractor import get_frame_extractor

    extractor = get_frame_extractor()
    frame_count = int(frame_cfg.get("frame_count") or 10)
    crop_budget = int(frame_cfg.get("subject_crop_count", 1) or 0)
    crop_budget = max(0, min(3, crop_budget))
    has_timing = timing_source == "smart_detect"
    crop_kwargs = {
        "min_area_fraction": frame_cfg.get("subject_crop_min_area_fraction"),
        "min_side_px": frame_cfg.get("subject_crop_min_side_px"),
    }

    # Fast path: no timing and no chance of a crop (no Protect box and crops off).
    # When crops are on but box is missing we still extract so local detectors can run.
    if not has_timing and box is None and crop_budget <= 0:
        frames, timestamps = await _legacy_extract(extractor, clip_path, frame_cfg)
        images = _as_jpeg_list(frames)
        times = [float(t) for t in (timestamps or [])]
        return FrameAssembly(
            images=images,
            timestamps=times,
            offsets=times,
            sampling="uniform",
            full_count=len(images),
        )

    if has_timing:
        duration = float(clip_duration_s or 0.0)
        samples = plan_frame_offsets(
            duration,
            frame_count,
            detection_start_s,
            detection_end_s,
            peak_s,
            offset_ms=int(frame_cfg.get("offset_ms") or 0),
        )
        sampling = "event_aligned"
        all_offsets = [s.offset_seconds for s in samples]
        raw_frames, raw_times = await extractor.extract_frames_with_timestamps(
            clip_path=clip_path,
            frame_count=max(1, len(all_offsets)),
            sampling_strategy="uniform",
            offset_ms=0,
            filter_blur=False,
            target_offsets_s=all_offsets,
        )
        images = _as_jpeg_list(raw_frames)
        times = [float(t) for t in (raw_times or [])]
        if len(times) != len(images):
            times = all_offsets[: len(images)]
        samples = samples[: len(images)]
    else:
        frames, timestamps = await _legacy_extract(extractor, clip_path, frame_cfg)
        images = _as_jpeg_list(frames)
        times = [float(t) for t in (timestamps or [])]
        samples = [FrameSample(t, "uniform") for t in times]
        sampling = "uniform"
        peak_s = peak_s if peak_s is not None else (times[len(times) // 2] if times else None)

    if not images:
        return FrameAssembly(sampling=sampling)

    box = await _resolve_subject_box(
        box,
        images=images,
        samples=samples,
        peak_s=peak_s,
        crop_budget=crop_budget,
    )

    if box is None or crop_budget <= 0:
        return FrameAssembly(
            images=images,
            timestamps=times[: len(images)] if times else [s.offset_seconds for s in samples],
            offsets=[s.offset_seconds for s in samples] if samples else times,
            sampling=sampling,
            full_count=len(images),
        )

    return await _apply_crops(
        extractor,
        clip_path,
        images,
        samples,
        box,
        crop_budget,
        peak_s=peak_s if peak_s is not None else (times[len(times) // 2] if times else None),
        sampling=sampling,
        **crop_kwargs,
    )


async def _apply_crops(
    extractor,
    clip_path,
    images: List[bytes],
    samples: List[FrameSample],
    box: Optional[SubjectBox],
    crop_budget: int,
    *,
    peak_s: Optional[float],
    sampling: str,
    preselected_crop_times: Optional[List[float]] = None,
    preselected_kept: Optional[List[FrameSample]] = None,
    min_area_fraction: Optional[float] = None,
    min_side_px: Optional[int] = None,
) -> FrameAssembly:
    from app.services.event_sampling import (
        DEFAULT_CROP_MIN_AREA_FRACTION,
        DEFAULT_CROP_MIN_SIDE_PX,
        crop_jpeg,
    )

    if box is None or crop_budget <= 0 or len(images) < 2:
        times = [s.offset_seconds for s in samples] or []
        return FrameAssembly(
            images=images,
            timestamps=times[: len(images)] or [0.0] * len(images),
            offsets=[s.offset_seconds for s in samples],
            sampling=sampling,
            full_count=len(images),
        )

    if preselected_kept is not None and preselected_crop_times is not None:
        kept = preselected_kept
        crop_times = preselected_crop_times
    else:
        kept, crop_times = allocate_subject_crops(samples, crop_budget, peak_s)

    by_time = {}
    for image, sample in zip(images, samples):
        by_time[round(sample.offset_seconds, 3)] = image
    # If the extractor returned a different timestamp grid, zip by position.
    if len(by_time) < len(images):
        by_time = {round(sample.offset_seconds, 3): image for image, sample in zip(images, samples)}

    crops = []
    used_times = []
    area_limit = (
        float(min_area_fraction)
        if min_area_fraction is not None
        else DEFAULT_CROP_MIN_AREA_FRACTION
    )
    side_limit = int(min_side_px) if min_side_px is not None else DEFAULT_CROP_MIN_SIDE_PX
    for offset in crop_times:
        native = await extractor.extract_native_jpeg_at(clip_path, offset)
        cropped = (
            crop_jpeg(native, box, min_area_fraction=area_limit, min_side_px=side_limit)
            if native
            else None
        )
        if cropped:
            crops.append(cropped)
            used_times.append(offset)

    if not crops:
        logger.info(
            "Subject crop unavailable; sending full frames only",
            extra={"event_type": "subject_crop_skipped", "sampling": sampling},
        )
        times = [s.offset_seconds for s in samples][: len(images)]
        return FrameAssembly(
            images=images,
            timestamps=times,
            offsets=times,
            sampling=sampling,
            full_count=len(images),
        )

    drop_n = len(crops)
    # Drop the frames allocate_subject_crops already chose, limited to crops we made.
    drop_offsets = []
    kept_offsets = {round(s.offset_seconds, 3) for s in kept}
    for sample in samples:
        key = round(sample.offset_seconds, 3)
        if key not in kept_offsets:
            drop_offsets.append(key)
    drop_offsets = drop_offsets[:drop_n]

    full_images = []
    full_times = []
    for sample, image in zip(samples, images):
        key = round(sample.offset_seconds, 3)
        if key in drop_offsets:
            drop_offsets.remove(key)
            continue
        full_images.append(image)
        full_times.append(sample.offset_seconds)

    return FrameAssembly(
        images=full_images + crops,
        timestamps=full_times + used_times,
        offsets=[s.offset_seconds for s in samples],
        subject_crop_used=True,
        crop_count=len(crops),
        full_count=len(full_images),
        sampling=sampling,
    )
