"""
Tests for MQTT Discovery Service (Story P4-2.2)

Tests cover:
- Discovery config generation (AC1, AC3)
- Discovery publishing (AC1, AC5)
- Sensor removal (AC4)
- Availability/LWT support (AC7)
- Discovery toggle (AC6)
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import json

from app.services.mqtt_discovery_service import (
    MQTTDiscoveryService,
    get_discovery_service,
    on_camera_deleted,
    on_camera_disabled,
)
from app.models.mqtt_config import MQTTConfig


class TestDiscoveryConfigGeneration:
    """Tests for discovery config payload generation (AC1, AC3)."""

    def test_generate_sensor_config_basic(self):
        """Generate discovery config with basic camera info."""
        service = MQTTDiscoveryService()

        # Create mock camera
        mock_camera = MagicMock()
        mock_camera.id = "camera-123"
        mock_camera.name = "Front Door"
        mock_camera.source_type = "rtsp"
        mock_camera.type = "rtsp"
        mock_camera.is_doorbell = False

        config = service.generate_sensor_config(mock_camera, topic_prefix="liveobject")

        # Verify entity identification (AC1)
        assert config["name"] == "Front Door AI Events"
        assert config["unique_id"] == "liveobject_camera-123_event"
        assert config["object_id"] == "liveobject_camera-123_event"

        # Verify state topic
        assert config["state_topic"] == "liveobject/camera/camera-123/event"

        # Verify value template
        assert "value_json.description" in config["value_template"]

        # Verify JSON attributes topic
        assert config["json_attributes_topic"] == "liveobject/camera/camera-123/event"

    def test_generate_sensor_config_device_grouping(self):
        """Generate config includes device grouping info (AC3)."""
        service = MQTTDiscoveryService()

        mock_camera = MagicMock()
        mock_camera.id = "camera-456"
        mock_camera.name = "Back Yard"
        mock_camera.source_type = "protect"
        mock_camera.type = "rtsp"
        mock_camera.is_doorbell = False

        config = service.generate_sensor_config(mock_camera)

        # Verify device info (AC3)
        assert "device" in config
        device = config["device"]
        assert device["identifiers"] == ["liveobject_camera-456"]
        assert device["name"] == "Back Yard"
        assert device["manufacturer"] == "ArgusAI"
        assert device["model"] == "AI Classifier - Protect"
        assert "sw_version" in device

    def test_generate_sensor_config_availability(self):
        """Generate config includes availability settings (AC7)."""
        service = MQTTDiscoveryService()

        mock_camera = MagicMock()
        mock_camera.id = "camera-789"
        mock_camera.name = "Side Gate"
        mock_camera.source_type = "usb"
        mock_camera.type = "usb"
        mock_camera.is_doorbell = False

        config = service.generate_sensor_config(mock_camera, topic_prefix="custom")

        # Verify availability configuration (AC7)
        assert config["availability_topic"] == "custom/status"
        assert config["payload_available"] == "online"
        assert config["payload_not_available"] == "offline"

    def test_generate_sensor_config_doorbell_icon(self):
        """Doorbell cameras get doorbell icon."""
        service = MQTTDiscoveryService()

        mock_camera = MagicMock()
        mock_camera.id = "camera-bell"
        mock_camera.name = "Front Door Bell"
        mock_camera.source_type = "protect"
        mock_camera.type = "rtsp"
        mock_camera.is_doorbell = True

        config = service.generate_sensor_config(mock_camera)

        assert config["icon"] == "mdi:doorbell-video"

    def test_generate_sensor_config_standard_icon(self):
        """Standard cameras get CCTV icon."""
        service = MQTTDiscoveryService()

        mock_camera = MagicMock()
        mock_camera.id = "camera-std"
        mock_camera.name = "Driveway"
        mock_camera.source_type = "rtsp"
        mock_camera.type = "rtsp"
        mock_camera.is_doorbell = False

        config = service.generate_sensor_config(mock_camera)

        assert config["icon"] == "mdi:cctv"

    def test_get_discovery_topic(self):
        """Get discovery topic follows HA format."""
        service = MQTTDiscoveryService()

        # Default prefix
        topic = service.get_discovery_topic("camera-123")
        assert topic == "homeassistant/sensor/liveobject_camera-123_event/config"

        # Custom prefix
        topic = service.get_discovery_topic("camera-456", discovery_prefix="custom")
        assert topic == "custom/sensor/liveobject_camera-456_event/config"


class TestDiscoveryPublishing:
    """Tests for discovery config publishing (AC1, AC5, AC6)."""

    @pytest.mark.asyncio
    async def test_publish_discovery_config_not_connected(self):
        """Publish fails gracefully when MQTT not connected."""
        mock_mqtt = MagicMock()
        mock_mqtt.is_connected = False

        service = MQTTDiscoveryService(mqtt_service=mock_mqtt)

        mock_camera = MagicMock()
        mock_camera.id = "camera-123"
        mock_camera.name = "Test"

        mock_config = MagicMock()
        mock_config.discovery_enabled = True

        result = await service.publish_discovery_config(mock_camera, mock_config)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_discovery_config_disabled(self):
        """Publish skipped when discovery_enabled=False (AC6)."""
        mock_mqtt = MagicMock()
        mock_mqtt.is_connected = True

        service = MQTTDiscoveryService(mqtt_service=mock_mqtt)

        mock_camera = MagicMock()
        mock_camera.id = "camera-123"
        mock_camera.name = "Test"

        mock_config = MagicMock()
        mock_config.discovery_enabled = False  # Disabled (AC6)

        result = await service.publish_discovery_config(mock_camera, mock_config)

        assert result is False
        mock_mqtt.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_discovery_config_success(self):
        """Publish discovery config successfully (AC1)."""
        mock_mqtt = MagicMock()
        mock_mqtt.is_connected = True
        mock_mqtt.publish = AsyncMock(return_value=True)

        service = MQTTDiscoveryService(mqtt_service=mock_mqtt)

        mock_camera = MagicMock()
        mock_camera.id = "camera-123"
        mock_camera.name = "Front Door"
        mock_camera.source_type = "protect"
        mock_camera.type = "rtsp"
        mock_camera.is_doorbell = False

        mock_config = MagicMock()
        mock_config.discovery_enabled = True
        mock_config.topic_prefix = "liveobject"
        mock_config.discovery_prefix = "homeassistant"

        result = await service.publish_discovery_config(mock_camera, mock_config)

        assert result is True
        # Service now publishes 6 sensors per camera: event, status, last_event, events_today, events_week, activity
        assert mock_mqtt.publish.call_count == 6

        # Verify the event sensor was published (use exact topic match)
        call_args_list = mock_mqtt.publish.call_args_list
        event_sensor_calls = [c for c in call_args_list if c.kwargs.get("topic", "") == "homeassistant/sensor/liveobject_camera-123_event/config"]
        assert len(event_sensor_calls) == 1

        call_args = event_sensor_calls[0]
        assert call_args.kwargs["topic"] == "homeassistant/sensor/liveobject_camera-123_event/config"
        assert call_args.kwargs["qos"] == 1
        assert call_args.kwargs["retain"] is True

        # Verify payload structure
        payload = call_args.kwargs["payload"]
        assert payload["unique_id"] == "liveobject_camera-123_event"
        assert payload["name"] == "Front Door AI Events"

    @pytest.mark.asyncio
    async def test_publish_discovery_config_tracks_camera(self):
        """Published cameras are tracked for later removal."""
        mock_mqtt = MagicMock()
        mock_mqtt.is_connected = True
        mock_mqtt.publish = AsyncMock(return_value=True)

        service = MQTTDiscoveryService(mqtt_service=mock_mqtt)

        mock_camera = MagicMock()
        mock_camera.id = "camera-tracked"
        mock_camera.name = "Test"
        mock_camera.source_type = "rtsp"
        mock_camera.type = "rtsp"
        mock_camera.is_doorbell = False

        mock_config = MagicMock()
        mock_config.discovery_enabled = True
        mock_config.topic_prefix = "liveobject"
        mock_config.discovery_prefix = "homeassistant"

        await service.publish_discovery_config(mock_camera, mock_config)

        assert "camera-tracked" in service._published_cameras


class TestSensorRemoval:
    """Tests for discovery config removal (AC4)."""

    @pytest.mark.asyncio
    async def test_remove_discovery_config_not_connected(self):
        """Removal cleans up tracking even when MQTT not connected."""
        mock_mqtt = MagicMock()
        mock_mqtt.is_connected = False
        mock_mqtt._client = None

        service = MQTTDiscoveryService(mqtt_service=mock_mqtt)
        service._published_cameras.add("camera-123")

        mock_config = MagicMock()
        mock_config.discovery_prefix = "homeassistant"

        result = await service.remove_discovery_config("camera-123", mock_config)

        # Should return False (not published) but remove from tracking
        assert result is False
        assert "camera-123" not in service._published_cameras

    @pytest.mark.asyncio
    async def test_remove_discovery_config_publishes_empty(self):
        """Remove publishes empty payload to discovery topic (AC4)."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result

        mock_mqtt = MagicMock()
        mock_mqtt.is_connected = True
        mock_mqtt._client = mock_client

        service = MQTTDiscoveryService(mqtt_service=mock_mqtt)
        service._published_cameras.add("camera-456")

        mock_config = MagicMock()
        mock_config.discovery_prefix = "homeassistant"

        result = await service.remove_discovery_config("camera-456", mock_config)

        assert result is True
        assert "camera-456" not in service._published_cameras

        # Verify empty payloads published for all 6 sensors
        assert mock_client.publish.call_count == 6

        # Verify the event sensor was removed (use exact topic match)
        call_args_list = mock_client.publish.call_args_list
        event_calls = [c for c in call_args_list if c[0][0] == "homeassistant/sensor/liveobject_camera-456_event/config"]
        assert len(event_calls) == 1
        call_args = event_calls[0]
        assert call_args[0][0] == "homeassistant/sensor/liveobject_camera-456_event/config"
        assert call_args[1]["payload"] == ""
        assert call_args[1]["retain"] is True


class TestAvailabilitySupport:
    """Tests for LWT and availability (AC7)."""

    @pytest.mark.asyncio
    async def test_publish_online_status(self):
        """Online status published to status topic (AC7)."""
        mock_client = MagicMock()

        mock_mqtt = MagicMock()
        mock_mqtt._client = mock_client

        service = MQTTDiscoveryService(mqtt_service=mock_mqtt)

        # Mock database query
        mock_config = MagicMock()
        mock_config.topic_prefix = "liveobject"

        with patch('app.services.mqtt_discovery_service.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_db.query.return_value.first.return_value = mock_config
            mock_session.return_value.__enter__.return_value = mock_db

            await service._publish_online_status()

        # Verify "online" published
        mock_client.publish.assert_called_once()
        call_args = mock_client.publish.call_args
        assert call_args[0][0] == "liveobject/status"
        assert call_args[1]["payload"] == "online"
        assert call_args[1]["retain"] is True


class TestDiscoveryServiceSingleton:
    """Tests for service singleton pattern."""

    def test_get_discovery_service_returns_same_instance(self):
        """get_discovery_service returns singleton."""
        # Clear singleton for test
        import app.services.mqtt_discovery_service as discovery_module
        discovery_module._discovery_service = None

        service1 = get_discovery_service()
        service2 = get_discovery_service()

        assert service1 is service2


class TestCameraHooks:
    """Tests for camera lifecycle hooks."""

    @pytest.mark.asyncio
    async def test_on_camera_deleted_calls_remove(self):
        """on_camera_deleted triggers discovery removal."""
        import app.services.mqtt_discovery_service as discovery_module

        mock_service = MagicMock()
        mock_service.remove_discovery_config = AsyncMock()

        discovery_module._discovery_service = mock_service

        await on_camera_deleted("camera-to-delete")

        mock_service.remove_discovery_config.assert_called_once_with("camera-to-delete")

    @pytest.mark.asyncio
    async def test_on_camera_disabled_calls_remove(self):
        """on_camera_disabled triggers discovery removal."""
        import app.services.mqtt_discovery_service as discovery_module

        mock_service = MagicMock()
        mock_service.remove_discovery_config = AsyncMock()

        discovery_module._discovery_service = mock_service

        await on_camera_disabled("camera-to-disable")

        mock_service.remove_discovery_config.assert_called_once_with("camera-to-disable")
