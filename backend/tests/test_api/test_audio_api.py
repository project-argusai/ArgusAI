"""Tests for Audio Event Configuration API (Story P6-3.2)

Tests the audio configuration API endpoints:
- GET /api/v1/audio/thresholds - Retrieve thresholds (AC#3)
- PATCH /api/v1/audio/thresholds - Update threshold per type (AC#3)
- GET /api/v1/audio/supported-types - List supported audio event types (AC#2)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.api.v1.audio import router
from app.core.database import get_db
from app.services.audio_classifiers import AudioEventType


# Create test app
test_app = FastAPI()
test_app.include_router(router, prefix="/api/v1")


@pytest.fixture
def mock_db():
    """Create mock database session"""
    db = MagicMock()
    # Mock no existing settings
    db.query.return_value.filter.return_value.first.return_value = None
    return db


@pytest.fixture
def client(mock_db):
    """Create test client with mocked database"""
    test_app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(test_app)


class TestGetAudioThresholds:
    """Tests for GET /api/v1/audio/thresholds"""

    def test_get_thresholds_success(self, client):
        """Test retrieving audio thresholds returns all event types"""
        response = client.get("/api/v1/audio/thresholds")

        assert response.status_code == 200
        data = response.json()

        # Verify all event types present
        assert "glass_break" in data
        assert "gunshot" in data
        assert "scream" in data
        assert "doorbell" in data
        assert "other" in data

    def test_get_thresholds_default_values(self, client):
        """AC#3: Test default thresholds are 70%"""
        response = client.get("/api/v1/audio/thresholds")

        assert response.status_code == 200
        data = response.json()

        # Default is 0.70 (70%) for all types
        assert data["glass_break"] == 0.70
        assert data["gunshot"] == 0.70
        assert data["scream"] == 0.70
        assert data["doorbell"] == 0.70
        assert data["other"] == 0.70


class TestUpdateAudioThreshold:
    """Tests for PATCH /api/v1/audio/thresholds"""

    def test_update_threshold_success(self, client):
        """AC#3: Test updating threshold for valid event type"""
        response = client.patch(
            "/api/v1/audio/thresholds",
            json={"event_type": "glass_break", "threshold": 0.85}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["event_type"] == "glass_break"
        assert data["old_threshold"] == 0.70  # Default
        assert data["new_threshold"] == 0.85
        assert "success" in data["message"].lower()

    def test_update_threshold_all_types(self, client):
        """Test updating threshold for all event types"""
        event_types = ["glass_break", "gunshot", "scream", "doorbell", "other"]

        for event_type in event_types:
            response = client.patch(
                "/api/v1/audio/thresholds",
                json={"event_type": event_type, "threshold": 0.80}
            )

            assert response.status_code == 200
            assert response.json()["event_type"] == event_type

    def test_update_threshold_invalid_event_type(self, client):
        """Test updating threshold for invalid event type returns 400"""
        response = client.patch(
            "/api/v1/audio/thresholds",
            json={"event_type": "invalid_type", "threshold": 0.80}
        )

        assert response.status_code == 400
        assert "Invalid event type" in response.json()["detail"]

    def test_update_threshold_too_high(self, client):
        """Test threshold above 1.0 returns 422"""
        response = client.patch(
            "/api/v1/audio/thresholds",
            json={"event_type": "glass_break", "threshold": 1.5}
        )

        assert response.status_code == 422

    def test_update_threshold_negative(self, client):
        """Test negative threshold returns 422"""
        response = client.patch(
            "/api/v1/audio/thresholds",
            json={"event_type": "glass_break", "threshold": -0.1}
        )

        assert response.status_code == 422

    def test_update_threshold_zero(self, client):
        """Test threshold of 0 is valid (disable detection)"""
        response = client.patch(
            "/api/v1/audio/thresholds",
            json={"event_type": "glass_break", "threshold": 0.0}
        )

        assert response.status_code == 200
        assert response.json()["new_threshold"] == 0.0

    def test_update_threshold_one(self, client):
        """Test threshold of 1.0 is valid (require perfect confidence)"""
        response = client.patch(
            "/api/v1/audio/thresholds",
            json={"event_type": "glass_break", "threshold": 1.0}
        )

        assert response.status_code == 200
        assert response.json()["new_threshold"] == 1.0

    def test_update_threshold_case_insensitive(self, client):
        """Test event type is case insensitive"""
        # Test uppercase
        response = client.patch(
            "/api/v1/audio/thresholds",
            json={"event_type": "GLASS_BREAK", "threshold": 0.80}
        )

        assert response.status_code == 200

        # Test mixed case
        response = client.patch(
            "/api/v1/audio/thresholds",
            json={"event_type": "Glass_Break", "threshold": 0.80}
        )

        assert response.status_code == 200


class TestGetSupportedTypes:
    """Tests for GET /api/v1/audio/supported-types"""

    def test_get_supported_types_success(self, client):
        """AC#2: Test retrieving supported audio event types"""
        response = client.get("/api/v1/audio/supported-types")

        assert response.status_code == 200
        data = response.json()

        # Verify all types present with descriptions
        assert "glass_break" in data
        assert "gunshot" in data
        assert "scream" in data
        assert "doorbell" in data
        assert "other" in data

        # Verify descriptions are strings
        for event_type, description in data.items():
            assert isinstance(description, str)
            assert len(description) > 0

    def test_supported_types_descriptions(self, client):
        """Test supported types have meaningful descriptions"""
        response = client.get("/api/v1/audio/supported-types")

        data = response.json()

        # Descriptions should mention relevant keywords
        assert "glass" in data["glass_break"].lower()
        assert "gun" in data["gunshot"].lower() or "fire" in data["gunshot"].lower()
        assert "scream" in data["scream"].lower()
        assert "doorbell" in data["doorbell"].lower()


class TestAudioAPIIntegration:
    """Integration tests for audio API"""

    def test_update_then_get_shows_new_value(self, client):
        """Test that update is reflected in subsequent get"""
        # Update threshold
        update_response = client.patch(
            "/api/v1/audio/thresholds",
            json={"event_type": "gunshot", "threshold": 0.95}
        )
        assert update_response.status_code == 200

        # Get thresholds - should show updated value
        # Note: Due to singleton, the updated value should persist
        get_response = client.get("/api/v1/audio/thresholds")
        assert get_response.status_code == 200

        # The gunshot threshold should be updated
        data = get_response.json()
        assert data["gunshot"] == 0.95
