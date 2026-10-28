"""Vehicle make for entity linking under local-first analysis (#755).

Part 1: the structured identification carries ``vehicle_make`` /
``vehicle_model`` and the vehicle linking rules use them when the
description names no make.
Part 2: a usable local answer for a vehicle event that names no make is
escalated to the cloud chain once, within the daily cap and disabled
providers; a failed escalation keeps the local answer.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.ai_types import AIProvider, AIResult
from app.services.entity_alert_service import (
    identified_vehicle_text,
    vehicle_description_signal,
    vehicle_label_agrees,
)
from app.services.entity_gallery_service import evaluate_vehicle_candidates, pick_vehicle
from app.services.event_entity_linking import NamedIdentity, verify_named_identities
from app.services.identification import (
    IDENTIFICATION_INSTRUCTION,
    loads_identification,
    parse_identification,
)
from app.services.local_first import (
    LocalFirstConfig,
    reset_cloud_fallback_budget,
    result_names_vehicle_make,
    should_escalate_vehicle_make,
)
from app.services.local_vlm_fallback import reset_local_vlm_fallback_service
from app.services.protect_ai_pipeline import ProtectAIPipeline, reset_protect_ai_pipeline
from app.services.snapshot_service import SnapshotResult

PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

TESLA = NamedIdentity(entity_id="v-tesla", name="Owner's Tesla", entity_type="vehicle",
                      vehicle_color="red", vehicle_make="tesla")
BMW = NamedIdentity(entity_id="v-bmw", name="Guest's BMW", entity_type="vehicle",
                    vehicle_color="black", vehicle_make="bmw")


def _result(description, identification=None, success=True, provider="local", ai_confidence=80):
    return AIResult(
        description=description, confidence=ai_confidence or 0, objects_detected=["vehicle"],
        provider=provider, tokens_used=10, response_time_ms=900, cost_estimate=0.0,
        success=success, error=None if success else "failed", ai_confidence=ai_confidence,
        identification=identification,
    )


# ---------------------------------------------------------------- Part 1

class TestIdentificationVehicleFields:
    def test_prompt_asks_for_make_and_model(self):
        assert "vehicle_make" in IDENTIFICATION_INSTRUCTION
        assert "vehicle_model" in IDENTIFICATION_INSTRUCTION

    def test_parses_make_and_drops_cannot_tell(self):
        ident = parse_identification(
            '{"object_type": "vehicle", "vehicle_make": "Tesla", "vehicle_model": "cannot_tell"}'
        )
        assert ident["vehicle_make"] == "tesla"
        assert "vehicle_model" not in ident

    def test_absent_fields_keep_original_shape(self):
        ident = parse_identification('{"object_type": "person"}')
        assert "vehicle_make" not in ident and "vehicle_model" not in ident

    def test_none_object_drops_vehicle_fields(self):
        ident = parse_identification('{"object_type": "none", "vehicle_make": "BMW"}')
        assert "vehicle_make" not in ident

    def test_round_trips_through_storage(self):
        stored = loads_identification('{"object_type": "vehicle", "vehicle_make": "bmw", "vehicle_model": "x3"}')
        assert stored["vehicle_make"] == "bmw" and stored["vehicle_model"] == "x3"


class TestIdentifiedVehicleText:
    def test_appends_make_when_description_has_none(self):
        text = identified_vehicle_text("A red sedan pulls in.", {"vehicle_make": "tesla", "vehicle_model": "model 3"})
        assert "tesla" in text.lower() and text.startswith("A red sedan pulls in.")

    def test_description_make_wins(self):
        desc = "A black BMW pulls in."
        assert identified_vehicle_text(desc, {"vehicle_make": "tesla"}) == desc

    @pytest.mark.parametrize("ident", [None, {}, {"vehicle_make": "cannot_tell"}, {"vehicle_make": "zzzcar"}, "x"])
    def test_ignores_missing_or_unknown_make(self, ident):
        assert identified_vehicle_text("A red sedan.", ident) == "A red sedan."


class TestLinkingUsesIdentification:
    def test_label_agrees_only_with_identified_make(self):
        assert vehicle_label_agrees("A red sedan pulls in.", TESLA) is False
        assert vehicle_label_agrees("A red sedan pulls in.", TESLA, {"vehicle_make": "tesla"}) is True
        assert vehicle_label_agrees("A red sedan pulls in.", BMW, {"vehicle_make": "tesla"}) is False

    def test_description_signal(self):
        assert vehicle_description_signal("A red sedan.", TESLA) == "none"
        assert vehicle_description_signal("A red sedan.", TESLA, {"vehicle_make": "tesla"}) == "agree"
        assert vehicle_description_signal("A red sedan.", BMW, {"vehicle_make": "tesla"}) == "contradict"

    def test_evaluate_candidates_links_by_identified_make(self):
        evidence = evaluate_vehicle_candidates(
            "A red sedan pulls into the driveway.", [TESLA, BMW], [], {},
            extra_signals=[], identification={"vehicle_make": "tesla"},
        )
        winner, tied = pick_vehicle(evidence)
        assert winner is not None and winner.entity_id == "v-tesla" and winner.signal == "description"

    def test_evaluate_candidates_without_identification_unchanged(self):
        evidence = evaluate_vehicle_candidates(
            "A red sedan pulls into the driveway.", [TESLA, BMW], [], {}, extra_signals=[],
        )
        assert all(not e.accepted for e in evidence)

    def test_verify_named_identities_passes_identification(self):
        with patch("app.services.event_entity_linking._all_named_vehicle_rows", return_value=[TESLA, BMW]), \
                patch("app.services.event_entity_linking._vehicle_gallery", return_value={}), \
                patch("app.services.entity_gallery_service.registered_vehicle_signals", return_value=[]):
            linked = verify_named_identities(
                object(), description="A red sedan pulls in.", candidates=[],
                looks_like_vehicle=True, identification={"vehicle_make": "tesla"},
            )
        assert [v.entity_id for v in linked] == ["v-tesla"]


# ---------------------------------------------------------------- Part 2

def _config(cap=5, escalate=True):
    return LocalFirstConfig(enabled=True, max_wait_ms=120_000, min_confidence=50,
                            daily_cloud_cap=cap, escalate_vehicle_no_make=escalate)


class TestShouldEscalate:
    def test_vehicle_without_make_escalates(self):
        with patch("app.services.ai_provider_order.disabled_providers", return_value=frozenset()):
            assert should_escalate_vehicle_make(_result("A red SUV pulls in."), "vehicle", _config())

    def test_make_in_description_or_identification_does_not(self):
        assert result_names_vehicle_make(_result("A red Tesla pulls in."))
        assert result_names_vehicle_make(_result("A red SUV.", {"vehicle_make": "tesla"}))
        assert not should_escalate_vehicle_make(_result("A red Tesla pulls in."), "vehicle", _config())

    @pytest.mark.parametrize(
        "res, event_type, cfg",
        [
            (_result("A red SUV."), "person", _config()),
            (_result("A red SUV."), "vehicle", _config(escalate=False)),
            (_result("A red SUV."), "vehicle", _config(cap=0)),
            (_result("Nothing there.", {"object_type": "none"}), "vehicle", _config()),
            (_result("", success=False), "vehicle", _config()),
            (None, "vehicle", _config()),
        ],
    )
    def test_no_escalation(self, res, event_type, cfg):
        assert not should_escalate_vehicle_make(res, event_type, cfg)

    def test_all_cloud_providers_disabled(self):
        everything = frozenset({AIProvider.OPENAI, AIProvider.GROK, AIProvider.CLAUDE, AIProvider.GEMINI})
        with patch("app.services.ai_provider_order.disabled_providers", return_value=everything):
            assert not should_escalate_vehicle_make(_result("A red SUV."), "vehicle", _config())

    def test_default_setting_is_on(self):
        from app.core.config import settings

        assert settings.LOCAL_PRIMARY_ESCALATE_VEHICLE_NO_MAKE is True


@pytest.fixture
def pipeline():
    reset_protect_ai_pipeline()
    reset_cloud_fallback_budget()
    reset_local_vlm_fallback_service()
    yield ProtectAIPipeline()
    reset_cloud_fallback_budget()
    reset_local_vlm_fallback_service()


@pytest.fixture
def camera():
    cam = Mock()
    cam.id, cam.name, cam.analysis_mode = "camera-1", "Driveway", "single_frame"
    return cam


@pytest.fixture
def snapshot():
    return SnapshotResult(
        image_base64=PNG_B64, thumbnail_path="/tmp/t.jpg", width=640, height=360,
        camera_id="camera-1", timestamp=datetime.now(timezone.utc),
    )


async def _submit(pipeline, camera, snapshot, *, local, cloud, config, event_type="vehicle"):
    from app.services.local_vlm_fallback import PrimaryOutcome

    orch = MagicMock()
    orch.analyze_image = AsyncMock(return_value=cloud)
    service = MagicMock()
    service.describe_now = AsyncMock(return_value=PrimaryOutcome(local, "ok", 0.2))
    with patch("app.services.vision_analysis_orchestrator.get_vision_analysis_orchestrator", return_value=orch), \
            patch("app.services.ai_service.ai_service") as ai, \
            patch("app.core.database.get_db_session"), \
            patch("app.services.local_first.LocalFirstConfig.from_settings", return_value=config), \
            patch("app.services.local_first._seed_from_db", return_value=0), \
            patch("app.services.ai_provider_order.disabled_providers", return_value=frozenset()), \
            patch("app.services.local_vlm_fallback.get_local_vlm_fallback_service", return_value=service):
        ai.load_api_keys_from_db = AsyncMock()
        out = await pipeline.submit_snapshot_for_analysis(
            snapshot_result=snapshot, camera=camera, event_type=event_type, clip_path=None,
        )
    return out, orch


class TestPipelineEscalation:
    @pytest.mark.asyncio
    async def test_vehicle_without_make_uses_cloud(self, pipeline, camera, snapshot, caplog):
        caplog.set_level("INFO")
        out, orch = await _submit(
            pipeline, camera, snapshot, local=_result("A red SUV pulls in."),
            cloud=_result("A red Tesla pulls in.", provider="grok"), config=_config(),
        )
        assert out.provider == "grok"
        assert orch.analyze_image.await_args.kwargs["extended_budget"] is True
        assert pipeline._last_fallback_reason == "local_primary:vehicle_no_make"
        logged = [r for r in caplog.records if getattr(r, "event_type", "") == "local_primary_vehicle_make_escalation"]
        assert logged and "SUV" not in logged[0].getMessage()

    @pytest.mark.asyncio
    async def test_cloud_failure_keeps_local_answer(self, pipeline, camera, snapshot):
        out, _ = await _submit(
            pipeline, camera, snapshot, local=_result("A red SUV pulls in."),
            cloud=_result("", success=False, provider="grok"), config=_config(),
        )
        assert out.provider == "local" and out.success
        assert pipeline._last_requested_mode == "local_primary"
        assert pipeline._last_fallback_reason == "local_primary:vehicle_no_make;cloud_failed"

    @pytest.mark.asyncio
    async def test_cap_reached_keeps_local_answer(self, pipeline, camera, snapshot):
        out, orch = await _submit(
            pipeline, camera, snapshot, local=_result("A red SUV pulls in."),
            cloud=_result("A red Tesla.", provider="grok"), config=_config(cap=1),
        )
        assert out.provider == "grok"
        out, orch = await _submit(
            pipeline, camera, snapshot, local=_result("A red SUV pulls in."),
            cloud=_result("A red Tesla.", provider="grok"), config=_config(cap=1),
        )
        orch.analyze_image.assert_not_called()
        assert out.provider == "local"
        assert pipeline._last_fallback_reason == "local_primary:vehicle_no_make;cloud_cap_reached"

    @pytest.mark.asyncio
    async def test_make_named_locally_skips_cloud(self, pipeline, camera, snapshot):
        out, orch = await _submit(
            pipeline, camera, snapshot, local=_result("A red SUV.", {"vehicle_make": "tesla"}),
            cloud=_result("x", provider="grok"), config=_config(),
        )
        orch.analyze_image.assert_not_called()
        assert out.provider == "local"

    @pytest.mark.asyncio
    async def test_person_event_never_escalates(self, pipeline, camera, snapshot):
        out, orch = await _submit(
            pipeline, camera, snapshot, local=_result("A person walks by."),
            cloud=_result("x", provider="grok"), config=_config(), event_type="person",
        )
        orch.analyze_image.assert_not_called()
        assert out.provider == "local"

    @pytest.mark.asyncio
    async def test_option_off_keeps_local(self, pipeline, camera, snapshot):
        out, orch = await _submit(
            pipeline, camera, snapshot, local=_result("A red SUV pulls in."),
            cloud=_result("x", provider="grok"), config=_config(escalate=False),
        )
        orch.analyze_image.assert_not_called()
        assert out.provider == "local"
