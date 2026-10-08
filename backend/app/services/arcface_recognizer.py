"""
Optional ArcFace face recognizer (``ARGUS_FACE_RECOGNIZER=arcface``).

SFace stays the default. ArcFace (InsightFace ``w600k_r50``, ResNet-50
trained on WebFace600K) is a stronger identity model, but its published
weights are licensed for **non-commercial research use only**. So:

* the weights are never in the repo and never downloaded automatically;
  the user puts the ONNX file in place themselves (see the entities docs);
* the file is checked against a SHA-256 before it is loaded: the pinned
  hash of InsightFace's ``buffalo_l`` release, or ``ARGUS_ARCFACE_SHA256``
  for another export. A file that does not match is refused;
* when ArcFace is selected but the weights are missing or do not match,
  the default SFace backend is used instead (with a warning), so face
  matching keeps working against the SFace references.

Detection and alignment reuse YuNet (MIT) and the standard ArcFace 112x112
five-point template, which is the same template OpenCV's
``FaceRecognizerSF.alignCrop`` uses. The aligned crops stored for SFace
galleries are therefore valid ArcFace input too, which is what
``scripts/reembed_face_gallery.py`` relies on when switching models.

Inference runs on OpenCV's DNN module (``cv2.dnn.readNetFromONNX``): no new
Python dependency.

Every embedding is stored with ``model_version`` (``arcface-w600k-r50-v1``)
and galleries only compare vectors of the active model, so ArcFace and
SFace references never mix.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from app.services.face_recognition_service import (
    FACE_MODEL_DIR_ENV,
    YUNET_FILE,
    DetectedFace,
    FaceIdentity,
    FaceRecognitionService,
    face_model_search_dirs,
    normalize,
)

logger = logging.getLogger(__name__)

ARCFACE_NAME = "arcface"
ARCFACE_MODEL_VERSION = "arcface-w600k-r50-v1"
ARCFACE_DIM = 512
ARCFACE_FILE = "w600k_r50.onnx"
# SHA-256 of w600k_r50.onnx inside InsightFace's buffalo_l.zip (v0.7 release).
ARCFACE_SHA256 = "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43"
ARCFACE_MODEL_ENV = "ARGUS_ARCFACE_MODEL_PATH"
ARCFACE_SHA256_ENV = "ARGUS_ARCFACE_SHA256"
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Standard ArcFace alignment template for a 112x112 crop (also used by
# OpenCV's FaceRecognizerSF.alignCrop).
ARCFACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def _setting(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        try:
            from app.core.config import settings

            value = getattr(settings, name, None)
        except Exception:  # noqa: BLE001
            value = None
    return str(value).strip() if value is not None and str(value).strip() else None


def arcface_model_path() -> Path:
    """Configured weights path, else ``<face model dir>/arcface/w600k_r50.onnx``."""
    configured = _setting(ARCFACE_MODEL_ENV)
    if configured:
        return Path(configured)
    return _BACKEND_DIR / "app" / "models" / "arcface" / ARCFACE_FILE


def expected_sha256() -> str:
    return (_setting(ARCFACE_SHA256_ENV) or ARCFACE_SHA256).lower()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_weights(path: Optional[Path] = None) -> tuple:
    """(ok, reason) for the weights file. Reads the whole file once."""
    path = path or arcface_model_path()
    if not path.is_file():
        return False, "missing"
    try:
        actual = file_sha256(path)
    except OSError:
        return False, "unreadable"
    if actual != expected_sha256():
        return False, "checksum_mismatch"
    return True, "ok"


def _yunet_path() -> Optional[str]:
    for d in face_model_search_dirs():
        if (d / YUNET_FILE).is_file():
            return str(d / YUNET_FILE)
    return None


def align_face(image: np.ndarray, row: np.ndarray) -> Optional[np.ndarray]:
    """112x112 crop aligned on YuNet's five landmarks (ArcFace template)."""
    src = np.asarray(row[4:14], dtype=np.float32).reshape(5, 2)
    matrix, _ = cv2.estimateAffinePartial2D(src, ARCFACE_TEMPLATE, method=cv2.LMEDS)
    if matrix is None:
        return None
    return cv2.warpAffine(image, matrix, (112, 112), borderValue=0.0)


class ArcFaceRecognizer:
    """YuNet detection + ArcFace w600k_r50 embeddings. Thread-safe."""

    name = ARCFACE_NAME
    model_version = ARCFACE_MODEL_VERSION
    dim = ARCFACE_DIM
    # Cosine for "same person" in ArcFace space. InsightFace's verification
    # operating points sit around 0.25-0.35; 0.36 starts on the strict side,
    # like SFace's 0.40. Tune with ARGUS_FACE_MATCH_THRESHOLD.
    default_match_threshold = 0.36

    def __init__(
        self,
        model_path: Optional[str] = None,
        yunet_path: Optional[str] = None,
        net=None,
        detector=None,
        verified: bool = False,
    ):
        self._model_path = model_path
        # The factory already checked the SHA-256; don't hash 170 MB twice.
        self._verified = verified
        self._yunet_path = yunet_path
        self._net = net
        self._detector = detector
        self._loaded = net is not None and detector is not None
        self._available = self._loaded
        # Reuse the SFace service's detection code with our own YuNet instance.
        self._detect_helper = FaceRecognitionService()
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = Path(self._model_path) if self._model_path else arcface_model_path()
        ok, reason = (path.is_file(), "missing") if self._verified else verify_weights(path)
        yunet = self._yunet_path or _yunet_path()
        if not ok or not yunet:
            logger.warning(
                "ArcFace weights or YuNet detector unavailable - face matching is DISABLED for ArcFace",
                extra={"event_type": "arcface_model_unavailable", "reason": reason if not ok else "yunet_missing"},
            )
            return
        self._net = cv2.dnn.readNetFromONNX(str(path))
        self._detector = cv2.FaceDetectorYN.create(yunet, "", (320, 320), 0.8, 0.3, 50)
        self._available = True
        logger.info(
            "ArcFace face recognizer loaded",
            extra={"event_type": "arcface_model_loaded", "model_version": ARCFACE_MODEL_VERSION},
        )

    def is_available(self) -> bool:
        with self._lock:
            self._load()
            return self._available

    def _embed_locked(self, aligned: np.ndarray) -> Optional[np.ndarray]:
        if aligned is None or aligned.size == 0:
            return None
        if aligned.shape[:2] != (112, 112):
            aligned = cv2.resize(aligned, (112, 112))
        blob = cv2.dnn.blobFromImage(aligned, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        self._net.setInput(blob)
        return normalize(self._net.forward())

    def detect(self, image: np.ndarray) -> List[DetectedFace]:
        with self._lock:
            self._load()
            if not self._available or image is None or image.size == 0:
                return []
            return self._detect_locked(image)

    def _detect_locked(self, image: np.ndarray) -> List[DetectedFace]:
        helper = self._detect_helper
        helper._detector = self._detector
        return helper._detect_locked(image)

    def identify(self, image: np.ndarray, faces: Optional[List[DetectedFace]] = None) -> List[FaceIdentity]:
        with self._lock:
            self._load()
            if not self._available or image is None or image.size == 0:
                return []
            if faces is None:
                faces = self._detect_locked(image)
            out = []
            for face in faces:
                aligned = align_face(image, face.row)
                vec = self._embed_locked(aligned) if aligned is not None else None
                if vec is None:
                    continue
                out.append(FaceIdentity(face=face, embedding=vec, aligned_crop=aligned))
            return out

    def embed_aligned(self, aligned_crop: np.ndarray) -> Optional[np.ndarray]:
        """Embedding of a stored 112x112 aligned crop (re-embedding a gallery)."""
        with self._lock:
            self._load()
            if not self._available:
                return None
            return self._embed_locked(aligned_crop)


def create_arcface_or_default():
    """Factory for ``ARGUS_FACE_RECOGNIZER=arcface``.

    Returns the ArcFace backend when its weights verify, else the default
    SFace backend, so a missing or wrong file never silently disables faces.
    """
    path = arcface_model_path()
    ok, reason = verify_weights(path)
    if ok:
        return ArcFaceRecognizer(model_path=str(path), verified=True)
    logger.warning(
        "ARGUS_FACE_RECOGNIZER=arcface but the weights are not usable; using SFace. Put "
        f"{ARCFACE_FILE} at {ARCFACE_MODEL_ENV} (or backend/app/models/arcface/) and check its SHA-256.",
        extra={"event_type": "arcface_fallback_to_sface", "reason": reason, "model_dir_env": FACE_MODEL_DIR_ENV},
    )
    return FaceRecognitionService()
