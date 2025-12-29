"""
Delivery Service for Digest Distribution (Story P4-4.3)

Provides multi-channel delivery for activity digests:
- Email delivery via SMTP (aiosmtplib)
- Push notifications via existing PushNotificationService
- In-app notifications via Notification model

Architecture:
    DigestScheduler.run_scheduled_digest()
        │
        ▼
    DeliveryService.deliver_digest(digest, channels)
        │
        ├── Email Channel ──► SMTP → Recipient(s)
        ├── Push Channel ──► pywebpush → All Subscriptions
        └── In-App Channel ──► Notification table + WebSocket
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.models.activity_summary import ActivitySummary
from app.models.system_setting import SystemSetting
from app.models.system_notification import SystemNotification
from app.models.push_subscription import PushSubscription
from app.services.push_notification_service import (
    PushNotificationService,
    get_push_notification_service,
)
from app.utils.encryption import decrypt_password

logger = logging.getLogger(__name__)

# Configuration
EMAIL_TIMEOUT_SECONDS = 30
PUSH_DELIVERY_TARGET_SECONDS = 5  # NFR2: Push within 5 seconds
MAX_SUMMARY_TRUNCATE_LENGTH = 200


@dataclass
class DeliveryResult:
    """Result of digest delivery attempt."""
    success: bool
    channels_attempted: List[str] = field(default_factory=list)
    channels_succeeded: List[str] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)
    delivery_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "channels_attempted": self.channels_attempted,
            "channels_succeeded": self.channels_succeeded,
            "errors": self.errors,
            "delivery_time_ms": self.delivery_time_ms
        }


class DeliveryService:
    """
    Service for delivering activity digests via multiple channels.

    Supports email, push notification, and in-app notification delivery.
    Each channel operates independently - failure in one does not affect others.

    Attributes:
        EMAIL_TIMEOUT_SECONDS: Maximum time for SMTP operations
    """

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize DeliveryService.

        Args:
            db: Optional database session. Creates new if not provided.
        """
        self._db = db
        self._owns_db = db is None

        logger.info(
            "DeliveryService initialized",
            extra={"event_type": "delivery_service_init"}
        )

    def _get_db(self) -> Session:
        """Get database session, creating one if needed.

        Note: Uses SessionLocal directly for lazy initialization pattern.
        The session is closed by _close_db() when the service is done.
        """
        if self._db is None:
            from app.core.database import SessionLocal
            self._db = SessionLocal()
            self._owns_db = True
        return self._db

    def _close_db(self) -> None:
        """Close database session if we own it."""
        if self._owns_db and self._db is not None:
            self._db.close()
            self._db = None

    def _get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a system setting value by key."""
        db = self._get_db()
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        return setting.value if setting else default

    def _get_delivery_channels(self) -> List[str]:
        """Get configured delivery channels from settings."""
        channels_json = self._get_setting("digest_delivery_channels", "[]")
        try:
            channels = json.loads(channels_json)
            if isinstance(channels, list):
                return [c for c in channels if c in ("email", "push", "in_app")]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    def _get_email_recipients(self) -> List[str]:
        """Get email recipients from settings."""
        recipients_str = self._get_setting("digest_email_recipients", "")
        if not recipients_str:
            return []
        # Parse comma-separated emails
        return [email.strip() for email in recipients_str.split(",") if email.strip()]

    def _get_smtp_config(self) -> Dict[str, Any]:
        """Get SMTP configuration from settings."""
        return {
            "host": self._get_setting("smtp_host", ""),
            "port": int(self._get_setting("smtp_port", "587") or "587"),
            "username": self._get_setting("smtp_username", ""),
            "password_encrypted": self._get_setting("smtp_password_encrypted", ""),
            "from_email": self._get_setting("smtp_from_email", ""),
            "use_tls": self._get_setting("smtp_use_tls", "true").lower() == "true",
        }

    async def deliver_digest(
        self,
        digest: ActivitySummary,
        channels: Optional[List[str]] = None
    ) -> DeliveryResult:
        """
        Deliver a digest via specified channels.

        Each channel operates independently. Failures in one channel
        do not affect others. All channels are attempted regardless
        of individual failures.

        Args:
            digest: ActivitySummary record to deliver
            channels: List of channels to use. If None, uses configured channels.
                     Valid values: "email", "push", "in_app"

        Returns:
            DeliveryResult with per-channel success/failure status
        """
        start_time = time.time()

        # Use configured channels if none specified
        if channels is None:
            channels = self._get_delivery_channels()

        # Filter to valid channels
        valid_channels = [c for c in channels if c in ("email", "push", "in_app")]

        if not valid_channels:
            logger.warning(
                "No valid delivery channels specified",
                extra={"event_type": "delivery_no_channels"}
            )
            return DeliveryResult(
                success=False,
                channels_attempted=[],
                channels_succeeded=[],
                errors={"general": "No valid delivery channels configured"}
            )

        logger.info(
            f"Starting digest delivery to {len(valid_channels)} channels",
            extra={
                "event_type": "delivery_start",
                "digest_id": digest.id,
                "channels": valid_channels
            }
        )

        result = DeliveryResult(
            success=False,
            channels_attempted=valid_channels.copy(),
            channels_succeeded=[],
            errors={}
        )

        # Attempt each channel independently
        for channel in valid_channels:
            try:
                if channel == "email":
                    await self._send_email_digest(digest)
                elif channel == "push":
                    await self._send_push_digest(digest)
                elif channel == "in_app":
                    await self._create_inapp_notification(digest)

                result.channels_succeeded.append(channel)
                logger.info(
                    f"Delivery succeeded for channel: {channel}",
                    extra={
                        "event_type": "delivery_channel_success",
                        "digest_id": digest.id,
                        "channel": channel
                    }
                )
            except Exception as e:
                error_msg = str(e)
                result.errors[channel] = error_msg
                logger.error(
                    f"Delivery failed for channel {channel}: {e}",
                    extra={
                        "event_type": "delivery_channel_error",
                        "digest_id": digest.id,
                        "channel": channel,
                        "error": error_msg
                    },
                    exc_info=True
                )

        # Success if at least one channel succeeded
        result.success = len(result.channels_succeeded) > 0
        result.delivery_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"Digest delivery complete: {len(result.channels_succeeded)}/{len(valid_channels)} succeeded",
            extra={
                "event_type": "delivery_complete",
                "digest_id": digest.id,
                "success": result.success,
                "succeeded": result.channels_succeeded,
                "failed": list(result.errors.keys()),
                "delivery_time_ms": result.delivery_time_ms
            }
        )

        return result

    async def _send_email_digest(self, digest: ActivitySummary) -> None:
        """
        Send digest via email.

        Args:
            digest: ActivitySummary to send

        Raises:
            Exception if email delivery fails
        """
        import aiosmtplib

        recipients = self._get_email_recipients()
        if not recipients:
            raise ValueError("No email recipients configured")

        smtp_config = self._get_smtp_config()
        if not smtp_config["host"]:
            raise ValueError("SMTP host not configured")

        # Decrypt SMTP password
        smtp_password = ""
        if smtp_config["password_encrypted"]:
            try:
                smtp_password = decrypt_password(smtp_config["password_encrypted"])
            except Exception as e:
                logger.error(f"Failed to decrypt SMTP password: {e}")
                raise ValueError("Failed to decrypt SMTP password")

        # Format date for display
        period_date = digest.period_start.strftime("%B %d, %Y")

        # Build email content
        subject = f"Daily Activity Summary - {period_date}"
        html_content = self._build_email_html(digest, period_date)
        text_content = self._build_email_text(digest, period_date)

        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_config["from_email"] or smtp_config["username"]
        msg["To"] = ", ".join(recipients)

        # Attach plain text and HTML versions
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        # Send email
        try:
            await asyncio.wait_for(
                aiosmtplib.send(
                    msg,
                    hostname=smtp_config["host"],
                    port=smtp_config["port"],
                    username=smtp_config["username"] or None,
                    password=smtp_password or None,
                    start_tls=smtp_config["use_tls"],
                    timeout=EMAIL_TIMEOUT_SECONDS,
                ),
                timeout=EMAIL_TIMEOUT_SECONDS + 5
            )

            logger.info(
                f"Email sent to {len(recipients)} recipients",
                extra={
                    "event_type": "email_sent",
                    "digest_id": digest.id,
                    "recipient_count": len(recipients)
                }
            )
        except asyncio.TimeoutError:
            raise Exception(f"Email delivery timed out after {EMAIL_TIMEOUT_SECONDS}s")

    def _build_email_html(self, digest: ActivitySummary, period_date: str) -> str:
        """Build HTML email content for digest."""
        # Parse stats if available (stored in summary stats)
        event_count = digest.event_count

        dashboard_url = self._get_setting("dashboard_url", "http://localhost:3000")
        digest_url = f"{dashboard_url}/summaries?date={digest.period_start.strftime('%Y-%m-%d')}"

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Activity Summary</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1a1a2e; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .header .date {{ opacity: 0.8; margin-top: 5px; }}
        .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 8px 8px; }}
        .summary {{ background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #4CAF50; }}
        .stats {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0; }}
        .stat {{ background: white; padding: 15px; border-radius: 8px; flex: 1; min-width: 120px; text-align: center; }}
        .stat-value {{ font-size: 28px; font-weight: bold; color: #1a1a2e; }}
        .stat-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
        .cta {{ display: inline-block; background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 15px; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Daily Activity Summary</h1>
        <div class="date">{period_date}</div>
    </div>
    <div class="content">
        <div class="summary">
            <p>{digest.summary_text}</p>
        </div>
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{event_count}</div>
                <div class="stat-label">Total Events</div>
            </div>
        </div>
        <a href="{digest_url}" class="cta">View Full Details</a>
    </div>
    <div class="footer">
        <p>Sent by ArgusAI - Your AI-Powered Security Assistant</p>
    </div>
</body>
</html>"""

    def _build_email_text(self, digest: ActivitySummary, period_date: str) -> str:
        """Build plain text email content for digest."""
        dashboard_url = self._get_setting("dashboard_url", "http://localhost:3000")
        digest_url = f"{dashboard_url}/summaries?date={digest.period_start.strftime('%Y-%m-%d')}"

        return f"""Daily Activity Summary - {period_date}
{'=' * 40}

{digest.summary_text}

Quick Stats:
- Total Events: {digest.event_count}

View full details: {digest_url}

---
Sent by ArgusAI - Your AI-Powered Security Assistant
"""

    async def _send_push_digest(self, digest: ActivitySummary) -> None:
        """
        Send digest via push notification.

        Uses existing PushNotificationService infrastructure.

        Args:
            digest: ActivitySummary to send

        Raises:
            Exception if push delivery fails completely
        """
        start_time = time.time()
        db = self._get_db()

        # Check if any push subscriptions exist
        subscription_count = db.query(PushSubscription).count()
        if subscription_count == 0:
            logger.info(
                "No push subscriptions to deliver to",
                extra={"event_type": "push_no_subscriptions"}
            )
            return

        # Format push notification
        period_date = digest.period_start.strftime("%B %d")
        title = f"Daily Summary - {period_date}"

        # Truncate summary text to 200 chars
        body = digest.summary_text
        if len(body) > MAX_SUMMARY_TRUNCATE_LENGTH:
            body = body[:MAX_SUMMARY_TRUNCATE_LENGTH - 3] + "..."

        # Build data payload
        data = {
            "type": "digest",
            "digest_id": digest.id,
            "url": f"/summaries?date={digest.period_start.strftime('%Y-%m-%d')}"
        }

        # Use existing push service
        push_service = get_push_notification_service(db)

        results = await push_service.broadcast_notification(
            title=title,
            body=body,
            data=data,
            tag=f"digest-{digest.period_start.strftime('%Y-%m-%d')}",
            icon="/icons/notification-192.svg",
            badge="/icons/badge-72.svg",
        )

        # Check delivery time
        delivery_time = time.time() - start_time
        if delivery_time > PUSH_DELIVERY_TARGET_SECONDS:
            logger.warning(
                f"Push delivery exceeded {PUSH_DELIVERY_TARGET_SECONDS}s target: {delivery_time:.2f}s",
                extra={
                    "event_type": "push_slow_delivery",
                    "delivery_time_seconds": delivery_time,
                    "target_seconds": PUSH_DELIVERY_TARGET_SECONDS
                }
            )

        # Count successes
        success_count = sum(1 for r in results if r.success)

        logger.info(
            f"Push notifications sent: {success_count}/{len(results)} succeeded",
            extra={
                "event_type": "push_delivery_complete",
                "digest_id": digest.id,
                "success_count": success_count,
                "total_count": len(results),
                "delivery_time_seconds": delivery_time
            }
        )

        # Raise if all failed
        if len(results) > 0 and success_count == 0:
            raise Exception(f"All {len(results)} push notifications failed")

    async def _create_inapp_notification(self, digest: ActivitySummary) -> None:
        """
        Create in-app notification for digest.

        Uses SystemNotification model for digest notifications.

        Args:
            digest: ActivitySummary to create notification for
        """
        db = self._get_db()

        # Format notification content
        period_date = digest.period_start.strftime("%B %d, %Y")
        title = "Daily Summary Available"

        # Get first sentence or truncate to 150 chars
        message = digest.summary_text
        if "." in message[:150]:
            message = message[:message.index(".") + 1]
        elif len(message) > 150:
            message = message[:147] + "..."

        # Create system notification (digest type doesn't require event_id/rule_id)
        notification = SystemNotification(
            id=str(uuid.uuid4()),
            title=title,
            message=message,
            notification_type="digest",
            severity="info",
            action_url=f"/summaries?date={digest.period_start.strftime('%Y-%m-%d')}",
            extra_data={
                "digest_id": digest.id,
                "period_date": period_date,
                "event_count": digest.event_count
            },
            read=False,
            dismissed=False,
            created_at=datetime.now(timezone.utc)
        )

        db.add(notification)
        db.commit()

        logger.info(
            "In-app notification created for digest",
            extra={
                "event_type": "inapp_notification_created",
                "digest_id": digest.id,
                "notification_id": notification.id
            }
        )


# Singleton instance
_delivery_service: Optional[DeliveryService] = None


def get_delivery_service(db: Optional[Session] = None) -> DeliveryService:
    """
    Get the DeliveryService instance.

    Args:
        db: Optional database session

    Returns:
        DeliveryService instance
    """
    if db is not None:
        # If db is provided, create new instance with that session
        return DeliveryService(db)

    global _delivery_service
    if _delivery_service is None:
        _delivery_service = DeliveryService()
    return _delivery_service


def reset_delivery_service() -> None:
    """Reset the singleton instance (for testing)."""
    global _delivery_service
    if _delivery_service is not None:
        _delivery_service._close_db()
    _delivery_service = None
