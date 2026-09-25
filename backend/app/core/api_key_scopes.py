"""Default-deny route policy for machine API keys.

Only the routes in ``API_KEY_ROUTE_SCOPES`` accept an API key. Every other
mounted route is denied, including routes added later, until this table is
updated. ``admin`` satisfies the scope of an allowlisted route and never
bypasses the allowlist.

User sessions are authorized separately by role dependencies. This module
does not grant or remove JWT access.

Event mutations use ``admin`` because no ``write:events`` scope exists.
Camera connection tests, analysis, and ONVIF discovery scans stay off the
allowlist. Batch and export routes outside the event API (motion events,
webhook logs, context adjustments, embedding batches) stay denied.
"""

from types import MappingProxyType

# (HTTP method, path template relative to the API prefix) -> required scope.
# Path parameters use the same ``{name}`` spellings as the mounted routes.
_API_KEY_ROUTE_SCOPE_ITEMS: dict[tuple[str, str], str] = {
    # Events — reads, including export and media.
    ("GET", "/events"): "read:events",
    ("GET", "/events/packages/today"): "read:events",
    ("GET", "/events/export"): "read:events",
    ("GET", "/events/reprocess-entities"): "read:events",
    ("GET", "/events/stats/aggregate"): "read:events",
    ("GET", "/events/{event_id}"): "read:events",
    ("GET", "/events/{event_id}/query-suggestions"): "read:events",
    ("GET", "/events/{event_id}/feedback"): "read:events",
    ("GET", "/events/{event_id}/frames"): "read:events",
    ("GET", "/events/{event_id}/frames/{frame_number}"): "read:events",
    ("GET", "/events/{event_id}/video"): "read:events",
    ("GET", "/events/{event_id}/video/download"): "read:events",
    ("GET", "/events/{event_id}/thumbnail"): "read:events",
    # Event list responses point at this file route, not the signed thumbnail.
    ("GET", "/thumbnails/{date}/{filename}"): "read:events",

    # Events — writes and deletes. No write:events scope exists.
    ("POST", "/events"): "admin",
    ("POST", "/events/reprocess-entities"): "admin",
    ("POST", "/events/reprocess-entities/estimate"): "admin",
    ("DELETE", "/events/reprocess-entities"): "admin",
    ("DELETE", "/events/cleanup"): "admin",
    ("DELETE", "/events/bulk"): "admin",
    ("POST", "/events/media-orphans/reconcile"): "admin",
    ("DELETE", "/events/{event_id}"): "admin",
    ("POST", "/events/{event_id}/reanalyze"): "admin",
    ("POST", "/events/{event_id}/smart-reanalyze"): "admin",
    ("POST", "/events/{event_id}/feedback"): "admin",
    ("PUT", "/events/{event_id}/feedback"): "admin",
    ("DELETE", "/events/{event_id}/feedback"): "admin",

    # Cameras — reads, including discovery availability checks.
    ("GET", "/cameras"): "read:cameras",
    ("GET", "/cameras/health"): "read:cameras",
    ("GET", "/cameras/stream/metrics"): "read:cameras",
    ("GET", "/cameras/discover/status"): "read:cameras",
    ("GET", "/cameras/discover/device/status"): "read:cameras",
    ("GET", "/cameras/{camera_id}"): "read:cameras",
    ("GET", "/cameras/{camera_id}/motion/config"): "read:cameras",
    ("GET", "/cameras/{camera_id}/zones"): "read:cameras",
    ("GET", "/cameras/{camera_id}/schedule"): "read:cameras",
    ("GET", "/cameras/{camera_id}/schedule/status"): "read:cameras",
    ("GET", "/cameras/{camera_id}/preview"): "read:cameras",
    ("GET", "/cameras/{camera_id}/audio/status"): "read:cameras",
    ("GET", "/cameras/{camera_id}/stream/info"): "read:cameras",
    ("GET", "/cameras/{camera_id}/stream/snapshot"): "read:cameras",

    # Cameras — create, update, delete, and capture/motion/zone/schedule/audio.
    ("POST", "/cameras"): "write:cameras",
    ("PUT", "/cameras/{camera_id}"): "write:cameras",
    ("DELETE", "/cameras/{camera_id}"): "write:cameras",
    ("POST", "/cameras/{camera_id}/reconnect"): "write:cameras",
    ("POST", "/cameras/{camera_id}/enable-capture"): "write:cameras",
    ("POST", "/cameras/{camera_id}/disable-capture"): "write:cameras",
    ("PUT", "/cameras/{camera_id}/motion/config"): "write:cameras",
    ("PUT", "/cameras/{camera_id}/zones"): "write:cameras",
    ("PUT", "/cameras/{camera_id}/schedule"): "write:cameras",
    ("PATCH", "/cameras/{camera_id}/audio"): "write:cameras",
}

API_KEY_ROUTE_SCOPES = MappingProxyType(_API_KEY_ROUTE_SCOPE_ITEMS)


def required_api_key_scope(method: str, path: str, prefix: str = "/api/v1") -> str | None:
    """Return the scope needed for an allowed route, or None to deny the key.

    ``HEAD`` uses the same scope as ``GET``. ``OPTIONS`` is not an API-key
    route. A static template wins over a parameterized one, so ``/events/export``
    does not inherit ``/events/{event_id}``.
    """
    method = method.upper()
    if method == "OPTIONS":
        return None
    if method == "HEAD":
        method = "GET"

    relative = _relative_path(path, prefix)
    if relative is None:
        return None

    segments = _segments(relative)
    if any(segment in {".", ".."} for segment in segments):
        return None

    best_literals = -1
    best_scope: str | None = None
    ambiguous = False
    for (route_method, template), scope in API_KEY_ROUTE_SCOPES.items():
        if route_method != method:
            continue
        literals = _literal_count(template, segments)
        if literals is None:
            continue
        if literals > best_literals:
            best_literals = literals
            best_scope = scope
            ambiguous = False
        elif literals == best_literals and scope != best_scope:
            ambiguous = True

    if ambiguous:
        return None
    return best_scope


def api_key_allows(scopes: list[str], required_scope: str | None) -> bool:
    """Admin keys may use allowlisted routes, but never bypass the allowlist."""
    return required_scope is not None and (
        "admin" in scopes or required_scope in scopes
    )


def _relative_path(path: str, prefix: str) -> str | None:
    api_prefix = prefix.rstrip("/")
    if path != api_prefix and not path.startswith(f"{api_prefix}/"):
        return None
    relative = path[len(api_prefix):] or "/"
    if len(relative) > 1 and relative.endswith("/"):
        relative = relative.rstrip("/")
    return relative


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def _literal_count(template: str, segments: list[str]) -> int | None:
    """Return how many static segments matched, or None when the template misses."""
    template_segments = _segments(template)
    if len(template_segments) != len(segments):
        return None
    literals = 0
    for expected, actual in zip(template_segments, segments):
        if expected.startswith("{") and expected.endswith("}") and len(expected) > 2:
            if not actual or actual in {".", ".."}:
                return None
            continue
        if expected != actual:
            return None
        literals += 1
    return literals
