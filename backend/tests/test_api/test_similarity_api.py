"""
API tests for Similarity Search endpoint (Story P4-3.2)

Tests:
- AC6: API endpoint GET /api/v1/context/similar/{event_id} returns similar events
- AC7: Similar event response includes required fields
- AC10: 404 returned when source event has no embedding
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.models.camera import Camera
from app.models.event import Event
from app.models.event_embedding import EventEmbedding
from app.api.v1.context import router
from app.services.similarity_service import (
    SimilarityService,
    SimilarEvent,
    get_similarity_service,
    reset_similarity_service,
)


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create database session."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def app(db_session):
    """Create FastAPI test app with database dependency override."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def test_camera(db_session):
    """Create test camera."""
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
def test_event(db_session, test_camera):
    """Create test event."""
    event = Event(
        id="test-event-001",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="A person walking by",
        confidence=85,
        objects_detected='["person"]',
        source_type="rtsp",
    )
    db_session.add(event)
    db_session.commit()
    return event


@pytest.fixture
def test_embedding(db_session, test_event):
    """Create test embedding for event."""
    embedding = EventEmbedding(
        event_id=test_event.id,
        embedding=json.dumps([0.1] * 512),
        model_version="clip-ViT-B-32-v1",
    )
    db_session.add(embedding)
    db_session.commit()
    return embedding


class TestSimilarEventsEndpoint:
    """Tests for GET /api/v1/context/similar/{event_id} endpoint (AC6)."""

    def test_similar_events_endpoint_exists(self, client, test_event, test_embedding, app):
        """Test that endpoint exists and is accessible."""
        # Mock the similarity service to return empty results
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])

        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}")

        # Should not return 405 (method not allowed) or 404 (endpoint not found)
        assert response.status_code == 200

    def test_similar_events_returns_correct_structure(
        self, client, test_event, test_embedding, app
    ):
        """Test that response has correct structure (AC7)."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])

        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}")
        data = response.json()

        assert "source_event_id" in data
        assert "similar_events" in data
        assert "total_results" in data
        assert "query_params" in data

        assert data["source_event_id"] == test_event.id
        assert isinstance(data["similar_events"], list)
        assert isinstance(data["total_results"], int)

    def test_similar_events_with_results(
        self, client, test_event, test_embedding, test_camera, app
    ):
        """Test that similar events are returned with all required fields (AC7)."""
        # Create mock similar event
        similar_event = SimilarEvent(
            event_id="similar-event-001",
            similarity_score=0.85,
            thumbnail_url="/api/v1/thumbnails/test.jpg",
            description="Another person walking",
            timestamp=datetime.now(timezone.utc),
            camera_name="Front Door Camera",
            camera_id=test_camera.id,
        )

        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[similar_event])

        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}")
        data = response.json()

        assert response.status_code == 200
        assert data["total_results"] == 1
        assert len(data["similar_events"]) == 1

        result = data["similar_events"][0]
        assert result["event_id"] == "similar-event-001"
        assert result["similarity_score"] == 0.85
        assert result["thumbnail_url"] == "/api/v1/thumbnails/test.jpg"
        assert result["description"] == "Another person walking"
        assert result["camera_name"] == "Front Door Camera"
        assert result["camera_id"] == test_camera.id
        assert "timestamp" in result


class TestQueryParameters:
    """Tests for query parameters."""

    def test_limit_parameter(self, client, test_event, test_embedding, app):
        """Test that limit parameter is passed correctly."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])

        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}?limit=5")

        assert response.status_code == 200
        # Verify limit was passed to service
        call_kwargs = mock_service.find_similar_events.call_args[1]
        assert call_kwargs["limit"] == 5

    def test_min_similarity_parameter(self, client, test_event, test_embedding, app):
        """Test that min_similarity parameter is passed correctly."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])

        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}?min_similarity=0.8")

        assert response.status_code == 200
        call_kwargs = mock_service.find_similar_events.call_args[1]
        assert call_kwargs["min_similarity"] == 0.8

    def test_time_window_days_parameter(self, client, test_event, test_embedding, app):
        """Test that time_window_days parameter is passed correctly."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])

        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}?time_window_days=60")

        assert response.status_code == 200
        call_kwargs = mock_service.find_similar_events.call_args[1]
        assert call_kwargs["time_window_days"] == 60

    def test_camera_id_parameter(self, client, test_event, test_embedding, app):
        """Test that camera_id parameter is passed correctly."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])

        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(
            f"/api/v1/context/similar/{test_event.id}?camera_id=test-camera-001"
        )

        assert response.status_code == 200
        call_kwargs = mock_service.find_similar_events.call_args[1]
        assert call_kwargs["camera_id"] == "test-camera-001"

    def test_query_params_in_response(self, client, test_event, test_embedding, app):
        """Test that query params are included in response."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])

        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(
            f"/api/v1/context/similar/{test_event.id}"
            "?limit=5&min_similarity=0.8&time_window_days=60&camera_id=test-cam"
        )

        data = response.json()
        assert data["query_params"]["limit"] == 5
        assert data["query_params"]["min_similarity"] == 0.8
        assert data["query_params"]["time_window_days"] == 60
        assert data["query_params"]["camera_id"] == "test-cam"


class TestParameterValidation:
    """Tests for parameter validation."""

    def test_limit_min_validation(self, client, test_event, test_embedding, app):
        """Test that limit < 1 is rejected."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])
        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}?limit=0")
        assert response.status_code == 422  # Validation error

    def test_limit_max_validation(self, client, test_event, test_embedding, app):
        """Test that limit > 100 is rejected."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])
        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}?limit=101")
        assert response.status_code == 422

    def test_min_similarity_range_validation(self, client, test_event, test_embedding, app):
        """Test that min_similarity outside 0-1 is rejected."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])
        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        # Greater than 1
        response = client.get(f"/api/v1/context/similar/{test_event.id}?min_similarity=1.5")
        assert response.status_code == 422

        # Less than 0
        response = client.get(f"/api/v1/context/similar/{test_event.id}?min_similarity=-0.5")
        assert response.status_code == 422


class TestErrorHandling:
    """Tests for error handling (AC10)."""

    def test_event_not_found_returns_404(self, tmp_path):
        """Test that non-existent event returns 404.

        Creates its own file-based database to avoid SQLite in-memory threading issues.
        """
        import os

        # Create file-based database to avoid in-memory threading issues
        db_path = tmp_path / "test.db"
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Create app with proper db override
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/v1")

        def override_get_db():
            session = SessionLocal()
            try:
                yield session
            finally:
                session.close()

        test_app.dependency_overrides[get_db] = override_get_db

        mock_service = MagicMock(spec=SimilarityService)
        test_app.dependency_overrides[get_similarity_service] = lambda: mock_service

        client = TestClient(test_app)
        response = client.get("/api/v1/context/similar/non-existent-event-id")

        assert response.status_code == 404
        assert "Event not found" in response.json()["detail"]

    def test_event_without_embedding_returns_404(self, client, test_event, app):
        """Test that event without embedding returns 404 (AC10)."""
        # test_event exists but has no embedding (no test_embedding fixture)
        mock_service = MagicMock(spec=SimilarityService)
        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}")

        assert response.status_code == 404
        assert "no embedding" in response.json()["detail"].lower()


class TestEmptyResults:
    """Tests for empty results handling (AC9)."""

    def test_empty_results_returns_success(self, client, test_event, test_embedding, app):
        """Test that empty results returns 200 with empty list (not error)."""
        mock_service = MagicMock(spec=SimilarityService)
        mock_service.find_similar_events = AsyncMock(return_value=[])

        app.dependency_overrides[get_similarity_service] = lambda: mock_service

        response = client.get(f"/api/v1/context/similar/{test_event.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["similar_events"] == []
        assert data["total_results"] == 0
