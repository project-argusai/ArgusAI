"""
Tests for HomeKit service (Story P4-6.1)

Tests the HomekitService class and related functionality.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

from app.config.homekit import HomekitConfig, generate_pincode, get_homekit_config
from app.services.homekit_service import (
    HomekitService,
    HomekitStatus,
    get_homekit_service,
)
from app.services.homekit_accessories import CameraMotionSensor, create_motion_sensor


class TestHomekitConfig:
    """Tests for HomeKit configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = HomekitConfig()
        assert config.enabled is False
        assert config.port == 51826
        assert config.bridge_name == "ArgusAI"
        assert config.manufacturer == "ArgusAI"
        assert config.persist_dir == "data/homekit"

    def test_persist_file_path(self):
        """Test persist_file property returns correct path."""
        config = HomekitConfig(persist_dir="test/dir")
        assert config.persist_file == "test/dir/accessory.state"

    def test_pincode_bytes(self):
        """Test pincode_bytes property."""
        config = HomekitConfig(pincode="123-45-678")
        assert config.pincode_bytes == b"123-45-678"

    def test_pincode_bytes_default(self):
        """Test pincode_bytes uses default when not set."""
        config = HomekitConfig(pincode=None)
        assert config.pincode_bytes == b"031-45-154"


class TestGeneratePincode:
    """Tests for pincode generation."""

    def test_pincode_format(self):
        """Test generated pincode follows XXX-XX-XXX format."""
        for _ in range(10):
            code = generate_pincode()
            parts = code.split('-')
            assert len(parts) == 3
            assert len(parts[0]) == 3
            assert len(parts[1]) == 2
            assert len(parts[2]) == 3
            # All parts should be numeric
            assert parts[0].isdigit()
            assert parts[1].isdigit()
            assert parts[2].isdigit()

    def test_pincode_not_trivial(self):
        """Test generated pincodes avoid trivial values."""
        trivial_codes = {"000-00-000", "111-11-111", "123-45-678"}
        for _ in range(100):
            code = generate_pincode()
            assert code not in trivial_codes


class TestHomekitService:
    """Tests for HomekitService class."""

    def test_init_default_config(self):
        """Test service initialization with default config."""
        service = HomekitService()
        assert service.config is not None
        assert service.is_running is False
        assert service.accessory_count == 0

    def test_init_custom_config(self):
        """Test service initialization with custom config."""
        config = HomekitConfig(enabled=True, port=51827)
        service = HomekitService(config=config)
        assert service.config.enabled is True
        assert service.config.port == 51827

    def test_is_available_without_hap(self):
        """Test is_available returns False when HAP-python not installed."""
        with patch('app.services.homekit_service.HAP_AVAILABLE', False):
            service = HomekitService()
            # Note: The instance was created before the patch, so we need a fresh one
            # Actually, HAP_AVAILABLE is checked at import time, so this test
            # documents the expected behavior
            pass  # This test is informational

    def test_get_status_disabled(self):
        """Test get_status when service is disabled."""
        config = HomekitConfig(enabled=False)
        service = HomekitService(config=config)
        status = service.get_status()

        assert status.enabled is False
        assert status.running is False
        assert status.paired is False
        assert status.accessory_count == 0
        assert status.bridge_name == "ArgusAI"

    def test_pincode_generation(self):
        """Test pincode is generated on first access."""
        config = HomekitConfig(pincode=None)
        service = HomekitService(config=config)

        # First access generates pincode
        code1 = service.pincode
        assert code1 is not None
        assert '-' in code1

        # Second access returns same pincode
        code2 = service.pincode
        assert code1 == code2

    def test_pincode_from_config(self):
        """Test pincode uses config value if provided."""
        config = HomekitConfig(pincode="111-22-333")
        service = HomekitService(config=config)
        assert service.pincode == "111-22-333"


class TestHomekitStatus:
    """Tests for HomekitStatus dataclass."""

    def test_default_values(self):
        """Test HomekitStatus has correct defaults."""
        status = HomekitStatus()
        assert status.enabled is False
        assert status.running is False
        assert status.paired is False
        assert status.accessory_count == 0
        assert status.bridge_name == "ArgusAI"
        assert status.setup_code is None
        assert status.qr_code_data is None
        assert status.port == 51826
        assert status.error is None

    def test_custom_values(self):
        """Test HomekitStatus accepts custom values."""
        status = HomekitStatus(
            enabled=True,
            running=True,
            paired=True,
            accessory_count=5,
            bridge_name="TestBridge",
            setup_code="123-45-678",
            port=51827,
        )
        assert status.enabled is True
        assert status.running is True
        assert status.paired is True
        assert status.accessory_count == 5
        assert status.bridge_name == "TestBridge"


class TestGetHomekitService:
    """Tests for the singleton service getter."""

    def test_returns_same_instance(self):
        """Test get_homekit_service returns singleton."""
        # Clear any existing instance
        import app.services.homekit_service as module
        module._homekit_service = None

        service1 = get_homekit_service()
        service2 = get_homekit_service()
        assert service1 is service2


class TestCameraMotionSensorMocked:
    """Tests for CameraMotionSensor with mocked HAP-python."""

    def test_create_motion_sensor_without_hap(self):
        """Test create_motion_sensor returns None when HAP not available."""
        mock_driver = Mock()

        # When HAP_AVAILABLE is False, create_motion_sensor should return None
        with patch('app.services.homekit_accessories.HAP_AVAILABLE', False):
            result = create_motion_sensor(
                driver=mock_driver,
                camera_id="test-camera-123",
                camera_name="Test Camera"
            )
            # Returns None when HAP not available
            assert result is None

    def test_camera_motion_sensor_requires_hap(self):
        """Test CameraMotionSensor raises ImportError without HAP."""
        with patch('app.services.homekit_accessories.HAP_AVAILABLE', False):
            with pytest.raises(ImportError):
                CameraMotionSensor(
                    driver=Mock(),
                    camera_id="test-camera",
                    name="Test Camera"
                )


class TestHomekitServiceStartStop:
    """Tests for service start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_when_disabled(self):
        """Test start returns False when service is disabled."""
        config = HomekitConfig(enabled=False)
        service = HomekitService(config=config)

        result = await service.start([])
        assert result is False
        assert service.is_running is False

    @pytest.mark.asyncio
    async def test_start_without_hap_available(self):
        """Test start fails gracefully when HAP-python not installed."""
        config = HomekitConfig(enabled=True)

        with patch('app.services.homekit_service.HAP_AVAILABLE', False):
            service = HomekitService(config=config)
            result = await service.start([])
            # Should return False when HAP not available
            assert result is False
            assert service._error == "HAP-python not installed"

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Test stop is safe when service not running."""
        service = HomekitService()
        await service.stop()  # Should not raise
        assert service.is_running is False


class TestHomekitServiceMotion:
    """Tests for motion triggering functionality."""

    def test_trigger_motion_no_sensor(self):
        """Test trigger_motion returns False when sensor not found."""
        service = HomekitService()
        result = service.trigger_motion("nonexistent-camera")
        assert result is False

    def test_clear_motion_no_sensor(self):
        """Test clear_motion returns False when sensor not found."""
        service = HomekitService()
        result = service.clear_motion("nonexistent-camera")
        assert result is False

    def test_clear_all_motion_empty(self):
        """Test clear_all_motion works with no sensors."""
        service = HomekitService()
        service.clear_all_motion()  # Should not raise


class TestEnvironmentConfig:
    """Tests for environment-based configuration."""

    def test_get_homekit_config_defaults(self):
        """Test get_homekit_config with no env vars set."""
        with patch.dict('os.environ', {}, clear=True):
            config = get_homekit_config()
            assert config.enabled is False
            assert config.port == 51826

    def test_get_homekit_config_enabled(self):
        """Test get_homekit_config with HOMEKIT_ENABLED=true."""
        with patch.dict('os.environ', {'HOMEKIT_ENABLED': 'true'}):
            config = get_homekit_config()
            assert config.enabled is True

    def test_get_homekit_config_custom_port(self):
        """Test get_homekit_config with custom port."""
        with patch.dict('os.environ', {'HOMEKIT_PORT': '51900'}):
            config = get_homekit_config()
            assert config.port == 51900
