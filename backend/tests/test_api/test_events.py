"""Integration tests for events API endpoints"""
import pytest
import json
import base64
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.database import Base, get_db
from app.models.event import Event
from app.models.camera import Camera


# Create test database (file-based to avoid threading issues)
import tempfile
import os

# Use file-based SQLite for testing
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

# Create FTS5 virtual table for testing
with engine.connect() as conn:
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

# Create test client
client = TestClient(app)


@pytest.fixture(scope="function")
def test_camera():
    """Create a test camera for event tests"""
    db = TestingSessionLocal()
    try:
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
    yield
    # Delete all events after each test
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
    assert "thumbnails/" in data["thumbnail_path"]


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
