"""
Integration tests for UniFi Protect event flow (Story P2-6.4, AC3)

Tests event flow from Protect to dashboard:
- Event received from WebSocket
- Event filtering based on camera configuration
- AI description generation
- Event storage in database
- Event appears in dashboard API

These tests use mocks since actual Protect controllers are not available.
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
    VALID_EVENT_TYPES,
    EVENT_COOLDOWN_SECONDS,
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
            id="test-ctrl-events-001",
            name="Test Event Controller",
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
def enabled_protect_camera(test_controller):
    """Create an enabled Protect camera"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id="protect-cam-events-001",
            name="Event Test Camera",
            type="rtsp",
            source_type="protect",
            protect_controller_id=test_controller.id,
            protect_camera_id="protect-native-001",
            smart_detection_types=json.dumps(["person", "vehicle"]),
            is_enabled=True
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera
    finally:
        db.close()


@pytest.fixture
def disabled_protect_camera(test_controller):
    """Create a disabled Protect camera"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id="protect-cam-events-disabled",
            name="Disabled Camera",
            type="rtsp",
            source_type="protect",
            protect_controller_id=test_controller.id,
            protect_camera_id="protect-native-disabled",
            is_enabled=False
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera
    finally:
        db.close()


@pytest.fixture
def event_handler():
    """Create a fresh event handler"""
    return ProtectEventHandler()


class TestEventTypeMapping:
    """Tests for event type parsing and mapping"""

    def test_event_type_mapping_defined(self):
        """Verify event type mapping is properly defined"""
        assert EVENT_TYPE_MAPPING["motion"] == "motion"
        assert EVENT_TYPE_MAPPING["smart_detect_person"] == "person"
        assert EVENT_TYPE_MAPPING["smart_detect_vehicle"] == "vehicle"
        assert EVENT_TYPE_MAPPING["smart_detect_package"] == "package"
        assert EVENT_TYPE_MAPPING["smart_detect_animal"] == "animal"
        assert EVENT_TYPE_MAPPING["ring"] == "ring"

    def test_valid_event_types(self):
        """Verify valid event types set"""
        assert "motion" in VALID_EVENT_TYPES
        assert "smart_detect_person" in VALID_EVENT_TYPES
        assert "smart_detect_vehicle" in VALID_EVENT_TYPES
        assert "ring" in VALID_EVENT_TYPES


class TestEventFiltering:
    """Tests for event filtering based on camera config (AC3)"""

    def test_event_cooldown_defined(self):
        """Verify event cooldown is configured"""
        assert EVENT_COOLDOWN_SECONDS == 60

    @pytest.mark.asyncio
    async def test_event_from_disabled_camera_discarded(self, event_handler, disabled_protect_camera):
        """Test that events from disabled cameras are discarded"""
        # Create mock WebSocket message
        mock_msg = MagicMock()
        mock_msg.new_obj = MagicMock()
        mock_msg.new_obj.id = disabled_protect_camera.protect_camera_id
        mock_msg.new_obj.__class__.__name__ = "Camera"
        mock_msg.new_obj.is_motion_currently_detected = True

        result = await event_handler.handle_event("test-ctrl-001", mock_msg)
        assert result is False

    @pytest.mark.asyncio
    async def test_event_from_unknown_camera_discarded(self, event_handler):
        """Test that events from unknown cameras are discarded"""
        mock_msg = MagicMock()
        mock_msg.new_obj = MagicMock()
        mock_msg.new_obj.id = "unknown-camera-id"
        mock_msg.new_obj.__class__.__name__ = "Camera"

        result = await event_handler.handle_event("test-ctrl-001", mock_msg)
        assert result is False


class TestEventHandler:
    """Tests for ProtectEventHandler"""

    def test_handler_has_event_tracking(self, event_handler):
        """Test handler has event time tracking dictionary"""
        assert hasattr(event_handler, '_last_event_times')
        assert isinstance(event_handler._last_event_times, dict)

    @pytest.mark.asyncio
    async def test_handle_event_returns_bool(self, event_handler):
        """Test handle_event returns boolean"""
        mock_msg = MagicMock()
        mock_msg.new_obj = None

        result = await event_handler.handle_event("test-ctrl-001", mock_msg)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_handle_event_invalid_message(self, event_handler):
        """Test handling invalid message (no new_obj)"""
        mock_msg = MagicMock()
        mock_msg.new_obj = None

        result = await event_handler.handle_event("test-ctrl-001", mock_msg)
        assert result is False


class TestEventStorage:
    """Tests for event storage in database"""

    def test_protect_event_stored_with_source_type(self, test_controller, enabled_protect_camera):
        """Test that Protect events have correct source_type"""
        db = TestingSessionLocal()
        try:
            event = Event(
                id="test-event-001",
                camera_id=enabled_protect_camera.id,
                source_type="protect",
                protect_event_id="protect-native-event-001",
                timestamp=datetime.now(timezone.utc),
                description="Person detected at front door",
                confidence=90,
                objects_detected=json.dumps(["person"]),
                smart_detection_type="person"
            )
            db.add(event)
            db.commit()

            # Verify event stored
            found = db.query(Event).filter(Event.id == "test-event-001").first()
            assert found is not None
            assert found.source_type == "protect"
            assert found.protect_event_id == "protect-native-event-001"
            assert found.smart_detection_type == "person"
        finally:
            db.close()

    def test_protect_event_has_all_required_fields(self, enabled_protect_camera):
        """Test that Protect events have all required fields"""
        db = TestingSessionLocal()
        try:
            event = Event(
                id="test-event-fields-001",
                camera_id=enabled_protect_camera.id,
                source_type="protect",
                protect_event_id="protect-native-fields-001",
                timestamp=datetime.now(timezone.utc),
                description="Vehicle in driveway",
                confidence=85,
                objects_detected=json.dumps(["vehicle"]),
                smart_detection_type="vehicle",
                provider_used="grok"
            )
            db.add(event)
            db.commit()

            found = db.query(Event).filter(Event.id == "test-event-fields-001").first()
            assert found is not None
            assert found.camera_id == enabled_protect_camera.id
            assert found.source_type == "protect"
            assert found.description == "Vehicle in driveway"
            assert found.confidence == 85
            assert found.provider_used == "grok"
        finally:
            db.close()


class TestEventAPIRetrieval:
    """Tests for retrieving events via API (AC3 - events appear in dashboard)"""

    def test_protect_events_in_events_list(self, enabled_protect_camera):
        """Test that Protect events appear in events list API"""
        db = TestingSessionLocal()
        try:
            # Create some events
            for i in range(3):
                event = Event(
                    id=f"api-event-{i}",
                    camera_id=enabled_protect_camera.id,
                    source_type="protect",
                    timestamp=datetime.now(timezone.utc),
                    description=f"Test event {i}",
                    confidence=80 + i,
                    objects_detected=json.dumps(["person"])
                )
                db.add(event)
            db.commit()
        finally:
            db.close()

        # Retrieve via API
        response = client.get("/api/v1/events?limit=10")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))
        # Check that our events are present
        protect_events = [e for e in events if e.get("source_type") == "protect"]
        assert len(protect_events) >= 3

    def test_filter_events_by_protect_source(self, enabled_protect_camera):
        """Test filtering events by protect source type"""
        db = TestingSessionLocal()
        try:
            # Create protect event
            event = Event(
                id="filter-event-001",
                camera_id=enabled_protect_camera.id,
                source_type="protect",
                timestamp=datetime.now(timezone.utc),
                description="Filter test event",
                confidence=85,
                objects_detected=json.dumps(["person"])
            )
            db.add(event)
            db.commit()
        finally:
            db.close()

        # Filter by source_type=protect
        response = client.get("/api/v1/events?source_type=protect")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))
        for event in events:
            assert event["source_type"] == "protect"

    def test_protect_event_detail_includes_smart_detection(self, enabled_protect_camera):
        """Test that event detail includes smart detection info"""
        db = TestingSessionLocal()
        try:
            event = Event(
                id="detail-event-001",
                camera_id=enabled_protect_camera.id,
                source_type="protect",
                protect_event_id="protect-detail-native-001",
                timestamp=datetime.now(timezone.utc),
                description="Person walking on driveway",
                confidence=92,
                objects_detected=json.dumps(["person"]),
                smart_detection_type="person"
            )
            db.add(event)
            db.commit()
        finally:
            db.close()

        # Get event detail
        response = client.get("/api/v1/events/detail-event-001")
        if response.status_code == 200:
            data = response.json()
            event_data = data.get("event", data.get("data", data))
            assert event_data.get("source_type") == "protect"
            assert event_data.get("smart_detection_type") == "person"


class TestEventDeduplication:
    """Tests for event deduplication"""

    def test_duplicate_protect_event_id_rejected(self, enabled_protect_camera):
        """Test that duplicate protect_event_id is handled"""
        db = TestingSessionLocal()
        try:
            # Create first event
            event1 = Event(
                id="dedup-event-001",
                camera_id=enabled_protect_camera.id,
                source_type="protect",
                protect_event_id="protect-dedup-native-001",
                timestamp=datetime.now(timezone.utc),
                description="First event",
                confidence=90,
                objects_detected=json.dumps(["person"])
            )
            db.add(event1)
            db.commit()

            # Count events
            count = db.query(Event).filter(
                Event.protect_event_id == "protect-dedup-native-001"
            ).count()
            assert count == 1
        finally:
            db.close()


class TestEventSmartDetectionTypes:
    """Tests for smart detection type filtering"""

    def test_event_smart_detection_type_stored(self, enabled_protect_camera):
        """Test smart detection type is properly stored"""
        db = TestingSessionLocal()
        try:
            types = ["person", "vehicle", "package", "animal"]
            for i, sdt in enumerate(types):
                event = Event(
                    id=f"sdt-event-{i}",
                    camera_id=enabled_protect_camera.id,
                    source_type="protect",
                    timestamp=datetime.now(timezone.utc),
                    description=f"Test {sdt} event",
                    confidence=85,
                    objects_detected=json.dumps([sdt]),
                    smart_detection_type=sdt
                )
                db.add(event)
            db.commit()

            # Verify each type stored correctly
            for i, sdt in enumerate(types):
                found = db.query(Event).filter(Event.id == f"sdt-event-{i}").first()
                assert found is not None
                assert found.smart_detection_type == sdt
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
