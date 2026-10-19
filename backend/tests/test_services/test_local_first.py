"""Local-first analysis (#691): local model primary, cloud as a capped fallback.

Covers the usable-answer rules, the daily cloud fallback cap, the live
local call (queue wait + call budget), the pipeline wiring (local answer
first, cloud only when unusable and under the cap, extended cloud budget),
provider disabling without deleting keys, HTTP 402/429 classification, and
the escalating quota circuit cooldown.
"""
import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services import ai_provider_order as apo
from app.services.ai_resilience_service import AIResilienceService
from app.services.ai_types import AIProvider, AIResult
from app.services.local_first import (
    CloudFallbackBudget,
    LocalFirstConfig,
    local_answer_problem,
    reset_cloud_fallback_budget,
)
from app.services.local_vlm_fallback import (
    LocalVLMConfig,
    LocalVLMFallbackService,
    RedescribeJob,
    reset_local_vlm_fallback_service,
)
from app.services.protect_ai_pipeline import ProtectAIPipeline, reset_protect_ai_pipeline
from app.services.snapshot_service import SnapshotResult
from app.services.vision_analysis_orchestrator import VisionAnalysisOrchestrator

PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def result(success=True, description="A person walks up the driveway.", ai_confidence=80, provider="local", error=None):
    return AIResult(
        description=description,
        confidence=ai_confidence or 0,
        objects_detected=["person"],
        provider=provider,
        tokens_used=10,
        response_time_ms=9000,
        cost_estimate=0.0,
        success=success,
        error=error,
        ai_confidence=ai_confidence,
    )


# --------------------------------------------------------------------------
# Usable-answer rules
# --------------------------------------------------------------------------

class TestLocalAnswerProblem:
    def test_good_answer_is_usable(self):
        assert local_answer_problem(result(), 50) is None

    def test_missing_confidence_is_not_low(self):
        assert local_answer_problem(result(ai_confidence=None), 50) is None

    @pytest.mark.parametrize(
        "answer, label",
        [
            (None, "no_result"),
            (result(success=False, description="", error="timeout"), "error"),
            (result(description="   "), "blank"),
            (result(ai_confidence=49), "low_confidence"),
        ],
    )
    def test_unusable_answers(self, answer, label):
        assert local_answer_problem(answer, 50) == label

    def test_confidence_at_threshold_is_usable(self):
        assert local_answer_problem(result(ai_confidence=50), 50) is None


# --------------------------------------------------------------------------
# Daily cloud fallback cap
# --------------------------------------------------------------------------

class TestCloudFallbackBudget:
    def test_cap_is_enforced(self):
        b = CloudFallbackBudget(2, today=lambda: date(2026, 10, 19))
        assert [b.try_acquire() for _ in range(3)] == [True, True, False]
        assert b.used == 2

    def test_zero_cap_never_allows_cloud(self):
        assert CloudFallbackBudget(0).try_acquire() is False

    def test_new_day_resets(self):
        day = {"d": date(2026, 10, 19)}
        b = CloudFallbackBudget(1, today=lambda: day["d"])
        assert b.try_acquire() is True
        assert b.try_acquire() is False
        day["d"] = date(2026, 10, 20)
        assert b.try_acquire() is True

    def test_seed_counts_toward_cap(self):
        b = CloudFallbackBudget(3, today=lambda: date(2026, 10, 19), seed=lambda d: 2)
        assert b.try_acquire() is True
        assert b.try_acquire() is False

    def test_failing_seed_starts_at_zero(self):
        def boom(_):
            raise RuntimeError("db down")

        b = CloudFallbackBudget(1, today=lambda: date(2026, 10, 19), seed=boom)
        assert b.try_acquire() is True


class TestLocalFirstConfig:
    def test_needs_local_vlm_enabled(self):
        fake = SimpleNamespace(AI_PRIMARY="local", LOCAL_VLM_ENABLED=False)
        with patch("app.core.config.settings", fake):
            assert LocalFirstConfig.from_settings().enabled is False

    def test_enabled_with_both(self):
        fake = SimpleNamespace(
            AI_PRIMARY="local", LOCAL_VLM_ENABLED=True, LOCAL_PRIMARY_MAX_WAIT_MS=90_000,
            LOCAL_PRIMARY_MIN_CONFIDENCE=60, CLOUD_FALLBACK_DAILY_CAP=7,
        )
        with patch("app.core.config.settings", fake):
            cfg = LocalFirstConfig.from_settings()
        assert (cfg.enabled, cfg.max_wait_ms, cfg.min_confidence, cfg.daily_cloud_cap) == (True, 90_000, 60, 7)

    def test_default_is_cloud(self):
        from app.core.config import Settings

        assert Settings.model_fields["AI_PRIMARY"].default == "cloud"


# --------------------------------------------------------------------------
# Live local call: queue wait + call budget
# --------------------------------------------------------------------------

def _service(provider):
    return LocalVLMFallbackService(
        config=LocalVLMConfig(enabled=True, timeout_ms=60_000),
        provider=provider,
        session_factory=MagicMock(),
    )


def _job():
    return RedescribeJob(event_id="live", image_base64=PNG_B64, camera_id="c", camera_name="Driveway", event_type="person")


class TestDescribeNow:
    @pytest.mark.asyncio
    async def test_returns_local_answer(self):
        provider = MagicMock()
        provider.generate_description = AsyncMock(return_value=result())
        svc = _service(provider)
        with patch.object(LocalVLMFallbackService, "build_prompt", return_value="p"):
            outcome = await svc.describe_now(_job(), max_wait_s=30)
        assert outcome.reason == "ok"
        assert outcome.result.description.startswith("A person")

    @pytest.mark.asyncio
    async def test_busy_when_slot_not_free_in_time(self):
        svc = _service(MagicMock())
        sem = svc._get_semaphore()
        await sem.acquire()
        try:
            outcome = await svc.describe_now(_job(), max_wait_s=0.05)
        finally:
            sem.release()
        assert outcome.result is None and outcome.reason == "busy"

    @pytest.mark.asyncio
    async def test_call_gets_only_remaining_budget(self):
        provider = MagicMock()
        provider.generate_description = AsyncMock(return_value=result())
        svc = _service(provider)
        with patch.object(LocalVLMFallbackService, "build_prompt", return_value="p"):
            await svc.describe_now(_job(), max_wait_s=20)
        timeout = provider.generate_description.call_args.kwargs["request_timeout_s"]
        assert 18 < timeout <= 20

    @pytest.mark.asyncio
    async def test_disabled_service_does_not_call(self):
        svc = LocalVLMFallbackService(config=LocalVLMConfig(enabled=False), provider=MagicMock())
        outcome = await svc.describe_now(_job(), max_wait_s=5)
        assert outcome.reason == "disabled"


# --------------------------------------------------------------------------
# Pipeline wiring
# --------------------------------------------------------------------------

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


def _local_first(enabled=True, cap=5):
    return LocalFirstConfig(enabled=enabled, max_wait_ms=120_000, min_confidence=50, daily_cloud_cap=cap)


async def _submit(pipeline, camera, snapshot, *, local, cloud, config):
    orch = MagicMock()
    orch.analyze_image = AsyncMock(return_value=cloud)
    service = MagicMock()
    service.describe_now = AsyncMock(return_value=local)
    with patch("app.services.vision_analysis_orchestrator.get_vision_analysis_orchestrator", return_value=orch), \
            patch("app.services.ai_service.ai_service") as ai, \
            patch("app.core.database.get_db_session"), \
            patch("app.services.local_first.LocalFirstConfig.from_settings", return_value=config), \
            patch("app.services.local_first._seed_from_db", return_value=0), \
            patch("app.services.local_vlm_fallback.get_local_vlm_fallback_service", return_value=service):
        ai.load_api_keys_from_db = AsyncMock()
        out = await pipeline.submit_snapshot_for_analysis(
            snapshot_result=snapshot, camera=camera, event_type="person", clip_path=None,
        )
    return out, orch, service


def _outcome(res, reason="ok"):
    from app.services.local_vlm_fallback import PrimaryOutcome

    return PrimaryOutcome(res, reason, 0.2)


class TestPipelineLocalFirst:
    @pytest.mark.asyncio
    async def test_usable_local_answer_skips_cloud(self, pipeline, camera, snapshot):
        out, orch, service = await _submit(
            pipeline, camera, snapshot, local=_outcome(result()), cloud=result(provider="grok"), config=_local_first()
        )
        assert out.provider == "local" and out.success
        orch.analyze_image.assert_not_called()
        assert service.describe_now.await_args.args[1] == 120.0
        assert pipeline._last_analysis_mode == "single_frame"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "local, reason",
        [
            (_outcome(result(description="")), "blank"),
            (_outcome(result(ai_confidence=20)), "low_confidence"),
            (_outcome(result(success=False, description="", error="timeout")), "error"),
            (_outcome(None, "busy"), "busy"),
        ],
    )
    async def test_unusable_local_answer_uses_cloud_with_extended_budget(self, pipeline, camera, snapshot, local, reason):
        out, orch, _ = await _submit(
            pipeline, camera, snapshot, local=local, cloud=result(provider="grok"), config=_local_first()
        )
        assert out.provider == "grok"
        assert orch.analyze_image.await_args.kwargs["extended_budget"] is True
        assert pipeline._last_fallback_reason == f"local_primary:{reason}"

    @pytest.mark.asyncio
    async def test_cap_reached_keeps_local_failure_and_skips_cloud(self, pipeline, camera, snapshot):
        out, orch, _ = await _submit(
            pipeline, camera, snapshot, local=_outcome(None, "busy"), cloud=result(provider="grok"),
            config=_local_first(cap=0),
        )
        orch.analyze_image.assert_not_called()
        assert out.success is False
        assert pipeline._last_fallback_reason == "local_primary:busy;cloud_cap_reached"

    @pytest.mark.asyncio
    async def test_cap_reached_keeps_low_confidence_local_answer(self, pipeline, camera, snapshot):
        out, orch, _ = await _submit(
            pipeline, camera, snapshot, local=_outcome(result(ai_confidence=30)), cloud=result(provider="grok"),
            config=_local_first(cap=0),
        )
        orch.analyze_image.assert_not_called()
        assert out.success and out.provider == "local" and out.ai_confidence == 30

    @pytest.mark.asyncio
    async def test_cap_reached_never_stores_a_blank_local_answer(self, pipeline, camera, snapshot):
        out, _, _ = await _submit(
            pipeline, camera, snapshot, local=_outcome(result(description="")), cloud=result(provider="grok"),
            config=_local_first(cap=0),
        )
        assert out.success is False

    @pytest.mark.asyncio
    async def test_cloud_primary_mode_is_unchanged(self, pipeline, camera, snapshot):
        out, orch, service = await _submit(
            pipeline, camera, snapshot, local=_outcome(result()), cloud=result(provider="grok"),
            config=_local_first(enabled=False),
        )
        assert out.provider == "grok"
        service.describe_now.assert_not_called()
        assert orch.analyze_image.await_args.kwargs["extended_budget"] is False

    @pytest.mark.asyncio
    async def test_context_bundle_restored_after_local_wait(self, pipeline, camera, snapshot):
        mine = SimpleNamespace(custom_prompt=None, local_timestamp=None)
        other = object()

        async def slow(*_a, **_k):
            # Another event ran through the singleton while this one waited.
            pipeline._last_context_bundle = other
            pipeline._last_frame_count = 9
            return _outcome(result())

        service = MagicMock()
        service.describe_now = slow
        with patch("app.services.ai_service.ai_service") as ai, \
                patch("app.core.database.get_db_session"), \
                patch("app.services.pre_ai_context_service.get_pre_ai_context_service") as ctx, \
                patch("app.services.local_first.LocalFirstConfig.from_settings", return_value=_local_first()), \
                patch("app.services.local_vlm_fallback.get_local_vlm_fallback_service", return_value=service):
            ai.load_api_keys_from_db = AsyncMock()
            ctx.return_value.gather = AsyncMock(return_value=mine)
            await pipeline.submit_snapshot_for_analysis(snapshot_result=snapshot, camera=camera, event_type="person")
        assert pipeline._last_context_bundle is mine
        assert pipeline._last_frame_count == 1


class TestHandlerSkipsBackgroundRedescribe:
    def test_no_background_job_in_local_first_mode(self):
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler.__new__(ProtectEventHandler)
        service = MagicMock(enabled=True)
        with patch("app.services.local_vlm_fallback.get_local_vlm_fallback_service", return_value=service), \
                patch("app.services.local_first.LocalFirstConfig.from_settings", return_value=_local_first()):
            handler._schedule_local_redescribe(SimpleNamespace(id="e1"), SimpleNamespace(image_base64=PNG_B64),
                                               SimpleNamespace(id="c", name="Driveway"), "person", None)
        service.schedule.assert_not_called()


# --------------------------------------------------------------------------
# Provider controls and circuit breaker
# --------------------------------------------------------------------------

class TestDisabledProviders:
    def test_parse_aliases_and_unknown(self):
        got = apo.parse_disabled_providers(" Claude, google ,openai, bogus,")
        assert got == {AIProvider.CLAUDE, AIProvider.GEMINI, AIProvider.OPENAI}

    def test_empty(self):
        assert apo.parse_disabled_providers("") == frozenset()

    def test_order_drops_disabled(self):
        with patch.object(apo, "disabled_providers", return_value=frozenset({AIProvider.CLAUDE, AIProvider.OPENAI})), \
                patch("app.core.database.get_db_session", side_effect=RuntimeError("no db")):
            order = apo.load_ai_provider_order()
        assert order == [AIProvider.GROK, AIProvider.GEMINI]


class TestErrorClassification:
    @pytest.mark.parametrize("err", ["Error code: 402 - payment required", "HTTP 402", "Payment Required"])
    def test_402_is_quota(self, err):
        assert apo.is_quota_error(err) is True
        assert apo.classify_provider_error(err) == "quota_exhausted"

    def test_plain_429_is_rate_limit_not_quota(self):
        assert apo.is_quota_error("Error code: 429 - rate limited") is False
        assert apo.classify_provider_error("Error code: 429 - rate limited") == "http_429"

    def test_bare_402_in_id_is_not_quota(self):
        assert apo.is_quota_error("request id 4021-abc failed") is False


def _resilience():
    svc = AIResilienceService.__new__(AIResilienceService)
    AIResilienceService.__init__(svc)
    breaker = MagicMock()
    breaker.state.value = "closed"
    breaker.get_state_value.return_value = 0
    svc.circuit_breakers = {"claude": breaker, "grok": breaker}
    return svc, breaker


class TestQuotaCooldown:
    def test_escalates_and_caps(self):
        svc, breaker = _resilience()
        fake = SimpleNamespace(AI_QUOTA_COOLDOWN_S=3600.0, AI_QUOTA_COOLDOWN_MAX_S=10_000.0, AI_RATE_LIMIT_COOLDOWN_S=300.0)
        with patch("app.core.config.settings", fake):
            for _ in range(4):
                svc.trip_quota("claude")
        cooldowns = [c.args[0] for c in breaker.force_open.call_args_list]
        assert cooldowns == [3600.0, 7200.0, 10_000.0, 10_000.0]

    def test_success_resets_escalation(self):
        svc, breaker = _resilience()
        fake = SimpleNamespace(AI_QUOTA_COOLDOWN_S=100.0, AI_QUOTA_COOLDOWN_MAX_S=1000.0, AI_RATE_LIMIT_COOLDOWN_S=30.0)
        with patch("app.core.config.settings", fake):
            svc.trip_quota("claude")
            svc.trip_quota("claude")
            svc.record_result("claude", True)
            svc.trip_quota("claude")
        assert [c.args[0] for c in breaker.force_open.call_args_list] == [100.0, 200.0, 100.0]

    def test_explicit_cooldown_still_honoured(self):
        svc, breaker = _resilience()
        svc.trip_quota("grok", cooldown_s=120)
        assert breaker.force_open.call_args.args[0] == 120

    def test_rate_limit_uses_its_own_cooldown(self):
        svc, breaker = _resilience()
        fake = SimpleNamespace(AI_QUOTA_COOLDOWN_S=3600.0, AI_QUOTA_COOLDOWN_MAX_S=21_600.0, AI_RATE_LIMIT_COOLDOWN_S=300.0)
        with patch("app.core.config.settings", fake):
            svc.trip_rate_limit("grok")
        assert breaker.force_open.call_args.args[0] == 300.0
        assert breaker.force_open.call_args.kwargs["reason"] == "rate_limited"


class TestOrchestratorBudgets:
    def _orch(self, **settings):
        defaults = dict(AI_SINGLE_IMAGE_SLA_MS=5000, AI_SINGLE_FIRST_CALL_MS=3000)
        defaults.update(settings)
        with patch("app.core.config.settings", SimpleNamespace(**defaults)):
            return VisionAnalysisOrchestrator.__wrapped__() if hasattr(VisionAnalysisOrchestrator, "__wrapped__") else VisionAnalysisOrchestrator()

    def test_single_image_caps_come_from_settings(self):
        orch = self._orch(AI_SINGLE_IMAGE_SLA_MS=9000, AI_SINGLE_FIRST_CALL_MS=7000)
        assert orch.default_single_image_sla_ms == 9000
        assert orch.max_first_single_ms == 7000

    def test_429_opens_rate_limit_circuit(self):
        orch = self._orch()
        orch.resilience_service = MagicMock()
        orch._record_provider_outcome("grok", result(success=False, description="", provider="grok", error="Error code: 429 - slow down"))
        orch.resilience_service.trip_rate_limit.assert_called_once_with("grok")
        orch.resilience_service.trip_quota.assert_not_called()

    @pytest.mark.asyncio
    async def test_extended_budget_gives_first_call_the_multi_frame_cap(self):
        import numpy as np

        orch = self._orch()
        orch.prompt_service = None
        provider = MagicMock()
        orch.providers = {AIProvider.GROK: provider}
        seen = {}

        async def run(name, timeout_ms, fn):
            seen["timeout_ms"] = timeout_ms
            return result(provider="grok")

        with patch.object(orch, "_get_provider_order", return_value=[AIProvider.GROK]), \
                patch.object(orch, "_run_with_deadline", side_effect=run), \
                patch.object(orch, "_preprocess_image", return_value="b64"), \
                patch.object(orch, "_track_usage"):
            await orch.analyze_image(np.zeros((4, 4, 3), dtype=np.uint8), "Driveway", extended_budget=True)
            extended = seen["timeout_ms"]
            await orch.analyze_image(np.zeros((4, 4, 3), dtype=np.uint8), "Driveway")
            live = seen["timeout_ms"]
        assert extended == orch.max_first_provider_ms
        assert live <= orch.max_first_single_ms
