"""
API tests for Person Matching endpoints (Story P4-8.2)

Tests the REST API endpoints for person management:
- GET /api/v1/context/persons
- GET /api/v1/context/persons/{id}
- PUT /api/v1/context/persons/{id}
"""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    return session


@pytest.fixture
def mock_person():
    """Create a mock person dict."""
    return {
        "id": str(uuid.uuid4()),
        "name": "Test Person",
        "first_seen_at": datetime.now(timezone.utc),
        "last_seen_at": datetime.now(timezone.utc),
        "occurrence_count": 5,
        "face_count": 3,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


class TestListPersonsEndpoint:
    """Tests for GET /api/v1/context/persons endpoint."""

    @pytest.mark.asyncio
    async def test_list_persons_empty(self):
        """Test listing persons when none exist."""
        from app.api.v1.context import list_persons
        from app.services.person_matching_service import PersonMatchingService

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.get_persons = AsyncMock(return_value=([], 0))

        result = await list_persons(
            limit=50,
            offset=0,
            named_only=False,
            db=mock_db,
            person_service=mock_service,
        )

        assert result.persons == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_persons_with_data(self, mock_person):
        """Test listing persons with data."""
        from app.api.v1.context import list_persons
        from app.services.person_matching_service import PersonMatchingService

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.get_persons = AsyncMock(return_value=([mock_person], 1))

        result = await list_persons(
            limit=50,
            offset=0,
            named_only=False,
            db=mock_db,
            person_service=mock_service,
        )

        assert len(result.persons) == 1
        assert result.total == 1
        assert result.persons[0].id == mock_person["id"]
        assert result.persons[0].name == mock_person["name"]
        assert result.persons[0].face_count == mock_person["face_count"]

    @pytest.mark.asyncio
    async def test_list_persons_named_only(self, mock_person):
        """Test listing only named persons."""
        from app.api.v1.context import list_persons
        from app.services.person_matching_service import PersonMatchingService

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.get_persons = AsyncMock(return_value=([mock_person], 1))

        result = await list_persons(
            limit=50,
            offset=0,
            named_only=True,
            db=mock_db,
            person_service=mock_service,
        )

        # Verify named_only was passed to service
        mock_service.get_persons.assert_called_once_with(
            mock_db,
            limit=50,
            offset=0,
            named_only=True,
        )

    @pytest.mark.asyncio
    async def test_list_persons_pagination(self, mock_person):
        """Test pagination parameters."""
        from app.api.v1.context import list_persons
        from app.services.person_matching_service import PersonMatchingService

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.get_persons = AsyncMock(return_value=([mock_person], 10))

        result = await list_persons(
            limit=5,
            offset=5,
            named_only=False,
            db=mock_db,
            person_service=mock_service,
        )

        assert result.limit == 5
        assert result.offset == 5
        mock_service.get_persons.assert_called_once_with(
            mock_db,
            limit=5,
            offset=5,
            named_only=False,
        )


class TestGetPersonEndpoint:
    """Tests for GET /api/v1/context/persons/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_person_not_found(self):
        """Test getting non-existent person returns 404."""
        from app.api.v1.context import get_person
        from app.services.person_matching_service import PersonMatchingService

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.get_person = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_person(
                person_id="nonexistent",
                include_faces=True,
                face_limit=10,
                db=mock_db,
                person_service=mock_service,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_get_person_found(self, mock_person):
        """Test getting existing person."""
        from app.api.v1.context import get_person
        from app.services.person_matching_service import PersonMatchingService

        mock_person_with_faces = {
            **mock_person,
            "recent_faces": [
                {
                    "id": str(uuid.uuid4()),
                    "event_id": str(uuid.uuid4()),
                    "bounding_box": {"x": 10, "y": 20, "width": 50, "height": 50},
                    "confidence": 0.95,
                    "created_at": datetime.now(timezone.utc),
                    "event_timestamp": datetime.now(timezone.utc),
                    "thumbnail_url": "/thumbnails/test.jpg",
                }
            ]
        }

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.get_person = AsyncMock(return_value=mock_person_with_faces)

        result = await get_person(
            person_id=mock_person["id"],
            include_faces=True,
            face_limit=10,
            db=mock_db,
            person_service=mock_service,
        )

        assert result.id == mock_person["id"]
        assert result.name == mock_person["name"]
        assert len(result.recent_faces) == 1

    @pytest.mark.asyncio
    async def test_get_person_without_faces(self, mock_person):
        """Test getting person without faces."""
        from app.api.v1.context import get_person
        from app.services.person_matching_service import PersonMatchingService

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.get_person = AsyncMock(return_value=mock_person)

        result = await get_person(
            person_id=mock_person["id"],
            include_faces=False,
            face_limit=10,
            db=mock_db,
            person_service=mock_service,
        )

        assert result.id == mock_person["id"]
        assert result.recent_faces == []


class TestUpdatePersonEndpoint:
    """Tests for PUT /api/v1/context/persons/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_person_not_found(self):
        """Test updating non-existent person returns 404."""
        from app.api.v1.context import update_person, PersonUpdateRequest
        from app.services.person_matching_service import PersonMatchingService

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.update_person_name = AsyncMock(return_value=None)

        request = PersonUpdateRequest(name="New Name")

        with pytest.raises(HTTPException) as exc_info:
            await update_person(
                person_id="nonexistent",
                request=request,
                db=mock_db,
                person_service=mock_service,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_person_name(self, mock_person):
        """Test updating person name."""
        from app.api.v1.context import update_person, PersonUpdateRequest
        from app.services.person_matching_service import PersonMatchingService

        updated_person = {
            "id": mock_person["id"],
            "name": "John Doe",
            "first_seen_at": mock_person["first_seen_at"],
            "last_seen_at": mock_person["last_seen_at"],
            "occurrence_count": mock_person["occurrence_count"],
        }

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.update_person_name = AsyncMock(return_value=updated_person)

        request = PersonUpdateRequest(name="John Doe")

        result = await update_person(
            person_id=mock_person["id"],
            request=request,
            db=mock_db,
            person_service=mock_service,
        )

        assert result.id == mock_person["id"]
        assert result.name == "John Doe"
        mock_service.update_person_name.assert_called_once_with(
            mock_db,
            mock_person["id"],
            name="John Doe",
        )

    @pytest.mark.asyncio
    async def test_update_person_clear_name(self, mock_person):
        """Test clearing person name."""
        from app.api.v1.context import update_person, PersonUpdateRequest
        from app.services.person_matching_service import PersonMatchingService

        updated_person = {
            "id": mock_person["id"],
            "name": None,
            "first_seen_at": mock_person["first_seen_at"],
            "last_seen_at": mock_person["last_seen_at"],
            "occurrence_count": mock_person["occurrence_count"],
        }

        mock_db = MagicMock()
        mock_service = MagicMock(spec=PersonMatchingService)
        mock_service.update_person_name = AsyncMock(return_value=updated_person)

        request = PersonUpdateRequest(name=None)

        result = await update_person(
            person_id=mock_person["id"],
            request=request,
            db=mock_db,
            person_service=mock_service,
        )

        assert result.name is None
