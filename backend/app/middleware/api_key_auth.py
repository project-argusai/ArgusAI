"""
API Key Authentication Middleware.

Story P13-1.4: Implement API Key Authentication Middleware
Story P13-1.5: Implement API Key Rate Limiting

Provides authentication via API keys for external integrations.
API keys can be used in the X-API-Key header for programmatic access.
Includes integrated rate limiting per API key.
"""
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.core.database import get_db
from app.services.service_container import container
from app.models.api_key import APIKey
from app.middleware.api_key_rate_limiter import (
    get_rate_limiter,
    RateLimitExceeded,
)

logger = logging.getLogger(__name__)


class APIKeyAuth:
    """
    API Key authentication handler.

    Validates API keys from the X-API-Key header and enforces scope requirements.
    """

    HEADER_NAME = "X-API-Key"

    def __init__(self, required_scopes: Optional[list[str]] = None):
        """
        Initialize with optional required scopes.

        Args:
            required_scopes: List of scopes required for access.
                           If None, any valid key is accepted.
        """
        self.required_scopes = required_scopes or []

    async def __call__(
        self,
        request: Request,
        db: Session = Depends(get_db),
    ) -> APIKey:
        """
        Validate API key from request header.

        Args:
            request: FastAPI request
            db: Database session

        Returns:
            Validated APIKey model

        Raises:
            HTTPException: 401 if key is missing or invalid
            HTTPException: 403 if key lacks required scopes
        """
        # Get API key from header
        api_key_header = request.headers.get(self.HEADER_NAME)

        if not api_key_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Verify the key
        service = container.api_key_service
        api_key = service.verify_key(db, api_key_header)

        if not api_key:
            logger.warning(
                "Invalid API key attempt",
                extra={
                    "event_type": "api_key_auth_failed",
                    "reason": "invalid_key",
                    "ip_address": self._get_client_ip(request),
                }
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Check required scopes
        if self.required_scopes:
            missing_scopes = []
            for scope in self.required_scopes:
                if not api_key.has_scope(scope):
                    missing_scopes.append(scope)

            if missing_scopes:
                logger.warning(
                    "API key scope insufficient",
                    extra={
                        "event_type": "api_key_auth_failed",
                        "reason": "insufficient_scope",
                        "api_key_id": api_key.id,
                        "required_scopes": self.required_scopes,
                        "missing_scopes": missing_scopes,
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API key lacks required scopes: {', '.join(missing_scopes)}",
                )

        # Store API key in request state for use by other middleware/handlers
        request.state.api_key = api_key

        # Check rate limit (Story P13-1.5)
        rate_limiter = get_rate_limiter()
        allowed, limit, remaining, reset_at = rate_limiter.check_rate_limit(api_key)

        if not allowed:
            logger.warning(
                f"API key rate limit exceeded: {api_key.id}",
                extra={
                    "event_type": "api_key_rate_limit_exceeded",
                    "api_key_id": api_key.id,
                    "api_key_name": api_key.name,
                    "limit": limit,
                }
            )
            raise RateLimitExceeded(limit, 0, reset_at)

        # Store rate limit info in request state for response headers
        request.state.rate_limit_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(int(reset_at.timestamp())),
        }

        # Record usage
        client_ip = self._get_client_ip(request)
        service.record_usage(db, api_key, ip_address=client_ip)

        logger.debug(
            "API key authenticated",
            extra={
                "event_type": "api_key_auth_success",
                "api_key_id": api_key.id,
                "api_key_name": api_key.name,
                "scopes": api_key.scopes,
            }
        )

        return api_key

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, considering proxies."""
        # Check X-Forwarded-For header (for reverse proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()

        # Fall back to direct client IP
        if request.client:
            return request.client.host

        return "unknown"


# Pre-configured authentication dependencies for common use cases
def require_api_key(
    request: Request,
    db: Session = Depends(get_db),
) -> APIKey:
    """
    Dependency that requires any valid API key.

    Usage:
        @router.get("/endpoint")
        async def endpoint(api_key: APIKey = Depends(require_api_key)):
            ...
    """
    auth = APIKeyAuth()
    return auth.__call__.__wrapped__(auth, request, db)


def require_read_events_scope(
    request: Request,
    db: Session = Depends(get_db),
) -> APIKey:
    """Dependency that requires read:events scope."""
    auth = APIKeyAuth(required_scopes=["read:events"])
    return auth.__call__.__wrapped__(auth, request, db)


def require_read_cameras_scope(
    request: Request,
    db: Session = Depends(get_db),
) -> APIKey:
    """Dependency that requires read:cameras scope."""
    auth = APIKeyAuth(required_scopes=["read:cameras"])
    return auth.__call__.__wrapped__(auth, request, db)


def require_write_cameras_scope(
    request: Request,
    db: Session = Depends(get_db),
) -> APIKey:
    """Dependency that requires write:cameras scope."""
    auth = APIKeyAuth(required_scopes=["write:cameras"])
    return auth.__call__.__wrapped__(auth, request, db)


def require_admin_scope(
    request: Request,
    db: Session = Depends(get_db),
) -> APIKey:
    """Dependency that requires admin scope."""
    auth = APIKeyAuth(required_scopes=["admin"])
    return auth.__call__.__wrapped__(auth, request, db)


async def get_optional_api_key(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[APIKey]:
    """
    Get API key if present, but don't require it.

    Useful for endpoints that support both JWT and API key authentication.
    Includes rate limiting check.

    Returns:
        APIKey if valid key provided, None otherwise

    Raises:
        RateLimitExceeded: If rate limit exceeded for the API key
    """
    api_key_header = request.headers.get(APIKeyAuth.HEADER_NAME)

    if not api_key_header:
        return None

    service = container.api_key_service
    api_key = service.verify_key(db, api_key_header)

    if api_key:
        # Store in request state
        request.state.api_key = api_key

        # Check rate limit (Story P13-1.5)
        rate_limiter = get_rate_limiter()
        allowed, limit, remaining, reset_at = rate_limiter.check_rate_limit(api_key)

        if not allowed:
            logger.warning(
                f"API key rate limit exceeded: {api_key.id}",
                extra={
                    "event_type": "api_key_rate_limit_exceeded",
                    "api_key_id": api_key.id,
                    "api_key_name": api_key.name,
                    "limit": limit,
                }
            )
            raise RateLimitExceeded(limit, 0, reset_at)

        # Store rate limit info for response headers
        request.state.rate_limit_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(int(reset_at.timestamp())),
        }

        # Record usage
        client_ip = None
        if request.client:
            client_ip = request.client.host
        service.record_usage(db, api_key, ip_address=client_ip)

    return api_key
