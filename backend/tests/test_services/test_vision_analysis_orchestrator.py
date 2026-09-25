"""
Tests for VisionAnalysisOrchestrator (Phase 3.2 - ai_service decomposition)

Comprehensive tests with mocked providers, resilience service, and prompt service.
"""

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
