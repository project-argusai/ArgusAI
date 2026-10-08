"""Per-object galleries: observations, enrollment, and the live path.

Observations are per-event crops that never change a gallery by
themselves. Only an explicit assign (or "use as reference") enrolls one,
so unconfirmed matches can't drift a reference.
"""
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.models.entity_gallery_item import EntityGalleryItem
from app.models.event import Event
from app.models.face_embedding import FaceEmbedding
from app.models.system_setting import SystemSetting
from app.models.vehicle_embedding import VehicleEmbedding
from app.services.ai_types import FACE_RECOGNITION_ENABLED, VEHICLE_RECOGNITION_ENABLED
from app.services.entity_gallery_service import (
    get_entity_gallery_service,
    load_gallery_index,
    mark_parked_vehicles,
    read_crop,
    resolve_crop_path,
)
from app.services.entity_service import get_entity_service
from app.services.event_entity_linking import run_post_persist_entity_steps, verify_named_identities
from app.services.face_recognition_service import SFACE_MODEL_VERSION
from app.services.object_identity_service import (
    VEHICLE_CROP_MODEL_VERSION,
    FaceObservation,
    ObjectAnalysis,
    VehicleObservation,
    analyze_image_bytes,
)
from tests.conftest import make_camera, make_entity, make_event

RNG = np.random.default_rng(42)


def unit(dim):
    v = RNG.normal(size=dim)
    return v / np.linalg.norm(v)


def with_cosine(ref, cos):
    noise = RNG.normal(size=ref.shape[0])
    noise -= noise.dot(ref) * ref
    noise /= np.linalg.norm(noise)
    return cos * ref + np.sqrt(1 - cos * cos) * noise


def face(embedding=None, w=80, x=10):
    return FaceObservation(
        bbox={"x": x, "y": 10, "width": w, "height": w},
        score=0.95,
        embedding=unit(128) if embedding is None else embedding,
        crop_jpeg=b"\xff\xd8face-jpeg",
    )


def vehicle(embedding=None, color="red", w=200, x=10, stationary=False):
    return VehicleObservation(
        bbox={"x": x, "y": 20, "width": w, "height": 120},
        score=0.9,
        vehicle_type="car",
        crop_jpeg=b"\xff\xd8car-jpeg",
        color=color,
        area_fraction=0.1,
        embedding=unit(512) if embedding is None else embedding,
        stationary=stationary,
    )


@pytest.fixture
def crops_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ENTITY_CROPS_DIR", str(tmp_path / "crops"), raising=False)
    return tmp_path / "crops"


def _enable(db, face=True, vehicle=True):
    for key, on in ((FACE_RECOGNITION_ENABLED, face), (VEHICLE_RECOGNITION_ENABLED, vehicle)):
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if row is None:
            db.add(SystemSetting(key=key, value="true" if on else "false"))
        else:
            row.value = "true" if on else "false"
    db.commit()


@pytest.fixture
def home(db_session, crops_dir):
    _enable(db_session)
    make_camera(db_session=db_session, id="cam-drive", name="Driveway")
    alex = make_entity(db_session, entity_type="person", name="Alex")
    tesla = make_entity(db_session, entity_type="vehicle", name="Alex's Tesla",
                        vehicle_color="red", vehicle_make="tesla", vehicle_model="model y")
    make_event(db_session=db_session, id="evt-1", camera_id="cam-drive",
               objects_detected=json.dumps(["person", "vehicle"]))
    make_event(db_session=db_session, id="evt-2", camera_id="cam-drive",
               objects_detected=json.dumps(["vehicle"]))
    return SimpleNamespace(db=db_session, alex=alex, tesla=tesla, gallery=get_entity_gallery_service())


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------

class TestObservations:
    def test_save_writes_rows_and_crops_without_an_entity(self, home):
        created = home.gallery.save_observations(
            home.db, "evt-1", ObjectAnalysis(faces=[face()], vehicles=[vehicle()])
        )
        assert len(created["face"]) == 1 and len(created["vehicle"]) == 1
        f = home.db.query(FaceEmbedding).one()
        v = home.db.query(VehicleEmbedding).one()
        assert f.entity_id is None and v.entity_id is None
        assert f.model_version == SFACE_MODEL_VERSION and v.model_version == VEHICLE_CROP_MODEL_VERSION
        assert v.dominant_color == "red"
        assert read_crop(f.crop_path) == b"\xff\xd8face-jpeg"
        assert f.crop_path.startswith("observations/face/")

    def test_save_is_idempotent_per_event(self, home):
        a = ObjectAnalysis(faces=[face()])
        home.gallery.save_observations(home.db, "evt-1", a)
        again = home.gallery.save_observations(home.db, "evt-1", a)
        assert again["face"] == []
        assert home.db.query(FaceEmbedding).count() == 1

    def test_vehicle_without_embedding_is_not_stored(self, home):
        v = vehicle()
        v.embedding = None
        created = home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(vehicles=[v]))
        assert created["vehicle"] == []

    @pytest.mark.asyncio
    async def test_post_persist_step_stores_observations_and_never_raises(self, home):
        @contextmanager
        def factory():
            yield home.db

        await run_post_persist_entity_steps(
            "evt-1", session_factory=factory, object_analysis=ObjectAnalysis(faces=[face()])
        )
        assert home.db.query(FaceEmbedding).count() == 1
        with patch.object(type(home.gallery), "save_observations", side_effect=RuntimeError("disk full")):
            await run_post_persist_entity_steps(
                "evt-2", session_factory=factory, object_analysis=ObjectAnalysis(faces=[face()])
            )


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------

class TestEnrollment:
    @pytest.mark.asyncio
    async def test_single_face_is_enrolled_and_copied(self, home):
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()]))
        result = await home.gallery.enroll_from_event(home.db, home.alex, "evt-1")
        assert result.status == "enrolled"
        item = result.items[0]
        assert item.kind == "face" and item.source_event_id == "evt-1"
        assert item.crop_path == f"gallery/{home.alex.id}/{item.id}.jpg"
        assert read_crop(item.crop_path) == b"\xff\xd8face-jpeg"
        # The observation itself is not re-owned (no drift from observations).
        assert home.db.query(FaceEmbedding).one().entity_id is None
        again = await home.gallery.enroll_from_event(home.db, home.alex, "evt-1")
        assert again.status == "already_enrolled"
        index = load_gallery_index(home.db)
        assert list(index.faces) == [home.alex.id]

    @pytest.mark.asyncio
    async def test_two_similar_crops_are_ambiguous_until_one_is_picked(self, home):
        home.gallery.save_observations(
            home.db, "evt-2", ObjectAnalysis(vehicles=[vehicle(w=200), vehicle(w=180, x=300)])
        )
        result = await home.gallery.enroll_from_event(home.db, home.tesla, "evt-2")
        assert result.status == "ambiguous" and len(result.candidates) == 2
        assert home.db.query(EntityGalleryItem).count() == 0
        chosen = result.candidates[1]["id"]
        picked = await home.gallery.enroll_from_event(home.db, home.tesla, "evt-2", observation_id=chosen)
        assert picked.status == "enrolled" and picked.items[0].source_observation_id == chosen

    @pytest.mark.asyncio
    async def test_clearly_largest_vehicle_is_picked(self, home):
        home.gallery.save_observations(
            home.db, "evt-2", ObjectAnalysis(vehicles=[vehicle(w=400), vehicle(w=100, x=500)])
        )
        result = await home.gallery.enroll_from_event(home.db, home.tesla, "evt-2")
        assert result.status == "enrolled"

    @pytest.mark.asyncio
    async def test_colour_filter_leaves_the_red_car(self, home):
        home.gallery.save_observations(
            home.db, "evt-2", ObjectAnalysis(vehicles=[vehicle(color="black"), vehicle(color="red", x=300)])
        )
        result = await home.gallery.enroll_from_event(home.db, home.tesla, "evt-2")
        assert result.status == "enrolled" and result.items[0].dominant_color == "red"

    @pytest.mark.asyncio
    async def test_privacy_flag_off_disables_enrollment(self, home):
        _enable(home.db, face=False)
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()]))
        result = await home.gallery.enroll_from_event(home.db, home.alex, "evt-1")
        assert result.status == "disabled"

    @pytest.mark.asyncio
    async def test_no_crop_on_event(self, home):
        result = await home.gallery.enroll_from_event(home.db, home.alex, "evt-1", observe_if_missing=False)
        assert result.status == "no_observation"

    @pytest.mark.asyncio
    async def test_unnamed_entities_are_not_in_the_index(self, home):
        anon = make_entity(home.db, entity_type="person", name=None)
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()]))
        assert (await home.gallery.enroll_from_event(home.db, anon, "evt-1")).status == "enrolled"
        assert load_gallery_index(home.db).faces == {}

    @pytest.mark.asyncio
    async def test_unenroll_reset_and_privacy_delete_remove_files(self, home):
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()], vehicles=[vehicle()]))
        f = (await home.gallery.enroll_from_event(home.db, home.alex, "evt-1")).items[0]
        v = (await home.gallery.enroll_from_event(home.db, home.tesla, "evt-1")).items[0]
        f_path, v_path = resolve_crop_path(f.crop_path), resolve_crop_path(v.crop_path)
        assert os.path.isfile(f_path) and os.path.isfile(v_path)

        assert home.gallery.unenroll_event(home.db, home.alex.id, "evt-1") == 1
        assert not os.path.exists(f_path)
        assert home.gallery.reset_entity(home.db, home.tesla.id) == 1
        assert not os.path.exists(v_path)
        assert home.db.query(EntityGalleryItem).count() == 0

    @pytest.mark.asyncio
    async def test_delete_all_faces_clears_face_galleries(self, home):
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()], vehicles=[vehicle()]))
        await home.gallery.enroll_from_event(home.db, home.alex, "evt-1")
        await home.gallery.enroll_from_event(home.db, home.tesla, "evt-1")
        from app.services.face_embedding_service import FaceEmbeddingService

        await FaceEmbeddingService().delete_all_faces(home.db)
        kinds = [k for (k,) in home.db.query(EntityGalleryItem.kind).all()]
        assert kinds == ["vehicle"]


class TestEntityServiceIntegration:
    @pytest.mark.asyncio
    async def test_assign_enrolls_and_unlink_removes(self, home):
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()]))
        svc = get_entity_service()
        result = await svc.assign_event(home.db, "evt-1", home.alex.id)
        assert result["reference"]["status"] == "enrolled"
        assert home.db.query(EntityGalleryItem).filter_by(entity_id=home.alex.id).count() == 1
        await svc.unlink_event(home.db, home.alex.id, "evt-1")
        assert home.db.query(EntityGalleryItem).filter_by(entity_id=home.alex.id).count() == 0

    @pytest.mark.asyncio
    async def test_replace_moves_the_reference(self, home):
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()]))
        sam = make_entity(home.db, entity_type="person", name="Sam")
        svc = get_entity_service()
        await svc.assign_event(home.db, "evt-1", home.alex.id)
        result = await svc.assign_event(home.db, "evt-1", sam.id, replace=True)
        assert result["reference"]["status"] == "enrolled"
        owners = [e for (e,) in home.db.query(EntityGalleryItem.entity_id).all()]
        assert owners == [sam.id]

    @pytest.mark.asyncio
    async def test_enrollment_failure_never_fails_the_assign(self, home):
        svc = get_entity_service()
        with patch.object(type(home.gallery), "enroll_from_event", side_effect=RuntimeError("boom")):
            result = await svc.assign_event(home.db, "evt-1", home.alex.id)
        assert result["reference"]["status"] == "error"
        assert home.alex.id in [e["id"] for e in result["entities"]]

    @pytest.mark.asyncio
    async def test_merge_moves_gallery_items(self, home):
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()]))
        dup = make_entity(home.db, entity_type="person", name="Alex (dup)")
        await home.gallery.enroll_from_event(home.db, dup, "evt-1")
        await get_entity_service().merge_entities(home.db, home.alex.id, dup.id)
        owners = [e for (e,) in home.db.query(EntityGalleryItem.entity_id).all()]
        assert owners == [home.alex.id]

    @pytest.mark.asyncio
    async def test_delete_entity_removes_gallery_files(self, home):
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()]))
        item = (await home.gallery.enroll_from_event(home.db, home.alex, "evt-1")).items[0]
        path = resolve_crop_path(item.crop_path)
        assert await get_entity_service().delete_entity(home.db, home.alex.id)
        assert not os.path.exists(path)


def test_gallery_survives_event_retention(tmp_path, crops_dir):
    """Deleting the source event keeps the reference (source_event_id -> NULL)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'fk.db'}")

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        make_camera(db_session=db, id="cam", name="Cam")
        alex = make_entity(db, entity_type="person", name="Alex")
        make_event(db_session=db, id="old", camera_id="cam")
        db.add(EntityGalleryItem(id="g1", entity_id=alex.id, kind="face", model_version=SFACE_MODEL_VERSION,
                                 embedding=json.dumps([0.0] * 128), source_event_id="old"))
        db.commit()
        db.query(Event).filter(Event.id == "old").delete()
        db.commit()
        db.expire_all()
        item = db.query(EntityGalleryItem).one()
        assert item.source_event_id is None
    finally:
        db.close()
        engine.dispose()


def test_prune_orphan_crops(home):
    home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face()]))
    kept = resolve_crop_path(home.db.query(FaceEmbedding).one().crop_path)
    orphan = os.path.join(os.path.dirname(kept), "orphan.jpg")
    young = os.path.join(os.path.dirname(kept), "young.jpg")
    for p in (orphan, young):
        with open(p, "wb") as fh:
            fh.write(b"x")
    old = time.time() - 7200
    os.utime(orphan, (old, old))
    os.utime(kept, (old, old))
    assert home.gallery.prune_orphan_crops(home.db) == 1
    assert os.path.exists(kept) and os.path.exists(young) and not os.path.exists(orphan)


# ---------------------------------------------------------------------------
# Parked vehicles
# ---------------------------------------------------------------------------

class TestParkedVehicles:
    def _seed(self, db, gallery, *, embedding, camera="cam-drive", when=None, event_id="evt-old", x=10):
        make_event(db_session=db, id=event_id, camera_id=camera,
                   timestamp=when or datetime.now(timezone.utc) - timedelta(hours=2))
        gallery.save_observations(db, event_id, ObjectAnalysis(vehicles=[vehicle(embedding, x=x)]))

    def test_same_place_and_look_is_parked(self, home):
        e = unit(512)
        self._seed(home.db, home.gallery, embedding=e)
        obs = [vehicle(with_cosine(e, 0.98)), vehicle(unit(512), x=600)]
        assert mark_parked_vehicles(home.db, "cam-drive", obs) == 1
        assert obs[0].stationary and not obs[1].stationary

    def test_moved_or_other_camera_or_stale_is_not_parked(self, home):
        e = unit(512)
        make_camera(db_session=home.db, id="cam-porch", name="Porch")
        self._seed(home.db, home.gallery, embedding=e, x=400, event_id="moved")
        self._seed(home.db, home.gallery, embedding=e, camera="cam-porch", event_id="porch")
        self._seed(home.db, home.gallery, embedding=e, event_id="stale",
                   when=datetime.now(timezone.utc) - timedelta(days=5))
        obs = [vehicle(with_cosine(e, 0.98))]
        assert mark_parked_vehicles(home.db, "cam-drive", obs) == 0

    def test_current_event_is_excluded(self, home):
        e = unit(512)
        self._seed(home.db, home.gallery, embedding=e, event_id="evt-now")
        obs = [vehicle(e)]
        assert mark_parked_vehicles(home.db, "cam-drive", obs, exclude_event_id="evt-now") == 0


# ---------------------------------------------------------------------------
# Live linking with galleries
# ---------------------------------------------------------------------------

class TestLiveLinking:
    @pytest.mark.asyncio
    async def _enroll_tesla(self, home, emb):
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(vehicles=[vehicle(emb)]))
        assert (await home.gallery.enroll_from_event(home.db, home.tesla, "evt-1")).status == "enrolled"

    @pytest.mark.asyncio
    async def test_crop_and_colour_link_without_a_description(self, home):
        ref = unit(512)
        await self._enroll_tesla(home, ref)
        analysis = ObjectAnalysis(vehicles=[vehicle(with_cosine(ref, 0.95), "red")])
        out = verify_named_identities(home.db, description=None, candidates=[], looks_like_vehicle=True,
                                      object_analysis=analysis)
        assert [e.entity_id for e in out] == [home.tesla.id]
        assert out[0].similarity_score == pytest.approx(0.95, abs=1e-3)

    @pytest.mark.asyncio
    async def test_empty_driveway_with_a_gallery_links_nothing(self, home):
        await self._enroll_tesla(home, unit(512))
        out = verify_named_identities(home.db, description="The driveway is empty.", candidates=[],
                                      looks_like_vehicle=True, object_analysis=ObjectAnalysis())
        assert out == []

    @pytest.mark.asyncio
    async def test_person_event_never_links_a_vehicle(self, home):
        ref = unit(512)
        await self._enroll_tesla(home, ref)
        analysis = ObjectAnalysis(vehicles=[vehicle(with_cosine(ref, 0.97), "red")])
        out = verify_named_identities(home.db, description="A person walks by a red Tesla.", candidates=[],
                                      looks_like_vehicle=False, object_analysis=analysis)
        assert out == []

    @pytest.mark.asyncio
    async def test_ai_failure_branch_still_links_a_crop_identified_vehicle(self, home):
        from app.services.protect_event_handler import ProtectEventHandler

        ref = unit(512)
        await self._enroll_tesla(home, ref)
        bundle = SimpleNamespace(
            named_identities=[], embedding_vector=None,
            object_analysis=ObjectAnalysis(vehicles=[vehicle(with_cosine(ref, 0.95), "red")]),
        )
        fields = ProtectEventHandler()._identity_only_fields("vehicle", home.db, bundle)
        assert json.loads(fields["matched_entity_ids"]) == [home.tesla.id]
        assert fields["recognition_status"] == "known"

    @pytest.mark.asyncio
    async def test_pre_ai_names_a_person_from_the_face_gallery(self, home):
        from app.services.pre_ai_context_service import PreAIContextService

        ref = unit(128)
        home.gallery.save_observations(home.db, "evt-1", ObjectAnalysis(faces=[face(ref)]))
        await home.gallery.enroll_from_event(home.db, home.alex, "evt-1")
        analysis = ObjectAnalysis(faces=[face(with_cosine(ref, 0.6))], faces_checked=True)
        ctx = MagicMock()
        ctx.build_context_enhanced_prompt = AsyncMock(return_value=None)
        helper = PreAIContextService()
        with patch.object(PreAIContextService, "_safe_object_analysis", AsyncMock(return_value=analysis)), \
                patch.object(PreAIContextService, "_safe_embedding", AsyncMock(return_value=None)):
            bundle = await helper.gather(
                db=home.db, camera_id="cam-drive", camera_name="Driveway",
                event_time=datetime.now(timezone.utc), detected_objects=["person"],
                thumbnail_base64="aGVsbG8=", event_type="person", context_service=ctx,
            )
        assert bundle.matched_entity_ids == [home.alex.id]
        assert bundle.object_analysis is analysis

    @pytest.mark.asyncio
    async def test_pre_ai_skips_the_scene_hint_once_vehicle_galleries_exist(self, home):
        from app.services.entity_service import EntityMatchResult
        from app.services.pre_ai_context_service import PreAIContextService

        await self._enroll_tesla(home, unit(512))
        scene = EntityMatchResult(
            entity_id=home.tesla.id, entity_type="vehicle", name=home.tesla.name,
            first_seen_at=home.tesla.first_seen_at, last_seen_at=home.tesla.last_seen_at,
            occurrence_count=1, similarity_score=0.88, is_new=False,
        )
        ctx = MagicMock()
        ctx.build_context_enhanced_prompt = AsyncMock(return_value=None)
        with patch.object(PreAIContextService, "_safe_object_analysis", AsyncMock(return_value=ObjectAnalysis())):
            bundle = await PreAIContextService().gather(
                db=home.db, camera_id="cam-drive", camera_name="Driveway",
                event_time=datetime.now(timezone.utc), detected_objects=["vehicle"],
                thumbnail_base64="aGVsbG8=", embedding_vector=[0.1] * 8, event_type="vehicle",
                clip_scene_entity=scene, context_service=ctx,
            )
        assert bundle.matched_entity_ids == []


@pytest.mark.asyncio
async def test_analysis_fails_open_on_garbage_bytes():
    result = await analyze_image_bytes(b"not an image", faces=True, vehicles=True)
    assert result.is_empty
    assert (await analyze_image_bytes(b"", faces=True, vehicles=True)).is_empty
