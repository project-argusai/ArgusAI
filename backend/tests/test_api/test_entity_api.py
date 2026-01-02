"""
API tests for Entity endpoints (Story P4-3.3: Recurring Visitor Detection)

Tests:
- AC7: GET /api/v1/context/entities returns list of entities with stats
- AC8: GET /api/v1/context/entities/{id} returns entity with events
- AC9: PUT /api/v1/context/entities/{id} allows naming entity
- AC10: DELETE /api/v1/context/entities/{id} removes entity
- AC12: Event response includes matched_entity data
"""
import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.context import router
from app.services.entity_service import reset_entity_service


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return MagicMock()


@pytest.fixture
def mock_entity_service():
    """Create mock EntityService."""
    service = AsyncMock()
    return service


@pytest.fixture
def app(mock_db, mock_entity_service):
    """Create FastAPI test app with dependency overrides."""
    reset_entity_service()

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield mock_db

    def override_get_entity_service():
        return mock_entity_service

    from app.core.database import get_db
    from app.services.entity_service import get_entity_service

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_entity_service] = override_get_entity_service

    yield test_app

    reset_entity_service()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestListEntitiesAPI:
    """Tests for GET /api/v1/context/entities endpoint (AC7)."""

    def test_get_entities_returns_empty_list(self, client, mock_entity_service):
        """Test that endpoint returns empty list when no entities."""
        mock_entity_service.get_all_entities.return_value = ([], 0)

        response = client.get("/api/v1/context/entities")

        assert response.status_code == 200
        data = response.json()
        assert data["entities"] == []
        assert data["total"] == 0

    def test_get_entities_returns_list(self, client, mock_entity_service):
        """AC7: GET /api/v1/context/entities returns list of entities."""
        entities = [{
            "id": "test-entity-001",
            "entity_type": "person",
            "name": None,
            "first_seen_at": datetime.now(timezone.utc) - timedelta(days=7),
            "last_seen_at": datetime.now(timezone.utc),
            "occurrence_count": 5,
        }]
        mock_entity_service.get_all_entities.return_value = (entities, 1)

        response = client.get("/api/v1/context/entities")

        assert response.status_code == 200
        data = response.json()
        assert len(data["entities"]) == 1
        assert data["total"] == 1
        assert data["entities"][0]["id"] == "test-entity-001"
        assert data["entities"][0]["entity_type"] == "person"

    def test_get_entities_with_type_filter(self, client, mock_entity_service):
        """Test filtering entities by type."""
        mock_entity_service.get_all_entities.return_value = ([], 0)

        response = client.get("/api/v1/context/entities?entity_type=person")

        assert response.status_code == 200
        mock_entity_service.get_all_entities.assert_called_once()
        call_kwargs = mock_entity_service.get_all_entities.call_args[1]
        assert call_kwargs["entity_type"] == "person"


class TestGetEntityAPI:
    """Tests for GET /api/v1/context/entities/{id} endpoint (AC8)."""

    def test_get_entity_returns_details(self, client, mock_entity_service):
        """AC8: GET /api/v1/context/entities/{id} returns entity with events."""
        mock_entity_service.get_entity.return_value = {
            "id": "test-entity-001",
            "entity_type": "person",
            "name": "Mail Carrier",
            "first_seen_at": datetime.now(timezone.utc) - timedelta(days=7),
            "last_seen_at": datetime.now(timezone.utc),
            "occurrence_count": 5,
            "created_at": datetime.now(timezone.utc) - timedelta(days=7),
            "updated_at": datetime.now(timezone.utc),
            "recent_events": [{
                "id": "event-001",
                "timestamp": datetime.now(timezone.utc),
                "description": "Person at door",
                "thumbnail_url": "/api/v1/thumbnails/test.jpg",
                "camera_id": "camera-001",
                "similarity_score": 0.92,
            }],
        }

        response = client.get("/api/v1/context/entities/test-entity-001")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-entity-001"
        assert data["name"] == "Mail Carrier"
        assert len(data["recent_events"]) == 1

    def test_get_entity_not_found(self, client, mock_entity_service):
        """Test 404 when entity not found."""
        mock_entity_service.get_entity.return_value = None

        response = client.get("/api/v1/context/entities/nonexistent-id")

        assert response.status_code == 404


class TestUpdateEntityAPI:
    """Tests for PUT /api/v1/context/entities/{id} endpoint (AC9, P16-3.1)."""

    def test_update_entity_name(self, client, mock_entity_service):
        """AC9: PUT /api/v1/context/entities/{id} allows naming entity."""
        mock_entity_service.update_entity.return_value = {
            "id": "test-entity-001",
            "entity_type": "person",
            "name": "Mail Carrier",
            "first_seen_at": datetime.now(timezone.utc) - timedelta(days=7),
            "last_seen_at": datetime.now(timezone.utc),
            "occurrence_count": 5,
        }

        response = client.put(
            "/api/v1/context/entities/test-entity-001",
            json={"name": "Mail Carrier"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Mail Carrier"

    def test_update_entity_type(self, client, mock_entity_service):
        """P16-3.1 AC1: Update entity_type field."""
        mock_entity_service.update_entity.return_value = {
            "id": "test-entity-001",
            "entity_type": "vehicle",
            "name": None,
            "first_seen_at": datetime.now(timezone.utc) - timedelta(days=7),
            "last_seen_at": datetime.now(timezone.utc),
            "occurrence_count": 3,
        }

        response = client.put(
            "/api/v1/context/entities/test-entity-001",
            json={"entity_type": "vehicle"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_type"] == "vehicle"
        # Verify service was called with entity_type
        mock_entity_service.update_entity.assert_called_once()
        call_kwargs = mock_entity_service.update_entity.call_args[1]
        assert call_kwargs["entity_type"] == "vehicle"

    def test_update_entity_type_all_valid_values(self, client, mock_entity_service):
        """P16-3.1 AC5: entity_type must be person, vehicle, or unknown."""
        for entity_type in ["person", "vehicle", "unknown"]:
            mock_entity_service.update_entity.return_value = {
                "id": "test-entity-001",
                "entity_type": entity_type,
                "name": None,
                "first_seen_at": datetime.now(timezone.utc),
                "last_seen_at": datetime.now(timezone.utc),
                "occurrence_count": 1,
            }

            response = client.put(
                "/api/v1/context/entities/test-entity-001",
                json={"entity_type": entity_type}
            )

            assert response.status_code == 200, f"Failed for entity_type={entity_type}"
            data = response.json()
            assert data["entity_type"] == entity_type

    def test_update_entity_type_invalid_returns_422(self, client, mock_entity_service):
        """P16-3.1 AC3: Invalid entity_type returns 422 validation error."""
        response = client.put(
            "/api/v1/context/entities/test-entity-001",
            json={"entity_type": "invalid"}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_update_entity_notes_max_length(self, client, mock_entity_service):
        """P16-3.1 AC7: notes max length is 2000 characters."""
        # Test with notes at max length (should succeed)
        notes_at_limit = "x" * 2000
        mock_entity_service.update_entity.return_value = {
            "id": "test-entity-001",
            "entity_type": "person",
            "name": None,
            "notes": notes_at_limit,
            "first_seen_at": datetime.now(timezone.utc),
            "last_seen_at": datetime.now(timezone.utc),
            "occurrence_count": 1,
        }

        response = client.put(
            "/api/v1/context/entities/test-entity-001",
            json={"notes": notes_at_limit}
        )

        assert response.status_code == 200

    def test_update_entity_notes_exceeds_max_length(self, client, mock_entity_service):
        """P16-3.1 AC7: notes exceeding 2000 characters returns 422."""
        notes_over_limit = "x" * 2001

        response = client.put(
            "/api/v1/context/entities/test-entity-001",
            json={"notes": notes_over_limit}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_update_entity_partial_update(self, client, mock_entity_service):
        """P16-3.1 AC2: Partial updates only change specified fields."""
        mock_entity_service.update_entity.return_value = {
            "id": "test-entity-001",
            "entity_type": "person",
            "name": "Original Name",
            "is_vip": True,
            "is_blocked": False,
            "first_seen_at": datetime.now(timezone.utc),
            "last_seen_at": datetime.now(timezone.utc),
            "occurrence_count": 1,
        }

        response = client.put(
            "/api/v1/context/entities/test-entity-001",
            json={"is_vip": True}
        )

        assert response.status_code == 200
        # Verify only is_vip was passed to service
        call_kwargs = mock_entity_service.update_entity.call_args[1]
        assert call_kwargs["is_vip"] is True
        assert call_kwargs["name"] is None  # Not provided, should be None
        assert call_kwargs["entity_type"] is None  # Not provided

    def test_update_entity_not_found(self, client, mock_entity_service):
        """Test 404 when entity not found."""
        mock_entity_service.update_entity.return_value = None

        response = client.put(
            "/api/v1/context/entities/nonexistent-id",
            json={"name": "Test"}
        )

        assert response.status_code == 404


class TestDeleteEntityAPI:
    """Tests for DELETE /api/v1/context/entities/{id} endpoint (AC10)."""

    def test_delete_entity_success(self, client, mock_entity_service):
        """AC10: DELETE /api/v1/context/entities/{id} removes entity."""
        mock_entity_service.delete_entity.return_value = True

        response = client.delete("/api/v1/context/entities/test-entity-001")

        assert response.status_code == 204

    def test_delete_entity_not_found(self, client, mock_entity_service):
        """Test 404 when entity not found."""
        mock_entity_service.delete_entity.return_value = False

        response = client.delete("/api/v1/context/entities/nonexistent-id")

        assert response.status_code == 404


class TestEntityResponseValidation:
    """Tests for entity response schema validation."""

    def test_entity_list_response_structure(self, client, mock_entity_service):
        """Test that entity list response has correct structure."""
        mock_entity_service.get_all_entities.return_value = ([], 0)

        response = client.get("/api/v1/context/entities")

        assert response.status_code == 200
        data = response.json()
        assert "entities" in data
        assert "total" in data
        assert isinstance(data["entities"], list)
        assert isinstance(data["total"], int)

    def test_entity_detail_response_structure(self, client, mock_entity_service):
        """Test that entity detail response has correct structure."""
        mock_entity_service.get_entity.return_value = {
            "id": "test-entity-001",
            "entity_type": "person",
            "name": None,
            "first_seen_at": datetime.now(timezone.utc),
            "last_seen_at": datetime.now(timezone.utc),
            "occurrence_count": 1,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "recent_events": [],
        }

        response = client.get("/api/v1/context/entities/test-entity-001")

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "entity_type" in data
        assert "name" in data
        assert "first_seen_at" in data
        assert "last_seen_at" in data
        assert "occurrence_count" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert "recent_events" in data


class TestQueryParameters:
    """Tests for query parameter handling."""

    def test_pagination_parameters(self, client, mock_entity_service):
        """Test pagination parameters are passed correctly."""
        mock_entity_service.get_all_entities.return_value = ([], 0)

        response = client.get("/api/v1/context/entities?limit=10&offset=20")

        assert response.status_code == 200
        call_kwargs = mock_entity_service.get_all_entities.call_args[1]
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 20

    def test_named_only_parameter(self, client, mock_entity_service):
        """Test named_only parameter is passed correctly."""
        mock_entity_service.get_all_entities.return_value = ([], 0)

        response = client.get("/api/v1/context/entities?named_only=true")

        assert response.status_code == 200
        call_kwargs = mock_entity_service.get_all_entities.call_args[1]
        assert call_kwargs["named_only"] is True
