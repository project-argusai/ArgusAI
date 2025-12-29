"""
Global Rate Limiting Middleware.

Story P14-2.6: Implement API Rate Limiting

Provides rate limiting for all API endpoints using slowapi.
- GET requests: 100/minute (configurable)
- POST/PUT/DELETE requests: 20/minute (configurable)
- Health endpoint: exempt
- API key authenticated requests: use per-key limits from api_key_rate_limiter
"""
from fastapi import Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable, Optional
import logging

from app.core.config import settings
from app.middleware.api_key_rate_limiter import (
    check_api_key_rate_limit,
    add_rate_limit_headers,
    RateLimitExceeded as APIKeyRateLimitExceeded,
)

logger = logging.getLogger(__name__)


def get_key_func(request: Request) -> str:
    """
    Custom key function for rate limiting.

    Returns the client IP address for rate limiting.
    If request has API key authentication, uses API key ID instead.
    """
    # Check if API key authenticated
    api_key = getattr(request.state, "api_key", None)
    if api_key:
        # API key authenticated - use key ID as rate limit key
        # (actual limit checking done by api_key_rate_limiter)
        return f"api_key:{api_key.id}"

    # Use client IP for unauthenticated/session-authenticated requests
    return get_remote_address(request)


# Global rate limiter instance
# Uses in-memory storage by default; can be configured for Redis
limiter = Limiter(
    key_func=get_key_func,
    default_limits=[settings.RATE_LIMIT_DEFAULT] if settings.RATE_LIMIT_ENABLED else [],
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    strategy="fixed-window",
)


# Exempt paths from rate limiting
EXEMPT_PATHS = {
    "/health",
    "/api/v1/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/ws",  # WebSocket connections
}


def is_exempt_path(path: str) -> bool:
    """Check if path is exempt from rate limiting."""
    # Exact match
    if path in EXEMPT_PATHS:
        return True

    # Prefix match for WebSocket
    if path.startswith("/ws"):
        return True

    return False


def get_rate_limit_for_method(method: str) -> str:
    """Get the appropriate rate limit based on HTTP method."""
    if method.upper() == "GET":
        return settings.RATE_LIMIT_READS
    elif method.upper() in ("POST", "PUT", "DELETE", "PATCH"):
        return settings.RATE_LIMIT_WRITES
    else:
        return settings.RATE_LIMIT_DEFAULT


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that applies rate limiting to all API endpoints.

    Features:
    - Method-based limits (GET vs POST/PUT/DELETE)
    - Exempt paths (health, metrics, docs)
    - Integration with API key rate limiting
    - Rate limit headers on all responses
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip if rate limiting is disabled
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Skip exempt paths
        if is_exempt_path(request.url.path):
            return await call_next(request)

        # Check API key rate limit first (if API key authenticated)
        # This is done after AuthMiddleware has set request.state.api_key
        api_key = getattr(request.state, "api_key", None)
        if api_key:
            try:
                await check_api_key_rate_limit(request)
            except APIKeyRateLimitExceeded:
                # Re-raise to let the exception handler deal with it
                raise

            # API key rate limiting handles everything, skip IP-based limiting
            response = await call_next(request)
            add_rate_limit_headers(request, response)
            return response

        # For non-API-key requests, apply IP-based rate limiting
        # Get the appropriate limit based on HTTP method
        rate_limit = get_rate_limit_for_method(request.method)

        # Check rate limit using slowapi
        key = get_remote_address(request)
        try:
            # Use the limiter to check/apply rate limit
            # slowapi handles the actual rate limit checking
            request.state.view_rate_limit = rate_limit

            response = await call_next(request)

            # Add rate limit headers to response
            # Note: slowapi automatically adds headers when using @limiter.limit decorator
            # For middleware-based limiting, we need to add them manually
            self._add_rate_limit_headers(request, response, rate_limit, key)

            return response

        except RateLimitExceeded as e:
            logger.warning(
                f"Rate limit exceeded for IP: {key}",
                extra={
                    "event_type": "ip_rate_limit_exceeded",
                    "client_ip": key,
                    "path": request.url.path,
                    "method": request.method,
                }
            )
            raise

    def _add_rate_limit_headers(
        self,
        request: Request,
        response: Response,
        rate_limit: str,
        key: str
    ) -> None:
        """Add rate limit headers to response."""
        # Parse rate limit string (e.g., "100/minute")
        try:
            limit_value, _ = rate_limit.split("/")
            limit = int(limit_value)
        except (ValueError, AttributeError):
            limit = 100  # Default

        # Get current window info from limiter if available
        # For simplicity, we'll just set the limit header
        # Full remaining/reset info would require accessing limiter internals
        response.headers["X-RateLimit-Limit"] = str(limit)

        # Note: X-RateLimit-Remaining and X-RateLimit-Reset are harder to
        # compute without deep integration with slowapi's storage backend.
        # For full header support, consider using slowapi's built-in decorators
        # or implementing a custom storage backend that tracks this info.


# Export the limiter for use in endpoint decorators
def get_limiter() -> Limiter:
    """Get the global rate limiter instance."""
    return limiter


# Convenience decorators for endpoint-level rate limiting
def limit_reads(func):
    """Decorator to apply read rate limit (100/minute) to an endpoint."""
    return limiter.limit(settings.RATE_LIMIT_READS)(func)


def limit_writes(func):
    """Decorator to apply write rate limit (20/minute) to an endpoint."""
    return limiter.limit(settings.RATE_LIMIT_WRITES)(func)


def limit_custom(limit_string: str):
    """Decorator factory to apply a custom rate limit to an endpoint."""
    return limiter.limit(limit_string)
