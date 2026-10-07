"""Manual links seed an empty entity embedding so recognition can match it.

Entities created by hand (or recreated after a wipe) start with the ``"[]"``
placeholder and are skipped by the match cache. Linking one to an event that
has a CLIP embedding must give it a usable reference vector.
"""
import json

import pytest

from app.models.event_embedding import EventEmbedding
from app.models.recognized_entity import RecognizedEntity
from app.services.entity_service import (
    EntityService,
    reset_entity_service,
    seed_entity_embedding_from_event,
)
from tests.conftest import make_camera, make_entity, make_event

VEC_A = [1.0] + [0.0] * 511
VEC_B = [0.0, 1.0] + [0.0] * 510


@pytest.fixture
def service():
    reset_entity_service()
    yield EntityService()
    reset_entity_service()


@pytest.fixture
def scene(db_session):
    camera = make_camera(db_session=db_session, id="cam-1", name="Driveway")
    make_entity(
        db_session=db_session, id="bmw", entity_type="vehicle", name="Isaac's BMW",
        reference_embedding="[]",
    )
    make_entity(
        db_session=db_session, id="brent", entity_type="person", name="Brent",
        reference_embedding=json.dumps(VEC_B),
    )
    for eid in ("evt-emb", "evt-noemb"):
        make_event(db_session=db_session, id=eid, camera_id=camera.id, description="x")
    db_session.add(EventEmbedding(
        event_id="evt-emb", embedding=json.dumps(VEC_A), model_version="clip-ViT-B-32-v1",
    ))
    db_session.commit()


def _embedding(db, entity_id):
    db.expire_all()
    return json.loads(
        db.query(RecognizedEntity).filter(RecognizedEntity.id == entity_id).one().reference_embedding
    )


@pytest.mark.asyncio
async def test_assign_seeds_empty_embedding(db_session, service, scene):
    await service.assign_event(db_session, "evt-emb", "bmw")
    assert _embedding(db_session, "bmw") == VEC_A


@pytest.mark.asyncio
async def test_seeded_entity_is_matchable(db_session, service, scene):
    service._load_entity_cache(db_session)
    assert "bmw" not in service._entity_cache

    await service.assign_event(db_session, "evt-emb", "bmw")

    match = await service.match_entity_only(db_session, embedding=VEC_A, threshold=0.75)
    assert match is not None and match.entity_id == "bmw"


@pytest.mark.asyncio
async def test_existing_embedding_is_not_overwritten(db_session, service, scene):
    await service.assign_event(db_session, "evt-emb", "brent")
    assert _embedding(db_session, "brent") == VEC_B


@pytest.mark.asyncio
async def test_event_without_embedding_leaves_placeholder(db_session, service, scene):
    result = await service.assign_event(db_session, "evt-noemb", "bmw")
    assert result["success"]
    assert _embedding(db_session, "bmw") == []


def test_wrong_dimension_is_ignored(db_session, scene):
    db_session.query(EventEmbedding).filter(EventEmbedding.event_id == "evt-emb").update(
        {"embedding": json.dumps([0.1] * 10)}
    )
    entity = db_session.query(RecognizedEntity).filter(RecognizedEntity.id == "bmw").one()
    assert seed_entity_embedding_from_event(db_session, entity, "evt-emb") is False
    assert entity.reference_embedding == "[]"
