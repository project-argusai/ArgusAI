"""
Tests for Story P4-7.3: Anomaly severity filtering in events API

Tests the anomaly_severity query parameter in GET /api/v1/events endpoint:
- Filter by low anomaly (< 0.3)
- Filter by medium anomaly (0.3 - 0.6)
- Filter by high anomaly (> 0.6)
- Combined severity filtering
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.camera import Camera
from app.services.anomaly_scoring_service import AnomalyScoringService


@pytest.fixture
def camera(db: Session) -> Camera:
    """Create a test camera."""
    camera = Camera(
        id="cam-001",
        name="Test Camera",
        rtsp_url="rtsp://test:test@localhost:554/stream",
        is_enabled=True
    )
    db.add(camera)
    db.commit()
    return camera


@pytest.fixture
def events_with_anomaly_scores(db: Session, camera: Camera) -> list[Event]:
    """Create events with various anomaly scores."""
    now = datetime.now(timezone.utc)

    events = [
        # Low anomaly events (< 0.3)
        Event(
            id="evt-low-1",
            camera_id=camera.id,
            timestamp=now,
            description="Normal activity - person walking",
            confidence=80,
            objects_detected='["person"]',
            anomaly_score=0.1,
            source_type="protect"
        ),
        Event(
            id="evt-low-2",
            camera_id=camera.id,
            timestamp=now,
            description="Normal activity - car passing",
            confidence=85,
            objects_detected='["vehicle"]',
            anomaly_score=0.25,
            source_type="protect"
        ),
        # Medium anomaly events (0.3 - 0.6)
        Event(
            id="evt-med-1",
            camera_id=camera.id,
            timestamp=now,
            description="Unusual activity - late night person",
            confidence=75,
            objects_detected='["person"]',
            anomaly_score=0.35,
            source_type="protect"
        ),
        Event(
            id="evt-med-2",
            camera_id=camera.id,
            timestamp=now,
            description="Unusual activity - unknown vehicle",
            confidence=70,
            objects_detected='["vehicle"]',
            anomaly_score=0.55,
            source_type="protect"
        ),
        # High anomaly events (> 0.6)
        Event(
            id="evt-high-1",
            camera_id=camera.id,
            timestamp=now,
            description="Anomaly - person at unusual time",
            confidence=90,
            objects_detected='["person"]',
            anomaly_score=0.75,
            source_type="protect"
        ),
        Event(
            id="evt-high-2",
            camera_id=camera.id,
            timestamp=now,
            description="Anomaly - rare activity pattern",
            confidence=88,
            objects_detected='["animal"]',
            anomaly_score=0.9,
            source_type="protect"
        ),
        # Event without anomaly score
        Event(
            id="evt-no-score",
            camera_id=camera.id,
            timestamp=now,
            description="Event without anomaly score",
            confidence=70,
            objects_detected='["unknown"]',
            anomaly_score=None,
            source_type="protect"
        ),
    ]

    for event in events:
        db.add(event)
    db.commit()

    return events


class TestAnomalySeverityFilter:
    """Tests for anomaly_severity filter parameter."""

    def test_filter_low_anomaly(
        self,
        client: TestClient,
        events_with_anomaly_scores: list[Event]
    ):
        """Test filtering events with low anomaly scores (< 0.3)."""
        response = client.get("/api/v1/events?anomaly_severity=low")

        assert response.status_code == 200
        data = response.json()

        # Should include events with score < 0.3 (0.1 and 0.25)
        event_ids = [e["id"] for e in data["events"]]
        assert "evt-low-1" in event_ids
        assert "evt-low-2" in event_ids
        # Should NOT include medium, high, or null score events
        assert "evt-med-1" not in event_ids
        assert "evt-high-1" not in event_ids
        assert "evt-no-score" not in event_ids

    def test_filter_medium_anomaly(
        self,
        client: TestClient,
        events_with_anomaly_scores: list[Event]
    ):
        """Test filtering events with medium anomaly scores (0.3 - 0.6)."""
        response = client.get("/api/v1/events?anomaly_severity=medium")

        assert response.status_code == 200
        data = response.json()

        event_ids = [e["id"] for e in data["events"]]
        assert "evt-med-1" in event_ids
        assert "evt-med-2" in event_ids
        # Should NOT include low or high scores
        assert "evt-low-1" not in event_ids
        assert "evt-high-1" not in event_ids

    def test_filter_high_anomaly(
        self,
        client: TestClient,
        events_with_anomaly_scores: list[Event]
    ):
        """Test filtering events with high anomaly scores (> 0.6)."""
        response = client.get("/api/v1/events?anomaly_severity=high")

        assert response.status_code == 200
        data = response.json()

        event_ids = [e["id"] for e in data["events"]]
        assert "evt-high-1" in event_ids
        assert "evt-high-2" in event_ids
        # Should NOT include low or medium scores
        assert "evt-low-1" not in event_ids
        assert "evt-med-1" not in event_ids

    def test_filter_multiple_severities(
        self,
        client: TestClient,
        events_with_anomaly_scores: list[Event]
    ):
        """Test filtering by multiple severity levels (medium,high)."""
        response = client.get("/api/v1/events?anomaly_severity=medium,high")

        assert response.status_code == 200
        data = response.json()

        event_ids = [e["id"] for e in data["events"]]
        # Should include both medium and high
        assert "evt-med-1" in event_ids
        assert "evt-med-2" in event_ids
        assert "evt-high-1" in event_ids
        assert "evt-high-2" in event_ids
        # Should NOT include low
        assert "evt-low-1" not in event_ids

    def test_filter_with_invalid_severity_ignored(
        self,
        client: TestClient,
        events_with_anomaly_scores: list[Event]
    ):
        """Test that invalid severity values are ignored."""
        response = client.get("/api/v1/events?anomaly_severity=invalid,high")

        assert response.status_code == 200
        data = response.json()

        # Should only apply valid "high" filter
        event_ids = [e["id"] for e in data["events"]]
        assert "evt-high-1" in event_ids
        assert "evt-high-2" in event_ids

    def test_filter_combined_with_camera(
        self,
        client: TestClient,
        events_with_anomaly_scores: list[Event],
        camera: Camera
    ):
        """Test combining anomaly filter with camera filter."""
        response = client.get(
            f"/api/v1/events?anomaly_severity=high&camera_id={camera.id}"
        )

        assert response.status_code == 200
        data = response.json()

        # Should return high anomaly events for this camera
        event_ids = [e["id"] for e in data["events"]]
        assert "evt-high-1" in event_ids
        assert "evt-high-2" in event_ids

    def test_severity_thresholds_match_service(self):
        """Verify filter thresholds match AnomalyScoringService constants."""
        # This test documents the expected threshold values
        assert AnomalyScoringService.LOW_THRESHOLD == 0.3
        assert AnomalyScoringService.HIGH_THRESHOLD == 0.6
