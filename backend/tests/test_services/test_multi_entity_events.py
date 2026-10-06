"""Several entities on one event (issue #652).

Covers EntityService add / remove / replace / merge, the ``entities`` list
builder, occurrence counts, EntityAdjustment rows, matched_entity_ids sync,
the primary (final_entity_*) columns, and the reanalysis rewrite.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.entity_adjustment import EntityAdjustment
from app.models.event import Event
from app.models.recognized_entity import EntityEvent, RecognizedEntity
from app.services.entity_service import (
    MAX_ENTITIES_PER_EVENT,
    EntityService,
    EventEntityLimitError,
    build_event_entities,
    parse_entity_id_list,
    reset_entity_service,
)
from tests.conftest import make_camera, make_entity, make_event


@pytest.fixture
def service():
    reset_entity_service()
    yield EntityService()
    reset_entity_service()


@pytest.fixture
def scene(db_session):
    """Isaac (person) and his BMW X3 (vehicle), plus one driveway event.

    Text ids on purpose: entity ids must stay strings end to end.
    """
    camera = make_camera(db_session=db_session, id="cam-driveway", name="Driveway")
    isaac = make_entity(
        db_session=db_session, id="isaac", entity_type="person", name="Isaac",
        occurrence_count=3,
    )
    bmw = make_entity(
        db_session=db_session, id="bmw-x3", entity_type="vehicle", name=None,
        vehicle_color="black", vehicle_make="BMW", vehicle_model="X3",
        occurrence_count=5,
    )
    event = make_event(
        db_session=db_session, id="evt-1", camera_id=camera.id,
        description="A person walks to a black BMW X3 in the driveway.",
        objects_detected=json.dumps(["person", "vehicle"]),
    )
    return {"camera": camera, "isaac": isaac, "bmw": bmw, "event": event}


def _links(db, event_id):
    return sorted(
        r.entity_id for r in db.query(EntityEvent).filter(EntityEvent.event_id == event_id)
    )


def _actions(db, event_id):
    return [
        (a.action, a.old_entity_id, a.new_entity_id)
        for a in db.query(EntityAdjustment)
        .filter(EntityAdjustment.event_id == event_id)
        .order_by(EntityAdjustment.created_at)
    ]


def _count(db, entity_id):
    db.expire_all()
    return db.query(RecognizedEntity).filter(RecognizedEntity.id == entity_id).one().occurrence_count


class TestAddKeepsExistingEntities:
    @pytest.mark.asyncio
    async def test_second_entity_is_added_not_moved(self, db_session, service, scene):
        first = await service.assign_event(db_session, "evt-1", "isaac")
        second = await service.assign_event(db_session, "evt-1", "bmw-x3")

        assert first["action"] == "add"
        assert second["action"] == "add"
        assert _links(db_session, "evt-1") == ["bmw-x3", "isaac"]
        assert [e["id"] for e in second["entities"]] == ["isaac", "bmw-x3"]
        assert all(isinstance(e["id"], str) for e in second["entities"])

        # occurrence counts: +1 each, nothing taken from the first entity
        assert _count(db_session, "isaac") == 4
        assert _count(db_session, "bmw-x3") == 6

        event = db_session.query(Event).filter(Event.id == "evt-1").one()
        assert parse_entity_id_list(event.matched_entity_ids) == ["isaac", "bmw-x3"]
        # First entity becomes primary; adding the car does not steal it.
        assert event.final_entity_id == "isaac"
        assert event.final_entity_type == "person"
        assert event.final_entity_name == "Isaac"

        assert _actions(db_session, "evt-1") == [
            ("add", None, "isaac"),
            ("add", None, "bmw-x3"),
        ]

    @pytest.mark.asyncio
    async def test_adding_the_same_entity_twice_is_a_no_op(self, db_session, service, scene):
        await service.assign_event(db_session, "evt-1", "isaac")
        again = await service.assign_event(db_session, "evt-1", "isaac")

        assert again["action"] == "none"
        assert _links(db_session, "evt-1") == ["isaac"]
        assert _count(db_session, "isaac") == 4
        assert len(_actions(db_session, "evt-1")) == 1

    @pytest.mark.asyncio
    async def test_both_entity_pages_list_the_event(self, db_session, service, scene):
        await service.assign_event(db_session, "evt-1", "isaac")
        await service.assign_event(db_session, "evt-1", "bmw-x3")

        for entity_id in ("isaac", "bmw-x3"):
            events, total = await service.get_entity_events(db_session, entity_id)
            assert total == 1
            assert events[0]["id"] == "evt-1"

    @pytest.mark.asyncio
    async def test_cap_per_event(self, db_session, service, scene):
        for i in range(MAX_ENTITIES_PER_EVENT):
            make_entity(db_session=db_session, id=f"p{i}", entity_type="person")
            await service.assign_event(db_session, "evt-1", f"p{i}")

        with pytest.raises(EventEntityLimitError):
            await service.assign_event(db_session, "evt-1", "isaac")
        assert len(_links(db_session, "evt-1")) == MAX_ENTITIES_PER_EVENT
        assert _count(db_session, "isaac") == 3

    @pytest.mark.asyncio
    async def test_unknown_event_or_entity_raises_value_error(self, db_session, service, scene):
        with pytest.raises(ValueError):
            await service.assign_event(db_session, "missing", "isaac")
        with pytest.raises(ValueError):
            await service.assign_event(db_session, "evt-1", "missing")

    @pytest.mark.asyncio
    async def test_adding_a_match_only_entity_creates_the_link(self, db_session, service, scene):
        """Live Protect ingest records named matches only in matched_entity_ids."""
        scene["event"].matched_entity_ids = json.dumps(["isaac"])
        db_session.commit()

        result = await service.assign_event(db_session, "evt-1", "isaac")

        assert result["action"] == "add"
        assert _links(db_session, "evt-1") == ["isaac"]
        assert result["entities"][0]["linked"] is True


class TestRemoveOne:
    @pytest.mark.asyncio
    async def test_removing_one_keeps_the_other(self, db_session, service, scene):
        await service.assign_event(db_session, "evt-1", "isaac")
        await service.assign_event(db_session, "evt-1", "bmw-x3")

        assert await service.unlink_event(db_session, "bmw-x3", "evt-1") is True

        assert _links(db_session, "evt-1") == ["isaac"]
        assert _count(db_session, "bmw-x3") == 5
        assert _count(db_session, "isaac") == 4
        event = db_session.query(Event).filter(Event.id == "evt-1").one()
        assert parse_entity_id_list(event.matched_entity_ids) == ["isaac"]
        assert event.final_entity_id == "isaac"
        assert _actions(db_session, "evt-1")[-1] == ("remove", "bmw-x3", None)

    @pytest.mark.asyncio
    async def test_removing_the_primary_promotes_the_next(self, db_session, service, scene):
        await service.assign_event(db_session, "evt-1", "isaac")
        await service.assign_event(db_session, "evt-1", "bmw-x3")

        await service.unlink_event(db_session, "isaac", "evt-1")

        event = db_session.query(Event).filter(Event.id == "evt-1").one()
        assert event.final_entity_id == "bmw-x3"
        assert event.final_entity_type == "vehicle"

        await service.unlink_event(db_session, "bmw-x3", "evt-1")
        db_session.refresh(event)
        assert event.final_entity_id is None
        assert event.matched_entity_ids is None
        assert _links(db_session, "evt-1") == []

    @pytest.mark.asyncio
    async def test_removing_a_match_only_entity(self, db_session, service, scene):
        scene["event"].matched_entity_ids = json.dumps(["isaac", "bmw-x3"])
        db_session.commit()

        assert await service.unlink_event(db_session, "isaac", "evt-1") is True

        event = db_session.query(Event).filter(Event.id == "evt-1").one()
        assert parse_entity_id_list(event.matched_entity_ids) == ["bmw-x3"]
        # It never had a link, so the count was never incremented.
        assert _count(db_session, "isaac") == 3

    @pytest.mark.asyncio
    async def test_removing_an_entity_not_on_the_event(self, db_session, service, scene):
        assert await service.unlink_event(db_session, "isaac", "evt-1") is False
        assert _actions(db_session, "evt-1") == []


class TestReplace:
    @pytest.mark.asyncio
    async def test_replace_removes_the_others(self, db_session, service, scene):
        make_entity(db_session=db_session, id="brent", entity_type="person", name="Brent",
                    occurrence_count=2)
        await service.assign_event(db_session, "evt-1", "isaac")
        await service.assign_event(db_session, "evt-1", "bmw-x3")

        result = await service.assign_event(db_session, "evt-1", "brent", replace=True)

        assert result["action"] == "replace"
        assert _links(db_session, "evt-1") == ["brent"]
        assert _count(db_session, "isaac") == 3
        assert _count(db_session, "bmw-x3") == 5
        assert _count(db_session, "brent") == 3
        event = db_session.query(Event).filter(Event.id == "evt-1").one()
        assert parse_entity_id_list(event.matched_entity_ids) == ["brent"]
        assert event.final_entity_id == "brent"
        actions = _actions(db_session, "evt-1")[2:]
        assert ("move_from", "isaac", "brent") in actions
        assert ("move_from", "bmw-x3", "brent") in actions
        assert ("move_to", "isaac", "brent") in actions

    @pytest.mark.asyncio
    async def test_replace_on_an_empty_event_is_an_add(self, db_session, service, scene):
        result = await service.assign_event(db_session, "evt-1", "isaac", replace=True)
        assert result["action"] == "add"
        assert _links(db_session, "evt-1") == ["isaac"]


class TestMerge:
    @pytest.mark.asyncio
    async def test_merge_when_both_entities_are_on_one_event(self, db_session, service, scene):
        dup = make_entity(db_session=db_session, id="isaac-dup", entity_type="person",
                          name="Isaac again", occurrence_count=0)
        other_event = make_event(db_session=db_session, id="evt-2", camera_id="cam-driveway")
        await service.assign_event(db_session, "evt-1", "isaac")       # isaac 4
        await service.assign_event(db_session, "evt-1", "isaac-dup")   # dup 1
        await service.assign_event(db_session, "evt-2", "isaac-dup")   # dup 2
        # Make the duplicate primary on evt-2 and present in alert ids.
        assert other_event.final_entity_id == "isaac-dup"

        result = await service.merge_entities(db_session, "isaac", dup.id)

        assert result["events_moved"] == 2
        assert _links(db_session, "evt-1") == ["isaac"]
        assert _links(db_session, "evt-2") == ["isaac"]
        # evt-1 counted once: 4 + 2 - 1 overlap
        assert _count(db_session, "isaac") == 5
        db_session.expire_all()
        evt1 = db_session.query(Event).filter(Event.id == "evt-1").one()
        evt2 = db_session.query(Event).filter(Event.id == "evt-2").one()
        assert parse_entity_id_list(evt1.matched_entity_ids) == ["isaac"]
        assert parse_entity_id_list(evt2.matched_entity_ids) == ["isaac"]
        assert evt2.final_entity_id == "isaac"
        assert evt2.final_entity_name == "Isaac"


class TestBuildEventEntities:
    @pytest.mark.asyncio
    async def test_order_flags_and_vehicle_descriptor(self, db_session, service, scene):
        await service.assign_event(db_session, "evt-1", "bmw-x3")
        await service.assign_event(db_session, "evt-1", "isaac")
        event = scene["event"]
        # Primary is the BMW (first added). Make Isaac primary instead.
        event.final_entity_id = "isaac"
        # A deleted entity's id lingering in matched ids is skipped.
        event.matched_entity_ids = json.dumps(["bmw-x3", "isaac", "gone"])
        db_session.commit()

        entities = build_event_entities(db_session, [event])["evt-1"]

        assert [e["id"] for e in entities] == ["isaac", "bmw-x3"]
        assert entities[0]["is_primary"] is True
        bmw = entities[1]
        assert bmw["entity_type"] == "vehicle"
        assert bmw["vehicle_make"] == "BMW"
        assert bmw["vehicle_model"] == "X3"
        assert bmw["display_name"] == "Black Bmw X3"  # RecognizedEntity.display_name title-cases
        assert bmw["linked"] is True
        assert bmw["similarity_score"] == 1.0

    def test_match_only_entities_are_included(self, db_session, scene):
        event = scene["event"]
        event.matched_entity_ids = json.dumps(["isaac", "bmw-x3"])
        db_session.commit()

        entities = build_event_entities(db_session, [event])["evt-1"]
        assert [(e["id"], e["linked"]) for e in entities] == [
            ("isaac", False), ("bmw-x3", False),
        ]

    def test_empty_input(self, db_session):
        assert build_event_entities(db_session, []) == {}

    def test_parse_entity_id_list_keeps_strings_only(self):
        assert parse_entity_id_list('["a", 7, null, "a", " b "]') == ["a", "b"]
        assert parse_entity_id_list("not-json") == []
        assert parse_entity_id_list('{"a": 1}') == []
        assert parse_entity_id_list(None) == []


class TestReanalysisRewriteUsesAllEntities:
    @pytest.mark.asyncio
    async def test_person_and_vehicle_both_named(self, db_session, service, scene):
        from app.services.entity_alert_service import (
            get_entity_alert_service,
            reset_entity_alert_service,
        )

        reset_entity_alert_service()
        db_session.query(RecognizedEntity).filter(RecognizedEntity.id == "bmw-x3").update(
            {"name": "Isaac's BMW"}
        )
        db_session.commit()
        await service.assign_event(db_session, "evt-1", "isaac")
        await service.assign_event(db_session, "evt-1", "bmw-x3")

        rewritten = await get_entity_alert_service().rewrite_reanalysis_description(
            db_session,
            scene["event"],
            "A person arrives in a vehicle at the driveway. It is a black BMW.",
        )
        assert "Isaac" in rewritten
        assert "BMW" in rewritten
        assert "a person" not in rewritten.lower()

    @pytest.mark.asyncio
    async def test_removed_entity_is_not_brought_back(self, db_session, service, scene):
        """A stale face embedding must not re-apply a name the user removed."""
        from app.models.face_embedding import FaceEmbedding
        from app.services.entity_alert_service import (
            collect_linked_entity_ids,
            reset_entity_alert_service,
        )

        reset_entity_alert_service()
        await service.assign_event(db_session, "evt-1", "isaac")
        await service.assign_event(db_session, "evt-1", "bmw-x3")
        db_session.add(FaceEmbedding(
            event_id="evt-1",
            entity_id="isaac",
            embedding=json.dumps([0.0] * 4),
            bounding_box=json.dumps({"x": 0, "y": 0, "width": 1, "height": 1}),
            confidence=0.9,
            model_version="test",
        ))
        db_session.commit()

        await service.unlink_event(db_session, "isaac", "evt-1")

        event = db_session.query(Event).filter(Event.id == "evt-1").one()
        assert collect_linked_entity_ids(db_session, event) == ["bmw-x3"]

        # Linking again brings it back.
        await service.assign_event(db_session, "evt-1", "isaac")
        db_session.refresh(event)
        assert set(collect_linked_entity_ids(db_session, event)) == {"isaac", "bmw-x3"}


@pytest.mark.asyncio
async def test_merge_keeps_moved_links(db_session, service):
    """Regression: merge used to delete every link it had just moved.

    Sessions use autoflush=False and the entity_events relationship cascades
    deletes, so deleting the secondary removed the moved rows too.
    """
    make_camera(db_session=db_session, id="cam")
    make_entity(db_session=db_session, id="keep", occurrence_count=1)
    make_entity(db_session=db_session, id="drop", occurrence_count=1)
    make_event(db_session=db_session, id="e-only-drop", camera_id="cam")
    db_session.add(EntityEvent(entity_id="drop", event_id="e-only-drop", similarity_score=0.9))
    db_session.commit()

    await service.merge_entities(db_session, "keep", "drop")

    assert _links(db_session, "e-only-drop") == ["keep"]
    assert _count(db_session, "keep") == 2


@pytest.mark.asyncio
async def test_automatic_matching_keeps_person_and_vehicle(db_session):
    """Pre-AI matching records a face match and a vehicle match together."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.entity_service import EntityMatchResult
    from app.services.pre_ai_context_service import (
        PreAIContextService,
        reset_pre_ai_context_service,
    )

    now = datetime.now(timezone.utc)

    def _match(entity_id, entity_type, name):
        return EntityMatchResult(
            entity_id=entity_id, entity_type=entity_type, name=name,
            first_seen_at=now - timedelta(days=3), last_seen_at=now,
            occurrence_count=4, similarity_score=0.9, is_new=False,
        )

    reset_pre_ai_context_service()
    helper = PreAIContextService()
    context_service = MagicMock()
    context_service.build_context_enhanced_prompt = AsyncMock(return_value=None)
    with patch(
        "app.services.pre_ai_context_service._privacy_flag_enabled", return_value=True
    ), patch.object(
        helper, "_safe_named_face_match",
        new=AsyncMock(return_value=_match("isaac", "person", "Isaac")),
    ):
        bundle = await helper.gather(
            db=db_session,
            camera_id="cam-driveway",
            camera_name="Driveway",
            event_time=now,
            detected_objects=["person", "vehicle"],
            thumbnail_base64="aGVsbG8=",
            embedding_vector=[0.1] * 8,
            clip_scene_entity=_match("bmw-x3", "vehicle", "Isaac's BMW"),
            context_service=context_service,
        )
    reset_pre_ai_context_service()

    assert bundle.matched_entity_ids == ["isaac", "bmw-x3"]
