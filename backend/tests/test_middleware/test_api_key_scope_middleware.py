"""API-key scope decisions at the middleware boundary.

JWT and cookie sessions are not subject to this allowlist. Invalid, revoked,
and expired keys all fail ``verify_key`` and must not reach a handler.
"""

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.auth_middleware import AuthMiddleware

pytestmark = pytest.mark.real_auth_middleware

PROTECTED_ROUTES = (
    ("GET", "/api/v1/events/export"),
    ("DELETE", "/api/v1/events/bulk"),
    ("DELETE", "/api/v1/events/cleanup"),
    ("DELETE", "/api/v1/events/id-123"),
    ("GET", "/api/v1/cameras"),
    ("GET", "/api/v1/cameras/id-123/preview"),
    ("POST", "/api/v1/cameras"),
    ("POST", "/api/v1/cameras/discover"),
    ("POST", "/api/v1/cameras/id-123/analyze"),
    ("GET", "/api/v1/thumbnails/2026-09-23/a.jpg"),
    ("DELETE", "/api/v1/system/data"),
    ("GET", "/api/v1/users"),
    ("POST", "/api/v1/api-keys"),
    ("GET", "/api/v1/motion-events/export"),
    ("POST", "/api/v1/context/embeddings/batch"),
)

# scope -> routes that must reach the handler. Every other protected route is 403.
ADMITTED = {
    "read:events": {
        ("GET", "/api/v1/events/export"),
        ("GET", "/api/v1/thumbnails/2026-09-23/a.jpg"),
    },
    "read:cameras": {
        ("GET", "/api/v1/cameras"),
        ("GET", "/api/v1/cameras/id-123/preview"),
    },
    "write:cameras": {
        ("POST", "/api/v1/cameras"),
    },
    "admin": {
        ("GET", "/api/v1/events/export"),
        ("DELETE", "/api/v1/events/bulk"),
        ("DELETE", "/api/v1/events/cleanup"),
        ("DELETE", "/api/v1/events/id-123"),
        ("GET", "/api/v1/cameras"),
        ("GET", "/api/v1/cameras/id-123/preview"),
        ("POST", "/api/v1/cameras"),
        ("GET", "/api/v1/thumbnails/2026-09-23/a.jpg"),
    },
}


class _Key:
    def __init__(self, scopes):
        self.id = "key-1"
        self.name = "integration"
        self.scopes = scopes


def _install_key_service(monkeypatch, verify):
    class _Service:
        def verify_key(self, db, plaintext):
            return verify(plaintext)

        def record_usage(self, db, api_key, ip_address=None):
            return None

    @contextmanager
    def _db():
        yield object()

    monkeypatch.setattr(
        "app.services.service_container.get_api_key_service", lambda: _Service()
    )
    monkeypatch.setattr("app.middleware.auth_middleware.get_db_session", _db)


def _app():
    entered = []
    app = FastAPI()

    for method, path in PROTECTED_ROUTES:
        def handler(method=method, path=path):
            entered.append((method, path))
            return {"reached": True, "method": method, "path": path}

        app.add_api_route(path, handler, methods=[method])

    app.add_middleware(AuthMiddleware)
    return app, entered


@pytest.mark.parametrize("scopes", ["read:events", "read:cameras", "write:cameras", "admin", []])
def test_api_key_reaches_only_allowlisted_routes_for_its_scope(monkeypatch, scopes):
    scope_list = scopes if isinstance(scopes, list) else [scopes]
    admitted = set() if isinstance(scopes, list) else ADMITTED[scopes]

    def verify(plaintext):
        assert plaintext == "argus_validvalid"
        return _Key(scope_list)

    _install_key_service(monkeypatch, verify)
    app, entered = _app()
    client = TestClient(app)

    for method, path in PROTECTED_ROUTES:
        entered.clear()
        response = client.request(method, path, headers={"X-API-Key": "argus_validvalid"})
        if (method, path) in admitted:
            assert response.status_code == 200, (method, path, response.json())
            assert entered == [(method, path)]
        else:
            assert response.status_code == 403, (method, path, response.status_code)
            assert response.json() == {"detail": "API key not permitted for this endpoint"}
            assert entered == []


@pytest.mark.parametrize("plaintext", ["argus_invalid", "argus_revoked", "argus_expired"])
def test_invalid_revoked_and_expired_keys_do_not_reach_handlers(monkeypatch, plaintext):
    """verify_key returns None for unknown, revoked, and expired keys."""

    def verify(presented):
        assert presented == plaintext
        return None

    _install_key_service(monkeypatch, verify)
    app, entered = _app()
    client = TestClient(app)

    for method, path in PROTECTED_ROUTES:
        entered.clear()
        response = client.request(method, path, headers={"X-API-Key": plaintext})
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"
        assert entered == []


def test_valid_key_does_not_fall_through_to_a_jwt_session(monkeypatch):
    def verify(plaintext):
        return _Key(["read:events"])

    _install_key_service(monkeypatch, verify)
    monkeypatch.setattr(
        "app.middleware.auth_middleware.decode_access_token",
        lambda token: {"user_id": "user-1"},
    )
    app, entered = _app()
    client = TestClient(app)
    response = client.request(
        "DELETE",
        "/api/v1/system/data",
        headers={"X-API-Key": "argus_validvalid", "Authorization": "Bearer session"},
    )
    assert response.status_code == 403
    assert entered == []


def test_jwt_and_cookie_sessions_skip_the_api_key_allowlist(monkeypatch):
    class _User:
        id = "user-1"
        username = "ada"
        is_active = True

    class _Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return _User()

    class _DB:
        def query(self, model):
            return _Query()

    @contextmanager
    def _db():
        yield _DB()

    monkeypatch.setattr("app.middleware.auth_middleware.get_db_session", _db)
    monkeypatch.setattr(
        "app.middleware.auth_middleware.decode_access_token",
        lambda token: {"user_id": "user-1"},
    )
    app, entered = _app()
    client = TestClient(app)

    bearer = client.request(
        "DELETE",
        "/api/v1/system/data",
        headers={"Authorization": "Bearer session-token"},
    )
    assert bearer.status_code == 200
    assert entered == [("DELETE", "/api/v1/system/data")]

    entered.clear()
    cookie = client.request(
        "POST",
        "/api/v1/api-keys",
        cookies={"access_token": "session-token"},
    )
    assert cookie.status_code == 200
    assert entered == [("POST", "/api/v1/api-keys")]
