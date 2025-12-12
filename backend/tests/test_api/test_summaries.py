"""
Integration tests for Summaries API (Story P4-4.1)

Tests:
- AC13: POST /api/v1/summaries/generate endpoint
- AC14: GET /api/v1/summaries/daily endpoint
- AC15: Validation errors (400 for invalid date ranges)
- AC16: Response schema verification
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from app.core.database import get_db
from app.services.summary_service import (
    SummaryService,
    get_summary_service,
    reset_summary_service,
    SummaryResult,
    SummaryStats,
)


# Shared mock instances (module level for persistence)
_mock_db = None
_mock_summary_service = None


def get_mock_db():
    """Get shared mock database session."""
    global _mock_db
    if _mock_db is None:
        _mock_db = MagicMock(spec=Session)
        # Set up default mock return values - VERY IMPORTANT: return None for cache checks
        # This ensures the endpoint calls generate_summary instead of returning cached result
        _mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = None
        _mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        _mock_db.query.return_value.filter.return_value.first.return_value = None
        _mock_db.query.return_value.count.return_value = 0
        _mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        _mock_db.add = MagicMock()
        _mock_db.commit = MagicMock()
        _mock_db.refresh = MagicMock()
    return _mock_db


def get_mock_summary_service():
    """Get shared mock summary service."""
    global _mock_summary_service
    if _mock_summary_service is None:
        _mock_summary_service = MagicMock(spec=SummaryService)
    return _mock_summary_service


# Mock database session fixture
@pytest.fixture
def mock_db():
    """Mock database session."""
    return get_mock_db()


# Mock summary service fixture
@pytest.fixture
def mock_summary_service():
    """Mock summary service."""
    return get_mock_summary_service()


@pytest.fixture
def client():
    """Create test client with mocked dependencies."""
    # Override dependencies with functions that return shared mocks
    app.dependency_overrides[get_db] = get_mock_db
    app.dependency_overrides[get_summary_service] = get_mock_summary_service

    yield TestClient(app)

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset mocks before each test."""
    global _mock_db, _mock_summary_service
    _mock_db = None
    _mock_summary_service = None
    reset_summary_service()
    yield
    reset_summary_service()


class TestGenerateSummaryEndpoint:
    """Tests for POST /api/v1/summaries/generate (AC13)."""

    def test_generate_summary_success(self, client, mock_summary_service):
        """Test successful summary generation."""
        # Mock generate_summary to return a successful result
        mock_summary_service.generate_summary = AsyncMock(return_value=SummaryResult(
            summary_text="Today was a quiet day with just the mail carrier visiting around noon.",
            period_start=datetime(2025, 12, 12, 0, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 12, 12, 23, 59, 59, tzinfo=timezone.utc),
            event_count=3,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(
                total_events=3,
                by_type={"person": 2, "vehicle": 1},
                by_camera={"Front Door": 3}
            ),
            ai_cost=Decimal("0.0001"),
            provider_used="openai",
            success=True
        ))

        response = client.post(
            "/api/v1/summaries/generate",
            json={
                "start_time": "2025-12-12T00:00:00Z",
                "end_time": "2025-12-12T23:59:59Z"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "summary_text" in data
        assert "period_start" in data
        assert "period_end" in data
        assert "event_count" in data
        assert "generated_at" in data

    def test_generate_summary_with_camera_ids(self, client, mock_summary_service):
        """Test summary generation with specific cameras."""
        mock_summary_service.generate_summary = AsyncMock(return_value=SummaryResult(
            summary_text="Activity on selected cameras.",
            period_start=datetime.now(timezone.utc) - timedelta(days=1),
            period_end=datetime.now(timezone.utc),
            event_count=5,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(total_events=5),
            success=True
        ))

        response = client.post(
            "/api/v1/summaries/generate",
            json={
                "start_time": "2025-12-11T00:00:00Z",
                "end_time": "2025-12-12T00:00:00Z",
                "camera_ids": ["cam-1", "cam-2"]
            }
        )

        assert response.status_code == 200

    def test_generate_summary_invalid_date_range(self, client):
        """Test 400 error for end_time before start_time (AC15)."""
        response = client.post(
            "/api/v1/summaries/generate",
            json={
                "start_time": "2025-12-12T23:59:59Z",
                "end_time": "2025-12-12T00:00:00Z"  # End before start
            }
        )

        assert response.status_code == 400
        assert "end_time must be after start_time" in response.json()["detail"]

    def test_generate_summary_future_date_rejected(self, client):
        """Test 400 error for future dates > 1 day (AC15)."""
        future_date = datetime.now(timezone.utc) + timedelta(days=10)

        response = client.post(
            "/api/v1/summaries/generate",
            json={
                "start_time": "2025-12-12T00:00:00Z",
                "end_time": future_date.isoformat()
            }
        )

        assert response.status_code == 400
        assert "future" in response.json()["detail"].lower()


class TestDailySummaryEndpoint:
    """Tests for GET /api/v1/summaries/daily (AC14)."""

    def test_daily_summary_success(self, client, mock_summary_service):
        """Test successful daily summary retrieval."""
        mock_summary_service.generate_summary = AsyncMock(return_value=SummaryResult(
            summary_text="Quiet day on December 11th.",
            period_start=datetime(2025, 12, 11, 0, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 12, 11, 23, 59, 59, tzinfo=timezone.utc),
            event_count=2,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(total_events=2),
            success=True
        ))

        response = client.get("/api/v1/summaries/daily?date=2025-12-11")

        assert response.status_code == 200
        data = response.json()
        assert "date" in data
        assert data["date"] == "2025-12-11"
        assert "cached" in data

    def test_daily_summary_invalid_date_format(self, client):
        """Test 400 for invalid date format."""
        response = client.get("/api/v1/summaries/daily?date=12-11-2025")

        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    def test_daily_summary_future_date_rejected(self, client):
        """Test 400 for future dates > 1 day (AC15)."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")

        response = client.get(f"/api/v1/summaries/daily?date={future_date}")

        assert response.status_code == 400
        assert "future" in response.json()["detail"].lower()

    def test_daily_summary_with_cameras(self, client, mock_summary_service):
        """Test daily summary with camera filter."""
        mock_summary_service.generate_summary = AsyncMock(return_value=SummaryResult(
            summary_text="Camera-specific summary.",
            period_start=datetime.now(timezone.utc) - timedelta(days=1),
            period_end=datetime.now(timezone.utc),
            event_count=5,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(total_events=5),
            success=True
        ))

        response = client.get(
            "/api/v1/summaries/daily?date=2025-12-11&camera_ids=cam-1,cam-2"
        )

        assert response.status_code == 200


class TestResponseSchema:
    """Tests for response schema compliance (AC16)."""

    def test_response_includes_required_fields(self, client, mock_summary_service):
        """Test response includes all required fields."""
        mock_summary_service.generate_summary = AsyncMock(return_value=SummaryResult(
            summary_text="Test summary",
            period_start=datetime(2025, 12, 12, 0, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 12, 12, 23, 59, 59, tzinfo=timezone.utc),
            event_count=10,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(total_events=10),
            ai_cost=Decimal("0.0001"),
            provider_used="openai",
            success=True
        ))

        response = client.post(
            "/api/v1/summaries/generate",
            json={
                "start_time": "2025-12-12T00:00:00Z",
                "end_time": "2025-12-12T23:59:59Z"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # AC16: Required fields
        assert "summary_text" in data
        assert "period_start" in data
        assert "period_end" in data
        assert "event_count" in data
        assert "generated_at" in data

        # Verify types
        assert isinstance(data["summary_text"], str)
        assert isinstance(data["event_count"], int)

    def test_stats_included_when_generated(self, client, mock_summary_service):
        """Test stats are included for fresh generation."""
        mock_summary_service.generate_summary = AsyncMock(return_value=SummaryResult(
            summary_text="Test summary",
            period_start=datetime(2025, 12, 12, 0, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 12, 12, 23, 59, 59, tzinfo=timezone.utc),
            event_count=10,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(
                total_events=10,
                by_type={"person": 6, "vehicle": 4},
                by_camera={"Front Door": 7, "Driveway": 3},
                alerts_triggered=1,
                doorbell_rings=2
            ),
            success=True
        ))

        response = client.post(
            "/api/v1/summaries/generate",
            json={
                "start_time": "2025-12-12T00:00:00Z",
                "end_time": "2025-12-12T23:59:59Z"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert "stats" in data
        assert data["stats"]["total_events"] == 10
        assert data["stats"]["by_type"]["person"] == 6


class TestListSummaries:
    """Tests for GET /api/v1/summaries endpoint."""

    def test_list_summaries_empty(self, client, mock_db):
        """Test listing summaries when none exist."""
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        response = client.get("/api/v1/summaries")

        assert response.status_code == 200
        data = response.json()
        assert "summaries" in data
        assert "total" in data
        assert len(data["summaries"]) == 0

    def test_list_summaries_pagination(self, client, mock_db):
        """Test listing summaries with pagination."""
        mock_db.query.return_value.count.return_value = 50
        mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        response = client.get("/api/v1/summaries?limit=10&offset=20")

        assert response.status_code == 200


class TestValidation:
    """Tests for input validation (AC15)."""

    def test_date_range_too_long(self, client):
        """Test 400 for date range > 90 days."""
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 6, 1, tzinfo=timezone.utc)  # 151 days

        response = client.post(
            "/api/v1/summaries/generate",
            json={
                "start_time": start.isoformat(),
                "end_time": end.isoformat()
            }
        )

        assert response.status_code == 400
        assert "90 days" in response.json()["detail"]

    def test_missing_required_fields(self, client):
        """Test 422 for missing required fields."""
        response = client.post(
            "/api/v1/summaries/generate",
            json={
                "start_time": "2025-12-12T00:00:00Z"
                # Missing end_time
            }
        )

        assert response.status_code == 422  # Pydantic validation error

    def test_invalid_datetime_format(self, client):
        """Test 422 for invalid datetime format."""
        response = client.post(
            "/api/v1/summaries/generate",
            json={
                "start_time": "not-a-date",
                "end_time": "also-not-a-date"
            }
        )

        assert response.status_code == 422
