"""
Tests for FrameStorageService

Story P8-2.1: Store All Analysis Frames During Event Processing

NOTE: Uses shared fixtures from conftest.py:
    - db_session: In-memory SQLite database session
    - sample_camera: Test camera instance
    - sample_event: Test event instance
    - make_camera, make_event: Factory functions for custom instances
"""
import io
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.models.event import Event
from app.models.event_frame import EventFrame
from app.services.frame_storage_service import (
    FrameStorageService,
    get_frame_storage_service,
    reset_frame_storage_service,
    FRAME_JPEG_QUALITY,
    FRAME_MAX_WIDTH,
)
# Import factory functions for creating custom test objects
from tests.conftest import make_camera, make_event


@pytest.fixture
def temp_dir():
    """Create a temporary directory for frame storage."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


# sample_camera and sample_event are now provided by global conftest.py


@pytest.fixture
def sample_frames():
    """Create sample JPEG frame bytes for testing."""
    frames = []
    for i in range(3):
        # Create a simple test image
        img = Image.new('RGB', (800, 600), color=(i * 80, 100, 150))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        frames.append(buffer.getvalue())
    return frames


@pytest.fixture
def sample_timestamps():
    """Create sample timestamps (in milliseconds)."""
    return [0, 1000, 2000]  # 0s, 1s, 2s


@pytest.fixture
def frame_storage_service(temp_dir, db_session):
    """Create a FrameStorageService with temp directory."""
    reset_frame_storage_service()
    service = FrameStorageService(session_factory=lambda: db_session)
    # Override base_dir to use temp directory
    service.base_dir = Path(temp_dir) / "frames"
    return service


class TestEventFrameModel:
    """Tests for EventFrame database model."""

    def test_event_frame_creation(self, db_session, sample_event):
        """AC1.2: Test EventFrame record creation."""
        frame = EventFrame(
            event_id=sample_event.id,
            frame_number=1,
            frame_path="frames/test/frame_001.jpg",
            timestamp_offset_ms=0,
            width=800,
            height=600,
            file_size_bytes=50000,
            created_at=datetime.now(timezone.utc)
        )
        db_session.add(frame)
        db_session.commit()

        # Verify record was created
        saved = db_session.query(EventFrame).filter(EventFrame.id == frame.id).first()
        assert saved is not None
        assert saved.event_id == sample_event.id
        assert saved.frame_number == 1
        assert saved.timestamp_offset_ms == 0

    def test_frame_metadata_stored_correctly(self, db_session, sample_event):
        """AC1.3: Test frame metadata includes required fields."""
        frame = EventFrame(
            event_id=sample_event.id,
            frame_number=3,
            frame_path="frames/test/frame_003.jpg",
            timestamp_offset_ms=2500,
            width=1280,
            height=720,
            file_size_bytes=75000,
            created_at=datetime.now(timezone.utc)
        )
        db_session.add(frame)
        db_session.commit()

        saved = db_session.query(EventFrame).filter(EventFrame.id == frame.id).first()
        assert saved.frame_number == 3
        assert saved.frame_path == "frames/test/frame_003.jpg"
        assert saved.timestamp_offset_ms == 2500
        assert saved.width == 1280
        assert saved.height == 720
        assert saved.file_size_bytes == 75000

    def test_unique_constraint_event_frame_number(self, db_session, sample_event):
        """Test unique constraint on (event_id, frame_number)."""
        frame1 = EventFrame(
            event_id=sample_event.id,
            frame_number=1,
            frame_path="frames/test/frame_001.jpg",
            timestamp_offset_ms=0
        )
        db_session.add(frame1)
        db_session.commit()

        # Try to add duplicate frame number for same event
        frame2 = EventFrame(
            event_id=sample_event.id,
            frame_number=1,  # Same frame number
            frame_path="frames/test/frame_001_dup.jpg",
            timestamp_offset_ms=100
        )
        db_session.add(frame2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()


class TestFrameStorageService:
    """Tests for FrameStorageService."""

    @pytest.mark.asyncio
    async def test_save_frames_creates_directory_and_files(
        self, frame_storage_service, sample_event, sample_frames, sample_timestamps, db_session
    ):
        """AC1.1: Test frames saved to data/frames/{event_id}/."""
        result = await frame_storage_service.save_frames(
            event_id=sample_event.id,
            frames=sample_frames,
            timestamps_ms=sample_timestamps,
            db=db_session
        )

        # Verify directory was created
        frame_dir = frame_storage_service._get_event_frame_dir(sample_event.id)
        assert frame_dir.exists()

        # Verify files were created with correct naming
        for i, event_frame in enumerate(result, start=1):
            expected_filename = f"frame_{i:03d}.jpg"
            file_path = frame_dir / expected_filename
            assert file_path.exists(), f"Frame file {expected_filename} should exist"

    @pytest.mark.asyncio
    async def test_save_frames_creates_db_records(
        self, frame_storage_service, sample_event, sample_frames, sample_timestamps, db_session
    ):
        """AC1.2: Test EventFrame records created in database."""
        result = await frame_storage_service.save_frames(
            event_id=sample_event.id,
            frames=sample_frames,
            timestamps_ms=sample_timestamps,
            db=db_session
        )

        assert len(result) == 3

        # Verify DB records exist
        frames = db_session.query(EventFrame).filter(
            EventFrame.event_id == sample_event.id
        ).all()
        assert len(frames) == 3

        # Verify records have correct event_id
        for frame in frames:
            assert frame.event_id == sample_event.id

    @pytest.mark.asyncio
    async def test_save_frames_metadata_correct(
        self, frame_storage_service, sample_event, sample_frames, sample_timestamps, db_session
    ):
        """AC1.3: Test frame metadata includes frame_number, path, timestamp_offset_ms."""
        result = await frame_storage_service.save_frames(
            event_id=sample_event.id,
            frames=sample_frames,
            timestamps_ms=sample_timestamps,
            db=db_session
        )

        for i, event_frame in enumerate(result):
            assert event_frame.frame_number == i + 1  # 1-indexed
            assert event_frame.timestamp_offset_ms == sample_timestamps[i]
            assert f"frame_{i+1:03d}.jpg" in event_frame.frame_path
            assert event_frame.width is not None
            assert event_frame.height is not None
            assert event_frame.file_size_bytes is not None
            assert event_frame.file_size_bytes > 0

    @pytest.mark.asyncio
    async def test_save_frames_with_empty_list(self, frame_storage_service, sample_event, db_session):
        """Edge case: Empty frames list should not create directory."""
        result = await frame_storage_service.save_frames(
            event_id=sample_event.id,
            frames=[],
            timestamps_ms=[],
            db=db_session
        )

        assert result == []

        # Directory should not be created
        frame_dir = frame_storage_service._get_event_frame_dir(sample_event.id)
        assert not frame_dir.exists()

    @pytest.mark.asyncio
    async def test_save_frames_handles_existing_directory(
        self, frame_storage_service, sample_event, sample_frames, sample_timestamps, db_session
    ):
        """Edge case: Directory already exists should not error."""
        # Pre-create directory
        frame_dir = frame_storage_service._get_event_frame_dir(sample_event.id)
        frame_dir.mkdir(parents=True, exist_ok=True)

        # Should not raise
        result = await frame_storage_service.save_frames(
            event_id=sample_event.id,
            frames=sample_frames,
            timestamps_ms=sample_timestamps,
            db=db_session
        )

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_delete_frames_removes_directory(
        self, frame_storage_service, sample_event, sample_frames, sample_timestamps, db_session
    ):
        """AC1.4: Test delete_frames removes directory and files."""
        # First save frames
        await frame_storage_service.save_frames(
            event_id=sample_event.id,
            frames=sample_frames,
            timestamps_ms=sample_timestamps,
            db=db_session
        )

        frame_dir = frame_storage_service._get_event_frame_dir(sample_event.id)
        assert frame_dir.exists()

        # Delete frames
        deleted_count = await frame_storage_service.delete_frames(sample_event.id)

        assert deleted_count == 3
        assert not frame_dir.exists()

    @pytest.mark.asyncio
    async def test_delete_frames_handles_missing_directory(self, frame_storage_service):
        """Edge case: Deleting non-existent frames should not error."""
        fake_event_id = str(uuid.uuid4())

        # Should not raise
        deleted_count = await frame_storage_service.delete_frames(fake_event_id)

        assert deleted_count == 0

    def test_get_frames_size(self, temp_dir, db_session):
        """Test frames size calculation."""
        # Create a fresh service with controlled base_dir
        reset_frame_storage_service()
        service = FrameStorageService(session_factory=lambda: db_session)
        service.base_dir = Path(temp_dir) / "frames"

        # Create base frames dir and some test files inside it
        frames_dir = service.base_dir
        frames_dir.mkdir(parents=True, exist_ok=True)

        test_dir = frames_dir / "test_event"
        test_dir.mkdir(parents=True, exist_ok=True)

        # Write 3 files of ~100KB each (300KB total = ~0.3MB)
        for i in range(3):
            (test_dir / f"frame_{i:03d}.jpg").write_bytes(b"x" * 100 * 1024)

        size_mb = service.get_frames_size()
        assert size_mb > 0.2, f"Expected > 0.2 MB, got {size_mb}"
        assert size_mb < 0.5  # ~300KB = ~0.3 MB


class TestEventDeletionCascade:
    """Tests for event deletion cascading to frames."""

    def test_event_deletion_cascades_to_frames(self, db_session, sample_camera):
        """AC1.4: Test deleting event removes EventFrame DB records."""
        # Create event using factory function
        event = make_event(
            db_session=db_session,
            camera_id=sample_camera.id,
            description="Test event for cascade deletion"
        )

        # Create frame records
        for i in range(3):
            frame = EventFrame(
                event_id=event.id,
                frame_number=i + 1,
                frame_path=f"frames/{event.id}/frame_{i+1:03d}.jpg",
                timestamp_offset_ms=i * 1000
            )
            db_session.add(frame)
        db_session.commit()

        # Verify frames exist
        frames = db_session.query(EventFrame).filter(EventFrame.event_id == event.id).all()
        assert len(frames) == 3

        # Delete event
        db_session.delete(event)
        db_session.commit()

        # Verify frames were cascade deleted
        frames = db_session.query(EventFrame).filter(EventFrame.event_id == event.id).all()
        assert len(frames) == 0


class TestSingletonPattern:
    """Tests for singleton service pattern."""

    def test_get_frame_storage_service_returns_singleton(self):
        """Test singleton pattern."""
        reset_frame_storage_service()

        service1 = get_frame_storage_service()
        service2 = get_frame_storage_service()

        assert service1 is service2

    def test_reset_frame_storage_service(self):
        """Test singleton reset."""
        reset_frame_storage_service()

        service1 = get_frame_storage_service()
        reset_frame_storage_service()
        service2 = get_frame_storage_service()

        assert service1 is not service2


class TestRetentionCleanupFrames:
    """Tests for retention cleanup with frames."""

    @pytest.mark.asyncio
    async def test_cleanup_service_removes_frames(self, temp_dir, db_session, sample_camera):
        """AC1.5: Test retention cleanup deletes frame directories."""
        from app.services.cleanup_service import CleanupService
        from datetime import timedelta

        # Create cleanup service with test session
        cleanup_service = CleanupService(session_factory=lambda: db_session)

        # Mock frame storage service to use temp directory
        mock_frame_service = FrameStorageService(session_factory=lambda: db_session)
        mock_frame_service.base_dir = Path(temp_dir) / "frames"

        # Create old event (31 days ago) using factory function
        old_event = make_event(
            db_session=db_session,
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc) - timedelta(days=31),
            description="Old event for cleanup test"
        )

        # Create frame directory and files manually
        frame_dir = mock_frame_service._get_event_frame_dir(old_event.id)
        frame_dir.mkdir(parents=True, exist_ok=True)
        (frame_dir / "frame_001.jpg").write_bytes(b"test")
        (frame_dir / "frame_002.jpg").write_bytes(b"test")

        # Verify setup
        assert frame_dir.exists()
        assert len(list(frame_dir.glob("*.jpg"))) == 2

        # Patch get_frame_storage_service to return our mock
        with patch('app.services.cleanup_service.get_frame_storage_service', return_value=mock_frame_service):
            stats = await cleanup_service.cleanup_old_events(retention_days=30)

        # Verify event was deleted
        assert stats["events_deleted"] == 1
        # Verify frames were deleted
        assert stats["frames_deleted"] == 2
        # Frame directory should be removed
        assert not frame_dir.exists()
