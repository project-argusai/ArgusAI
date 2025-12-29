"""
Unit tests for ProtectService (Story P14-3.1)

Tests the UniFi Protect controller connection management, WebSocket lifecycle,
camera discovery, and event handling functionality.
"""
import pytest
import asyncio
import ssl
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from dataclasses import dataclass

import aiohttp
from uiprotect.exceptions import BadRequest, NotAuthorized, NvrError

from app.services.protect_service import (
    ProtectService,
    ConnectionTestResult,
    DiscoveredCamera,
    CameraDiscoveryResult,
    get_protect_service,
    CONNECTION_TIMEOUT,
    BACKOFF_DELAYS,
    CAMERA_CACHE_TTL_SECONDS,
    CAMERA_STATUS_DEBOUNCE_SECONDS,
    PROTECT_CONNECTION_STATUS,
    CAMERA_STATUS_CHANGED,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def protect_service():
    """Create a fresh ProtectService instance for testing."""
    return ProtectService()


@pytest.fixture
def mock_protect_client():
    """Create a mock ProtectApiClient."""
    with patch('app.services.protect_service.ProtectApiClient') as mock_class:
        mock_client = AsyncMock()
        mock_class.return_value = mock_client

        # Default successful bootstrap
        mock_bootstrap = MagicMock()
        mock_bootstrap.nvr = MagicMock()
        mock_bootstrap.nvr.version = "3.0.22"
        mock_bootstrap.cameras = {}
        mock_client.bootstrap = mock_bootstrap

        yield mock_client


@pytest.fixture
def mock_websocket_manager():
    """Mock the WebSocket manager for broadcast verification."""
    with patch('app.services.protect_service.get_websocket_manager') as mock_get:
        mock_manager = AsyncMock()
        mock_get.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def mock_event_handler():
    """Mock the protect event handler."""
    with patch('app.services.protect_service.get_protect_event_handler') as mock_get:
        mock_handler = AsyncMock()
        mock_get.return_value = mock_handler
        yield mock_handler


@pytest.fixture
def mock_db_session():
    """Mock database session for state updates."""
    with patch('app.services.protect_service.get_db_session') as mock_get:
        mock_session = MagicMock()
        mock_get.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get.return_value.__exit__ = Mock(return_value=False)
        yield mock_session


@pytest.fixture
def mock_controller():
    """Create a mock ProtectController model."""
    controller = MagicMock()
    controller.id = "test-controller-123"
    controller.name = "Test Controller"
    controller.host = "192.168.1.1"
    controller.port = 443
    controller.username = "admin"
    controller.verify_ssl = False
    controller.get_decrypted_password.return_value = "test_password"
    return controller


@pytest.fixture
def mock_camera():
    """Create a mock camera object from uiprotect."""
    camera = MagicMock()
    camera.id = "cam-123"
    camera.name = "Front Door"
    camera.type = "camera"
    camera.model = "G4 Pro"
    camera.is_connected = True
    camera.can_detect_person = True
    camera.can_detect_vehicle = True
    camera.can_detect_package = False
    camera.can_detect_animal = False
    camera.feature_flags = MagicMock()
    camera.feature_flags.has_chime = False
    camera.feature_flags.is_doorbell = False
    return camera


@pytest.fixture
def mock_doorbell():
    """Create a mock doorbell camera from uiprotect."""
    doorbell = MagicMock()
    doorbell.id = "doorbell-456"
    doorbell.name = "Front Doorbell"
    doorbell.type = "doorbell"
    doorbell.model = "G4 Doorbell Pro"
    doorbell.is_connected = True
    doorbell.can_detect_person = True
    doorbell.can_detect_vehicle = False
    doorbell.can_detect_package = True
    doorbell.can_detect_animal = False
    doorbell.feature_flags = MagicMock()
    doorbell.feature_flags.has_chime = True
    doorbell.feature_flags.is_doorbell = True
    return doorbell


# =============================================================================
# Test: Service Initialization
# =============================================================================

class TestProtectServiceInit:
    """Tests for ProtectService initialization."""

    def test_init_default_state(self, protect_service):
        """Test service initializes with empty connection tracking."""
        assert len(protect_service._connections) == 0
        assert len(protect_service._listener_tasks) == 0
        assert protect_service._shutdown_event.is_set() is False
        assert len(protect_service._camera_cache) == 0
        assert len(protect_service._camera_status_broadcast_times) == 0
        assert len(protect_service._last_camera_status) == 0

    def test_constants_defined(self):
        """Test service constants are defined correctly."""
        assert CONNECTION_TIMEOUT == 10.0
        assert BACKOFF_DELAYS == [1, 2, 4, 8, 16, 30]
        assert CAMERA_CACHE_TTL_SECONDS == 60
        assert CAMERA_STATUS_DEBOUNCE_SECONDS == 5

    def test_get_protect_service_singleton(self):
        """Test get_protect_service returns singleton instance."""
        service1 = get_protect_service()
        service2 = get_protect_service()
        assert service1 is service2


# =============================================================================
# Test: test_connection Method
# =============================================================================

class TestConnectionTest:
    """Tests for test_connection method."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, protect_service):
        """Test successful connection returns firmware version and camera count."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client

            # Setup bootstrap with cameras
            mock_bootstrap = MagicMock()
            mock_bootstrap.nvr = MagicMock()
            mock_bootstrap.nvr.version = "3.0.22"
            mock_bootstrap.cameras = {"cam1": MagicMock(), "cam2": MagicMock()}
            mock_client.bootstrap = mock_bootstrap

            result = await protect_service.test_connection(
                host="192.168.1.1",
                port=443,
                username="admin",
                password="password",
                verify_ssl=False
            )

            assert result.success is True
            assert result.message == "Connected successfully"
            assert result.firmware_version == "3.0.22"
            assert result.camera_count == 2
            assert result.error_type is None

            # Verify client was closed
            mock_client.close_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_connection_timeout(self, protect_service):
        """Test timeout returns error with timeout type."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_client.update = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_class.return_value = mock_client

            result = await protect_service.test_connection(
                host="192.168.1.1",
                port=443,
                username="admin",
                password="password"
            )

            assert result.success is False
            assert "timed out" in result.message.lower()
            assert result.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_test_connection_not_authorized(self, protect_service):
        """Test NotAuthorized exception returns auth_error type."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_client.update = AsyncMock(side_effect=NotAuthorized("Invalid credentials"))
            mock_class.return_value = mock_client

            result = await protect_service.test_connection(
                host="192.168.1.1",
                port=443,
                username="admin",
                password="wrong_password"
            )

            assert result.success is False
            assert result.message == "Authentication failed"
            assert result.error_type == "auth_error"

    @pytest.mark.asyncio
    async def test_test_connection_ssl_certificate_error(self, protect_service):
        """Test SSL certificate error returns ssl_error type."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_client.update = AsyncMock(
                side_effect=aiohttp.ClientConnectorCertificateError(
                    Mock(), Exception("Certificate error")
                )
            )
            mock_class.return_value = mock_client

            result = await protect_service.test_connection(
                host="192.168.1.1",
                port=443,
                username="admin",
                password="password",
                verify_ssl=True
            )

            assert result.success is False
            assert "ssl" in result.message.lower()
            assert result.error_type == "ssl_error"

    @pytest.mark.asyncio
    async def test_test_connection_ssl_error(self, protect_service):
        """Test SSLError returns ssl_error type."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_client.update = AsyncMock(
                side_effect=ssl.SSLError("certificate verify failed")
            )
            mock_class.return_value = mock_client

            result = await protect_service.test_connection(
                host="192.168.1.1",
                port=443,
                username="admin",
                password="password"
            )

            assert result.success is False
            assert result.error_type == "ssl_error"

    @pytest.mark.asyncio
    async def test_test_connection_host_unreachable(self, protect_service):
        """Test ClientConnectorError returns connection_error type."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            # Create a proper OSError for ClientConnectorError
            os_error = OSError(111, "Connection refused")
            mock_client.update = AsyncMock(
                side_effect=aiohttp.ClientConnectorError(
                    Mock(), os_error
                )
            )
            mock_class.return_value = mock_client

            result = await protect_service.test_connection(
                host="192.168.1.99",
                port=443,
                username="admin",
                password="password"
            )

            assert result.success is False
            assert "unreachable" in result.message.lower()
            assert result.error_type == "connection_error"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exception,expected_type", [
        (BadRequest("Invalid request"), "nvr_error"),
        (NvrError("NVR error"), "nvr_error"),
    ])
    async def test_test_connection_nvr_errors(self, protect_service, exception, expected_type):
        """Test BadRequest and NvrError return nvr_error type."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_client.update = AsyncMock(side_effect=exception)
            mock_class.return_value = mock_client

            result = await protect_service.test_connection(
                host="192.168.1.1",
                port=443,
                username="admin",
                password="password"
            )

            assert result.success is False
            assert result.error_type == expected_type

    @pytest.mark.asyncio
    async def test_test_connection_unknown_error(self, protect_service):
        """Test unknown exception returns unknown error type."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_client.update = AsyncMock(side_effect=RuntimeError("Unknown error"))
            mock_class.return_value = mock_client

            result = await protect_service.test_connection(
                host="192.168.1.1",
                port=443,
                username="admin",
                password="password"
            )

            assert result.success is False
            assert result.error_type == "unknown"

    @pytest.mark.asyncio
    async def test_test_connection_closes_client_on_error(self, protect_service):
        """Test client is closed even when connection fails."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_client.update = AsyncMock(side_effect=NotAuthorized("Invalid"))
            mock_class.return_value = mock_client

            await protect_service.test_connection(
                host="192.168.1.1",
                port=443,
                username="admin",
                password="password"
            )

            mock_client.close_session.assert_called_once()


# =============================================================================
# Test: Connection Lifecycle (connect, disconnect)
# =============================================================================

class TestConnectionLifecycle:
    """Tests for connect and disconnect methods."""

    @pytest.mark.asyncio
    async def test_connect_success(self, protect_service, mock_controller, mock_websocket_manager):
        """Test successful connection stores client and broadcasts status."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client
            mock_client.bootstrap = MagicMock()

            with patch.object(protect_service, '_update_controller_state', new_callable=AsyncMock):
                result = await protect_service.connect(mock_controller)

                assert result is True
                assert str(mock_controller.id) in protect_service._connections
                assert str(mock_controller.id) in protect_service._listener_tasks

                # Verify status broadcasts
                calls = mock_websocket_manager.broadcast.call_args_list
                assert len(calls) >= 2

                # First call should be "connecting"
                first_msg = calls[0][0][0]
                assert first_msg["type"] == PROTECT_CONNECTION_STATUS
                assert first_msg["data"]["status"] == "connecting"

                # Second call should be "connected"
                second_msg = calls[1][0][0]
                assert second_msg["data"]["status"] == "connected"

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, protect_service, mock_controller):
        """Test connecting already connected controller returns True immediately."""
        controller_id = str(mock_controller.id)
        protect_service._connections[controller_id] = MagicMock()

        result = await protect_service.connect(mock_controller)

        assert result is True

    @pytest.mark.asyncio
    async def test_connect_timeout(self, protect_service, mock_controller, mock_websocket_manager):
        """Test connection timeout updates state and broadcasts error."""
        with patch('app.services.protect_service.ProtectApiClient') as mock_class:
            mock_client = AsyncMock()
            mock_client.update = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_class.return_value = mock_client

            with patch.object(protect_service, '_update_controller_state', new_callable=AsyncMock) as mock_update:
                result = await protect_service.connect(mock_controller)

                assert result is False

                # Verify state update with error
                mock_update.assert_called()
                call_kwargs = mock_update.call_args_list[-1][1]
                assert call_kwargs['is_connected'] is False
                assert 'timed out' in call_kwargs['last_error'].lower()

    @pytest.mark.asyncio
    async def test_disconnect_success(self, protect_service, mock_websocket_manager):
        """Test disconnect removes client, cancels task, updates state."""
        controller_id = "test-controller-123"

        # Setup connected state
        mock_client = AsyncMock()
        protect_service._connections[controller_id] = mock_client

        # Create a mock task that behaves like a cancelled asyncio.Task
        # Using MagicMock for synchronous attributes and make it awaitable
        mock_task = MagicMock()
        mock_task.done.return_value = True  # Already done - avoids wait_for
        mock_task.cancel = MagicMock()
        protect_service._listener_tasks[controller_id] = mock_task

        with patch.object(protect_service, '_update_controller_state', new_callable=AsyncMock):
            await protect_service.disconnect(controller_id)

            assert controller_id not in protect_service._connections
            assert controller_id not in protect_service._listener_tasks
            mock_client.close_session.assert_called_once()

            # Verify disconnected broadcast
            disconnect_msg = mock_websocket_manager.broadcast.call_args[0][0]
            assert disconnect_msg["data"]["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self, protect_service, mock_websocket_manager):
        """Test disconnect on non-connected controller is no-op."""
        with patch.object(protect_service, '_update_controller_state', new_callable=AsyncMock):
            await protect_service.disconnect("non-existent-controller")

            # Should still broadcast disconnected status
            mock_websocket_manager.broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_all(self, protect_service, mock_websocket_manager):
        """Test disconnect_all disconnects all controllers."""
        # Setup two connected controllers
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
        protect_service._connections["ctrl-1"] = mock_client1
        protect_service._connections["ctrl-2"] = mock_client2

        mock_task1 = MagicMock()
        mock_task1.done.return_value = True
        mock_task2 = MagicMock()
        mock_task2.done.return_value = True
        protect_service._listener_tasks["ctrl-1"] = mock_task1
        protect_service._listener_tasks["ctrl-2"] = mock_task2

        with patch.object(protect_service, '_update_controller_state', new_callable=AsyncMock):
            await protect_service.disconnect_all()

            assert protect_service._shutdown_event.is_set()
            assert len(protect_service._connections) == 0
            assert len(protect_service._listener_tasks) == 0


# =============================================================================
# Test: Exponential Backoff
# =============================================================================

class TestExponentialBackoff:
    """Tests for exponential backoff delay calculation."""

    @pytest.mark.parametrize("attempt,expected_delay", [
        (0, 1),
        (1, 2),
        (2, 4),
        (3, 8),
        (4, 16),
        (5, 30),
        (6, 30),  # Max delay
        (10, 30),  # Still max
    ])
    def test_backoff_delay_calculation(self, attempt, expected_delay):
        """Test exponential backoff uses correct delays from BACKOFF_DELAYS."""
        delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
        assert delay == expected_delay

    def test_backoff_delays_constant(self):
        """Test BACKOFF_DELAYS constant values."""
        assert BACKOFF_DELAYS == [1, 2, 4, 8, 16, 30]


# =============================================================================
# Test: Camera Discovery
# =============================================================================

class TestCameraDiscovery:
    """Tests for camera discovery functionality."""

    @pytest.mark.asyncio
    async def test_discover_cameras_success(self, protect_service, mock_camera, mock_doorbell):
        """Test successful camera discovery returns DiscoveredCamera list."""
        controller_id = "test-controller-123"

        # Setup connected client with cameras
        mock_client = MagicMock()
        mock_bootstrap = MagicMock()
        mock_bootstrap.cameras = {
            "cam1": mock_camera,
            "cam2": mock_doorbell
        }
        mock_client.bootstrap = mock_bootstrap
        protect_service._connections[controller_id] = mock_client

        result = await protect_service.discover_cameras(controller_id)

        assert result.cached is False
        assert len(result.cameras) == 2
        assert result.warning is None

        # Verify camera properties
        cam = next(c for c in result.cameras if c.protect_camera_id == "cam-123")
        assert cam.name == "Front Door"
        assert cam.is_doorbell is False
        assert "person" in cam.smart_detection_capabilities
        assert "vehicle" in cam.smart_detection_capabilities

        # Verify doorbell identified
        doorbell = next(c for c in result.cameras if c.protect_camera_id == "doorbell-456")
        assert doorbell.is_doorbell is True
        assert doorbell.type == "doorbell"

    @pytest.mark.asyncio
    async def test_discover_cameras_cache_hit(self, protect_service):
        """Test cache returns results within TTL."""
        controller_id = "test-controller-123"

        # Pre-populate cache
        cached_cameras = [
            DiscoveredCamera(
                protect_camera_id="cached-cam",
                name="Cached Camera",
                type="camera",
                model="G4 Pro",
                is_online=True,
                is_doorbell=False,
                smart_detection_capabilities=["person"]
            )
        ]
        cached_at = datetime.now(timezone.utc)
        protect_service._camera_cache[controller_id] = (cached_cameras, cached_at)

        result = await protect_service.discover_cameras(controller_id)

        assert result.cached is True
        assert result.cached_at == cached_at
        assert len(result.cameras) == 1
        assert result.cameras[0].name == "Cached Camera"

    @pytest.mark.asyncio
    async def test_discover_cameras_cache_expired(self, protect_service, mock_camera):
        """Test expired cache fetches fresh data."""
        controller_id = "test-controller-123"

        # Pre-populate expired cache
        old_cameras = [
            DiscoveredCamera(
                protect_camera_id="old-cam",
                name="Old Camera",
                type="camera",
                model="G3",
                is_online=True,
                is_doorbell=False
            )
        ]
        expired_time = datetime.now(timezone.utc) - timedelta(seconds=CAMERA_CACHE_TTL_SECONDS + 10)
        protect_service._camera_cache[controller_id] = (old_cameras, expired_time)

        # Setup connected client
        mock_client = MagicMock()
        mock_bootstrap = MagicMock()
        mock_bootstrap.cameras = {"cam1": mock_camera}
        mock_client.bootstrap = mock_bootstrap
        protect_service._connections[controller_id] = mock_client

        result = await protect_service.discover_cameras(controller_id)

        assert result.cached is False
        assert result.cameras[0].name == "Front Door"  # Fresh data

    @pytest.mark.asyncio
    async def test_discover_cameras_not_connected(self, protect_service):
        """Test not connected returns empty with warning when no cache."""
        result = await protect_service.discover_cameras("not-connected-controller")

        assert len(result.cameras) == 0
        assert result.cached is False
        assert result.warning is not None
        assert "not connected" in result.warning.lower()

    @pytest.mark.asyncio
    async def test_discover_cameras_not_connected_with_cache(self, protect_service):
        """Test not connected returns cached results with warning."""
        controller_id = "cached-controller"

        # Pre-populate cache
        cached_cameras = [
            DiscoveredCamera(
                protect_camera_id="cached-cam",
                name="Cached Camera",
                type="camera",
                model="G4 Pro",
                is_online=True,
                is_doorbell=False
            )
        ]
        cached_at = datetime.now(timezone.utc) - timedelta(seconds=120)  # Stale
        protect_service._camera_cache[controller_id] = (cached_cameras, cached_at)

        result = await protect_service.discover_cameras(controller_id)

        assert result.cached is True
        assert len(result.cameras) == 1
        assert result.warning is not None
        assert "not connected" in result.warning.lower()

    @pytest.mark.asyncio
    async def test_discover_cameras_force_refresh(self, protect_service, mock_camera):
        """Test force_refresh bypasses cache."""
        controller_id = "test-controller-123"

        # Pre-populate fresh cache (should be bypassed)
        cached_cameras = [
            DiscoveredCamera(
                protect_camera_id="cached-cam",
                name="Cached Camera",
                type="camera",
                model="G3",
                is_online=True,
                is_doorbell=False
            )
        ]
        cached_at = datetime.now(timezone.utc)  # Fresh cache
        protect_service._camera_cache[controller_id] = (cached_cameras, cached_at)

        # Setup connected client
        mock_client = MagicMock()
        mock_bootstrap = MagicMock()
        mock_bootstrap.cameras = {"cam1": mock_camera}
        mock_client.bootstrap = mock_bootstrap
        protect_service._connections[controller_id] = mock_client

        result = await protect_service.discover_cameras(controller_id, force_refresh=True)

        assert result.cached is False
        assert result.cameras[0].name == "Front Door"  # Fresh, not cached

    @pytest.mark.asyncio
    async def test_discover_cameras_error_fallback_to_cache(self, protect_service):
        """Test discovery error falls back to cached results."""
        controller_id = "test-controller-123"

        # Pre-populate cache
        cached_cameras = [
            DiscoveredCamera(
                protect_camera_id="cached-cam",
                name="Cached Camera",
                type="camera",
                model="G4 Pro",
                is_online=True,
                is_doorbell=False
            )
        ]
        cached_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        protect_service._camera_cache[controller_id] = (cached_cameras, cached_at)

        # Setup client that throws error when accessing bootstrap.cameras
        mock_client = MagicMock()
        mock_bootstrap = MagicMock()
        mock_bootstrap.cameras = MagicMock()
        # Make cameras.values() raise an exception
        mock_bootstrap.cameras.values.side_effect = RuntimeError("Connection lost")
        mock_client.bootstrap = mock_bootstrap
        protect_service._connections[controller_id] = mock_client

        result = await protect_service.discover_cameras(controller_id, force_refresh=True)

        # Should return cached results with warning
        assert result.cached is True
        assert len(result.cameras) == 1
        assert result.warning is not None


# =============================================================================
# Test: Doorbell Detection
# =============================================================================

class TestDoorbellDetection:
    """Tests for doorbell camera identification."""

    def test_is_doorbell_by_type(self, protect_service):
        """Test doorbell detected from type field."""
        camera = MagicMock()
        camera.type = "doorbell"
        camera.model = "some model"
        camera.feature_flags = None

        assert protect_service._is_doorbell_camera(camera) is True

    def test_is_doorbell_by_model(self, protect_service):
        """Test doorbell detected from model field."""
        camera = MagicMock()
        camera.type = "camera"
        camera.model = "G4 Doorbell Pro"
        camera.feature_flags = None

        assert protect_service._is_doorbell_camera(camera) is True

    def test_is_doorbell_by_has_chime(self, protect_service):
        """Test doorbell detected from has_chime feature flag."""
        camera = MagicMock()
        camera.type = "camera"
        camera.model = "some model"
        camera.feature_flags = MagicMock()
        camera.feature_flags.has_chime = True
        camera.feature_flags.is_doorbell = False

        assert protect_service._is_doorbell_camera(camera) is True

    def test_is_doorbell_by_is_doorbell_flag(self, protect_service):
        """Test doorbell detected from is_doorbell feature flag."""
        camera = MagicMock()
        camera.type = "camera"
        camera.model = "some model"
        camera.feature_flags = MagicMock()
        camera.feature_flags.has_chime = False
        camera.feature_flags.is_doorbell = True

        assert protect_service._is_doorbell_camera(camera) is True

    def test_is_not_doorbell(self, protect_service):
        """Test regular camera is not identified as doorbell."""
        camera = MagicMock()
        camera.type = "camera"
        camera.model = "G4 Pro"
        camera.feature_flags = MagicMock()
        camera.feature_flags.has_chime = False
        camera.feature_flags.is_doorbell = False

        assert protect_service._is_doorbell_camera(camera) is False


# =============================================================================
# Test: Smart Detection Capabilities
# =============================================================================

class TestSmartDetectionCapabilities:
    """Tests for smart detection capability extraction."""

    def test_get_smart_detection_person_vehicle(self, protect_service):
        """Test extracting person and vehicle capabilities."""
        camera = MagicMock()
        camera.can_detect_person = True
        camera.can_detect_vehicle = True
        camera.can_detect_package = False
        camera.can_detect_animal = False
        camera.feature_flags = None

        capabilities = protect_service._get_smart_detection_capabilities(camera)

        assert "person" in capabilities
        assert "vehicle" in capabilities
        assert "package" not in capabilities
        assert "animal" not in capabilities

    def test_get_smart_detection_all(self, protect_service):
        """Test extracting all detection capabilities."""
        camera = MagicMock()
        camera.can_detect_person = True
        camera.can_detect_vehicle = True
        camera.can_detect_package = True
        camera.can_detect_animal = True
        camera.feature_flags = None

        capabilities = protect_service._get_smart_detection_capabilities(camera)

        assert set(capabilities) == {"person", "vehicle", "package", "animal"}

    def test_get_smart_detection_from_feature_flags(self, protect_service):
        """Test extracting capabilities from feature flags fallback."""
        camera = MagicMock()
        camera.can_detect_person = False
        camera.can_detect_vehicle = False
        camera.can_detect_package = False
        camera.can_detect_animal = False
        camera.feature_flags = MagicMock()
        camera.feature_flags.can_detect_person = True
        camera.feature_flags.can_detect_vehicle = True
        camera.feature_flags.has_smart_detect = False

        capabilities = protect_service._get_smart_detection_capabilities(camera)

        assert "person" in capabilities
        assert "vehicle" in capabilities

    def test_get_smart_detection_generic_motion(self, protect_service):
        """Test generic motion capability when has_smart_detect but no specifics."""
        camera = MagicMock()
        camera.can_detect_person = False
        camera.can_detect_vehicle = False
        camera.can_detect_package = False
        camera.can_detect_animal = False
        camera.feature_flags = MagicMock()
        camera.feature_flags.can_detect_person = False
        camera.feature_flags.can_detect_vehicle = False
        camera.feature_flags.has_smart_detect = True

        capabilities = protect_service._get_smart_detection_capabilities(camera)

        assert "motion" in capabilities


# =============================================================================
# Test: Camera Status Debounce
# =============================================================================

class TestCameraStatusDebounce:
    """Tests for camera status change debouncing."""

    def test_should_broadcast_first_time(self, protect_service):
        """Test first broadcast for camera is always allowed."""
        result = protect_service._should_broadcast_camera_status("new-camera")
        assert result is True

    def test_should_broadcast_after_debounce_window(self, protect_service):
        """Test broadcast allowed after debounce window expires."""
        camera_id = "test-camera"
        old_time = datetime.now(timezone.utc) - timedelta(seconds=CAMERA_STATUS_DEBOUNCE_SECONDS + 1)
        protect_service._camera_status_broadcast_times[camera_id] = old_time

        result = protect_service._should_broadcast_camera_status(camera_id)
        assert result is True

    def test_should_not_broadcast_within_debounce_window(self, protect_service):
        """Test broadcast blocked within debounce window."""
        camera_id = "test-camera"
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=1)
        protect_service._camera_status_broadcast_times[camera_id] = recent_time

        result = protect_service._should_broadcast_camera_status(camera_id)
        assert result is False


# =============================================================================
# Test: WebSocket Event Handling
# =============================================================================

class TestWebSocketEventHandling:
    """Tests for WebSocket event handling."""

    @pytest.mark.asyncio
    async def test_handle_websocket_event_camera_status_change(
        self, protect_service, mock_websocket_manager
    ):
        """Test camera status change broadcasts to frontend."""
        controller_id = "test-controller"

        # Create mock WebSocket message
        mock_msg = MagicMock()
        mock_msg.action = "update"
        mock_new_obj = MagicMock()
        mock_new_obj.id = "cam-123"
        mock_new_obj.is_connected = False
        mock_msg.new_obj = mock_new_obj
        type(mock_new_obj).__name__ = "Camera"

        # Set initial status as True so change is detected
        protect_service._last_camera_status["cam-123"] = True

        await protect_service._handle_websocket_event(controller_id, mock_msg)

        # Verify broadcast
        mock_websocket_manager.broadcast.assert_called_once()
        msg = mock_websocket_manager.broadcast.call_args[0][0]
        assert msg["type"] == CAMERA_STATUS_CHANGED
        assert msg["data"]["camera_id"] == "cam-123"
        assert msg["data"]["is_online"] is False

    @pytest.mark.asyncio
    async def test_handle_websocket_event_no_status_change(
        self, protect_service, mock_websocket_manager
    ):
        """Test no broadcast when status hasn't changed."""
        controller_id = "test-controller"

        mock_msg = MagicMock()
        mock_msg.action = "update"
        mock_new_obj = MagicMock()
        mock_new_obj.id = "cam-123"
        mock_new_obj.is_connected = True
        mock_msg.new_obj = mock_new_obj
        type(mock_new_obj).__name__ = "Camera"

        # Same status as before
        protect_service._last_camera_status["cam-123"] = True

        await protect_service._handle_websocket_event(controller_id, mock_msg)

        mock_websocket_manager.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_websocket_event_debounced(
        self, protect_service, mock_websocket_manager
    ):
        """Test rapid status changes are debounced."""
        controller_id = "test-controller"
        camera_id = "cam-123"

        # Set recent broadcast time
        protect_service._camera_status_broadcast_times[camera_id] = datetime.now(timezone.utc)
        protect_service._last_camera_status[camera_id] = True

        mock_msg = MagicMock()
        mock_msg.action = "update"
        mock_new_obj = MagicMock()
        mock_new_obj.id = camera_id
        mock_new_obj.is_connected = False
        mock_msg.new_obj = mock_new_obj
        type(mock_new_obj).__name__ = "Camera"

        await protect_service._handle_websocket_event(controller_id, mock_msg)

        # Should be debounced
        mock_websocket_manager.broadcast.assert_not_called()


# =============================================================================
# Test: Helper Methods
# =============================================================================

class TestHelperMethods:
    """Tests for helper methods."""

    def test_get_connection_status_connected(self, protect_service):
        """Test get_connection_status for connected controller."""
        controller_id = "test-controller"
        protect_service._connections[controller_id] = MagicMock()

        mock_task = MagicMock()
        mock_task.done.return_value = False
        protect_service._listener_tasks[controller_id] = mock_task

        status = protect_service.get_connection_status(controller_id)

        assert status["connected"] is True
        assert status["has_task"] is True

    def test_get_connection_status_not_connected(self, protect_service):
        """Test get_connection_status for non-connected controller."""
        status = protect_service.get_connection_status("not-connected")

        assert status["connected"] is False
        assert status["has_task"] is False

    def test_get_all_connection_statuses(self, protect_service):
        """Test get_all_connection_statuses returns all tracked controllers."""
        protect_service._connections["ctrl-1"] = MagicMock()
        protect_service._connections["ctrl-2"] = MagicMock()

        mock_task = MagicMock()
        mock_task.done.return_value = False
        protect_service._listener_tasks["ctrl-1"] = mock_task

        statuses = protect_service.get_all_connection_statuses()

        assert "ctrl-1" in statuses
        assert "ctrl-2" in statuses
        assert statuses["ctrl-1"]["connected"] is True
        assert statuses["ctrl-1"]["has_task"] is True
        assert statuses["ctrl-2"]["connected"] is True
        assert statuses["ctrl-2"]["has_task"] is False

    def test_clear_camera_cache_specific(self, protect_service):
        """Test clearing cache for specific controller."""
        protect_service._camera_cache["ctrl-1"] = ([], datetime.now(timezone.utc))
        protect_service._camera_cache["ctrl-2"] = ([], datetime.now(timezone.utc))

        protect_service.clear_camera_cache("ctrl-1")

        assert "ctrl-1" not in protect_service._camera_cache
        assert "ctrl-2" in protect_service._camera_cache

    def test_clear_camera_cache_all(self, protect_service):
        """Test clearing all cache entries."""
        protect_service._camera_cache["ctrl-1"] = ([], datetime.now(timezone.utc))
        protect_service._camera_cache["ctrl-2"] = ([], datetime.now(timezone.utc))

        protect_service.clear_camera_cache()

        assert len(protect_service._camera_cache) == 0


# =============================================================================
# Test: Camera Snapshot
# =============================================================================

class TestCameraSnapshot:
    """Tests for camera snapshot functionality."""

    @pytest.mark.asyncio
    async def test_get_camera_snapshot_success(self, protect_service):
        """Test successful snapshot retrieval."""
        controller_id = "test-controller"
        camera_id = "cam-123"

        mock_client = AsyncMock()
        mock_client.get_camera_snapshot = AsyncMock(return_value=b"fake_image_bytes")
        protect_service._connections[controller_id] = mock_client

        result = await protect_service.get_camera_snapshot(controller_id, camera_id)

        assert result == b"fake_image_bytes"
        mock_client.get_camera_snapshot.assert_called_once_with(
            camera_id=camera_id,
            width=640,
            height=None
        )

    @pytest.mark.asyncio
    async def test_get_camera_snapshot_not_connected(self, protect_service):
        """Test snapshot raises error when not connected."""
        with pytest.raises(ValueError, match="not connected"):
            await protect_service.get_camera_snapshot("not-connected", "cam-123")

    @pytest.mark.asyncio
    async def test_get_camera_snapshot_error(self, protect_service):
        """Test snapshot returns None on error."""
        controller_id = "test-controller"
        camera_id = "cam-123"

        mock_client = AsyncMock()
        mock_client.get_camera_snapshot = AsyncMock(side_effect=Exception("Snapshot failed"))
        protect_service._connections[controller_id] = mock_client

        result = await protect_service.get_camera_snapshot(controller_id, camera_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_camera_snapshot_custom_dimensions(self, protect_service):
        """Test snapshot with custom dimensions."""
        controller_id = "test-controller"
        camera_id = "cam-123"

        mock_client = AsyncMock()
        mock_client.get_camera_snapshot = AsyncMock(return_value=b"image")
        protect_service._connections[controller_id] = mock_client

        await protect_service.get_camera_snapshot(
            controller_id, camera_id, width=1920, height=1080
        )

        mock_client.get_camera_snapshot.assert_called_once_with(
            camera_id=camera_id,
            width=1920,
            height=1080
        )
