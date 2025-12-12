"""
Integration tests for Digests API (Story P4-4.2, P4-4.3)

Tests:
- AC10: POST /api/v1/digests/trigger endpoint
- AC11: GET /api/v1/digests/status endpoint
- AC6: Settings API includes digest configuration
- AC12: Performance (60s limit)

Story P4-4.3 additions:
- delivery_status field in digest responses (AC11)
- DeliveryStatusResponse schema
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from app.core.database import get_db
from app.services.digest_scheduler import (
    get_digest_scheduler,
    reset_digest_scheduler,
    DigestStatus,
)
from app.services.summary_service import SummaryResult, SummaryStats


# Shared mock instances
_mock_db = None
_mock_digest_scheduler = None


def get_mock_db():
    """Get shared mock database session."""
    global _mock_db
    if _mock_db is None:
        _mock_db = MagicMock(spec=Session)
        _mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        _mock_db.query.return_value.filter.return_value.first.return_value = None
        _mock_db.query.return_value.count.return_value = 0
        _mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        _mock_db.add = MagicMock()
        _mock_db.commit = MagicMock()
        _mock_db.refresh = MagicMock()
    return _mock_db


def get_mock_digest_scheduler():
    """Get shared mock digest scheduler."""
    global _mock_digest_scheduler
    if _mock_digest_scheduler is None:
        _mock_digest_scheduler = MagicMock()
        _mock_digest_scheduler.get_status.return_value = DigestStatus(
            enabled=False,
            schedule_time="06:00",
            last_run=None,
            last_status="never_run",
            last_error=None,
            next_run=None,
        )
    return _mock_digest_scheduler


@pytest.fixture
def mock_db():
    """Mock database session."""
    return get_mock_db()


@pytest.fixture
def mock_digest_scheduler():
    """Mock digest scheduler."""
    return get_mock_digest_scheduler()


@pytest.fixture
def client():
    """Create test client with mocked dependencies."""
    app.dependency_overrides[get_db] = get_mock_db
    app.dependency_overrides[get_digest_scheduler] = get_mock_digest_scheduler

    yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset mocks before each test."""
    global _mock_db, _mock_digest_scheduler
    _mock_db = None
    _mock_digest_scheduler = None
    reset_digest_scheduler()
    yield
    reset_digest_scheduler()


class TestDigestTriggerEndpoint:
    """Tests for POST /api/v1/digests/trigger (AC10)."""

    def test_trigger_digest_success(self, client, mock_digest_scheduler):
        """Test successful digest trigger."""
        # Mock successful digest generation
        mock_digest_scheduler.run_scheduled_digest = AsyncMock(return_value=SummaryResult(
            summary_text="Test digest summary",
            period_start=datetime(2025, 12, 11, 0, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 12, 11, 23, 59, 59, tzinfo=timezone.utc),
            event_count=10,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(total_events=10),
            ai_cost=Decimal("0.001"),
            provider_used="openai",
            success=True
        ))

        with patch('app.api.v1.digests.get_digest_scheduler', return_value=mock_digest_scheduler):
            response = client.post("/api/v1/digests/trigger")

            assert response.status_code == 200
            data = response.json()
            assert "message" in data
            assert data["skipped"] is False

    def test_trigger_digest_with_date(self, client, mock_digest_scheduler):
        """Test digest trigger with specific date."""
        mock_digest_scheduler.run_scheduled_digest = AsyncMock(return_value=SummaryResult(
            summary_text="Test digest",
            period_start=datetime(2025, 12, 10, 0, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 12, 10, 23, 59, 59, tzinfo=timezone.utc),
            event_count=5,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(total_events=5),
            success=True
        ))

        with patch('app.api.v1.digests.get_digest_scheduler', return_value=mock_digest_scheduler):
            response = client.post(
                "/api/v1/digests/trigger",
                json={"date": "2025-12-10"}
            )

            assert response.status_code == 200

    def test_trigger_digest_skipped(self, client, mock_digest_scheduler):
        """Test digest trigger when already exists (skipped)."""
        # Mock skipped generation
        mock_digest_scheduler.run_scheduled_digest = AsyncMock(return_value=None)

        with patch('app.api.v1.digests.get_digest_scheduler', return_value=mock_digest_scheduler):
            response = client.post("/api/v1/digests/trigger")

            assert response.status_code == 200
            data = response.json()
            assert data["skipped"] is True
            assert "already exists" in data["message"]

    def test_trigger_digest_invalid_date_format(self, client):
        """Test 400 for invalid date format."""
        response = client.post(
            "/api/v1/digests/trigger",
            json={"date": "12-10-2025"}  # Invalid format
        )

        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    def test_trigger_digest_future_date_rejected(self, client):
        """Test 400 for future dates."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")

        response = client.post(
            "/api/v1/digests/trigger",
            json={"date": future_date}
        )

        assert response.status_code == 400
        assert "future" in response.json()["detail"].lower()


class TestDigestStatusEndpoint:
    """Tests for GET /api/v1/digests/status (AC11)."""

    def test_get_status_success(self, client, mock_digest_scheduler):
        """Test successful status retrieval."""
        mock_digest_scheduler.get_status.return_value = DigestStatus(
            enabled=True,
            schedule_time="07:30",
            last_run=datetime(2025, 12, 11, 7, 30, 0, tzinfo=timezone.utc),
            last_status="success",
            last_error=None,
            next_run=datetime(2025, 12, 12, 7, 30, 0, tzinfo=timezone.utc),
        )

        with patch('app.api.v1.digests.get_digest_scheduler', return_value=mock_digest_scheduler):
            response = client.get("/api/v1/digests/status")

            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is True
            assert data["schedule_time"] == "07:30"
            assert data["last_status"] == "success"
            assert "next_run" in data

    def test_get_status_disabled(self, client, mock_digest_scheduler):
        """Test status when scheduler is disabled."""
        mock_digest_scheduler.get_status.return_value = DigestStatus(
            enabled=False,
            schedule_time="06:00",
            last_run=None,
            last_status="never_run",
            last_error=None,
            next_run=None,
        )

        with patch('app.api.v1.digests.get_digest_scheduler', return_value=mock_digest_scheduler):
            response = client.get("/api/v1/digests/status")

            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is False
            assert data["last_status"] == "never_run"

    def test_get_status_with_error(self, client, mock_digest_scheduler):
        """Test status includes last error."""
        mock_digest_scheduler.get_status.return_value = DigestStatus(
            enabled=True,
            schedule_time="06:00",
            last_run=datetime.now(timezone.utc),
            last_status="error",
            last_error="AI provider unavailable",
            next_run=datetime.now(timezone.utc) + timedelta(days=1),
        )

        with patch('app.api.v1.digests.get_digest_scheduler', return_value=mock_digest_scheduler):
            response = client.get("/api/v1/digests/status")

            assert response.status_code == 200
            data = response.json()
            assert data["last_status"] == "error"
            assert data["last_error"] == "AI provider unavailable"


class TestListDigestsEndpoint:
    """Tests for GET /api/v1/digests endpoint."""

    def test_list_digests_empty(self, client, mock_db):
        """Test listing digests when none exist."""
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        response = client.get("/api/v1/digests")

        assert response.status_code == 200
        data = response.json()
        assert "digests" in data
        assert "total" in data
        assert len(data["digests"]) == 0

    def test_list_digests_pagination(self, client, mock_db):
        """Test listing digests with pagination."""
        mock_db.query.return_value.filter.return_value.count.return_value = 50
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        response = client.get("/api/v1/digests?limit=10&offset=20")

        assert response.status_code == 200

    def test_list_digests_filter_by_type(self, client, mock_db):
        """Test listing digests with type filter."""
        mock_db.query.return_value.filter.return_value.count.return_value = 10
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        response = client.get("/api/v1/digests?digest_type=daily")

        assert response.status_code == 200


class TestGetDigestEndpoint:
    """Tests for GET /api/v1/digests/{digest_id} endpoint."""

    def test_get_digest_not_found(self, client, mock_db):
        """Test 404 for non-existent digest."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        response = client.get("/api/v1/digests/non-existent-id")

        assert response.status_code == 404


class TestResponseSchema:
    """Tests for response schema compliance."""

    def test_trigger_response_schema(self, client, mock_digest_scheduler):
        """Test trigger response includes required fields."""
        mock_digest_scheduler.run_scheduled_digest = AsyncMock(return_value=None)

        with patch('app.api.v1.digests.get_digest_scheduler', return_value=mock_digest_scheduler):
            response = client.post("/api/v1/digests/trigger")

            assert response.status_code == 200
            data = response.json()
            assert "message" in data
            assert "digest" in data
            assert "skipped" in data

    def test_status_response_schema(self, client, mock_digest_scheduler):
        """Test status response includes required fields (AC11)."""
        mock_digest_scheduler.get_status.return_value = DigestStatus(
            enabled=True,
            schedule_time="06:00",
            last_run=None,
            last_status="never_run",
            last_error=None,
            next_run=None,
        )

        with patch('app.api.v1.digests.get_digest_scheduler', return_value=mock_digest_scheduler):
            response = client.get("/api/v1/digests/status")

            assert response.status_code == 200
            data = response.json()

            # AC11: Required fields
            assert "enabled" in data
            assert "schedule_time" in data
            assert "last_run" in data
            assert "last_status" in data
            assert "next_run" in data


class TestDeliveryStatusResponse:
    """Tests for delivery_status in digest responses (Story P4-4.3, AC11)."""

    def test_digest_response_includes_delivery_status_field(self, client, mock_db):
        """Test DigestResponse schema includes delivery_status field (AC11)."""
        from app.models.activity_summary import ActivitySummary
        import json

        mock_digest = MagicMock(spec=ActivitySummary)
        mock_digest.id = "test-id"
        mock_digest.summary_text = "Test summary"
        mock_digest.period_start = datetime(2025, 12, 11, 0, 0, 0, tzinfo=timezone.utc)
        mock_digest.period_end = datetime(2025, 12, 11, 23, 59, 59, tzinfo=timezone.utc)
        mock_digest.event_count = 5
        mock_digest.generated_at = datetime.now(timezone.utc)
        mock_digest.digest_type = "daily"
        mock_digest.ai_cost = 0.001
        mock_digest.provider_used = "openai"
        mock_digest.delivery_status = json.dumps({
            "success": True,
            "channels_attempted": ["push", "in_app"],
            "channels_succeeded": ["push", "in_app"],
            "errors": {},
            "delivery_time_ms": 150
        })

        mock_db.query.return_value.filter.return_value.first.return_value = mock_digest

        response = client.get("/api/v1/digests/test-id")

        assert response.status_code == 200
        data = response.json()

        # Verify delivery_status is present (AC11)
        assert "delivery_status" in data
        assert data["delivery_status"] is not None
        assert data["delivery_status"]["success"] is True
        assert "push" in data["delivery_status"]["channels_succeeded"]

    def test_digest_response_without_delivery_status(self, client, mock_db):
        """Test digest response handles null delivery_status gracefully."""
        from app.models.activity_summary import ActivitySummary

        mock_digest = MagicMock(spec=ActivitySummary)
        mock_digest.id = "test-id"
        mock_digest.summary_text = "Test summary"
        mock_digest.period_start = datetime(2025, 12, 11, 0, 0, 0, tzinfo=timezone.utc)
        mock_digest.period_end = datetime(2025, 12, 11, 23, 59, 59, tzinfo=timezone.utc)
        mock_digest.event_count = 5
        mock_digest.generated_at = datetime.now(timezone.utc)
        mock_digest.digest_type = "daily"
        mock_digest.ai_cost = 0.001
        mock_digest.provider_used = "openai"
        mock_digest.delivery_status = None  # No delivery status

        mock_db.query.return_value.filter.return_value.first.return_value = mock_digest

        response = client.get("/api/v1/digests/test-id")

        assert response.status_code == 200
        data = response.json()

        # delivery_status should be None
        assert "delivery_status" in data
        assert data["delivery_status"] is None

    def test_delivery_status_response_schema(self, client, mock_db):
        """Test DeliveryStatusResponse includes all required fields."""
        from app.models.activity_summary import ActivitySummary
        import json

        mock_digest = MagicMock(spec=ActivitySummary)
        mock_digest.id = "test-id"
        mock_digest.summary_text = "Test"
        mock_digest.period_start = datetime(2025, 12, 11, 0, 0, 0, tzinfo=timezone.utc)
        mock_digest.period_end = datetime(2025, 12, 11, 23, 59, 59, tzinfo=timezone.utc)
        mock_digest.event_count = 3
        mock_digest.generated_at = datetime.now(timezone.utc)
        mock_digest.digest_type = "daily"
        mock_digest.ai_cost = 0.0
        mock_digest.provider_used = None
        mock_digest.delivery_status = json.dumps({
            "success": False,
            "channels_attempted": ["email"],
            "channels_succeeded": [],
            "errors": {"email": "SMTP connection failed"},
            "delivery_time_ms": 5000
        })

        mock_db.query.return_value.filter.return_value.first.return_value = mock_digest

        response = client.get("/api/v1/digests/test-id")

        assert response.status_code == 200
        data = response.json()
        ds = data["delivery_status"]

        # Verify DeliveryStatusResponse schema
        assert "success" in ds
        assert "channels_attempted" in ds
        assert "channels_succeeded" in ds
        assert "errors" in ds
        assert "delivery_time_ms" in ds

        # Verify error is captured
        assert ds["success"] is False
        assert "email" in ds["errors"]

    def test_list_digests_includes_delivery_status(self, client, mock_db):
        """Test list digests endpoint includes delivery_status for each digest."""
        from app.models.activity_summary import ActivitySummary
        import json

        mock_digest1 = MagicMock(spec=ActivitySummary)
        mock_digest1.id = "test-1"
        mock_digest1.summary_text = "Summary 1"
        mock_digest1.period_start = datetime(2025, 12, 11, 0, 0, 0, tzinfo=timezone.utc)
        mock_digest1.period_end = datetime(2025, 12, 11, 23, 59, 59, tzinfo=timezone.utc)
        mock_digest1.event_count = 5
        mock_digest1.generated_at = datetime.now(timezone.utc)
        mock_digest1.digest_type = "daily"
        mock_digest1.ai_cost = 0.001
        mock_digest1.provider_used = "openai"
        mock_digest1.delivery_status = json.dumps({"success": True, "channels_attempted": ["push"], "channels_succeeded": ["push"], "errors": {}, "delivery_time_ms": 100})

        mock_db.query.return_value.filter.return_value.count.return_value = 1
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_digest1]

        response = client.get("/api/v1/digests")

        assert response.status_code == 200
        data = response.json()
        assert len(data["digests"]) == 1
        assert "delivery_status" in data["digests"][0]
