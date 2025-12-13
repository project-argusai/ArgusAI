"""
Unit tests for FaceEmbeddingService (Story P4-8.1)

Tests face embedding generation and storage including:
- Processing event faces
- Getting/deleting face embeddings
- Privacy controls integration
- Handling no-face scenarios
"""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.face_detection_service import BoundingBox, FaceDetection


@pytest.fixture
def mock_face_detector():
    """Create a mock FaceDetectionService."""
    detector = MagicMock()
    detector.detect_faces = AsyncMock(return_value=[])
    detector.extract_face_region = AsyncMock(return_value=b"mock_face_bytes")
    return detector


@pytest.fixture
def mock_embedding_service():
    """Create a mock EmbeddingService."""
    service = MagicMock()
    service.generate_embedding = AsyncMock(return_value=[0.1] * 512)
    return service


@pytest.fixture
def face_embedding_service(mock_face_detector, mock_embedding_service):
    """Create a FaceEmbeddingService with mocked dependencies."""
    from app.services.face_embedding_service import FaceEmbeddingService

    service = FaceEmbeddingService(
        face_detector=mock_face_detector,
        embedding_service=mock_embedding_service,
    )
    return service


class TestFaceEmbeddingService:
    """Tests for FaceEmbeddingService class."""

    def test_service_initialization(self, face_embedding_service):
        """Test that service initializes correctly."""
        assert face_embedding_service is not None
        assert face_embedding_service.MODEL_VERSION == "clip-ViT-B-32-face-v1"

    def test_get_model_version(self, face_embedding_service):
        """Test model version getter."""
        version = face_embedding_service.get_model_version()
        assert version == "clip-ViT-B-32-face-v1"

    @pytest.mark.asyncio
    async def test_process_event_faces_empty_bytes_raises_error(
        self, face_embedding_service
    ):
        """Test that empty thumbnail bytes raises ValueError."""
        mock_db = MagicMock()
        event_id = str(uuid.uuid4())

        with pytest.raises(ValueError, match="thumbnail_bytes cannot be empty"):
            await face_embedding_service.process_event_faces(mock_db, event_id, b"")

    @pytest.mark.asyncio
    async def test_process_event_faces_no_faces_detected(
        self, face_embedding_service, mock_face_detector
    ):
        """Test processing returns empty list when no faces detected."""
        mock_db = MagicMock()
        event_id = str(uuid.uuid4())
        thumbnail_bytes = b"test_image_bytes"

        # Mock no faces detected
        mock_face_detector.detect_faces.return_value = []

        result = await face_embedding_service.process_event_faces(
            mock_db, event_id, thumbnail_bytes
        )

        assert result == []
        mock_face_detector.detect_faces.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_event_faces_single_face(
        self, face_embedding_service, mock_face_detector, mock_embedding_service
    ):
        """Test processing a single face."""
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        event_id = str(uuid.uuid4())
        thumbnail_bytes = b"test_image_bytes"

        # Mock single face detection
        face = FaceDetection(
            bbox=BoundingBox(x=10, y=20, width=100, height=100),
            confidence=0.9,
        )
        mock_face_detector.detect_faces.return_value = [face]

        result = await face_embedding_service.process_event_faces(
            mock_db, event_id, thumbnail_bytes
        )

        assert len(result) == 1
        mock_face_detector.detect_faces.assert_called_once()
        mock_face_detector.extract_face_region.assert_called_once()
        mock_embedding_service.generate_embedding.assert_called_once()
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_event_faces_multiple_faces(
        self, face_embedding_service, mock_face_detector, mock_embedding_service
    ):
        """Test processing multiple faces."""
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        event_id = str(uuid.uuid4())
        thumbnail_bytes = b"test_image_bytes"

        # Mock multiple face detections
        faces = [
            FaceDetection(
                bbox=BoundingBox(x=10, y=20, width=50, height=50),
                confidence=0.95,
            ),
            FaceDetection(
                bbox=BoundingBox(x=150, y=30, width=60, height=60),
                confidence=0.85,
            ),
            FaceDetection(
                bbox=BoundingBox(x=100, y=150, width=40, height=40),
                confidence=0.75,
            ),
        ]
        mock_face_detector.detect_faces.return_value = faces

        result = await face_embedding_service.process_event_faces(
            mock_db, event_id, thumbnail_bytes
        )

        assert len(result) == 3
        assert mock_face_detector.extract_face_region.call_count == 3
        assert mock_embedding_service.generate_embedding.call_count == 3
        assert mock_db.add.call_count == 3

    @pytest.mark.asyncio
    async def test_process_event_faces_handles_face_extraction_error(
        self, face_embedding_service, mock_face_detector, mock_embedding_service
    ):
        """Test that face extraction errors don't stop processing other faces."""
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        event_id = str(uuid.uuid4())
        thumbnail_bytes = b"test_image_bytes"

        # Mock multiple face detections
        faces = [
            FaceDetection(
                bbox=BoundingBox(x=10, y=20, width=50, height=50),
                confidence=0.95,
            ),
            FaceDetection(
                bbox=BoundingBox(x=150, y=30, width=60, height=60),
                confidence=0.85,
            ),
        ]
        mock_face_detector.detect_faces.return_value = faces

        # Make first extraction fail, second succeed
        mock_face_detector.extract_face_region.side_effect = [
            Exception("Extraction failed"),
            b"face_bytes",
        ]

        result = await face_embedding_service.process_event_faces(
            mock_db, event_id, thumbnail_bytes
        )

        # Should process only the successful face
        assert len(result) == 1
        assert mock_db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_get_face_embeddings(self, face_embedding_service):
        """Test getting face embeddings for an event."""
        from app.models.face_embedding import FaceEmbedding

        mock_db = MagicMock()
        event_id = str(uuid.uuid4())

        # Create mock face embeddings
        mock_embedding1 = MagicMock(spec=FaceEmbedding)
        mock_embedding1.id = str(uuid.uuid4())
        mock_embedding1.event_id = event_id
        mock_embedding1.entity_id = None
        mock_embedding1.bounding_box = json.dumps({"x": 10, "y": 20, "width": 50, "height": 50})
        mock_embedding1.confidence = 0.95
        mock_embedding1.model_version = "clip-ViT-B-32-face-v1"
        mock_embedding1.created_at = datetime.now(timezone.utc)

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_embedding1
        ]

        result = await face_embedding_service.get_face_embeddings(mock_db, event_id)

        assert len(result) == 1
        assert result[0]["event_id"] == event_id
        assert result[0]["confidence"] == 0.95
        assert result[0]["bounding_box"]["x"] == 10

    @pytest.mark.asyncio
    async def test_delete_event_faces(self, face_embedding_service):
        """Test deleting face embeddings for an event."""
        mock_db = MagicMock()
        event_id = str(uuid.uuid4())

        mock_db.query.return_value.filter.return_value.delete.return_value = 3

        result = await face_embedding_service.delete_event_faces(mock_db, event_id)

        assert result == 3
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_all_faces(self, face_embedding_service):
        """Test deleting all face embeddings."""
        mock_db = MagicMock()

        mock_db.query.return_value.delete.return_value = 10

        result = await face_embedding_service.delete_all_faces(mock_db)

        assert result == 10
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_face_count(self, face_embedding_service):
        """Test getting face count for an event."""
        mock_db = MagicMock()
        event_id = str(uuid.uuid4())

        mock_db.query.return_value.filter.return_value.count.return_value = 2

        result = await face_embedding_service.get_face_count(mock_db, event_id)

        assert result == 2

    @pytest.mark.asyncio
    async def test_get_total_face_count(self, face_embedding_service):
        """Test getting total face count."""
        mock_db = MagicMock()

        mock_db.query.return_value.count.return_value = 100

        result = await face_embedding_service.get_total_face_count(mock_db)

        assert result == 100

    @pytest.mark.asyncio
    async def test_get_face_embedding_vector(self, face_embedding_service):
        """Test getting actual embedding vector."""
        from app.models.face_embedding import FaceEmbedding

        mock_db = MagicMock()
        face_id = str(uuid.uuid4())

        # Create mock face embedding
        mock_embedding = MagicMock(spec=FaceEmbedding)
        mock_embedding.embedding = json.dumps([0.1] * 512)

        mock_db.query.return_value.filter.return_value.first.return_value = mock_embedding

        result = await face_embedding_service.get_face_embedding_vector(mock_db, face_id)

        assert result is not None
        assert len(result) == 512
        assert all(v == 0.1 for v in result)

    @pytest.mark.asyncio
    async def test_get_face_embedding_vector_not_found(self, face_embedding_service):
        """Test getting embedding vector for non-existent face."""
        mock_db = MagicMock()
        face_id = str(uuid.uuid4())

        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await face_embedding_service.get_face_embedding_vector(mock_db, face_id)

        assert result is None


class TestFaceEmbeddingServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_face_embedding_service_returns_same_instance(self):
        """Test that get_face_embedding_service returns singleton."""
        import app.services.face_embedding_service as module

        # Reset singleton for test
        module._face_embedding_service = None

        service1 = module.get_face_embedding_service()
        service2 = module.get_face_embedding_service()

        assert service1 is service2
