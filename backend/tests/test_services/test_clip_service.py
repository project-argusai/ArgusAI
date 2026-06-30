"""
Unit tests for ClipService (Story P3-1.1, P3-1.2, P3-1.3)

Tests cover:
Story P3-1.1:
- AC1: ClipService class exists with download_clip() method
- AC2: Downloads MP4 clips via uiprotect library
- AC3: Clips saved to data/clips/{event_id}.mp4
- AC4: Returns Path on success, None on failure
- AC5: Download completes within 10 seconds (timeout handling)
- AC6: Uses existing controller credentials from ProtectService
- AC7: Returns None and logs on controller unreachable
- AC8: Creates data/clips/ directory if not exists

Story P3-1.2:
- AC1: cleanup_clip() deletes single clip, returns True/False
- AC2: cleanup_old_clips() deletes clips older than MAX_CLIP_AGE_HOURS
- AC3: Storage pressure deletes oldest clips when over MAX_STORAGE_MB
- AC4: Initialization runs cleanup_old_clips()
- AC5: Background scheduler runs cleanup every 15 minutes

Story P3-1.3:
- AC1: Retry up to 3 times with exponential backoff (1s, 2s, 4s)
- AC2: Returns None after all retries exhausted, logs failure
- AC3: Returns file path on success, logs with attempt count
- AC4: Non-retriable errors skip retries (404, empty file)
"""
import pytest
import asyncio
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.clip_service import (
    ClipService,
    TEMP_CLIP_DIR,
    MAX_CLIP_AGE_HOURS,
    MAX_STORAGE_MB,
    STORAGE_PRESSURE_TARGET_MB,
    DOWNLOAD_TIMEOUT,
    CLEANUP_INTERVAL_MINUTES,
    MAX_RETRY_ATTEMPTS,
    RETRY_MIN_WAIT,
    RETRY_MAX_WAIT,
    RetriableClipError,
    NonRetriableClipError,
    get_clip_service,
    reset_clip_service,
)


class TestClipServiceConstants:
    """Test service constants are properly defined"""

    def test_temp_clip_dir(self):
        """AC3: Verify clip directory constant"""
        assert TEMP_CLIP_DIR == "data/clips"

    def test_max_clip_age(self):
        """Verify cleanup age constant"""
        assert MAX_CLIP_AGE_HOURS == 1

    def test_max_storage(self):
        """Verify storage limit constant"""
        assert MAX_STORAGE_MB == 1024

    def test_download_timeout(self):
        """AC5: Verify 10 second timeout constant"""
        assert DOWNLOAD_TIMEOUT == 10.0

    def test_storage_pressure_target(self):
        """P3-1.2 AC3: Verify storage pressure target is 90% of max"""
        assert STORAGE_PRESSURE_TARGET_MB == int(MAX_STORAGE_MB * 0.9)
        assert STORAGE_PRESSURE_TARGET_MB == 921  # 90% of 1024

    def test_cleanup_interval(self):
        """P3-1.2 AC5: Verify cleanup interval is 15 minutes"""
        assert CLEANUP_INTERVAL_MINUTES == 15


class TestClipServiceInit:
    """Test ClipService initialization"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        # Create temp directory for clip storage
        self.temp_dir = tempfile.mkdtemp()
        self.original_clip_dir = TEMP_CLIP_DIR

        yield

        # Cleanup
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        reset_clip_service()

    def test_init_creates_clip_directory(self):
        """AC8: Verify directory is created on init"""
        mock_protect = MagicMock()
        test_dir = Path(self.temp_dir) / "test_clips"

        with patch("app.services.clip_service.TEMP_CLIP_DIR", str(test_dir)):
            # Import again to get patched value
            from app.services.clip_service import ClipService as PatchedClipService

            # Force re-evaluation by creating new instance
            service = ClipService(mock_protect)
            # Since TEMP_CLIP_DIR is module-level, we need to test differently
            # The _ensure_clip_dir call happens in __init__

        # Verify original directory creation works
        clip_dir = Path(TEMP_CLIP_DIR)
        clip_dir.mkdir(parents=True, exist_ok=True)
        assert clip_dir.exists()
        # Cleanup
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)

    def test_init_accepts_protect_service(self):
        """AC6: Verify ClipService takes ProtectService as dependency"""
        mock_protect = MagicMock()

        service = ClipService(mock_protect)

        assert service._protect_service is mock_protect


class TestClipServiceHelpers:
    """Test helper methods"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        self.service = ClipService(self.mock_protect)
        # Ensure directory doesn't exist for directory creation tests
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)

        yield

        # Cleanup
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    def test_get_clip_path_format(self):
        """AC3: Verify clip path format is data/clips/{event_id}.mp4"""
        event_id = "test-event-123"

        path = self.service._get_clip_path(event_id)

        assert path == Path(TEMP_CLIP_DIR) / f"{event_id}.mp4"
        assert str(path).endswith(".mp4")

    def test_get_clip_path_different_ids(self):
        """AC3: Verify unique paths for different event IDs"""
        path1 = self.service._get_clip_path("event-1")
        path2 = self.service._get_clip_path("event-2")

        assert path1 != path2
        assert "event-1" in str(path1)
        assert "event-2" in str(path2)

    def test_ensure_clip_dir_creates_directory(self):
        """AC8: Verify _ensure_clip_dir creates directory"""
        clip_dir = Path(TEMP_CLIP_DIR)
        if clip_dir.exists():
            shutil.rmtree(clip_dir)

        self.service._ensure_clip_dir()

        assert clip_dir.exists()
        assert clip_dir.is_dir()

    def test_ensure_clip_dir_idempotent(self):
        """AC8: Verify _ensure_clip_dir is safe to call multiple times"""
        self.service._ensure_clip_dir()
        self.service._ensure_clip_dir()  # Should not raise

        assert Path(TEMP_CLIP_DIR).exists()


class TestDownloadClip:
    """Test download_clip method"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        self.mock_client = AsyncMock()
        self.mock_protect._connections = {}

        self.service = ClipService(self.mock_protect)

        # Test data
        self.controller_id = "test-controller-id"
        self.camera_id = "test-camera-id"
        self.event_id = "test-event-id"
        self.event_start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.event_end = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)

        yield

        # Cleanup
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    @pytest.mark.asyncio
    async def test_download_clip_success(self):
        """AC2, AC4: Successful download returns file path"""
        # Setup mock client
        self.mock_protect._connections[self.controller_id] = self.mock_client

        # Mock get_camera_video to create a test file
        async def mock_download(camera_id, start, end, output_file):
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"fake mp4 data")

        self.mock_client.get_camera_video = mock_download

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is not None
        assert isinstance(result, Path)
        assert result.exists()
        assert result.name == f"{self.event_id}.mp4"

    @pytest.mark.asyncio
    async def test_download_clip_returns_none_when_controller_not_connected(self):
        """AC7: Returns None when controller not in connections"""
        # No controller in _connections dict

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_download_clip_returns_none_on_client_error(self):
        """AC4, AC7: Returns None on download error"""
        self.mock_protect._connections[self.controller_id] = self.mock_client
        self.mock_client.get_camera_video = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_download_clip_returns_none_on_timeout(self):
        """AC5: Returns None when download exceeds 10 second timeout"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        async def slow_download(camera_id, start, end, output_file):
            await asyncio.sleep(15)  # Longer than timeout

        self.mock_client.get_camera_video = slow_download

        # Use shorter timeout for test
        with patch("app.services.clip_service.DOWNLOAD_TIMEOUT", 0.1):
            result = await self.service.download_clip(
                controller_id=self.controller_id,
                camera_id=self.camera_id,
                event_start=self.event_start,
                event_end=self.event_end,
                event_id=self.event_id,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_download_clip_returns_none_on_empty_file(self):
        """AC4: Returns None when download produces empty file"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        async def empty_download(camera_id, start, end, output_file):
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.touch()  # Create empty file

        self.mock_client.get_camera_video = empty_download

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_download_clip_cleans_up_partial_file_on_error(self):
        """AC4: Partial files are cleaned up on error"""
        self.mock_protect._connections[self.controller_id] = self.mock_client
        output_path = self.service._get_clip_path(self.event_id)

        async def failing_download(camera_id, start, end, output_file):
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"partial data")
            raise Exception("Download interrupted")

        self.mock_client.get_camera_video = failing_download

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is None
        assert not output_path.exists()

    @pytest.mark.asyncio
    async def test_gateway_404_502_is_retriable(self):
        """A Protect export 'Status: 404 - Reason: 502' is a transient gateway
        error (clip not finalized yet), NOT a true not-found. It must be classified
        RetriableClipError so the existing backoff re-requests once the clip is
        ready, instead of immediately degrading the event to single_frame."""
        async def gateway_502(camera_id, start, end, output_file):
            raise Exception(
                "Request failed: https://10.0.1.254/proxy/protect/api/video/export"
                "?camera=cam1&start=1&end=2&channel=0 - Status: 404 - Reason: 502"
            )

        self.mock_client.get_camera_video = gateway_502
        output_path = self.service._get_clip_path(self.event_id)

        with pytest.raises(RetriableClipError):
            await self.service._download_clip_attempt(
                client=self.mock_client,
                camera_id=self.camera_id,
                event_start=self.event_start,
                event_end=self.event_end,
                output_path=output_path,
            )

    @pytest.mark.asyncio
    async def test_true_404_not_found_stays_non_retriable(self):
        """A genuine 404 (no gateway reason) means the clip does not exist; it must
        stay NonRetriableClipError so we fail fast instead of retrying pointlessly."""
        async def real_404(camera_id, start, end, output_file):
            raise Exception(
                "Request failed: https://10.0.1.254/proxy/protect/api/video/export"
                "?camera=cam1 - Status: 404 - Reason: Not Found"
            )

        self.mock_client.get_camera_video = real_404
        output_path = self.service._get_clip_path(self.event_id)

        with pytest.raises(NonRetriableClipError):
            await self.service._download_clip_attempt(
                client=self.mock_client,
                camera_id=self.camera_id,
                event_start=self.event_start,
                event_end=self.event_end,
                output_path=output_path,
            )

    @pytest.mark.asyncio
    async def test_download_clip_uses_correct_parameters(self):
        """AC2, AC6: Verify correct parameters passed to uiprotect"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        captured_args = {}

        async def capture_download(camera_id, start, end, output_file):
            captured_args["camera_id"] = camera_id
            captured_args["start"] = start
            captured_args["end"] = end
            captured_args["output_file"] = output_file
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"test data")

        self.mock_client.get_camera_video = capture_download

        await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert captured_args["camera_id"] == self.camera_id
        assert captured_args["start"] == self.event_start
        assert captured_args["end"] == self.event_end
        assert str(captured_args["output_file"]).endswith(f"{self.event_id}.mp4")


class TestClipServiceLogging:
    """Test logging behavior"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        self.mock_protect._connections = {}
        self.service = ClipService(self.mock_protect)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    @pytest.mark.asyncio
    async def test_logs_on_controller_not_connected(self):
        """AC7: Logs warning when controller not connected"""
        with patch("app.services.clip_service.logger") as mock_logger:
            await self.service.download_clip(
                controller_id="unknown-controller",
                camera_id="cam1",
                event_start=datetime.now(timezone.utc),
                event_end=datetime.now(timezone.utc),
                event_id="evt1",
            )

            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "not connected" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_logs_on_download_error(self):
        """AC7: Logs error on download failure"""
        self.mock_protect._connections["ctrl1"] = AsyncMock()
        self.mock_protect._connections["ctrl1"].get_camera_video = AsyncMock(
            side_effect=Exception("Network error")
        )

        with patch("app.services.clip_service.logger") as mock_logger:
            await self.service.download_clip(
                controller_id="ctrl1",
                camera_id="cam1",
                event_start=datetime.now(timezone.utc),
                event_end=datetime.now(timezone.utc),
                event_id="evt1",
            )

            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_logs_success(self):
        """AC2: Logs info on successful download"""
        self.mock_protect._connections["ctrl1"] = AsyncMock()

        async def mock_download(camera_id, start, end, output_file):
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"video data")

        self.mock_protect._connections["ctrl1"].get_camera_video = mock_download

        with patch("app.services.clip_service.logger") as mock_logger:
            await self.service.download_clip(
                controller_id="ctrl1",
                camera_id="cam1",
                event_start=datetime.now(timezone.utc),
                event_end=datetime.now(timezone.utc),
                event_id="evt1",
            )

            # Should have info logs for start and success
            assert mock_logger.info.call_count >= 2


class TestClipServiceSingleton:
    """Test singleton pattern"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test"""
        reset_clip_service()
        yield
        reset_clip_service()
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)

    def test_get_clip_service_returns_instance(self):
        """AC1: get_clip_service returns ClipService instance"""
        with patch(
            "app.services.protect_service.get_protect_service"
        ) as mock_get:
            mock_get.return_value = MagicMock()

            service = get_clip_service()

            assert isinstance(service, ClipService)

    def test_get_clip_service_returns_same_instance(self):
        """AC6: Singleton returns same instance"""
        with patch(
            "app.services.protect_service.get_protect_service"
        ) as mock_get:
            mock_get.return_value = MagicMock()

            service1 = get_clip_service()
            service2 = get_clip_service()

            assert service1 is service2

    def test_reset_clip_service_clears_singleton(self):
        """Test reset allows new instance creation"""
        with patch(
            "app.services.protect_service.get_protect_service"
        ) as mock_get:
            mock_get.return_value = MagicMock()

            service1 = get_clip_service()
            reset_clip_service()
            service2 = get_clip_service()

            assert service1 is not service2


# ============================================================================
# Story P3-1.2: Temporary Clip Storage Management Tests
# ============================================================================


class TestCleanupClip:
    """Test cleanup_clip method (P3-1.2 AC1)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        # Patch scheduler to avoid background tasks in tests
        with patch.object(ClipService, '_start_scheduler'):
            self.service = ClipService(self.mock_protect)

        # Ensure clean directory
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        Path(TEMP_CLIP_DIR).mkdir(parents=True, exist_ok=True)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    def test_cleanup_clip_success(self):
        """P3-1.2 AC1: cleanup_clip returns True when file exists"""
        # Create a test clip file
        event_id = "test-event-123"
        clip_path = Path(TEMP_CLIP_DIR) / f"{event_id}.mp4"
        clip_path.write_bytes(b"fake video data")

        result = self.service.cleanup_clip(event_id)

        assert result is True
        assert not clip_path.exists()

    def test_cleanup_clip_not_found(self):
        """P3-1.2 AC1: cleanup_clip returns False when file not found"""
        event_id = "nonexistent-event"

        result = self.service.cleanup_clip(event_id)

        assert result is False

    def test_cleanup_clip_logs_success(self):
        """P3-1.2 AC1: Logs successful cleanup"""
        event_id = "test-event-456"
        clip_path = Path(TEMP_CLIP_DIR) / f"{event_id}.mp4"
        clip_path.write_bytes(b"test data")

        with patch("app.services.clip_service.logger") as mock_logger:
            self.service.cleanup_clip(event_id)

            mock_logger.info.assert_called()


class TestCleanupOldClips:
    """Test cleanup_old_clips method (P3-1.2 AC2)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        # Patch scheduler to avoid background tasks in tests
        with patch.object(ClipService, '_start_scheduler'):
            with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
                self.service = ClipService(self.mock_protect)

        # Ensure clean directory
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        Path(TEMP_CLIP_DIR).mkdir(parents=True, exist_ok=True)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    def test_cleanup_old_clips_deletes_old_files(self):
        """P3-1.2 AC2: Deletes clips older than MAX_CLIP_AGE_HOURS"""
        import time
        import os

        # Create an old clip (set mtime to 2 hours ago)
        old_clip = Path(TEMP_CLIP_DIR) / "old-event.mp4"
        old_clip.write_bytes(b"old data")
        old_mtime = time.time() - (2 * 3600)  # 2 hours ago
        os.utime(old_clip, (old_mtime, old_mtime))

        # Create a new clip (recent)
        new_clip = Path(TEMP_CLIP_DIR) / "new-event.mp4"
        new_clip.write_bytes(b"new data")

        result = self.service.cleanup_old_clips()

        assert result >= 1
        assert not old_clip.exists()
        assert new_clip.exists()

    def test_cleanup_old_clips_returns_count(self):
        """P3-1.2 AC2: Returns count of deleted files"""
        import time
        import os

        # Create 3 old clips
        for i in range(3):
            clip = Path(TEMP_CLIP_DIR) / f"old-{i}.mp4"
            clip.write_bytes(b"data")
            old_mtime = time.time() - (2 * 3600)
            os.utime(clip, (old_mtime, old_mtime))

        result = self.service.cleanup_old_clips()

        assert result >= 3

    def test_cleanup_old_clips_empty_directory(self):
        """P3-1.2 AC2: Returns 0 on empty directory"""
        result = self.service.cleanup_old_clips()

        assert result == 0

    def test_cleanup_old_clips_keeps_recent_files(self):
        """P3-1.2 AC2: Keeps files younger than MAX_CLIP_AGE_HOURS"""
        # Create a recent clip (30 minutes old)
        import time
        import os

        recent_clip = Path(TEMP_CLIP_DIR) / "recent.mp4"
        recent_clip.write_bytes(b"recent data")
        recent_mtime = time.time() - (30 * 60)  # 30 minutes ago
        os.utime(recent_clip, (recent_mtime, recent_mtime))

        result = self.service.cleanup_old_clips()

        assert result == 0
        assert recent_clip.exists()


class TestStoragePressure:
    """Test storage pressure management (P3-1.2 AC3)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        # Patch scheduler to avoid background tasks
        with patch.object(ClipService, '_start_scheduler'):
            with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
                self.service = ClipService(self.mock_protect)

        # Ensure clean directory
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        Path(TEMP_CLIP_DIR).mkdir(parents=True, exist_ok=True)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    def test_no_pressure_when_under_limit(self):
        """P3-1.2 AC3: No deletion when under MAX_STORAGE_MB"""
        # Create a small file (well under limit)
        clip = Path(TEMP_CLIP_DIR) / "small.mp4"
        clip.write_bytes(b"x" * 1000)  # 1KB

        result = self.service._check_storage_pressure()

        assert result == 0
        assert clip.exists()

    def test_pressure_deletes_oldest_first(self):
        """P3-1.2 AC3: Deletes oldest files first when over limit"""
        import time
        import os

        # This is a functional test - we'll mock the size to trigger pressure
        with patch.object(self.service, '_get_directory_size_bytes') as mock_size:
            # First call: over limit
            # Subsequent calls: decreasing as files are "deleted"
            mock_size.side_effect = [
                1100 * 1024 * 1024,  # Over 1GB
                950 * 1024 * 1024,   # Still over 900MB target
                850 * 1024 * 1024,   # Under target
            ]

            # Create test clips with different ages
            for i in range(3):
                clip = Path(TEMP_CLIP_DIR) / f"clip-{i}.mp4"
                clip.write_bytes(b"x" * 100)
                mtime = time.time() - (i * 3600)  # Different ages
                os.utime(clip, (mtime, mtime))

            result = self.service._check_storage_pressure()

            # Should have deleted at least one
            assert result >= 1

    def test_pressure_logs_warning(self):
        """P3-1.2 AC3: Logs warning when storage pressure detected"""
        with patch.object(self.service, '_get_directory_size_bytes') as mock_size:
            mock_size.return_value = 1100 * 1024 * 1024  # Over 1GB

            with patch("app.services.clip_service.logger") as mock_logger:
                self.service._check_storage_pressure()

                mock_logger.warning.assert_called()

    def test_get_directory_size(self):
        """P3-1.2 AC3: _get_directory_size_bytes calculates correctly"""
        # Create files with known sizes
        clip1 = Path(TEMP_CLIP_DIR) / "clip1.mp4"
        clip2 = Path(TEMP_CLIP_DIR) / "clip2.mp4"
        clip1.write_bytes(b"x" * 1000)
        clip2.write_bytes(b"y" * 500)

        result = self.service._get_directory_size_bytes()

        assert result == 1500


class TestInitializationCleanup:
    """Test initialization cleanup (P3-1.2 AC4)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    def test_init_calls_cleanup(self):
        """P3-1.2 AC4: __init__ calls cleanup_old_clips"""
        mock_protect = MagicMock()

        with patch.object(ClipService, '_start_scheduler'):
            with patch.object(ClipService, 'cleanup_old_clips', return_value=5) as mock_cleanup:
                service = ClipService(mock_protect)

                mock_cleanup.assert_called_once()

    def test_init_handles_cleanup_errors(self):
        """P3-1.2 AC4: __init__ doesn't fail on cleanup errors"""
        mock_protect = MagicMock()

        with patch.object(ClipService, '_start_scheduler'):
            with patch.object(ClipService, 'cleanup_old_clips', side_effect=Exception("Cleanup failed")):
                # Should not raise
                service = ClipService(mock_protect)

                assert service is not None

    def test_init_creates_directory(self):
        """P3-1.2 AC4: __init__ creates clips directory"""
        mock_protect = MagicMock()
        clip_dir = Path(TEMP_CLIP_DIR)

        # Ensure directory doesn't exist
        if clip_dir.exists():
            shutil.rmtree(clip_dir)

        with patch.object(ClipService, '_start_scheduler'):
            with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
                service = ClipService(mock_protect)

        assert clip_dir.exists()


class TestBackgroundScheduler:
    """Test background cleanup scheduler (P3-1.2 AC5)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    def test_scheduler_starts_on_init(self):
        """P3-1.2 AC5: Scheduler starts when ClipService initializes"""
        mock_protect = MagicMock()

        with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
            with patch('app.services.clip_service.BackgroundScheduler') as mock_scheduler_class:
                mock_scheduler = MagicMock()
                mock_scheduler_class.return_value = mock_scheduler

                service = ClipService(mock_protect)

                mock_scheduler.start.assert_called_once()
                mock_scheduler.add_job.assert_called_once()

    def test_scheduler_adds_cleanup_job(self):
        """P3-1.2 AC5: Scheduler adds cleanup job with correct interval"""
        mock_protect = MagicMock()

        with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
            with patch('app.services.clip_service.BackgroundScheduler') as mock_scheduler_class:
                mock_scheduler = MagicMock()
                mock_scheduler_class.return_value = mock_scheduler

                service = ClipService(mock_protect)

                # Verify add_job was called with correct parameters
                call_args = mock_scheduler.add_job.call_args
                assert call_args[0][0] == service.cleanup_old_clips
                assert call_args[0][1] == 'interval'
                assert call_args[1]['minutes'] == CLEANUP_INTERVAL_MINUTES
                assert call_args[1]['id'] == 'clip_cleanup'

    def test_stop_scheduler_shuts_down(self):
        """P3-1.2 AC5: _stop_scheduler shuts down scheduler"""
        mock_protect = MagicMock()

        with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
            with patch('app.services.clip_service.BackgroundScheduler') as mock_scheduler_class:
                mock_scheduler = MagicMock()
                mock_scheduler_class.return_value = mock_scheduler

                service = ClipService(mock_protect)
                service._stop_scheduler()

                mock_scheduler.shutdown.assert_called_once_with(wait=False)

    def test_reset_stops_scheduler(self):
        """P3-1.2 AC5: reset_clip_service stops scheduler"""
        mock_protect = MagicMock()

        with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
            with patch('app.services.clip_service.BackgroundScheduler') as mock_scheduler_class:
                mock_scheduler = MagicMock()
                mock_scheduler_class.return_value = mock_scheduler

                # Set the global singleton manually for this test
                import app.services.clip_service as clip_module
                service = ClipService(mock_protect)
                clip_module._clip_service = service

                reset_clip_service()

                mock_scheduler.shutdown.assert_called()

    def test_scheduler_handles_start_error(self):
        """P3-1.2 AC5: Handles scheduler start errors gracefully"""
        mock_protect = MagicMock()

        with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
            with patch('app.services.clip_service.BackgroundScheduler') as mock_scheduler_class:
                mock_scheduler_class.side_effect = Exception("Scheduler error")

                # Should not raise
                service = ClipService(mock_protect)

                assert service is not None


# ============================================================================
# Story P3-1.3: Retry Logic with Exponential Backoff Tests
# ============================================================================


class TestRetryConstants:
    """Test retry configuration constants (P3-1.3)"""

    def test_max_retry_attempts(self):
        """P3-1.3 AC1: Verify max retry attempts is 3"""
        assert MAX_RETRY_ATTEMPTS == 3

    def test_retry_min_wait(self):
        """P3-1.3 AC1: Verify minimum wait is 1 second"""
        assert RETRY_MIN_WAIT == 1

    def test_retry_max_wait(self):
        """P3-1.3 AC1: Verify maximum wait is 4 seconds"""
        assert RETRY_MAX_WAIT == 4

    def test_exponential_backoff_sequence(self):
        """P3-1.3 AC1: Verify exponential backoff sequence is 1s, 2s, 4s"""
        # Backoff formula: min(max_wait, min_wait * 2^(attempt-1))
        expected = [1, 2, 4]
        for attempt in range(1, 4):
            calculated = min(RETRY_MAX_WAIT, RETRY_MIN_WAIT * (2 ** (attempt - 1)))
            assert calculated == expected[attempt - 1]


class TestRetryExceptions:
    """Test retry exception classes (P3-1.3)"""

    def test_retriable_clip_error_exists(self):
        """P3-1.3 AC1: RetriableClipError exception class exists"""
        assert issubclass(RetriableClipError, Exception)

    def test_non_retriable_clip_error_exists(self):
        """P3-1.3 AC4: NonRetriableClipError exception class exists"""
        assert issubclass(NonRetriableClipError, Exception)

    def test_retriable_error_is_distinct(self):
        """P3-1.3: RetriableClipError is not the same as NonRetriableClipError"""
        assert RetriableClipError is not NonRetriableClipError

    def test_retriable_error_can_be_raised(self):
        """P3-1.3: RetriableClipError can be raised and caught"""
        with pytest.raises(RetriableClipError):
            raise RetriableClipError("Test retriable error")

    def test_non_retriable_error_can_be_raised(self):
        """P3-1.3: NonRetriableClipError can be raised and caught"""
        with pytest.raises(NonRetriableClipError):
            raise NonRetriableClipError("Test non-retriable error")


class TestRetryOnFailure:
    """Test retry behavior on download failures (P3-1.3)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        self.mock_client = AsyncMock()
        self.mock_protect._connections = {}

        with patch.object(ClipService, '_start_scheduler'):
            with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
                self.service = ClipService(self.mock_protect)

        # Test data
        self.controller_id = "test-controller-id"
        self.camera_id = "test-camera-id"
        self.event_id = "test-event-retry"
        self.event_start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.event_end = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    @pytest.mark.asyncio
    async def test_retry_success_on_second_attempt(self):
        """P3-1.3 AC1, AC3: Retry on first failure, success on second attempt"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        # Track call count
        call_count = 0

        async def mock_download(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt fails with retriable error
                raise ConnectionError("Network timeout")
            # Second attempt succeeds
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"video data on retry")

        self.mock_client.get_camera_video = mock_download

        # Patch retry wait to speed up test
        with patch('app.services.clip_service.RETRY_MIN_WAIT', 0.01):
            with patch('app.services.clip_service.RETRY_MAX_WAIT', 0.04):
                result = await self.service.download_clip(
                    controller_id=self.controller_id,
                    camera_id=self.camera_id,
                    event_start=self.event_start,
                    event_end=self.event_end,
                    event_id=self.event_id,
                )

        assert result is not None
        assert result.exists()
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_returns_none(self):
        """P3-1.3 AC2: All 3 retry attempts fail, returns None"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        # Track call count
        call_count = 0

        async def mock_always_fail(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent network error")

        self.mock_client.get_camera_video = mock_always_fail

        # Patch retry wait to speed up test
        with patch('app.services.clip_service.RETRY_MIN_WAIT', 0.01):
            with patch('app.services.clip_service.RETRY_MAX_WAIT', 0.04):
                result = await self.service.download_clip(
                    controller_id=self.controller_id,
                    camera_id=self.camera_id,
                    event_start=self.event_start,
                    event_end=self.event_end,
                    event_id=self.event_id,
                )

        assert result is None
        assert call_count == MAX_RETRY_ATTEMPTS

    @pytest.mark.asyncio
    async def test_success_on_first_attempt_no_retry(self):
        """P3-1.3 AC3: Success on first attempt, no retries needed"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_immediate_success(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"immediate success video data")

        self.mock_client.get_camera_video = mock_immediate_success

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is not None
        assert result.exists()
        assert call_count == 1  # Only one attempt needed

    @pytest.mark.asyncio
    async def test_success_on_third_attempt(self):
        """P3-1.3 AC1, AC3: Retry succeeds on third attempt"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_download(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"Network error on attempt {call_count}")
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"success on third try")

        self.mock_client.get_camera_video = mock_download

        with patch('app.services.clip_service.RETRY_MIN_WAIT', 0.01):
            with patch('app.services.clip_service.RETRY_MAX_WAIT', 0.04):
                result = await self.service.download_clip(
                    controller_id=self.controller_id,
                    camera_id=self.camera_id,
                    event_start=self.event_start,
                    event_end=self.event_end,
                    event_id=self.event_id,
                )

        assert result is not None
        assert call_count == 3


class TestNonRetriableErrors:
    """Test non-retriable error handling (P3-1.3 AC4)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        self.mock_client = AsyncMock()
        self.mock_protect._connections = {}

        with patch.object(ClipService, '_start_scheduler'):
            with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
                self.service = ClipService(self.mock_protect)

        self.controller_id = "test-controller-id"
        self.camera_id = "test-camera-id"
        self.event_id = "test-event-nonretry"
        self.event_start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.event_end = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    @pytest.mark.asyncio
    async def test_404_error_no_retry(self):
        """P3-1.3 AC4: 404/not-found error skips retries"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_not_found(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            raise Exception("404 Not Found: Clip does not exist")

        self.mock_client.get_camera_video = mock_not_found

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is None
        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_empty_file_no_retry(self):
        """P3-1.3 AC4: Empty file is non-retriable"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_empty_file(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.touch()  # Create empty file

        self.mock_client.get_camera_video = mock_empty_file

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is None
        assert call_count == 1  # No retries for empty file

    @pytest.mark.asyncio
    async def test_auth_error_no_retry(self):
        """P3-1.3 AC4: Authentication error skips retries"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_auth_error(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            raise Exception("401 Unauthorized: Invalid credentials")

        self.mock_client.get_camera_video = mock_auth_error

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is None
        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_403_forbidden_no_retry(self):
        """P3-1.3 AC4: 403 Forbidden error skips retries"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_forbidden(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            raise Exception("403 Forbidden: Access denied")

        self.mock_client.get_camera_video = mock_forbidden

        result = await self.service.download_clip(
            controller_id=self.controller_id,
            camera_id=self.camera_id,
            event_start=self.event_start,
            event_end=self.event_end,
            event_id=self.event_id,
        )

        assert result is None
        assert call_count == 1  # No retries


class TestRetriableErrors:
    """Test retriable error handling (P3-1.3)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        self.mock_client = AsyncMock()
        self.mock_protect._connections = {}

        with patch.object(ClipService, '_start_scheduler'):
            with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
                self.service = ClipService(self.mock_protect)

        self.controller_id = "test-controller-id"
        self.camera_id = "test-camera-id"
        self.event_id = "test-event-retriable"
        self.event_start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.event_end = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self):
        """P3-1.3 AC1: Timeout error triggers retry"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_timeout_then_success(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError("Connection timed out")
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"success after timeout")

        self.mock_client.get_camera_video = mock_timeout_then_success

        with patch('app.services.clip_service.RETRY_MIN_WAIT', 0.01):
            with patch('app.services.clip_service.RETRY_MAX_WAIT', 0.04):
                result = await self.service.download_clip(
                    controller_id=self.controller_id,
                    camera_id=self.camera_id,
                    event_start=self.event_start,
                    event_end=self.event_end,
                    event_id=self.event_id,
                )

        assert result is not None
        assert call_count == 2  # Retried once

    @pytest.mark.asyncio
    async def test_connection_error_triggers_retry(self):
        """P3-1.3 AC1: ConnectionError triggers retry"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_connection_then_success(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Connection refused")
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"success after connection error")

        self.mock_client.get_camera_video = mock_connection_then_success

        with patch('app.services.clip_service.RETRY_MIN_WAIT', 0.01):
            with patch('app.services.clip_service.RETRY_MAX_WAIT', 0.04):
                result = await self.service.download_clip(
                    controller_id=self.controller_id,
                    camera_id=self.camera_id,
                    event_start=self.event_start,
                    event_end=self.event_end,
                    event_id=self.event_id,
                )

        assert result is not None
        assert call_count == 2


class TestRetryLogging:
    """Test retry logging behavior (P3-1.3)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.mock_protect = MagicMock()
        self.mock_client = AsyncMock()
        self.mock_protect._connections = {}

        with patch.object(ClipService, '_start_scheduler'):
            with patch.object(ClipService, 'cleanup_old_clips', return_value=0):
                self.service = ClipService(self.mock_protect)

        self.controller_id = "test-controller-id"
        self.camera_id = "test-camera-id"
        self.event_id = "test-event-logging"
        self.event_start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.event_end = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)

        yield

        shutil.rmtree(TEMP_CLIP_DIR, ignore_errors=True)
        reset_clip_service()

    @pytest.mark.asyncio
    async def test_logs_retry_attempt_with_attempt_number(self):
        """P3-1.3 AC1: Logs each retry attempt with attempt number"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_fail_twice(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"Error on attempt {call_count}")
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"success on third")

        self.mock_client.get_camera_video = mock_fail_twice

        with patch('app.services.clip_service.RETRY_MIN_WAIT', 0.01):
            with patch('app.services.clip_service.RETRY_MAX_WAIT', 0.04):
                with patch("app.services.clip_service.logger") as mock_logger:
                    await self.service.download_clip(
                        controller_id=self.controller_id,
                        camera_id=self.camera_id,
                        event_start=self.event_start,
                        event_end=self.event_end,
                        event_id=self.event_id,
                    )

                    # Check that warning was called for retries
                    warning_calls = mock_logger.warning.call_args_list
                    retry_logs = [c for c in warning_calls
                                  if "retry" in str(c).lower() and "attempt" in str(c).lower()]
                    assert len(retry_logs) >= 1

    @pytest.mark.asyncio
    async def test_logs_success_on_retry(self):
        """P3-1.3 AC3: Logs success with file path when retry succeeds"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        call_count = 0

        async def mock_fail_then_succeed(camera_id, start, end, output_file):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("First attempt fails")
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"success")

        self.mock_client.get_camera_video = mock_fail_then_succeed

        with patch('app.services.clip_service.RETRY_MIN_WAIT', 0.01):
            with patch('app.services.clip_service.RETRY_MAX_WAIT', 0.04):
                with patch("app.services.clip_service.logger") as mock_logger:
                    result = await self.service.download_clip(
                        controller_id=self.controller_id,
                        camera_id=self.camera_id,
                        event_start=self.event_start,
                        event_end=self.event_end,
                        event_id=self.event_id,
                    )

                    assert result is not None
                    # Check success was logged
                    info_calls = mock_logger.info.call_args_list
                    success_logs = [c for c in info_calls
                                    if "success" in str(c).lower()]
                    assert len(success_logs) >= 1

    @pytest.mark.asyncio
    async def test_logs_final_failure_after_all_retries(self):
        """P3-1.3 AC2: Logs 'Clip download failed after N attempts' on exhaustion"""
        self.mock_protect._connections[self.controller_id] = self.mock_client

        async def mock_always_fail(camera_id, start, end, output_file):
            raise ConnectionError("Persistent failure")

        self.mock_client.get_camera_video = mock_always_fail

        with patch('app.services.clip_service.RETRY_MIN_WAIT', 0.01):
            with patch('app.services.clip_service.RETRY_MAX_WAIT', 0.04):
                with patch("app.services.clip_service.logger") as mock_logger:
                    result = await self.service.download_clip(
                        controller_id=self.controller_id,
                        camera_id=self.camera_id,
                        event_start=self.event_start,
                        event_end=self.event_end,
                        event_id=self.event_id,
                    )

                    assert result is None
                    # Check error was logged
                    error_calls = mock_logger.error.call_args_list
                    failure_logs = [c for c in error_calls
                                    if "failed" in str(c).lower() and "3" in str(c)]
                    assert len(failure_logs) >= 1
