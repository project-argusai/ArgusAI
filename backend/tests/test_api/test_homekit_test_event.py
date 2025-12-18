"""
HomeKit Test Event API Tests (Story P7-1.3)

Tests for POST /api/v1/homekit/test-event endpoint that allows manual
triggering of HomeKit events for testing and debugging.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from app.models.camera import Camera
from app.core.database import get_db


# Test client fixture
@pytest.fixture
def client(db_session):
    """Create test client with database session override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def test_camera(db_session):
    """Create a test camera in the database."""
    camera = Camera(
        id="test-camera-uuid-1234",
        name="Test Camera",
        type="rtsp",
        rtsp_url="rtsp://192.168.1.100/stream",
        is_enabled=True,
        homekit_enabled=True
    )
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


class TestHomekitTestEventEndpoint:
    """Tests for POST /api/v1/homekit/test-event endpoint (Story P7-1.3 AC5)."""

    def test_test_event_camera_not_found(self, client):
        """Test event trigger returns 404 when camera not found."""
        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            mock_service.return_value.is_running = True

            response = client.post(
                "/api/v1/homekit/test-event",
                json={
                    "camera_id": "nonexistent-camera-id",
                    "event_type": "motion"
                }
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_test_event_bridge_not_running(self, client, test_camera):
        """Test event trigger returns 400 when bridge is not running."""
        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            mock_service.return_value.is_running = False

            response = client.post(
                "/api/v1/homekit/test-event",
                json={
                    "camera_id": test_camera.id,
                    "event_type": "motion"
                }
            )

            assert response.status_code == 400
            assert "not running" in response.json()["detail"].lower()

    def test_test_event_invalid_event_type(self, client, test_camera):
        """Test event trigger returns 422 for invalid event type."""
        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            mock_service.return_value.is_running = True

            response = client.post(
                "/api/v1/homekit/test-event",
                json={
                    "camera_id": test_camera.id,
                    "event_type": "invalid_type"
                }
            )

            assert response.status_code == 422

    def test_test_event_motion_success(self, client, test_camera):
        """Test successful motion event trigger."""
        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            service_mock = MagicMock()
            service_mock.is_running = True
            service_mock.trigger_test_event.return_value = {
                "success": True,
                "message": "Motion event triggered for Test Camera Motion",
                "sensor_name": "Test Camera Motion",
                "delivered_to_clients": 2
            }
            mock_service.return_value = service_mock

            response = client.post(
                "/api/v1/homekit/test-event",
                json={
                    "camera_id": test_camera.id,
                    "event_type": "motion"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["camera_id"] == test_camera.id
            assert data["event_type"] == "motion"
            assert data["sensor_name"] == "Test Camera Motion"
            assert data["delivered_to_clients"] == 2
            assert "timestamp" in data

    def test_test_event_occupancy_success(self, client, test_camera):
        """Test successful occupancy event trigger."""
        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            service_mock = MagicMock()
            service_mock.is_running = True
            service_mock.trigger_test_event.return_value = {
                "success": True,
                "message": "Occupancy event triggered for Test Camera Occupancy",
                "sensor_name": "Test Camera Occupancy",
                "delivered_to_clients": 1
            }
            mock_service.return_value = service_mock

            response = client.post(
                "/api/v1/homekit/test-event",
                json={
                    "camera_id": test_camera.id,
                    "event_type": "occupancy"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["event_type"] == "occupancy"

    def test_test_event_doorbell_success(self, client, test_camera):
        """Test successful doorbell event trigger."""
        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            service_mock = MagicMock()
            service_mock.is_running = True
            service_mock.trigger_test_event.return_value = {
                "success": True,
                "message": "Doorbell event triggered for Test Camera Doorbell",
                "sensor_name": "Test Camera Doorbell",
                "delivered_to_clients": 3
            }
            mock_service.return_value = service_mock

            response = client.post(
                "/api/v1/homekit/test-event",
                json={
                    "camera_id": test_camera.id,
                    "event_type": "doorbell"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["event_type"] == "doorbell"
            assert data["delivered_to_clients"] == 3

    def test_test_event_sensor_not_found(self, client, test_camera):
        """Test event trigger returns 400 when sensor not found for camera."""
        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            service_mock = MagicMock()
            service_mock.is_running = True
            service_mock.trigger_test_event.return_value = {
                "success": False,
                "message": "No vehicle sensor found for camera: test-camera-uuid-1234",
                "sensor_name": None,
                "delivered_to_clients": 0
            }
            mock_service.return_value = service_mock

            response = client.post(
                "/api/v1/homekit/test-event",
                json={
                    "camera_id": test_camera.id,
                    "event_type": "vehicle"
                }
            )

            assert response.status_code == 400
            assert "sensor" in response.json()["detail"].lower()

    def test_test_event_all_valid_types(self, client, test_camera):
        """Test all valid event types are accepted."""
        valid_types = ["motion", "occupancy", "vehicle", "animal", "package", "doorbell"]

        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            service_mock = MagicMock()
            service_mock.is_running = True
            service_mock.trigger_test_event.return_value = {
                "success": True,
                "message": "Event triggered",
                "sensor_name": "Test Sensor",
                "delivered_to_clients": 1
            }
            mock_service.return_value = service_mock

            for event_type in valid_types:
                response = client.post(
                    "/api/v1/homekit/test-event",
                    json={
                        "camera_id": test_camera.id,
                        "event_type": event_type
                    }
                )
                assert response.status_code == 200, f"Failed for event_type: {event_type}"


class TestHomekitTestEventSchema:
    """Tests for HomeKitTestEventRequest/Response schemas."""

    def test_request_schema_minimum_fields(self, client, test_camera):
        """Test request accepts minimum required fields."""
        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            service_mock = MagicMock()
            service_mock.is_running = True
            service_mock.trigger_test_event.return_value = {
                "success": True,
                "message": "Event triggered",
                "sensor_name": "Test Sensor",
                "delivered_to_clients": 1
            }
            mock_service.return_value = service_mock

            # Only camera_id required (event_type defaults to "motion")
            response = client.post(
                "/api/v1/homekit/test-event",
                json={
                    "camera_id": test_camera.id
                }
            )

            assert response.status_code == 200

    def test_request_schema_empty_camera_id(self, client):
        """Test request rejects empty camera_id."""
        response = client.post(
            "/api/v1/homekit/test-event",
            json={
                "camera_id": "",
                "event_type": "motion"
            }
        )

        assert response.status_code == 422

    def test_response_schema_contains_all_fields(self, client, test_camera):
        """Test response contains all expected fields."""
        with patch('app.api.v1.homekit.get_homekit_service') as mock_service:
            service_mock = MagicMock()
            service_mock.is_running = True
            service_mock.trigger_test_event.return_value = {
                "success": True,
                "message": "Motion event triggered for Test Camera Motion",
                "sensor_name": "Test Camera Motion",
                "delivered_to_clients": 2
            }
            mock_service.return_value = service_mock

            response = client.post(
                "/api/v1/homekit/test-event",
                json={
                    "camera_id": test_camera.id,
                    "event_type": "motion"
                }
            )

            assert response.status_code == 200
            data = response.json()

            # All expected fields present
            assert "success" in data
            assert "message" in data
            assert "camera_id" in data
            assert "event_type" in data
            assert "sensor_name" in data
            assert "delivered_to_clients" in data
            assert "timestamp" in data
