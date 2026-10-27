"""#730 (#691 P1 S3): pure pair-comparison metrics for a local/cloud result.

Inputs are dicts, AIResult-like objects, or None. Outputs are a flat dict of
plain numbers (int/float) only: no text, no None, no numpy, so they survive a
JSON round trip and can go straight into the numbers-only daily summary.
No I/O. All data here is synthetic.
"""
import json
import math
import socket
from types import SimpleNamespace

import numpy as np
import pytest

from app.services import pair_metrics as pm

FAKE_NAME = "Thessaly Okonkwo-Vane"
FAKE_PLATE = "QX7TEST"

LOCAL = {"description": "A person walks a dog past the gate.", "confidence": 70,
         "objects_detected": ["person", "animal"], "matched_entity_ids": ["e1", "e2"]}
CLOUD = {"description": "A person walking a dog passes the gate.", "confidence": 90,
         "objects_detected": ["person", "animal", "vehicle"], "matched_entity_ids": ["e2"]}


def _assert_plain_numbers(m):
    assert isinstance(m, dict) and m
    for k, v in m.items():
        assert isinstance(k, str)
        assert type(v) in (int, float), (k, type(v))
        assert not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))), k
    assert json.loads(json.dumps(m)) == m


class TestScorePair:
    def test_full_pair(self):
        m = pm.score_pair(LOCAL, CLOUD)
        _assert_plain_numbers(m)
        assert m["pair_complete"] == 1
        assert m["local_blank"] == 0 and m["cloud_blank"] == 0 and m["blank_agree"] == 1
        assert m["objects_jaccard"] == pytest.approx(2 / 3)
        assert m["objects_local_only"] == 0 and m["objects_cloud_only"] == 1
        assert m["entities_jaccard"] == pytest.approx(1 / 2)
        assert 0.3 < m["description_similarity"] < 1.0
        assert m["confidence_delta"] == -20

    def test_identical_pair_scores_one(self):
        m = pm.score_pair(LOCAL, dict(LOCAL))
        assert m["objects_jaccard"] == 1.0 and m["entities_jaccard"] == 1.0
        assert m["description_similarity"] == 1.0 and m["confidence_delta"] == 0

    def test_disjoint_descriptions_score_zero(self):
        m = pm.score_pair({**LOCAL, "description": "alpha beta"},
                          {**CLOUD, "description": "gamma delta"})
        assert m["description_similarity"] == 0.0

    def test_keys_are_stable(self):
        a = pm.score_pair(LOCAL, CLOUD)
        b = pm.score_pair(None, None)
        c = pm.score_pair({}, CLOUD)
        assert set(a) == set(b) == set(c) == set(pm.METRIC_KEYS)


class TestBlankAndMissing:
    @pytest.mark.parametrize("blank", [
        {"description": "", "objects_detected": []},
        {"description": "   ", "objects_detected": []},
        {"description": "No person, vehicle, animal, or package is visible.",
         "objects_detected": []},
        {"description": "AI analysis unavailable", "objects_detected": ["unknown"]},
        {"blank": True, "description": "ignored", "objects_detected": ["person"]},
    ])
    def test_blank_results(self, blank):
        m = pm.score_pair(blank, CLOUD)
        _assert_plain_numbers(m)
        assert m["local_blank"] == 1 and m["cloud_blank"] == 0 and m["blank_agree"] == 0

    def test_both_blank_agree(self):
        m = pm.score_pair({"description": ""}, {"description": "AI analysis unavailable"})
        assert m["local_blank"] == 1 and m["cloud_blank"] == 1 and m["blank_agree"] == 1
        assert m["objects_jaccard"] == 1.0  # both empty sets agree

    def test_missing_local(self):
        m = pm.score_pair(None, CLOUD)
        _assert_plain_numbers(m)
        assert m["local_missing"] == 1 and m["cloud_missing"] == 0 and m["pair_complete"] == 0
        assert m["description_similarity"] == 0.0 and m["confidence_delta"] == 0

    def test_missing_both(self):
        m = pm.score_pair(None, None)
        _assert_plain_numbers(m)
        assert m["local_missing"] == 1 and m["cloud_missing"] == 1 and m["pair_complete"] == 0

    def test_failed_result_counts_as_missing(self):
        m = pm.score_pair({**LOCAL, "success": False}, CLOUD)
        assert m["local_missing"] == 1 and m["pair_complete"] == 0

    def test_missing_fields_are_tolerated(self):
        m = pm.score_pair({"description": "A cat."}, {"confidence": None})
        _assert_plain_numbers(m)


class TestInputShapes:
    def test_ai_result_like_objects(self):
        local = SimpleNamespace(description=LOCAL["description"], confidence=70,
                                objects_detected=["person", "animal"], success=True,
                                identification={"matched_entity_ids": ["e1", "e2"]})
        cloud = SimpleNamespace(description=CLOUD["description"], confidence=90,
                                objects_detected=["person", "animal", "vehicle"], success=True,
                                identification={"matched_entity_ids": ["e2"]})
        assert pm.score_pair(local, cloud) == pm.score_pair(LOCAL, CLOUD)

    def test_numpy_inputs_give_plain_numbers(self):
        local = {**LOCAL, "confidence": np.int64(70), "objects_detected": np.array(["person"])}
        cloud = {**CLOUD, "confidence": np.float32(90.0)}
        m = pm.score_pair(local, cloud)
        _assert_plain_numbers(m)
        assert m["confidence_delta"] == -20

    def test_entity_ids_from_json_string(self):
        local = {**LOCAL, "matched_entity_ids": json.dumps(["e1", "e2"])}
        assert pm.score_pair(local, CLOUD)["entities_jaccard"] == pytest.approx(0.5)

    def test_object_labels_are_case_insensitive(self):
        m = pm.score_pair({**LOCAL, "objects_detected": ["Person", "ANIMAL"]},
                          {**LOCAL, "objects_detected": ["person", "animal"]})
        assert m["objects_jaccard"] == 1.0


class TestNoTextAndNoIO:
    def test_outputs_carry_no_text(self):
        local = {**LOCAL, "description": f"{FAKE_NAME} parks {FAKE_PLATE}"}
        m = pm.score_pair(local, CLOUD)
        blob = json.dumps(m)
        assert FAKE_NAME not in blob and FAKE_PLATE not in blob
        assert "e1" not in json.dumps(list(m.values()))

    def test_no_io(self, monkeypatch, tmp_path):
        def boom(*a, **k):
            raise AssertionError("I/O attempted")
        monkeypatch.setattr("builtins.open", boom)
        monkeypatch.setattr(socket, "socket", boom)
        pm.score_pair(LOCAL, CLOUD)
        pm.score_pair(None, {"description": ""})

    def test_inputs_not_mutated(self):
        local = json.loads(json.dumps(LOCAL))
        pm.score_pair(local, CLOUD)
        assert local == LOCAL


class TestHelpers:
    def test_jaccard(self):
        assert pm.jaccard(set(), set()) == 1.0
        assert pm.jaccard({"a"}, set()) == 0.0
        assert pm.jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)

    def test_description_similarity_bounds(self):
        assert pm.description_similarity("", "") == 1.0
        assert pm.description_similarity("a cat", "") == 0.0
        assert pm.description_similarity("The Cat!", "the cat") == 1.0


class TestGracieReview:
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"),
                                     "nan", "inf", np.float64("nan"), 10 ** 400])
    def test_number_non_finite_is_none(self, bad):
        assert pm._number(bad) is None

    def test_non_finite_confidence_gives_zero_delta(self):
        m = pm.score_pair({**LOCAL, "confidence": float("nan")}, {**CLOUD, "confidence": 10 ** 400})
        _assert_plain_numbers(m)
        assert m["confidence_delta"] == 0

    def test_blank_constants_come_from_source(self):
        from app.services.ai_providers.local_provider import EMPTY_SCENE_DESCRIPTION
        from app.services.local_vlm_fallback import UNAVAILABLE_DESCRIPTION
        assert pm.BLANK_DESCRIPTIONS == frozenset({EMPTY_SCENE_DESCRIPTION, UNAVAILABLE_DESCRIPTION})

    @pytest.mark.parametrize("text", ["No activity detected.", "Nothing notable.", "No motion.",
                                      "No person, vehicle, animal, or package is visible. A cat sits."])
    def test_near_miss_text_is_not_blank(self, text):
        assert pm.is_blank({"description": text, "objects_detected": []}) is False

    def test_entities_not_compared_without_ids(self):
        a = {k: v for k, v in LOCAL.items() if k != "matched_entity_ids"}
        b = {k: v for k, v in CLOUD.items() if k != "matched_entity_ids"}
        m = pm.score_pair(a, b)
        assert m["entities_compared"] == 0 and m["entities_jaccard"] == 0.0

    def test_entities_compared_flag_set(self):
        m = pm.score_pair(LOCAL, CLOUD)
        assert m["entities_compared"] == 1
        assert m["entities_jaccard"] == pytest.approx(0.5)

    def test_entities_compared_in_metric_keys(self):
        assert "entities_compared" in pm.METRIC_KEYS
        assert pm.score_pair(None, None)["entities_compared"] == 0

    def test_prefers_ai_confidence(self):
        m = pm.score_pair({**LOCAL, "ai_confidence": 40, "confidence": 99},
                          {**CLOUD, "ai_confidence": 50, "confidence": 1})
        assert m["confidence_delta"] == -10

    def test_falls_back_to_confidence(self):
        m = pm.score_pair({**LOCAL, "ai_confidence": None}, CLOUD)
        assert m["confidence_delta"] == -20
