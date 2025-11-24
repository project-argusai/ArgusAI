"""
Tests for Webhook Service (Story 5.3)

Tests cover:
- URL validation and SSRF prevention
- Rate limiting
- Payload building
- Webhook delivery with retry logic
- Error handling
"""
import asyncio
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.services.webhook_service import (
    WebhookService,
    WebhookResult,
    WebhookValidationError,
    WebhookRateLimitError,
    RATE_LIMIT_PER_MINUTE,
)
from app.models.alert_rule import AlertRule, WebhookLog
from app.models.event import Event


class TestURLValidation:
    """Tests for webhook URL validation."""

    def test_valid_https_url(self):
        """Valid HTTPS URLs should pass validation."""
        db = MagicMock()
        service = WebhookService(db)

        # Should not raise
        with patch.object(service, '_resolve_hostname', return_value='8.8.8.8'):
            service.validate_url("https://example.com/webhook")

    def test_http_url_blocked_by_default(self):
        """HTTP URLs should be blocked by default."""
        db = MagicMock()
        service = WebhookService(db, allow_http=False)

        with pytest.raises(WebhookValidationError, match="HTTPS is required"):
            service.validate_url("http://example.com/webhook")

    def test_http_url_allowed_when_configured(self):
        """HTTP URLs should be allowed when allow_http=True."""
        db = MagicMock()
        service = WebhookService(db, allow_http=True)

        with patch.object(service, '_resolve_hostname', return_value='8.8.8.8'):
            service.validate_url("http://example.com/webhook")

    def test_localhost_blocked(self):
        """Localhost should be blocked."""
        db = MagicMock()
        service = WebhookService(db, allow_http=True)

        with pytest.raises(WebhookValidationError, match="Blocked hostname"):
            service.validate_url("http://localhost/webhook")

        with pytest.raises(WebhookValidationError, match="Blocked hostname"):
            service.validate_url("http://127.0.0.1/webhook")

    def test_private_ip_blocked(self):
        """Private IP addresses should be blocked."""
        db = MagicMock()
        service = WebhookService(db, allow_http=True)

        # Mock DNS resolution to return private IP
        with patch.object(service, '_resolve_hostname', return_value='192.168.1.1'):
            with pytest.raises(WebhookValidationError, match="private IP"):
                service.validate_url("http://internal.example.com/webhook")

    def test_invalid_scheme_blocked(self):
        """Non-http/https schemes should be blocked."""
        db = MagicMock()
        service = WebhookService(db)

        with pytest.raises(WebhookValidationError, match="http or https"):
            service.validate_url("ftp://example.com/file")

    def test_missing_hostname(self):
        """URLs without hostname should be blocked."""
        db = MagicMock()
        service = WebhookService(db, allow_http=True)

        with pytest.raises(WebhookValidationError, match="hostname"):
            service.validate_url("http:///webhook")


class TestPrivateIPDetection:
    """Tests for private IP detection."""

    def test_detect_10_network(self):
        """10.x.x.x should be detected as private."""
        db = MagicMock()
        service = WebhookService(db)

        assert service._is_private_ip("10.0.0.1") is True
        assert service._is_private_ip("10.255.255.255") is True

    def test_detect_172_16_network(self):
        """172.16-31.x.x should be detected as private."""
        db = MagicMock()
        service = WebhookService(db)

        assert service._is_private_ip("172.16.0.1") is True
        assert service._is_private_ip("172.31.255.255") is True
        assert service._is_private_ip("172.32.0.1") is False

    def test_detect_192_168_network(self):
        """192.168.x.x should be detected as private."""
        db = MagicMock()
        service = WebhookService(db)

        assert service._is_private_ip("192.168.0.1") is True
        assert service._is_private_ip("192.168.255.255") is True

    def test_detect_loopback(self):
        """127.x.x.x should be detected as private."""
        db = MagicMock()
        service = WebhookService(db)

        assert service._is_private_ip("127.0.0.1") is True
        assert service._is_private_ip("127.255.255.255") is True

    def test_public_ip_not_private(self):
        """Public IPs should not be detected as private."""
        db = MagicMock()
        service = WebhookService(db)

        assert service._is_private_ip("8.8.8.8") is False
        assert service._is_private_ip("1.1.1.1") is False


class TestRateLimiting:
    """Tests for webhook rate limiting."""

    def test_rate_limit_not_exceeded(self):
        """Should allow requests under rate limit."""
        db = MagicMock()
        service = WebhookService(db)

        # Should not raise for first request
        service.check_rate_limit("rule-123")

    def test_rate_limit_exceeded(self):
        """Should block requests over rate limit."""
        db = MagicMock()
        service = WebhookService(db)

        # Fill up rate limit
        for _ in range(RATE_LIMIT_PER_MINUTE):
            service.check_rate_limit("rule-123")

        # Next request should fail
        with pytest.raises(WebhookRateLimitError):
            service.check_rate_limit("rule-123")

    def test_rate_limit_per_rule(self):
        """Rate limits should be per-rule."""
        db = MagicMock()
        service = WebhookService(db)

        # Fill up rate limit for rule-123
        for _ in range(RATE_LIMIT_PER_MINUTE):
            service.check_rate_limit("rule-123")

        # Different rule should still work
        service.check_rate_limit("rule-456")


class TestPayloadBuilding:
    """Tests for webhook payload construction."""

    def test_build_payload_basic(self):
        """Should build payload with all required fields."""
        db = MagicMock()
        service = WebhookService(db)

        event = MagicMock(spec=Event)
        event.id = "event-123"
        event.timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        event.camera_id = "camera-456"
        event.description = "Person detected at door"
        event.confidence = 95
        event.objects_detected = json.dumps(["person"])

        rule = MagicMock(spec=AlertRule)
        rule.id = "rule-789"
        rule.name = "Door Monitor"

        payload = service.build_payload(event, rule)

        assert payload["event_id"] == "event-123"
        assert payload["camera"]["id"] == "camera-456"
        assert payload["description"] == "Person detected at door"
        assert payload["confidence"] == 95
        assert payload["objects_detected"] == ["person"]
        assert payload["rule"]["id"] == "rule-789"
        assert payload["rule"]["name"] == "Door Monitor"
        assert "/api/v1/events/event-123/thumbnail" in payload["thumbnail_url"]

    def test_build_payload_handles_json_string(self):
        """Should parse JSON string for objects_detected."""
        db = MagicMock()
        service = WebhookService(db)

        event = MagicMock(spec=Event)
        event.id = "event-123"
        event.timestamp = datetime.now(timezone.utc)
        event.camera_id = "camera-456"
        event.description = "Test"
        event.confidence = 90
        event.objects_detected = '["person", "vehicle"]'

        rule = MagicMock(spec=AlertRule)
        rule.id = "rule-789"
        rule.name = "Test Rule"

        payload = service.build_payload(event, rule)

        assert payload["objects_detected"] == ["person", "vehicle"]


@pytest.mark.asyncio
class TestWebhookDelivery:
    """Tests for webhook delivery with retry logic."""

    async def test_successful_delivery(self):
        """Successful webhook should return success result."""
        db = MagicMock()

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        service = WebhookService(db, http_client=mock_client, allow_http=True)

        result = await service.send_webhook(
            url="http://example.com/webhook",
            headers={},
            payload={"test": "data"},
            skip_validation=True
        )

        assert result.success is True
        assert result.status_code == 200
        assert result.retry_count == 0

    async def test_retry_on_failure(self):
        """Should retry on failure with backoff."""
        db = MagicMock()

        # First two calls fail, third succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        mock_response_fail.text = "Internal Server Error"

        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.text = "OK"

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = [
            mock_response_fail,
            mock_response_fail,
            mock_response_success
        ]

        service = WebhookService(db, http_client=mock_client, allow_http=True)

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await service.send_webhook(
                url="http://example.com/webhook",
                headers={},
                payload={"test": "data"},
                skip_validation=True
            )

        assert result.success is True
        assert result.retry_count == 2
        assert mock_client.post.call_count == 3

    async def test_all_retries_exhausted(self):
        """Should return failure after all retries exhausted."""
        db = MagicMock()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        service = WebhookService(db, http_client=mock_client, allow_http=True)

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await service.send_webhook(
                url="http://example.com/webhook",
                headers={},
                payload={"test": "data"},
                skip_validation=True
            )

        assert result.success is False
        assert result.status_code == 500
        assert result.retry_count == 2  # 3 attempts = retry_count of 2

    async def test_timeout_handling(self):
        """Should handle timeout exceptions."""
        db = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException("Request timeout")

        service = WebhookService(db, http_client=mock_client, allow_http=True)

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await service.send_webhook(
                url="http://example.com/webhook",
                headers={},
                payload={"test": "data"},
                skip_validation=True
            )

        assert result.success is False
        assert "timeout" in result.error_message.lower()


@pytest.mark.asyncio
class TestExecuteRuleWebhook:
    """Tests for execute_rule_webhook method."""

    async def test_no_webhook_configured(self):
        """Should return None if no webhook action configured."""
        db = MagicMock()
        service = WebhookService(db)

        event = MagicMock(spec=Event)
        rule = MagicMock(spec=AlertRule)
        rule.id = "rule-123"
        rule.actions = json.dumps({"dashboard_notification": True})

        result = await service.execute_rule_webhook(event, rule)

        assert result is None

    async def test_webhook_url_validation_failure(self):
        """Should handle URL validation failures gracefully."""
        db = MagicMock()
        service = WebhookService(db, allow_http=False)

        event = MagicMock(spec=Event)
        event.id = "event-123"
        event.timestamp = datetime.now(timezone.utc)
        event.camera_id = "camera-456"
        event.description = "Test"
        event.confidence = 90
        event.objects_detected = "[]"

        rule = MagicMock(spec=AlertRule)
        rule.id = "rule-123"
        rule.name = "Test Rule"
        rule.actions = json.dumps({
            "webhook": {
                "url": "http://example.com/webhook"  # HTTP not allowed
            }
        })

        result = await service.execute_rule_webhook(event, rule)

        assert result is not None
        assert result.success is False
        assert "HTTPS" in result.error_message


class TestWebhookLogging:
    """Tests for webhook attempt logging."""

    def test_log_attempt_creates_entry(self):
        """Should create WebhookLog entry."""
        db = MagicMock()
        service = WebhookService(db)

        service._log_attempt(
            rule_id="rule-123",
            event_id="event-456",
            url="https://example.com/webhook",
            status_code=200,
            response_time_ms=100,
            retry_count=0,
            success=True,
            error_message=None
        )

        # Check that add and commit were called
        db.add.assert_called_once()
        db.commit.assert_called_once()

        # Check the logged entry
        log_entry = db.add.call_args[0][0]
        assert isinstance(log_entry, WebhookLog)
        assert log_entry.alert_rule_id == "rule-123"
        assert log_entry.event_id == "event-456"
        assert log_entry.success is True

    def test_log_attempt_handles_error(self):
        """Should handle logging errors gracefully."""
        db = MagicMock()
        db.commit.side_effect = Exception("DB error")

        service = WebhookService(db)

        # Should not raise
        service._log_attempt(
            rule_id="rule-123",
            event_id="event-456",
            url="https://example.com/webhook",
            status_code=200,
            response_time_ms=100,
            retry_count=0,
            success=True,
            error_message=None
        )

        # Should rollback on error
        db.rollback.assert_called_once()
