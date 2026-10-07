"""Read-only MCP connector endpoint (issue #648).

``POST /api/v1/mcp`` speaks MCP Streamable HTTP (stateless, JSON responses)
through the official ``mcp`` SDK. ``GET /api/v1/mcp`` answers 405: the server
never opens a server-initiated SSE stream.

Authorization, in order:
1. ``AuthMiddleware`` verifies the API key (``X-API-Key`` header, or
   ``Authorization: Bearer argus_...`` on this path only) and applies the
   route allowlist, where this path requires ``read:mcp``.
2. This endpoint requires an API key principal (user sessions are refused),
   requires ``read:mcp``, and refuses any key that also holds ``admin`` or a
   ``write:`` scope.
3. A per-key rate limit (the lower of the key's own limit and
   ``MCP_RATE_LIMIT_PER_MINUTE``) is enforced before the JSON-RPC body is read.

``GET /api/v1/mcp/thumbnails/{event_id}`` serves one event thumbnail to a
holder of an unexpired HMAC-signed link minted by an MCP tool result.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Mapping, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from app.core.api_key_scopes import is_read_only_scope_set
from app.core.config import settings
from app.core.database import get_db_session
from app.middleware.api_key_rate_limiter import get_rate_limiter
from app.models.event import Event
from app.services.mcp_connector.server import PRINCIPAL_STATE_KEY, get_server
from app.services.mcp_connector.thumbnails import (
    is_valid_event_id,
    load_thumbnail_bytes,
    verify_thumbnail_signature,
)

logger = logging.getLogger(__name__)

# The SDK logs session start/stop at INFO for every stateless request. Our own
# audit and request logs already cover each call, so keep the SDK to warnings.
for _sdk_logger in ("mcp.server.streamable_http", "mcp.server.streamable_http_manager", "mcp.server.lowlevel.server"):
    logging.getLogger(_sdk_logger).setLevel(logging.WARNING)

MCP_SCOPE = "read:mcp"
MCP_PATH = f"{settings.API_V1_PREFIX}/mcp"

router = APIRouter(prefix="/mcp", tags=["MCP"])


def _header(scope: Scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            try:
                return value.decode("latin-1")
            except Exception:
                return None
    return None


def _client_ip(scope: Scope) -> Optional[str]:
    """Direct peer address (the proxy when behind the frontend or tunnel)."""
    client = scope.get("client")
    return str(client[0])[:45] if client else None


def _error(status_code: int, message: str, headers: Optional[dict] = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": message}, headers=headers)


def _authorize(scope: Scope) -> tuple[Optional[Mapping[str, Any]], Optional[JSONResponse]]:
    state = scope.get("state") or {}
    key = state.get("api_key")
    if not isinstance(key, Mapping) or not key.get("id"):
        return None, _error(
            status.HTTP_401_UNAUTHORIZED,
            "MCP requires a read-only API key (X-API-Key or Authorization: Bearer)",
            {"WWW-Authenticate": 'Bearer realm="argusai-mcp"'},
        )
    scopes = [str(s) for s in (key.get("scopes") or [])]
    if MCP_SCOPE not in scopes or not is_read_only_scope_set(scopes):
        logger.warning(
            "API key refused by MCP scope policy",
            extra={
                "event_type": "mcp_scope_denied",
                "api_key_id": key.get("id"),
                "has_mcp_scope": MCP_SCOPE in scopes,
                "read_only": is_read_only_scope_set(scopes),
            },
        )
        return None, _error(
            status.HTTP_403_FORBIDDEN,
            "MCP requires an API key with the read:mcp scope and no admin or write scopes",
        )
    return key, None


def _check_rate_limit(key: Mapping[str, Any]) -> Optional[JSONResponse]:
    ceiling = settings.MCP_RATE_LIMIT_PER_MINUTE
    try:
        key_limit = int(key.get("rate_limit_per_minute") or ceiling)
    except (TypeError, ValueError):
        key_limit = ceiling
    bucket = SimpleNamespace(id=f"mcp:{key['id']}", rate_limit_per_minute=max(1, min(key_limit, ceiling)))
    allowed, limit, _remaining, reset_at = get_rate_limiter().check_rate_limit(bucket)
    if allowed:
        return None
    retry_after = max(1, int((reset_at - datetime.now(timezone.utc)).total_seconds()))
    logger.warning(
        "MCP rate limit exceeded",
        extra={"event_type": "mcp_rate_limited", "api_key_id": key.get("id"), "limit": limit},
    )
    return _error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Rate limit exceeded ({limit}/minute)",
        {"Retry-After": str(retry_after), "X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"},
    )


class MCPEndpoint:
    """ASGI endpoint mounted at ``/api/v1/mcp``."""

    def __init__(self) -> None:
        self._security = TransportSecuritySettings(
            # Header-only API key auth; cookies are never accepted here, so
            # DNS rebinding cannot borrow a browser session. Host checks would
            # break the Cloudflare tunnel's public hostname.
            enable_dns_rebinding_protection=False,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await _error(status.HTTP_404_NOT_FOUND, "Not Found")(scope, receive, send)
            return
        if not settings.MCP_ENABLED:
            await _error(status.HTTP_404_NOT_FOUND, "MCP connector is disabled")(scope, receive, send)
            return

        key, denial = _authorize(scope)
        if denial is not None:
            await denial(scope, receive, send)
            return

        limited = _check_rate_limit(key)
        if limited is not None:
            await limited(scope, receive, send)
            return

        if scope.get("method") != "POST":
            # No server-initiated stream (spec: GET may answer 405).
            await _error(
                status.HTTP_405_METHOD_NOT_ALLOWED, "Method Not Allowed", {"Allow": "POST"}
            )(scope, receive, send)
            return

        user_agent = _header(scope, b"user-agent")
        scope.setdefault("state", {})[PRINCIPAL_STATE_KEY] = {
            "id": key.get("id"),
            "prefix": key.get("prefix"),
            "client_ip": _client_ip(scope),
            # Client-supplied header, kept for context only.
            "forwarded_for": (_header(scope, b"x-forwarded-for") or "")[:100] or None,
            "user_agent": user_agent[:200] if user_agent else None,
        }

        # Stateless: a fresh transport per request, so no lifespan hook or
        # session table is needed and nothing outlives the HTTP request.
        manager = StreamableHTTPSessionManager(
            app=get_server(),
            json_response=True,
            stateless=True,
            security_settings=self._security,
            max_request_body_size=256 * 1024,
        )
        async with manager.run():
            await manager.handle_request(scope, receive, send)


@router.get("/thumbnails/{event_id}", include_in_schema=False)
def get_mcp_thumbnail(
    event_id: str,
    expires: int = Query(..., ge=0, le=2**40),
    sig: str = Query(..., min_length=64, max_length=64),
) -> Response:
    """One event thumbnail for a holder of an unexpired signed link."""
    if not settings.MCP_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not is_valid_event_id(event_id) or not verify_thumbnail_signature(event_id, expires, sig):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired link")

    with get_db_session() as db:
        row = db.query(Event.thumbnail_path, Event.thumbnail_base64).filter(Event.id == event_id).first()
    data = load_thumbnail_bytes(row.thumbnail_path, row.thumbnail_base64) if row else None
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'inline; filename="thumbnail.jpg"',
        },
    )
