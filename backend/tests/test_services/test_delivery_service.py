"""
Unit tests for DeliveryService (Story P4-4.3)

Tests cover:
- AC1: DeliveryService instantiation and method signatures
- AC2: Email delivery with mocked SMTP
- AC3: Push notification delivery reusing existing infrastructure
- AC4: In-app notification creation
- AC8: Email template content
- AC9: Push notification truncation and format
- AC10: Error handling - delivery failures don't crash
"""
import json
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from dataclasses import dataclass

from app.models.activity_summary import ActivitySummary
from app.models.system_notification import SystemNotification
from app.models.push_subscription import PushSubscription
from app.services.delivery_service import (
    DeliveryService,
    DeliveryResult,
    get_delivery_service,
    reset_delivery_service,
    MAX_SUMMARY_TRUNCATE_LENGTH,
)


# Test fixtures
@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.count.return_value = 0
    return db


@pytest.fixture
def sample_digest():
    """Create a sample ActivitySummary for testing."""
    return ActivitySummary(
        id=str(uuid.uuid4()),
        summary_text="Today's activity summary: 5 person detections at the front door between 9am and 5pm. 2 vehicle detections in the driveway. 1 package delivery at 2:30pm.",
        period_start=datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc),
        period_end=datetime(2024, 1, 15, 23, 59, 59, tzinfo=timezone.utc),
        event_count=8,
        generated_at=datetime.now(timezone.utc),
        digest_type='daily',
        ai_cost=0.0023,
        provider_used='openai',
        input_tokens=150,
        output_tokens=50,
    )


@pytest.fixture
def long_summary_digest(sample_digest):
    """Create a digest with summary text > 200 chars."""
    sample_digest.summary_text = "A" * 250  # 250 chars
    return sample_digest


class TestDeliveryResult:
    """Tests for DeliveryResult dataclass."""

    def test_creation(self):
        """Test DeliveryResult can be created."""
        result = DeliveryResult(
            success=True,
            channels_attempted=["email", "push"],
            channels_succeeded=["email", "push"],
            errors={},
            delivery_time_ms=150
        )
        assert result.success is True
        assert result.channels_attempted == ["email", "push"]
        assert result.channels_succeeded == ["email", "push"]
        assert result.errors == {}
        assert result.delivery_time_ms == 150

    def test_to_dict(self):
        """Test DeliveryResult serialization."""
        result = DeliveryResult(
            success=True,
            channels_attempted=["email"],
            channels_succeeded=["email"],
            errors={},
            delivery_time_ms=100
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["channels_attempted"] == ["email"]
        assert d["channels_succeeded"] == ["email"]
        assert d["errors"] == {}
        assert d["delivery_time_ms"] == 100

    def test_partial_failure(self):
        """Test DeliveryResult with partial failure."""
        result = DeliveryResult(
            success=True,  # True because at least one succeeded
            channels_attempted=["email", "push"],
            channels_succeeded=["push"],
            errors={"email": "SMTP connection failed"},
            delivery_time_ms=200
        )
        assert result.success is True
        assert len(result.channels_succeeded) == 1
        assert "email" in result.errors


class TestDeliveryServiceInit:
    """Tests for DeliveryService initialization (AC1)."""

    def test_init_with_db(self, mock_db):
        """Test DeliveryService initializes with provided db."""
        service = DeliveryService(mock_db)
        assert service._db == mock_db
        assert service._owns_db is False

    def test_init_without_db(self):
        """Test DeliveryService creates own db session if none provided."""
        with patch('app.core.database.SessionLocal') as mock_session:
            service = DeliveryService()
            # Session created lazily, so _db is still None initially
            assert service._db is None
            assert service._owns_db is True

    def test_get_delivery_service(self):
        """Test singleton getter."""
        reset_delivery_service()
        service1 = get_delivery_service()
        service2 = get_delivery_service()
        # Without db, returns singleton
        # With db, returns new instance
        reset_delivery_service()


class TestDeliverDigest:
    """Tests for deliver_digest method (AC1, AC10)."""

    @pytest.mark.asyncio
    async def test_no_channels_configured(self, mock_db, sample_digest):
        """Test deliver_digest with no channels returns appropriate result."""
        service = DeliveryService(mock_db)

        # Mock no channels configured
        with patch.object(service, '_get_delivery_channels', return_value=[]):
            result = await service.deliver_digest(sample_digest)

        assert result.success is False
        assert result.channels_attempted == []
        assert "general" in result.errors

    @pytest.mark.asyncio
    async def test_single_channel_success(self, mock_db, sample_digest):
        """Test deliver_digest with single successful channel."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_delivery_channels', return_value=["in_app"]):
            with patch.object(service, '_create_inapp_notification', new_callable=AsyncMock) as mock_inapp:
                result = await service.deliver_digest(sample_digest)

        assert result.success is True
        assert "in_app" in result.channels_succeeded
        mock_inapp.assert_called_once_with(sample_digest)

    @pytest.mark.asyncio
    async def test_multiple_channels_success(self, mock_db, sample_digest):
        """Test deliver_digest with multiple successful channels."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_delivery_channels', return_value=["email", "push", "in_app"]):
            with patch.object(service, '_send_email_digest', new_callable=AsyncMock):
                with patch.object(service, '_send_push_digest', new_callable=AsyncMock):
                    with patch.object(service, '_create_inapp_notification', new_callable=AsyncMock):
                        result = await service.deliver_digest(sample_digest)

        assert result.success is True
        assert len(result.channels_succeeded) == 3
        assert result.errors == {}

    @pytest.mark.asyncio
    async def test_partial_failure(self, mock_db, sample_digest):
        """Test deliver_digest continues after individual channel failure (AC10)."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_delivery_channels', return_value=["email", "push", "in_app"]):
            with patch.object(service, '_send_email_digest', new_callable=AsyncMock, side_effect=Exception("SMTP error")):
                with patch.object(service, '_send_push_digest', new_callable=AsyncMock):
                    with patch.object(service, '_create_inapp_notification', new_callable=AsyncMock):
                        result = await service.deliver_digest(sample_digest)

        # Should succeed because push and in_app worked
        assert result.success is True
        assert "email" in result.errors
        assert "push" in result.channels_succeeded
        assert "in_app" in result.channels_succeeded

    @pytest.mark.asyncio
    async def test_all_channels_fail(self, mock_db, sample_digest):
        """Test deliver_digest handles all channels failing."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_delivery_channels', return_value=["email", "push"]):
            with patch.object(service, '_send_email_digest', new_callable=AsyncMock, side_effect=Exception("SMTP error")):
                with patch.object(service, '_send_push_digest', new_callable=AsyncMock, side_effect=Exception("Push error")):
                    result = await service.deliver_digest(sample_digest)

        assert result.success is False
        assert len(result.errors) == 2

    @pytest.mark.asyncio
    async def test_explicit_channels_override(self, mock_db, sample_digest):
        """Test deliver_digest with explicit channels overrides settings."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_delivery_channels', return_value=["email", "push"]):
            with patch.object(service, '_create_inapp_notification', new_callable=AsyncMock):
                result = await service.deliver_digest(sample_digest, channels=["in_app"])

        assert "in_app" in result.channels_succeeded
        # Email and push should not be attempted
        assert "email" not in result.channels_attempted
        assert "push" not in result.channels_attempted


class TestEmailDelivery:
    """Tests for email delivery (AC2, AC8)."""

    @pytest.mark.asyncio
    async def test_no_recipients_raises(self, mock_db, sample_digest):
        """Test email delivery fails with no recipients."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_email_recipients', return_value=[]):
            with pytest.raises(ValueError, match="No email recipients"):
                await service._send_email_digest(sample_digest)

    @pytest.mark.asyncio
    async def test_no_smtp_host_raises(self, mock_db, sample_digest):
        """Test email delivery fails with no SMTP host."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_email_recipients', return_value=["test@example.com"]):
            with patch.object(service, '_get_smtp_config', return_value={
                "host": "",
                "port": 587,
                "username": "",
                "password_encrypted": "",
                "from_email": "",
                "use_tls": True
            }):
                with pytest.raises(ValueError, match="SMTP host not configured"):
                    await service._send_email_digest(sample_digest)

    @pytest.mark.asyncio
    async def test_email_sent_successfully(self, mock_db, sample_digest):
        """Test email is sent with correct parameters."""
        import aiosmtplib
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_email_recipients', return_value=["user@example.com"]):
            with patch.object(service, '_get_smtp_config', return_value={
                "host": "smtp.example.com",
                "port": 587,
                "username": "user",
                "password_encrypted": "encrypted:test",
                "from_email": "noreply@example.com",
                "use_tls": True
            }):
                with patch('app.services.delivery_service.decrypt_password', return_value="password"):
                    with patch.object(aiosmtplib, 'send', new_callable=AsyncMock) as mock_send:
                        await service._send_email_digest(sample_digest)

        mock_send.assert_called_once()

    def test_email_html_content(self, mock_db, sample_digest):
        """Test email HTML template includes required content (AC8)."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_setting', return_value="http://localhost:3000"):
            html = service._build_email_html(sample_digest, "January 15, 2024")

        # Check for required elements
        assert "January 15, 2024" in html
        assert sample_digest.summary_text in html
        assert str(sample_digest.event_count) in html
        assert "View Full Details" in html
        assert "ArgusAI" in html

    def test_email_text_content(self, mock_db, sample_digest):
        """Test email plain text template includes required content."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_setting', return_value="http://localhost:3000"):
            text = service._build_email_text(sample_digest, "January 15, 2024")

        assert "January 15, 2024" in text
        assert sample_digest.summary_text in text
        assert str(sample_digest.event_count) in text


class TestPushDelivery:
    """Tests for push notification delivery (AC3, AC9)."""

    @pytest.mark.asyncio
    async def test_no_subscriptions_returns_early(self, mock_db, sample_digest):
        """Test push delivery exits early with no subscriptions."""
        service = DeliveryService(mock_db)
        mock_db.query.return_value.count.return_value = 0

        # Should not raise, just return early
        await service._send_push_digest(sample_digest)

    @pytest.mark.asyncio
    async def test_push_uses_existing_service(self, mock_db, sample_digest):
        """Test push delivery uses existing PushNotificationService (AC3)."""
        service = DeliveryService(mock_db)
        mock_db.query.return_value.count.return_value = 1

        mock_push_service = MagicMock()
        mock_push_service.broadcast_notification = AsyncMock(return_value=[])

        with patch('app.services.delivery_service.get_push_notification_service', return_value=mock_push_service):
            await service._send_push_digest(sample_digest)

        mock_push_service.broadcast_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_truncates_long_summary(self, mock_db, long_summary_digest):
        """Test push notification truncates summary to 200 chars (AC9)."""
        service = DeliveryService(mock_db)
        mock_db.query.return_value.count.return_value = 1

        mock_push_service = MagicMock()
        mock_push_service.broadcast_notification = AsyncMock(return_value=[])

        with patch('app.services.delivery_service.get_push_notification_service', return_value=mock_push_service):
            await service._send_push_digest(long_summary_digest)

        # Check the body parameter was truncated
        call_kwargs = mock_push_service.broadcast_notification.call_args.kwargs
        body = call_kwargs['body']
        assert len(body) <= MAX_SUMMARY_TRUNCATE_LENGTH
        assert body.endswith("...")

    @pytest.mark.asyncio
    async def test_push_payload_format(self, mock_db, sample_digest):
        """Test push notification payload format (AC9)."""
        service = DeliveryService(mock_db)
        mock_db.query.return_value.count.return_value = 1

        mock_push_service = MagicMock()
        mock_push_service.broadcast_notification = AsyncMock(return_value=[])

        with patch('app.services.delivery_service.get_push_notification_service', return_value=mock_push_service):
            await service._send_push_digest(sample_digest)

        call_kwargs = mock_push_service.broadcast_notification.call_args.kwargs

        # Verify payload structure
        assert "Daily Summary" in call_kwargs['title']
        assert call_kwargs['data']['type'] == "digest"
        assert call_kwargs['data']['digest_id'] == sample_digest.id
        assert "/summaries?date=" in call_kwargs['data']['url']
        assert call_kwargs['tag'].startswith("digest-")


class TestInAppNotification:
    """Tests for in-app notification delivery (AC4)."""

    @pytest.mark.asyncio
    async def test_notification_created(self, mock_db, sample_digest):
        """Test in-app notification is created in database (AC4)."""
        service = DeliveryService(mock_db)

        await service._create_inapp_notification(sample_digest)

        # Verify db.add was called with SystemNotification
        mock_db.add.assert_called_once()
        notification = mock_db.add.call_args[0][0]
        assert isinstance(notification, SystemNotification)
        assert notification.notification_type == "digest"
        assert notification.severity == "info"
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_notification_content(self, mock_db, sample_digest):
        """Test in-app notification has correct content."""
        service = DeliveryService(mock_db)

        await service._create_inapp_notification(sample_digest)

        notification = mock_db.add.call_args[0][0]
        assert notification.title == "Daily Summary Available"
        assert notification.action_url is not None
        assert notification.extra_data is not None

    @pytest.mark.asyncio
    async def test_notification_truncates_message(self, mock_db, long_summary_digest):
        """Test notification message is truncated."""
        service = DeliveryService(mock_db)

        await service._create_inapp_notification(long_summary_digest)

        notification = mock_db.add.call_args[0][0]
        assert len(notification.message) <= 150


class TestSettingsHelpers:
    """Tests for settings helper methods (AC5, AC6)."""

    def test_get_delivery_channels_parses_json(self, mock_db):
        """Test delivery channels parsing from JSON setting (AC5)."""
        service = DeliveryService(mock_db)

        mock_setting = MagicMock()
        mock_setting.value = '["email", "push", "in_app"]'
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        channels = service._get_delivery_channels()
        assert channels == ["email", "push", "in_app"]

    def test_get_delivery_channels_filters_invalid(self, mock_db):
        """Test delivery channels filters invalid values."""
        service = DeliveryService(mock_db)

        mock_setting = MagicMock()
        mock_setting.value = '["email", "invalid_channel", "push"]'
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        channels = service._get_delivery_channels()
        assert "email" in channels
        assert "push" in channels
        assert "invalid_channel" not in channels

    def test_get_email_recipients_parses_csv(self, mock_db):
        """Test email recipients parsing from comma-separated string (AC6)."""
        service = DeliveryService(mock_db)

        mock_setting = MagicMock()
        mock_setting.value = "user1@example.com, user2@example.com,user3@example.com"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        recipients = service._get_email_recipients()
        assert len(recipients) == 3
        assert "user1@example.com" in recipients
        assert "user2@example.com" in recipients
        assert "user3@example.com" in recipients

    def test_get_email_recipients_handles_empty(self, mock_db):
        """Test email recipients returns empty list when not configured."""
        service = DeliveryService(mock_db)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        recipients = service._get_email_recipients()
        assert recipients == []


class TestErrorHandling:
    """Tests for error handling (AC10)."""

    @pytest.mark.asyncio
    async def test_channel_error_logged_not_propagated(self, mock_db, sample_digest):
        """Test channel errors are logged but don't crash delivery (AC10)."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_delivery_channels', return_value=["email"]):
            with patch.object(service, '_send_email_digest', new_callable=AsyncMock, side_effect=Exception("Test error")):
                # Should not raise
                result = await service.deliver_digest(sample_digest)

        assert result.success is False
        assert "email" in result.errors
        assert "Test error" in result.errors["email"]

    @pytest.mark.asyncio
    async def test_delivery_time_tracked(self, mock_db, sample_digest):
        """Test delivery time is tracked in result."""
        service = DeliveryService(mock_db)

        with patch.object(service, '_get_delivery_channels', return_value=["in_app"]):
            with patch.object(service, '_create_inapp_notification', new_callable=AsyncMock):
                result = await service.deliver_digest(sample_digest)

        assert result.delivery_time_ms >= 0
