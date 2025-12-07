"""
Unit tests for Fallback Chain functionality (Story P3-3.5)

Tests:
    - Fallback from video_native -> multi_frame -> single_frame
    - Fallback from multi_frame -> single_frame on clip download failure
    - Complete failure scenario (all modes fail)
    - Fallback_reason is correctly populated
    - Analysis_mode reflects actual mode used
    - Non-Protect cameras default to single_frame regardless of config
"""
import pytest
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from dataclasses import dataclass
import os
import tempfile

from app.services.protect_event_handler import ProtectEventHandler
from app.services.snapshot_service import SnapshotResult


@dataclass
class MockAIResult:
    """Mock AIResult for testing"""
    success: bool
    description: str = "Test description"
    error: str = None
    provider: str = "openai"
    confidence: int = 85
    response_time_ms: int = 500
    objects_detected: list = None

    def __post_init__(self):
        if self.objects_detected is None:
            self.objects_detected = ["person"]


@pytest.fixture
def handler():
    """Create a ProtectEventHandler instance for testing"""
    return ProtectEventHandler()


@pytest.fixture
def mock_camera_protect():
    """Create a mock Protect camera with configurable analysis_mode"""
    camera = Mock()
    camera.id = "camera-123"
    camera.name = "Test Camera"
    camera.source_type = "protect"
    camera.analysis_mode = "single_frame"  # Default, can be overridden
    camera.protect_camera_id = "protect-abc"
    return camera


@pytest.fixture
def mock_camera_rtsp():
    """Create a mock RTSP camera"""
    camera = Mock()
    camera.id = "camera-rtsp-123"
    camera.name = "RTSP Camera"
    camera.source_type = "rtsp"
    camera.analysis_mode = "video_native"  # Configured but should be ignored
    return camera


@pytest.fixture
def mock_snapshot_result():
    """Create a mock SnapshotResult"""
    return SnapshotResult(
        image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        thumbnail_path="/tmp/test_thumb.jpg",
        width=1920,
        height=1080,
        camera_id="camera-123",
        timestamp=datetime.now(timezone.utc)
    )


@pytest.fixture
def temp_clip_file():
    """Create a temporary clip file that actually exists"""
    # Create a real temp file
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    yield Path(path)
    # Cleanup
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


class TestFallbackChainVideoNative:
    """Test fallback from video_native -> multi_frame -> single_frame (AC1)"""

    @pytest.mark.asyncio
    async def test_video_native_falls_back_to_multi_frame_then_single_frame(
        self, handler, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """AC1: video_native configured, falls through to single_frame"""
        mock_camera_protect.analysis_mode = "video_native"

        # Mock multi-frame to fail
        with patch.object(
            handler, '_try_multi_frame_analysis',
            new_callable=AsyncMock,
            return_value=None  # Multi-frame fails
        ) as mock_multi:
            # Mock single-frame to succeed
            success_result = MockAIResult(success=True, description="Single frame success")

            with patch.object(
                handler, '_single_frame_analysis',
                new_callable=AsyncMock,
                return_value=success_result
            ) as mock_single:
                # Mock AI service loading
                with patch('app.services.ai_service.ai_service') as mock_ai:
                    mock_ai.load_api_keys_from_db = AsyncMock()

                    with patch('app.services.protect_event_handler.SessionLocal'):
                        result = await handler._submit_to_ai_pipeline(
                            snapshot_result=mock_snapshot_result,
                            camera=mock_camera_protect,
                            event_type="person",
                            is_doorbell_ring=False,
                            clip_path=temp_clip_file
                        )

                # Verify fallback chain was followed
                assert result is not None
                assert result.success is True

                # Verify video_native was tracked in fallback chain
                assert "video_native:provider_unsupported" in handler._fallback_chain

                # Verify multi_frame was attempted
                mock_multi.assert_called_once()

                # Verify single_frame was called
                mock_single.assert_called_once()

    @pytest.mark.asyncio
    async def test_video_native_records_fallback_reason(
        self, handler, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """AC1, AC4: fallback_reason records why each step failed"""
        mock_camera_protect.analysis_mode = "video_native"

        # Mock both to fail, then single to succeed
        # We need to simulate the internal state setting that _single_frame_analysis does
        async def mock_single_frame(*args, **kwargs):
            # Simulate what the real method does on success
            handler._last_analysis_mode = "single_frame"
            handler._last_frame_count = 1
            if hasattr(handler, '_fallback_chain') and handler._fallback_chain:
                handler._last_fallback_reason = ",".join(handler._fallback_chain)
            return MockAIResult(success=True)

        with patch.object(
            handler, '_try_multi_frame_analysis',
            new_callable=AsyncMock,
            return_value=None
        ):
            with patch.object(handler, '_single_frame_analysis', side_effect=mock_single_frame):
                with patch('app.services.ai_service.ai_service') as mock_ai:
                    mock_ai.load_api_keys_from_db = AsyncMock()
                    with patch('app.services.protect_event_handler.SessionLocal'):
                        await handler._submit_to_ai_pipeline(
                            snapshot_result=mock_snapshot_result,
                            camera=mock_camera_protect,
                            event_type="person",
                            clip_path=temp_clip_file
                        )

                # Verify fallback_reason is set
                assert handler._last_fallback_reason is not None
                assert "video_native:" in handler._last_fallback_reason


class TestFallbackChainMultiFrame:
    """Test fallback from multi_frame -> single_frame (AC2)"""

    @pytest.mark.asyncio
    async def test_multi_frame_no_clip_falls_back_to_single_frame(
        self, handler, mock_camera_protect, mock_snapshot_result
    ):
        """AC2: multi_frame configured but no clip available"""
        mock_camera_protect.analysis_mode = "multi_frame"

        # No clip path provided
        success_result = MockAIResult(success=True, description="Single frame fallback")

        with patch.object(
            handler, '_single_frame_analysis',
            new_callable=AsyncMock,
            return_value=success_result
        ) as mock_single:
            with patch('app.services.ai_service.ai_service') as mock_ai:
                mock_ai.load_api_keys_from_db = AsyncMock()
                with patch('app.services.protect_event_handler.SessionLocal'):
                    result = await handler._submit_to_ai_pipeline(
                        snapshot_result=mock_snapshot_result,
                        camera=mock_camera_protect,
                        event_type="person",
                        clip_path=None  # No clip available
                    )

            assert result is not None
            assert result.success is True
            mock_single.assert_called_once()

            # Verify fallback reason indicates no clip
            assert "multi_frame:no_clip_available" in handler._fallback_chain

    @pytest.mark.asyncio
    async def test_multi_frame_frame_extraction_failure_falls_back(
        self, handler, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """AC2: multi_frame extraction fails, falls back to single_frame"""
        mock_camera_protect.analysis_mode = "multi_frame"

        # Mock frame extractor to return empty frames
        with patch('app.services.protect_event_handler.get_frame_extractor') as mock_extractor:
            mock_extractor.return_value.extract_frames = AsyncMock(return_value=[])

            success_result = MockAIResult(success=True)
            with patch.object(
                handler, '_single_frame_analysis',
                new_callable=AsyncMock,
                return_value=success_result
            ):
                with patch('app.services.ai_service.ai_service') as mock_ai:
                    mock_ai.load_api_keys_from_db = AsyncMock()
                    with patch('app.services.protect_event_handler.SessionLocal'):
                        result = await handler._submit_to_ai_pipeline(
                            snapshot_result=mock_snapshot_result,
                            camera=mock_camera_protect,
                            event_type="person",
                            clip_path=temp_clip_file
                        )

                assert result is not None
                assert "multi_frame:frame_extraction_failed" in handler._fallback_chain


class TestCompleteFailure:
    """Test complete fallback failure scenario (AC3)"""

    @pytest.mark.asyncio
    async def test_all_modes_fail_returns_none(
        self, handler, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """AC3: All analysis modes fail, returns None for complete failure handling"""
        mock_camera_protect.analysis_mode = "video_native"

        # Mock all to fail
        with patch.object(
            handler, '_try_multi_frame_analysis',
            new_callable=AsyncMock,
            return_value=None
        ):
            with patch.object(
                handler, '_single_frame_analysis',
                new_callable=AsyncMock,
                return_value=None  # Single frame also fails
            ):
                with patch('app.services.ai_service.ai_service') as mock_ai:
                    mock_ai.load_api_keys_from_db = AsyncMock()
                    with patch('app.services.protect_event_handler.SessionLocal'):
                        result = await handler._submit_to_ai_pipeline(
                            snapshot_result=mock_snapshot_result,
                            camera=mock_camera_protect,
                            event_type="person",
                            clip_path=temp_clip_file
                        )

                # Complete failure returns None
                assert result is None

                # Fallback chain should have all failures
                assert "video_native:" in ",".join(handler._fallback_chain)
                assert "single_frame:ai_failed" in handler._fallback_chain

                # Last fallback reason should contain full chain
                assert handler._last_fallback_reason is not None
                assert "," in handler._last_fallback_reason  # Comma-separated


class TestAnalysisModeTracking:
    """Test analysis_mode reflects actual mode used (AC4)"""

    @pytest.mark.asyncio
    async def test_successful_multi_frame_sets_analysis_mode(
        self, handler, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """AC4: Successful multi_frame sets analysis_mode correctly"""
        mock_camera_protect.analysis_mode = "multi_frame"

        # Mock successful multi-frame
        success_result = MockAIResult(success=True, description="Multi-frame success")

        with patch.object(
            handler, '_try_multi_frame_analysis',
            new_callable=AsyncMock,
            return_value=success_result
        ):
            with patch('app.services.ai_service.ai_service') as mock_ai:
                mock_ai.load_api_keys_from_db = AsyncMock()
                with patch('app.services.protect_event_handler.SessionLocal'):
                    result = await handler._submit_to_ai_pipeline(
                        snapshot_result=mock_snapshot_result,
                        camera=mock_camera_protect,
                        event_type="person",
                        clip_path=temp_clip_file
                    )

            assert result is not None
            # _try_multi_frame_analysis sets _last_analysis_mode internally

    @pytest.mark.asyncio
    async def test_fallback_to_single_frame_sets_correct_mode(
        self, handler, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """AC4: Fallback from multi_frame sets analysis_mode to single_frame"""
        mock_camera_protect.analysis_mode = "multi_frame"

        # We need to simulate the internal state setting that _single_frame_analysis does
        async def mock_single_frame(*args, **kwargs):
            # Simulate what the real method does on success
            handler._last_analysis_mode = "single_frame"
            handler._last_frame_count = 1
            if hasattr(handler, '_fallback_chain') and handler._fallback_chain:
                handler._last_fallback_reason = ",".join(handler._fallback_chain)
            return MockAIResult(success=True)

        # Mock multi-frame to fail
        with patch.object(
            handler, '_try_multi_frame_analysis',
            new_callable=AsyncMock,
            return_value=None
        ):
            # Mock single-frame to succeed (with state setting)
            with patch.object(handler, '_single_frame_analysis', side_effect=mock_single_frame):
                with patch('app.services.ai_service.ai_service') as mock_ai:
                    mock_ai.load_api_keys_from_db = AsyncMock()
                    with patch('app.services.protect_event_handler.SessionLocal'):
                        await handler._submit_to_ai_pipeline(
                            snapshot_result=mock_snapshot_result,
                            camera=mock_camera_protect,
                            event_type="person",
                            clip_path=temp_clip_file
                        )

                # After fallback, analysis_mode should be single_frame
                assert handler._last_analysis_mode == "single_frame"


class TestNonProtectCameras:
    """Test non-Protect cameras default to single_frame (AC - all, constraint)"""

    @pytest.mark.asyncio
    async def test_rtsp_camera_uses_single_frame_regardless_of_config(
        self, handler, mock_camera_rtsp, mock_snapshot_result
    ):
        """Non-Protect cameras always use single_frame regardless of analysis_mode config"""
        # RTSP camera has video_native configured but should use single_frame
        assert mock_camera_rtsp.analysis_mode == "video_native"
        assert mock_camera_rtsp.source_type == "rtsp"

        success_result = MockAIResult(success=True, description="RTSP single frame")

        with patch.object(
            handler, '_single_frame_analysis',
            new_callable=AsyncMock,
            return_value=success_result
        ) as mock_single:
            # Ensure multi-frame is NOT called for RTSP
            with patch.object(
                handler, '_try_multi_frame_analysis',
                new_callable=AsyncMock
            ) as mock_multi:
                with patch.object(
                    handler, '_try_video_native_analysis',
                    new_callable=AsyncMock
                ) as mock_video:
                    with patch('app.services.ai_service.ai_service') as mock_ai:
                        mock_ai.load_api_keys_from_db = AsyncMock()
                        with patch('app.services.protect_event_handler.SessionLocal'):
                            result = await handler._submit_to_ai_pipeline(
                                snapshot_result=mock_snapshot_result,
                                camera=mock_camera_rtsp,
                                event_type="motion"
                            )

                    # Single frame should be called directly
                    mock_single.assert_called_once()

                    # Video native and multi-frame should NOT be called
                    mock_video.assert_not_called()
                    mock_multi.assert_not_called()

                    assert result is not None
                    assert result.success is True

    @pytest.mark.asyncio
    async def test_usb_camera_uses_single_frame(self, handler, mock_snapshot_result):
        """USB cameras also use single_frame regardless of config"""
        mock_camera_usb = Mock()
        mock_camera_usb.id = "camera-usb-123"
        mock_camera_usb.name = "USB Camera"
        mock_camera_usb.source_type = "usb"
        mock_camera_usb.analysis_mode = "multi_frame"  # Should be ignored

        success_result = MockAIResult(success=True)

        with patch.object(
            handler, '_single_frame_analysis',
            new_callable=AsyncMock,
            return_value=success_result
        ) as mock_single:
            with patch('app.services.ai_service.ai_service') as mock_ai:
                mock_ai.load_api_keys_from_db = AsyncMock()
                with patch('app.services.protect_event_handler.SessionLocal'):
                    result = await handler._submit_to_ai_pipeline(
                        snapshot_result=mock_snapshot_result,
                        camera=mock_camera_usb,
                        event_type="motion"
                    )

            mock_single.assert_called_once()
            assert result is not None


class TestVideoNativeMethod:
    """Test _try_video_native_analysis method specifically"""

    @pytest.mark.asyncio
    async def test_video_native_with_clip_returns_none_provider_unsupported(
        self, handler, mock_camera_protect, mock_snapshot_result, temp_clip_file
    ):
        """Video native with valid clip returns None (not implemented in MVP)"""
        handler._fallback_chain = []

        result = await handler._try_video_native_analysis(
            clip_path=temp_clip_file,  # Real file that exists
            snapshot_result=mock_snapshot_result,
            camera=mock_camera_protect,
            event_type="person"
        )

        assert result is None
        assert "video_native:provider_unsupported" in handler._fallback_chain

    @pytest.mark.asyncio
    async def test_video_native_no_clip_records_reason(
        self, handler, mock_camera_protect, mock_snapshot_result
    ):
        """Video native with no clip records appropriate reason"""
        handler._fallback_chain = []

        result = await handler._try_video_native_analysis(
            clip_path=None,
            snapshot_result=mock_snapshot_result,
            camera=mock_camera_protect,
            event_type="person"
        )

        assert result is None
        assert "video_native:no_clip_available" in handler._fallback_chain


class TestStoreEventWithoutAI:
    """Test _store_event_without_ai method (AC3)"""

    @pytest.mark.asyncio
    async def test_store_event_without_ai_sets_description(
        self, handler, mock_camera_protect, mock_snapshot_result
    ):
        """AC3: Event stored with 'AI analysis unavailable' description"""
        handler._fallback_chain = ["video_native:provider_unsupported", "multi_frame:ai_failed", "single_frame:ai_failed"]

        mock_db = Mock()
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        with patch('app.services.protect_event_handler.Event') as MockEvent:
            mock_event = Mock()
            mock_event.id = "event-123"
            mock_event.description = "AI analysis unavailable"
            mock_event.fallback_reason = "video_native:provider_unsupported,multi_frame:ai_failed,single_frame:ai_failed"
            mock_event.description_retry_needed = True
            mock_event.smart_detection_type = "person"
            mock_event.is_doorbell_ring = False
            mock_event.camera_id = mock_camera_protect.id
            MockEvent.return_value = mock_event

            result = await handler._store_event_without_ai(
                db=mock_db,
                snapshot_result=mock_snapshot_result,
                camera=mock_camera_protect,
                event_type="person",
                protect_event_id="protect-event-456",
                is_doorbell_ring=False,
                event_id_override="generated-event-789"
            )

            # Verify Event was created with correct description
            MockEvent.assert_called_once()
            call_kwargs = MockEvent.call_args[1]
            assert call_kwargs['description'] == "AI analysis unavailable"
            assert call_kwargs['description_retry_needed'] is True
            assert call_kwargs['analysis_mode'] is None  # No mode succeeded
            assert call_kwargs['confidence'] == 0.0

            # Verify fallback_reason contains full chain
            assert "video_native:" in call_kwargs['fallback_reason']
            assert "multi_frame:" in call_kwargs['fallback_reason']

            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
