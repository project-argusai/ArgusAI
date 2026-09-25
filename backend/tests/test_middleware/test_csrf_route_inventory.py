"""Every cookie-authenticated unsafe route is covered by the Origin gate.

The middleware has no path exemption. Auth-middleware exclusions (login,
logout, refresh, mobile pairing) still pass through this gate when a session
cookie is present. Machine clients without access_token or refresh_token
cookies are not subject to the check.
"""

from fastapi.testclient import TestClient

from app.core.csrf import CSRF_EXEMPT_PATHS, UNSAFE_METHODS
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.csrf import CSRFMiddleware
from main import app


# Writes that non-browser clients perform without web session cookies.
# They stay covered when a cookie is also present; they are not path-exempt.
COOKIELESS_MACHINE_WRITES = {
    ("POST", "/api/v1/mobile/auth/pair"),
    ("POST", "/api/v1/mobile/auth/exchange"),
    ("POST", "/api/v1/mobile/auth/refresh"),
}

# Issue #596 called these out. All must be mounted and not exempt.
REQUIRED_COOKIE_WRITES = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/change-password"),
    ("DELETE", "/api/v1/auth/sessions"),
    ("DELETE", "/api/v1/auth/sessions/{session_id}"),
    ("POST", "/api/v1/homekit/enable"),
    ("POST", "/api/v1/homekit/disable"),
    ("POST", "/api/v1/cameras"),
    ("PUT", "/api/v1/cameras/{camera_id}"),
    ("DELETE", "/api/v1/cameras/{camera_id}"),
    ("POST", "/api/v1/events"),
    ("DELETE", "/api/v1/events/cleanup"),
    ("DELETE", "/api/v1/events/{event_id}"),
    ("PUT", "/api/v1/system/settings"),
    ("POST", "/api/v1/system/backup"),
    ("POST", "/api/v1/system/backup/validate"),
    ("POST", "/api/v1/system/restore"),
    ("PUT", "/api/v1/integrations/mqtt/config"),
    ("POST", "/api/v1/webhooks/test"),
}


def _join(prefix: str, path: str) -> str:
    prefix = (prefix or "").rstrip("/")
    path = path or ""
    if path and not path.startswith("/"):
        path = f"/{path}"
    if path in {"", "/"}:
        return prefix or "/"
    return f"{prefix}{path}" if prefix else path


def _iter_routes(routes, prefix=""):
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


def _unsafe_routes() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route, path in _iter_routes(app.routes):
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            if method in UNSAFE_METHODS:
                found.add((method, path))
    return found


def test_origin_gate_has_no_path_exemptions():
    assert CSRF_EXEMPT_PATHS == frozenset()
    assert CSRFMiddleware.exempt_paths == frozenset()
    installed = [
        middleware
        for middleware in app.user_middleware
        if middleware.cls is CSRFMiddleware
    ]
    assert len(installed) == 1
    assert "exempt_paths" not in installed[0].kwargs


def test_every_unsafe_route_is_covered_including_auth_exclusions():
    unsafe = _unsafe_routes()
    assert len(unsafe) >= 80
    exempt = {(method, path) for method, path in unsafe if path in CSRF_EXEMPT_PATHS}
    assert exempt == set()

    missing = REQUIRED_COOKIE_WRITES - unsafe
    assert not missing, f"required cookie writes are not mounted: {sorted(missing)}"

    auth_excluded_writes = {
        (method, path)
        for method, path in unsafe
        if path in AuthMiddleware.EXCLUDED_PATHS
        or any(path.startswith(prefix) for prefix in AuthMiddleware.EXCLUDED_PREFIXES)
    }
    # Login, logout, refresh, and mobile pairing are outside the auth middleware
    # but still inside the Origin gate.
    assert {
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/mobile/auth/pair"),
        ("POST", "/api/v1/mobile/auth/exchange"),
        ("POST", "/api/v1/mobile/auth/refresh"),
    } <= auth_excluded_writes
    assert COOKIELESS_MACHINE_WRITES <= unsafe
    assert COOKIELESS_MACHINE_WRITES.isdisjoint(
        {(method, path) for method, path in unsafe if path in CSRF_EXEMPT_PATHS}
    )

    webhook_writes = {item for item in unsafe if "/webhooks" in item[1]}
    assert webhook_writes == {("POST", "/api/v1/webhooks/test")}


def test_origin_gate_stays_outside_the_backup_upload_guard():
    """#626 registers the upload guard just before CSRF.

    Starlette runs the later add_middleware call first, so a request is
    authenticated, then Origin-checked, and only then size-capped.
    """
    names = [middleware.cls.__name__ for middleware in app.user_middleware]
    assert names.index("AuthMiddleware") < names.index("CSRFMiddleware")
    assert names.index("CSRFMiddleware") < names.index("BackupUploadGuard")


def test_cookie_backup_validate_and_restore_are_origin_rejected():
    """A hostile cookie write is 403 before the upload guard can return 413."""
    from app.services.backup_limits import upload_body_limit

    too_big = upload_body_limit() + 1
    paths = ("/api/v1/system/backup/validate", "/api/v1/system/restore")
    with TestClient(app) as client:
        for path in paths:
            response = client.post(
                path,
                content=b"",
                headers={
                    "Origin": "https://evil.example",
                    "Content-Length": str(too_big),
                    "Content-Type": "multipart/form-data; boundary=x",
                },
                cookies={"access_token": "session"},
            )
            assert response.status_code == 403, path
            assert response.json()["error_code"] == "CSRF_ORIGIN_DENIED"
            assert "Backup exceeds" not in response.text


def test_auth_excluded_login_with_cookie_and_bad_or_missing_origin_is_rejected():
    with TestClient(app) as client:
        hostile = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "secret"},
            cookies={"access_token": "session"},
            headers={"Origin": "https://evil.example"},
        )
        missing = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "secret"},
            cookies={"access_token": "session"},
        )
    assert hostile.status_code == 403
    assert hostile.json()["error_code"] == "CSRF_ORIGIN_DENIED"
    assert missing.status_code == 403
    assert missing.json()["error_code"] == "CSRF_ORIGIN_DENIED"


def test_cookieless_machine_and_api_key_requests_are_not_origin_blocked():
    """Hostile Origin is irrelevant when no session cookie is sent.

    Handlers may still fail for their own reasons (auth, validation, schema).
    Those failures must not be the Origin gate.
    """
    with TestClient(app, raise_server_exceptions=False) as client:
        responses = [
            client.post(
                "/api/v1/mobile/auth/pair",
                json={"device_id": "device-1", "platform": "ios"},
                headers={"Origin": "https://evil.example"},
            ),
            client.post(
                "/api/v1/homekit/disable",
                headers={
                    "Origin": "https://evil.example",
                    "X-API-Key": "not-a-session-cookie",
                },
            ),
            client.post(
                "/api/v1/homekit/disable",
                headers={
                    "Origin": "https://evil.example",
                    "Authorization": "Bearer not-a-cookie",
                },
            ),
        ]
    for response in responses:
        assert "CSRF_ORIGIN_DENIED" not in response.text
