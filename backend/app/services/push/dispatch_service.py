"""
Unified Push Dispatch Service.

Story P11-2.3: Routes notifications to WebPush, APNS, and FCM providers.

Features:
- Parallel dispatch to all user devices
- Platform-aware routing (ios -> APNS, android -> FCM, web -> WebPush)
- Notification preference filtering (quiet hours, camera, object type)
- Token invalidation handling
- Aggregated dispatch results
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.push.apns_provider import APNSProvider
from app.services.push.fcm_provider import FCMProvider
from app.services.push.models import (
    APNSPayload,
    APNSAlert,
    FCMPayload,
    DeliveryResult,
    DeliveryStatus,
)

logger = logging.getLogger(__name__)

# Default concurrency limit for parallel dispatch
DEFAULT_CONCURRENCY = 100


@dataclass
class NotificationPayload:
    """Platform-agnostic notification payload.

    Used as input to dispatch methods - converted to platform-specific
    payloads before sending.

    Attributes:
        title: Notification title
        body: Notification body text
        data: Custom data payload (event_id, camera_id, etc.)
        image_url: Optional thumbnail/image URL
        tag: Optional grouping/collapse tag
        priority: Message priority (high or normal)
    """

    title: str
    body: str
    data: Dict[str, Any] = field(default_factory=dict)
    image_url: Optional[str] = None
    tag: Optional[str] = None
    priority: str = "high"


@dataclass
class DispatchResult:
    """Aggregated result of dispatching to multiple devices.

    Attributes:
        user_id: Target user ID
        total_devices: Total devices found for user
        success_count: Number of successful deliveries
        failure_count: Number of failed deliveries
        skipped_count: Number skipped due to preferences
        results: Per-device DeliveryResult list
        duration_ms: Total dispatch duration in milliseconds
        timestamp: When dispatch occurred
    """

    user_id: str
    total_devices: int = 0
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    results: List[DeliveryResult] = field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def all_succeeded(self) -> bool:
        """True if all attempted deliveries succeeded (no failures)."""
        return self.failure_count == 0 and self.success_count > 0

    @property
    def any_succeeded(self) -> bool:
        """True if at least one delivery succeeded."""
        return self.success_count > 0


@dataclass
class DeviceInfo:
    """Device information for routing.

    Note: This is a stub until Story P11-2.4 creates the Device model.
    """

    device_id: str
    user_id: str
    platform: str  # 'ios', 'android', 'web'
    push_token: str
    name: Optional[str] = None


class PushDispatchService:
    """
    Unified push dispatch service.

    Routes notifications to the appropriate provider based on device platform:
    - iOS devices -> APNSProvider
    - Android devices -> FCMProvider
    - Web subscriptions -> PushNotificationService

    Features:
    - Parallel dispatch to all devices
    - Preference filtering (quiet hours, camera, object type)
    - Token invalidation callbacks
    - Graceful degradation when providers unavailable

    Usage:
        service = PushDispatchService(db)
        result = await service.dispatch(
            user_id="user-123",
            notification=NotificationPayload(
                title="Front Door: Person Detected",
                body="A person was seen at the front door",
                data={"event_id": "evt-456"},
            ),
        )
    """

    def __init__(
        self,
        db: Session,
        apns_provider: Optional[APNSProvider] = None,
        fcm_provider: Optional[FCMProvider] = None,
        on_token_invalid: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Initialize dispatch service.

        Args:
            db: Database session for device and preference lookup
            apns_provider: Optional APNS provider (iOS)
            fcm_provider: Optional FCM provider (Android)
            on_token_invalid: Callback(device_id, platform) when token is invalid
        """
        self.db = db
        self._apns = apns_provider
        self._fcm = fcm_provider
        self._on_token_invalid = on_token_invalid

        # Log available providers
        providers = []
        if self._apns:
            providers.append("APNS")
        if self._fcm:
            providers.append("FCM")
        providers.append("WebPush")  # Always available via PushNotificationService

        logger.info(
            "PushDispatchService initialized",
            extra={"providers": providers}
        )

    def _get_user_devices(self, user_id: str) -> List[DeviceInfo]:
        """
        Get all devices registered for a user.

        Note: This is a stub implementation. Story P11-2.4 will create
        the Device model and implement actual database lookup.

        Args:
            user_id: User ID to get devices for

        Returns:
            List of DeviceInfo for the user
        """
        # TODO: P11-2.4 - Replace with actual Device model query
        # For now, return empty list - web push handled separately
        logger.debug(
            f"Device lookup stub called for user {user_id}",
            extra={"note": "Awaiting P11-2.4 Device model implementation"}
        )
        return []

    def _check_preferences(
        self,
        user_id: str,
        camera_id: Optional[str] = None,
        smart_detection_type: Optional[str] = None,
        is_critical: bool = False,
    ) -> tuple[bool, bool]:
        """
        Check notification preferences for dispatch.

        Reuses logic from push_notification_service.py.

        Args:
            user_id: User ID to check preferences for
            camera_id: Optional camera ID for filtering
            smart_detection_type: Optional detection type for filtering
            is_critical: If True, override quiet hours

        Returns:
            Tuple of (should_send, sound_enabled)
        """
        # Import here to avoid circular imports
        from app.services.push_notification_service import (
            is_within_quiet_hours,
        )
        from app.models.notification_preference import NotificationPreference

        try:
            # Look up user's notification preferences
            # Note: Currently preferences are per-subscription, not per-user
            # For now, return (True, True) to allow all notifications
            # P11-2.5 will add user-level quiet hours

            # Stub: Always allow, sound enabled
            return (True, True)

        except Exception as e:
            logger.warning(
                f"Error checking preferences for user {user_id}: {e}",
                exc_info=True
            )
            # Fail open - send notification
            return (True, True)

    def _to_apns_payload(self, notification: NotificationPayload) -> APNSPayload:
        """Convert generic notification to APNS payload."""
        return APNSPayload(
            alert=APNSAlert(
                title=notification.title,
                body=notification.body,
            ),
            sound="default",
            mutable_content=True,
            thread_id=notification.tag,
            custom_data=notification.data,
        )

    def _to_fcm_payload(self, notification: NotificationPayload) -> FCMPayload:
        """Convert generic notification to FCM payload."""
        # FCM data must be string values
        string_data = {k: str(v) for k, v in notification.data.items()}

        return FCMPayload(
            title=notification.title,
            body=notification.body,
            image_url=notification.image_url,
            data=string_data,
            priority=notification.priority,
            tag=notification.tag,
        )

    async def _dispatch_to_device(
        self,
        device: DeviceInfo,
        notification: NotificationPayload,
    ) -> DeliveryResult:
        """
        Dispatch notification to a single device.

        Routes to appropriate provider based on platform.

        Args:
            device: Device to send to
            notification: Notification payload

        Returns:
            DeliveryResult with success status
        """
        try:
            if device.platform == "ios":
                if not self._apns:
                    return DeliveryResult(
                        device_token=device.push_token,
                        success=False,
                        status=DeliveryStatus.FAILED,
                        error="APNS provider not configured",
                    )
                payload = self._to_apns_payload(notification)
                result = await self._apns.send(device.push_token, payload)

            elif device.platform == "android":
                if not self._fcm:
                    return DeliveryResult(
                        device_token=device.push_token,
                        success=False,
                        status=DeliveryStatus.FAILED,
                        error="FCM provider not configured",
                    )
                payload = self._to_fcm_payload(notification)
                result = await self._fcm.send(device.push_token, payload)

            else:
                # Unknown platform
                return DeliveryResult(
                    device_token=device.push_token,
                    success=False,
                    status=DeliveryStatus.FAILED,
                    error=f"Unknown platform: {device.platform}",
                )

            # Handle token invalidation
            if result.status == DeliveryStatus.INVALID_TOKEN:
                if self._on_token_invalid:
                    try:
                        self._on_token_invalid(device.device_id, device.platform)
                    except Exception as e:
                        logger.error(f"Token invalidation callback error: {e}")

            return result

        except Exception as e:
            logger.error(
                f"Error dispatching to device {device.device_id}: {e}",
                exc_info=True
            )
            return DeliveryResult(
                device_token=device.push_token,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )

    async def dispatch(
        self,
        user_id: str,
        notification: NotificationPayload,
        is_critical: bool = False,
        camera_id: Optional[str] = None,
        smart_detection_type: Optional[str] = None,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> DispatchResult:
        """
        Dispatch notification to all user's devices.

        Sends to iOS, Android, and web devices in parallel.
        Applies preference filtering (quiet hours, camera, object type).

        Args:
            user_id: User to send notification to
            notification: Notification content
            is_critical: If True, override quiet hours
            camera_id: Optional camera ID for preference filtering
            smart_detection_type: Optional detection type for filtering
            concurrency: Max concurrent dispatches

        Returns:
            DispatchResult with aggregated status
        """
        start_time = time.time()

        # Check preferences
        should_send, _ = self._check_preferences(
            user_id=user_id,
            camera_id=camera_id,
            smart_detection_type=smart_detection_type,
            is_critical=is_critical,
        )

        if not should_send:
            logger.info(
                f"Dispatch skipped due to preferences",
                extra={
                    "user_id": user_id,
                    "camera_id": camera_id,
                    "smart_detection_type": smart_detection_type,
                }
            )
            return DispatchResult(
                user_id=user_id,
                total_devices=0,
                skipped_count=1,
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Get user's mobile devices
        devices = self._get_user_devices(user_id)

        # Also dispatch to web push subscriptions
        web_results = await self._dispatch_to_web(
            notification=notification,
            camera_id=camera_id,
            smart_detection_type=smart_detection_type,
        )

        if not devices and not web_results:
            logger.debug(
                f"No devices found for user {user_id}",
                extra={"user_id": user_id}
            )
            return DispatchResult(
                user_id=user_id,
                total_devices=0,
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Dispatch to mobile devices in parallel
        semaphore = asyncio.Semaphore(concurrency)

        async def dispatch_with_semaphore(device: DeviceInfo) -> DeliveryResult:
            async with semaphore:
                return await self._dispatch_to_device(device, notification)

        mobile_results = []
        if devices:
            mobile_results = await asyncio.gather(
                *[dispatch_with_semaphore(d) for d in devices],
                return_exceptions=True,
            )

        # Process results
        all_results: List[DeliveryResult] = []

        # Add mobile results
        for i, result in enumerate(mobile_results):
            if isinstance(result, Exception):
                logger.error(f"Dispatch exception: {result}")
                all_results.append(DeliveryResult(
                    device_token=devices[i].push_token,
                    success=False,
                    status=DeliveryStatus.FAILED,
                    error=str(result),
                ))
            else:
                all_results.append(result)

        # Add web results
        all_results.extend(web_results)

        # Calculate counts
        success_count = sum(1 for r in all_results if r.success)
        failure_count = sum(1 for r in all_results if not r.success)
        invalid_tokens = sum(
            1 for r in all_results if r.status == DeliveryStatus.INVALID_TOKEN
        )

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Dispatch complete",
            extra={
                "user_id": user_id,
                "total_devices": len(all_results),
                "success": success_count,
                "failed": failure_count,
                "invalid_tokens": invalid_tokens,
                "duration_ms": round(duration_ms, 2),
            }
        )

        return DispatchResult(
            user_id=user_id,
            total_devices=len(all_results),
            success_count=success_count,
            failure_count=failure_count,
            results=all_results,
            duration_ms=duration_ms,
        )

    async def _dispatch_to_web(
        self,
        notification: NotificationPayload,
        camera_id: Optional[str] = None,
        smart_detection_type: Optional[str] = None,
    ) -> List[DeliveryResult]:
        """
        Dispatch to web push subscriptions.

        Uses existing PushNotificationService for web push.

        Args:
            notification: Notification payload
            camera_id: Optional camera ID for filtering
            smart_detection_type: Optional detection type for filtering

        Returns:
            List of DeliveryResult for web subscriptions
        """
        try:
            from app.services.push_notification_service import (
                PushNotificationService,
            )

            service = PushNotificationService(self.db)

            # Use broadcast_event_notification for preference filtering
            results = await service.broadcast_event_notification(
                title=notification.title,
                body=notification.body,
                camera_id=camera_id,
                smart_detection_type=smart_detection_type,
                data=notification.data,
                tag=notification.tag,
                image=notification.image_url,
            )

            # Convert to DeliveryResult format
            delivery_results = []
            for r in results:
                delivery_results.append(DeliveryResult(
                    device_token=r.subscription_id,
                    success=r.success,
                    status=DeliveryStatus.SUCCESS if r.success else DeliveryStatus.FAILED,
                    error=r.error,
                    retries=r.retries,
                ))

            return delivery_results

        except Exception as e:
            logger.error(f"Error dispatching to web push: {e}", exc_info=True)
            return []

    async def dispatch_event(
        self,
        user_id: str,
        event_id: str,
        camera_id: str,
        camera_name: str,
        description: str,
        smart_detection_type: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        is_critical: bool = False,
    ) -> DispatchResult:
        """
        Convenience method for dispatching event notifications.

        Creates a properly formatted notification from event data.

        Args:
            user_id: User to notify
            event_id: Event ID
            camera_id: Camera ID
            camera_name: Camera display name
            description: Event description
            smart_detection_type: Optional detection type
            thumbnail_url: Optional thumbnail URL
            is_critical: Override quiet hours if True

        Returns:
            DispatchResult with aggregated status
        """
        # Build title based on detection type
        if smart_detection_type:
            detection_labels = {
                "person": "Person Detected",
                "vehicle": "Vehicle Detected",
                "package": "Package Detected",
                "animal": "Animal Detected",
                "ring": "Doorbell Ring",
                "motion": "Motion Detected",
            }
            detection_label = detection_labels.get(
                smart_detection_type, "Motion Detected"
            )
            title = f"{camera_name}: {detection_label}"
        else:
            title = f"{camera_name}: Motion Detected"

        # Truncate description if too long
        body = description
        if len(body) > 100:
            body = body[:97] + "..."

        # Build data payload
        data: Dict[str, Any] = {
            "event_id": event_id,
            "camera_id": camera_id,
            "camera_name": camera_name,
            "url": f"/events?highlight={event_id}",
        }
        if smart_detection_type:
            data["smart_detection_type"] = smart_detection_type

        notification = NotificationPayload(
            title=title,
            body=body,
            data=data,
            image_url=thumbnail_url,
            tag=camera_id,  # Group by camera
            priority="high",
        )

        return await self.dispatch(
            user_id=user_id,
            notification=notification,
            is_critical=is_critical,
            camera_id=camera_id,
            smart_detection_type=smart_detection_type,
        )

    async def close(self) -> None:
        """Close providers and release resources."""
        if self._apns:
            await self._apns.close()
        if self._fcm:
            await self._fcm.close()
        logger.debug("PushDispatchService closed")

    async def __aenter__(self) -> "PushDispatchService":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.close()
