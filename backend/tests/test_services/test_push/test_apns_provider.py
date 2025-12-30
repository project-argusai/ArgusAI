"""
Tests for APNS Provider.

Story P11-2.1: Unit tests for iOS push notifications via APNS.
"""

import asyncio
import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

from app.services.push.apns_provider import APNSProvider
from app.services.push.models import (
    APNSConfig,
    APNSPayload,
    APNSAlert,
    DeliveryResult,
    DeliveryStatus,
    format_event_for_apns,
)
from app.services.push.constants import (
    APNS_PRODUCTION_HOST,
    APNS_SANDBOX_HOST,
    JWT_ALGORITHM,
)


# Test fixtures
@pytest.fixture
def test_key_file(tmp_path):
    """Create a temporary .p8 key file for testing."""
    # Generate a test EC private key
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    key_file = tmp_path / "AuthKey_TEST.p8"
    key_file.write_bytes(pem)
    return str(key_file)


@pytest.fixture
def apns_config(test_key_file):
    """Create a test APNS configuration."""
    return APNSConfig(
        key_file=test_key_file,
        key_id="KEYID12345",
        team_id="TEAMID1234",
        bundle_id="com.argusai.test",
        use_sandbox=True,
    )


@pytest.fixture
def sample_payload():
    """Create a sample APNS payload."""
    return APNSPayload(
        alert=APNSAlert(
            title="Front Door: Person Detected",
            body="A person was detected at the front door",
            subtitle="Front Door Camera",
        ),
        badge=1,
        sound="default",
        mutable_content=True,
        category="SECURITY_ALERT",
        thread_id="camera-123",
        custom_data={
            "event_id": "evt-123",
            "camera_id": "cam-456",
        },
    )


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx AsyncClient."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    return mock_client


# =============================================================================
# APNSConfig Tests
# =============================================================================

class TestAPNSConfig:
    """Tests for APNSConfig model."""

    def test_valid_config(self, test_key_file):
        """Test valid configuration creation."""
        config = APNSConfig(
            key_file=test_key_file,
            key_id="ABCDE12345",
            team_id="TEAM123456",
            bundle_id="com.example.app",
            use_sandbox=False,
        )
        assert config.key_id == "ABCDE12345"
        assert config.team_id == "TEAM123456"
        assert config.bundle_id == "com.example.app"
        assert config.use_sandbox is False

    def test_key_id_validation_length(self, test_key_file):
        """Test key_id must be exactly 10 characters."""
        with pytest.raises(ValueError):
            APNSConfig(
                key_file=test_key_file,
                key_id="SHORT",  # Too short
                team_id="TEAM123456",
                bundle_id="com.example.app",
            )

    def test_team_id_validation_length(self, test_key_file):
        """Test team_id must be exactly 10 characters."""
        with pytest.raises(ValueError):
            APNSConfig(
                key_file=test_key_file,
                key_id="KEYID12345",
                team_id="SHORT",  # Too short
                bundle_id="com.example.app",
            )

    def test_identifiers_converted_to_uppercase(self, test_key_file):
        """Test identifiers are converted to uppercase."""
        config = APNSConfig(
            key_file=test_key_file,
            key_id="abcde12345",
            team_id="team123456",
            bundle_id="com.example.app",
        )
        assert config.key_id == "ABCDE12345"
        assert config.team_id == "TEAM123456"


# =============================================================================
# APNSPayload Tests
# =============================================================================

class TestAPNSPayload:
    """Tests for APNSPayload model."""

    def test_payload_to_apns_dict(self, sample_payload):
        """Test conversion to APNS dictionary format."""
        result = sample_payload.to_apns_dict()

        assert "aps" in result
        aps = result["aps"]

        # Check alert structure
        assert aps["alert"]["title"] == "Front Door: Person Detected"
        assert aps["alert"]["body"] == "A person was detected at the front door"
        assert aps["alert"]["subtitle"] == "Front Door Camera"

        # Check aps fields
        assert aps["badge"] == 1
        assert aps["sound"] == "default"
        assert aps["mutable-content"] == 1
        assert aps["category"] == "SECURITY_ALERT"
        assert aps["thread-id"] == "camera-123"

        # Check custom data at root level
        assert result["event_id"] == "evt-123"
        assert result["camera_id"] == "cam-456"

    def test_payload_minimal(self):
        """Test minimal payload with only required fields."""
        payload = APNSPayload(
            alert=APNSAlert(
                title="Test",
                body="Test body",
            ),
        )
        result = payload.to_apns_dict()

        assert result["aps"]["alert"]["title"] == "Test"
        assert result["aps"]["alert"]["body"] == "Test body"
        assert result["aps"]["sound"] == "default"
        assert result["aps"]["mutable-content"] == 1

    def test_background_notification(self):
        """Test content-available flag for background notifications."""
        payload = APNSPayload(
            alert=APNSAlert(title="Background", body="Update"),
            content_available=True,
        )
        result = payload.to_apns_dict()

        assert result["aps"]["content-available"] == 1

    @pytest.mark.parametrize("level", ["passive", "active", "time-sensitive", "critical"])
    def test_interruption_level_validation_valid(self, level):
        """Test valid interruption level values."""
        payload = APNSPayload(
            alert=APNSAlert(title="Test", body="Body"),
            interruption_level=level,
        )
        assert payload.interruption_level == level

    def test_interruption_level_validation_invalid(self):
        """Test invalid interruption level raises error."""
        with pytest.raises(ValueError):
            APNSPayload(
                alert=APNSAlert(title="Test", body="Body"),
                interruption_level="invalid",
            )


# =============================================================================
# APNSProvider Tests
# =============================================================================

class TestAPNSProvider:
    """Tests for APNSProvider class."""

    def test_provider_initialization(self, apns_config):
        """Test provider initializes correctly."""
        provider = APNSProvider(apns_config)

        assert provider.config == apns_config
        assert provider._host == APNS_SANDBOX_HOST  # sandbox=True in config
        assert provider._client is None  # Lazy initialized

    def test_provider_uses_production_host(self, test_key_file):
        """Test provider uses production host when sandbox=False."""
        config = APNSConfig(
            key_file=test_key_file,
            key_id="KEYID12345",
            team_id="TEAMID1234",
            bundle_id="com.argusai.app",
            use_sandbox=False,
        )
        provider = APNSProvider(config)

        assert provider._host == APNS_PRODUCTION_HOST

    @pytest.mark.asyncio
    async def test_jwt_generation(self, apns_config):
        """Test JWT is generated correctly."""
        provider = APNSProvider(apns_config)

        token = provider._generate_jwt()

        # Decode token (without verification since we don't have the public key)
        decoded = jwt.decode(token, options={"verify_signature": False})

        assert decoded["iss"] == apns_config.team_id
        assert "iat" in decoded

        # Check headers
        headers = jwt.get_unverified_header(token)
        assert headers["alg"] == JWT_ALGORITHM
        assert headers["kid"] == apns_config.key_id

    @pytest.mark.asyncio
    async def test_jwt_caching(self, apns_config):
        """Test JWT is cached and reused within validity period."""
        provider = APNSProvider(apns_config)

        token1 = provider._generate_jwt()
        token2 = provider._generate_jwt()

        # Should return the same cached token
        assert token1 == token2

    @pytest.mark.asyncio
    async def test_send_success(self, apns_config, sample_payload, mock_httpx_client):
        """Test successful notification send."""
        provider = APNSProvider(apns_config)

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"apns-id": "test-apns-id-123"}
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        with patch.object(provider, '_get_client', return_value=mock_httpx_client):
            result = await provider.send("device-token-123", sample_payload)

        assert result.success is True
        assert result.status == DeliveryStatus.SUCCESS
        assert result.status_code == 200
        assert result.apns_id == "test-apns-id-123"

    @pytest.mark.asyncio
    async def test_send_invalid_token_410(self, apns_config, sample_payload, mock_httpx_client):
        """Test handling of 410 response (token unregistered)."""
        provider = APNSProvider(apns_config)
        invalidated_tokens = []

        def on_token_invalid(token):
            invalidated_tokens.append(token)

        provider._on_token_invalid = on_token_invalid

        # Mock 410 response
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_response.content = b'{"reason": "Unregistered"}'
        mock_response.json.return_value = {"reason": "Unregistered"}
        mock_response.headers = {}
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        with patch.object(provider, '_get_client', return_value=mock_httpx_client):
            result = await provider.send("invalid-device-token", sample_payload)

        assert result.success is False
        assert result.status == DeliveryStatus.INVALID_TOKEN
        assert result.status_code == 410
        assert result.error_reason == "Unregistered"
        assert "invalid-device-token" in invalidated_tokens

    @pytest.mark.asyncio
    async def test_send_auth_error_403(self, apns_config, sample_payload, mock_httpx_client):
        """Test handling of 403 response (auth error)."""
        provider = APNSProvider(apns_config)

        # Set a JWT to verify it gets cleared
        provider._jwt_token = "old-jwt-token"
        provider._jwt_expires_at = 9999999999

        # Mock 403 response
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.content = b'{"reason": "InvalidProviderToken"}'
        mock_response.json.return_value = {"reason": "InvalidProviderToken"}
        mock_response.headers = {}
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        with patch.object(provider, '_get_client', return_value=mock_httpx_client):
            result = await provider.send("device-token", sample_payload)

        assert result.success is False
        assert result.status == DeliveryStatus.AUTH_ERROR
        assert result.status_code == 403

        # JWT should be invalidated
        assert provider._jwt_token is None
        assert provider._jwt_expires_at == 0

    @pytest.mark.asyncio
    async def test_send_rate_limited_429(self, apns_config, sample_payload, mock_httpx_client):
        """Test handling of 429 response (rate limited)."""
        provider = APNSProvider(apns_config)

        # Mock 429 response (always returns 429 to exhaust retries)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.content = b'{"reason": "TooManyRequests"}'
        mock_response.json.return_value = {"reason": "TooManyRequests"}
        mock_response.headers = {}
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        with patch.object(provider, '_get_client', return_value=mock_httpx_client):
            with patch('asyncio.sleep', new_callable=AsyncMock):  # Skip delays
                result = await provider.send("device-token", sample_payload)

        assert result.success is False
        assert result.status == DeliveryStatus.RATE_LIMITED
        assert result.status_code == 429
        assert result.retries > 0  # Should have retried

    @pytest.mark.asyncio
    async def test_send_server_error_with_retry(self, apns_config, sample_payload, mock_httpx_client):
        """Test retry logic for server errors."""
        provider = APNSProvider(apns_config)

        # First call returns 500, second returns 200
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.content = b'{"reason": "InternalServerError"}'
        error_response.json.return_value = {"reason": "InternalServerError"}
        error_response.headers = {}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {"apns-id": "retry-success-id"}

        mock_httpx_client.post = AsyncMock(side_effect=[error_response, success_response])

        with patch.object(provider, '_get_client', return_value=mock_httpx_client):
            with patch('asyncio.sleep', new_callable=AsyncMock):  # Skip delays
                result = await provider.send("device-token", sample_payload)

        assert result.success is True
        assert result.status == DeliveryStatus.SUCCESS
        assert result.retries == 1  # One retry

    @pytest.mark.asyncio
    async def test_send_batch(self, apns_config, sample_payload, mock_httpx_client):
        """Test batch send to multiple devices."""
        provider = APNSProvider(apns_config)

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"apns-id": "batch-id"}
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        tokens = ["token1", "token2", "token3"]

        with patch.object(provider, '_get_client', return_value=mock_httpx_client):
            results = await provider.send_batch(tokens, sample_payload)

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_send_batch_mixed_results(self, apns_config, sample_payload, mock_httpx_client):
        """Test batch send with mixed success/failure."""
        provider = APNSProvider(apns_config)

        # First token succeeds, second fails (410), third succeeds
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {"apns-id": "success-id"}

        invalid_response = MagicMock()
        invalid_response.status_code = 410
        invalid_response.content = b'{"reason": "Unregistered"}'
        invalid_response.json.return_value = {"reason": "Unregistered"}
        invalid_response.headers = {}

        mock_httpx_client.post = AsyncMock(
            side_effect=[success_response, invalid_response, success_response]
        )

        tokens = ["token1", "token2", "token3"]

        with patch.object(provider, '_get_client', return_value=mock_httpx_client):
            results = await provider.send_batch(tokens, sample_payload)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[1].status == DeliveryStatus.INVALID_TOKEN
        assert results[2].success is True

    @pytest.mark.asyncio
    async def test_context_manager(self, apns_config):
        """Test provider as async context manager."""
        async with APNSProvider(apns_config) as provider:
            assert provider is not None
            # Use the provider
            assert provider.config == apns_config

        # Client should be closed after exiting context
        # (we can't easily verify this without accessing internals)

    @pytest.mark.asyncio
    async def test_close(self, apns_config, mock_httpx_client):
        """Test explicit close."""
        provider = APNSProvider(apns_config)

        # Set mock client
        provider._client = mock_httpx_client
        mock_httpx_client.aclose = AsyncMock()

        # Close
        await provider.close()
        assert provider._client is None
        mock_httpx_client.aclose.assert_called_once()


# =============================================================================
# format_event_for_apns Tests
# =============================================================================

class TestFormatEventForApns:
    """Tests for format_event_for_apns helper."""

    def test_basic_event(self):
        """Test basic event formatting."""
        payload = format_event_for_apns(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="A person was detected at the front door at 10:30 AM",
            smart_detection_type="person",
        )

        assert payload.alert.title == "Front Door: Person Detected"
        assert "A person was detected" in payload.alert.body
        assert payload.alert.subtitle == "Front Door"
        assert payload.category == "SECURITY_ALERT"
        assert payload.thread_id == "cam-456"

    def test_event_with_entity_names(self):
        """Test event with recognized entities."""
        payload = format_event_for_apns(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="John arrived",
            entity_names=["John"],
        )

        assert "John at Front Door" in payload.alert.title

    def test_event_with_multiple_entities(self):
        """Test event with multiple entities."""
        payload = format_event_for_apns(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="John and Jane arrived",
            entity_names=["John", "Jane"],
        )

        assert "John and Jane" in payload.alert.title

    def test_event_high_anomaly(self):
        """Test event with high anomaly score."""
        payload = format_event_for_apns(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="Unusual activity detected",
            smart_detection_type="person",
            anomaly_score=0.75,
        )

        assert "Unusual" in payload.alert.title

    def test_event_with_thumbnail(self):
        """Test event with thumbnail URL."""
        payload = format_event_for_apns(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description="Person detected",
            thumbnail_url="https://example.com/thumb.jpg",
        )

        assert payload.custom_data["thumbnail_url"] == "https://example.com/thumb.jpg"

    def test_long_description_truncated(self):
        """Test long descriptions are truncated."""
        long_description = "A" * 150  # More than 100 chars
        payload = format_event_for_apns(
            event_id="evt-123",
            camera_id="cam-456",
            camera_name="Front Door",
            description=long_description,
        )

        assert len(payload.alert.body) == 100
        assert payload.alert.body.endswith("...")


# =============================================================================
# Integration-like Tests (Still Unit Tests)
# =============================================================================

class TestAPNSProviderHeaders:
    """Tests for APNS request headers."""

    def test_build_headers_alert(self, apns_config, sample_payload):
        """Test headers for alert notification."""
        provider = APNSProvider(apns_config)
        headers = provider._build_headers(sample_payload)

        assert "authorization" in headers
        assert headers["authorization"].startswith("bearer ")
        assert headers["apns-topic"] == apns_config.bundle_id
        assert headers["apns-push-type"] == "alert"
        assert headers["apns-priority"] == "10"
        assert headers["apns-expiration"] == "0"

    def test_build_headers_background(self, apns_config):
        """Test headers for background notification."""
        provider = APNSProvider(apns_config)
        payload = APNSPayload(
            alert=APNSAlert(title="Background", body="Update"),
            content_available=True,
        )
        headers = provider._build_headers(payload)

        assert headers["apns-push-type"] == "background"
        assert headers["apns-priority"] == "5"  # Lower priority for background


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
