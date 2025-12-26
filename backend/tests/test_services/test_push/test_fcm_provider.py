"""
Tests for FCM Provider.

Story P11-2.2: Unit tests for Android push notifications via FCM.
"""

import asyncio
import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from app.services.push.fcm_provider import FCMProvider, FIREBASE_AVAILABLE
from app.services.push.models import (
    FCMConfig,
    FCMPayload,
    DeliveryResult,
    DeliveryStatus,
    format_event_for_fcm,
)


# Skip all tests if firebase-admin is not installed
pytestmark = pytest.mark.skipif(
    not FIREBASE_AVAILABLE,
    reason="firebase-admin not installed"
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def test_credentials_file(tmp_path):
    """Create a temporary service account JSON file for testing."""
    creds = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "key123",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MoPl2Sb7e4RY5F+F\nfakekey123456789\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    creds_file = tmp_path / "service-account.json"
    creds_file.write_text(json.dumps(creds))
    return str(creds_file)


@pytest.fixture
def fcm_config(test_credentials_file):
    """Create a test FCM configuration."""
    return FCMConfig(
        project_id="test-project",
        credentials_path=test_credentials_file,
    )


@pytest.fixture
def sample_payload():
    """Create a sample FCM payload."""
    return FCMPayload(
        title="Front Door: Person Detected",
        body="A person was detected at the front door",
        image_url="https://example.com/thumb.jpg",
        data={
            "event_id": "evt-123",
            "camera_id": "cam-456",
            "camera_name": "Front Door",
        },
        channel_id="argusai_events",
        priority="high",
        icon="ic_notification",
        color="#4A90D9",
        tag="camera-123",
    )


@pytest.fixture
def mock_messaging():
    """Create a mock firebase_admin.messaging module."""
    mock = MagicMock()

    # Mock message classes
    mock.Message = MagicMock
    mock.MulticastMessage = MagicMock
    mock.Notification = MagicMock
    mock.AndroidConfig = MagicMock
    mock.AndroidNotification = MagicMock

    # Mock exceptions
    mock.UnregisteredError = type('UnregisteredError', (Exception,), {})
    mock.QuotaExceededError = type('QuotaExceededError', (Exception,), {})
    mock.ThirdPartyAuthError = type('ThirdPartyAuthError', (Exception,), {})
    mock.SenderIdMismatchError = type('SenderIdMismatchError', (Exception,), {})
    mock.UnavailableError = type('UnavailableError', (Exception,), {})

    return mock


# =============================================================================
# FCMConfig Tests
# =============================================================================

class TestFCMConfig:
    """Tests for FCMConfig model."""

    def test_valid_config(self, test_credentials_file):
        """Test valid configuration creation."""
        config = FCMConfig(
            project_id="my-project-123",
            credentials_path=test_credentials_file,
        )
        assert config.project_id == "my-project-123"
        assert config.credentials_path == test_credentials_file

    def test_credentials_path_validation_empty(self, test_credentials_file):
        """Test credentials_path cannot be empty."""
        with pytest.raises(ValueError):
            FCMConfig(
                project_id="my-project",
                credentials_path="",
            )

    def test_credentials_path_validation_whitespace(self, test_credentials_file):
        """Test credentials_path cannot be whitespace only."""
        with pytest.raises(ValueError):
            FCMConfig(
                project_id="my-project",
                credentials_path="   ",
            )


# =============================================================================
# FCMPayload Tests
# =============================================================================

class TestFCMPayload:
    """Tests for FCMPayload model."""

    def test_payload_creation(self, sample_payload):
        """Test payload creation with all fields."""
        assert sample_payload.title == "Front Door: Person Detected"
        assert sample_payload.body == "A person was detected at the front door"
        assert sample_payload.image_url == "https://example.com/thumb.jpg"
        assert sample_payload.channel_id == "argusai_events"
        assert sample_payload.priority == "high"
        assert sample_payload.icon == "ic_notification"
        assert sample_payload.color == "#4A90D9"
        assert sample_payload.tag == "camera-123"

    def test_payload_minimal(self):
        """Test minimal payload with only required fields."""
        payload = FCMPayload(
            title="Test",
            body="Test body",
        )
        assert payload.title == "Test"
        assert payload.body == "Test body"
        assert payload.channel_id == "argusai_events"  # Default
        assert payload.priority == "high"  # Default
        assert payload.data == {}  # Default empty

    def test_priority_validation_valid(self):
        """Test valid priority values."""
        for priority in ["high", "normal"]:
            payload = FCMPayload(
                title="Test",
                body="Body",
                priority=priority,
            )
            assert payload.priority == priority

    def test_priority_validation_invalid(self):
        """Test invalid priority value."""
        with pytest.raises(ValueError):
            FCMPayload(
                title="Test",
                body="Body",
                priority="low",  # Invalid
            )

    def test_color_validation_valid(self):
        """Test valid color formats."""
        for color in ["#FFF", "#FFFFFF", "#abc", "#aabbcc"]:
            payload = FCMPayload(
                title="Test",
                body="Body",
                color=color,
            )
            assert payload.color == color

    def test_color_validation_invalid(self):
        """Test invalid color formats."""
        for invalid_color in ["FFF", "FFFFFF", "#FFFFFFF", "#FF"]:
            with pytest.raises(ValueError):
                FCMPayload(
                    title="Test",
                    body="Body",
                    color=invalid_color,
                )

    def test_data_payload(self):
        """Test data payload for background processing."""
        payload = FCMPayload(
            title="Test",
            body="Body",
            data={
                "event_id": "evt-123",
                "action": "sync",
            },
        )
        assert payload.data["event_id"] == "evt-123"
        assert payload.data["action"] == "sync"


# =============================================================================
# FCMProvider Tests
# =============================================================================

class TestFCMProvider:
    """Tests for FCMProvider class."""

    def test_provider_creation(self, fcm_config):
        """Test provider is created correctly."""
        with patch('app.services.push.fcm_provider.FIREBASE_AVAILABLE', True):
            provider = FCMProvider(fcm_config)
            assert provider.config == fcm_config
            assert provider._initialized is False
            assert provider._app is None

    def test_provider_without_firebase(self, fcm_config):
        """Test provider raises error when firebase-admin not installed."""
        with patch('app.services.push.fcm_provider.FIREBASE_AVAILABLE', False):
            with pytest.raises(ImportError):
                FCMProvider(fcm_config)

    @pytest.mark.asyncio
    async def test_send_success(self, fcm_config, sample_payload, mock_messaging):
        """Test successful notification send."""
        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    # Setup mocks
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()
                    mock_messaging.send.return_value = "message-id-123"

                    provider = FCMProvider(fcm_config)

                    result = await provider.send("device-token-123", sample_payload)

                    assert result.success is True
                    assert result.status == DeliveryStatus.SUCCESS
                    assert result.apns_id == "message-id-123"
                    assert result.retries == 0

    @pytest.mark.asyncio
    async def test_send_unregistered_error(self, fcm_config, sample_payload, mock_messaging):
        """Test handling of unregistered device token."""
        invalidated_tokens = []

        def on_token_invalid(token):
            invalidated_tokens.append(token)

        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    # Setup mocks
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()

                    # Simulate UnregisteredError
                    mock_messaging.send.side_effect = mock_messaging.UnregisteredError("Unregistered")

                    provider = FCMProvider(fcm_config, on_token_invalid=on_token_invalid)

                    result = await provider.send("invalid-token", sample_payload)

                    assert result.success is False
                    assert result.status == DeliveryStatus.INVALID_TOKEN
                    assert "invalid-token" in invalidated_tokens

    @pytest.mark.asyncio
    async def test_send_quota_exceeded_with_retry(self, fcm_config, sample_payload, mock_messaging):
        """Test retry logic for quota exceeded error."""
        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    # Setup mocks
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()

                    # Always return quota exceeded to exhaust retries
                    mock_messaging.send.side_effect = mock_messaging.QuotaExceededError("Quota exceeded")

                    provider = FCMProvider(fcm_config)

                    with patch('asyncio.sleep', new_callable=AsyncMock):  # Skip delays
                        result = await provider.send("device-token", sample_payload)

                    assert result.success is False
                    assert result.status == DeliveryStatus.RATE_LIMITED
                    assert result.retries > 0  # Should have retried

    @pytest.mark.asyncio
    async def test_send_auth_error(self, fcm_config, sample_payload, mock_messaging):
        """Test handling of authentication error."""
        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    # Setup mocks
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()

                    mock_messaging.send.side_effect = mock_messaging.ThirdPartyAuthError("Auth failed")

                    provider = FCMProvider(fcm_config)

                    result = await provider.send("device-token", sample_payload)

                    assert result.success is False
                    assert result.status == DeliveryStatus.AUTH_ERROR

    @pytest.mark.asyncio
    async def test_send_sender_id_mismatch(self, fcm_config, sample_payload, mock_messaging):
        """Test handling of sender ID mismatch error."""
        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    # Setup mocks
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()

                    mock_messaging.send.side_effect = mock_messaging.SenderIdMismatchError("Wrong project")

                    provider = FCMProvider(fcm_config)

                    result = await provider.send("device-token", sample_payload)

                    assert result.success is False
                    assert result.status == DeliveryStatus.FAILED

    @pytest.mark.asyncio
    async def test_send_unavailable_with_retry(self, fcm_config, sample_payload, mock_messaging):
        """Test retry logic for service unavailable error."""
        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    # Setup mocks
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()

                    # First call unavailable, second success
                    mock_messaging.send.side_effect = [
                        mock_messaging.UnavailableError("Unavailable"),
                        "message-id-retry",
                    ]

                    provider = FCMProvider(fcm_config)

                    with patch('asyncio.sleep', new_callable=AsyncMock):  # Skip delays
                        result = await provider.send("device-token", sample_payload)

                    assert result.success is True
                    assert result.status == DeliveryStatus.SUCCESS
                    assert result.retries == 1

    @pytest.mark.asyncio
    async def test_send_data_only(self, fcm_config, mock_messaging):
        """Test data-only message for background processing."""
        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    # Setup mocks
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()
                    mock_messaging.send.return_value = "data-msg-id"

                    provider = FCMProvider(fcm_config)

                    result = await provider.send_data_only(
                        "device-token",
                        {"event_id": "evt-123", "sync": True},
                    )

                    assert result.success is True
                    assert result.status == DeliveryStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_send_batch_success(self, fcm_config, sample_payload, mock_messaging):
        """Test batch send to multiple devices."""
        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    # Setup mocks
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()

                    # Mock batch response
                    mock_response = MagicMock()
                    mock_response.responses = [
                        MagicMock(success=True, message_id="msg-1"),
                        MagicMock(success=True, message_id="msg-2"),
                        MagicMock(success=True, message_id="msg-3"),
                    ]
                    mock_messaging.send_each_for_multicast.return_value = mock_response

                    provider = FCMProvider(fcm_config)
                    tokens = ["token1", "token2", "token3"]

                    results = await provider.send_batch(tokens, sample_payload)

                    assert len(results) == 3
                    assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_send_batch_mixed_results(self, fcm_config, sample_payload, mock_messaging):
        """Test batch send with mixed success/failure."""
        invalidated_tokens = []

        def on_token_invalid(token):
            invalidated_tokens.append(token)

        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    # Setup mocks
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()

                    # Mock batch response with mixed results
                    mock_response = MagicMock()
                    mock_response.responses = [
                        MagicMock(success=True, message_id="msg-1"),
                        MagicMock(success=False, exception=mock_messaging.UnregisteredError("Unregistered")),
                        MagicMock(success=True, message_id="msg-3"),
                    ]
                    mock_messaging.send_each_for_multicast.return_value = mock_response

                    provider = FCMProvider(fcm_config, on_token_invalid=on_token_invalid)
                    tokens = ["token1", "token2", "token3"]

                    results = await provider.send_batch(tokens, sample_payload)

                    assert len(results) == 3
                    assert results[0].success is True
                    assert results[1].success is False
                    assert results[1].status == DeliveryStatus.INVALID_TOKEN
                    assert results[2].success is True
                    assert "token2" in invalidated_tokens

    @pytest.mark.asyncio
    async def test_context_manager(self, fcm_config, mock_messaging):
        """Test provider as async context manager."""
        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials'):
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_firebase.delete_app = MagicMock()

                    async with FCMProvider(fcm_config) as provider:
                        assert provider is not None
                        assert provider.config == fcm_config

    @pytest.mark.asyncio
    async def test_close(self, fcm_config, mock_messaging):
        """Test explicit close."""
        with patch('app.services.push.fcm_provider.messaging', mock_messaging):
            with patch('app.services.push.fcm_provider.firebase_admin') as mock_firebase:
                with patch('app.services.push.fcm_provider.credentials') as mock_creds:
                    mock_firebase.get_app.side_effect = ValueError("Not found")
                    mock_firebase.initialize_app.return_value = MagicMock()
                    mock_creds.Certificate.return_value = MagicMock()
                    mock_firebase.delete_app = MagicMock()

                    provider = FCMProvider(fcm_config)
                    provider._initialize()

                    await provider.close()

                    assert provider._app is None
                    assert provider._initialized is False
                    mock_firebase.delete_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_credentials_file_not_found(self, tmp_path):
        """Test error when credentials file doesn't exist."""
        config = FCMConfig(
            project_id="test-project",
            credentials_path=str(tmp_path / "nonexistent.json"),
        )

        with patch('app.services.push.fcm_provider.FIREBASE_AVAILABLE', True):
            provider = FCMProvider(config)

            payload = FCMPayload(title="Test", body="Body")
            result = await provider.send("device-token", payload)

            assert result.success is False
            assert result.status == DeliveryStatus.AUTH_ERROR
            assert "not found" in result.error.lower()


# =============================================================================
# format_event_for_fcm Tests
# =============================================================================

class TestFormatEventForFcm:
    """Tests for format_event_for_fcm helper."""

    def test_basic_event(self):
        """Test basic event formatting."""
        payload = format_event_for_fcm(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="A person was detected at the front door at 10:30 AM",
            smart_detection_type="person",
        )

        assert payload.title == "Front Door: Person Detected"
        assert "A person was detected" in payload.body
        assert payload.channel_id == "argusai_events"
        assert payload.tag == "cam-456"
        assert payload.data["event_id"] == "evt-123"
        assert payload.data["camera_id"] == "cam-456"

    def test_event_with_entity_names(self):
        """Test event with recognized entities."""
        payload = format_event_for_fcm(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="John arrived",
            entity_names=["John"],
        )

        assert "John at Front Door" in payload.title
        assert payload.data["entity_names"] == "John"

    def test_event_with_multiple_entities(self):
        """Test event with multiple entities."""
        payload = format_event_for_fcm(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="John and Jane arrived",
            entity_names=["John", "Jane"],
        )

        assert "John and Jane" in payload.title
        assert payload.data["entity_names"] == "John,Jane"

    def test_event_with_three_entities(self):
        """Test event with three or more entities."""
        payload = format_event_for_fcm(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="Group arrived",
            entity_names=["John", "Jane", "Bob"],
        )

        assert "John and 2 others" in payload.title

    def test_event_high_anomaly(self):
        """Test event with high anomaly score."""
        payload = format_event_for_fcm(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="Unusual activity detected",
            smart_detection_type="person",
            anomaly_score=0.75,
        )

        assert "Unusual" in payload.title
        assert payload.data["anomaly_score"] == "0.75"
        assert payload.data["is_unusual"] == "true"

    def test_event_low_anomaly(self):
        """Test event with low anomaly score."""
        payload = format_event_for_fcm(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="Normal activity",
            anomaly_score=0.3,
        )

        assert "Unusual" not in payload.title
        assert payload.data["is_unusual"] == "false"

    def test_event_with_thumbnail(self):
        """Test event with thumbnail URL."""
        payload = format_event_for_fcm(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="Person detected",
            thumbnail_url="https://example.com/thumb.jpg",
        )

        assert payload.image_url == "https://example.com/thumb.jpg"

    def test_long_description_truncated(self):
        """Test long descriptions are truncated."""
        long_description = "A" * 150  # More than 100 chars
        payload = format_event_for_fcm(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description=long_description,
        )

        assert len(payload.body) == 100
        assert payload.body.endswith("...")

    def test_detection_type_labels(self):
        """Test various detection types."""
        detection_types = {
            "person": "Person Detected",
            "vehicle": "Vehicle Detected",
            "package": "Package Detected",
            "animal": "Animal Detected",
            "ring": "Doorbell Ring",
            "motion": "Motion Detected",
        }

        for detection_type, expected_label in detection_types.items():
            payload = format_event_for_fcm(
                event_id="evt-123",
                camera_id="cam-456",
                camera_name="Front Door",
                description="Detection",
                smart_detection_type=detection_type,
            )

            assert expected_label in payload.title

    def test_data_payload_values_are_strings(self):
        """Test all data payload values are strings (FCM requirement)."""
        payload = format_event_for_fcm(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="Test",
            smart_detection_type="person",
            entity_names=["John"],
            is_vip=True,
            anomaly_score=0.8,
        )

        # All values in data must be strings
        for key, value in payload.data.items():
            assert isinstance(value, str), f"Data key '{key}' has non-string value: {type(value)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
