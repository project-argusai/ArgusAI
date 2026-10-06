"""Tool behavior and result shapes for the read-only MCP connector (issue #648)."""
import base64

import pytest

from app.models.user_audit_log import UserAuditLog
from app.services.mcp_connector import queries
from tests.test_mcp_connector.conftest import THUMB_BYTES, call_tool, rpc

pytestmark = pytest.mark.real_auth_middleware

EXPECTED_TOOLS = {"recent_events", "event_summary", "camera_status", "package_status", "entity_sightings"}


def test_initialize_returns_server_info_and_tools_capability(client, seeded, mcp_key):
    response = rpc(client, mcp_key["key"], "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test-bot", "version": "0"},
    })
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    result = response.json()["result"]
    assert result["serverInfo"]["name"] == "argusai"
    assert "tools" in result["capabilities"]
    assert "read-only" in result["instructions"].lower()


def test_tools_list_contains_only_read_only_tools(client, seeded, mcp_key):
    response = rpc(client, mcp_key["key"], "tools/list", {})
    assert response.status_code == 200, response.text
    tools = response.json()["result"]["tools"]
    assert {tool["name"] for tool in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["destructiveHint"] is False
        assert tool["inputSchema"]["additionalProperties"] is False
        lowered = tool["name"].lower()
        assert not any(verb in lowered for verb in ("delete", "update", "set", "create", "write", "control"))


def test_recent_events_shape_and_window(client, seeded, mcp_key):
    result, raw = call_tool(client, mcp_key["key"], "recent_events", {"since": "1h"})
    assert result["isError"] is False
    data = result["structuredContent"]
    ids = [event["id"] for event in data["events"]]
    assert ids == [seeded["ids"]["person_now"], seeded["ids"]["car_front"], seeded["ids"]["car_drive"]]
    assert data["count"] == 3 and data["truncated"] is False
    assert data["window"]["timezone"] == "America/New_York"

    first = data["events"][0]
    assert first["camera"] == "Front Door"
    assert first["description"].startswith("Alex walks up")
    assert first["objects"] == ["person"]
    assert first["doorbell_ring"] is True
    assert {"label": "Alex", "type": "person", "named": True} in first["people_vehicles"]
    assert first["time"][-6:] in ("-04:00", "-05:00")  # America/New_York offset
    assert first["thumbnail_url"].startswith(f"/api/v1/mcp/thumbnails/{first['id']}?expires=")
    assert "thumbnail_url" not in data["events"][1]  # no thumbnail stored
    assert data["events"][1]["incident_id"] == seeded["group"]
    # Never leak stored image data or file paths.
    assert base64.b64encode(THUMB_BYTES).decode() not in raw
    assert "thumbnail_base64" not in raw and "thumbnail_path" not in raw


def test_recent_events_filters_and_limit(client, seeded, mcp_key):
    result, _ = call_tool(client, mcp_key["key"], "recent_events",
                          {"since": "24h", "camera": "driveway", "object_type": "vehicle"})
    assert [e["id"] for e in result["structuredContent"]["events"]] == [seeded["ids"]["car_drive"]]

    result, _ = call_tool(client, mcp_key["key"], "recent_events", {"since": "24h", "limit": 2})
    data = result["structuredContent"]
    assert data["count"] == 2 and data["truncated"] is True


def test_unknown_camera_is_a_helpful_error(client, seeded, mcp_key):
    result, _ = call_tool(client, mcp_key["key"], "recent_events", {"camera": "Garage"})
    assert result["isError"] is True
    message = result["structuredContent"]["error"]
    assert "Garage" in message and "Front Door" in message and "Driveway" in message


@pytest.mark.parametrize("arguments", [
    {"limit": 1000},
    {"since": "banana"},
    {"since": "500d"},
    {"since": "2999-01-01T00:00:00Z"},
    {"unexpected": "field"},
    {"object_type": "spaceship"},
])
def test_invalid_arguments_are_rejected_and_audited(client, seeded, mcp_key, mcp_db, arguments):
    result, _ = call_tool(client, mcp_key["key"], "recent_events", arguments)
    assert result["isError"] is True
    db = mcp_db()
    try:
        row = db.query(UserAuditLog).filter(UserAuditLog.action == "mcp_tool_call").one()
        assert row.details["outcome"] == "invalid_input"
        assert row.details["result_count"] is None
    finally:
        db.close()


def test_event_summary_groups_multi_camera_incidents(client, seeded, mcp_key):
    result, _ = call_tool(client, mcp_key["key"], "event_summary", {"window": "24h"})
    data = result["structuredContent"]
    totals = data["totals"]
    assert totals["events"] == 5
    assert totals["incidents"] == 4  # the two truck events are one incident
    assert totals["doorbell_rings"] == 1
    assert totals["package_events"] == 1
    assert totals["by_camera"] == {"Front Door": 4, "Driveway": 1}
    grouped = [i for i in data["incidents"] if i.get("incident_id") == seeded["group"]]
    assert len(grouped) == 1
    assert grouped[0]["event_count"] == 2
    assert set(grouped[0]["cameras"]) == {"Front Door", "Driveway"}
    assert data["named_visitors"][0]["name"] == "Alex"
    assert "5 events" in data["headline"]
    assert data["partial"] is False


def test_camera_status_reports_each_camera_and_last_event(client, seeded, mcp_key, monkeypatch):
    statuses = {"Front Door": ("online", None), "Driveway": ("offline", "capture worker not running")}
    monkeypatch.setattr(queries, "_default_status_provider", lambda camera: statuses[camera.name])
    result, _ = call_tool(client, mcp_key["key"], "camera_status")
    data = result["structuredContent"]
    by_name = {camera["name"]: camera for camera in data["cameras"]}
    assert by_name["Front Door"]["status"] == "online"
    assert by_name["Front Door"]["doorbell"] is True
    assert by_name["Front Door"]["last_event"].startswith("Alex walks up")
    assert by_name["Driveway"]["status"] == "offline"
    assert by_name["Driveway"]["status_reason"] == "capture worker not running"
    assert by_name["Driveway"]["last_event"].startswith("A blue pickup truck pulls")
    assert data["counts"] == {"online": 1, "offline": 1}


def test_default_status_provider_disabled_and_rtsp(seeded, mcp_db):
    db = mcp_db()
    try:
        from app.models.camera import Camera

        drive = db.query(Camera).filter(Camera.name == "Driveway").one()
        status, reason = queries._default_status_provider(drive)
        assert status == "offline"  # no capture worker in tests
        drive.is_enabled = False
        assert queries._default_status_provider(drive) == ("disabled", "disabled in settings")
    finally:
        db.rollback()
        db.close()


def test_package_status_is_best_effort_and_honest(client, seeded, mcp_key):
    result, _ = call_tool(client, mcp_key["key"], "package_status", {"since": "24h"})
    data = result["structuredContent"]
    assert data["package_events"] == 1
    package = data["packages"][0]
    assert package["event_id"] == seeded["ids"]["package"]
    assert package["carrier"] == "ups"
    assert package["pickup_status"] == "possibly_picked_up"
    assert "picks up the package" in package["pickup_evidence"]["description"]
    assert package["later_person_events_on_camera"] >= 1
    assert data["pickup_tracking"] == "best_effort"
    assert "does not confirm pickups" in data["note"]


def test_entity_sightings_found_and_suggestions(client, seeded, mcp_key):
    result, _ = call_tool(client, mcp_key["key"], "entity_sightings", {"name": "alex", "since": "7d"})
    data = result["structuredContent"]
    assert data["found"] is True
    match = data["matches"][0]
    assert match["name"] == "Alex" and match["type"] == "person"
    assert match["total_sightings"] == 12
    sighted = [s["event_id"] for s in match["sightings_in_window"]]
    # One via matched_entity_ids, one via the entity_events link table.
    assert sighted == [seeded["ids"]["person_now"], seeded["ids"]["old_person"]]

    result, _ = call_tool(client, mcp_key["key"], "entity_sightings", {"name": "Alx"})
    data = result["structuredContent"]
    assert data["found"] is False
    assert data["suggestions"] == ["Alex"]


def test_tool_call_writes_audit_row_without_secrets(client, seeded, mcp_key, mcp_db):
    call_tool(client, mcp_key["key"], "recent_events", {"since": "1h", "camera": "Front Door"})
    db = mcp_db()
    try:
        rows = db.query(UserAuditLog).filter(UserAuditLog.action == "mcp_tool_call").all()
        assert len(rows) == 1
        details = rows[0].details
        assert details["api_key_id"] == mcp_key["id"]
        assert details["api_key_prefix"] == mcp_key["prefix"]
        assert details["tool"] == "recent_events"
        assert details["args"] == {"since": "1h", "camera": "Front Door"}
        assert details["result_count"] == 2
        assert details["outcome"] == "ok"
        assert rows[0].user_id is None
        assert mcp_key["key"] not in str(details)
    finally:
        db.close()


def test_unknown_tool_is_rejected_and_audited(client, seeded, mcp_key, mcp_db):
    result, _ = call_tool(client, mcp_key["key"], "delete_events", {})
    assert result["isError"] is True
    db = mcp_db()
    try:
        row = db.query(UserAuditLog).filter(UserAuditLog.action == "mcp_tool_call").one()
        assert row.details["outcome"] == "unknown_tool"
    finally:
        db.close()


def test_internal_errors_are_generic(client, seeded, mcp_key, monkeypatch):
    def boom(db, **kwargs):
        raise RuntimeError("sqlite3.OperationalError at /secret/internal/path")

    monkeypatch.setattr(queries, "camera_status", boom)
    result, raw = call_tool(client, mcp_key["key"], "camera_status")
    assert result["isError"] is True
    assert "secret" not in raw and "OperationalError" not in raw


def test_audit_failure_does_not_break_tool_call(client, seeded, mcp_key, monkeypatch):
    from app.services.mcp_connector import audit

    class _Broken:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(audit, "get_db_session", lambda: _Broken())
    result, _ = call_tool(client, mcp_key["key"], "recent_events", {"since": "1h"})
    assert result["isError"] is False
