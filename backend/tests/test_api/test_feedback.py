"""
Tests for Event Feedback API endpoints (Story P4-5.1)
"""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
from datetime import datetime, timezone

from main import app
from app.core.database import Base, get_db
from app.models.event import Event
from app.models.event_feedback import EventFeedback
from app.models.camera import Camera
from app.models.summary_feedback import SummaryFeedback  # Story P9-3.6
from app.models.activity_summary import ActivitySummary  # Story P9-3.6


# Create module-level temp database (file-based for isolation)
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{_test_db_path}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    """Override dependency to use test database"""
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
    """Set up database and override at module start, teardown at end."""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    # Clean up temp file
    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)


@pytest.fixture(scope="function")
def clean_db():
    """Clean up all data before each test function."""
    # Clean up data from previous test
    db = TestingSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            try:
                db.execute(table.delete())
            except Exception:
                pass
        db.commit()
    finally:
        db.close()
    yield
    # Also clean after test
    db = TestingSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            try:
                db.execute(table.delete())
            except Exception:
                pass
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client(clean_db):
    """Create test client - override already applied at module level"""
    yield TestClient(app)


@pytest.fixture
def db_session(clean_db):
    """Get database session for test setup"""
    return TestingSessionLocal()


@pytest.fixture
def test_camera(db_session) -> Camera:
    """Create a test camera"""
    camera = Camera(
        id=str(uuid.uuid4()),
        name="Test Camera",
        type="rtsp",  # Required field
        rtsp_url="rtsp://test:test@localhost:554/stream",
        is_enabled=True,
        source_type="rtsp"
    )
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


@pytest.fixture
def test_event(db_session, test_camera: Camera) -> Event:
    """Create a test event"""
    event = Event(
        id=str(uuid.uuid4()),
        camera_id=test_camera.id,
        timestamp=datetime.now(timezone.utc),
        description="Test event description",
        confidence=85,
        objects_detected='["person"]',
        alert_triggered=False,
        source_type="rtsp"
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


class TestEventFeedbackEndpoints:
    """Test suite for event feedback API endpoints"""

    def test_create_feedback_helpful(self, client, test_event: Event):
        """Test creating feedback with helpful rating (AC3, AC12)"""
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={"rating": "helpful"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["event_id"] == test_event.id
        assert data["rating"] == "helpful"
        assert data["correction"] is None
        assert "id" in data
        assert "created_at" in data

    def test_create_feedback_not_helpful(self, client, test_event: Event):
        """Test creating feedback with not_helpful rating (AC4, AC12)"""
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={"rating": "not_helpful"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["rating"] == "not_helpful"

    def test_create_feedback_with_correction(self, client, test_event: Event):
        """Test creating feedback with correction text (AC13)"""
        correction_text = "This was actually a delivery driver"
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={
                "rating": "not_helpful",
                "correction": correction_text
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["correction"] == correction_text
        assert data["rating"] == "not_helpful"

    def test_create_feedback_without_correction(self, client, test_event: Event):
        """Test creating feedback without correction (null) (AC6)"""
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={"rating": "not_helpful", "correction": None}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["correction"] is None

    def test_create_feedback_event_not_found(self, client):
        """Test creating feedback for non-existent event (AC12)"""
        fake_id = str(uuid.uuid4())
        response = client.post(
            f"/api/v1/events/{fake_id}/feedback",
            json={"rating": "helpful"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_feedback_duplicate(self, client, test_event: Event):
        """Test creating feedback when one already exists (returns 409)"""
        # Create initial feedback
        response1 = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={"rating": "helpful"}
        )
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={"rating": "not_helpful"}
        )
        assert response2.status_code == 409
        assert "already exists" in response2.json()["detail"].lower()

    def test_create_feedback_invalid_rating(self, client, test_event: Event):
        """Test creating feedback with invalid rating value"""
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={"rating": "invalid_rating"}
        )
        assert response.status_code == 422  # Validation error

    def test_create_feedback_correction_max_length(self, client, test_event: Event):
        """Test correction text max length validation (AC7)"""
        long_correction = "a" * 501  # Over 500 char limit
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={
                "rating": "not_helpful",
                "correction": long_correction
            }
        )
        assert response.status_code == 422  # Validation error

    def test_get_feedback(self, client, db_session, test_event: Event):
        """Test getting feedback for an event (AC10)"""
        # Create feedback directly
        feedback = EventFeedback(
            event_id=test_event.id,
            rating="helpful"
        )
        db_session.add(feedback)
        db_session.commit()

        response = client.get(f"/api/v1/events/{test_event.id}/feedback")
        assert response.status_code == 200
        data = response.json()
        assert data["event_id"] == test_event.id
        assert data["rating"] == "helpful"

    def test_get_feedback_not_found(self, client, test_event: Event):
        """Test getting feedback when none exists"""
        response = client.get(f"/api/v1/events/{test_event.id}/feedback")
        assert response.status_code == 404

    def test_get_feedback_event_not_found(self, client):
        """Test getting feedback for non-existent event"""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/events/{fake_id}/feedback")
        assert response.status_code == 404

    def test_update_feedback(self, client, db_session, test_event: Event):
        """Test updating existing feedback (AC11)"""
        # Create initial feedback
        feedback = EventFeedback(
            event_id=test_event.id,
            rating="helpful"
        )
        db_session.add(feedback)
        db_session.commit()

        # Update to not_helpful with correction
        response = client.put(
            f"/api/v1/events/{test_event.id}/feedback",
            json={
                "rating": "not_helpful",
                "correction": "Updated correction"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == "not_helpful"
        assert data["correction"] == "Updated correction"

    def test_update_feedback_partial(self, client, db_session, test_event: Event):
        """Test partial update of feedback (only rating)"""
        feedback = EventFeedback(
            event_id=test_event.id,
            rating="helpful",
            correction="Original correction"
        )
        db_session.add(feedback)
        db_session.commit()

        # Only update rating
        response = client.put(
            f"/api/v1/events/{test_event.id}/feedback",
            json={"rating": "not_helpful"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == "not_helpful"
        # Original correction should be preserved
        assert data["correction"] == "Original correction"

    def test_update_feedback_not_found(self, client, test_event: Event):
        """Test updating non-existent feedback"""
        response = client.put(
            f"/api/v1/events/{test_event.id}/feedback",
            json={"rating": "not_helpful"}
        )
        assert response.status_code == 404

    def test_delete_feedback(self, client, db_session, test_event: Event):
        """Test deleting feedback"""
        feedback = EventFeedback(
            event_id=test_event.id,
            rating="helpful"
        )
        db_session.add(feedback)
        db_session.commit()

        response = client.delete(f"/api/v1/events/{test_event.id}/feedback")
        assert response.status_code == 204

        # Verify deletion
        get_response = client.get(f"/api/v1/events/{test_event.id}/feedback")
        assert get_response.status_code == 404

    def test_delete_feedback_not_found(self, client, test_event: Event):
        """Test deleting non-existent feedback"""
        response = client.delete(f"/api/v1/events/{test_event.id}/feedback")
        assert response.status_code == 404

    def test_correction_at_max_length(self, client, test_event: Event):
        """Test correction text at exactly 500 characters (boundary)"""
        max_correction = "a" * 500  # Exactly at limit
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={
                "rating": "not_helpful",
                "correction": max_correction
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data["correction"]) == 500

    # Story P9-3.3: Tests for correction_type (Package False Positive Feedback)

    def test_create_feedback_with_correction_type_not_package(self, client, test_event: Event):
        """Test creating feedback with correction_type='not_package' (Story P9-3.3)"""
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={
                "rating": "not_helpful",
                "correction_type": "not_package"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["rating"] == "not_helpful"
        assert data["correction_type"] == "not_package"
        assert data["correction"] is None

    def test_create_feedback_with_correction_type_and_text(self, client, test_event: Event):
        """Test creating feedback with both correction_type and correction text (Story P9-3.3)"""
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={
                "rating": "not_helpful",
                "correction": "This is a shadow",
                "correction_type": "not_package"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["correction"] == "This is a shadow"
        assert data["correction_type"] == "not_package"

    def test_create_feedback_without_correction_type(self, client, test_event: Event):
        """Test that correction_type is null by default (Story P9-3.3)"""
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={"rating": "helpful"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data.get("correction_type") is None

    def test_create_feedback_invalid_correction_type(self, client, test_event: Event):
        """Test creating feedback with invalid correction_type (Story P9-3.3)"""
        response = client.post(
            f"/api/v1/events/{test_event.id}/feedback",
            json={
                "rating": "not_helpful",
                "correction_type": "invalid_type"
            }
        )
        assert response.status_code == 422  # Validation error

    def test_update_feedback_with_correction_type(self, client, db_session, test_event: Event):
        """Test updating feedback to add correction_type (Story P9-3.3)"""
        # Create initial feedback without correction_type
        feedback = EventFeedback(
            event_id=test_event.id,
            rating="helpful"
        )
        db_session.add(feedback)
        db_session.commit()

        # Update with correction_type
        response = client.put(
            f"/api/v1/events/{test_event.id}/feedback",
            json={
                "rating": "not_helpful",
                "correction_type": "not_package"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == "not_helpful"
        assert data["correction_type"] == "not_package"

    def test_get_feedback_with_correction_type(self, client, db_session, test_event: Event):
        """Test getting feedback returns correction_type (Story P9-3.3)"""
        # Create feedback with correction_type
        feedback = EventFeedback(
            event_id=test_event.id,
            rating="not_helpful",
            correction_type="not_package"
        )
        db_session.add(feedback)
        db_session.commit()

        response = client.get(f"/api/v1/events/{test_event.id}/feedback")
        assert response.status_code == 200
        data = response.json()
        assert data["correction_type"] == "not_package"


# ============================================================================
# Story P9-3.6: Tests for Summary Feedback Stats in AI Accuracy Stats
# ============================================================================


class TestSummaryFeedbackStats:
    """Test suite for summary feedback stats in /api/v1/feedback/stats endpoint (Story P9-3.6)"""

    def test_stats_without_summary_feedback(self, client, db_session, test_camera: Camera, test_event: Event):
        """Test that summary_feedback is null when no summary feedback exists (AC-3.6.4)"""
        # Create some event feedback but no summary feedback
        feedback = EventFeedback(
            event_id=test_event.id,
            camera_id=test_camera.id,
            rating="helpful"
        )
        db_session.add(feedback)
        db_session.commit()

        response = client.get("/api/v1/feedback/stats")
        assert response.status_code == 200
        data = response.json()

        # Event feedback should be present
        assert data["total_count"] == 1
        assert data["helpful_count"] == 1

        # Summary feedback should be null
        assert data["summary_feedback"] is None

    def test_stats_with_summary_feedback(self, client, db_session, test_camera: Camera):
        """Test that summary_feedback stats are calculated correctly (AC-3.6.2, AC-3.6.3)"""
        now = datetime.now(timezone.utc)

        # Create 3 positive and 2 negative summary feedback
        for i in range(3):
            summary = ActivitySummary(
                id=str(uuid.uuid4()),
                summary_text=f"Test summary pos {i}",
                period_start=now,
                period_end=now,
                event_count=10
            )
            db_session.add(summary)
            db_session.commit()
            db_session.refresh(summary)

            sf = SummaryFeedback(
                id=str(uuid.uuid4()),
                summary_id=summary.id,
                rating="positive"
            )
            db_session.add(sf)

        for i in range(2):
            summary = ActivitySummary(
                id=str(uuid.uuid4()),
                summary_text=f"Test summary neg {i}",
                period_start=now,
                period_end=now,
                event_count=10
            )
            db_session.add(summary)
            db_session.commit()
            db_session.refresh(summary)

            sf = SummaryFeedback(
                id=str(uuid.uuid4()),
                summary_id=summary.id,
                rating="negative"
            )
            db_session.add(sf)

        db_session.commit()

        response = client.get("/api/v1/feedback/stats")
        assert response.status_code == 200
        data = response.json()

        # Summary feedback should be present
        assert data["summary_feedback"] is not None
        summary_stats = data["summary_feedback"]

        assert summary_stats["total_count"] == 5
        assert summary_stats["positive_count"] == 3
        assert summary_stats["negative_count"] == 2
        assert summary_stats["accuracy_rate"] == 60.0  # 3/5 * 100

    def test_stats_summary_feedback_100_percent_accuracy(self, client, db_session):
        """Test summary_feedback accuracy when all positive (AC-3.6.3)"""
        now = datetime.now(timezone.utc)

        # Create a summary and positive feedback
        summary = ActivitySummary(
            id=str(uuid.uuid4()),
            summary_text="Test summary",
            period_start=now,
            period_end=now,
            event_count=5
        )
        db_session.add(summary)
        db_session.commit()
        db_session.refresh(summary)

        sf = SummaryFeedback(
            id=str(uuid.uuid4()),
            summary_id=summary.id,
            rating="positive"
        )
        db_session.add(sf)
        db_session.commit()

        response = client.get("/api/v1/feedback/stats")
        assert response.status_code == 200
        data = response.json()

        assert data["summary_feedback"] is not None
        assert data["summary_feedback"]["accuracy_rate"] == 100.0
        assert data["summary_feedback"]["positive_count"] == 1
        assert data["summary_feedback"]["negative_count"] == 0

    def test_stats_summary_feedback_0_percent_accuracy(self, client, db_session):
        """Test summary_feedback accuracy when all negative (AC-3.6.3)"""
        now = datetime.now(timezone.utc)

        # Create a summary and negative feedback
        summary = ActivitySummary(
            id=str(uuid.uuid4()),
            summary_text="Test summary",
            period_start=now,
            period_end=now,
            event_count=5
        )
        db_session.add(summary)
        db_session.commit()
        db_session.refresh(summary)

        sf = SummaryFeedback(
            id=str(uuid.uuid4()),
            summary_id=summary.id,
            rating="negative"
        )
        db_session.add(sf)
        db_session.commit()

        response = client.get("/api/v1/feedback/stats")
        assert response.status_code == 200
        data = response.json()

        assert data["summary_feedback"] is not None
        assert data["summary_feedback"]["accuracy_rate"] == 0.0
        assert data["summary_feedback"]["positive_count"] == 0
        assert data["summary_feedback"]["negative_count"] == 1
