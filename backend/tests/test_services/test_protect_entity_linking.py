"""Entity matching on live Protect events (#678 follow-up).

Protect events named people and vehicles before the first notification but
never stored entity links or ran alert rules, and the stored
``matched_entity_ids`` trusted a whole-scene CLIP pick (an empty porch scored
0.87 against a saved car). These tests cover the verified naming, the links,
the alert rules that read them, and that none of it can fail the event.
"""
import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uiprotect.data.types import EventType as ProtectEventType

from app.models.entity_adjustment import EntityAdjustment
from app.models.event import Event
from app.models.notification import Notification
from app.models.recognized_entity import EntityEvent, RecognizedEntity
from app.services import event_entity_linking as linking
from app.services.entity_service import EntityMatchResult, get_entity_service
from app.services.event_entity_linking import (
    NamedIdentity,
    event_looks_like_vehicle,
    run_post_persist_entity_steps,
    select_named_vehicles,
    verify_named_identities,
)
from app.services.protect_event_handler import ProtectEventHandler
from tests.conftest import make_alert_rule, make_camera, make_entity, make_event

PROTECT_ID = "a1b2c3d4-0000-1111-2222-333344445555"


@contextmanager
def _db(session):
    yield session


def _vec(seed: float) -> list:
    return [seed] + [0.01] * 511


def _ident(entity, score=0.8):
    return EntityMatchResult(
        entity_id=entity.id,
        entity_type=entity.entity_type,
        name=entity.name,
        first_seen_at=entity.first_seen_at,
        last_seen_at=entity.last_seen_at,
        occurrence_count=entity.occurrence_count,
        similarity_score=score,
        is_new=False,
        vehicle_color=getattr(entity, "vehicle_color", None),
        vehicle_make=getattr(entity, "vehicle_make", None),
        vehicle_model=getattr(entity, "vehicle_model", None),
    )


@pytest.fixture
def household(db_session):
    brent = make_entity(db_session, entity_type="person", name="Brent")
    tesla = make_entity(
        db_session, entity_type="vehicle", name="Brent's Tesla",
        vehicle_color="red", vehicle_make="tesla", vehicle_model="model y",
        reference_embedding=json.dumps(_vec(0.9)),
    )
    bmw = make_entity(
        db_session, entity_type="vehicle", name="Isaac's BMW",
        vehicle_color="red", vehicle_make="bmw", vehicle_model="x3",
        reference_embedding=json.dumps(_vec(0.2)),
    )
    return SimpleNamespace(brent=brent, tesla=tesla, bmw=bmw)


class TestSelectNamedVehicles:
    def _v(self, name, make=None, model=None, color=None, ref=None, eid=None):
        return NamedIdentity(
            entity_id=eid or name, name=name, entity_type="vehicle",
            vehicle_make=make, vehicle_model=model, vehicle_color=color,
            reference_embedding=ref,
        )

    def test_picks_the_vehicle_the_description_names(self):
        tesla = self._v("Brent's Tesla", "tesla", "model y", "red")
        bmw = self._v("Isaac's BMW", "bmw", "x3", "red")
        picked = select_named_vehicles("A red BMW X3 pulls into the driveway.", [tesla, bmw])
        assert [v.name for v in picked] == ["Isaac's BMW"]

    def test_no_make_in_description_links_nothing(self):
        tesla = self._v("Brent's Tesla", "tesla", "model y", "red")
        assert select_named_vehicles("A white semi-truck passes on the street.", [tesla]) == []
        assert select_named_vehicles("A red SUV is parked.", [tesla]) == []

    def test_contradicting_model_or_color_links_nothing(self):
        bmw = self._v("Isaac's BMW", "bmw", "x3", "red")
        assert select_named_vehicles("A red BMW X5 arrives.", [bmw]) == []
        assert select_named_vehicles("A gray BMW X3 arrives.", [bmw]) == []

    def test_two_agreeing_vehicles_prefer_the_clip_pick(self):
        a = self._v("Isaac's BMW", "bmw", "x3", eid="a")
        b = self._v("Neighbor BMW", "bmw", "x3", eid="b")
        picked = select_named_vehicles("A BMW X3 arrives.", [a, b], preferred_ids=["b"])
        assert [v.entity_id for v in picked] == ["b"]

    def test_two_agreeing_vehicles_fall_back_to_clip_similarity(self):
        a = self._v("Isaac's BMW", "bmw", "x3", eid="a", ref=_vec(0.1))
        b = self._v("Neighbor BMW", "bmw", "x3", eid="b", ref=_vec(0.9))
        picked = select_named_vehicles("A BMW X3 arrives.", [a, b], embedding=_vec(0.9))
        assert [v.entity_id for v in picked] == ["b"]
        assert picked[0].similarity_score is not None

    def test_ambiguous_without_any_signal_links_nothing(self):
        a = self._v("Isaac's BMW", "bmw", "x3", eid="a")
        b = self._v("Neighbor BMW", "bmw", "x3", eid="b")
        assert select_named_vehicles("A BMW X3 arrives.", [a, b]) == []


class TestEventLooksLikeVehicle:
    def test_protect_type_or_identification(self):
        assert event_looks_like_vehicle("vehicle") is True
        assert event_looks_like_vehicle("person") is False
        ai = SimpleNamespace(identification={"object_type": "vehicle"}, objects_detected=["person"])
        assert event_looks_like_vehicle("motion", ai) is True
        ai = SimpleNamespace(identification={"object_type": "person"}, objects_detected=["person"])
        assert event_looks_like_vehicle("person", ai) is False


class TestVerifyNamedIdentities:
    def test_wrong_clip_vehicle_is_replaced_by_the_described_one(self, db_session, household):
        out = verify_named_identities(
            db_session,
            description="Isaac's red BMW X3 pulls into the driveway.",
            candidates=[_ident(household.tesla, 0.87)],
            looks_like_vehicle=True,
        )
        assert [e.entity_id for e in out] == [household.bmw.id]

    def test_clip_vehicle_without_support_is_dropped(self, db_session, household):
        out = verify_named_identities(
            db_session,
            description="A white semi-truck moves along the street.",
            candidates=[_ident(household.tesla, 0.83)],
            looks_like_vehicle=True,
        )
        assert out == []

    def test_face_matched_person_passes_and_vehicles_stay_out_of_person_events(
        self, db_session, household
    ):
        out = verify_named_identities(
            db_session,
            description="A man walks past a red BMW X3 to the front door.",
            candidates=[_ident(household.brent, 0.74)],
            looks_like_vehicle=False,
        )
        assert [e.entity_id for e in out] == [household.brent.id]

    def test_unnamed_entities_are_never_candidates(self, db_session, household):
        make_entity(
            db_session, entity_type="vehicle", name=None,
            vehicle_make="bmw", vehicle_model="x3",
        )
        out = verify_named_identities(
            db_session,
            description="A BMW X3 arrives.",
            candidates=[],
            looks_like_vehicle=True,
        )
        assert [e.entity_id for e in out] == [household.bmw.id]


class TestPostAiContextFields:
    def _handler(self, named=(), embedding=None):
        handler = ProtectEventHandler()
        handler.ai_pipeline._last_context_bundle = SimpleNamespace(
            named_identities=list(named),
            embedding_vector=embedding,
            context_included=False,
            context_stats=None,
        )
        return handler

    def test_stores_only_verified_ids_and_enriches(self, db_session, household):
        handler = self._handler([_ident(household.tesla, 0.87)])
        ai = SimpleNamespace(
            description="A red BMW X3 pulls into the driveway.",
            identification={"object_type": "vehicle"},
            objects_detected=["vehicle"],
        )
        fields = handler._post_ai_context_fields(ai, "vehicle", db_session)
        assert json.loads(fields["matched_entity_ids"]) == [household.bmw.id]
        assert fields["recognition_status"] == "known"
        # A vehicle name is only written in when the sentence supports it
        # (#645); here the make/model already say it. Both fields agree.
        assert ai.description == fields["enriched_description"]

    def test_naming_failure_still_returns_fields(self, db_session, household):
        handler = self._handler([_ident(household.brent)])
        ai = SimpleNamespace(description="A person at the door.", identification=None,
                             objects_detected=["person"])
        with patch(
            "app.services.event_entity_linking.verify_named_identities",
            side_effect=RuntimeError("boom"),
        ):
            fields = handler._post_ai_context_fields(ai, "person", db_session)
        assert fields["matched_entity_ids"] is None
        assert fields["recognition_status"] is None
        assert fields["enriched_description"] == "A person at the door."

    def test_without_db_still_names_face_matched_people(self, household):
        handler = self._handler([_ident(household.brent)])
        ai = SimpleNamespace(description="A person walks up to the door.",
                             identification=None, objects_detected=["person"])
        fields = handler._post_ai_context_fields(ai, "person")
        assert json.loads(fields["matched_entity_ids"]) == [household.brent.id]
        assert fields["enriched_description"].startswith("Brent")


class TestLinkMatchedEntities:
    @pytest.mark.asyncio
    async def test_links_once_without_touching_the_embedding(self, db_session, household):
        cam = make_camera(db_session, source_type="protect")
        ev = make_event(
            db_session, camera_id=cam.id, source_type="protect",
            matched_entity_ids=json.dumps([household.bmw.id]),
            timestamp=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        before_ref = household.bmw.reference_embedding
        before_count = household.bmw.occurrence_count
        svc = get_entity_service()

        linked = await svc.link_matched_entities(db_session, ev.id, [household.bmw.id])
        again = await svc.link_matched_entities(db_session, ev.id, [household.bmw.id])

        db_session.expire_all()
        bmw = db_session.get(RecognizedEntity, household.bmw.id)
        event = db_session.get(Event, ev.id)
        assert linked == [household.bmw.id]
        assert again == []
        assert db_session.query(EntityEvent).filter_by(event_id=ev.id).count() == 1
        assert bmw.occurrence_count == before_count + 1
        assert bmw.reference_embedding == before_ref
        assert event.final_entity_id == household.bmw.id
        assert json.loads(event.matched_entity_ids) == [household.bmw.id]
        assert db_session.query(EntityAdjustment).count() == 0

    @pytest.mark.asyncio
    async def test_skips_unknown_and_user_removed_entities(self, db_session, household):
        cam = make_camera(db_session, source_type="protect")
        ev = make_event(db_session, camera_id=cam.id, source_type="protect")
        db_session.add(EntityAdjustment(
            event_id=ev.id, old_entity_id=household.tesla.id, action="remove",
        ))
        db_session.commit()

        linked = await get_entity_service().link_matched_entities(
            db_session, ev.id, ["missing-entity", household.tesla.id, household.brent.id]
        )
        assert linked == [household.brent.id]


class TestPostPersistSteps:
    def _event(self, db_session, household, objects, matched):
        cam = make_camera(db_session, source_type="protect")
        return make_event(
            db_session, camera_id=cam.id, source_type="protect",
            objects_detected=json.dumps(objects), confidence=90,
            matched_entity_ids=json.dumps(matched) if matched else None,
        )

    @pytest.mark.asyncio
    async def test_entity_rule_fires_after_linking(self, db_session, household):
        rule = make_alert_rule(
            db_session, name="Alert: BMW X3 detected",
            conditions={"rule_type": "any", "object_types": ["vehicle"]},
            entity_match_mode="specific", entity_id=household.bmw.id,
        )
        other = make_alert_rule(
            db_session, name="Alert: Tesla detected",
            conditions={"rule_type": "any", "object_types": ["vehicle"]},
            entity_match_mode="specific", entity_id=household.tesla.id,
        )
        ev = self._event(db_session, household, ["vehicle"], [household.bmw.id])

        await run_post_persist_entity_steps(ev.id, session_factory=lambda: _db(db_session))

        db_session.expire_all()
        assert db_session.query(EntityEvent).filter_by(event_id=ev.id).count() == 1
        assert db_session.get(Event, ev.id).alert_triggered is True
        fired = {n.rule_id for n in db_session.query(Notification).all()}
        assert fired == {rule.id}
        assert other.id not in fired

    @pytest.mark.asyncio
    async def test_link_failure_still_runs_alert_rules(self, db_session, household):
        rule = make_alert_rule(
            db_session, conditions={"object_types": ["person"]},
        )
        ev = self._event(db_session, household, ["person"], [household.brent.id])
        with patch.object(
            type(get_entity_service()), "link_matched_entities",
            new_callable=AsyncMock, side_effect=RuntimeError("db gone"),
        ):
            await run_post_persist_entity_steps(ev.id, session_factory=lambda: _db(db_session))
        db_session.expire_all()
        assert db_session.get(Event, ev.id).alert_triggered is True
        assert db_session.query(Notification).filter_by(rule_id=rule.id).count() == 1

    @pytest.mark.asyncio
    async def test_slow_steps_are_bounded_and_never_raise(self, db_session, household):
        ev = self._event(db_session, household, ["person"], [household.brent.id])

        async def _hang(*_a, **_k):
            await asyncio.sleep(5)

        with patch.object(linking, "link_stored_matches", _hang), \
             patch.object(linking, "evaluate_alert_rules", _hang):
            started = asyncio.get_running_loop().time()
            await run_post_persist_entity_steps(
                ev.id, session_factory=lambda: _db(db_session),
                link_timeout_s=0.05, alert_timeout_s=0.05,
            )
            assert asyncio.get_running_loop().time() - started < 1.0

    @pytest.mark.asyncio
    async def test_alert_failure_is_swallowed(self, db_session, household):
        ev = self._event(db_session, household, ["person"], None)
        with patch(
            "app.services.alert_engine.process_event_alerts",
            new_callable=AsyncMock, side_effect=RuntimeError("rules broke"),
        ):
            await run_post_persist_entity_steps(ev.id, session_factory=lambda: _db(db_session))

    @pytest.mark.asyncio
    async def test_non_string_ids_are_ignored(self):
        await run_post_persist_entity_steps(MagicMock(), session_factory=MagicMock())
        await run_post_persist_entity_steps(None, session_factory=MagicMock())


def _native_event(smart_values):
    event = type("Event", (), {})()
    event.type = ProtectEventType.SMART_DETECT
    event.camera_id = "protect-cam-ent"
    event.id = PROTECT_ID
    event.start = datetime.now(timezone.utc) - timedelta(seconds=5)
    event.end = datetime.now(timezone.utc)
    event.metadata = None
    event.get_thumbnail = None
    event.smart_detect_types = [type("S", (), {"value": v})() for v in smart_values]
    return event


class TestNativeProtectEventEndToEnd:
    """The live websocket path stores, links and alerts in that order."""

    async def _run(self, db_session, household, ai_description, named):
        camera = make_camera(
            db_session=db_session, name="Driveway", source_type="protect",
            protect_camera_id="protect-cam-ent", is_enabled=True,
            smart_detection_types='["person", "vehicle"]',
        )
        handler = ProtectEventHandler()
        handler.event_filter._last_event_times.pop(camera.id, None)
        bundle = SimpleNamespace(
            named_identities=list(named), embedding_vector=None,
            context_included=False, context_stats=None,
        )

        async def _analyze(*_a, **_k):
            handler.ai_pipeline._last_context_bundle = bundle
            handler.ai_pipeline._last_analysis_mode = "single_frame"
            return SimpleNamespace(
                success=True, description=ai_description, confidence=0.9,
                objects_detected=["vehicle"], provider="test", ai_confidence=90,
                cost_estimate=0.0, identification={"object_type": "vehicle"},
                bounding_boxes=None, response_time_ms=10,
            )

        snapshot = SimpleNamespace(
            thumbnail_path="/api/v1/thumbnails/x.jpg",
            timestamp=datetime.now(timezone.utc), image_base64="",
        )
        order = []
        real_steps = linking.run_post_persist_entity_steps

        async def _broadcast(*_a, **_k):
            order.append("broadcast")

        async def _steps(*a, **k):
            order.append("post_persist")
            return await real_steps(*a, **k)

        with patch("app.services.protect_event_handler.get_db_session", lambda: _db(db_session)), \
             patch.object(handler.media_service, "get_media_for_event", new_callable=AsyncMock) as media, \
             patch.object(handler.ai_pipeline, "submit_snapshot_for_analysis", side_effect=_analyze), \
             patch.object(handler, "_store_protect_embedding", new_callable=AsyncMock), \
             patch.object(handler, "_link_cross_camera_incident", new_callable=AsyncMock), \
             patch.object(handler.broadcaster, "broadcast_event_created", side_effect=_broadcast), \
             patch("app.services.protect_detection_hints.fetch_event_thumbnail_bytes",
                   new_callable=AsyncMock, return_value=None), \
             patch.object(linking, "run_post_persist_entity_steps", _steps):
            media.return_value = SimpleNamespace(
                snapshot_result=snapshot, clip_path=None, fallback_reason=None, clip_plan=None,
            )
            result = await handler._handle_native_event("ctrl-1", _native_event(["vehicle"]))

        db_session.expire_all()
        stored = db_session.query(Event).filter(Event.protect_event_id == PROTECT_ID).one()
        return result, stored, order

    @pytest.mark.asyncio
    async def test_bmw_event_is_linked_named_and_alerts(self, db_session, household):
        rule = make_alert_rule(
            db_session, name="Alert: BMW X3 detected",
            conditions={"rule_type": "any", "object_types": ["vehicle"]},
            entity_match_mode="specific", entity_id=household.bmw.id,
        )
        result, stored, order = await self._run(
            db_session, household,
            "A red BMW X3 pulls into the driveway and parks.",
            [_ident(household.tesla, 0.87)],  # the scene-level CLIP pick is wrong
        )
        assert result is True
        assert order == ["broadcast", "post_persist"]
        assert json.loads(stored.matched_entity_ids) == [household.bmw.id]
        assert stored.description == stored.enriched_description
        assert stored.recognition_status == "known"
        assert stored.final_entity_id == household.bmw.id
        links = db_session.query(EntityEvent).filter_by(event_id=stored.id).all()
        assert [l.entity_id for l in links] == [household.bmw.id]
        assert stored.alert_triggered is True
        assert db_session.query(Notification).filter_by(rule_id=rule.id).count() == 1

    @pytest.mark.asyncio
    async def test_matching_failure_never_drops_the_event(self, db_session, household):
        make_alert_rule(
            db_session, name="Any vehicle",
            conditions={"rule_type": "any", "object_types": ["vehicle"]},
        )
        with patch.object(
            type(get_entity_service()), "link_matched_entities",
            new_callable=AsyncMock, side_effect=RuntimeError("link exploded"),
        ):
            result, stored, order = await self._run(
                db_session, household,
                "A red Tesla Model Y backs out of the driveway.", [],
            )
        assert result is True
        assert order == ["broadcast", "post_persist"]
        assert json.loads(stored.matched_entity_ids) == [household.tesla.id]
        assert db_session.query(EntityEvent).filter_by(event_id=stored.id).count() == 0
        # Alert rules still ran even though linking failed.
        assert stored.alert_triggered is True
