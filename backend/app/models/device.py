"""Device SQLAlchemy ORM model for mobile push notification tokens (Story P11-2.4, P11-2.5)"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.utils.encryption import encrypt_password, decrypt_password
import uuid
from datetime import datetime, timezone


class Device(Base):
    """
    Device model for mobile push notification tokens.

    Stores device registration data for iOS (APNS) and Android (FCM) push notifications.
    Each device represents a unique mobile device that can receive push notifications.

    Attributes:
        id: UUID primary key
        user_id: FK to users table (required for device ownership)
        device_id: Unique device identifier from mobile app
        platform: Device platform ('ios', 'android', 'web')
        name: User-friendly device name (e.g., "iPhone 15 Pro")
        push_token: Push notification token (Fernet encrypted)
        last_seen_at: Last successful interaction timestamp (UTC)
        created_at: Device registration timestamp (UTC)
    """

    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    device_id = Column(String(255), nullable=False, unique=True, index=True)
    platform = Column(String(20), nullable=False)  # 'ios', 'android', 'web'
    name = Column(String(100), nullable=True)  # User-friendly device name
    push_token = Column(Text, nullable=True)  # Fernet encrypted
    last_seen_at = Column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(timezone.utc)
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Quiet hours configuration (Story P11-2.5)
    quiet_hours_enabled = Column(Boolean, nullable=False, default=False)
    quiet_hours_start = Column(String(5), nullable=True)  # "HH:MM" format, e.g., "22:00"
    quiet_hours_end = Column(String(5), nullable=True)    # "HH:MM" format, e.g., "07:00"
    quiet_hours_timezone = Column(String(64), nullable=False, default="UTC")
    quiet_hours_override_critical = Column(Boolean, nullable=False, default=True)

    # Relationship to User
    user = relationship("User", back_populates="devices")

    __table_args__ = (
        Index('idx_devices_user', 'user_id'),
        Index('idx_devices_device_id', 'device_id'),
        Index('idx_devices_platform', 'platform'),
    )

    def __repr__(self):
        return f"<Device(id={self.id}, device_id={self.device_id[:20]}..., platform={self.platform})>"

    def set_push_token(self, token: str) -> None:
        """
        Encrypt and store push token.

        Args:
            token: Plain text push token to encrypt and store
        """
        if token:
            self.push_token = encrypt_password(token)
        else:
            self.push_token = None

    def get_push_token(self) -> str | None:
        """
        Decrypt and return push token.

        Returns:
            Decrypted push token or None if not set
        """
        if self.push_token:
            return decrypt_password(self.push_token)
        return None

    def update_last_seen(self) -> None:
        """Update last_seen_at to current time."""
        self.last_seen_at = datetime.now(timezone.utc)

    def to_dict(self, include_token: bool = False) -> dict:
        """
        Convert device to dictionary for API responses.

        Args:
            include_token: If True, include decrypted push_token (use with caution)

        Returns:
            Dictionary representation of device
        """
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "platform": self.platform,
            "name": self.name,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            # Quiet hours (Story P11-2.5)
            "quiet_hours_enabled": self.quiet_hours_enabled,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "quiet_hours_timezone": self.quiet_hours_timezone,
            "quiet_hours_override_critical": self.quiet_hours_override_critical,
        }
        if include_token:
            result["push_token"] = self.get_push_token()
        return result

    def is_in_quiet_hours(self, now: datetime = None) -> bool:
        """
        Check if device is currently in quiet hours (Story P11-2.5).

        Handles overnight quiet hours that span midnight (e.g., 22:00 - 07:00).

        Args:
            now: Optional datetime for testing; defaults to current time

        Returns:
            True if device is currently in quiet hours, False otherwise
        """
        if not self.quiet_hours_enabled:
            return False

        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False

        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(self.quiet_hours_timezone)

            if now is None:
                now = datetime.now(tz)
            else:
                # Convert to device's timezone
                now = now.astimezone(tz)

            current_time = now.time()
            start_time = datetime.strptime(self.quiet_hours_start, "%H:%M").time()
            end_time = datetime.strptime(self.quiet_hours_end, "%H:%M").time()

            # Handle overnight quiet hours (e.g., 22:00 - 07:00)
            if start_time > end_time:
                # Quiet hours span midnight
                return current_time >= start_time or current_time < end_time
            else:
                # Normal range (e.g., 09:00 - 17:00)
                return start_time <= current_time < end_time

        except Exception:
            # Fail open - if there's an error, don't block notifications
            return False
