"""Authentication must never trust caller-provided test identifiers."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.auth_middleware import AuthMiddleware


pytestmark = pytest.mark.real_auth_middleware


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/cameras"),
    ("POST", "/api/v1/cameras"),
    ("DELETE", "/api/v1/system/data"),
])
@pytest.mark.parametrize("user_agent", [
    "ordinary-browser",
    "testclient",
    "Mozilla/5.0 TeStClIeNt spoof",
])
def test_anonymous_requests_cannot_enter_protected_handlers(
    method, path, user_agent, monkeypatch
):
    # A misconfigured legacy TESTING variable must not weaken HTTP auth either.
    monkeypatch.setenv("TESTING", "1")
    entered = []
    app = FastAPI()

    @app.api_route(path, methods=[method])
    def protected_handler():
        entered.append(True)
        return {"reached": True}

    app.add_middleware(AuthMiddleware)
    response = TestClient(app).request(
        method, path, headers={"User-Agent": user_agent}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert entered == []


def test_documented_public_health_path_remains_available():
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True}

    app.add_middleware(AuthMiddleware)
    response = TestClient(app).get("/health")
    assert response.status_code == 200


@pytest.mark.parametrize("path", [
    "/api/v1/auth/login-extra",
    "/api/v1/mobile/auth/pair-extra",
    "/api/v1/mobile/auth/refresh-extra",
])
def test_public_endpoint_names_do_not_exclude_prefixed_paths(path):
    entered = []
    app = FastAPI()

    @app.get(path)
    def protected_handler():
        entered.append(True)
        return {"reached": True}

    app.add_middleware(AuthMiddleware)
    response = TestClient(app).get(path, headers={"User-Agent": "testclient"})
    assert response.status_code == 401
    assert entered == []
