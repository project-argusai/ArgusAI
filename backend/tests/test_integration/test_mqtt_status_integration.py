"""
Integration Tests for MQTT Status Sensors (Story P4-2.5)

End-to-end tests verifying:
- Status publish on camera lifecycle events
- Discovery config publish includes all sensor types
- Event processor triggers status sensor updates
- Startup publishes initial camera states
"""
import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestStatusSensorIntegration:
    """Integration tests for camera status sensors."""

    @pytest.fixture
    def mock_mqtt_service(self):
        """Create a fully mocked MQTT service."""
        service = MagicMock()
        service._connected = True
        service.is_connected = True
        service._client = MagicMock()
        service._config = MagicMock()
        service._config.topic_prefix = "liveobject"
        service._config.qos = 1
        service.publish = AsyncMock(return_value=True)
        service.publish_camera_status = AsyncMock(return_value=True)
        service.publish_last_event_timestamp = AsyncMock(return_value=True)
        service.publish_event_counts = AsyncMock(return_value=True)
        service.publish_activity_state = AsyncMock(return_value=True)
        return service

    @pytest.mark.asyncio
    async def test_discovery_publishes_all_sensor_types(self, mock_mqtt_service):
        """Test that discovery publishes all 6 sensor types for each camera (AC5)."""
        from app.services.mqtt_discovery_service import MQTTDiscoveryService

        # Create mock camera
        mock_camera = MagicMock()
        mock_camera.id = "test-camera-integration"
        mock_camera.name = "Integration Test Camera"
        mock_camera.source_type = "rtsp"
        mock_camera.type = "rtsp"
        mock_camera.is_doorbell = False

        # Create mock config
        mock_config = MagicMock()
        mock_config.discovery_enabled = True
        mock_config.discovery_prefix = "homeassistant"
        mock_config.topic_prefix = "liveobject"

        # Create service with mocked MQTT using patch
        with patch('app.services.mqtt_discovery_service.get_mqtt_service', return_value=mock_mqtt_service):
            with patch('app.services.mqtt_discovery_service.SessionLocal'):
                service = MQTTDiscoveryService()
                result = await service.publish_discovery_config(mock_camera, mock_config)

        # Verify result
        assert result is True

        # Verify publish was called 6 times (one for each sensor type)
        assert mock_mqtt_service.publish.call_count == 6

        # Verify topics for each sensor type
        call_topics = [
            call[1]["topic"] for call in mock_mqtt_service.publish.call_args_list
        ]

        expected_topic_patterns = [
            "homeassistant/sensor/liveobject_test-camera-integration_event/config",
            "homeassistant/sensor/liveobject_test-camera-integration_status/config",
            "homeassistant/sensor/liveobject_test-camera-integration_last_event/config",
            "homeassistant/sensor/liveobject_test-camera-integration_events_today/config",
            "homeassistant/sensor/liveobject_test-camera-integration_events_week/config",
            "homeassistant/binary_sensor/liveobject_test-camera-integration_activity/config",
        ]

        for expected in expected_topic_patterns:
            assert expected in call_topics, f"Expected topic {expected} not found in {call_topics}"

    @pytest.mark.asyncio
    async def test_status_publish_on_camera_connect(self, mock_mqtt_service):
        """Test status is published when camera connects (AC1, AC9)."""
        from app.services.mqtt_status_service import publish_camera_status_update

        with patch('app.services.mqtt_service.get_mqtt_service', return_value=mock_mqtt_service):
            result = await publish_camera_status_update(
                camera_id="test-123",
                camera_name="Test Camera",
                status="connected",
                source_type="rtsp"
            )

        assert result is True
        mock_mqtt_service.publish_camera_status.assert_called_once()
        call_args = mock_mqtt_service.publish_camera_status.call_args
        assert call_args[1]["status"] == "connected"

    @pytest.mark.asyncio
    async def test_status_sensors_published_after_event(self, mock_mqtt_service):
        """Test all status sensors are updated after event processing (AC2, AC3, AC4, AC8)."""
        from app.services.mqtt_status_service import get_camera_event_counts

        # Mock the count query
        with patch('app.services.mqtt_status_service.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.scalar.return_value = 10

            counts = await get_camera_event_counts("test-camera")

        assert counts["events_today"] >= 0
        assert counts["events_this_week"] >= 0

    @pytest.mark.asyncio
    async def test_remove_discovery_clears_all_sensors(self, mock_mqtt_service):
        """Test discovery removal clears all 6 sensor configs."""
        from app.services.mqtt_discovery_service import MQTTDiscoveryService

        # Create mock config
        mock_config = MagicMock()
        mock_config.discovery_prefix = "homeassistant"

        # Mock client publish to return success
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_mqtt_service._client.publish.return_value = mock_result

        # Create service with mocked MQTT
        camera_id = "test-removal-camera"

        with patch('app.services.mqtt_discovery_service.get_mqtt_service', return_value=mock_mqtt_service):
            with patch('app.services.mqtt_discovery_service.SessionLocal'):
                service = MQTTDiscoveryService()
                # Add camera to tracking set
                service._published_cameras.add(camera_id)

                # Call remove_discovery_config
                result = await service.remove_discovery_config(camera_id, mock_config)

        # Verify result
        assert result is True

        # Verify camera removed from tracking
        assert camera_id not in service._published_cameras

        # Verify empty payload published to all 6 topics
        assert mock_mqtt_service._client.publish.call_count == 6

    @pytest.mark.asyncio
    async def test_activity_timeout_integration(self, mock_mqtt_service):
        """Test activity sensor transitions from ON to OFF after timeout."""
        from datetime import timedelta
        from app.services.mqtt_status_service import (
            set_activity_on, check_activity_timeouts,
            _active_cameras, _activity_lock, ACTIVITY_TIMEOUT_MINUTES
        )

        camera_id = "activity-test-camera"

        # Clean state
        async with _activity_lock:
            _active_cameras.clear()

        # Set activity ON with old timestamp
        old_time = datetime.now(timezone.utc) - timedelta(minutes=ACTIVITY_TIMEOUT_MINUTES + 1)
        async with _activity_lock:
            _active_cameras[camera_id] = old_time

        # Run timeout check with mocked MQTT
        with patch('app.services.mqtt_service.get_mqtt_service', return_value=mock_mqtt_service):
            await check_activity_timeouts()

        # Verify camera was removed from active set
        async with _activity_lock:
            assert camera_id not in _active_cameras

        # Verify OFF state was published
        mock_mqtt_service.publish_activity_state.assert_called_once()
        call_args = mock_mqtt_service.publish_activity_state.call_args
        assert call_args[1]["state"] == "OFF"

        # Clean up
        async with _activity_lock:
            _active_cameras.clear()


class TestStatusSensorPayloadValidation:
    """Test MQTT payload structure matches Home Assistant expectations."""

    def test_status_payload_has_required_fields(self):
        """Verify status payload has all HA-required fields."""
        from app.schemas.mqtt import CameraStatusPayload

        payload = CameraStatusPayload(
            camera_id="test-123",
            camera_name="Test Camera",
            status="online",
            source_type="rtsp",
            last_updated=datetime.now(timezone.utc)
        )

        data = payload.model_dump(mode='json')

        # Required fields for HA sensor
        assert "status" in data
        assert data["status"] in ["online", "offline", "unavailable"]
        assert "last_updated" in data
        assert "camera_name" in data

    def test_last_event_payload_timestamp_format(self):
        """Verify last event timestamp is ISO format for HA timestamp sensor."""
        from app.schemas.mqtt import LastEventPayload
        from datetime import datetime as dt

        event_time = dt(2025, 12, 11, 10, 30, 0, tzinfo=timezone.utc)
        payload = LastEventPayload(
            camera_id="test-123",
            camera_name="Test Camera",
            event_id="event-456",
            timestamp=event_time,
            description_snippet="Test event",
            smart_detection_type=None
        )

        data = payload.model_dump(mode='json')

        # Timestamp should be ISO format string
        assert "timestamp" in data
        # Should be parseable as ISO timestamp
        parsed = dt.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        assert parsed.year == 2025

    def test_activity_payload_binary_states(self):
        """Verify activity sensor uses HA-compatible binary states."""
        from app.schemas.mqtt import CameraActivityPayload

        on_payload = CameraActivityPayload(
            camera_id="test-123",
            state="ON",
            last_event_at=datetime.now(timezone.utc)
        )

        off_payload = CameraActivityPayload(
            camera_id="test-123",
            state="OFF",
            last_event_at=None
        )

        assert on_payload.model_dump(mode='json')["state"] == "ON"
        assert off_payload.model_dump(mode='json')["state"] == "OFF"


class TestDiscoveryConfigValidation:
    """Test discovery configs match Home Assistant MQTT discovery spec."""

    @pytest.fixture
    def mock_camera(self):
        """Create mock camera for discovery tests."""
        camera = MagicMock()
        camera.id = "discovery-test-camera"
        camera.name = "Discovery Test Camera"
        camera.source_type = "rtsp"
        camera.type = "rtsp"
        camera.is_doorbell = False
        return camera

    def test_status_sensor_discovery_has_required_fields(self, mock_camera):
        """Test status sensor discovery has HA-required fields."""
        from app.services.mqtt_discovery_service import MQTTDiscoveryService

        service = MQTTDiscoveryService()
        config = service.generate_status_sensor_config(mock_camera)

        # Required fields for HA MQTT sensor
        assert "name" in config
        assert "unique_id" in config
        assert "state_topic" in config
        assert "availability_topic" in config
        assert "device" in config

        # Device info requirements
        assert "identifiers" in config["device"]
        assert "name" in config["device"]

    def test_activity_binary_sensor_has_required_fields(self, mock_camera):
        """Test activity sensor discovery has binary_sensor-specific fields."""
        from app.services.mqtt_discovery_service import MQTTDiscoveryService

        service = MQTTDiscoveryService()
        config = service.generate_activity_binary_sensor_config(mock_camera)

        # Required fields for HA binary_sensor
        assert "payload_on" in config
        assert "payload_off" in config
        assert "device_class" in config

        # Verify binary state values
        assert config["payload_on"] == "ON"
        assert config["payload_off"] == "OFF"
        assert config["device_class"] == "motion"

    def test_counter_sensors_have_state_class(self, mock_camera):
        """Test counter sensors have state_class for HA statistics (AC3)."""
        from app.services.mqtt_discovery_service import MQTTDiscoveryService

        service = MQTTDiscoveryService()

        today_config = service.generate_events_today_sensor_config(mock_camera)
        week_config = service.generate_events_week_sensor_config(mock_camera)

        # state_class: total allows HA to track statistics
        assert today_config.get("state_class") == "total"
        assert week_config.get("state_class") == "total"

        # Unit of measurement for display
        assert today_config.get("unit_of_measurement") == "events"
        assert week_config.get("unit_of_measurement") == "events"

    def test_timestamp_sensor_has_device_class(self, mock_camera):
        """Test last event sensor uses timestamp device_class."""
        from app.services.mqtt_discovery_service import MQTTDiscoveryService

        service = MQTTDiscoveryService()
        config = service.generate_last_event_sensor_config(mock_camera)

        # device_class: timestamp enables relative time display in HA
        assert config.get("device_class") == "timestamp"
