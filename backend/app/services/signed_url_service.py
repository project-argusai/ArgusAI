"""
Signed URL Service for secure thumbnail access.

Story P11-2.6: Generates and verifies HMAC-SHA256 signed URLs for thumbnails
in push notifications. Prevents unauthorized access with short expiration.

Usage:
    from app.services.signed_url_service import get_signed_url_service

    service = get_signed_url_service()
    url = service.generate_signed_url(event_id, base_url="https://example.com")
    is_valid = service.verify_signed_url(event_id, signature, expires)
"""

import hashlib
import hmac
import logging
import time
from typing import Optional
from urllib.parse import urlencode

from app.core.config import settings

logger = logging.getLogger(__name__)

# Default expiration in seconds (60 seconds for push notifications)
DEFAULT_EXPIRATION_SECONDS = 60


class SignedURLService:
    """
    Service for generating and verifying signed URLs for secure resource access.

    Uses HMAC-SHA256 with the application's ENCRYPTION_KEY for signatures.
    Designed for short-lived access tokens in push notifications.

    Attributes:
        _secret_key: Bytes from ENCRYPTION_KEY for HMAC signing
    """

    def __init__(self, secret_key: Optional[bytes] = None):
        """
        Initialize the signed URL service.

        Args:
            secret_key: Optional secret key bytes. If not provided,
                        uses ENCRYPTION_KEY from settings.
        """
        if secret_key:
            self._secret_key = secret_key
        else:
            # Use ENCRYPTION_KEY from settings (Fernet key, base64 encoded)
            # We use the raw key bytes for HMAC signing
            self._secret_key = settings.ENCRYPTION_KEY.encode("utf-8")

        logger.debug("SignedURLService initialized")

    def generate_signed_url(
        self,
        event_id: str,
        base_url: str,
        expiration_seconds: int = DEFAULT_EXPIRATION_SECONDS,
    ) -> str:
        """
        Generate a signed URL for secure thumbnail access.

        Creates a time-limited URL with HMAC-SHA256 signature that can be
        verified by the thumbnail endpoint.

        Args:
            event_id: UUID of the event to access thumbnail for
            base_url: Base URL of the API (e.g., "https://example.com")
            expiration_seconds: How long the URL should be valid (default 60s)

        Returns:
            Complete signed URL with signature and expiration parameters

        Example:
            >>> url = service.generate_signed_url("abc-123", "https://api.example.com")
            >>> # Returns: https://api.example.com/api/v1/events/abc-123/thumbnail?signature=...&expires=...
        """
        expires = int(time.time()) + expiration_seconds

        # Create signature from event_id and expiration
        signature = self._create_signature(event_id, expires)

        # Build query parameters
        params = urlencode({"signature": signature, "expires": str(expires)})

        # Construct full URL
        url = f"{base_url.rstrip('/')}/api/v1/events/{event_id}/thumbnail?{params}"

        logger.debug(
            "Generated signed URL",
            extra={
                "event_id": event_id,
                "expires_in_seconds": expiration_seconds,
                "expires_at": expires,
            }
        )

        return url

    def verify_signed_url(
        self,
        event_id: str,
        signature: str,
        expires: int,
    ) -> bool:
        """
        Verify a signed URL is valid and not expired.

        Checks both the signature validity and expiration timestamp.

        Args:
            event_id: UUID of the event from the URL path
            signature: HMAC-SHA256 signature from query parameter
            expires: Unix timestamp expiration from query parameter

        Returns:
            True if signature is valid and not expired, False otherwise
        """
        # Check expiration first
        current_time = int(time.time())
        if current_time > expires:
            logger.debug(
                "Signed URL expired",
                extra={
                    "event_id": event_id,
                    "expired_at": expires,
                    "current_time": current_time,
                    "expired_seconds_ago": current_time - expires,
                }
            )
            return False

        # Verify signature
        expected_signature = self._create_signature(event_id, expires)

        # Use constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(signature, expected_signature)

        if not is_valid:
            logger.warning(
                "Invalid signed URL signature",
                extra={
                    "event_id": event_id,
                    "expires": expires,
                }
            )

        return is_valid

    def _create_signature(self, event_id: str, expires: int) -> str:
        """
        Create HMAC-SHA256 signature for event_id and expiration.

        Args:
            event_id: UUID of the event
            expires: Unix timestamp expiration

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        message = f"{event_id}:{expires}".encode("utf-8")
        signature = hmac.new(
            self._secret_key,
            message,
            hashlib.sha256
        ).hexdigest()
        return signature


# Global singleton instance
_signed_url_service: Optional[SignedURLService] = None


def get_signed_url_service() -> SignedURLService:
    """Get the global SignedURLService singleton instance."""
    global _signed_url_service
    if _signed_url_service is None:
        _signed_url_service = SignedURLService()
    return _signed_url_service


def reset_signed_url_service() -> None:
    """Reset the singleton instance (useful for testing)."""
    global _signed_url_service
    _signed_url_service = None
