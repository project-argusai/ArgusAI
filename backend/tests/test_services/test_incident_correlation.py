"""Cross-camera incident grouping (issue #642).

The window is detection time, not insert order. Same-camera rows stay
independent so Protect's per-camera dedup is unchanged. Each event row
keeps its own description.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.camera import Camera
from app.models.event import Event
from app.services.correlation_service import (
    CorrelationService,
    resolve_correlation_window,
    reset_correlation_service,
)

WINDOW = 2
BASE = datetime(2026, 10, 1, 17, 28, 18, tzinfo=timezone.utc)


@pytest.fixture
def correlator():
    reset_correlation_service()
    service = CorrelationService(time_window_seconds=WINDOW)
    yield service
    reset_correlation_service()


def _camera(db, camera_id: str, name: str) -> Camera:
    camera = Camera(
        id=camera_id,
        name=name,
        type="rtsp",
        rtsp_url=f"rtsp://camera.example/{camera_id}",
        frame_rate=5,
        is_enabled=True,
    )
    db.add(camera)
    db.commit()
    return camera


def _event(
    db,
    event_id: str,
    camera_id: str,
    timestamp: datetime,
    description: str,
    detection: str = "vehicle",
) -> Event:
    event = Event(
        id=event_id,
        camera_id=camera_id,
        timestamp=timestamp,
        description=description,
        confidence=80,
        objects_detected=json.dumps([detection]),
        alert_triggered=False,
        source_type="protect",
        smart_detection_type=detection,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _reload(db, event_id: str) -> Event:
    db.expire_all()
    return db.query(Event).filter(Event.id == event_id).one()


class TestCorrelationWindow:
    @pytest.mark.asyncio
    async def test_events_inside_window_share_a_group(self, db_session, correlator):
        _camera(db_session, "cam-driveway", "Driveway")
        _camera(db_session, "cam-garage", "Garage")
        driveway = _event(
            db_session, "evt-driveway", "cam-driveway", BASE, "Car arrives on the driveway"
        )
        assert await correlator.assign_group(db_session, driveway) is None

        garage = _event(
            db_session,
            "evt-garage",
            "cam-garage",
            BASE + timedelta(seconds=1),
            "Same car at the garage",
            detection="motion",
        )
        group_id = await correlator.assign_group(db_session, garage)

        driveway = _reload(db_session, "evt-driveway")
        garage = _reload(db_session, "evt-garage")
        assert group_id is not None
        assert driveway.correlation_group_id == group_id
        assert garage.correlation_group_id == group_id
        assert driveway.description == "Car arrives on the driveway"
        assert garage.description == "Same car at the garage"
        assert db_session.query(Event).count() == 2

    @pytest.mark.asyncio
    async def test_exact_window_boundary_is_included(self, db_session, correlator):
        _camera(db_session, "cam-driveway", "Driveway")
        _camera(db_session, "cam-garage", "Garage")
        _event(db_session, "evt-driveway", "cam-driveway", BASE, "Driveway")
        on_boundary = _event(
            db_session,
            "evt-garage",
            "cam-garage",
            BASE + timedelta(seconds=WINDOW),
            "Garage at the boundary",
        )

        group_id = await correlator.assign_group(db_session, on_boundary)

        assert group_id is not None
        assert _reload(db_session, "evt-driveway").correlation_group_id == group_id
        assert _reload(db_session, "evt-garage").description == "Garage at the boundary"

    @pytest.mark.asyncio
    async def test_events_outside_window_stay_separate(self, db_session, correlator):
        _camera(db_session, "cam-driveway", "Driveway")
        _camera(db_session, "cam-street", "Street")
        _event(db_session, "evt-driveway", "cam-driveway", BASE, "Driveway")
        outside = _event(
            db_session,
            "evt-street",
            "cam-street",
            BASE + timedelta(seconds=WINDOW, milliseconds=1),
            "Street, too late",
        )

        assert await correlator.assign_group(db_session, outside) is None
        assert _reload(db_session, "evt-driveway").correlation_group_id is None
        assert _reload(db_session, "evt-street").correlation_group_id is None
        assert _reload(db_session, "evt-street").description == "Street, too late"

    @pytest.mark.asyncio
    async def test_same_camera_is_excluded(self, db_session, correlator):
        _camera(db_session, "cam-driveway", "Driveway")
        first = _event(db_session, "evt-1", "cam-driveway", BASE, "First look")
        second = _event(
            db_session,
            "evt-2",
            "cam-driveway",
            BASE + timedelta(milliseconds=500),
            "Second look, same camera",
        )

        assert await correlator.assign_group(db_session, first) is None
        assert await correlator.assign_group(db_session, second) is None
        assert _reload(db_session, "evt-1").correlation_group_id is None
        assert _reload(db_session, "evt-2").correlation_group_id is None
        assert _reload(db_session, "evt-2").description == "Second look, same camera"

    @pytest.mark.asyncio
    async def test_three_cameras_one_group(self, db_session, correlator):
        _camera(db_session, "cam-driveway", "Driveway")
        _camera(db_session, "cam-garage", "Garage")
        _camera(db_session, "cam-porch", "Porch")
        descriptions = {
            "evt-driveway": "Driveway frame",
            "evt-garage": "Garage frame",
            "evt-porch": "Porch frame",
        }
        driveway = _event(db_session, "evt-driveway", "cam-driveway", BASE, descriptions["evt-driveway"])
        garage = _event(
            db_session,
            "evt-garage",
            "cam-garage",
            BASE + timedelta(milliseconds=800),
            descriptions["evt-garage"],
        )
        porch = _event(
            db_session,
            "evt-porch",
            "cam-porch",
            BASE + timedelta(milliseconds=1600),
            descriptions["evt-porch"],
            detection="person",
        )

        await correlator.assign_group(db_session, driveway)
        group_id = await correlator.assign_group(db_session, garage)
        await correlator.assign_group(db_session, porch)

        db_session.expire_all()
        rows = db_session.query(Event).all()
        assert len(rows) == 3
        assert {row.correlation_group_id for row in rows} == {group_id}
        for row in rows:
            assert row.description == descriptions[row.id]
            member_ids = json.loads(row.correlated_event_ids)
            assert set(member_ids) == set(descriptions)

    @pytest.mark.asyncio
    async def test_out_of_order_arrival(self, db_session, correlator):
        """A later timestamp can be stored before the earlier one."""
        _camera(db_session, "cam-driveway", "Driveway")
        _camera(db_session, "cam-garage", "Garage")
        _camera(db_session, "cam-porch", "Porch")
        garage = _event(
            db_session,
            "evt-garage",
            "cam-garage",
            BASE + timedelta(seconds=1.5),
            "Garage, stored first",
        )
        assert await correlator.assign_group(db_session, garage) is None

        driveway = _event(
            db_session, "evt-driveway", "cam-driveway", BASE, "Driveway, stored second"
        )
        group_id = await correlator.assign_group(db_session, driveway)
        porch = _event(
            db_session,
            "evt-porch",
            "cam-porch",
            BASE + timedelta(seconds=0.4),
            "Porch, stored last",
        )
        await correlator.assign_group(db_session, porch)

        db_session.expire_all()
        rows = {row.id: row for row in db_session.query(Event).all()}
        assert len(rows) == 3
        assert rows["evt-garage"].correlation_group_id == group_id
        assert rows["evt-driveway"].correlation_group_id == group_id
        assert rows["evt-porch"].correlation_group_id == group_id
        assert rows["evt-garage"].description == "Garage, stored first"
        assert rows["evt-driveway"].description == "Driveway, stored second"
        assert rows["evt-porch"].description == "Porch, stored last"


def test_window_config_falls_closed(monkeypatch):
    assert resolve_correlation_window(None) == 2
    assert resolve_correlation_window(0) == 2
    assert resolve_correlation_window(-5) == 2
    assert resolve_correlation_window(1.5) == 1.5
    assert resolve_correlation_window(45) == 30

    monkeypatch.setenv("CORRELATION_WINDOW_SECONDS", "not-a-number")
    assert resolve_correlation_window() == 2

    monkeypatch.setenv("CORRELATION_WINDOW_SECONDS", "4")
    assert resolve_correlation_window() == 4
