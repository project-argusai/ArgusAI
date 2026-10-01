"""One Protect event id must produce one Argus event (issue #633).

The per-camera cooldown is 60 seconds and is a strict less-than check, so a
WebSocket update for the same protect_event_id at about 60 seconds was stored
as a second row and analyzed again. These tests cover that update.
"""
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uiprotect.data.types import EventType as ProtectEventType

from app.models.event import Event
from app.services.protect_event_filter import (
    PROTECT_EVENT_ID_MEMORY_SECONDS,
    ProtectEventFilter,
)
from app.services.protect_event_handler import ProtectEventHandler
from app.services.protect_event_storage_service import ProtectEventStorageService
from tests.conftest import make_camera, make_event

PROTECT_ID = "5343366b-1111-2222-3333-444444444444"
OTHER_ID = "d8bedd4f-aaaa-bbbb-cccc-dddddddddddd"


@contextmanager
def _db(session):
    yield session


def _expire_cooldown(handler, camera_id, seconds=60):
    """Place the camera cooldown at or past the 60s boundary."""
    handler.event_filter._last_event_times[camera_id] = (
        datetime.now(timezone.utc) - timedelta(seconds=seconds)
    )


def _protect_camera(db_session, **overrides):
    filters = overrides.pop(
        "smart_detection_types",
        '["person", "vehicle", "animal", "ring"]',
    )
    return make_camera(
        db_session=db_session,
        name="Driveway",
        source_type="protect",
        protect_camera_id="protect-cam-1",
        is_enabled=True,
        smart_detection_types=filters,
        **overrides,
    )


def _stored_event(db_session, camera, protect_event_id, smart_type, objects, **overrides):
    when = overrides.pop("timestamp", None)
    if when is None:
        when = datetime.now(timezone.utc) - timedelta(seconds=60)
    return make_event(
        db_session=db_session,
        camera_id=camera.id,
        source_type="protect",
        protect_event_id=protect_event_id,
        smart_detection_type=smart_type,
        objects_detected=json.dumps(objects),
        description=overrides.pop("description", f"{smart_type} on the driveway"),
        timestamp=when,
        **overrides,
    )


def _native_event(protect_id, smart_values, event_type=ProtectEventType.SMART_DETECT):
    event = type("Event", (), {})()
    event.type = event_type
    event.camera_id = "protect-cam-1"
    event.id = protect_id
    event.start = datetime.now(timezone.utc) - timedelta(seconds=60)
    event.end = datetime.now(timezone.utc)
    event.metadata = None
    event.get_thumbnail = None
    event.smart_detect_types = [
        type("SmartType", (), {"value": value})() for value in smart_values
    ]
    return event


def _camera_update(protect_id, *, person=False, vehicle=False, animal=False):
    state = type("Camera", (), {})()
    state.id = "protect-cam-1"
    state.is_motion_currently_detected = False
    state.is_smart_currently_detected = person or vehicle or animal
    state.is_person_currently_detected = person
    state.is_vehicle_currently_detected = vehicle
    state.is_package_currently_detected = False
    state.is_animal_currently_detected = animal
    state.active_smart_detect_types = []
    state.last_smart_detect_event_ids = {}
    state.last_motion = None
    if protect_id:
        last = type("LastSmart", (), {})()
        last.id = protect_id
        state.last_smart_detect = last
    else:
        state.last_smart_detect = None
    message = type("Msg", (), {})()
    message.new_obj = state
    return message


@pytest.fixture
def handler():
    return ProtectEventHandler()


def _rows(db_session, protect_event_id):
    db_session.expire_all()
    return (
        db_session.query(Event)
        .filter(Event.protect_event_id == protect_event_id)
        .order_by(Event.timestamp.asc(), Event.id.asc())
        .all()
    )


class TestProtectEventIdMemory:
    def test_reservation_blocks_a_second_claim_until_abandoned(self):
        event_filter = ProtectEventFilter()
        assert event_filter.try_begin_protect_event(PROTECT_ID) is True
        assert event_filter.try_begin_protect_event(PROTECT_ID) is False
        event_filter.note_pending_protect_update(PROTECT_ID, ["person"], False)
        event_filter.abandon_protect_event(PROTECT_ID)
        assert event_filter.is_protect_event_known(PROTECT_ID) is False
        assert event_filter.try_begin_protect_event(PROTECT_ID) is True
        types, is_ring = event_filter.take_pending_protect_update(PROTECT_ID)
        assert types == ["person"]
        assert is_ring is False

    def test_seen_ids_expire(self):
        event_filter = ProtectEventFilter()
        event_filter.try_begin_protect_event(PROTECT_ID)
        event_filter._seen_protect_event_ids[PROTECT_ID] = (
            event_filter._seen_protect_event_ids[PROTECT_ID]
            - PROTECT_EVENT_ID_MEMORY_SECONDS
            - 1
        )
        assert event_filter.is_protect_event_known(PROTECT_ID) is False


class TestMergeDetectionTypes:
    def test_unions_types_without_rewriting_the_primary_token(self, db_session):
        camera = _protect_camera(db_session)
        event = _stored_event(db_session, camera, PROTECT_ID, "vehicle", ["vehicle"])
        storage = ProtectEventStorageService()

        changed = storage.merge_detection_types(db_session, event, ["person", "vehicle"], False)

        assert changed is True
        assert event.smart_detection_type == "vehicle"
        assert json.loads(event.objects_detected) == ["vehicle", "person"]
        assert event.description == "vehicle on the driveway"

    def test_malformed_objects_detected_is_left_unchanged(self, db_session):
        camera = _protect_camera(db_session)
        event = _stored_event(db_session, camera, PROTECT_ID, "vehicle", ["vehicle"])
        event.objects_detected = "{not-a-list"
        db_session.commit()
        storage = ProtectEventStorageService()

        changed = storage.merge_detection_types(db_session, event, ["person"], False)

        assert changed is False
        assert event.objects_detected == "{not-a-list"
        assert event.smart_detection_type == "vehicle"

    def test_unknown_type_tokens_are_ignored(self, db_session):
        camera = _protect_camera(db_session)
        event = _stored_event(db_session, camera, PROTECT_ID, "animal", ["animal"])
        storage = ProtectEventStorageService()

        changed = storage.merge_detection_types(
            db_session, event, ["<script>", "person"], False
        )

        assert changed is True
        assert json.loads(event.objects_detected) == ["animal", "person"]


class TestSameProtectEventIdAboutSixtySecondsLater:
    @pytest.mark.asyncio
    async def test_native_update_with_a_new_type_does_not_reanalyze(self, handler, db_session):
        camera = _protect_camera(db_session)
        original = _stored_event(db_session, camera, PROTECT_ID, "vehicle", ["vehicle"])
        _expire_cooldown(handler, camera.id, seconds=60)

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.media_service, "get_media_for_event", new_callable=AsyncMock) as media, \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai, \
             patch.object(handler.broadcaster, "broadcast_event_created", new_callable=AsyncMock) as broadcast, \
             patch.object(handler.broadcaster, "broadcast_doorbell_ring", new_callable=AsyncMock) as doorbell, \
             patch.object(handler.broadcaster, "trigger_homekit_doorbell") as homekit:
            result = await handler._handle_native_event(
                "ctrl-1", _native_event(PROTECT_ID, ["person"])
            )

        assert result is False
        media.assert_not_called()
        ai.assert_not_called()
        broadcast.assert_not_called()
        doorbell.assert_not_called()
        homekit.assert_not_called()

        rows = _rows(db_session, PROTECT_ID)
        assert len(rows) == 1
        assert rows[0].id == original.id
        assert rows[0].smart_detection_type == "vehicle"
        assert json.loads(rows[0].objects_detected) == ["vehicle", "person"]
        assert rows[0].description == "vehicle on the driveway"

    @pytest.mark.asyncio
    async def test_native_update_with_the_same_type_does_not_insert(self, handler, db_session):
        camera = _protect_camera(db_session)
        _stored_event(
            db_session,
            camera,
            PROTECT_ID,
            "animal",
            ["animal"],
            description="Animal near the fence",
        )
        _expire_cooldown(handler, camera.id, seconds=61)

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai, \
             patch.object(handler.broadcaster, "broadcast_event_created", new_callable=AsyncMock) as broadcast:
            result = await handler._handle_native_event(
                "ctrl-1", _native_event(PROTECT_ID, ["animal"])
            )

        assert result is False
        ai.assert_not_called()
        broadcast.assert_not_called()
        rows = _rows(db_session, PROTECT_ID)
        assert len(rows) == 1
        assert json.loads(rows[0].objects_detected) == ["animal"]
        assert rows[0].description == "Animal near the fence"

    @pytest.mark.asyncio
    async def test_camera_state_update_about_60s_later_does_not_reanalyze(
        self, handler, db_session
    ):
        camera = _protect_camera(db_session)
        _stored_event(db_session, camera, PROTECT_ID, "vehicle", ["vehicle"])
        _expire_cooldown(handler, camera.id, seconds=60)

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.media_service, "get_media_for_event", new_callable=AsyncMock) as media, \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai, \
             patch.object(handler.broadcaster, "broadcast_event_created", new_callable=AsyncMock) as broadcast:
            result = await handler.handle_event(
                "ctrl-1", _camera_update(PROTECT_ID, person=True)
            )

        assert result is False
        media.assert_not_called()
        ai.assert_not_called()
        broadcast.assert_not_called()
        rows = _rows(db_session, PROTECT_ID)
        assert len(rows) == 1
        assert json.loads(rows[0].objects_detected) == ["vehicle", "person"]
        assert rows[0].smart_detection_type == "vehicle"

    @pytest.mark.asyncio
    async def test_update_inside_the_cooldown_merges_without_refreshing_it(
        self, handler, db_session
    ):
        camera = _protect_camera(db_session)
        _stored_event(db_session, camera, PROTECT_ID, "vehicle", ["vehicle"])
        _expire_cooldown(handler, camera.id, seconds=10)
        cooldown_mark = handler.event_filter._last_event_times[camera.id]

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai:
            result = await handler._handle_native_event(
                "ctrl-1", _native_event(PROTECT_ID, ["person"])
            )

        assert result is False
        ai.assert_not_called()
        assert handler.event_filter._last_event_times[camera.id] == cooldown_mark
        rows = _rows(db_session, PROTECT_ID)
        assert len(rows) == 1
        assert json.loads(rows[0].objects_detected) == ["vehicle", "person"]

    @pytest.mark.asyncio
    async def test_ring_update_sets_the_flag_without_a_second_notification(
        self, handler, db_session
    ):
        camera = _protect_camera(db_session)
        _stored_event(db_session, camera, PROTECT_ID, "person", ["person"])
        _expire_cooldown(handler, camera.id, seconds=60)

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai, \
             patch.object(handler.broadcaster, "broadcast_event_created", new_callable=AsyncMock) as broadcast, \
             patch.object(handler.broadcaster, "broadcast_doorbell_ring", new_callable=AsyncMock) as doorbell, \
             patch.object(handler.broadcaster, "trigger_homekit_doorbell") as homekit:
            result = await handler._handle_native_event(
                "ctrl-1",
                _native_event(PROTECT_ID, [], event_type=ProtectEventType.RING),
            )

        assert result is False
        ai.assert_not_called()
        broadcast.assert_not_called()
        doorbell.assert_not_called()
        homekit.assert_not_called()
        rows = _rows(db_session, PROTECT_ID)
        assert len(rows) == 1
        assert rows[0].is_doorbell_ring is True
        assert rows[0].smart_detection_type == "person"
        assert "ring" in json.loads(rows[0].objects_detected)

    @pytest.mark.asyncio
    async def test_existing_duplicate_rows_are_not_deleted(self, handler, db_session):
        camera = _protect_camera(db_session)
        earlier = _stored_event(
            db_session,
            camera,
            PROTECT_ID,
            "vehicle",
            ["vehicle"],
            id="earlier-row",
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=60),
        )
        later = _stored_event(
            db_session,
            camera,
            PROTECT_ID,
            "person",
            ["person"],
            id="later-row",
            description="second historical row",
            timestamp=datetime.now(timezone.utc),
        )
        _expire_cooldown(handler, camera.id, seconds=60)

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai:
            result = await handler._handle_native_event(
                "ctrl-1", _native_event(PROTECT_ID, ["animal"])
            )

        assert result is False
        ai.assert_not_called()
        rows = _rows(db_session, PROTECT_ID)
        assert [row.id for row in rows] == [earlier.id, later.id]
        assert json.loads(rows[0].objects_detected) == ["vehicle", "animal"]
        assert rows[1].description == "second historical row"
        assert json.loads(rows[1].objects_detected) == ["person"]

    @pytest.mark.asyncio
    async def test_in_flight_id_skips_ai_and_keeps_the_new_type(self, handler, db_session):
        camera = _protect_camera(db_session)
        assert handler.event_filter.try_begin_protect_event(PROTECT_ID) is True

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai:
            result = await handler._handle_native_event(
                "ctrl-1", _native_event(PROTECT_ID, ["person"])
            )

        assert result is False
        ai.assert_not_called()
        assert _rows(db_session, PROTECT_ID) == []
        pending, is_ring = handler.event_filter.take_pending_protect_update(PROTECT_ID)
        assert pending == ["person"]
        assert is_ring is False
        assert camera.id not in handler.event_filter._last_event_times

    @pytest.mark.asyncio
    async def test_different_protect_id_after_60s_still_runs_ai(self, handler, db_session):
        camera = _protect_camera(db_session)
        _stored_event(db_session, camera, PROTECT_ID, "vehicle", ["vehicle"])
        _expire_cooldown(handler, camera.id, seconds=60)

        stored = MagicMock()
        stored.id = "new-event"
        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.media_service, "get_media_for_event", new_callable=AsyncMock) as media, \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai, \
             patch.object(handler.storage_service, "persist_protect_event", new_callable=AsyncMock) as persist, \
             patch.object(handler, "_post_ai_context_fields", return_value={}), \
             patch.object(handler, "_store_protect_embedding", new_callable=AsyncMock), \
             patch.object(handler.broadcaster, "broadcast_event_created", new_callable=AsyncMock) as broadcast:
            media.return_value = MagicMock(
                snapshot_result=MagicMock(thumbnail_path="/thumbnails/new.jpg", timestamp=datetime.now(timezone.utc)),
                clip_path=None,
                fallback_reason=None,
                clip_plan=None,
            )
            ai.return_value = MagicMock(success=True, description="A person", objects_detected=["person"])
            persist.return_value = stored

            result = await handler._handle_native_event(
                "ctrl-1", _native_event(OTHER_ID, ["person"])
            )

        assert result is True
        ai.assert_awaited_once()
        persist.assert_awaited_once()
        assert persist.await_args.kwargs["protect_event_id"] == OTHER_ID
        broadcast.assert_awaited_once()
        assert len(_rows(db_session, PROTECT_ID)) == 1
        assert _rows(db_session, OTHER_ID) == []

    @pytest.mark.asyncio
    async def test_failed_attempt_does_not_permanently_swallow_the_id(self, handler, db_session):
        camera = _protect_camera(db_session)

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.media_service, "get_media_for_event", new_callable=AsyncMock) as media, \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai:
            media.return_value = MagicMock(snapshot_result=None, clip_path=None, fallback_reason=None)
            first = await handler._handle_native_event(
                "ctrl-1", _native_event(PROTECT_ID, ["vehicle"])
            )

        assert first is False
        ai.assert_not_called()
        assert handler.event_filter.is_protect_event_known(PROTECT_ID) is False

        _expire_cooldown(handler, camera.id, seconds=60)
        stored = MagicMock()
        stored.id = "retried"
        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.media_service, "get_media_for_event", new_callable=AsyncMock) as media, \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", new_callable=AsyncMock) as ai, \
             patch.object(handler.storage_service, "persist_protect_event", new_callable=AsyncMock) as persist, \
             patch.object(handler, "_post_ai_context_fields", return_value={}), \
             patch.object(handler, "_store_protect_embedding", new_callable=AsyncMock), \
             patch.object(handler.broadcaster, "broadcast_event_created", new_callable=AsyncMock):
            media.return_value = MagicMock(
                snapshot_result=MagicMock(thumbnail_path="/thumbnails/retry.jpg", timestamp=datetime.now(timezone.utc)),
                clip_path=None,
                fallback_reason=None,
                clip_plan=None,
            )
            ai.return_value = MagicMock(success=True, description="A vehicle")
            persist.return_value = stored
            second = await handler._handle_native_event(
                "ctrl-1", _native_event(PROTECT_ID, ["vehicle"])
            )

        assert second is True
        ai.assert_awaited_once()
        assert persist.await_args.kwargs["protect_event_id"] == PROTECT_ID
