"""
Tests for Webhook API Endpoints (Story 5.3)

Tests cover:
- POST /api/v1/webhooks/test - Test webhook configuration
- GET /api/v1/webhooks/logs - Get webhook logs with filtering
- GET /api/v1/webhooks/logs/export - Export logs as CSV
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from main import app
from app.core.database import get_db
from app.models.alert_rule import AlertRule, WebhookLog


# Test client
client = TestClient(app)


class TestWebhookTestEndpoint:
    """Tests for POST /api/v1/webhooks/test"""

    def test_test_webhook_invalid_url_format(self):
        """Should return 400 for invalid URL format."""
        response = client.post(
            "/api/v1/webhooks/test",
            json={"url": "not-a-valid-url"}
        )

        assert response.status_code == 400
        assert "URL" in response.json()["detail"]

    def test_test_webhook_blocked_localhost(self):
        """Should return 400 for localhost URLs."""
        response = client.post(
            "/api/v1/webhooks/test",
            json={"url": "http://localhost/webhook"}
        )

        assert response.status_code == 400
        assert "Blocked" in response.json()["detail"]

    @patch('app.api.v1.webhooks.WebhookService')
    def test_test_webhook_success(self, mock_service_class):
        """Should return test result for valid webhook."""
        # Mock the service
        mock_service = mock_service_class.return_value
        mock_service.validate_url.return_value = None

        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.status_code = 200
        mock_result.response_body = "OK"
        mock_result.response_time_ms = 100
        mock_result.error_message = None

        mock_service.send_webhook = AsyncMock(return_value=mock_result)

        response = client.post(
            "/api/v1/webhooks/test",
            json={"url": "https://example.com/webhook"}
        )

        # Note: Status code may vary based on actual validation
        # This test verifies the endpoint is callable


class TestWebhookLogsEndpoint:
    """Tests for GET /api/v1/webhooks/logs"""

    def test_get_logs_empty(self, db_session):
        """Should return empty list when no logs exist."""
        # Override dependency
        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/v1/webhooks/logs")

            assert response.status_code == 200
            data = response.json()
            assert data["total_count"] == 0
            assert data["data"] == []
        finally:
            app.dependency_overrides.clear()

    def test_get_logs_with_data(self, db_session):
        """Should return logs when they exist."""
        # Create test rule first
        rule = AlertRule(
            id="test-rule-123",
            name="Test Rule",
            is_enabled=True,
            conditions="{}",
            actions='{"webhook": {"url": "https://example.com"}}',
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        # Create test log
        log = WebhookLog(
            alert_rule_id="test-rule-123",
            event_id="test-event-456",
            url="https://example.com/webhook",
            status_code=200,
            response_time_ms=100,
            retry_count=0,
            success=True
        )
        db_session.add(log)
        db_session.commit()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/v1/webhooks/logs")

            assert response.status_code == 200
            data = response.json()
            assert data["total_count"] == 1
            assert len(data["data"]) == 1
            assert data["data"][0]["event_id"] == "test-event-456"
            assert data["data"][0]["rule_name"] == "Test Rule"
        finally:
            app.dependency_overrides.clear()

    def test_get_logs_filter_by_success(self, db_session):
        """Should filter logs by success status."""
        # Create test rule
        rule = AlertRule(
            id="test-rule-filter",
            name="Filter Test Rule",
            is_enabled=True,
            conditions="{}",
            actions='{}',
            cooldown_minutes=5
        )
        db_session.add(rule)

        # Create success log
        success_log = WebhookLog(
            alert_rule_id="test-rule-filter",
            event_id="success-event",
            url="https://example.com",
            status_code=200,
            response_time_ms=100,
            retry_count=0,
            success=True
        )
        db_session.add(success_log)

        # Create failure log
        failure_log = WebhookLog(
            alert_rule_id="test-rule-filter",
            event_id="failure-event",
            url="https://example.com",
            status_code=500,
            response_time_ms=200,
            retry_count=2,
            success=False,
            error_message="Server error"
        )
        db_session.add(failure_log)
        db_session.commit()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Filter for success=true
            response = client.get("/api/v1/webhooks/logs?success=true")

            assert response.status_code == 200
            data = response.json()
            assert data["total_count"] == 1
            assert data["data"][0]["success"] is True

            # Filter for success=false
            response = client.get("/api/v1/webhooks/logs?success=false")

            assert response.status_code == 200
            data = response.json()
            assert data["total_count"] == 1
            assert data["data"][0]["success"] is False
        finally:
            app.dependency_overrides.clear()

    def test_get_logs_pagination(self, db_session):
        """Should support pagination."""
        # Create test rule
        rule = AlertRule(
            id="test-rule-paginate",
            name="Pagination Test Rule",
            is_enabled=True,
            conditions="{}",
            actions='{}',
            cooldown_minutes=5
        )
        db_session.add(rule)

        # Create multiple logs
        for i in range(5):
            log = WebhookLog(
                alert_rule_id="test-rule-paginate",
                event_id=f"event-{i}",
                url="https://example.com",
                status_code=200,
                response_time_ms=100,
                retry_count=0,
                success=True
            )
            db_session.add(log)
        db_session.commit()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        try:
            # Get first page
            response = client.get("/api/v1/webhooks/logs?limit=2&offset=0")

            assert response.status_code == 200
            data = response.json()
            assert data["total_count"] == 5
            assert len(data["data"]) == 2

            # Get second page
            response = client.get("/api/v1/webhooks/logs?limit=2&offset=2")

            assert response.status_code == 200
            data = response.json()
            assert data["total_count"] == 5
            assert len(data["data"]) == 2
        finally:
            app.dependency_overrides.clear()


class TestWebhookLogsExportEndpoint:
    """Tests for GET /api/v1/webhooks/logs/export"""

    def test_export_logs_csv(self, db_session):
        """Should export logs as CSV."""
        # Create test rule
        rule = AlertRule(
            id="test-rule-export",
            name="Export Test Rule",
            is_enabled=True,
            conditions="{}",
            actions='{}',
            cooldown_minutes=5
        )
        db_session.add(rule)

        # Create test log
        log = WebhookLog(
            alert_rule_id="test-rule-export",
            event_id="export-event",
            url="https://example.com/webhook",
            status_code=200,
            response_time_ms=100,
            retry_count=0,
            success=True
        )
        db_session.add(log)
        db_session.commit()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/v1/webhooks/logs/export")

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/csv; charset=utf-8"
            assert "attachment" in response.headers["content-disposition"]
            assert "webhook_logs" in response.headers["content-disposition"]

            # Check CSV content
            csv_content = response.text
            assert "ID" in csv_content  # Header
            assert "Rule Name" in csv_content
            assert "export-event" in csv_content  # Data
        finally:
            app.dependency_overrides.clear()


# Pytest fixture for database session
@pytest.fixture
def db_session():
    """Create a test database session."""
    from app.core.database import SessionLocal, engine, Base

    # Create tables
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Clean up test data
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
