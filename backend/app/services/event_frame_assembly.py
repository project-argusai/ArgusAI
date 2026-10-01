"""Build the image list sent to vision providers for one Protect clip.

Full frames stay on the existing resize path. A subject crop, when a box
exists, replaces the frames farthest from the detection so the image count
stays at the configured budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from app.services.event_sampling import (
    FrameSample,
    SubjectBox,
    allocate_subject_crops,
    plan_frame_offsets,
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
    its offset and blur filter, unless a subject box asks for a crop.
    """
    from app.services.frame_extractor import get_frame_extractor

    extractor = get_frame_extractor()
    frame_count = int(frame_cfg.get("frame_count") or 10)
    crop_budget = int(frame_cfg.get("subject_crop_count", 1) or 0)
    crop_budget = max(0, min(3, crop_budget))
    has_timing = timing_source == "smart_detect"
    use_crop = box is not None and crop_budget > 0

    if not has_timing and not use_crop:
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
    else:
        frames, timestamps = await _legacy_extract(extractor, clip_path, frame_cfg)
        images = _as_jpeg_list(frames)
        times = [float(t) for t in (timestamps or [])]
        samples = [FrameSample(t, "uniform") for t in times]
        return await _apply_crops(
            extractor,
            clip_path,
            images,
            samples,
            box,
            crop_budget,
            peak_s=times[len(times) // 2] if times else None,
            sampling="uniform",
        )

    if use_crop:
        kept, crop_times = allocate_subject_crops(samples, crop_budget, peak_s)
    else:
        kept, crop_times = samples, []

    # Extract every planned full frame first. Crops replace a subset so a
    # failed crop still leaves the original frame in the request.
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
    paired = list(zip(images, times if times else all_offsets))
    if not paired:
        return FrameAssembly(sampling=sampling)

    if not crop_times:
        return FrameAssembly(
            images=[img for img, _ in paired],
            timestamps=[ts for _, ts in paired],
            offsets=all_offsets,
            sampling=sampling,
            full_count=len(paired),
        )

    return await _apply_crops(
        extractor,
        clip_path,
        [img for img, _ in paired],
        samples[: len(paired)],
        box,
        len(crop_times),
        peak_s=peak_s if peak_s is not None else (crop_times[0] if crop_times else None),
        sampling=sampling,
        preselected_crop_times=crop_times,
        preselected_kept=kept,
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
) -> FrameAssembly:
    from app.services.event_sampling import crop_jpeg

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
    for offset in crop_times:
        native = await extractor.extract_native_jpeg_at(clip_path, offset)
        cropped = crop_jpeg(native, box) if native else None
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
