"""Integration tests for camera API endpoints"""
import pytest
import json
import tempfile
import os
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
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
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Apply override for all tests in this module
    app.dependency_overrides[get_db] = _override_get_db
    yield
    # Drop tables after all tests in module complete
    Base.metadata.drop_all(bind=engine)


# Create test client (module-level)
client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    # Clean up before the test to ensure isolation
    db = TestingSessionLocal()
    try:
        db.query(Camera).delete()
        db.commit()
    finally:
        db.close()
    yield
    # Clean up after each test
    db = TestingSessionLocal()
    try:
        db.query(Camera).delete()
        db.commit()
    finally:
        db.close()


class TestCameraAPI:
    """Test suite for camera CRUD API endpoints"""

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_create_camera_rtsp(self, mock_videocapture):
        """POST /cameras should create RTSP camera"""
        # Mock camera service to prevent actual camera connection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_videocapture.return_value = mock_cap

        camera_data = {
            "name": "Test Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://192.168.1.50:554/stream1",
            "username": "admin",
            "password": "secret123",
            "frame_rate": 5,
            "is_enabled": False  # Disable to avoid starting thread in test
        }

        response = client.post("/api/v1/cameras", json=camera_data)

        assert response.status_code == 201
        data = response.json()

        assert data["name"] == "Test Camera"
        assert data["type"] == "rtsp"
        assert data["rtsp_url"] == "rtsp://192.168.1.50:554/stream1"
        assert data["username"] == "admin"
        assert "password" not in data  # Password should not be returned
        assert data["frame_rate"] == 5
        assert data["is_enabled"] is False
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_camera_usb(self):
        """POST /cameras should create USB camera"""
        camera_data = {
            "name": "Webcam",
            "type": "usb",
            "device_index": 0,
            "frame_rate": 15,
            "is_enabled": False
        }

        response = client.post("/api/v1/cameras", json=camera_data)

        assert response.status_code == 201
        data = response.json()

        assert data["name"] == "Webcam"
        assert data["type"] == "usb"
        assert data["device_index"] == 0
        assert data["frame_rate"] == 15

    def test_create_camera_duplicate_name(self):
        """POST /cameras with duplicate name should return 409"""
        camera_data = {
            "name": "Duplicate Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "is_enabled": False
        }

        # Create first camera
        response1 = client.post("/api/v1/cameras", json=camera_data)
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = client.post("/api/v1/cameras", json=camera_data)
        assert response2.status_code == 409
        assert "already exists" in response2.json()["detail"]

    def test_create_camera_invalid_rtsp_url(self):
        """POST /cameras with invalid RTSP URL should return 422"""
        camera_data = {
            "name": "Invalid Camera",
            "type": "rtsp",
            "rtsp_url": "http://example.com/stream",  # Should be rtsp://
            "is_enabled": False
        }

        response = client.post("/api/v1/cameras", json=camera_data)
        assert response.status_code == 422

    def test_create_camera_missing_rtsp_url(self):
        """POST /cameras for RTSP without URL should return 422"""
        camera_data = {
            "name": "Missing URL Camera",
            "type": "rtsp",
            "is_enabled": False
        }

        response = client.post("/api/v1/cameras", json=camera_data)
        assert response.status_code == 422

    def test_create_camera_missing_device_index(self):
        """POST /cameras for USB without device_index should return 422"""
        camera_data = {
            "name": "Missing Index Camera",
            "type": "usb",
            "is_enabled": False
        }

        response = client.post("/api/v1/cameras", json=camera_data)
        assert response.status_code == 422

    def test_list_cameras_empty(self):
        """GET /cameras should return empty list when no cameras"""
        response = client.get("/api/v1/cameras")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_cameras(self):
        """GET /cameras should return all cameras"""
        # Create test cameras
        camera1_data = {
            "name": "Camera 1",
            "type": "rtsp",
            "rtsp_url": "rtsp://example1.com/stream",
            "is_enabled": False
        }
        camera2_data = {
            "name": "Camera 2",
            "type": "usb",
            "device_index": 0,
            "is_enabled": False
        }

        client.post("/api/v1/cameras", json=camera1_data)
        client.post("/api/v1/cameras", json=camera2_data)

        # List cameras
        response = client.get("/api/v1/cameras")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Camera 1"
        assert data[1]["name"] == "Camera 2"

    def test_list_cameras_filter_by_enabled(self):
        """GET /cameras with is_enabled filter should work"""
        # Create cameras with different enabled status
        client.post("/api/v1/cameras", json={
            "name": "Enabled Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "is_enabled": True
        })
        client.post("/api/v1/cameras", json={
            "name": "Disabled Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example2.com/stream",
            "is_enabled": False
        })

        # Filter by enabled=True
        response = client.get("/api/v1/cameras?is_enabled=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Enabled Camera"

    def test_get_camera_by_id(self):
        """GET /cameras/{id} should return camera details"""
        # Create camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Test Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Get camera
        response = client.get(f"/api/v1/cameras/{camera_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == camera_id
        assert data["name"] == "Test Camera"

    def test_get_camera_not_found(self):
        """GET /cameras/{id} for non-existent camera should return 404"""
        # Use a valid UUID format that doesn't exist in the database
        response = client.get("/api/v1/cameras/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_get_camera_invalid_uuid(self):
        """GET /cameras/{id} with invalid UUID should return 422"""
        response = client.get("/api/v1/cameras/non-existent-id")

        assert response.status_code == 422

    def test_update_camera(self):
        """PUT /cameras/{id} should update camera"""
        # Create camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Original Name",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "frame_rate": 5,
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Update camera
        update_data = {
            "name": "Updated Name",
            "frame_rate": 10
        }
        response = client.put(f"/api/v1/cameras/{camera_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["frame_rate"] == 10

    def test_update_camera_not_found(self):
        """PUT /cameras/{id} for non-existent camera should return 404"""
        # Use a valid UUID format that doesn't exist in the database
        response = client.put("/api/v1/cameras/00000000-0000-0000-0000-000000000000", json={"name": "Test"})

        assert response.status_code == 404

    def test_update_camera_invalid_uuid(self):
        """PUT /cameras/{id} with invalid UUID should return 422"""
        response = client.put("/api/v1/cameras/non-existent-id", json={"name": "Test"})

        assert response.status_code == 422

    def test_delete_camera(self):
        """DELETE /cameras/{id} should delete camera"""
        # Create camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Camera to Delete",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Delete camera
        response = client.delete(f"/api/v1/cameras/{camera_id}")

        assert response.status_code == 204  # 204 No Content is proper RESTful behavior for DELETE

        # Verify deleted
        get_response = client.get(f"/api/v1/cameras/{camera_id}")
        assert get_response.status_code == 404

    def test_delete_camera_not_found(self):
        """DELETE /cameras/{id} for non-existent camera should return 404"""
        # Use a valid UUID format that doesn't exist in the database
        response = client.delete("/api/v1/cameras/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 404

    def test_delete_camera_invalid_uuid(self):
        """DELETE /cameras/{id} with invalid UUID should return 422"""
        response = client.delete("/api/v1/cameras/non-existent-id")

        assert response.status_code == 422

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_test_camera_connection_success(self, mock_videocapture):
        """POST /cameras/{id}/test should test connection and return thumbnail"""
        # Create camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Test Connection Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "username": "admin",
            "password": "password",
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Mock successful connection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        # Create fake frame (numpy array)
        import numpy as np
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        mock_videocapture.return_value = mock_cap

        # Test connection
        response = client.post(f"/api/v1/cameras/{camera_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "successful" in data["message"].lower()
        assert data["thumbnail"] is not None
        assert data["thumbnail"].startswith("data:image/jpeg;base64,")

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_test_camera_connection_failure(self, mock_videocapture):
        """POST /cameras/{id}/test should handle connection failure"""
        # Create camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Failed Connection Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Mock failed connection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        # Test connection
        response = client.post(f"/api/v1/cameras/{camera_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "failed" in data["message"].lower() or "check" in data["message"].lower()

    def test_test_camera_connection_not_found(self):
        """POST /cameras/{id}/test for non-existent camera should return 404"""
        # Use a valid UUID format that doesn't exist in the database
        response = client.post("/api/v1/cameras/00000000-0000-0000-0000-000000000000/test")

        assert response.status_code == 404

    def test_test_camera_connection_invalid_uuid(self):
        """POST /cameras/{id}/test with invalid UUID should return 422"""
        response = client.post("/api/v1/cameras/non-existent-id/test")

        assert response.status_code == 422

    # USB-Specific Test Connection Tests (Story F1.3)

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_test_usb_camera_connection_success(self, mock_videocapture):
        """POST /cameras/{id}/test should work for USB cameras"""
        # Create USB camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Test USB Camera",
            "type": "usb",
            "device_index": 0,
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Mock successful USB connection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        import numpy as np
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        mock_videocapture.return_value = mock_cap

        # Test connection
        response = client.post(f"/api/v1/cameras/{camera_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "usb camera connected successfully" in data["message"].lower()
        assert "device 0" in data["message"].lower()
        assert data["thumbnail"] is not None

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_test_usb_camera_not_found(self, mock_videocapture):
        """POST /cameras/{id}/test should return device not found for USB cameras"""
        # Create USB camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Missing USB Camera",
            "type": "usb",
            "device_index": 99,  # Unlikely to exist
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Mock device not found
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        # Test connection
        response = client.post(f"/api/v1/cameras/{camera_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "usb camera not found" in data["message"].lower()
        assert "device index 99" in data["message"].lower()

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_test_usb_camera_permission_denied(self, mock_videocapture):
        """POST /cameras/{id}/test should handle permission errors for USB cameras"""
        # Create USB camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Permission Denied USB Camera",
            "type": "usb",
            "device_index": 0,
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Mock permission denied error
        mock_videocapture.side_effect = Exception("Permission denied")

        # Test connection
        response = client.post(f"/api/v1/cameras/{camera_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "permission denied" in data["message"].lower()
        assert "video" in data["message"].lower()  # Should mention video group

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_test_usb_camera_already_in_use(self, mock_videocapture):
        """POST /cameras/{id}/test should handle device busy errors for USB cameras"""
        # Create USB camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Busy USB Camera",
            "type": "usb",
            "device_index": 0,
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Mock device busy error
        mock_videocapture.side_effect = Exception("Device is busy or in use")

        # Test connection
        response = client.post(f"/api/v1/cameras/{camera_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "in use" in data["message"].lower()
        assert "another application" in data["message"].lower()


# ==================== Pre-Save Connection Test Tests (Story P6-1.1) ====================


class TestCameraPreSaveTestAPI:
    """Test suite for pre-save camera connection test endpoint (Story P6-1.1)"""

    def test_presave_test_invalid_rtsp_url_missing_protocol(self):
        """POST /cameras/test with invalid RTSP URL should return 422 (AC-2)"""
        test_data = {
            "type": "rtsp",
            "rtsp_url": "192.168.1.50:554/stream1"  # Missing protocol
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 422

    def test_presave_test_invalid_rtsp_url_wrong_protocol(self):
        """POST /cameras/test with HTTP URL should return 422 (AC-2)"""
        test_data = {
            "type": "rtsp",
            "rtsp_url": "http://192.168.1.50/stream1"  # Wrong protocol
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 422

    def test_presave_test_missing_rtsp_url(self):
        """POST /cameras/test for RTSP without URL should return 422 (AC-2)"""
        test_data = {
            "type": "rtsp"
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 422

    def test_presave_test_missing_usb_device_index(self):
        """POST /cameras/test for USB without device_index should return 422 (AC-2)"""
        test_data = {
            "type": "usb"
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 422

    def test_presave_test_negative_device_index(self):
        """POST /cameras/test with negative device_index should return 422 (AC-2)"""
        test_data = {
            "type": "usb",
            "device_index": -1
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 422

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_presave_test_rtsp_success(self, mock_videocapture):
        """POST /cameras/test with valid RTSP config should return success with stream info (AC-1,3,4,6)"""
        import cv2 as cv2_module
        # Mock successful connection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2_module.CAP_PROP_FRAME_WIDTH: 1920,
            cv2_module.CAP_PROP_FRAME_HEIGHT: 1080,
            cv2_module.CAP_PROP_FPS: 30.0,
            cv2_module.CAP_PROP_FOURCC: cv2_module.VideoWriter_fourcc('H', '2', '6', '4')
        }.get(prop, 0)

        # Create fake frame
        import numpy as np
        fake_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        mock_videocapture.return_value = mock_cap

        test_data = {
            "type": "rtsp",
            "rtsp_url": "rtsp://192.168.1.50:554/stream1",
            "username": "admin",
            "password": "password123"
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "successful" in data["message"].lower()
        assert data["thumbnail"] is not None
        assert data["thumbnail"].startswith("data:image/jpeg;base64,")
        assert data["resolution"] == "1920x1080"
        assert data["fps"] == 30.0
        assert data["codec"] is not None

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_presave_test_usb_success(self, mock_videocapture):
        """POST /cameras/test with valid USB config should return success (AC-1,3,4,6)"""
        import cv2 as cv2_module
        # Mock successful connection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2_module.CAP_PROP_FRAME_WIDTH: 640,
            cv2_module.CAP_PROP_FRAME_HEIGHT: 480,
            cv2_module.CAP_PROP_FPS: 15.0,
            cv2_module.CAP_PROP_FOURCC: cv2_module.VideoWriter_fourcc('M', 'J', 'P', 'G')
        }.get(prop, 0)

        # Create fake frame
        import numpy as np
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        mock_videocapture.return_value = mock_cap

        test_data = {
            "type": "usb",
            "device_index": 0
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "usb camera connected successfully" in data["message"].lower()
        assert "device 0" in data["message"].lower()
        assert data["thumbnail"] is not None
        assert data["resolution"] == "640x480"
        assert data["fps"] == 15.0

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_presave_test_connection_failure(self, mock_videocapture):
        """POST /cameras/test with connection failure should return diagnostic message (AC-3,5)"""
        # Mock failed connection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        test_data = {
            "type": "rtsp",
            "rtsp_url": "rtsp://192.168.1.50:554/stream1"
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "failed" in data["message"].lower() or "check" in data["message"].lower()
        assert data["thumbnail"] is None

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_presave_test_usb_not_found(self, mock_videocapture):
        """POST /cameras/test with USB not found should return device not found message (AC-5)"""
        # Mock device not found
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        test_data = {
            "type": "usb",
            "device_index": 99
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "usb camera not found" in data["message"].lower()
        assert "device index 99" in data["message"].lower()

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_presave_test_auth_failure(self, mock_videocapture):
        """POST /cameras/test with auth failure should return authentication message (AC-5)"""
        # Mock authentication error
        mock_videocapture.side_effect = Exception("401 Unauthorized")

        test_data = {
            "type": "rtsp",
            "rtsp_url": "rtsp://192.168.1.50:554/stream1",
            "username": "admin",
            "password": "wrongpassword"
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "authentication failed" in data["message"].lower()

    @patch('app.api.v1.cameras.cv2.VideoCapture')
    def test_presave_test_timeout(self, mock_videocapture):
        """POST /cameras/test with timeout should return timeout message (AC-5)"""
        # Mock timeout error
        mock_videocapture.side_effect = Exception("Connection timed out")

        test_data = {
            "type": "rtsp",
            "rtsp_url": "rtsp://192.168.1.50:554/stream1"
        }

        response = client.post("/api/v1/cameras/test", json=test_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "timeout" in data["message"].lower()

    def test_presave_test_no_database_record_created(self):
        """POST /cameras/test should NOT create any database record (AC-7)"""
        # Count cameras before test
        list_response_before = client.get("/api/v1/cameras")
        count_before = len(list_response_before.json())

        # Even though this will fail (no mock), it shouldn't create a DB record
        test_data = {
            "type": "rtsp",
            "rtsp_url": "rtsp://192.168.1.50:554/stream1"
        }

        # This will return success=false (connection fails), but should not create DB record
        client.post("/api/v1/cameras/test", json=test_data)

        # Count cameras after test
        list_response_after = client.get("/api/v1/cameras")
        count_after = len(list_response_after.json())

        # No new cameras should be created
        assert count_after == count_before

    def test_presave_test_valid_rtsp_url_formats(self):
        """POST /cameras/test should accept both rtsp:// and rtsps:// URLs (AC-2)"""
        # Test rtsp:// format - validation should pass (422 only for format errors)
        test_data_rtsp = {
            "type": "rtsp",
            "rtsp_url": "rtsp://192.168.1.50:554/stream1"
        }
        response_rtsp = client.post("/api/v1/cameras/test", json=test_data_rtsp)
        # Should not be 422 (validation passes, connection may fail)
        assert response_rtsp.status_code == 200

        # Test rtsps:// format
        test_data_rtsps = {
            "type": "rtsp",
            "rtsp_url": "rtsps://192.168.1.50:7441/secure-stream"
        }
        response_rtsps = client.post("/api/v1/cameras/test", json=test_data_rtsps)
        # Should not be 422 (validation passes)
        assert response_rtsps.status_code == 200


# ==================== Detection Zone Tests (F2.2) ====================


def test_get_camera_zones_returns_empty_list_when_no_zones():
    """Test GET /cameras/{id}/zones returns empty list for camera with no zones"""
    # Create camera without zones
    create_response = client.post("/api/v1/cameras", json={
        "name": "Camera No Zones",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Get zones
    response = client.get(f"/api/v1/cameras/{camera_id}/zones")

    assert response.status_code == 200
    assert response.json() == []


def test_put_camera_zones_updates_detection_zones():
    """Test PUT /cameras/{id}/zones updates zones successfully"""
    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Camera With Zones",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Define zones
    zones = [
        {
            "id": "zone-1",
            "name": "Front Door",
            "vertices": [
                {"x": 100, "y": 100},
                {"x": 200, "y": 100},
                {"x": 200, "y": 200},
                {"x": 100, "y": 200}
            ],
            "enabled": True
        },
        {
            "id": "zone-2",
            "name": "Driveway",
            "vertices": [
                {"x": 300, "y": 300},
                {"x": 400, "y": 300},
                {"x": 400, "y": 400},
                {"x": 300, "y": 400}
            ],
            "enabled": False
        }
    ]

    # Update zones
    response = client.put(f"/api/v1/cameras/{camera_id}/zones", json=zones)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == camera_id
    assert data["detection_zones"] is not None

    # Verify zones persisted
    get_response = client.get(f"/api/v1/cameras/{camera_id}/zones")
    assert get_response.status_code == 200
    saved_zones = get_response.json()
    assert len(saved_zones) == 2
    assert saved_zones[0]["name"] == "Front Door"
    assert saved_zones[1]["name"] == "Driveway"


def test_put_camera_zones_validates_zone_limit():
    """Test PUT /cameras/{id}/zones enforces maximum 10 zones"""
    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Camera Too Many Zones",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Create 11 zones (over limit)
    zones = []
    for i in range(11):
        zones.append({
            "id": f"zone-{i}",
            "name": f"Zone {i}",
            "vertices": [
                {"x": i * 10, "y": i * 10},
                {"x": i * 10 + 50, "y": i * 10},
                {"x": i * 10 + 50, "y": i * 10 + 50},
                {"x": i * 10, "y": i * 10 + 50}
            ],
            "enabled": True
        })

    # Attempt to update zones
    response = client.put(f"/api/v1/cameras/{camera_id}/zones", json=zones)

    assert response.status_code == 422
    assert "Maximum 10 zones" in response.json()["detail"]


def test_put_camera_zones_returns_404_for_nonexistent_camera():
    """Test PUT /cameras/{id}/zones returns 404 for non-existent camera"""
    zones = [
        {
            "id": "zone-1",
            "name": "Test Zone",
            "vertices": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 100},
                {"x": 0, "y": 100}
            ],
            "enabled": True
        }
    ]

    response = client.put("/api/v1/cameras/nonexistent-id/zones", json=zones)

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_camera_zones_returns_404_for_nonexistent_camera():
    """Test GET /cameras/{id}/zones returns 404 for non-existent camera"""
    response = client.get("/api/v1/cameras/nonexistent-id/zones")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_zones_persist_across_camera_updates():
    """Test that zones persist when camera is updated"""
    # Create camera with zones
    create_response = client.post("/api/v1/cameras", json={
        "name": "Persistence Test Camera",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Set zones
    zones = [
        {
            "id": "persistent-zone",
            "name": "Persistent Zone",
            "vertices": [
                {"x": 50, "y": 50},
                {"x": 150, "y": 50},
                {"x": 150, "y": 150},
                {"x": 50, "y": 150}
            ],
            "enabled": True
        }
    ]
    client.put(f"/api/v1/cameras/{camera_id}/zones", json=zones)

    # Update camera name (non-zone field)
    update_response = client.put(f"/api/v1/cameras/{camera_id}", json={
        "name": "Updated Camera Name"
    })
    assert update_response.status_code == 200

    # Verify zones still exist
    get_response = client.get(f"/api/v1/cameras/{camera_id}/zones")
    assert get_response.status_code == 200
    saved_zones = get_response.json()
    assert len(saved_zones) == 1
    assert saved_zones[0]["name"] == "Persistent Zone"


def test_detection_zone_schema_validates_vertices():
    """Test that DetectionZone schema validates minimum vertices"""
    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Validation Test Camera",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Invalid zone with only 2 vertices (need at least 3 for polygon)
    invalid_zones = [
        {
            "id": "invalid-zone",
            "name": "Invalid",
            "vertices": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 100}
            ],
            "enabled": True
        }
    ]

    # Attempt to update zones
    response = client.put(f"/api/v1/cameras/{camera_id}/zones", json=invalid_zones)

    # Should fail validation (422)
    assert response.status_code == 422


def test_zone_auto_close_polygon():
    """Test that DetectionZone schema auto-closes polygon if needed"""
    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Auto-close Test",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Zone with unclosed polygon (first != last)
    zones = [
        {
            "id": "autoclosed-zone",
            "name": "Auto-closed",
            "vertices": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 100},
                {"x": 0, "y": 100}
                # Missing closing vertex (0, 0) - should be auto-added
            ],
            "enabled": True
        }
    ]

    response = client.put(f"/api/v1/cameras/{camera_id}/zones", json=zones)
    assert response.status_code == 200

    # Verify polygon was auto-closed
    get_response = client.get(f"/api/v1/cameras/{camera_id}/zones")
    saved_zones = get_response.json()
    assert len(saved_zones[0]["vertices"]) == 5  # Original 4 + auto-closed vertex
    assert saved_zones[0]["vertices"][0] == saved_zones[0]["vertices"][-1]


# ============================================================================
# Detection Schedule Tests (F2.3)
# ============================================================================

def test_put_schedule_creates_new():
    """Test that PUT /cameras/{id}/schedule creates new schedule"""
    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Schedule Test",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Create schedule
    schedule = {
        "id": "schedule-1",
        "name": "Weekday Nights",
        "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
        "start_time": "22:00",
        "end_time": "06:00",
        "enabled": True
    }

    response = client.put(f"/api/v1/cameras/{camera_id}/schedule", json=schedule)
    assert response.status_code == 200

    # Verify schedule stored
    camera_data = response.json()
    assert camera_data["detection_schedule"] is not None


def test_put_schedule_updates_existing():
    """Test that PUT /cameras/{id}/schedule updates existing schedule"""
    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Schedule Update Test",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Create initial schedule
    schedule1 = {
        "id": "schedule-1",
        "name": "Original Schedule",
        "days_of_week": [0, 1, 2, 3, 4],
        "start_time": "09:00",
        "end_time": "17:00",
        "enabled": True
    }
    client.put(f"/api/v1/cameras/{camera_id}/schedule", json=schedule1)

    # Update schedule
    schedule2 = {
        "id": "schedule-2",
        "name": "Updated Schedule",
        "days_of_week": [5, 6],  # Weekend only
        "start_time": "00:00",
        "end_time": "23:59",
        "enabled": True
    }
    response = client.put(f"/api/v1/cameras/{camera_id}/schedule", json=schedule2)
    assert response.status_code == 200

    # Verify updated
    get_response = client.get(f"/api/v1/cameras/{camera_id}/schedule")
    saved_schedule = get_response.json()
    assert saved_schedule["name"] == "Updated Schedule"
    assert saved_schedule["days_of_week"] == [5, 6]


def test_get_schedule_returns_config():
    """Test that GET /cameras/{id}/schedule returns configured schedule"""
    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Get Schedule Test",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Create schedule
    schedule = {
        "id": "schedule-1",
        "name": "Test Schedule",
        "days_of_week": [0, 1, 2],
        "start_time": "08:00",
        "end_time": "18:00",
        "enabled": True
    }
    client.put(f"/api/v1/cameras/{camera_id}/schedule", json=schedule)

    # Get schedule
    response = client.get(f"/api/v1/cameras/{camera_id}/schedule")
    assert response.status_code == 200

    saved_schedule = response.json()
    assert saved_schedule["id"] == "schedule-1"
    assert saved_schedule["name"] == "Test Schedule"
    assert saved_schedule["days_of_week"] == [0, 1, 2]
    assert saved_schedule["start_time"] == "08:00"
    assert saved_schedule["end_time"] == "18:00"
    assert saved_schedule["enabled"] is True


def test_get_schedule_null_when_not_set():
    """Test that GET /cameras/{id}/schedule returns null when not configured"""
    # Create camera without schedule
    create_response = client.post("/api/v1/cameras", json={
        "name": "No Schedule Test",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Get schedule (should be null)
    response = client.get(f"/api/v1/cameras/{camera_id}/schedule")
    assert response.status_code == 200
    assert response.json() is None


def test_get_schedule_status_active():
    """Test GET /cameras/{id}/schedule/status returns active state"""
    from unittest.mock import patch
    from datetime import datetime

    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Status Test",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Create schedule (Mon-Fri 08:00-18:00)
    schedule = {
        "id": "schedule-1",
        "name": "Business Hours",
        "days_of_week": [0, 1, 2, 3, 4],
        "start_time": "08:00",
        "end_time": "18:00",
        "enabled": True
    }
    client.put(f"/api/v1/cameras/{camera_id}/schedule", json=schedule)

    # Mock datetime to Monday 10:00am
    with patch('app.services.schedule_manager.datetime') as mock_datetime:
        mock_datetime.now.return_value = datetime(2025, 11, 17, 10, 0)  # Monday 10am

        # Get schedule status
        response = client.get(f"/api/v1/cameras/{camera_id}/schedule/status")
        assert response.status_code == 200

        status_data = response.json()
        assert status_data["active"] is True
        assert "within" in status_data["reason"].lower()
        assert status_data["schedule_enabled"] is True


def test_get_schedule_status_inactive():
    """Test GET /cameras/{id}/schedule/status returns inactive state"""
    from unittest.mock import patch
    from datetime import datetime

    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Status Inactive Test",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Create schedule (Mon-Fri 08:00-18:00)
    schedule = {
        "id": "schedule-1",
        "name": "Business Hours",
        "days_of_week": [0, 1, 2, 3, 4],
        "start_time": "08:00",
        "end_time": "18:00",
        "enabled": True
    }
    client.put(f"/api/v1/cameras/{camera_id}/schedule", json=schedule)

    # Mock datetime to Saturday 10:00am (outside Mon-Fri)
    with patch('app.services.schedule_manager.datetime') as mock_datetime:
        mock_datetime.now.return_value = datetime(2025, 11, 22, 10, 0)  # Saturday 10am

        # Get schedule status
        response = client.get(f"/api/v1/cameras/{camera_id}/schedule/status")
        assert response.status_code == 200

        status_data = response.json()
        assert status_data["active"] is False
        assert "outside" in status_data["reason"].lower()


def test_schedule_validation_rejects_invalid_time():
    """Test that schedule validation rejects invalid time format"""
    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Invalid Time Test",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Invalid time format
    schedule = {
        "id": "schedule-1",
        "name": "Bad Time",
        "days_of_week": [0, 1, 2, 3, 4],
        "start_time": "25:00",  # Invalid hour
        "end_time": "18:00",
        "enabled": True
    }

    response = client.put(f"/api/v1/cameras/{camera_id}/schedule", json=schedule)
    # Should fail validation (422)
    assert response.status_code == 422


def test_schedule_validation_rejects_invalid_days():
    """Test that schedule validation rejects invalid days_of_week"""
    # Create camera
    create_response = client.post("/api/v1/cameras", json={
        "name": "Invalid Days Test",
        "type": "usb",
        "device_index": 0,
        "is_enabled": False
    })
    camera_id = create_response.json()["id"]

    # Invalid day (7 is outside 0-6 range)
    schedule = {
        "id": "schedule-1",
        "name": "Bad Days",
        "days_of_week": [0, 1, 7],  # 7 is invalid
        "start_time": "08:00",
        "end_time": "18:00",
        "enabled": True
    }

    response = client.put(f"/api/v1/cameras/{camera_id}/schedule", json=schedule)
    # Should fail validation (422)
    assert response.status_code == 422


def test_schedule_404_for_nonexistent_camera():
    """Test that schedule endpoints return 404 for non-existent camera"""
    fake_id = "00000000-0000-0000-0000-000000000000"

    # GET schedule
    response = client.get(f"/api/v1/cameras/{fake_id}/schedule")
    assert response.status_code == 404

    # PUT schedule
    schedule = {
        "id": "schedule-1",
        "name": "Test",
        "days_of_week": [0],
        "start_time": "08:00",
        "end_time": "18:00",
        "enabled": True
    }
    response = client.put(f"/api/v1/cameras/{fake_id}/schedule", json=schedule)
    assert response.status_code == 404

    # GET schedule status
    response = client.get(f"/api/v1/cameras/{fake_id}/schedule/status")
    assert response.status_code == 404


# ============================================================================
# Analysis Mode Tests (Story P3-3.1)
# ============================================================================


class TestCameraAnalysisModeAPI:
    """Test suite for Camera analysis_mode API (Story P3-3.1)"""

    def test_create_camera_default_analysis_mode(self):
        """AC2: Camera created without analysis_mode defaults to 'single_frame'"""
        camera_data = {
            "name": "Default Analysis Mode Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "is_enabled": False
        }

        response = client.post("/api/v1/cameras", json=camera_data)

        assert response.status_code == 201
        data = response.json()
        assert data["analysis_mode"] == "single_frame"

    def test_create_camera_with_single_frame_mode(self):
        """AC1: Camera can be created with analysis_mode='single_frame'"""
        camera_data = {
            "name": "Single Frame Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "analysis_mode": "single_frame",
            "is_enabled": False
        }

        response = client.post("/api/v1/cameras", json=camera_data)

        assert response.status_code == 201
        data = response.json()
        assert data["analysis_mode"] == "single_frame"

    def test_create_camera_with_multi_frame_mode(self):
        """AC1: Camera can be created with analysis_mode='multi_frame'"""
        camera_data = {
            "name": "Multi Frame Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "analysis_mode": "multi_frame",
            "is_enabled": False
        }

        response = client.post("/api/v1/cameras", json=camera_data)

        assert response.status_code == 201
        data = response.json()
        assert data["analysis_mode"] == "multi_frame"

    def test_create_camera_with_video_native_mode(self):
        """AC1: Camera can be created with analysis_mode='video_native'"""
        camera_data = {
            "name": "Video Native Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "analysis_mode": "video_native",
            "is_enabled": False
        }

        response = client.post("/api/v1/cameras", json=camera_data)

        assert response.status_code == 201
        data = response.json()
        assert data["analysis_mode"] == "video_native"

    def test_create_camera_with_invalid_analysis_mode(self):
        """AC1: Camera with invalid analysis_mode should return 422"""
        camera_data = {
            "name": "Invalid Mode Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "analysis_mode": "invalid_mode",
            "is_enabled": False
        }

        response = client.post("/api/v1/cameras", json=camera_data)

        assert response.status_code == 422

    def test_update_camera_analysis_mode(self):
        """Camera's analysis_mode can be updated via PUT"""
        # Create camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Update Mode Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "analysis_mode": "single_frame",
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Update analysis_mode
        update_response = client.put(f"/api/v1/cameras/{camera_id}", json={
            "analysis_mode": "multi_frame"
        })

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["analysis_mode"] == "multi_frame"

    def test_update_camera_invalid_analysis_mode(self):
        """PUT with invalid analysis_mode should return 422"""
        # Create camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Update Invalid Mode Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Try to update with invalid analysis_mode
        update_response = client.put(f"/api/v1/cameras/{camera_id}", json={
            "analysis_mode": "invalid_mode"
        })

        assert update_response.status_code == 422

    def test_get_camera_includes_analysis_mode(self):
        """GET /cameras/{id} response includes analysis_mode field"""
        # Create camera
        create_response = client.post("/api/v1/cameras", json={
            "name": "Get Mode Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream",
            "analysis_mode": "multi_frame",
            "is_enabled": False
        })
        camera_id = create_response.json()["id"]

        # Get camera
        get_response = client.get(f"/api/v1/cameras/{camera_id}")

        assert get_response.status_code == 200
        data = get_response.json()
        assert "analysis_mode" in data
        assert data["analysis_mode"] == "multi_frame"

    def test_list_cameras_includes_analysis_mode(self):
        """GET /cameras response includes analysis_mode for each camera"""
        # Create cameras with different modes
        client.post("/api/v1/cameras", json={
            "name": "Camera Mode 1",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream1",
            "analysis_mode": "single_frame",
            "is_enabled": False
        })
        client.post("/api/v1/cameras", json={
            "name": "Camera Mode 2",
            "type": "rtsp",
            "rtsp_url": "rtsp://example.com/stream2",
            "analysis_mode": "multi_frame",
            "is_enabled": False
        })

        # List cameras
        list_response = client.get("/api/v1/cameras")

        assert list_response.status_code == 200
        data = list_response.json()
        assert len(data) == 2
        # Check each camera has analysis_mode
        for camera in data:
            assert "analysis_mode" in camera
        # Verify different modes
        modes = {c["analysis_mode"] for c in data}
        assert "single_frame" in modes
        assert "multi_frame" in modes
