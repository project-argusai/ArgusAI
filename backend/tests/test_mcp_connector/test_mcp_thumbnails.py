"""Signed, expiring thumbnail links for MCP results (issue #648)."""
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.config import settings
from app.services.mcp_connector import thumbnails
from app.services.signed_url_service import SignedURLService
from tests.test_mcp_connector.conftest import THUMB_BYTES, call_tool

pytestmark = pytest.mark.real_auth_middleware


def _split(url):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    return parts.path, int(query["expires"][0]), query["sig"][0]


def test_signed_link_from_tool_result_serves_thumbnail_without_auth(client, seeded, mcp_key):
    result, _ = call_tool(client, mcp_key["key"], "recent_events", {"since": "1h"})
    url = result["structuredContent"]["events"][0]["thumbnail_url"]
    response = client.get(url)  # no API key, no session
    assert response.status_code == 200
    assert response.content == THUMB_BYTES
    assert response.headers["content-type"] == "image/jpeg"
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_expired_link_is_rejected(client, seeded):
    event_id = seeded["ids"]["person_now"]
    url = thumbnails.signed_thumbnail_path(event_id, ttl_seconds=60, now=time.time() - 120)
    assert client.get(url).status_code == 403


def test_tampered_or_cross_event_link_is_rejected(client, seeded):
    event_id = seeded["ids"]["person_now"]
    path, expires, sig = _split(thumbnails.signed_thumbnail_path(event_id))
    bad_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert client.get(path, params={"expires": expires, "sig": bad_sig}).status_code == 403
    assert client.get(path, params={"expires": expires + 1, "sig": sig}).status_code == 403
    other = f"/api/v1/mcp/thumbnails/{seeded['ids']['car_drive']}"
    assert client.get(other, params={"expires": expires, "sig": sig}).status_code == 403


def test_push_notification_signature_is_not_accepted(client, seeded):
    event_id = seeded["ids"]["person_now"]
    expires = int(time.time()) + 60
    push_sig = SignedURLService(secret_key=settings.ENCRYPTION_KEY.encode())._create_signature(event_id, expires)
    response = client.get(f"/api/v1/mcp/thumbnails/{event_id}", params={"expires": expires, "sig": push_sig})
    assert response.status_code == 403


def test_overlong_lifetime_is_rejected():
    event_id = "abc-123"
    now = time.time()
    path = thumbnails.signed_thumbnail_path(event_id, ttl_seconds=7200, now=now)
    _, expires, sig = _split(path)
    assert not thumbnails.verify_thumbnail_signature(event_id, expires, sig, now=now)
    path = thumbnails.signed_thumbnail_path(event_id, ttl_seconds=600, now=now)
    _, expires, sig = _split(path)
    assert thumbnails.verify_thumbnail_signature(event_id, expires, sig, now=now)


def test_event_without_thumbnail_is_404(client, seeded):
    event_id = seeded["ids"]["car_drive"]
    assert client.get(thumbnails.signed_thumbnail_path(event_id)).status_code == 404


def test_missing_query_is_rejected(client, seeded):
    response = client.get(f"/api/v1/mcp/thumbnails/{seeded['ids']['person_now']}")
    assert response.status_code == 422


def test_file_thumbnails_are_confined(tmp_path, monkeypatch):
    base = tmp_path / "thumbnails"
    (base / "2026-10-06").mkdir(parents=True)
    (base / "2026-10-06" / "a.jpg").write_bytes(b"jpeg")
    (tmp_path / "secret.txt").write_text("nope")
    monkeypatch.setattr(thumbnails, "THUMBNAIL_DIR", base)
    assert thumbnails.load_thumbnail_bytes("2026-10-06/a.jpg", None) == b"jpeg"
    assert thumbnails.load_thumbnail_bytes("/api/v1/thumbnails/2026-10-06/a.jpg", None) == b"jpeg"
    assert thumbnails.load_thumbnail_bytes("../secret.txt", None) is None
    assert thumbnails.load_thumbnail_bytes("2026-10-06/../../secret.txt", None) is None
    assert thumbnails.load_thumbnail_bytes(str(tmp_path / "secret.txt"), None) is None


def test_public_base_url_makes_links_absolute(monkeypatch):
    monkeypatch.setattr(settings, "MCP_PUBLIC_BASE_URL", "https://argusai.example.com")
    url = thumbnails.signed_thumbnail_url("abc-123")
    assert url.startswith("https://argusai.example.com/api/v1/mcp/thumbnails/abc-123?expires=")
