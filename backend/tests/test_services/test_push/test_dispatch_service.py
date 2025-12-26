"""
Tests for PushDispatchService.

Story P11-2.3: Unified push dispatch service tests.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.push.dispatch_service import (
    DeviceInfo,
    DispatchResult,
    NotificationPayload,
    PushDispatchService,
)
from app.services.push.models import DeliveryResult, DeliveryStatus


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return MagicMock()


@pytest.fixture
def mock_apns_provider():
    """Create mock APNS provider."""
    provider = AsyncMock()
    provider.send = AsyncMock(return_value=DeliveryResult(
        device_token="ios-token-123",
        success=True,
        status=DeliveryStatus.SUCCESS,
        apns_id="apns-msg-123",
    ))
    provider.close = AsyncMock()
    return provider


@pytest.fixture
def mock_fcm_provider():
    """Create mock FCM provider."""
    provider = AsyncMock()
    provider.send = AsyncMock(return_value=DeliveryResult(
        device_token="fcm-token-456",
        success=True,
        status=DeliveryStatus.SUCCESS,
        apns_id="fcm-msg-456",
    ))
    provider.close = AsyncMock()
    return provider


@pytest.fixture
def sample_notification():
    """Create sample notification payload."""
    return NotificationPayload(
        title="Front Door: Person Detected",
        body="A person was detected at the front door",
        data={
            "event_id": "evt-123",
            "camera_id": "cam-456",
            "camera_name": "Front Door",
        },
        image_url="https://example.com/thumbnail.jpg",
        tag="cam-456",
        priority="high",
    )


@pytest.fixture
def ios_device():
    """Create sample iOS device."""
    return DeviceInfo(
        device_id="device-ios-1",
        user_id="user-123",
        platform="ios",
        push_token="ios-token-abc123",
        name="iPhone 15 Pro",
    )


@pytest.fixture
def android_device():
    """Create sample Android device."""
    return DeviceInfo(
        device_id="device-android-1",
        user_id="user-123",
        platform="android",
        push_token="fcm-token-def456",
        name="Pixel 8",
    )


# =============================================================================
# NotificationPayload Tests
# =============================================================================


class TestNotificationPayload:
    """Tests for NotificationPayload dataclass."""

    def test_create_basic_payload(self):
        """Test creating basic notification payload."""
        payload = NotificationPayload(
            title="Test Title",
            body="Test Body",
        )
        assert payload.title == "Test Title"
        assert payload.body == "Test Body"
        assert payload.data == {}
        assert payload.image_url is None
        assert payload.tag is None
        assert payload.priority == "high"

    def test_create_full_payload(self):
        """Test creating full notification payload."""
        payload = NotificationPayload(
            title="Alert",
            body="Motion detected",
            data={"event_id": "123", "camera": "front"},
            image_url="https://example.com/img.jpg",
            tag="camera-1",
            priority="normal",
        )
        assert payload.title == "Alert"
        assert payload.data == {"event_id": "123", "camera": "front"}
        assert payload.image_url == "https://example.com/img.jpg"
        assert payload.tag == "camera-1"
        assert payload.priority == "normal"


# =============================================================================
# DispatchResult Tests
# =============================================================================


class TestDispatchResult:
    """Tests for DispatchResult dataclass."""

    def test_create_empty_result(self):
        """Test creating empty dispatch result."""
        result = DispatchResult(user_id="user-123")
        assert result.user_id == "user-123"
        assert result.total_devices == 0
        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.skipped_count == 0
        assert result.results == []
        assert result.duration_ms == 0.0
        assert not result.all_succeeded
        assert not result.any_succeeded

    def test_all_succeeded_property(self):
        """Test all_succeeded property."""
        # No failures, has successes
        result = DispatchResult(
            user_id="user-123",
            total_devices=3,
            success_count=3,
            failure_count=0,
        )
        assert result.all_succeeded is True

        # Has failures
        result2 = DispatchResult(
            user_id="user-123",
            total_devices=3,
            success_count=2,
            failure_count=1,
        )
        assert result2.all_succeeded is False

        # No successes
        result3 = DispatchResult(
            user_id="user-123",
            total_devices=0,
            success_count=0,
            failure_count=0,
        )
        assert result3.all_succeeded is False

    def test_any_succeeded_property(self):
        """Test any_succeeded property."""
        # Has successes
        result = DispatchResult(
            user_id="user-123",
            success_count=1,
            failure_count=2,
        )
        assert result.any_succeeded is True

        # No successes
        result2 = DispatchResult(
            user_id="user-123",
            success_count=0,
            failure_count=2,
        )
        assert result2.any_succeeded is False


# =============================================================================
# PushDispatchService Initialization Tests
# =============================================================================


class TestPushDispatchServiceInit:
    """Tests for PushDispatchService initialization."""

    def test_init_with_no_providers(self, mock_db):
        """Test initialization with no providers."""
        service = PushDispatchService(db=mock_db)
        assert service._apns is None
        assert service._fcm is None
        assert service._on_token_invalid is None

    def test_init_with_apns_only(self, mock_db, mock_apns_provider):
        """Test initialization with APNS only."""
        service = PushDispatchService(
            db=mock_db,
            apns_provider=mock_apns_provider,
        )
        assert service._apns is mock_apns_provider
        assert service._fcm is None

    def test_init_with_fcm_only(self, mock_db, mock_fcm_provider):
        """Test initialization with FCM only."""
        service = PushDispatchService(
            db=mock_db,
            fcm_provider=mock_fcm_provider,
        )
        assert service._apns is None
        assert service._fcm is mock_fcm_provider

    def test_init_with_all_providers(
        self, mock_db, mock_apns_provider, mock_fcm_provider
    ):
        """Test initialization with all providers."""
        callback = MagicMock()
        service = PushDispatchService(
            db=mock_db,
            apns_provider=mock_apns_provider,
            fcm_provider=mock_fcm_provider,
            on_token_invalid=callback,
        )
        assert service._apns is mock_apns_provider
        assert service._fcm is mock_fcm_provider
        assert service._on_token_invalid is callback


# =============================================================================
# Payload Conversion Tests
# =============================================================================


class TestPayloadConversion:
    """Tests for payload conversion methods."""

    def test_to_apns_payload(self, mock_db, sample_notification):
        """Test conversion to APNS payload."""
        service = PushDispatchService(db=mock_db)
        apns_payload = service._to_apns_payload(sample_notification)

        assert apns_payload.alert.title == sample_notification.title
        assert apns_payload.alert.body == sample_notification.body
        assert apns_payload.thread_id == sample_notification.tag
        assert "event_id" in apns_payload.custom_data
        assert apns_payload.mutable_content is True

    def test_to_fcm_payload(self, mock_db, sample_notification):
        """Test conversion to FCM payload."""
        service = PushDispatchService(db=mock_db)
        fcm_payload = service._to_fcm_payload(sample_notification)

        assert fcm_payload.title == sample_notification.title
        assert fcm_payload.body == sample_notification.body
        assert fcm_payload.image_url == sample_notification.image_url
        assert fcm_payload.tag == sample_notification.tag
        assert fcm_payload.priority == sample_notification.priority
        # FCM data values should be strings
        assert fcm_payload.data["event_id"] == "evt-123"

    def test_to_fcm_payload_converts_values_to_strings(self, mock_db):
        """Test that FCM payload converts all data values to strings."""
        notification = NotificationPayload(
            title="Test",
            body="Test",
            data={
                "number": 123,
                "boolean": True,
                "float": 3.14,
                "string": "hello",
            },
        )
        service = PushDispatchService(db=mock_db)
        fcm_payload = service._to_fcm_payload(notification)

        assert fcm_payload.data["number"] == "123"
        assert fcm_payload.data["boolean"] == "True"
        assert fcm_payload.data["float"] == "3.14"
        assert fcm_payload.data["string"] == "hello"


# =============================================================================
# Dispatch to Device Tests
# =============================================================================


class TestDispatchToDevice:
    """Tests for dispatching to individual devices."""

    @pytest.mark.asyncio
    async def test_dispatch_to_ios_device(
        self, mock_db, mock_apns_provider, ios_device, sample_notification
    ):
        """Test dispatching to iOS device."""
        service = PushDispatchService(
            db=mock_db,
            apns_provider=mock_apns_provider,
        )

        result = await service._dispatch_to_device(ios_device, sample_notification)

        assert result.success is True
        assert result.status == DeliveryStatus.SUCCESS
        mock_apns_provider.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_to_android_device(
        self, mock_db, mock_fcm_provider, android_device, sample_notification
    ):
        """Test dispatching to Android device."""
        service = PushDispatchService(
            db=mock_db,
            fcm_provider=mock_fcm_provider,
        )

        result = await service._dispatch_to_device(android_device, sample_notification)

        assert result.success is True
        assert result.status == DeliveryStatus.SUCCESS
        mock_fcm_provider.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_to_ios_without_apns_provider(
        self, mock_db, ios_device, sample_notification
    ):
        """Test dispatching to iOS when APNS not configured."""
        service = PushDispatchService(db=mock_db)  # No APNS provider

        result = await service._dispatch_to_device(ios_device, sample_notification)

        assert result.success is False
        assert result.status == DeliveryStatus.FAILED
        assert "APNS provider not configured" in result.error

    @pytest.mark.asyncio
    async def test_dispatch_to_android_without_fcm_provider(
        self, mock_db, android_device, sample_notification
    ):
        """Test dispatching to Android when FCM not configured."""
        service = PushDispatchService(db=mock_db)  # No FCM provider

        result = await service._dispatch_to_device(android_device, sample_notification)

        assert result.success is False
        assert result.status == DeliveryStatus.FAILED
        assert "FCM provider not configured" in result.error

    @pytest.mark.asyncio
    async def test_dispatch_to_unknown_platform(
        self, mock_db, sample_notification
    ):
        """Test dispatching to unknown platform."""
        service = PushDispatchService(db=mock_db)
        unknown_device = DeviceInfo(
            device_id="device-1",
            user_id="user-123",
            platform="blackberry",  # Unknown platform
            push_token="token-123",
        )

        result = await service._dispatch_to_device(unknown_device, sample_notification)

        assert result.success is False
        assert result.status == DeliveryStatus.FAILED
        assert "Unknown platform" in result.error

    @pytest.mark.asyncio
    async def test_token_invalidation_callback_called(
        self, mock_db, mock_apns_provider, ios_device, sample_notification
    ):
        """Test that token invalidation callback is called on invalid token."""
        callback = MagicMock()

        # Mock APNS to return invalid token
        mock_apns_provider.send.return_value = DeliveryResult(
            device_token=ios_device.push_token,
            success=False,
            status=DeliveryStatus.INVALID_TOKEN,
            error="Token not registered",
        )

        service = PushDispatchService(
            db=mock_db,
            apns_provider=mock_apns_provider,
            on_token_invalid=callback,
        )

        await service._dispatch_to_device(ios_device, sample_notification)

        callback.assert_called_once_with(ios_device.device_id, ios_device.platform)

    @pytest.mark.asyncio
    async def test_exception_in_dispatch_handled(
        self, mock_db, mock_apns_provider, ios_device, sample_notification
    ):
        """Test that exceptions during dispatch are handled gracefully."""
        mock_apns_provider.send.side_effect = Exception("Network error")

        service = PushDispatchService(
            db=mock_db,
            apns_provider=mock_apns_provider,
        )

        result = await service._dispatch_to_device(ios_device, sample_notification)

        assert result.success is False
        assert result.status == DeliveryStatus.FAILED
        assert "Network error" in result.error


# =============================================================================
# Main Dispatch Tests
# =============================================================================


class TestDispatch:
    """Tests for main dispatch method."""

    @pytest.mark.asyncio
    async def test_dispatch_with_no_devices(self, mock_db, sample_notification):
        """Test dispatch when user has no devices."""
        service = PushDispatchService(db=mock_db)

        # Mock web push to return empty
        with patch.object(
            service, "_dispatch_to_web", new_callable=AsyncMock
        ) as mock_web:
            mock_web.return_value = []

            result = await service.dispatch(
                user_id="user-123",
                notification=sample_notification,
            )

        assert result.user_id == "user-123"
        assert result.total_devices == 0
        assert result.success_count == 0
        assert result.failure_count == 0

    @pytest.mark.asyncio
    async def test_dispatch_includes_web_push(self, mock_db, sample_notification):
        """Test that dispatch includes web push subscriptions."""
        service = PushDispatchService(db=mock_db)

        # Mock web push to return results
        web_result = DeliveryResult(
            device_token="subscription-123",
            success=True,
            status=DeliveryStatus.SUCCESS,
        )
        with patch.object(
            service, "_dispatch_to_web", new_callable=AsyncMock
        ) as mock_web:
            mock_web.return_value = [web_result]

            result = await service.dispatch(
                user_id="user-123",
                notification=sample_notification,
            )

        assert result.total_devices == 1
        assert result.success_count == 1
        mock_web.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_duration_tracked(self, mock_db, sample_notification):
        """Test that dispatch duration is tracked."""
        service = PushDispatchService(db=mock_db)

        with patch.object(
            service, "_dispatch_to_web", new_callable=AsyncMock
        ) as mock_web:
            mock_web.return_value = []

            result = await service.dispatch(
                user_id="user-123",
                notification=sample_notification,
            )

        assert result.duration_ms >= 0


# =============================================================================
# Dispatch Event Tests
# =============================================================================


class TestDispatchEvent:
    """Tests for dispatch_event convenience method."""

    @pytest.mark.asyncio
    async def test_dispatch_event_builds_correct_notification(self, mock_db):
        """Test dispatch_event creates correct notification payload."""
        service = PushDispatchService(db=mock_db)

        with patch.object(
            service, "dispatch", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = DispatchResult(user_id="user-123")

            await service.dispatch_event(
                user_id="user-123",
                event_id="evt-456",
                camera_id="cam-789",
                camera_name="Front Door",
                description="A person was seen",
                smart_detection_type="person",
                thumbnail_url="https://example.com/thumb.jpg",
            )

            # Check the notification passed to dispatch
            call_args = mock_dispatch.call_args
            notification = call_args.kwargs["notification"]

            assert notification.title == "Front Door: Person Detected"
            assert notification.body == "A person was seen"
            assert notification.data["event_id"] == "evt-456"
            assert notification.data["camera_id"] == "cam-789"
            assert notification.image_url == "https://example.com/thumb.jpg"
            assert notification.tag == "cam-789"

    @pytest.mark.asyncio
    async def test_dispatch_event_truncates_long_description(self, mock_db):
        """Test that long descriptions are truncated."""
        service = PushDispatchService(db=mock_db)
        long_description = "A" * 150  # 150 characters

        with patch.object(
            service, "dispatch", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = DispatchResult(user_id="user-123")

            await service.dispatch_event(
                user_id="user-123",
                event_id="evt-456",
                camera_id="cam-789",
                camera_name="Front Door",
                description=long_description,
            )

            notification = mock_dispatch.call_args.kwargs["notification"]
            assert len(notification.body) == 100
            assert notification.body.endswith("...")

    @pytest.mark.asyncio
    async def test_dispatch_event_detection_type_labels(self, mock_db):
        """Test detection type labels are applied correctly."""
        service = PushDispatchService(db=mock_db)

        test_cases = [
            ("person", "Front Door: Person Detected"),
            ("vehicle", "Front Door: Vehicle Detected"),
            ("package", "Front Door: Package Detected"),
            ("animal", "Front Door: Animal Detected"),
            ("ring", "Front Door: Doorbell Ring"),
            ("motion", "Front Door: Motion Detected"),
            ("unknown", "Front Door: Motion Detected"),
            (None, "Front Door: Motion Detected"),
        ]

        for detection_type, expected_title in test_cases:
            with patch.object(
                service, "dispatch", new_callable=AsyncMock
            ) as mock_dispatch:
                mock_dispatch.return_value = DispatchResult(user_id="user-123")

                await service.dispatch_event(
                    user_id="user-123",
                    event_id="evt-456",
                    camera_id="cam-789",
                    camera_name="Front Door",
                    description="Event",
                    smart_detection_type=detection_type,
                )

                notification = mock_dispatch.call_args.kwargs["notification"]
                assert notification.title == expected_title, (
                    f"Expected '{expected_title}' for detection_type='{detection_type}'"
                )


# =============================================================================
# Close and Context Manager Tests
# =============================================================================


class TestCloseAndContextManager:
    """Tests for close and context manager."""

    @pytest.mark.asyncio
    async def test_close_closes_providers(
        self, mock_db, mock_apns_provider, mock_fcm_provider
    ):
        """Test that close() closes all providers."""
        service = PushDispatchService(
            db=mock_db,
            apns_provider=mock_apns_provider,
            fcm_provider=mock_fcm_provider,
        )

        await service.close()

        mock_apns_provider.close.assert_called_once()
        mock_fcm_provider.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_handles_no_providers(self, mock_db):
        """Test that close() works with no providers."""
        service = PushDispatchService(db=mock_db)
        await service.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_context_manager(
        self, mock_db, mock_apns_provider, mock_fcm_provider
    ):
        """Test context manager properly closes resources."""
        async with PushDispatchService(
            db=mock_db,
            apns_provider=mock_apns_provider,
            fcm_provider=mock_fcm_provider,
        ) as service:
            assert service._apns is mock_apns_provider

        # After context, providers should be closed
        mock_apns_provider.close.assert_called_once()
        mock_fcm_provider.close.assert_called_once()


# =============================================================================
# Parallel Dispatch Tests
# =============================================================================


class TestParallelDispatch:
    """Tests for parallel dispatch behavior."""

    @pytest.mark.asyncio
    async def test_dispatch_to_multiple_devices_parallel(
        self, mock_db, mock_apns_provider, mock_fcm_provider, sample_notification
    ):
        """Test that multiple devices are dispatched in parallel."""
        service = PushDispatchService(
            db=mock_db,
            apns_provider=mock_apns_provider,
            fcm_provider=mock_fcm_provider,
        )

        devices = [
            DeviceInfo("d1", "user-1", "ios", "token-1"),
            DeviceInfo("d2", "user-1", "android", "token-2"),
            DeviceInfo("d3", "user-1", "ios", "token-3"),
        ]

        # Mock _get_user_devices to return test devices
        with patch.object(service, "_get_user_devices", return_value=devices):
            with patch.object(
                service, "_dispatch_to_web", new_callable=AsyncMock
            ) as mock_web:
                mock_web.return_value = []

                result = await service.dispatch(
                    user_id="user-1",
                    notification=sample_notification,
                )

        # All devices should be attempted
        assert mock_apns_provider.send.call_count == 2  # 2 iOS devices
        assert mock_fcm_provider.send.call_count == 1  # 1 Android device

    @pytest.mark.asyncio
    async def test_one_failure_doesnt_block_others(
        self, mock_db, mock_apns_provider, mock_fcm_provider, sample_notification
    ):
        """Test that one device failure doesn't affect others."""
        # First call fails, second succeeds
        mock_apns_provider.send.side_effect = [
            DeliveryResult(
                device_token="token-1",
                success=False,
                status=DeliveryStatus.FAILED,
                error="Network error",
            ),
            DeliveryResult(
                device_token="token-3",
                success=True,
                status=DeliveryStatus.SUCCESS,
            ),
        ]

        service = PushDispatchService(
            db=mock_db,
            apns_provider=mock_apns_provider,
            fcm_provider=mock_fcm_provider,
        )

        devices = [
            DeviceInfo("d1", "user-1", "ios", "token-1"),
            DeviceInfo("d2", "user-1", "android", "token-2"),
            DeviceInfo("d3", "user-1", "ios", "token-3"),
        ]

        with patch.object(service, "_get_user_devices", return_value=devices):
            with patch.object(
                service, "_dispatch_to_web", new_callable=AsyncMock
            ) as mock_web:
                mock_web.return_value = []

                result = await service.dispatch(
                    user_id="user-1",
                    notification=sample_notification,
                )

        # Should have attempted all devices
        assert result.total_devices == 3
        assert result.success_count == 2  # FCM + second APNS
        assert result.failure_count == 1  # First APNS


# =============================================================================
# Integration with Web Push Tests
# =============================================================================


class TestWebPushIntegration:
    """Tests for integration with web push service."""

    @pytest.mark.asyncio
    async def test_dispatch_to_web_calls_push_service(
        self, mock_db, sample_notification
    ):
        """Test that _dispatch_to_web uses PushNotificationService."""
        service = PushDispatchService(db=mock_db)

        with patch(
            "app.services.push_notification_service.PushNotificationService"
        ) as MockPushService:
            mock_service_instance = MagicMock()
            mock_service_instance.broadcast_event_notification = AsyncMock(
                return_value=[]
            )
            MockPushService.return_value = mock_service_instance

            await service._dispatch_to_web(
                notification=sample_notification,
                camera_id="cam-123",
                smart_detection_type="person",
            )

            mock_service_instance.broadcast_event_notification.assert_called_once()
            call_kwargs = mock_service_instance.broadcast_event_notification.call_args.kwargs
            assert call_kwargs["title"] == sample_notification.title
            assert call_kwargs["body"] == sample_notification.body
            assert call_kwargs["camera_id"] == "cam-123"
            assert call_kwargs["smart_detection_type"] == "person"

    @pytest.mark.asyncio
    async def test_dispatch_to_web_handles_exceptions(
        self, mock_db, sample_notification
    ):
        """Test that web push exceptions are handled gracefully."""
        service = PushDispatchService(db=mock_db)

        with patch(
            "app.services.push_notification_service.PushNotificationService"
        ) as MockPushService:
            MockPushService.side_effect = Exception("Web push error")

            results = await service._dispatch_to_web(
                notification=sample_notification,
            )

            assert results == []  # Should return empty list on error
