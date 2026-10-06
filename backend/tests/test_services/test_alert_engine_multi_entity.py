"""Person and vehicle rules on one multi-entity event (issue #652).

"Isaac detected" (person) and "BMW X3 detected" (vehicle) must both fire
for an event linked to both, once each, and still once per camera when
two cameras record the same moment (#646 keeps one event per camera).
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.alert_rule import AlertRule
from app.services.alert_engine import AlertEngine
from app.services.entity_service import EntityService, reset_entity_service
from tests.conftest import make_alert_rule, make_camera, make_entity, make_event

ANY_OBJECT = {"object_types": ["person", "vehicle"], "cameras": [], "min_confidence": 0}


@pytest.fixture
def rules(db_session):
    make_camera(db_session=db_session, id="cam-driveway", name="Driveway")
    make_camera(db_session=db_session, id="cam-garage", name="Garage")
    make_entity(db_session=db_session, id="isaac", entity_type="person", name="Isaac")
    make_entity(db_session=db_session, id="bmw-x3", entity_type="vehicle", name="Isaac's BMW",
                vehicle_make="BMW", vehicle_model="X3")
    isaac_rule = make_alert_rule(
        db_session=db_session, id="rule-isaac", name="Isaac detected",
        conditions=ANY_OBJECT, cooldown_minutes=0,
        entity_match_mode="specific", entity_id="isaac",
    )
    bmw_rule = make_alert_rule(
        db_session=db_session, id="rule-bmw", name="BMW X3 detected",
        conditions=ANY_OBJECT, cooldown_minutes=0,
        entity_ids=json.dumps(["bmw-x3"]),
    )
    stranger_rule = make_alert_rule(
        db_session=db_session, id="rule-stranger", name="Stranger",
        conditions=ANY_OBJECT, cooldown_minutes=0, entity_match_mode="unknown",
    )
    return isaac_rule, bmw_rule, stranger_rule


async def _event_with_both(db_session, event_id, camera_id, group="incident-1"):
    make_event(
        db_session=db_session, id=event_id, camera_id=camera_id,
        timestamp=datetime(2026, 10, 5, 18, 0, 0, tzinfo=timezone.utc),
        objects_detected=json.dumps(["person", "vehicle"]),
        correlation_group_id=group,
    )
    reset_entity_service()
    service = EntityService()
    await service.assign_event(db_session, event_id, "isaac")
    await service.assign_event(db_session, event_id, "bmw-x3")
    from app.models.event import Event
    return db_session.query(Event).filter(Event.id == event_id).one()


@pytest.mark.asyncio
async def test_person_and_vehicle_rules_both_match(db_session, rules):
    event = await _event_with_both(db_session, "evt-driveway", "cam-driveway")

    matched = AlertEngine(db_session).evaluate_all_rules(event)

    assert sorted(r.id for r in matched) == ["rule-bmw", "rule-isaac"]


@pytest.mark.asyncio
async def test_each_rule_fires_once_per_camera(db_session, rules):
    driveway = await _event_with_both(db_session, "evt-driveway", "cam-driveway")
    garage = await _event_with_both(db_session, "evt-garage", "cam-garage")

    engine = AlertEngine(db_session)
    with patch.object(
        AlertEngine, "_execute_dashboard_notification", new=AsyncMock(return_value=True)
    ) as notify:
        first = await engine.process_event(driveway)
        second = await engine.process_event(garage)

    assert sorted(first["matched_rule_ids"]) == ["rule-bmw", "rule-isaac"]
    assert sorted(second["matched_rule_ids"]) == ["rule-bmw", "rule-isaac"]
    # One notification per rule per camera event, not one per entity.
    fired = sorted((call.args[0].camera_id, call.args[1].id) for call in notify.await_args_list)
    assert fired == [
        ("cam-driveway", "rule-bmw"),
        ("cam-driveway", "rule-isaac"),
        ("cam-garage", "rule-bmw"),
        ("cam-garage", "rule-isaac"),
    ]
    db_session.expire_all()
    counts = {r.id: r.trigger_count for r in db_session.query(AlertRule).all()}
    assert counts == {"rule-isaac": 2, "rule-bmw": 2, "rule-stranger": 0}


@pytest.mark.asyncio
async def test_removing_the_car_stops_the_vehicle_rule(db_session, rules):
    event = await _event_with_both(db_session, "evt-driveway", "cam-driveway")
    await EntityService().unlink_event(db_session, "bmw-x3", "evt-driveway")
    db_session.refresh(event)

    matched = AlertEngine(db_session).evaluate_all_rules(event)

    assert [r.id for r in matched] == ["rule-isaac"]


def test_non_string_ids_in_matched_list_are_ignored(db_session, rules):
    """Ids stay strings: a numeric value never matches a text rule id."""
    event = make_event(
        db_session=db_session, id="evt-odd", camera_id="cam-driveway",
        objects_detected=json.dumps(["person"]),
        matched_entity_ids=json.dumps([123, None, "isaac"]),
    )

    matched = AlertEngine(db_session).evaluate_all_rules(event)

    assert [r.id for r in matched] == ["rule-isaac"]
