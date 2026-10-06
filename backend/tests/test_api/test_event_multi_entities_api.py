"""API shape for several entities on one event (issue #652)."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.models.entity_adjustment import EntityAdjustment
from app.services.entity_service import MAX_ENTITIES_PER_EVENT, reset_entity_service
from main import app
from tests.conftest import make_camera, make_entity, make_event


@pytest.fixture
def db_session():
    """Private in-memory database (the test_api conftest one is module-shared)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def api_client(db_session):
    previous = app.dependency_overrides.get(get_db)

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    reset_entity_service()
    client = TestClient(app)
    yield client
    reset_entity_service()
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


@pytest.fixture
def seeded(db_session):
    make_camera(db_session=db_session, id="cam-driveway", name="Driveway")
    make_entity(db_session=db_session, id="isaac", entity_type="person", name="Isaac",
                occurrence_count=1)
    make_entity(db_session=db_session, id="bmw-x3", entity_type="vehicle", name=None,
                vehicle_color="black", vehicle_make="BMW", vehicle_model="X3",
                occurrence_count=1)
    make_event(db_session=db_session, id="evt-1", camera_id="cam-driveway",
               objects_detected=json.dumps(["person", "vehicle"]))
    return db_session


def _assign(client, entity_id, **extra):
    return client.post(
        "/api/v1/context/events/evt-1/entity",
        json={"entity_id": entity_id, **extra},
    )


def test_add_two_entities_and_read_them_back(api_client, seeded):
    first = _assign(api_client, "isaac")
    second = _assign(api_client, "bmw-x3")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["action"] == "add"
    body = second.json()
    assert body["action"] == "add"
    assert [e["id"] for e in body["entities"]] == ["isaac", "bmw-x3"]

    detail = api_client.get("/api/v1/events/evt-1").json()
    assert [e["id"] for e in detail["entities"]] == ["isaac", "bmw-x3"]
    assert detail["entities"][0]["is_primary"] is True
    vehicle = detail["entities"][1]
    assert vehicle["entity_type"] == "vehicle"
    assert vehicle["vehicle_make"] == "BMW"
    assert vehicle["vehicle_model"] == "X3"
    assert vehicle["vehicle_color"] == "black"
    # Legacy single-entity fields mirror the primary entity.
    assert detail["entity_id"] == "isaac"
    assert detail["entity_name"] == "Isaac"

    listing = api_client.get("/api/v1/events").json()
    listed = next(e for e in listing["events"] if e["id"] == "evt-1")
    assert [e["id"] for e in listed["entities"]] == ["isaac", "bmw-x3"]
    assert listed["entity_id"] == "isaac"

    for entity_id in ("isaac", "bmw-x3"):
        page = api_client.get(f"/api/v1/context/entities/{entity_id}/events").json()
        assert [e["id"] for e in page["events"]] == ["evt-1"]
        entity = api_client.get(f"/api/v1/context/entities/{entity_id}").json()
        assert entity["occurrence_count"] == 2


def test_remove_one_keeps_the_other(api_client, seeded):
    _assign(api_client, "isaac")
    _assign(api_client, "bmw-x3")

    removed = api_client.delete("/api/v1/context/entities/isaac/events/evt-1")

    assert removed.status_code == 200, removed.text
    assert [e["id"] for e in removed.json()["entities"]] == ["bmw-x3"]
    detail = api_client.get("/api/v1/events/evt-1").json()
    assert [e["id"] for e in detail["entities"]] == ["bmw-x3"]
    assert detail["entity_id"] == "bmw-x3"
    actions = [a.action for a in seeded.query(EntityAdjustment).all()]
    assert sorted(actions) == ["add", "add", "remove"]

    again = api_client.delete("/api/v1/context/entities/isaac/events/evt-1")
    assert again.status_code == 404


def test_replace_is_explicit(api_client, seeded):
    _assign(api_client, "isaac")
    replaced = _assign(api_client, "bmw-x3", replace=True)

    assert replaced.status_code == 200
    assert replaced.json()["action"] == "replace"
    assert [e["id"] for e in replaced.json()["entities"]] == ["bmw-x3"]


def test_cap_returns_409(api_client, seeded):
    for i in range(MAX_ENTITIES_PER_EVENT):
        make_entity(db_session=seeded, id=f"p{i}", entity_type="person")
        assert _assign(api_client, f"p{i}").status_code == 200

    over = _assign(api_client, "isaac")
    assert over.status_code == 409
    assert str(MAX_ENTITIES_PER_EVENT) in over.json()["detail"]


@pytest.mark.parametrize("payload", [
    {"entity_id": ""},
    {"entity_id": "x" * 129},
    {"entity_id": 123},
    {},
    {"entity_id": "isaac", "replace": "maybe"},
])
def test_request_validation(api_client, seeded, payload):
    response = api_client.post("/api/v1/context/events/evt-1/entity", json=payload)
    assert response.status_code == 422


def test_unknown_ids_return_404(api_client, seeded):
    assert _assign(api_client, "nobody").status_code == 404
    response = api_client.post(
        "/api/v1/context/events/missing/entity", json={"entity_id": "isaac"}
    )
    assert response.status_code == 404


def test_match_only_entities_are_listed_and_removable(api_client, seeded):
    """Live Protect ingest stores named matches only in matched_entity_ids."""
    from app.models.event import Event

    event = seeded.query(Event).filter(Event.id == "evt-1").one()
    event.matched_entity_ids = json.dumps(["isaac", "bmw-x3"])
    seeded.commit()

    detail = api_client.get("/api/v1/events/evt-1").json()
    assert [(e["id"], e["linked"]) for e in detail["entities"]] == [
        ("isaac", False), ("bmw-x3", False),
    ]

    removed = api_client.delete("/api/v1/context/entities/bmw-x3/events/evt-1")
    assert removed.status_code == 200
    seeded.refresh(event)
    assert json.loads(event.matched_entity_ids) == ["isaac"]
