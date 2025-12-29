"""Tests for camera audio settings API endpoints (Story P6-3.3)

These tests verify the per-camera audio settings functionality:
- audio_event_types: JSON array of event types to detect
- audio_threshold: Per-camera confidence threshold override
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.database import Base, get_db
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
    """Set up database at module level and clean up after all tests"""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    db = TestingSessionLocal()
    try:
        db.query(Camera).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = TestingSessionLocal()
    try:
        db.query(Camera).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def sample_rtsp_camera():
    """Sample RTSP camera data for testing."""
    return {
        "name": "Test Camera",
        "type": "rtsp",
        "rtsp_url": "rtsp://192.168.1.50:554/stream1",
        "frame_rate": 5,
        "is_enabled": True,
        "motion_enabled": True,
        "motion_sensitivity": "medium",
        "motion_cooldown": 30,
        "motion_algorithm": "mog2",
    }


@patch('app.services.camera_service.cv2.VideoCapture')
def test_create_camera_with_audio_settings(mock_videocapture, sample_rtsp_camera):
    """Test creating a camera with audio settings (AC#1, AC#2, AC#3)."""
    camera_data = {
        **sample_rtsp_camera,
        "audio_enabled": True,
        "audio_event_types": ["glass_break", "doorbell"],
        "audio_threshold": 0.85,
    }

    response = client.post("/api/v1/cameras", json=camera_data)
    assert response.status_code == 201

    data = response.json()
    assert data["audio_enabled"] is True
    assert data["audio_event_types"] == ["glass_break", "doorbell"]
    assert data["audio_threshold"] == 0.85


@patch('app.services.camera_service.cv2.VideoCapture')
def test_create_camera_with_no_audio_settings(mock_videocapture, sample_rtsp_camera):
    """Test creating a camera without audio settings uses defaults."""
    response = client.post("/api/v1/cameras", json=sample_rtsp_camera)
    assert response.status_code == 201

    data = response.json()
    assert data["audio_enabled"] is False
    assert data["audio_event_types"] is None
    assert data["audio_threshold"] is None


@patch('app.services.camera_service.cv2.VideoCapture')
def test_update_camera_audio_settings(mock_videocapture, sample_rtsp_camera):
    """Test updating camera audio settings (AC#1, AC#2, AC#3)."""
    # Create camera first
    create_response = client.post("/api/v1/cameras", json=sample_rtsp_camera)
    camera_id = create_response.json()["id"]

    # Update with audio settings
    update_data = {
        "audio_enabled": True,
        "audio_event_types": ["gunshot", "scream"],
        "audio_threshold": 0.75,
    }

    response = client.put(f"/api/v1/cameras/{camera_id}", json=update_data)
    assert response.status_code == 200

    data = response.json()
    assert data["audio_enabled"] is True
    assert data["audio_event_types"] == ["gunshot", "scream"]
    assert data["audio_threshold"] == 0.75


@patch('app.services.camera_service.cv2.VideoCapture')
def test_get_camera_returns_audio_settings(mock_videocapture, sample_rtsp_camera):
    """Test GET camera includes audio settings in response (AC#1, AC#2, AC#3)."""
    # Create camera with audio settings
    camera_data = {
        **sample_rtsp_camera,
        "audio_enabled": True,
        "audio_event_types": ["glass_break"],
        "audio_threshold": 0.90,
    }

    create_response = client.post("/api/v1/cameras", json=camera_data)
    assert create_response.status_code == 201
    camera_id = create_response.json()["id"]

    # Get camera and verify audio settings
    response = client.get(f"/api/v1/cameras/{camera_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["audio_enabled"] is True
    assert data["audio_event_types"] == ["glass_break"]
    assert data["audio_threshold"] == 0.90


@patch('app.services.camera_service.cv2.VideoCapture')
def test_list_cameras_returns_audio_settings(mock_videocapture, sample_rtsp_camera):
    """Test list cameras includes audio settings in each camera."""
    # Create camera with audio settings
    camera_data = {
        **sample_rtsp_camera,
        "audio_enabled": True,
        "audio_event_types": ["doorbell"],
        "audio_threshold": 0.80,
    }

    create_resp = client.post("/api/v1/cameras", json=camera_data)
    assert create_resp.status_code == 201

    # List cameras
    response = client.get("/api/v1/cameras")
    assert response.status_code == 200

    cameras = response.json()
    assert len(cameras) >= 1

    # Find our camera
    audio_camera = next(
        (c for c in cameras if c.get("audio_event_types") == ["doorbell"]),
        None
    )
    assert audio_camera is not None
    assert audio_camera["audio_enabled"] is True
    assert audio_camera["audio_threshold"] == 0.80


@patch('app.services.camera_service.cv2.VideoCapture')
def test_update_camera_clear_audio_settings(mock_videocapture, sample_rtsp_camera):
    """Test clearing audio settings by setting to null."""
    # Create camera with audio settings
    camera_data = {
        **sample_rtsp_camera,
        "audio_enabled": True,
        "audio_event_types": ["glass_break", "gunshot"],
        "audio_threshold": 0.85,
    }

    create_response = client.post("/api/v1/cameras", json=camera_data)
    camera_id = create_response.json()["id"]

    # Clear audio settings
    update_data = {
        "audio_enabled": False,
        "audio_event_types": None,
        "audio_threshold": None,
    }

    response = client.put(f"/api/v1/cameras/{camera_id}", json=update_data)
    assert response.status_code == 200

    data = response.json()
    assert data["audio_enabled"] is False
    assert data["audio_event_types"] is None
    assert data["audio_threshold"] is None


@patch('app.services.camera_service.cv2.VideoCapture')
def test_audio_threshold_validation(mock_videocapture, sample_rtsp_camera):
    """Test audio_threshold must be between 0.0 and 1.0."""
    # Test threshold > 1.0 should fail
    camera_data = {
        **sample_rtsp_camera,
        "audio_threshold": 1.5,
    }

    response = client.post("/api/v1/cameras", json=camera_data)
    # Either 422 validation error or 400 bad request is acceptable
    assert response.status_code in (400, 422)

    # Test threshold < 0.0 should fail
    camera_data["audio_threshold"] = -0.1
    response = client.post("/api/v1/cameras", json=camera_data)
    assert response.status_code in (400, 422)


@patch('app.services.camera_service.cv2.VideoCapture')
def test_audio_event_types_as_string_json(mock_videocapture, sample_rtsp_camera):
    """Test that audio_event_types accepts JSON string format."""
    # Create camera first
    create_response = client.post("/api/v1/cameras", json=sample_rtsp_camera)
    camera_id = create_response.json()["id"]

    # Update with audio_event_types as JSON string
    update_data = {
        "audio_event_types": json.dumps(["glass_break", "scream"]),
    }

    response = client.put(f"/api/v1/cameras/{camera_id}", json=update_data)
    assert response.status_code == 200

    data = response.json()
    assert data["audio_event_types"] == ["glass_break", "scream"]


@patch('app.services.camera_service.cv2.VideoCapture')
def test_partial_update_preserves_audio_settings(mock_videocapture, sample_rtsp_camera):
    """Test that partial updates preserve existing audio settings."""
    # Create camera with audio settings
    camera_data = {
        **sample_rtsp_camera,
        "audio_enabled": True,
        "audio_event_types": ["glass_break"],
        "audio_threshold": 0.80,
    }

    create_response = client.post("/api/v1/cameras", json=camera_data)
    assert create_response.status_code == 201
    camera_id = create_response.json()["id"]

    # Update only the name (not audio settings)
    update_data = {"name": "Updated Camera Name"}
    response = client.put(f"/api/v1/cameras/{camera_id}", json=update_data)
    assert response.status_code == 200

    data = response.json()
    # Audio settings should be preserved
    assert data["audio_enabled"] is True
    assert data["audio_event_types"] == ["glass_break"]
    assert data["audio_threshold"] == 0.80
    # Name should be updated
    assert data["name"] == "Updated Camera Name"
