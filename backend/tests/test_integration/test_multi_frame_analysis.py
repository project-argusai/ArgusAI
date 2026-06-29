"""
Integration tests for Multi-Frame Analysis flow (originally Story P3-2.6)

REWRITE NOTE (post Phase-4 / #443-#450 decomposition):
    The multi-frame / fallback orchestration that originally lived on
    ``ProtectEventHandler._submit_to_ai_pipeline`` was extracted into the new
    ``ProtectAIPipeline.submit_snapshot_for_analysis``
    (``app/services/protect_ai_pipeline.py``), and event persistence moved from
    ``ProtectEventHandler._store_protect_event`` to
    ``ProtectEventStorageService.persist_protect_event``
    (``app/services/protect_event_storage_service.py``).

    Contract changes that drove the repointing below:

      * AI calls are now made through the ``VisionAnalysisOrchestrator``
        (``analyze_images(images=...)`` for the multi-frame path,
        ``analyze_image(frame=...)`` for single-frame) — *not*
        ``ai_service.describe_images`` / ``ai_service.generate_description``.
      * Frame extraction is ``_extract_frames_from_clip`` (a pipeline method that
        wraps ``FrameExtractor.extract_frames_with_timestamps``); tests patch the
        pipeline method directly, mirroring tests/test_services/test_fallback_chain.py.
      * Analysis-mode / frame-count / fallback-reason tracking lives on the
        *pipeline* (``_last_analysis_mode`` / ``_last_frame_count`` /
        ``_last_fallback_reason``), not the handler.
      * ``persist_protect_event`` takes ``analysis_mode`` / ``frame_count_used`` /
        ``fallback_reason`` as explicit arguments — it no longer reads ``_last_*``
        state off a handler.

REMOVED_TESTS (behaviour genuinely gone from source — not a relocation):
    - test_fallback_to_single_frame_when_multi_frame_ai_fails:
        The current pipeline does NOT fall back to single-frame when the
        multi-frame AI call returns ``success=False``; it returns that failed
        result as-is (only an *exception* triggers the single-frame fallback).
        The ``ai_failed`` fallback-reason vocabulary no longer exists in app/.
    - test_single_frame_when_clip_path_does_not_exist:
        ``submit_snapshot_for_analysis`` branches on ``clip_path`` truthiness, not
        on ``clip_path.exists()``. The "exists() gates the mode" premise is gone;
        the no-clip path is already covered by
        test_single_frame_analysis_when_no_clip_available.
    - test_doorbell_prompt_used_in_multi_frame_analysis:
        The pipeline passes ``custom_prompt=None`` to ``analyze_images`` (the
        doorbell-prompt wiring is an explicit ``TODO`` in source). No "front door"
        prompt is threaded through the multi-frame path, so the asserted
        behaviour does not exist anywhere in app/.

    The fallback-reason *vocabulary* the old tests asserted
    (``frame_extraction_failed``, ``ai_failed``) was likewise dropped: when frame
    extraction yields nothing the pipeline silently degrades to single-frame with
    ``_last_fallback_reason == None``; an extraction *exception* is caught inside
    ``_extract_frames_from_clip`` (also yielding ``[]`` with no reason). Those
    assertions were updated to match the contract that exists today.
"""
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.camera import Camera
from app.models.event import Event
from app.services.snapshot_service import SnapshotResult
from app.services.protect_ai_pipeline import (
    ProtectAIPipeline,
    reset_protect_ai_pipeline,
)
from app.services.protect_event_storage_service import (
    ProtectEventStorageService,
    reset_protect_event_storage_service,
)


# Create test database
test_db_fd, test_db_path = tempfile.mkstemp(suffix="_multiframe.db")
os.close(test_db_fd)

TEST_DATABASE_URL = f"sqlite:///{test_db_path}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)


# 1x1 PNG (valid, decodable by Pillow) used for the single-frame path.
_VALID_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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
def pipeline():
    """Create a fresh ProtectAIPipeline (singleton) instance for testing."""
    reset_protect_ai_pipeline()
    return ProtectAIPipeline()


@pytest.fixture
def storage_service():
    """Create a fresh ProtectEventStorageService (singleton) instance."""
    reset_protect_event_storage_service()
    return ProtectEventStorageService()


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
    """Create a mock SnapshotResult with a decodable image"""
    return SnapshotResult(
        image_base64=_VALID_PNG_B64,
        thumbnail_path="thumbnails/test/event.jpg",
        width=640,
        height=480,
        camera_id="test-camera-001",
        timestamp=datetime.now(timezone.utc)
    )


@pytest.fixture
def mock_ai_result():
    """Create a mock single-frame AI result"""
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


@pytest.fixture
def temp_clip_file():
    """Create a temporary clip file that actually exists (truthy clip_path)."""
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    yield Path(path)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _patch_pipeline_deps(orchestrator):
    """
    Patch the lazily-imported dependencies of ``submit_snapshot_for_analysis``:
    the orchestrator getter, the ai_service key loader, and the db session.
    Mirrors the helper in tests/test_services/test_fallback_chain.py.
    """
    return (
        patch(
            "app.services.vision_analysis_orchestrator.get_vision_analysis_orchestrator",
            return_value=orchestrator,
        ),
        patch("app.services.ai_service.ai_service"),
        patch("app.core.database.get_db_session"),
    )


class TestMultiFrameAnalysisIntegration:
    """Integration tests for the multi-frame analysis flow (ProtectAIPipeline)."""

    @pytest.mark.asyncio
    async def test_single_frame_analysis_when_no_clip_available(
        self, pipeline, test_camera_single_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC1: Single-frame analysis when no clip is available."""
        orch = MagicMock()
        orch.analyze_image = AsyncMock(return_value=mock_ai_result)

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db:
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_single_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=None,  # No clip available
            )

        assert result is not None
        assert result.success is True
        assert pipeline._last_analysis_mode == "single_frame"
        assert pipeline._last_frame_count == 1
        orch.analyze_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_frame_analysis_with_successful_extraction(
        self, pipeline, test_camera_multi_frame, mock_snapshot_result, mock_multi_frame_ai_result, temp_clip_file
    ):
        """AC1: Multi-frame analysis when a clip is available and extraction succeeds."""
        mock_frames = [b"frame1_jpeg", b"frame2_jpeg", b"frame3_jpeg", b"frame4_jpeg", b"frame5_jpeg"]
        mock_timestamps = [0.0, 1.0, 2.0, 3.0, 4.0]

        orch = MagicMock()
        orch.analyze_images = AsyncMock(return_value=mock_multi_frame_ai_result)
        orch.analyze_image = AsyncMock()

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db, patch.object(
            pipeline, "_try_video_native_analysis", new_callable=AsyncMock, return_value=None
        ), patch.object(
            pipeline,
            "_extract_frames_from_clip",
            new_callable=AsyncMock,
            return_value=(mock_frames, mock_timestamps),
        ):
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=temp_clip_file,
            )

        assert result is not None
        assert result.success is True
        assert pipeline._last_analysis_mode == "multi_frame"
        assert pipeline._last_frame_count == 5
        orch.analyze_images.assert_called_once()
        orch.analyze_image.assert_not_called()
        # Verify frames were passed to analyze_images
        call_args = orch.analyze_images.call_args
        assert call_args.kwargs["images"] == mock_frames

    @pytest.mark.asyncio
    async def test_fallback_to_single_frame_when_extraction_fails(
        self, pipeline, test_camera_multi_frame, mock_snapshot_result, mock_ai_result, temp_clip_file
    ):
        """AC2: Falls back to single-frame when frame extraction returns empty.

        NOTE: the current pipeline degrades silently — no fallback-reason string is
        recorded for an empty extraction (the old ``frame_extraction_failed``
        vocabulary no longer exists in app/).
        """
        orch = MagicMock()
        orch.analyze_images = AsyncMock()
        orch.analyze_image = AsyncMock(return_value=mock_ai_result)

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db, patch.object(
            pipeline, "_try_video_native_analysis", new_callable=AsyncMock, return_value=None
        ), patch.object(
            pipeline,
            "_extract_frames_from_clip",
            new_callable=AsyncMock,
            return_value=([], []),  # extraction failure
        ):
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=temp_clip_file,
            )

        assert result is not None
        assert result.success is True
        assert pipeline._last_analysis_mode == "single_frame"
        assert pipeline._last_frame_count == 1
        orch.analyze_images.assert_not_called()
        orch.analyze_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_single_frame_when_multi_frame_ai_raises_exception(
        self, pipeline, test_camera_multi_frame, mock_snapshot_result, mock_ai_result, temp_clip_file
    ):
        """AC3: Falls back to single-frame when the multi-frame AI call raises.

        An exception in the multi-frame branch is caught and recorded on
        ``_last_fallback_reason`` as ``multi_frame_failed:<err>``, then the
        pipeline completes via the single-frame path.
        """
        mock_frames = [b"frame1_jpeg", b"frame2_jpeg", b"frame3_jpeg"]
        mock_timestamps = [0.0, 1.0, 2.0]

        orch = MagicMock()
        orch.analyze_images = AsyncMock(side_effect=Exception("API timeout"))
        orch.analyze_image = AsyncMock(return_value=mock_ai_result)

        p_orch, p_ai, p_db = _patch_pipeline_deps(orch)
        with p_orch, p_ai as mock_ai, p_db, patch.object(
            pipeline, "_try_video_native_analysis", new_callable=AsyncMock, return_value=None
        ), patch.object(
            pipeline,
            "_extract_frames_from_clip",
            new_callable=AsyncMock,
            return_value=(mock_frames, mock_timestamps),
        ):
            mock_ai.load_api_keys_from_db = AsyncMock()
            result = await pipeline.submit_snapshot_for_analysis(
                snapshot_result=mock_snapshot_result,
                camera=test_camera_multi_frame,
                event_type="person",
                is_doorbell_ring=False,
                clip_path=temp_clip_file,
            )

        assert result is not None
        assert result.success is True
        assert pipeline._last_analysis_mode == "single_frame"
        assert pipeline._last_fallback_reason is not None
        assert pipeline._last_fallback_reason.startswith("multi_frame_failed:")
        orch.analyze_image.assert_called_once()


class TestMultiFrameEventStorage:
    """Integration tests for persisting events with analysis_mode tracking (AC4)."""

    @pytest.mark.asyncio
    async def test_store_event_with_multi_frame_analysis_mode(
        self, storage_service, test_camera_multi_frame, mock_snapshot_result, mock_multi_frame_ai_result
    ):
        """AC4: Event stored with analysis_mode='multi_frame' and frame_count_used."""
        db = TestingSessionLocal()
        try:
            event = await storage_service.persist_protect_event(
                db=db,
                camera=test_camera_multi_frame,
                snapshot_result=mock_snapshot_result,
                ai_result=mock_multi_frame_ai_result,
                protect_event_id="protect-event-001",
                event_type="person",
                is_doorbell_ring=False,
                analysis_mode="multi_frame",
                frame_count_used=5,
                fallback_reason=None,
                event_id_override="test-event-mf-001",
            )

            assert event is not None
            assert event.analysis_mode == "multi_frame"
            assert event.frame_count_used == 5
            assert event.fallback_reason is None
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_store_event_with_single_frame_fallback(
        self, storage_service, test_camera_multi_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC4: Event stored with a fallback_reason when multi-frame degraded to single."""
        db = TestingSessionLocal()
        try:
            event = await storage_service.persist_protect_event(
                db=db,
                camera=test_camera_multi_frame,
                snapshot_result=mock_snapshot_result,
                ai_result=mock_ai_result,
                protect_event_id="protect-event-002",
                event_type="person",
                is_doorbell_ring=False,
                analysis_mode="single_frame",
                frame_count_used=1,
                fallback_reason="frame_extraction_failed",
                event_id_override="test-event-sf-001",
            )

            assert event is not None
            assert event.analysis_mode == "single_frame"
            assert event.frame_count_used == 1
            assert event.fallback_reason == "frame_extraction_failed"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_store_event_persists_provided_fallback_reason(
        self, storage_service, test_camera_multi_frame, mock_snapshot_result, mock_ai_result
    ):
        """AC4: The fallback_reason passed by the caller is persisted verbatim.

        (Precedence between competing fallback reasons is now resolved by the
        caller before persistence — the storage service simply stores what it is
        given, so we assert the round-trip of a clip-download fallback reason.)
        """
        db = TestingSessionLocal()
        try:
            event = await storage_service.persist_protect_event(
                db=db,
                camera=test_camera_multi_frame,
                snapshot_result=mock_snapshot_result,
                ai_result=mock_ai_result,
                protect_event_id="protect-event-003",
                event_type="person",
                is_doorbell_ring=False,
                analysis_mode="single_frame",
                frame_count_used=1,
                fallback_reason="clip_download_failed",
                event_id_override="test-event-clip-fb-001",
            )

            assert event is not None
            assert event.fallback_reason == "clip_download_failed"
        finally:
            db.close()
