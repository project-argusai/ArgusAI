"""
Device Last Seen Middleware (Story P12-2.4)

Updates the last_seen_at timestamp for mobile devices on API requests.
This enables device lifecycle tracking and inactive device detection.

The middleware:
- Extracts device_id from X-Device-ID header
- Updates last_seen_at asynchronously to avoid blocking
- Only updates if device exists and user is authenticated
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.database import get_db_session
from app.models.device import Device

logger = logging.getLogger(__name__)


class LastSeenMiddleware(BaseHTTPMiddleware):
    """
    Middleware that tracks device activity by updating last_seen_at.

    For each request with X-Device-ID header:
    1. Check if user is authenticated (via request.state.user)
    2. Extract device_id from header
    3. Asynchronously update last_seen_at
    """

    # Paths excluded from last_seen tracking (high-frequency or public)
    EXCLUDED_PATHS = {
        '/health',
        '/metrics',
        '/ws',
    }

    EXCLUDED_PREFIXES = (
        '/api/v1/auth/',
        '/api/v1/thumbnails/',
        '/api/v1/events/',  # Exclude event frames for performance
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Process the request first
        response = await call_next(request)

        # Only track if successful response
        if response.status_code >= 400:
            return response

        # Check if path should be tracked
        path = request.url.path
        if self._is_excluded(path):
            return response

        # Check for device header
        device_id = request.headers.get("X-Device-ID")
        if not device_id:
            return response

        # Check if user is authenticated
        user_info = getattr(request.state, 'user', None)
        if not user_info:
            return response

        user_id = user_info.get('id')
        if not user_id:
            return response

        # Update last_seen asynchronously (fire and forget)
        asyncio.create_task(
            self._update_last_seen(device_id, user_id)
        )

        return response

    def _is_excluded(self, path: str) -> bool:
        """Check if path should be excluded from tracking."""
        if path in self.EXCLUDED_PATHS:
            return True

        for prefix in self.EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return True

        return False

    async def _update_last_seen(self, device_id: str, user_id: str) -> None:
        """
        Update device last_seen_at timestamp.

        Runs asynchronously to avoid blocking the main request.
        Uses a separate database session for isolation.
        """
        try:
            with get_db_session() as db:
                device = db.query(Device).filter(
                    Device.device_id == device_id,
                    Device.user_id == user_id
                ).first()

                if device:
                    device.last_seen_at = datetime.now(timezone.utc)
                    db.commit()

                    logger.debug(
                        "Device last_seen updated",
                        extra={
                            "device_id": device_id,
                            "user_id": user_id,
                        }
                    )

        except Exception as e:
            # Don't let tracking failures affect the request
            logger.warning(
                f"Failed to update device last_seen: {e}",
                extra={
                    "device_id": device_id,
                    "user_id": user_id,
                    "error": str(e),
                }
            )
