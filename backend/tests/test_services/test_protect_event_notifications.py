"""Push + MQTT for stored Protect events, and the doorbell / legacy-path fixes.

The Phase B refactor dropped push notifications and MQTT publishing from the
Protect path, and left two calls to handler methods that no longer exist
(``_broadcast_doorbell_ring`` on the live ring path, ``_publish_event_to_mqtt``
on the legacy AI-failure path). These tests cover the restored fan-out, the
settings it respects, and that no failure in it touches the stored event.
"""
import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uiprotect.data.types import EventType as ProtectEventType

from app.models.event import Event
from app.services.protect_event_handler import ProtectEventHandler
from app.services.protect_event_notifications import (
    EventSnapshot,
    ProtectEventNotifier,
    get_protect_event_notifier,
    load_event_snapshot,
)
from tests.conftest import make_camera, make_entity, make_event

SEND = "app.services.push_notification_service.send_event_notification"
MQTT = "app.services.mqtt_service.get_mqtt_service"
COUNTS = "app.services.mqtt_status_service.get_camera_event_counts"
ACTIVITY = "app.services.mqtt_status_service.set_activity_on"


@contextmanager
def _db(session):
    yield session


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _ok(n=2):
    return [SimpleNamespace(success=True) for _ in range(n)]


def _snap(camera_id="cam-1", ring=False, **kw):
    return EventSnapshot(
        event_id=kw.pop("event_id", "evt-1"), camera_id=camera_id, camera_name="Front Door",
        description="A person walks up to the door.", timestamp=datetime.now(timezone.utc),
        is_doorbell_ring=ring, smart_detection_type="ring" if ring else "person", **kw,
    )


def _mqtt(connected=True):
    m = MagicMock()
    m.is_connected = connected
    m.get_api_base_url.return_value = "http://argus.test"
    m.get_event_topic.side_effect = lambda cid: f"argusai/camera/{cid}/event"
    m.publish = AsyncMock(return_value=True)
    m.publish_last_event_timestamp = AsyncMock()
    m.publish_activity_state = AsyncMock()
    m.publish_event_counts = AsyncMock()
    return m


@pytest.fixture
def stored(db_session):
    camera = make_camera(db_session=db_session, name="Front Door", source_type="protect")
    alex = make_entity(db_session, entity_type="person", name="Alex", is_vip=True)
    event = make_event(
        db_session=db_session, camera_id=camera.id,
        description="Alex walks up to the front door.",
        smart_detection_type="person",
        thumbnail_path="/api/v1/thumbnails/2026-01-01/evt.jpg",
        matched_entity_ids=json.dumps([alex.id]),
        recognition_status="known", delivery_carrier="ups",
    )
    return SimpleNamespace(camera=camera, alex=alex, event=event)


class TestEventSnapshot:
    def test_reads_names_vip_and_urls(self, db_session, stored):
        snap = load_event_snapshot(db_session, stored.event.id)
        assert snap.camera_name == "Front Door"
        assert snap.entity_names == ["Alex"]
        assert snap.is_vip is True and snap.has_blocked_entity is False
        # Protect rows already store the API path; it must not be prefixed twice.
        assert snap.thumbnail_url == "/api/v1/thumbnails/2026-01-01/evt.jpg"

    def test_relative_thumbnail_is_prefixed_and_bad_ids_ignored(self, db_session, stored):
        stored.event.thumbnail_path = "2026-01-01/evt.jpg"
        stored.event.matched_entity_ids = "not json"
        db_session.commit()
        snap = load_event_snapshot(db_session, stored.event.id)
        assert snap.thumbnail_url == "/api/v1/thumbnails/2026-01-01/evt.jpg"
        assert snap.entity_names == []

    def test_missing_event(self, db_session):
        assert load_event_snapshot(db_session, "nope") is None


class TestPush:
    @pytest.mark.asyncio
    async def test_push_carries_entity_names_and_preferences_inputs(self, db_session, stored):
        notifier = ProtectEventNotifier()
        with patch(SEND, new_callable=AsyncMock, return_value=_ok()) as send:
            snap = load_event_snapshot(db_session, stored.event.id)
            assert await notifier.send_push(snap, lambda: _db(db_session)) == 2
        kw = send.call_args.kwargs
        assert kw["entity_names"] == ["Alex"] and kw["is_vip"] is True
        # camera_id + smart_detection_type drive the per-subscription preference filter.
        assert kw["camera_id"] == stored.camera.id
        assert kw["smart_detection_type"] == "person"
        assert kw["delivery_carrier_display"] == "UPS"
        assert kw["db"] is db_session

    @pytest.mark.asyncio
    async def test_camera_cooldown_limits_bursts(self, db_session):
        clock = _Clock()
        notifier = ProtectEventNotifier(push_cooldown_s=120, clock=clock)
        sf = lambda: _db(db_session)
        with patch(SEND, new_callable=AsyncMock, return_value=_ok()) as send:
            assert await notifier.send_push(_snap(), sf) == 2
            clock.t += 30
            assert await notifier.send_push(_snap(event_id="e2"), sf) == 0  # same camera
            assert await notifier.send_push(_snap("cam-2", event_id="e3"), sf) == 2  # other camera
            clock.t += 91
            assert await notifier.send_push(_snap(event_id="e4"), sf) == 2  # window passed
        assert send.await_count == 3

    @pytest.mark.asyncio
    async def test_doorbell_ring_bypasses_cooldown(self, db_session):
        notifier = ProtectEventNotifier(push_cooldown_s=120, clock=_Clock())
        sf = lambda: _db(db_session)
        with patch(SEND, new_callable=AsyncMock, return_value=_ok()) as send:
            await notifier.send_push(_snap(), sf)
            assert await notifier.send_push(_snap(ring=True, event_id="r1"), sf) == 2
        assert send.call_args.kwargs["smart_detection_type"] == "ring"

    @pytest.mark.asyncio
    async def test_nothing_sent_does_not_hold_the_window(self, db_session):
        """All subscriptions filtered by preferences (or none): next event may push."""
        notifier = ProtectEventNotifier(push_cooldown_s=120, clock=_Clock())
        sf = lambda: _db(db_session)
        with patch(SEND, new_callable=AsyncMock, side_effect=[[], _ok()]) as send:
            assert await notifier.send_push(_snap(), sf) == 0
            assert await notifier.send_push(_snap(event_id="e2"), sf) == 2
        assert send.await_count == 2

    @pytest.mark.asyncio
    async def test_blocked_entity_suppresses_push(self, db_session):
        notifier = ProtectEventNotifier()
        with patch(SEND, new_callable=AsyncMock) as send:
            assert await notifier.send_push(_snap(has_blocked_entity=True), lambda: _db(db_session)) == 0
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_error_releases_window_and_is_swallowed_by_notify(self, db_session, stored):
        notifier = ProtectEventNotifier(push_cooldown_s=120, clock=_Clock())
        with patch(SEND, new_callable=AsyncMock, side_effect=RuntimeError("vapid broke")), \
             patch(MQTT, return_value=_mqtt(connected=False)):
            await notifier.notify(stored.event.id, lambda: _db(db_session))  # must not raise
        assert stored.camera.id not in notifier._last_push_at


class TestMqtt:
    @pytest.mark.asyncio
    async def test_publishes_event_and_status_sensors(self, db_session, stored):
        mqtt = _mqtt()
        with patch(MQTT, return_value=mqtt), \
             patch(COUNTS, new_callable=AsyncMock, return_value={"events_today": 3, "events_this_week": 9}), \
             patch(ACTIVITY, new_callable=AsyncMock) as activity:
            snap = load_event_snapshot(db_session, stored.event.id)
            assert await ProtectEventNotifier().publish_mqtt(snap, lambda: _db(db_session)) is True
        topic, payload = mqtt.publish.call_args.args
        assert topic == f"argusai/camera/{stored.camera.id}/event"
        assert payload["event_id"] == stored.event.id
        mqtt.publish_last_event_timestamp.assert_awaited_once()
        mqtt.publish_activity_state.assert_awaited_once()
        activity.assert_awaited_once()
        assert mqtt.publish_event_counts.call_args.kwargs["events_today"] == 3

    @pytest.mark.asyncio
    async def test_disconnected_or_disabled_publishes_nothing(self, db_session, stored):
        mqtt = _mqtt(connected=False)
        with patch(MQTT, return_value=mqtt):
            snap = load_event_snapshot(db_session, stored.event.id)
            assert await ProtectEventNotifier().publish_mqtt(snap, lambda: _db(db_session)) is False
        mqtt.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_failing_sensor_does_not_stop_the_rest(self, db_session, stored):
        mqtt = _mqtt()
        mqtt.publish_last_event_timestamp.side_effect = RuntimeError("broker hiccup")
        with patch(MQTT, return_value=mqtt), \
             patch(COUNTS, new_callable=AsyncMock, return_value={"events_today": 1, "events_this_week": 1}), \
             patch(ACTIVITY, new_callable=AsyncMock):
            snap = load_event_snapshot(db_session, stored.event.id)
            await ProtectEventNotifier().publish_mqtt(snap, lambda: _db(db_session))
        mqtt.publish_activity_state.assert_awaited_once()
        mqtt.publish_event_counts.assert_awaited_once()


class TestIsolation:
    @pytest.mark.asyncio
    async def test_blocked_entity_still_publishes_mqtt(self, db_session, stored):
        stored.alex.is_blocked = True
        db_session.commit()
        mqtt = _mqtt()
        with patch(SEND, new_callable=AsyncMock) as send, patch(MQTT, return_value=mqtt), \
             patch(COUNTS, new_callable=AsyncMock, return_value={"events_today": 1, "events_this_week": 1}), \
             patch(ACTIVITY, new_callable=AsyncMock):
            await ProtectEventNotifier().notify(stored.event.id, lambda: _db(db_session))
        send.assert_not_awaited()
        mqtt.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hung_push_is_bounded_and_mqtt_still_publishes(self, db_session, stored):
        async def _hang(**_k):
            await asyncio.sleep(30)

        mqtt = _mqtt()
        notifier = ProtectEventNotifier(push_timeout_s=0.05)
        with patch(SEND, side_effect=_hang), patch(MQTT, return_value=mqtt), \
             patch(COUNTS, new_callable=AsyncMock, return_value={"events_today": 1, "events_this_week": 1}), \
             patch(ACTIVITY, new_callable=AsyncMock):
            await asyncio.wait_for(notifier.notify(stored.event.id, lambda: _db(db_session)), 2)
        mqtt.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mqtt_error_does_not_stop_push(self, db_session, stored):
        with patch(SEND, new_callable=AsyncMock, return_value=_ok()) as send, \
             patch(MQTT, side_effect=RuntimeError("mqtt import-time failure")):
            await ProtectEventNotifier().notify(stored.event.id, lambda: _db(db_session))
        send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_failure_and_bad_ids_are_swallowed(self):
        def _boom():
            raise RuntimeError("db down")

        notifier = ProtectEventNotifier()
        await notifier.notify("evt", _boom)
        assert notifier.schedule(None, _boom) is None
        assert notifier.schedule(MagicMock(), _boom) is None

    @pytest.mark.asyncio
    async def test_schedule_runs_in_background_and_drains(self, db_session, stored):
        notifier = ProtectEventNotifier()
        with patch(SEND, new_callable=AsyncMock, return_value=_ok()) as send, \
             patch(MQTT, return_value=_mqtt(connected=False)):
            task = notifier.schedule(stored.event.id, lambda: _db(db_session))
            assert task is not None
            await notifier.drain()
        send.assert_awaited_once()


# --------------------------------------------------------------------------
# Handler wiring
# --------------------------------------------------------------------------

def _native(event_type, smart_values=(), pid="0f0e0d0c-0000-1111-2222-333344445555"):
    ev = type("Event", (), {})()
    ev.type = event_type
    ev.camera_id = "protect-cam-door"
    ev.id = pid
    ev.start = datetime.now(timezone.utc) - timedelta(seconds=3)
    ev.end = datetime.now(timezone.utc)
    ev.metadata = None
    ev.get_thumbnail = None
    ev.smart_detect_types = [type("S", (), {"value": v})() for v in smart_values]
    return ev


class TestHandlerWiring:
    async def _run_native(self, db_session, event_obj, ai_success=True):
        camera = make_camera(
            db_session=db_session, name="Front Door", source_type="protect",
            protect_camera_id="protect-cam-door", is_enabled=True,
            smart_detection_types='["person", "vehicle", "ring"]',
        )
        handler = ProtectEventHandler()
        handler.event_filter._last_event_times.pop(camera.id, None)
        handler.ai_pipeline._last_context_bundle = None

        async def _analyze(*_a, **_k):
            if not ai_success:
                return SimpleNamespace(success=False, error="provider down", response_time_ms=5)
            return SimpleNamespace(
                success=True, description="A person rings the doorbell.", confidence=0.9,
                objects_detected=["person"], provider="test", ai_confidence=90,
                cost_estimate=0.0, identification=None, bounding_boxes=None, response_time_ms=10,
            )

        snapshot = SimpleNamespace(
            thumbnail_path="/api/v1/thumbnails/2026-01-01/door.jpg",
            timestamp=datetime.now(timezone.utc), image_base64="",
        )
        order = []

        async def _post(*_a, **_k):
            order.append("post_persist")

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.media_service, "get_media_for_event", new_callable=AsyncMock) as media, \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", side_effect=_analyze), \
             patch.object(handler, "_store_protect_embedding", new_callable=AsyncMock), \
             patch.object(handler, "_link_cross_camera_incident", new_callable=AsyncMock), \
             patch.object(handler, "_run_entity_post_persist", side_effect=_post), \
             patch.object(handler.broadcaster, "broadcast_event_created", new_callable=AsyncMock), \
             patch.object(handler.broadcaster, "broadcast_doorbell_ring", new_callable=AsyncMock) as ring, \
             patch("app.services.protect_detection_hints.fetch_event_thumbnail_bytes",
                   new_callable=AsyncMock, return_value=None), \
             patch(SEND, new_callable=AsyncMock, return_value=_ok()) as send, \
             patch(MQTT, return_value=_mqtt(connected=False)):
            media.return_value = SimpleNamespace(
                snapshot_result=snapshot, clip_path=None, fallback_reason=None, clip_plan=None,
            )
            original = handler.notifier.schedule

            def _schedule(*a, **k):
                order.append("notify")
                return original(*a, **k)

            with patch.object(handler.notifier, "schedule", side_effect=_schedule):
                result = await handler._handle_native_event("ctrl-1", event_obj)
            await handler.notifier.drain()

        db_session.expire_all()
        stored = db_session.query(Event).filter(Event.protect_event_id == event_obj.id).one_or_none()
        return SimpleNamespace(result=result, stored=stored, order=order, send=send, ring=ring)

    @pytest.mark.asyncio
    async def test_native_ring_is_stored_broadcast_and_pushed(self, db_session):
        """Before: AttributeError on ``_broadcast_doorbell_ring`` dropped every ring."""
        run = await self._run_native(db_session, _native(ProtectEventType.RING))
        assert run.result is True
        assert run.stored is not None and run.stored.is_doorbell_ring is True
        run.ring.assert_awaited_once()
        assert run.order == ["post_persist", "notify"]
        run.send.assert_awaited_once()
        assert run.send.call_args.kwargs["smart_detection_type"] == "ring"

    @pytest.mark.asyncio
    async def test_native_ai_failure_still_notifies(self, db_session):
        run = await self._run_native(
            db_session, _native(ProtectEventType.SMART_DETECT, ["person"]), ai_success=False
        )
        assert run.result is True and run.stored is not None
        assert run.order == ["post_persist", "notify"]
        run.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notifier_failure_never_drops_the_event(self, db_session):
        with patch.object(
            type(get_protect_event_notifier()), "notify",
            new_callable=AsyncMock, side_effect=RuntimeError("fan-out exploded"),
        ):
            run = await self._run_native(
                db_session, _native(ProtectEventType.SMART_DETECT, ["person"])
            )
        assert run.result is True and run.stored is not None

    @pytest.mark.asyncio
    async def test_scheduling_failure_never_drops_the_event(self, db_session):
        with patch.object(
            type(get_protect_event_notifier()), "schedule", side_effect=RuntimeError("no loop"),
        ):
            run = await self._run_native(
                db_session, _native(ProtectEventType.SMART_DETECT, ["person"])
            )
        assert run.result is True and run.stored is not None
        run.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_legacy_ai_failure_path_returns_true_and_notifies(self, db_session):
        """Before: AttributeError on ``_publish_event_to_mqtt`` after storing."""
        make_camera(
            db_session=db_session, name="Driveway", source_type="protect",
            protect_camera_id="legacy-cam", is_enabled=True,
            smart_detection_types='["person"]',
        )
        handler = ProtectEventHandler()
        handler.clear_event_tracking()
        msg = MagicMock()
        msg.new_obj = MagicMock()
        type(msg.new_obj).__name__ = "Camera"
        msg.new_obj.id = "legacy-cam"
        msg.new_obj.is_motion_currently_detected = False
        msg.new_obj.active_smart_detect_types = [SimpleNamespace(value="person")]
        msg.new_obj.last_motion = None
        msg.new_obj.last_smart_detect = None
        snapshot = SimpleNamespace(
            thumbnail_path="/api/v1/thumbnails/x.jpg",
            timestamp=datetime.now(timezone.utc), image_base64="",
        )
        stored_event = SimpleNamespace(id="legacy-evt")
        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.media_service, "get_media_for_event", new_callable=AsyncMock) as media, \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock,
                          return_value=SimpleNamespace(success=False, error="down", response_time_ms=1)), \
             patch.object(handler.storage_service, "persist_protect_event", new_callable=AsyncMock,
                          return_value=stored_event), \
             patch.object(handler, "_apply_pending_protect_update"), \
             patch.object(handler, "_link_cross_camera_incident", new_callable=AsyncMock), \
             patch.object(handler, "_run_entity_post_persist", new_callable=AsyncMock), \
             patch.object(handler.broadcaster, "broadcast_event_created", new_callable=AsyncMock), \
             patch.object(handler.notifier, "schedule") as schedule:
            media.return_value = SimpleNamespace(
                snapshot_result=snapshot, clip_path=None, fallback_reason=None, clip_plan=None,
            )
            result = await handler.handle_event("ctrl-1", msg)
        assert result is True
        schedule.assert_called_once()
        assert schedule.call_args.args[0] == "legacy-evt"
