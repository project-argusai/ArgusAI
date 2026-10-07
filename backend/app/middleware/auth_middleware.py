"""
Authentication Middleware (Story 6.3, AC: #6)

Middleware that:
- Intercepts all API requests
- Checks for API key in X-API-Key header (for programmatic access)
- Checks for JWT in cookie or Authorization header (for user sessions)
- Validates token and adds user to request.state
- Excludes health, auth, metrics, docs endpoints
"""
import asyncio
import logging
from typing import Callable, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.core.database import get_db_session
from app.core.config import settings
from app.core.api_key_scopes import api_key_allows, required_api_key_scope
from app.models.user import User
from app.utils.jwt import decode_access_token, TokenError
from app.services.service_container import container

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

    # Public HTTP paths: liveness/metrics and API documentation. These expose
    # no account data. The root path serves the API landing response.
    EXCLUDED_PATHS: Set[str] = {
        '/health',
        '/metrics',
        '/docs',
        '/redoc',
        '/openapi.json',
        '/',
        '/api/v1/auth/login',
        '/api/v1/auth/logout',
        '/api/v1/auth/refresh',
        '/api/v1/auth/setup-status',
        '/api/v1/mobile/auth/pair',
        '/api/v1/mobile/auth/exchange',
        '/api/v1/mobile/auth/refresh',
        '/ws',
    }

    # Public flows: login/logout/refresh and setup status must work before an
    # access token exists; mobile pairing/status/exchange/refresh have their
    # own one-time-code or refresh-token validation in the route handlers.
    # WebSocket upgrades are authenticated by their respective handlers.
    EXCLUDED_PREFIXES: tuple = (
        '/ws/',  # WebSocket connections handle their own auth
        # Mobile auth endpoints that don't require authentication (Story P12-3)
        '/api/v1/mobile/auth/status/',   # Mobile polls for confirmation
        # MCP thumbnail links (issue #648): the handler requires an unexpired
        # HMAC signature bound to one event id. /api/v1/mcp itself stays
        # authenticated.
        '/api/v1/mcp/thumbnails/',
    )

    # The MCP connector also accepts an API key as ``Authorization: Bearer
    # argus_...`` because many MCP clients can only send a bearer token. JWTs
    # never start with the ``argus_`` key prefix.
    MCP_BEARER_PATHS: Set[str] = {'/api/v1/mcp'}
    API_KEY_BEARER_PREFIX = "argus_"

    # Only the camera WebSocket upgrade skips HTTP auth. /ws/stream/{id} is
    # already covered by EXCLUDED_PREFIXES. HTTP routes such as
    # /cameras/{id}/stream/snapshot stay authenticated.

    COOKIE_NAME = "access_token"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        method = request.method

        # Skip auth for excluded paths
        if self._is_excluded(path):
            return await call_next(request)

        # Skip auth for OPTIONS requests (CORS preflight)
        if method == "OPTIONS":
            return await call_next(request)

        # Check for API key first (programmatic access)
        api_key_valid = await self._check_api_key(request)
        if api_key_valid:
            required_scope = required_api_key_scope(
                method, path, settings.API_V1_PREFIX
            )
            key_info = request.state.api_key
            scopes = key_info.get("scopes") or []
            if not api_key_allows(scopes, required_scope):
                logger.warning(
                    "API key denied by route scope policy",
                    extra={
                        "event_type": "api_key_scope_denied",
                        "api_key_id": key_info["id"],
                        "path": path,
                        "method": method,
                        "required_scope": required_scope,
                    },
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "API key not permitted for this endpoint"},
                    headers=_get_cors_headers(request),
                )
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

        # Pool checkout must not run on the event loop. A full pool waits on
        # a threading lock for pool_timeout seconds; doing that here froze
        # every other request, including /health.
        user_info = await asyncio.to_thread(_load_session_user, user_id)
        if user_info is None:
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

        if user_info is False:
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

        request.state.user = user_info

        # Continue to route handler
        return await call_next(request)

    def _is_excluded(self, path: str) -> bool:
        """Check if path is excluded from authentication"""
        if path in self.EXCLUDED_PATHS:
            return True

        for prefix in self.EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return True

        path_only = path.split('?')[0] if '?' in path else path
        return self._is_camera_websocket_stream(path_only)

    def _is_camera_websocket_stream(self, path: str) -> bool:
        """True only for /api/v1/cameras/{camera_id}/stream.

        A suffix of ``/stream`` would also skip auth for any future HTTP route
        that happened to end the same way. The camera id is a single segment.
        """
        prefix = f"{settings.API_V1_PREFIX.rstrip('/')}/cameras/"
        suffix = "/stream"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return False
        camera_id = path[len(prefix):-len(suffix)]
        return bool(camera_id) and "/" not in camera_id and camera_id not in {".", ".."}

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
            api_key_header = self._mcp_bearer_key(request)
        if not api_key_header:
            return False

        client_ip = request.client.host if request.client else None
        key_info = await asyncio.to_thread(
            _load_api_key, api_key_header, client_ip
        )
        if key_info:
            request.state.api_key = key_info
            logger.debug(
                "API key authenticated",
                extra={
                    "event_type": "api_key_auth_success",
                    "api_key_id": key_info["id"],
                    "api_key_name": key_info["name"],
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


    def _mcp_bearer_key(self, request: Request) -> Optional[str]:
        """API key sent as a bearer token, accepted on the MCP path only."""
        if request.url.path not in self.MCP_BEARER_PATHS:
            return None
        auth_header = request.headers.get("Authorization") or ""
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:].strip()
        return token if token.startswith(self.API_KEY_BEARER_PREFIX) else None


def _load_session_user(user_id: str) -> Optional[dict | bool]:
    """Load the session user off the event loop.

    Returns a plain dict, False when the account is disabled, or None when
    the user row is missing. The session is closed before return.
    """
    with get_db_session() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            return None
        if not user.is_active:
            return False
        return {"id": user.id, "username": user.username}


def _load_api_key(raw_key: str, client_ip: Optional[str]) -> Optional[dict]:
    """Verify an API key and record usage. Connection is closed before return."""
    with get_db_session() as db:
        service = container.api_key_service
        api_key = service.verify_key(db, raw_key)
        if not api_key:
            return None
        scopes = api_key.scopes
        if isinstance(scopes, list):
            scopes = list(scopes)
        info = {
            "id": api_key.id,
            "name": api_key.name,
            "scopes": scopes,
            "prefix": getattr(api_key, "prefix", None),
            "rate_limit_per_minute": getattr(api_key, "rate_limit_per_minute", None),
        }
        service.record_usage(db, api_key, ip_address=client_ip)
        return info
