"""
Face detection + identity embeddings with YuNet and SFace (OpenCV Model Zoo).

Why this exists: the older face path ran a ResNet-10 SSD detector and then a
CLIP embedding of the face crop. CLIP is not an identity model, and the crop
was compared with a person's whole-frame reference vector, so person matching
could not work. YuNet gives a box plus five landmarks, SFace aligns the face
to 112x112 from those landmarks and returns a 128-d identity embedding that is
compared face-to-face against a per-person gallery.

Both models run on OpenCV's DNN module (``cv2.FaceDetectorYN`` and
``cv2.FaceRecognizerSF``, present in the pinned OpenCV 4.x), so there is no
new Python dependency. Weights: ``scripts/download_vehicle_model.py --only face``
(YuNet MIT, SFace Apache-2.0), pinned by SHA-256.

Everything here is synchronous and CPU-bound. Callers run it in an executor
and must treat a missing model as "no faces" (fail-open).

Pluggable: callers use ``get_face_recognition_service()``, which returns the
recognizer named by ``ARGUS_FACE_RECOGNIZER`` (built-in: ``sface``, the
default, and the opt-in ``arcface`` with user-supplied weights, see
``arcface_recognizer``). Another backend implements ``FaceRecognizer`` and registers with
``register_face_recognizer``. Every embedding is stored with the backend's
``model_version`` and galleries only compare vectors of the active version,
so switching backends never mixes vector spaces; the stored 112x112 aligned
crops can be re-embedded with ``embed_aligned``.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Tuple, runtime_checkable

import cv2
import numpy as np

logger = logging.getLogger(__name__)

FACE_MODEL_DIR_ENV = "ARGUS_FACE_MODEL_DIR"
YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Stored with every embedding so a later model swap never mixes vector spaces.
SFACE_MODEL_VERSION = "sface-2021dec-v1"
SFACE_DIM = 128

# YuNet keeps faces scoring at least this. The model's own default is 0.9;
# 0.8 keeps slightly harder doorbell angles while still rejecting textures.
DETECTION_SCORE_THRESHOLD = 0.8
NMS_THRESHOLD = 0.3
# Faces narrower than this (in source pixels) are not embedded: SFace on a
# 20-30 px face is mostly noise and would only produce false matches.
MIN_FACE_PX = 40
# YuNet runs on a downscaled copy. Faces at the doors stay well above
# MIN_FACE_PX at this size, and it keeps detection to a few ms.
DETECT_MAX_SIDE = 1280
MAX_FACES = 5


def face_model_search_dirs() -> List[Path]:
    dirs = []
    env_dir = os.environ.get(FACE_MODEL_DIR_ENV)
    if env_dir:
        dirs.append(Path(env_dir))
    dirs.append(_BACKEND_DIR / "app" / "models" / "opencv_zoo")
    return dirs


def resolve_face_model_paths() -> Tuple[Optional[str], Optional[str]]:
    """Return (yunet, sface) from the first directory that has both."""
    for d in face_model_search_dirs():
        det, rec = d / YUNET_FILE, d / SFACE_FILE
        if det.is_file() and rec.is_file():
            return str(det), str(rec)
    return None, None


@dataclass
class DetectedFace:
    """One face in source-image pixels."""

    x: int
    y: int
    width: int
    height: int
    score: float
    # YuNet row (box, 5 landmarks, score) in source coordinates; SFace needs it to align.
    row: np.ndarray

    def bbox(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class FaceIdentity:
    face: DetectedFace
    embedding: np.ndarray  # L2-normalised, SFACE_DIM floats
    aligned_crop: np.ndarray  # 112x112 BGR, exactly what SFace saw


def normalize(vec) -> Optional[np.ndarray]:
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if not np.isfinite(norm) or norm == 0.0:
        return None
    return arr / norm


@runtime_checkable
class FaceRecognizer(Protocol):
    """What the gallery and live path need from a face backend."""

    name: str
    model_version: str  # stored with every embedding
    dim: int
    # Cosine a gallery match must reach for this backend's vector space.
    default_match_threshold: float

    def is_available(self) -> bool: ...

    def identify(self, image: np.ndarray) -> List["FaceIdentity"]: ...

    def embed_aligned(self, aligned_crop: np.ndarray) -> Optional[np.ndarray]: ...


class FaceRecognitionService:
    """Lazy-loaded YuNet detector + SFace recognizer. Thread-safe. The default backend."""

    name = "sface"
    model_version = SFACE_MODEL_VERSION
    dim = SFACE_DIM
    # OpenCV publishes 0.363 for SFace on LFW; 0.40 is a little stricter
    # (LFW impostor FPR 0.03% per pair, see the PR / docs).
    default_match_threshold = 0.40

    def __init__(self, yunet_path: Optional[str] = None, sface_path: Optional[str] = None):
        self._paths = (yunet_path, sface_path)
        self._detector = None
        self._recognizer = None
        self._loaded = False
        self._available = False
        # cv2 DNN objects keep per-call state (input size), so one call at a time.
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._loaded:
            return
        yunet, sface = self._paths
        if not yunet or not sface:
            yunet, sface = resolve_face_model_paths()
        if not yunet or not sface:
            logger.warning(
                "Face recognition models not found - face matching is DISABLED. Run "
                "`python scripts/download_vehicle_model.py --only face` or set "
                f"{FACE_MODEL_DIR_ENV}.",
                extra={
                    "event_type": "face_recognition_model_missing",
                    "searched_dirs": [str(d) for d in face_model_search_dirs()],
                },
            )
            self._loaded = True
            return
        self._detector = cv2.FaceDetectorYN.create(
            yunet, "", (320, 320), DETECTION_SCORE_THRESHOLD, NMS_THRESHOLD, 50
        )
        self._recognizer = cv2.FaceRecognizerSF.create(sface, "")
        self._available = True
        self._loaded = True
        logger.info(
            "Face recognition models loaded (YuNet + SFace)",
            extra={"event_type": "face_recognition_model_loaded", "model_version": SFACE_MODEL_VERSION},
        )

    def is_available(self) -> bool:
        with self._lock:
            self._load()
            return self._available

    def detect(self, image: np.ndarray) -> List[DetectedFace]:
        """Faces in a BGR image, largest first, at most ``MAX_FACES``."""
        with self._lock:
            self._load()
            if not self._available or image is None or image.size == 0:
                return []
            return self._detect_locked(image)

    def _detect_locked(self, image: np.ndarray) -> List[DetectedFace]:
        h, w = image.shape[:2]
        scale = min(1.0, DETECT_MAX_SIDE / float(max(h, w)))
        small = image if scale == 1.0 else cv2.resize(
            image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA
        )
        sh, sw = small.shape[:2]
        self._detector.setInputSize((sw, sh))
        _, rows = self._detector.detect(small)
        if rows is None:
            return []
        faces = []
        for raw in rows:
            row = np.array(raw, dtype=np.float32).copy()
            row[:14] /= scale  # box + landmarks back to source pixels
            x, y, fw, fh = (int(round(v)) for v in row[:4])
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(w, x + fw), min(h, y + fh)
            if x1 - x0 < MIN_FACE_PX or y1 - y0 < MIN_FACE_PX:
                continue
            faces.append(DetectedFace(x0, y0, x1 - x0, y1 - y0, float(row[14]), row))
        faces.sort(key=lambda f: f.width * f.height, reverse=True)
        return faces[:MAX_FACES]

    def identify(self, image: np.ndarray, faces: Optional[List[DetectedFace]] = None) -> List[FaceIdentity]:
        """Detect (unless ``faces`` given), align, and embed every usable face."""
        with self._lock:
            self._load()
            if not self._available or image is None or image.size == 0:
                return []
            if faces is None:
                faces = self._detect_locked(image)
            out = []
            for face in faces:
                aligned = self._recognizer.alignCrop(image, face.row)
                vec = normalize(self._recognizer.feature(aligned))
                if vec is None:
                    continue
                out.append(FaceIdentity(face=face, embedding=vec, aligned_crop=aligned))
            return out

    def embed_aligned(self, aligned_crop: np.ndarray) -> Optional[np.ndarray]:
        """Embedding of a stored 112x112 aligned crop (re-embedding a gallery)."""
        with self._lock:
            self._load()
            if not self._available or aligned_crop is None or aligned_crop.size == 0:
                return None
            if aligned_crop.shape[:2] != (112, 112):
                aligned_crop = cv2.resize(aligned_crop, (112, 112))
            return normalize(self._recognizer.feature(aligned_crop))


FACE_RECOGNIZER_ENV = "ARGUS_FACE_RECOGNIZER"
DEFAULT_FACE_RECOGNIZER = "sface"

def _arcface_factory() -> FaceRecognizer:
    # Opt-in, user-supplied weights (non-commercial licence); see arcface_recognizer.
    from app.services.arcface_recognizer import create_arcface_or_default

    return create_arcface_or_default()


_RECOGNIZERS: Dict[str, Callable[[], FaceRecognizer]] = {
    "sface": FaceRecognitionService,
    "arcface": _arcface_factory,
}
_service: Optional[FaceRecognizer] = None
_service_lock = threading.Lock()


def configured_face_recognizer() -> Optional[str]:
    """``ARGUS_FACE_RECOGNIZER`` from the process environment, else from settings (.env)."""
    value = os.environ.get(FACE_RECOGNIZER_ENV)
    if value and value.strip():
        return value.strip()
    try:
        from app.core.config import settings

        value = getattr(settings, FACE_RECOGNIZER_ENV, None)
    except Exception:  # noqa: BLE001
        value = None
    return value.strip() if isinstance(value, str) and value.strip() else None


def register_face_recognizer(name: str, factory: Callable[[], FaceRecognizer]) -> None:
    """Make a face backend selectable with ``ARGUS_FACE_RECOGNIZER=<name>``."""
    with _service_lock:
        _RECOGNIZERS[name.strip().lower()] = factory


def get_face_recognition_service() -> FaceRecognizer:
    """The active face backend (created lazily; models load on first use)."""
    global _service
    with _service_lock:
        if _service is None:
            name = (configured_face_recognizer() or DEFAULT_FACE_RECOGNIZER).strip().lower()
            if name not in _RECOGNIZERS:
                logger.warning(
                    "Unknown face recognizer; using the default",
                    extra={"event_type": "face_recognizer_unknown", "requested": name,
                           "default": DEFAULT_FACE_RECOGNIZER},
                )
                name = DEFAULT_FACE_RECOGNIZER
            _service = _RECOGNIZERS[name]()
        return _service


def active_face_model() -> Tuple[str, int]:
    """(model_version, dim) of the active backend. Does not load model weights."""
    svc = get_face_recognition_service()
    return svc.model_version, svc.dim


def reset_face_recognition_service() -> None:
    global _service
    with _service_lock:
        _service = None
