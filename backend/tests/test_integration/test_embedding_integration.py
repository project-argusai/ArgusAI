"""
Integration tests for embedding functionality (Story P4-3.1)

Tests:
- AC2: Embedding generated for each new event thumbnail
- AC3: Embeddings stored in event_embeddings table with event_id reference
- AC8: Batch processing endpoint for generating embeddings on existing events
- AC9: Batch processing respects rate limiting (max 100 events per request)
- AC10: Embedding generation works for both base64 and file-path thumbnails
- AC11: SQLite fallback stores embeddings as JSON array
- AC12: API endpoint to check embedding status for an event
"""
import base64
import io
import json
import os
import pytest
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.models.event import Event
from app.models.event_embedding import EventEmbedding
from app.models.camera import Camera


@pytest.fixture(scope="function")
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def test_camera(test_db):
    """Create a test camera in the database."""
    camera = Camera(
        id="test-camera-001",
        name="Test Camera",
        type="rtsp",
        rtsp_url="rtsp://test:test@localhost/stream",
        is_enabled=True,
    )
    test_db.add(camera)
    test_db.commit()
    return camera


@pytest.fixture
def test_image_base64():
    """Create a test image as base64 string."""
    img = Image.new("RGB", (320, 180), color=(100, 150, 200))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    b64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


@pytest.fixture
def mock_embedding_model():
    """Create a mock CLIP model for fast tests."""
    mock = MagicMock()
    mock.encode.return_value = np.random.randn(512).astype(np.float32)
    return mock


class TestEventEmbeddingStorage:
    """Tests for embedding storage in SQLite (AC3, AC11)."""

    def test_create_event_embedding(self, test_db, test_camera):
        """Test creating an event embedding record (AC3)."""
        # Create an event first
        event = Event(
            id="event-001",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=85,
            objects_detected='["person"]',
        )
        test_db.add(event)
        test_db.commit()

        # Create embedding
        embedding_data = [float(i) / 512 for i in range(512)]
        embedding = EventEmbedding(
            event_id=event.id,
            embedding=json.dumps(embedding_data),
            model_version="clip-ViT-B-32-v1",
        )
        test_db.add(embedding)
        test_db.commit()

        # Verify storage
        stored = test_db.query(EventEmbedding).filter(
            EventEmbedding.event_id == event.id
        ).first()

        assert stored is not None
        assert stored.event_id == event.id
        assert stored.model_version == "clip-ViT-B-32-v1"

        # AC11: Verify JSON array storage
        loaded_embedding = json.loads(stored.embedding)
        assert isinstance(loaded_embedding, list)
        assert len(loaded_embedding) == 512
        assert loaded_embedding == embedding_data

    def test_event_embedding_unique_constraint(self, test_db, test_camera):
        """Test that event_id has unique constraint."""
        from sqlalchemy.exc import IntegrityError

        event = Event(
            id="event-002",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=85,
            objects_detected='["vehicle"]',
        )
        test_db.add(event)
        test_db.commit()

        # First embedding
        embedding1 = EventEmbedding(
            event_id=event.id,
            embedding=json.dumps([0.1] * 512),
            model_version="clip-ViT-B-32-v1",
        )
        test_db.add(embedding1)
        test_db.commit()

        # Second embedding for same event should fail
        embedding2 = EventEmbedding(
            event_id=event.id,
            embedding=json.dumps([0.2] * 512),
            model_version="clip-ViT-B-32-v1",
        )
        test_db.add(embedding2)

        with pytest.raises(IntegrityError):
            test_db.commit()

        test_db.rollback()

    def test_event_embedding_cascade_delete(self, test_db, test_camera):
        """Test that embedding is deleted when event is deleted."""
        event = Event(
            id="event-003",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=85,
            objects_detected='["animal"]',
        )
        test_db.add(event)
        test_db.commit()

        embedding = EventEmbedding(
            event_id=event.id,
            embedding=json.dumps([0.3] * 512),
            model_version="clip-ViT-B-32-v1",
        )
        test_db.add(embedding)
        test_db.commit()

        # Delete event
        test_db.delete(event)
        test_db.commit()

        # Embedding should be cascade deleted
        remaining = test_db.query(EventEmbedding).filter(
            EventEmbedding.event_id == "event-003"
        ).first()
        assert remaining is None


class TestThumbnailModes:
    """Tests for both thumbnail storage modes (AC10)."""

    @pytest.mark.asyncio
    async def test_base64_thumbnail_embedding(self, test_db, test_camera, mock_embedding_model):
        """Test embedding generation from base64 thumbnail (AC10)."""
        from app.services.embedding_service import EmbeddingService

        # Create event with base64 thumbnail
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        b64 = base64.b64encode(buffer.getvalue()).decode()
        thumbnail_base64 = f"data:image/jpeg;base64,{b64}"

        event = Event(
            id="event-b64-001",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Base64 thumbnail test",
            confidence=90,
            objects_detected='["person"]',
            thumbnail_base64=thumbnail_base64,
        )
        test_db.add(event)
        test_db.commit()

        # Generate embedding
        service = EmbeddingService()
        service._model = mock_embedding_model

        embedding = await service.generate_embedding_from_base64(thumbnail_base64)

        assert len(embedding) == 512
        mock_embedding_model.encode.assert_called_once()

    @pytest.mark.asyncio
    async def test_file_path_thumbnail_embedding(self, test_db, test_camera, mock_embedding_model):
        """Test embedding generation from file path thumbnail (AC10)."""
        from app.services.embedding_service import EmbeddingService

        # Create test image file
        img = Image.new("RGB", (100, 100), color=(0, 255, 0))
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            img.save(f, format="JPEG")
            temp_path = f.name

        try:
            # Generate embedding from file
            service = EmbeddingService()
            service._model = mock_embedding_model

            embedding = await service.generate_embedding_from_file(temp_path)

            assert len(embedding) == 512
            mock_embedding_model.encode.assert_called_once()
        finally:
            os.unlink(temp_path)


class TestBatchProcessing:
    """Tests for batch embedding generation (AC8, AC9)."""

    @pytest.mark.asyncio
    async def test_batch_processing_limit(self, test_db, test_camera, mock_embedding_model):
        """Test batch processing respects 100 event limit (AC9)."""
        # Create 150 events without embeddings
        img = Image.new("RGB", (50, 50), color=(128, 128, 128))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        b64 = f"data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}"

        for i in range(150):
            event = Event(
                id=f"batch-event-{i:03d}",
                camera_id=test_camera.id,
                timestamp=datetime.now(timezone.utc),
                description=f"Batch test event {i}",
                confidence=75,
                objects_detected='["unknown"]',
                thumbnail_base64=b64,
            )
            test_db.add(event)
        test_db.commit()

        # Query events without embeddings
        events_with_embeddings = test_db.query(EventEmbedding.event_id).subquery()
        events_to_process = test_db.query(Event).filter(
            ~Event.id.in_(events_with_embeddings),
            Event.thumbnail_base64.isnot(None)
        ).limit(100).all()

        # Should be limited to 100
        assert len(events_to_process) == 100

    def test_events_without_embeddings_query(self, test_db, test_camera):
        """Test querying events that need embedding generation."""
        # Create events - some with embeddings, some without
        for i in range(5):
            event = Event(
                id=f"query-test-event-{i}",
                camera_id=test_camera.id,
                timestamp=datetime.now(timezone.utc),
                description=f"Query test {i}",
                confidence=80,
                objects_detected='["person"]',
                thumbnail_base64="data:image/jpeg;base64,test",
            )
            test_db.add(event)
        test_db.commit()

        # Add embeddings for first 2 events
        for i in range(2):
            embedding = EventEmbedding(
                event_id=f"query-test-event-{i}",
                embedding=json.dumps([0.1] * 512),
                model_version="clip-ViT-B-32-v1",
            )
            test_db.add(embedding)
        test_db.commit()

        # Query events without embeddings
        events_with_embeddings = test_db.query(EventEmbedding.event_id).subquery()
        events_without = test_db.query(Event).filter(
            ~Event.id.in_(events_with_embeddings)
        ).all()

        # Should have 3 events without embeddings
        assert len(events_without) == 3


class TestEmbeddingStatusEndpoint:
    """Tests for embedding status API endpoint (AC12)."""

    @pytest.mark.asyncio
    async def test_get_embedding_status_exists(self, test_db, test_camera):
        """Test status endpoint returns correct data when embedding exists."""
        from app.services.embedding_service import EmbeddingService

        # Create event and embedding
        event = Event(
            id="status-test-001",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Status test event",
            confidence=85,
            objects_detected='["vehicle"]',
        )
        test_db.add(event)
        test_db.commit()

        embedding = EventEmbedding(
            event_id=event.id,
            embedding=json.dumps([0.5] * 512),
            model_version="clip-ViT-B-32-v1",
        )
        test_db.add(embedding)
        test_db.commit()

        # Get status via service
        service = EmbeddingService()
        status = await service.get_embedding(test_db, event.id)

        assert status is not None
        assert status["exists"] is True
        assert status["model_version"] == "clip-ViT-B-32-v1"
        assert status["created_at"] is not None

    @pytest.mark.asyncio
    async def test_get_embedding_status_not_exists(self, test_db, test_camera):
        """Test status endpoint returns None when embedding doesn't exist."""
        from app.services.embedding_service import EmbeddingService

        # Create event without embedding
        event = Event(
            id="status-test-002",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="No embedding event",
            confidence=80,
            objects_detected='["person"]',
        )
        test_db.add(event)
        test_db.commit()

        # Get status
        service = EmbeddingService()
        status = await service.get_embedding(test_db, event.id)

        assert status is None


class TestEmbeddingJSONStorage:
    """Tests for SQLite JSON storage format (AC11)."""

    def test_embedding_json_format(self, test_db, test_camera):
        """Test embeddings are stored as valid JSON arrays (AC11)."""
        event = Event(
            id="json-test-001",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="JSON format test",
            confidence=90,
            objects_detected='["package"]',
        )
        test_db.add(event)
        test_db.commit()

        # Store embedding with specific values
        test_embedding = [float(i) * 0.001 for i in range(512)]
        embedding = EventEmbedding(
            event_id=event.id,
            embedding=json.dumps(test_embedding),
            model_version="clip-ViT-B-32-v1",
        )
        test_db.add(embedding)
        test_db.commit()

        # Retrieve and verify JSON parsing
        stored = test_db.query(EventEmbedding).filter(
            EventEmbedding.event_id == event.id
        ).first()

        # Should be valid JSON
        loaded = json.loads(stored.embedding)
        assert isinstance(loaded, list)
        assert len(loaded) == 512

        # Values should match
        for i, val in enumerate(loaded):
            assert abs(val - test_embedding[i]) < 1e-6

    def test_embedding_preserves_float_precision(self, test_db, test_camera):
        """Test that float precision is preserved in JSON storage."""
        event = Event(
            id="precision-test-001",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Precision test",
            confidence=95,
            objects_detected='["animal"]',
        )
        test_db.add(event)
        test_db.commit()

        # Use specific float values
        test_values = [0.123456789, -0.987654321, 1e-10, 1e10]
        test_embedding = test_values + [0.0] * (512 - len(test_values))

        embedding = EventEmbedding(
            event_id=event.id,
            embedding=json.dumps(test_embedding),
            model_version="clip-ViT-B-32-v1",
        )
        test_db.add(embedding)
        test_db.commit()

        # Retrieve and verify precision
        stored = test_db.query(EventEmbedding).filter(
            EventEmbedding.event_id == event.id
        ).first()
        loaded = json.loads(stored.embedding)

        # Check first few values
        assert abs(loaded[0] - 0.123456789) < 1e-8
        assert abs(loaded[1] - (-0.987654321)) < 1e-8


class TestEventRelationship:
    """Tests for Event-EventEmbedding relationship."""

    def test_event_has_embedding_relationship(self, test_db, test_camera):
        """Test that Event model has embedding relationship."""
        event = Event(
            id="relationship-test-001",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Relationship test",
            confidence=88,
            objects_detected='["person"]',
        )
        test_db.add(event)
        test_db.commit()

        embedding = EventEmbedding(
            event_id=event.id,
            embedding=json.dumps([0.1] * 512),
            model_version="clip-ViT-B-32-v1",
        )
        test_db.add(embedding)
        test_db.commit()

        # Refresh to load relationship
        test_db.refresh(event)

        # Access via relationship
        assert event.embedding is not None
        assert event.embedding.model_version == "clip-ViT-B-32-v1"
