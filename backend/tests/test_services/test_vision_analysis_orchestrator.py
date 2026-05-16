"""
Tests for VisionAnalysisOrchestrator (Phase 3.2 - ai_service decomposition)

Comprehensive tests with mocked providers, resilience service, and prompt service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

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
        # Small valid JPEG bytes (minimal header)
        fake_jpeg = b'\xff\xd8\xff\xe0' + b'\x00' * 100 + b'\xff\xd9'
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

        fake_images = [b'\xff\xd8\xff' + b'\x00' * 200 + b'\xff\xd9' for _ in range(3)]

        result = await orchestrator.analyze_images(fake_images, "Driveway")

        assert result.success is True
        assert "Multiple people" in result.description
        mock_resilience.record_result.assert_called()
