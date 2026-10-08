"""Opt-in ArcFace backend: selection, weight checks, per-model references, re-embedding.

Model calls are mocked. ``test_real_weights`` runs only when the user has
put the (non-commercial) weights in place; CI never has them.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.core.config import settings
from app.models.entity_gallery_item import EntityGalleryItem
from app.models.face_embedding import FaceEmbedding
from app.services import arcface_recognizer as arc
from app.services import face_recognition_service as frs
from app.services.entity_gallery_service import MatchThresholds, load_gallery_index, write_crop
from tests.conftest import make_entity, make_event

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "faces" / "astronaut_256.jpg"


@pytest.fixture(autouse=True)
def clean_backend(monkeypatch):
    monkeypatch.delenv("ARGUS_FACE_RECOGNIZER", raising=False)
    monkeypatch.delenv(arc.ARCFACE_MODEL_ENV, raising=False)
    monkeypatch.delenv(arc.ARCFACE_SHA256_ENV, raising=False)
    monkeypatch.setattr(settings, "ARGUS_FACE_RECOGNIZER", None, raising=False)
    monkeypatch.setattr(settings, "ARGUS_ARCFACE_MODEL_PATH", None, raising=False)
    monkeypatch.setattr(settings, "ARGUS_ARCFACE_SHA256", None, raising=False)
    frs.reset_face_recognition_service()
    yield
    frs.reset_face_recognition_service()


@pytest.fixture
def fake_weights(tmp_path, monkeypatch):
    path = tmp_path / "w600k_r50.onnx"
    path.write_bytes(b"not-really-onnx")
    monkeypatch.setattr(settings, "ARGUS_ARCFACE_MODEL_PATH", str(path), raising=False)
    monkeypatch.setattr(settings, "ARGUS_ARCFACE_SHA256", hashlib.sha256(b"not-really-onnx").hexdigest(), raising=False)
    return path


class FakeNet:
    def __init__(self):
        self.inputs = []

    def setInput(self, blob):
        self.inputs.append(blob)

    def forward(self):
        blob = self.inputs[-1]
        rng = np.random.default_rng(int(blob.sum() * 1000) % (2 ** 32))
        return rng.normal(size=(1, arc.ARCFACE_DIM)).astype(np.float32)


class FakeDetector:
    """One face whose landmarks sit on the ArcFace template, offset by (50, 40)."""

    def setInputSize(self, size):
        self.size = size

    def detect(self, image):
        pts = (arc.ARCFACE_TEMPLATE + np.array([50, 40], np.float32)).reshape(-1)
        row = np.concatenate([[50, 40, 112, 112], pts, [0.95]]).astype(np.float32)
        return 1, np.array([row])


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

class TestSelection:
    def test_sface_stays_the_default(self):
        svc = frs.get_face_recognition_service()
        assert svc.name == "sface" and svc.model_version == frs.SFACE_MODEL_VERSION

    def test_arcface_selected_from_env_when_weights_verify(self, fake_weights, monkeypatch):
        monkeypatch.setenv("ARGUS_FACE_RECOGNIZER", "arcface")
        svc = frs.get_face_recognition_service()
        assert isinstance(svc, arc.ArcFaceRecognizer)
        assert (svc.model_version, svc.dim) == (arc.ARCFACE_MODEL_VERSION, 512)
        assert frs.active_face_model() == (arc.ARCFACE_MODEL_VERSION, 512)

    def test_arcface_selected_from_settings_env_file(self, fake_weights, monkeypatch):
        monkeypatch.setattr(settings, "ARGUS_FACE_RECOGNIZER", "ArcFace", raising=False)
        assert frs.get_face_recognition_service().name == "arcface"

    def test_process_env_wins_over_settings(self, fake_weights, monkeypatch):
        monkeypatch.setattr(settings, "ARGUS_FACE_RECOGNIZER", "arcface", raising=False)
        monkeypatch.setenv("ARGUS_FACE_RECOGNIZER", "sface")
        assert frs.get_face_recognition_service().name == "sface"

    def test_missing_weights_fall_back_to_sface(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "ARGUS_ARCFACE_MODEL_PATH", str(tmp_path / "absent.onnx"), raising=False)
        monkeypatch.setenv("ARGUS_FACE_RECOGNIZER", "arcface")
        assert frs.get_face_recognition_service().name == "sface"

    def test_wrong_checksum_falls_back_to_sface(self, fake_weights, monkeypatch):
        monkeypatch.setattr(settings, "ARGUS_ARCFACE_SHA256", "0" * 64, raising=False)
        monkeypatch.setenv("ARGUS_FACE_RECOGNIZER", "arcface")
        assert frs.get_face_recognition_service().name == "sface"

    def test_threshold_follows_the_backend(self, fake_weights, monkeypatch):
        monkeypatch.delenv("ARGUS_FACE_MATCH_THRESHOLD", raising=False)
        assert MatchThresholds.from_env().face_match == pytest.approx(0.40)
        monkeypatch.setenv("ARGUS_FACE_RECOGNIZER", "arcface")
        frs.reset_face_recognition_service()
        assert MatchThresholds.from_env().face_match == pytest.approx(arc.ArcFaceRecognizer.default_match_threshold)

    def test_settings_declare_the_keys_so_env_file_works(self):
        from app.core.config import Settings

        for key in ("ARGUS_FACE_RECOGNIZER", "ARGUS_ARCFACE_MODEL_PATH", "ARGUS_ARCFACE_SHA256"):
            assert Settings.model_fields[key].default is None


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

class TestWeights:
    def test_verify(self, fake_weights, tmp_path, monkeypatch):
        assert arc.verify_weights(fake_weights) == (True, "ok")
        assert arc.verify_weights(tmp_path / "nope.onnx") == (False, "missing")
        monkeypatch.setattr(settings, "ARGUS_ARCFACE_SHA256", None, raising=False)
        assert arc.verify_weights(fake_weights) == (False, "checksum_mismatch")
        assert arc.expected_sha256() == arc.ARCFACE_SHA256

    def test_default_path_is_outside_git(self):
        path = arc.arcface_model_path()
        assert path.parts[-3:] == ("models", "arcface", arc.ARCFACE_FILE)
        gitignore = (Path(__file__).resolve().parents[3] / ".gitignore").read_text()
        assert "backend/app/models/arcface/" in gitignore

    def test_no_weights_in_repo(self):
        repo = Path(__file__).resolve().parents[3]
        tracked = [p for p in (repo / "backend").rglob("w600k*.onnx") if ".venv" not in p.parts]
        ignored_dir = repo / "backend" / "app" / "models" / "arcface"
        assert all(ignored_dir in p.parents for p in tracked)

    def test_unverified_load_refuses_mismatch(self, fake_weights, monkeypatch):
        monkeypatch.setattr(settings, "ARGUS_ARCFACE_SHA256", "f" * 64, raising=False)
        rec = arc.ArcFaceRecognizer(model_path=str(fake_weights))
        assert rec.is_available() is False
        assert rec.identify(np.zeros((200, 200, 3), np.uint8)) == []
        assert rec.embed_aligned(np.zeros((112, 112, 3), np.uint8)) is None

    def test_verify_script(self, fake_weights, tmp_path, capsys):
        from scripts.verify_arcface_weights import main

        assert main(["--path", str(fake_weights)]) == 0
        assert "OK" in capsys.readouterr().out
        assert main(["--path", str(tmp_path / "missing.onnx")]) == 1


# ---------------------------------------------------------------------------
# Embedding with a mocked network
# ---------------------------------------------------------------------------

class TestEmbedding:
    def rec(self):
        return arc.ArcFaceRecognizer(net=FakeNet(), detector=FakeDetector())

    def test_identify_aligns_and_embeds(self):
        image = np.random.default_rng(1).integers(0, 255, (300, 300, 3), dtype=np.uint8)
        faces = self.rec().identify(image)
        assert len(faces) == 1
        f = faces[0]
        assert f.embedding.shape == (512,) and np.linalg.norm(f.embedding) == pytest.approx(1.0, abs=1e-5)
        assert f.aligned_crop.shape == (112, 112, 3)
        # Landmarks on the template: alignment is a pure crop at the offset.
        assert np.abs(f.aligned_crop[20:90, 20:90].astype(int) - image[60:130, 70:140].astype(int)).mean() < 2

    def test_embed_aligned_resizes_and_preprocesses(self):
        rec = self.rec()
        vec = rec.embed_aligned(np.full((100, 90, 3), 200, np.uint8))
        assert vec.shape == (512,)
        blob = rec._net.inputs[-1]
        assert blob.shape == (1, 3, 112, 112)
        assert blob.max() == pytest.approx((200 - 127.5) / 127.5, abs=1e-5)

    def test_alignment_matches_opencv_template(self):
        row = np.zeros(15, np.float32)
        row[4:14] = (arc.ARCFACE_TEMPLATE * 2 + 10).reshape(-1)
        img = np.random.default_rng(3).integers(0, 255, (300, 300, 3), dtype=np.uint8)
        aligned = arc.align_face(img, row)
        assert aligned.shape == (112, 112, 3)


# ---------------------------------------------------------------------------
# References stay per model
# ---------------------------------------------------------------------------

def _vec(dim, seed):
    v = np.random.default_rng(seed).normal(size=dim)
    return (v / np.linalg.norm(v)).tolist()


@pytest.fixture
def people(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ENTITY_CROPS_DIR", str(tmp_path / "crops"), raising=False)
    make_entity(db_session, id="p1", entity_type="person", name="Person One")
    make_event(db_session=db_session, id="e1", camera_id="cam")
    crop = cv2.imencode(".jpg", np.full((112, 112, 3), 128, np.uint8))[1].tobytes()
    rel = write_crop("gallery/p1/g1.jpg", crop)
    db_session.add(EntityGalleryItem(id="g1", entity_id="p1", kind="face", model_version=frs.SFACE_MODEL_VERSION,
                                     embedding=json.dumps(_vec(128, 1)), crop_path=rel, source_observation_id="o1"))
    db_session.add(EntityGalleryItem(id="g2", entity_id="p1", kind="face", model_version=frs.SFACE_MODEL_VERSION,
                                     embedding=json.dumps(_vec(128, 2)), crop_path=None, source_observation_id="o2"))
    db_session.add(FaceEmbedding(id="o1", event_id="e1", embedding=json.dumps(_vec(128, 1)), bounding_box="{}", confidence=0.9,
                                 model_version=frs.SFACE_MODEL_VERSION, crop_path=rel))
    db_session.commit()
    return db_session


def test_index_only_uses_the_active_models_references(people, fake_weights, monkeypatch):
    assert set(load_gallery_index(people).faces) == {"p1"}
    monkeypatch.setenv("ARGUS_FACE_RECOGNIZER", "arcface")
    frs.reset_face_recognition_service()
    assert load_gallery_index(people).faces == {}


def test_reembed_rebuilds_vectors_in_place(people):
    from scripts.reembed_face_gallery import reembed

    fake = SimpleNamespace(model_version=arc.ARCFACE_MODEL_VERSION,
                           embed_aligned=lambda img: np.ones(512, np.float32) / np.sqrt(512))
    dry = reembed(people, fake, apply=False)
    assert dry == {"gallery": 1, "observations": 1, "skipped_no_crop": 1, "failed": 0}
    assert people.query(EntityGalleryItem).filter_by(model_version=arc.ARCFACE_MODEL_VERSION).count() == 0

    reembed(people, fake, apply=True)
    g1 = people.get(EntityGalleryItem, "g1")
    assert g1.model_version == arc.ARCFACE_MODEL_VERSION and len(json.loads(g1.embedding)) == 512
    assert people.get(EntityGalleryItem, "g2").model_version == frs.SFACE_MODEL_VERSION  # no crop: untouched
    assert people.get(FaceEmbedding, "o1").model_version == arc.ARCFACE_MODEL_VERSION
    assert reembed(people, fake, apply=True)["gallery"] == 0  # idempotent


# ---------------------------------------------------------------------------
# Real weights (only when the user supplied them)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not arc.verify_weights()[0] or frs.resolve_face_model_paths()[0] is None,
                    reason="ArcFace weights (user-supplied) or YuNet not present")
def test_real_weights():
    rec = arc.ArcFaceRecognizer()
    img = cv2.imread(str(FIXTURE))
    faces = rec.identify(img)
    assert len(faces) == 1
    same = rec.embed_aligned(cv2.flip(faces[0].aligned_crop, 1))
    noise = rec.embed_aligned(np.random.default_rng(0).integers(0, 255, (112, 112, 3), dtype=np.uint8))
    assert float(faces[0].embedding @ same) > 0.8 > float(faces[0].embedding @ noise)
