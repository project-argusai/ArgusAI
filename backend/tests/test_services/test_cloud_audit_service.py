"""#736 (#691 P1 S2a): sampled background cloud audit of key events.

Local is primary. A sample of key events (person, vehicle, package, doorbell
ring) gets a background cloud call, capped at 200/day counted from
shadow_results rows. Same event -> same decision. At most 2 pending, a 3rd is
dropped. 30 s timeout, no retry, never writes to events. Paused when fewer
than 10 fallback calls remain, never with AI_PRIMARY=cloud, kill switch
re-checked inside the task, yields to an in-progress #696 fallback call.
A fallback pair that already called cloud is recorded free (source=fallback).
All data here is synthetic.
"""
import asyncio
import json
import logging
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.camera import Camera
from app.models.event import Event
from app.models.shadow_result import ShadowDailySummary, ShadowResult
from app.services import cloud_audit_service as cas
from app.services.cloud_audit_service import AuditConfig, CloudAuditService

FAKE_NAME = "Orsolya Fenwright"
FAKE_PLATE = "QZ4TEST"
FAKE_PATH = "data/thumbnails/2026-06-01/fake.jpg"
LOCAL = {"description": f"{FAKE_NAME} drives {FAKE_PLATE}", "confidence": 60,
         "objects_detected": ["person", "vehicle"], "thumbnail_path": FAKE_PATH}
CLOUD = {"description": "A person drives a car.", "confidence": 90,
         "objects_detected": ["person", "vehicle"]}
IMAGE = "c3ludGhldGlj"  # base64("synthetic")


def _uid():
    return str(uuid.uuid4())


@pytest.fixture
def db_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    yield factory
    engine.dispose()


def _event(factory, smart="person", ring=False):
    db = factory()
    cam = Camera(id=_uid(), name="Cam A", type="rtsp", rtsp_url="rtsp://camera.example/s",
                 frame_rate=5, is_enabled=True)
    db.add(cam)
    ev = Event(id=_uid(), camera_id=cam.id, timestamp=datetime.now(timezone.utc),
               description="Local text.", confidence=60, objects_detected='["person"]',
               alert_triggered=False, source_type="protect", smart_detection_type=smart,
               is_doorbell_ring=ring, provider_used="local")
    db.add(ev)
    db.commit()
    snap = {c.name: getattr(ev, c.name) for c in Event.__table__.columns}
    db.close()
    return ev.id, snap


def _event_row(factory, event_id):
    db = factory()
    ev = db.get(Event, event_id)
    snap = {c.name: getattr(ev, c.name) for c in Event.__table__.columns}
    db.close()
    return snap


BASE_CFG = AuditConfig(enabled=True, primary_local=True, sample_rate=1.0, daily_cap=200,
                       max_pending=2, timeout_s=30.0, min_fallback_left=10,
                       min_free_memory_mb=0)


class Calls:
    def __init__(self, result=None, exc=None, delay=0.0):
        self.n = 0
        self.result = CLOUD if result is None else result
        self.exc = exc
        self.delay = delay

    async def __call__(self, *, event_id, image_base64, event_type):
        self.n += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.result


def _svc(factory, cfg=BASE_CFG, call=None, **kw):
    state = {"cfg": cfg}
    defaults = dict(fallback_remaining=lambda: 50, fallback_in_progress=lambda: False,
                    free_memory_mb=lambda: 8000, cost_ok=lambda db: True,
                    scorer=lambda l, c: {"pair_complete": 1, "objects_jaccard": 1.0})
    defaults.update(kw)
    svc = CloudAuditService(cloud_call=call or Calls(), session_factory=factory,
                            config_provider=lambda: state["cfg"], **defaults)
    return svc, state


async def _run(svc, event_id, event_type="person"):
    outcome = svc.maybe_schedule(event_id=event_id, event_type=event_type,
                                 local_result=LOCAL, image_base64=IMAGE)
    await svc.drain()
    return outcome


def _rows(factory, source=None):
    db = factory()
    q = db.query(ShadowResult)
    if source:
        q = q.filter(ShadowResult.source == source)
    rows = q.all()
    db.close()
    return rows


class TestSampling:
    @pytest.mark.parametrize("etype", ["person", "vehicle", "package", "ring"])
    def test_key_types_sampled(self, db_factory, etype):
        svc, _ = _svc(db_factory)
        assert svc.should_sample(_uid(), etype) is True

    @pytest.mark.parametrize("etype", ["animal", "motion", "unknown", None, ""])
    def test_non_key_types_never(self, db_factory, etype):
        svc, _ = _svc(db_factory)
        assert svc.should_sample(_uid(), etype) is False

    def test_same_event_same_decision(self, db_factory):
        svc, state = _svc(db_factory)
        state["cfg"] = replace(BASE_CFG, sample_rate=0.5)
        ids = [f"evt-{i}" for i in range(400)]
        first = [svc.should_sample(i, "person") for i in ids]
        again = [svc.should_sample(i, "person") for i in ids]
        fresh, _ = _svc(db_factory, cfg=replace(BASE_CFG, sample_rate=0.5))
        assert first == again == [fresh.should_sample(i, "person") for i in ids]
        assert 120 < sum(first) < 280  # roughly half

    def test_rate_zero_never(self, db_factory):
        svc, _ = _svc(db_factory, cfg=replace(BASE_CFG, sample_rate=0.0))
        assert not any(svc.should_sample(f"e{i}", "person") for i in range(50))

    @pytest.mark.asyncio
    async def test_non_key_type_makes_no_call(self, db_factory):
        call = Calls()
        svc, _ = _svc(db_factory, call=call)
        eid, _ = _event(db_factory, smart="animal")
        assert await _run(svc, eid, "animal") == "not_key_type"
        assert call.n == 0 and _rows(db_factory) == []


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_records_audit_pair_and_summary(self, db_factory):
        call = Calls()
        svc, _ = _svc(db_factory, call=call)
        eid, before = _event(db_factory)
        assert await _run(svc, eid) == "scheduled"
        assert call.n == 1
        rows = _rows(db_factory, "audit")
        assert len(rows) == 1 and rows[0].event_id == eid
        assert json.loads(rows[0].cloud_result)["confidence"] == 90
        assert _event_row(db_factory, eid) == before  # events untouched
        db = db_factory()
        summary = db.query(ShadowDailySummary).one()
        metrics = json.loads(summary.metrics)
        db.close()
        assert summary.source == "audit" and metrics["pairs"] == 1
        assert metrics["sum_objects_jaccard"] == 1.0

    @pytest.mark.asyncio
    async def test_doorbell_flag_counts_as_key(self, db_factory):
        svc, _ = _svc(db_factory)
        eid, _ = _event(db_factory, smart=None, ring=True)
        assert svc.maybe_schedule(event_id=eid, event_type=None, local_result=LOCAL,
                                  image_base64=IMAGE, is_doorbell_ring=True) == "scheduled"
        await svc.drain()
        assert len(_rows(db_factory)) == 1


class TestGates:
    @pytest.mark.asyncio
    async def test_never_with_ai_primary_cloud(self, db_factory):
        call = Calls()
        svc, _ = _svc(db_factory, cfg=replace(BASE_CFG, primary_local=False), call=call)
        eid, _ = _event(db_factory)
        assert await _run(svc, eid) == "primary_cloud"
        assert call.n == 0

    @pytest.mark.asyncio
    async def test_primary_flips_to_cloud_before_task_runs(self, db_factory):
        call = Calls()
        svc, state = _svc(db_factory, call=call)
        eid, _ = _event(db_factory)
        assert svc.maybe_schedule(event_id=eid, event_type="person", local_result=LOCAL,
                                  image_base64=IMAGE) == "scheduled"
        state["cfg"] = replace(BASE_CFG, primary_local=False)
        await svc.drain()
        assert call.n == 0 and svc.last_outcomes[-1] == "primary_cloud"

    @pytest.mark.asyncio
    async def test_kill_switch_off(self, db_factory):
        call = Calls()
        svc, _ = _svc(db_factory, cfg=replace(BASE_CFG, enabled=False), call=call)
        eid, _ = _event(db_factory)
        assert await _run(svc, eid) == "disabled"
        assert call.n == 0

    @pytest.mark.asyncio
    async def test_kill_switch_mid_run_stops_new_calls(self, db_factory):
        call = Calls(delay=0.05)
        svc, state = _svc(db_factory, call=call)
        e1, _ = _event(db_factory)
        e2, _ = _event(db_factory)
        assert svc.maybe_schedule(event_id=e1, event_type="person", local_result=LOCAL,
                                  image_base64=IMAGE) == "scheduled"
        assert svc.maybe_schedule(event_id=e2, event_type="person", local_result=LOCAL,
                                  image_base64=IMAGE) == "scheduled"
        state["cfg"] = replace(BASE_CFG, enabled=False)  # flipped before tasks run
        await svc.drain()
        assert call.n == 0
        assert svc.last_outcomes.count("disabled") == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("left,expected_calls", [(10, 1), (9, 0), (0, 0)])
    async def test_fallback_floor(self, db_factory, left, expected_calls):
        call = Calls()
        svc, _ = _svc(db_factory, call=call, fallback_remaining=lambda: left)
        eid, _ = _event(db_factory)
        await _run(svc, eid)
        assert call.n == expected_calls
        if not expected_calls:
            assert svc.last_outcomes[-1] == "fallback_floor"

    @pytest.mark.asyncio
    async def test_yields_to_fallback_in_progress(self, db_factory):
        call = Calls()
        svc, _ = _svc(db_factory, call=call, fallback_in_progress=lambda: True)
        eid, _ = _event(db_factory)
        await _run(svc, eid)
        assert call.n == 0 and svc.last_outcomes[-1] == "fallback_in_progress"

    @pytest.mark.asyncio
    async def test_low_memory_skips(self, db_factory):
        call = Calls()
        svc, _ = _svc(db_factory, cfg=replace(BASE_CFG, min_free_memory_mb=2048), call=call,
                      free_memory_mb=lambda: 1000)
        eid, _ = _event(db_factory)
        await _run(svc, eid)
        assert call.n == 0 and svc.last_outcomes[-1] == "low_memory"

    @pytest.mark.asyncio
    async def test_cost_cap_skips(self, db_factory):
        call = Calls()
        svc, _ = _svc(db_factory, call=call, cost_ok=lambda db: False)
        eid, _ = _event(db_factory)
        await _run(svc, eid)
        assert call.n == 0 and svc.last_outcomes[-1] == "cost_cap"


class TestCap:
    @pytest.mark.asyncio
    async def test_daily_cap_counts_rows(self, db_factory):
        call = Calls()
        svc, _ = _svc(db_factory, cfg=replace(BASE_CFG, daily_cap=2), call=call)
        for _ in range(3):
            eid, _ = _event(db_factory)
            await _run(svc, eid)
        assert call.n == 2 and svc.last_outcomes[-1] == "daily_cap"
        assert len(_rows(db_factory, "audit")) == 2

    @pytest.mark.asyncio
    async def test_cap_holds_across_restart(self, db_factory):
        cfg = replace(BASE_CFG, daily_cap=2)
        svc1, _ = _svc(db_factory, cfg=cfg)
        for _ in range(2):
            eid, _ = _event(db_factory)
            await _run(svc1, eid)
        call = Calls()
        svc2, _ = _svc(db_factory, cfg=cfg, call=call)  # "restart": fresh service
        eid, _ = _event(db_factory)
        await _run(svc2, eid)
        assert call.n == 0 and svc2.last_outcomes[-1] == "daily_cap"

    @pytest.mark.asyncio
    async def test_fallback_pairs_do_not_use_audit_cap(self, db_factory):
        svc, _ = _svc(db_factory, cfg=replace(BASE_CFG, daily_cap=1))
        f, _ = _event(db_factory)
        assert svc.record_fallback_pair(event_id=f, local_result=LOCAL, cloud_result=CLOUD) == "recorded"
        call = Calls()
        svc.cloud_call = call
        eid, _ = _event(db_factory)
        await _run(svc, eid)
        assert call.n == 1

    def test_default_cap_is_200(self):
        assert AuditConfig().daily_cap == 200 and AuditConfig().max_pending == 2
        assert AuditConfig().timeout_s == 30.0 and AuditConfig().min_fallback_left == 10
        assert AuditConfig().enabled is False  # kill switch off by default


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_third_pending_is_dropped(self, db_factory):
        call = Calls(delay=0.05)
        svc, _ = _svc(db_factory, call=call)
        ids = [_event(db_factory)[0] for _ in range(3)]
        outs = [svc.maybe_schedule(event_id=i, event_type="person", local_result=LOCAL,
                                   image_base64=IMAGE) for i in ids]
        assert outs == ["scheduled", "scheduled", "dropped_busy"]
        assert svc.pending == 2
        await svc.drain()
        assert call.n == 2 and svc.pending == 0
        eid, _ = _event(db_factory)
        assert svc.maybe_schedule(event_id=eid, event_type="person", local_result=LOCAL,
                                  image_base64=IMAGE) == "scheduled"
        await svc.drain()


class TestFailures:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("exc,label", [(RuntimeError(f"{FAKE_NAME} boom"), "error"),
                                           (MemoryError(), "out_of_memory")])
    async def test_raise_and_oom_leave_events_unchanged(self, db_factory, exc, label, caplog):
        caplog.set_level(logging.DEBUG)
        call = Calls(exc=exc)
        svc, _ = _svc(db_factory, call=call)
        eid, before = _event(db_factory)
        await _run(svc, eid)  # nothing escapes
        assert call.n == 1 and svc.last_outcomes[-1] == label
        assert _rows(db_factory) == []
        assert _event_row(db_factory, eid) == before
        assert all(FAKE_NAME not in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_timeout_no_retry(self, db_factory):
        call = Calls(delay=1.0)
        svc, _ = _svc(db_factory, cfg=replace(BASE_CFG, timeout_s=0.05), call=call)
        eid, before = _event(db_factory)
        await _run(svc, eid)
        assert call.n == 1 and svc.last_outcomes[-1] == "timeout"
        assert _rows(db_factory) == [] and _event_row(db_factory, eid) == before

    @pytest.mark.asyncio
    async def test_failed_cloud_result_not_recorded(self, db_factory):
        svc, _ = _svc(db_factory, call=Calls(result={"success": False, "description": ""}))
        eid, _ = _event(db_factory)
        await _run(svc, eid)
        assert svc.last_outcomes[-1] == "cloud_failed" and _rows(db_factory) == []

    @pytest.mark.asyncio
    async def test_scorer_failure_still_records_pair(self, db_factory):
        def bad(l, c):
            raise ValueError("x")
        svc, _ = _svc(db_factory, scorer=bad)
        eid, _ = _event(db_factory)
        await _run(svc, eid)
        assert len(_rows(db_factory, "audit")) == 1


class TestFallbackPair:
    @pytest.mark.asyncio
    async def test_fallback_pair_free_no_extra_call(self, db_factory):
        call = Calls()
        svc, _ = _svc(db_factory, call=call)
        eid, before = _event(db_factory)
        assert svc.record_fallback_pair(event_id=eid, local_result=LOCAL,
                                        cloud_result=CLOUD) == "recorded"
        await svc.drain()
        assert call.n == 0
        rows = _rows(db_factory, "fallback")
        assert len(rows) == 1 and rows[0].event_id == eid
        assert _event_row(db_factory, eid) == before
        # A later audit for the same event makes no cloud call either.
        assert svc.maybe_schedule(event_id=eid, event_type="person", local_result=LOCAL,
                                  image_base64=IMAGE) == "already_paired"
        await svc.drain()
        assert call.n == 0

    def test_fallback_pair_recorded_even_when_primary_cloud_or_disabled(self, db_factory):
        svc, _ = _svc(db_factory, cfg=replace(BASE_CFG, enabled=False))
        eid, _ = _event(db_factory)
        assert svc.record_fallback_pair(event_id=eid, local_result=LOCAL,
                                        cloud_result=CLOUD) == "disabled"
        assert _rows(db_factory) == []


class TestLogs:
    @pytest.mark.asyncio
    async def test_logs_carry_no_text(self, db_factory, caplog):
        caplog.set_level(logging.DEBUG)
        svc, _ = _svc(db_factory)
        e1, _ = _event(db_factory)
        e2, _ = _event(db_factory)
        await _run(svc, e1)
        svc.record_fallback_pair(event_id=e2, local_result=LOCAL, cloud_result=CLOUD)
        for r in caplog.records:
            blob = f"{r.getMessage()} {sorted(vars(r).items(), key=lambda kv: kv[0])!r}"
            for bad in (FAKE_NAME, FAKE_PLATE, FAKE_PATH, "drives a car", IMAGE):
                assert bad not in blob, (bad, r.getMessage())


class TestSettings:
    def test_from_settings(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "AI_PRIMARY", "local")
        monkeypatch.setattr(settings, "CLOUD_AUDIT_ENABLED", True)
        cfg = AuditConfig.from_settings()
        assert cfg.enabled and cfg.primary_local and cfg.daily_cap == 200
        monkeypatch.setattr(settings, "AI_PRIMARY", "cloud")
        assert AuditConfig.from_settings().primary_local is False

    def test_fallback_tracker(self):
        from app.services import local_first
        assert local_first.cloud_fallback_in_progress() is False
        with local_first.track_cloud_fallback():
            assert local_first.cloud_fallback_in_progress() is True
        assert local_first.cloud_fallback_in_progress() is False
