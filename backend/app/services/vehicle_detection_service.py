"""
Vehicle Detection Service for Vehicle Recognition (Story P4-8.3)

This module provides vehicle detection using OpenCV's DNN with MobileNet-SSD.
Detects vehicles in images, extracts bounding boxes, and crops vehicle regions
for embedding generation.

Architecture:
    - Uses OpenCV's pre-trained MobileNet-SSD model (COCO classes)
    - Lazy model loading on first detection request
    - Returns bounding boxes with confidence scores
    - Extracts and resizes vehicle regions for embedding

Vehicle Classes (COCO):
    - car (class 7)
    - motorcycle (class 4)
    - bus (class 6)
    - truck (class 8)

Migrated to @singleton: Story P14-5.3
"""
import asyncio
import base64
import io
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from app.core.decorators import singleton

logger = logging.getLogger(__name__)

# Vehicle class IDs in COCO/VOC datasets
VEHICLE_CLASSES = {
    7: "car",
    4: "motorcycle",
    6: "bus",
    8: "truck",
    # MobileNet-SSD VOC classes
    "car": 7,
    "motorbike": 4,
    "bus": 6,
}

# Class names for MobileNet-SSD trained on VOC (indices 0-20)
VOC_CLASSES = [
    "background", "aeroplane", "bicycle", "bird", "boat",
    "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
    "dog", "horse", "motorbike", "person", "pottedplant",
    "sheep", "sofa", "train", "tvmonitor"
]

# Vehicle class indices in VOC classes
VOC_VEHICLE_INDICES = {
    6: "bus",
    7: "car",
    14: "motorbike",
    19: "train",  # Include trains as vehicles
}


@dataclass
class BoundingBox:
    """Bounding box coordinates for a detected vehicle."""
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
class VehicleDetection:
    """Result of vehicle detection for a single vehicle."""
    bbox: BoundingBox
    confidence: float
    vehicle_type: str  # "car", "truck", "bus", "motorcycle"


@singleton
class VehicleDetectionService:
    """
    Detect vehicles in images using OpenCV's DNN.

    Uses MobileNet-SSD which provides good accuracy with fast inference.
    Falls back to simple object detection if model files aren't available.

    Attributes:
        CONFIDENCE_THRESHOLD: Minimum confidence for valid detection
        TARGET_SIZE: Standard size for cropped vehicle regions
        DEFAULT_PADDING: Padding around detected vehicle (percentage)
    """

    CONFIDENCE_THRESHOLD = 0.50
    TARGET_SIZE = (224, 224)  # Standard size for CLIP
    DEFAULT_PADDING = 0.1  # 10% padding

    def __init__(self):
        """Initialize VehicleDetectionService."""
        self._net: Optional[cv2.dnn.Net] = None
        self._model_loaded = False
        self._use_fallback = False  # True if model files not available

        logger.info(
            "VehicleDetectionService initialized",
            extra={
                "event_type": "vehicle_detection_service_init",
                "confidence_threshold": self.CONFIDENCE_THRESHOLD,
                "target_size": self.TARGET_SIZE,
            }
        )

    def _load_model(self) -> None:
        """
        Load the OpenCV DNN vehicle detector model.

        Uses MobileNet-SSD trained on VOC/COCO.
        Falls back to simple detection if model files not found.
        """
        if self._model_loaded:
            return

        # Model file paths (MobileNet-SSD trained on VOC)
        model_dir = os.path.join(os.path.dirname(__file__), "..", "..", "models")
        prototxt_path = os.path.join(model_dir, "MobileNetSSD_deploy.prototxt")
        caffemodel_path = os.path.join(model_dir, "MobileNetSSD_deploy.caffemodel")

        if not os.path.exists(prototxt_path) or not os.path.exists(caffemodel_path):
            logger.warning(
                "Vehicle detection model files not found - using fallback mode",
                extra={
                    "event_type": "vehicle_model_fallback",
                    "prototxt": prototxt_path,
                    "caffemodel": caffemodel_path,
                }
            )
            self._use_fallback = True
            self._model_loaded = True
            return

        logger.info(
            "Loading OpenCV vehicle detection model...",
            extra={
                "event_type": "vehicle_model_loading",
                "prototxt": prototxt_path,
                "caffemodel": caffemodel_path,
            }
        )

        self._net = cv2.dnn.readNetFromCaffe(prototxt_path, caffemodel_path)
        self._model_loaded = True

        logger.info(
            "Vehicle detection model loaded successfully",
            extra={"event_type": "vehicle_model_loaded"}
        )

    def _bytes_to_cv2(self, image_bytes: bytes) -> np.ndarray:
        """
        Convert image bytes to OpenCV format.

        Args:
            image_bytes: Raw image bytes (JPEG/PNG)

        Returns:
            OpenCV BGR image array
        """
        # Decode with PIL first (handles more formats)
        image = Image.open(io.BytesIO(image_bytes))
        np_image = np.array(image)

        # Handle grayscale images
        if len(np_image.shape) == 2:
            np_image = cv2.cvtColor(np_image, cv2.COLOR_GRAY2BGR)
        # Handle RGBA images
        elif np_image.shape[2] == 4:
            np_image = cv2.cvtColor(np_image, cv2.COLOR_RGBA2BGR)
        else:
            # Convert RGB to BGR for OpenCV
            np_image = cv2.cvtColor(np_image, cv2.COLOR_RGB2BGR)

        return np_image

    def _detect_vehicles_sync(
        self,
        image: np.ndarray,
        confidence_threshold: Optional[float] = None
    ) -> list[VehicleDetection]:
        """
        Synchronous vehicle detection on a single image.

        Args:
            image: OpenCV image (BGR format)
            confidence_threshold: Minimum confidence (defaults to CONFIDENCE_THRESHOLD)

        Returns:
            List of VehicleDetection results
        """
        if confidence_threshold is None:
            confidence_threshold = self.CONFIDENCE_THRESHOLD

        if self._use_fallback:
            # Fallback: return empty list (vehicles will be detected by AI description)
            return []

        (h, w) = image.shape[:2]

        # Create blob from image
        blob = cv2.dnn.blobFromImage(
            cv2.resize(image, (300, 300)),
            0.007843,
            (300, 300),
            127.5
        )

        # Run inference
        self._net.setInput(blob)
        detections = self._net.forward()

        vehicles = []

        # Process detections
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]

            if confidence < confidence_threshold:
                continue

            # Get class ID
            class_id = int(detections[0, 0, i, 1])

            # Check if it's a vehicle class
            if class_id not in VOC_VEHICLE_INDICES:
                continue

            vehicle_type = VOC_VEHICLE_INDICES[class_id]

            # Get bounding box (scaled to original image size)
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x1, y1, x2, y2) = box.astype("int")

            # Ensure coordinates are within image bounds
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)

            width = x2 - x1
            height = y2 - y1

            # Skip invalid detections
            if width <= 0 or height <= 0:
                continue

            bbox = BoundingBox(x=x1, y=y1, width=width, height=height)
            vehicles.append(VehicleDetection(
                bbox=bbox,
                confidence=float(confidence),
                vehicle_type=vehicle_type,
            ))

        return vehicles

    async def detect_vehicles(
        self,
        image_bytes: bytes,
        confidence_threshold: Optional[float] = None
    ) -> list[VehicleDetection]:
        """
        Detect vehicles in an image.

        Args:
            image_bytes: Raw image bytes (JPEG/PNG)
            confidence_threshold: Minimum confidence (defaults to CONFIDENCE_THRESHOLD)

        Returns:
            List of VehicleDetection results, sorted by confidence descending
        """
        # Load model if needed
        if not self._model_loaded:
            self._load_model()

        # Convert to OpenCV format
        image = self._bytes_to_cv2(image_bytes)

        # Run detection in thread pool (CPU-bound)
        loop = asyncio.get_event_loop()
        vehicles = await loop.run_in_executor(
            None,
            self._detect_vehicles_sync,
            image,
            confidence_threshold
        )

        logger.debug(
            "Vehicle detection completed",
            extra={
                "event_type": "vehicle_detection_complete",
                "vehicles_found": len(vehicles),
                "confidence_threshold": confidence_threshold or self.CONFIDENCE_THRESHOLD,
            }
        )

        # Sort by confidence descending
        vehicles.sort(key=lambda v: v.confidence, reverse=True)

        return vehicles

    def crop_vehicle(
        self,
        image_bytes: bytes,
        bbox: BoundingBox,
        padding: Optional[float] = None
    ) -> bytes:
        """
        Crop a vehicle region from an image.

        Args:
            image_bytes: Original image bytes
            bbox: Bounding box of the vehicle
            padding: Padding around vehicle as fraction (default: DEFAULT_PADDING)

        Returns:
            Cropped and resized vehicle image as JPEG bytes
        """
        if padding is None:
            padding = self.DEFAULT_PADDING

        # Convert to OpenCV format
        image = self._bytes_to_cv2(image_bytes)
        (h, w) = image.shape[:2]

        # Calculate padded bounding box
        pad_w = int(bbox.width * padding)
        pad_h = int(bbox.height * padding)

        x1 = max(0, bbox.x - pad_w)
        y1 = max(0, bbox.y - pad_h)
        x2 = min(w, bbox.x + bbox.width + pad_w)
        y2 = min(h, bbox.y + bbox.height + pad_h)

        # Crop vehicle region
        vehicle_crop = image[y1:y2, x1:x2]

        # Resize to standard size
        vehicle_resized = cv2.resize(vehicle_crop, self.TARGET_SIZE)

        # Encode as JPEG
        _, buffer = cv2.imencode('.jpg', vehicle_resized, [cv2.IMWRITE_JPEG_QUALITY, 90])
        vehicle_bytes = buffer.tobytes()

        return vehicle_bytes

    def is_model_loaded(self) -> bool:
        """Check if the vehicle detection model is loaded."""
        return self._model_loaded

    def is_using_fallback(self) -> bool:
        """Check if using fallback mode (no model files)."""
        return self._use_fallback


# Backward compatible getter (delegates to @singleton decorator)
def get_vehicle_detection_service() -> VehicleDetectionService:
    """
    Get the global VehicleDetectionService instance.

    Returns:
        VehicleDetectionService singleton instance

    Note: This is a backward-compatible wrapper. New code should use
          VehicleDetectionService() directly, which returns the singleton instance.
    """
    return VehicleDetectionService()


def reset_vehicle_detection_service() -> None:
    """
    Reset the global VehicleDetectionService instance.

    Useful for testing to ensure a fresh instance.

    Note: This is a backward-compatible wrapper. New code should use
          VehicleDetectionService._reset_instance() directly.
    """
    VehicleDetectionService._reset_instance()
