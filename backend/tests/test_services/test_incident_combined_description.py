"""Combined AI description per grouped multi-camera incident.

One multi-image call over at most one frame per camera (max 4) inside the
multi-image SLA. Timeout or error falls back to per-camera descriptions.
The entity chip on an incident is only the union of members'
matched_entity_ids, never anything parsed from description text.
All ids and images here are synthetic.
"""
import asyncio
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import numpy as np
import pytest

from app.models.camera import Camera
from app.models.event import Event
from app.models.incident import Incident
from app.models.system_setting import SystemSetting
from app.services import incident_service
from app.services.ai_types import AIResult

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
FRAME = base64.b64encode(b"\xff\xd8synthetic-jpeg\xff\xd9").decode()


def _uid() -> str:
    return str(uuid.uuid4())


def _camera(db, name):
    cam = Camera(id=_uid(), name=name, type="rtsp",
                 rtsp_url="rtsp://camera.example/stream", frame_rate=5, is_enabled=True)
    db.add(cam)
    db.commit()
    return cam


def _event(db, camera, group_id, seconds=0, description="A vehicle stops.",
           entity_ids=None, frame=FRAME):
    ev = Event(
        id=_uid(), camera_id=camera.id, timestamp=BASE + timedelta(seconds=seconds),
        description=description, confidence=80, objects_detected='["vehicle"]',
        alert_triggered=False, source_type="protect", thumbnail_base64=frame,
        correlation_group_id=group_id,
        matched_entity_ids=json.dumps(entity_ids) if entity_ids else None,
    )
    db.add(ev)
    db.commit()
    return ev


def _enable(db, value="true"):
    db.merge(SystemSetting(key=incident_service.COMBINED_SETTING_KEY, value=value))
    db.commit()


def _ok(description="Combined: a vehicle arrives and a package is left."):
    return AIResult(description=description, confidence=90, objects_detected=["vehicle", "package"],
                    provider="test", tokens_used=10, response_time_ms=5, cost_estimate=0.0,
                    success=True, identification={"count": np.int64(2), "score": np.float32(0.5)})


def _orch(result=None, side_effect=None):
    orch = AsyncMock()
    orch.default_multi_image_sla_ms = 25_000
    orch.analyze_images = AsyncMock(return_value=result, side_effect=side_effect)
    return orch


def _group(db, n_cameras=2, **kw):
    gid = _uid()
    events = [_event(db, _camera(db, f"Cam {i}"), gid, seconds=i, **kw) for i in range(n_cameras)]
    return gid, events


class TestFlag:
    def test_flag_defaults_on(self, db_session):
        assert incident_service.combined_description_enabled(db_session) is True

    @pytest.mark.parametrize("value", ["false", "0", "off", "no", " False "])
    def test_explicit_false_is_off(self, db_session, value):
        _enable(db_session, value)
        assert incident_service.combined_description_enabled(db_session) is False

    @pytest.mark.parametrize("value", ["true", "", "nonsense"])
    def test_true_or_unparseable_uses_default_on(self, db_session, value):
        _enable(db_session, value)
        assert incident_service.combined_description_enabled(db_session) is True

    @pytest.mark.asyncio
    async def test_flag_off_makes_no_call_and_no_row(self, db_session):
        _enable(db_session, "false")
        gid, _ = _group(db_session)
        orch = _orch(_ok())
        assert await incident_service.run_combined_pass(db_session, gid, orchestrator=orch) is None
        orch.analyze_images.assert_not_called()
        assert db_session.query(Incident).count() == 0


class TestSettle:
    def test_default_and_clamped(self, monkeypatch):
        monkeypatch.delenv("INCIDENT_SETTLE_MS", raising=False)
        assert incident_service.resolve_settle_ms() == 3000
        assert incident_service.resolve_settle_ms(5) == 1000
        assert incident_service.resolve_settle_ms(99999) == 10000
        monkeypatch.setenv("INCIDENT_SETTLE_MS", "garbage")
        assert incident_service.resolve_settle_ms() == 3000


class TestCombinedPass:
    @pytest.mark.asyncio
    async def test_multi_camera_group_gets_one_combined_row(self, db_session):
        _enable(db_session)
        gid, events = _group(db_session, 2)
        orch = _orch(_ok())
        inc = await incident_service.run_combined_pass(db_session, gid, orchestrator=orch)
        assert inc.status == "done"
        assert inc.combined_description.startswith("Combined")
        assert inc.member_count == 2
        assert inc.primary_event_id == events[0].id
        orch.analyze_images.assert_awaited_once()
        kwargs = orch.analyze_images.await_args.kwargs
        assert len(kwargs["images"]) == 2
        assert kwargs["sla_timeout_ms"] == 25_000
        # Per-camera descriptions untouched.
        db_session.expire_all()
        assert {e.description for e in db_session.query(Event).all()} == {"A vehicle stops."}
        # numpy values were cast before json.dumps.
        assert json.loads(inc.combined_identification) == {"count": 2, "score": 0.5}

    @pytest.mark.asyncio
    async def test_at_most_one_frame_per_camera_and_four_cameras(self, db_session):
        _enable(db_session)
        gid, events = _group(db_session, 6)
        # A second event on the first camera must not add a second frame.
        cam0 = db_session.get(Camera, events[0].camera_id)
        _event(db_session, cam0, gid, seconds=1)
        orch = _orch(_ok())
        await incident_service.run_combined_pass(db_session, gid, orchestrator=orch)
        assert len(orch.analyze_images.await_args.kwargs["images"]) == 4

    @pytest.mark.asyncio
    async def test_single_camera_makes_no_call(self, db_session):
        _enable(db_session)
        gid, _ = _group(db_session, 1)
        orch = _orch(_ok())
        assert await incident_service.run_combined_pass(db_session, gid, orchestrator=orch) is None
        orch.analyze_images.assert_not_called()
        assert db_session.query(Incident).count() == 0

    @pytest.mark.asyncio
    async def test_timeout_falls_back(self, db_session, monkeypatch):
        _enable(db_session)
        gid, _ = _group(db_session, 2)

        async def slow(**_):
            await asyncio.sleep(5)

        orch = _orch(side_effect=slow)
        orch.default_multi_image_sla_ms = 50
        monkeypatch.setattr(incident_service, "SLA_GRACE_MS", 0)
        inc = await incident_service.run_combined_pass(db_session, gid, orchestrator=orch)
        assert inc.status == "fallback"
        assert inc.combined_description is None
        db_session.expire_all()
        assert all(e.description == "A vehicle stops." for e in db_session.query(Event).all())

    @pytest.mark.asyncio
    async def test_provider_failure_falls_back(self, db_session):
        _enable(db_session)
        gid, _ = _group(db_session, 2)
        bad = _ok("Failed to generate description - Multi-image SLA timeout")
        bad.success = False
        inc = await incident_service.run_combined_pass(db_session, gid, orchestrator=_orch(bad))
        assert inc.status == "fallback" and inc.combined_description is None

    @pytest.mark.asyncio
    async def test_exception_falls_back(self, db_session):
        _enable(db_session)
        gid, _ = _group(db_session, 2)
        inc = await incident_service.run_combined_pass(
            db_session, gid, orchestrator=_orch(side_effect=RuntimeError("boom")))
        assert inc.status == "fallback"

    @pytest.mark.asyncio
    async def test_rerun_is_idempotent(self, db_session):
        _enable(db_session)
        gid, _ = _group(db_session, 2)
        orch = _orch(_ok())
        await incident_service.run_combined_pass(db_session, gid, orchestrator=orch)
        await incident_service.run_combined_pass(db_session, gid, orchestrator=orch)
        assert db_session.query(Incident).count() == 1
        assert orch.analyze_images.await_count == 1

    @pytest.mark.asyncio
    async def test_new_member_recomputes(self, db_session):
        _enable(db_session)
        gid, events = _group(db_session, 2)
        orch = _orch(_ok())
        await incident_service.run_combined_pass(db_session, gid, orchestrator=orch)
        _event(db_session, _camera(db_session, "Cam late"), gid, seconds=2)
        inc = await incident_service.run_combined_pass(db_session, gid, orchestrator=orch)
        assert inc.member_count == 3 and orch.analyze_images.await_count == 2


class TestEntityChip:
    @pytest.mark.asyncio
    async def test_union_of_member_matched_entity_ids(self, db_session):
        _enable(db_session)
        a, b, c = _uid(), _uid(), _uid()
        gid = _uid()
        _event(db_session, _camera(db_session, "Cam A"), gid, 0, entity_ids=[a, b])
        _event(db_session, _camera(db_session, "Cam B"), gid, 1, entity_ids=[b, c])
        inc = await incident_service.run_combined_pass(db_session, gid, orchestrator=_orch(_ok()))
        assert json.loads(inc.matched_entity_ids) == [a, b, c]

    @pytest.mark.asyncio
    async def test_description_text_alone_never_produces_chip(self, db_session):
        _enable(db_session)
        from app.models.recognized_entity import RecognizedEntity
        ent = RecognizedEntity(id=_uid(), entity_type="person", name="Synthetic Person",
                               reference_embedding="[]", first_seen_at=BASE, last_seen_at=BASE)
        db_session.add(ent)
        db_session.commit()
        gid = _uid()
        text = f"Synthetic Person ({ent.id}) arrives."
        _event(db_session, _camera(db_session, "Cam A"), gid, 0, description=text)
        _event(db_session, _camera(db_session, "Cam B"), gid, 1, description=text)
        inc = await incident_service.run_combined_pass(
            db_session, gid, orchestrator=_orch(_ok(f"Synthetic Person {ent.id} left a package.")))
        assert inc.matched_entity_ids is None
        payload = incident_service.serialize_incident(db_session, inc)
        assert payload["matched_entity_ids"] == []


class TestSerialize:
    @pytest.mark.asyncio
    async def test_api_shape(self, db_session):
        _enable(db_session)
        gid, events = _group(db_session, 2)
        inc = await incident_service.run_combined_pass(db_session, gid, orchestrator=_orch(_ok()))
        payload = incident_service.serialize_incident(db_session, inc)
        assert payload["id"] == gid and payload["correlation_group_id"] == gid
        assert payload["status"] == "done"
        assert payload["member_event_ids"] == [e.id for e in events]
        assert set(payload) >= {"combined_description", "combined_identification",
                                "matched_entity_ids", "member_count", "primary_event_id"}
        json.dumps(payload, default=str)

    def test_incidents_for_events_none_without_row(self, db_session):
        gid, events = _group(db_session, 2)
        assert incident_service.incidents_for_events(db_session, events) == {}

    def test_json_safe_casts_numpy(self):
        out = incident_service.json_safe({"a": np.int32(1), "b": [np.float64(0.25)], "c": np.bool_(True)})
        assert json.dumps(out) == '{"a": 1, "b": [0.25], "c": true}'


class TestHooks:
    @pytest.mark.asyncio
    async def test_assign_group_schedules_only_when_enabled(self, db_session, monkeypatch):
        from app.services.correlation_service import CorrelationService

        calls = []
        monkeypatch.setattr(incident_service, "schedule_combined_pass",
                            lambda db, gid: calls.append(gid))
        a = _event(db_session, _camera(db_session, "Cam A"), None, 0)
        b = _event(db_session, _camera(db_session, "Cam B"), None, 1)
        svc = CorrelationService(time_window_seconds=2)
        await svc.assign_group(db_session, a)
        gid = await svc.assign_group(db_session, b)
        assert gid and calls[-1] == gid


class TestApi:
    def test_event_and_incident_endpoints(self, db_session, monkeypatch):
        from fastapi.testclient import TestClient
        from app.core.database import get_db
        from main import app

        _enable(db_session)
        gid, events = _group(db_session, 2)
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            incident_service.run_combined_pass(db_session, gid, orchestrator=_orch(_ok())))
        lone = _event(db_session, _camera(db_session, "Cam solo"), None, 30)

        app.dependency_overrides[get_db] = lambda: db_session
        try:
            client = TestClient(app)
            detail = client.get(f"/api/v1/events/{events[1].id}").json()
            assert detail["incident"]["status"] == "done"
            assert detail["incident"]["member_event_ids"] == [e.id for e in events]
            assert detail["incident"]["correlation_group_id"] == gid
            assert client.get(f"/api/v1/events/{lone.id}").json()["incident"] is None
            listed = {e["id"]: e for e in client.get("/api/v1/events?limit=50").json()["events"]}
            assert listed[events[0].id]["incident"]["id"] == gid
            assert listed[lone.id]["incident"] is None
            inc = client.get(f"/api/v1/incidents/{gid}")
            assert inc.status_code == 200 and inc.json()["combined_description"].startswith("Combined")
            assert client.get(f"/api/v1/incidents/{_uid()}").status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestFailedStatus:
    @pytest.mark.asyncio
    async def test_internal_error_marks_failed(self, db_session, monkeypatch):
        gid, _ = _group(db_session, 2)
        db_session.add(Incident(id=gid, status="pending", member_count=2))
        db_session.commit()

        async def boom(db, group_id, orchestrator=None):
            raise RuntimeError("internal")

        monkeypatch.setattr(incident_service, "run_combined_pass", boom)
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        await incident_service._settle_then_run(gid, 0)
        db_session.expire_all()
        assert db_session.get(Incident, gid).status == "failed"

    def test_update_pushed_at_column_exists_and_nullable(self):
        col = Incident.__table__.c.update_pushed_at
        assert col.nullable is True


class TestReviewFixes:
    @pytest.mark.asyncio
    async def test_recompute_clears_stale_combined_fields(self, db_session):
        _enable(db_session)
        gid, _ = _group(db_session, 2)
        await incident_service.run_combined_pass(db_session, gid, orchestrator=_orch(_ok()))
        _event(db_session, _camera(db_session, "Cam late"), gid, seconds=2)
        seen = {}

        async def capture(**_):
            row = db_session.get(Incident, gid)
            seen["desc"], seen["ident"], seen["status"] = (
                row.combined_description, row.combined_identification, row.status)
            raise RuntimeError("provider down")

        await incident_service.run_combined_pass(db_session, gid, orchestrator=_orch(side_effect=capture))
        assert seen == {"desc": None, "ident": None, "status": "pending"}

    @pytest.mark.asyncio
    async def test_schedule_inserts_pending_row_idempotently(self, db_session, monkeypatch):
        gid, _ = _group(db_session, 2)

        async def never(*a, **k):
            return None

        monkeypatch.setattr(incident_service, "_settle_then_run", never)
        incident_service.schedule_combined_pass(db_session, gid)
        incident_service.schedule_combined_pass(db_session, gid)
        rows = db_session.query(Incident).filter(Incident.id == gid).all()
        assert len(rows) == 1 and rows[0].status == "pending"
        for t in list(incident_service._pending_tasks.values()):
            t.cancel()
        incident_service._pending_tasks.clear()

    @pytest.mark.asyncio
    async def test_schedule_does_not_reset_finished_row(self, db_session, monkeypatch):
        _enable(db_session)
        gid, _ = _group(db_session, 2)
        await incident_service.run_combined_pass(db_session, gid, orchestrator=_orch(_ok()))

        async def never(*a, **k):
            return None

        monkeypatch.setattr(incident_service, "_settle_then_run", never)
        incident_service.schedule_combined_pass(db_session, gid)
        db_session.expire_all()
        assert db_session.get(Incident, gid).status == "done"
        incident_service._pending_tasks.clear()

    def test_cleanup_deletes_incidents_without_members(self, db_session):
        from app.services.cleanup_service import CleanupService
        gid, events = _group(db_session, 2)
        db_session.add(Incident(id=gid, status="done", member_count=2))
        db_session.add(Incident(id=_uid(), status="pending", member_count=2))
        db_session.commit()
        CleanupService(session_factory=lambda: db_session)._delete_orphan_dependent_rows(db_session)
        db_session.commit()
        assert [i.id for i in db_session.query(Incident).all()] == [gid]

    def test_invalid_base64_frame_is_skipped(self):
        ev = Event(thumbnail_base64="not*valid*base64!!", key_frames_base64=None)
        assert incident_service._frame_bytes(ev) is None

    def test_models_export_incident(self):
        import app.models as models
        assert "Incident" in models.__all__
