"""Model download manifest and the reference reset script."""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.entity_gallery_item import EntityGalleryItem
from tests.conftest import make_entity

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDownloadManifest:
    def test_face_and_vehicle_sets_are_pinned(self):
        mod = _load("download_vehicle_model")
        assert set(mod.MODEL_SETS) == {"face", "vehicle"}
        face = mod.MODEL_SETS["face"]["files"]
        assert set(face) == {"face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx"}
        for url, digest in face.values():
            assert url.startswith("https://") and len(digest) == 64
            # Pinned to a commit, not a branch.
            assert "/main/" not in url and "/master/" not in url
        assert mod.MODELS is mod.MODEL_SETS["vehicle"]["files"]

    def test_dest_requires_only(self, tmp_path):
        mod = _load("download_vehicle_model")
        with pytest.raises(SystemExit):
            mod.main(["--dest", str(tmp_path)])

    def test_bad_checksum_is_rejected(self, tmp_path):
        mod = _load("download_vehicle_model")
        files = {"m.onnx": ("https://example.invalid/m.onnx", "0" * 64)}

        def fake_fetch(url, filename):
            Path(filename).write_bytes(b"tampered")
            return filename, None

        with patch.object(mod.urllib.request, "urlretrieve", side_effect=fake_fetch):
            assert mod.download_set(files, tmp_path) is False
        assert not (tmp_path / "m.onnx").exists()


class _NoClose:
    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def close(self):
        pass


class TestResetScript:
    def test_dry_run_then_apply(self, db_session, capsys):
        mod = _load("reset_entity_references")
        bmw = make_entity(db_session, entity_type="vehicle", name="Sam's BMW",
                          thumbnail_path="/api/v1/thumbnails/x.jpg")
        db_session.add(EntityGalleryItem(id="g", entity_id=bmw.id, kind="vehicle",
                                         model_version="m", embedding="[]"))
        db_session.commit()
        with patch("app.core.database.SessionLocal", lambda: _NoClose(db_session)):
            assert mod.main(["--list"]) == 0
            assert "Sam's BMW" in capsys.readouterr().out
            argv = ["--entity", bmw.id, "--clear-gallery", "--clear-reference-embedding", "--clear-thumbnail"]
            assert mod.main(argv) == 0
            db_session.refresh(bmw)
            assert json.loads(bmw.reference_embedding)  # untouched in a dry run
            assert db_session.query(EntityGalleryItem).count() == 1
            assert mod.main(argv + ["--apply"]) == 0
        db_session.refresh(bmw)
        assert bmw.reference_embedding == "[]"
        assert bmw.thumbnail_path is None
        assert db_session.query(EntityGalleryItem).count() == 0

    def test_needs_a_target(self):
        mod = _load("reset_entity_references")
        with pytest.raises(SystemExit):
            mod.main(["--clear-gallery"])

    def test_unknown_entity(self, db_session):
        mod = _load("reset_entity_references")
        with patch("app.core.database.SessionLocal", lambda: _NoClose(db_session)):
            assert mod.main(["--entity", "nope", "--clear-gallery"]) == 2
