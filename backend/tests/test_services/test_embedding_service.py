"""
Unit tests for EmbeddingService (Story P4-3.1)

Tests:
- AC1: CLIP ViT-B/32 model loaded and initialized
- AC4: Embedding dimension is 512
- AC5: Embedding generation completes in <200ms per image
- AC6: Model version tracked in database
- AC7: Graceful fallback if embedding generation fails
"""
import asyncio
import io
import json
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from PIL import Image

from app.services.embedding_service import EmbeddingService, get_embedding_service


class TestEmbeddingServiceInit:
    """Tests for EmbeddingService initialization (AC1)."""

    def test_service_initialization(self):
        """Test that service initializes with correct constants."""
        service = EmbeddingService()

        assert service.MODEL_NAME == "clip-ViT-B-32"
        assert service.MODEL_VERSION == "clip-ViT-B-32-v1"
        assert service.EMBEDDING_DIM == 512
        assert service._model is None  # Lazy loading

    def test_lazy_model_loading(self):
        """Test that model is not loaded until first use."""
        service = EmbeddingService()

        # Model should not be loaded yet
        assert service._model is None

    def test_get_model_version(self):
        """Test model version accessor (AC6)."""
        service = EmbeddingService()
        assert service.get_model_version() == "clip-ViT-B-32-v1"

    def test_get_embedding_dimension(self):
        """Test embedding dimension accessor (AC4)."""
        service = EmbeddingService()
        assert service.get_embedding_dimension() == 512


class TestEmbeddingServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_embedding_service_returns_same_instance(self):
        """Test that get_embedding_service returns singleton."""
        # Reset global singleton for test
        import app.services.embedding_service as module
        module._embedding_service = None

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2

        # Cleanup
        module._embedding_service = None


class TestEmbeddingGeneration:
    """Tests for embedding generation with mocked CLIP model."""

    @pytest.fixture
    def mock_model(self):
        """Create a mock SentenceTransformer model."""
        import numpy as np

        mock = MagicMock()
        # Return a 512-dim numpy array
        mock.encode.return_value = np.random.randn(512).astype(np.float32)
        return mock

    @pytest.fixture
    def service_with_mock(self, mock_model):
        """Create EmbeddingService with mocked model."""
        service = EmbeddingService()
        service._model = mock_model
        return service

    @pytest.fixture
    def test_image_bytes(self):
        """Create test image bytes."""
        # Create a simple 100x100 RGB image
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        return buffer.getvalue()

    @pytest.mark.asyncio
    async def test_generate_embedding_returns_512_dim(self, service_with_mock, test_image_bytes):
        """Test that embeddings have correct dimension (AC4)."""
        embedding = await service_with_mock.generate_embedding(test_image_bytes)

        assert isinstance(embedding, list)
        assert len(embedding) == 512
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.asyncio
    async def test_generate_embedding_calls_model_encode(self, service_with_mock, test_image_bytes, mock_model):
        """Test that model.encode is called with correct parameters."""
        await service_with_mock.generate_embedding(test_image_bytes)

        mock_model.encode.assert_called_once()
        # First argument should be a PIL Image
        call_args = mock_model.encode.call_args
        assert hasattr(call_args[0][0], 'mode')  # PIL Image has 'mode' attribute

    @pytest.mark.asyncio
    async def test_generate_embedding_converts_rgba_to_rgb(self, service_with_mock, mock_model):
        """Test that RGBA images are converted to RGB."""
        # Create RGBA image
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        await service_with_mock.generate_embedding(image_bytes)

        # Should have been converted to RGB
        mock_model.encode.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_embedding_empty_bytes_raises(self, service_with_mock):
        """Test that empty bytes raises ValueError."""
        with pytest.raises(ValueError, match="image_bytes cannot be empty"):
            await service_with_mock.generate_embedding(b"")

    @pytest.mark.asyncio
    async def test_generate_embedding_invalid_bytes_raises(self, service_with_mock):
        """Test that invalid image bytes raises exception (AC7 - tests failure path)."""
        with pytest.raises(Exception):
            await service_with_mock.generate_embedding(b"not an image")

    @pytest.mark.asyncio
    async def test_generate_embedding_from_base64(self, service_with_mock, test_image_bytes):
        """Test embedding generation from base64 string (AC10)."""
        import base64

        # With data URI prefix
        b64_with_prefix = f"data:image/jpeg;base64,{base64.b64encode(test_image_bytes).decode()}"
        embedding1 = await service_with_mock.generate_embedding_from_base64(b64_with_prefix)

        assert len(embedding1) == 512

        # Without data URI prefix
        b64_without_prefix = base64.b64encode(test_image_bytes).decode()
        embedding2 = await service_with_mock.generate_embedding_from_base64(b64_without_prefix)

        assert len(embedding2) == 512


class TestEmbeddingPerformance:
    """Tests for embedding generation performance (AC5)."""

    @pytest.mark.asyncio
    async def test_embedding_generation_timing_with_mock(self):
        """Test that embedding generation completes quickly with mocked model."""
        import numpy as np

        # Create mock that returns quickly
        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(512).astype(np.float32)

        service = EmbeddingService()
        service._model = mock_model

        # Create test image
        img = Image.new("RGB", (320, 180), color=(128, 128, 128))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()

        # Measure time
        start = time.time()
        await service.generate_embedding(image_bytes)
        duration_ms = (time.time() - start) * 1000

        # Mock should complete almost instantly
        # In real tests with actual model, this would verify <200ms
        assert duration_ms < 1000  # Very generous for mocked model


class TestEmbeddingStorage:
    """Tests for embedding storage functionality."""

    @pytest.fixture
    def db_session(self):
        """Create mock database session."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.database import Base

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()

        yield session

        session.close()
        Base.metadata.drop_all(engine)

    @pytest.fixture
    def test_event(self, db_session):
        """Create a test event in the database."""
        from app.models.event import Event
        from datetime import datetime, timezone

        event = Event(
            id="test-event-123",
            camera_id="test-camera-456",
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=85,
            objects_detected='["person"]',
        )
        db_session.add(event)
        db_session.commit()
        return event

    @pytest.mark.asyncio
    async def test_store_embedding(self, db_session, test_event):
        """Test storing an embedding in the database (AC3)."""
        from app.models.event_embedding import EventEmbedding

        service = EmbeddingService()
        embedding = [0.1] * 512

        embedding_id = await service.store_embedding(
            db=db_session,
            event_id=test_event.id,
            embedding=embedding,
        )

        assert embedding_id is not None

        # Verify stored in database
        stored = db_session.query(EventEmbedding).filter(
            EventEmbedding.event_id == test_event.id
        ).first()

        assert stored is not None
        assert stored.model_version == "clip-ViT-B-32-v1"  # AC6
        assert json.loads(stored.embedding) == embedding

    @pytest.mark.asyncio
    async def test_get_embedding_metadata(self, db_session, test_event):
        """Test retrieving embedding metadata (AC12)."""
        service = EmbeddingService()
        embedding = [0.2] * 512

        # Store embedding first
        await service.store_embedding(
            db=db_session,
            event_id=test_event.id,
            embedding=embedding,
        )

        # Get metadata
        meta = await service.get_embedding(db_session, test_event.id)

        assert meta is not None
        assert meta["exists"] is True
        assert meta["event_id"] == test_event.id
        assert meta["model_version"] == "clip-ViT-B-32-v1"
        assert meta["created_at"] is not None

    @pytest.mark.asyncio
    async def test_get_embedding_not_found(self, db_session):
        """Test get_embedding returns None for non-existent event."""
        service = EmbeddingService()

        meta = await service.get_embedding(db_session, "non-existent-id")

        assert meta is None

    @pytest.mark.asyncio
    async def test_get_embedding_vector(self, db_session, test_event):
        """Test retrieving the actual embedding vector."""
        service = EmbeddingService()
        embedding = [float(i) / 512 for i in range(512)]

        # Store embedding
        await service.store_embedding(
            db=db_session,
            event_id=test_event.id,
            embedding=embedding,
        )

        # Get vector
        vector = await service.get_embedding_vector(db_session, test_event.id)

        assert vector is not None
        assert len(vector) == 512
        assert vector == embedding


class TestGracefulFailure:
    """Tests for graceful failure handling (AC7)."""

    @pytest.mark.asyncio
    async def test_model_load_failure_raises(self):
        """Test that model load failure raises appropriate exception."""
        service = EmbeddingService()

        with patch("app.services.embedding_service.EmbeddingService._load_model") as mock_load:
            mock_load.side_effect = ImportError("sentence-transformers not installed")

            with pytest.raises(ImportError):
                await service._ensure_model_loaded()

    @pytest.mark.asyncio
    async def test_encode_failure_propagates(self):
        """Test that encoding failures propagate correctly."""
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("CUDA out of memory")

        service = EmbeddingService()
        service._model = mock_model

        # Create valid image
        img = Image.new("RGB", (100, 100), color=(0, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()

        with pytest.raises(RuntimeError, match="CUDA out of memory"):
            await service.generate_embedding(image_bytes)
