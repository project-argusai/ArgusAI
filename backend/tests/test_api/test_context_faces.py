"""
API tests for Face Embedding endpoints (Story P4-8.1)

Tests the REST API endpoints for face embeddings:
- GET /api/v1/context/faces/{event_id}
- DELETE /api/v1/context/faces/{event_id}
- DELETE /api/v1/context/faces
- GET /api/v1/context/faces/stats
"""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    return session


@pytest.fixture
def mock_event():
    """Create a mock Event object."""
    from app.models.event import Event

    event = MagicMock(spec=Event)
    event.id = str(uuid.uuid4())
    event.camera_id = str(uuid.uuid4())
    event.timestamp = datetime.now(timezone.utc)
    event.description = "Test event"
    return event


@pytest.fixture
def mock_face_embedding():
    """Create a mock FaceEmbedding object."""
    from app.models.face_embedding import FaceEmbedding

    embedding = MagicMock(spec=FaceEmbedding)
    embedding.id = str(uuid.uuid4())
    embedding.event_id = str(uuid.uuid4())
    embedding.entity_id = None
    embedding.embedding = json.dumps([0.1] * 512)
    embedding.bounding_box = json.dumps({"x": 10, "y": 20, "width": 50, "height": 50})
    embedding.confidence = 0.95
    embedding.model_version = "clip-ViT-B-32-face-v1"
    embedding.created_at = datetime.now(timezone.utc)
    return embedding


class TestGetFaceEmbeddingsEndpoint:
    """Tests for GET /api/v1/context/faces/{event_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_face_embeddings_success(self):
        """Test successfully getting face embeddings for an event."""
        from app.api.v1.context import get_face_embeddings, FaceEmbeddingsResponse
        from app.services.face_embedding_service import FaceEmbeddingService

        event_id = str(uuid.uuid4())

        # Create mock event
        mock_event = MagicMock()
        mock_event.id = event_id

        # Create mock face embeddings
        mock_faces = [
            {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "entity_id": None,
                "bounding_box": {"x": 10, "y": 20, "width": 50, "height": 50},
                "confidence": 0.95,
                "model_version": "clip-ViT-B-32-face-v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "entity_id": None,
                "bounding_box": {"x": 100, "y": 30, "width": 60, "height": 60},
                "confidence": 0.85,
                "model_version": "clip-ViT-B-32-face-v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]

        # Mock database session
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        # Mock face service
        mock_face_service = MagicMock(spec=FaceEmbeddingService)
        mock_face_service.get_face_embeddings = AsyncMock(return_value=mock_faces)

        result = await get_face_embeddings(event_id, mock_db, mock_face_service)

        assert result.event_id == event_id
        assert result.face_count == 2
        assert len(result.faces) == 2
        assert result.faces[0].confidence == 0.95
        assert result.faces[1].confidence == 0.85

    @pytest.mark.asyncio
    async def test_get_face_embeddings_event_not_found(self):
        """Test getting face embeddings for non-existent event returns 404."""
        from app.api.v1.context import get_face_embeddings
        from app.services.face_embedding_service import FaceEmbeddingService
        from fastapi import HTTPException

        event_id = str(uuid.uuid4())

        # Mock database session - event not found
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_face_service = MagicMock(spec=FaceEmbeddingService)

        with pytest.raises(HTTPException) as exc_info:
            await get_face_embeddings(event_id, mock_db, mock_face_service)

        assert exc_info.value.status_code == 404
        assert "Event not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_face_embeddings_no_faces(self):
        """Test getting face embeddings when no faces exist."""
        from app.api.v1.context import get_face_embeddings
        from app.services.face_embedding_service import FaceEmbeddingService

        event_id = str(uuid.uuid4())

        mock_event = MagicMock()
        mock_event.id = event_id

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        mock_face_service = MagicMock(spec=FaceEmbeddingService)
        mock_face_service.get_face_embeddings = AsyncMock(return_value=[])

        result = await get_face_embeddings(event_id, mock_db, mock_face_service)

        assert result.event_id == event_id
        assert result.face_count == 0
        assert len(result.faces) == 0


class TestDeleteEventFacesEndpoint:
    """Tests for DELETE /api/v1/context/faces/{event_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_event_faces_success(self):
        """Test successfully deleting face embeddings for an event."""
        from app.api.v1.context import delete_event_faces
        from app.services.face_embedding_service import FaceEmbeddingService

        event_id = str(uuid.uuid4())

        mock_event = MagicMock()
        mock_event.id = event_id

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        mock_face_service = MagicMock(spec=FaceEmbeddingService)
        mock_face_service.delete_event_faces = AsyncMock(return_value=3)

        result = await delete_event_faces(event_id, mock_db, mock_face_service)

        assert result.deleted_count == 3
        assert "Deleted 3 face embedding(s)" in result.message

    @pytest.mark.asyncio
    async def test_delete_event_faces_event_not_found(self):
        """Test deleting face embeddings for non-existent event returns 404."""
        from app.api.v1.context import delete_event_faces
        from app.services.face_embedding_service import FaceEmbeddingService
        from fastapi import HTTPException

        event_id = str(uuid.uuid4())

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_face_service = MagicMock(spec=FaceEmbeddingService)

        with pytest.raises(HTTPException) as exc_info:
            await delete_event_faces(event_id, mock_db, mock_face_service)

        assert exc_info.value.status_code == 404


class TestDeleteAllFacesEndpoint:
    """Tests for DELETE /api/v1/context/faces endpoint."""

    @pytest.mark.asyncio
    async def test_delete_all_faces_success(self):
        """Test successfully deleting all face embeddings."""
        from app.api.v1.context import delete_all_faces
        from app.services.face_embedding_service import FaceEmbeddingService

        mock_db = MagicMock()

        mock_face_service = MagicMock(spec=FaceEmbeddingService)
        mock_face_service.delete_all_faces = AsyncMock(return_value=25)

        result = await delete_all_faces(mock_db, mock_face_service)

        assert result.deleted_count == 25
        assert "Deleted all 25 face embedding(s)" in result.message


class TestGetFaceStatsEndpoint:
    """Tests for GET /api/v1/context/faces/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_face_stats_success(self):
        """Test successfully getting face stats."""
        from app.api.v1.context import get_face_stats
        from app.services.face_embedding_service import FaceEmbeddingService
        from app.models.system_setting import SystemSetting

        mock_db = MagicMock()

        # Mock setting
        mock_setting = MagicMock(spec=SystemSetting)
        mock_setting.value = "true"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        mock_face_service = MagicMock(spec=FaceEmbeddingService)
        mock_face_service.get_total_face_count = AsyncMock(return_value=50)
        mock_face_service.get_model_version = MagicMock(return_value="clip-ViT-B-32-face-v1")

        result = await get_face_stats(mock_db, mock_face_service)

        assert result.total_face_embeddings == 50
        assert result.face_recognition_enabled is True
        assert result.model_version == "clip-ViT-B-32-face-v1"

    @pytest.mark.asyncio
    async def test_get_face_stats_disabled(self):
        """Test face stats when face recognition is disabled."""
        from app.api.v1.context import get_face_stats
        from app.services.face_embedding_service import FaceEmbeddingService
        from app.models.system_setting import SystemSetting

        mock_db = MagicMock()

        # Mock setting - disabled
        mock_setting = MagicMock(spec=SystemSetting)
        mock_setting.value = "false"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        mock_face_service = MagicMock(spec=FaceEmbeddingService)
        mock_face_service.get_total_face_count = AsyncMock(return_value=0)
        mock_face_service.get_model_version = MagicMock(return_value="clip-ViT-B-32-face-v1")

        result = await get_face_stats(mock_db, mock_face_service)

        assert result.total_face_embeddings == 0
        assert result.face_recognition_enabled is False

    @pytest.mark.asyncio
    async def test_get_face_stats_no_setting(self):
        """Test face stats when setting doesn't exist (default false)."""
        from app.api.v1.context import get_face_stats
        from app.services.face_embedding_service import FaceEmbeddingService

        mock_db = MagicMock()

        # Mock no setting found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_face_service = MagicMock(spec=FaceEmbeddingService)
        mock_face_service.get_total_face_count = AsyncMock(return_value=0)
        mock_face_service.get_model_version = MagicMock(return_value="clip-ViT-B-32-face-v1")

        result = await get_face_stats(mock_db, mock_face_service)

        # Should default to disabled when setting doesn't exist
        assert result.face_recognition_enabled is False
