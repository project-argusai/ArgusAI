"""Local vision model fallback (Ollama or another OpenAI-compatible server).

Events whose cloud analysis failed were stored as "AI analysis unavailable"
for good. The local fallback re-describes them in the background after the
event is stored and notified. These tests cover the provider, the opt-in and
loopback-only config, the bounded queue and time budget, the row update, the
alert-rule re-run, and that nothing here can delay or drop an event.
"""
import asyncio
import base64
import io
import json
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from uiprotect.data.types import EventType as ProtectEventType

from app.models.event import Event
from app.models.notification import Notification
from app.models.recognized_entity import EntityEvent
from app.services.ai_providers.local_provider import (
    LOCAL_PROVIDER_NAME,
    LocalVLMProvider,
    downscale_image_base64,
)
from app.services.ai_providers.quota_aware_client import LOCAL_PROVIDER_API_KEY
from app.services.ai_types import AIResult
from app.services.local_vlm_fallback import (
    UNAVAILABLE_DESCRIPTION,
    LocalVLMConfig,
    LocalVLMFallbackService,
    RedescribeJob,
    is_loopback_host,
    reset_local_vlm_fallback_service,
)
from app.services.protect_event_handler import ProtectEventHandler
from tests.conftest import make_alert_rule, make_camera, make_entity, make_event

SEND = "app.services.push_notification_service.send_event_notification"
MQTT = "app.services.mqtt_service.get_mqtt_service"
GET_SERVICE = "app.services.local_vlm_fallback.get_local_vlm_fallback_service"

REPLY = json.dumps({
    "description": "At 9:31 AM a red BMW X3 pulls into the driveway and parks near the house.",
    "object_type": "vehicle",
    "count": 1,
    "identity": "unknown",
    "action": "parks",
    "direction": "left",
    "package_or_carrier": "none",
    "confidence": 82,
})


@contextmanager
def _db(session):
    yield session


@pytest.fixture(autouse=True)
def _reset_service():
    reset_local_vlm_fallback_service()
    yield
    reset_local_vlm_fallback_service()


def _jpeg_b64(w=1920, h=1080) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 30, 30)).save(buf, "JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _completion(content=REPLY):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=1900, prompt_tokens=1800, completion_tokens=100),
    )


def _ok_result(description="At 9:31 AM a red BMW X3 pulls into the driveway.") -> AIResult:
    return AIResult(
        description=description, confidence=82, objects_detected=["vehicle"],
        provider=LOCAL_PROVIDER_NAME, tokens_used=10, response_time_ms=8000,
        cost_estimate=0.0, success=True, ai_confidence=82,
        identification={"object_type": "vehicle", "count": 1, "identity": "unknown"},
    )


class _FakeProvider:
    def __init__(self, result=None, delay=0.0, exc=None):
        self.result = result or _ok_result()
        self.delay = delay
        self.exc = exc
        self.calls = []

    async def generate_description(self, image_base64, camera_name, timestamp, detected_objects, **kw):
        self.calls.append(dict(image=image_base64, camera=camera_name, ts=timestamp, **kw))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.result


def _enabled(**kw) -> LocalVLMConfig:
    return LocalVLMConfig(enabled=True, **kw)


def _service(db_session, provider, **cfg) -> LocalVLMFallbackService:
    return LocalVLMFallbackService(
        config=_enabled(**cfg), provider=provider, session_factory=lambda: _db(db_session)
    )


def _placeholder_event(db_session, **kw):
    camera = make_camera(db_session=db_session, name="Driveway", source_type="protect")
    return make_event(
        db_session=db_session, camera_id=camera.id, description=UNAVAILABLE_DESCRIPTION,
        confidence=0, objects_detected='["vehicle"]', smart_detection_type="vehicle",
        provider_used=None, **kw,
    )


def _job(event, **kw):
    data = dict(
        event_id=event.id, image_base64=_jpeg_b64(), camera_id=event.camera_id,
        camera_name="Driveway", event_type="vehicle", local_timestamp="9:31 AM",
    )
    data.update(kw)
    return RedescribeJob(**data)


# --------------------------------------------------------------------------
# Provider
# --------------------------------------------------------------------------

class TestLocalVLMProvider:
    @pytest.mark.asyncio
    async def test_sends_prompt_and_image_and_parses_identification(self):
        provider = LocalVLMProvider("http://127.0.0.1:11434/v1", "qwen3-vl:4b-instruct")
        provider.client = MagicMock()
        provider.client.chat.completions.create = AsyncMock(return_value=_completion())

        result = await provider.generate_description(
            _jpeg_b64(320, 180), "Driveway", "9:31 AM", [], custom_prompt="PROMPT", request_timeout_s=42,
        )

        assert result.success is True
        assert result.provider == "local" and result.cost_estimate == 0.0
        assert "red BMW X3" in result.description
        assert result.identification["object_type"] == "vehicle"
        kw = provider.client.chat.completions.create.call_args.kwargs
        assert kw["model"] == "qwen3-vl:4b-instruct"
        assert kw["timeout"] == 42
        assert kw["response_format"] == {"type": "json_object"}
        user = kw["messages"][1]["content"]
        assert user[0] == {"type": "text", "text": "PROMPT"}
        assert user[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    @pytest.mark.asyncio
    async def test_large_images_are_downscaled_before_sending(self):
        provider = LocalVLMProvider("http://127.0.0.1:11434/v1", "m", max_image_side=512)
        provider.client = MagicMock()
        provider.client.chat.completions.create = AsyncMock(return_value=_completion())
        await provider.generate_description(_jpeg_b64(1920, 1080), "Driveway", "t", [])
        url = provider.client.chat.completions.create.call_args.kwargs["messages"][1]["content"][1]["image_url"]["url"]
        sent = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
        assert max(sent.size) == 512

    def test_small_image_is_left_unchanged(self):
        small = _jpeg_b64(320, 180)
        assert downscale_image_base64(small, 1024) == small

    @pytest.mark.asyncio
    async def test_errors_and_empty_replies_return_a_failed_result(self):
        provider = LocalVLMProvider("http://127.0.0.1:11434/v1", "m")
        provider.client = MagicMock()
        provider.client.chat.completions.create = AsyncMock(side_effect=ConnectionError("refused"))
        failed = await provider.generate_description(_jpeg_b64(64, 64), "c", "t", [])
        assert failed.success is False and failed.error.startswith("ConnectionError")

        provider.client.chat.completions.create = AsyncMock(return_value=_completion(content=""))
        empty = await provider.generate_description(_jpeg_b64(64, 64), "c", "t", [])
        assert empty.success is False

    def test_client_targets_only_the_configured_url_without_a_key_or_retries(self):
        provider = LocalVLMProvider("http://127.0.0.1:11434/v1", "m")
        assert str(provider.client.base_url).startswith("http://127.0.0.1:11434/v1")
        assert provider.client.max_retries == 0
        assert provider.client.api_key == LOCAL_PROVIDER_API_KEY

    @pytest.mark.asyncio
    async def test_a_stopped_server_fails_fast(self):
        # Port 9 (discard) is closed on CI runners and dev machines.
        provider = LocalVLMProvider("http://127.0.0.1:9/v1", "m")
        start = time.monotonic()
        result = await provider.generate_description(_jpeg_b64(64, 64), "c", "t", [], request_timeout_s=5)
        assert result.success is False
        assert time.monotonic() - start < 5


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

class TestConfig:
    def test_off_by_default(self):
        from app.core.config import settings

        assert settings.LOCAL_VLM_ENABLED is False
        service = LocalVLMFallbackService()
        assert service.enabled is False and service.disabled_reason == "disabled"
        assert service.schedule(RedescribeJob("e", "x", None, "c", "vehicle")) is False

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:11434/v1", "http://localhost:11434/v1", "http://[::1]:11434/v1",
        "https://127.0.0.2:8443/v1",
    ])
    def test_loopback_urls_are_accepted(self, url):
        assert _enabled(base_url=url).problem() is None

    @pytest.mark.parametrize("url,reason", [
        ("http://192.0.2.20:11434/v1", "not loopback"),
        ("http://ollama.example.com/v1", "not loopback"),
        ("ftp://127.0.0.1/v1", "http(s)"),
        ("127.0.0.1:11434", "http(s)"),
        ("http://user:pw@127.0.0.1:11434/v1", "credentials"),
    ])
    def test_unsafe_urls_disable_the_fallback(self, url, reason):
        problem = _enabled(base_url=url).problem()
        assert problem and reason in problem

    def test_remote_needs_explicit_opt_in(self):
        assert _enabled(base_url="http://198.51.100.5:11434/v1", allow_remote=True).problem() is None

    def test_missing_model_disables(self):
        assert "model" in _enabled(model="").problem()

    def test_loopback_helper(self):
        assert is_loopback_host("LOCALHOST.") and is_loopback_host("127.8.9.10")
        assert not is_loopback_host("localhost.evil.com") and not is_loopback_host("")


# --------------------------------------------------------------------------
# Background job
# --------------------------------------------------------------------------

class TestBackgroundRedescribe:
    @pytest.mark.asyncio
    async def test_fills_the_placeholder_links_entities_and_fires_only_new_rules(self, db_session):
        bmw = make_entity(db_session, entity_type="vehicle", name="Sam's BMW",
                          vehicle_make="bmw", vehicle_model="x3", vehicle_color="red")
        fired = make_alert_rule(db_session, name="Any vehicle (already fired)",
                                conditions={"object_types": ["vehicle"]}, cooldown_minutes=0)
        new = make_alert_rule(db_session, name="Vehicle, second rule",
                              conditions={"object_types": ["vehicle"]}, cooldown_minutes=0)
        event = _placeholder_event(db_session, alert_triggered=True, alert_rule_ids=json.dumps([fired.id]))

        def fields(result, db):
            result.description = "At 9:31 AM Sam's BMW pulls into the driveway."
            return {"enriched_description": result.description,
                    "matched_entity_ids": json.dumps([bmw.id]), "recognition_status": "known"}

        provider = _FakeProvider()
        service = _service(db_session, provider)
        assert service.schedule(_job(event, fields_builder=fields)) is True
        await service.drain()

        db_session.expire_all()
        row = db_session.get(Event, event.id)
        assert row.description == "At 9:31 AM Sam's BMW pulls into the driveway."
        assert row.provider_used == "local" and row.ai_fallback_used is True
        assert row.ai_confidence == 82 and row.recognition_status == "known"
        assert json.loads(row.objects_detected) == ["vehicle"]
        assert json.loads(row.identification)["object_type"] == "vehicle"
        assert db_session.query(EntityEvent).filter_by(event_id=event.id, entity_id=bmw.id).count() == 1
        assert json.loads(row.alert_rule_ids) == [fired.id, new.id]
        notes = db_session.query(Notification).filter_by(event_id=event.id).all()
        assert [n.rule_id for n in notes] == [new.id]
        assert service.stats["applied"] == 1
        # Same prompt the live path builds, with the camera and local time.
        assert "Camera/location: Driveway" in provider.calls[0]["custom_prompt"]
        assert "Local time: 9:31 AM" in provider.calls[0]["custom_prompt"]

    @pytest.mark.asyncio
    async def test_never_overwrites_an_event_that_was_already_described(self, db_session):
        event = _placeholder_event(db_session)
        event.description = "Manual re-analysis text"
        event.provider_used = "grok"
        db_session.commit()
        service = _service(db_session, _FakeProvider())
        service.schedule(_job(event))
        await service.drain()
        db_session.expire_all()
        row = db_session.get(Event, event.id)
        assert row.description == "Manual re-analysis text" and row.provider_used == "grok"
        assert service.stats["skipped_already_described"] == 1

    @pytest.mark.asyncio
    async def test_timeout_or_error_leaves_the_placeholder(self, db_session):
        event = _placeholder_event(db_session)
        slow = _service(db_session, _FakeProvider(delay=5), timeout_ms=100)
        slow.schedule(_job(event))
        start = time.monotonic()
        await slow.drain()
        assert time.monotonic() - start < 4
        broken = _service(db_session, _FakeProvider(exc=RuntimeError("boom")))
        broken.schedule(_job(event))
        await broken.drain()
        db_session.expire_all()
        row = db_session.get(Event, event.id)
        assert row.description == UNAVAILABLE_DESCRIPTION and row.provider_used is None
        assert slow.stats["failed"] == 1 and broken.stats["failed"] == 1

    @pytest.mark.asyncio
    async def test_schedule_returns_immediately_and_the_queue_is_bounded(self, db_session):
        event = _placeholder_event(db_session)
        provider = _FakeProvider(delay=0.3)
        service = _service(db_session, provider, max_pending=1)
        start = time.monotonic()
        assert service.schedule(_job(event)) is True
        assert time.monotonic() - start < 0.1
        assert service.schedule(_job(event)) is False
        assert service.stats["skipped_queue_full"] == 1
        await service.drain()
        assert service.pending == 0
        assert service.schedule(_job(event)) is True
        await service.drain()

    @pytest.mark.asyncio
    async def test_calls_run_one_at_a_time(self, db_session):
        events = [_placeholder_event(db_session) for _ in range(3)]
        active = {"now": 0, "max": 0}

        class _Counting(_FakeProvider):
            async def generate_description(self, *a, **kw):
                active["now"] += 1
                active["max"] = max(active["max"], active["now"])
                await asyncio.sleep(0.05)
                active["now"] -= 1
                return _ok_result()

        service = _service(db_session, _Counting())
        for ev in events:
            service.schedule(_job(ev))
        await service.drain()
        assert active["max"] == 1 and service.stats["applied"] == 3

    @pytest.mark.asyncio
    async def test_stale_jobs_are_skipped(self, db_session):
        event = _placeholder_event(db_session)
        provider = _FakeProvider()
        service = _service(db_session, provider)
        service.schedule(_job(event, created_monotonic=time.monotonic() - 3600))
        await service.drain()
        assert provider.calls == [] and service.stats["skipped_stale"] == 1

    @pytest.mark.asyncio
    async def test_image_is_downscaled_before_the_provider_sees_it(self, db_session):
        event = _placeholder_event(db_session)
        provider = _FakeProvider()
        service = _service(db_session, provider, max_image_side=640)
        service.schedule(_job(event))
        await service.drain()
        sent = Image.open(io.BytesIO(base64.b64decode(provider.calls[0]["image"])))
        assert max(sent.size) == 640

    @pytest.mark.asyncio
    async def test_naming_failure_still_stores_the_description(self, db_session):
        event = _placeholder_event(db_session)

        def broken(result, db):
            raise RuntimeError("naming exploded")

        service = _service(db_session, _FakeProvider())
        service.schedule(_job(event, fields_builder=broken))
        await service.drain()
        db_session.expire_all()
        assert db_session.get(Event, event.id).provider_used == "local"


# --------------------------------------------------------------------------
# Handler wiring
# --------------------------------------------------------------------------

def _native(event_type, smart_values=(), pid="0f0e0d0c-0000-1111-2222-333344445555"):
    ev = type("Event", (), {})()
    ev.type = event_type
    ev.camera_id = "protect-cam-drive"
    ev.id = pid
    ev.start = datetime.now(timezone.utc) - timedelta(seconds=3)
    ev.end = datetime.now(timezone.utc)
    ev.metadata = None
    ev.get_thumbnail = None
    ev.smart_detect_types = [type("S", (), {"value": v})() for v in smart_values]
    return ev


class TestHandlerWiring:
    async def _run(self, db_session, service, ai_success=False):
        camera = make_camera(
            db_session=db_session, name="Driveway", source_type="protect",
            protect_camera_id="protect-cam-drive", is_enabled=True,
            smart_detection_types='["person", "vehicle"]',
        )
        handler = ProtectEventHandler()
        handler.event_filter._last_event_times.pop(camera.id, None)
        bundle = SimpleNamespace(
            custom_prompt="BASE PROMPT", local_timestamp="9:31 AM",
            named_identities=[], embedding_vector=None, context_stats=None, context_included=False,
        )

        async def _analyze(*_a, **_k):
            handler.ai_pipeline._last_context_bundle = bundle
            if not ai_success:
                return SimpleNamespace(success=False, error="grok:timeout", response_time_ms=5000)
            return SimpleNamespace(
                success=True, description="A red car parks.", confidence=80,
                objects_detected=["vehicle"], provider="grok", ai_confidence=80,
                cost_estimate=0.0, identification=None, bounding_boxes=None, response_time_ms=10,
            )

        snapshot = SimpleNamespace(
            thumbnail_path="/api/v1/thumbnails/2026-01-01/drive.jpg",
            timestamp=datetime.now(timezone.utc), image_base64="SNAPSHOT-B64",
        )
        order = []

        async def _post(*_a, **_k):
            order.append("post_persist")

        original_schedule = handler.notifier.schedule

        def _notify(*a, **k):
            order.append("notify")
            return original_schedule(*a, **k)

        def _vlm(job):
            order.append("local_vlm")
            return service.schedule_impl(job)

        service.schedule = MagicMock(side_effect=_vlm)
        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch(GET_SERVICE, return_value=service), \
             patch.object(handler.media_service, "get_media_for_event", new_callable=AsyncMock) as media, \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", side_effect=_analyze), \
             patch.object(handler, "_store_protect_embedding", new_callable=AsyncMock), \
             patch.object(handler, "_link_cross_camera_incident", new_callable=AsyncMock), \
             patch.object(handler, "_run_entity_post_persist", side_effect=_post), \
             patch.object(handler.broadcaster, "broadcast_event_created", new_callable=AsyncMock), \
             patch("app.services.protect_detection_hints.fetch_event_thumbnail_bytes",
                   new_callable=AsyncMock, return_value=None), \
             patch(SEND, new_callable=AsyncMock, return_value=[]), \
             patch(MQTT, return_value=MagicMock(is_connected=False)), \
             patch.object(handler.notifier, "schedule", side_effect=_notify):
            media.return_value = SimpleNamespace(
                snapshot_result=snapshot, clip_path=None, fallback_reason=None, clip_plan=None,
            )
            result = await handler._handle_native_event(
                "ctrl-1", _native(ProtectEventType.SMART_DETECT, ["vehicle"])
            )
            await handler.notifier.drain()
        db_session.expire_all()
        stored = db_session.query(Event).filter(Event.protect_event_id.isnot(None)).one_or_none()
        return SimpleNamespace(result=result, stored=stored, order=order, bundle=bundle)

    def _fake_service(self, enabled=True, schedule=None):
        service = SimpleNamespace(enabled=enabled)
        service.schedule_impl = schedule or (lambda job: True)
        return service

    @pytest.mark.asyncio
    async def test_failed_event_is_handed_over_after_it_is_stored_and_notified(self, db_session):
        service = self._fake_service()
        run = await self._run(db_session, service)
        assert run.result is True and run.stored.description == UNAVAILABLE_DESCRIPTION
        assert run.order == ["post_persist", "notify", "local_vlm"]
        job = service.schedule.call_args.args[0]
        assert job.event_id == run.stored.id
        assert job.image_base64 == "SNAPSHOT-B64"
        assert job.camera_name == "Driveway" and job.event_type == "vehicle"
        assert job.custom_prompt == "BASE PROMPT" and job.local_timestamp == "9:31 AM"
        # The naming step uses this event's own pre-AI context, not later state.
        with patch.object(ProtectEventHandler, "_post_ai_context_fields", return_value={}) as fields:
            job.fields_builder(_ok_result(), db_session)
        assert fields.call_args.kwargs["bundle"] is run.bundle

    @pytest.mark.asyncio
    async def test_disabled_fallback_is_not_scheduled(self, db_session):
        service = self._fake_service(enabled=False)
        run = await self._run(db_session, service)
        assert run.result is True and "local_vlm" not in run.order

    @pytest.mark.asyncio
    async def test_successful_cloud_analysis_is_not_scheduled(self, db_session):
        service = self._fake_service()
        run = await self._run(db_session, service, ai_success=True)
        assert run.result is True and "local_vlm" not in run.order

    @pytest.mark.asyncio
    async def test_scheduling_errors_never_drop_the_event(self, db_session):
        def _boom(job):
            raise RuntimeError("scheduler exploded")

        run = await self._run(db_session, self._fake_service(schedule=_boom))
        assert run.result is True and run.stored is not None


class TestReplyWithoutDescription:
    """A 4B model dropped ``description`` on about half of empty-scene replies."""

    async def _ask(self, content):
        provider = LocalVLMProvider("http://127.0.0.1:11434/v1", "m")
        provider.client = MagicMock()
        provider.client.chat.completions.create = AsyncMock(return_value=_completion(content=content))
        return await provider.generate_description(_jpeg_b64(64, 64), "c", "t", [])

    @pytest.mark.asyncio
    async def test_empty_scene_without_description_gets_the_plain_sentence(self):
        result = await self._ask(json.dumps({
            "object_type": "none", "count": 0, "identity": "unknown",
            "action": "cannot_tell", "direction": "cannot_tell", "package_or_carrier": "none",
        }))
        assert result.success is True
        assert result.description == "No person, vehicle, animal, or package is visible."
        assert result.identification["object_type"] == "none"

    @pytest.mark.asyncio
    async def test_subject_without_description_is_a_failure_not_raw_json(self):
        result = await self._ask(json.dumps({"object_type": "animal", "count": 1, "action": "walking"}))
        assert result.success is False and "no description" in result.error

    @pytest.mark.asyncio
    async def test_plain_text_reply_is_kept(self):
        result = await self._ask("A small dog walks across the deck.")
        assert result.success is True and result.description == "A small dog walks across the deck."
