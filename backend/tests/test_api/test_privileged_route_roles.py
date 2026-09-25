"""Regression coverage for the highest-risk system and API-key role checks."""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.real_user_roles

from main import app
from app.api.v1.auth import get_current_user
from app.models.user import UserRole


@pytest.fixture
def as_role():
    def set_role(role):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=f"{role.value}-user", username=f"{role.value}-user", role=role
        )

    yield set_role
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("role", [UserRole.VIEWER, UserRole.OPERATOR])
@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("put", "/api/v1/system/retention", {"json": {"retention_days": 7}}),
        ("get", "/api/v1/system/retention", {}),
        ("put", "/api/v1/system/settings", {"json": {}}),
        ("get", "/api/v1/system/settings", {}),
        ("post", "/api/v1/system/backup", {}),
        ("get", "/api/v1/system/backup/list", {}),
        ("get", "/api/v1/system/backup/missing/download", {}),
        ("post", "/api/v1/system/backup/validate", {"files": {"file": ("backup.zip", b"invalid")}}),
        ("post", "/api/v1/system/restore", {"files": {"file": ("backup.zip", b"invalid")}}),
        ("delete", "/api/v1/system/backup/missing", {}),
        ("delete", "/api/v1/system/data", {}),
        ("post", "/api/v1/api-keys", {"json": {"name": "escalation", "scopes": ["admin"]}}),
        ("get", "/api/v1/api-keys", {}),
    ],
)
def test_non_admin_cannot_reach_privileged_routes(api_client, as_role, role, method, path, kwargs):
    as_role(role)
    response = getattr(api_client, method)(path, **kwargs)
    assert response.status_code == 403


def test_denied_retention_write_leaves_policy_unchanged(api_client, as_role):
    as_role(UserRole.VIEWER)
    denied = api_client.put("/api/v1/system/retention", json={"retention_days": 7})
    assert denied.status_code == 403

    as_role(UserRole.ADMIN)
    response = api_client.get("/api/v1/system/retention")
    assert response.status_code == 200
    assert response.json()["retention_days"] == 30


def test_denied_admin_scope_key_was_not_created(api_client, as_role):
    as_role(UserRole.VIEWER)
    denied = api_client.post(
        "/api/v1/api-keys", json={"name": "escalation", "scopes": ["admin"]}
    )
    assert denied.status_code == 403

    as_role(UserRole.ADMIN)
    assert api_client.get("/api/v1/api-keys").json() == []


@pytest.mark.parametrize("path", ["/api/v1/system/retention", "/api/v1/api-keys"])
def test_anonymous_privileged_reads_are_rejected(api_client, path):
    app.dependency_overrides.pop(get_current_user, None)
    assert api_client.get(path).status_code == 401


def test_admin_can_access_api_key_management(api_client, as_role):
    as_role(UserRole.ADMIN)
    response = api_client.get("/api/v1/api-keys")
    assert response.status_code == 200
    assert response.json() == []


def test_admin_can_update_retention(api_client, as_role):
    as_role(UserRole.ADMIN)
    response = api_client.put("/api/v1/system/retention", json={"retention_days": 7})
    assert response.status_code == 200
    assert response.json()["retention_days"] == 7
