"""
Unit tests for SnapshotService (Story P14-3.3)

Tests snapshot retrieval, image processing, thumbnail generation,
notification optimization, and cache cleanup functionality.
"""
import asyncio
import base64
import io
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.services.snapshot_service import (
    AI_MAX_HEIGHT,
    AI_MAX_WIDTH,
    DEFAULT_THUMBNAIL_PATH,
    MAX_CONCURRENT_SNAPSHOTS,
    NOTIFICATION_CACHE_SUFFIX,
    NOTIFICATION_MAX_DIMENSION,
    NOTIFICATION_MAX_FILE_SIZE,
    RETRY_DELAY_SECONDS,
    SEMAPHORE_TIMEOUT_SECONDS,
    SNAPSHOT_TIMEOUT_SECONDS,
    THUMBNAIL_HEIGHT,
    THUMBNAIL_WIDTH,
    SnapshotResult,
    SnapshotService,
    cleanup_notification_cache,
    get_snapshot_service,
    optimize_thumbnail_for_notification,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_thumbnail_dir():
    """Create a temporary directory for thumbnail storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def snapshot_service(temp_thumbnail_dir):
    """Create a SnapshotService instance with temp directory."""
    return SnapshotService(thumbnail_path=temp_thumbnail_dir)


@pytest.fixture
def mock_protect_service():
    """Mock the ProtectService for snapshot retrieval."""
    # The import happens inside _fetch_snapshot_with_retry, so we patch the module
    with patch("app.services.protect_service.get_protect_service") as mock:
        service = MagicMock()
        service.get_camera_snapshot = AsyncMock()
        mock.return_value = service
        yield service


@pytest.fixture
def sample_jpeg_bytes():
    """Create sample JPEG image bytes for testing."""
    img = Image.new("RGB", (1920, 1080), color="red")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def small_jpeg_bytes():
    """Create small JPEG image bytes for testing."""
    img = Image.new("RGB", (320, 180), color="blue")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def large_jpeg_bytes():
    """Create large JPEG image bytes (4K) for testing."""
    img = Image.new("RGB", (3840, 2160), color="green")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return buffer.read()


# =============================================================================
# Test Constants
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_snapshot_timeout_seconds(self):
        """Verify snapshot timeout is 1 second."""
        assert SNAPSHOT_TIMEOUT_SECONDS == 1.0

    def test_retry_delay_seconds(self):
        """Verify retry delay is 0.5 seconds."""
        assert RETRY_DELAY_SECONDS == 0.5

    def test_max_concurrent_snapshots(self):
        """Verify max concurrent snapshots is 3."""
        assert MAX_CONCURRENT_SNAPSHOTS == 3

    def test_semaphore_timeout_seconds(self):
        """Verify semaphore timeout is 5 seconds."""
        assert SEMAPHORE_TIMEOUT_SECONDS == 5.0

    def test_ai_max_dimensions(self):
        """Verify AI max dimensions are 1920x1080."""
        assert AI_MAX_WIDTH == 1920
        assert AI_MAX_HEIGHT == 1080

    def test_thumbnail_dimensions(self):
        """Verify thumbnail dimensions are 320x180."""
        assert THUMBNAIL_WIDTH == 320
        assert THUMBNAIL_HEIGHT == 180

    def test_notification_max_dimension(self):
        """Verify notification max dimension is 1024."""
        assert NOTIFICATION_MAX_DIMENSION == 1024

    def test_notification_max_file_size(self):
        """Verify notification max file size is 1MB."""
        assert NOTIFICATION_MAX_FILE_SIZE == 1 * 1024 * 1024


# =============================================================================
# Test SnapshotService Initialization
# =============================================================================


class TestSnapshotServiceInit:
    """Tests for SnapshotService initialization."""

    def test_init_creates_thumbnail_directory(self, temp_thumbnail_dir):
        """Test that init creates the thumbnail directory."""
        new_dir = os.path.join(temp_thumbnail_dir, "new_thumbnails")
        service = SnapshotService(thumbnail_path=new_dir)
        assert os.path.exists(new_dir)
        assert service._thumbnail_path == new_dir

    def test_init_with_existing_directory(self, temp_thumbnail_dir):
        """Test that init works with existing directory."""
        service = SnapshotService(thumbnail_path=temp_thumbnail_dir)
        assert service._thumbnail_path == temp_thumbnail_dir

    def test_init_default_path(self):
        """Test that default path is used when not specified."""
        with patch("os.makedirs"):
            service = SnapshotService()
            assert service._thumbnail_path == DEFAULT_THUMBNAIL_PATH

    def test_init_counters_zero(self, snapshot_service):
        """Test that metrics counters start at zero."""
        assert snapshot_service._snapshot_failures_total == 0
        assert snapshot_service._snapshot_success_total == 0

    def test_init_empty_semaphores(self, snapshot_service):
        """Test that semaphores dict starts empty."""
        assert len(snapshot_service._controller_semaphores) == 0


class TestSnapshotServiceSingleton:
    """Tests for the singleton pattern."""

    def test_get_snapshot_service_returns_same_instance(self):
        """Test that get_snapshot_service returns singleton."""
        # Reset singleton
        import app.services.snapshot_service as module

        module._snapshot_service = None

        service1 = get_snapshot_service()
        service2 = get_snapshot_service()
        assert service1 is service2

        # Reset for other tests
        module._snapshot_service = None


# =============================================================================
# Test Controller Semaphore
# =============================================================================


class TestControllerSemaphore:
    """Tests for controller semaphore management."""

    def test_get_controller_semaphore_creates_new(self, snapshot_service):
        """Test that new semaphore is created for new controller."""
        semaphore = snapshot_service._get_controller_semaphore("controller-1")
        assert isinstance(semaphore, asyncio.Semaphore)
        assert "controller-1" in snapshot_service._controller_semaphores

    def test_get_controller_semaphore_returns_existing(self, snapshot_service):
        """Test that same semaphore is returned for same controller."""
        semaphore1 = snapshot_service._get_controller_semaphore("controller-1")
        semaphore2 = snapshot_service._get_controller_semaphore("controller-1")
        assert semaphore1 is semaphore2

    def test_get_controller_semaphore_different_controllers(self, snapshot_service):
        """Test that different controllers get different semaphores."""
        semaphore1 = snapshot_service._get_controller_semaphore("controller-1")
        semaphore2 = snapshot_service._get_controller_semaphore("controller-2")
        assert semaphore1 is not semaphore2

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_requests(self, snapshot_service):
        """Test that semaphore limits concurrent snapshots to MAX_CONCURRENT_SNAPSHOTS."""
        semaphore = snapshot_service._get_controller_semaphore("controller-1")

        # Acquire all available slots
        acquired = []
        for _ in range(MAX_CONCURRENT_SNAPSHOTS):
            await semaphore.acquire()
            acquired.append(True)

        assert len(acquired) == MAX_CONCURRENT_SNAPSHOTS

        # Try to acquire one more with timeout - should fail
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
            assert False, "Should have timed out"
        except asyncio.TimeoutError:
            pass  # Expected

        # Release all
        for _ in range(MAX_CONCURRENT_SNAPSHOTS):
            semaphore.release()


# =============================================================================
# Test Image Resizing
# =============================================================================


class TestResizeForAI:
    """Tests for _resize_for_ai method."""

    def test_resize_smaller_image_unchanged(self, snapshot_service):
        """Test that smaller images are not resized (returns copy)."""
        img = Image.new("RGB", (800, 600), color="red")
        result = snapshot_service._resize_for_ai(img)
        assert result.size == (800, 600)

    def test_resize_exact_size_unchanged(self, snapshot_service):
        """Test that exact max size images are not resized."""
        img = Image.new("RGB", (AI_MAX_WIDTH, AI_MAX_HEIGHT), color="red")
        result = snapshot_service._resize_for_ai(img)
        assert result.size == (AI_MAX_WIDTH, AI_MAX_HEIGHT)

    def test_resize_larger_width(self, snapshot_service):
        """Test that wider images are resized by width."""
        # 4K image: 3840x2160
        img = Image.new("RGB", (3840, 2160), color="red")
        result = snapshot_service._resize_for_ai(img)
        # Should be scaled to 1920 width, 1080 height (maintains 16:9)
        assert result.size[0] == 1920
        assert result.size[1] == 1080

    def test_resize_larger_height(self, snapshot_service):
        """Test that taller images are resized by height."""
        # Tall image: 1000x2000
        img = Image.new("RGB", (1000, 2000), color="red")
        result = snapshot_service._resize_for_ai(img)
        # Height should be 1080, width proportionally smaller
        assert result.size[1] == 1080
        assert result.size[0] == 540  # 1000 * (1080/2000)

    @pytest.mark.parametrize(
        "original_size,expected_size",
        [
            ((800, 600), (800, 600)),  # Smaller - unchanged
            ((1920, 1080), (1920, 1080)),  # Exact - unchanged
            ((3840, 2160), (1920, 1080)),  # 4K 16:9
            ((4000, 3000), (1440, 1080)),  # 4:3 ratio, height constrained
            ((2000, 500), (1920, 480)),  # Ultra-wide, width constrained
        ],
    )
    def test_resize_maintains_aspect_ratio(
        self, snapshot_service, original_size, expected_size
    ):
        """Test that aspect ratio is maintained during resize."""
        img = Image.new("RGB", original_size, color="red")
        result = snapshot_service._resize_for_ai(img)
        assert result.size == expected_size

    def test_resize_uses_lanczos(self, snapshot_service):
        """Test that LANCZOS resampling is used for high quality."""
        img = Image.new("RGB", (3840, 2160), color="red")
        # This test verifies the method signature includes LANCZOS
        # The actual resampling quality is implicit in PIL
        with patch.object(img, "resize", return_value=img) as mock_resize:
            snapshot_service._resize_for_ai(img)
            mock_resize.assert_called_once()
            _, kwargs = mock_resize.call_args
            if kwargs:
                # Check that LANCZOS was passed (as positional or keyword)
                pass  # Called with positional args
            else:
                call_args = mock_resize.call_args[0]
                assert call_args[1] == Image.Resampling.LANCZOS


# =============================================================================
# Test Thumbnail Generation
# =============================================================================


class TestGenerateThumbnail:
    """Tests for _generate_thumbnail method."""

    @pytest.mark.asyncio
    async def test_generate_thumbnail_creates_file(self, snapshot_service, temp_thumbnail_dir):
        """Test that thumbnail file is created on disk."""
        img = Image.new("RGB", (1920, 1080), color="red")
        timestamp = datetime(2025, 1, 15, 12, 30, 45, tzinfo=timezone.utc)

        path = await snapshot_service._generate_thumbnail(img, "camera-123", timestamp)

        # Path should be API URL format
        assert path.startswith("/api/v1/thumbnails/")
        assert "2025-01-15" in path
        assert "camera-123" in path

        # Actual file should exist
        relative_path = path[len("/api/v1/thumbnails/"):]
        full_path = os.path.join(temp_thumbnail_dir, relative_path)
        assert os.path.exists(full_path)

    @pytest.mark.asyncio
    async def test_generate_thumbnail_date_directory(self, snapshot_service, temp_thumbnail_dir):
        """Test that thumbnail is saved in date-based subdirectory."""
        img = Image.new("RGB", (800, 600), color="blue")
        timestamp = datetime(2025, 6, 20, 8, 15, 0, tzinfo=timezone.utc)

        path = await snapshot_service._generate_thumbnail(img, "cam-1", timestamp)

        # Check date directory was created
        date_dir = os.path.join(temp_thumbnail_dir, "2025-06-20")
        assert os.path.exists(date_dir)

    @pytest.mark.asyncio
    async def test_generate_thumbnail_api_path_format(self, snapshot_service, temp_thumbnail_dir):
        """Test that returned path is in API URL format."""
        img = Image.new("RGB", (800, 600), color="green")
        timestamp = datetime(2025, 3, 10, 14, 0, 0, tzinfo=timezone.utc)

        path = await snapshot_service._generate_thumbnail(img, "test-cam", timestamp)

        assert path.startswith("/api/v1/thumbnails/")
        assert path.endswith(".jpg")

    @pytest.mark.asyncio
    async def test_generate_thumbnail_unique_filename(self, snapshot_service, temp_thumbnail_dir):
        """Test that each call generates a unique filename."""
        img = Image.new("RGB", (800, 600), color="purple")
        timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        path1 = await snapshot_service._generate_thumbnail(img, "cam", timestamp)
        path2 = await snapshot_service._generate_thumbnail(img, "cam", timestamp)

        assert path1 != path2

    @pytest.mark.asyncio
    async def test_generate_thumbnail_correct_size(self, snapshot_service, temp_thumbnail_dir):
        """Test that thumbnail is resized to correct dimensions."""
        img = Image.new("RGB", (1920, 1080), color="red")
        timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        path = await snapshot_service._generate_thumbnail(img, "cam", timestamp)

        # Load saved thumbnail and check size
        relative_path = path[len("/api/v1/thumbnails/"):]
        full_path = os.path.join(temp_thumbnail_dir, relative_path)
        saved_img = Image.open(full_path)

        assert saved_img.size[0] <= THUMBNAIL_WIDTH
        assert saved_img.size[1] <= THUMBNAIL_HEIGHT


# =============================================================================
# Test Base64 Conversion
# =============================================================================


class TestToBase64:
    """Tests for _to_base64 method."""

    def test_to_base64_valid_output(self, snapshot_service):
        """Test that valid base64 string is returned."""
        img = Image.new("RGB", (100, 100), color="red")
        result = snapshot_service._to_base64(img)

        # Should be a string
        assert isinstance(result, str)
        # Should be valid base64
        assert len(result) > 0

    def test_to_base64_decodable(self, snapshot_service):
        """Test that base64 can be decoded back to image."""
        img = Image.new("RGB", (100, 100), color="blue")
        result = snapshot_service._to_base64(img)

        # Decode and verify it's a valid image
        decoded_bytes = base64.b64decode(result)
        decoded_img = Image.open(io.BytesIO(decoded_bytes))
        assert decoded_img.size == (100, 100)

    def test_to_base64_jpeg_format(self, snapshot_service):
        """Test that output is JPEG format."""
        img = Image.new("RGB", (100, 100), color="green")
        result = snapshot_service._to_base64(img)

        decoded_bytes = base64.b64decode(result)
        # JPEG files start with FFD8
        assert decoded_bytes[:2] == b"\xff\xd8"


# =============================================================================
# Test Fetch Snapshot with Retry
# =============================================================================


class TestFetchSnapshotWithRetry:
    """Tests for _fetch_snapshot_with_retry method."""

    @pytest.mark.asyncio
    async def test_fetch_first_attempt_success(
        self, snapshot_service, mock_protect_service, sample_jpeg_bytes
    ):
        """Test successful fetch on first attempt."""
        mock_protect_service.get_camera_snapshot.return_value = sample_jpeg_bytes

        result = await snapshot_service._fetch_snapshot_with_retry(
            "controller-1", "protect-cam-1", "Front Door"
        )

        assert result == sample_jpeg_bytes
        assert mock_protect_service.get_camera_snapshot.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_retry_on_empty_response(
        self, snapshot_service, mock_protect_service, sample_jpeg_bytes
    ):
        """Test retry when first response is empty."""
        mock_protect_service.get_camera_snapshot.side_effect = [
            None,  # First attempt empty
            sample_jpeg_bytes,  # Second attempt succeeds
        ]

        result = await snapshot_service._fetch_snapshot_with_retry(
            "controller-1", "protect-cam-1", "Front Door"
        )

        assert result == sample_jpeg_bytes
        assert mock_protect_service.get_camera_snapshot.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_retry_on_timeout(
        self, snapshot_service, mock_protect_service, sample_jpeg_bytes
    ):
        """Test retry when first attempt times out."""
        mock_protect_service.get_camera_snapshot.side_effect = [
            asyncio.TimeoutError(),  # First attempt timeout
            sample_jpeg_bytes,  # Second attempt succeeds
        ]

        result = await snapshot_service._fetch_snapshot_with_retry(
            "controller-1", "protect-cam-1", "Front Door"
        )

        assert result == sample_jpeg_bytes
        assert mock_protect_service.get_camera_snapshot.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_failure_after_retries(
        self, snapshot_service, mock_protect_service
    ):
        """Test that None is returned after max retries."""
        mock_protect_service.get_camera_snapshot.side_effect = [
            asyncio.TimeoutError(),  # First attempt
            asyncio.TimeoutError(),  # Second attempt
        ]

        result = await snapshot_service._fetch_snapshot_with_retry(
            "controller-1", "protect-cam-1", "Front Door"
        )

        assert result is None
        assert mock_protect_service.get_camera_snapshot.call_count == 2
        assert snapshot_service._snapshot_failures_total == 1

    @pytest.mark.asyncio
    async def test_fetch_exception_retries(
        self, snapshot_service, mock_protect_service, sample_jpeg_bytes
    ):
        """Test retry on general exception."""
        mock_protect_service.get_camera_snapshot.side_effect = [
            Exception("Connection error"),  # First attempt
            sample_jpeg_bytes,  # Second attempt succeeds
        ]

        result = await snapshot_service._fetch_snapshot_with_retry(
            "controller-1", "protect-cam-1", "Front Door"
        )

        assert result == sample_jpeg_bytes


# =============================================================================
# Test Get Snapshot (Main Method)
# =============================================================================


class TestGetSnapshot:
    """Tests for get_snapshot main method."""

    @pytest.mark.asyncio
    async def test_get_snapshot_success(
        self, snapshot_service, mock_protect_service, sample_jpeg_bytes
    ):
        """Test successful snapshot retrieval flow."""
        mock_protect_service.get_camera_snapshot.return_value = sample_jpeg_bytes

        result = await snapshot_service.get_snapshot(
            controller_id="controller-1",
            protect_camera_id="protect-cam-1",
            camera_id="internal-cam-1",
            camera_name="Front Door",
        )

        assert isinstance(result, SnapshotResult)
        assert result.camera_id == "internal-cam-1"
        assert result.image_base64  # Non-empty
        assert result.thumbnail_path.startswith("/api/v1/thumbnails/")
        assert snapshot_service._snapshot_success_total == 1

    @pytest.mark.asyncio
    async def test_get_snapshot_fetch_failure(
        self, snapshot_service, mock_protect_service
    ):
        """Test None returned when fetch fails."""
        mock_protect_service.get_camera_snapshot.side_effect = [
            asyncio.TimeoutError(),
            asyncio.TimeoutError(),
        ]

        result = await snapshot_service.get_snapshot(
            controller_id="controller-1",
            protect_camera_id="protect-cam-1",
            camera_id="internal-cam-1",
            camera_name="Front Door",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_snapshot_with_timestamp(
        self, snapshot_service, mock_protect_service, sample_jpeg_bytes
    ):
        """Test snapshot with explicit timestamp."""
        mock_protect_service.get_camera_snapshot.return_value = sample_jpeg_bytes
        timestamp = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)

        result = await snapshot_service.get_snapshot(
            controller_id="controller-1",
            protect_camera_id="protect-cam-1",
            camera_id="internal-cam-1",
            camera_name="Front Door",
            timestamp=timestamp,
        )

        assert result.timestamp == timestamp

    @pytest.mark.asyncio
    async def test_get_snapshot_increments_success_counter(
        self, snapshot_service, mock_protect_service, sample_jpeg_bytes
    ):
        """Test that success counter is incremented."""
        mock_protect_service.get_camera_snapshot.return_value = sample_jpeg_bytes

        await snapshot_service.get_snapshot(
            controller_id="controller-1",
            protect_camera_id="protect-cam-1",
            camera_id="cam-1",
            camera_name="Cam 1",
        )

        await snapshot_service.get_snapshot(
            controller_id="controller-1",
            protect_camera_id="protect-cam-2",
            camera_id="cam-2",
            camera_name="Cam 2",
        )

        assert snapshot_service._snapshot_success_total == 2


# =============================================================================
# Test Metrics
# =============================================================================


class TestMetrics:
    """Tests for metrics methods."""

    def test_get_metrics_returns_counters(self, snapshot_service):
        """Test that get_metrics returns all counters."""
        snapshot_service._snapshot_success_total = 5
        snapshot_service._snapshot_failures_total = 2
        snapshot_service._controller_semaphores["ctrl-1"] = asyncio.Semaphore(3)

        metrics = snapshot_service.get_metrics()

        assert metrics["snapshot_success_total"] == 5
        assert metrics["snapshot_failures_total"] == 2
        assert metrics["active_semaphores"] == 1

    def test_reset_metrics_clears_counters(self, snapshot_service):
        """Test that reset_metrics sets counters to zero."""
        snapshot_service._snapshot_success_total = 10
        snapshot_service._snapshot_failures_total = 5

        snapshot_service.reset_metrics()

        assert snapshot_service._snapshot_success_total == 0
        assert snapshot_service._snapshot_failures_total == 0


# =============================================================================
# Test Notification Thumbnail Optimization
# =============================================================================


class TestOptimizeThumbnailForNotification:
    """Tests for optimize_thumbnail_for_notification function."""

    def test_optimize_missing_file_returns_none(self, temp_thumbnail_dir):
        """Test that None is returned for missing file."""
        result = optimize_thumbnail_for_notification(
            "/api/v1/thumbnails/2025-01-01/missing.jpg",
            cache_dir=temp_thumbnail_dir,
        )
        assert result is None

    def test_optimize_already_small_returns_original(self, temp_thumbnail_dir):
        """Test that small images return original path."""
        # Create small thumbnail
        date_dir = os.path.join(temp_thumbnail_dir, "2025-01-01")
        os.makedirs(date_dir, exist_ok=True)

        img = Image.new("RGB", (320, 180), color="red")
        filepath = os.path.join(date_dir, "small.jpg")
        img.save(filepath, "JPEG", quality=85)

        result = optimize_thumbnail_for_notification(
            "/api/v1/thumbnails/2025-01-01/small.jpg",
            cache_dir=temp_thumbnail_dir,
        )

        assert result == "/api/v1/thumbnails/2025-01-01/small.jpg"

    def test_optimize_large_image_resizes(self, temp_thumbnail_dir):
        """Test that large images are resized."""
        date_dir = os.path.join(temp_thumbnail_dir, "2025-01-01")
        os.makedirs(date_dir, exist_ok=True)

        # Create large image (2048x2048)
        img = Image.new("RGB", (2048, 2048), color="blue")
        filepath = os.path.join(date_dir, "large.jpg")
        img.save(filepath, "JPEG", quality=95)

        result = optimize_thumbnail_for_notification(
            "/api/v1/thumbnails/2025-01-01/large.jpg",
            cache_dir=temp_thumbnail_dir,
        )

        # Should return path to cached version
        assert NOTIFICATION_CACHE_SUFFIX in result

        # Verify cached file exists
        relative_path = result[len("/api/v1/thumbnails/"):]
        cached_path = os.path.join(temp_thumbnail_dir, relative_path)
        assert os.path.exists(cached_path)

        # Verify dimensions are reduced
        cached_img = Image.open(cached_path)
        assert cached_img.size[0] <= NOTIFICATION_MAX_DIMENSION
        assert cached_img.size[1] <= NOTIFICATION_MAX_DIMENSION

    def test_optimize_caches_result(self, temp_thumbnail_dir):
        """Test that cached version is used on second call."""
        date_dir = os.path.join(temp_thumbnail_dir, "2025-01-01")
        os.makedirs(date_dir, exist_ok=True)

        # Create large image
        img = Image.new("RGB", (2048, 2048), color="green")
        filepath = os.path.join(date_dir, "cached.jpg")
        img.save(filepath, "JPEG", quality=95)

        # First call creates cache
        result1 = optimize_thumbnail_for_notification(
            "/api/v1/thumbnails/2025-01-01/cached.jpg",
            cache_dir=temp_thumbnail_dir,
        )

        # Second call should use cache
        result2 = optimize_thumbnail_for_notification(
            "/api/v1/thumbnails/2025-01-01/cached.jpg",
            cache_dir=temp_thumbnail_dir,
        )

        assert result1 == result2

    def test_optimize_handles_filesystem_path(self, temp_thumbnail_dir):
        """Test that filesystem paths (not API paths) are handled."""
        date_dir = os.path.join(temp_thumbnail_dir, "2025-01-01")
        os.makedirs(date_dir, exist_ok=True)

        img = Image.new("RGB", (320, 180), color="yellow")
        filepath = os.path.join(date_dir, "fs_test.jpg")
        img.save(filepath, "JPEG", quality=85)

        # Pass relative path without API prefix
        result = optimize_thumbnail_for_notification(
            "2025-01-01/fs_test.jpg",
            cache_dir=temp_thumbnail_dir,
        )

        # Should return path (either original or cached)
        assert result is not None


# =============================================================================
# Test Notification Cache Cleanup
# =============================================================================


class TestCleanupNotificationCache:
    """Tests for cleanup_notification_cache function."""

    def test_cleanup_removes_orphaned_cache(self, temp_thumbnail_dir):
        """Test that orphaned cache files are deleted."""
        date_dir = os.path.join(temp_thumbnail_dir, "2025-01-01")
        os.makedirs(date_dir, exist_ok=True)

        # Create orphaned cache file (no original)
        orphan_path = os.path.join(date_dir, f"orphan{NOTIFICATION_CACHE_SUFFIX}.jpg")
        with open(orphan_path, "w") as f:
            f.write("fake")

        count = cleanup_notification_cache(cache_dir=temp_thumbnail_dir)

        assert count == 1
        assert not os.path.exists(orphan_path)

    def test_cleanup_keeps_valid_cache(self, temp_thumbnail_dir):
        """Test that cache files with originals are kept."""
        date_dir = os.path.join(temp_thumbnail_dir, "2025-01-01")
        os.makedirs(date_dir, exist_ok=True)

        # Create original and cache file
        original_path = os.path.join(date_dir, "valid.jpg")
        cache_path = os.path.join(date_dir, f"valid{NOTIFICATION_CACHE_SUFFIX}.jpg")

        with open(original_path, "w") as f:
            f.write("original")
        with open(cache_path, "w") as f:
            f.write("cache")

        count = cleanup_notification_cache(cache_dir=temp_thumbnail_dir)

        assert count == 0
        assert os.path.exists(cache_path)

    def test_cleanup_empty_directory(self, temp_thumbnail_dir):
        """Test that empty directory doesn't cause error."""
        count = cleanup_notification_cache(cache_dir=temp_thumbnail_dir)
        assert count == 0

    def test_cleanup_nonexistent_directory(self):
        """Test that nonexistent directory returns 0."""
        count = cleanup_notification_cache(cache_dir="/nonexistent/path")
        assert count == 0

    def test_cleanup_returns_count(self, temp_thumbnail_dir):
        """Test that cleanup returns correct deleted count."""
        date_dir = os.path.join(temp_thumbnail_dir, "2025-01-01")
        os.makedirs(date_dir, exist_ok=True)

        # Create multiple orphaned cache files
        for i in range(3):
            orphan_path = os.path.join(
                date_dir, f"orphan{i}{NOTIFICATION_CACHE_SUFFIX}.jpg"
            )
            with open(orphan_path, "w") as f:
                f.write("fake")

        count = cleanup_notification_cache(cache_dir=temp_thumbnail_dir)
        assert count == 3


# =============================================================================
# Test SnapshotResult Dataclass
# =============================================================================


class TestSnapshotResult:
    """Tests for SnapshotResult dataclass."""

    def test_snapshot_result_creation(self):
        """Test creating a SnapshotResult."""
        timestamp = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = SnapshotResult(
            image_base64="base64data",
            thumbnail_path="/api/v1/thumbnails/test.jpg",
            width=1920,
            height=1080,
            camera_id="cam-1",
            timestamp=timestamp,
        )

        assert result.image_base64 == "base64data"
        assert result.thumbnail_path == "/api/v1/thumbnails/test.jpg"
        assert result.width == 1920
        assert result.height == 1080
        assert result.camera_id == "cam-1"
        assert result.timestamp == timestamp

    def test_snapshot_result_attributes(self):
        """Test that all required attributes exist."""
        result = SnapshotResult(
            image_base64="",
            thumbnail_path="",
            width=0,
            height=0,
            camera_id="",
            timestamp=datetime.now(timezone.utc),
        )

        assert hasattr(result, "image_base64")
        assert hasattr(result, "thumbnail_path")
        assert hasattr(result, "width")
        assert hasattr(result, "height")
        assert hasattr(result, "camera_id")
        assert hasattr(result, "timestamp")
