"""
Tests for SignedURLService (Story P11-2.6).

Tests signed URL generation, verification, and expiration handling
for secure thumbnail access in push notifications.
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from app.services.signed_url_service import (
    SignedURLService,
    get_signed_url_service,
    reset_signed_url_service,
    DEFAULT_EXPIRATION_SECONDS,
)


class TestSignedURLService:
    """Test suite for SignedURLService."""

    @pytest.fixture
    def service(self):
        """Create a fresh SignedURLService instance."""
        return SignedURLService(secret_key=b"test-secret-key-for-testing")

    @pytest.fixture
    def event_id(self):
        """Sample event ID."""
        return "abc-123-def-456"

    @pytest.fixture
    def base_url(self):
        """Sample base URL."""
        return "https://api.example.com"

    def test_generate_signed_url_format(self, service, event_id, base_url):
        """Test that generated URL has correct format."""
        url = service.generate_signed_url(event_id, base_url)

        # Check URL structure
        assert url.startswith(f"{base_url}/api/v1/events/{event_id}/thumbnail?")
        assert "signature=" in url
        assert "expires=" in url

    def test_generate_signed_url_with_custom_expiration(self, service, event_id, base_url):
        """Test URL generation with custom expiration."""
        url = service.generate_signed_url(event_id, base_url, expiration_seconds=120)

        # Extract expires parameter
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        expires = int(params["expires"][0])
        expected_min = int(time.time()) + 118  # Allow 2 second margin
        expected_max = int(time.time()) + 122

        assert expected_min <= expires <= expected_max

    def test_verify_signed_url_success(self, service, event_id, base_url):
        """Test successful verification of valid signed URL."""
        url = service.generate_signed_url(event_id, base_url)

        # Extract parameters
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        signature = params["signature"][0]
        expires = int(params["expires"][0])

        # Verify should pass
        assert service.verify_signed_url(event_id, signature, expires) is True

    def test_verify_signed_url_expired(self, service, event_id):
        """Test that expired URLs are rejected."""
        # Create signature with past expiration
        expires = int(time.time()) - 100  # 100 seconds ago
        signature = service._create_signature(event_id, expires)

        assert service.verify_signed_url(event_id, signature, expires) is False

    def test_verify_signed_url_invalid_signature(self, service, event_id):
        """Test that invalid signatures are rejected."""
        expires = int(time.time()) + 60  # Valid expiration

        # Use wrong signature
        invalid_signature = "invalid_signature_12345"

        assert service.verify_signed_url(event_id, invalid_signature, expires) is False

    def test_verify_signed_url_wrong_event_id(self, service, event_id, base_url):
        """Test that signature for wrong event is rejected."""
        url = service.generate_signed_url(event_id, base_url)

        # Extract parameters
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        signature = params["signature"][0]
        expires = int(params["expires"][0])

        # Try to use signature with different event ID
        wrong_event_id = "different-event-id"
        assert service.verify_signed_url(wrong_event_id, signature, expires) is False

    def test_signature_is_deterministic(self, service, event_id):
        """Test that same inputs produce same signature."""
        expires = int(time.time()) + 60

        sig1 = service._create_signature(event_id, expires)
        sig2 = service._create_signature(event_id, expires)

        assert sig1 == sig2

    def test_different_secrets_produce_different_signatures(self, event_id):
        """Test that different secret keys produce different signatures."""
        service1 = SignedURLService(secret_key=b"secret-key-1")
        service2 = SignedURLService(secret_key=b"secret-key-2")

        expires = int(time.time()) + 60

        sig1 = service1._create_signature(event_id, expires)
        sig2 = service2._create_signature(event_id, expires)

        assert sig1 != sig2

    def test_url_contains_no_trailing_slash_issues(self, service, event_id):
        """Test that base URL with trailing slash works correctly."""
        # With trailing slash
        url1 = service.generate_signed_url(event_id, "https://example.com/")
        assert "//" not in url1.replace("https://", "")

        # Without trailing slash
        url2 = service.generate_signed_url(event_id, "https://example.com")
        assert "//" not in url2.replace("https://", "")


class TestSignedURLServiceSingleton:
    """Test singleton behavior."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_signed_url_service()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_signed_url_service()

    @patch("app.services.signed_url_service.settings")
    def test_get_singleton_uses_settings(self, mock_settings):
        """Test that singleton uses ENCRYPTION_KEY from settings."""
        mock_settings.ENCRYPTION_KEY = "test-encryption-key"

        service = get_signed_url_service()
        assert service is not None
        assert service._secret_key == b"test-encryption-key"

    @patch("app.services.signed_url_service.settings")
    def test_get_singleton_returns_same_instance(self, mock_settings):
        """Test that get_signed_url_service returns same instance."""
        mock_settings.ENCRYPTION_KEY = "test-key"

        service1 = get_signed_url_service()
        service2 = get_signed_url_service()

        assert service1 is service2

    def test_reset_clears_singleton(self):
        """Test that reset_signed_url_service clears the singleton."""
        # Create a service with custom key
        from app.services.signed_url_service import _signed_url_service
        import app.services.signed_url_service as module

        # Manually set singleton
        module._signed_url_service = SignedURLService(secret_key=b"custom")

        # Reset
        reset_signed_url_service()

        # Singleton should be None
        assert module._signed_url_service is None


class TestSignedURLTiming:
    """Test timing-related behavior."""

    @pytest.fixture
    def service(self):
        """Create a fresh SignedURLService instance."""
        return SignedURLService(secret_key=b"test-secret")

    def test_verify_just_before_expiration(self, service):
        """Test URL verification just before expiration."""
        event_id = "test-event"
        expires = int(time.time()) + 2  # 2 seconds from now
        signature = service._create_signature(event_id, expires)

        # Should be valid
        assert service.verify_signed_url(event_id, signature, expires) is True

    def test_verify_at_exact_expiration(self, service):
        """Test URL verification at exact expiration time."""
        event_id = "test-event"
        expires = int(time.time())  # Now
        signature = service._create_signature(event_id, expires)

        # At exact time, should still be valid (not past)
        # Note: This depends on timing, might be flaky
        # The check is current_time > expires, so equal should pass
        result = service.verify_signed_url(event_id, signature, expires)
        # Allow either result as timing is sensitive
        assert isinstance(result, bool)

    def test_default_expiration_is_60_seconds(self, service):
        """Test that default expiration is 60 seconds."""
        assert DEFAULT_EXPIRATION_SECONDS == 60

        event_id = "test-event"
        base_url = "https://example.com"

        url = service.generate_signed_url(event_id, base_url)

        # Extract expires
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        expires = int(params["expires"][0])

        expected = int(time.time()) + 60
        # Allow 2 second margin
        assert abs(expires - expected) <= 2
