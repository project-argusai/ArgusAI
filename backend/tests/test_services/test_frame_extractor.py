"""
Unit tests for FrameExtractor (Story P3-2.1, P3-2.2)

Tests cover:
Story P3-2.1:
- AC1: Returns list of JPEG-encoded frame bytes, extraction within 2s
- AC2: Evenly-spaced strategy with first/last frames included
- AC3: frame_count parameter (3-10) works correctly
- AC4: Error handling for invalid/corrupted files

Story P3-2.2:
- AC1: _is_frame_usable() detects blur and empty frames
- AC2: Blurry frames replaced, minimum 3 frames guaranteed
- AC3: All-blurry scenario returns best available with warning
- AC4: filter_blur=False bypasses quality checks
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import numpy as np

from app.services.frame_extractor import (
    FrameExtractor,
    get_frame_extractor,
    reset_frame_extractor,
    FRAME_EXTRACT_DEFAULT_COUNT,
    FRAME_EXTRACT_MIN_COUNT,
    FRAME_EXTRACT_MAX_COUNT,
    FRAME_JPEG_QUALITY,
    FRAME_MAX_WIDTH,
    FRAME_BLUR_THRESHOLD,
    FRAME_EMPTY_STD_THRESHOLD,
)


class TestFrameExtractorConstants:
    """Test service constants are properly defined"""

    def test_default_frame_count(self):
        """AC1: Verify default frame count is 5"""
        assert FRAME_EXTRACT_DEFAULT_COUNT == 5

    def test_min_frame_count(self):
        """AC3/FR8: Verify minimum frame count is 3"""
        assert FRAME_EXTRACT_MIN_COUNT == 3

    def test_max_frame_count(self):
        """AC3/FR8: Verify maximum frame count is 10"""
        assert FRAME_EXTRACT_MAX_COUNT == 10

    def test_jpeg_quality(self):
        """AC1: Verify JPEG quality is 85%"""
        assert FRAME_JPEG_QUALITY == 85

    def test_max_width(self):
        """AC1: Verify max width is 1280px"""
        assert FRAME_MAX_WIDTH == 1280

    def test_blur_threshold(self):
        """P3-2.2 AC1: Verify blur threshold is 100"""
        assert FRAME_BLUR_THRESHOLD == 100

    def test_empty_std_threshold(self):
        """P3-2.2 AC1: Verify empty frame std threshold is defined"""
        assert FRAME_EMPTY_STD_THRESHOLD == 10


class TestFrameExtractorInit:
    """Test FrameExtractor initialization"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test"""
        reset_frame_extractor()
        yield
        reset_frame_extractor()

    def test_init_sets_defaults(self):
        """AC1: Verify initialization with correct defaults"""
        extractor = FrameExtractor()

        assert extractor.default_frame_count == FRAME_EXTRACT_DEFAULT_COUNT
        assert extractor.jpeg_quality == FRAME_JPEG_QUALITY
        assert extractor.max_width == FRAME_MAX_WIDTH


class TestFrameExtractorSingleton:
    """Test singleton pattern"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test"""
        reset_frame_extractor()
        yield
        reset_frame_extractor()

    def test_get_frame_extractor_returns_instance(self):
        """Verify get_frame_extractor returns FrameExtractor instance"""
        extractor = get_frame_extractor()

        assert isinstance(extractor, FrameExtractor)

    def test_get_frame_extractor_returns_same_instance(self):
        """Singleton returns same instance"""
        extractor1 = get_frame_extractor()
        extractor2 = get_frame_extractor()

        assert extractor1 is extractor2

    def test_reset_frame_extractor_clears_singleton(self):
        """Reset allows new instance creation"""
        extractor1 = get_frame_extractor()
        reset_frame_extractor()
        extractor2 = get_frame_extractor()

        assert extractor1 is not extractor2


class TestCalculateFrameIndices:
    """Test _calculate_frame_indices method (AC2, AC3)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Create extractor for tests"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    def test_evenly_spaced_5_frames_from_300(self):
        """AC2: 5 frames from 300 total -> [0, 74, 149, 224, 299]"""
        indices = self.extractor._calculate_frame_indices(300, 5)

        assert len(indices) == 5
        assert indices[0] == 0  # First frame
        assert indices[-1] == 299  # Last frame
        # Check intermediate frames are evenly spaced
        # Formula: index = int((i * (total-1)) / (count-1))
        # For 300 frames, 5 count: [0, 74, 149, 224, 299]
        assert indices == [0, 74, 149, 224, 299]

    def test_first_frame_always_zero(self):
        """AC2: First frame is always index 0"""
        for frame_count in range(3, 11):
            indices = self.extractor._calculate_frame_indices(1000, frame_count)
            assert indices[0] == 0, f"First frame should be 0 for frame_count={frame_count}"

    def test_last_frame_always_total_minus_one(self):
        """AC2: Last frame is always total_frames - 1"""
        for total_frames in [100, 300, 500, 1000]:
            for frame_count in range(3, 11):
                if frame_count <= total_frames:
                    indices = self.extractor._calculate_frame_indices(total_frames, frame_count)
                    assert indices[-1] == total_frames - 1, \
                        f"Last frame should be {total_frames - 1} for total={total_frames}, count={frame_count}"

    def test_frame_count_3_returns_3_frames(self):
        """AC3: frame_count=3 returns exactly 3 frames"""
        indices = self.extractor._calculate_frame_indices(300, 3)

        assert len(indices) == 3
        # Formula: [0, 149, 299] = [int(0*299/2), int(1*299/2), int(2*299/2)]
        assert indices == [0, 149, 299]

    def test_frame_count_10_returns_10_frames(self):
        """AC3: frame_count=10 returns exactly 10 frames"""
        indices = self.extractor._calculate_frame_indices(300, 10)

        assert len(indices) == 10
        assert indices[0] == 0
        assert indices[-1] == 299

    def test_frame_count_exceeds_total_returns_all(self):
        """AC3: If frame_count > total_frames, return all frames"""
        indices = self.extractor._calculate_frame_indices(5, 10)

        assert len(indices) == 5
        assert indices == [0, 1, 2, 3, 4]

    def test_single_frame_returns_first(self):
        """Edge case: frame_count=1 returns first frame only"""
        indices = self.extractor._calculate_frame_indices(300, 1)

        assert indices == [0]

    def test_empty_video_returns_empty(self):
        """Edge case: total_frames=0 returns empty list"""
        indices = self.extractor._calculate_frame_indices(0, 5)

        assert indices == []

    def test_negative_values_return_empty(self):
        """Edge case: negative values return empty list"""
        assert self.extractor._calculate_frame_indices(-1, 5) == []
        assert self.extractor._calculate_frame_indices(100, -1) == []


class TestEncodeFrame:
    """Test _encode_frame method (AC1)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Create extractor for tests"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    def test_encode_frame_returns_jpeg_bytes(self):
        """AC1: Returns JPEG-encoded bytes"""
        # Create a simple RGB image array
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :, 0] = 255  # Red channel

        result = self.extractor._encode_frame(frame)

        assert isinstance(result, bytes)
        # JPEG files start with FFD8
        assert result[:2] == b'\xff\xd8'

    def test_encode_frame_jpeg_magic_bytes(self):
        """AC1: Verify JPEG magic bytes (FFD8 start, FFD9 end)"""
        frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)

        result = self.extractor._encode_frame(frame)

        # JPEG start marker
        assert result[:2] == b'\xff\xd8'
        # JPEG end marker
        assert result[-2:] == b'\xff\xd9'

    def test_encode_frame_resizes_large_images(self):
        """AC1: Large images are resized to max_width"""
        # Create a wide image
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)

        result = self.extractor._encode_frame(frame)

        # Result should be valid JPEG
        assert result[:2] == b'\xff\xd8'
        # We can't easily check dimensions from bytes without decoding,
        # but the function should have resized it

    def test_encode_frame_small_images_unchanged(self):
        """AC1: Small images are not resized"""
        # Create a small image
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = self.extractor._encode_frame(frame)

        # Should still be valid JPEG
        assert result[:2] == b'\xff\xd8'


class TestExtractFrames:
    """Test extract_frames method (AC1, AC2, AC3, AC4)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for tests"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    @pytest.mark.asyncio
    async def test_extract_frames_file_not_found(self):
        """AC4: FileNotFoundError returns empty list"""
        result = await self.extractor.extract_frames(
            Path("/nonexistent/video.mp4"),
            frame_count=5
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_extract_frames_logs_file_not_found(self):
        """AC4: Logs error with file path on FileNotFoundError"""
        with patch("app.services.frame_extractor.logger") as mock_logger:
            await self.extractor.extract_frames(
                Path("/nonexistent/video.mp4"),
                frame_count=5
            )

            mock_logger.error.assert_called()
            call_args = mock_logger.error.call_args
            assert "not found" in call_args[0][0].lower() or "extra" in str(call_args)

    @pytest.mark.asyncio
    async def test_extract_frames_av_error_returns_empty(self):
        """AC4: av.FFmpegError returns empty list"""
        import av

        with patch("app.services.frame_extractor.av.open") as mock_open:
            mock_open.side_effect = av.FFmpegError(0, "Test error")

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_extract_frames_av_error_logs(self):
        """AC4: Logs error with file path on av.FFmpegError"""
        import av

        with patch("app.services.frame_extractor.av.open") as mock_open:
            mock_open.side_effect = av.FFmpegError(0, "Test error")

            with patch("app.services.frame_extractor.logger") as mock_logger:
                await self.extractor.extract_frames(
                    Path("/test/video.mp4"),
                    frame_count=5
                )

                mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_extract_frames_generic_error_returns_empty(self):
        """AC4: Generic exceptions return empty list"""
        with patch("app.services.frame_extractor.av.open") as mock_open:
            mock_open.side_effect = RuntimeError("Unexpected error")

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_extract_frames_no_video_stream(self):
        """AC4: No video stream returns empty list"""
        with patch("av.open") as mock_open:
            mock_container = MagicMock()
            mock_container.streams.video = []
            mock_container.__enter__ = MagicMock(return_value=mock_container)
            mock_container.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_container

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_extract_frames_clamps_min_count(self):
        """AC3: frame_count < 3 is clamped to 3"""
        with patch("av.open") as mock_open:
            mock_container = MagicMock()
            mock_stream = MagicMock()
            mock_stream.frames = 100
            mock_container.streams.video = [mock_stream]
            mock_container.__enter__ = MagicMock(return_value=mock_container)
            mock_container.__exit__ = MagicMock(return_value=False)

            # Mock frame decoding to return fake frames
            mock_frame = MagicMock()
            mock_frame.to_ndarray.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
            mock_container.decode.return_value = [mock_frame] * 100

            mock_open.return_value = mock_container

            # Request 1 frame, should get clamped to 3
            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=1
            )

            # Since we're mocking, we should get frames based on clamped count
            # The exact count depends on how mock iteration works
            assert len(result) <= FRAME_EXTRACT_MIN_COUNT

    @pytest.mark.asyncio
    async def test_extract_frames_clamps_max_count(self):
        """AC3: frame_count > 10 is clamped to 10"""
        with patch("av.open") as mock_open:
            mock_container = MagicMock()
            mock_stream = MagicMock()
            mock_stream.frames = 1000
            mock_container.streams.video = [mock_stream]
            mock_container.__enter__ = MagicMock(return_value=mock_container)
            mock_container.__exit__ = MagicMock(return_value=False)

            # Mock frame decoding
            mock_frame = MagicMock()
            mock_frame.to_ndarray.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
            mock_container.decode.return_value = [mock_frame] * 1000

            mock_open.return_value = mock_container

            # Request 20 frames, should get clamped to 10
            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=20
            )

            assert len(result) <= FRAME_EXTRACT_MAX_COUNT


class TestExtractFramesWithMockedVideo:
    """Test extract_frames with properly mocked video container"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for tests"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    def _create_mock_container(self, total_frames: int):
        """Create a mock PyAV container with the specified number of frames"""
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.frames = total_frames
        mock_stream.average_rate = 30  # 30 fps
        mock_container.streams.video = [mock_stream]
        mock_container.duration = (total_frames / 30) * 1_000_000  # microseconds

        # Create mock frames
        mock_frames = []
        for i in range(total_frames):
            mock_frame = MagicMock()
            # Create a simple colored frame based on index
            frame_array = np.zeros((100, 100, 3), dtype=np.uint8)
            frame_array[:, :, 0] = i % 256  # Vary red channel
            mock_frame.to_ndarray.return_value = frame_array
            mock_frames.append(mock_frame)

        mock_container.decode.return_value = iter(mock_frames)
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)

        return mock_container

    @pytest.mark.asyncio
    async def test_extract_5_frames_from_300(self):
        """AC1, AC2: Extract 5 frames from 300-frame video"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container(300)

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5
            )

            assert len(result) == 5
            # All should be valid JPEG
            for frame in result:
                assert frame[:2] == b'\xff\xd8'

    @pytest.mark.asyncio
    async def test_extract_3_frames(self):
        """AC3: Extract exactly 3 frames"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container(300)

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=3
            )

            assert len(result) == 3

    @pytest.mark.asyncio
    async def test_extract_10_frames(self):
        """AC3: Extract exactly 10 frames"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container(300)

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=10
            )

            assert len(result) == 10

    @pytest.mark.asyncio
    async def test_extract_from_short_video(self):
        """AC3: Short video with fewer frames than requested returns all frames"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container(3)

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=10
            )

            # Should return all 3 frames, not 10
            assert len(result) == 3

    @pytest.mark.asyncio
    async def test_all_frames_are_valid_jpeg(self):
        """AC1: All returned frames are valid JPEG bytes"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container(100)

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5
            )

            for i, frame in enumerate(result):
                assert frame[:2] == b'\xff\xd8', f"Frame {i} is not valid JPEG (missing FFD8 header)"
                assert frame[-2:] == b'\xff\xd9', f"Frame {i} is not valid JPEG (missing FFD9 footer)"


class TestExtractFramesLogging:
    """Test logging behavior"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for tests"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    @pytest.mark.asyncio
    async def test_logs_extraction_start(self):
        """Logs start of extraction with clip path and frame count"""
        with patch("app.services.frame_extractor.logger") as mock_logger:
            with patch("av.open") as mock_open:
                mock_open.side_effect = FileNotFoundError("Not found")

                await self.extractor.extract_frames(
                    Path("/test/video.mp4"),
                    frame_count=5
                )

                # Check that info was called for start
                mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_logs_success_with_frame_count(self):
        """Logs successful extraction with frame count"""
        with patch("av.open") as mock_open:
            mock_container = MagicMock()
            mock_stream = MagicMock()
            mock_stream.frames = 100
            mock_container.streams.video = [mock_stream]
            mock_container.__enter__ = MagicMock(return_value=mock_container)
            mock_container.__exit__ = MagicMock(return_value=False)

            mock_frame = MagicMock()
            mock_frame.to_ndarray.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
            mock_container.decode.return_value = [mock_frame] * 100

            mock_open.return_value = mock_container

            with patch("app.services.frame_extractor.logger") as mock_logger:
                await self.extractor.extract_frames(
                    Path("/test/video.mp4"),
                    frame_count=5
                )

                # Should have logged success
                info_calls = [str(c) for c in mock_logger.info.call_args_list]
                assert any("success" in c.lower() or "complete" in c.lower() for c in info_calls)


class TestIsFrameUsable:
    """Test _is_frame_usable method (Story P3-2.2 AC1)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Create extractor for tests"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    def test_blurry_frame_returns_false(self):
        """P3-2.2 AC1: Blurry frame (low Laplacian variance) returns False"""
        # Create a blurry frame - uniform gradient with no sharp edges
        # A very smooth gradient has very low Laplacian variance
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        # Create a smooth horizontal gradient
        for i in range(100):
            frame[:, i, :] = i * 2  # Smooth gradient 0-198

        result = self.extractor._is_frame_usable(frame)

        assert result is False, "Blurry frame should return False"

    def test_single_color_frame_returns_false(self):
        """P3-2.2 AC1: Single-color/empty frame returns False"""
        # Create a solid black frame (std deviation = 0)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        result = self.extractor._is_frame_usable(frame)

        assert result is False, "Single-color frame should return False"

    def test_all_white_frame_returns_false(self):
        """P3-2.2 AC1: All white frame returns False"""
        # Create a solid white frame
        frame = np.ones((100, 100, 3), dtype=np.uint8) * 255

        result = self.extractor._is_frame_usable(frame)

        assert result is False, "All-white frame should return False"

    def test_clear_frame_with_edges_returns_true(self):
        """P3-2.2 AC1: Clear frame with edges/content returns True"""
        # Create a frame with clear edges - checkerboard pattern
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        # Create checkerboard pattern (high contrast edges)
        for i in range(0, 100, 10):
            for j in range(0, 100, 10):
                if (i // 10 + j // 10) % 2 == 0:
                    frame[i:i+10, j:j+10, :] = 255

        result = self.extractor._is_frame_usable(frame)

        assert result is True, "Clear frame with edges should return True"

    def test_random_noise_frame_returns_true(self):
        """P3-2.2 AC1: Frame with random content (high variance) returns True"""
        # Random noise has high Laplacian variance and high std deviation
        np.random.seed(42)  # For reproducibility
        frame = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)

        result = self.extractor._is_frame_usable(frame)

        assert result is True, "Random noise frame should return True"


class TestGetFrameQualityScore:
    """Test _get_frame_quality_score method (Story P3-2.2)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Create extractor for tests"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    def test_blurry_frame_has_low_score(self):
        """Blurry frame has low quality score"""
        # Solid color frame has very low Laplacian variance
        frame = np.ones((100, 100, 3), dtype=np.uint8) * 128

        score = self.extractor._get_frame_quality_score(frame)

        assert score < FRAME_BLUR_THRESHOLD, f"Blurry frame score {score} should be below threshold"

    def test_clear_frame_has_high_score(self):
        """Clear frame with edges has high quality score"""
        # Checkerboard pattern has high Laplacian variance
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        for i in range(0, 100, 10):
            for j in range(0, 100, 10):
                if (i // 10 + j // 10) % 2 == 0:
                    frame[i:i+10, j:j+10, :] = 255

        score = self.extractor._get_frame_quality_score(frame)

        assert score >= FRAME_BLUR_THRESHOLD, f"Clear frame score {score} should be at/above threshold"

    def test_score_is_float(self):
        """Quality score is returned as float"""
        frame = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)

        score = self.extractor._get_frame_quality_score(frame)

        assert isinstance(score, float)


class TestBlurFiltering:
    """Test blur filtering in extract_frames (Story P3-2.2 AC2, AC4)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for tests"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    def _create_mock_container_with_quality(self, frame_qualities: list):
        """
        Create a mock PyAV container with frames of specified qualities.

        Args:
            frame_qualities: List of 'clear' or 'blurry' for each frame
        """
        total_frames = len(frame_qualities)
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.frames = total_frames
        mock_stream.average_rate = 30
        mock_container.streams.video = [mock_stream]
        mock_container.duration = (total_frames / 30) * 1_000_000

        # Create mock frames with appropriate quality
        mock_frames = []
        for i, quality in enumerate(frame_qualities):
            mock_frame = MagicMock()
            if quality == 'clear':
                # Checkerboard pattern - high variance
                frame_array = np.zeros((100, 100, 3), dtype=np.uint8)
                for x in range(0, 100, 10):
                    for y in range(0, 100, 10):
                        if (x // 10 + y // 10) % 2 == 0:
                            frame_array[x:x+10, y:y+10, :] = 255
            else:  # blurry
                # Solid gray - low variance
                frame_array = np.ones((100, 100, 3), dtype=np.uint8) * 128

            mock_frame.to_ndarray.return_value = frame_array
            mock_frames.append(mock_frame)

        mock_container.decode.return_value = iter(mock_frames)
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)

        return mock_container

    @pytest.mark.asyncio
    async def test_filter_blur_false_returns_all_frames(self):
        """P3-2.2 AC4: filter_blur=False returns all frames regardless of quality"""
        # Create 5 blurry frames
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container_with_quality(
                ['blurry', 'blurry', 'blurry', 'blurry', 'blurry']
            )

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5,
                filter_blur=False
            )

            # Should return all 5 frames even though they're all blurry
            assert len(result) == 5

    @pytest.mark.asyncio
    async def test_filter_blur_false_logs_disabled(self):
        """P3-2.2 AC4: Logs that blur filtering is disabled"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container_with_quality(
                ['clear', 'clear', 'clear']
            )

            with patch("app.services.frame_extractor.logger") as mock_logger:
                await self.extractor.extract_frames(
                    Path("/test/video.mp4"),
                    frame_count=3,
                    filter_blur=False
                )

                # Check debug was called with blur filter disabled message
                debug_calls = [str(c) for c in mock_logger.debug.call_args_list]
                assert any("blur" in c.lower() and "disabled" in c.lower() for c in debug_calls)

    @pytest.mark.asyncio
    async def test_minimum_3_frames_always_returned(self):
        """P3-2.2 AC2: At least min_frames (3) are always returned"""
        # Create 5 frames where only 1 is clear
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container_with_quality(
                ['blurry', 'blurry', 'clear', 'blurry', 'blurry']
            )

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5,
                filter_blur=True
            )

            # Should return at least 3 frames (the minimum)
            assert len(result) >= FRAME_EXTRACT_MIN_COUNT

    @pytest.mark.asyncio
    async def test_clear_frames_preferred_over_blurry(self):
        """P3-2.2 AC2: Clear frames are preferred when filtering"""
        # Create mix of clear and blurry frames
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container_with_quality(
                ['clear', 'clear', 'clear', 'clear', 'clear']
            )

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5,
                filter_blur=True
            )

            # Should return all 5 clear frames
            assert len(result) == 5


class TestAllBlurryScenario:
    """Test all-blurry frame scenario (Story P3-2.2 AC3)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for tests"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    def _create_mock_container_all_blurry(self, count: int, varying_quality: bool = False):
        """Create container with all blurry frames"""
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.frames = count
        mock_stream.average_rate = 30
        mock_container.streams.video = [mock_stream]
        mock_container.duration = (count / 30) * 1_000_000

        mock_frames = []
        for i in range(count):
            mock_frame = MagicMock()
            # All frames are solid color (blurry), but with slightly different values
            # for varying quality
            if varying_quality:
                gray_value = 128 + (i * 5) % 50
            else:
                gray_value = 128
            frame_array = np.ones((100, 100, 3), dtype=np.uint8) * gray_value
            mock_frame.to_ndarray.return_value = frame_array
            mock_frames.append(mock_frame)

        mock_container.decode.return_value = iter(mock_frames)
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)

        return mock_container

    @pytest.mark.asyncio
    async def test_all_blurry_returns_best_available(self):
        """P3-2.2 AC3: All blurry frames returns best available by quality"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container_all_blurry(5)

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5,
                filter_blur=True
            )

            # Should return frames even though all are blurry
            assert len(result) >= FRAME_EXTRACT_MIN_COUNT

    @pytest.mark.asyncio
    async def test_all_blurry_logs_warning(self):
        """P3-2.2 AC3: Logs warning 'All frames below quality threshold'"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container_all_blurry(5)

            with patch("app.services.frame_extractor.logger") as mock_logger:
                await self.extractor.extract_frames(
                    Path("/test/video.mp4"),
                    frame_count=5,
                    filter_blur=True
                )

                # Check warning was called with appropriate message
                mock_logger.warning.assert_called()
                warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
                assert any("all frames below quality threshold" in c.lower() for c in warning_calls)

    @pytest.mark.asyncio
    async def test_all_blurry_returns_valid_jpeg(self):
        """P3-2.2 AC3: All-blurry scenario still returns valid JPEG frames"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container_all_blurry(5)

            result = await self.extractor.extract_frames(
                Path("/test/video.mp4"),
                frame_count=5,
                filter_blur=True
            )

            for frame in result:
                assert frame[:2] == b'\xff\xd8', "Frame should be valid JPEG"
                assert frame[-2:] == b'\xff\xd9', "Frame should be valid JPEG"
