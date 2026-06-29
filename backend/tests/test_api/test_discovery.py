"""
API Integration Tests for ONVIF Camera Discovery (Stories P5-2.1, P5-2.2)

Tests the discovery API endpoints:
- POST /api/v1/cameras/discover (P5-2.1)
- GET /api/v1/cameras/discover/status (P5-2.1)
- POST /api/v1/cameras/discover/clear-cache (P5-2.1)
- GET /api/v1/cameras/discover/device/status (P5-2.2)
- POST /api/v1/cameras/discover/device (P5-2.2)
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.schemas.discovery import (
    DiscoveredDevice,
    DiscoveryResponse,
    DeviceInfo,
    StreamProfile,
    DiscoveredCameraDetails,
)
from app.services.onvif_discovery_service import (
    ONVIFDiscoveryService,
    DiscoveryResult,
    DeviceDetailsResult,
)


@pytest.fixture
def client():
    """Create test client with mocked discovery service."""
    from main import app
    return TestClient(app)


@pytest.fixture
def mock_discovery_service():
    """Create mock discovery service."""
    mock_service = MagicMock(spec=ONVIFDiscoveryService)
    mock_service.is_available = True
    return mock_service


class TestDiscoverEndpoint:
    """Tests for POST /api/v1/cameras/discover."""

    def test_discover_returns_devices(self, client, mock_discovery_service):
        """AC5: Test discovery endpoint returns device list."""
        mock_device = DiscoveredDevice(
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            scopes=["onvif://www.onvif.org/type/NVT"],
            types=["tdn:NetworkVideoTransmitter"],
            metadata_version="1"
        )

        mock_result = DiscoveryResult(
            devices=[mock_device],
            duration_ms=5234,
            status="complete",
            error=None
        )

        mock_discovery_service.discover_cameras_with_result.return_value = mock_result

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post("/api/v1/cameras/discover")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "complete"
        assert data["duration_ms"] == 5234
        assert data["device_count"] == 1
        assert len(data["devices"]) == 1
        assert data["devices"][0]["endpoint_url"] == "http://192.168.1.100:80/onvif/device_service"

    def test_discover_with_custom_timeout(self, client, mock_discovery_service):
        """AC5: Test custom timeout parameter."""
        mock_result = DiscoveryResult(
            devices=[],
            duration_ms=15000,
            status="complete"
        )

        mock_discovery_service.discover_cameras_with_result.return_value = mock_result

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover",
                json={"timeout": 15}
            )

        assert response.status_code == 200
        mock_discovery_service.discover_cameras_with_result.assert_called_once_with(timeout=15)

    def test_discover_empty_results(self, client, mock_discovery_service):
        """AC5: Test empty discovery results."""
        mock_result = DiscoveryResult(
            devices=[],
            duration_ms=10000,
            status="complete"
        )

        mock_discovery_service.discover_cameras_with_result.return_value = mock_result

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post("/api/v1/cameras/discover")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "complete"
        assert data["device_count"] == 0
        assert data["devices"] == []

    def test_discover_multiple_devices(self, client, mock_discovery_service):
        """AC5: Test discovery with multiple devices."""
        devices = [
            DiscoveredDevice(
                endpoint_url="http://192.168.1.100:80/onvif/device_service",
                scopes=[],
                types=["tdn:NetworkVideoTransmitter"]
            ),
            DiscoveredDevice(
                endpoint_url="http://192.168.1.101:80/onvif/device_service",
                scopes=[],
                types=["tdn:NetworkVideoTransmitter"]
            ),
            DiscoveredDevice(
                endpoint_url="http://192.168.1.102:80/onvif/device_service",
                scopes=[],
                types=["tdn:NetworkVideoTransmitter"]
            ),
        ]

        mock_result = DiscoveryResult(
            devices=devices,
            duration_ms=8500,
            status="complete"
        )

        mock_discovery_service.discover_cameras_with_result.return_value = mock_result

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post("/api/v1/cameras/discover")

        assert response.status_code == 200
        data = response.json()

        assert data["device_count"] == 3
        assert len(data["devices"]) == 3

    def test_discover_service_unavailable(self, client, mock_discovery_service):
        """AC5: Test 503 when discovery service unavailable."""
        mock_discovery_service.is_available = False

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post("/api/v1/cameras/discover")

        assert response.status_code == 503
        data = response.json()
        assert "discovery_unavailable" in str(data["detail"])

    def test_discover_service_error(self, client, mock_discovery_service):
        """AC5: Test error handling for service exceptions."""
        mock_discovery_service.discover_cameras_with_result.side_effect = Exception(
            "Network error"
        )

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post("/api/v1/cameras/discover")

        assert response.status_code == 500
        data = response.json()
        assert "discovery_failed" in str(data["detail"])

    def test_discover_default_timeout(self, client, mock_discovery_service):
        """AC5: Test default timeout when not specified."""
        mock_result = DiscoveryResult(
            devices=[],
            duration_ms=10000,
            status="complete"
        )

        mock_discovery_service.discover_cameras_with_result.return_value = mock_result

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post("/api/v1/cameras/discover")

        assert response.status_code == 200
        # Default timeout is 10 seconds
        mock_discovery_service.discover_cameras_with_result.assert_called_once_with(timeout=10)


class TestDiscoveryStatusEndpoint:
    """Tests for GET /api/v1/cameras/discover/status."""

    def test_status_available(self, client, mock_discovery_service):
        """Test status returns available when library installed."""
        mock_discovery_service.is_available = True

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.get("/api/v1/cameras/discover/status")

        assert response.status_code == 200
        data = response.json()

        assert data["available"] is True
        assert data["library_installed"] is True
        assert "available" in data["message"].lower()

    def test_status_unavailable(self, client, mock_discovery_service):
        """Test status returns unavailable when library not installed."""
        mock_discovery_service.is_available = False

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.get("/api/v1/cameras/discover/status")

        assert response.status_code == 200
        data = response.json()

        assert data["available"] is False
        assert data["library_installed"] is False
        assert "unavailable" in data["message"].lower()


class TestClearCacheEndpoint:
    """Tests for POST /api/v1/cameras/discover/clear-cache."""

    def test_clear_cache_success(self, client, mock_discovery_service):
        """Test cache clear returns success."""
        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post("/api/v1/cameras/discover/clear-cache")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        mock_discovery_service.clear_cache.assert_called_once()


class TestDiscoveryResponseSchema:
    """Test DiscoveryResponse schema validation."""

    def test_response_schema(self, client, mock_discovery_service):
        """Verify response matches DiscoveryResponse schema."""
        mock_device = DiscoveredDevice(
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            scopes=["scope1", "scope2"],
            types=["type1"],
            metadata_version="1"
        )

        mock_result = DiscoveryResult(
            devices=[mock_device],
            duration_ms=5000,
            status="complete"
        )

        mock_discovery_service.discover_cameras_with_result.return_value = mock_result

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post("/api/v1/cameras/discover")

        data = response.json()

        # Validate all expected fields exist
        assert "status" in data
        assert "duration_ms" in data
        assert "devices" in data
        assert "device_count" in data

        # Validate device fields
        device = data["devices"][0]
        assert "endpoint_url" in device
        assert "scopes" in device
        assert "types" in device

    def test_timeout_validation(self, client, mock_discovery_service):
        """Test timeout parameter validation."""
        mock_result = DiscoveryResult(devices=[], duration_ms=0, status="complete")
        mock_discovery_service.discover_cameras_with_result.return_value = mock_result

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            # Valid timeout
            response = client.post("/api/v1/cameras/discover", json={"timeout": 30})
            assert response.status_code == 200

            # Timeout too high (max 60)
            response = client.post("/api/v1/cameras/discover", json={"timeout": 120})
            assert response.status_code == 422  # Validation error

            # Timeout too low (min 1)
            response = client.post("/api/v1/cameras/discover", json={"timeout": 0})
            assert response.status_code == 422  # Validation error


# ============================================================================
# Story P5-2.2: Device Details API Tests
# ============================================================================


class TestDeviceDetailsStatusEndpoint:
    """Tests for GET /api/v1/cameras/discover/device/status (P5-2.2)."""

    def test_device_details_status_available(self, client, mock_discovery_service):
        """Test status returns available when onvif-zeep installed."""
        mock_discovery_service.is_device_details_available = True

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.get("/api/v1/cameras/discover/device/status")

        assert response.status_code == 200
        data = response.json()

        assert data["available"] is True
        assert data["library_installed"] is True
        assert "available" in data["message"].lower()

    def test_device_details_status_unavailable(self, client, mock_discovery_service):
        """Test status returns unavailable when onvif-zeep not installed."""
        mock_discovery_service.is_device_details_available = False

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.get("/api/v1/cameras/discover/device/status")

        assert response.status_code == 200
        data = response.json()

        assert data["available"] is False
        assert data["library_installed"] is False
        assert "unavailable" in data["message"].lower()


class TestGetDeviceDetailsEndpoint:
    """Tests for POST /api/v1/cameras/discover/device (P5-2.2)."""

    def test_get_device_details_success(self, client, mock_discovery_service):
        """AC1, AC4, AC5: Test successful device details retrieval."""
        mock_discovery_service.is_device_details_available = True

        mock_device = DiscoveredCameraDetails(
            id="camera-192-168-1-100-80",
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            ip_address="192.168.1.100",
            port=80,
            device_info=DeviceInfo(
                name="Dahua IPC-HDW2431T",
                manufacturer="Dahua",
                model="IPC-HDW2431T-AS-S2",
                firmware_version="2.800.0000000.44.R"
            ),
            profiles=[
                StreamProfile(
                    name="mainStream",
                    token="profile_1",
                    resolution="1920x1080",
                    width=1920,
                    height=1080,
                    fps=30,
                    rtsp_url="rtsp://192.168.1.100:554/stream",
                    encoding="H264"
                )
            ],
            primary_rtsp_url="rtsp://192.168.1.100:554/stream",
            requires_auth=False,
            discovered_at=datetime.utcnow()
        )

        mock_result = DeviceDetailsResult(
            status="success",
            device=mock_device,
            duration_ms=1234
        )

        async def mock_get_device_details(*args, **kwargs):
            return mock_result

        mock_discovery_service.get_device_details = mock_get_device_details

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/device",
                json={"endpoint_url": "http://192.168.1.100:80/onvif/device_service"}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["duration_ms"] == 1234
        assert data["device"]["ip_address"] == "192.168.1.100"
        assert data["device"]["device_info"]["manufacturer"] == "Dahua"
        assert len(data["device"]["profiles"]) == 1
        assert data["device"]["profiles"][0]["resolution"] == "1920x1080"

    def test_get_device_details_with_credentials(self, client, mock_discovery_service):
        """AC1: Test device details with authentication credentials."""
        mock_discovery_service.is_device_details_available = True

        mock_device = DiscoveredCameraDetails(
            id="camera-192-168-1-100-80",
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            ip_address="192.168.1.100",
            port=80,
            device_info=DeviceInfo(
                name="Test Camera",
                manufacturer="Test",
                model="Model"
            ),
            profiles=[],
            primary_rtsp_url="rtsp://192.168.1.100:554/stream",
            requires_auth=False,
            discovered_at=datetime.utcnow()
        )

        mock_result = DeviceDetailsResult(
            status="success",
            device=mock_device,
            duration_ms=500
        )

        captured_args = {}

        async def mock_get_device_details(endpoint_url, username=None, password=None):
            captured_args["endpoint_url"] = endpoint_url
            captured_args["username"] = username
            captured_args["password"] = password
            return mock_result

        mock_discovery_service.get_device_details = mock_get_device_details

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/device",
                json={
                    "endpoint_url": "http://192.168.1.100:80/onvif/device_service",
                    "username": "admin",
                    "password": "password123"
                }
            )

        assert response.status_code == 200
        assert captured_args["username"] == "admin"
        assert captured_args["password"] == "password123"

    def test_get_device_details_auth_required(self, client, mock_discovery_service):
        """AC1: Test auth_required response when credentials needed."""
        mock_discovery_service.is_device_details_available = True

        mock_result = DeviceDetailsResult(
            status="auth_required",
            error="Authentication required to access this device",
            duration_ms=234
        )

        async def mock_get_device_details(*args, **kwargs):
            return mock_result

        mock_discovery_service.get_device_details = mock_get_device_details

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/device",
                json={"endpoint_url": "http://192.168.1.100:80/onvif/device_service"}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "auth_required"
        assert "Authentication" in data["error_message"]
        assert data["device"] is None

    def test_get_device_details_service_unavailable(self, client, mock_discovery_service):
        """Test 503 when onvif-zeep not installed."""
        mock_discovery_service.is_device_details_available = False

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/device",
                json={"endpoint_url": "http://192.168.1.100:80/onvif/device_service"}
            )

        assert response.status_code == 503
        data = response.json()
        assert "device_details_unavailable" in str(data["detail"])

    def test_get_device_details_connection_error(self, client, mock_discovery_service):
        """Test error response for connection failures."""
        mock_discovery_service.is_device_details_available = True

        mock_result = DeviceDetailsResult(
            status="error",
            error="Connection refused",
            duration_ms=100
        )

        async def mock_get_device_details(*args, **kwargs):
            return mock_result

        mock_discovery_service.get_device_details = mock_get_device_details

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/device",
                json={"endpoint_url": "http://192.168.1.100:80/onvif/device_service"}
            )

        assert response.status_code == 200  # Returns 200 with error status
        data = response.json()

        assert data["status"] == "error"
        assert "Connection refused" in data["error_message"]
        assert data["device"] is None

    def test_get_device_details_exception_handling(self, client, mock_discovery_service):
        """Test 500 for unexpected exceptions."""
        mock_discovery_service.is_device_details_available = True

        async def mock_get_device_details(*args, **kwargs):
            raise Exception("Unexpected error")

        mock_discovery_service.get_device_details = mock_get_device_details

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/device",
                json={"endpoint_url": "http://192.168.1.100:80/onvif/device_service"}
            )

        assert response.status_code == 500
        data = response.json()
        assert "device_query_failed" in str(data["detail"])

    def test_get_device_details_missing_endpoint_url(self, client, mock_discovery_service):
        """Test validation error when endpoint_url is missing."""
        mock_discovery_service.is_device_details_available = True

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/device",
                json={}  # Missing endpoint_url
            )

        assert response.status_code == 422  # Validation error


class TestDeviceDetailsResponseSchema:
    """Test DeviceDetailsResponse schema (P5-2.2)."""

    def test_response_includes_all_fields(self, client, mock_discovery_service):
        """AC4, AC5: Verify response includes all expected fields."""
        mock_discovery_service.is_device_details_available = True

        mock_device = DiscoveredCameraDetails(
            id="camera-192-168-1-100-80",
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            ip_address="192.168.1.100",
            port=80,
            device_info=DeviceInfo(
                name="Test Camera",
                manufacturer="TestCo",
                model="TestModel",
                firmware_version="1.0.0",
                serial_number="12345",
                hardware_id="HW001"
            ),
            profiles=[
                StreamProfile(
                    name="mainStream",
                    token="profile_1",
                    resolution="1920x1080",
                    width=1920,
                    height=1080,
                    fps=30,
                    rtsp_url="rtsp://192.168.1.100:554/stream",
                    encoding="H264"
                ),
                StreamProfile(
                    name="subStream",
                    token="profile_2",
                    resolution="640x480",
                    width=640,
                    height=480,
                    fps=15,
                    rtsp_url="rtsp://192.168.1.100:554/stream2",
                    encoding="H264"
                )
            ],
            primary_rtsp_url="rtsp://192.168.1.100:554/stream",
            requires_auth=False,
            discovered_at=datetime.utcnow()
        )

        mock_result = DeviceDetailsResult(
            status="success",
            device=mock_device,
            duration_ms=1234
        )

        async def mock_get_device_details(*args, **kwargs):
            return mock_result

        mock_discovery_service.get_device_details = mock_get_device_details

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/device",
                json={"endpoint_url": "http://192.168.1.100:80/onvif/device_service"}
            )

        assert response.status_code == 200
        data = response.json()

        # Check top-level fields
        assert "status" in data
        assert "device" in data
        assert "error_message" in data
        assert "duration_ms" in data

        # Check device fields
        device = data["device"]
        assert "id" in device
        assert "endpoint_url" in device
        assert "ip_address" in device
        assert "port" in device
        assert "device_info" in device
        assert "profiles" in device
        assert "primary_rtsp_url" in device
        assert "requires_auth" in device

        # Check device_info fields
        device_info = device["device_info"]
        assert device_info["manufacturer"] == "TestCo"
        assert device_info["model"] == "TestModel"
        assert device_info["firmware_version"] == "1.0.0"

        # Check profiles
        assert len(device["profiles"]) == 2
        profile = device["profiles"][0]
        assert "name" in profile
        assert "token" in profile
        assert "resolution" in profile
        assert "width" in profile
        assert "height" in profile
        assert "fps" in profile
        assert "rtsp_url" in profile


# ============================================================================
# Story P5-2.4: Test Connection API Tests
# ============================================================================


class TestTestConnectionEndpoint:
    """Tests for POST /api/v1/cameras/discover/test (P5-2.4)."""

    def test_test_connection_success(self, client, mock_discovery_service):
        """AC1, AC2: Test successful connection returns stream metadata."""
        from app.schemas.discovery import TestConnectionResponse

        mock_result = TestConnectionResponse(
            success=True,
            latency_ms=234,
            resolution="1920x1080",
            fps=30,
            codec="H.264",
            error=None
        )

        async def mock_test_connection(*args, **kwargs):
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "rtsp://192.168.1.100:554/stream"}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["latency_ms"] == 234
        assert data["resolution"] == "1920x1080"
        assert data["fps"] == 30
        assert data["codec"] == "H.264"
        assert data["error"] is None

    def test_test_connection_with_credentials(self, client, mock_discovery_service):
        """AC1: Test connection with username and password."""
        from app.schemas.discovery import TestConnectionResponse

        captured_args = {}

        mock_result = TestConnectionResponse(
            success=True,
            latency_ms=500,
            resolution="1280x720",
            fps=25,
            codec="H.264"
        )

        async def mock_test_connection(rtsp_url, username=None, password=None):
            captured_args["rtsp_url"] = rtsp_url
            captured_args["username"] = username
            captured_args["password"] = password
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={
                    "rtsp_url": "rtsp://192.168.1.100:554/stream",
                    "username": "admin",
                    "password": "secret123"
                }
            )

        assert response.status_code == 200
        assert captured_args["username"] == "admin"
        assert captured_args["password"] == "secret123"

    def test_test_connection_invalid_url_scheme(self, client, mock_discovery_service):
        """AC1, AC3: Test rejection of non-RTSP URL schemes."""
        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            # HTTP URL should fail validation
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "http://192.168.1.100/stream"}
            )

        assert response.status_code == 422
        data = response.json()
        assert "rtsp://" in str(data["detail"]).lower() or "invalid" in str(data["detail"]).lower()

    def test_test_connection_rtsps_url_accepted(self, client, mock_discovery_service):
        """AC1: Test that rtsps:// URLs are accepted."""
        from app.schemas.discovery import TestConnectionResponse

        mock_result = TestConnectionResponse(
            success=True,
            latency_ms=300,
            resolution="1920x1080",
            fps=30,
            codec="H.265"
        )

        async def mock_test_connection(*args, **kwargs):
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "rtsps://192.168.1.100:322/secure_stream"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_test_connection_auth_failure(self, client, mock_discovery_service):
        """AC4: Test authentication failure error message."""
        from app.schemas.discovery import TestConnectionResponse

        mock_result = TestConnectionResponse(
            success=False,
            latency_ms=100,
            error="Authentication failed - check username/password"
        )

        async def mock_test_connection(*args, **kwargs):
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "rtsp://192.168.1.100:554/stream"}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert "Authentication failed" in data["error"]

    def test_test_connection_timeout(self, client, mock_discovery_service):
        """AC4, AC5: Test timeout error message."""
        from app.schemas.discovery import TestConnectionResponse

        mock_result = TestConnectionResponse(
            success=False,
            latency_ms=5000,
            error="Connection timed out after 5 seconds"
        )

        async def mock_test_connection(*args, **kwargs):
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "rtsp://192.168.1.100:554/stream"}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert "timed out" in data["error"].lower()

    def test_test_connection_host_unreachable(self, client, mock_discovery_service):
        """AC3, AC4: Test connection refused error message."""
        from app.schemas.discovery import TestConnectionResponse

        mock_result = TestConnectionResponse(
            success=False,
            latency_ms=50,
            error="Connection refused - host unreachable"
        )

        async def mock_test_connection(*args, **kwargs):
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "rtsp://10.0.0.1:554/stream"}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert "unreachable" in data["error"].lower() or "refused" in data["error"].lower()

    def test_test_connection_stream_not_found(self, client, mock_discovery_service):
        """AC4: Test stream not found error message."""
        from app.schemas.discovery import TestConnectionResponse

        mock_result = TestConnectionResponse(
            success=False,
            latency_ms=200,
            error="Stream not found - check RTSP path"
        )

        async def mock_test_connection(*args, **kwargs):
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "rtsp://192.168.1.100:554/invalid_path"}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_test_connection_missing_rtsp_url(self, client, mock_discovery_service):
        """AC1: Test validation error when rtsp_url is missing."""
        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={}  # Missing rtsp_url
            )

        assert response.status_code == 422

    def test_test_connection_password_not_in_response(self, client, mock_discovery_service):
        """AC1: Verify password is not included in response."""
        from app.schemas.discovery import TestConnectionResponse

        mock_result = TestConnectionResponse(
            success=True,
            latency_ms=200,
            resolution="1920x1080",
            fps=30
        )

        async def mock_test_connection(*args, **kwargs):
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={
                    "rtsp_url": "rtsp://192.168.1.100:554/stream",
                    "username": "admin",
                    "password": "supersecret123"
                }
            )

        assert response.status_code == 200
        response_text = response.text

        # Password should not appear in response
        assert "supersecret123" not in response_text
        assert "password" not in response_text.lower() or '"password":null' in response_text.lower()

    def test_test_connection_service_exception(self, client, mock_discovery_service):
        """Test error handling for service exceptions."""
        async def mock_test_connection(*args, **kwargs):
            raise Exception("Unexpected OpenCV error")

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "rtsp://192.168.1.100:554/stream"}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert data["error"] is not None


class TestTestConnectionResponseSchema:
    """Test TestConnectionResponse schema validation (P5-2.4)."""

    def test_response_includes_all_success_fields(self, client, mock_discovery_service):
        """AC2: Verify successful response includes all metadata fields."""
        from app.schemas.discovery import TestConnectionResponse

        mock_result = TestConnectionResponse(
            success=True,
            latency_ms=234,
            resolution="2560x1440",
            fps=25,
            codec="H.265",
            error=None
        )

        async def mock_test_connection(*args, **kwargs):
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "rtsp://192.168.1.100:554/stream"}
            )

        assert response.status_code == 200
        data = response.json()

        # Check all expected fields
        assert "success" in data
        assert "latency_ms" in data
        assert "resolution" in data
        assert "fps" in data
        assert "codec" in data
        assert "error" in data

        # Verify values
        assert data["success"] is True
        assert isinstance(data["latency_ms"], int)
        assert data["latency_ms"] > 0
        assert "x" in data["resolution"]
        assert isinstance(data["fps"], int)
        assert data["codec"] in ["H.264", "H.265", "MJPEG", None]

    def test_response_includes_all_failure_fields(self, client, mock_discovery_service):
        """AC3, AC4: Verify failure response includes error message."""
        from app.schemas.discovery import TestConnectionResponse

        mock_result = TestConnectionResponse(
            success=False,
            latency_ms=100,
            resolution=None,
            fps=None,
            codec=None,
            error="Connection refused - host unreachable"
        )

        async def mock_test_connection(*args, **kwargs):
            return mock_result

        mock_discovery_service.test_connection = mock_test_connection

        with patch(
            'app.services.service_container.get_onvif_discovery_service',
            return_value=mock_discovery_service
        ):
            response = client.post(
                "/api/v1/cameras/discover/test",
                json={"rtsp_url": "rtsp://10.0.0.1:554/stream"}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert data["error"] is not None
        assert data["resolution"] is None
        assert data["fps"] is None
        assert data["codec"] is None
