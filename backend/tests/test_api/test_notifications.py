"""
Integration tests for Notification API endpoints.

Story P14-3.9: Add Missing API Route Tests
Tests for: backend/app/api/v1/notifications.py

Endpoints tested:
- GET /api/v1/notifications (list with filtering)
- PATCH /api/v1/notifications/{id}/read (mark single as read)
- PATCH /api/v1/notifications/mark-all-read (mark all as read)
- DELETE /api/v1/notifications/{id} (delete single)
- DELETE /api/v1/notifications (bulk delete)
"""
import pytest
import tempfile
import os
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.database import Base, get_db
from app.models.notification import Notification
from app.models.event import Event
from app.models.alert_rule import AlertRule
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


@pytest.fixture(scope="module", autouse=True)
def setup_module_database():
    """Set up database at module level"""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)


client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    db = TestingSessionLocal()
    try:
        db.query(Notification).delete()
        db.query(Event).delete()
        db.query(AlertRule).delete()
        db.query(Camera).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def sample_camera():
    """Create a sample camera for events"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id=str(uuid.uuid4()),
            name="Test Camera",
            type="rtsp",
            source_type="rtsp",
            rtsp_url="rtsp://test:test@192.168.1.100:554/stream",
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        yield camera
    finally:
        db.close()


@pytest.fixture
def sample_event(sample_camera):
    """Create a sample event"""
    db = TestingSessionLocal()
    try:
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Person detected at front door",
            source_type="rtsp",
            objects_detected='["person"]',
            confidence=85,  # Required field
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        yield event
    finally:
        db.close()


@pytest.fixture
def sample_rule():
    """Create a sample alert rule"""
    db = TestingSessionLocal()
    try:
        rule = AlertRule(
            id=str(uuid.uuid4()),
            name="Person Alert",
            is_enabled=True,
            conditions='{"object_type": "person"}',
            actions='{"dashboard_notification": true}',
            cooldown_minutes=5,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        yield rule
    finally:
        db.close()


@pytest.fixture
def sample_notification(sample_event, sample_rule):
    """Create a sample notification"""
    db = TestingSessionLocal()
    try:
        notification = Notification(
            id=str(uuid.uuid4()),
            event_id=sample_event.id,
            rule_id=sample_rule.id,
            rule_name=sample_rule.name,
            event_description="Person detected at front door",
            thumbnail_url="/api/v1/events/{}/thumbnail".format(sample_event.id),
            read=False,
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        yield notification
    finally:
        db.close()


@pytest.fixture
def multiple_notifications(sample_event, sample_rule):
    """Create multiple notifications for testing"""
    db = TestingSessionLocal()
    try:
        notifications = []
        for i in range(5):
            notification = Notification(
                id=str(uuid.uuid4()),
                event_id=sample_event.id,
                rule_id=sample_rule.id,
                rule_name=f"Rule {i+1}",
                event_description=f"Event {i+1}",
                read=(i % 2 == 0),  # Every other one is read
                created_at=datetime.now(timezone.utc) - timedelta(hours=i),
            )
            db.add(notification)
            notifications.append(notification)
        db.commit()
        for n in notifications:
            db.refresh(n)
        yield notifications
    finally:
        db.close()


class TestListNotifications:
    """Test GET /api/v1/notifications endpoint"""

    def test_list_notifications_empty(self):
        """Returns empty list when no notifications exist"""
        response = client.get("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total_count"] == 0
        assert data["unread_count"] == 0

    def test_list_notifications_with_data(self, sample_notification):
        """Returns list of notifications"""
        response = client.get("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["total_count"] == 1
        assert data["unread_count"] == 1
        assert data["data"][0]["rule_name"] == "Person Alert"

    def test_list_notifications_filter_unread(self, multiple_notifications):
        """Filter to only unread notifications"""
        response = client.get("/api/v1/notifications?read=false")

        assert response.status_code == 200
        data = response.json()
        # 5 notifications: indices 0,2,4 are read (even), indices 1,3 are unread
        assert all(n["read"] is False for n in data["data"])

    def test_list_notifications_filter_read(self, multiple_notifications):
        """Filter to only read notifications"""
        response = client.get("/api/v1/notifications?read=true")

        assert response.status_code == 200
        data = response.json()
        assert all(n["read"] is True for n in data["data"])

    def test_list_notifications_pagination(self, multiple_notifications):
        """Test pagination with limit and offset"""
        response = client.get("/api/v1/notifications?limit=2&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        assert data["total_count"] == 5

        # Get second page
        response2 = client.get("/api/v1/notifications?limit=2&offset=2")
        data2 = response2.json()
        assert len(data2["data"]) == 2

    def test_list_notifications_sorted_by_created_at(self, multiple_notifications):
        """Notifications are sorted by created_at descending"""
        response = client.get("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        # Most recent should be first
        timestamps = [n["created_at"] for n in data["data"]]
        assert timestamps == sorted(timestamps, reverse=True)


class TestMarkNotificationRead:
    """Test PATCH /api/v1/notifications/{id}/read endpoint"""

    def test_mark_notification_read_success(self, sample_notification):
        """Successfully mark notification as read"""
        response = client.patch(f"/api/v1/notifications/{sample_notification.id}/read")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_notification.id
        assert data["read"] is True

    def test_mark_notification_read_not_found(self):
        """Returns 404 for non-existent notification"""
        fake_id = str(uuid.uuid4())
        response = client.patch(f"/api/v1/notifications/{fake_id}/read")

        assert response.status_code == 404
        assert response.json()["detail"] == "Notification not found"

    def test_mark_already_read_notification(self, sample_notification):
        """Marking already-read notification is idempotent"""
        # First mark as read
        client.patch(f"/api/v1/notifications/{sample_notification.id}/read")

        # Mark again
        response = client.patch(f"/api/v1/notifications/{sample_notification.id}/read")

        assert response.status_code == 200
        assert response.json()["read"] is True


class TestMarkAllNotificationsRead:
    """Test PATCH /api/v1/notifications/mark-all-read endpoint"""

    def test_mark_all_read_success(self, multiple_notifications):
        """Successfully mark all notifications as read"""
        # Verify we have unread notifications
        list_response = client.get("/api/v1/notifications")
        assert list_response.json()["unread_count"] > 0

        # Mark all as read
        response = client.patch("/api/v1/notifications/mark-all-read")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["updated_count"] >= 0  # May be 0 if all already read

        # Verify all are now read
        list_response2 = client.get("/api/v1/notifications")
        assert list_response2.json()["unread_count"] == 0

    def test_mark_all_read_empty(self):
        """Marking all read when no notifications exists returns success"""
        response = client.patch("/api/v1/notifications/mark-all-read")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["updated_count"] == 0


class TestDeleteNotification:
    """Test DELETE /api/v1/notifications/{id} endpoint"""

    def test_delete_notification_success(self, sample_notification):
        """Successfully delete a notification"""
        response = client.delete(f"/api/v1/notifications/{sample_notification.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["id"] == sample_notification.id

        # Verify it's gone
        list_response = client.get("/api/v1/notifications")
        assert list_response.json()["total_count"] == 0

    def test_delete_notification_not_found(self):
        """Returns 404 for non-existent notification"""
        fake_id = str(uuid.uuid4())
        response = client.delete(f"/api/v1/notifications/{fake_id}")

        assert response.status_code == 404


class TestDeleteAllNotifications:
    """Test DELETE /api/v1/notifications endpoint"""

    def test_delete_all_notifications(self, multiple_notifications):
        """Delete all notifications"""
        # Verify we have notifications
        list_response = client.get("/api/v1/notifications")
        assert list_response.json()["total_count"] == 5

        # Delete all
        response = client.delete("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["count"] == 5

        # Verify all are gone
        list_response2 = client.get("/api/v1/notifications")
        assert list_response2.json()["total_count"] == 0

    def test_delete_only_read_notifications(self, multiple_notifications):
        """Delete only read notifications"""
        # Count initial read notifications (indices 0,2,4 = 3 read)
        list_response = client.get("/api/v1/notifications?read=true")
        read_count = list_response.json()["total_count"]

        # Delete only read
        response = client.delete("/api/v1/notifications?read_only=true")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["count"] == read_count

        # Verify only unread remain
        list_response2 = client.get("/api/v1/notifications")
        assert all(n["read"] is False for n in list_response2.json()["data"])

    def test_delete_all_empty(self):
        """Deleting when no notifications exists returns count 0"""
        response = client.delete("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["count"] == 0


class TestNotificationResponse:
    """Test notification response schema"""

    def test_notification_response_fields(self, sample_notification):
        """Response contains all expected fields"""
        response = client.get("/api/v1/notifications")

        assert response.status_code == 200
        notification = response.json()["data"][0]

        assert "id" in notification
        assert "event_id" in notification
        assert "rule_id" in notification
        assert "rule_name" in notification
        assert "event_description" in notification
        assert "thumbnail_url" in notification
        assert "read" in notification
        assert "created_at" in notification


class TestNotificationPaginationParametrized:
    """Parametrized tests for pagination"""

    @pytest.mark.parametrize("limit,expected", [
        (1, 1),
        (3, 3),
        (10, 5),  # Only 5 exist
        (100, 5),  # Max available
    ])
    def test_pagination_limits(self, multiple_notifications, limit, expected):
        """Test various pagination limits"""
        response = client.get(f"/api/v1/notifications?limit={limit}")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == expected

    @pytest.mark.parametrize("limit", [0, -1, 101])
    def test_invalid_limits(self, limit):
        """Invalid limits should return 422"""
        response = client.get(f"/api/v1/notifications?limit={limit}")
        assert response.status_code == 422

    @pytest.mark.parametrize("offset", [-1])
    def test_invalid_offsets(self, offset):
        """Invalid offsets should return 422"""
        response = client.get(f"/api/v1/notifications?offset={offset}")
        assert response.status_code == 422
