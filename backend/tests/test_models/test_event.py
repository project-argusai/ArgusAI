"""Unit tests for Event SQLAlchemy model"""
import pytest
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.event import Event
from app.models.camera import Camera


# Create in-memory test database
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test"""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    # Clean up
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function")
def test_camera(db_session):
    """Create a test camera for event tests"""
    camera = Camera(
        id="test-camera-123",
        name="Test Camera",
        type="rtsp",
        rtsp_url="rtsp://test.local/stream",
        frame_rate=5,
        is_enabled=True
    )
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


def test_create_event_minimal(db_session, test_camera):
    """Test creating event with minimal required fields"""
    event = Event(
        id="event-123",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Person detected at entrance",
        confidence=85,
        objects_detected=json.dumps(["person"]),
        alert_triggered=False
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.id == "event-123"
    assert event.camera_id == test_camera.id
    assert event.description == "Person detected at entrance"
    assert event.confidence == 85
    assert event.alert_triggered is False
    assert event.created_at is not None


def test_create_event_with_thumbnail_path(db_session, test_camera):
    """Test creating event with filesystem thumbnail"""
    event = Event(
        id="event-456",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Vehicle in driveway",
        confidence=90,
        objects_detected=json.dumps(["vehicle"]),
        thumbnail_path="thumbnails/2025-11-17/event_456.jpg",
        alert_triggered=True
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.thumbnail_path == "thumbnails/2025-11-17/event_456.jpg"
    assert event.thumbnail_base64 is None


def test_create_event_with_thumbnail_base64(db_session, test_camera):
    """Test creating event with base64 thumbnail"""
    base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    event = Event(
        id="event-789",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Package delivered",
        confidence=88,
        objects_detected=json.dumps(["package"]),
        thumbnail_base64=base64_data,
        alert_triggered=False
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.thumbnail_base64 == base64_data
    assert event.thumbnail_path is None


def test_event_confidence_constraint_min(db_session, test_camera):
    """Test confidence constraint prevents values < 0"""
    from sqlalchemy.exc import IntegrityError

    event = Event(
        id="event-invalid-1",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Invalid confidence test",
        confidence=-10,  # Invalid: < 0
        objects_detected=json.dumps(["person"]),
        alert_triggered=False
    )

    db_session.add(event)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()

    assert "check_confidence_range" in str(exc_info.value).lower()


def test_event_confidence_constraint_max(db_session, test_camera):
    """Test confidence constraint prevents values > 100"""
    from sqlalchemy.exc import IntegrityError

    event = Event(
        id="event-invalid-2",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Invalid confidence test",
        confidence=150,  # Invalid: > 100
        objects_detected=json.dumps(["person"]),
        alert_triggered=False
    )

    db_session.add(event)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()

    assert "check_confidence_range" in str(exc_info.value).lower()


def test_event_confidence_boundary_min(db_session, test_camera):
    """Test confidence constraint allows 0"""
    event = Event(
        id="event-boundary-1",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Boundary test",
        confidence=0,  # Valid: minimum
        objects_detected=json.dumps(["unknown"]),
        alert_triggered=False
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.confidence == 0


def test_event_confidence_boundary_max(db_session, test_camera):
    """Test confidence constraint allows 100"""
    event = Event(
        id="event-boundary-2",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Boundary test",
        confidence=100,  # Valid: maximum
        objects_detected=json.dumps(["person"]),
        alert_triggered=False
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.confidence == 100


def test_event_objects_detected_json(db_session, test_camera):
    """Test objects_detected stores and retrieves JSON correctly"""
    objects = ["person", "vehicle", "package"]

    event = Event(
        id="event-json-test",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Multiple objects detected",
        confidence=85,
        objects_detected=json.dumps(objects),
        alert_triggered=False
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    # Retrieve and parse JSON
    retrieved_objects = json.loads(event.objects_detected)
    assert retrieved_objects == objects
    assert len(retrieved_objects) == 3


def test_event_relationship_with_camera(db_session, test_camera):
    """Test bidirectional relationship between Event and Camera"""
    event = Event(
        id="event-relationship",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Relationship test",
        confidence=80,
        objects_detected=json.dumps(["person"]),
        alert_triggered=False
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    db_session.refresh(test_camera)

    # Test forward relationship (event -> camera)
    assert event.camera.id == test_camera.id
    assert event.camera.name == "Test Camera"

    # Test reverse relationship (camera -> events)
    assert len(test_camera.events) == 1
    assert test_camera.events[0].id == "event-relationship"


def test_event_cascade_delete(db_session, test_camera):
    """Test CASCADE delete when camera is deleted"""
    event = Event(
        id="event-cascade",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Cascade delete test",
        confidence=85,
        objects_detected=json.dumps(["person"]),
        alert_triggered=False
    )

    db_session.add(event)
    db_session.commit()

    # Verify event exists
    assert db_session.query(Event).filter(Event.id == "event-cascade").first() is not None

    # Delete camera
    db_session.delete(test_camera)
    db_session.commit()

    # Verify event was cascade deleted
    assert db_session.query(Event).filter(Event.id == "event-cascade").first() is None


def test_event_created_at_auto_populated(db_session, test_camera):
    """Test created_at is automatically set"""
    event = Event(
        id="event-timestamp",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Timestamp test",
        confidence=85,
        objects_detected=json.dumps(["person"]),
        alert_triggered=False
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.created_at is not None
    # Verify created_at is a datetime object
    assert isinstance(event.created_at, datetime)


def test_event_repr(db_session, test_camera):
    """Test __repr__ method returns expected format"""
    timestamp = datetime.now(timezone.utc)

    event = Event(
        id="event-repr",
        camera_id=test_camera.id,
        timestamp=timestamp,
        description="Repr test",
        confidence=85,
        objects_detected=json.dumps(["person"]),
        alert_triggered=False
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    repr_str = repr(event)

    assert "Event" in repr_str
    assert "event-repr" in repr_str
    assert test_camera.id in repr_str
    assert "85" in repr_str


def test_event_alert_triggered_default(db_session, test_camera):
    """Test alert_triggered defaults to False"""
    event = Event(
        id="event-alert-default",
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Alert default test",
        confidence=85,
        objects_detected=json.dumps(["person"])
        # alert_triggered not specified
    )

    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.alert_triggered is False


def test_query_events_by_confidence(db_session, test_camera):
    """Test querying events by confidence range"""
    # Create events with different confidence scores
    events = [
        Event(
            id=f"event-{i}",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description=f"Event {i}",
            confidence=60 + (i * 10),
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        for i in range(5)  # confidence: 60, 70, 80, 90, 100
    ]

    db_session.add_all(events)
    db_session.commit()

    # Query events with confidence >= 80
    high_confidence_events = db_session.query(Event).filter(
        Event.confidence >= 80
    ).all()

    assert len(high_confidence_events) == 3
    assert all(e.confidence >= 80 for e in high_confidence_events)


def test_query_events_by_alert_triggered(db_session, test_camera):
    """Test querying events by alert status"""
    # Create mix of alert/no-alert events
    events = [
        Event(
            id=f"event-{i}",
            camera_id=test_camera.id,
            timestamp=datetime.now(timezone.utc),
            description=f"Event {i}",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=(i % 2 == 0)  # Even indexes trigger alerts
        )
        for i in range(6)
    ]

    db_session.add_all(events)
    db_session.commit()

    # Query only alert events
    alert_events = db_session.query(Event).filter(
        Event.alert_triggered == True
    ).all()

    assert len(alert_events) == 3
    assert all(e.alert_triggered for e in alert_events)


def test_query_events_by_timestamp_range(db_session, test_camera):
    """Test querying events by timestamp range"""
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Create events at different times
    events = [
        Event(
            id=f"event-{i}",
            camera_id=test_camera.id,
            timestamp=now - timedelta(hours=i),
            description=f"Event {i} hours ago",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            alert_triggered=False
        )
        for i in range(10)  # 0-9 hours ago
    ]

    db_session.add_all(events)
    db_session.commit()

    # Query events from last 5 hours (exclusive cutoff)
    recent_cutoff = now - timedelta(hours=5)
    recent_events = db_session.query(Event).filter(
        Event.timestamp > recent_cutoff
    ).all()

    # Should get events from 0-4 hours ago (5 events)
    assert len(recent_events) == 5
