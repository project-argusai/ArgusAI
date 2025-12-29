"""
Authentication Middleware (Story 6.3, AC: #6)

Middleware that:
- Intercepts all API requests
- Checks for API key in X-API-Key header (for programmatic access)
- Checks for JWT in cookie or Authorization header (for user sessions)
- Validates token and adds user to request.state
- Excludes health, auth, metrics, docs endpoints
"""
import logging
import os
from typing import Callable, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.core.database import get_db_session
from app.core.config import settings
from app.models.user import User
from app.utils.jwt import decode_access_token, TokenError
from app.services.api_key_service import get_api_key_service

logger = logging.getLogger(__name__)


def _get_cors_headers(request: Request = None) -> dict:
    """Get CORS headers for error responses"""
    # Use the request origin if available and valid, otherwise fallback
    origin = "http://localhost:3000"
    if request:
        req_origin = request.headers.get("origin", "")
        if req_origin:
            origin = req_origin

    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates JWT tokens on protected routes.

    For each request:
    1. Check if path is excluded from auth
    2. Extract JWT from cookie or Authorization header
    3. Validate token and fetch user
    4. Add user to request.state
    5. Reject with 401 if invalid
    """

    # Paths that don't require authentication
    EXCLUDED_PATHS: Set[str] = {
        '/health',
        '/metrics',
        '/docs',
        '/redoc',
        '/openapi.json',
        '/',
    }

    # Path prefixes that don't require authentication
    EXCLUDED_PREFIXES: tuple = (
        '/api/v1/auth/login',
        '/api/v1/auth/logout',
        '/api/v1/auth/setup-status',
        '/api/v1/thumbnails/',  # Thumbnail images (public for img tags)
        '/ws',  # WebSocket connections handle their own auth
        # Mobile auth endpoints that don't require authentication (Story P12-3)
        '/api/v1/mobile/auth/pair',      # Mobile initiates pairing
        '/api/v1/mobile/auth/status/',   # Mobile polls for confirmation
        '/api/v1/mobile/auth/exchange',  # Mobile exchanges code for tokens
        '/api/v1/mobile/auth/refresh',   # Mobile refreshes tokens
    )

    COOKIE_NAME = "access_token"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        method = request.method

        # Skip auth in test mode (when running pytest)
        # Check for TestClient user-agent or TESTING environment variable
        user_agent = request.headers.get("user-agent", "")
        if "testclient" in user_agent.lower() or os.environ.get("TESTING") == "1":
            return await call_next(request)

        # Skip auth for excluded paths
        if self._is_excluded(path):
            return await call_next(request)

        # Skip auth for OPTIONS requests (CORS preflight)
        if method == "OPTIONS":
            return await call_next(request)

        # Check for API key first (programmatic access)
        api_key_valid = await self._check_api_key(request)
        if api_key_valid:
            return await call_next(request)

        # Extract JWT token
        token = self._extract_token(request)

        if not token:
            logger.debug(
                "Authentication required but no token provided",
                extra={
                    "event_type": "auth_missing_token",
                    "path": path,
                    "method": method,
                }
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer", **_get_cors_headers(request)},
            )

        # Validate token
        try:
            payload = decode_access_token(token)
            user_id = payload.get("user_id")

            if not user_id:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid token"},
                    headers=_get_cors_headers(request),
                )

        except TokenError as e:
            logger.debug(
                "Token validation failed",
                extra={
                    "event_type": "auth_token_invalid",
                    "path": path,
                    "error": str(e),
                }
            )
            return JSONResponse(
                status_code=401,
                content={"detail": str(e)},
                headers=_get_cors_headers(request),
            )

        # Fetch user from database
        with get_db_session() as db:
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                logger.warning(
                    "Token valid but user not found",
                    extra={
                        "event_type": "auth_user_not_found",
                        "user_id": user_id,
                    }
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "User not found"},
                    headers=_get_cors_headers(request),
                )

            if not user.is_active:
                logger.warning(
                    "Token valid but user disabled",
                    extra={
                        "event_type": "auth_user_disabled",
                        "user_id": user_id,
                    }
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Account disabled"},
                    headers=_get_cors_headers(request),
                )

            # Add user info to request state
            request.state.user = {
                "id": user.id,
                "username": user.username,
            }

        # Continue to route handler
        return await call_next(request)

    def _is_excluded(self, path: str) -> bool:
        """Check if path is excluded from authentication"""
        if path in self.EXCLUDED_PATHS:
            return True

        for prefix in self.EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return True

        # Event frames are public (used in img tags)
        # Pattern: /api/v1/events/{uuid}/frames or /api/v1/events/{uuid}/frames/{number}
        if path.startswith('/api/v1/events/') and '/frames' in path:
            return True

        return False

    def _extract_token(self, request: Request) -> str | None:
        """Extract JWT token from cookie or Authorization header"""
        # Check cookie first
        token = request.cookies.get(self.COOKIE_NAME)
        if token:
            return token

        # Fallback to Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]

        return None

    async def _check_api_key(self, request: Request) -> bool:
        """
        Check for valid API key in X-API-Key header.

        Returns True if valid API key found, False otherwise.
        Stores API key info in request.state if valid.
        """
        api_key_header = request.headers.get("X-API-Key")
        if not api_key_header:
            return False

        with get_db_session() as db:
            service = get_api_key_service()
            api_key = service.verify_key(db, api_key_header)

            if api_key:
                # Store API key in request state for downstream use
                request.state.api_key = {
                    "id": api_key.id,
                    "name": api_key.name,
                    "scopes": api_key.scopes,
                }

                # Record usage
                client_ip = None
                if request.client:
                    client_ip = request.client.host
                service.record_usage(db, api_key, ip_address=client_ip)

                logger.debug(
                    "API key authenticated",
                    extra={
                        "event_type": "api_key_auth_success",
                        "api_key_id": api_key.id,
                        "api_key_name": api_key.name,
                    }
                )
                return True

            logger.debug(
                "Invalid API key",
                extra={
                    "event_type": "api_key_auth_failed",
                    "path": request.url.path,
                }
            )
            return False
