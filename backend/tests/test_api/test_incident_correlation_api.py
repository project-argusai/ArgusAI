"""API shape for cross-camera incidents (issue #642)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.camera import Camera
from app.models.event import Event
from app.services.correlation_service import CorrelationService, reset_correlation_service
from main import app

BASE = datetime(2026, 10, 1, 17, 28, 18, tzinfo=timezone.utc)


@pytest.fixture
def api_client(db_session):
    previous = app.dependency_overrides.get(get_db)

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    yield client
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def _seed_pair(db):
    db.add_all([
        Camera(
            id="cam-driveway",
            name="Driveway",
            type="rtsp",
            rtsp_url="rtsp://camera.example/driveway",
            frame_rate=5,
            is_enabled=True,
        ),
        Camera(
            id="cam-garage",
            name="Garage",
            type="rtsp",
            rtsp_url="rtsp://camera.example/garage",
            frame_rate=5,
            is_enabled=True,
        ),
    ])
    db.commit()
    driveway = Event(
        id="evt-driveway",
        camera_id="cam-driveway",
        timestamp=BASE,
        description="Amazon van on the driveway",
        confidence=90,
        objects_detected=json.dumps(["vehicle"]),
        alert_triggered=False,
        source_type="protect",
        smart_detection_type="vehicle",
        thumbnail_path="2026-10-01/evt-driveway.jpg",
    )
    garage = Event(
        id="evt-garage",
        camera_id="cam-garage",
        timestamp=BASE + timedelta(seconds=1),
        description="Van at the garage door",
        confidence=70,
        objects_detected=json.dumps(["vehicle"]),
        alert_triggered=False,
        source_type="protect",
        smart_detection_type="vehicle",
    )
    alone = Event(
        id="evt-alone",
        camera_id="cam-driveway",
        timestamp=BASE + timedelta(minutes=10),
        description="Later, unrelated motion",
        confidence=40,
        objects_detected=json.dumps(["unknown"]),
        alert_triggered=False,
        source_type="protect",
        smart_detection_type="motion",
    )
    db.add_all([driveway, garage, alone])
    db.commit()
    reset_correlation_service()
    service = CorrelationService(time_window_seconds=2)
    return service, driveway, garage


def _sibling(payload, event_id):
    matches = [item for item in payload["correlated_events"] if item["id"] == event_id]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.asyncio
async def test_list_and_detail_expose_the_incident(db_session, api_client):
    service, driveway, garage = _seed_pair(db_session)
    group_id = await service.assign_group(db_session, garage)
    assert group_id is not None
    assert driveway.id == "evt-driveway"

    detail = api_client.get("/api/v1/events/evt-driveway")
    assert detail.status_code == 200
    body = detail.json()
    assert body["correlation_group_id"] == group_id
    assert body["description"] == "Amazon van on the driveway"
    sibling = _sibling(body, "evt-garage")
    assert sibling["camera_name"] == "Garage"
    assert "timestamp" in sibling
    assert sibling["thumbnail_url"] is None

    garage_detail = api_client.get("/api/v1/events/evt-garage")
    assert garage_detail.status_code == 200
    garage_body = garage_detail.json()
    assert garage_body["correlation_group_id"] == group_id
    assert garage_body["description"] == "Van at the garage door"
    driveway_sibling = _sibling(garage_body, "evt-driveway")
    assert driveway_sibling["camera_name"] == "Driveway"
    assert driveway_sibling["thumbnail_url"] == "/api/v1/thumbnails/2026-10-01/evt-driveway.jpg"

    listing = api_client.get("/api/v1/events")
    assert listing.status_code == 200
    events = {item["id"]: item for item in listing.json()["events"]}
    assert set(events) == {"evt-driveway", "evt-garage", "evt-alone"}
    assert events["evt-driveway"]["correlation_group_id"] == group_id
    assert events["evt-garage"]["correlation_group_id"] == group_id
    assert _sibling(events["evt-driveway"], "evt-garage")["camera_name"] == "Garage"
    assert _sibling(events["evt-garage"], "evt-driveway")["camera_name"] == "Driveway"
    assert events["evt-alone"]["correlation_group_id"] is None
    assert events["evt-alone"]["correlated_events"] is None
    assert events["evt-alone"]["description"] == "Later, unrelated motion"

    reset_correlation_service()
