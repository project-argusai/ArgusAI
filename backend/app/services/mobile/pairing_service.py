"""
Pairing Service (Story P12-3.2)

Handles 6-digit pairing code generation, confirmation, and cleanup.
"""
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.pairing_code import PairingCode
from app.models.device import Device

logger = logging.getLogger(__name__)

# Constants
CODE_LENGTH = 6
CODE_EXPIRY_MINUTES = 5
MAX_ATTEMPTS_PER_MINUTE = 5


class PairingService:
    """
    Service for managing device pairing codes.

    Flow:
    1. Mobile app calls generate_code() to get a 6-digit code
    2. User enters code in web dashboard
    3. Dashboard calls confirm_code() to associate with user
    4. Mobile app polls check_status() or calls exchange_code()
    5. After exchange, code is deleted
    """

    def __init__(self, db: Session):
        self.db = db

    def generate_code(
        self,
        device_id: str,
        platform: str,
        device_name: Optional[str] = None,
        device_model: Optional[str] = None
    ) -> PairingCode:
        """
        Generate a new 6-digit pairing code.

        Args:
            device_id: Hardware device identifier
            platform: 'ios' or 'android'
            device_name: Optional user-friendly name
            device_model: Optional hardware model

        Returns:
            PairingCode with generated code

        Raises:
            ValueError: If rate limit exceeded
        """
        # Clean up expired codes for this device
        self._cleanup_expired_codes(device_id)

        # Check rate limiting
        recent_count = self._count_recent_attempts(device_id)
        if recent_count >= MAX_ATTEMPTS_PER_MINUTE:
            raise ValueError("Rate limit exceeded. Please wait before requesting another code.")

        # Generate unique 6-digit code
        code = self._generate_unique_code()

        # Create pairing code record
        pairing_code = PairingCode(
            code=code,
            device_id=device_id,
            platform=platform,
            device_name=device_name,
            device_model=device_model,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRY_MINUTES)
        )

        self.db.add(pairing_code)
        self.db.commit()
        self.db.refresh(pairing_code)

        logger.info(
            "Pairing code generated",
            extra={
                "device_id": device_id,
                "platform": platform,
                "expires_in": CODE_EXPIRY_MINUTES * 60,
            }
        )

        return pairing_code

    def confirm_code(self, code: str, user_id: str) -> Optional[PairingCode]:
        """
        Confirm a pairing code from the web dashboard.

        Args:
            code: 6-digit code entered by user
            user_id: ID of the authenticated user

        Returns:
            PairingCode if found and valid, None otherwise
        """
        pairing_code = self.db.query(PairingCode).filter(
            PairingCode.code == code,
            PairingCode.confirmed_at.is_(None)
        ).first()

        if not pairing_code:
            logger.warning("Pairing code not found", extra={"code": code[:2] + "****"})
            return None

        if pairing_code.is_expired:
            logger.warning("Pairing code expired", extra={"code": code[:2] + "****"})
            return None

        # Confirm the code
        pairing_code.user_id = user_id
        pairing_code.confirmed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(pairing_code)

        logger.info(
            "Pairing code confirmed",
            extra={
                "device_id": pairing_code.device_id,
                "user_id": user_id,
            }
        )

        return pairing_code

    def check_status(self, code: str) -> dict:
        """
        Check the status of a pairing code (polled by mobile app).

        Args:
            code: 6-digit code to check

        Returns:
            Dict with 'confirmed' and 'expired' status
        """
        pairing_code = self.db.query(PairingCode).filter(
            PairingCode.code == code
        ).first()

        if not pairing_code:
            return {"confirmed": False, "expired": True}

        return {
            "confirmed": pairing_code.is_confirmed,
            "expired": pairing_code.is_expired
        }

    def get_confirmed_code(self, code: str) -> Optional[PairingCode]:
        """
        Get a confirmed pairing code ready for token exchange.

        Args:
            code: 6-digit code

        Returns:
            PairingCode if valid for exchange, None otherwise
        """
        pairing_code = self.db.query(PairingCode).filter(
            PairingCode.code == code
        ).first()

        if not pairing_code:
            return None

        if not pairing_code.is_valid_for_exchange:
            return None

        return pairing_code

    def delete_code(self, code: str) -> None:
        """Delete a pairing code after successful exchange."""
        self.db.query(PairingCode).filter(PairingCode.code == code).delete()
        self.db.commit()

    def get_pending_code(self, code: str) -> Optional[PairingCode]:
        """
        Get a specific pending pairing code.

        Args:
            code: The 6-digit pairing code

        Returns:
            PairingCode if found and still pending, None otherwise
        """
        now = datetime.now(timezone.utc)
        return self.db.query(PairingCode).filter(
            PairingCode.code == code,
            PairingCode.confirmed_at.is_(None),
            PairingCode.expires_at > now
        ).first()

    def get_pending_pairings(self, user_id: Optional[str] = None) -> list[PairingCode]:
        """
        Get pending (unconfirmed, unexpired) pairing codes.

        Args:
            user_id: If provided, return pending codes for confirmed user's device

        Returns:
            List of pending PairingCode objects
        """
        now = datetime.now(timezone.utc)

        query = self.db.query(PairingCode).filter(
            PairingCode.confirmed_at.is_(None),
            PairingCode.expires_at > now
        )

        return query.order_by(PairingCode.created_at.desc()).all()

    def _generate_unique_code(self) -> str:
        """Generate a unique 6-digit numeric code."""
        max_attempts = 10
        for _ in range(max_attempts):
            # Generate cryptographically secure random digits
            code = ''.join(str(secrets.randbelow(10)) for _ in range(CODE_LENGTH))

            # Check uniqueness
            existing = self.db.query(PairingCode).filter(
                PairingCode.code == code
            ).first()

            if not existing:
                return code

        # Extremely unlikely, but handle it
        raise RuntimeError("Failed to generate unique pairing code")

    def _cleanup_expired_codes(self, device_id: Optional[str] = None) -> int:
        """
        Delete expired pairing codes.

        Args:
            device_id: If provided, only cleanup for this device

        Returns:
            Number of codes deleted
        """
        now = datetime.now(timezone.utc)

        query = self.db.query(PairingCode).filter(PairingCode.expires_at < now)

        if device_id:
            query = query.filter(PairingCode.device_id == device_id)

        count = query.delete()
        self.db.commit()

        if count > 0:
            logger.debug(f"Cleaned up {count} expired pairing codes")

        return count

    def _count_recent_attempts(self, device_id: str) -> int:
        """Count pairing attempts in the last minute for rate limiting."""
        one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)

        return self.db.query(PairingCode).filter(
            PairingCode.device_id == device_id,
            PairingCode.created_at > one_minute_ago
        ).count()
