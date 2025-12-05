"""
Coexistence Integration Tests (Story P2-6.1)

Verifies that RTSP, USB, and Protect cameras can coexist without conflicts:
- Events from all sources appear in unified timeline
- Source type filtering works correctly
- Alert rules evaluate events from all sources
- Performance meets requirements (<500ms for event list)
"""
import pytest
import json
import time
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from unittest.mock import Mock, patch, AsyncMock

from main import app
from app.core.database import Base, get_db
from app.models.event import Event
from app.models.camera import Camera
from app.models.alert_rule import AlertRule

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
    conn.commit()

# Create test client
client = TestClient(app)


# ==================== Fixtures ====================

@pytest.fixture(scope="function")
def db_session():
    """Create a clean database session for each test"""
    db = TestingSessionLocal()
    # Clean up any existing data
    db.query(Event).delete()
    db.query(Camera).delete()
    db.query(AlertRule).delete()
    db.commit()
    yield db
    db.close()


@pytest.fixture
def rtsp_camera(db_session):
    """Create an RTSP camera for testing"""
    camera = Camera(
        id="rtsp-cam-001",
        name="Front Door RTSP",
        type="rtsp",  # Legacy type field
        source_type="rtsp",
        rtsp_url="rtsp://192.168.1.100:554/stream1",
        is_enabled=True
    )
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


@pytest.fixture
def usb_camera(db_session):
    """Create a USB camera for testing"""
    camera = Camera(
        id="usb-cam-001",
        name="Back Door USB",
        type="usb",  # Legacy type field
        source_type="usb",
        device_index=0,
        is_enabled=True
    )
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


@pytest.fixture
def protect_camera(db_session):
    """Create a Protect camera for testing"""
    camera = Camera(
        id="protect-cam-001",
        name="Garage Protect",
        type="rtsp",  # Legacy type field (Protect uses rtsp internally)
        source_type="protect",
        protect_camera_id="protect-native-id-001",
        is_enabled=True
    )
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


@pytest.fixture
def mixed_source_events(db_session, rtsp_camera, usb_camera, protect_camera):
    """Create events from all three source types"""
    base_time = datetime.now(timezone.utc)
    events = []

    # RTSP events
    for i in range(3):
        event = Event(
            id=f"rtsp-event-{i}",
            camera_id=rtsp_camera.id,
            source_type="rtsp",
            timestamp=base_time - timedelta(minutes=i * 10),
            description=f"RTSP motion detected at front door {i}",
            confidence=85 + i,
            objects_detected=json.dumps(["person"]),
            provider_used="openai"
        )
        events.append(event)
        db_session.add(event)

    # USB events
    for i in range(3):
        event = Event(
            id=f"usb-event-{i}",
            camera_id=usb_camera.id,
            source_type="usb",
            timestamp=base_time - timedelta(minutes=5 + i * 10),
            description=f"USB motion detected at back door {i}",
            confidence=80 + i,
            objects_detected=json.dumps(["vehicle"]),
            provider_used="grok"
        )
        events.append(event)
        db_session.add(event)

    # Protect events
    for i in range(3):
        event = Event(
            id=f"protect-event-{i}",
            camera_id=protect_camera.id,
            source_type="protect",
            timestamp=base_time - timedelta(minutes=2 + i * 10),
            description=f"Protect smart detection in garage {i}",
            confidence=90 + i,
            objects_detected=json.dumps(["person", "vehicle"]),
            smart_detection_type="person",
            protect_event_id=f"protect-native-{i}",
            provider_used="claude"
        )
        events.append(event)
        db_session.add(event)

    db_session.commit()
    return events


# ==================== Test Classes ====================

class TestMixedSourceTimeline:
    """Tests for unified event timeline with all source types (AC3, AC5, AC8)"""

    def test_events_sorted_by_timestamp_across_sources(self, mixed_source_events, db_session):
        """AC5: Verify events are sorted by timestamp regardless of source type"""
        response = client.get("/api/v1/events?limit=100")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))

        # Verify we have events from all sources
        source_types = set(e["source_type"] for e in events)
        assert "rtsp" in source_types
        assert "usb" in source_types
        assert "protect" in source_types

        # Verify timestamp ordering (newest first)
        timestamps = [e["timestamp"] for e in events]
        for i in range(1, len(timestamps)):
            assert timestamps[i - 1] >= timestamps[i], "Events should be sorted newest first"

    def test_all_sources_appear_in_timeline(self, mixed_source_events, db_session):
        """AC3: Verify all source types coexist in unified timeline"""
        response = client.get("/api/v1/events?limit=100")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))

        # Count events by source type
        rtsp_count = sum(1 for e in events if e["source_type"] == "rtsp")
        usb_count = sum(1 for e in events if e["source_type"] == "usb")
        protect_count = sum(1 for e in events if e["source_type"] == "protect")

        assert rtsp_count == 3, f"Expected 3 RTSP events, got {rtsp_count}"
        assert usb_count == 3, f"Expected 3 USB events, got {usb_count}"
        assert protect_count == 3, f"Expected 3 Protect events, got {protect_count}"

    def test_search_across_all_sources(self, mixed_source_events, db_session):
        """AC8: Verify search includes events from all sources"""
        # Search for "motion" which appears in RTSP and USB events
        response = client.get("/api/v1/events?search_query=motion")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))

        # Should find events from RTSP and USB sources
        source_types = set(e["source_type"] for e in events)
        assert "rtsp" in source_types or "usb" in source_types

    def test_pagination_with_mixed_sources(self, mixed_source_events, db_session):
        """Test pagination works correctly with mixed source events"""
        # Get first page
        response1 = client.get("/api/v1/events?limit=5&offset=0")
        assert response1.status_code == 200
        data1 = response1.json()
        events1 = data1.get("events", data1.get("items", []))
        assert len(events1) == 5

        # Get second page
        response2 = client.get("/api/v1/events?limit=5&offset=5")
        assert response2.status_code == 200
        data2 = response2.json()
        events2 = data2.get("events", data2.get("items", []))
        assert len(events2) == 4  # 9 total events, 5 on first page

        # Verify no duplicates between pages
        ids1 = set(e["id"] for e in events1)
        ids2 = set(e["id"] for e in events2)
        assert len(ids1 & ids2) == 0, "Should be no duplicate events between pages"


class TestSourceTypeFiltering:
    """Tests for source type filtering (AC6, AC7)"""

    def test_filter_rtsp_only(self, mixed_source_events, db_session):
        """AC7: Filter returns only RTSP events"""
        response = client.get("/api/v1/events?source_type=rtsp")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))

        assert len(events) == 3
        for event in events:
            assert event["source_type"] == "rtsp"

    def test_filter_usb_only(self, mixed_source_events, db_session):
        """AC7: Filter returns only USB events"""
        response = client.get("/api/v1/events?source_type=usb")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))

        assert len(events) == 3
        for event in events:
            assert event["source_type"] == "usb"

    def test_filter_protect_only(self, mixed_source_events, db_session):
        """AC7: Filter returns only Protect events"""
        response = client.get("/api/v1/events?source_type=protect")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))

        assert len(events) == 3
        for event in events:
            assert event["source_type"] == "protect"

    def test_filter_multiple_source_types(self, mixed_source_events, db_session):
        """AC7: Filter with multiple source types"""
        response = client.get("/api/v1/events?source_type=rtsp,protect")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))

        assert len(events) == 6  # 3 RTSP + 3 Protect
        for event in events:
            assert event["source_type"] in ["rtsp", "protect"]

    def test_filter_source_type_with_camera_id(self, mixed_source_events, rtsp_camera, db_session):
        """AC7: Filter by source type combined with camera_id"""
        response = client.get(f"/api/v1/events?source_type=rtsp&camera_id={rtsp_camera.id}")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))

        assert len(events) == 3
        for event in events:
            assert event["source_type"] == "rtsp"
            assert event["camera_id"] == rtsp_camera.id

    def test_event_response_includes_source_type(self, mixed_source_events, db_session):
        """AC6: Verify source_type field is present in event responses"""
        response = client.get("/api/v1/events?limit=1")
        assert response.status_code == 200

        data = response.json()
        events = data.get("events", data.get("items", []))
        assert len(events) >= 1

        event = events[0]
        assert "source_type" in event
        assert event["source_type"] in ["rtsp", "usb", "protect"]


class TestAlertRuleCoexistence:
    """Tests for alert rules with all source types (AC9, AC10, AC11)"""

    @pytest.fixture
    def alert_rule(self, db_session, rtsp_camera, usb_camera, protect_camera):
        """Create an alert rule for testing"""
        rule = AlertRule(
            id="coexist-rule-001",
            name="Person Detection Rule",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person"],
                "cameras": [rtsp_camera.id, usb_camera.id, protect_camera.id],
                "min_confidence": 80
            }),
            actions=json.dumps({
                "dashboard_notification": True
            }),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)
        return rule

    def test_alert_rule_matches_rtsp_event(self, alert_rule, rtsp_camera, db_session):
        """AC9: Alert rule evaluates RTSP events"""
        from app.services.alert_engine import AlertEngine

        # Create RTSP event with person detected
        event = Event(
            id="rtsp-alert-test-001",
            camera_id=rtsp_camera.id,
            source_type="rtsp",
            timestamp=datetime.now(timezone.utc),
            description="Person at front door",
            confidence=90,
            objects_detected=json.dumps(["person"])
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        conditions = json.loads(alert_rule.conditions)
        event_objects = json.loads(event.objects_detected)

        # Check object types match (signature: event_objects, rule_object_types)
        matched = engine._check_object_types(
            event_objects,
            conditions.get("object_types", [])
        )
        assert matched, "Rule should match RTSP event with person"

    def test_alert_rule_matches_protect_event(self, alert_rule, protect_camera, db_session):
        """AC9, AC10: Alert rule evaluates Protect events with smart detection"""
        from app.services.alert_engine import AlertEngine

        # Create Protect event with person smart detection
        event = Event(
            id="protect-alert-test-001",
            camera_id=protect_camera.id,
            source_type="protect",
            timestamp=datetime.now(timezone.utc),
            description="Smart detection: Person in garage",
            confidence=95,
            objects_detected=json.dumps(["person"]),
            smart_detection_type="person",
            protect_event_id="protect-native-alert-001"
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        conditions = json.loads(alert_rule.conditions)
        event_objects = json.loads(event.objects_detected)

        # Check object types match (signature: event_objects, rule_object_types)
        matched = engine._check_object_types(
            event_objects,
            conditions.get("object_types", [])
        )
        assert matched, "Rule should match Protect event with person smart detection"


class TestPerformance:
    """Performance tests for coexistence (AC12, AC13)"""

    @pytest.fixture
    def large_mixed_events(self, db_session, rtsp_camera, usb_camera, protect_camera):
        """Create 1000+ events for performance testing"""
        base_time = datetime.now(timezone.utc)
        events = []

        # Create 400 events per source type = 1200 total
        for i in range(400):
            # RTSP event
            rtsp_event = Event(
                id=f"perf-rtsp-{i}",
                camera_id=rtsp_camera.id,
                source_type="rtsp",
                timestamp=base_time - timedelta(minutes=i),
                description=f"RTSP performance test event {i}",
                confidence=80,
                objects_detected=json.dumps(["person"])
            )
            events.append(rtsp_event)

            # USB event
            usb_event = Event(
                id=f"perf-usb-{i}",
                camera_id=usb_camera.id,
                source_type="usb",
                timestamp=base_time - timedelta(minutes=i, seconds=30),
                description=f"USB performance test event {i}",
                confidence=75,
                objects_detected=json.dumps(["vehicle"])
            )
            events.append(usb_event)

            # Protect event
            protect_event = Event(
                id=f"perf-protect-{i}",
                camera_id=protect_camera.id,
                source_type="protect",
                timestamp=base_time - timedelta(minutes=i, seconds=15),
                description=f"Protect performance test event {i}",
                confidence=90,
                objects_detected=json.dumps(["person", "vehicle"]),
                smart_detection_type="person"
            )
            events.append(protect_event)

        # Bulk insert for performance
        db_session.bulk_save_objects(events)
        db_session.commit()
        return events

    def test_event_list_response_time_under_500ms(self, large_mixed_events, db_session):
        """AC13: Event timeline loads efficiently (<500ms)"""
        # Warm up
        client.get("/api/v1/events?limit=50")

        # Time the request
        start_time = time.time()
        response = client.get("/api/v1/events?limit=50")
        elapsed_ms = (time.time() - start_time) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 500, f"Event list took {elapsed_ms:.0f}ms, should be <500ms"

        data = response.json()
        events = data.get("events", data.get("items", []))
        assert len(events) == 50

    def test_source_type_filter_performance(self, large_mixed_events, db_session):
        """AC13: Filtered event list still performs well"""
        # Time filtering by source type
        start_time = time.time()
        response = client.get("/api/v1/events?source_type=protect&limit=50")
        elapsed_ms = (time.time() - start_time) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 500, f"Filtered event list took {elapsed_ms:.0f}ms, should be <500ms"

    def test_search_performance_across_sources(self, large_mixed_events, db_session):
        """AC13: Search across all sources performs well"""
        # Time search query
        start_time = time.time()
        response = client.get("/api/v1/events?search_query=performance&limit=50")
        elapsed_ms = (time.time() - start_time) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 500, f"Search took {elapsed_ms:.0f}ms, should be <500ms"


class TestNoDuplicateEvents:
    """Tests to ensure no duplicate events (AC4)"""

    def test_protect_event_has_unique_id(self, protect_camera, db_session):
        """AC4: Protect events use unique protect_event_id"""
        # Create Protect event
        event = Event(
            id="protect-unique-001",
            camera_id=protect_camera.id,
            source_type="protect",
            timestamp=datetime.now(timezone.utc),
            description="Unique Protect event",
            confidence=90,
            objects_detected=json.dumps(["person"]),
            protect_event_id="protect-native-unique-001"
        )
        db_session.add(event)
        db_session.commit()

        # Query by protect_event_id
        found = db_session.query(Event).filter(
            Event.protect_event_id == "protect-native-unique-001"
        ).first()

        assert found is not None
        assert found.id == "protect-unique-001"

    def test_rtsp_usb_events_have_no_protect_event_id(self, mixed_source_events, db_session):
        """AC4: RTSP/USB events should not have protect_event_id"""
        rtsp_events = db_session.query(Event).filter(Event.source_type == "rtsp").all()
        usb_events = db_session.query(Event).filter(Event.source_type == "usb").all()

        for event in rtsp_events:
            assert event.protect_event_id is None, "RTSP events should not have protect_event_id"

        for event in usb_events:
            assert event.protect_event_id is None, "USB events should not have protect_event_id"


# ==================== Run Tests ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
