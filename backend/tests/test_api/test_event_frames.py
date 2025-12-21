"""
Tests for Event Frames API endpoints (Story P8-2.2)

Tests the frame gallery endpoints:
- GET /api/v1/events/{event_id}/frames - List frames for an event
- GET /api/v1/events/{event_id}/frames/{frame_number} - Get frame image
"""

import pytest
import os
import tempfile
import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.models.event import Event
from app.models.event_frame import EventFrame
from app.core.database import Base, get_db


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
    """Set up database at module level and clean up after all tests"""
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Apply override for all tests in this module
    app.dependency_overrides[get_db] = _override_get_db
    yield
    # Drop tables after all tests in module complete
    Base.metadata.drop_all(bind=engine)
    # Clean up temp file
    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)


# Create test client (module-level)
client = TestClient(app)


@pytest.fixture(scope="function")
def sample_event():
    """Create a sample event for testing"""
    import uuid

    db = TestingSessionLocal()
    try:
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            description="Test event for frame testing",
            confidence=85,
            objects_detected=json.dumps(["person"]),
            source_type="protect",
            analysis_mode="multi_frame",
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        yield event

        # Cleanup
        db.query(EventFrame).filter(EventFrame.event_id == event.id).delete()
        db.query(Event).filter(Event.id == event.id).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="function")
def sample_frames(sample_event):
    """Create sample frames for testing"""
    import uuid

    db = TestingSessionLocal()
    try:
        frames = []
        for i in range(1, 4):  # Create 3 frames
            frame_path = f"frames/{sample_event.id}/frame_{i:03d}.jpg"

            frame = EventFrame(
                id=str(uuid.uuid4()),
                event_id=sample_event.id,
                frame_number=i,
                frame_path=frame_path,
                timestamp_offset_ms=i * 500,  # 0.5s intervals
                width=1920,
                height=1080,
                file_size_bytes=50000,
            )
            db.add(frame)
            frames.append(frame)

        db.commit()
        yield frames
    finally:
        db.close()


class TestGetEventFrames:
    """Tests for GET /api/v1/events/{event_id}/frames"""

    def test_get_frames_success(self, sample_event, sample_frames):
        """Test successful frame list retrieval"""
        response = client.get(f"/api/v1/events/{sample_event.id}/frames")

        assert response.status_code == 200
        data = response.json()

        assert data["event_id"] == sample_event.id
        assert data["total_count"] == 3
        assert len(data["frames"]) == 3
        assert data["total_size_bytes"] == 150000  # 3 * 50000

        # Check frame ordering and structure
        for i, frame in enumerate(data["frames"]):
            assert frame["frame_number"] == i + 1
            assert frame["event_id"] == sample_event.id
            assert "url" in frame
            assert frame["url"] == f"/api/v1/events/{sample_event.id}/frames/{i + 1}"
            assert frame["timestamp_offset_ms"] == (i + 1) * 500
            assert frame["width"] == 1920
            assert frame["height"] == 1080

    def test_get_frames_event_not_found(self):
        """Test 404 when event doesn't exist"""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(f"/api/v1/events/{fake_id}/frames")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_frames_empty(self, sample_event):
        """Test empty frames list for event without frames"""
        response = client.get(f"/api/v1/events/{sample_event.id}/frames")

        assert response.status_code == 200
        data = response.json()

        assert data["event_id"] == sample_event.id
        assert data["total_count"] == 0
        assert len(data["frames"]) == 0
        assert data["total_size_bytes"] == 0


class TestGetEventFrameImage:
    """Tests for GET /api/v1/events/{event_id}/frames/{frame_number}"""

    def test_get_frame_image_event_not_found(self):
        """Test 404 when event doesn't exist"""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(f"/api/v1/events/{fake_id}/frames/1")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_frame_image_frame_not_found(self, sample_event):
        """Test 404 when frame number doesn't exist"""
        response = client.get(f"/api/v1/events/{sample_event.id}/frames/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_frame_image_file_missing(self, sample_event, sample_frames):
        """Test 404 when frame file is missing from disk"""
        # Frame record exists but file doesn't
        response = client.get(f"/api/v1/events/{sample_event.id}/frames/1")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestFrameResponseFormat:
    """Tests for frame response format and fields"""

    def test_frame_response_includes_all_fields(self, sample_event, sample_frames):
        """Test that frame response includes all required fields"""
        response = client.get(f"/api/v1/events/{sample_event.id}/frames")

        assert response.status_code == 200
        frame = response.json()["frames"][0]

        # Required fields per EventFrameResponse schema
        assert "id" in frame
        assert "event_id" in frame
        assert "frame_number" in frame
        assert "frame_path" in frame
        assert "timestamp_offset_ms" in frame
        assert "width" in frame
        assert "height" in frame
        assert "file_size_bytes" in frame
        assert "created_at" in frame
        assert "url" in frame

    def test_frames_ordered_by_frame_number(self, sample_event, sample_frames):
        """Test that frames are returned in correct order"""
        response = client.get(f"/api/v1/events/{sample_event.id}/frames")

        assert response.status_code == 200
        frame_numbers = [f["frame_number"] for f in response.json()["frames"]]

        assert frame_numbers == [1, 2, 3]

    def test_frame_url_format(self, sample_event, sample_frames):
        """Test that frame URLs follow expected format"""
        response = client.get(f"/api/v1/events/{sample_event.id}/frames")

        assert response.status_code == 200
        for frame in response.json()["frames"]:
            expected_url = f"/api/v1/events/{sample_event.id}/frames/{frame['frame_number']}"
            assert frame["url"] == expected_url
