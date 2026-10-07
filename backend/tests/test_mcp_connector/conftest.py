"""Fixtures for the read-only MCP connector tests (issue #648).

The tests seed a throwaway SQLite file and point ``SessionLocal`` at it, so
the deployed middleware (API key verification) and the MCP tools both read the
seeded rows through the normal ``get_db_session()`` helper.
"""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from app.core import database
from app.core.database import Base
from app.middleware.api_key_rate_limiter import get_rate_limiter
from app.models.recognized_entity import EntityEvent
from app.models.system_setting import SystemSetting
from app.services.api_key_service import APIKeyService
from tests.conftest import make_camera, make_entity, make_event

# 1x1 JPEG-ish bytes; content is irrelevant to the tests.
THUMB_BYTES = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"
NOW = datetime.now(timezone.utc)


@pytest.fixture
def mcp_db(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'mcp.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    get_rate_limiter().clear()
    yield session_factory
    get_rate_limiter().clear()
    engine.dispose()


@pytest.fixture
def seeded(mcp_db):
    """Two cameras, six events, one named person, one multi-camera incident."""
    db = mcp_db()
    try:
        db.add(SystemSetting(key="settings_timezone", value="America/New_York"))
        front = make_camera(db, name="Front Door", source_type="protect", is_doorbell=True)
        drive = make_camera(db, name="Driveway")
        alex = make_entity(
            db, name="Alex", entity_type="person", occurrence_count=12,
            first_seen_at=NOW - timedelta(days=30), last_seen_at=NOW - timedelta(minutes=10),
        )
        group = str(uuid.uuid4())
        ids = {}

        def add(key, camera, minutes_ago, description, objects, **extra):
            event = make_event(
                db,
                camera_id=camera.id,
                timestamp=NOW - timedelta(minutes=minutes_ago),
                description=description,
                objects_detected=json.dumps(objects),
                **extra,
            )
            ids[key] = event.id
            return event

        add("person_now", front, 10, "A person in a grey hoodie walks up to the front door.", ["person"],
            enriched_description="Alex walks up to the front door in a grey hoodie.",
            thumbnail_base64=base64.b64encode(THUMB_BYTES).decode(), smart_detection_type="person",
            is_doorbell_ring=True, matched_entity_ids=json.dumps([alex.id]))
        add("car_drive", drive, 30, "A blue pickup truck pulls into the driveway.", ["vehicle"],
            correlation_group_id=group, smart_detection_type="vehicle")
        add("car_front", front, 29, "A blue pickup truck is visible from the front door.", ["vehicle"],
            correlation_group_id=group, smart_detection_type="vehicle")
        add("package", front, 120, "A UPS driver leaves a box on the porch.", ["person", "package"],
            delivery_carrier="ups", smart_detection_type="package")
        add("pickup", front, 90, "A person picks up the package from the porch and goes inside.", ["person"])
        add("old_person", drive, 60 * 24 * 3, "A person walks down the driveway.", ["person"])
        db.add(EntityEvent(entity_id=alex.id, event_id=ids["old_person"], similarity_score=0.9))
        db.commit()
        return {"ids": ids, "front": front.id, "drive": drive.id, "alex": alex.id, "group": group}
    finally:
        db.close()


def _make_key(session_factory, scopes, *, rate_limit=100, revoke=False):
    db = session_factory()
    try:
        service = APIKeyService()
        api_key, plaintext = service.generate_api_key(
            db, name=f"test {'+'.join(scopes) or 'none'}", scopes=scopes, rate_limit_per_minute=rate_limit,
        )
        if revoke:
            api_key.revoke()
            db.commit()
        return {"id": api_key.id, "prefix": api_key.prefix, "key": plaintext}
    finally:
        db.close()


@pytest.fixture
def make_key(mcp_db):
    return lambda scopes, **kw: _make_key(mcp_db, scopes, **kw)


@pytest.fixture
def mcp_key(make_key):
    return make_key(["read:mcp"])


@pytest.fixture
def client(mcp_db):
    # No context manager: the app lifespan (cameras, schedulers) is not needed.
    return TestClient(main.app)


MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def rpc(client, key, method, params=None, *, request_id=1, auth="x-api-key", extra_headers=None):
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    headers = dict(MCP_HEADERS)
    if key is not None:
        if auth == "bearer":
            headers["Authorization"] = f"Bearer {key}"
        else:
            headers["X-API-Key"] = key
    headers.update(extra_headers or {})
    return client.post("/api/v1/mcp", json=body, headers=headers)


def call_tool(client, key, name, arguments=None):
    response = rpc(client, key, "tools/call", {"name": name, "arguments": arguments or {}})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    return result, response.text
