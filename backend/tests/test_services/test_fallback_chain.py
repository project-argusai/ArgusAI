"""
Unit tests for the AI Fallback Chain (originally Story P3-3.5).

REWRITE NOTE (post Phase-4 / #443-#450 decomposition):
    The fallback/orchestration logic was extracted out of ``ProtectEventHandler``
    into the new ``ProtectAIPipeline`` service (``app/services/protect_ai_pipeline.py``).
    During that extraction the contract changed substantially:

      * ``ProtectEventHandler._submit_to_ai_pipeline`` -> ``ProtectAIPipeline.submit_snapshot_for_analysis``
      * The granular ``self._fallback_chain`` *list* (with strings like
        ``"multi_frame:no_clip_available"``) was replaced by a single
        ``self._last_fallback_reason`` *string* (e.g. ``"video_native_failed:<err>"``).
      * The named private methods the old tests patched
        (``_single_frame_analysis``, ``_try_multi_frame_analysis``,
        ``_try_video_native_upload``, ``_try_video_frame_extraction``,
        ``_store_event_without_ai``) no longer exist. The current pipeline exposes
        ``submit_snapshot_for_analysis``, ``_try_video_native_analysis`` and
        ``_extract_frames_from_clip``; mode is tracked via ``_last_analysis_mode``.
      * Non-Protect-camera special casing and the ``no_clip_source`` /
        ``no_clip_available`` / ``frame_extraction_failed`` reason vocabulary were
        dropped from the implementation.

    These tests are repointed at ``ProtectAIPipeline`` and assert the contract that
    actually exists today. Tests whose behaviour no longer exists in source were
    removed (each removal documented in ``REMOVED_TESTS`` below) rather than faked
    green. The current source carries an explicit
    ``TODO: Full extraction of the fallback chain`` note — when that richer
    contract is re-implemented these tests should be expanded accordingly.

REMOVED_TESTS (behaviour genuinely gone from source — not a relocation):
    - TestNonProtectCameras / TestNonProtectCameraFallbackReason:
        ProtectAIPipeline no longer branches on ``camera.source_type``; the
        ``video_native:no_clip_source`` / ``multi_frame:no_clip_source`` reasons
        do not exist anywhere in app/.
    - TestStoreEventWithoutAI::test_store_event_without_ai_sets_description:
        ``_store_event_without_ai`` was removed entirely (no replacement in app/).
    - The ``_fallback_chain`` list-contract assertions
        (``multi_frame:no_clip_available``, ``multi_frame:frame_extraction_failed``,
        ``single_frame:ai_failed``, ``video_native:timeout``,
        ``video_native:exception:ValueError``, ``describe_video_failed``):
        the list and those reason strings were replaced by a single
        ``_last_fallback_reason`` string with different vocabulary.
    - The dedicated ``_try_video_native_upload`` / ``_try_video_frame_extraction``
        provider-plumbing tests: those methods were collapsed into the single
        ``_try_video_native_analysis`` method, which is covered below.
"""
import asyncio
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.protect_ai_pipeline import (
    ProtectAIPipeline,
    reset_protect_ai_pipeline,
)
from app.services.snapshot_service import SnapshotResult


# 1x1 PNG (valid, decodable by Pillow) used for the single-frame path.
_VALID_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@dataclass
class MockAIResult:
    """Mock AIResult for testing."""

    success: bool
    description: str = "Test description"
    error: str = None
    provider: str = "openai"
    confidence: int = 85
    response_time_ms: int = 500
    objects_detected: list = None
    tokens_used: int = 100

    def __post_init__(self):
        if self.objects_detected is None:
            self.objects_detected = ["person"]


@pytest.fixture
def pipeline():
    """Create a fresh ProtectAIPipeline (singleton) instance for testing."""
    reset_protect_ai_pipeline()
    return ProtectAIPipeline()


@pytest.fixture
def mock_camera_protect():
    """Create a mock Protect camera with configurable analysis_mode."""
    camera = Mock()
    camera.id = "camera-123"
    camera.name = "Test Camera"
    camera.source_type = "protect"
    camera.analysis_mode = "single_frame"
    camera.protect_camera_id = "protect-abc"
    return camera


@pytest.fixture
def mock_snapshot_result():
    """Create a mock SnapshotResult with a decodable image."""
    return SnapshotResult(
        image_base64=_VALID_PNG_B64,
        thumbnail_path="/tmp/test_thumb.jpg",
        width=1920,
        height=1080,
        camera_id="camera-123",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def temp_clip_file():
    """Create a temporary clip file that actually exists."""
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    yield Path(path)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _patch_pipeline_deps(orchestrator):
    """
    Context-manager bundle that patches the lazily-imported dependencies of
    ``submit_snapshot_for_analysis``: the orchestrator getter, the ai_service
    key loader, and the db session.

    Returns a list of started patchers' context managers to be used in a
    contextlib.ExitStack-free nested ``with`` -- here we just return the three
    patch objects so callers can enter them.
    """
    return (
        patch(
            "app.services.vision_analysis_orchestrator.get_vision_analysis_orchestrator",
            return_value=orchestrator,
        ),
        patch("app.services.ai_service.ai_service"),
        patch("app.core.database.get_db_session"),
    )


class TestSingleFramePath:
    """No clip available -> single_frame analysis (the base path)."""

    @pytest.mark.asyncio
    async def test_no_clip_uses_single_frame(
        self, pipeline, mock_camera_protect, mock_snapshot_result
    ):
        orch = MagicMock()
        orch.analyze_image = AsyncMock(
            return_value=MockAIResult(success=True, description="single frame")
        )

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db:
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=mock_camera_protect,
                event_type="person",
                clip_path=None,
            )

        assert result is not None
        assert result.success is True
        orch.analyze_image.assert_called_once()
        assert pipeline._last_analysis_mode == "single_frame"
        assert pipeline._last_frame_count == 1


class TestFallbackChainVideoNative:
    """video_native -> (multi_frame) -> single_frame fallthrough (AC1)."""

    @pytest.mark.asyncio
    async def test_video_native_falls_back_to_single_frame(
        self, pipeline, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """AC1: video_native returns None and frames extraction yields nothing,
        so the pipeline falls all the way through to single_frame."""
        mock_camera_protect.analysis_mode = "video_native"

        orch = MagicMock()
        orch.analyze_image = AsyncMock(
            return_value=MockAIResult(success=True, description="single frame success")
        )

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db, patch.object(
            pipeline, "_try_video_native_analysis", new_callable=AsyncMock, return_value=None
        ) as mock_video, patch.object(
            pipeline,
            "_extract_frames_from_clip",
            new_callable=AsyncMock,
            return_value=([], []),
        ) as mock_extract:
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=mock_camera_protect,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=temp_clip_file,
            )

        assert result is not None
        assert result.success is True
        mock_video.assert_called_once()
        mock_extract.assert_called_once()
        orch.analyze_image.assert_called_once()
        assert pipeline._last_analysis_mode == "single_frame"

    @pytest.mark.asyncio
    async def test_video_native_exception_records_fallback_reason(
        self, pipeline, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """AC1, AC4: when video_native raises, the failure reason is recorded
        on ``_last_fallback_reason`` and the pipeline still completes via
        single_frame."""
        mock_camera_protect.analysis_mode = "video_native"

        async def boom(*args, **kwargs):
            raise ValueError("provider unavailable")

        orch = MagicMock()
        orch.analyze_image = AsyncMock(return_value=MockAIResult(success=True))

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db, patch.object(
            pipeline, "_try_video_native_analysis", boom
        ), patch.object(
            pipeline,
            "_extract_frames_from_clip",
            new_callable=AsyncMock,
            return_value=([], []),
        ):
            mock_ai.load_api_keys_from_db = AsyncMock()
            await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=mock_camera_protect,
                event_type="person",
                clip_path=temp_clip_file,
            )

        assert pipeline._last_fallback_reason is not None
        assert pipeline._last_fallback_reason.startswith("video_native_failed:")


class TestMultiFramePath:
    """Clip present + frames extracted -> multi_frame analysis (AC2)."""

    @pytest.mark.asyncio
    async def test_clip_with_frames_uses_multi_frame(
        self, pipeline, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        orch = MagicMock()
        orch.analyze_images = AsyncMock(
            return_value=MockAIResult(success=True, description="multi frame")
        )
        orch.analyze_image = AsyncMock(
            return_value=MockAIResult(success=True, description="single frame")
        )

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db, patch.object(
            pipeline, "_try_video_native_analysis", new_callable=AsyncMock, return_value=None
        ), patch.object(
            pipeline,
            "_extract_frames_from_clip",
            new_callable=AsyncMock,
            return_value=([b"f1", b"f2", b"f3"], [0.0, 0.5, 1.0]),
        ):
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=mock_camera_protect,
                event_type="person",
                clip_path=temp_clip_file,
            )

        assert result is not None
        assert result.success is True
        orch.analyze_images.assert_called_once()
        orch.analyze_image.assert_not_called()
        assert pipeline._last_analysis_mode == "multi_frame"
        assert pipeline._last_frame_count == 3

    @pytest.mark.asyncio
    async def test_multi_frame_no_frames_falls_back_to_single_frame(
        self, pipeline, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """AC2: clip present but frame extraction returns nothing -> single_frame."""
        orch = MagicMock()
        orch.analyze_images = AsyncMock(return_value=MockAIResult(success=True))
        orch.analyze_image = AsyncMock(
            return_value=MockAIResult(success=True, description="single fallback")
        )

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db, patch.object(
            pipeline, "_try_video_native_analysis", new_callable=AsyncMock, return_value=None
        ), patch.object(
            pipeline,
            "_extract_frames_from_clip",
            new_callable=AsyncMock,
            return_value=([], []),
        ):
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=mock_camera_protect,
                event_type="person",
                clip_path=temp_clip_file,
            )

        assert result is not None
        orch.analyze_images.assert_not_called()
        orch.analyze_image.assert_called_once()
        assert pipeline._last_analysis_mode == "single_frame"


class TestCompleteFailure:
    """All paths raise -> submit returns None and records an exception reason (AC3)."""

    @pytest.mark.asyncio
    async def test_all_modes_fail_returns_none(
        self, pipeline, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        mock_camera_protect.analysis_mode = "video_native"

        orch = MagicMock()
        # single-frame path raises so the whole submit fails
        orch.analyze_image = AsyncMock(side_effect=RuntimeError("ai down"))

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db, patch.object(
            pipeline, "_try_video_native_analysis", new_callable=AsyncMock, return_value=None
        ), patch.object(
            pipeline,
            "_extract_frames_from_clip",
            new_callable=AsyncMock,
            return_value=([], []),
        ):
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=mock_camera_protect,
                event_type="person",
                clip_path=temp_clip_file,
            )

        assert result is None
        assert pipeline._last_fallback_reason is not None
        assert pipeline._last_fallback_reason.startswith("exception:")


class TestAnalysisModeTracking:
    """analysis_mode reflects the actual mode used (AC4)."""

    @pytest.mark.asyncio
    async def test_successful_video_native_sets_mode(
        self, pipeline, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        mock_camera_protect.analysis_mode = "video_native"
        orch = MagicMock()

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db, patch.object(
            pipeline,
            "_try_video_native_analysis",
            new_callable=AsyncMock,
            return_value=MockAIResult(success=True, provider="gemini"),
        ):
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=mock_camera_protect,
                event_type="person",
                clip_path=temp_clip_file,
            )

        assert result is not None
        assert pipeline._last_analysis_mode == "video_native"
        # AC: video native uses the whole clip, so frame_count is null.
        assert pipeline._last_frame_count is None

    @pytest.mark.asyncio
    async def test_property_accessors_expose_tracking_state(
        self, pipeline, mock_camera_protect, mock_snapshot_result
    ):
        orch = MagicMock()
        orch.analyze_image = AsyncMock(return_value=MockAIResult(success=True))

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db:
            mock_ai.load_api_keys_from_db = AsyncMock()
            await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=mock_camera_protect,
                event_type="person",
                clip_path=None,
            )

        assert pipeline.last_analysis_mode == "single_frame"
        assert pipeline.last_frame_count == 1
        assert pipeline.last_fallback_reason == pipeline._last_fallback_reason


class TestVideoNativeMethod:
    """Directly exercise ``_try_video_native_analysis`` (the surviving video method)."""

    def _provider_map(self, *, has_gemini=True, success=True, raises=False):
        if not has_gemini:
            return {}
        enum = MagicMock()
        enum.value = "gemini"
        provider = MagicMock()
        if raises:
            async def describe_video(*args, **kwargs):
                raise RuntimeError("network error")

            provider.describe_video = describe_video
        else:
            provider.describe_video = AsyncMock(
                return_value=MockAIResult(success=success, provider="gemini")
            )
        return {enum: provider}

    @pytest.mark.asyncio
    async def test_no_video_provider_returns_none(
        self, pipeline, mock_camera_protect, temp_clip_file
    ):
        with patch.object(pipeline, "_get_providers", return_value=self._provider_map(has_gemini=False)):
            result = await pipeline._try_video_native_analysis(
                clip_path=temp_clip_file,
                camera=mock_camera_protect,
                event_type="person",
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_gemini_success_returns_result(
        self, pipeline, mock_camera_protect, temp_clip_file
    ):
        with patch.object(pipeline, "_get_providers", return_value=self._provider_map(success=True)):
            result = await pipeline._try_video_native_analysis(
                clip_path=temp_clip_file,
                camera=mock_camera_protect,
                event_type="person",
            )
        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_gemini_failure_result_returns_none(
        self, pipeline, mock_camera_protect, temp_clip_file
    ):
        with patch.object(pipeline, "_get_providers", return_value=self._provider_map(success=False)):
            result = await pipeline._try_video_native_analysis(
                clip_path=temp_clip_file,
                camera=mock_camera_protect,
                event_type="person",
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_gemini_exception_returns_none(
        self, pipeline, mock_camera_protect, temp_clip_file
    ):
        with patch.object(pipeline, "_get_providers", return_value=self._provider_map(raises=True)):
            result = await pipeline._try_video_native_analysis(
                clip_path=temp_clip_file,
                camera=mock_camera_protect,
                event_type="person",
            )
        assert result is None
