"""
Tests for Integrations API endpoints (Story P4-2.1)

Tests cover:
- MQTT configuration endpoints (schemas and validation)
- MQTT status endpoint
- MQTT test connection endpoint
"""
import pytest
from pydantic import ValidationError

from app.api.v1.integrations import (
    MQTTConfigResponse,
    MQTTConfigUpdate,
    MQTTTestRequest,
    MQTTTestResponse,
    MQTTStatusResponse,
)


class TestMQTTConfigSchemas:
    """Tests for MQTT configuration Pydantic schemas."""

    def test_config_response_schema(self):
        """MQTTConfigResponse validates correctly."""
        response = MQTTConfigResponse(
            id="test-id",
            broker_host="mqtt.local",
            broker_port=1883,
            username="testuser",
            topic_prefix="liveobject",
            discovery_prefix="homeassistant",
            discovery_enabled=True,
            qos=1,
            enabled=True,
            retain_messages=True,
            use_tls=False,
            has_password=True,
            created_at="2025-12-10T10:00:00Z",
            updated_at="2025-12-10T10:00:00Z"
        )

        assert response.broker_host == "mqtt.local"
        assert response.broker_port == 1883
        assert response.has_password is True

    def test_config_response_optional_fields(self):
        """MQTTConfigResponse handles optional fields."""
        response = MQTTConfigResponse(
            id="test-id",
            broker_host="",
            broker_port=1883,
            username=None,
            topic_prefix="liveobject",
            discovery_prefix="homeassistant",
            discovery_enabled=True,
            qos=1,
            enabled=False,
            retain_messages=True,
            use_tls=False,
            has_password=False,
            created_at=None,
            updated_at=None
        )

        assert response.username is None
        assert response.created_at is None

    def test_config_update_schema(self):
        """MQTTConfigUpdate validates correctly."""
        update = MQTTConfigUpdate(
            broker_host="new-broker.local",
            broker_port=8883,
            username="newuser",
            password="newpass",
            topic_prefix="custom",
            discovery_prefix="homeassistant",
            discovery_enabled=True,
            qos=2,
            enabled=True,
            retain_messages=True,
            use_tls=True
        )

        assert update.broker_host == "new-broker.local"
        assert update.broker_port == 8883
        assert update.qos == 2
        assert update.use_tls is True

    def test_config_update_validates_empty_host(self):
        """MQTTConfigUpdate rejects empty broker_host."""
        with pytest.raises(ValidationError):
            MQTTConfigUpdate(
                broker_host="",  # Empty not allowed
                broker_port=1883,
                topic_prefix="liveobject",
                discovery_prefix="homeassistant",
                discovery_enabled=True,
                qos=1,
                enabled=True,
                retain_messages=True,
                use_tls=False
            )

    def test_config_update_validates_port_range(self):
        """MQTTConfigUpdate validates port range."""
        # Valid port
        update = MQTTConfigUpdate(
            broker_host="test.local",
            broker_port=8883,
            topic_prefix="liveobject",
            discovery_prefix="homeassistant",
            discovery_enabled=True,
            qos=1,
            enabled=True,
            retain_messages=True,
            use_tls=False
        )
        assert update.broker_port == 8883

        # Invalid port (too high)
        with pytest.raises(ValidationError):
            MQTTConfigUpdate(
                broker_host="test.local",
                broker_port=70000,
                topic_prefix="liveobject",
                discovery_prefix="homeassistant",
                discovery_enabled=True,
                qos=1,
                enabled=True,
                retain_messages=True,
                use_tls=False
            )

        # Invalid port (zero)
        with pytest.raises(ValidationError):
            MQTTConfigUpdate(
                broker_host="test.local",
                broker_port=0,
                topic_prefix="liveobject",
                discovery_prefix="homeassistant",
                discovery_enabled=True,
                qos=1,
                enabled=True,
                retain_messages=True,
                use_tls=False
            )

    def test_config_update_validates_qos(self):
        """MQTTConfigUpdate validates QoS values."""
        # Valid QoS values
        for qos in [0, 1, 2]:
            update = MQTTConfigUpdate(
                broker_host="test.local",
                broker_port=1883,
                topic_prefix="liveobject",
                discovery_prefix="homeassistant",
                discovery_enabled=True,
                qos=qos,
                enabled=True,
                retain_messages=True,
                use_tls=False
            )
            assert update.qos == qos

        # Invalid QoS
        with pytest.raises(ValidationError):
            MQTTConfigUpdate(
                broker_host="test.local",
                broker_port=1883,
                topic_prefix="liveobject",
                discovery_prefix="homeassistant",
                discovery_enabled=True,
                qos=3,
                enabled=True,
                retain_messages=True,
                use_tls=False
            )


class TestMQTTTestSchemas:
    """Tests for MQTT test connection schemas."""

    def test_test_request_schema(self):
        """MQTTTestRequest validates correctly."""
        request = MQTTTestRequest(
            broker_host="test.local",
            broker_port=1883,
            username="user",
            password="pass",
            use_tls=False
        )

        assert request.broker_host == "test.local"
        assert request.broker_port == 1883
        assert request.use_tls is False

    def test_test_request_optional_auth(self):
        """MQTTTestRequest allows optional auth."""
        request = MQTTTestRequest(
            broker_host="test.local",
            broker_port=1883,
            use_tls=False
        )

        assert request.username is None
        assert request.password is None

    def test_test_request_validates_host(self):
        """MQTTTestRequest validates host."""
        with pytest.raises(ValidationError):
            MQTTTestRequest(
                broker_host="",  # Empty not allowed
                broker_port=1883,
                use_tls=False
            )

    def test_test_response_schema(self):
        """MQTTTestResponse validates correctly."""
        response = MQTTTestResponse(
            success=True,
            message="Connected to broker"
        )

        assert response.success is True
        assert "Connected" in response.message


class TestMQTTStatusSchema:
    """Tests for MQTT status response schema."""

    def test_status_response_connected(self):
        """MQTTStatusResponse for connected state."""
        response = MQTTStatusResponse(
            connected=True,
            broker="mqtt.local:1883",
            last_connected_at="2025-12-10T10:00:00Z",
            messages_published=1234,
            last_error=None,
            reconnect_attempt=0
        )

        assert response.connected is True
        assert response.messages_published == 1234
        assert response.last_error is None

    def test_status_response_disconnected(self):
        """MQTTStatusResponse for disconnected state."""
        response = MQTTStatusResponse(
            connected=False,
            broker=None,
            last_connected_at=None,
            messages_published=0,
            last_error="Connection refused",
            reconnect_attempt=3
        )

        assert response.connected is False
        assert response.last_error == "Connection refused"
        assert response.reconnect_attempt == 3

    def test_status_response_optional_fields(self):
        """MQTTStatusResponse handles optional fields."""
        response = MQTTStatusResponse(
            connected=False,
            broker=None,
            last_connected_at=None,
            messages_published=0,
            last_error=None,
            reconnect_attempt=0
        )

        assert response.broker is None
        assert response.last_connected_at is None
