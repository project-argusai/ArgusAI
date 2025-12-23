"""
API tests for Context Adjustments endpoints (Story P9-4.6)

Tests:
- AC-4.6.4: GET /api/v1/context/adjustments endpoint with pagination and filtering
- AC-4.6.5: GET /api/v1/context/adjustments/export endpoint for ML training data
"""
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.context import (
    router,
    AdjustmentResponse,
    AdjustmentListResponse,
)
from app.services.entity_service import EntityService, get_entity_service
from app.core.database import get_db


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def mock_entity_service():
    """Create a mock entity service."""
    service = MagicMock(spec=EntityService)
    return service


@pytest.fixture
def test_app(mock_db, mock_entity_service):
    """Create FastAPI test app with mocked dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_entity_service] = lambda: mock_entity_service

    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


class TestAdjustmentResponseModels:
    """Tests for adjustment response model structures."""

    def test_adjustment_response_model(self):
        """Test AdjustmentResponse model structure."""
        now = datetime.now(timezone.utc)
        response = AdjustmentResponse(
            id="adj-123",
            event_id="event-456",
            old_entity_id="old-entity-789",
            new_entity_id=None,
            action="unlink",
            event_description="Person walking",
            created_at=now,
        )

        assert response.id == "adj-123"
        assert response.event_id == "event-456"
        assert response.old_entity_id == "old-entity-789"
        assert response.new_entity_id is None
        assert response.action == "unlink"
        assert response.event_description == "Person walking"
        assert response.created_at == now

    def test_adjustment_response_assign_action(self):
        """Test AdjustmentResponse for assign action (old_entity_id is None)."""
        response = AdjustmentResponse(
            id="adj-123",
            event_id="event-456",
            old_entity_id=None,
            new_entity_id="new-entity-789",
            action="assign",
            event_description="White Toyota Camry",
            created_at=datetime.now(timezone.utc),
        )

        assert response.old_entity_id is None
        assert response.new_entity_id == "new-entity-789"
        assert response.action == "assign"

    def test_adjustment_list_response_model(self):
        """Test AdjustmentListResponse model structure."""
        now = datetime.now(timezone.utc)
        adjustments = [
            AdjustmentResponse(
                id="adj-1",
                event_id="event-1",
                old_entity_id="entity-1",
                new_entity_id=None,
                action="unlink",
                event_description="Test event 1",
                created_at=now,
            ),
            AdjustmentResponse(
                id="adj-2",
                event_id="event-2",
                old_entity_id=None,
                new_entity_id="entity-2",
                action="assign",
                event_description="Test event 2",
                created_at=now,
            ),
        ]

        response = AdjustmentListResponse(
            adjustments=adjustments,
            total=100,
            page=1,
            limit=50,
        )

        assert len(response.adjustments) == 2
        assert response.total == 100
        assert response.page == 1
        assert response.limit == 50


class TestGetAdjustmentsEndpoint:
    """Tests for GET /api/v1/context/adjustments endpoint (AC-4.6.4)."""

    def test_get_adjustments_default_pagination(self, client, mock_entity_service):
        """Test getting adjustments with default pagination."""
        now = datetime.now(timezone.utc)
        mock_adjustments = [
            {
                "id": "adj-1",
                "event_id": "event-1",
                "old_entity_id": "entity-1",
                "new_entity_id": None,
                "action": "unlink",
                "event_description": "Person walking",
                "created_at": now,
            }
        ]

        mock_entity_service.get_adjustments = AsyncMock(
            return_value=(mock_adjustments, 1)
        )

        response = client.get("/api/v1/context/adjustments")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["limit"] == 50
        assert data["total"] == 1
        assert len(data["adjustments"]) == 1

    def test_get_adjustments_with_pagination(self, client, mock_entity_service):
        """Test getting adjustments with custom pagination."""
        mock_entity_service.get_adjustments = AsyncMock(return_value=([], 50))

        response = client.get("/api/v1/context/adjustments?page=2&limit=25")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["limit"] == 25

        # Verify offset calculation
        mock_entity_service.get_adjustments.assert_called_once()
        call_kwargs = mock_entity_service.get_adjustments.call_args[1]
        assert call_kwargs["offset"] == 25  # (page 2 - 1) * 25

    def test_get_adjustments_filter_by_action(self, client, mock_entity_service):
        """Test filtering adjustments by action type."""
        mock_entity_service.get_adjustments = AsyncMock(return_value=([], 0))

        response = client.get("/api/v1/context/adjustments?action=unlink")

        assert response.status_code == 200
        call_kwargs = mock_entity_service.get_adjustments.call_args[1]
        assert call_kwargs["action"] == "unlink"

    def test_get_adjustments_filter_by_entity_id(self, client, mock_entity_service):
        """Test filtering adjustments by entity ID."""
        mock_entity_service.get_adjustments = AsyncMock(return_value=([], 0))

        entity_id = "test-entity-uuid"
        response = client.get(f"/api/v1/context/adjustments?entity_id={entity_id}")

        assert response.status_code == 200
        call_kwargs = mock_entity_service.get_adjustments.call_args[1]
        assert call_kwargs["entity_id"] == entity_id

    def test_get_adjustments_filter_by_date_range(self, client, mock_entity_service):
        """Test filtering adjustments by date range."""
        mock_entity_service.get_adjustments = AsyncMock(return_value=([], 0))

        start = "2025-01-01T00:00:00Z"
        end = "2025-12-31T23:59:59Z"
        response = client.get(
            f"/api/v1/context/adjustments?start_date={start}&end_date={end}"
        )

        assert response.status_code == 200
        call_kwargs = mock_entity_service.get_adjustments.call_args[1]
        assert call_kwargs["start_date"] is not None
        assert call_kwargs["end_date"] is not None

    def test_get_adjustments_invalid_action(self, client, mock_entity_service):
        """Test that invalid action type returns 400 error."""
        response = client.get("/api/v1/context/adjustments?action=invalid")

        assert response.status_code == 400
        assert "Invalid action" in response.json()["detail"]

    def test_get_adjustments_valid_actions(self, client, mock_entity_service):
        """Test that all valid action types are accepted."""
        mock_entity_service.get_adjustments = AsyncMock(return_value=([], 0))

        valid_actions = ["unlink", "assign", "move", "move_from", "move_to", "merge"]

        for action in valid_actions:
            response = client.get(f"/api/v1/context/adjustments?action={action}")
            assert response.status_code == 200, f"Action '{action}' should be valid"

    def test_get_adjustments_limit_validation(self, client, mock_entity_service):
        """Test that limit is validated (1-100)."""
        mock_entity_service.get_adjustments = AsyncMock(return_value=([], 0))

        # Valid limit
        response = client.get("/api/v1/context/adjustments?limit=100")
        assert response.status_code == 200

        # Invalid limit (too high)
        response = client.get("/api/v1/context/adjustments?limit=101")
        assert response.status_code == 422  # Validation error

        # Invalid limit (too low)
        response = client.get("/api/v1/context/adjustments?limit=0")
        assert response.status_code == 422


class TestExportAdjustmentsEndpoint:
    """Tests for GET /api/v1/context/adjustments/export endpoint (AC-4.6.5)."""

    def test_export_adjustments_returns_jsonl(self, client, mock_entity_service):
        """Test that export returns JSON Lines format."""
        now = datetime.now(timezone.utc)
        mock_adjustments = [
            {
                "event_id": "event-1",
                "action": "unlink",
                "old_entity_id": "entity-1",
                "new_entity_id": None,
                "old_entity_type": "person",
                "new_entity_type": None,
                "event_description": "Person walking",
                "created_at": now.isoformat(),
            },
            {
                "event_id": "event-2",
                "action": "assign",
                "old_entity_id": None,
                "new_entity_id": "entity-2",
                "old_entity_type": None,
                "new_entity_type": "vehicle",
                "event_description": "White Toyota",
                "created_at": now.isoformat(),
            },
        ]

        mock_entity_service.export_adjustments = AsyncMock(
            return_value=mock_adjustments
        )

        response = client.get("/api/v1/context/adjustments/export")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-ndjson"
        assert "attachment" in response.headers["content-disposition"]

        # Parse JSON Lines
        lines = response.text.strip().split("\n")
        assert len(lines) == 2

        # Verify each line is valid JSON
        for line in lines:
            parsed = json.loads(line)
            assert "event_id" in parsed
            assert "action" in parsed

    def test_export_adjustments_with_date_filter(self, client, mock_entity_service):
        """Test export with date range filter."""
        mock_entity_service.export_adjustments = AsyncMock(return_value=[])

        start = "2025-01-01T00:00:00Z"
        end = "2025-12-31T23:59:59Z"
        response = client.get(
            f"/api/v1/context/adjustments/export?start_date={start}&end_date={end}"
        )

        assert response.status_code == 200
        call_kwargs = mock_entity_service.export_adjustments.call_args[1]
        assert call_kwargs["start_date"] is not None
        assert call_kwargs["end_date"] is not None

    def test_export_adjustments_empty_result(self, client, mock_entity_service):
        """Test export with no adjustments returns empty response."""
        mock_entity_service.export_adjustments = AsyncMock(return_value=[])

        response = client.get("/api/v1/context/adjustments/export")

        assert response.status_code == 200
        assert response.text == ""

    def test_export_adjustments_includes_entity_types(self, client, mock_entity_service):
        """Test that export includes entity types for ML training."""
        mock_adjustments = [
            {
                "event_id": "event-1",
                "action": "merge",
                "old_entity_id": "old-id",
                "new_entity_id": "new-id",
                "old_entity_type": "person",
                "new_entity_type": "person",
                "event_description": "Person detected",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]

        mock_entity_service.export_adjustments = AsyncMock(
            return_value=mock_adjustments
        )

        response = client.get("/api/v1/context/adjustments/export")

        assert response.status_code == 200
        line = response.text.strip()
        parsed = json.loads(line)
        assert parsed["old_entity_type"] == "person"
        assert parsed["new_entity_type"] == "person"
