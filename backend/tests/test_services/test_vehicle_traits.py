"""Distinguishing vehicle traits as a soft linking signal (#755).

A saved vehicle may store ``entity_metadata["distinguishing_traits"]``
(``front_light_bar``, ``front_plate``). The AI reports what it sees as
``front_light_bar`` / ``front_plate_present``. A contradiction vetoes, an
agreement modestly supports, unknown is neutral.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.entity_alert_service import (
    entity_vehicle_traits,
    vehicle_label_agrees,
    vehicle_traits_signal,
)
from app.services.entity_gallery_service import (
    GalleryEntry,
    MatchThresholds,
    evaluate_vehicle_candidates,
    pick_vehicle,
)
from app.services.event_entity_linking import NamedIdentity, as_named_identity
from app.services.identification import IDENTIFICATION_INSTRUCTION, parse_identification

LIGHT_BAR_NO_PLATE = {"front_light_bar": True, "front_plate": False}


def _vehicle(entity_id="v-a", name="Red Tesla", make="tesla", color="red", traits=LIGHT_BAR_NO_PLATE):
    return NamedIdentity(entity_id=entity_id, name=name, entity_type="vehicle",
                         vehicle_color=color, vehicle_make=make, vehicle_traits=traits)


class TestIdentificationTraits:
    def test_prompt_mentions_traits(self):
        assert "front_light_bar" in IDENTIFICATION_INSTRUCTION
        assert "front_plate_present" in IDENTIFICATION_INSTRUCTION
        assert "light bar" in IDENTIFICATION_INSTRUCTION.split("Fields:")[0]

    def test_parses_yes_no_and_drops_unknown(self):
        ident = parse_identification(
            '{"object_type": "vehicle", "front_light_bar": "Yes", "front_plate_present": "unknown"}'
        )
        assert ident["front_light_bar"] == "yes"
        assert "front_plate_present" not in ident

    def test_none_object_drops_traits(self):
        ident = parse_identification('{"object_type": "none", "front_light_bar": "yes"}')
        assert "front_light_bar" not in ident


class TestStoredTraits:
    def test_reads_entity_metadata_json(self):
        row = SimpleNamespace(entity_metadata=json.dumps({"distinguishing_traits": {"front_light_bar": True, "x": 1}}))
        assert entity_vehicle_traits(row) == {"front_light_bar": True}

    @pytest.mark.parametrize("meta", [None, "", "not json", json.dumps([1]), json.dumps({"distinguishing_traits": "yes"})])
    def test_missing_or_bad_metadata_is_empty(self, meta):
        assert entity_vehicle_traits(SimpleNamespace(entity_metadata=meta)) == {}

    def test_named_identity_carries_traits(self):
        row = SimpleNamespace(id="v-a", name="Red Tesla", entity_type="vehicle",
                              entity_metadata=json.dumps({"distinguishing_traits": LIGHT_BAR_NO_PLATE}))
        assert as_named_identity(row).vehicle_traits == LIGHT_BAR_NO_PLATE


class TestTraitsSignal:
    @pytest.mark.parametrize(
        "ident, expected",
        [
            ({"front_light_bar": "yes", "front_plate_present": "no"}, "agree"),
            ({"front_light_bar": "yes"}, "agree"),
            ({"front_plate_present": "yes"}, "contradict"),
            ({"front_light_bar": "no"}, "contradict"),
            ({"front_light_bar": "yes", "front_plate_present": "yes"}, "none"),
            ({}, "none"),
            (None, "none"),
        ],
    )
    def test_signal(self, ident, expected):
        assert vehicle_traits_signal(_vehicle(), ident) == expected

    def test_entity_without_traits_is_neutral(self):
        assert vehicle_traits_signal(_vehicle(traits=None), {"front_plate_present": "yes"}) == "none"

    def test_label_agrees_vetoed_by_contradiction(self):
        desc = "A red Tesla pulls in."
        assert vehicle_label_agrees(desc, _vehicle(), {"front_light_bar": "yes"})
        assert not vehicle_label_agrees(desc, _vehicle(), {"front_plate_present": "yes"})


class TestEvaluateWithTraits:
    def test_description_link_vetoed_by_contradiction(self):
        ev = evaluate_vehicle_candidates("A red Tesla pulls in.", [_vehicle()], [], {}, extra_signals=[],
                                         identification={"front_plate_present": "yes"})
        assert not ev[0].accepted and ev[0].reason == "traits_contradict"
        assert ev[0].as_log()["traits"] == "contradict"

    def test_unknown_traits_keep_description_link(self):
        ev = evaluate_vehicle_candidates("A red Tesla pulls in.", [_vehicle()], [], {}, extra_signals=[],
                                         identification={})
        assert ev[0].accepted and ev[0].signal == "description"

    def test_traits_break_description_tie(self):
        a = _vehicle("v-a", traits=LIGHT_BAR_NO_PLATE)
        b = _vehicle("v-b", name="Other Tesla", traits={"front_light_bar": False})
        ev = evaluate_vehicle_candidates("A red Tesla pulls in.", [a, b], [], {}, extra_signals=[],
                                         identification={"front_light_bar": "yes"})
        winner, tied = pick_vehicle(ev)
        assert winner is not None and winner.entity_id == "v-a" and tied == []

    def test_no_traits_tie_stays_tied(self):
        a, b = _vehicle("v-a", traits=None), _vehicle("v-b", name="Other Tesla", traits=None)
        ev = evaluate_vehicle_candidates("A red Tesla pulls in.", [a, b], [], {}, extra_signals=[])
        winner, tied = pick_vehicle(ev)
        assert winner is None and len(tied) == 2

    def test_agreeing_traits_support_a_supported_crop(self):
        t = MatchThresholds.from_env()
        mid = (t.vehicle_support + t.vehicle_strong) / 2
        if not t.vehicle_support < mid < t.vehicle_strong:
            pytest.skip("support and strong thresholds coincide")
        obs = SimpleNamespace(embedding=[1.0, 0.0], color="red", stationary=False)
        entry = object.__new__(GalleryEntry)
        with patch("app.services.entity_gallery_service.gallery_score", return_value=mid), \
                patch.object(GalleryEntry, "reference_color", return_value="red", create=True):
            plain = evaluate_vehicle_candidates("A red car.", [_vehicle()], [obs], {"v-a": entry},
                                                extra_signals=[], identification={})
            backed = evaluate_vehicle_candidates("A red car.", [_vehicle()], [obs], {"v-a": entry},
                                                 extra_signals=[], identification={"front_light_bar": "yes"})
        assert not plain[0].accepted and plain[0].reason == "crop_disagrees"
        assert backed[0].accepted and backed[0].signal == "crop+color"
