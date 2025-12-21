"""
Push Notification Service for Web Push notifications (Story P4-1.1, P4-1.3, P4-1.4)

Handles sending push notifications to subscribed browsers with:
- VAPID authentication
- Retry logic with exponential backoff
- Automatic cleanup of invalid subscriptions
- Delivery tracking and metrics
- Rich notifications with thumbnails, actions, and deep links (P4-1.3)
- Preference filtering: camera, object type, quiet hours, sound (P4-1.4)
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from pywebpush import webpush, WebPushException
from py_vapid import Vapid
from sqlalchemy.orm import Session

from app.models.push_subscription import PushSubscription
from app.models.notification_preference import NotificationPreference
from app.utils.vapid import ensure_vapid_keys
from app.core.database import SessionLocal
from app.core.metrics import record_push_notification_sent, update_push_subscription_count

logger = logging.getLogger(__name__)

# Configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 2  # Exponential backoff: 2s, 4s, 8s
VAPID_CLAIMS_EMAIL = "mailto:admin@argusai.local"


# ============================================================================
# Preference Filtering Helpers (Story P4-1.4)
# ============================================================================


def is_within_quiet_hours(
    start: str,
    end: str,
    tz_name: str,
    now: Optional[datetime] = None
) -> bool:
    """
    Check if current time is within quiet hours (Story P4-1.4).

    Handles overnight quiet hours that span midnight (e.g., 22:00 - 06:00).

    Args:
        start: Start time in HH:MM format (e.g., "22:00")
        end: End time in HH:MM format (e.g., "06:00")
        tz_name: IANA timezone string (e.g., "America/New_York")
        now: Optional datetime for testing; defaults to current time

    Returns:
        True if current time is within quiet hours, False otherwise
    """
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)

        if now is None:
            now = datetime.now(tz)
        else:
            # Convert to target timezone
            now = now.astimezone(tz)

        current_time = now.time()
        start_time = datetime.strptime(start, "%H:%M").time()
        end_time = datetime.strptime(end, "%H:%M").time()

        # Handle overnight quiet hours (e.g., 22:00 - 06:00)
        if start_time > end_time:
            # Quiet hours span midnight
            return current_time >= start_time or current_time < end_time
        else:
            # Normal range (e.g., 09:00 - 17:00)
            return start_time <= current_time < end_time

    except Exception as e:
        logger.warning(f"Error checking quiet hours: {e}, defaulting to not-in-quiet-hours")
        return False


def should_send_notification(
    db: Session,
    subscription_id: str,
    camera_id: Optional[str] = None,
    smart_detection_type: Optional[str] = None,
) -> tuple[bool, Optional[bool]]:
    """
    Check if notification should be sent based on subscription preferences (Story P4-1.4).

    Args:
        db: Database session
        subscription_id: UUID of the push subscription
        camera_id: Optional camera UUID to check against enabled cameras
        smart_detection_type: Optional object type to check against enabled types

    Returns:
        Tuple of (should_send: bool, sound_enabled: Optional[bool])
        - should_send: True if notification should be sent
        - sound_enabled: True if sound is enabled, None if no preferences found
    """
    try:
        preference = db.query(NotificationPreference).filter(
            NotificationPreference.subscription_id == subscription_id
        ).first()

        if not preference:
            # No preferences = send all notifications with sound
            return (True, True)

        # Check camera filter
        if camera_id and not preference.is_camera_enabled(camera_id):
            logger.debug(
                f"Notification blocked: camera {camera_id} not enabled for subscription {subscription_id}"
            )
            return (False, None)

        # Check object type filter
        if smart_detection_type and not preference.is_object_type_enabled(smart_detection_type):
            logger.debug(
                f"Notification blocked: object type {smart_detection_type} not enabled for subscription {subscription_id}"
            )
            return (False, None)

        # Check quiet hours
        if preference.quiet_hours_enabled:
            if preference.quiet_hours_start and preference.quiet_hours_end:
                if is_within_quiet_hours(
                    preference.quiet_hours_start,
                    preference.quiet_hours_end,
                    preference.timezone
                ):
                    logger.debug(
                        f"Notification blocked: within quiet hours for subscription {subscription_id}"
                    )
                    return (False, None)

        # All checks passed - return sound preference
        return (True, preference.sound_enabled)

    except Exception as e:
        logger.error(f"Error checking notification preferences: {e}", exc_info=True)
        # On error, send notification (fail open) with sound
        return (True, True)


@dataclass
class NotificationResult:
    """Result of a notification delivery attempt."""
    subscription_id: str
    success: bool
    error: Optional[str] = None
    status_code: Optional[int] = None
    retries: int = 0


class PushNotificationService:
    """
    Service for sending Web Push notifications.

    Features:
    - VAPID authentication with automatic key management
    - Exponential backoff retry for transient failures
    - Automatic removal of invalid/expired subscriptions
    - Async notification sending (non-blocking)
    - Delivery success/failure tracking

    Usage:
        service = PushNotificationService(db_session)
        result = await service.send_notification(
            subscription_id="...",
            title="Motion Detected",
            body="Person at front door",
            data={"event_id": "..."}
        )
    """

    def __init__(self, db: Session):
        """
        Initialize PushNotificationService.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self._vapid_private_key: Optional[str] = None
        self._vapid_public_key: Optional[str] = None

    def _ensure_vapid_keys(self) -> tuple[str, str]:
        """
        Ensure VAPID keys are loaded (lazy loading).

        Returns:
            Tuple of (private_key, public_key)
        """
        if not self._vapid_private_key or not self._vapid_public_key:
            self._vapid_private_key, self._vapid_public_key = ensure_vapid_keys(self.db)
        return self._vapid_private_key, self._vapid_public_key

    async def send_notification(
        self,
        subscription_id: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        icon: str = "/icons/notification-192.svg",
        badge: str = "/icons/badge-72.svg",
        tag: Optional[str] = None,
        image: Optional[str] = None,
        actions: Optional[List[Dict[str, str]]] = None,
        renotify: bool = True,
    ) -> NotificationResult:
        """
        Send a push notification to a specific subscription.

        Args:
            subscription_id: UUID of the push subscription
            title: Notification title
            body: Notification body text
            data: Additional data payload (event_id, url, etc.)
            icon: Icon URL for notification
            badge: Badge icon URL
            tag: Tag for notification grouping/collapse
            image: Large image URL for rich notification (P4-1.3)
            actions: List of action buttons [{action, title, icon}] (P4-1.3)
            renotify: Alert again even if same tag (P4-1.3)

        Returns:
            NotificationResult with success status and details
        """
        # Get subscription
        subscription = self.db.query(PushSubscription).filter(
            PushSubscription.id == subscription_id
        ).first()

        if not subscription:
            logger.warning(f"Subscription not found: {subscription_id}")
            return NotificationResult(
                subscription_id=subscription_id,
                success=False,
                error="Subscription not found"
            )

        return await self._send_to_subscription(
            subscription=subscription,
            title=title,
            body=body,
            data=data,
            icon=icon,
            badge=badge,
            tag=tag,
            image=image,
            actions=actions,
            renotify=renotify
        )

    async def broadcast_notification(
        self,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        icon: str = "/icons/notification-192.svg",
        badge: str = "/icons/badge-72.svg",
        tag: Optional[str] = None,
        image: Optional[str] = None,
        actions: Optional[List[Dict[str, str]]] = None,
        renotify: bool = True,
        silent: bool = False,
    ) -> List[NotificationResult]:
        """
        Send a push notification to all subscriptions.

        Args:
            title: Notification title
            body: Notification body text
            data: Additional data payload
            icon: Icon URL for notification
            badge: Badge icon URL
            tag: Tag for notification grouping/collapse
            image: Large image URL for rich notification (P4-1.3)
            actions: List of action buttons [{action, title, icon}] (P4-1.3)
            renotify: Alert again even if same tag (P4-1.3)
            silent: Suppress notification sound (P4-1.4)

        Returns:
            List of NotificationResult for each subscription
        """
        subscriptions = self.db.query(PushSubscription).all()

        if not subscriptions:
            logger.info("No push subscriptions to broadcast to")
            return []

        logger.info(f"Broadcasting notification to {len(subscriptions)} subscriptions")

        # Send notifications concurrently
        tasks = [
            self._send_to_subscription(
                subscription=sub,
                title=title,
                body=body,
                data=data,
                icon=icon,
                badge=badge,
                tag=tag,
                image=image,
                actions=actions,
                renotify=renotify,
                silent=silent
            )
            for sub in subscriptions
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle exceptions
        notification_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Broadcast exception for subscription: {result}")
                notification_results.append(NotificationResult(
                    subscription_id=subscriptions[i].id,
                    success=False,
                    error=str(result)
                ))
            else:
                notification_results.append(result)

        # Log summary
        success_count = sum(1 for r in notification_results if r.success)
        logger.info(
            f"Broadcast complete: {success_count}/{len(subscriptions)} successful",
            extra={
                "total_subscriptions": len(subscriptions),
                "successful_deliveries": success_count,
                "failed_deliveries": len(subscriptions) - success_count
            }
        )

        return notification_results

    async def broadcast_event_notification(
        self,
        title: str,
        body: str,
        camera_id: Optional[str] = None,
        smart_detection_type: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        icon: str = "/icons/notification-192.svg",
        badge: str = "/icons/badge-72.svg",
        tag: Optional[str] = None,
        image: Optional[str] = None,
        actions: Optional[List[Dict[str, str]]] = None,
        renotify: bool = True,
    ) -> List[NotificationResult]:
        """
        Send an event notification with preference filtering (Story P4-1.4).

        For each subscription, checks preferences before sending:
        - Camera enabled
        - Object type enabled
        - Not in quiet hours
        - Respects sound preference

        Args:
            title: Notification title
            body: Notification body text
            camera_id: Camera UUID for preference filtering
            smart_detection_type: Object type for preference filtering
            data: Additional data payload
            icon: Icon URL for notification
            badge: Badge icon URL
            tag: Tag for notification grouping/collapse
            image: Large image URL for rich notification
            actions: List of action buttons
            renotify: Alert again even if same tag

        Returns:
            List of NotificationResult for each subscription (skipped subscriptions included)
        """
        subscriptions = self.db.query(PushSubscription).all()

        if not subscriptions:
            logger.info("No push subscriptions to broadcast to")
            return []

        logger.info(f"Broadcasting event notification to {len(subscriptions)} subscriptions (with preference filtering)")

        # Build list of (subscription, should_send, sound_enabled) tuples
        send_list = []
        skipped_count = 0

        for sub in subscriptions:
            should_send, sound_enabled = should_send_notification(
                self.db,
                sub.id,
                camera_id=camera_id,
                smart_detection_type=smart_detection_type
            )

            if should_send:
                send_list.append((sub, sound_enabled))
            else:
                skipped_count += 1

        if not send_list:
            logger.info(f"All {skipped_count} subscriptions filtered by preferences")
            return []

        logger.info(
            f"Sending to {len(send_list)} subscriptions ({skipped_count} skipped by preferences)",
            extra={
                "camera_id": camera_id,
                "smart_detection_type": smart_detection_type,
                "subscriptions_to_send": len(send_list),
                "subscriptions_skipped": skipped_count
            }
        )

        # Send notifications concurrently with per-subscription sound preference
        tasks = [
            self._send_to_subscription(
                subscription=sub,
                title=title,
                body=body,
                data=data,
                icon=icon,
                badge=badge,
                tag=tag,
                image=image,
                actions=actions,
                renotify=renotify,
                silent=not sound_enabled if sound_enabled is not None else False
            )
            for sub, sound_enabled in send_list
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle exceptions
        notification_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Broadcast exception for subscription: {result}")
                notification_results.append(NotificationResult(
                    subscription_id=send_list[i][0].id,
                    success=False,
                    error=str(result)
                ))
            else:
                notification_results.append(result)

        # Log summary
        success_count = sum(1 for r in notification_results if r.success)
        logger.info(
            f"Event broadcast complete: {success_count}/{len(send_list)} successful ({skipped_count} skipped by preferences)",
            extra={
                "total_subscriptions": len(subscriptions),
                "subscriptions_filtered": skipped_count,
                "subscriptions_attempted": len(send_list),
                "successful_deliveries": success_count,
                "failed_deliveries": len(send_list) - success_count
            }
        )

        return notification_results

    async def _send_to_subscription(
        self,
        subscription: PushSubscription,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]],
        icon: str,
        badge: str,
        tag: Optional[str],
        image: Optional[str] = None,
        actions: Optional[List[Dict[str, str]]] = None,
        renotify: bool = True,
        silent: bool = False,
    ) -> NotificationResult:
        """
        Send notification to a single subscription with retry logic.

        Implements exponential backoff for transient failures.
        Automatically removes invalid/expired subscriptions (410/404 responses only).
        Supports rich notifications with images, actions, and collapse (P4-1.3).
        Supports silent mode for sound preference (P4-1.4).

        Note (Story P8-1.3): This method preserves subscriptions unless the push
        service explicitly returns 410 Gone or 404 Not Found. The last_used_at
        timestamp is updated on successful sends but does not invalidate the
        subscription.
        """
        # Story P8-1.3: Log entry for debugging
        logger.debug(
            f"_send_to_subscription starting",
            extra={
                "subscription_id": subscription.id,
                "endpoint_prefix": subscription.endpoint[:50] if subscription.endpoint else "N/A",
                "title": title,
            }
        )

        private_key, _ = self._ensure_vapid_keys()

        # Build notification payload (P4-1.3: add rich notification fields)
        payload = {
            "title": title,
            "body": body,
            "icon": icon,
            "badge": badge,
            "renotify": renotify,
            "silent": silent,  # P4-1.4: sound preference
        }
        if tag:
            payload["tag"] = tag
        if data:
            payload["data"] = data
        if image:
            payload["image"] = image
        if actions:
            payload["actions"] = actions

        payload_json = json.dumps(payload)

        # Get subscription info in pywebpush format
        subscription_info = subscription.get_subscription_info()

        retries = 0
        last_error = None
        last_status_code = None
        start_time = time.time()

        # Create Vapid instance from PEM key once (outside retry loop)
        # Using Vapid.from_pem() is more reliable than passing raw key string
        vapid_instance = Vapid.from_pem(private_key.encode('utf-8'))

        while retries <= MAX_RETRIES:
            try:
                # Send notification using pywebpush
                # Run in executor since webpush is synchronous
                loop = asyncio.get_event_loop()

                # Define sync function to call webpush (avoids lambda capture issues)
                def send_push():
                    return webpush(
                        subscription_info=subscription_info,
                        data=payload_json,
                        vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
                        vapid_private_key=vapid_instance,  # Pass the Vapid instance
                    )

                await loop.run_in_executor(None, send_push)

                # Success - update last_used_at
                subscription.last_used_at = datetime.now(timezone.utc)
                self.db.commit()

                # Record metrics
                duration = time.time() - start_time
                record_push_notification_sent("success", duration)

                logger.info(
                    f"Push notification sent successfully",
                    extra={
                        "subscription_id": subscription.id,
                        "title": title,
                        "retries": retries,
                        "duration_seconds": duration
                    }
                )

                return NotificationResult(
                    subscription_id=subscription.id,
                    success=True,
                    retries=retries
                )

            except WebPushException as e:
                last_error = str(e)
                last_status_code = e.response.status_code if e.response else None

                # Check if subscription is invalid/expired (should not retry)
                if last_status_code in (404, 410):
                    # 404: Not Found, 410: Gone - subscription is invalid
                    duration = time.time() - start_time
                    record_push_notification_sent("failure", duration)

                    logger.warning(
                        f"Removing invalid subscription (HTTP {last_status_code})",
                        extra={
                            "subscription_id": subscription.id,
                            "status_code": last_status_code
                        }
                    )
                    self.db.delete(subscription)
                    self.db.commit()

                    return NotificationResult(
                        subscription_id=subscription.id,
                        success=False,
                        error=f"Subscription expired/invalid (HTTP {last_status_code})",
                        status_code=last_status_code,
                        retries=retries
                    )

                # Retry for transient errors (5xx, network issues)
                if retries < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY_SECONDS * (2 ** retries)
                    logger.warning(
                        f"Push notification failed, retrying in {delay}s",
                        extra={
                            "subscription_id": subscription.id,
                            "attempt": retries + 1,
                            "max_retries": MAX_RETRIES,
                            "error": last_error,
                            "status_code": last_status_code
                        }
                    )
                    await asyncio.sleep(delay)
                    retries += 1
                else:
                    break

            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"Unexpected error sending push notification: {e}",
                    exc_info=True,
                    extra={"subscription_id": subscription.id}
                )

                if retries < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY_SECONDS * (2 ** retries)
                    await asyncio.sleep(delay)
                    retries += 1
                else:
                    break

        # All retries exhausted - record failure metric
        duration = time.time() - start_time
        record_push_notification_sent("failure", duration)

        logger.error(
            f"Push notification failed after {MAX_RETRIES} retries",
            extra={
                "subscription_id": subscription.id,
                "error": last_error,
                "status_code": last_status_code,
                "duration_seconds": duration
            }
        )

        return NotificationResult(
            subscription_id=subscription.id,
            success=False,
            error=last_error,
            status_code=last_status_code,
            retries=retries
        )


# ============================================================================
# Global service accessor
# ============================================================================

_push_service: Optional[PushNotificationService] = None


def get_push_notification_service(db: Optional[Session] = None) -> PushNotificationService:
    """
    Get the PushNotificationService instance.

    Args:
        db: Optional database session. If not provided, creates new session.

    Returns:
        PushNotificationService instance
    """
    if db is None:
        db = SessionLocal()

    return PushNotificationService(db)


# ============================================================================
# Rich Notification Helpers (Story P4-1.3)
# ============================================================================

# Default action buttons for event notifications
DEFAULT_NOTIFICATION_ACTIONS = [
    {"action": "view", "title": "View", "icon": "/icons/view-24.svg"},
    {"action": "dismiss", "title": "Dismiss", "icon": "/icons/dismiss-24.svg"},
]


def format_rich_notification(
    event_id: str,
    camera_id: str,
    camera_name: str,
    description: str,
    thumbnail_url: Optional[str] = None,
    smart_detection_type: Optional[str] = None,
    anomaly_score: Optional[float] = None,
    entity_names: Optional[List[str]] = None,
    is_vip: bool = False,
    recognition_status: Optional[str] = None,
    delivery_carrier: Optional[str] = None,
    delivery_carrier_display: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format a rich notification payload for an event (Story P4-1.3, P4-7.3, P4-8.4).

    Creates a notification with:
    - Descriptive title based on smart detection type
    - Entity names when recognized (P4-8.4): "John at Front Door" instead of "Person Detected"
    - VIP indicator for priority entities (P4-8.4): star emoji prefix
    - Anomaly indicator in title for high anomaly events (P4-7.3)
    - Truncated body text
    - Thumbnail image URL
    - Action buttons (View, Dismiss)
    - Deep link URL
    - Tag for notification collapse per camera

    Args:
        event_id: UUID of the event
        camera_id: UUID of the camera (used for collapse tag)
        camera_name: Display name of the camera
        description: AI-generated event description
        thumbnail_url: Optional URL to event thumbnail image
        smart_detection_type: Optional smart detection type (person, vehicle, etc.)
        anomaly_score: Optional anomaly score 0.0-1.0 (P4-7.3)
        entity_names: Optional list of recognized entity names (P4-8.4)
        is_vip: Whether any matched entity is VIP (P4-8.4)
        recognition_status: Recognition status - 'known', 'stranger', 'unknown' (P4-8.4)

    Returns:
        Dict with notification payload fields
    """
    # Story P4-7.3: Check for high anomaly (>0.6)
    from app.services.anomaly_scoring_service import AnomalyScoringService
    is_high_anomaly = (
        anomaly_score is not None and
        anomaly_score >= AnomalyScoringService.HIGH_THRESHOLD
    )

    # Story P4-8.4: Build VIP prefix
    vip_prefix = "⭐ " if is_vip else ""

    # Story P4-8.4: Check if we have recognized entity names
    has_entity_names = entity_names and len(entity_names) > 0

    # Build title based on detection type and entity recognition
    if has_entity_names:
        # P4-8.4: Use entity names in title
        if len(entity_names) == 1:
            name_str = entity_names[0]
        elif len(entity_names) == 2:
            name_str = f"{entity_names[0]} and {entity_names[1]}"
        else:
            name_str = f"{entity_names[0]} and {len(entity_names) - 1} others"

        # P4-7.3: Add unusual indicator if high anomaly
        if is_high_anomaly:
            title = f"{vip_prefix}{name_str} - Unusual Activity at {camera_name}"
        else:
            title = f"{vip_prefix}{name_str} at {camera_name}"
    elif smart_detection_type:
        detection_labels = {
            "person": "Person Detected",
            "vehicle": "Vehicle Detected",
            "package": "Package Detected",
            "animal": "Animal Detected",
            "ring": "Doorbell Ring",
            "motion": "Motion Detected",
        }
        detection_label = detection_labels.get(smart_detection_type, "Motion Detected")

        # Story P7-2.2: Special handling for package with carrier
        if smart_detection_type == "package" and delivery_carrier_display:
            detection_label = f"Package delivered by {delivery_carrier_display}"

        # P4-7.3: Add "Unusual" prefix for high anomaly events
        if is_high_anomaly:
            title = f"{vip_prefix}{camera_name}: Unusual Activity - {detection_label}"
        else:
            title = f"{vip_prefix}{camera_name}: {detection_label}"
    else:
        if is_high_anomaly:
            title = f"{vip_prefix}{camera_name}: Unusual Activity"
        else:
            title = f"{vip_prefix}{camera_name}: Motion Detected"

    # Truncate description if too long
    body = description
    if len(body) > 100:
        body = body[:97] + "..."

    # Build deep link URL
    url = f"/events?highlight={event_id}"

    # Build data payload
    data = {
        "event_id": event_id,
        "camera_id": camera_id,
        "camera_name": camera_name,
        "url": url,
    }
    if smart_detection_type:
        data["smart_detection_type"] = smart_detection_type
    # Story P4-7.3: Include anomaly data in payload
    if anomaly_score is not None:
        data["anomaly_score"] = anomaly_score
        data["is_unusual"] = is_high_anomaly
    # Story P4-8.4: Include entity recognition data in payload
    if entity_names:
        data["entity_names"] = entity_names
    if is_vip:
        data["is_vip"] = True
    if recognition_status:
        data["recognition_status"] = recognition_status
    # Story P7-2.2: Include carrier data in payload
    if delivery_carrier:
        data["delivery_carrier"] = delivery_carrier
    if delivery_carrier_display:
        data["delivery_carrier_display"] = delivery_carrier_display

    # Build full notification payload
    notification = {
        "title": title,
        "body": body,
        "data": data,
        "tag": camera_id,  # Use camera_id for collapse (AC4)
        "actions": DEFAULT_NOTIFICATION_ACTIONS,
        "renotify": True,  # Alert on updates even with same tag
    }

    # Add thumbnail image if available (AC1, AC8)
    if thumbnail_url:
        notification["image"] = thumbnail_url

    return notification


async def send_event_notification(
    event_id: str,
    camera_name: str,
    description: str,
    thumbnail_url: Optional[str] = None,
    camera_id: Optional[str] = None,
    smart_detection_type: Optional[str] = None,
    anomaly_score: Optional[float] = None,
    entity_names: Optional[List[str]] = None,
    is_vip: bool = False,
    recognition_status: Optional[str] = None,
    delivery_carrier: Optional[str] = None,
    delivery_carrier_display: Optional[str] = None,
    db: Optional[Session] = None
) -> List[NotificationResult]:
    """
    Convenience function to send rich notification for a new event (P4-1.3, P4-1.4, P4-7.3, P4-8.4).

    This is the main entry point for event pipeline integration.
    Sends to subscriptions with preference filtering:
    - Per-camera enable/disable (P4-1.4)
    - Object type filtering (P4-1.4)
    - Quiet hours (P4-1.4)
    - Sound preference (P4-1.4)

    Supports entity-aware notifications (P4-8.4):
    - Personalized titles with entity names ("John at Front Door")
    - VIP indicator (star emoji prefix)
    - Recognition status in payload

    Note on session management (Story P8-1.3):
    - This function creates its own database session if none provided
    - The session is kept open until all notifications are sent
    - Session is only closed in finally block after all async operations complete
    - Subscriptions are NOT deleted or invalidated by this function (except for 410 responses)

    Args:
        event_id: UUID of the event
        camera_name: Name of the camera that detected the event
        description: AI-generated event description
        thumbnail_url: Optional URL to event thumbnail
        camera_id: Optional camera UUID (for notification collapse and preference filtering)
        smart_detection_type: Optional smart detection type (person, vehicle, etc.)
        anomaly_score: Optional anomaly score 0.0-1.0 for unusual activity indicator (P4-7.3)
        entity_names: Optional list of recognized entity names (P4-8.4)
        is_vip: Whether any matched entity is VIP (P4-8.4)
        recognition_status: Recognition status - 'known', 'stranger', 'unknown' (P4-8.4)
        db: Optional database session

    Returns:
        List of NotificationResult for each subscription
    """
    # Track whether we created the session (for cleanup)
    session_created = db is None
    if session_created:
        db = SessionLocal()

    # Story P8-1.3: Enhanced logging for debugging notification flow
    logger.info(
        f"send_event_notification called",
        extra={
            "event_id": event_id,
            "camera_name": camera_name,
            "camera_id": camera_id,
            "smart_detection_type": smart_detection_type,
            "session_created": session_created,
        }
    )

    try:
        service = PushNotificationService(db)

        # Use camera_id for collapse tag, fallback to event_id
        collapse_tag = camera_id or event_id

        # Format rich notification (P4-1.3, P4-7.3, P4-8.4, P7-2.2)
        notification = format_rich_notification(
            event_id=event_id,
            camera_id=collapse_tag,
            camera_name=camera_name,
            description=description,
            thumbnail_url=thumbnail_url,
            smart_detection_type=smart_detection_type,
            anomaly_score=anomaly_score,
            entity_names=entity_names,
            is_vip=is_vip,
            recognition_status=recognition_status,
            delivery_carrier=delivery_carrier,
            delivery_carrier_display=delivery_carrier_display,
        )

        # Use broadcast_event_notification for preference filtering (P4-1.4)
        results = await service.broadcast_event_notification(
            title=notification["title"],
            body=notification["body"],
            camera_id=camera_id,  # For preference filtering
            smart_detection_type=smart_detection_type,  # For preference filtering
            data=notification["data"],
            tag=notification["tag"],
            image=notification.get("image"),
            actions=notification["actions"],
            renotify=notification["renotify"],
        )

        # Story P8-1.3: Log results summary
        success_count = sum(1 for r in results if r.success)
        logger.info(
            f"send_event_notification completed",
            extra={
                "event_id": event_id,
                "total_subscriptions": len(results),
                "successful": success_count,
                "failed": len(results) - success_count,
            }
        )

        return results

    except Exception as e:
        logger.error(
            f"Error sending event notification",
            exc_info=True,
            extra={
                "event_id": event_id,
                "error": str(e),
            }
        )
        return []
    finally:
        # Only close session if we created it
        if session_created and db:
            db.close()
            logger.debug(f"Closed database session for event {event_id}")
