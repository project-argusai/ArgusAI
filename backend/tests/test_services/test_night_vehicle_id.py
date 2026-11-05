"""Night vehicle identification: low-light handling, headlight signature,
and the labelled context guess. All fixtures are synthetic."""
import base64
import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from app.services.ai_types import AIResult
from app.services.entity_alert_service import (
    entity_vehicle_traits,
    vehicle_description_signal,
    vehicle_label_agrees,
    vehicle_traits_signal,
)
from app.services.event_entity_linking import NamedIdentity
from app.services.identification import (
    IDENTIFICATION_INSTRUCTION,
    loads_identification,
    parse_identification,
)
from app.services.local_first import LocalFirstConfig, should_escalate_night_vehicle
from app.services.local_vlm_fallback import prepare_low_light, tag_frame_condition
from app.services.night_vehicle_guess import (
    GuessConfig,
    Sighting,
    action_indicates_approach,
    direction_kind,
    is_unidentified_night_arrival,
    pick_guess,
    pick_guess_skip_reason,
    score_candidates,
    suggest_for_event,
)
from app.services.night_vision import (
    FRAME_IR,
    FRAME_LOW_LIGHT,
    FRAME_NORMAL,
    classify_frame,
    enhance_low_light,
    is_night_hour,
    low_light_prompt_note,
)


def _b64(arr):
    buf = io.BytesIO()
    Image.fromarray(arr.astype("uint8")).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _gray(level=40):
    return _b64(np.full((64, 64, 3), level))


def _dark_color():
    arr = np.zeros((64, 64, 3))
    arr[..., 0] = 60
    arr[..., 2] = 10
    return _b64(arr)


def _bright_color():
    arr = np.zeros((64, 64, 3))
    arr[..., 0] = 200
    arr[..., 1] = 120
    arr[..., 2] = 40
    return _b64(arr)


def _gradient_dark():
    ramp = np.tile(np.linspace(5, 50, 64), (64, 1))
    arr = np.stack([ramp + 15, ramp, ramp], axis=-1)
    return _b64(arr)


# ------------------------------------------------------------ Part 3: low light

class TestClassifyFrame:
    def test_grayscale_is_ir(self):
        assert classify_frame(_gray()).condition == FRAME_IR

    def test_dark_colour_is_low_light(self):
        assert classify_frame(_dark_color()).condition == FRAME_LOW_LIGHT

    def test_bright_colour_is_normal(self):
        light = classify_frame(_bright_color())
        assert light.condition == FRAME_NORMAL and not light.is_low_light

    def test_bad_image_is_none(self):
        assert classify_frame("not-an-image") is None


class TestEnhance:
    @pytest.mark.parametrize("method", ["clahe", "gamma"])
    def test_brightens(self, method):
        src = _gradient_dark()
        out = enhance_low_light(src, method)
        assert out != src
        before = np.asarray(Image.open(io.BytesIO(base64.b64decode(src)))).mean()
        after = np.asarray(Image.open(io.BytesIO(base64.b64decode(out)))).mean()
        assert after > before

    def test_none_method_and_bad_input_pass_through(self):
        assert enhance_low_light("abc", "none") == "abc"
        assert enhance_low_light("abc", "gamma") == "abc"


class TestPromptNote:
    def test_ir_note_forbids_colour(self):
        note = low_light_prompt_note(classify_frame(_gray()), enhanced=True)
        assert "do not name a vehicle colour" in note and "headlight_pattern" in note

    def test_normal_frame_has_no_note(self):
        assert low_light_prompt_note(classify_frame(_bright_color())) == ""


class TestPrepareLowLight:
    def _settings(self, **kw):
        base = dict(NIGHT_VEHICLE_LOW_LIGHT_ENABLED=True, NIGHT_VEHICLE_ENHANCE_METHOD="gamma", NIGHT_VEHICLE_DARK_LUMA=70)
        base.update(kw)
        return patch.multiple("app.core.config.settings", **base)

    def test_dark_frame_enhanced_and_noted(self):
        src = _gradient_dark()
        with self._settings():
            image, prompt, light = prepare_low_light(src, "PROMPT")
        assert image != src and "NIGHT FRAME NOTE" in prompt and light.is_low_light

    def test_disabled_is_untouched(self):
        src = _gradient_dark()
        with self._settings(NIGHT_VEHICLE_LOW_LIGHT_ENABLED=False):
            assert prepare_low_light(src, "PROMPT") == (src, "PROMPT", None)

    def test_tag_frame_condition(self):
        res = SimpleNamespace(identification={"object_type": "vehicle"})
        tag_frame_condition(res, classify_frame(_gray()))
        assert res.identification["frame_condition"] == "ir"
        empty = SimpleNamespace(identification={"object_type": "none"})
        tag_frame_condition(empty, classify_frame(_gray()))
        assert "frame_condition" not in empty.identification


class TestColourIgnoredOnIR:
    RED = NamedIdentity(entity_id="v-1", name="Sample Car", entity_type="vehicle", vehicle_color="red")

    def test_label_agrees_ignores_colour_on_ir(self):
        desc = "A white SUV pulls in."
        assert not vehicle_label_agrees(desc, self.RED, {"object_type": "vehicle"})
        assert vehicle_label_agrees(desc, self.RED, {"object_type": "vehicle", "frame_condition": "ir"})

    def test_description_signal_ignores_colour_on_ir(self):
        entity = NamedIdentity(entity_id="v-1", name="Sample Car", entity_type="vehicle",
                               vehicle_color="red", vehicle_make="tesla")
        desc = "A white vehicle pulls in."
        assert vehicle_description_signal(desc, entity, {}) == "contradict"
        assert vehicle_description_signal(desc, entity, {"frame_condition": "ir"}) == "none"


def _result(ident, success=True):
    return AIResult(description="A vehicle with bright headlights.", confidence=80, objects_detected=["vehicle"],
                    provider="local", tokens_used=0, response_time_ms=1, cost_estimate=0.0, success=success,
                    identification=ident)


class TestNightEscalation:
    CFG = LocalFirstConfig(enabled=True, daily_cloud_cap=5)

    @pytest.fixture(autouse=True)
    def _providers(self):
        with patch("app.services.ai_provider_order.disabled_providers", return_value=frozenset()):
            yield

    def test_unidentified_night_vehicle_escalates(self):
        ident = {"object_type": "vehicle", "identity": "unknown", "frame_condition": "ir"}
        assert should_escalate_night_vehicle(_result(ident), "vehicle", self.CFG)

    @pytest.mark.parametrize("ident, event_type, cfg", [
        ({"object_type": "vehicle", "identity": "unknown", "frame_condition": "normal"}, "vehicle", CFG),
        ({"object_type": "vehicle", "identity": "Sample Car", "frame_condition": "ir"}, "vehicle", CFG),
        ({"object_type": "none", "frame_condition": "ir"}, "vehicle", CFG),
        ({"object_type": "vehicle", "frame_condition": "ir"}, "person", CFG),
        ({"object_type": "vehicle", "frame_condition": "ir"}, "vehicle",
         LocalFirstConfig(enabled=True, daily_cloud_cap=5, escalate_night_unidentified=False)),
        ({"object_type": "vehicle", "frame_condition": "ir"}, "vehicle", LocalFirstConfig(enabled=True, daily_cloud_cap=0)),
    ])
    def test_no_escalation(self, ident, event_type, cfg):
        assert not should_escalate_night_vehicle(_result(ident), event_type, cfg)

    def test_default_on(self):
        from app.core.config import settings

        assert settings.NIGHT_VEHICLE_ESCALATE_UNIDENTIFIED is True
        assert settings.NIGHT_VEHICLE_LOW_LIGHT_ENABLED is True


# ------------------------------------------------------- Part 2: headlight signature

LIGHT_BAR = NamedIdentity(entity_id="v-a", name="Car A", entity_type="vehicle",
                          vehicle_traits={"front_light_bar": True, "front_plate": False})
SIGNATURE_BAR = SimpleNamespace(
    id="v-a", name="Car A", entity_metadata=json.dumps(
        {"distinguishing_traits": {"night_lighting_signature": "full_width_light_bar"}}))
SIGNATURE_SPLIT = SimpleNamespace(
    id="v-b", name="Car B", entity_metadata=json.dumps(
        {"distinguishing_traits": {"night_lighting_signature": "split_headlights"}}))


class TestHeadlightSignature:
    def test_prompt_and_parse(self):
        assert "headlight_pattern" in IDENTIFICATION_INSTRUCTION and "drl_shape" in IDENTIFICATION_INSTRUCTION
        ident = parse_identification(
            '{"object_type": "vehicle", "headlight_pattern": "Full-width light bar", "drl_shape": "nonsense"}')
        assert ident["headlight_pattern"] == "full_width_light_bar"
        assert "drl_shape" not in ident

    def test_stored_signature_read(self):
        assert entity_vehicle_traits(SIGNATURE_BAR) == {"night_lighting_signature": "full_width_light_bar"}

    def test_light_bar_pattern_supports_saved_light_bar(self):
        assert vehicle_traits_signal(LIGHT_BAR, {"headlight_pattern": "full_width_light_bar"}) == "agree"
        assert vehicle_traits_signal(LIGHT_BAR, {"headlight_pattern": "split_headlights"}) == "contradict"

    def test_signature_match_and_veto(self):
        bar = {"headlight_pattern": "full_width_light_bar"}
        assert vehicle_traits_signal(SIGNATURE_BAR, bar) == "agree"
        assert vehicle_traits_signal(SIGNATURE_SPLIT, bar) == "contradict"

    def test_setting_off_ignores_lighting(self):
        with patch("app.core.config.settings.NIGHT_VEHICLE_LIGHTING_MATCH_ENABLED", False):
            assert vehicle_traits_signal(SIGNATURE_BAR, {"headlight_pattern": "split_headlights"}) == "none"


# ------------------------------------------------------------- Part 1: context guess

NIGHT = datetime(2026, 1, 10, 3, 0, tzinfo=timezone.utc)
CFG = GuessConfig(night_start_hour=0, night_end_hour=23)  # make every hour "night" for unit tests


def _veh(entity_id, name, traits=None):
    return SimpleNamespace(id=entity_id, name=name, is_blocked=False, entity_type="vehicle",
                           vehicle_traits=traits or {})


class TestScoring:
    def test_direction_kind(self):
        assert direction_kind("away") == "departure"
        assert direction_kind("toward camera") == "arrival"
        assert direction_kind("cannot_tell") == "other"
        # Schema / free-text "left" used to miss "leav" and stay other.
        assert direction_kind("left") == "departure"
        assert direction_kind("going left") == "departure"
        assert direction_kind("leaving") == "departure"
        assert direction_kind("right") == "other"

    def test_departed_vehicle_is_guessed(self):
        a, b = _veh("a", "Car A"), _veh("b", "Car B")
        sightings = [Sighting("a", "cam", NIGHT - timedelta(hours=4), "departure"),
                     Sighting("b", "cam", NIGHT - timedelta(hours=4), "arrival")]
        best = pick_guess(score_candidates(event_time=NIGHT, camera_id="cam", identification={},
                                           vehicles=[a, b], sightings=sightings, config=CFG))
        assert best.entity.id == "a" and best.basis

    def test_returned_vehicle_is_not_guessed(self):
        a = _veh("a", "Car A")
        sightings = [Sighting("a", "cam", NIGHT - timedelta(hours=5), "departure"),
                     Sighting("a", "cam", NIGHT - timedelta(hours=2), "arrival")]
        assert pick_guess(score_candidates(event_time=NIGHT, camera_id="cam", identification={},
                                           vehicles=[a], sightings=sightings, config=CFG)) is None

    def test_ambiguous_last_seen_plus_hour_reaches_min_score(self):
        """Last same-cam sighting other/cannot_tell gives +1; with hour pattern reaches 2."""
        a = _veh("a", "Car A")
        sightings = [
            Sighting("a", "cam", NIGHT - timedelta(hours=4), "other"),
            Sighting("a", "cam", NIGHT - timedelta(days=1), "arrival"),
            Sighting("a", "cam", NIGHT - timedelta(days=2), "arrival"),
        ]
        best = pick_guess(score_candidates(event_time=NIGHT, camera_id="cam", identification={},
                                           vehicles=[a], sightings=sightings, config=CFG))
        assert best is not None and best.entity.id == "a"
        assert best.score == 2.0
        assert any("direction unclear" in b for b in best.basis)

    def test_ambiguous_last_seen_alone_below_min_score(self):
        a = _veh("a", "Car A")
        sightings = [Sighting("a", "cam", NIGHT - timedelta(hours=3), "other")]
        scored = score_candidates(event_time=NIGHT, camera_id="cam", identification={},
                                  vehicles=[a], sightings=sightings, config=CFG)
        assert scored and scored[0].score == 1.0
        assert pick_guess(scored) is None

    def test_arrival_pattern_plus_trait_agreement(self):
        a = _veh("a", "Car A", {"front_light_bar": True})
        sightings = [Sighting("a", "cam", NIGHT - timedelta(days=d), "arrival") for d in (1, 2, 3)]
        best = pick_guess(score_candidates(event_time=NIGHT, camera_id="cam",
                                           identification={"headlight_pattern": "full_width_light_bar"},
                                           vehicles=[a], sightings=sightings, config=CFG))
        assert best is not None and best.score == 2.0

    def test_trait_contradiction_vetoes(self):
        a = _veh("a", "Car A", {"front_light_bar": True})
        sightings = [Sighting("a", "cam", NIGHT - timedelta(hours=3), "departure")]
        assert score_candidates(event_time=NIGHT, camera_id="cam",
                                identification={"headlight_pattern": "split_headlights"},
                                vehicles=[a], sightings=sightings, config=CFG) == []

    def test_tie_gives_no_guess(self):
        a, b = _veh("a", "Car A"), _veh("b", "Car B")
        sightings = [Sighting(x, "cam", NIGHT - timedelta(hours=3), "departure") for x in ("a", "b")]
        scored = score_candidates(event_time=NIGHT, camera_id="cam", identification={},
                                  vehicles=[a, b], sightings=sightings, config=CFG)
        assert pick_guess(scored) is None
        assert pick_guess_skip_reason(scored) == "tie"
        assert pick_guess_skip_reason([]) == "score"

    def test_night_arrival_gate(self):
        ev = SimpleNamespace(smart_detection_type="vehicle", timestamp=NIGHT)
        day_cfg = GuessConfig(night_start_hour=22, night_end_hour=22)  # empty window
        assert is_unidentified_night_arrival(ev, {"object_type": "vehicle", "frame_condition": "ir"}, day_cfg)
        assert not is_unidentified_night_arrival(ev, {"object_type": "vehicle"}, day_cfg)
        assert not is_unidentified_night_arrival(ev, {"object_type": "vehicle", "identity": "Car A",
                                                      "frame_condition": "ir"}, day_cfg)
        # Clear leave without approach action still blocked.
        assert not is_unidentified_night_arrival(ev, {"object_type": "vehicle", "direction": "away",
                                                      "frame_condition": "ir"}, day_cfg)
        # Soft gate: away + approaching action is eligible; cannot_tell/other too.
        assert is_unidentified_night_arrival(
            ev,
            {"object_type": "vehicle", "direction": "away", "action": "approaching driveway",
             "frame_condition": "ir"},
            day_cfg,
        )
        assert is_unidentified_night_arrival(
            ev, {"object_type": "vehicle", "direction": "cannot_tell", "frame_condition": "ir"}, day_cfg
        )
        assert is_unidentified_night_arrival(
            ev, {"object_type": "vehicle", "direction": "other", "frame_condition": "ir"}, day_cfg
        )
        assert action_indicates_approach("approaching driveway")
        assert action_indicates_approach("pulling in")
        assert not action_indicates_approach("cannot_tell")
        assert not action_indicates_approach("driving away")

    def test_is_night_hour_wraps(self):
        local = datetime(2026, 1, 1, 23, 0)
        assert is_night_hour(local, 18, 7)
        assert not is_night_hour(local.replace(hour=12), 18, 7)


class TestSuggestForEvent:
    def _setup(self, db):
        from app.models.camera import Camera
        from app.models.event import Event
        from app.models.recognized_entity import EntityEvent, RecognizedEntity

        db.add(Camera(id="cam-1", name="Test Cam", type="rtsp", rtsp_url="rtsp://example.invalid/s",
                      source_type="rtsp", is_enabled=True, frame_rate=5))
        car = RecognizedEntity(id="ent-1", entity_type="vehicle", name="Car A",
                               reference_embedding="[]", occurrence_count=1,
                               first_seen_at=NIGHT - timedelta(days=5), last_seen_at=NIGHT - timedelta(hours=4))
        db.add(car)
        left = Event(id="ev-left", camera_id="cam-1", timestamp=NIGHT - timedelta(hours=4),
                     description="A car drives away.", confidence=80, objects_detected='["vehicle"]',
                     identification=json.dumps({"object_type": "vehicle", "direction": "away"}))
        new = Event(id="ev-new", camera_id="cam-1", timestamp=NIGHT,
                    description="A vehicle with bright headlights pulls in.", confidence=80,
                    objects_detected='["vehicle"]', smart_detection_type="vehicle",
                    identification=json.dumps({"object_type": "vehicle", "identity": "unknown",
                                               "direction": "toward camera", "frame_condition": "ir"}))
        db.add_all([left, new])
        db.flush()
        db.add(EntityEvent(entity_id="ent-1", event_id="ev-left", similarity_score=1.0))
        db.commit()
        return new

    def test_stores_labelled_guess_without_linking(self, db_session):
        from app.models.recognized_entity import EntityEvent

        new = self._setup(db_session)
        payload = suggest_for_event(db_session, "ev-new", CFG)
        assert payload["label"] == "likely Car A (guess)" and payload["is_guess"] is True
        db_session.refresh(new)
        stored = loads_identification(new.identification)
        assert stored["likely_vehicle"]["label"] == "likely Car A (guess)"
        assert not new.matched_entity_ids
        assert not new.alert_triggered
        assert db_session.query(EntityEvent).filter(EntityEvent.event_id == "ev-new").count() == 0

    def test_disabled(self, db_session):
        self._setup(db_session)
        assert suggest_for_event(db_session, "ev-new", GuessConfig(enabled=False)) is None

    def test_skip_logs_disabled(self, db_session, caplog):
        import logging

        self._setup(db_session)
        with caplog.at_level(logging.DEBUG, logger="app.services.night_vehicle_guess"):
            assert suggest_for_event(db_session, "ev-new", GuessConfig(enabled=False)) is None
        records = [r for r in caplog.records if getattr(r, "event_type", None) == "night_vehicle_guess_skipped"]
        assert records and records[-1].reason == "disabled"

    def test_skip_logs_departure(self, db_session, caplog):
        import logging
        from app.models.event import Event

        self._setup(db_session)
        ev = db_session.query(Event).filter(Event.id == "ev-new").one()
        ev.identification = json.dumps({
            "object_type": "vehicle",
            "identity": "unknown",
            "direction": "away",
            "action": "cannot_tell",
            "frame_condition": "ir",
        })
        db_session.commit()
        with caplog.at_level(logging.DEBUG, logger="app.services.night_vehicle_guess"):
            assert suggest_for_event(db_session, "ev-new", CFG) is None
        records = [r for r in caplog.records if getattr(r, "event_type", None) == "night_vehicle_guess_skipped"]
        assert records and records[-1].reason == "departure"

    def test_skip_logs_already_linked(self, db_session, caplog):
        import logging
        from app.models.event import Event
        from app.models.recognized_entity import EntityEvent

        self._setup(db_session)
        db_session.add(EntityEvent(entity_id="ent-1", event_id="ev-new", similarity_score=0.9))
        db_session.commit()
        with caplog.at_level(logging.DEBUG, logger="app.services.night_vehicle_guess"):
            assert suggest_for_event(db_session, "ev-new", CFG) is None
        records = [r for r in caplog.records if getattr(r, "event_type", None) == "night_vehicle_guess_skipped"]
        assert records and records[-1].reason == "already_linked"

    def test_away_with_approach_action_still_guesses(self, db_session):
        """Soft gate: direction=away but action approaching remains eligible."""
        from app.models.event import Event

        new = self._setup(db_session)
        new.identification = json.dumps({
            "object_type": "vehicle",
            "identity": "unknown",
            "direction": "away",
            "action": "approaching driveway",
            "frame_condition": "ir",
        })
        db_session.commit()
        payload = suggest_for_event(db_session, "ev-new", CFG)
        assert payload is not None and payload["is_guess"] is True


# ------------------------------------------------------ pipeline: night escalation

from tests.test_services.test_local_vehicle_make_linking import (  # noqa: E402
    _submit,
    camera,  # noqa: F401 - fixture
    pipeline,  # noqa: F401 - fixture
    snapshot,  # noqa: F401 - fixture
)


class TestPipelineNightEscalation:
    @pytest.mark.asyncio
    async def test_night_unidentified_uses_cloud_and_keeps_frame_condition(self, pipeline, camera, snapshot):
        local = _result({"object_type": "vehicle", "identity": "unknown", "vehicle_make": "tesla",
                         "frame_condition": "ir"})
        cloud = _result({"object_type": "vehicle", "identity": "unknown"})
        cloud.provider = "grok"
        out, orch = await _submit(pipeline, camera, snapshot, local=local, cloud=cloud,
                                  config=LocalFirstConfig(enabled=True, daily_cloud_cap=5))
        assert out.provider == "grok"
        assert pipeline._last_fallback_reason == "local_primary:night_vehicle_unidentified"
        assert out.identification["frame_condition"] == "ir"

    @pytest.mark.asyncio
    async def test_night_option_off_keeps_local(self, pipeline, camera, snapshot):
        local = _result({"object_type": "vehicle", "identity": "unknown", "vehicle_make": "tesla",
                         "frame_condition": "ir"})
        out, orch = await _submit(pipeline, camera, snapshot, local=local, cloud=_result({}),
                                  config=LocalFirstConfig(enabled=True, daily_cloud_cap=5,
                                                          escalate_night_unidentified=False))
        orch.analyze_image.assert_not_called()
        assert out.provider == "local"
