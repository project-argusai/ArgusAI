"""
Per-object analysis of a live event frame: faces and vehicles as crops.

Runs once per event on the full-resolution Protect snapshot, before the
vision call, and produces everything identity matching needs:

* faces: YuNet box + SFace identity embedding + the aligned 112x112 crop
* vehicles: MobileNet-SSD box, a CLIP embedding of the padded crop (not the
  whole frame), and a coarse colour family

The scene around an object no longer reaches the matcher. On a fixed camera
the background dominated whole-frame vectors, so an empty driveway scored
higher against a saved car than the car itself did. With crops, "no vehicle
box" simply means "no vehicle match".

Fail-open: any error yields an empty analysis. Callers bound the call with a
timeout (``pre_ai_context_service``); CPU work runs in the default executor.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

import cv2
import numpy as np

from app.services.face_recognition_service import (
    SFACE_MODEL_VERSION,
    get_face_recognition_service,
    normalize,
)
from app.services.vehicle_color import dominant_vehicle_color, frame_is_grayscale

logger = logging.getLogger(__name__)

VEHICLE_CROP_MODEL_VERSION = "clip-ViT-B-32-vehicle-crop-v1"

# MobileNet-SSD is weak on far vehicles; 0.45 recovers some without
# admitting much clutter. Boxes under 0.5% of the frame (~100x100 px at
# 1080p) are street traffic or noise, too small to identify.
VEHICLE_DETECTION_THRESHOLD = 0.45
VEHICLE_MIN_AREA_FRACTION = 0.005
MAX_VEHICLES = 3
VEHICLE_CROP_PADDING = 0.08
VEHICLE_CROP_MAX_SIDE = 320
CROP_JPEG_QUALITY = 85

# Shared by every caller: cv2.dnn nets are not safe to run concurrently.
_vehicle_net_lock = threading.Lock()


@dataclass
class FaceObservation:
    bbox: dict
    score: float
    embedding: np.ndarray
    crop_jpeg: bytes
    model_version: str = SFACE_MODEL_VERSION
    # Filled by the pre-AI face match (logging / persistence only).
    match_entity_id: Optional[str] = None
    match_score: Optional[float] = None

    @property
    def area(self) -> int:
        return int(self.bbox.get("width", 0)) * int(self.bbox.get("height", 0))


@dataclass
class VehicleObservation:
    bbox: dict
    score: float
    vehicle_type: str
    crop_jpeg: bytes
    color: Optional[str]
    area_fraction: float
    embedding: Optional[np.ndarray] = None
    model_version: str = VEHICLE_CROP_MODEL_VERSION
    # Same place and look as a recent observation on this camera: a parked
    # vehicle, not the subject of the event (``mark_parked_vehicles``).
    stationary: bool = False

    @property
    def area(self) -> int:
        return int(self.bbox.get("width", 0)) * int(self.bbox.get("height", 0))


@dataclass
class ObjectAnalysis:
    faces: List[FaceObservation] = field(default_factory=list)
    vehicles: List[VehicleObservation] = field(default_factory=list)
    faces_checked: bool = False
    vehicles_checked: bool = False
    frame_grayscale: bool = False
    image_size: Optional[tuple] = None
    elapsed_ms: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not self.faces and not self.vehicles


def decode_image(image_bytes: bytes) -> Optional[np.ndarray]:
    if not image_bytes:
        return None
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    return img


def encode_jpeg(image: np.ndarray, max_side: Optional[int] = None) -> bytes:
    if max_side and max(image.shape[:2]) > max_side:
        scale = max_side / float(max(image.shape[:2]))
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, CROP_JPEG_QUALITY])
    return buf.tobytes() if ok else b""


def _pad_box(bbox: dict, w: int, h: int, padding: float) -> tuple:
    pw, ph = int(bbox["width"] * padding), int(bbox["height"] * padding)
    x0, y0 = max(0, bbox["x"] - pw), max(0, bbox["y"] - ph)
    x1, y1 = min(w, bbox["x"] + bbox["width"] + pw), min(h, bbox["y"] + bbox["height"] + ph)
    return x0, y0, x1, y1


def _detect_vehicle_boxes(image: np.ndarray) -> list:
    """(bbox, score, type) for vehicles, largest first. [] when the model is missing."""
    from app.services.vehicle_detection_service import get_vehicle_detection_service

    detector = get_vehicle_detection_service()
    with _vehicle_net_lock:
        if not detector.is_model_loaded():
            detector._load_model()
        if detector.is_using_fallback():
            return []
        found = detector._detect_vehicles_sync(image, VEHICLE_DETECTION_THRESHOLD)
    h, w = image.shape[:2]
    out = []
    for det in found:
        if det.vehicle_type == "train":
            continue
        bbox = det.bbox.to_dict()
        frac = (bbox["width"] * bbox["height"]) / float(w * h)
        if frac < VEHICLE_MIN_AREA_FRACTION:
            continue
        out.append((bbox, float(det.confidence), det.vehicle_type, frac))
    out.sort(key=lambda item: item[3], reverse=True)
    return out[:MAX_VEHICLES]


def analyze_frame_sync(image: np.ndarray, *, faces: bool, vehicles: bool) -> ObjectAnalysis:
    """CPU part of the analysis (no CLIP). Safe to call from an executor."""
    started = time.monotonic()
    h, w = image.shape[:2]
    gray = frame_is_grayscale(image)
    result = ObjectAnalysis(frame_grayscale=gray, image_size=(w, h))

    if faces:
        result.faces_checked = True
        recognizer = get_face_recognition_service()
        for ident in recognizer.identify(image):
            crop = encode_jpeg(ident.aligned_crop)
            if not crop:
                continue
            result.faces.append(FaceObservation(
                bbox=ident.face.bbox(),
                score=round(ident.face.score, 4),
                embedding=ident.embedding,
                crop_jpeg=crop,
                model_version=recognizer.model_version,
            ))

    if vehicles:
        result.vehicles_checked = True
        for bbox, score, vtype, frac in _detect_vehicle_boxes(image):
            x0, y0, x1, y1 = _pad_box(bbox, w, h, VEHICLE_CROP_PADDING)
            crop_img = image[y0:y1, x0:x1]
            if crop_img.size == 0:
                continue
            tight = image[bbox["y"]: bbox["y"] + bbox["height"], bbox["x"]: bbox["x"] + bbox["width"]]
            crop = encode_jpeg(crop_img, VEHICLE_CROP_MAX_SIDE)
            if not crop:
                continue
            result.vehicles.append(VehicleObservation(
                bbox=bbox,
                score=round(score, 4),
                vehicle_type=vtype,
                crop_jpeg=crop,
                color=dominant_vehicle_color(tight, frame_grayscale=gray),
                area_fraction=round(frac, 5),
            ))

    result.elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    return result


EmbedFn = Callable[[bytes], Awaitable[list]]


async def _default_embed(image_bytes: bytes) -> list:
    from app.services.embedding_service import get_embedding_service

    return await get_embedding_service().generate_embedding(image_bytes)


async def analyze_image_bytes(
    image_bytes: bytes,
    *,
    faces: bool,
    vehicles: bool,
    embed: Optional[EmbedFn] = None,
) -> ObjectAnalysis:
    """Full analysis of an encoded image. Raises nothing; empty on failure."""
    if not image_bytes or not (faces or vehicles):
        return ObjectAnalysis()
    started = time.monotonic()
    loop = asyncio.get_running_loop()
    try:
        image = await loop.run_in_executor(None, decode_image, image_bytes)
        if image is None:
            return ObjectAnalysis()
        result = await loop.run_in_executor(
            None, lambda: analyze_frame_sync(image, faces=faces, vehicles=vehicles)
        )
    except Exception as exc:  # noqa: BLE001 - identity is best-effort
        logger.info(
            "Object analysis failed open",
            extra={"event_type": "object_analysis_failed", "error_type": type(exc).__name__},
        )
        return ObjectAnalysis()

    embed = embed or _default_embed
    for obs in result.vehicles:
        try:
            obs.embedding = normalize(await embed(obs.crop_jpeg))
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "Vehicle crop embedding failed",
                extra={"event_type": "vehicle_crop_embedding_failed", "error_type": type(exc).__name__},
            )
            obs.embedding = None

    result.elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    logger.info(
        "Object analysis complete",
        extra={
            "event_type": "object_analysis_complete",
            "faces": len(result.faces),
            "vehicles": len(result.vehicles),
            "vehicle_colors": [v.color for v in result.vehicles],
            "frame_grayscale": result.frame_grayscale,
            "elapsed_ms": result.elapsed_ms,
        },
    )
    return result
