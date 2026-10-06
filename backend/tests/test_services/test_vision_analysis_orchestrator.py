"""
Tests for VisionAnalysisOrchestrator (Phase 3.2 - ai_service decomposition)

Comprehensive tests with mocked providers, resilience service, and prompt service.
"""

import asyncio
import io

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
from PIL import Image


def _make_jpeg_bytes(width: int = 16, height: int = 16) -> bytes:
    """Produce real, PIL-decodable JPEG bytes for preprocessing tests."""
    img = Image.new("RGB", (width, height), color=(120, 120, 120))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

from app.services.vision_analysis_orchestrator import (
    VisionAnalysisOrchestrator,
    get_vision_analysis_orchestrator,
    reset_vision_analysis_orchestrator,
)
from app.services.ai_service import AIProvider, AIResult
from app.services.ai_circuit_breaker import CircuitState


@pytest.fixture(autouse=True)
def _reset_vision_orchestrator_between_tests():
    """Ensure each test gets a clean VisionAnalysisOrchestrator instance (thanks to @singleton + reset)."""
    reset_vision_analysis_orchestrator()
    yield
    reset_vision_analysis_orchestrator()


class TestVisionAnalysisOrchestratorBasic:
    def test_initialization_with_dependencies(self):
        orchestrator = VisionAnalysisOrchestrator()
        assert orchestrator.providers == {}
        assert orchestrator.prompt_service is None
        assert orchestrator.resilience_service is None

    def test_set_providers_and_services(self):
        mock_prompt = MagicMock()
        mock_resilience = MagicMock()
        orchestrator = VisionAnalysisOrchestrator()

        orchestrator.set_providers({AIProvider.OPENAI: MagicMock()})
        orchestrator.set_prompt_service(mock_prompt)
        orchestrator.set_resilience_service(mock_resilience)

        assert AIProvider.OPENAI in orchestrator.providers
        assert orchestrator.prompt_service is mock_prompt
        assert orchestrator.resilience_service is mock_resilience

    def test_preprocess_image_basic(self):
        orchestrator = VisionAnalysisOrchestrator()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        result = orchestrator._preprocess_image(frame)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_preprocess_image_bytes_basic(self):
        orchestrator = VisionAnalysisOrchestrator()
        # Real, PIL-decodable JPEG bytes
        fake_jpeg = _make_jpeg_bytes()
        result = orchestrator._preprocess_image_bytes(fake_jpeg)
        assert isinstance(result, str)


class TestVisionAnalysisOrchestratorSingleImage:
    @pytest.mark.asyncio
    async def test_analyze_image_no_providers_returns_error(self):
        orchestrator = VisionAnalysisOrchestrator()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        result = await orchestrator.analyze_image(frame, "TestCam")

        assert result.success is False
        assert "No AI providers configured" in result.error

    @pytest.mark.asyncio
    async def test_analyze_image_success_with_mocked_provider(self):
        """Happy path with a successful provider."""
        mock_provider = AsyncMock()
        mock_provider.generate_description.return_value = AIResult(
            description="A person walking by",
            confidence=85,
            objects_detected=["person"],
            provider="openai",
            tokens_used=120,
            response_time_ms=800,
            cost_estimate=0.0012,
            success=True,
        )

        mock_resilience = MagicMock()
        mock_resilience.can_use_provider.return_value = True

        mock_prompt = MagicMock()
        mock_prompt.select_and_build_prompt.return_value = ("Describe the scene", None)

        orchestrator = VisionAnalysisOrchestrator(
            providers={AIProvider.OPENAI: mock_provider},
            prompt_service=mock_prompt,
            resilience_service=mock_resilience,
        )

        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        result = await orchestrator.analyze_image(frame, "FrontDoor", camera_id="cam-001")

        assert result.success is True
        assert "person walking" in result.description
        mock_resilience.record_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_image_sla_timeout(self):
        orchestrator = VisionAnalysisOrchestrator(
            providers={AIProvider.OPENAI: AsyncMock()},
        )
        frame = np.zeros((50, 50, 3), dtype=np.uint8)

        result = await orchestrator.analyze_image(frame, "TestCam", sla_timeout_ms=0)

        assert result.success is False
        assert "SLA timeout" in result.error


class TestVisionAnalysisOrchestratorMultiFrame:
    @pytest.mark.asyncio
    async def test_analyze_images_empty_list(self):
        orchestrator = VisionAnalysisOrchestrator()
        result = await orchestrator.analyze_images([], "TestCam")

        assert result.success is False
        assert "Empty image list" in result.error

    @pytest.mark.asyncio
    async def test_analyze_images_success_path(self):
        mock_provider = AsyncMock()
        mock_provider.generate_multi_image_description.return_value = AIResult(
            description="Multiple people arrived",
            confidence=78,
            objects_detected=["person", "person"],
            provider="grok",
            tokens_used=340,
            response_time_ms=2100,
            cost_estimate=0.0045,
            success=True,
        )

        mock_resilience = MagicMock()
        mock_resilience.can_use_provider.return_value = True

        orchestrator = VisionAnalysisOrchestrator(
            providers={AIProvider.GROK: mock_provider},
            resilience_service=mock_resilience,
        )

        fake_images = [_make_jpeg_bytes() for _ in range(3)]

        result = await orchestrator.analyze_images(fake_images, "Driveway")

        assert result.success is True
        assert "Multiple people" in result.description
        mock_resilience.record_result.assert_called()


def _failed_result(provider: str, error: str) -> AIResult:
    return AIResult(
        description="",
        confidence=0,
        objects_detected=[],
        provider=provider,
        tokens_used=0,
        response_time_ms=50,
        cost_estimate=0.0,
        success=False,
        error=error,
    )


def _ok_result(provider: str) -> AIResult:
    return AIResult(
        description=f"Described by {provider}",
        confidence=80,
        objects_detected=["person"],
        provider=provider,
        tokens_used=40,
        response_time_ms=100,
        cost_estimate=0.001,
        success=True,
    )


class TestProviderOrderFromSettings:
    """Orchestrator must honor ai_provider_order the same way AIService does."""

    @pytest.fixture
    def order_db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.core.database import Base
        from app.models.system_setting import SystemSetting  # noqa: F401 — register table

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()

    def _patch_db(self, order_db):
        return patch("app.core.database.SessionLocal", return_value=order_db)

    @pytest.mark.asyncio
    async def test_honors_stored_order_and_name_mapping(self, order_db, caplog):
        import json
        import logging

        from app.models.system_setting import SystemSetting

        caplog.set_level(logging.INFO)
        order_db.add(SystemSetting(
            key="ai_provider_order",
            value=json.dumps(["grok", "anthropic", "google", "openai"]),
        ))
        order_db.commit()

        called = []

        async def grok_call(*args, **kwargs):
            called.append("grok")
            return _failed_result("grok", "connection refused")

        async def openai_call(*args, **kwargs):
            called.append("openai")
            return _ok_result("openai")

        grok = AsyncMock()
        grok.generate_description = grok_call
        openai = AsyncMock()
        openai.generate_description = openai_call

        orchestrator = VisionAnalysisOrchestrator(providers={
            AIProvider.GROK: grok,
            AIProvider.OPENAI: openai,
        })
        frame = np.zeros((32, 32, 3), dtype=np.uint8)

        with self._patch_db(order_db):
            result = await orchestrator.analyze_image(frame, "Front Door")

        assert result.success is True
        assert result.provider == "openai"
        # anthropic -> claude, google -> gemini, and grok is tried before openai.
        assert called == ["grok", "openai"]
        assert "Using configured provider order: ['grok', 'claude', 'gemini', 'openai']" in caplog.text
        assert "claude not configured, skipping" in caplog.text
        assert "gemini not configured, skipping" in caplog.text

    @pytest.mark.asyncio
    async def test_missing_setting_uses_default_order(self, order_db, caplog):
        import logging

        caplog.set_level(logging.INFO)
        called = []

        async def openai_call(*args, **kwargs):
            called.append("openai")
            return _ok_result("openai")

        openai = AsyncMock()
        openai.generate_description = openai_call
        grok = AsyncMock()
        grok.generate_description = AsyncMock(return_value=_ok_result("grok"))

        orchestrator = VisionAnalysisOrchestrator(providers={
            AIProvider.OPENAI: openai,
            AIProvider.GROK: grok,
        })
        frame = np.zeros((32, 32, 3), dtype=np.uint8)

        with self._patch_db(order_db):
            result = await orchestrator.analyze_image(frame, "Front Door")

        assert result.success is True
        assert called == ["openai"]
        grok.generate_description.assert_not_called()
        assert "Using configured provider order: ['openai', 'grok', 'claude', 'gemini']" in caplog.text

    @pytest.mark.asyncio
    async def test_invalid_setting_falls_back_to_default(self, order_db, caplog):
        import logging

        from app.models.system_setting import SystemSetting

        caplog.set_level(logging.INFO)
        order_db.add(SystemSetting(key="ai_provider_order", value="not-valid-json"))
        order_db.commit()

        called = []

        async def openai_call(*args, **kwargs):
            called.append("openai")
            return _ok_result("openai")

        openai = AsyncMock()
        openai.generate_description = openai_call
        orchestrator = VisionAnalysisOrchestrator(providers={AIProvider.OPENAI: openai})
        frame = np.zeros((32, 32, 3), dtype=np.uint8)

        with self._patch_db(order_db):
            result = await orchestrator.analyze_image(frame, "Front Door")

        assert result.success is True
        assert called == ["openai"]
        assert "Invalid provider order in settings" in caplog.text
        assert "Using configured provider order: ['openai', 'grok', 'claude', 'gemini']" in caplog.text

    @pytest.mark.asyncio
    async def test_all_providers_fail_logs_failure_not_success(self, order_db, caplog):
        import json
        import logging

        from app.models.system_setting import SystemSetting

        caplog.set_level(logging.INFO)
        order_db.add(SystemSetting(
            key="ai_provider_order",
            value=json.dumps(["grok", "openai"]),
        ))
        order_db.commit()

        secret_payload = (
            "Error code: 429 - {'error': {'type': 'insufficient_quota', "
            "'message': 'sk-live-secret-key-do-not-log'}}"
        )
        grok = AsyncMock()
        grok.generate_multi_image_description = AsyncMock(
            return_value=_failed_result("grok", secret_payload)
        )
        openai = AsyncMock()
        openai.generate_multi_image_description = AsyncMock(
            return_value=_failed_result("openai", secret_payload)
        )
        orchestrator = VisionAnalysisOrchestrator(providers={
            AIProvider.GROK: grok,
            AIProvider.OPENAI: openai,
        })

        with self._patch_db(order_db):
            result = await orchestrator.analyze_images(
                [_make_jpeg_bytes(), _make_jpeg_bytes()],
                "Driveway",
            )

        assert result.success is False
        assert "quota_exhausted" in (result.error or "")
        assert "grok:quota_exhausted" in (result.error or "")
        assert "openai:quota_exhausted" in (result.error or "")
        assert "sk-live-secret" not in (result.error or "")
        assert "Vision analysis failed (multi_frame)" in caplog.text
        assert "grok:quota_exhausted" in caplog.text
        assert "openai:quota_exhausted" in caplog.text
        assert "sk-live-secret" not in caplog.text
        assert "Multi-frame analysis successful" not in caplog.text
        assert "Success with" not in caplog.text

    @pytest.mark.asyncio
    async def test_sla_abort_logs_failure_not_success(self, order_db, caplog):
        import logging

        caplog.set_level(logging.INFO)
        openai = AsyncMock()
        orchestrator = VisionAnalysisOrchestrator(providers={AIProvider.OPENAI: openai})
        frame = np.zeros((16, 16, 3), dtype=np.uint8)

        with self._patch_db(order_db):
            result = await orchestrator.analyze_image(frame, "Front Door", sla_timeout_ms=0)

        assert result.success is False
        assert "SLA timeout" in (result.error or "")
        assert "Vision analysis failed (single_image)" in caplog.text
        assert "Success with" not in caplog.text
        openai.generate_description.assert_not_called()


class TestProviderCallBudget:
    """Per-provider deadlines so one slow call cannot skip the fallback chain."""

    def test_default_multi_frame_budget_leaves_room_for_fallback(self, monkeypatch):
        monkeypatch.delenv("AI_MULTI_IMAGE_SLA_MS", raising=False)
        orchestrator = VisionAnalysisOrchestrator()
        assert orchestrator.default_multi_image_sla_ms == 25_000
        first = orchestrator.provider_call_timeout_ms(
            elapsed_ms=0,
            sla_timeout_ms=25_000,
            calls_started=0,
            multi=True,
        )
        assert first == 15_000
        fallback = orchestrator.provider_call_timeout_ms(
            elapsed_ms=first,
            sla_timeout_ms=25_000,
            calls_started=1,
            multi=True,
        )
        assert fallback == 10_000
        assert first + fallback == 25_000
        grace = orchestrator.provider_call_timeout_ms(
            elapsed_ms=25_000,
            sla_timeout_ms=25_000,
            calls_started=1,
            multi=True,
        )
        assert grace == 10_000
        assert orchestrator.provider_call_timeout_ms(
            elapsed_ms=25_000,
            sla_timeout_ms=25_000,
            calls_started=2,
            multi=True,
        ) is None

    def test_multi_frame_budget_is_configurable(self, monkeypatch):
        monkeypatch.setenv("AI_MULTI_IMAGE_SLA_MS", "30000")
        orchestrator = VisionAnalysisOrchestrator()
        assert orchestrator.default_multi_image_sla_ms == 30_000
        first = orchestrator.provider_call_timeout_ms(
            elapsed_ms=0,
            sla_timeout_ms=orchestrator.default_multi_image_sla_ms,
            calls_started=0,
            multi=True,
        )
        assert first == 15_000

    def test_invalid_budget_env_uses_default_without_logging_the_value(self, monkeypatch, caplog):
        import logging

        caplog.set_level(logging.WARNING)
        monkeypatch.setenv("AI_MULTI_IMAGE_SLA_MS", "sk-live-secret-key")
        orchestrator = VisionAnalysisOrchestrator()
        assert orchestrator.default_multi_image_sla_ms == 25_000
        assert "sk-live-secret" not in caplog.text
        assert "Ignoring invalid AI_MULTI_IMAGE_SLA_MS" in caplog.text


class TestFallbackChainDeadlines:
    """Issue #625: a slow or quota-failed first provider must not skip fallback."""

    @pytest.fixture
    def order_db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.core.database import Base
        from app.models.system_setting import SystemSetting  # noqa: F401

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()

    def _patch_db(self, order_db):
        return patch("app.core.database.SessionLocal", return_value=order_db)

    def _order(self, order_db, names):
        import json

        from app.models.system_setting import SystemSetting

        order_db.add(SystemSetting(key="ai_provider_order", value=json.dumps(names)))
        order_db.commit()

    @pytest.mark.asyncio
    async def test_first_provider_timeout_then_second_succeeds(self, order_db, caplog):
        import logging
        import time

        caplog.set_level(logging.INFO)
        self._order(order_db, ["grok", "anthropic"])

        async def grok_call(*args, **kwargs):
            await asyncio.sleep(5)
            return _ok_result("grok")

        async def claude_call(*args, **kwargs):
            return _ok_result("claude")

        grok = AsyncMock()
        grok.generate_multi_image_description = grok_call
        claude = AsyncMock()
        claude.generate_multi_image_description = claude_call
        orchestrator = VisionAnalysisOrchestrator(providers={
            AIProvider.GROK: grok,
            AIProvider.CLAUDE: claude,
        })
        orchestrator.min_provider_call_ms = 20
        orchestrator.max_first_provider_ms = 80
        orchestrator.fallback_reserve_ms = 80
        orchestrator.max_fallback_provider_ms = 500
        orchestrator.fallback_grace_ms = 500

        started = time.monotonic()
        with self._patch_db(order_db):
            result = await orchestrator.analyze_images(
                [_make_jpeg_bytes(), _make_jpeg_bytes()],
                "Front Door",
                sla_timeout_ms=25_000,
            )
        elapsed = time.monotonic() - started

        assert elapsed < 1.5
        assert result.success is True
        assert result.provider == "claude"
        assert result.response_time_ms == 100
        assert "grok timed out" in caplog.text
        assert "claude call finished" in caplog.text

    @pytest.mark.asyncio
    async def test_quota_429_is_not_retried_and_second_succeeds(self, order_db, caplog):
        import logging

        caplog.set_level(logging.INFO)
        self._order(order_db, ["grok", "anthropic"])
        calls = {"grok": 0}

        async def grok_call(*args, **kwargs):
            calls["grok"] += 1
            return _failed_result(
                "grok",
                "Error code: 429 - {'error': {'type': 'insufficient_quota', "
                "'message': 'You have no credits. sk-live-secret-key-do-not-log'}}",
            )

        async def claude_call(*args, **kwargs):
            return _ok_result("claude")

        grok = AsyncMock()
        grok.generate_multi_image_description = grok_call
        claude = AsyncMock()
        claude.generate_multi_image_description = claude_call
        resilience = MagicMock()
        resilience.can_use_provider.return_value = True
        orchestrator = VisionAnalysisOrchestrator(
            providers={AIProvider.GROK: grok, AIProvider.CLAUDE: claude},
            resilience_service=resilience,
        )

        with self._patch_db(order_db):
            result = await orchestrator.analyze_images(
                [_make_jpeg_bytes()],
                "Driveway",
            )

        assert calls["grok"] == 1
        assert result.success is True
        assert result.provider == "claude"
        assert result.response_time_ms == 100
        resilience.trip_quota.assert_called_once_with("grok")
        assert "grok failed (quota_exhausted)" in caplog.text
        assert "grok call finished" in caplog.text
        assert "claude call finished" in caplog.text
        assert "sk-live-secret" not in caplog.text
        assert "Vision analysis failed" not in caplog.text

    @pytest.mark.asyncio
    async def test_all_providers_fail_logs_failure_not_success(self, order_db, caplog):
        import logging

        caplog.set_level(logging.INFO)
        self._order(order_db, ["grok", "openai"])
        grok = AsyncMock()
        grok.generate_multi_image_description = AsyncMock(
            return_value=_failed_result("grok", "connection refused")
        )
        openai = AsyncMock()
        openai.generate_multi_image_description = AsyncMock(
            return_value=_failed_result("openai", "connection refused")
        )
        orchestrator = VisionAnalysisOrchestrator(providers={
            AIProvider.GROK: grok,
            AIProvider.OPENAI: openai,
        })

        with self._patch_db(order_db):
            result = await orchestrator.analyze_images(
                [_make_jpeg_bytes()],
                "Driveway",
            )

        assert result.success is False
        assert "Vision analysis failed (multi_frame)" in caplog.text
        assert "grok call finished" in caplog.text
        assert "openai call finished" in caplog.text
        assert "Success with" not in caplog.text
        assert grok.generate_multi_image_description.await_count == 1
        assert openai.generate_multi_image_description.await_count == 1


class TestManualReanalysisBudget:
    """Re-analyze uses the live 15s provider cap inside a 45s manual deadline."""

    @pytest.fixture
    def order_db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.core.database import Base
        from app.models.system_setting import SystemSetting  # noqa: F401

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()

    def _patch_db(self, order_db):
        return patch("app.core.database.SessionLocal", return_value=order_db)

    def _order(self, order_db, names):
        import json

        from app.models.system_setting import SystemSetting

        order_db.add(SystemSetting(key="ai_provider_order", value=json.dumps(names)))
        order_db.commit()

    def test_live_pipeline_limits_are_unchanged(self, monkeypatch):
        from app.services.vision_analysis_orchestrator import (
            DEFAULT_MULTI_IMAGE_SLA_MS,
            DEFAULT_SINGLE_IMAGE_SLA_MS,
            MANUAL_ANALYSIS_SLA_MS,
            MAX_FIRST_PROVIDER_MS,
            MAX_FIRST_SINGLE_MS,
        )

        monkeypatch.delenv("AI_MULTI_IMAGE_SLA_MS", raising=False)
        orchestrator = VisionAnalysisOrchestrator()
        assert orchestrator.default_single_image_sla_ms == DEFAULT_SINGLE_IMAGE_SLA_MS == 5_000
        assert orchestrator.default_multi_image_sla_ms == DEFAULT_MULTI_IMAGE_SLA_MS == 25_000
        assert orchestrator.max_first_provider_ms == MAX_FIRST_PROVIDER_MS == 15_000
        assert orchestrator.max_first_single_ms == MAX_FIRST_SINGLE_MS == 3_000
        live_single = orchestrator.provider_call_timeout_ms(
            elapsed_ms=0,
            sla_timeout_ms=orchestrator.default_single_image_sla_ms,
            calls_started=0,
            multi=False,
        )
        live_multi = orchestrator.provider_call_timeout_ms(
            elapsed_ms=0,
            sla_timeout_ms=orchestrator.default_multi_image_sla_ms,
            calls_started=0,
            multi=True,
        )
        assert live_single == 3_000
        assert live_multi == 15_000
        assert MANUAL_ANALYSIS_SLA_MS == 45_000

    @pytest.mark.asyncio
    async def test_user_initiated_single_image_gives_full_provider_budget(self, order_db):
        self._order(order_db, ["grok"])
        seen = {}

        async def grok_call(*args, **kwargs):
            seen["timeout_s"] = kwargs.get("request_timeout_s")
            return _ok_result("grok")

        grok = AsyncMock()
        grok.generate_description = grok_call
        orchestrator = VisionAnalysisOrchestrator(providers={AIProvider.GROK: grok})
        frame = np.zeros((16, 16, 3), dtype=np.uint8)

        with self._patch_db(order_db):
            result = await orchestrator.analyze_image(
                frame, "Front Door", user_initiated=True
            )

        assert result.success is True
        assert result.provider == "grok"
        assert seen["timeout_s"] >= 14

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_user_initiated_provider_taking_about_ten_seconds_succeeds(self, order_db):
        """A ~10s Grok call fits the manual budget and is not cancelled at 3s."""
        import time

        self._order(order_db, ["grok"])

        async def grok_call(*args, **kwargs):
            assert kwargs.get("request_timeout_s", 0) >= 10
            await asyncio.sleep(10)
            return _ok_result("grok")

        grok = AsyncMock()
        grok.generate_description = grok_call
        orchestrator = VisionAnalysisOrchestrator(providers={AIProvider.GROK: grok})
        frame = np.zeros((16, 16, 3), dtype=np.uint8)

        started = time.monotonic()
        with self._patch_db(order_db):
            result = await orchestrator.analyze_image(
                frame, "Front Door", user_initiated=True
            )
        elapsed = time.monotonic() - started

        assert result.success is True
        assert result.provider == "grok"
        assert elapsed >= 9
        assert elapsed < 14

    @pytest.mark.asyncio
    async def test_quota_exhausted_is_skipped_and_next_provider_is_tried(
        self, order_db, caplog
    ):
        """Quota does not spend the fallback slot, so a later provider still runs."""
        import logging
        import time

        caplog.set_level(logging.INFO)
        self._order(order_db, ["grok", "anthropic", "google"])
        calls = []

        async def grok_call(*args, **kwargs):
            calls.append("grok")
            await asyncio.sleep(5)
            return _ok_result("grok")

        async def claude_call(*args, **kwargs):
            calls.append("claude")
            return _failed_result(
                "claude",
                "You have no credits. sk-live-secret-DO-NOT-LEAK",
            )

        async def gemini_call(*args, **kwargs):
            calls.append("gemini")
            return _ok_result("gemini")

        grok = AsyncMock()
        grok.generate_description = grok_call
        claude = AsyncMock()
        claude.generate_description = claude_call
        gemini = AsyncMock()
        gemini.generate_description = gemini_call
        resilience = MagicMock()
        resilience.can_use_provider.return_value = True
        orchestrator = VisionAnalysisOrchestrator(
            providers={
                AIProvider.GROK: grok,
                AIProvider.CLAUDE: claude,
                AIProvider.GEMINI: gemini,
            },
            resilience_service=resilience,
        )
        # Tight live single-image budget: after one real timeout, a second
        # consuming failure would leave too little time for a third call.
        orchestrator.min_provider_call_ms = 100
        orchestrator.max_first_single_ms = 50
        orchestrator.max_fallback_single_ms = 50
        orchestrator.single_fallback_reserve_ms = 0
        orchestrator.single_fallback_grace_ms = 50
        frame = np.zeros((16, 16, 3), dtype=np.uint8)

        started = time.monotonic()
        with self._patch_db(order_db):
            result = await orchestrator.analyze_image(
                frame, "Front Door", sla_timeout_ms=120
            )
        elapsed = time.monotonic() - started

        assert elapsed < 1.5
        assert calls == ["grok", "claude", "gemini"]
        assert result.success is True
        assert result.provider == "gemini"
        resilience.trip_quota.assert_called_once_with("claude")
        assert "sk-live-secret" not in (result.error or "")
        assert "sk-live-secret" not in caplog.text

    @pytest.mark.asyncio
    async def test_auth_error_does_not_consume_budget(self, order_db):
        self._order(order_db, ["grok", "openai"])
        calls = []

        async def grok_call(*args, **kwargs):
            calls.append("grok")
            return _failed_result("grok", "invalid api key")

        async def openai_call(*args, **kwargs):
            calls.append("openai")
            return _ok_result("openai")

        grok = AsyncMock()
        grok.generate_description = grok_call
        openai = AsyncMock()
        openai.generate_description = openai_call
        resilience = MagicMock()
        resilience.can_use_provider.return_value = True
        orchestrator = VisionAnalysisOrchestrator(
            providers={AIProvider.GROK: grok, AIProvider.OPENAI: openai},
            resilience_service=resilience,
        )
        frame = np.zeros((16, 16, 3), dtype=np.uint8)

        with self._patch_db(order_db):
            result = await orchestrator.analyze_image(frame, "Front Door")

        assert calls == ["grok", "openai"]
        assert result.success is True
        assert result.provider == "openai"
        resilience.trip_quota.assert_called_once_with("grok", reason="auth_error")

    @pytest.mark.asyncio
    async def test_insufficient_budget_message_when_time_remains(self, order_db):
        self._order(order_db, ["grok", "anthropic", "google"])

        async def slow(*args, **kwargs):
            await asyncio.sleep(5)
            return _ok_result("unused")

        grok = AsyncMock()
        grok.generate_description = AsyncMock(side_effect=slow)
        claude = AsyncMock()
        claude.generate_description = AsyncMock(side_effect=slow)
        gemini = AsyncMock()
        gemini.generate_description = AsyncMock(side_effect=slow)
        orchestrator = VisionAnalysisOrchestrator(providers={
            AIProvider.GROK: grok,
            AIProvider.CLAUDE: claude,
            AIProvider.GEMINI: gemini,
        })
        orchestrator.min_provider_call_ms = 470
        orchestrator.max_first_single_ms = 40
        orchestrator.max_fallback_single_ms = 40
        orchestrator.single_fallback_reserve_ms = 0
        orchestrator.single_fallback_grace_ms = 40
        frame = np.zeros((16, 16, 3), dtype=np.uint8)

        with self._patch_db(order_db):
            result = await orchestrator.analyze_image(
                frame, "Front Door", sla_timeout_ms=500
            )

        assert result.success is False
        assert "insufficient remaining budget" in (result.error or "")
        assert "ms left" in (result.error or "")
        assert "SLA timeout" not in (result.error or "")
        assert ">" not in (result.error or "")
        assert gemini.generate_description.await_count == 0
        assert grok.generate_description.await_count == 1
        assert claude.generate_description.await_count == 1
