"""
Tests for Summary Feedback API endpoints (Story P9-3.4)
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
from app.models.activity_summary import ActivitySummary
from app.models.summary_feedback import SummaryFeedback


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
def test_summary(db_session) -> ActivitySummary:
    """Create a test summary"""
    summary = ActivitySummary(
        id=str(uuid.uuid4()),
        summary_text="Test summary for today's activity",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        event_count=10,
        generated_at=datetime.now(timezone.utc),
        ai_cost=0.01,
        provider_used="openai",
        input_tokens=100,
        output_tokens=50,
        digest_type="daily"
    )
    db_session.add(summary)
    db_session.commit()
    db_session.refresh(summary)
    return summary


class TestSummaryFeedbackEndpoints:
    """Test suite for summary feedback API endpoints (Story P9-3.4)"""

    def test_create_feedback_positive(self, client, test_summary: ActivitySummary):
        """Test creating feedback with positive rating (AC-3.4.2)"""
        response = client.post(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={"rating": "positive"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["summary_id"] == test_summary.id
        assert data["rating"] == "positive"
        assert data["correction_text"] is None
        assert "id" in data
        assert "created_at" in data

    def test_create_feedback_negative(self, client, test_summary: ActivitySummary):
        """Test creating feedback with negative rating (AC-3.4.4)"""
        response = client.post(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={"rating": "negative"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["rating"] == "negative"

    def test_create_feedback_with_correction_text(self, client, test_summary: ActivitySummary):
        """Test creating feedback with correction text (AC-3.4.5)"""
        correction = "Summary missed the morning package delivery"
        response = client.post(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={
                "rating": "negative",
                "correction_text": correction
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["correction_text"] == correction
        assert data["rating"] == "negative"

    def test_create_feedback_summary_not_found(self, client):
        """Test creating feedback for non-existent summary"""
        fake_id = str(uuid.uuid4())
        response = client.post(
            f"/api/v1/summaries/{fake_id}/feedback",
            json={"rating": "positive"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_feedback_duplicate(self, client, test_summary: ActivitySummary):
        """Test creating feedback when one already exists (returns 409)"""
        # Create initial feedback
        response1 = client.post(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={"rating": "positive"}
        )
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = client.post(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={"rating": "negative"}
        )
        assert response2.status_code == 409
        assert "already exists" in response2.json()["detail"].lower()

    def test_create_feedback_invalid_rating(self, client, test_summary: ActivitySummary):
        """Test creating feedback with invalid rating value"""
        response = client.post(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={"rating": "invalid_rating"}
        )
        assert response.status_code == 422  # Validation error

    def test_create_feedback_correction_max_length(self, client, test_summary: ActivitySummary):
        """Test correction text max length validation"""
        long_correction = "a" * 501  # Over 500 char limit
        response = client.post(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={
                "rating": "negative",
                "correction_text": long_correction
            }
        )
        assert response.status_code == 422  # Validation error

    def test_get_feedback(self, client, db_session, test_summary: ActivitySummary):
        """Test getting feedback for a summary (AC-3.4.3)"""
        # Create feedback directly
        feedback = SummaryFeedback(
            summary_id=test_summary.id,
            rating="positive"
        )
        db_session.add(feedback)
        db_session.commit()

        response = client.get(f"/api/v1/summaries/{test_summary.id}/feedback")
        assert response.status_code == 200
        data = response.json()
        assert data["summary_id"] == test_summary.id
        assert data["rating"] == "positive"

    def test_get_feedback_not_found(self, client, test_summary: ActivitySummary):
        """Test getting feedback when none exists"""
        response = client.get(f"/api/v1/summaries/{test_summary.id}/feedback")
        assert response.status_code == 404

    def test_get_feedback_summary_not_found(self, client):
        """Test getting feedback for non-existent summary"""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/summaries/{fake_id}/feedback")
        assert response.status_code == 404

    def test_update_feedback(self, client, db_session, test_summary: ActivitySummary):
        """Test updating existing feedback"""
        # Create initial feedback
        feedback = SummaryFeedback(
            summary_id=test_summary.id,
            rating="positive"
        )
        db_session.add(feedback)
        db_session.commit()

        # Update to negative with correction
        response = client.put(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={
                "rating": "negative",
                "correction_text": "Updated correction"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == "negative"
        assert data["correction_text"] == "Updated correction"

    def test_update_feedback_partial(self, client, db_session, test_summary: ActivitySummary):
        """Test partial update of feedback (only rating)"""
        feedback = SummaryFeedback(
            summary_id=test_summary.id,
            rating="positive",
            correction_text="Original correction"
        )
        db_session.add(feedback)
        db_session.commit()

        # Only update rating
        response = client.put(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={"rating": "negative"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == "negative"
        # Original correction should be preserved
        assert data["correction_text"] == "Original correction"

    def test_update_feedback_not_found(self, client, test_summary: ActivitySummary):
        """Test updating non-existent feedback"""
        response = client.put(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={"rating": "negative"}
        )
        assert response.status_code == 404

    def test_delete_feedback(self, client, db_session, test_summary: ActivitySummary):
        """Test deleting feedback"""
        feedback = SummaryFeedback(
            summary_id=test_summary.id,
            rating="positive"
        )
        db_session.add(feedback)
        db_session.commit()

        response = client.delete(f"/api/v1/summaries/{test_summary.id}/feedback")
        assert response.status_code == 204

        # Verify deletion
        get_response = client.get(f"/api/v1/summaries/{test_summary.id}/feedback")
        assert get_response.status_code == 404

    def test_delete_feedback_not_found(self, client, test_summary: ActivitySummary):
        """Test deleting non-existent feedback"""
        response = client.delete(f"/api/v1/summaries/{test_summary.id}/feedback")
        assert response.status_code == 404

    def test_correction_at_max_length(self, client, test_summary: ActivitySummary):
        """Test correction text at exactly 500 characters (boundary)"""
        max_correction = "a" * 500  # Exactly at limit
        response = client.post(
            f"/api/v1/summaries/{test_summary.id}/feedback",
            json={
                "rating": "negative",
                "correction_text": max_correction
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data["correction_text"]) == 500
