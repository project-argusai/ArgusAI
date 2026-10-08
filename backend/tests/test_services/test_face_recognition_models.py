"""Real YuNet + SFace models on a bundled public-domain image.

Skipped when the ONNX files are not present (run
``scripts/download_vehicle_model.py --only face`` first).
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services.face_recognition_service import (
    SFACE_DIM,
    FaceRecognitionService,
    resolve_face_model_paths,
)
from app.services.entity_gallery_service import GalleryEntry, GalleryIndex, MatchThresholds, match_face
from app.services.object_identity_service import analyze_image_bytes

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "faces" / "astronaut_256.jpg"

yunet, sface = resolve_face_model_paths()
pytestmark = pytest.mark.skipif(
    not (yunet and sface), reason="YuNet/SFace models not downloaded"
)


@pytest.fixture(scope="module")
def service():
    svc = FaceRecognitionService()
    assert svc.is_available()
    return svc


@pytest.fixture(scope="module")
def image():
    img = cv2.imread(str(FIXTURE))
    assert img is not None
    return img


def test_detects_one_face_and_embeds_it(service, image):
    ids = service.identify(image)
    assert len(ids) == 1
    ident = ids[0]
    assert ident.face.score >= 0.8
    assert ident.aligned_crop.shape == (112, 112, 3)
    assert ident.embedding.shape == (SFACE_DIM,)
    assert np.linalg.norm(ident.embedding) == pytest.approx(1.0, abs=1e-4)


def test_same_person_under_changes_matches_their_gallery(service, image):
    ref = service.identify(image)[0].embedding
    other = np.random.default_rng(1).normal(size=SFACE_DIM)
    other /= np.linalg.norm(other)
    index = GalleryIndex(faces={
        "astro": GalleryEntry("astro", "Astronaut", "person", np.vstack([ref])),
        "other": GalleryEntry("other", "Someone", "person", np.vstack([other])),
    })
    variants = [
        cv2.flip(image, 1),
        cv2.convertScaleAbs(image, alpha=0.6, beta=10),       # dim
        cv2.resize(image, None, fx=2, fy=2),                  # bigger frame
        cv2.GaussianBlur(image, (3, 3), 0),
    ]
    for variant in variants:
        probe = service.identify(variant)
        assert probe, "face not found in variant"
        match = match_face(index, [probe[0].embedding], MatchThresholds())
        assert match is not None and match.entity_id == "astro"
        assert match.score > 0.8


def test_no_face_in_a_plain_frame(service):
    blank = np.full((240, 320, 3), 127, dtype=np.uint8)
    assert service.identify(blank) == []


def test_tiny_faces_are_ignored(service, image):
    tiny = cv2.resize(image, (64, 64), interpolation=cv2.INTER_AREA)
    assert service.identify(tiny) == []


@pytest.mark.asyncio
async def test_full_analysis_on_jpeg_bytes(image):
    ok, buf = cv2.imencode(".jpg", image)
    result = await analyze_image_bytes(buf.tobytes(), faces=True, vehicles=False)
    assert len(result.faces) == 1
    assert result.faces[0].crop_jpeg[:2] == b"\xff\xd8"
    assert result.faces_checked and not result.vehicles_checked
