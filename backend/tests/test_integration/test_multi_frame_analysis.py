"""
Integration tests for Multi-Frame Analysis flow (Story P3-2.6)

Tests the complete flow of multi-frame analysis:
- AC1: FrameExtractor integration with EventProcessor
- AC2: Frame extraction fallback when clip processing fails
- AC3: AI service fallback when multi-frame API fails
- AC4: Tracking analysis_mode and frame_count_used in events

Uses mocks since actual video files and AI providers are not available.
"""
import pytest
import asyncio
import json
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.camera import Camera
from app.models.event import Event
from app.services.protect_event_handler import ProtectEventHandler
from app.services.snapshot_service import SnapshotResult


# Create test database
test_db_fd, test_db_path = tempfile.mkstemp(suffix="_multiframe.db")
os.close(test_db_fd)

TEST_DATABASE_URL = f"sqlite:///{test_db_path}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    yield
    db = TestingSessionLocal()
    try:
        db.query(Event).delete()
        db.query(Camera).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def test_camera_single_frame():
    """Create a test camera with single_frame analysis mode"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id="test-camera-sf-001",
            name="Test Camera Single Frame",
            type="rtsp",  # Must be rtsp or usb due to check constraint
            source_type="protect",  # But source_type is protect
            is_enabled=True,
            protect_camera_id="protect-cam-sf-001",
            protect_controller_id="test-ctrl-001",
            # analysis_mode not set - defaults to single_frame behavior
        )
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera
    finally:
        db.close()


@pytest.fixture
def test_camera_multi_frame():
    """Create a test camera with multi_frame analysis mode"""
    db = TestingSessionLocal()
    try:
        camera = Camera(
            id="test-camera-mf-001",
            name="Test Camera Multi Frame",
            type="rtsp",  # Must be rtsp or usb due to check constraint
            source_type="protect",  # But source_type is protect
            is_enabled=True,
            protect_camera_id="protect-cam-mf-001",
            protect_controller_id="test-ctrl-001",
        )
        # Manually set analysis_mode since column may not exist in test DB yet
        camera.analysis_mode = "multi_frame"
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera
    finally:
        db.close()


@pytest.fixture
def mock_snapshot_result():
    """Create a mock SnapshotResult"""
    return SnapshotResult(
        image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        thumbnail_path="thumbnails/test/event.jpg",
        width=640,
        height=480,
        camera_id="test-camera-001",
        timestamp=datetime.now(timezone.utc)
    )


@pytest.fixture
def mock_ai_result():
    """Create a mock AI result"""
    return MagicMock(
        success=True,
        description="Person detected walking toward entrance",
        confidence=85,
        objects_detected=["person"],
        provider="openai",
        response_time_ms=250,
        error=None,
        ai_confidence=85,
        cost_estimate=0.001,
        bounding_boxes=None  # Story P15-5.1: Added for AI visual annotations
    )


@pytest.fixture
def mock_multi_frame_ai_result():
    """Create a mock multi-frame AI result"""
    return MagicMock(
        success=True,
        description="Person walking toward entrance carrying a package, appears to be a delivery driver based on uniform",
        confidence=92,
        objects_detected=["person", "package"],
        provider="openai",
        response_time_ms=450,
        error=None,
        ai_confidence=92,
        cost_estimate=0.003,
        bounding_boxes=None  # Story P15-5.1: Added for AI visual annotations
    )


class TestMultiFrameAnalysisIntegration:
    """Integration tests for multi-frame analysis flow (Story P3-2.6)"""

    @pytest.mark.asyncio
    async def test_single_frame_analysis_when_no_clip_available(
        self, test_camera_single_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC1: Single-frame analysis when clip is not available"""
        handler = ProtectEventHandler()

        with patch('app.services.ai_service.ai_service') as mock_ai_service:
            mock_ai_service.generate_description = AsyncMock(return_value=mock_ai_result)
            mock_ai_service.load_api_keys_from_db = AsyncMock()

            # Call _submit_to_ai_pipeline with no clip_path
            result = await handler._submit_to_ai_pipeline(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_single_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=None  # No clip available
            )

            assert result is not None
            assert result.success is True
            assert handler._last_analysis_mode == "single_frame"
            assert handler._last_frame_count == 1
            mock_ai_service.generate_description.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_frame_analysis_with_successful_extraction(
        self, test_camera_multi_frame, mock_snapshot_result, mock_multi_frame_ai_result
    ):
        """AC1: Multi-frame analysis when clip is available and extraction succeeds"""
        handler = ProtectEventHandler()

        # Create a mock clip path that "exists"
        mock_clip_path = MagicMock(spec=Path)
        mock_clip_path.exists.return_value = True

        # Mock frames returned by extractor - now using extract_frames_with_timestamps
        mock_frames = [b"frame1_jpeg", b"frame2_jpeg", b"frame3_jpeg", b"frame4_jpeg", b"frame5_jpeg"]
        mock_timestamps = [0.0, 1.0, 2.0, 3.0, 4.0]

        with patch('app.services.ai_service.ai_service') as mock_ai_service, \
             patch('app.services.protect_event_handler.get_frame_extractor') as mock_get_extractor:

            mock_ai_service.describe_images = AsyncMock(return_value=mock_multi_frame_ai_result)
            mock_ai_service.load_api_keys_from_db = AsyncMock()

            mock_extractor = MagicMock()
            # The actual method is extract_frames_with_timestamps which returns (frames, timestamps)
            mock_extractor.extract_frames_with_timestamps = AsyncMock(return_value=(mock_frames, mock_timestamps))
            mock_get_extractor.return_value = mock_extractor

            result = await handler._submit_to_ai_pipeline(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=mock_clip_path
            )

            assert result is not None
            assert result.success is True
            assert handler._last_analysis_mode == "multi_frame"
            assert handler._last_frame_count == 5
            mock_ai_service.describe_images.assert_called_once()
            # Verify frames were passed to describe_images
            call_args = mock_ai_service.describe_images.call_args
            assert call_args.kwargs['images'] == mock_frames

    @pytest.mark.asyncio
    async def test_fallback_to_single_frame_when_extraction_fails(
        self, test_camera_multi_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC2: Falls back to single-frame when frame extraction returns empty"""
        handler = ProtectEventHandler()

        mock_clip_path = MagicMock(spec=Path)
        mock_clip_path.exists.return_value = True

        with patch('app.services.ai_service.ai_service') as mock_ai_service, \
             patch('app.services.protect_event_handler.get_frame_extractor') as mock_get_extractor:

            mock_ai_service.generate_description = AsyncMock(return_value=mock_ai_result)
            mock_ai_service.load_api_keys_from_db = AsyncMock()

            # Return empty frames to simulate extraction failure
            mock_extractor = MagicMock()
            mock_extractor.extract_frames_with_timestamps = AsyncMock(return_value=([], []))
            mock_get_extractor.return_value = mock_extractor

            result = await handler._submit_to_ai_pipeline(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=mock_clip_path
            )

            assert result is not None
            assert result.success is True
            assert handler._last_analysis_mode == "single_frame"
            assert handler._last_frame_count == 1
            # Fallback reason now includes the mode prefix
            assert "frame_extraction_failed" in handler._last_fallback_reason
            mock_ai_service.generate_description.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_single_frame_when_extraction_raises_exception(
        self, test_camera_multi_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC2: Falls back to single-frame when frame extraction raises exception"""
        handler = ProtectEventHandler()

        mock_clip_path = MagicMock(spec=Path)
        mock_clip_path.exists.return_value = True

        with patch('app.services.ai_service.ai_service') as mock_ai_service, \
             patch('app.services.protect_event_handler.get_frame_extractor') as mock_get_extractor:

            mock_ai_service.generate_description = AsyncMock(return_value=mock_ai_result)
            mock_ai_service.load_api_keys_from_db = AsyncMock()

            # Raise exception during extraction
            mock_extractor = MagicMock()
            mock_extractor.extract_frames_with_timestamps = AsyncMock(side_effect=Exception("Video decode error"))
            mock_get_extractor.return_value = mock_extractor

            result = await handler._submit_to_ai_pipeline(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=mock_clip_path
            )

            assert result is not None
            assert result.success is True
            assert handler._last_analysis_mode == "single_frame"
            # Fallback reason now includes the mode prefix
            assert "frame_extraction_failed" in handler._last_fallback_reason

    @pytest.mark.asyncio
    async def test_fallback_to_single_frame_when_multi_frame_ai_fails(
        self, test_camera_multi_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC3: Falls back to single-frame when multi-frame AI request fails"""
        handler = ProtectEventHandler()

        mock_clip_path = MagicMock(spec=Path)
        mock_clip_path.exists.return_value = True
        mock_frames = [b"frame1_jpeg", b"frame2_jpeg", b"frame3_jpeg"]
        mock_timestamps = [0.0, 1.0, 2.0]

        failed_ai_result = MagicMock(
            success=False,
            description="",
            error="Rate limit exceeded"
        )

        with patch('app.services.ai_service.ai_service') as mock_ai_service, \
             patch('app.services.protect_event_handler.get_frame_extractor') as mock_get_extractor:

            # Multi-frame fails, single-frame succeeds
            mock_ai_service.describe_images = AsyncMock(return_value=failed_ai_result)
            mock_ai_service.generate_description = AsyncMock(return_value=mock_ai_result)
            mock_ai_service.load_api_keys_from_db = AsyncMock()

            mock_extractor = MagicMock()
            mock_extractor.extract_frames_with_timestamps = AsyncMock(return_value=(mock_frames, mock_timestamps))
            mock_get_extractor.return_value = mock_extractor

            result = await handler._submit_to_ai_pipeline(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=mock_clip_path
            )

            assert result is not None
            assert result.success is True
            assert handler._last_analysis_mode == "single_frame"
            # Fallback reason now includes the mode prefix
            assert "ai_failed" in handler._last_fallback_reason

    @pytest.mark.asyncio
    async def test_fallback_to_single_frame_when_multi_frame_ai_raises_exception(
        self, test_camera_multi_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC3: Falls back to single-frame when multi-frame AI raises exception"""
        handler = ProtectEventHandler()

        mock_clip_path = MagicMock(spec=Path)
        mock_clip_path.exists.return_value = True
        mock_frames = [b"frame1_jpeg", b"frame2_jpeg", b"frame3_jpeg"]
        mock_timestamps = [0.0, 1.0, 2.0]

        with patch('app.services.ai_service.ai_service') as mock_ai_service, \
             patch('app.services.protect_event_handler.get_frame_extractor') as mock_get_extractor:

            # Multi-frame raises exception, single-frame succeeds
            mock_ai_service.describe_images = AsyncMock(side_effect=Exception("API timeout"))
            mock_ai_service.generate_description = AsyncMock(return_value=mock_ai_result)
            mock_ai_service.load_api_keys_from_db = AsyncMock()

            mock_extractor = MagicMock()
            mock_extractor.extract_frames_with_timestamps = AsyncMock(return_value=(mock_frames, mock_timestamps))
            mock_get_extractor.return_value = mock_extractor

            result = await handler._submit_to_ai_pipeline(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=mock_clip_path
            )

            assert result is not None
            assert result.success is True
            assert handler._last_analysis_mode == "single_frame"
            # Fallback reason now includes the mode prefix
            assert "ai_failed" in handler._last_fallback_reason

    @pytest.mark.asyncio
    async def test_single_frame_when_clip_path_does_not_exist(
        self, test_camera_multi_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC1: Uses single-frame when clip path doesn't exist"""
        handler = ProtectEventHandler()

        mock_clip_path = MagicMock(spec=Path)
        mock_clip_path.exists.return_value = False  # File doesn't exist

        with patch('app.services.ai_service.ai_service') as mock_ai_service:
            mock_ai_service.generate_description = AsyncMock(return_value=mock_ai_result)
            mock_ai_service.load_api_keys_from_db = AsyncMock()

            result = await handler._submit_to_ai_pipeline(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=mock_clip_path
            )

            assert result is not None
            assert handler._last_analysis_mode == "single_frame"
            mock_ai_service.generate_description.assert_called_once()


class TestMultiFrameEventStorage:
    """Integration tests for storing events with analysis_mode tracking (AC4)"""

    @pytest.mark.asyncio
    async def test_store_event_with_multi_frame_analysis_mode(
        self, test_camera_multi_frame, mock_snapshot_result, mock_multi_frame_ai_result
    ):
        """AC4: Event stored with analysis_mode='multi_frame' and frame_count_used"""
        handler = ProtectEventHandler()

        # Simulate multi-frame analysis completed
        handler._last_analysis_mode = "multi_frame"
        handler._last_frame_count = 5
        handler._last_fallback_reason = None

        db = TestingSessionLocal()
        try:
            event = await handler._store_protect_event(
                db=db,
                ai_result=mock_multi_frame_ai_result,
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                protect_event_id="protect-event-001",
                is_doorbell_ring=False,
                fallback_reason=None,
                event_id_override="test-event-mf-001"
            )

            assert event is not None
            assert event.analysis_mode == "multi_frame"
            assert event.frame_count_used == 5
            assert event.fallback_reason is None
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_store_event_with_single_frame_fallback(
        self, test_camera_multi_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC4: Event stored with fallback_reason when multi-frame failed"""
        handler = ProtectEventHandler()

        # Simulate fallback to single-frame
        handler._last_analysis_mode = "single_frame"
        handler._last_frame_count = 1
        handler._last_fallback_reason = "frame_extraction_failed"

        db = TestingSessionLocal()
        try:
            event = await handler._store_protect_event(
                db=db,
                ai_result=mock_ai_result,
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                protect_event_id="protect-event-002",
                is_doorbell_ring=False,
                fallback_reason=None,  # Will be overridden by _last_fallback_reason
                event_id_override="test-event-sf-001"
            )

            assert event is not None
            assert event.analysis_mode == "single_frame"
            assert event.frame_count_used == 1
            assert event.fallback_reason == "frame_extraction_failed"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_store_event_clip_download_fallback_takes_precedence(
        self, test_camera_multi_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC4: Clip download fallback_reason takes precedence over AI fallback"""
        handler = ProtectEventHandler()

        # Simulate both clip download failure AND AI fallback
        handler._last_analysis_mode = "single_frame"
        handler._last_frame_count = 1
        handler._last_fallback_reason = "multi_frame_ai_failed"

        db = TestingSessionLocal()
        try:
            event = await handler._store_protect_event(
                db=db,
                ai_result=mock_ai_result,
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                protect_event_id="protect-event-003",
                is_doorbell_ring=False,
                fallback_reason="clip_download_failed",  # This takes precedence
                event_id_override="test-event-clip-fb-001"
            )

            assert event is not None
            assert event.fallback_reason == "clip_download_failed"
        finally:
            db.close()


class TestMultiFrameDoorbellPrompt:
    """Test doorbell prompt is used for multi-frame analysis"""

    @pytest.mark.asyncio
    async def test_doorbell_prompt_used_in_multi_frame_analysis(
        self, test_camera_multi_frame, mock_snapshot_result, mock_multi_frame_ai_result
    ):
        """Doorbell prompt is passed to describe_images when is_doorbell_ring=True"""
        handler = ProtectEventHandler()

        mock_clip_path = MagicMock(spec=Path)
        mock_clip_path.exists.return_value = True
        mock_frames = [b"frame1", b"frame2", b"frame3"]
        mock_timestamps = [0.0, 1.0, 2.0]

        with patch('app.services.ai_service.ai_service') as mock_ai_service, \
             patch('app.services.protect_event_handler.get_frame_extractor') as mock_get_extractor:

            mock_ai_service.describe_images = AsyncMock(return_value=mock_multi_frame_ai_result)
            mock_ai_service.load_api_keys_from_db = AsyncMock()

            mock_extractor = MagicMock()
            mock_extractor.extract_frames_with_timestamps = AsyncMock(return_value=(mock_frames, mock_timestamps))
            mock_get_extractor.return_value = mock_extractor

            result = await handler._submit_to_ai_pipeline(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="ring",
                is_doorbell_ring=True,  # Doorbell ring event
                clip_path=mock_clip_path
            )

            # Verify doorbell prompt was passed
            call_args = mock_ai_service.describe_images.call_args
            assert call_args.kwargs['custom_prompt'] is not None
            assert "front door" in call_args.kwargs['custom_prompt'].lower()
