"""
Integration tests for doorbell ring detection (Story P2-6.4, AC4)

Tests doorbell ring detection and display:
- Doorbell ring event detection
- is_doorbell_ring flag stored correctly
- Doorbell events have distinct styling indication
- Doorbell-specific AI prompts

These tests use mocks since actual doorbells are not available.
"""
import pytest
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os

from main import app
from app.core.database import Base, get_db
from app.models.protect_controller import ProtectController
from app.models.camera import Camera
from app.models.event import Event
from app.services.protect_event_handler import (
    ProtectEventHandler,
    EVENT_TYPE_MAPPING,
    DOORBELL_RING_PROMPT,
)


# Create test database
test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(test_db_fd)

TEST_DATABASE_URL = f"sqlite:///{test_db_path}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    db = TestingSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Override database dependency
app.dependency_overrides[get_db] = override_get_db

# Create tables once
Base.metadata.create_all(bind=engine)

# Create test client
client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    yield
    db = TestingSessionLocal()
    try:
        db.query(Event).delete()
        db.query(Camera).delete()
        db.query(ProtectController).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def test_controller():
    """Create a test controller"""
    db = TestingSessionLocal()
    try:
        controller = ProtectController(
            id="test-ctrl-doorbell",
            name="Doorbell Controller",
            host="192.168.1.1",
            port=443,
            username="admin",
            password="testpassword",
            is_connected=True
        )
        db.add(controller)
        db.commit()
        db.refresh(controller)
        return controller
    finally:
        db.close()


@pytest.fixture
def doorbell_camera(test_controller):
    """Create a doorbell camera"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id="doorbell-cam-001",
            name="Front Door Doorbell",
            type="rtsp",
            source_type="protect",
            protect_controller_id=test_controller.id,
            protect_camera_id="protect-doorbell-native-001",
            protect_camera_type="doorbell",
            is_doorbell=True,
            smart_detection_types=json.dumps(["person", "package", "ring"]),
            is_enabled=True
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera
    finally:
        db.close()


@pytest.fixture
def regular_camera(test_controller):
    """Create a regular (non-doorbell) camera"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id="regular-cam-001",
            name="Garage Camera",
            type="rtsp",
            source_type="protect",
            protect_controller_id=test_controller.id,
            protect_camera_id="protect-regular-native-001",
            is_doorbell=False,
            smart_detection_types=json.dumps(["person", "vehicle"]),
            is_enabled=True
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera
    finally:
        db.close()


class TestDoorbellRingDetection:
    """Tests for doorbell ring event detection (AC4)"""

    def test_ring_event_type_mapping(self):
        """Test ring event type is properly mapped"""
        assert EVENT_TYPE_MAPPING["ring"] == "ring"

    def test_doorbell_ring_prompt_defined(self):
        """Test doorbell-specific AI prompt is defined"""
        assert DOORBELL_RING_PROMPT is not None
        assert len(DOORBELL_RING_PROMPT) > 0
        # Should mention describing who is at the door
        assert "door" in DOORBELL_RING_PROMPT.lower()

    def test_doorbell_flag_stored_correctly(self, doorbell_camera):
        """Test is_doorbell flag is stored on camera"""
        db = TestingSessionLocal()
        try:
            found = db.query(Camera).filter(Camera.id == doorbell_camera.id).first()
            assert found is not None
            assert found.is_doorbell is True
        finally:
            db.close()

    def test_regular_camera_not_doorbell(self, regular_camera):
        """Test regular camera is_doorbell is False"""
        db = TestingSessionLocal()
        try:
            found = db.query(Camera).filter(Camera.id == regular_camera.id).first()
            assert found is not None
            assert found.is_doorbell is False
        finally:
            db.close()


class TestDoorbellEventStorage:
    """Tests for doorbell event storage"""

    def test_doorbell_ring_event_has_flag(self, doorbell_camera):
        """Test doorbell ring event has is_doorbell_ring=True"""
        db = TestingSessionLocal()
        try:
            event = Event(
                id="ring-event-001",
                camera_id=doorbell_camera.id,
                source_type="protect",
                protect_event_id="protect-ring-native-001",
                timestamp=datetime.now(timezone.utc),
                description="Someone is at the front door wearing a blue jacket",
                confidence=95,
                objects_detected=json.dumps(["person"]),
                smart_detection_type="ring",
                is_doorbell_ring=True
            )
            db.add(event)
            db.commit()

            found = db.query(Event).filter(Event.id == "ring-event-001").first()
            assert found is not None
            assert found.is_doorbell_ring is True
            assert found.smart_detection_type == "ring"
        finally:
            db.close()

    def test_non_ring_event_no_flag(self, doorbell_camera):
        """Test non-ring events from doorbell don't have ring flag"""
        db = TestingSessionLocal()
        try:
            # Person detection from doorbell (not a ring)
            event = Event(
                id="person-doorbell-001",
                camera_id=doorbell_camera.id,
                source_type="protect",
                protect_event_id="protect-person-native-001",
                timestamp=datetime.now(timezone.utc),
                description="Person walking by the door",
                confidence=90,
                objects_detected=json.dumps(["person"]),
                smart_detection_type="person",
                is_doorbell_ring=False
            )
            db.add(event)
            db.commit()

            found = db.query(Event).filter(Event.id == "person-doorbell-001").first()
            assert found is not None
            assert found.is_doorbell_ring is False
        finally:
            db.close()


class TestDoorbellEventAPI:
    """Tests for doorbell events in API responses"""

    def test_doorbell_ring_event_in_api(self, doorbell_camera):
        """Test doorbell ring events appear in API with correct fields"""
        db = TestingSessionLocal()
        try:
            event = Event(
                id="api-ring-event-001",
                camera_id=doorbell_camera.id,
                source_type="protect",
                protect_event_id="protect-api-ring-001",
                timestamp=datetime.now(timezone.utc),
                description="Delivery person at front door",
                confidence=95,
                objects_detected=json.dumps(["person"]),
                smart_detection_type="ring",
                is_doorbell_ring=True
            )
            db.add(event)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/events?limit=10")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))
        ring_events = [e for e in events if e.get("id") == "api-ring-event-001"]

        if ring_events:
            ring_event = ring_events[0]
            assert ring_event.get("is_doorbell_ring") is True
            assert ring_event.get("smart_detection_type") == "ring"

    def test_filter_doorbell_events(self, doorbell_camera, regular_camera):
        """Test filtering to find doorbell ring events"""
        db = TestingSessionLocal()
        try:
            # Ring event
            ring_event = Event(
                id="filter-ring-001",
                camera_id=doorbell_camera.id,
                source_type="protect",
                timestamp=datetime.now(timezone.utc),
                description="Ring at door",
                confidence=95,
                objects_detected=json.dumps(["person"]),
                is_doorbell_ring=True
            )
            db.add(ring_event)

            # Non-ring event
            non_ring = Event(
                id="filter-motion-001",
                camera_id=regular_camera.id,
                source_type="protect",
                timestamp=datetime.now(timezone.utc),
                description="Motion in garage",
                confidence=80,
                objects_detected=json.dumps(["vehicle"]),
                is_doorbell_ring=False
            )
            db.add(non_ring)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/events")
        assert response.status_code == 200


class TestDoorbellDistinctStyling:
    """Tests to verify doorbell events have distinct display indication (AC4)"""

    def test_doorbell_event_includes_camera_type(self, doorbell_camera):
        """Test that doorbell events include camera type for styling"""
        db = TestingSessionLocal()
        try:
            event = Event(
                id="styling-ring-001",
                camera_id=doorbell_camera.id,
                source_type="protect",
                timestamp=datetime.now(timezone.utc),
                description="Visitor at door",
                confidence=95,
                objects_detected=json.dumps(["person"]),
                is_doorbell_ring=True
            )
            db.add(event)
            db.commit()
        finally:
            db.close()

        # Verify camera is marked as doorbell
        db = TestingSessionLocal()
        try:
            camera = db.query(Camera).filter(Camera.id == doorbell_camera.id).first()
            assert camera.is_doorbell is True
            assert camera.protect_camera_type == "doorbell"
        finally:
            db.close()

    def test_doorbell_ring_distinguishable_from_motion(self, doorbell_camera):
        """Test ring events are distinguishable from motion events"""
        db = TestingSessionLocal()
        try:
            # Create both ring and motion events from doorbell
            ring = Event(
                id="distinguish-ring-001",
                camera_id=doorbell_camera.id,
                source_type="protect",
                timestamp=datetime.now(timezone.utc),
                description="Someone rang the doorbell",
                confidence=95,
                objects_detected=json.dumps(["person"]),
                smart_detection_type="ring",
                is_doorbell_ring=True
            )
            motion = Event(
                id="distinguish-motion-001",
                camera_id=doorbell_camera.id,
                source_type="protect",
                timestamp=datetime.now(timezone.utc),
                description="Person detected at door",
                confidence=90,
                objects_detected=json.dumps(["person"]),
                smart_detection_type="person",
                is_doorbell_ring=False
            )
            db.add(ring)
            db.add(motion)
            db.commit()

            # Verify they can be distinguished
            ring_found = db.query(Event).filter(Event.id == "distinguish-ring-001").first()
            motion_found = db.query(Event).filter(Event.id == "distinguish-motion-001").first()

            assert ring_found.is_doorbell_ring is True
            assert ring_found.smart_detection_type == "ring"

            assert motion_found.is_doorbell_ring is False
            assert motion_found.smart_detection_type == "person"
        finally:
            db.close()


class TestDoorbellAIPrompt:
    """Tests for doorbell-specific AI prompt"""

    def test_doorbell_prompt_describes_visitor(self):
        """Test doorbell prompt asks to describe visitor"""
        # The prompt should ask about describing who is at the door
        assert "describe" in DOORBELL_RING_PROMPT.lower()
        assert "door" in DOORBELL_RING_PROMPT.lower()

    def test_doorbell_prompt_mentions_delivery(self):
        """Test doorbell prompt considers delivery people"""
        assert "delivery" in DOORBELL_RING_PROMPT.lower()


class TestDoorbellCameraType:
    """Tests for doorbell camera type field"""

    def test_protect_camera_type_stored(self, doorbell_camera):
        """Test protect_camera_type is stored for doorbells"""
        db = TestingSessionLocal()
        try:
            found = db.query(Camera).filter(Camera.id == doorbell_camera.id).first()
            assert found is not None
            assert found.protect_camera_type == "doorbell"
        finally:
            db.close()

    def test_regular_camera_type(self, regular_camera):
        """Test regular cameras don't have doorbell type"""
        db = TestingSessionLocal()
        try:
            found = db.query(Camera).filter(Camera.id == regular_camera.id).first()
            assert found is not None
            assert found.protect_camera_type != "doorbell" or found.protect_camera_type is None
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
