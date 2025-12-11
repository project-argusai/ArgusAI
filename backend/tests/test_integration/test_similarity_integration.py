"""
Integration tests for SimilarityService (Story P4-3.2)

Tests:
- AC2: find_similar_events returns top-N similar events
- AC3: Results sorted by similarity score (highest first)
- AC8: Query performance <100ms for top-10 with up to 10,000 embeddings
- AC12: Support optional camera_id filter
"""
import json
import pytest
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.event import Event
from app.models.event_embedding import EventEmbedding
from app.models.camera import Camera
from app.services.embedding_service import EmbeddingService
from app.services.similarity_service import (
    SimilarityService,
    batch_cosine_similarity,
    reset_similarity_service,
)


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
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
def test_camera(db_session):
    """Create a test camera."""
    camera = Camera(
        id="test-camera-001",
        name="Front Door Camera",
        type="rtsp",
        rtsp_url="rtsp://example.com/stream",
    )
    db_session.add(camera)
    db_session.commit()
    return camera


@pytest.fixture
def second_camera(db_session):
    """Create a second test camera for multi-camera tests."""
    camera = Camera(
        id="test-camera-002",
        name="Back Yard Camera",
        type="rtsp",
        rtsp_url="rtsp://example.com/stream2",
    )
    db_session.add(camera)
    db_session.commit()
    return camera


@pytest.fixture
def mock_embedding_service():
    """Create mock embedding service that returns stored embeddings."""
    service = MagicMock(spec=EmbeddingService)
    return service


def create_event_with_embedding(
    db_session,
    event_id: str,
    camera_id: str,
    embedding: list[float],
    description: str = "Test event",
    days_ago: int = 0,
):
    """Helper to create an event with embedding."""
    timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)

    event = Event(
        id=event_id,
        camera_id=camera_id,
        timestamp=timestamp,
        description=description,
        confidence=85,
        objects_detected='["person"]',
        source_type="rtsp",
    )
    db_session.add(event)
    db_session.commit()

    event_embedding = EventEmbedding(
        event_id=event_id,
        embedding=json.dumps(embedding),
        model_version="clip-ViT-B-32-v1",
    )
    db_session.add(event_embedding)
    db_session.commit()

    return event


class TestFindSimilarEventsIntegration:
    """Integration tests for find_similar_events with real database (AC2)."""

    @pytest.mark.asyncio
    async def test_find_similar_events_returns_results(
        self, db_session, test_camera, mock_embedding_service
    ):
        """Test that find_similar_events returns similar events."""
        # Create source event with embedding
        source_embedding = [1.0, 0.0, 0.0] + [0.0] * 509  # 512-dim
        source_event = create_event_with_embedding(
            db_session,
            "source-event",
            test_camera.id,
            source_embedding,
            "Source event",
        )

        # Create similar event (same direction, high similarity)
        similar_embedding = [0.9, 0.1, 0.0] + [0.0] * 509
        create_event_with_embedding(
            db_session,
            "similar-event",
            test_camera.id,
            similar_embedding,
            "Similar event",
        )

        # Create dissimilar event (orthogonal, low similarity)
        dissimilar_embedding = [0.0, 1.0, 0.0] + [0.0] * 509
        create_event_with_embedding(
            db_session,
            "dissimilar-event",
            test_camera.id,
            dissimilar_embedding,
            "Dissimilar event",
        )

        # Mock embedding service to return source embedding
        async def mock_get_embedding_vector(db, event_id):
            return source_embedding

        mock_embedding_service.get_embedding_vector = mock_get_embedding_vector

        service = SimilarityService(embedding_service=mock_embedding_service)
        results = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
            min_similarity=0.5,  # Lower threshold to catch similar-event
        )

        # Should find similar-event but not dissimilar-event (orthogonal = 0.0)
        assert len(results) == 1
        assert results[0].event_id == "similar-event"
        assert results[0].similarity_score > 0.5

    @pytest.mark.asyncio
    async def test_results_sorted_by_similarity_descending(
        self, db_session, test_camera, mock_embedding_service
    ):
        """Test that results are sorted by similarity (highest first) (AC3)."""
        # Source embedding pointing in [1, 0, 0, ...]
        source_embedding = [1.0] + [0.0] * 511

        create_event_with_embedding(
            db_session,
            "source-event",
            test_camera.id,
            source_embedding,
            "Source",
        )

        # Create events with different similarities
        embeddings_with_similarity = [
            ("event-high", [0.95, 0.05] + [0.0] * 510),    # ~0.998
            ("event-mid", [0.8, 0.2] + [0.0] * 510),       # ~0.97
            ("event-low", [0.7, 0.3] + [0.0] * 510),       # ~0.92
        ]

        for event_id, embedding in embeddings_with_similarity:
            create_event_with_embedding(
                db_session,
                event_id,
                test_camera.id,
                embedding,
                f"Event {event_id}",
            )

        async def mock_get_embedding_vector(db, event_id):
            return source_embedding

        mock_embedding_service.get_embedding_vector = mock_get_embedding_vector

        service = SimilarityService(embedding_service=mock_embedding_service)
        results = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
            min_similarity=0.5,
        )

        # Results should be in descending order by similarity
        assert len(results) == 3
        for i in range(len(results) - 1):
            assert results[i].similarity_score >= results[i + 1].similarity_score

    @pytest.mark.asyncio
    async def test_limit_parameter_respected(
        self, db_session, test_camera, mock_embedding_service
    ):
        """Test that limit parameter restricts results."""
        source_embedding = [1.0] + [0.0] * 511

        create_event_with_embedding(
            db_session,
            "source-event",
            test_camera.id,
            source_embedding,
            "Source",
        )

        # Create many similar events
        for i in range(10):
            embedding = [0.9 + i * 0.01] + [0.0] * 511
            create_event_with_embedding(
                db_session,
                f"event-{i}",
                test_camera.id,
                embedding,
                f"Event {i}",
            )

        async def mock_get_embedding_vector(db, event_id):
            return source_embedding

        mock_embedding_service.get_embedding_vector = mock_get_embedding_vector

        service = SimilarityService(embedding_service=mock_embedding_service)

        # Test limit=3
        results = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
            limit=3,
            min_similarity=0.5,
        )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_camera_id_filter(
        self, db_session, test_camera, second_camera, mock_embedding_service
    ):
        """Test that camera_id filter works (AC12)."""
        source_embedding = [1.0] + [0.0] * 511

        create_event_with_embedding(
            db_session,
            "source-event",
            test_camera.id,
            source_embedding,
            "Source",
        )

        # Create event on same camera
        create_event_with_embedding(
            db_session,
            "same-camera-event",
            test_camera.id,
            [0.95] + [0.0] * 511,
            "Same camera",
        )

        # Create event on different camera
        create_event_with_embedding(
            db_session,
            "different-camera-event",
            second_camera.id,
            [0.95] + [0.0] * 511,
            "Different camera",
        )

        async def mock_get_embedding_vector(db, event_id):
            return source_embedding

        mock_embedding_service.get_embedding_vector = mock_get_embedding_vector

        service = SimilarityService(embedding_service=mock_embedding_service)

        # Without filter - should find both
        results_all = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
            min_similarity=0.5,
        )
        assert len(results_all) == 2

        # With filter - should only find same camera event
        results_filtered = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
            min_similarity=0.5,
            camera_id=test_camera.id,
        )
        assert len(results_filtered) == 1
        assert results_filtered[0].event_id == "same-camera-event"

    @pytest.mark.asyncio
    async def test_time_window_filter(
        self, db_session, test_camera, mock_embedding_service
    ):
        """Test that time_window_days filter works (AC5)."""
        source_embedding = [1.0] + [0.0] * 511

        create_event_with_embedding(
            db_session,
            "source-event",
            test_camera.id,
            source_embedding,
            "Source",
        )

        # Create recent event (within window)
        create_event_with_embedding(
            db_session,
            "recent-event",
            test_camera.id,
            [0.95] + [0.0] * 511,
            "Recent event",
            days_ago=5,
        )

        # Create old event (outside window)
        create_event_with_embedding(
            db_session,
            "old-event",
            test_camera.id,
            [0.95] + [0.0] * 511,
            "Old event",
            days_ago=40,
        )

        async def mock_get_embedding_vector(db, event_id):
            return source_embedding

        mock_embedding_service.get_embedding_vector = mock_get_embedding_vector

        service = SimilarityService(embedding_service=mock_embedding_service)

        # 30 day window - should only find recent event
        results = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
            time_window_days=30,
            min_similarity=0.5,
        )

        assert len(results) == 1
        assert results[0].event_id == "recent-event"

    @pytest.mark.asyncio
    async def test_source_event_excluded(
        self, db_session, test_camera, mock_embedding_service
    ):
        """Test that source event is excluded from results (AC11)."""
        source_embedding = [1.0] + [0.0] * 511

        create_event_with_embedding(
            db_session,
            "source-event",
            test_camera.id,
            source_embedding,
            "Source",
        )

        # Create another event that's also very similar
        create_event_with_embedding(
            db_session,
            "other-event",
            test_camera.id,
            [0.99] + [0.0] * 511,
            "Other event",
        )

        async def mock_get_embedding_vector(db, event_id):
            return source_embedding

        mock_embedding_service.get_embedding_vector = mock_get_embedding_vector

        service = SimilarityService(embedding_service=mock_embedding_service)
        results = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
            min_similarity=0.5,
        )

        # Source event should not be in results
        event_ids = [r.event_id for r in results]
        assert "source-event" not in event_ids
        assert "other-event" in event_ids


class TestPerformance:
    """Performance tests for similarity search (AC8).

    Note: These tests use relaxed thresholds to avoid flaky failures in CI environments.
    The actual production performance target is <100ms for 10,000 embeddings.
    """

    @pytest.mark.asyncio
    async def test_batch_similarity_performance_10k_embeddings(self):
        """Test that batch similarity calculation for 10,000 embeddings is reasonably fast (AC8).

        The production target is <100ms. We use a relaxed threshold of 200ms
        to account for CI environment variability.
        """
        np.random.seed(42)

        # Generate query and 10,000 candidate embeddings (512 dimensions)
        query = np.random.randn(512).tolist()
        candidates = [np.random.randn(512).tolist() for _ in range(10000)]

        # Measure time
        start_time = time.time()
        results = batch_cosine_similarity(query, candidates)
        duration_ms = (time.time() - start_time) * 1000

        # Relaxed threshold for CI environments (target is <100ms in production)
        assert duration_ms < 200, f"Batch similarity took {duration_ms:.2f}ms, expected <200ms"
        assert len(results) == 10000

    def test_batch_similarity_performance_larger_dataset(self):
        """Test batch similarity with 50,000 embeddings for margin.

        This tests scalability beyond the 10k target. Uses relaxed threshold.
        """
        np.random.seed(42)

        query = np.random.randn(512).tolist()
        candidates = [np.random.randn(512).tolist() for _ in range(50000)]

        start_time = time.time()
        results = batch_cosine_similarity(query, candidates)
        duration_ms = (time.time() - start_time) * 1000

        # Relaxed threshold for CI environments (target is linear scaling)
        assert duration_ms < 1000, f"Batch similarity took {duration_ms:.2f}ms"
        assert len(results) == 50000


class TestEmptyResults:
    """Tests for empty result handling (AC9)."""

    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty_list(
        self, db_session, test_camera, mock_embedding_service
    ):
        """Test that no candidates returns empty list (not error)."""
        source_embedding = [1.0] + [0.0] * 511

        # Only create source event, no other events
        create_event_with_embedding(
            db_session,
            "source-event",
            test_camera.id,
            source_embedding,
            "Source",
        )

        async def mock_get_embedding_vector(db, event_id):
            return source_embedding

        mock_embedding_service.get_embedding_vector = mock_get_embedding_vector

        service = SimilarityService(embedding_service=mock_embedding_service)
        results = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
        )

        # Should return empty list, not error
        assert results == []
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_all_below_threshold_returns_empty_list(
        self, db_session, test_camera, mock_embedding_service
    ):
        """Test that results below threshold returns empty list."""
        source_embedding = [1.0, 0.0] + [0.0] * 510

        create_event_with_embedding(
            db_session,
            "source-event",
            test_camera.id,
            source_embedding,
            "Source",
        )

        # Create event that's orthogonal (similarity ~0)
        create_event_with_embedding(
            db_session,
            "orthogonal-event",
            test_camera.id,
            [0.0, 1.0] + [0.0] * 510,
            "Orthogonal",
        )

        async def mock_get_embedding_vector(db, event_id):
            return source_embedding

        mock_embedding_service.get_embedding_vector = mock_get_embedding_vector

        service = SimilarityService(embedding_service=mock_embedding_service)
        results = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
            min_similarity=0.7,  # Threshold above orthogonal similarity
        )

        # Should return empty list since orthogonal has similarity ~0
        assert results == []


class TestResponseSchema:
    """Tests for response schema (AC7)."""

    @pytest.mark.asyncio
    async def test_response_includes_all_required_fields(
        self, db_session, test_camera, mock_embedding_service
    ):
        """Test that results include all required fields."""
        source_embedding = [1.0] + [0.0] * 511

        create_event_with_embedding(
            db_session,
            "source-event",
            test_camera.id,
            source_embedding,
            "Source event description",
        )

        create_event_with_embedding(
            db_session,
            "similar-event",
            test_camera.id,
            [0.95] + [0.0] * 511,
            "Similar event description",
        )

        async def mock_get_embedding_vector(db, event_id):
            return source_embedding

        mock_embedding_service.get_embedding_vector = mock_get_embedding_vector

        service = SimilarityService(embedding_service=mock_embedding_service)
        results = await service.find_similar_events(
            db=db_session,
            event_id="source-event",
            min_similarity=0.5,
        )

        assert len(results) == 1
        result = results[0]

        # Check all required fields exist
        assert hasattr(result, 'event_id')
        assert hasattr(result, 'similarity_score')
        assert hasattr(result, 'thumbnail_url')
        assert hasattr(result, 'description')
        assert hasattr(result, 'timestamp')
        assert hasattr(result, 'camera_name')
        assert hasattr(result, 'camera_id')

        # Check field values
        assert result.event_id == "similar-event"
        assert 0.0 <= result.similarity_score <= 1.0
        assert result.description == "Similar event description"
        assert result.camera_name == "Front Door Camera"
        assert result.camera_id == test_camera.id
        assert isinstance(result.timestamp, datetime)
