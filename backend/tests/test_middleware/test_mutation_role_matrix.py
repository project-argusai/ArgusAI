"""Every state-changing route enforces a session role.

The route list comes from the mounted app, so a new POST/PUT/PATCH/DELETE is
covered without editing this file. Self-service and public writes are an
explicit allowlist. Everything else is admin unless it is listed as operator.

Requests go through the production middleware stack (no auth bypass) with
bearer tokens. API-key scope behavior is asserted separately and is not a
user role.
"""

import re
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from app.core.database import Base, SessionLocal, engine, get_db
from app.models.user import User, UserRole
from app.utils.auth import hash_password
from app.utils.jwt import create_access_token

pytestmark = pytest.mark.real_auth_middleware

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Any authenticated role, or public auth flows that must stay callable
# without a role dependency.
SELF_SERVICE_ALLOWLIST = frozenset({
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/change-password"),
    ("DELETE", "/api/v1/auth/sessions"),
    ("DELETE", "/api/v1/auth/sessions/{session_id}"),
    ("POST", "/api/v1/mobile/auth/pair"),
    ("POST", "/api/v1/mobile/auth/exchange"),
    ("POST", "/api/v1/mobile/auth/refresh"),
    ("POST", "/api/v1/mobile/auth/confirm"),
    ("DELETE", "/api/v1/mobile/auth/pending/{code}"),
    ("POST", "/api/v1/mobile/auth/revoke"),
    ("POST", "/api/v1/devices"),
    ("PUT", "/api/v1/devices/{id}"),
    ("PUT", "/api/v1/devices/{device_id}/token"),
    ("PUT", "/api/v1/devices/{device_id}/preferences"),
    ("DELETE", "/api/v1/devices/{device_id}"),
    ("DELETE", "/api/v1/devices/inactive"),
    ("POST", "/api/v1/push/subscribe"),
    ("DELETE", "/api/v1/push/subscribe"),
    ("POST", "/api/v1/push/unsubscribe"),
    ("POST", "/api/v1/push/preferences"),
    ("PUT", "/api/v1/push/preferences"),
})

# Day-to-day actions. Viewer is denied. Operator passes the role check.
OPERATOR_ROUTES = frozenset({
    ("POST", "/api/v1/cameras/{camera_id}/analyze"),
    ("POST", "/api/v1/events/{event_id}/feedback"),
    ("PUT", "/api/v1/events/{event_id}/feedback"),
    ("DELETE", "/api/v1/events/{event_id}/feedback"),
    ("POST", "/api/v1/events/{event_id}/reanalyze"),
    ("POST", "/api/v1/events/{event_id}/smart-reanalyze"),
    ("POST", "/api/v1/summaries/generate"),
    ("POST", "/api/v1/summaries/{summary_id}/feedback"),
    ("PUT", "/api/v1/summaries/{summary_id}/feedback"),
    ("DELETE", "/api/v1/summaries/{summary_id}/feedback"),
    ("PATCH", "/api/v1/notifications/{notification_id}/read"),
    ("PATCH", "/api/v1/notifications/mark-all-read"),
    ("DELETE", "/api/v1/notifications/{notification_id}"),
    ("DELETE", "/api/v1/notifications"),
    ("PATCH", "/api/v1/system-notifications/{notification_id}/read"),
    ("PATCH", "/api/v1/system-notifications/{notification_id}/dismiss"),
    ("PATCH", "/api/v1/system-notifications/mark-all-read"),
    ("DELETE", "/api/v1/system-notifications/{notification_id}"),
    ("DELETE", "/api/v1/system-notifications"),
    ("POST", "/api/v1/context/entities"),
    ("POST", "/api/v1/context/entities/merge"),
    ("PUT", "/api/v1/context/entities/{entity_id}"),
    ("POST", "/api/v1/context/events/{event_id}/entity"),
    ("DELETE", "/api/v1/context/entities/{entity_id}/events/{event_id}"),
    ("PUT", "/api/v1/context/persons/{person_id}"),
    ("PUT", "/api/v1/context/vehicles/{vehicle_id}"),
    ("POST", "/api/v1/context/anomaly/score"),
    ("POST", "/api/v1/voice/query"),
})


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


def unsafe_routes() -> list[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route, path in _iter_routes(app.routes):
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            if method in UNSAFE_METHODS:
                found.add((method, path))
    return sorted(found)


GUARDED_ROUTES = [
    item for item in unsafe_routes() if item not in SELF_SERVICE_ALLOWLIST
]


def _permission_denied(response) -> bool:
    if response.status_code != 403:
        return False
    detail = response.json().get("detail")
    return isinstance(detail, dict) and detail.get("error_code") == "INSUFFICIENT_PERMISSIONS"


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "missing-id", path)


@pytest.fixture(scope="module")
def matrix_client():
    """Users in the app database, production middleware, bearer tokens."""
    Base.metadata.create_all(bind=engine)
    saved_get_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = get_db

    db = SessionLocal()
    tokens = {}
    user_ids = []
    try:
        for role in (UserRole.VIEWER, UserRole.OPERATOR, UserRole.ADMIN):
            user = User(
                id=str(uuid.uuid4()),
                username=f"role_matrix_{role.value}_{uuid.uuid4().hex[:8]}",
                password_hash=hash_password("RoleMatrix123!"),
                role=role,
                is_active=True,
            )
            db.add(user)
            db.commit()
            user_ids.append(user.id)
            tokens[role] = create_access_token(user.id, user.username)
        db.close()

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, tokens
    finally:
        db = SessionLocal()
        try:
            db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
        if saved_get_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = saved_get_db


@pytest.fixture(autouse=True)
def _avoid_side_effects(_reset_all_singletons):
    """Role checks must run. Handlers must not scan the network, start
    HomeKit, write a backup, reprocess embeddings, or delete media files.

    ``_reset_all_singletons`` runs first and drops cached services, so the
    stubs are applied to the instances this test will actually call.
    """
    import shutil
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.services.event_media_deletion import EventMediaDeletionService
    from app.services.service_container import container

    discovery = container.onvif_discovery_service
    original_discover = discovery.discover_cameras_with_result

    async def _quiet_discover(*args, **kwargs):
        return SimpleNamespace(status="completed", duration_ms=0, devices=[], error=None)

    discovery.discover_cameras_with_result = _quiet_discover

    homekit = container.homekit_service
    original_start = homekit.start
    homekit.start = AsyncMock(return_value=False)

    backup = container.backup_service
    original_create = backup.create_backup

    async def _quiet_backup(*args, **kwargs):
        return SimpleNamespace(
            success=False,
            message="role matrix test",
            timestamp="",
            size_bytes=0,
            download_url="",
            database_size_bytes=0,
            thumbnails_count=0,
            thumbnails_size_bytes=0,
            settings_count=0,
        )

    backup.create_backup = _quiet_backup

    tunnel = container.tunnel_service
    original_tunnel_start = tunnel.start
    original_tunnel_stop = tunnel.stop
    tunnel.start = AsyncMock(return_value=False)
    tunnel.stop = AsyncMock(return_value=False)

    reprocessing = container.reprocessing_service
    original_reprocess = reprocessing.start_reprocessing

    async def _quiet_reprocess(*args, **kwargs):
        raise ValueError("role matrix test does not start reprocessing")

    reprocessing.start_reprocessing = _quiet_reprocess

    original_reconcile = EventMediaDeletionService.reconcile_orphans

    def _quiet_reconcile(self, db, *, dry_run=True):
        return SimpleNamespace(
            skipped=True,
            dry_run=True,
            success=False,
            orphan_files=0,
            deleted_files=0,
            failed_files=0,
            skipped_symlinks=0,
            bytes=0,
            by_kind={},
            as_dict=lambda: {"skipped": True, "dry_run": True},
        )

    EventMediaDeletionService.reconcile_orphans = _quiet_reconcile

    original_rmtree = shutil.rmtree
    original_unlink = Path.unlink

    def _guarded_rmtree(path, *args, **kwargs):
        if "data" in str(path):
            return None
        return original_rmtree(path, *args, **kwargs)

    def _guarded_unlink(self, *args, **kwargs):
        if "data" in str(self):
            return None
        return original_unlink(self, *args, **kwargs)

    shutil.rmtree = _guarded_rmtree
    Path.unlink = _guarded_unlink

    yield

    discovery.discover_cameras_with_result = original_discover
    homekit.start = original_start
    backup.create_backup = original_create
    tunnel.start = original_tunnel_start
    tunnel.stop = original_tunnel_stop
    reprocessing.start_reprocessing = original_reprocess
    EventMediaDeletionService.reconcile_orphans = original_reconcile
    shutil.rmtree = original_rmtree
    Path.unlink = original_unlink


def test_role_matrix_does_not_override_the_principal():
    """This module uses the deployed middleware and the real role dependency."""
    from app.core.permissions import get_mutation_principal
    from app.api.v1.auth import get_current_user

    assert get_mutation_principal not in app.dependency_overrides
    assert get_current_user not in app.dependency_overrides


def test_allowlist_and_operator_routes_are_mounted():
    mounted = set(unsafe_routes())
    missing_allow = SELF_SERVICE_ALLOWLIST - mounted
    missing_operator = OPERATOR_ROUTES - mounted
    assert not missing_allow, sorted(missing_allow)
    assert not missing_operator, sorted(missing_operator)
    assert OPERATOR_ROUTES.isdisjoint(SELF_SERVICE_ALLOWLIST)
    assert len(GUARDED_ROUTES) >= 100


@pytest.mark.parametrize("method,path", GUARDED_ROUTES)
def test_session_role_on_state_changing_route(matrix_client, method, path):
    client, tokens = matrix_client
    url = _concrete(path)
    level = "operator" if (method, path) in OPERATOR_ROUTES else "admin"

    def call(role: UserRole):
        return client.request(
            method,
            url,
            headers={"Authorization": f"Bearer {tokens[role]}"},
            json={},
        )

    viewer = call(UserRole.VIEWER)
    operator = call(UserRole.OPERATOR)
    admin = call(UserRole.ADMIN)

    assert _permission_denied(viewer), (method, path, viewer.status_code, viewer.text[:300])
    assert not _permission_denied(admin), (method, path, admin.status_code, admin.text[:300])
    assert admin.status_code != 401, (method, path, admin.text[:300])

    if level == "admin":
        assert _permission_denied(operator), (method, path, operator.status_code, operator.text[:300])
    else:
        assert not _permission_denied(operator), (method, path, operator.status_code, operator.text[:300])
        assert operator.status_code != 401, (method, path, operator.text[:300])


@pytest.mark.parametrize("method,path", sorted(SELF_SERVICE_ALLOWLIST))
def test_self_service_routes_are_not_role_denied(matrix_client, method, path):
    client, tokens = matrix_client
    response = client.request(
        method,
        _concrete(path),
        headers={"Authorization": f"Bearer {tokens[UserRole.VIEWER]}"},
        json={},
    )
    assert not _permission_denied(response), (method, path, response.status_code, response.text[:300])


def test_cleanup_confirmation_is_unchanged_for_admin(matrix_client):
    """Admin passes the role check. The handler still refuses an unconfirmed delete."""
    client, tokens = matrix_client
    missing = client.request(
        "DELETE",
        "/api/v1/events/cleanup",
        headers={"Authorization": f"Bearer {tokens[UserRole.ADMIN]}"},
    )
    assert missing.status_code == 422

    unconfirmed = client.request(
        "DELETE",
        "/api/v1/events/cleanup",
        params={"before_date": "2000-01-01", "confirm": "false"},
        headers={"Authorization": f"Bearer {tokens[UserRole.ADMIN]}"},
    )
    assert unconfirmed.status_code == 400
    assert not _permission_denied(unconfirmed)


def test_cookie_session_uses_the_same_role_check(matrix_client):
    client, tokens = matrix_client
    origin = {"Origin": "http://localhost:3000"}
    viewer = client.post(
        "/api/v1/cameras",
        json={},
        cookies={"access_token": tokens[UserRole.VIEWER]},
        headers=origin,
    )
    assert _permission_denied(viewer)

    admin = client.post(
        "/api/v1/cameras",
        json={},
        cookies={"access_token": tokens[UserRole.ADMIN]},
        headers=origin,
    )
    assert not _permission_denied(admin)
    assert admin.status_code != 401


def test_api_key_scopes_are_unchanged_by_user_role_checks(matrix_client, monkeypatch):
    """A permitted key reaches the handler. A denied key is still the allowlist 403."""
    client, _tokens = matrix_client

    class _Key:
        def __init__(self, scopes):
            self.id = "role-matrix-key"
            self.name = "role-matrix"
            self.scopes = scopes

    def verify_key(_db, plaintext):
        scopes = {
            "argus_write_cameras": ["write:cameras"],
            "argus_read_events": ["read:events"],
            "argus_admin": ["admin"],
        }.get(plaintext)
        if scopes is None:
            return None
        return _Key(scopes)

    from app.services.service_container import container

    service = container.api_key_service
    monkeypatch.setattr(service, "verify_key", verify_key)
    monkeypatch.setattr(service, "record_usage", lambda *args, **kwargs: None)

    write_cameras = client.post(
        "/api/v1/cameras",
        json={},
        headers={"X-API-Key": "argus_write_cameras"},
    )
    assert write_cameras.status_code != 401
    assert not _permission_denied(write_cameras)

    read_events = client.post(
        "/api/v1/cameras",
        json={},
        headers={"X-API-Key": "argus_read_events"},
    )
    assert read_events.status_code == 403
    assert read_events.json()["detail"] == "API key not permitted for this endpoint"

    admin_key_delete = client.request(
        "DELETE",
        "/api/v1/events/missing-id",
        headers={"X-API-Key": "argus_admin"},
    )
    assert admin_key_delete.status_code != 401
    assert not _permission_denied(admin_key_delete)

    # System wipe is not on the API-key allowlist, including for an admin key.
    wipe = client.request(
        "DELETE",
        "/api/v1/system/data",
        headers={"X-API-Key": "argus_admin"},
    )
    assert wipe.status_code == 403
    assert wipe.json()["detail"] == "API key not permitted for this endpoint"
