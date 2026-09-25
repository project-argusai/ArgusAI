"""Every mounted route is allowlisted with a scope or denied to API keys."""

from app.core.api_key_scopes import API_KEY_ROUTE_SCOPES, required_api_key_scope
from app.core.config import settings
from app.schemas.api_key import VALID_SCOPES
from main import app


def _join(prefix: str, path: str) -> str:
    prefix = (prefix or "").rstrip("/")
    path = path or ""
    if path and not path.startswith("/"):
        path = f"/{path}"
    if path in {"", "/"}:
        return prefix or "/"
    return f"{prefix}{path}" if prefix else path


def _iter_routes(routes, prefix=""):
    """Yield mounted routes, expanding FastAPI's lazy included routers."""
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            include_prefix = route.include_context.prefix or ""
            yield from _iter_routes(
                route.original_router.routes, _join(prefix, include_prefix)
            )
            continue
        path = getattr(route, "path", None)
        if not path:
            continue
        yield route, _join(prefix, path)


def _fill(path: str) -> str:
    parts = []
    for segment in path.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append("id-123")
        else:
            parts.append(segment)
    return "/".join(parts)


def _relative(path: str) -> str | None:
    prefix = settings.API_V1_PREFIX.rstrip("/")
    if path == prefix:
        return "/"
    if not path.startswith(f"{prefix}/"):
        return None
    return path[len(prefix):]


def test_allowlisted_scopes_are_issued_scope_names():
    assert set(API_KEY_ROUTE_SCOPES.values()) <= VALID_SCOPES


def test_every_mounted_route_is_allowlisted_or_denied():
    """Fail when a new route is mounted without an explicit scope decision.

    Allowlisted routes must appear in ``API_KEY_ROUTE_SCOPES`` with the scope
    the middleware enforces. Every other HTTP route must produce no scope, so
    a valid API key is denied. WebSocket routes are not API-key routes.
    """
    mismatches = []
    mounted_templates = set()
    http_routes = 0

    for route, path in _iter_routes(app.routes):
        concrete = _fill(path)
        if type(route).__name__ in {"WebSocketRoute", "APIWebSocketRoute"}:
            for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                scope = required_api_key_scope(method, concrete)
                if scope is not None:
                    mismatches.append(f"websocket {method} {path} allowed as {scope}")
            continue

        methods = getattr(route, "methods", None)
        if not methods:
            continue
        http_routes += 1
        relative = _relative(path)
        for method in sorted(methods):
            actual = required_api_key_scope(method, concrete)
            if method == "OPTIONS":
                if actual is not None:
                    mismatches.append(f"OPTIONS {path} -> {actual}")
                continue
            lookup = "GET" if method == "HEAD" else method
            expected = None if relative is None else API_KEY_ROUTE_SCOPES.get((lookup, relative))
            if method != "HEAD" and relative is not None:
                mounted_templates.add((lookup, relative))
            if actual != expected:
                mismatches.append(
                    f"{method} {path} expected {expected!r} but policy returned {actual!r}"
                )

    stale = sorted(set(API_KEY_ROUTE_SCOPES) - mounted_templates)
    if stale:
        mismatches.append(
            "allowlist entries are not mounted: "
            + ", ".join(f"{method} {template}" for method, template in stale)
        )

    assert http_routes >= 100, f"expected the full app route table, found {http_routes}"
    assert not mismatches, "\n".join(mismatches)


def test_event_batch_and_export_routes_have_explicit_scopes():
    assert API_KEY_ROUTE_SCOPES[("GET", "/events/export")] == "read:events"
    assert API_KEY_ROUTE_SCOPES[("DELETE", "/events/bulk")] == "admin"
    assert API_KEY_ROUTE_SCOPES[("DELETE", "/events/cleanup")] == "admin"
    for method, path in (
        ("GET", "/api/v1/motion-events/export"),
        ("GET", "/api/v1/webhooks/logs/export"),
        ("GET", "/api/v1/context/adjustments/export"),
        ("POST", "/api/v1/context/embeddings/batch"),
        ("POST", "/api/v1/context/patterns/batch"),
    ):
        assert required_api_key_scope(method, path) is None
