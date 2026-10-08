"""Gallery endpoints: list, enroll ("use as reference"), remove, reset, crops."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.models.system_setting import SystemSetting
from app.models.user import UserRole
from app.services.ai_types import FACE_RECOGNITION_ENABLED, VEHICLE_RECOGNITION_ENABLED
from app.services.entity_gallery_service import get_entity_gallery_service
from app.services.object_identity_service import FaceObservation, ObjectAnalysis, VehicleObservation
from main import app
from tests.conftest import make_camera, make_entity, make_event


def _vec(dim, seed):
    v = np.random.default_rng(seed).normal(size=dim)
    return v / np.linalg.norm(v)


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ENTITY_CROPS_DIR", str(tmp_path / "crops"), raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_session):
    previous = app.dependency_overrides.get(get_db)

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


@pytest.fixture
def seeded(db_session):
    for key in (FACE_RECOGNITION_ENABLED, VEHICLE_RECOGNITION_ENABLED):
        db_session.add(SystemSetting(key=key, value="true"))
    db_session.commit()
    make_camera(db_session=db_session, id="cam-1", name="Driveway")
    make_entity(db_session, id="alex", entity_type="person", name="Alex")
    make_entity(db_session, id="car", entity_type="vehicle", name="Alex's Tesla", vehicle_color="red")
    make_event(db_session=db_session, id="evt-1", camera_id="cam-1")
    get_entity_gallery_service().save_observations(db_session, "evt-1", ObjectAnalysis(
        faces=[FaceObservation(bbox={"x": 1, "y": 1, "width": 60, "height": 60}, score=0.9,
                               embedding=_vec(128, 1), crop_jpeg=b"\xff\xd8face")],
        vehicles=[
            VehicleObservation(bbox={"x": 0, "y": 0, "width": 200, "height": 100}, score=0.9,
                               vehicle_type="car", crop_jpeg=b"\xff\xd8car1", color="red",
                               area_fraction=0.2, embedding=_vec(512, 2)),
            VehicleObservation(bbox={"x": 300, "y": 0, "width": 190, "height": 100}, score=0.9,
                               vehicle_type="car", crop_jpeg=b"\xff\xd8car2", color="red",
                               area_fraction=0.2, embedding=_vec(512, 3)),
        ],
    ))
    return db_session


BASE = "/api/v1/context"


def test_observations_and_crops(client, seeded):
    r = client.get(f"{BASE}/events/evt-1/observations")
    assert r.status_code == 200, r.text
    obs = r.json()["observations"]
    assert sorted(o["kind"] for o in obs) == ["face", "vehicle", "vehicle"]
    assert all(o["has_crop"] for o in obs)
    face = next(o for o in obs if o["kind"] == "face")
    crop = client.get(f"{BASE}/observations/face/{face['id']}/crop")
    assert crop.status_code == 200
    assert crop.headers["content-type"] == "image/jpeg"
    assert crop.content == b"\xff\xd8face"
    assert client.get(f"{BASE}/observations/face/nope/crop").status_code == 404
    assert client.get(f"{BASE}/observations/../crop").status_code == 404
    assert client.get(f"{BASE}/events/missing/observations").status_code == 404


def test_enroll_list_remove_reset(client, seeded):
    r = client.post(f"{BASE}/entities/alex/gallery", json={"event_id": "evt-1"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "enrolled"
    item = r.json()["items"][0]

    listed = client.get(f"{BASE}/entities/alex/gallery").json()
    assert [i["id"] for i in listed["items"]] == [item["id"]]
    crop = client.get(f"{BASE}/entities/alex/gallery/{item['id']}/crop")
    assert crop.status_code == 200 and crop.content == b"\xff\xd8face"

    assert client.delete(f"{BASE}/entities/alex/gallery/{item['id']}").json() == {"deleted_count": 1}
    assert client.delete(f"{BASE}/entities/alex/gallery/{item['id']}").status_code == 404

    client.post(f"{BASE}/entities/alex/gallery", json={"event_id": "evt-1"})
    assert client.delete(f"{BASE}/entities/alex/gallery?kind=face").json() == {"deleted_count": 1}


def test_two_similar_vehicles_need_a_pick(client, seeded):
    r = client.post(f"{BASE}/entities/car/gallery", json={"event_id": "evt-1"})
    body = r.json()
    assert body["status"] == "ambiguous" and len(body["candidates"]) == 2
    pick = body["candidates"][0]["id"]
    r = client.post(f"{BASE}/entities/car/gallery", json={"event_id": "evt-1", "observation_id": pick})
    assert r.json()["status"] == "enrolled"
    assert r.json()["items"][0]["source_observation_id"] == pick


def test_unknown_entity_or_event(client, seeded):
    assert client.get(f"{BASE}/entities/nope/gallery").status_code == 404
    assert client.post(f"{BASE}/entities/alex/gallery", json={"event_id": "missing"}).status_code == 404
    assert client.post(f"{BASE}/entities/alex/gallery", json={}).status_code == 422


def test_assign_response_carries_the_reference_status(client, seeded):
    r = client.post(f"{BASE}/events/evt-1/entity", json={"entity_id": "alex"})
    assert r.status_code == 200, r.text
    assert r.json()["reference"]["status"] == "enrolled"


@pytest.mark.real_user_roles
@pytest.mark.parametrize("role,enroll,reset", [
    (UserRole.VIEWER, 403, 403),
    (UserRole.OPERATOR, 200, 403),
    (UserRole.ADMIN, 200, 200),
])
def test_roles(client, seeded, role, enroll, reset):
    from app.api.v1.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u", username="u", role=role)
    try:
        assert client.get(f"{BASE}/entities/alex/gallery").status_code == 200
        assert client.post(f"{BASE}/entities/alex/gallery", json={"event_id": "evt-1"}).status_code == enroll
        assert client.delete(f"{BASE}/entities/alex/gallery").status_code == reset
    finally:
        app.dependency_overrides.pop(get_current_user, None)
