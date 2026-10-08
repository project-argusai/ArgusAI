"""Matching rules for per-object galleries (no models, no database).

Covers how a face or a vehicle is named: SFace face galleries with a
threshold and a margin; vehicle crops combined with colour and the AI
description, with vetoes that keep false names out (an empty driveway, the
other red SUV, a car that is only parked in the frame).
"""
import cv2
import numpy as np
import pytest

from app.services.entity_alert_service import vehicle_description_signal
from app.services.entity_gallery_service import (
    GalleryEntry,
    GalleryIndex,
    MatchThresholds,
    box_iou,
    evaluate_vehicle_candidates,
    match_face,
    pick_vehicle,
)
from app.services.event_entity_linking import NamedIdentity
from app.services.object_identity_service import VehicleObservation
from app.services.vehicle_color import (
    color_agreement,
    dominant_vehicle_color,
    frame_is_grayscale,
    normalize_color_name,
)

T = MatchThresholds()
RNG = np.random.default_rng(677)


def unit(dim=512):
    v = RNG.normal(size=dim)
    return v / np.linalg.norm(v)


def with_cosine(ref, cos):
    """A unit vector whose cosine with ``ref`` is exactly ``cos``."""
    noise = RNG.normal(size=ref.shape[0])
    noise -= noise.dot(ref) * ref
    noise /= np.linalg.norm(noise)
    return cos * ref + np.sqrt(max(0.0, 1 - cos * cos)) * noise


def entry(entity_id, name, vectors, *, etype="vehicle", color=None, make=None, model=None, colors=None):
    return GalleryEntry(
        entity_id=entity_id,
        name=name,
        entity_type=etype,
        vectors=np.vstack(vectors),
        colors=colors or [],
        vehicle_color=color,
        vehicle_make=make,
        vehicle_model=model,
    )


def car(embedding, color="red", *, stationary=False, bbox=None):
    return VehicleObservation(
        bbox=bbox or {"x": 10, "y": 10, "width": 200, "height": 120},
        score=0.9,
        vehicle_type="car",
        crop_jpeg=b"jpeg",
        color=color,
        area_fraction=0.1,
        embedding=embedding,
        stationary=stationary,
    )


TESLA = NamedIdentity("tesla", "Alex's Tesla", "vehicle", vehicle_color="red",
                      vehicle_make="tesla", vehicle_model="model y")
BMW = NamedIdentity("bmw", "Sam's BMW", "vehicle", vehicle_color="red",
                    vehicle_make="bmw", vehicle_model="x3")
KIA = NamedIdentity("kia", "Jo's Kia", "vehicle", vehicle_color="black",
                    vehicle_make="kia", vehicle_model="telluride")


@pytest.fixture
def galleries():
    t, b, k = unit(), unit(), unit()
    return {
        "vecs": {"tesla": t, "bmw": b, "kia": k},
        "gallery": {
            "tesla": entry("tesla", TESLA.name, [t], color="red", make="tesla", model="model y"),
            "bmw": entry("bmw", BMW.name, [b], color="red", make="bmw", model="x3"),
            "kia": entry("kia", KIA.name, [k], color="black", make="kia", model="telluride"),
        },
    }


def decide(description, vehicles, gallery, identities=(TESLA, BMW, KIA)):
    evidence = evaluate_vehicle_candidates(description, list(identities), vehicles, gallery, T)
    winner, tied = pick_vehicle(evidence, T)
    return winner, tied, {e.entity_id: e for e in evidence}


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

class TestVehicleRules:
    def test_empty_driveway_links_nothing(self, galleries):
        winner, tied, ev = decide("The driveway is empty; no vehicles are visible.", [], galleries["gallery"])
        assert winner is None and tied == []
        assert all(not e.accepted for e in ev.values())

    def test_empty_driveway_without_galleries_links_nothing(self):
        winner, tied, _ = decide("An empty driveway at night.", [], {})
        assert winner is None and tied == []

    def test_strong_crop_and_colour_link_without_a_description(self, galleries):
        obs = car(with_cosine(galleries["vecs"]["tesla"], 0.95), "red")
        winner, _, ev = decide(None, [obs], galleries["gallery"])
        assert winner.entity_id == "tesla" and winner.signal == "crop+color"
        assert ev["kia"].reason == "color_conflict"

    def test_strong_crop_at_night_needs_the_description(self, galleries):
        obs = car(with_cosine(galleries["vecs"]["tesla"], 0.95), None)  # IR: colour unknown
        winner, _, ev = decide(None, [obs], galleries["gallery"])
        assert winner is None
        assert ev["tesla"].reason == "crop_disagrees"
        winner, _, _ = decide("A Tesla pulls into the driveway.", [obs], galleries["gallery"])
        assert winner.entity_id == "tesla" and winner.signal == "crop+description"

    def test_supporting_crop_and_description_link(self, galleries):
        obs = car(with_cosine(galleries["vecs"]["tesla"], 0.85), "red")
        winner, _, _ = decide("A red Tesla Model Y arrives.", [obs], galleries["gallery"])
        assert winner.entity_id == "tesla" and winner.signal == "crop+description"

    def test_colour_conflict_vetoes_even_a_strong_crop(self, galleries):
        obs = car(with_cosine(galleries["vecs"]["tesla"], 0.97), "black")
        winner, _, ev = decide("A Tesla pulls in.", [obs], galleries["gallery"])
        assert winner is None
        assert ev["tesla"].reason == "color_conflict"

    def test_description_naming_another_make_vetoes(self, galleries):
        obs = car(with_cosine(galleries["vecs"]["tesla"], 0.97), "red")
        winner, _, ev = decide("A red Ford F-150 pulls in.", [obs], galleries["gallery"])
        assert ev["tesla"].reason == "description_contradicts"
        assert winner is None

    def test_detected_car_that_does_not_look_like_it_blocks_the_description(self, galleries):
        # The AI says "Tesla" but the only car in frame looks nothing like
        # the enrolled Tesla: no link.
        obs = car(with_cosine(galleries["vecs"]["tesla"], 0.40), "red")
        winner, _, ev = decide("A red Tesla drives past.", [obs], galleries["gallery"])
        assert winner is None
        assert ev["tesla"].reason == "crop_disagrees"

    def test_two_red_suvs_equally_close_is_ambiguous(self, galleries):
        t, b = galleries["vecs"]["tesla"], galleries["vecs"]["bmw"]
        mixed = 0.5 * t + 0.5 * b
        mixed /= np.linalg.norm(mixed)
        # Rotate the mix to put it ~0.94 from both references.
        obs = car(mixed, "red")
        g = galleries["gallery"]
        g["tesla"].vectors = np.vstack([with_cosine(mixed, 0.94)])
        g["bmw"].vectors = np.vstack([with_cosine(mixed, 0.93)])
        winner, tied, ev = decide(None, [obs], g)
        assert ev["tesla"].accepted and ev["bmw"].accepted
        assert winner is None and tied == []

    def test_description_breaks_a_tie_between_two_red_suvs(self, galleries):
        obs = car(unit(), "red")
        g = galleries["gallery"]
        g["tesla"].vectors = np.vstack([with_cosine(obs.embedding, 0.94)])
        g["bmw"].vectors = np.vstack([with_cosine(obs.embedding, 0.93)])
        winner, _, ev = decide("A red BMW X3 backs out.", [obs], g)
        assert ev["tesla"].reason == "description_contradicts"
        assert winner.entity_id == "bmw" and winner.signal == "crop+description"

    def test_no_vehicle_detected_falls_back_to_the_description_rule(self, galleries):
        winner, _, _ = decide("A red Tesla Model Y pulls in.", [], galleries["gallery"])
        assert winner.entity_id == "tesla" and winner.signal == "description"

    def test_without_galleries_the_679_description_rule_is_unchanged(self):
        obs = car(unit(), "red")
        winner, _, _ = decide("A red BMW X3 pulls in.", [obs], {})
        assert winner.entity_id == "bmw" and winner.signal == "description"

    def test_description_without_a_make_never_links(self):
        winner, _, _ = decide("A red SUV pulls in.", [car(unit(), "red")], {})
        assert winner is None

    def test_parked_car_in_view_is_not_linked(self, galleries):
        parked = car(with_cosine(galleries["vecs"]["tesla"], 0.97), "red", stationary=True)
        van = car(unit(), "white", bbox={"x": 400, "y": 50, "width": 220, "height": 150})
        winner, _, ev = decide(
            "A white delivery van stops; a red Tesla is parked in the driveway.",
            [parked, van],
            galleries["gallery"],
        )
        assert winner is None
        assert ev["tesla"].reason == "parked_in_view"
        assert ev["tesla"].parked_score == pytest.approx(0.97, abs=1e-6)

    def test_parked_car_does_not_block_a_moving_match(self, galleries):
        parked = car(with_cosine(galleries["vecs"]["tesla"], 0.97), "red", stationary=True)
        moving = car(with_cosine(galleries["vecs"]["bmw"], 0.95), "red",
                     bbox={"x": 400, "y": 50, "width": 220, "height": 150})
        winner, _, ev = decide(None, [parked, moving], galleries["gallery"])
        assert winner.entity_id == "bmw" and winner.signal == "crop+color"
        assert ev["tesla"].reason == "parked_in_view"

    def test_majority_crop_colour_stands_in_for_a_missing_saved_colour(self):
        v = unit()
        e = entry("tesla", TESLA.name, [v, v], color=None, colors=["red", "red"])
        ident = NamedIdentity("tesla", "Alex's car", "vehicle")
        winner, _, _ = decide(None, [car(with_cosine(v, 0.95), "red")], {"tesla": e}, [ident])
        assert winner.signal == "crop+color"
        winner, _, ev = decide(None, [car(with_cosine(v, 0.95), "black")], {"tesla": e}, [ident])
        assert winner is None and ev["tesla"].reason == "color_conflict"


class TestPickVehicle:
    def _ev(self, eid, signal, score):
        from app.services.entity_gallery_service import VehicleEvidence

        return VehicleEvidence(eid, eid, True, score, "agree", "agree", accepted=True, signal=signal)

    def test_crop_backed_beats_description_only(self):
        winner, _ = pick_vehicle([self._ev("a", "description", None), self._ev("b", "crop+color", 0.93)], T)
        assert winner.entity_id == "b"

    def test_crop_plus_description_outranks_crop_plus_colour(self):
        winner, _ = pick_vehicle([self._ev("a", "crop+color", 0.99), self._ev("b", "crop+description", 0.85)], T)
        assert winner.entity_id == "b"

    def test_clear_margin_wins(self):
        winner, _ = pick_vehicle([self._ev("a", "crop+color", 0.97), self._ev("b", "crop+color", 0.93)], T)
        assert winner.entity_id == "a"

    def test_description_ties_go_to_the_existing_tie_break(self):
        winner, tied = pick_vehicle([self._ev("a", "description", None), self._ev("b", "description", None)], T)
        assert winner is None and {e.entity_id for e in tied} == {"a", "b"}


class TestThresholdsFromEnv:
    def test_overrides_and_bad_values(self, monkeypatch):
        monkeypatch.setenv("ARGUS_FACE_MATCH_THRESHOLD", "0.45")
        monkeypatch.setenv("ARGUS_VEHICLE_CROP_STRONG", "not-a-number")
        monkeypatch.setenv("ARGUS_VEHICLE_CROP_SUPPORT", "7")  # out of range
        t = MatchThresholds.from_env()
        assert t.face_match == 0.45
        assert t.vehicle_strong == MatchThresholds().vehicle_strong
        assert t.vehicle_support == MatchThresholds().vehicle_support


# ---------------------------------------------------------------------------
# Faces
# ---------------------------------------------------------------------------

class TestFaceMatch:
    def _index(self, **people):
        return GalleryIndex(faces={
            pid: entry(pid, pid.title(), vecs, etype="person") for pid, vecs in people.items()
        })

    def test_match_above_threshold(self):
        a = unit(128)
        m = match_face(self._index(alex=[a], sam=[unit(128)]), [with_cosine(a, 0.55)], T)
        assert m.entity_id == "alex" and m.score == pytest.approx(0.55, abs=1e-3)

    def test_below_threshold_is_unknown(self):
        a = unit(128)
        assert match_face(self._index(alex=[a]), [with_cosine(a, 0.38)], T) is None

    def test_needs_a_margin_over_the_next_person(self):
        a = unit(128)
        probe = with_cosine(a, 0.60)
        b = with_cosine(probe, 0.57)
        assert match_face(self._index(alex=[a], sam=[b]), [probe], T) is None

    def test_best_of_several_gallery_images_counts(self):
        a = unit(128)
        probe = with_cosine(a, 0.7)
        m = match_face(self._index(alex=[unit(128), a]), [probe], T)
        assert m.entity_id == "alex"

    def test_highest_confident_face_wins_across_faces(self):
        a, s = unit(128), unit(128)
        m = match_face(self._index(alex=[a], sam=[s]), [with_cosine(a, 0.5), with_cosine(s, 0.8)], T)
        assert m.entity_id == "sam" and m.face_index == 1

    def test_empty_gallery_names_nobody(self):
        assert match_face(GalleryIndex(), [unit(128)], T) is None


# ---------------------------------------------------------------------------
# Description signal and colour
# ---------------------------------------------------------------------------

class TestDescriptionSignal:
    @pytest.mark.parametrize("text,expected", [
        ("A red Tesla Model Y pulls in.", "agree"),
        ("A red BMW X3 pulls in.", "contradict"),
        ("A white Tesla pulls in.", "contradict"),
        ("A red SUV pulls in.", "none"),
        ("The driveway is empty.", "none"),
        ("", "none"),
        (None, "none"),
    ])
    def test_signal(self, text, expected):
        assert vehicle_description_signal(text, TESLA) == expected


def _solid(bgr, size=(120, 200)):
    img = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    img[:] = bgr
    return img


class TestVehicleColour:
    @pytest.mark.parametrize("bgr,expected", [
        ((30, 30, 200), "red"),
        ((15, 15, 15), "black"),
        ((235, 235, 235), "white"),
        ((128, 128, 128), "gray"),
        ((200, 60, 20), "blue"),
    ])
    def test_solid_paint(self, bgr, expected):
        assert dominant_vehicle_color(_solid(bgr), frame_grayscale=False) == expected

    def test_red_body_with_dark_windows_is_still_red(self):
        img = _solid((30, 30, 200))
        img[30:60, :] = (10, 10, 10)  # windows / tyres
        assert dominant_vehicle_color(img, frame_grayscale=False) == "red"

    def test_ir_frame_has_no_colour(self):
        gray = cv2.cvtColor(_solid((90, 90, 90)), cv2.COLOR_BGR2GRAY)
        ir = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        assert frame_is_grayscale(ir) is True
        assert dominant_vehicle_color(ir) is None

    def test_colour_frame_is_not_grayscale(self):
        assert frame_is_grayscale(_solid((30, 30, 200))) is False

    @pytest.mark.parametrize("name,expected", [
        ("Silver", "gray"), ("grey", "gray"), ("Dark Red", "red"), ("navy", "blue"), ("sparkly", None), (None, None),
    ])
    def test_normalize(self, name, expected):
        assert normalize_color_name(name) == expected

    @pytest.mark.parametrize("obs,exp,expected", [
        ("red", "red", "agree"),
        ("red", "black", "conflict"),
        ("white", "silver", "unknown"),  # neighbours never conflict
        (None, "red", "unknown"),         # night
        ("red", None, "unknown"),
    ])
    def test_agreement(self, obs, exp, expected):
        assert color_agreement(obs, exp) == expected


def test_box_iou():
    a = {"x": 0, "y": 0, "width": 100, "height": 100}
    assert box_iou(a, a) == pytest.approx(1.0)
    assert box_iou(a, {"x": 50, "y": 0, "width": 100, "height": 100}) == pytest.approx(1 / 3)
    assert box_iou(a, {"x": 500, "y": 500, "width": 10, "height": 10}) == 0.0
    assert box_iou(a, None) == 0.0
