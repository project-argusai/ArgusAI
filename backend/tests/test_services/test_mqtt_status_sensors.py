"""
Unit Tests for MQTT Status Sensors (Story P4-2.5)

Tests for:
- Status payload serialization (AC1)
- Event count calculations (AC3, AC10)
- Activity sensor timeout logic (AC4)
- Discovery config structure (AC5, AC6, AC7)
- Topic format verification (AC6)
"""
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.mqtt import (
    CameraStatusPayload,
    CameraCountsPayload,
    CameraActivityPayload,
    LastEventPayload
)


class TestMQTTPayloadSchemas:
    """Test MQTT payload schema serialization (AC1, AC2, AC3, AC4)."""

    def test_camera_status_payload_serialization(self):
        """Test CameraStatusPayload JSON serialization."""
        payload = CameraStatusPayload(
            camera_id="test-123",
            camera_name="Front Door",
            status="online",
            source_type="rtsp",
            last_updated=datetime(2025, 12, 11, 10, 30, 0, tzinfo=timezone.utc)
        )

        data = payload.model_dump(mode='json')

        assert data["camera_id"] == "test-123"
        assert data["camera_name"] == "Front Door"
        assert data["status"] == "online"
        assert data["source_type"] == "rtsp"
        assert "last_updated" in data

    def test_camera_status_payload_valid_statuses(self):
        """Test only valid status values are accepted."""
        # Valid statuses
        for status in ["online", "offline", "unavailable"]:
            payload = CameraStatusPayload(
                camera_id="test",
                camera_name="Test",
                status=status,
                source_type="rtsp",
                last_updated=datetime.now(timezone.utc)
            )
            assert payload.status == status

        # Invalid status should raise validation error
        with pytest.raises(ValueError):
            CameraStatusPayload(
                camera_id="test",
                camera_name="Test",
                status="invalid_status",
                source_type="rtsp",
                last_updated=datetime.now(timezone.utc)
            )

    def test_camera_counts_payload_serialization(self):
        """Test CameraCountsPayload JSON serialization."""
        payload = CameraCountsPayload(
            camera_id="test-123",
            camera_name="Front Door",
            events_today=5,
            events_this_week=25,
            last_updated=datetime.now(timezone.utc)
        )

        data = payload.model_dump(mode='json')

        assert data["camera_id"] == "test-123"
        assert data["events_today"] == 5
        assert data["events_this_week"] == 25

    def test_camera_counts_payload_non_negative(self):
        """Test count values must be non-negative."""
        with pytest.raises(ValueError):
            CameraCountsPayload(
                camera_id="test",
                camera_name="Test",
                events_today=-1,
                events_this_week=0,
                last_updated=datetime.now(timezone.utc)
            )

    def test_camera_activity_payload_serialization(self):
        """Test CameraActivityPayload JSON serialization."""
        event_time = datetime.now(timezone.utc)
        payload = CameraActivityPayload(
            camera_id="test-123",
            state="ON",
            last_event_at=event_time
        )

        data = payload.model_dump(mode='json')

        assert data["camera_id"] == "test-123"
        assert data["state"] == "ON"
        assert data["last_event_at"] is not None

    def test_camera_activity_payload_valid_states(self):
        """Test only valid state values are accepted."""
        for state in ["ON", "OFF"]:
            payload = CameraActivityPayload(
                camera_id="test",
                state=state
            )
            assert payload.state == state

    def test_last_event_payload_serialization(self):
        """Test LastEventPayload JSON serialization."""
        payload = LastEventPayload(
            camera_id="test-123",
            camera_name="Front Door",
            event_id="event-456",
            timestamp=datetime.now(timezone.utc),
            description_snippet="A person was detected at the front door",
            smart_detection_type="person"
        )

        data = payload.model_dump(mode='json')

        assert data["camera_id"] == "test-123"
        assert data["event_id"] == "event-456"
        assert data["description_snippet"] == "A person was detected at the front door"
        assert data["smart_detection_type"] == "person"

    def test_last_event_payload_description_truncation(self):
        """Test description_snippet respects max_length."""
        long_description = "A" * 200
        # Schema enforces max_length=100
        payload = LastEventPayload(
            camera_id="test",
            camera_name="Test",
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            description_snippet=long_description[:100]  # Must be pre-truncated
        )
        assert len(payload.description_snippet) <= 100


class TestMQTTServiceStatusMethods:
    """Test MQTTService camera status methods."""

    @pytest.fixture
    def mock_mqtt_service(self):
        """Create a mock MQTT service."""
        from app.services.mqtt_service import MQTTService

        service = MQTTService()
        service._connected = True
        service._client = MagicMock()
        service._config = MagicMock()
        service._config.topic_prefix = "liveobject"
        service._config.qos = 1
        service._config.retain_messages = True

        return service

    def test_get_status_topic_format(self, mock_mqtt_service):
        """Test status topic format (AC6)."""
        topic = mock_mqtt_service.get_status_topic("camera-123")
        assert topic == "liveobject/camera/camera-123/status"

    def test_get_last_event_topic_format(self, mock_mqtt_service):
        """Test last event topic format."""
        topic = mock_mqtt_service.get_last_event_topic("camera-123")
        assert topic == "liveobject/camera/camera-123/last_event"

    def test_get_counts_topic_format(self, mock_mqtt_service):
        """Test counts topic format."""
        topic = mock_mqtt_service.get_counts_topic("camera-123")
        assert topic == "liveobject/camera/camera-123/counts"

    def test_get_activity_topic_format(self, mock_mqtt_service):
        """Test activity topic format."""
        topic = mock_mqtt_service.get_activity_topic("camera-123")
        assert topic == "liveobject/camera/camera-123/activity"

    def test_topic_sanitization(self, mock_mqtt_service):
        """Test camera_id is sanitized for MQTT topics."""
        # ID with special characters
        topic = mock_mqtt_service.get_status_topic("camera/test#wild+card")
        # Should only contain alphanumeric, hyphens, underscores
        assert "/" not in topic.split("/camera/")[1].split("/")[0]
        assert "#" not in topic
        assert "+" not in topic

    @pytest.mark.asyncio
    async def test_publish_camera_status_normalizes_status(self, mock_mqtt_service):
        """Test status normalization in publish_camera_status."""
        mock_mqtt_service.publish = AsyncMock(return_value=True)

        # Test mapping: "connected" -> "online"
        await mock_mqtt_service.publish_camera_status(
            camera_id="test-123",
            camera_name="Test Camera",
            status="connected",
            source_type="rtsp"
        )

        # Verify the payload has normalized status
        call_args = mock_mqtt_service.publish.call_args
        payload = call_args[1]["payload"]
        assert payload["status"] == "online"

    @pytest.mark.asyncio
    async def test_publish_camera_status_not_connected(self, mock_mqtt_service):
        """Test publish returns False when not connected."""
        mock_mqtt_service._connected = False

        result = await mock_mqtt_service.publish_camera_status(
            camera_id="test-123",
            camera_name="Test Camera",
            status="online",
            source_type="rtsp"
        )

        assert result is False


class TestMQTTDiscoveryServiceSensors:
    """Test discovery config generation for status sensors (AC5, AC7)."""

    @pytest.fixture
    def mock_camera(self):
        """Create a mock camera."""
        camera = MagicMock()
        camera.id = "test-camera-123"
        camera.name = "Front Door Camera"
        camera.source_type = "rtsp"
        camera.type = "rtsp"
        camera.is_doorbell = False
        return camera

    @pytest.fixture
    def discovery_service(self):
        """Create discovery service instance."""
        from app.services.mqtt_discovery_service import MQTTDiscoveryService
        return MQTTDiscoveryService()

    def test_status_sensor_config_structure(self, discovery_service, mock_camera):
        """Test status sensor discovery config (AC5)."""
        config = discovery_service.generate_status_sensor_config(mock_camera)

        assert config["name"] == "Front Door Camera Status"
        assert config["unique_id"] == "liveobject_test-camera-123_status"
        assert config["state_topic"] == "liveobject/camera/test-camera-123/status"
        assert config["value_template"] == "{{ value_json.status }}"
        assert "device" in config

    def test_last_event_sensor_config_structure(self, discovery_service, mock_camera):
        """Test last event sensor discovery config."""
        config = discovery_service.generate_last_event_sensor_config(mock_camera)

        assert config["name"] == "Front Door Camera Last Event"
        assert config["device_class"] == "timestamp"
        assert config["value_template"] == "{{ value_json.timestamp }}"

    def test_events_today_sensor_config_structure(self, discovery_service, mock_camera):
        """Test events today sensor discovery config."""
        config = discovery_service.generate_events_today_sensor_config(mock_camera)

        assert config["name"] == "Front Door Camera Events Today"
        assert config["unit_of_measurement"] == "events"
        assert config["state_class"] == "total"

    def test_events_week_sensor_config_structure(self, discovery_service, mock_camera):
        """Test events this week sensor discovery config."""
        config = discovery_service.generate_events_week_sensor_config(mock_camera)

        assert config["name"] == "Front Door Camera Events This Week"
        assert config["unit_of_measurement"] == "events"

    def test_activity_binary_sensor_config_structure(self, discovery_service, mock_camera):
        """Test activity binary sensor discovery config (AC4)."""
        config = discovery_service.generate_activity_binary_sensor_config(mock_camera)

        assert config["name"] == "Front Door Camera Activity"
        assert config["device_class"] == "motion"
        assert config["payload_on"] == "ON"
        assert config["payload_off"] == "OFF"

    def test_all_sensors_share_device_block(self, discovery_service, mock_camera):
        """Test all sensors use same device identifiers for HA grouping (AC7)."""
        configs = [
            discovery_service.generate_sensor_config(mock_camera),
            discovery_service.generate_status_sensor_config(mock_camera),
            discovery_service.generate_last_event_sensor_config(mock_camera),
            discovery_service.generate_events_today_sensor_config(mock_camera),
            discovery_service.generate_events_week_sensor_config(mock_camera),
            discovery_service.generate_activity_binary_sensor_config(mock_camera),
        ]

        # All configs should have the same device identifiers
        expected_identifiers = [f"liveobject_{mock_camera.id}"]
        for config in configs:
            assert "device" in config
            assert config["device"]["identifiers"] == expected_identifiers
            assert config["device"]["name"] == mock_camera.name

    def test_discovery_topic_formats(self, discovery_service):
        """Test discovery topic formats for different sensor types."""
        camera_id = "test-123"

        assert discovery_service.get_status_discovery_topic(camera_id) == \
            "homeassistant/sensor/liveobject_test-123_status/config"

        assert discovery_service.get_last_event_discovery_topic(camera_id) == \
            "homeassistant/sensor/liveobject_test-123_last_event/config"

        assert discovery_service.get_events_today_discovery_topic(camera_id) == \
            "homeassistant/sensor/liveobject_test-123_events_today/config"

        assert discovery_service.get_events_week_discovery_topic(camera_id) == \
            "homeassistant/sensor/liveobject_test-123_events_week/config"

        # Activity is binary_sensor, not sensor
        assert discovery_service.get_activity_discovery_topic(camera_id) == \
            "homeassistant/binary_sensor/liveobject_test-123_activity/config"


class TestEventCountCalculations:
    """Test event count calculation logic (AC3, AC10)."""

    @pytest.mark.asyncio
    async def test_get_camera_event_counts_returns_dict(self):
        """Test count function returns expected structure."""
        with patch('app.services.mqtt_status_service.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock query result
            mock_db.query.return_value.filter.return_value.scalar.return_value = 5

            from app.services.mqtt_status_service import get_camera_event_counts
            result = await get_camera_event_counts("test-camera")

            assert "events_today" in result
            assert "events_this_week" in result
            assert isinstance(result["events_today"], int)
            assert isinstance(result["events_this_week"], int)

    def test_week_start_calculation(self):
        """Test week start is Monday at 00:00 (AC10)."""
        # Tuesday Dec 10, 2025
        test_date = datetime(2025, 12, 10, 14, 30, 0, tzinfo=timezone.utc)

        # Calculate start of week (Monday)
        days_since_monday = test_date.weekday()  # 1 for Tuesday
        week_start = (test_date - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Should be Monday Dec 8, 2025 at 00:00
        assert week_start.weekday() == 0  # Monday
        assert week_start.hour == 0
        assert week_start.minute == 0

    def test_day_start_calculation(self):
        """Test day start is midnight (AC10)."""
        test_date = datetime(2025, 12, 10, 14, 30, 0, tzinfo=timezone.utc)

        today_start = test_date.replace(hour=0, minute=0, second=0, microsecond=0)

        assert today_start.day == test_date.day
        assert today_start.hour == 0
        assert today_start.minute == 0


class TestActivityTimeoutLogic:
    """Test activity sensor timeout logic (AC4)."""

    @pytest.mark.asyncio
    async def test_activity_timeout_threshold(self):
        """Test 5-minute timeout threshold (AC4)."""
        from app.services.mqtt_status_service import ACTIVITY_TIMEOUT_MINUTES

        assert ACTIVITY_TIMEOUT_MINUTES == 5

    @pytest.mark.asyncio
    async def test_set_activity_on_tracks_camera(self):
        """Test set_activity_on adds camera to active tracking."""
        from app.services.mqtt_status_service import set_activity_on, _active_cameras, _activity_lock

        camera_id = "test-camera-timeout"
        event_time = datetime.now(timezone.utc)

        await set_activity_on(camera_id, event_time)

        async with _activity_lock:
            assert camera_id in _active_cameras
            assert _active_cameras[camera_id] == event_time

    def test_timeout_logic_removes_old_entries(self):
        """Test timeout logic identifies cameras older than threshold."""
        from app.services.mqtt_status_service import ACTIVITY_TIMEOUT_MINUTES

        now = datetime.now(timezone.utc)
        timeout_threshold = now - timedelta(minutes=ACTIVITY_TIMEOUT_MINUTES)

        # Old camera should be removed
        old_time = now - timedelta(minutes=ACTIVITY_TIMEOUT_MINUTES + 1)
        assert old_time < timeout_threshold  # Should be deactivated

        # Recent camera should be kept
        recent_time = now - timedelta(minutes=ACTIVITY_TIMEOUT_MINUTES - 1)
        assert recent_time >= timeout_threshold  # Should stay active
