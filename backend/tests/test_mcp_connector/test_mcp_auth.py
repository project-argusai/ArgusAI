"""Read-only enforcement, rate limiting, and transport rules (issue #648)."""
import pytest

from app.core.api_key_scopes import is_read_only_scope_set, required_api_key_scope
from app.core.config import settings
from app.schemas.api_key import VALID_SCOPES
from tests.test_mcp_connector.conftest import MCP_HEADERS, rpc

pytestmark = pytest.mark.real_auth_middleware


def test_scope_table_and_read_only_check():
    assert "read:mcp" in VALID_SCOPES
    assert required_api_key_scope("POST", "/api/v1/mcp") == "read:mcp"
    assert required_api_key_scope("GET", "/api/v1/mcp") == "read:mcp"
    assert required_api_key_scope("DELETE", "/api/v1/mcp") is None
    assert is_read_only_scope_set(["read:mcp", "read:events", "read:cameras"])
    assert not is_read_only_scope_set(["read:mcp", "admin"])
    assert not is_read_only_scope_set(["read:mcp", "write:cameras"])
    assert not is_read_only_scope_set(["read:mcp", "write:anything"])


def test_unauthenticated_request_is_rejected(client, seeded):
    response = rpc(client, None, "tools/list", {})
    assert response.status_code == 401


def test_invalid_key_is_rejected(client, seeded):
    response = rpc(client, "argus_notarealkeyvalue12345678901234", "tools/list", {})
    assert response.status_code == 401


def test_revoked_key_is_rejected(client, seeded, make_key):
    revoked = make_key(["read:mcp"], revoke=True)
    assert rpc(client, revoked["key"], "tools/list", {}).status_code == 401


def test_key_without_mcp_scope_is_rejected(client, seeded, make_key):
    key = make_key(["read:events", "read:cameras"])
    response = rpc(client, key["key"], "tools/list", {})
    assert response.status_code == 403


@pytest.mark.parametrize("scopes", [["admin"], ["read:mcp", "admin"], ["read:mcp", "write:cameras"]])
def test_write_or_admin_keys_are_refused(client, seeded, make_key, scopes):
    key = make_key(scopes)
    response = rpc(client, key["key"], "tools/list", {})
    assert response.status_code == 403
    assert "read:mcp" in response.json()["detail"]


def test_read_only_key_with_extra_read_scopes_is_allowed(client, seeded, make_key):
    key = make_key(["read:mcp", "read:events"])
    assert rpc(client, key["key"], "tools/list", {}).status_code == 200


def test_mcp_key_cannot_use_other_routes(client, seeded, mcp_key):
    response = client.get("/api/v1/events", headers={"X-API-Key": mcp_key["key"]})
    assert response.status_code == 403
    response = client.get("/api/v1/cameras", headers={"X-API-Key": mcp_key["key"]})
    assert response.status_code == 403


def test_bearer_api_key_works_on_mcp_only(client, seeded, mcp_key):
    response = rpc(client, mcp_key["key"], "tools/list", {}, auth="bearer")
    assert response.status_code == 200, response.text
    # Elsewhere a bearer token is a JWT; an API key there is not accepted.
    response = client.get("/api/v1/events", headers={"Authorization": f"Bearer {mcp_key['key']}"})
    assert response.status_code == 401


def test_user_session_cannot_use_mcp(client, seeded, mcp_db):
    from app.models.user import User, UserRole
    from app.utils.jwt import create_access_token

    db = mcp_db()
    try:
        user = User(username="viewer1", password_hash="x" * 60, role=UserRole.ADMIN, is_active=True)
        db.add(user)
        db.commit()
        token = create_access_token(user.id, user.username)
    finally:
        db.close()
    response = client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_get_answers_405_without_opening_a_stream(client, seeded, mcp_key):
    response = client.get(
        "/api/v1/mcp", headers={"X-API-Key": mcp_key["key"], "Accept": "text/event-stream"}
    )
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


def test_delete_is_not_an_api_key_route(client, seeded, mcp_key):
    response = client.delete("/api/v1/mcp", headers={"X-API-Key": mcp_key["key"]})
    assert response.status_code == 403


def test_per_key_rate_limit(client, seeded, make_key):
    key = make_key(["read:mcp"], rate_limit=3)
    codes = [rpc(client, key["key"], "tools/list", {}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    limited = rpc(client, key["key"], "tools/list", {})
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1


def test_global_mcp_ceiling_caps_generous_keys(client, seeded, make_key, monkeypatch):
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_PER_MINUTE", 2)
    key = make_key(["read:mcp"], rate_limit=1000)
    codes = [rpc(client, key["key"], "tools/list", {}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_kill_switch_disables_endpoint(client, seeded, mcp_key, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    assert rpc(client, mcp_key["key"], "tools/list", {}).status_code == 404
