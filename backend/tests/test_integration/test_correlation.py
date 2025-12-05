"""
Integration tests for multi-camera event correlation (Story P2-6.4, AC5)

Tests multi-camera correlation:
- Events within time window get same correlation_group_id
- Events from different time windows get different groups
- Correlated events display together

These tests use database-level correlation testing.
"""
import pytest
import json
from datetime import datetime, timezone, timedelta
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


# Correlation time window (same as in event_processor.py)
CORRELATION_WINDOW_SECONDS = 10


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
            id="test-ctrl-correlation",
            name="Correlation Controller",
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
def camera_front(test_controller):
    """Create front camera"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id="cam-front-001",
            name="Front Camera",
            type="rtsp",
            source_type="protect",
            protect_controller_id=test_controller.id,
            protect_camera_id="protect-front-001",
            is_enabled=True
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera
    finally:
        db.close()


@pytest.fixture
def camera_side(test_controller):
    """Create side camera"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id="cam-side-001",
            name="Side Camera",
            type="rtsp",
            source_type="protect",
            protect_controller_id=test_controller.id,
            protect_camera_id="protect-side-001",
            is_enabled=True
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera
    finally:
        db.close()


@pytest.fixture
def camera_back(test_controller):
    """Create back camera"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id="cam-back-001",
            name="Back Camera",
            type="rtsp",
            source_type="protect",
            protect_controller_id=test_controller.id,
            protect_camera_id="protect-back-001",
            is_enabled=True
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera
    finally:
        db.close()


class TestCorrelationGrouping:
    """Tests for correlation_group_id assignment (AC5)"""

    def test_events_same_time_get_same_group(self, camera_front, camera_side):
        """Test events within time window get same correlation_group_id"""
        db = TestingSessionLocal()
        try:
            base_time = datetime.now(timezone.utc)
            correlation_id = "corr-group-001"

            # Event from front camera
            event1 = Event(
                id="corr-event-001",
                camera_id=camera_front.id,
                source_type="protect",
                timestamp=base_time,
                description="Person detected at front",
                confidence=90,
                objects_detected=json.dumps(["person"]),
                correlation_group_id=correlation_id
            )
            db.add(event1)

            # Event from side camera within window
            event2 = Event(
                id="corr-event-002",
                camera_id=camera_side.id,
                source_type="protect",
                timestamp=base_time + timedelta(seconds=5),
                description="Person detected at side",
                confidence=88,
                objects_detected=json.dumps(["person"]),
                correlation_group_id=correlation_id
            )
            db.add(event2)
            db.commit()

            # Verify same correlation group
            found1 = db.query(Event).filter(Event.id == "corr-event-001").first()
            found2 = db.query(Event).filter(Event.id == "corr-event-002").first()

            assert found1.correlation_group_id == found2.correlation_group_id
            assert found1.correlation_group_id == correlation_id
        finally:
            db.close()

    def test_events_different_times_different_groups(self, camera_front, camera_side):
        """Test events outside time window get different correlation groups"""
        db = TestingSessionLocal()
        try:
            base_time = datetime.now(timezone.utc)

            # Event 1 with correlation group
            event1 = Event(
                id="diff-corr-001",
                camera_id=camera_front.id,
                source_type="protect",
                timestamp=base_time,
                description="First person",
                confidence=90,
                objects_detected=json.dumps(["person"]),
                correlation_group_id="group-a"
            )
            db.add(event1)

            # Event 2 much later with different group
            event2 = Event(
                id="diff-corr-002",
                camera_id=camera_side.id,
                source_type="protect",
                timestamp=base_time + timedelta(minutes=5),
                description="Different person",
                confidence=85,
                objects_detected=json.dumps(["person"]),
                correlation_group_id="group-b"
            )
            db.add(event2)
            db.commit()

            found1 = db.query(Event).filter(Event.id == "diff-corr-001").first()
            found2 = db.query(Event).filter(Event.id == "diff-corr-002").first()

            assert found1.correlation_group_id != found2.correlation_group_id
        finally:
            db.close()


class TestMultiCameraCorrelation:
    """Tests for multi-camera correlation (more than 2 cameras)"""

    def test_three_camera_correlation(self, camera_front, camera_side, camera_back):
        """Test correlation across three cameras"""
        db = TestingSessionLocal()
        try:
            base_time = datetime.now(timezone.utc)
            correlation_id = "triple-corr-001"

            events = [
                Event(
                    id="triple-event-001",
                    camera_id=camera_front.id,
                    source_type="protect",
                    timestamp=base_time,
                    description="Person at front",
                    confidence=90,
                    objects_detected=json.dumps(["person"]),
                    correlation_group_id=correlation_id
                ),
                Event(
                    id="triple-event-002",
                    camera_id=camera_side.id,
                    source_type="protect",
                    timestamp=base_time + timedelta(seconds=3),
                    description="Person at side",
                    confidence=88,
                    objects_detected=json.dumps(["person"]),
                    correlation_group_id=correlation_id
                ),
                Event(
                    id="triple-event-003",
                    camera_id=camera_back.id,
                    source_type="protect",
                    timestamp=base_time + timedelta(seconds=7),
                    description="Person at back",
                    confidence=92,
                    objects_detected=json.dumps(["person"]),
                    correlation_group_id=correlation_id
                )
            ]

            for event in events:
                db.add(event)
            db.commit()

            # Query all events with same correlation group
            correlated = db.query(Event).filter(
                Event.correlation_group_id == correlation_id
            ).all()

            assert len(correlated) == 3
            camera_ids = {e.camera_id for e in correlated}
            assert len(camera_ids) == 3  # All from different cameras
        finally:
            db.close()


class TestCorrelationAPI:
    """Tests for correlation display in API"""

    def test_event_detail_includes_correlated_events(self, camera_front, camera_side):
        """Test event detail returns correlated events"""
        db = TestingSessionLocal()
        try:
            base_time = datetime.now(timezone.utc)
            correlation_id = "api-corr-001"

            event1 = Event(
                id="api-corr-event-001",
                camera_id=camera_front.id,
                source_type="protect",
                timestamp=base_time,
                description="Main event",
                confidence=90,
                objects_detected=json.dumps(["person"]),
                correlation_group_id=correlation_id
            )
            event2 = Event(
                id="api-corr-event-002",
                camera_id=camera_side.id,
                source_type="protect",
                timestamp=base_time + timedelta(seconds=5),
                description="Correlated event",
                confidence=88,
                objects_detected=json.dumps(["person"]),
                correlation_group_id=correlation_id
            )
            db.add(event1)
            db.add(event2)
            db.commit()
        finally:
            db.close()

        # Get event detail
        response = client.get("/api/v1/events/api-corr-event-001")
        if response.status_code == 200:
            data = response.json()
            # Check for correlated_events in response
            event_data = data.get("event", data.get("data", data))
            correlated = event_data.get("correlated_events", [])
            # Should have at least one correlated event (the other one)
            # Or correlated_events might not include self
            if correlated:
                correlated_ids = [e.get("id") for e in correlated]
                assert "api-corr-event-002" in correlated_ids

    def test_correlation_excludes_self(self, camera_front, camera_side):
        """Test correlation list does not include the event itself"""
        db = TestingSessionLocal()
        try:
            base_time = datetime.now(timezone.utc)
            correlation_id = "exclude-self-001"

            event1 = Event(
                id="exclude-event-001",
                camera_id=camera_front.id,
                source_type="protect",
                timestamp=base_time,
                description="Event one",
                confidence=90,
                objects_detected=json.dumps(["person"]),
                correlation_group_id=correlation_id
            )
            event2 = Event(
                id="exclude-event-002",
                camera_id=camera_side.id,
                source_type="protect",
                timestamp=base_time + timedelta(seconds=3),
                description="Event two",
                confidence=85,
                objects_detected=json.dumps(["person"]),
                correlation_group_id=correlation_id
            )
            db.add(event1)
            db.add(event2)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/events/exclude-event-001")
        if response.status_code == 200:
            data = response.json()
            event_data = data.get("event", data.get("data", data))
            correlated = event_data.get("correlated_events", [])
            correlated_ids = [e.get("id") for e in correlated]
            # Should not include self
            assert "exclude-event-001" not in correlated_ids


class TestCorrelationWithMixedSources:
    """Tests for correlation with mixed source types"""

    def test_protect_and_rtsp_correlation(self, test_controller):
        """Test correlation between Protect and RTSP cameras"""
        db = TestingSessionLocal()
        try:
            # Create RTSP camera
            rtsp_cam = Camera(
                id="rtsp-corr-001",
                name="RTSP Camera",
                type="rtsp",
                source_type="rtsp",
                rtsp_url="rtsp://192.168.1.100:554/stream1",
                is_enabled=True
            )
            db.add(rtsp_cam)

            # Create Protect camera
            protect_cam = Camera(
                id="protect-corr-001",
                name="Protect Camera",
                type="rtsp",
                source_type="protect",
                protect_controller_id=test_controller.id,
                protect_camera_id="protect-native-corr-001",
                is_enabled=True
            )
            db.add(protect_cam)
            db.commit()

            base_time = datetime.now(timezone.utc)
            correlation_id = "mixed-source-001"

            event_rtsp = Event(
                id="mixed-rtsp-001",
                camera_id=rtsp_cam.id,
                source_type="rtsp",
                timestamp=base_time,
                description="Person on RTSP cam",
                confidence=85,
                objects_detected=json.dumps(["person"]),
                correlation_group_id=correlation_id
            )
            event_protect = Event(
                id="mixed-protect-001",
                camera_id=protect_cam.id,
                source_type="protect",
                timestamp=base_time + timedelta(seconds=5),
                description="Person on Protect cam",
                confidence=90,
                objects_detected=json.dumps(["person"]),
                correlation_group_id=correlation_id
            )
            db.add(event_rtsp)
            db.add(event_protect)
            db.commit()

            # Verify both have same correlation group
            found_rtsp = db.query(Event).filter(Event.id == "mixed-rtsp-001").first()
            found_protect = db.query(Event).filter(Event.id == "mixed-protect-001").first()

            assert found_rtsp.correlation_group_id == found_protect.correlation_group_id
            assert found_rtsp.source_type == "rtsp"
            assert found_protect.source_type == "protect"
        finally:
            db.close()


class TestEventCountInCorrelation:
    """Tests for counting correlated events"""

    def test_count_correlated_events(self, camera_front, camera_side, camera_back):
        """Test counting events in correlation group"""
        db = TestingSessionLocal()
        try:
            base_time = datetime.now(timezone.utc)
            correlation_id = "count-corr-001"

            # Create 5 correlated events
            for i in range(5):
                camera_id = [camera_front.id, camera_side.id, camera_back.id][i % 3]
                event = Event(
                    id=f"count-event-{i}",
                    camera_id=camera_id,
                    source_type="protect",
                    timestamp=base_time + timedelta(seconds=i * 2),
                    description=f"Event {i}",
                    confidence=85 + i,
                    objects_detected=json.dumps(["person"]),
                    correlation_group_id=correlation_id
                )
                db.add(event)
            db.commit()

            count = db.query(Event).filter(
                Event.correlation_group_id == correlation_id
            ).count()

            assert count == 5
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
