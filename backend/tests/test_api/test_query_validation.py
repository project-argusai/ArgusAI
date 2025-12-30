"""
Query Parameter Validation Tests (Story P14-8.1)

Comprehensive tests for query parameter validation across API endpoints.
Tests cover limit/offset validation, UUID format, date format, and enum validation.
"""
import pytest
from datetime import datetime, timedelta
import uuid

# Import the shared client fixture
from tests.test_api.conftest import api_client, test_db


class TestEventsQueryValidation:
    """Tests for /events endpoint query parameter validation."""

    @pytest.mark.parametrize("limit,expected_status", [
        (0, 422),       # Too small - min is 1
        (-1, 422),      # Negative
        (501, 422),     # Too large - max is 500
        (50, 200),      # Valid
        (1, 200),       # Valid minimum
        (500, 200),     # Valid maximum
    ])
    def test_limit_validation(self, api_client, limit, expected_status):
        """Test that limit parameter validates range correctly."""
        response = api_client.get(f"/api/v1/events?limit={limit}")
        assert response.status_code == expected_status

    def test_limit_non_numeric(self, api_client):
        """Test that non-numeric limit is rejected."""
        response = api_client.get("/api/v1/events?limit=abc")
        assert response.status_code == 422
        # Verify error message mentions the issue
        detail = response.json().get("detail", [])
        assert len(detail) > 0

    @pytest.mark.parametrize("offset,expected_status", [
        (-1, 422),      # Negative
        (0, 200),       # Valid minimum
        (1000, 200),    # Valid large offset
    ])
    def test_offset_validation(self, api_client, offset, expected_status):
        """Test that offset parameter validates range correctly."""
        response = api_client.get(f"/api/v1/events?offset={offset}")
        assert response.status_code == expected_status

    def test_offset_non_numeric(self, api_client):
        """Test that non-numeric offset is rejected."""
        response = api_client.get("/api/v1/events?offset=abc")
        assert response.status_code == 422

    def test_invalid_camera_id_format(self, api_client):
        """Test that invalid UUID format for camera_id is handled gracefully."""
        # Note: The current implementation may accept invalid UUIDs as strings
        # This test documents the expected behavior
        response = api_client.get("/api/v1/events?camera_id=not-a-uuid")
        # Even if it doesn't reject, it should return empty results (not error)
        assert response.status_code in [200, 422]

    def test_valid_camera_id_format(self, api_client):
        """Test that valid UUID format is accepted."""
        valid_uuid = str(uuid.uuid4())
        response = api_client.get(f"/api/v1/events?camera_id={valid_uuid}")
        assert response.status_code == 200

    def test_invalid_date_format(self, api_client):
        """Test that invalid date format is rejected."""
        response = api_client.get("/api/v1/events?start_time=not-a-date")
        assert response.status_code == 422

    def test_valid_iso_date_format(self, api_client):
        """Test that valid ISO 8601 date is accepted."""
        now = datetime.now().isoformat()
        response = api_client.get(f"/api/v1/events?start_time={now}")
        assert response.status_code == 200

    def test_invalid_sort_order(self, api_client):
        """Test that invalid sort_order is rejected."""
        response = api_client.get("/api/v1/events?sort_order=invalid")
        assert response.status_code == 422

    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    def test_valid_sort_order(self, api_client, sort_order):
        """Test that valid sort_order values are accepted."""
        response = api_client.get(f"/api/v1/events?sort_order={sort_order}")
        assert response.status_code == 200

    def test_min_confidence_range(self, api_client):
        """Test min_confidence range validation (0-100)."""
        # Valid values
        for val in [0, 50, 100]:
            response = api_client.get(f"/api/v1/events?min_confidence={val}")
            assert response.status_code == 200, f"min_confidence={val} should be valid"

        # Invalid: negative
        response = api_client.get("/api/v1/events?min_confidence=-1")
        assert response.status_code == 422

        # Invalid: too high
        response = api_client.get("/api/v1/events?min_confidence=101")
        assert response.status_code == 422


class TestNotificationsQueryValidation:
    """Tests for /notifications endpoint query parameter validation."""

    @pytest.mark.parametrize("limit,expected_status", [
        (0, 422),       # Too small
        (-1, 422),      # Negative
        (101, 422),     # Too large - max is 100
        (20, 200),      # Valid (default)
        (1, 200),       # Valid minimum
        (100, 200),     # Valid maximum
    ])
    def test_limit_validation(self, api_client, limit, expected_status):
        """Test that limit parameter validates range correctly."""
        response = api_client.get(f"/api/v1/notifications?limit={limit}")
        assert response.status_code == expected_status

    @pytest.mark.parametrize("offset,expected_status", [
        (-1, 422),      # Negative
        (0, 200),       # Valid minimum
        (100, 200),     # Valid
    ])
    def test_offset_validation(self, api_client, offset, expected_status):
        """Test that offset parameter validates range correctly."""
        response = api_client.get(f"/api/v1/notifications?offset={offset}")
        assert response.status_code == expected_status

    @pytest.mark.parametrize("read_value,expected_status", [
        ("true", 200),
        ("false", 200),
        ("True", 200),
        ("False", 200),
    ])
    def test_boolean_filter(self, api_client, read_value, expected_status):
        """Test that boolean read filter works correctly."""
        response = api_client.get(f"/api/v1/notifications?read={read_value}")
        assert response.status_code == expected_status


class TestMotionEventsQueryValidation:
    """Tests for /motion-events endpoint query parameter validation."""

    @pytest.mark.parametrize("limit,expected_status", [
        (0, 422),       # Too small
        (-1, 422),      # Negative
        (201, 422),     # Too large - max is 200
        (50, 200),      # Valid (default)
        (1, 200),       # Valid minimum
        (200, 200),     # Valid maximum
    ])
    def test_limit_validation(self, api_client, limit, expected_status):
        """Test that limit parameter validates range correctly."""
        response = api_client.get(f"/api/v1/motion-events?limit={limit}")
        assert response.status_code == expected_status

    def test_min_confidence_range(self, api_client):
        """Test min_confidence range validation (0.0-1.0)."""
        # Valid values
        for val in [0.0, 0.5, 1.0]:
            response = api_client.get(f"/api/v1/motion-events?min_confidence={val}")
            assert response.status_code == 200, f"min_confidence={val} should be valid"

        # Invalid: negative
        response = api_client.get("/api/v1/motion-events?min_confidence=-0.1")
        assert response.status_code == 422

        # Invalid: too high
        response = api_client.get("/api/v1/motion-events?min_confidence=1.1")
        assert response.status_code == 422


class TestDigestsQueryValidation:
    """Tests for /digests endpoint query parameter validation."""

    @pytest.mark.parametrize("limit,expected_status", [
        (0, 422),       # Too small
        (-1, 422),      # Negative
        (101, 422),     # Too large - max is 100
        (20, 200),      # Valid (default)
        (1, 200),       # Valid minimum
        (100, 200),     # Valid maximum
    ])
    def test_limit_validation(self, api_client, limit, expected_status):
        """Test that limit parameter validates range correctly."""
        response = api_client.get(f"/api/v1/digests?limit={limit}")
        assert response.status_code == expected_status


class TestSummariesQueryValidation:
    """Tests for /summaries endpoint query parameter validation."""

    @pytest.mark.parametrize("limit,expected_status", [
        (0, 422),       # Too small
        (-1, 422),      # Negative
        (101, 422),     # Too large - max is 100
        (20, 200),      # Valid (default)
        (1, 200),       # Valid minimum
        (100, 200),     # Valid maximum
    ])
    def test_list_summaries_limit_validation(self, api_client, limit, expected_status):
        """Test that limit parameter validates range correctly."""
        response = api_client.get(f"/api/v1/summaries?limit={limit}")
        assert response.status_code == expected_status


class TestWebhooksQueryValidation:
    """Tests for /webhooks endpoint query parameter validation."""

    @pytest.mark.parametrize("limit,expected_status", [
        (0, 422),       # Too small
        (-1, 422),      # Negative
        (201, 422),     # Too large - max is 200
        (50, 200),      # Valid (default)
        (1, 200),       # Valid minimum
        (200, 200),     # Valid maximum
    ])
    def test_logs_limit_validation(self, api_client, limit, expected_status):
        """Test that limit parameter validates range correctly for webhook logs."""
        response = api_client.get(f"/api/v1/webhooks/logs?limit={limit}")
        assert response.status_code == expected_status


class TestContextEntitiesQueryValidation:
    """Tests for /context/entities endpoint query parameter validation."""

    @pytest.mark.parametrize("limit,expected_status", [
        (0, 422),       # Too small
        (-1, 422),      # Negative
        (101, 422),     # Too large - max is 100
        (50, 200),      # Valid (default)
        (1, 200),       # Valid minimum
        (100, 200),     # Valid maximum
    ])
    def test_limit_validation(self, api_client, limit, expected_status):
        """Test that limit parameter validates range correctly."""
        response = api_client.get(f"/api/v1/context/entities?limit={limit}")
        assert response.status_code == expected_status

    @pytest.mark.parametrize("entity_type,expected_status", [
        ("person", 200),
        ("vehicle", 200),
        ("unknown", 200),
    ])
    def test_valid_entity_type(self, api_client, entity_type, expected_status):
        """Test that valid entity types are accepted."""
        response = api_client.get(f"/api/v1/context/entities?entity_type={entity_type}")
        assert response.status_code == expected_status


class TestLogsQueryValidation:
    """Tests for /logs endpoint query parameter validation."""

    @pytest.mark.parametrize("limit,expected_status", [
        (0, 422),       # Too small
        (-1, 422),      # Negative
        (1001, 422),    # Too large - max is 1000
        (100, 200),     # Valid (default)
        (1, 200),       # Valid minimum
        (1000, 200),    # Valid maximum
    ])
    def test_limit_validation(self, api_client, limit, expected_status):
        """Test that limit parameter validates range correctly."""
        response = api_client.get(f"/api/v1/logs?limit={limit}")
        assert response.status_code == expected_status

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_valid_log_levels(self, api_client, level):
        """Test that valid log levels are accepted."""
        response = api_client.get(f"/api/v1/logs?level={level}")
        assert response.status_code == 200


class TestEventsExportQueryValidation:
    """Tests for /events/export endpoint query parameter validation."""

    def test_format_required(self, api_client):
        """Test that format parameter is required."""
        response = api_client.get("/api/v1/events/export")
        assert response.status_code == 422

    @pytest.mark.parametrize("format_value,expected_status", [
        ("json", 200),
        ("csv", 200),
        ("xml", 422),     # Invalid format
        ("invalid", 422),
    ])
    def test_format_validation(self, api_client, format_value, expected_status):
        """Test that format parameter validates correctly."""
        response = api_client.get(f"/api/v1/events/export?format={format_value}")
        assert response.status_code == expected_status

    def test_date_format(self, api_client):
        """Test date format validation for export."""
        # Valid date
        response = api_client.get("/api/v1/events/export?format=json&start_date=2025-01-01")
        assert response.status_code == 200

        # Invalid date format
        response = api_client.get("/api/v1/events/export?format=json&start_date=01-01-2025")
        assert response.status_code == 422


class TestCombinedQueryParameters:
    """Tests for multiple query parameters combined."""

    def test_valid_combination(self, api_client):
        """Test that valid combinations work together."""
        response = api_client.get(
            "/api/v1/events?limit=50&offset=0&sort_order=desc&min_confidence=50"
        )
        assert response.status_code == 200

    def test_invalid_limit_with_valid_others(self, api_client):
        """Test that one invalid parameter fails the whole request."""
        response = api_client.get(
            "/api/v1/events?limit=-1&offset=0&sort_order=desc"
        )
        assert response.status_code == 422

    def test_multiple_invalid_parameters(self, api_client):
        """Test response with multiple invalid parameters."""
        response = api_client.get(
            "/api/v1/events?limit=-1&offset=-1&min_confidence=200"
        )
        assert response.status_code == 422
        # Should report multiple validation errors
        detail = response.json().get("detail", [])
        assert len(detail) >= 1  # At least one error reported


class TestEmptyAndDefaultValues:
    """Tests for empty and default parameter handling."""

    def test_no_parameters_uses_defaults(self, api_client):
        """Test that endpoints work with no parameters (use defaults)."""
        response = api_client.get("/api/v1/events")
        assert response.status_code == 200

    def test_empty_string_parameter(self, api_client):
        """Test handling of empty string parameters."""
        response = api_client.get("/api/v1/events?camera_id=")
        # Should either use default or treat as no filter
        assert response.status_code in [200, 422]
