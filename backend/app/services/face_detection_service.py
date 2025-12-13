"""
Face Detection Service for Person Recognition (Story P4-8.1)

This module provides face detection using OpenCV's DNN face detector.
Detects faces in images, extracts bounding boxes, and crops face regions
for embedding generation.

Architecture:
    - Uses OpenCV's pre-trained DNN face detector (SSD-based)
    - Lazy model loading on first detection request
    - Returns bounding boxes with confidence scores
    - Extracts and resizes face regions for embedding

Privacy:
    - Face data is processed locally only
    - No external API calls for face detection
    - Face recognition must be explicitly enabled in settings
"""
import asyncio
import io
import logging
import os
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    """Bounding box coordinates for a detected face."""
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BoundingBox":
        """Create from dictionary."""
        return cls(
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
        )


@dataclass
class FaceDetection:
    """Result of face detection for a single face."""
    bbox: BoundingBox
    confidence: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "bbox": self.bbox.to_dict(),
            "confidence": self.confidence,
        }


class FaceDetectionService:
    """
    Detect faces in images using OpenCV's DNN face detector.

    Uses the SSD-based face detector which provides good accuracy
    with fast inference (~50ms per image).

    Attributes:
        CONFIDENCE_THRESHOLD: Minimum confidence for valid detection
        TARGET_SIZE: Standard size for cropped face regions
        DEFAULT_PADDING: Padding around detected face (percentage)
    """

    CONFIDENCE_THRESHOLD = 0.5
    TARGET_SIZE = (160, 160)  # Standard face recognition input size
    DEFAULT_PADDING = 0.2  # 20% padding around face

    # Model paths (relative to this file or absolute)
    MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "opencv_face")
    PROTOTXT_FILE = "deploy.prototxt"
    CAFFEMODEL_FILE = "res10_300x300_ssd_iter_140000.caffemodel"

    def __init__(self):
        """Initialize FaceDetectionService with lazy model loading."""
        self._net = None
        self._model_lock = asyncio.Lock()
        self._model_loaded = False

        logger.info(
            "FaceDetectionService initialized",
            extra={
                "event_type": "face_detection_service_init",
                "confidence_threshold": self.CONFIDENCE_THRESHOLD,
                "target_size": self.TARGET_SIZE,
            }
        )

    def _get_model_paths(self) -> tuple[str, str]:
        """Get paths to model files, checking multiple locations."""
        # Try service models directory first
        prototxt_path = os.path.join(self.MODEL_DIR, self.PROTOTXT_FILE)
        caffemodel_path = os.path.join(self.MODEL_DIR, self.CAFFEMODEL_FILE)

        if os.path.exists(prototxt_path) and os.path.exists(caffemodel_path):
            return prototxt_path, caffemodel_path

        # Try backend/models directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        alt_model_dir = os.path.join(backend_dir, "models", "opencv_face")
        alt_prototxt = os.path.join(alt_model_dir, self.PROTOTXT_FILE)
        alt_caffemodel = os.path.join(alt_model_dir, self.CAFFEMODEL_FILE)

        if os.path.exists(alt_prototxt) and os.path.exists(alt_caffemodel):
            return alt_prototxt, alt_caffemodel

        return prototxt_path, caffemodel_path

    def _load_model(self) -> None:
        """
        Load the OpenCV DNN face detector model.

        Raises:
            FileNotFoundError: If model files are not found
            cv2.error: If model loading fails
        """
        prototxt_path, caffemodel_path = self._get_model_paths()

        if not os.path.exists(prototxt_path):
            raise FileNotFoundError(
                f"Face detection model prototxt not found: {prototxt_path}. "
                "Run scripts/download_face_model.py to download the model."
            )

        if not os.path.exists(caffemodel_path):
            raise FileNotFoundError(
                f"Face detection model weights not found: {caffemodel_path}. "
                "Run scripts/download_face_model.py to download the model."
            )

        logger.info(
            "Loading OpenCV face detection model...",
            extra={
                "event_type": "face_model_loading",
                "prototxt": prototxt_path,
                "caffemodel": caffemodel_path,
            }
        )

        self._net = cv2.dnn.readNetFromCaffe(prototxt_path, caffemodel_path)
        self._model_loaded = True

        logger.info(
            "Face detection model loaded successfully",
            extra={"event_type": "face_model_loaded"}
        )

    async def _ensure_model_loaded(self) -> None:
        """Ensure the model is loaded in an async-safe manner."""
        if not self._model_loaded:
            async with self._model_lock:
                if not self._model_loaded:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self._load_model)

    def _bytes_to_cv2(self, image_bytes: bytes) -> np.ndarray:
        """Convert image bytes to OpenCV BGR format."""
        # Load with PIL first (handles various formats)
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Convert to numpy array (RGB)
        np_image = np.array(image)

        # Convert RGB to BGR for OpenCV
        return cv2.cvtColor(np_image, cv2.COLOR_RGB2BGR)

    def _detect_faces_sync(
        self,
        image: np.ndarray,
        confidence_threshold: Optional[float] = None
    ) -> list[FaceDetection]:
        """
        Synchronous face detection on a single image.

        Args:
            image: OpenCV image (BGR format)
            confidence_threshold: Minimum confidence (uses default if None)

        Returns:
            List of FaceDetection objects
        """
        if confidence_threshold is None:
            confidence_threshold = self.CONFIDENCE_THRESHOLD

        (h, w) = image.shape[:2]

        # Create blob from image (resize to 300x300 for SSD)
        blob = cv2.dnn.blobFromImage(
            cv2.resize(image, (300, 300)),
            1.0,
            (300, 300),
            (104.0, 177.0, 123.0)
        )

        # Run inference
        self._net.setInput(blob)
        detections = self._net.forward()

        faces = []

        # Process detections
        for i in range(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]

            if confidence < confidence_threshold:
                continue

            # Get bounding box (scaled to original image size)
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x1, y1, x2, y2) = box.astype("int")

            # Ensure coordinates are within image bounds
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)

            # Calculate width and height
            width = x2 - x1
            height = y2 - y1

            # Skip invalid detections
            if width <= 0 or height <= 0:
                continue

            faces.append(FaceDetection(
                bbox=BoundingBox(x=x1, y=y1, width=width, height=height),
                confidence=float(confidence)
            ))

        return faces

    async def detect_faces(
        self,
        image_bytes: bytes,
        confidence_threshold: Optional[float] = None
    ) -> list[FaceDetection]:
        """
        Detect faces in an image.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, etc.)
            confidence_threshold: Minimum confidence (uses default if None)

        Returns:
            List of FaceDetection objects with bounding boxes and confidence scores

        Raises:
            ValueError: If image_bytes is empty or invalid
        """
        if not image_bytes:
            raise ValueError("image_bytes cannot be empty")

        await self._ensure_model_loaded()

        # Convert to OpenCV format
        image = self._bytes_to_cv2(image_bytes)

        # Run detection in thread pool (CPU-bound)
        loop = asyncio.get_event_loop()
        faces = await loop.run_in_executor(
            None,
            self._detect_faces_sync,
            image,
            confidence_threshold
        )

        logger.debug(
            "Face detection completed",
            extra={
                "event_type": "face_detection_complete",
                "faces_found": len(faces),
                "confidence_threshold": confidence_threshold or self.CONFIDENCE_THRESHOLD,
            }
        )

        return faces

    def _extract_face_sync(
        self,
        image: np.ndarray,
        bbox: BoundingBox,
        padding: float = DEFAULT_PADDING,
        target_size: tuple[int, int] = TARGET_SIZE
    ) -> bytes:
        """
        Extract and resize face region synchronously.

        Args:
            image: OpenCV image (BGR format)
            bbox: Bounding box of the face
            padding: Padding percentage around face
            target_size: Output size for the cropped face

        Returns:
            JPEG bytes of the cropped and resized face
        """
        (h, w) = image.shape[:2]

        # Calculate padded bounding box
        pad_w = int(bbox.width * padding)
        pad_h = int(bbox.height * padding)

        x1 = max(0, bbox.x - pad_w)
        y1 = max(0, bbox.y - pad_h)
        x2 = min(w, bbox.x + bbox.width + pad_w)
        y2 = min(h, bbox.y + bbox.height + pad_h)

        # Crop face region
        face_crop = image[y1:y2, x1:x2]

        # Resize to target size
        face_resized = cv2.resize(face_crop, target_size)

        # Encode to JPEG
        _, buffer = cv2.imencode(".jpg", face_resized)
        return buffer.tobytes()

    async def extract_face_region(
        self,
        image_bytes: bytes,
        bbox: BoundingBox,
        padding: float = DEFAULT_PADDING,
        target_size: tuple[int, int] = TARGET_SIZE
    ) -> bytes:
        """
        Extract and resize a face region from an image.

        Args:
            image_bytes: Raw image bytes
            bbox: Bounding box of the face to extract
            padding: Padding percentage around face (default 20%)
            target_size: Output size for the cropped face

        Returns:
            JPEG bytes of the cropped and resized face

        Raises:
            ValueError: If image_bytes is empty or invalid
        """
        if not image_bytes:
            raise ValueError("image_bytes cannot be empty")

        # Convert to OpenCV format
        image = self._bytes_to_cv2(image_bytes)

        # Extract in thread pool
        loop = asyncio.get_event_loop()
        face_bytes = await loop.run_in_executor(
            None,
            self._extract_face_sync,
            image,
            bbox,
            padding,
            target_size
        )

        return face_bytes

    def is_model_loaded(self) -> bool:
        """Check if the face detection model is loaded."""
        return self._model_loaded


# Global singleton instance
_face_detection_service: Optional[FaceDetectionService] = None


def get_face_detection_service() -> FaceDetectionService:
    """
    Get the global FaceDetectionService instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        FaceDetectionService singleton instance
    """
    global _face_detection_service

    if _face_detection_service is None:
        _face_detection_service = FaceDetectionService()
        logger.info(
            "Global FaceDetectionService instance created",
            extra={"event_type": "face_detection_service_singleton_created"}
        )

    return _face_detection_service
