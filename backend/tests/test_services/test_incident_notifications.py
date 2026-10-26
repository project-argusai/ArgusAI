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

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id="settings-admin", username="settings-admin", role=UserRole.ADMIN)
        try:
            client = TestClient(app)
            got = client.get("/api/v1/system/settings")
            assert got.status_code == 200, got.text[:300]
            assert got.json()["notify_per_incident"] is False
            r = client.put("/api/v1/system/settings", json={"notify_per_incident": True})
            assert r.status_code == 200 and r.json()["notify_per_incident"] is True
            provider = app.dependency_overrides.get(get_db, get_db)
            gen = provider()
            db = next(gen) if hasattr(gen, "__next__") else gen
            assert inn.notify_per_incident_enabled(db) is True
            client.put("/api/v1/system/settings", json={"notify_per_incident": False})
        finally:
            app.dependency_overrides.pop(get_current_user, None)
