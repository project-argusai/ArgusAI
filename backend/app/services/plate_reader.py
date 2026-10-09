"""
License-plate reading and keyed hashing for known-vehicle matching.

Privacy model (the reason this module is shaped the way it is):

* A plate is only ever handled as a *keyed hash*: HMAC-SHA256 with the
  ``PLATE_HASH_SALT`` secret over the normalised plate text. ``PlateReader.read``
  hashes each OCR result inside this module and returns only the hash and a
  confidence; the text never leaves the function, is never logged, and is
  never written anywhere.
* Without the salt, nothing is read: the feature stays off rather than fall
  back to an unkeyed (and therefore brute-forceable) hash.
* Which hashes are kept is decided by ``entity_plate_service``: only hashes
  of plates on saved vehicles. Every other read is dropped right after the
  comparison.

Models: fast-alpr (MIT) with the open-image-models YOLOv9-t plate detector
and the fast-plate-ocr CCT-XS global OCR model (both MIT). The weights are
downloaded by ``scripts/download_vehicle_model.py --only plate``, pinned by
SHA-256; fast-alpr's own hub download is never used. The Python packages
are optional (``requirements-plates.txt``): with them missing, plate
matching simply reports "no opinion".

Loading the models takes about a second, so the live path never waits for
it: the first call starts a background load and returns no reads.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

HASH_VERSION = "hmac-sha256-v1"
MIN_SALT_LENGTH = 16
# Live reads shorter than this are usually a partial plate (one half cut off).
MIN_READ_LENGTH = 4
# A saved plate (typed by a user) may be a short vanity plate.
MIN_PLATE_LENGTH = 2
MAX_PLATE_LENGTH = 10
MAX_PLATES_PER_IMAGE = 2

DETECTOR_FILE = "yolo-v9-t-384-license-plates-end2end.onnx"
OCR_FILE = "cct_xs_v2_global.onnx"
OCR_CONFIG_FILE = "cct_xs_v2_global_plate_config.yaml"
DETECTOR_CONFIDENCE = 0.4
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# OCR mixes up these glyphs more than any others, and plate issuers avoid
# relying on them; folding them makes a hash survive the most common misread.
_FOLD = str.maketrans({"O": "0", "Q": "0", "I": "1"})
_NOT_ALNUM = re.compile(r"[^A-Z0-9]")


def _settings():
    from app.core.config import settings

    return settings


def normalize_plate(text: Optional[str], *, min_length: int = MIN_PLATE_LENGTH) -> Optional[str]:
    """Upper-case letters and digits only, with O/Q->0 and I->1. None if unusable."""
    if not isinstance(text, str):
        return None
    cleaned = _NOT_ALNUM.sub("", text.upper()).translate(_FOLD)
    if not (min_length <= len(cleaned) <= MAX_PLATE_LENGTH):
        return None
    return cleaned


def hash_key() -> Optional[bytes]:
    """The HMAC key from ``PLATE_HASH_SALT``, or None when unset or too short."""
    raw = getattr(_settings(), "PLATE_HASH_SALT", None)
    if raw is None:
        return None
    value = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw)
    value = value.strip()
    if len(value) < MIN_SALT_LENGTH:
        return None
    return value.encode("utf-8")


def key_id(key: Optional[bytes] = None) -> Optional[str]:
    """A short public fingerprint of the key, stored with each hash.

    Lets the app tell saved hashes made with an older salt (which can never
    match again) from current ones, without revealing the salt.
    """
    key = key if key is not None else hash_key()
    if not key:
        return None
    return hmac.new(key, b"argus-plate-key-id", hashlib.sha256).hexdigest()[:12]


def hash_plate(text: Optional[str], key: Optional[bytes] = None, *, min_length: int = MIN_PLATE_LENGTH) -> Optional[str]:
    """Keyed hash of a plate, or None (bad text or no key). Never logs the text."""
    key = key if key is not None else hash_key()
    norm = normalize_plate(text, min_length=min_length)
    if not key or not norm:
        return None
    return hmac.new(key, f"{HASH_VERSION}:{norm}".encode("ascii"), hashlib.sha256).hexdigest()


def plates_enabled() -> bool:
    """Feature flag on and a usable salt configured."""
    s = _settings()
    if not bool(getattr(s, "PLATE_RECOGNITION_ENABLED", False)):
        return False
    if hash_key() is None:
        _warn_once(
            "no_salt",
            "PLATE_RECOGNITION_ENABLED is set but PLATE_HASH_SALT is missing or shorter than "
            f"{MIN_SALT_LENGTH} characters; plate matching stays off.",
        )
        return False
    return True


_warned: set = set()


def _warn_once(key: str, message: str) -> None:
    if key in _warned:
        return
    _warned.add(key)
    logger.warning(message, extra={"event_type": "plate_recognition_config", "reason": key})


@dataclass(frozen=True)
class PlateRead:
    """One plate read on an image: keyed hash and OCR confidence, no text."""

    plate_hash: str
    confidence: float  # weakest character probability of the read
    length: int


def model_dir() -> Path:
    configured = getattr(_settings(), "PLATE_MODEL_DIR", None)
    if configured and str(configured).strip():
        return Path(str(configured).strip())
    return _BACKEND_DIR / "app" / "models" / "plates"


def _read_confidence(confidence, length: int) -> float:
    """Weakest probability over the plate's characters (pad slots ignored)."""
    if isinstance(confidence, (int, float)):
        return float(confidence)
    try:
        values = [float(c) for c in list(confidence)[: max(length, 1)]]
    except (TypeError, ValueError):
        return 0.0
    return min(values) if values else 0.0


class PlateReader:
    """Lazy fast-alpr pipeline (detector + OCR). Thread-safe."""

    def __init__(self, alpr=None):
        self._alpr = alpr
        self._state = "ready" if alpr is not None else "idle"  # idle | loading | ready | unavailable
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def _build(self):
        directory = model_dir()
        det, ocr, cfg = directory / DETECTOR_FILE, directory / OCR_FILE, directory / OCR_CONFIG_FILE
        missing = [p.name for p in (det, ocr, cfg) if not p.is_file()]
        if missing:
            raise FileNotFoundError(f"plate model files missing: {', '.join(missing)}")
        from fast_alpr import ALPR
        from fast_alpr.base import BaseDetector
        from fast_alpr.default_ocr import DefaultOCR
        from open_image_models.detection.core.yolo_v9.inference import YoloV9Detector

        detector = YoloV9Detector(
            det,
            class_labels=["License Plate"],
            conf_thresh=DETECTOR_CONFIDENCE,
            providers=["CPUExecutionProvider"],
        )

        class _LocalDetector(BaseDetector):
            def predict(self, frame):
                return detector.predict(frame)

        ocr_model = DefaultOCR(hub_ocr_model=None, device="cpu", model_path=ocr, config_path=cfg)
        return ALPR(detector=_LocalDetector(), ocr=ocr_model)

    def load(self) -> bool:
        """Load the models now (blocking; enrollment path). True when ready."""
        with self._lock:
            if self._state in ("ready", "unavailable"):
                return self._state == "ready"
            self._state = "loading"
        return self._do_load()

    def ensure_loading(self) -> bool:
        """True when ready; otherwise starts a background load (once) and returns False."""
        with self._lock:
            if self._state == "ready":
                return True
            if self._state != "idle":
                return False
            self._state = "loading"
        threading.Thread(target=self._do_load, name="plate-model-load", daemon=True).start()
        return False

    def _do_load(self) -> bool:
        try:
            alpr = self._build()
        except Exception as exc:  # noqa: BLE001 - missing package or weights: feature reports no opinion
            with self._lock:
                self._state = "unavailable"
            logger.warning(
                "Plate recognition models unavailable; plate matching stays inactive. Install "
                "requirements-plates.txt and run `python scripts/download_vehicle_model.py --only plate`.",
                extra={"event_type": "plate_model_unavailable", "error_type": type(exc).__name__},
            )
            return False
        with self._lock:
            self._alpr, self._state = alpr, "ready"
        logger.info("Plate recognition models loaded", extra={"event_type": "plate_model_loaded"})
        return True

    def read(self, image: np.ndarray, key: bytes, *, min_length: int = MIN_READ_LENGTH) -> List[PlateRead]:
        """Plates on a BGR image as keyed hashes. [] when not ready or nothing usable."""
        if self._state != "ready" or image is None or getattr(image, "size", 0) == 0:
            return []
        with self._run_lock:
            results = self._alpr.predict(image)
        reads: List[PlateRead] = []
        for result in results or []:
            ocr = getattr(result, "ocr", None)
            text = getattr(ocr, "text", None)
            norm = normalize_plate(text, min_length=min_length)
            if norm is None:
                continue
            length = len(norm)
            digest = hash_plate(norm, key, min_length=min_length)
            confidence = _read_confidence(getattr(ocr, "confidence", 0.0), length)
            del text, norm  # the plain text goes no further than this loop
            if digest:
                reads.append(PlateRead(digest, round(confidence, 4), length))
            if len(reads) >= MAX_PLATES_PER_IMAGE:
                break
        return reads


_reader: Optional[PlateReader] = None
_reader_lock = threading.Lock()


def get_plate_reader() -> PlateReader:
    global _reader
    with _reader_lock:
        if _reader is None:
            _reader = PlateReader()
        return _reader


def reset_plate_reader(reader: Optional[PlateReader] = None) -> None:
    global _reader
    with _reader_lock:
        _reader = reader


def read_vehicle_plates(crops: Sequence[np.ndarray], *, budget_ms: Optional[float] = None) -> List[List[PlateRead]]:
    """Plate reads for each vehicle crop, live-path rules. Never raises.

    Returns one list per crop (empty when off, not loaded yet, over budget,
    or on any error), so callers can zip it with their observations.
    """
    out: List[List[PlateRead]] = [[] for _ in crops]
    if not crops or not plates_enabled():
        return out
    key = hash_key()
    reader = get_plate_reader()
    if not key or not reader.ensure_loading():
        return out
    budget = float(budget_ms if budget_ms is not None else getattr(_settings(), "PLATE_TIME_BUDGET_MS", 800))
    started = time.monotonic()
    for i, crop in enumerate(crops):
        if (time.monotonic() - started) * 1000.0 >= budget:
            logger.debug("Plate read budget spent", extra={"event_type": "plate_budget_spent", "read": i})
            break
        try:
            out[i] = reader.read(crop, key)
        except Exception as exc:  # noqa: BLE001 - a plate read is optional evidence
            logger.debug("Plate read failed open", extra={"event_type": "plate_read_failed", "error_type": type(exc).__name__})
            out[i] = []
    return out
