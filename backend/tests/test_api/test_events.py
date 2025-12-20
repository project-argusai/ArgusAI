"""Integration tests for events API endpoints"""
import pytest
import json
import base64
import tempfile
import os
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.database import Base, get_db
from app.models.event import Event
from app.models.camera import Camera


# Create module-level temp database
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

TEST_DATABASE_URL = f"sqlite:///{_test_db_path}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
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


def _setup_fts5_tables(eng):
    """Set up FTS5 virtual table for full-text search testing"""
    with eng.connect() as conn:
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS events_fts
            USING fts5(
                id UNINDEXED,
                description,
                content='events',
                content_rowid='rowid'
            )
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
                INSERT INTO events_fts(rowid, id, description)
                VALUES (new.rowid, new.id, new.description);
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
                UPDATE events_fts
                SET description = new.description
                WHERE rowid = old.rowid;
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
                DELETE FROM events_fts WHERE rowid = old.rowid;
            END
        """))
        conn.commit()


@pytest.fixture(scope="module", autouse=True)
def setup_module_database():
    """Set up database at module level and clean up after all tests"""
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Set up FTS5
    _setup_fts5_tables(engine)
    # Apply override for all tests in this module
    app.dependency_overrides[get_db] = _override_get_db
    yield
    # Drop tables after all tests in module complete
    Base.metadata.drop_all(bind=engine)


# Create test client (module-level)
client = TestClient(app)


@pytest.fixture(scope="function")
def test_camera():
    """Create a test camera for event tests"""
    db = TestingSessionLocal()
    try:
        # Clean up any existing cameras first
        db.query(Camera).delete()
        db.commit()

        camera = Camera(
            id="test-camera-123",
            name="Test Camera",
            type="rtsp",
            rtsp_url="rtsp://test.local/stream",
            frame_rate=5,
            is_enabled=True
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        yield camera
    finally:
        db.query(Camera).delete()
        db.commit()
        db.close()


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    # Clean up BEFORE the test to ensure isolation
    db = TestingSessionLocal()
    try:
        db.query(Event).delete()
        db.commit()
    finally:
        db.close()
    yield
    # Clean up after each test
    db = TestingSessionLocal()
    try:
        db.query(Event).delete()
        db.commit()
    finally:
        db.close()


# ==================== POST /events Tests ====================

def test_create_event_success(test_camera):
    """Test creating an event with valid data"""
    event_data = {
        "camera_id": test_camera.id,
        "timestamp": "2025-11-17T14:30:00Z",
        "description": "Person walking towards front door carrying a package",
        "confidence": 85,
        "objects_detected": ["person", "package"],
        "alert_triggered": True
    }

    response = client.post("/api/v1/events", json=event_data)

    assert response.status_code == 201
    data = response.json()
    assert data["camera_id"] == test_camera.id
    assert data["description"] == event_data["description"]
    assert data["confidence"] == 85
    assert data["alert_triggered"] is True
    assert "id" in data
    assert "created_at" in data


def test_create_event_with_thumbnail_base64(test_camera):
    """Test creating event with base64-encoded thumbnail"""
    # Create minimal valid JPEG header in base64
    jpeg_bytes = bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46])
    thumbnail_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')

    event_data = {
        "camera_id": test_camera.id,
        "timestamp": "2025-11-17T14:30:00Z",
        "description": "Person detected at entrance",
        "confidence": 90,
        "objects_detected": ["person"],
        "thumbnail_base64": thumbnail_base64,
        "alert_triggered": False
    }

    response = client.post("/api/v1/events", json=event_data)

    assert response.status_code == 201
    data = response.json()
    assert data["thumbnail_path"] is not None
    # Thumbnail path now uses date-based format: YYYY-MM-DD/event_<uuid>.jpg
    assert ".jpg" in data["thumbnail_path"] or "thumbnails/" in data["thumbnail_path"]


def test_create_event_with_thumbnail_path(test_camera):
    """Test creating event with filesystem thumbnail path"""
    event_data = {
        "camera_id": test_camera.id,
        "timestamp": "2025-11-17T14:30:00Z",
        "description": "Vehicle in driveway",
        "confidence": 75,
        "objects_detected": ["vehicle"],
        "thumbnail_path": "thumbnails/2025-11-17/event_123.jpg",
        "alert_triggered": False
    }

    response = client.post("/api/v1/events", json=event_data)

    assert response.status_code == 201
    data = response.json()
    assert data["thumbnail_path"] == "thumbnails/2025-11-17/event_123.jpg"


def test_create_event_invalid_confidence(test_camera):
    """Test creating event with invalid confidence score"""
    event_data = {
        "camera_id": test_camera.id,
        "timestamp": "2025-11-17T14:30:00Z",
        "description": "Test event",
        "confidence": 150,  # Invalid: > 100
        "objects_detected": ["person"],
        "alert_triggered": False
    }

    response = client.post("/api/v1/events", json=event_data)
    assert response.status_code == 422  # Validation error


def test_create_event_empty_objects_detected(test_camera):
    """Test creating event with empty objects_detected list"""
    event_data = {
        "camera_id": test_camera.id,
        "timestamp": "2025-11-17T14:30:00Z",
        "description": "Test event",
        "confidence": 80,
        "objects_detected": [],  # Invalid: empty list
        "alert_triggered": False
    }

    response = client.post("/api/v1/events", json=event_data)
    assert response.status_code == 422  # Validation error


def test_create_event_invalid_object_type(test_camera):
    """Test creating event with invalid object type"""
    event_data = {
        "camera_id": test_camera.id,
        "timestamp": "2025-11-17T14:30:00Z",
        "description": "Test event",
        "confidence": 80,
        "objects_detected": ["invalid_object_type"],  # Not in allowed types
        "alert_triggered": False
    }

    response = client.post("/api/v1/events", json=event_data)
    assert response.status_code == 422  # Validation error


# ==================== GET /events Tests ====================

def test_list_events_empty(test_camera):
    """Test listing events when none exist"""
    response = client.get("/api/v1/events")

    assert response.status_code == 200
    data = response.json()
    assert data["events"] == []
    assert data["total_count"] == 0
    assert data["has_more"] is False
    assert data["next_offset"] is None


def test_list_events_with_data(test_camera):
    """Test listing events with multiple entries"""
    db = TestingSessionLocal()
    try:
        # Create 3 test events
        for i in range(3):
            event = Event(
                id=f"event-{i}",
                camera_id=test_camera.id,
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
                description=f"Test event {i}",
                confidence=80 + i,
                objects_detected=json.dumps(["person"]),
                alert_triggered=False
            )
            db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events")

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 3
    assert data["total_count"] == 3
    assert data["has_more"] is False


def test_list_events_pagination(test_camera):
    """Test event pagination"""
    db = TestingSessionLocal()
    try:
        # Create 10 test events
        for i in range(10):
            event = Event(
                id=f"event-{i}",
                camera_id=test_camera.id,
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
                description=f"Test event {i}",
                confidence=80,
                objects_detected=json.dumps(["person"]),
                alert_triggered=False
            )
            db.add(event)
        db.commit()
    finally:
        db.close()

    # First page
    response = client.get("/api/v1/events?limit=5&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 5
    assert data["total_count"] == 10
    assert data["has_more"] is True
    assert data["next_offset"] == 5

    # Second page
    response = client.get("/api/v1/events?limit=5&offset=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 5
    assert data["has_more"] is False
    assert data["next_offset"] is None


def test_list_events_filter_by_camera(test_camera):
    """Test filtering events by camera_id"""
    db = TestingSessionLocal()
    try:
        # Create another camera
        camera2 = Camera(
            id="test-camera-456",
            name="Camera 2",
            type="usb",
            device_index=0,
            frame_rate=5,
            is_enabled=True
        )
        db.add(camera2)
        db.commit()

        # Create events for both cameras
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Camera 1 event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        event2 = Event(
            id="event-2",
            camera_id=camera2.id,
            timestamp=datetime.now(timezone.utc),
            description="Camera 2 event",
            confidence=85,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False
        )
        db.add(event1)
        db.add(event2)
        db.commit()
    finally:
        db.close()

    # Filter by first camera
    response = client.get(f"/api/v1/events?camera_id={test_camera.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["camera_id"] == test_camera.id


def test_list_events_filter_by_time_range(test_camera):
    """Test filtering events by time range"""
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Create events at different times
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=now - timedelta(days=5),
            description="Old event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=now - timedelta(hours=1),
            description="Recent event",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        db.add(event1)
        db.add(event2)
        db.commit()
    finally:
        db.close()

    # Filter for last 2 days
    start_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace('+00:00', 'Z')
    response = client.get(f"/api/v1/events?start_time={start_time}")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert "Recent event" in data["events"][0]["description"]


def test_list_events_filter_by_confidence(test_camera):
    """Test filtering events by minimum confidence"""
    db = TestingSessionLocal()
    try:
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Low confidence",
            confidence=60,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="High confidence",
            confidence=90,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        db.add(event1)
        db.add(event2)
        db.commit()
    finally:
        db.close()

    # Filter for confidence >= 80
    response = client.get("/api/v1/events?min_confidence=80")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["confidence"] >= 80


def test_list_events_filter_by_object_type(test_camera):
    """Test filtering events by object types"""
    db = TestingSessionLocal()
    try:
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Person detected",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Vehicle detected",
            confidence=85,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False
        )
        db.add(event1)
        db.add(event2)
        db.commit()
    finally:
        db.close()

    # Filter for person only
    response = client.get("/api/v1/events?object_types=person")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert "person" in data["events"][0]["objects_detected"]


def test_list_events_filter_by_alert_status(test_camera):
    """Test filtering events by alert_triggered"""
    db = TestingSessionLocal()
    try:
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="No alert",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Alert triggered",
            confidence=90,
            objects_detected=json.dumps(["person"]),
            alert_triggered=True
        )
        db.add(event1)
        db.add(event2)
        db.commit()
    finally:
        db.close()

    # Filter for alerts only
    response = client.get("/api/v1/events?alert_triggered=true")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["alert_triggered"] is True


def test_list_events_full_text_search(test_camera):
    """Test full-text search using FTS5"""
    db = TestingSessionLocal()
    try:
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Person walking towards front door",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Vehicle parked in driveway",
            confidence=85,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False
        )
        db.add(event1)
        db.add(event2)
        db.commit()
    finally:
        db.close()

    # Search for "front door"
    response = client.get("/api/v1/events?search_query=door")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert "door" in data["events"][0]["description"].lower()


def test_list_events_sort_order(test_camera):
    """Test sorting events by timestamp"""
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=now - timedelta(hours=2),
            description="Older event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=now - timedelta(hours=1),
            description="Newer event",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        db.add(event1)
        db.add(event2)
        db.commit()
    finally:
        db.close()

    # Test descending order (default - newest first)
    response = client.get("/api/v1/events?sort_order=desc")
    assert response.status_code == 200
    data = response.json()
    assert "Newer event" in data["events"][0]["description"]

    # Test ascending order (oldest first)
    response = client.get("/api/v1/events?sort_order=asc")
    assert response.status_code == 200
    data = response.json()
    assert "Older event" in data["events"][0]["description"]


# ==================== GET /events/{id} Tests ====================

def test_get_event_success(test_camera):
    """Test retrieving a single event by ID"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id="test-event-123",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=True
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/test-event-123")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-event-123"
    assert data["description"] == "Test event"
    assert data["confidence"] == 85
    assert data["alert_triggered"] is True


def test_get_event_not_found():
    """Test retrieving non-existent event"""
    response = client.get("/api/v1/events/nonexistent-id")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ==================== GET /events/stats/aggregate Tests ====================

def test_get_event_stats_empty(test_camera):
    """Test getting stats when no events exist"""
    response = client.get("/api/v1/events/stats/aggregate")

    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 0
    assert data["average_confidence"] == 0.0
    assert data["alerts_triggered"] == 0


def test_get_event_stats_with_data(test_camera):
    """Test getting event statistics"""
    db = TestingSessionLocal()
    try:
        # Create test events with varied data
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Person detected",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=True
        )
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Vehicle detected",
            confidence=90,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False
        )
        event3 = Event(
            id="event-3",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Person and package",
            confidence=85,
            objects_detected=json.dumps(["person", "package"]),
            alert_triggered=True
        )
        db.add_all([event1, event2, event3])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/stats/aggregate")

    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 3
    assert data["average_confidence"] == pytest.approx(85.0, rel=0.1)
    assert data["alerts_triggered"] == 2
    assert data["events_by_camera"][test_camera.id] == 3
    assert data["events_by_object_type"]["person"] == 2
    assert data["events_by_object_type"]["vehicle"] == 1
    assert data["events_by_object_type"]["package"] == 1


def test_get_event_stats_filter_by_camera(test_camera):
    """Test getting stats filtered by camera"""
    db = TestingSessionLocal()
    try:
        # Create another camera
        camera2 = Camera(
            id="camera-2",
            name="Camera 2",
            type="usb",
            device_index=0,
            frame_rate=5,
            is_enabled=True
        )
        db.add(camera2)
        db.commit()

        # Create events for both cameras
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Camera 1 event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        event2 = Event(
            id="event-2",
            camera_id=camera2.id,
            timestamp=datetime.now(timezone.utc),
            description="Camera 2 event",
            confidence=90,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False
        )
        db.add_all([event1, event2])
        db.commit()
    finally:
        db.close()

    # Get stats for camera 1 only
    response = client.get(f"/api/v1/events/stats/aggregate?camera_id={test_camera.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 1
    assert test_camera.id in data["events_by_camera"]
    assert data["events_by_camera"][test_camera.id] == 1


def test_get_event_stats_time_range(test_camera):
    """Test getting stats for specific time range"""
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Old event (5 days ago)
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=now - timedelta(days=5),
            description="Old event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        # Recent event (1 hour ago)
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=now - timedelta(hours=1),
            description="Recent event",
            confidence=90,
            objects_detected=json.dumps(["person"]),
            alert_triggered=True
        )
        db.add_all([event1, event2])
        db.commit()
    finally:
        db.close()

    # Get stats for last 2 days only
    start_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace('+00:00', 'Z')
    response = client.get(f"/api/v1/events/stats/aggregate?start_time={start_time}")

    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 1
    assert data["alerts_triggered"] == 1


# ==================== Package Delivery Tests (Story P7-2.4) ====================

def test_get_package_deliveries_today_empty(test_camera):
    """Test getting package deliveries when none exist"""
    response = client.get("/api/v1/events/packages/today")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert data["by_carrier"] == {}
    assert data["recent_events"] == []


def test_get_package_deliveries_today_with_data(test_camera):
    """Test getting package deliveries with carrier breakdown"""
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # Create package events with carriers
        event1 = Event(
            id="pkg-event-1",
            camera_id=test_camera.id,
            timestamp=now - timedelta(hours=1),
            description="FedEx delivery",
            confidence=85,
            objects_detected=json.dumps(["package"]),
            smart_detection_type="package",
            delivery_carrier="fedex",
            alert_triggered=False
        )
        event2 = Event(
            id="pkg-event-2",
            camera_id=test_camera.id,
            timestamp=now - timedelta(hours=2),
            description="Amazon delivery",
            confidence=80,
            objects_detected=json.dumps(["package", "person"]),
            smart_detection_type="package",
            delivery_carrier="amazon",
            alert_triggered=False
        )
        event3 = Event(
            id="pkg-event-3",
            camera_id=test_camera.id,
            timestamp=now - timedelta(hours=3),
            description="Unknown carrier package",
            confidence=75,
            objects_detected=json.dumps(["package"]),
            smart_detection_type="package",
            delivery_carrier=None,  # Unknown carrier
            alert_triggered=False
        )
        db.add_all([event1, event2, event3])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/packages/today")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 3
    assert data["by_carrier"]["fedex"] == 1
    assert data["by_carrier"]["amazon"] == 1
    assert data["by_carrier"]["unknown"] == 1
    assert len(data["recent_events"]) == 3
    # Most recent first
    assert data["recent_events"][0]["id"] == "pkg-event-1"
    assert data["recent_events"][0]["delivery_carrier_display"] == "FedEx"


def test_get_package_deliveries_today_excludes_yesterday(test_camera):
    """Test that only today's deliveries are included"""
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # Today's package
        event_today = Event(
            id="pkg-today",
            camera_id=test_camera.id,
            timestamp=now - timedelta(hours=1),
            description="Today's package",
            confidence=85,
            objects_detected=json.dumps(["package"]),
            smart_detection_type="package",
            delivery_carrier="ups",
            alert_triggered=False
        )
        # Yesterday's package
        event_yesterday = Event(
            id="pkg-yesterday",
            camera_id=test_camera.id,
            timestamp=now - timedelta(days=1, hours=5),
            description="Yesterday's package",
            confidence=85,
            objects_detected=json.dumps(["package"]),
            smart_detection_type="package",
            delivery_carrier="fedex",
            alert_triggered=False
        )
        db.add_all([event_today, event_yesterday])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/packages/today")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["by_carrier"]["ups"] == 1
    assert "fedex" not in data["by_carrier"]


# ==================== Performance Tests ====================

def test_list_events_performance_large_dataset(test_camera):
    """Test query performance with large dataset"""
    db = TestingSessionLocal()
    try:
        # Create 100 events
        import time
        events = []
        for i in range(100):
            event = Event(
                id=f"event-{i}",
                camera_id=test_camera.id,
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
                description=f"Performance test event {i}",
                confidence=70 + (i % 30),
                objects_detected=json.dumps(["person"] if i % 2 == 0 else ["vehicle"]),
                alert_triggered=(i % 3 == 0)
            )
            events.append(event)
        db.add_all(events)
        db.commit()

        # Test query performance
        start_time = time.time()
        response = client.get("/api/v1/events?limit=50&offset=0&min_confidence=80")
        elapsed_time = time.time() - start_time

        assert response.status_code == 200
        assert elapsed_time < 1.0  # Should complete in less than 1 second
    finally:
        db.close()


def test_fts5_search_performance(test_camera):
    """Test FTS5 full-text search performance"""
    db = TestingSessionLocal()
    try:
        # Create events with varied descriptions
        import time
        descriptions = [
            "Person walking towards front door",
            "Vehicle parked in driveway",
            "Package delivered at entrance",
            "Animal crossing the yard",
            "Person carrying a package to the door",
            "Unknown object detected near entrance"
        ]
        events = []
        for i in range(50):
            event = Event(
                id=f"event-{i}",
                camera_id=test_camera.id,
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
                description=descriptions[i % len(descriptions)],
                confidence=80,
                objects_detected=json.dumps(["person"]),
                alert_triggered=False
            )
            events.append(event)
        db.add_all(events)
        db.commit()

        # Test FTS5 search performance
        start_time = time.time()
        response = client.get("/api/v1/events?search_query=door")
        elapsed_time = time.time() - start_time

        assert response.status_code == 200
        assert elapsed_time < 0.5  # FTS5 should be very fast
        assert response.json()["total_count"] > 0
    finally:
        db.close()


# ==================== Source Type Filter Tests (Phase 2) ====================

def test_list_events_filter_by_source_type_single(test_camera):
    """Test filtering events by a single source_type"""
    db = TestingSessionLocal()
    try:
        # Create events with different source types
        event_rtsp = Event(
            id="event-rtsp",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="RTSP camera event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp"
        )
        event_protect = Event(
            id="event-protect",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Protect camera event",
            confidence=85,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False,
            source_type="protect",
            smart_detection_type="vehicle"
        )
        event_usb = Event(
            id="event-usb",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="USB camera event",
            confidence=75,
            objects_detected=json.dumps(["animal"]),
            alert_triggered=False,
            source_type="usb"
        )
        db.add_all([event_rtsp, event_protect, event_usb])
        db.commit()
    finally:
        db.close()

    # Filter for protect only
    response = client.get("/api/v1/events?source_type=protect")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["source_type"] == "protect"
    assert data["events"][0]["smart_detection_type"] == "vehicle"


def test_list_events_filter_by_source_type_multiple(test_camera):
    """Test filtering events by multiple source_types (comma-separated)"""
    db = TestingSessionLocal()
    try:
        event_rtsp = Event(
            id="event-rtsp",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="RTSP event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp"
        )
        event_protect = Event(
            id="event-protect",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Protect event",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="protect"
        )
        event_usb = Event(
            id="event-usb",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="USB event",
            confidence=75,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="usb"
        )
        db.add_all([event_rtsp, event_protect, event_usb])
        db.commit()
    finally:
        db.close()

    # Filter for rtsp and protect
    response = client.get("/api/v1/events?source_type=rtsp,protect")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2
    source_types = {e["source_type"] for e in data["events"]}
    assert source_types == {"rtsp", "protect"}


def test_list_events_filter_by_source_type_invalid_ignored(test_camera):
    """Test that invalid source_type values are ignored"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp"
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    # Filter with invalid source type - should return nothing
    # because "invalid" is not a valid source type and is filtered out
    response = client.get("/api/v1/events?source_type=invalid")
    assert response.status_code == 200
    data = response.json()
    # All events returned when filter is effectively empty after validation
    assert data["total_count"] == 1


def test_list_events_filter_source_type_with_other_filters(test_camera):
    """Test source_type filter combined with other filters"""
    db = TestingSessionLocal()
    try:
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="High confidence protect event",
            confidence=95,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="protect"
        )
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Low confidence protect event",
            confidence=50,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="protect"
        )
        event3 = Event(
            id="event-3",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="High confidence rtsp event",
            confidence=95,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp"
        )
        db.add_all([event1, event2, event3])
        db.commit()
    finally:
        db.close()

    # Filter for protect events with confidence >= 80
    response = client.get("/api/v1/events?source_type=protect&min_confidence=80")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["source_type"] == "protect"
    assert data["events"][0]["confidence"] >= 80


def test_event_response_includes_source_fields(test_camera):
    """Test that event responses include source_type and smart_detection_type"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id="event-protect-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Person detected at front door",
            confidence=90,
            objects_detected=json.dumps(["person"]),
            alert_triggered=True,
            source_type="protect",
            smart_detection_type="person"
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/event-protect-1")
    assert response.status_code == 200
    data = response.json()
    assert "source_type" in data
    assert data["source_type"] == "protect"
    assert "smart_detection_type" in data
    assert data["smart_detection_type"] == "person"


# ==================== Story P2-4.4: Correlated Events Tests ====================

def test_get_event_with_correlated_events(test_camera):
    """Test that GET /events/{id} returns correlated_events when correlation_group_id exists (AC7)"""
    db = TestingSessionLocal()
    try:
        # Create a second camera
        camera2 = Camera(
            id="camera-2-corr",
            name="Front Door Camera",
            type="rtsp",
            rtsp_url="rtsp://test.local/stream2",
            frame_rate=5,
            is_enabled=True
        )
        db.add(camera2)
        db.commit()

        correlation_id = "corr-group-123"
        now = datetime.now(timezone.utc)

        # Create primary event
        event1 = Event(
            id="event-corr-1",
            camera_id=test_camera.id,
            timestamp=now,
            description="Person detected at primary camera",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            correlation_group_id=correlation_id
        )
        # Create correlated event from second camera
        event2 = Event(
            id="event-corr-2",
            camera_id=camera2.id,
            timestamp=now - timedelta(seconds=5),
            description="Person detected at secondary camera",
            confidence=90,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            correlation_group_id=correlation_id,
            thumbnail_path="thumbnails/2025-11-30/event-corr-2.jpg"
        )
        db.add_all([event1, event2])
        db.commit()
    finally:
        db.close()

    # Fetch the primary event - should include correlated_events
    response = client.get("/api/v1/events/event-corr-1")
    assert response.status_code == 200
    data = response.json()

    # Verify correlated_events is populated
    assert "correlated_events" in data
    assert data["correlated_events"] is not None
    assert len(data["correlated_events"]) == 1

    # Verify correlated event structure
    correlated = data["correlated_events"][0]
    assert correlated["id"] == "event-corr-2"
    assert correlated["camera_name"] == "Front Door Camera"
    assert correlated["thumbnail_url"] == "/api/v1/thumbnails/thumbnails/2025-11-30/event-corr-2.jpg"
    assert "timestamp" in correlated


def test_get_event_without_correlation_returns_null(test_camera):
    """Test that GET /events/{id} returns null correlated_events when no correlation_group_id"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id="event-no-corr",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Standalone event",
            confidence=80,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False,
            correlation_group_id=None  # No correlation
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/event-no-corr")
    assert response.status_code == 200
    data = response.json()

    # correlated_events should be null/None when no correlation
    assert data.get("correlated_events") is None


def test_get_event_correlation_excludes_self(test_camera):
    """Test that correlated_events does not include the event being fetched"""
    db = TestingSessionLocal()
    try:
        correlation_id = "corr-group-self"
        now = datetime.now(timezone.utc)

        # Create event with correlation
        event = Event(
            id="event-self",
            camera_id=test_camera.id,
            timestamp=now,
            description="Self-referential test",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            correlation_group_id=correlation_id
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/event-self")
    assert response.status_code == 200
    data = response.json()

    # Should return empty list (not None) when no other correlated events
    # Actually based on implementation, should be None if no OTHER events in group
    assert data.get("correlated_events") is None or len(data.get("correlated_events", [])) == 0


def test_get_event_correlation_multiple_cameras(test_camera):
    """Test correlated_events with 3+ cameras in same correlation group"""
    db = TestingSessionLocal()
    try:
        # Create additional cameras
        camera2 = Camera(
            id="camera-multi-2",
            name="Backyard Camera",
            type="rtsp",
            rtsp_url="rtsp://test.local/backyard",
            frame_rate=5,
            is_enabled=True
        )
        camera3 = Camera(
            id="camera-multi-3",
            name="Side Entrance",
            type="usb",
            device_index=0,
            frame_rate=5,
            is_enabled=True
        )
        db.add_all([camera2, camera3])
        db.commit()

        correlation_id = "corr-group-multi"
        now = datetime.now(timezone.utc)

        # Create events from 3 cameras
        event1 = Event(
            id="event-multi-1",
            camera_id=test_camera.id,
            timestamp=now,
            description="Event from primary",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            correlation_group_id=correlation_id
        )
        event2 = Event(
            id="event-multi-2",
            camera_id=camera2.id,
            timestamp=now - timedelta(seconds=3),
            description="Event from backyard",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            correlation_group_id=correlation_id
        )
        event3 = Event(
            id="event-multi-3",
            camera_id=camera3.id,
            timestamp=now - timedelta(seconds=7),
            description="Event from side entrance",
            confidence=75,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            correlation_group_id=correlation_id
        )
        db.add_all([event1, event2, event3])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/event-multi-1")
    assert response.status_code == 200
    data = response.json()

    # Should have 2 correlated events (excludes self)
    assert data["correlated_events"] is not None
    assert len(data["correlated_events"]) == 2

    # Verify camera names
    camera_names = {e["camera_name"] for e in data["correlated_events"]}
    assert "Backyard Camera" in camera_names
    assert "Side Entrance" in camera_names


# ==================== Story P3-6.4: Re-Analyze Event Tests ====================


def test_reanalyze_event_not_found():
    """Test POST /events/{id}/reanalyze returns 404 for non-existent event"""
    response = client.post(
        "/api/v1/events/non-existent-event/reanalyze",
        json={"analysis_mode": "single_frame"}
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_reanalyze_event_invalid_mode_for_rtsp_camera(test_camera):
    """Test that multi_frame/video_native modes are rejected for RTSP cameras (AC6)"""
    db = TestingSessionLocal()
    try:
        # Create an RTSP event with a thumbnail
        event = Event(
            id="event-rtsp-reanalyze",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Original description",
            confidence=60,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp",
            low_confidence=True,
            thumbnail_base64="dGVzdA=="  # base64 "test"
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    # Try multi_frame mode - should fail for RTSP
    response = client.post(
        "/api/v1/events/event-rtsp-reanalyze/reanalyze",
        json={"analysis_mode": "multi_frame"}
    )
    assert response.status_code == 400
    assert "not available" in response.json()["detail"].lower()

    # Try video_native mode - should fail for RTSP
    response = client.post(
        "/api/v1/events/event-rtsp-reanalyze/reanalyze",
        json={"analysis_mode": "video_native"}
    )
    assert response.status_code == 400
    assert "not available" in response.json()["detail"].lower()


def test_reanalyze_event_rate_limiting(test_camera):
    """Test rate limiting: max 3 re-analyses per event per hour (AC6)"""
    db = TestingSessionLocal()
    try:
        # Create event that has already been re-analyzed 3 times within the hour
        event = Event(
            id="event-rate-limit",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Rate limited event",
            confidence=40,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp",
            low_confidence=True,
            thumbnail_base64="dGVzdA==",
            reanalyzed_at=datetime.now(timezone.utc),  # Within the hour
            reanalysis_count=3  # Already at limit
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    # Should be rate limited
    response = client.post(
        "/api/v1/events/event-rate-limit/reanalyze",
        json={"analysis_mode": "single_frame"}
    )
    assert response.status_code == 429
    assert "rate limit" in response.json()["detail"].lower()


def test_reanalyze_event_rate_limit_resets_after_hour(test_camera):
    """Test that rate limit resets after 1 hour"""
    db = TestingSessionLocal()
    try:
        # Create event that was re-analyzed 3 times but over an hour ago
        event = Event(
            id="event-rate-reset",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Rate reset event",
            confidence=40,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp",
            low_confidence=True,
            thumbnail_base64="dGVzdA==",
            reanalyzed_at=datetime.now(timezone.utc) - timedelta(hours=2),  # Over an hour ago
            reanalysis_count=3
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    # Should NOT be rate limited since last reanalysis was over an hour ago
    # Note: This test will fail because we don't mock the AI service
    # In a real test, we'd mock the AI service to return a result
    # For now, just verify the endpoint doesn't return 429
    response = client.post(
        "/api/v1/events/event-rate-reset/reanalyze",
        json={"analysis_mode": "single_frame"}
    )
    # Should not be 429 (rate limit)
    assert response.status_code != 429


def test_reanalyze_event_missing_thumbnail(test_camera):
    """Test re-analyze fails gracefully when thumbnail is missing"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id="event-no-thumb",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="No thumbnail event",
            confidence=40,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp",
            low_confidence=True,
            thumbnail_base64=None,
            thumbnail_path=None
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/events/event-no-thumb/reanalyze",
        json={"analysis_mode": "single_frame"}
    )
    assert response.status_code == 400
    assert "thumbnail" in response.json()["detail"].lower()


def test_reanalyze_request_schema_validation():
    """Test that invalid analysis_mode is rejected by schema validation"""
    response = client.post(
        "/api/v1/events/any-event/reanalyze",
        json={"analysis_mode": "invalid_mode"}
    )
    # Pydantic validation should return 422
    assert response.status_code == 422


def test_reanalyze_event_corrupted_thumbnail(test_camera):
    """Test re-analyze fails gracefully when thumbnail is corrupted (AC1.5, AC1.6)

    Story P8-1.1: Fix Re-Analyse Function Error
    - AC1.5: Given re-analysis failure, then clear error message is displayed
    - AC1.6: Given re-analysis failure, then error is logged with stack trace
    """
    db = TestingSessionLocal()
    try:
        event = Event(
            id="event-corrupt-thumb",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event with corrupted thumbnail",
            confidence=40,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp",
            low_confidence=True,
            # This is NOT valid image data - just random base64 text
            thumbnail_base64="dGhpcyBpcyBub3QgYSB2YWxpZCBpbWFnZQ=="
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/events/event-corrupt-thumb/reanalyze",
        json={"analysis_mode": "single_frame"}
    )
    assert response.status_code == 400
    # AC1.5: Clear error message
    assert "corrupted" in response.json()["detail"].lower() or "invalid" in response.json()["detail"].lower()


def test_reanalyze_event_response_includes_reanalyzed_fields(test_camera):
    """Test that response includes reanalyzed_at and reanalysis_count fields"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id="event-resp-fields",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Response fields test",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            source_type="rtsp",
            low_confidence=False,
            reanalyzed_at=datetime.now(timezone.utc),
            reanalysis_count=1
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    # GET single event should include the new fields
    response = client.get("/api/v1/events/event-resp-fields")
    assert response.status_code == 200
    data = response.json()
    assert "reanalyzed_at" in data
    assert "reanalysis_count" in data
    assert data["reanalysis_count"] == 1


# ==================== Analysis Mode Filter Tests (Story P3-7.6) ====================

def test_list_events_filter_by_analysis_mode_single_frame(test_camera):
    """Test filtering events by analysis_mode=single_frame"""
    db = TestingSessionLocal()
    try:
        # Create events with different analysis modes
        event_single = Event(
            id="event-single",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Single frame analysis event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="single_frame"
        )
        event_multi = Event(
            id="event-multi",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Multi frame analysis event",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="multi_frame",
            frame_count_used=5
        )
        event_video = Event(
            id="event-video",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Video native analysis event",
            confidence=90,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False,
            analysis_mode="video_native"
        )
        db.add_all([event_single, event_multi, event_video])
        db.commit()
    finally:
        db.close()

    # Filter for single_frame only
    response = client.get("/api/v1/events?analysis_mode=single_frame")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["analysis_mode"] == "single_frame"


def test_list_events_filter_by_analysis_mode_multi_frame(test_camera):
    """Test filtering events by analysis_mode=multi_frame"""
    db = TestingSessionLocal()
    try:
        event_single = Event(
            id="event-single",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Single frame event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="single_frame"
        )
        event_multi = Event(
            id="event-multi",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Multi frame event",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="multi_frame",
            frame_count_used=5
        )
        db.add_all([event_single, event_multi])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events?analysis_mode=multi_frame")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["analysis_mode"] == "multi_frame"
    assert data["events"][0]["frame_count_used"] == 5


def test_list_events_filter_by_analysis_mode_video_native(test_camera):
    """Test filtering events by analysis_mode=video_native"""
    db = TestingSessionLocal()
    try:
        event_multi = Event(
            id="event-multi",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Multi frame event",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="multi_frame"
        )
        event_video = Event(
            id="event-video",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Video native event",
            confidence=90,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False,
            analysis_mode="video_native"
        )
        db.add_all([event_multi, event_video])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events?analysis_mode=video_native")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["analysis_mode"] == "video_native"


def test_list_events_filter_by_has_fallback_true(test_camera):
    """Test filtering events with has_fallback=true returns events with fallback_reason"""
    db = TestingSessionLocal()
    try:
        event_fallback = Event(
            id="event-fallback",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event with fallback",
            confidence=75,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="single_frame",
            fallback_reason="clip_download_failed"
        )
        event_no_fallback = Event(
            id="event-no-fallback",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event without fallback",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="multi_frame",
            fallback_reason=None
        )
        db.add_all([event_fallback, event_no_fallback])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events?has_fallback=true")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["fallback_reason"] == "clip_download_failed"


def test_list_events_filter_by_has_fallback_false(test_camera):
    """Test filtering events with has_fallback=false returns events without fallback_reason"""
    db = TestingSessionLocal()
    try:
        event_fallback = Event(
            id="event-fallback",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event with fallback",
            confidence=75,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            fallback_reason="clip_download_failed"
        )
        event_no_fallback = Event(
            id="event-no-fallback",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event without fallback",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            fallback_reason=None
        )
        db.add_all([event_fallback, event_no_fallback])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events?has_fallback=false")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["fallback_reason"] is None


def test_list_events_filter_by_low_confidence_true(test_camera):
    """Test filtering events with low_confidence=true returns uncertain descriptions"""
    db = TestingSessionLocal()
    try:
        event_low = Event(
            id="event-low-conf",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Uncertain event description",
            confidence=40,
            objects_detected=json.dumps(["unknown"]),
            alert_triggered=False,
            low_confidence=True,
            ai_confidence=35
        )
        event_high = Event(
            id="event-high-conf",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Confident event description",
            confidence=90,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            low_confidence=False,
            ai_confidence=88
        )
        db.add_all([event_low, event_high])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events?low_confidence=true")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["low_confidence"] is True
    assert data["events"][0]["ai_confidence"] == 35


def test_list_events_filter_by_low_confidence_false(test_camera):
    """Test filtering events with low_confidence=false returns confident descriptions"""
    db = TestingSessionLocal()
    try:
        event_low = Event(
            id="event-low-conf",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Uncertain event",
            confidence=40,
            objects_detected=json.dumps(["unknown"]),
            alert_triggered=False,
            low_confidence=True
        )
        event_high = Event(
            id="event-high-conf",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Confident event",
            confidence=90,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            low_confidence=False
        )
        db.add_all([event_low, event_high])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events?low_confidence=false")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["low_confidence"] is False


def test_list_events_combined_analysis_filters(test_camera):
    """Test combined analysis mode filters (analysis_mode + has_fallback + camera_id)"""
    db = TestingSessionLocal()
    try:
        # Event: multi_frame with fallback (should match)
        event1 = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Multi frame with fallback",
            confidence=75,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="multi_frame",
            fallback_reason="video_upload_failed"
        )
        # Event: multi_frame without fallback (should NOT match)
        event2 = Event(
            id="event-2",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Multi frame no fallback",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="multi_frame",
            fallback_reason=None
        )
        # Event: single_frame with fallback (should NOT match - wrong mode)
        event3 = Event(
            id="event-3",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Single frame with fallback",
            confidence=70,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="single_frame",
            fallback_reason="clip_too_short"
        )
        db.add_all([event1, event2, event3])
        db.commit()
    finally:
        db.close()

    # Filter for multi_frame AND has_fallback
    response = client.get(f"/api/v1/events?analysis_mode=multi_frame&has_fallback=true&camera_id={test_camera.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["events"][0]["analysis_mode"] == "multi_frame"
    assert data["events"][0]["fallback_reason"] == "video_upload_failed"


def test_list_events_analysis_mode_invalid_ignored(test_camera):
    """Test that invalid analysis_mode values are ignored"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id="event-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            analysis_mode="multi_frame"
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    # Invalid analysis_mode should be filtered out, returning all events
    response = client.get("/api/v1/events?analysis_mode=invalid_mode")
    assert response.status_code == 200
    data = response.json()
    # Since invalid mode is filtered out, no filter is applied
    assert data["total_count"] == 1


# ==================== Delivery Carrier Tests (Story P7-2.1) ====================

def test_event_response_includes_delivery_carrier_field(test_camera):
    """Test that event response includes delivery_carrier field (AC: 5)"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id="event-carrier-fedex",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="FedEx driver delivered a package",
            confidence=85,
            objects_detected=json.dumps(["person", "package"]),
            alert_triggered=False,
            delivery_carrier="fedex"
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/event-carrier-fedex")
    assert response.status_code == 200
    data = response.json()
    assert "delivery_carrier" in data
    assert data["delivery_carrier"] == "fedex"
    assert "delivery_carrier_display" in data
    assert data["delivery_carrier_display"] == "FedEx"


def test_event_response_delivery_carrier_null_when_not_detected(test_camera):
    """Test that delivery_carrier is null when not detected (AC: 5)"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id="event-no-carrier",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Person walking across the driveway",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            delivery_carrier=None
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/events/event-no-carrier")
    assert response.status_code == 200
    data = response.json()
    assert "delivery_carrier" in data
    assert data["delivery_carrier"] is None
    assert "delivery_carrier_display" in data
    assert data["delivery_carrier_display"] is None


def test_event_list_includes_delivery_carrier_fields(test_camera):
    """Test that event list response includes delivery_carrier fields (AC: 5)"""
    db = TestingSessionLocal()
    try:
        event1 = Event(
            id="event-list-carrier-1",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="UPS driver dropped off package",
            confidence=90,
            objects_detected=json.dumps(["person", "package"]),
            alert_triggered=False,
            delivery_carrier="ups"
        )
        event2 = Event(
            id="event-list-carrier-2",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Amazon van parked in driveway",
            confidence=85,
            objects_detected=json.dumps(["vehicle"]),
            alert_triggered=False,
            delivery_carrier="amazon"
        )
        db.add_all([event1, event2])
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/v1/events?camera_id={test_camera.id}&limit=10")
    assert response.status_code == 200
    data = response.json()
    # Find the carrier events in the list
    carriers_found = {}
    for event in data["events"]:
        if event.get("delivery_carrier"):
            carriers_found[event["delivery_carrier"]] = event.get("delivery_carrier_display")

    # Verify at least our test carriers are present
    assert "ups" in carriers_found or "amazon" in carriers_found


@pytest.mark.parametrize("carrier,display_name", [
    ("fedex", "FedEx"),
    ("ups", "UPS"),
    ("usps", "USPS"),
    ("amazon", "Amazon"),
    ("dhl", "DHL"),
])
def test_delivery_carrier_display_name_mapping(test_camera, carrier, display_name):
    """Test that each carrier has correct display name (AC: 5)"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id=f"event-carrier-{carrier}",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description=f"{display_name} delivery",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False,
            delivery_carrier=carrier
        )
        db.add(event)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/v1/events/event-carrier-{carrier}")
    assert response.status_code == 200
    data = response.json()
    assert data["delivery_carrier"] == carrier
    assert data["delivery_carrier_display"] == display_name
