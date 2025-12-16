"""
Unit Tests for ONVIF WS-Discovery Service (Stories P5-2.1, P5-2.2)

Tests the ONVIFDiscoveryService for:
- WS-Discovery probe message generation (P5-2.1)
- Response parsing and device extraction (P5-2.1)
- Timeout behavior (P5-2.1)
- Deduplication of devices (P5-2.1)
- Cache behavior (P5-2.1)
- Error handling for malformed responses (P5-2.1)
- Device details retrieval via ONVIF SOAP (P5-2.2)
- Stream profile parsing (P5-2.2)
- Authentication error handling (P5-2.2)
"""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from typing import List

from app.schemas.discovery import (
    DiscoveredDevice,
    DeviceInfo,
    StreamProfile,
    DiscoveredCameraDetails,
)
from app.services.onvif_discovery_service import (
    ONVIFDiscoveryService,
    get_onvif_discovery_service,
    DiscoveryResult,
    DeviceDetailsResult,
    MULTICAST_GROUP,
    MULTICAST_PORT,
    DEFAULT_TIMEOUT,
    ONVIF_NVT_TYPE,
    DEVICE_QUERY_TIMEOUT,
)


class MockService:
    """Mock WS-Discovery service response."""

    def __init__(
        self,
        xaddrs: List[str],
        scopes: List[str] = None,
        types: List[str] = None,
        metadata_version: str = "1"
    ):
        self._xaddrs = xaddrs
        self._scopes = scopes or []
        self._types = types or [ONVIF_NVT_TYPE]
        self._metadata_version = metadata_version

    def getXAddrs(self):
        return self._xaddrs

    def getScopes(self):
        return self._scopes

    def getTypes(self):
        return self._types

    def getMetadataVersion(self):
        return self._metadata_version


class TestONVIFDiscoveryConstants:
    """Test discovery constants are correctly defined."""

    def test_multicast_group(self):
        """AC1: Verify multicast group is standard WS-Discovery address."""
        assert MULTICAST_GROUP == "239.255.255.250"

    def test_multicast_port(self):
        """AC1: Verify multicast port is standard WS-Discovery port."""
        assert MULTICAST_PORT == 3702

    def test_default_timeout(self):
        """AC2: Verify default timeout is 10 seconds per PRD."""
        assert DEFAULT_TIMEOUT == 10

    def test_onvif_nvt_type(self):
        """AC1: Verify ONVIF NVT type for camera targeting."""
        assert "NetworkVideoTransmitter" in ONVIF_NVT_TYPE


class TestONVIFDiscoveryServiceInit:
    """Test service initialization."""

    def test_create_service(self):
        """Test service can be instantiated."""
        service = ONVIFDiscoveryService()
        assert service is not None

    def test_singleton_instance(self):
        """Test get_onvif_discovery_service returns singleton."""
        service1 = get_onvif_discovery_service()
        service2 = get_onvif_discovery_service()
        assert service1 is service2

    def test_cache_initialized_empty(self):
        """Test cache is initially empty."""
        service = ONVIFDiscoveryService()
        assert service._cached_devices == []
        assert service._last_discovery_time is None


class TestDiscoveryServiceAvailability:
    """Test service availability checks."""

    def test_is_available_property(self):
        """Test is_available reflects library availability."""
        service = ONVIFDiscoveryService()
        # This depends on whether WSDiscovery is installed
        # At minimum, property should be accessible
        assert isinstance(service.is_available, bool)


class TestSyncDiscovery:
    """Test synchronous discovery method with mocked WS-Discovery.

    These tests require WSDiscovery to be installed. They are skipped
    if the library is not available.
    """

    @pytest.fixture(autouse=True)
    def check_wsdiscovery(self):
        """Skip tests if WSDiscovery not installed."""
        from app.services.onvif_discovery_service import WSDISCOVERY_AVAILABLE
        if not WSDISCOVERY_AVAILABLE:
            pytest.skip("WSDiscovery library not installed")

    def test_discover_single_camera(self):
        """AC4: Test discovery returns single camera correctly."""
        from app.services.onvif_discovery_service import ThreadedWSDiscovery

        with patch.object(ThreadedWSDiscovery, '__init__', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'start', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'stop', return_value=None):

            mock_service = MockService(
                xaddrs=["http://192.168.1.100:80/onvif/device_service"],
                scopes=["onvif://www.onvif.org/type/NetworkVideoTransmitter"],
                types=["tdn:NetworkVideoTransmitter"]
            )

            with patch.object(ThreadedWSDiscovery, 'searchServices', return_value=[mock_service]):
                service = ONVIFDiscoveryService()
                devices = service._sync_discover(timeout=5)

                assert len(devices) == 1
                assert devices[0].endpoint_url == "http://192.168.1.100:80/onvif/device_service"
                assert "onvif://www.onvif.org/type/NetworkVideoTransmitter" in devices[0].scopes

    def test_discover_multiple_cameras(self):
        """AC3: Test discovery handles multiple cameras."""
        from app.services.onvif_discovery_service import ThreadedWSDiscovery

        with patch.object(ThreadedWSDiscovery, '__init__', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'start', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'stop', return_value=None):

            mock_services = [
                MockService(xaddrs=["http://192.168.1.100:80/onvif/device_service"]),
                MockService(xaddrs=["http://192.168.1.101:80/onvif/device_service"]),
                MockService(xaddrs=["http://192.168.1.102:80/onvif/device_service"]),
            ]

            with patch.object(ThreadedWSDiscovery, 'searchServices', return_value=mock_services):
                service = ONVIFDiscoveryService()
                devices = service._sync_discover(timeout=5)

                assert len(devices) == 3
                urls = [d.endpoint_url for d in devices]
                assert "http://192.168.1.100:80/onvif/device_service" in urls
                assert "http://192.168.1.101:80/onvif/device_service" in urls
                assert "http://192.168.1.102:80/onvif/device_service" in urls

    def test_discover_deduplicates_same_endpoint(self):
        """AC3: Test deduplication of devices found on multiple interfaces."""
        from app.services.onvif_discovery_service import ThreadedWSDiscovery

        with patch.object(ThreadedWSDiscovery, '__init__', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'start', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'stop', return_value=None):

            # Same camera responding twice (from different interfaces)
            same_url = "http://192.168.1.100:80/onvif/device_service"
            mock_services = [
                MockService(xaddrs=[same_url]),
                MockService(xaddrs=[same_url]),  # Duplicate
            ]

            with patch.object(ThreadedWSDiscovery, 'searchServices', return_value=mock_services):
                service = ONVIFDiscoveryService()
                devices = service._sync_discover(timeout=5)

                # Should only have one device after deduplication
                assert len(devices) == 1
                assert devices[0].endpoint_url == same_url

    def test_discover_empty_response(self):
        """AC2: Test graceful handling of no responses."""
        from app.services.onvif_discovery_service import ThreadedWSDiscovery

        with patch.object(ThreadedWSDiscovery, '__init__', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'start', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'stop', return_value=None):

            with patch.object(ThreadedWSDiscovery, 'searchServices', return_value=[]):
                service = ONVIFDiscoveryService()
                devices = service._sync_discover(timeout=5)

                assert devices == []

    def test_discover_skips_empty_xaddrs(self):
        """AC3: Test devices with no XAddrs are skipped."""
        from app.services.onvif_discovery_service import ThreadedWSDiscovery

        with patch.object(ThreadedWSDiscovery, '__init__', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'start', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'stop', return_value=None):

            mock_services = [
                MockService(xaddrs=[]),  # No XAddrs
                MockService(xaddrs=["http://192.168.1.100:80/onvif/device_service"]),
            ]

            with patch.object(ThreadedWSDiscovery, 'searchServices', return_value=mock_services):
                service = ONVIFDiscoveryService()
                devices = service._sync_discover(timeout=5)

                assert len(devices) == 1

    def test_discover_handles_malformed_service(self):
        """AC3: Test graceful handling of malformed responses."""
        from app.services.onvif_discovery_service import ThreadedWSDiscovery

        with patch.object(ThreadedWSDiscovery, '__init__', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'start', return_value=None), \
             patch.object(ThreadedWSDiscovery, 'stop', return_value=None):

            # Service that raises exception on getXAddrs
            bad_service = MagicMock()
            bad_service.getXAddrs.side_effect = Exception("Malformed response")

            good_service = MockService(
                xaddrs=["http://192.168.1.100:80/onvif/device_service"]
            )

            with patch.object(ThreadedWSDiscovery, 'searchServices', return_value=[bad_service, good_service]):
                service = ONVIFDiscoveryService()
                devices = service._sync_discover(timeout=5)

                # Should still get the good device
                assert len(devices) == 1
                assert devices[0].endpoint_url == "http://192.168.1.100:80/onvif/device_service"


class TestAsyncDiscovery:
    """Test async discovery methods."""

    @pytest.mark.asyncio
    @patch('app.services.onvif_discovery_service.WSDISCOVERY_AVAILABLE', True)
    async def test_discover_cameras_with_result(self):
        """AC4, AC5: Test discover_cameras_with_result returns DiscoveryResult."""
        service = ONVIFDiscoveryService()

        # Mock _sync_discover
        with patch.object(service, '_sync_discover', return_value=[]):
            result = await service.discover_cameras_with_result(timeout=5)

        assert isinstance(result, DiscoveryResult)
        assert result.status in ["complete", "error"]
        assert result.duration_ms >= 0
        assert isinstance(result.devices, list)

    @pytest.mark.asyncio
    @patch('app.services.onvif_discovery_service.WSDISCOVERY_AVAILABLE', True)
    async def test_discover_cameras_returns_list(self):
        """AC4: Test discover_cameras returns device list."""
        service = ONVIFDiscoveryService()

        mock_device = DiscoveredDevice(
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            scopes=["onvif://www.onvif.org/type/NVT"],
            types=["tdn:NVT"]
        )

        with patch.object(service, '_sync_discover', return_value=[mock_device]):
            devices = await service.discover_cameras(timeout=5, use_cache=False)

        assert len(devices) == 1
        assert devices[0].endpoint_url == "http://192.168.1.100:80/onvif/device_service"

    @pytest.mark.asyncio
    @patch('app.services.onvif_discovery_service.WSDISCOVERY_AVAILABLE', False)
    async def test_discover_raises_when_unavailable(self):
        """Test discovery raises RuntimeError when library unavailable."""
        service = ONVIFDiscoveryService()

        with pytest.raises(RuntimeError) as exc_info:
            await service.discover_cameras()

        assert "WSDiscovery" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch('app.services.onvif_discovery_service.WSDISCOVERY_AVAILABLE', False)
    async def test_discover_with_result_returns_error_when_unavailable(self):
        """Test discover_cameras_with_result returns error when library unavailable."""
        service = ONVIFDiscoveryService()

        result = await service.discover_cameras_with_result(timeout=5)

        assert result.status == "error"
        assert "WSDiscovery" in result.error


class TestDiscoveryCache:
    """Test caching behavior."""

    @pytest.mark.asyncio
    @patch('app.services.onvif_discovery_service.WSDISCOVERY_AVAILABLE', True)
    async def test_cache_is_used(self):
        """Test cached results are returned when cache is valid."""
        service = ONVIFDiscoveryService()

        mock_device = DiscoveredDevice(
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            scopes=[],
            types=[]
        )

        call_count = 0

        def mock_sync_discover(timeout):
            nonlocal call_count
            call_count += 1
            return [mock_device]

        with patch.object(service, '_sync_discover', side_effect=mock_sync_discover):
            # First call should invoke discovery
            devices1 = await service.discover_cameras(timeout=5, use_cache=True)
            # Second call should use cache
            devices2 = await service.discover_cameras(timeout=5, use_cache=True)

        assert call_count == 1  # Only one actual discovery
        assert devices1 == devices2

    @pytest.mark.asyncio
    @patch('app.services.onvif_discovery_service.WSDISCOVERY_AVAILABLE', True)
    async def test_cache_bypass(self):
        """Test use_cache=False bypasses cache."""
        service = ONVIFDiscoveryService()

        mock_device = DiscoveredDevice(
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            scopes=[],
            types=[]
        )

        call_count = 0

        def mock_sync_discover(timeout):
            nonlocal call_count
            call_count += 1
            return [mock_device]

        with patch.object(service, '_sync_discover', side_effect=mock_sync_discover):
            await service.discover_cameras(timeout=5, use_cache=False)
            await service.discover_cameras(timeout=5, use_cache=False)

        assert call_count == 2  # Discovery called both times

    def test_clear_cache(self):
        """Test clear_cache resets cache state."""
        service = ONVIFDiscoveryService()

        # Simulate cached state
        service._cached_devices = [
            DiscoveredDevice(endpoint_url="http://test", scopes=[], types=[])
        ]
        import time
        service._last_discovery_time = time.time()

        service.clear_cache()

        assert service._cached_devices == []
        assert service._last_discovery_time is None


class TestDiscoveredDeviceSchema:
    """Test DiscoveredDevice Pydantic model."""

    def test_create_device(self):
        """Test DiscoveredDevice creation."""
        device = DiscoveredDevice(
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            scopes=["onvif://www.onvif.org/type/NVT"],
            types=["tdn:NetworkVideoTransmitter"],
            metadata_version="1"
        )

        assert device.endpoint_url == "http://192.168.1.100:80/onvif/device_service"
        assert len(device.scopes) == 1
        assert len(device.types) == 1
        assert device.metadata_version == "1"

    def test_device_defaults(self):
        """Test DiscoveredDevice default values."""
        device = DiscoveredDevice(
            endpoint_url="http://192.168.1.100:80/onvif/device_service"
        )

        assert device.scopes == []
        assert device.types == []
        assert device.metadata_version is None

    def test_device_serialization(self):
        """Test DiscoveredDevice JSON serialization."""
        device = DiscoveredDevice(
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            scopes=["scope1"],
            types=["type1"]
        )

        json_data = device.model_dump()

        assert json_data["endpoint_url"] == "http://192.168.1.100:80/onvif/device_service"
        assert json_data["scopes"] == ["scope1"]
        assert json_data["types"] == ["type1"]


# ============================================================================
# Story P5-2.2: Device Details Tests
# ============================================================================


class TestDeviceDetailsConstants:
    """Test device details constants (P5-2.2)."""

    def test_device_query_timeout(self):
        """AC1: Verify device query timeout is reasonable."""
        assert DEVICE_QUERY_TIMEOUT >= 2
        assert DEVICE_QUERY_TIMEOUT <= 30


class TestParseEndpointUrl:
    """Test endpoint URL parsing helper (P5-2.2)."""

    def test_parse_standard_url(self):
        """AC4: Parse standard ONVIF endpoint URL."""
        service = ONVIFDiscoveryService()
        host, port = service._parse_endpoint_url(
            "http://192.168.1.100:80/onvif/device_service"
        )
        assert host == "192.168.1.100"
        assert port == 80

    def test_parse_url_without_port(self):
        """AC4: Parse URL without explicit port (defaults to 80)."""
        service = ONVIFDiscoveryService()
        host, port = service._parse_endpoint_url(
            "http://192.168.1.100/onvif/device_service"
        )
        assert host == "192.168.1.100"
        assert port == 80

    def test_parse_url_with_non_standard_port(self):
        """AC4: Parse URL with non-standard port."""
        service = ONVIFDiscoveryService()
        host, port = service._parse_endpoint_url(
            "http://192.168.1.100:8080/onvif/device_service"
        )
        assert host == "192.168.1.100"
        assert port == 8080

    def test_parse_ipv6_url(self):
        """AC4: Parse IPv6 address URL."""
        service = ONVIFDiscoveryService()
        host, port = service._parse_endpoint_url(
            "http://[::1]:80/onvif/device_service"
        )
        assert host == "::1"
        assert port == 80

    def test_parse_invalid_url(self):
        """AC4: Handle invalid URL gracefully."""
        service = ONVIFDiscoveryService()
        # Empty string should return None host
        host, port = service._parse_endpoint_url("")
        assert host is None or host == ""
        # A string without scheme returns None hostname from urlparse
        host2, port2 = service._parse_endpoint_url(":::")
        assert host2 is None or host2 == ""


class TestGenerateCameraId:
    """Test camera ID generation (P5-2.2)."""

    def test_generate_id_standard(self):
        """Test standard camera ID generation."""
        service = ONVIFDiscoveryService()
        camera_id = service._generate_camera_id("192.168.1.100", 80)
        assert camera_id == "camera-192-168-1-100-80"

    def test_generate_id_different_port(self):
        """Test camera ID with different port."""
        service = ONVIFDiscoveryService()
        camera_id = service._generate_camera_id("192.168.1.100", 8080)
        assert camera_id == "camera-192-168-1-100-8080"

    def test_generate_id_deterministic(self):
        """Test camera ID generation is deterministic."""
        service = ONVIFDiscoveryService()
        id1 = service._generate_camera_id("192.168.1.100", 80)
        id2 = service._generate_camera_id("192.168.1.100", 80)
        assert id1 == id2


class TestDeviceInfoSchema:
    """Test DeviceInfo Pydantic model (P5-2.2)."""

    def test_create_device_info(self):
        """AC1: Test DeviceInfo creation with all fields."""
        info = DeviceInfo(
            name="Dahua IPC-HDW2431T",
            manufacturer="Dahua",
            model="IPC-HDW2431T-AS-S2",
            firmware_version="2.800.0000000.44.R",
            serial_number="6G12345678",
            hardware_id="1.0"
        )
        assert info.manufacturer == "Dahua"
        assert info.model == "IPC-HDW2431T-AS-S2"
        assert info.firmware_version == "2.800.0000000.44.R"

    def test_device_info_optional_fields(self):
        """AC1: Test DeviceInfo with only required fields."""
        info = DeviceInfo(
            name="Test Camera",
            manufacturer="Unknown",
            model="Unknown"
        )
        assert info.firmware_version is None
        assert info.serial_number is None
        assert info.hardware_id is None


class TestStreamProfileSchema:
    """Test StreamProfile Pydantic model (P5-2.2)."""

    def test_create_stream_profile(self):
        """AC2, AC5: Test StreamProfile creation."""
        profile = StreamProfile(
            name="mainStream",
            token="profile_1",
            resolution="1920x1080",
            width=1920,
            height=1080,
            fps=30,
            rtsp_url="rtsp://192.168.1.100:554/stream",
            encoding="H264"
        )
        assert profile.name == "mainStream"
        assert profile.resolution == "1920x1080"
        assert profile.width == 1920
        assert profile.height == 1080
        assert profile.fps == 30

    def test_stream_profile_serialization(self):
        """AC5: Test StreamProfile JSON serialization."""
        profile = StreamProfile(
            name="mainStream",
            token="profile_1",
            resolution="1920x1080",
            width=1920,
            height=1080,
            fps=30,
            rtsp_url="rtsp://192.168.1.100:554/stream"
        )
        data = profile.model_dump()
        assert data["name"] == "mainStream"
        assert data["resolution"] == "1920x1080"


class TestDiscoveredCameraDetailsSchema:
    """Test DiscoveredCameraDetails Pydantic model (P5-2.2)."""

    def test_create_camera_details(self):
        """AC4, AC5: Test DiscoveredCameraDetails creation."""
        device_info = DeviceInfo(
            name="Test Camera",
            manufacturer="Dahua",
            model="IPC-HDW2431T"
        )
        profile = StreamProfile(
            name="mainStream",
            token="profile_1",
            resolution="1920x1080",
            width=1920,
            height=1080,
            fps=30,
            rtsp_url="rtsp://192.168.1.100:554/stream"
        )

        details = DiscoveredCameraDetails(
            id="camera-192-168-1-100-80",
            endpoint_url="http://192.168.1.100:80/onvif/device_service",
            ip_address="192.168.1.100",
            port=80,
            device_info=device_info,
            profiles=[profile],
            primary_rtsp_url="rtsp://192.168.1.100:554/stream",
            requires_auth=False,
            discovered_at=datetime.utcnow()
        )

        assert details.id == "camera-192-168-1-100-80"
        assert details.ip_address == "192.168.1.100"
        assert details.device_info.manufacturer == "Dahua"
        assert len(details.profiles) == 1
        assert details.requires_auth is False


class TestDeviceDetailsResult:
    """Test DeviceDetailsResult dataclass (P5-2.2)."""

    def test_success_result(self):
        """Test success result creation."""
        result = DeviceDetailsResult(
            status="success",
            duration_ms=1234
        )
        assert result.status == "success"
        assert result.duration_ms == 1234
        assert result.device is None
        assert result.error is None

    def test_auth_required_result(self):
        """AC1: Test auth_required result."""
        result = DeviceDetailsResult(
            status="auth_required",
            error="Authentication required"
        )
        assert result.status == "auth_required"
        assert "Authentication" in result.error

    def test_error_result(self):
        """Test error result creation."""
        result = DeviceDetailsResult(
            status="error",
            error="Connection timeout"
        )
        assert result.status == "error"
        assert "timeout" in result.error


class TestDeviceDetailsAvailability:
    """Test device details availability checks (P5-2.2)."""

    def test_is_device_details_available_property(self):
        """Test is_device_details_available property exists."""
        service = ONVIFDiscoveryService()
        assert isinstance(service.is_device_details_available, bool)


class TestAsyncGetDeviceDetails:
    """Test async get_device_details method (P5-2.2)."""

    @pytest.mark.asyncio
    @patch('app.services.onvif_discovery_service.ONVIF_ZEEP_AVAILABLE', False)
    async def test_returns_error_when_unavailable(self):
        """Test get_device_details returns error when library unavailable."""
        service = ONVIFDiscoveryService()

        result = await service.get_device_details(
            "http://192.168.1.100:80/onvif/device_service"
        )

        assert result.status == "error"
        assert "onvif-zeep" in result.error

    @pytest.mark.asyncio
    @patch('app.services.onvif_discovery_service.ONVIF_ZEEP_AVAILABLE', True)
    async def test_returns_error_for_invalid_url(self):
        """AC4: Test error returned for invalid endpoint URL."""
        service = ONVIFDiscoveryService()

        # Mock _sync_get_device_details to avoid actual network call
        with patch.object(service, '_parse_endpoint_url', return_value=(None, 0)):
            result = await service.get_device_details("invalid-url")

        assert result.status == "error"
        assert "Invalid endpoint URL" in result.error

    @pytest.mark.asyncio
    @patch('app.services.onvif_discovery_service.ONVIF_ZEEP_AVAILABLE', True)
    async def test_success_with_mock(self):
        """AC1, AC4: Test successful device details retrieval with mock."""
        service = ONVIFDiscoveryService()

        mock_result = DeviceDetailsResult(
            status="success",
            device=DiscoveredCameraDetails(
                id="camera-192-168-1-100-80",
                endpoint_url="http://192.168.1.100:80/onvif/device_service",
                ip_address="192.168.1.100",
                port=80,
                device_info=DeviceInfo(
                    name="Test Camera",
                    manufacturer="Dahua",
                    model="IPC-HDW2431T"
                ),
                profiles=[],
                primary_rtsp_url="rtsp://192.168.1.100:554/stream",
                requires_auth=False,
                discovered_at=datetime.utcnow()
            ),
            duration_ms=0
        )

        with patch.object(service, '_sync_get_device_details', return_value=mock_result):
            result = await service.get_device_details(
                "http://192.168.1.100:80/onvif/device_service"
            )

        assert result.status == "success"
        assert result.device.ip_address == "192.168.1.100"
        assert result.device.device_info.manufacturer == "Dahua"


class TestSyncGetDeviceDetails:
    """Test synchronous device details query (P5-2.2).

    These tests mock the ONVIF camera client to test parsing logic.
    """

    @pytest.fixture(autouse=True)
    def check_onvif_zeep(self):
        """Skip tests if onvif-zeep not installed."""
        from app.services.onvif_discovery_service import ONVIF_ZEEP_AVAILABLE
        if not ONVIF_ZEEP_AVAILABLE:
            pytest.skip("onvif-zeep library not installed")

    def test_parse_device_info_response(self):
        """AC1: Test parsing GetDeviceInformation response."""
        service = ONVIFDiscoveryService()

        # Create mock ONVIF camera and services
        mock_camera = MagicMock()
        mock_device_service = MagicMock()
        mock_media_service = MagicMock()

        # Mock GetDeviceInformation response
        mock_device_info = MagicMock()
        mock_device_info.Manufacturer = "Dahua"
        mock_device_info.Model = "IPC-HDW2431T-AS-S2"
        mock_device_info.FirmwareVersion = "2.800.0000000.44.R"
        mock_device_info.SerialNumber = "6G12345678"
        mock_device_info.HardwareId = "1.0"

        mock_device_service.GetDeviceInformation.return_value = mock_device_info
        mock_media_service.GetProfiles.return_value = []

        mock_camera.create_devicemgmt_service.return_value = mock_device_service
        mock_camera.create_media_service.return_value = mock_media_service

        with patch('app.services.onvif_discovery_service.ONVIFCamera', return_value=mock_camera):
            result = service._sync_get_device_details(
                host="192.168.1.100",
                port=80,
                username="admin",
                password="password",
                endpoint_url="http://192.168.1.100:80/onvif/device_service"
            )

        assert result.status == "success"
        assert result.device.device_info.manufacturer == "Dahua"
        assert result.device.device_info.model == "IPC-HDW2431T-AS-S2"
        assert result.device.device_info.firmware_version == "2.800.0000000.44.R"

    def test_parse_stream_profiles(self):
        """AC2, AC5: Test parsing GetProfiles response."""
        service = ONVIFDiscoveryService()

        # Create mock camera
        mock_camera = MagicMock()
        mock_device_service = MagicMock()
        mock_media_service = MagicMock()

        # Mock device info
        mock_device_info = MagicMock()
        mock_device_info.Manufacturer = "Dahua"
        mock_device_info.Model = "IPC-HDW2431T"
        mock_device_info.FirmwareVersion = None
        mock_device_info.SerialNumber = None
        mock_device_info.HardwareId = None

        mock_device_service.GetDeviceInformation.return_value = mock_device_info

        # Mock profile with resolution
        mock_profile = MagicMock()
        mock_profile.token = "profile_1"
        mock_profile.Name = "mainStream"

        mock_resolution = MagicMock()
        mock_resolution.Width = 1920
        mock_resolution.Height = 1080

        mock_rate_control = MagicMock()
        mock_rate_control.FrameRateLimit = 30

        mock_video_encoder = MagicMock()
        mock_video_encoder.Resolution = mock_resolution
        mock_video_encoder.RateControl = mock_rate_control
        mock_video_encoder.Encoding = "H264"

        mock_profile.VideoEncoderConfiguration = mock_video_encoder

        mock_media_service.GetProfiles.return_value = [mock_profile]

        # Mock GetStreamUri
        mock_uri_response = MagicMock()
        mock_uri_response.Uri = "rtsp://192.168.1.100:554/stream"
        mock_media_service.GetStreamUri.return_value = mock_uri_response

        mock_camera.create_devicemgmt_service.return_value = mock_device_service
        mock_camera.create_media_service.return_value = mock_media_service

        with patch('app.services.onvif_discovery_service.ONVIFCamera', return_value=mock_camera):
            result = service._sync_get_device_details(
                host="192.168.1.100",
                port=80,
                username="",
                password="",
                endpoint_url="http://192.168.1.100:80/onvif/device_service"
            )

        assert result.status == "success"
        assert len(result.device.profiles) == 1

        profile = result.device.profiles[0]
        assert profile.name == "mainStream"
        assert profile.width == 1920
        assert profile.height == 1080
        assert profile.fps == 30
        assert profile.rtsp_url == "rtsp://192.168.1.100:554/stream"

    def test_profiles_sorted_by_resolution(self):
        """AC5: Test profiles are sorted by resolution (highest first)."""
        service = ONVIFDiscoveryService()

        mock_camera = MagicMock()
        mock_device_service = MagicMock()
        mock_media_service = MagicMock()

        mock_device_info = MagicMock()
        mock_device_info.Manufacturer = "Test"
        mock_device_info.Model = "Camera"
        mock_device_info.FirmwareVersion = None
        mock_device_info.SerialNumber = None
        mock_device_info.HardwareId = None

        mock_device_service.GetDeviceInformation.return_value = mock_device_info

        # Create two profiles with different resolutions
        profiles = []
        for name, width, height in [
            ("subStream", 640, 480),
            ("mainStream", 1920, 1080)
        ]:
            profile = MagicMock()
            profile.token = f"token_{name}"
            profile.Name = name
            resolution = MagicMock()
            resolution.Width = width
            resolution.Height = height
            rate_control = MagicMock()
            rate_control.FrameRateLimit = 30
            video_encoder = MagicMock()
            video_encoder.Resolution = resolution
            video_encoder.RateControl = rate_control
            video_encoder.Encoding = "H264"
            profile.VideoEncoderConfiguration = video_encoder
            profiles.append(profile)

        mock_media_service.GetProfiles.return_value = profiles

        mock_uri_response = MagicMock()
        mock_uri_response.Uri = "rtsp://test:554/stream"
        mock_media_service.GetStreamUri.return_value = mock_uri_response

        mock_camera.create_devicemgmt_service.return_value = mock_device_service
        mock_camera.create_media_service.return_value = mock_media_service

        with patch('app.services.onvif_discovery_service.ONVIFCamera', return_value=mock_camera):
            result = service._sync_get_device_details(
                host="192.168.1.100",
                port=80,
                username="",
                password="",
                endpoint_url="http://192.168.1.100/onvif/device_service"
            )

        assert result.status == "success"
        assert len(result.device.profiles) == 2
        # First profile should be highest resolution
        assert result.device.profiles[0].width == 1920
        assert result.device.profiles[1].width == 640
        # Primary RTSP URL should be from highest resolution profile
        assert result.device.primary_rtsp_url == result.device.profiles[0].rtsp_url

    def test_auth_required_detection(self):
        """AC1: Test authentication required error handling."""
        service = ONVIFDiscoveryService()

        mock_camera = MagicMock()
        mock_device_service = MagicMock()

        # Simulate authentication error
        from app.services.onvif_discovery_service import ZeepFault
        mock_device_service.GetDeviceInformation.side_effect = ZeepFault(
            "Sender not authorized"
        )

        mock_camera.create_devicemgmt_service.return_value = mock_device_service

        with patch('app.services.onvif_discovery_service.ONVIFCamera', return_value=mock_camera):
            result = service._sync_get_device_details(
                host="192.168.1.100",
                port=80,
                username="",
                password="",
                endpoint_url="http://192.168.1.100/onvif/device_service"
            )

        assert result.status == "auth_required"
        assert "Authentication" in result.error or "authorized" in result.error.lower()

    def test_connection_error_handling(self):
        """Test connection error is handled gracefully."""
        service = ONVIFDiscoveryService()

        # Simulate connection error during ONVIFCamera creation
        with patch(
            'app.services.onvif_discovery_service.ONVIFCamera',
            side_effect=Exception("Connection refused")
        ):
            result = service._sync_get_device_details(
                host="192.168.1.100",
                port=80,
                username="",
                password="",
                endpoint_url="http://192.168.1.100/onvif/device_service"
            )

        assert result.status == "error"
        assert "Connection refused" in result.error or "Failed to query" in result.error

    def test_device_name_fallback_to_model(self):
        """AC4: Test device name falls back to model when name unavailable."""
        service = ONVIFDiscoveryService()

        mock_camera = MagicMock()
        mock_device_service = MagicMock()
        mock_media_service = MagicMock()

        # Device info without explicit name
        mock_device_info = MagicMock()
        mock_device_info.Manufacturer = "Dahua"
        mock_device_info.Model = "IPC-HDW2431T"
        mock_device_info.FirmwareVersion = None
        mock_device_info.SerialNumber = None
        mock_device_info.HardwareId = None

        mock_device_service.GetDeviceInformation.return_value = mock_device_info
        mock_media_service.GetProfiles.return_value = []

        mock_camera.create_devicemgmt_service.return_value = mock_device_service
        mock_camera.create_media_service.return_value = mock_media_service

        with patch('app.services.onvif_discovery_service.ONVIFCamera', return_value=mock_camera):
            result = service._sync_get_device_details(
                host="192.168.1.100",
                port=80,
                username="",
                password="",
                endpoint_url="http://192.168.1.100/onvif/device_service"
            )

        assert result.status == "success"
        # Name should be "Manufacturer Model"
        assert "Dahua" in result.device.device_info.name
        assert "IPC-HDW2431T" in result.device.device_info.name
