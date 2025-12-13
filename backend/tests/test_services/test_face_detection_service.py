"""
Unit tests for FaceDetectionService (Story P4-8.1)

Tests face detection functionality including:
- Face detection on images with single/multiple/no faces
- Confidence threshold filtering
- Face region extraction with padding
- Error handling for invalid input
"""
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
from PIL import Image

# Create a simple test image with a colored rectangle (simulating a face region)
def create_test_image(width: int = 300, height: int = 300, has_face: bool = True) -> bytes:
    """Create a test image as bytes.

    Args:
        width: Image width
        height: Image height
        has_face: If True, add a face-like region (skin-colored rectangle)

    Returns:
        JPEG bytes of the test image
    """
    # Create a simple image with numpy
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Fill with background color
    img[:, :] = [100, 120, 100]  # BGR greenish background

    if has_face:
        # Add a skin-colored rectangle (face-like region)
        face_x1, face_y1 = width // 4, height // 4
        face_x2, face_y2 = 3 * width // 4, 3 * height // 4
        img[face_y1:face_y2, face_x1:face_x2] = [140, 160, 200]  # BGR skin-ish color

    # Convert to PIL Image and save as JPEG
    pil_img = Image.fromarray(img[:, :, ::-1])  # BGR to RGB
    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG")
    return buffer.getvalue()


class TestFaceDetectionService:
    """Tests for FaceDetectionService class."""

    @pytest.fixture
    def face_service(self):
        """Create a FaceDetectionService instance with mocked model."""
        from app.services.face_detection_service import FaceDetectionService

        service = FaceDetectionService()
        return service

    def test_service_initialization(self, face_service):
        """Test that service initializes correctly."""
        assert face_service is not None
        assert face_service.CONFIDENCE_THRESHOLD == 0.5
        assert face_service.TARGET_SIZE == (160, 160)
        assert face_service.DEFAULT_PADDING == 0.2
        assert face_service._model_loaded is False

    def test_is_model_loaded_initially_false(self, face_service):
        """Test that model is not loaded initially."""
        assert face_service.is_model_loaded() is False

    @pytest.mark.asyncio
    async def test_detect_faces_empty_bytes_raises_error(self, face_service):
        """Test that empty image bytes raises ValueError."""
        with pytest.raises(ValueError, match="image_bytes cannot be empty"):
            await face_service.detect_faces(b"")

    @pytest.mark.asyncio
    async def test_detect_faces_none_bytes_raises_error(self, face_service):
        """Test that None image bytes raises ValueError."""
        with pytest.raises(ValueError, match="image_bytes cannot be empty"):
            await face_service.detect_faces(None)

    @pytest.mark.asyncio
    async def test_extract_face_region_empty_bytes_raises_error(self, face_service):
        """Test that empty image bytes raises ValueError for face extraction."""
        from app.services.face_detection_service import BoundingBox

        bbox = BoundingBox(x=10, y=10, width=50, height=50)

        with pytest.raises(ValueError, match="image_bytes cannot be empty"):
            await face_service.extract_face_region(b"", bbox)

    def test_bounding_box_to_dict(self):
        """Test BoundingBox serialization."""
        from app.services.face_detection_service import BoundingBox

        bbox = BoundingBox(x=10, y=20, width=100, height=150)
        result = bbox.to_dict()

        assert result == {"x": 10, "y": 20, "width": 100, "height": 150}

    def test_bounding_box_from_dict(self):
        """Test BoundingBox deserialization."""
        from app.services.face_detection_service import BoundingBox

        data = {"x": 10, "y": 20, "width": 100, "height": 150}
        bbox = BoundingBox.from_dict(data)

        assert bbox.x == 10
        assert bbox.y == 20
        assert bbox.width == 100
        assert bbox.height == 150

    def test_face_detection_to_dict(self):
        """Test FaceDetection serialization."""
        from app.services.face_detection_service import BoundingBox, FaceDetection

        bbox = BoundingBox(x=10, y=20, width=100, height=150)
        detection = FaceDetection(bbox=bbox, confidence=0.95)

        result = detection.to_dict()

        assert result["confidence"] == 0.95
        assert result["bbox"]["x"] == 10
        assert result["bbox"]["y"] == 20

    @pytest.mark.asyncio
    async def test_detect_faces_model_not_found(self, face_service):
        """Test that missing model files raises appropriate error."""
        # Use a non-existent model path
        face_service.MODEL_DIR = "/nonexistent/path"

        test_image = create_test_image()

        with pytest.raises(FileNotFoundError, match="Face detection model"):
            await face_service.detect_faces(test_image)

    @pytest.mark.asyncio
    async def test_detect_faces_with_mocked_model(self, face_service):
        """Test face detection with mocked OpenCV model."""
        import cv2

        # Mock the model loading and inference
        mock_net = MagicMock()

        # Create mock detection output (shape: 1, 1, num_detections, 7)
        # Each detection: [batch_id, class_id, confidence, x1, y1, x2, y2]
        mock_detections = np.array([[[[0, 0, 0.95, 0.1, 0.1, 0.9, 0.9]]]])
        mock_net.forward.return_value = mock_detections

        # Patch the model loading
        face_service._net = mock_net
        face_service._model_loaded = True

        test_image = create_test_image()

        faces = await face_service.detect_faces(test_image)

        assert len(faces) == 1
        assert faces[0].confidence == 0.95
        assert faces[0].bbox.x >= 0
        assert faces[0].bbox.y >= 0
        assert faces[0].bbox.width > 0
        assert faces[0].bbox.height > 0

    @pytest.mark.asyncio
    async def test_detect_faces_no_faces_found(self, face_service):
        """Test face detection returns empty list when no faces found."""
        mock_net = MagicMock()

        # Create mock detection output with no detections above threshold
        mock_detections = np.array([[[[0, 0, 0.1, 0.1, 0.1, 0.9, 0.9]]]])  # Low confidence
        mock_net.forward.return_value = mock_detections

        face_service._net = mock_net
        face_service._model_loaded = True

        test_image = create_test_image(has_face=False)

        faces = await face_service.detect_faces(test_image)

        assert faces == []

    @pytest.mark.asyncio
    async def test_detect_faces_multiple_faces(self, face_service):
        """Test face detection with multiple faces."""
        mock_net = MagicMock()

        # Create mock detection output with multiple detections
        mock_detections = np.array([[
            [[0, 0, 0.9, 0.1, 0.1, 0.4, 0.4]],
            [[0, 0, 0.85, 0.5, 0.5, 0.8, 0.8]],
            [[0, 0, 0.7, 0.2, 0.6, 0.4, 0.9]],
        ]])
        mock_detections = mock_detections.reshape(1, 1, 3, 7)
        mock_net.forward.return_value = mock_detections

        face_service._net = mock_net
        face_service._model_loaded = True

        test_image = create_test_image()

        faces = await face_service.detect_faces(test_image)

        assert len(faces) == 3
        assert all(f.confidence >= 0.5 for f in faces)

    @pytest.mark.asyncio
    async def test_detect_faces_custom_confidence_threshold(self, face_service):
        """Test face detection with custom confidence threshold."""
        mock_net = MagicMock()

        # Create mock detection output with various confidences
        mock_detections = np.array([[
            [[0, 0, 0.9, 0.1, 0.1, 0.4, 0.4]],
            [[0, 0, 0.6, 0.5, 0.5, 0.8, 0.8]],
            [[0, 0, 0.3, 0.2, 0.6, 0.4, 0.9]],  # Below threshold
        ]])
        mock_detections = mock_detections.reshape(1, 1, 3, 7)
        mock_net.forward.return_value = mock_detections

        face_service._net = mock_net
        face_service._model_loaded = True

        test_image = create_test_image()

        # With default threshold (0.5), should get 2 faces
        faces = await face_service.detect_faces(test_image)
        assert len(faces) == 2

        # With higher threshold (0.8), should get only 1 face
        faces_high = await face_service.detect_faces(test_image, confidence_threshold=0.8)
        assert len(faces_high) == 1
        assert faces_high[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_extract_face_region_returns_bytes(self, face_service):
        """Test that face region extraction returns valid JPEG bytes."""
        from app.services.face_detection_service import BoundingBox

        test_image = create_test_image(width=300, height=300)
        bbox = BoundingBox(x=50, y=50, width=100, height=100)

        face_bytes = await face_service.extract_face_region(test_image, bbox)

        assert face_bytes is not None
        assert len(face_bytes) > 0

        # Verify it's a valid JPEG
        assert face_bytes[:2] == b'\xff\xd8'  # JPEG magic bytes

    @pytest.mark.asyncio
    async def test_extract_face_region_correct_size(self, face_service):
        """Test that extracted face region has correct size."""
        from app.services.face_detection_service import BoundingBox

        test_image = create_test_image(width=300, height=300)
        bbox = BoundingBox(x=50, y=50, width=100, height=100)

        target_size = (200, 200)
        face_bytes = await face_service.extract_face_region(
            test_image, bbox, target_size=target_size
        )

        # Verify output size
        from PIL import Image
        import io

        face_img = Image.open(io.BytesIO(face_bytes))
        assert face_img.size == target_size

    @pytest.mark.asyncio
    async def test_extract_face_region_with_padding(self, face_service):
        """Test face region extraction with custom padding."""
        from app.services.face_detection_service import BoundingBox

        test_image = create_test_image(width=300, height=300)
        bbox = BoundingBox(x=100, y=100, width=50, height=50)

        # With 0 padding
        face_bytes_no_pad = await face_service.extract_face_region(
            test_image, bbox, padding=0.0
        )

        # With 50% padding
        face_bytes_pad = await face_service.extract_face_region(
            test_image, bbox, padding=0.5
        )

        # Both should produce valid images (resized to same target)
        assert len(face_bytes_no_pad) > 0
        assert len(face_bytes_pad) > 0


class TestFaceDetectionServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_face_detection_service_returns_same_instance(self):
        """Test that get_face_detection_service returns singleton."""
        from app.services.face_detection_service import (
            get_face_detection_service,
            _face_detection_service,
        )

        # Reset singleton for test
        import app.services.face_detection_service as module
        module._face_detection_service = None

        service1 = get_face_detection_service()
        service2 = get_face_detection_service()

        assert service1 is service2

    def test_get_model_version(self):
        """Test that service has model version."""
        from app.services.face_detection_service import FaceDetectionService

        service = FaceDetectionService()
        # Model version is tracked in FaceEmbeddingService, not detection service
        # Detection service just has confidence threshold and target size
        assert hasattr(service, 'CONFIDENCE_THRESHOLD')
        assert hasattr(service, 'TARGET_SIZE')
