"""One notification per multi-camera incident (setting ``notify_per_incident``).

Off (default): per-camera alerts exactly as today. On: the first member
pushes immediately; later members are deduped per channel (generic push,
or one alert rule) per incident. Doorbell rings bypass. A dedup error sends.
A blocked entity on any member suppresses the incident push. One update
push per incident after the combined pass, only when another camera joined.
All ids and text are synthetic.
"""
import asyncio
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.camera import Camera
from app.models.event import Event
from app.models.incident import Incident
from app.models.recognized_entity import RecognizedEntity
from app.models.system_setting import SystemSetting
from app.services import incident_notifications as inn
from app.services.protect_event_notifications import ProtectEventNotifier, load_event_snapshot

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
SEND = "app.services.push_notification_service.send_event_notification"


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _db(session):
    yield session


def _on(db, value="true"):
    db.merge(SystemSetting(key=inn.SETTING_KEY, value=value))
    db.commit()


def _camera(db, name="Cam"):
    cam = Camera(id=_uid(), name=name, type="rtsp", rtsp_url="rtsp://camera.example/s",
                 frame_rate=5, is_enabled=True)
    db.add(cam)
    db.commit()
    return cam


def _event(db, camera, group_id=None, seconds=0, description="Per-camera text.",
           ring=False, entity_ids=None):
    ev = Event(id=_uid(), camera_id=camera.id, timestamp=BASE + timedelta(seconds=seconds),
               description=description, confidence=80, objects_detected='["person"]',
               alert_triggered=False, source_type="protect", correlation_group_id=group_id,
               is_doorbell_ring=ring, smart_detection_type="ring" if ring else "person",
               matched_entity_ids=json.dumps(entity_ids) if entity_ids else None)
    db.add(ev)
    db.commit()
    return ev


def _ok(n=1):
    return [SimpleNamespace(success=True) for _ in range(n)]


async def _push(db, event_id, notifier=None):
    notifier = notifier or ProtectEventNotifier(push_cooldown_s=0)
    snap = load_event_snapshot(db, event_id)
    return await notifier.send_push(snap, lambda: _db(db))


class TestSetting:
    def test_default_off(self, db_session):
        assert inn.notify_per_incident_enabled(db_session) is False

    @pytest.mark.parametrize("value", ["", "garbage", "false", "0"])
    def test_unreadable_off(self, db_session, value):
        _on(db_session, value)
        assert inn.notify_per_incident_enabled(db_session) is False

    def test_db_error_off(self):
        class Broken:
            def get(self, *a, **k):
                raise RuntimeError("db down")
        assert inn.notify_per_incident_enabled(Broken()) is False

    def test_setting_key_matches_settings_api(self):
        from app.schemas.system import SystemSettings, SystemSettingsUpdate
        assert inn.SETTING_KEY == "settings_notify_per_incident"
        assert SystemSettings().notify_per_incident is False
        assert "notify_per_incident" in SystemSettingsUpdate.model_fields


class TestPushDedup:
    @pytest.mark.asyncio
    async def test_off_means_per_camera(self, db_session):
        gid = _uid()
        a = _event(db_session, _camera(db_session), gid, 0)
        b = _event(db_session, _camera(db_session), gid, 1)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await _push(db_session, a.id) == 1
            assert await _push(db_session, b.id) == 1
        assert send.await_count == 2

    @pytest.mark.asyncio
    async def test_on_dedups_group(self, db_session):
        _on(db_session)
        gid = _uid()
        a = _event(db_session, _camera(db_session), gid, 0)
        b = _event(db_session, _camera(db_session), gid, 1)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await _push(db_session, a.id) == 1
            assert await _push(db_session, b.id) == 0
        assert send.await_count == 1

    @pytest.mark.asyncio
    async def test_first_pushed_before_group_formed_still_holds_claim(self, db_session):
        _on(db_session)
        cam_a, cam_b = _camera(db_session), _camera(db_session)
        a = _event(db_session, cam_a, None, 0)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await _push(db_session, a.id) == 1
            gid = _uid()
            a.correlation_group_id = gid
            db_session.commit()
            b = _event(db_session, cam_b, gid, 1)
            assert await _push(db_session, b.id) == 0
        assert send.await_count == 1

    @pytest.mark.asyncio
    async def test_doorbell_bypasses(self, db_session):
        _on(db_session)
        gid = _uid()
        a = _event(db_session, _camera(db_session), gid, 0)
        ring = _event(db_session, _camera(db_session), gid, 1, ring=True)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            await _push(db_session, a.id)
            assert await _push(db_session, ring.id) == 1
        assert send.await_count == 2

    @pytest.mark.asyncio
    async def test_dedup_error_sends(self, db_session, monkeypatch):
        _on(db_session)
        gid = _uid()
        a = _event(db_session, _camera(db_session), gid, 0)
        b = _event(db_session, _camera(db_session), gid, 1)

        def boom(*a, **k):
            raise RuntimeError("claim failed")

        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            await _push(db_session, a.id)
            monkeypatch.setattr(inn, "_claim", boom)
            assert await _push(db_session, b.id) == 1
        assert send.await_count == 2

    @pytest.mark.asyncio
    async def test_blocked_member_suppresses_incident_push(self, db_session):
        _on(db_session)
        blocked = RecognizedEntity(id=_uid(), entity_type="person", name=None,
                                   reference_embedding="[]", first_seen_at=BASE,
                                   last_seen_at=BASE, is_blocked=True)
        db_session.add(blocked)
        db_session.commit()
        gid = _uid()
        _event(db_session, _camera(db_session), gid, 0, entity_ids=[blocked.id])
        b = _event(db_session, _camera(db_session), gid, 1)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await _push(db_session, b.id) == 0
        send.assert_not_called()


class TestRuleDedup:
    def test_once_per_rule_per_incident(self, db_session):
        _on(db_session)
        gid = _uid()
        a = _event(db_session, _camera(db_session), gid, 0)
        b = _event(db_session, _camera(db_session), gid, 1)
        assert inn.should_deliver(db_session, a, "rule:r1") is True
        assert inn.should_deliver(db_session, b, "rule:r1") is False
        # A different rule still fires once.
        assert inn.should_deliver(db_session, b, "rule:r2") is True

    def test_off_always_delivers(self, db_session):
        gid = _uid()
        a = _event(db_session, _camera(db_session), gid, 0)
        assert inn.should_deliver(db_session, a, "rule:r1") is True
        assert inn.should_deliver(db_session, a, "rule:r1") is True

    @pytest.mark.asyncio
    async def test_alert_engine_skips_duplicate_rule_actions(self, db_session):
        from app.services.alert_engine import AlertEngine
        _on(db_session)
        gid = _uid()
        a = _event(db_session, _camera(db_session), gid, 0)
        b = _event(db_session, _camera(db_session), gid, 1)
        rule = SimpleNamespace(id="rule-x", actions=json.dumps({"dashboard_notification": True}),
                               name="r", trigger_count=0, last_triggered_at=None)
        engine = AlertEngine(db_session)
        engine._execute_dashboard_notification = AsyncMock(return_value=True)
        engine.update_rule_triggered = lambda r: None
        engine.update_event_alert_status = lambda e, r: None
        await engine.execute_actions(a, [rule])
        await engine.execute_actions(b, [rule])
        assert engine._execute_dashboard_notification.await_count == 1


def _incident(db, gid, members, status="done", text="Combined text."):
    inc = Incident(id=gid, status=status, member_count=len(members),
                   primary_event_id=members[0].id,
                   combined_description=text if status == "done" else None)
    db.add(inc)
    db.commit()
    return inc


class TestUpdatePush:
    async def _setup(self, db, late=True):
        _on(db)
        gid = _uid()
        a = _event(db, _camera(db, "Cam A"), gid, 0, description="First camera text.")
        members = [a]
        if late:
            members.append(_event(db, _camera(db, "Cam B"), gid, 1, description="Late camera text."))
        with patch(SEND, new=AsyncMock(return_value=_ok())):
            await _push(db, a.id)
            for m in members[1:]:
                await _push(db, m.id)
        return gid, members

    @pytest.mark.asyncio
    async def test_late_joiner_one_update(self, db_session):
        gid, members = await self._setup(db_session)
        inc = _incident(db_session, gid, members)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await inn.maybe_send_update_push(db_session, inc) is True
            assert await inn.maybe_send_update_push(db_session, inc) is False
        assert send.await_count == 1
        assert send.await_args.kwargs["description"] == "Combined text."
        assert db_session.get(Incident, gid).update_pushed_at is not None

    @pytest.mark.asyncio
    async def test_concurrent_finishers_one_push(self, db_session):
        gid, members = await self._setup(db_session)
        inc = _incident(db_session, gid, members)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            results = await asyncio.gather(inn.maybe_send_update_push(db_session, inc),
                                           inn.maybe_send_update_push(db_session, inc))
        assert sorted(results) == [False, True]
        assert send.await_count == 1

    @pytest.mark.asyncio
    async def test_claim_is_conditional_update(self, db_session):
        gid, members = await self._setup(db_session)
        _incident(db_session, gid, members)
        assert inn._claim_update_push(db_session, gid) is True
        assert inn._claim_update_push(db_session, gid) is False

    @pytest.mark.asyncio
    async def test_no_late_joiner_no_update(self, db_session):
        gid, members = await self._setup(db_session, late=False)
        # Same camera second event: not another camera joining.
        cam = db_session.get(Camera, members[0].camera_id)
        members.append(_event(db_session, cam, gid, 1))
        inc = _incident(db_session, gid, members)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await inn.maybe_send_update_push(db_session, inc) is False
        send.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_uses_per_camera_text(self, db_session):
        gid, members = await self._setup(db_session)
        inc = _incident(db_session, gid, members, status="fallback")
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await inn.maybe_send_update_push(db_session, inc) is True
        assert send.await_args.kwargs["description"] == "Late camera text."

    @pytest.mark.asyncio
    async def test_off_no_update(self, db_session):
        gid, members = await self._setup(db_session)
        inc = _incident(db_session, gid, members)
        _on(db_session, "false")
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await inn.maybe_send_update_push(db_session, inc) is False
        send.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocked_member_no_update(self, db_session):
        gid, members = await self._setup(db_session)
        blocked = RecognizedEntity(id=_uid(), entity_type="person", name=None,
                                   reference_embedding="[]", first_seen_at=BASE,
                                   last_seen_at=BASE, is_blocked=True)
        db_session.add(blocked)
        members[1].matched_entity_ids = json.dumps([blocked.id])
        db_session.commit()
        inc = _incident(db_session, gid, members)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await inn.maybe_send_update_push(db_session, inc) is False
        send.assert_not_called()

    @pytest.mark.asyncio
    async def test_combined_pass_triggers_update(self, db_session, monkeypatch):
        from app.services import incident_service
        gid, members = await self._setup(db_session)
        _incident(db_session, gid, members, status="pending")
        calls = []

        async def fake_pass(db, group_id, orchestrator=None):
            return db.get(Incident, group_id)

        async def fake_update(db, incident):
            calls.append(incident.id)
            return True

        monkeypatch.setattr(incident_service, "run_combined_pass", fake_pass)
        monkeypatch.setattr(inn, "maybe_send_update_push", fake_update)
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        await incident_service._settle_then_run(gid, 0)
        assert calls == [gid]


class TestSettingsApi:
    def test_toggle_saves_through_settings_api(self):
        from fastapi.testclient import TestClient
        from app.core.database import get_db
        from main import app
        from app.api.v1.auth import get_current_user
        from app.models.user import UserRole

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.core.database import Base

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                               poolclass=StaticPool)
        Base.metadata.create_all(engine)
        TestSession = sessionmaker(bind=engine, autoflush=False)

        def _test_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _test_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id="settings-admin", username="settings-admin", role=UserRole.ADMIN)
        try:
            client = TestClient(app)
            got = client.get("/api/v1/system/settings")
            assert got.status_code == 200, got.text[:300]
            assert got.json()["notify_per_incident"] is False
            r = client.put("/api/v1/system/settings", json={"notify_per_incident": True})
            assert r.status_code == 200 and r.json()["notify_per_incident"] is True
            db = TestSession()
            try:
                assert inn.notify_per_incident_enabled(db) is True
            finally:
                db.close()
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
            engine.dispose()


class TestCleanup:
    def test_orphan_deliveries_deleted(self, db_session):
        from app.models.incident import IncidentDelivery
        from app.services.cleanup_service import CleanupService
        ev = _event(db_session, _camera(db_session), None, 0)
        db_session.add(IncidentDelivery(group_key=ev.id, channel="push", event_id=ev.id))
        db_session.add(IncidentDelivery(group_key=_uid(), channel="push", event_id=_uid()))
        db_session.commit()
        CleanupService(session_factory=lambda: db_session)._delete_orphan_dependent_rows(db_session)
        db_session.commit()
        assert [d.group_key for d in db_session.query(IncidentDelivery).all()] == [ev.id]


class TestClaimReview:
    """Gracie's #724 review: claim race, shared-session safety, push errors."""

    @pytest.fixture
    def two_sessions(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.database import Base

        engine = create_engine(f"sqlite:///{tmp_path / 'claims.db'}",
                               connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        make = sessionmaker(bind=engine, autoflush=False)
        s1, s2 = make(), make()
        yield s1, s2
        s1.close()
        s2.close()
        engine.dispose()

    def test_two_sessions_only_one_member_wins(self, two_sessions):
        s1, s2 = two_sessions
        _on(s1)
        cam_a, cam_b, cam_c = _camera(s1), _camera(s1), _camera(s1)
        a = _event(s1, cam_a, None, 0)
        assert inn.should_deliver(s1, a, "push") is True
        gid = _uid()
        a.correlation_group_id = gid
        s1.commit()
        b = _event(s1, cam_b, gid, 1)
        c = _event(s1, cam_c, gid, 2)
        b2 = s2.get(Event, b.id)
        c1 = s1.get(Event, c.id)
        assert inn.should_deliver(s2, b2, "push") is False
        assert inn.should_deliver(s1, c1, "push") is False
        from app.models.incident import IncidentDelivery
        rows = s2.query(IncidentDelivery).filter_by(group_key=gid, channel="push").all()
        assert [r.event_id for r in rows] == [a.id]

    def test_two_sessions_new_group_one_winner(self, two_sessions):
        s1, s2 = two_sessions
        _on(s1)
        gid = _uid()
        b = _event(s1, _camera(s1), gid, 0)
        c = _event(s1, _camera(s1), gid, 1)
        results = [inn.should_deliver(s1, s1.get(Event, b.id), "push"),
                   inn.should_deliver(s2, s2.get(Event, c.id), "push")]
        assert sorted(results) == [False, True]

    def test_claim_does_not_commit_or_roll_back_caller_session(self, db_session):
        _on(db_session)
        gid = _uid()
        a = _event(db_session, _camera(db_session), gid, 0)
        b = _event(db_session, _camera(db_session), gid, 1)
        pending = SystemSetting(key="caller_pending_work", value="x")
        db_session.add(pending)
        with patch.object(db_session, "commit", side_effect=AssertionError("commit")), \
                patch.object(db_session, "rollback", side_effect=AssertionError("rollback")):
            assert inn.should_deliver(db_session, a, "push") is True
            assert inn.should_deliver(db_session, b, "push") is False
        assert pending in db_session.new

    @pytest.mark.asyncio
    async def test_update_push_error_returns_false(self, db_session):
        gid, members = await TestUpdatePush()._setup(db_session)
        inc = _incident(db_session, gid, members)
        with patch(SEND, new=AsyncMock(side_effect=RuntimeError("down"))):
            assert await inn.maybe_send_update_push(db_session, inc) is False

    @pytest.mark.asyncio
    async def test_failed_pass_sends_update_with_per_camera_text(self, db_session):
        gid, members = await TestUpdatePush()._setup(db_session)
        inc = _incident(db_session, gid, members, status="failed")
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await inn.maybe_send_update_push(db_session, inc) is True
        assert send.await_args.kwargs["description"] == "Late camera text."

    def test_bool_setting_stored_lowercase(self, db_session):
        from app.api.v1.system import _set_setting_in_db
        _set_setting_in_db(db_session, inn.SETTING_KEY, True)
        assert db_session.get(SystemSetting, inn.SETTING_KEY).value == "true"
        assert inn.notify_per_incident_enabled(db_session) is True
        _set_setting_in_db(db_session, inn.SETTING_KEY, False)
        assert db_session.get(SystemSetting, inn.SETTING_KEY).value == "false"
        assert inn.notify_per_incident_enabled(db_session) is False

    @pytest.mark.asyncio
    async def test_failed_pass_triggers_update_push(self, db_session, monkeypatch):
        from app.services import incident_service
        gid, members = await TestUpdatePush()._setup(db_session)
        _incident(db_session, gid, members, status="pending")
        calls = []

        async def boom(db, group_id, orchestrator=None):
            raise RuntimeError("internal")

        async def fake_update(db, incident):
            calls.append((incident.id, incident.status))
            return True

        monkeypatch.setattr(incident_service, "run_combined_pass", boom)
        monkeypatch.setattr(inn, "maybe_send_update_push", fake_update)
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        await incident_service._settle_then_run(gid, 0)
        assert calls == [(gid, "failed")]


class TestClaimAfterGrouping:
    """#724 M1 follow-up: grouped and ungrouped claims must collide on one key.

    Two real sessions on a file-backed SQLite DB. The claim never waits:
    correlation runs inline before it, and an event with no group (or a
    failed correlation) claims on its own id and sends.
    """

    @pytest.fixture
    def two(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.database import Base

        engine = create_engine(f"sqlite:///{tmp_path / 'm1.db'}",
                               connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        make = sessionmaker(bind=engine, autoflush=False)
        s1, s2 = make(), make()
        _on(s1)
        yield s1, s2
        s1.close()
        s2.close()
        engine.dispose()

    @staticmethod
    def _group(session, gid, *events):
        for ev in events:
            session.query(Event).filter(Event.id == ev.id).update({"correlation_group_id": gid})
        session.commit()

    @staticmethod
    def _rows(session, gid):
        from app.models.incident import IncidentDelivery
        session.expire_all()
        return session.query(IncidentDelivery).filter_by(group_key=gid, channel="push").all()

    def test_grouped_claims_first_then_stale_ungrouped_loses(self, two):
        s1, s2 = two
        a = _event(s1, _camera(s1), None, 0)
        b = _event(s1, _camera(s1), None, 1)
        a_stale = s2.get(Event, a.id)  # s2 still thinks A is ungrouped
        gid = _uid()
        self._group(s1, gid, a, b)
        s1.refresh(b)
        assert inn.should_deliver(s1, b, "push") is True
        assert a_stale.correlation_group_id is None
        assert inn.should_deliver(s2, a_stale, "push") is False

    def test_ungrouped_first_then_grouped_loses(self, two):
        s1, s2 = two
        a = _event(s1, _camera(s1), None, 0)
        assert inn.should_deliver(s1, a, "push") is True
        b = _event(s2, _camera(s2), None, 1)
        gid = _uid()
        self._group(s2, gid, s2.get(Event, a.id), b)
        s2.refresh(b)
        assert inn.should_deliver(s2, b, "push") is False

    def test_interleaved_mid_claim_one_winner(self, two, monkeypatch):
        """A reads 'no group'; before A inserts, B groups A+B and claims."""
        s1, s2 = two
        a = _event(s1, _camera(s1), None, 0)
        b = _event(s2, _camera(s2), None, 1)
        gid = _uid()
        real = inn._insert_claim
        fired = []

        def racing_insert(session, key, channel, event_id):
            if event_id == a.id and not fired:
                fired.append(1)
                self._group(s2, gid, s2.get(Event, a.id), b)
                s2.refresh(b)
                results.append(inn.should_deliver(s2, b, "push"))
            return real(session, key, channel, event_id)

        results = []
        monkeypatch.setattr(inn, "_insert_claim", racing_insert)
        results.insert(0, inn.should_deliver(s1, a, "push"))
        assert sorted(results) == [False, True]
        assert len(self._rows(s1, gid)) == 1

    def test_two_early_ungrouped_then_grouped(self, two):
        s1, s2 = two
        a = _event(s1, _camera(s1), None, 0)
        c = _event(s2, _camera(s2), None, 1)
        assert inn.should_deliver(s1, a, "push") is True
        assert inn.should_deliver(s2, c, "push") is True  # separate at send time
        gid = _uid()
        d = _event(s1, _camera(s1), None, 2)
        self._group(s1, gid, a, s1.get(Event, c.id), d)
        s1.refresh(d)
        assert inn.should_deliver(s1, d, "push") is False
        assert inn.should_deliver(s2, s2.get(Event, d.id), "push") is False
        assert [r.event_id for r in self._rows(s2, gid)] == [a.id]

    def test_concurrent_threads_one_winner(self, two):
        import threading
        s1, s2 = two
        gid = _uid()
        a = _event(s1, _camera(s1), None, 0)
        b = _event(s1, _camera(s1), None, 1)
        self._group(s1, gid, a, b)
        evs = {s1: s1.get(Event, a.id), s2: s2.get(Event, b.id)}
        s1.refresh(evs[s1])
        barrier = threading.Barrier(2)
        out = []

        def run(sess):
            barrier.wait()
            out.append(inn.should_deliver(sess, evs[sess], "push"))

        threads = [threading.Thread(target=run, args=(s,)) for s in (s1, s2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(out) == [False, True]

    @pytest.mark.asyncio
    async def test_first_alert_adds_no_wait(self, db_session, monkeypatch):
        _on(db_session)
        a = _event(db_session, _camera(db_session), None, 0)
        sleeps = []
        real_sleep = asyncio.sleep

        async def spy(delay, *args, **kw):
            sleeps.append(delay)
            return await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", spy)
        loop = asyncio.get_running_loop()
        start = loop.time()
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await _push(db_session, a.id) == 1
        assert (loop.time() - start) < 0.5
        assert not [d for d in sleeps if d and d > 0]
        send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_correlation_failure_claims_on_event_id_and_sends(self, db_session):
        from app.services.protect_event_handler import ProtectEventHandler
        from app.models.incident import IncidentDelivery
        _on(db_session)
        a = _event(db_session, _camera(db_session), None, 0)
        with patch("app.services.correlation_service.get_correlation_service") as gcs:
            gcs.return_value.assign_group = AsyncMock(side_effect=asyncio.TimeoutError())
            await ProtectEventHandler._link_cross_camera_incident(
                SimpleNamespace(), db_session, a)
        with patch(SEND, new=AsyncMock(return_value=_ok())) as send:
            assert await _push(db_session, a.id) == 1
        send.assert_awaited_once()
        row = db_session.query(IncidentDelivery).filter_by(channel="push").one()
        assert row.group_key == a.id

    def _terry_order(self, s1, s2, channel_call):
        """Terry's ordering: (1) A loaded ungrouped and passes the gate,
        (2) B joins group G and claims G first, (3) A claims with its stale
        ungrouped object. Exactly one may win."""
        a = _event(s1, _camera(s1), None, 0)
        a_stale = s1.get(Event, a.id)                     # step 1: group is None
        assert a_stale.correlation_group_id is None
        b = _event(s2, _camera(s2), None, 1)
        gid = _uid()
        self._group(s2, gid, s2.get(Event, a.id), b)      # step 2: G forms
        s2.refresh(b)
        first = channel_call(s2, b)
        assert a_stale.correlation_group_id is None       # still stale in s1
        second = channel_call(s1, a_stale)                # step 3
        return first, second

    def test_terry_order_push_path(self, two):
        s1, s2 = two
        b_won, a_won = self._terry_order(s1, s2, lambda s, e: inn.should_deliver(s, e, "push"))
        assert (b_won, a_won) == (True, False)

    @pytest.mark.asyncio
    async def test_terry_order_alert_rule_path(self, two):
        from app.services.alert_engine import AlertEngine
        s1, s2 = two
        rule = SimpleNamespace(id="rule-t", actions=json.dumps({"dashboard_notification": True}),
                               name="r", trigger_count=0, last_triggered_at=None)
        engines = {}

        def engine_for(s):
            if s not in engines:
                e = AlertEngine(s)
                e._execute_dashboard_notification = AsyncMock(return_value=True)
                e.update_rule_triggered = lambda r: None
                e.update_event_alert_status = lambda ev, r: None
                engines[s] = e
            return engines[s]

        calls = []

        def via_engine(s, ev):
            calls.append((s, ev))
            return None

        self._terry_order(s1, s2, via_engine)
        # Replay the same ordering through AlertEngine (shared, stale self.db).
        (sb, b), (sa, a_stale) = calls
        from app.models.incident import IncidentDelivery
        sb.query(IncidentDelivery).delete()
        sb.commit()
        await engine_for(sb).execute_actions(b, [rule])
        await engine_for(sa).execute_actions(a_stale, [rule])
        total = sum(e._execute_dashboard_notification.await_count for e in engines.values())
        assert total == 1


class TestTerryLows:
    def test_notify_per_incident_strict_bool(self):
        from pydantic import ValidationError
        from app.schemas.system import SystemSettingsUpdate
        assert SystemSettingsUpdate(notify_per_incident=True).notify_per_incident is True
        for bad in ("yes", 1, "true"):
            with pytest.raises(ValidationError):
                SystemSettingsUpdate(notify_per_incident=bad)

    @pytest.mark.asyncio
    async def test_definite_send_failure_retries_exactly_once(self, db_session):
        gid, members = await TestUpdatePush()._setup(db_session)
        inc = _incident(db_session, gid, members)
        failed = [SimpleNamespace(success=False)]
        with patch(SEND, new=AsyncMock(return_value=failed)) as send:
            assert await inn.maybe_send_update_push(db_session, inc) is False  # try
            assert await inn.maybe_send_update_push(db_session, inc) is False  # one retry
            assert await inn.maybe_send_update_push(db_session, inc) is False  # capped
            assert await inn.maybe_send_update_push(db_session, inc) is False
        assert send.await_count == 2
        db_session.expire_all()
        assert db_session.get(Incident, gid).update_pushed_at is not None

    @pytest.mark.asyncio
    async def test_definite_failure_then_retry_succeeds(self, db_session):
        gid, members = await TestUpdatePush()._setup(db_session)
        inc = _incident(db_session, gid, members)
        with patch(SEND, new=AsyncMock(side_effect=[[SimpleNamespace(success=False)], _ok()])) as send:
            assert await inn.maybe_send_update_push(db_session, inc) is False
            assert await inn.maybe_send_update_push(db_session, inc) is True
            assert await inn.maybe_send_update_push(db_session, inc) is False
        assert send.await_count == 2

    @pytest.mark.asyncio
    async def test_ambiguous_exception_never_resends(self, db_session):
        gid, members = await TestUpdatePush()._setup(db_session)
        inc = _incident(db_session, gid, members)
        with patch(SEND, new=AsyncMock(side_effect=RuntimeError("after send?"))) as send:
            assert await inn.maybe_send_update_push(db_session, inc) is False
            assert await inn.maybe_send_update_push(db_session, inc) is False
        assert send.await_count == 1
        db_session.expire_all()
        assert db_session.get(Incident, gid).update_pushed_at is not None

    @pytest.mark.asyncio
    async def test_failure_path_calls_update_push_once(self, db_session, monkeypatch):
        from app.services import incident_service
        gid, members = await TestUpdatePush()._setup(db_session)
        _incident(db_session, gid, members, status="pending")
        calls = []

        async def ok_pass(db, group_id, orchestrator=None):
            inc = db.get(Incident, group_id)
            inc.status = "failed"
            db.commit()
            return inc

        async def raising_update(db, incident):
            calls.append(incident.id)
            raise RuntimeError("push gate blew up")

        monkeypatch.setattr(incident_service, "run_combined_pass", ok_pass)
        monkeypatch.setattr(inn, "maybe_send_update_push", raising_update)
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        await incident_service._settle_then_run(gid, 0)
        assert calls == [gid]
