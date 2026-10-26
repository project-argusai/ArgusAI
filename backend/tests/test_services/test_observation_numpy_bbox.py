"""Regression: live object observations were never stored (object_observations_failed TypeError).

MobileNet-SSD boxes come out of ``box.astype("int")`` as numpy int64; the
bbox dict then failed ``json.dumps`` in ``save_observations``, so every live
event with a vehicle crop lost its observations (prod: 0 vehicle_embeddings).
"""
import json

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.services.entity_gallery_service import get_entity_gallery_service
from app.services.object_identity_service import FaceObservation, ObjectAnalysis, VehicleObservation
from app.services.vehicle_detection_service import BoundingBox
from tests.conftest import make_camera, make_event


def _vec(dim, seed):
    v = np.random.default_rng(seed).normal(size=dim).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def db(tmp_path, monkeypatch):
    import app.services.entity_gallery_service as egs

    monkeypatch.setattr(egs, "resolve_crop_path", lambda rel: str(tmp_path / rel))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    make_camera(db_session=session, id="cam-1", name="Driveway")
    make_event(db_session=session, id="evt-np", camera_id="cam-1")
    yield session
    session.close()


def test_bounding_box_to_dict_is_plain_ints():
    bbox = BoundingBox(x=np.int64(10), y=np.int64(20), width=np.int64(30), height=np.int64(40)).to_dict()
    assert all(type(v) is int for v in bbox.values())
    json.dumps(bbox)


def test_save_observations_accepts_numpy_bbox_and_score(db):
    np_box = {k: np.int64(v) for k, v in {"x": 5, "y": 6, "width": 200, "height": 100}.items()}
    analysis = ObjectAnalysis(
        faces=[FaceObservation(bbox=dict(np_box), score=np.float32(0.9),
                               embedding=_vec(128, 1), crop_jpeg=b"\xff\xd8face")],
        vehicles=[VehicleObservation(bbox=dict(np_box), score=np.float32(0.8), vehicle_type="car",
                                     crop_jpeg=b"\xff\xd8car", color="blue", area_fraction=0.2,
                                     embedding=_vec(512, 2))],
    )
    created = get_entity_gallery_service().save_observations(db, "evt-np", analysis)
    assert len(created["vehicle"]) == 1 and len(created["face"]) == 1
    from app.models.vehicle_embedding import VehicleEmbedding

    row = db.query(VehicleEmbedding).filter_by(event_id="evt-np").one()
    assert json.loads(row.bounding_box) == {"x": 5, "y": 6, "width": 200, "height": 100}
