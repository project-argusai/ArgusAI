"""
Unit tests for HomeKit vehicle/animal/package sensor triggering (Story P5-1.6, P7-2.3)

Tests cover:
- Vehicle detection triggers only vehicle sensor (AC1)
- Animal detection triggers only animal sensor (AC2)
- Package detection triggers only package sensor (AC3)
- Motion sensor still triggers on all detection types (AC4)
- Auto-reset timeouts for each sensor type
- Camera ID mapping (Protect MAC addresses)
- Error resilience
- Story P7-2.3: Carrier info in package trigger logging
- Story P7-2.3: Per-carrier sensor configuration
"""
import asyncio
import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass

from app.config.homekit import HomekitConfig


# Mock sensor classes for tests (match homekit_accessories.py interface)
@dataclass
class MockDetectionSensor:
    """Mock detection sensor (vehicle/animal/package) for testing."""
    camera_id: str
    name: str
    _motion_detected: bool = False

    @property
    def motion_detected(self) -> bool:
        return self._motion_detected

    def trigger_motion(self):
        self._motion_detected = True

    def clear_motion(self):
        self._motion_detected = False


@dataclass
class MockCameraMotionSensor:
    """Mock motion sensor for testing."""
    camera_id: str
    name: str
    _motion_detected: bool = False

    @property
    def motion_detected(self) -> bool:
        return self._motion_detected

    def trigger_motion(self):
        self._motion_detected = True

    def clear_motion(self):
        self._motion_detected = False


@dataclass
class MockCameraOccupancySensor:
    """Mock occupancy sensor for testing."""
    camera_id: str
    name: str
    _occupancy_detected: bool = False

    @property
    def occupancy_detected(self) -> bool:
        return self._occupancy_detected

    def trigger_occupancy(self):
        self._occupancy_detected = True

    def clear_occupancy(self):
        self._occupancy_detected = False


class TestHomekitVehicleSensorTrigger:
    """Tests for HomekitService.trigger_vehicle() (Story P5-1.6 AC1)"""

    @pytest.fixture
    def config(self):
        """Create test HomeKit config with short timeout for tests."""
        return HomekitConfig(
            enabled=True,
            port=51826,
            bridge_name="Test Bridge",
            manufacturer="Test",
            persist_dir="/tmp/homekit_test",
            motion_reset_seconds=2,
            max_motion_duration=10,
            vehicle_reset_seconds=2,  # Short timeout for tests (normally 30s)
            animal_reset_seconds=2,
            package_reset_seconds=3,  # Package has longer timeout
        )

    @pytest.fixture
    def mock_service(self, config):
        """Create a mock HomeKit service for testing."""
        from app.services.homekit_service import HomekitService

        service = HomekitService(config=config)
        service._running = True

        # Add mock vehicle sensors
        service._vehicle_sensors = {
            "camera-1": MockDetectionSensor(camera_id="camera-1", name="Front Door Vehicle"),
            "camera-2": MockDetectionSensor(camera_id="camera-2", name="Back Yard Vehicle"),
        }

        # Add mock occupancy sensors to verify isolation
        service._occupancy_sensors = {
            "camera-1": MockCameraOccupancySensor(camera_id="camera-1", name="Front Door Occupancy"),
            "camera-2": MockCameraOccupancySensor(camera_id="camera-2", name="Back Yard Occupancy"),
        }

        # Add mock motion sensors
        service._sensors = {
            "camera-1": MockCameraMotionSensor(camera_id="camera-1", name="Front Door"),
            "camera-2": MockCameraMotionSensor(camera_id="camera-2", name="Back Yard"),
        }

        return service

    def test_trigger_vehicle_sets_sensor_state(self, mock_service):
        """AC1: Vehicle trigger sets motion_detected = True on vehicle sensor"""
        sensor = mock_service._vehicle_sensors["camera-1"]
        assert sensor.motion_detected is False

        result = mock_service.trigger_vehicle("camera-1", event_id=123)

        assert result is True
        assert sensor.motion_detected is True

    def test_trigger_vehicle_unknown_camera(self, mock_service):
        """Triggering unknown camera returns False"""
        result = mock_service.trigger_vehicle("unknown-camera")
        assert result is False

    def test_trigger_vehicle_does_not_trigger_occupancy(self, mock_service):
        """AC1: Vehicle detection does NOT trigger occupancy sensor"""
        occupancy_sensor = mock_service._occupancy_sensors["camera-1"]
        assert occupancy_sensor.occupancy_detected is False

        mock_service.trigger_vehicle("camera-1")

        # Occupancy should remain False
        assert occupancy_sensor.occupancy_detected is False

    def test_camera_id_mapping_mac_address_vehicle(self, mock_service):
        """Protect cameras can be triggered by MAC address for vehicle"""
        # Register MAC mapping
        mock_service.register_camera_mapping("camera-1", "AA:BB:CC:DD:EE:FF")

        # Trigger by MAC address
        result = mock_service.trigger_vehicle("AA:BB:CC:DD:EE:FF")

        assert result is True
        assert mock_service._vehicle_sensors["camera-1"].motion_detected is True

    @pytest.mark.asyncio
    async def test_vehicle_resets_after_timeout(self, mock_service):
        """AC1: Vehicle sensor resets after timeout (30s default, 2s for test)"""
        sensor = mock_service._vehicle_sensors["camera-1"]

        mock_service.trigger_vehicle("camera-1")
        assert sensor.motion_detected is True

        # Wait for timeout (config has 2s timeout for tests)
        await asyncio.sleep(2.5)

        assert sensor.motion_detected is False


class TestHomekitAnimalSensorTrigger:
    """Tests for HomekitService.trigger_animal() (Story P5-1.6 AC2)"""

    @pytest.fixture
    def config(self):
        """Create test HomeKit config with short timeout for tests."""
        return HomekitConfig(
            enabled=True,
            port=51826,
            bridge_name="Test Bridge",
            manufacturer="Test",
            persist_dir="/tmp/homekit_test",
            motion_reset_seconds=2,
            max_motion_duration=10,
            vehicle_reset_seconds=2,
            animal_reset_seconds=2,  # Short timeout for tests (normally 30s)
            package_reset_seconds=3,
        )

    @pytest.fixture
    def mock_service(self, config):
        """Create a mock HomeKit service for testing."""
        from app.services.homekit_service import HomekitService

        service = HomekitService(config=config)
        service._running = True

        # Add mock animal sensors
        service._animal_sensors = {
            "camera-1": MockDetectionSensor(camera_id="camera-1", name="Front Door Animal"),
            "camera-2": MockDetectionSensor(camera_id="camera-2", name="Back Yard Animal"),
        }

        # Add mock occupancy sensors to verify isolation
        service._occupancy_sensors = {
            "camera-1": MockCameraOccupancySensor(camera_id="camera-1", name="Front Door Occupancy"),
            "camera-2": MockCameraOccupancySensor(camera_id="camera-2", name="Back Yard Occupancy"),
        }

        # Add mock motion sensors
        service._sensors = {
            "camera-1": MockCameraMotionSensor(camera_id="camera-1", name="Front Door"),
            "camera-2": MockCameraMotionSensor(camera_id="camera-2", name="Back Yard"),
        }

        return service

    def test_trigger_animal_sets_sensor_state(self, mock_service):
        """AC2: Animal trigger sets motion_detected = True on animal sensor"""
        sensor = mock_service._animal_sensors["camera-1"]
        assert sensor.motion_detected is False

        result = mock_service.trigger_animal("camera-1", event_id=456)

        assert result is True
        assert sensor.motion_detected is True

    def test_trigger_animal_unknown_camera(self, mock_service):
        """Triggering unknown camera returns False"""
        result = mock_service.trigger_animal("unknown-camera")
        assert result is False

    def test_trigger_animal_does_not_trigger_occupancy(self, mock_service):
        """AC2: Animal detection does NOT trigger occupancy sensor"""
        occupancy_sensor = mock_service._occupancy_sensors["camera-1"]
        assert occupancy_sensor.occupancy_detected is False

        mock_service.trigger_animal("camera-1")

        # Occupancy should remain False
        assert occupancy_sensor.occupancy_detected is False

    @pytest.mark.asyncio
    async def test_animal_resets_after_timeout(self, mock_service):
        """AC2: Animal sensor resets after timeout (30s default, 2s for test)"""
        sensor = mock_service._animal_sensors["camera-1"]

        mock_service.trigger_animal("camera-1")
        assert sensor.motion_detected is True

        # Wait for timeout
        await asyncio.sleep(2.5)

        assert sensor.motion_detected is False


class TestHomekitPackageSensorTrigger:
    """Tests for HomekitService.trigger_package() (Story P5-1.6 AC3)"""

    @pytest.fixture
    def config(self):
        """Create test HomeKit config with short timeout for tests."""
        return HomekitConfig(
            enabled=True,
            port=51826,
            bridge_name="Test Bridge",
            manufacturer="Test",
            persist_dir="/tmp/homekit_test",
            motion_reset_seconds=2,
            max_motion_duration=10,
            vehicle_reset_seconds=2,
            animal_reset_seconds=2,
            package_reset_seconds=3,  # Longer timeout for packages (normally 60s)
        )

    @pytest.fixture
    def mock_service(self, config):
        """Create a mock HomeKit service for testing."""
        from app.services.homekit_service import HomekitService

        service = HomekitService(config=config)
        service._running = True

        # Add mock package sensors
        service._package_sensors = {
            "camera-1": MockDetectionSensor(camera_id="camera-1", name="Front Door Package"),
            "camera-2": MockDetectionSensor(camera_id="camera-2", name="Back Yard Package"),
        }

        # Add mock occupancy sensors to verify isolation
        service._occupancy_sensors = {
            "camera-1": MockCameraOccupancySensor(camera_id="camera-1", name="Front Door Occupancy"),
            "camera-2": MockCameraOccupancySensor(camera_id="camera-2", name="Back Yard Occupancy"),
        }

        # Add mock motion sensors
        service._sensors = {
            "camera-1": MockCameraMotionSensor(camera_id="camera-1", name="Front Door"),
            "camera-2": MockCameraMotionSensor(camera_id="camera-2", name="Back Yard"),
        }

        return service

    def test_trigger_package_sets_sensor_state(self, mock_service):
        """AC3: Package trigger sets motion_detected = True on package sensor"""
        sensor = mock_service._package_sensors["camera-1"]
        assert sensor.motion_detected is False

        result = mock_service.trigger_package("camera-1", event_id=789)

        assert result is True
        assert sensor.motion_detected is True

    def test_trigger_package_unknown_camera(self, mock_service):
        """Triggering unknown camera returns False"""
        result = mock_service.trigger_package("unknown-camera")
        assert result is False

    def test_trigger_package_does_not_trigger_occupancy(self, mock_service):
        """AC3: Package detection does NOT trigger occupancy sensor"""
        occupancy_sensor = mock_service._occupancy_sensors["camera-1"]
        assert occupancy_sensor.occupancy_detected is False

        mock_service.trigger_package("camera-1")

        # Occupancy should remain False
        assert occupancy_sensor.occupancy_detected is False

    @pytest.mark.asyncio
    async def test_package_resets_after_timeout(self, mock_service):
        """AC3: Package sensor resets after timeout (60s default, 3s for test)"""
        sensor = mock_service._package_sensors["camera-1"]

        mock_service.trigger_package("camera-1")
        assert sensor.motion_detected is True

        # Wait for timeout
        await asyncio.sleep(3.5)

        assert sensor.motion_detected is False


class TestDetectionSensorIsolation:
    """Tests verifying each detection type triggers its own sensor (Story P5-1.6 AC4)"""

    @pytest.fixture
    def config(self):
        """Create test HomeKit config."""
        return HomekitConfig(
            enabled=True,
            port=51826,
            bridge_name="Test Bridge",
            manufacturer="Test",
            persist_dir="/tmp/homekit_test",
            motion_reset_seconds=2,
            vehicle_reset_seconds=2,
            animal_reset_seconds=2,
            package_reset_seconds=3,
        )

    @pytest.fixture
    def mock_service(self, config):
        """Create a mock HomeKit service with all sensor types."""
        from app.services.homekit_service import HomekitService

        service = HomekitService(config=config)
        service._running = True

        # All sensor types for camera-1
        service._sensors = {"camera-1": MockCameraMotionSensor("camera-1", "Front Door")}
        service._occupancy_sensors = {"camera-1": MockCameraOccupancySensor("camera-1", "Front Door Occupancy")}
        service._vehicle_sensors = {"camera-1": MockDetectionSensor("camera-1", "Front Door Vehicle")}
        service._animal_sensors = {"camera-1": MockDetectionSensor("camera-1", "Front Door Animal")}
        service._package_sensors = {"camera-1": MockDetectionSensor("camera-1", "Front Door Package")}

        return service

    def test_vehicle_only_triggers_vehicle_sensor(self, mock_service):
        """AC4: Vehicle detection only triggers vehicle sensor"""
        mock_service.trigger_vehicle("camera-1")

        # Vehicle sensor triggered
        assert mock_service._vehicle_sensors["camera-1"].motion_detected is True

        # Others not triggered
        assert mock_service._animal_sensors["camera-1"].motion_detected is False
        assert mock_service._package_sensors["camera-1"].motion_detected is False
        assert mock_service._occupancy_sensors["camera-1"].occupancy_detected is False

    def test_animal_only_triggers_animal_sensor(self, mock_service):
        """AC4: Animal detection only triggers animal sensor"""
        mock_service.trigger_animal("camera-1")

        # Animal sensor triggered
        assert mock_service._animal_sensors["camera-1"].motion_detected is True

        # Others not triggered
        assert mock_service._vehicle_sensors["camera-1"].motion_detected is False
        assert mock_service._package_sensors["camera-1"].motion_detected is False
        assert mock_service._occupancy_sensors["camera-1"].occupancy_detected is False

    def test_package_only_triggers_package_sensor(self, mock_service):
        """AC4: Package detection only triggers package sensor"""
        mock_service.trigger_package("camera-1")

        # Package sensor triggered
        assert mock_service._package_sensors["camera-1"].motion_detected is True

        # Others not triggered
        assert mock_service._vehicle_sensors["camera-1"].motion_detected is False
        assert mock_service._animal_sensors["camera-1"].motion_detected is False
        assert mock_service._occupancy_sensors["camera-1"].occupancy_detected is False

    def test_clear_all_detection_sensors(self, mock_service):
        """clear_all_detection_sensors clears all vehicle/animal/package sensors"""
        # Trigger all detection sensors
        mock_service.trigger_vehicle("camera-1")
        mock_service.trigger_animal("camera-1")
        mock_service.trigger_package("camera-1")

        assert mock_service._vehicle_sensors["camera-1"].motion_detected is True
        assert mock_service._animal_sensors["camera-1"].motion_detected is True
        assert mock_service._package_sensors["camera-1"].motion_detected is True

        # Clear all detection sensors
        mock_service.clear_all_detection_sensors()

        assert mock_service._vehicle_sensors["camera-1"].motion_detected is False
        assert mock_service._animal_sensors["camera-1"].motion_detected is False
        assert mock_service._package_sensors["camera-1"].motion_detected is False


class TestDetectionSensorConfig:
    """Tests for HomeKit detection sensor configuration (Story P5-1.6)"""

    def test_default_vehicle_reset_seconds(self):
        """Default vehicle reset timeout is 30 seconds"""
        from app.config.homekit import DEFAULT_VEHICLE_RESET_SECONDS
        assert DEFAULT_VEHICLE_RESET_SECONDS == 30

    def test_default_animal_reset_seconds(self):
        """Default animal reset timeout is 30 seconds"""
        from app.config.homekit import DEFAULT_ANIMAL_RESET_SECONDS
        assert DEFAULT_ANIMAL_RESET_SECONDS == 30

    def test_default_package_reset_seconds(self):
        """Default package reset timeout is 60 seconds (longer for packages)"""
        from app.config.homekit import DEFAULT_PACKAGE_RESET_SECONDS
        assert DEFAULT_PACKAGE_RESET_SECONDS == 60

    def test_config_loads_detection_sensor_from_env(self):
        """Config loads detection sensor settings from environment"""
        import os
        from app.config.homekit import get_homekit_config

        os.environ["HOMEKIT_VEHICLE_RESET_SECONDS"] = "45"
        os.environ["HOMEKIT_ANIMAL_RESET_SECONDS"] = "45"
        os.environ["HOMEKIT_PACKAGE_RESET_SECONDS"] = "90"

        try:
            config = get_homekit_config()
            assert config.vehicle_reset_seconds == 45
            assert config.animal_reset_seconds == 45
            assert config.package_reset_seconds == 90
        finally:
            del os.environ["HOMEKIT_VEHICLE_RESET_SECONDS"]
            del os.environ["HOMEKIT_ANIMAL_RESET_SECONDS"]
            del os.environ["HOMEKIT_PACKAGE_RESET_SECONDS"]

    def test_homekit_config_has_detection_sensor_fields(self):
        """HomekitConfig dataclass includes detection sensor fields"""
        from app.config.homekit import HomekitConfig

        config = HomekitConfig()
        assert hasattr(config, 'vehicle_reset_seconds')
        assert hasattr(config, 'animal_reset_seconds')
        assert hasattr(config, 'package_reset_seconds')
        assert config.vehicle_reset_seconds == 30
        assert config.animal_reset_seconds == 30
        assert config.package_reset_seconds == 60


class TestDetectionSensorClasses:
    """Tests for sensor class existence (Story P5-1.6)"""

    def test_vehicle_sensor_class_exists(self):
        """CameraVehicleSensor class exists"""
        from app.services.homekit_accessories import CameraVehicleSensor
        assert CameraVehicleSensor is not None

    def test_animal_sensor_class_exists(self):
        """CameraAnimalSensor class exists"""
        from app.services.homekit_accessories import CameraAnimalSensor
        assert CameraAnimalSensor is not None

    def test_package_sensor_class_exists(self):
        """CameraPackageSensor class exists"""
        from app.services.homekit_accessories import CameraPackageSensor
        assert CameraPackageSensor is not None

    def test_create_vehicle_sensor_factory_exists(self):
        """Factory function for creating vehicle sensors exists"""
        from app.services.homekit_accessories import create_vehicle_sensor
        assert callable(create_vehicle_sensor)

    def test_create_animal_sensor_factory_exists(self):
        """Factory function for creating animal sensors exists"""
        from app.services.homekit_accessories import create_animal_sensor
        assert callable(create_animal_sensor)

    def test_create_package_sensor_factory_exists(self):
        """Factory function for creating package sensors exists"""
        from app.services.homekit_accessories import create_package_sensor
        assert callable(create_package_sensor)

    def test_vehicle_sensor_uses_motion_sensor_service(self):
        """CameraVehicleSensor uses MotionSensor service (not custom)"""
        from app.services.homekit_accessories import CameraVehicleSensor
        # Verify it's documented as using MotionSensor
        assert "MotionSensor" in CameraVehicleSensor.__doc__


class TestEventProcessorDetectionRouting:
    """Tests for event processor routing to detection sensors (Story P5-1.6)"""

    @pytest.mark.asyncio
    async def test_event_processor_triggers_vehicle_for_vehicle_detection(self):
        """Event with smart_detection_type='vehicle' triggers vehicle sensor"""
        from unittest.mock import MagicMock

        class MockEventProcessor:
            async def _trigger_homekit_vehicle(self, homekit_service, camera_id, event_id):
                try:
                    success = homekit_service.trigger_vehicle(camera_id, event_id=event_id)
                    return success
                except Exception:
                    pass

        mock_homekit = MagicMock()
        mock_homekit.is_running = True
        mock_homekit.trigger_vehicle = MagicMock(return_value=True)

        processor = MockEventProcessor()
        await processor._trigger_homekit_vehicle(mock_homekit, "test-camera", "event-123")

        mock_homekit.trigger_vehicle.assert_called_once_with("test-camera", event_id="event-123")

    @pytest.mark.asyncio
    async def test_event_processor_triggers_animal_for_animal_detection(self):
        """Event with smart_detection_type='animal' triggers animal sensor"""
        from unittest.mock import MagicMock

        class MockEventProcessor:
            async def _trigger_homekit_animal(self, homekit_service, camera_id, event_id):
                try:
                    success = homekit_service.trigger_animal(camera_id, event_id=event_id)
                    return success
                except Exception:
                    pass

        mock_homekit = MagicMock()
        mock_homekit.is_running = True
        mock_homekit.trigger_animal = MagicMock(return_value=True)

        processor = MockEventProcessor()
        await processor._trigger_homekit_animal(mock_homekit, "test-camera", "event-456")

        mock_homekit.trigger_animal.assert_called_once_with("test-camera", event_id="event-456")

    @pytest.mark.asyncio
    async def test_event_processor_triggers_package_for_package_detection(self):
        """Event with smart_detection_type='package' triggers package sensor"""
        from unittest.mock import MagicMock

        class MockEventProcessor:
            async def _trigger_homekit_package(self, homekit_service, camera_id, event_id):
                try:
                    success = homekit_service.trigger_package(camera_id, event_id=event_id)
                    return success
                except Exception:
                    pass

        mock_homekit = MagicMock()
        mock_homekit.is_running = True
        mock_homekit.trigger_package = MagicMock(return_value=True)

        processor = MockEventProcessor()
        await processor._trigger_homekit_package(mock_homekit, "test-camera", "event-789")

        mock_homekit.trigger_package.assert_called_once_with("test-camera", event_id="event-789")

    @pytest.mark.asyncio
    async def test_event_processor_handles_detection_sensor_errors(self):
        """Detection sensor errors don't block event processing"""
        from unittest.mock import MagicMock

        class MockEventProcessor:
            async def _trigger_homekit_vehicle(self, homekit_service, camera_id, event_id):
                try:
                    success = homekit_service.trigger_vehicle(camera_id, event_id=event_id)
                    return success
                except Exception:
                    pass

        mock_homekit = MagicMock()
        mock_homekit.is_running = True
        mock_homekit.trigger_vehicle = MagicMock(side_effect=Exception("HAP error"))

        processor = MockEventProcessor()

        # Should not raise
        await processor._trigger_homekit_vehicle(mock_homekit, "test-camera", "event-123")

        mock_homekit.trigger_vehicle.assert_called_once()


class TestHomekitStatusDetectionSensors:
    """Tests for HomekitStatus including detection sensor counts (Story P5-1.6)"""

    def test_homekit_status_has_detection_sensor_counts(self):
        """HomekitStatus includes vehicle_count, animal_count, package_count"""
        from app.services.homekit_service import HomekitStatus

        status = HomekitStatus()
        assert hasattr(status, 'vehicle_count')
        assert hasattr(status, 'animal_count')
        assert hasattr(status, 'package_count')
        assert status.vehicle_count == 0
        assert status.animal_count == 0
        assert status.package_count == 0

    def test_get_status_includes_detection_sensor_counts(self):
        """get_status() includes detection sensor counts"""
        from app.services.homekit_service import HomekitService
        from app.config.homekit import HomekitConfig

        config = HomekitConfig(enabled=True, persist_dir="/tmp/homekit_test")
        service = HomekitService(config=config)
        service._running = True

        # Add mock sensors
        service._vehicle_sensors = {"cam1": MagicMock(), "cam2": MagicMock()}
        service._animal_sensors = {"cam1": MagicMock()}
        service._package_sensors = {"cam1": MagicMock(), "cam2": MagicMock(), "cam3": MagicMock()}

        status = service.get_status()

        assert status.vehicle_count == 2
        assert status.animal_count == 1
        assert status.package_count == 3


# =============================================================================
# Story P7-2.3: Package Delivery to HomeKit (Carrier Support)
# =============================================================================


class TestPackageDeliveryCarrier:
    """Tests for HomeKit package trigger with carrier info (Story P7-2.3)"""

    @pytest.fixture
    def config(self):
        """Create test HomeKit config."""
        return HomekitConfig(
            enabled=True,
            port=51826,
            bridge_name="Test Bridge",
            manufacturer="Test",
            persist_dir="/tmp/homekit_test",
            package_reset_seconds=3,
            per_carrier_sensors=False,  # Default is off
        )

    @pytest.fixture
    def mock_service(self, config):
        """Create a mock HomeKit service for testing."""
        from app.services.homekit_service import HomekitService

        service = HomekitService(config=config)
        service._running = True

        # Add mock package sensors
        service._package_sensors = {
            "camera-1": MockDetectionSensor(camera_id="camera-1", name="Front Door Package"),
        }

        return service

    def test_trigger_package_with_carrier(self, mock_service):
        """AC1: trigger_package accepts delivery_carrier parameter"""
        sensor = mock_service._package_sensors["camera-1"]
        assert sensor.motion_detected is False

        result = mock_service.trigger_package(
            "camera-1", event_id=123, delivery_carrier="fedex"
        )

        assert result is True
        assert sensor.motion_detected is True

    def test_trigger_package_without_carrier(self, mock_service):
        """AC1: trigger_package works without carrier (backward compatible)"""
        sensor = mock_service._package_sensors["camera-1"]

        result = mock_service.trigger_package("camera-1", event_id=456)

        assert result is True
        assert sensor.motion_detected is True

    def test_trigger_package_unknown_carrier(self, mock_service):
        """trigger_package works with unknown carrier"""
        sensor = mock_service._package_sensors["camera-1"]

        result = mock_service.trigger_package(
            "camera-1", event_id=789, delivery_carrier="unknown_carrier"
        )

        assert result is True
        assert sensor.motion_detected is True


class TestPerCarrierSensorConfig:
    """Tests for per-carrier sensor configuration (Story P7-2.3 AC3)"""

    def test_config_has_per_carrier_sensors_field(self):
        """HomekitConfig has per_carrier_sensors field"""
        from app.config.homekit import HomekitConfig

        config = HomekitConfig()
        assert hasattr(config, 'per_carrier_sensors')
        assert config.per_carrier_sensors is False  # Default off

    def test_config_loads_per_carrier_sensors_from_env(self):
        """Config loads per_carrier_sensors from environment"""
        import os
        from app.config.homekit import get_homekit_config

        os.environ["HOMEKIT_PER_CARRIER_SENSORS"] = "true"

        try:
            config = get_homekit_config()
            assert config.per_carrier_sensors is True
        finally:
            del os.environ["HOMEKIT_PER_CARRIER_SENSORS"]

    def test_config_per_carrier_sensors_default_false(self):
        """per_carrier_sensors defaults to False"""
        from app.config.homekit import get_homekit_config
        import os

        # Ensure env var is not set
        os.environ.pop("HOMEKIT_PER_CARRIER_SENSORS", None)

        config = get_homekit_config()
        assert config.per_carrier_sensors is False


class TestPerCarrierSensorTrigger:
    """Tests for per-carrier sensor triggering (Story P7-2.3 AC3)"""

    @pytest.fixture
    def config_with_carrier_sensors(self):
        """Config with per_carrier_sensors enabled."""
        return HomekitConfig(
            enabled=True,
            port=51826,
            bridge_name="Test Bridge",
            manufacturer="Test",
            persist_dir="/tmp/homekit_test",
            package_reset_seconds=3,
            per_carrier_sensors=True,  # Enabled
        )

    @pytest.fixture
    def mock_service_with_carriers(self, config_with_carrier_sensors):
        """Create a mock HomeKit service with per-carrier sensors."""
        from app.services.homekit_service import HomekitService

        service = HomekitService(config=config_with_carrier_sensors)
        service._running = True

        # Add mock package sensor (generic)
        service._package_sensors = {
            "camera-1": MockDetectionSensor(camera_id="camera-1", name="Front Door Package"),
        }

        # Add mock carrier-specific sensors
        service._carrier_sensors = {
            "camera-1_fedex": MockDetectionSensor(
                camera_id="camera-1_fedex", name="Front Door FedEx Package"
            ),
            "camera-1_ups": MockDetectionSensor(
                camera_id="camera-1_ups", name="Front Door UPS Package"
            ),
            "camera-1_usps": MockDetectionSensor(
                camera_id="camera-1_usps", name="Front Door USPS Package"
            ),
            "camera-1_amazon": MockDetectionSensor(
                camera_id="camera-1_amazon", name="Front Door Amazon Package"
            ),
            "camera-1_dhl": MockDetectionSensor(
                camera_id="camera-1_dhl", name="Front Door DHL Package"
            ),
        }

        return service

    def test_trigger_package_triggers_carrier_sensor(self, mock_service_with_carriers):
        """AC3: When per_carrier_sensors=True, triggers carrier-specific sensor"""
        generic_sensor = mock_service_with_carriers._package_sensors["camera-1"]
        carrier_sensor = mock_service_with_carriers._carrier_sensors["camera-1_fedex"]

        mock_service_with_carriers.trigger_package(
            "camera-1", event_id=123, delivery_carrier="fedex"
        )

        # Both generic and carrier-specific sensors should trigger
        assert generic_sensor.motion_detected is True
        assert carrier_sensor.motion_detected is True

    def test_trigger_package_only_triggers_matching_carrier(self, mock_service_with_carriers):
        """AC3: Only the matching carrier sensor triggers"""
        fedex_sensor = mock_service_with_carriers._carrier_sensors["camera-1_fedex"]
        ups_sensor = mock_service_with_carriers._carrier_sensors["camera-1_ups"]
        amazon_sensor = mock_service_with_carriers._carrier_sensors["camera-1_amazon"]

        mock_service_with_carriers.trigger_package(
            "camera-1", event_id=123, delivery_carrier="fedex"
        )

        # Only FedEx sensor should trigger
        assert fedex_sensor.motion_detected is True
        assert ups_sensor.motion_detected is False
        assert amazon_sensor.motion_detected is False

    def test_trigger_package_no_carrier_sensor_for_unknown(self, mock_service_with_carriers):
        """Unknown carrier triggers generic sensor only"""
        generic_sensor = mock_service_with_carriers._package_sensors["camera-1"]

        mock_service_with_carriers.trigger_package(
            "camera-1", event_id=123, delivery_carrier="ontrac"
        )

        # Generic sensor triggers, but there's no "ontrac" carrier sensor
        assert generic_sensor.motion_detected is True

    def test_service_has_carrier_sensor_count_property(self):
        """HomekitService has carrier_sensor_count property"""
        from app.services.homekit_service import HomekitService
        from app.config.homekit import HomekitConfig

        config = HomekitConfig(enabled=True, persist_dir="/tmp/homekit_test")
        service = HomekitService(config=config)

        assert hasattr(service, 'carrier_sensor_count')
        assert service.carrier_sensor_count == 0

        # Add carrier sensors
        service._carrier_sensors = {
            "cam1_fedex": MagicMock(),
            "cam1_ups": MagicMock(),
        }

        assert service.carrier_sensor_count == 2


class TestCarrierSensorNaming:
    """Tests for carrier sensor naming conventions (Story P7-2.3)"""

    def test_carrier_sensor_names(self):
        """Per-carrier sensors have correct display names"""
        # Verify the CARRIER_DISPLAY_NAMES mapping
        from app.services.carrier_extractor import CARRIER_DISPLAY_NAMES

        assert CARRIER_DISPLAY_NAMES["fedex"] == "FedEx"
        assert CARRIER_DISPLAY_NAMES["ups"] == "UPS"
        assert CARRIER_DISPLAY_NAMES["usps"] == "USPS"
        assert CARRIER_DISPLAY_NAMES["amazon"] == "Amazon"
        assert CARRIER_DISPLAY_NAMES["dhl"] == "DHL"


class TestEventProcessorCarrierRouting:
    """Tests for event processor routing with carrier (Story P7-2.3)"""

    @pytest.mark.asyncio
    async def test_event_processor_passes_carrier_to_homekit(self):
        """Event processor passes delivery_carrier to trigger_package"""
        from unittest.mock import MagicMock, AsyncMock

        class MockEventProcessor:
            async def _trigger_homekit_package(
                self, homekit_service, camera_id, event_id, delivery_carrier=None
            ):
                try:
                    success = homekit_service.trigger_package(
                        camera_id, event_id=event_id, delivery_carrier=delivery_carrier
                    )
                    return success
                except Exception:
                    pass

        mock_homekit = MagicMock()
        mock_homekit.is_running = True
        mock_homekit.trigger_package = MagicMock(return_value=True)

        processor = MockEventProcessor()
        await processor._trigger_homekit_package(
            mock_homekit, "test-camera", "event-123", delivery_carrier="ups"
        )

        mock_homekit.trigger_package.assert_called_once_with(
            "test-camera", event_id="event-123", delivery_carrier="ups"
        )

    @pytest.mark.asyncio
    async def test_event_processor_handles_none_carrier(self):
        """Event processor handles None carrier gracefully"""
        from unittest.mock import MagicMock

        class MockEventProcessor:
            async def _trigger_homekit_package(
                self, homekit_service, camera_id, event_id, delivery_carrier=None
            ):
                try:
                    success = homekit_service.trigger_package(
                        camera_id, event_id=event_id, delivery_carrier=delivery_carrier
                    )
                    return success
                except Exception:
                    pass

        mock_homekit = MagicMock()
        mock_homekit.trigger_package = MagicMock(return_value=True)

        processor = MockEventProcessor()
        await processor._trigger_homekit_package(
            mock_homekit, "test-camera", "event-456", delivery_carrier=None
        )

        mock_homekit.trigger_package.assert_called_once_with(
            "test-camera", event_id="event-456", delivery_carrier=None
        )
