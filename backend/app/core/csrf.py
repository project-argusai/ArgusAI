"""Origin policy for cookie-authenticated state changes."""

from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit


UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SESSION_COOKIES = frozenset({"access_token", "refresh_token"})


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
