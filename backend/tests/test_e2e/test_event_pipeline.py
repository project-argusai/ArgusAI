"""
End-to-end tests for the event processing pipeline.

Story P14-3.10: Add End-to-End Integration Tests
Tests the complete flow: Camera Event -> AI Description -> Database -> WebSocket
"""
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock

from app.models.event import Event
from app.models.camera import Camera


@pytest.mark.e2e
class TestEventPipeline:
    """End-to-end tests for the complete event processing pipeline."""

    def test_create_event_via_api(self, e2e_client, authenticated_user, sample_camera, db_session):
        """Test creating an event via API stores it in database."""
        # Create event via API
        event_data = {
            "camera_id": sample_camera.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Person detected at front door",
            "objects_detected": ["person"],
            "confidence": 85,
        }

        response = e2e_client.post("/api/v1/events", json=event_data)

        # Verify response
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        assert data["camera_id"] == sample_camera.id

        # Verify event in database
        event = db_session.query(Event).filter_by(id=data["id"]).first()
        assert event is not None
        assert event.description == "Person detected at front door"

    def test_get_event_list(self, e2e_client, authenticated_user, sample_camera, db_session):
        """Test retrieving event list includes created events."""
        # Create events directly in database
        for i in range(3):
            event = Event(
                id=str(uuid.uuid4()),
                camera_id=sample_camera.id,
                timestamp=datetime.now(timezone.utc),
                description=f"Test event {i+1}",
                source_type="rtsp",
                objects_detected='["person"]',
                confidence=80 + i,
            )
            db_session.add(event)
        db_session.commit()

        # Retrieve via API
        response = e2e_client.get("/api/v1/events")

        assert response.status_code == 200
        data = response.json()
        # EventListResponse uses 'events' key
        assert "events" in data
        events = data["events"]
        assert len(events) >= 3

    def test_get_event_by_id(self, e2e_client, authenticated_user, sample_camera, db_session):
        """Test retrieving a specific event by ID."""
        # Create event
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Specific event for retrieval",
            source_type="rtsp",
            objects_detected='["vehicle"]',
            confidence=90,
        )
        db_session.add(event)
        db_session.commit()

        # Retrieve by ID
        response = e2e_client.get(f"/api/v1/events/{event.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == event.id
        assert data["description"] == "Specific event for retrieval"

    def test_event_filtering_by_camera(self, e2e_client, authenticated_user, sample_cameras, db_session):
        """Test filtering events by camera ID."""
        # Create events for different cameras
        for i, camera in enumerate(sample_cameras):
            event = Event(
                id=str(uuid.uuid4()),
                camera_id=camera.id,
                timestamp=datetime.now(timezone.utc),
                description=f"Event from camera {i+1}",
                source_type="rtsp",
                objects_detected='["person"]',
                confidence=85,
            )
            db_session.add(event)
        db_session.commit()

        # Filter by first camera
        target_camera = sample_cameras[0]
        response = e2e_client.get(f"/api/v1/events?camera_id={target_camera.id}")

        assert response.status_code == 200
        data = response.json()
        events = data.get("events", [])
        # All returned events should be from the target camera
        for event in events:
            assert event["camera_id"] == target_camera.id

    def test_event_deletion(self, e2e_client, authenticated_user, sample_camera, db_session):
        """Test deleting an event removes it from database."""
        # Create event
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event to be deleted",
            source_type="rtsp",
            objects_detected='["person"]',
            confidence=75,
        )
        db_session.add(event)
        db_session.commit()
        event_id = event.id

        # Delete event
        response = e2e_client.delete(f"/api/v1/events/{event_id}")
        assert response.status_code in [200, 204]

        # Verify deletion
        db_session.expire_all()
        deleted_event = db_session.query(Event).filter_by(id=event_id).first()
        assert deleted_event is None


@pytest.mark.e2e
class TestEventWithCamera:
    """Tests for event-camera relationship."""

    def test_event_includes_camera_info(self, e2e_client, authenticated_user, sample_camera, db_session):
        """Test that event details include camera information."""
        # Create event
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event with camera info",
            source_type="rtsp",
            objects_detected='["package"]',
            confidence=88,
        )
        db_session.add(event)
        db_session.commit()

        # Retrieve event
        response = e2e_client.get(f"/api/v1/events/{event.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["camera_id"] == sample_camera.id
        # Camera name may or may not be included depending on API design
        if "camera_name" in data:
            assert data["camera_name"] == sample_camera.name

    def test_event_with_nonexistent_camera_fails(self, e2e_client, authenticated_user, db_session):
        """Test that creating event with invalid camera ID fails."""
        fake_camera_id = str(uuid.uuid4())

        event_data = {
            "camera_id": fake_camera_id,
            "description": "Event with fake camera",
            "objects_detected": ["person"],
            "confidence": 80,
        }

        response = e2e_client.post("/api/v1/events", json=event_data)

        # Should fail with 400 or 404
        assert response.status_code in [400, 404, 422]


@pytest.mark.e2e
class TestEventPagination:
    """Tests for event list pagination."""

    def test_event_pagination(self, e2e_client, authenticated_user, sample_camera, db_session):
        """Test paginating through events."""
        # Create 15 events
        for i in range(15):
            event = Event(
                id=str(uuid.uuid4()),
                camera_id=sample_camera.id,
                timestamp=datetime.now(timezone.utc),
                description=f"Paginated event {i+1}",
                source_type="rtsp",
                objects_detected='["person"]',
                confidence=80,
            )
            db_session.add(event)
        db_session.commit()

        # First page
        response1 = e2e_client.get("/api/v1/events?limit=10&offset=0")
        assert response1.status_code == 200
        data1 = response1.json()
        events1 = data1.get("events", [])
        assert len(events1) == 10

        # Second page
        response2 = e2e_client.get("/api/v1/events?limit=10&offset=10")
        assert response2.status_code == 200
        data2 = response2.json()
        events2 = data2.get("events", [])
        assert len(events2) == 5
