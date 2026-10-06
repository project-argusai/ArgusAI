"""Short-lived signed thumbnail URLs for MCP results (issue #648).

The MCP connector never returns frames, clips, or base64 images. An event's
thumbnail is reachable only through an HMAC-SHA256 signed URL that expires
after ``MCP_THUMBNAIL_URL_TTL_SECONDS`` (default 10 minutes).

The signing key is derived from ``ENCRYPTION_KEY`` with a fixed label, so these
signatures cannot be replayed against the push-notification thumbnail route
(``SignedURLService``) and vice versa.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from app.core.config import settings

THUMBNAIL_ROUTE_PREFIX = "/mcp/thumbnails"
_KEY_LABEL = b"argusai-mcp-thumbnail-v1"
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{64}$")

# backend/data/thumbnails, the same directory the event routes serve from.
THUMBNAIL_DIR = Path(__file__).resolve().parents[3] / "data" / "thumbnails"


def _signing_key(secret: Optional[str] = None) -> bytes:
    material = (secret if secret is not None else settings.ENCRYPTION_KEY).encode("utf-8")
    return hmac.new(material, _KEY_LABEL, hashlib.sha256).digest()


def _signature(event_id: str, expires: int, secret: Optional[str] = None) -> str:
    message = f"{event_id}:{int(expires)}".encode("utf-8")
    return hmac.new(_signing_key(secret), message, hashlib.sha256).hexdigest()


def is_valid_event_id(event_id: str) -> bool:
    return bool(event_id) and bool(_EVENT_ID_RE.match(event_id))


def signed_thumbnail_path(
    event_id: str,
    *,
    ttl_seconds: Optional[int] = None,
    now: Optional[float] = None,
    secret: Optional[str] = None,
) -> str:
    """API path (no host) for a signed, expiring thumbnail URL."""
    ttl = int(ttl_seconds if ttl_seconds is not None else settings.MCP_THUMBNAIL_URL_TTL_SECONDS)
    expires = int(now if now is not None else time.time()) + ttl
    query = urlencode({"expires": str(expires), "sig": _signature(event_id, expires, secret)})
    return f"{settings.API_V1_PREFIX}{THUMBNAIL_ROUTE_PREFIX}/{event_id}?{query}"


def signed_thumbnail_url(event_id: str, *, base_url: Optional[str] = None, **kwargs) -> str:
    """Absolute URL when a public base URL is configured, otherwise the API path."""
    path = signed_thumbnail_path(event_id, **kwargs)
    base = base_url if base_url is not None else settings.MCP_PUBLIC_BASE_URL
    return f"{base.rstrip('/')}{path}" if base else path


def verify_thumbnail_signature(
    event_id: str,
    expires: int,
    signature: str,
    *,
    now: Optional[float] = None,
    secret: Optional[str] = None,
) -> bool:
    """Constant-time signature check plus expiry and lifetime bounds."""
    if not is_valid_event_id(event_id) or not signature or not _SIGNATURE_RE.match(signature):
        return False
    current = int(now if now is not None else time.time())
    if expires < current:
        return False
    # A link may not outlive the configured maximum lifetime (3600s ceiling).
    if expires - current > 3600:
        return False
    return hmac.compare_digest(signature, _signature(event_id, expires, secret))


def load_thumbnail_bytes(thumbnail_path: Optional[str], thumbnail_base64: Optional[str]) -> Optional[bytes]:
    """Thumbnail bytes from the database or the confined thumbnail directory."""
    if thumbnail_base64:
        data = thumbnail_base64
        if data.startswith("data:"):
            comma = data.find(",")
            data = data[comma + 1:] if comma > 0 else ""
        try:
            return base64.b64decode(data, validate=False) or None
        except (ValueError, TypeError):
            return None

    if not thumbnail_path:
        return None
    relative = thumbnail_path
    if relative.startswith("/api/v1/thumbnails/"):
        relative = relative[len("/api/v1/thumbnails/"):]
    relative = relative.lstrip("/\\")
    if not relative or ".." in Path(relative).parts:
        return None
    base = THUMBNAIL_DIR.resolve()
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return None
    try:
        return candidate.read_bytes()
    except OSError:
        return None
