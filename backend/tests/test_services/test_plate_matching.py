"""Licence-plate matching for known vehicles: hashing, reading, evidence, signal, storage.

All model calls are mocked; ``test_real_models_read_a_rendered_plate`` runs
the real fast-alpr pipeline when the optional packages and the plate
weights are installed, and skips otherwise (CI).
"""
import dataclasses
import json
import logging
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.models.entity_plate import EntityPlate
from app.models.system_setting import SystemSetting
from app.services import entity_plate_service as eps
from app.services import plate_reader as pr
from app.services.ai_types import VEHICLE_RECOGNITION_ENABLED
from app.services.entity_gallery_service import (
    SignalVerdict,
    evaluate_vehicle_candidates,
    get_entity_gallery_service,
    pick_vehicle,
)
from app.services.event_entity_linking import NamedIdentity, verify_named_identities
from app.services.object_identity_service import ObjectAnalysis, VehicleObservation, analyze_frame_sync
from tests.conftest import make_camera, make_entity, make_event

SALT = "unit-test-salt-not-a-secret-0001"
PLATE = "ABC 1234"  # made-up plate used only in tests
OTHER = "XYZ9876"


@pytest.fixture
def plates_on(monkeypatch):
    monkeypatch.setattr(settings, "PLATE_RECOGNITION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "PLATE_HASH_SALT", SecretStr(SALT), raising=False)
    monkeypatch.setattr(settings, "PLATE_VETO_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "PLATE_MIN_CONFIDENCE", 0.5, raising=False)
    monkeypatch.setattr(settings, "PLATE_STRICT_CONFIDENCE", 0.85, raising=False)
    eps.invalidate_plate_index()
    yield
    eps.invalidate_plate_index()
    pr.reset_plate_reader(None)


def read(text, conf=0.99):
    norm = pr.normalize_plate(text)
    return pr.PlateRead(pr.hash_plate(text), conf, len(norm))


def car(reads=(), stationary=False, x=10, color="red"):
    return VehicleObservation(
        bbox={"x": x, "y": 20, "width": 200, "height": 120},
        score=0.9,
        vehicle_type="car",
        crop_jpeg=b"\xff\xd8car",
        color=color,
        area_fraction=0.1,
        embedding=None,
        stationary=stationary,
        plate_reads=list(reads),
    )


def ident(entity_id, name="Test car", color="red", make=None):
    return NamedIdentity(entity_id=entity_id, name=name, entity_type="vehicle", vehicle_color=color, vehicle_make=make)


class FakeOcr:
    def __init__(self, text, conf):
        self.text, self.confidence = text, conf


class FakeAlpr:
    def __init__(self, results):
        self.results = results
        self.calls = 0

    def predict(self, image):
        self.calls += 1
        if isinstance(self.results, Exception):
            raise self.results
        return [SimpleNamespace(ocr=FakeOcr(t, c)) for t, c in self.results]


# ---------------------------------------------------------------------------
# Normalising and hashing
# ---------------------------------------------------------------------------

class TestHashing:
    def test_normalize_folds_case_spacing_and_lookalikes(self):
        assert pr.normalize_plate(" abc-1234 ") == "ABC1234"
        assert pr.normalize_plate("OIQ 10") == "010 10".replace(" ", "")
        assert pr.normalize_plate("A") is None
        assert pr.normalize_plate("ABCDEFGHIJK") is None
        assert pr.normalize_plate(None) is None

    def test_hash_is_keyed_stable_and_hex(self, plates_on):
        h = pr.hash_plate(PLATE)
        assert len(h) == 64 and int(h, 16) >= 0
        assert pr.hash_plate("abc1234") == h == pr.hash_plate("ABC-1234")
        assert pr.hash_plate("ABC1234", b"another-salt-entirely-123") != h
        assert pr.normalize_plate(PLATE) not in h

    def test_no_or_short_salt_means_no_hash(self, monkeypatch):
        monkeypatch.setattr(settings, "PLATE_HASH_SALT", None, raising=False)
        assert pr.hash_key() is None and pr.hash_plate(PLATE) is None and pr.key_id() is None
        monkeypatch.setattr(settings, "PLATE_HASH_SALT", SecretStr("short"), raising=False)
        assert pr.hash_key() is None

    def test_enabled_needs_flag_and_salt(self, monkeypatch):
        monkeypatch.setattr(settings, "PLATE_RECOGNITION_ENABLED", False, raising=False)
        monkeypatch.setattr(settings, "PLATE_HASH_SALT", SecretStr(SALT), raising=False)
        assert not pr.plates_enabled()
        monkeypatch.setattr(settings, "PLATE_RECOGNITION_ENABLED", True, raising=False)
        assert pr.plates_enabled()
        monkeypatch.setattr(settings, "PLATE_HASH_SALT", None, raising=False)
        assert not pr.plates_enabled()

    def test_key_id_is_a_short_fingerprint(self, plates_on):
        kid = pr.key_id()
        assert len(kid) == 12 and SALT not in kid and kid == pr.key_id()

    def test_off_by_default(self):
        from app.core.config import Settings

        assert Settings.model_fields["PLATE_RECOGNITION_ENABLED"].default is False
        assert Settings.model_fields["PLATE_HASH_SALT"].default is None


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

class TestReader:
    def test_read_returns_hashes_never_text(self, plates_on):
        reader = pr.PlateReader(FakeAlpr([("ABC1234", [0.99] * 7 + [0.1] * 3)]))
        reads = reader.read(np.zeros((50, 50, 3), np.uint8), pr.hash_key())
        assert [f.name for f in dataclasses.fields(pr.PlateRead)] == ["plate_hash", "confidence", "length"]
        assert reads == [pr.PlateRead(pr.hash_plate(PLATE), 0.99, 7)]  # pad slots ignored

    def test_confidence_is_the_weakest_character(self, plates_on):
        reader = pr.PlateReader(FakeAlpr([("ABC1234", [0.99, 0.4, 0.99, 0.99, 0.99, 0.99, 0.99])]))
        assert reader.read(np.zeros((5, 5, 3), np.uint8), pr.hash_key())[0].confidence == 0.4

    def test_short_and_empty_reads_are_dropped_and_capped(self, plates_on):
        reader = pr.PlateReader(FakeAlpr([("AB", [1.0]), ("", 0.0), ("AAA111", 0.9), ("BBB222", 0.9), ("CCC333", 0.9)]))
        reads = reader.read(np.zeros((5, 5, 3), np.uint8), pr.hash_key())
        assert len(reads) == pr.MAX_PLATES_PER_IMAGE

    def test_not_ready_reads_nothing(self, plates_on):
        assert pr.PlateReader().read(np.zeros((5, 5, 3), np.uint8), pr.hash_key()) == []

    def test_missing_models_mark_unavailable(self, plates_on, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "PLATE_MODEL_DIR", str(tmp_path), raising=False)
        reader = pr.PlateReader()
        assert reader.load() is False and reader.state == "unavailable"
        assert reader.ensure_loading() is False

    def test_live_reads_start_a_background_load_and_skip(self, plates_on, monkeypatch):
        reader = pr.PlateReader()
        started = []
        monkeypatch.setattr(reader, "_do_load", lambda: started.append(1))
        monkeypatch.setattr(pr.threading, "Thread", lambda target, **kw: SimpleNamespace(start=target))
        pr.reset_plate_reader(reader)
        assert pr.read_vehicle_plates([np.zeros((5, 5, 3), np.uint8)]) == [[]]
        assert started == [1] and reader.state == "loading"

    def test_live_reads_off_budget_and_errors(self, plates_on, monkeypatch):
        crops = [np.zeros((5, 5, 3), np.uint8)] * 2
        pr.reset_plate_reader(pr.PlateReader(FakeAlpr([("ABC1234", 0.95)])))
        assert pr.read_vehicle_plates(crops)[0][0].plate_hash == pr.hash_plate(PLATE)
        assert pr.read_vehicle_plates(crops, budget_ms=0) == [[], []]
        pr.reset_plate_reader(pr.PlateReader(FakeAlpr(RuntimeError("onnx"))))
        assert pr.read_vehicle_plates(crops) == [[], []]
        monkeypatch.setattr(settings, "PLATE_RECOGNITION_ENABLED", False, raising=False)
        pr.reset_plate_reader(pr.PlateReader(FakeAlpr([("ABC1234", 0.95)])))
        assert pr.read_vehicle_plates(crops) == [[], []]

    def test_analyze_frame_puts_reads_on_vehicles(self, plates_on, monkeypatch):
        from app.services import object_identity_service as ois

        monkeypatch.setattr(ois, "_detect_vehicle_boxes", lambda img: [({"x": 10, "y": 10, "width": 100, "height": 60}, 0.9, "car", 0.1)])
        seen = []
        monkeypatch.setattr(pr, "read_vehicle_plates", lambda crops: seen.append(len(crops)) or [[read(PLATE)]])
        image = np.full((200, 300, 3), 120, np.uint8)
        with_plates = analyze_frame_sync(image, faces=False, vehicles=True, plates=True)
        assert seen == [1] and with_plates.vehicles[0].plate_reads == [read(PLATE)]
        without = analyze_frame_sync(image, faces=False, vehicles=True)
        assert seen == [1] and without.vehicles[0].plate_reads == []


# ---------------------------------------------------------------------------
# Evidence and the vehicle signal
# ---------------------------------------------------------------------------

@pytest.fixture
def garage(db_session, plates_on):
    db_session.add(SystemSetting(key=VEHICLE_RECOGNITION_ENABLED, value="true"))
    db_session.commit()
    make_camera(db_session=db_session, id="cam-drive", name="Driveway")
    mine = make_entity(db_session, id="mine", entity_type="vehicle", name="Test SUV", vehicle_color="red")
    theirs = make_entity(db_session, id="theirs", entity_type="vehicle", name="Test Van", vehicle_color="white")
    make_event(db_session=db_session, id="evt-1", camera_id="cam-drive", objects_detected=json.dumps(["vehicle"]))
    assert eps.set_plate(db_session, mine, PLATE).status == "enrolled"
    return SimpleNamespace(db=db_session, mine=mine, theirs=theirs)


class TestEvidence:
    def test_matching_read_becomes_evidence_and_hashes_are_dropped(self, garage):
        analysis = ObjectAnalysis(vehicles=[car([read(PLATE)])])
        assert eps.resolve_plate_evidence(garage.db, analysis) == 1
        obs = analysis.vehicles[0]
        assert obs.plate_reads == []
        assert obs.plate_evidence.matched_entity_ids == {"mine"}
        assert obs.plate_evidence.confident_read is True
        assert "plate_hash" not in repr(obs.plate_evidence)

    def test_unknown_plate_is_discarded_and_never_stored(self, garage):
        before = garage.db.query(EntityPlate).count()
        analysis = ObjectAnalysis(vehicles=[car([read(OTHER)])])
        assert eps.resolve_plate_evidence(garage.db, analysis) == 0
        assert analysis.vehicles[0].plate_reads == []
        assert analysis.vehicles[0].plate_evidence.matched_entity_ids == frozenset()
        assert garage.db.query(EntityPlate).count() == before

    def test_low_confidence_read_does_not_match(self, garage):
        analysis = ObjectAnalysis(vehicles=[car([read(PLATE, conf=0.3)])])
        eps.resolve_plate_evidence(garage.db, analysis)
        ev = analysis.vehicles[0].plate_evidence
        assert ev.matched_entity_ids == frozenset() and ev.confident_read is False

    def test_rows_from_another_salt_are_ignored(self, garage, monkeypatch):
        monkeypatch.setattr(settings, "PLATE_HASH_SALT", SecretStr("a-rotated-salt-0123456789"), raising=False)
        eps.invalidate_plate_index()
        index = eps.load_plate_index(garage.db)
        assert index.by_hash == {} and index.stale == 1

    def test_failure_still_drops_hashes(self, garage, monkeypatch):
        monkeypatch.setattr(eps, "get_plate_index", lambda db: (_ for _ in ()).throw(RuntimeError("db")))
        analysis = ObjectAnalysis(vehicles=[car([read(PLATE)])])
        assert eps.resolve_plate_evidence(garage.db, analysis) == 0
        assert analysis.vehicles[0].plate_reads == [] and analysis.vehicles[0].plate_evidence is None


def evidence(matched=(), confident=True, known=("mine",)):
    return eps.PlateEvidence(frozenset(matched), confident, frozenset(known))


def with_ev(ev, **kw):
    v = car(**kw)
    v.plate_evidence = ev
    return v


class TestSignal:
    sig = eps.PlateSignal()

    def test_agree_on_a_moving_match(self):
        assert self.sig.evaluate(ident("mine"), [with_ev(evidence(["mine"]))], None).status == "agree"

    def test_confident_other_plate_vetoes_when_one_vehicle_moves(self):
        assert self.sig.evaluate(ident("mine"), [with_ev(evidence())], None).status == "contradict"

    def test_no_veto_when_unsure_or_two_vehicles_or_disabled(self):
        assert self.sig.evaluate(ident("mine"), [with_ev(evidence(confident=False))], None).status == "none"
        two = [with_ev(evidence()), with_ev(None, x=300)]
        assert self.sig.evaluate(ident("mine"), two, None).status == "none"
        assert eps.PlateSignal(veto=False).evaluate(ident("mine"), [with_ev(evidence())], None).status == "none"

    def test_parked_match_contradicts(self):
        obs = [with_ev(evidence(["mine"]), stationary=True), with_ev(evidence(confident=False), x=300)]
        assert self.sig.evaluate(ident("mine"), obs, None).status == "contradict"

    def test_no_opinion_without_saved_plate_or_reads(self):
        assert self.sig.evaluate(ident("theirs"), [with_ev(evidence())], None).status == "none"
        assert self.sig.evaluate(ident("mine"), [car()], None).status == "none"
        assert self.sig.evaluate(ident("mine"), [], None).status == "none"

    def test_plate_links_above_crop_and_keeps_builtin_vetoes(self):
        obs = [with_ev(evidence(["mine"]))]
        ev = evaluate_vehicle_candidates(None, [ident("mine"), ident("theirs", color="white")], obs, {}, extra_signals=[self.sig])
        winner, _ = pick_vehicle(ev)
        assert winner.entity_id == "mine" and winner.signal == "plate" and winner.tier == eps.PLATE_SIGNAL_TIER
        # The description names another colour: the built-in veto wins.
        ev = evaluate_vehicle_candidates("A white van pulls in", [ident("mine")], obs, {}, extra_signals=[self.sig])
        assert not ev[0].accepted and ev[0].reason == "description_contradicts"
        # Colour conflict on the crop also still vetoes.
        ev = evaluate_vehicle_candidates(None, [ident("mine")], [with_ev(evidence(["mine"]), color="white")], {}, extra_signals=[self.sig])
        assert not ev[0].accepted and ev[0].reason == "color_conflict"

    def test_veto_blocks_a_description_link(self):
        ev = evaluate_vehicle_candidates(
            "A red Testmake SUV in the driveway", [ident("mine", make="testmake")],
            [with_ev(evidence())], {}, extra_signals=[self.sig],
        )
        assert not ev[0].accepted and ev[0].reason == "plate_contradicts"

    def test_signal_error_is_no_opinion(self):
        broken = SimpleNamespace(name="plate", tier=4, evaluate=lambda *a: 1 / 0)
        ev = evaluate_vehicle_candidates(None, [ident("mine")], [with_ev(evidence(["mine"]))], {}, extra_signals=[broken])
        assert ev[0].signals == {"plate": "none"} and not ev[0].accepted

    def test_install_registers_only_when_enabled(self, plates_on, monkeypatch):
        from app.services.entity_gallery_service import registered_vehicle_signals, unregister_vehicle_signal

        monkeypatch.setattr(pr.PlateReader, "ensure_loading", lambda self: False)
        try:
            assert eps.install_plate_signal() is True
            assert [s.name for s in registered_vehicle_signals()] == ["plate"]
            monkeypatch.setattr(settings, "PLATE_RECOGNITION_ENABLED", False, raising=False)
            assert eps.install_plate_signal() is False
            assert registered_vehicle_signals() == []
        finally:
            unregister_vehicle_signal("plate")


class TestLiveLinking:
    def test_plate_only_vehicle_links_without_description_or_gallery(self, garage, monkeypatch):
        from app.services.entity_gallery_service import register_vehicle_signal, unregister_vehicle_signal

        register_vehicle_signal(eps.PlateSignal())
        try:
            analysis = ObjectAnalysis(vehicles=[car([read(PLATE)])])
            eps.resolve_plate_evidence(garage.db, analysis)
            linked = verify_named_identities(
                garage.db, description=None, candidates=[], looks_like_vehicle=True, object_analysis=analysis,
            )
            assert [v.entity_id for v in linked] == ["mine"]
            other = ObjectAnalysis(vehicles=[car([read(OTHER)])])
            eps.resolve_plate_evidence(garage.db, other)
            assert verify_named_identities(
                garage.db, description="A red Test SUV", candidates=[], looks_like_vehicle=True, object_analysis=other,
            ) == []
        finally:
            unregister_vehicle_signal("plate")

    def test_pre_ai_hint_names_a_plate_match(self, garage):
        from app.services.entity_gallery_service import register_vehicle_signal, unregister_vehicle_signal
        from app.services.pre_ai_context_service import PreAIContextService

        register_vehicle_signal(eps.PlateSignal())
        try:
            analysis = ObjectAnalysis(vehicles=[car([read(PLATE)])])
            svc = PreAIContextService()
            svc._resolve_plates(garage.db, analysis)
            hint = svc._gallery_vehicle_hint(garage.db, analysis)
            assert hint is not None and hint.entity_id == "mine"
        finally:
            unregister_vehicle_signal("plate")


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class TestStorage:
    def test_manual_plate_is_hashed_and_idempotent(self, garage):
        row = garage.db.query(EntityPlate).one()
        assert row.plate_hash == pr.hash_plate(PLATE) and row.source == "manual"
        assert row.key_id == pr.key_id() and row.hash_version == pr.HASH_VERSION
        cols = {c.name for c in EntityPlate.__table__.columns}
        assert not cols & {"plate", "plate_text", "text"}
        assert eps.set_plate(garage.db, garage.mine, "abc-1234").status == "already_enrolled"
        assert eps.set_plate(garage.db, garage.mine, "!").status == "invalid"

    def test_only_vehicles_and_only_with_a_salt(self, garage, monkeypatch):
        person = make_entity(garage.db, entity_type="person", name="Someone")
        assert eps.set_plate(garage.db, person, PLATE).status == "not_vehicle"
        monkeypatch.setattr(settings, "PLATE_HASH_SALT", None, raising=False)
        assert eps.set_plate(garage.db, garage.theirs, OTHER).status == "disabled"

    @pytest.mark.asyncio
    async def test_enroll_from_crop_needs_a_strict_read(self, garage):
        pr.reset_plate_reader(pr.PlateReader(FakeAlpr([(OTHER, 0.6)])))
        crop = cv2.imencode(".jpg", np.full((60, 120, 3), 200, np.uint8))[1].tobytes()
        assert (await eps.enroll_plate_from_crop(garage.db, garage.theirs, crop, "evt-1")).status == "low_confidence"
        pr.reset_plate_reader(pr.PlateReader(FakeAlpr([])))
        assert (await eps.enroll_plate_from_crop(garage.db, garage.theirs, crop, "evt-1")).status == "no_read"
        pr.reset_plate_reader(pr.PlateReader(FakeAlpr([(OTHER, 0.97)])))
        result = await eps.enroll_plate_from_crop(garage.db, garage.theirs, crop, "evt-1")
        assert result.status == "enrolled" and result.plate.source == "event" and result.plate.source_event_id == "evt-1"
        assert (await eps.enroll_plate_from_crop(garage.db, garage.theirs, None, "evt-1")).status == "no_read"

    @pytest.mark.asyncio
    async def test_enroll_from_crop_fails_open(self, garage):
        pr.reset_plate_reader(pr.PlateReader(FakeAlpr(RuntimeError("onnx"))))
        crop = cv2.imencode(".jpg", np.full((60, 120, 3), 200, np.uint8))[1].tobytes()
        assert (await eps.enroll_plate_from_crop(garage.db, garage.theirs, crop, "evt-1")).status == "error"

    def test_unenroll_removes_only_event_plates_of_that_event(self, garage):
        garage.db.add(EntityPlate(entity_id="theirs", plate_hash=pr.hash_plate(OTHER), hash_version=pr.HASH_VERSION,
                                  key_id=pr.key_id(), source="event", source_event_id="evt-1"))
        garage.db.commit()
        get_entity_gallery_service().unenroll_event(garage.db, "theirs", "evt-1")
        get_entity_gallery_service().unenroll_event(garage.db, "mine", "evt-1")
        assert [r.entity_id for r in garage.db.query(EntityPlate).all()] == ["mine"]

    def test_merge_moves_plates_without_duplicates(self, garage):
        eps.set_plate(garage.db, garage.theirs, PLATE)
        eps.set_plate(garage.db, garage.theirs, OTHER)
        get_entity_gallery_service().move_items(garage.db, "theirs", "mine")
        garage.db.commit()
        rows = garage.db.query(EntityPlate).all()
        assert sorted(r.entity_id for r in rows) == ["mine", "mine"]

    def test_remove_and_clear(self, garage):
        row = garage.db.query(EntityPlate).one()
        assert eps.remove_plate(garage.db, "theirs", row.id) is False
        assert eps.remove_plate(garage.db, "mine", row.id) is True
        eps.set_plate(garage.db, garage.mine, PLATE)
        eps.set_plate(garage.db, garage.theirs, OTHER)
        assert eps.clear_plates(garage.db, "theirs") == 1
        assert eps.clear_plates(garage.db) == 1

    @pytest.mark.asyncio
    async def test_entity_delete_removes_its_plates(self, garage):
        from app.services.entity_service import get_entity_service

        assert await get_entity_service().delete_entity(garage.db, "mine") is True
        assert garage.db.query(EntityPlate).count() == 0

    @pytest.mark.asyncio
    async def test_assign_enrolls_the_plate_on_the_crop(self, garage, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "MEDIA_ENTITY_CROPS_DIR", str(tmp_path / "crops"), raising=False)
        crop = cv2.imencode(".jpg", np.full((60, 120, 3), 200, np.uint8))[1].tobytes()
        v = car(color="white")
        v.embedding = np.ones(512) / np.sqrt(512)
        v.crop_jpeg = crop
        get_entity_gallery_service().save_observations(garage.db, "evt-1", ObjectAnalysis(vehicles=[v]))
        pr.reset_plate_reader(pr.PlateReader(FakeAlpr([(OTHER, 0.97)])))
        result = await get_entity_gallery_service().enroll_from_event(garage.db, garage.theirs, "evt-1")
        assert result.status == "enrolled" and result.plate == "enrolled"
        assert garage.db.query(EntityPlate).filter(EntityPlate.entity_id == "theirs").one().source_event_id == "evt-1"

    def test_status_has_no_plate_data(self, garage):
        status = eps.plate_status(garage.db)
        assert status["vehicles_with_plates"] == 1 and status["saved_plates"] == 1
        assert pr.hash_plate(PLATE) not in json.dumps(status)


def test_plate_text_never_reaches_the_logs(db_session, plates_on, caplog):
    caplog.set_level(logging.DEBUG)
    car_entity = make_entity(db_session, entity_type="vehicle", name="Logged car")
    eps.set_plate(db_session, car_entity, PLATE)
    pr.reset_plate_reader(pr.PlateReader(FakeAlpr([(OTHER, 0.99)])))
    analysis = ObjectAnalysis(vehicles=[car(pr.read_vehicle_plates([np.zeros((5, 5, 3), np.uint8)])[0])])
    eps.resolve_plate_evidence(db_session, analysis)
    text = caplog.text + json.dumps([r.__dict__ for r in caplog.records], default=str)
    for secret in ("ABC1234", "ABC 1234", "XYZ9876", pr.hash_plate(PLATE), pr.hash_plate(OTHER), SALT):
        assert secret not in text


# ---------------------------------------------------------------------------
# Real models (skips unless installed)
# ---------------------------------------------------------------------------

def _real_models_available() -> bool:
    try:
        import fast_alpr  # noqa: F401
    except ImportError:
        return False
    d = pr.model_dir()
    return all((d / f).is_file() for f in (pr.DETECTOR_FILE, pr.OCR_FILE, pr.OCR_CONFIG_FILE))


@pytest.mark.skipif(not _real_models_available(), reason="fast-alpr or plate weights not installed")
def test_real_models_read_a_rendered_plate(plates_on):
    plate = np.full((110, 260, 3), 245, np.uint8)
    cv2.rectangle(plate, (3, 3), (256, 106), (40, 40, 40), 3)
    cv2.putText(plate, "XYZ987", (18, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.9, (30, 30, 30), 5, cv2.LINE_AA)
    scene = np.full((540, 720, 3), (60, 40, 150), np.uint8)
    scene[360:470, 230:490] = plate
    reader = pr.PlateReader()
    assert reader.load() is True
    reads = reader.read(scene, pr.hash_key())
    assert reads and all(len(r.plate_hash) == 64 for r in reads)
    assert all(0.0 <= r.confidence <= 1.0 for r in reads)
