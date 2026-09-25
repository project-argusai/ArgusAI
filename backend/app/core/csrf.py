"""Origin policy for cookie-authenticated state changes."""

from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit


UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SESSION_COOKIES = frozenset({"access_token", "refresh_token"})

# No path is exempt. A session cookie on an unsafe method always requires a
# trusted Origin, or a trusted Referer when Origin is absent. Non-browser
# clients are unaffected because they do not send these cookies:
#   POST /api/v1/mobile/auth/pair
#   POST /api/v1/mobile/auth/exchange
#   POST /api/v1/mobile/auth/refresh
#   Authorization: Bearer (iOS and other token clients)
#   X-API-Key
# ArgusAI does not expose an inbound webhook receiver. POST /api/v1/webhooks/test
# is a signed-in user action and stays covered. Login, logout, and refresh are
# excluded from the auth middleware but not from this check: when a session
# cookie is present they are rejected unless the Origin matches.
CSRF_EXEMPT_PATHS: frozenset[str] = frozenset()


def _origin_from_referer(referer: str) -> str | None:
    try:
        parsed = urlsplit(referer)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        # Accessing .port validates malformed ports before comparison.
        parsed.port
    except ValueError:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def cookie_write_origin_allowed(
    method: str,
    cookie_names: set[str],
    headers: Mapping[str, str],
    allowed_origins: Sequence[str],
) -> bool:
    """Check the Origin or Referer of a cookie-authenticated write.

    Bearer/API-key requests without a session cookie are unaffected. An Origin
    header takes precedence over Referer. Wildcards and null are never trusted.
    """
    if method.upper() not in UNSAFE_METHODS or not (cookie_names & SESSION_COOKIES):
        return True

    trusted = {origin.rstrip("/") for origin in allowed_origins if origin != "*"}
    origin = headers.get("origin")
    if origin is not None:
        return origin in trusted

    referer = headers.get("referer")
    return bool(referer and _origin_from_referer(referer) in trusted)
