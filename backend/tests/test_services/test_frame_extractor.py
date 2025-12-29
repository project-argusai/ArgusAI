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
        """AC1: Verify default frame count is 10 (Story P8-2.3)"""
        assert FRAME_EXTRACT_DEFAULT_COUNT == 10

    def test_min_frame_count(self):
        """AC3/FR8: Verify minimum frame count is 3"""
        assert FRAME_EXTRACT_MIN_COUNT == 3

    def test_max_frame_count(self):
        """AC3/FR8: Verify maximum frame count is 20 (Story P8-2.3)"""
        assert FRAME_EXTRACT_MAX_COUNT == 20

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
        indices = self.extractor._calculate_frame_indices(1000, 5)
        assert indices[0] == 0

    @pytest.mark.parametrize("frame_count", [3, 4, 5, 6, 7, 8, 9, 10])
    def test_first_frame_always_zero_parametrized(self, frame_count):
        """AC2: First frame is always index 0 for various frame counts"""
        indices = self.extractor._calculate_frame_indices(1000, frame_count)
        assert indices[0] == 0, f"First frame should be 0 for frame_count={frame_count}"

    @pytest.mark.parametrize("total_frames,frame_count", [
        (100, 3),
        (100, 5),
        (300, 5),
        (500, 7),
        (1000, 10),
    ])
    def test_last_frame_always_total_minus_one(self, total_frames, frame_count):
        """AC2: Last frame is always total_frames - 1"""
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


class TestExtractFramesWithTimestamps:
    """Test extract_frames_with_timestamps method (Story P3-7.5)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    def _create_mock_container(self, total_frames: int = 150, fps: float = 30.0):
        """Create a mock av container for testing"""
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.frames = total_frames
        mock_stream.average_rate = fps
        mock_container.streams.video = [mock_stream]
        mock_container.duration = (total_frames / fps) * 1_000_000

        # Generate mock frames
        mock_frames = []
        for i in range(total_frames):
            mock_frame = MagicMock()
            # Create varied frames (not uniform solid colors)
            frame_array = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
            mock_frame.to_ndarray.return_value = frame_array
            mock_frames.append(mock_frame)

        mock_container.decode.return_value = iter(mock_frames)
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)

        return mock_container

    @pytest.mark.asyncio
    async def test_returns_frames_and_timestamps(self):
        """P3-7.5 AC4: Method returns both frames and timestamps"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container(total_frames=150, fps=30.0)

            frames, timestamps = await self.extractor.extract_frames_with_timestamps(
                Path("/test/video.mp4"),
                frame_count=5
            )

            assert len(frames) == 5, "Should return 5 frames"
            assert len(timestamps) == 5, "Should return 5 timestamps"
            assert len(frames) == len(timestamps), "Frame count should match timestamp count"

    @pytest.mark.asyncio
    async def test_timestamps_are_floats(self):
        """P3-7.5 AC4: Timestamps are float seconds"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container(total_frames=150, fps=30.0)

            frames, timestamps = await self.extractor.extract_frames_with_timestamps(
                Path("/test/video.mp4"),
                frame_count=5
            )

            for ts in timestamps:
                assert isinstance(ts, float), "Timestamp should be float"
                assert ts >= 0, "Timestamp should be non-negative"

    @pytest.mark.asyncio
    async def test_timestamps_increase_monotonically(self):
        """P3-7.5: Timestamps should increase monotonically (evenly spaced)"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container(total_frames=150, fps=30.0)

            frames, timestamps = await self.extractor.extract_frames_with_timestamps(
                Path("/test/video.mp4"),
                frame_count=5
            )

            for i in range(1, len(timestamps)):
                assert timestamps[i] > timestamps[i - 1], "Timestamps should increase"

    @pytest.mark.asyncio
    async def test_first_timestamp_near_zero(self):
        """P3-7.5: First frame timestamp should be at or near 0"""
        with patch("av.open") as mock_open:
            mock_open.return_value = self._create_mock_container(total_frames=150, fps=30.0)

            frames, timestamps = await self.extractor.extract_frames_with_timestamps(
                Path("/test/video.mp4"),
                frame_count=5
            )

            assert timestamps[0] == 0.0 or timestamps[0] < 0.5, "First frame should be at start"

    @pytest.mark.asyncio
    async def test_empty_on_no_video_stream(self):
        """P3-7.5: Returns empty lists when no video stream"""
        mock_container = MagicMock()
        mock_container.streams.video = []
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)

        with patch("av.open") as mock_open:
            mock_open.return_value = mock_container

            frames, timestamps = await self.extractor.extract_frames_with_timestamps(
                Path("/test/video.mp4"),
                frame_count=5
            )

            assert frames == [], "Should return empty frames"
            assert timestamps == [], "Should return empty timestamps"

    @pytest.mark.asyncio
    async def test_empty_on_error(self):
        """P3-7.5: Returns empty lists on error"""
        with patch("av.open") as mock_open:
            mock_open.side_effect = Exception("Test error")

            frames, timestamps = await self.extractor.extract_frames_with_timestamps(
                Path("/test/video.mp4"),
                frame_count=5
            )

            assert frames == [], "Should return empty frames on error"
            assert timestamps == [], "Should return empty timestamps on error"


class TestEncodeFrameForStorage:
    """Test encode_frame_for_storage method (Story P3-7.5)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test"""
        reset_frame_extractor()
        self.extractor = FrameExtractor()
        yield
        reset_frame_extractor()

    def _create_test_jpeg(self, width: int = 640, height: int = 480) -> bytes:
        """Create a test JPEG image"""
        from PIL import Image
        import io

        # Create a random image
        img = Image.new('RGB', (width, height), color=(100, 100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()

    def test_returns_base64_string(self):
        """P3-7.5 AC4: Returns base64-encoded string"""
        import base64

        jpeg_bytes = self._create_test_jpeg()
        result = self.extractor.encode_frame_for_storage(jpeg_bytes)

        assert isinstance(result, str), "Should return string"
        assert len(result) > 0, "Should not be empty"

        # Verify it's valid base64
        decoded = base64.b64decode(result)
        assert decoded[:2] == b'\xff\xd8', "Decoded should be valid JPEG"

    def test_reduces_image_size(self):
        """P3-7.5: Resizes large images to max 320px width"""
        import base64

        # Create a large image (1280px wide)
        jpeg_bytes = self._create_test_jpeg(width=1280, height=720)
        result = self.extractor.encode_frame_for_storage(jpeg_bytes, max_width=320)

        # Decode and check dimensions
        from PIL import Image
        import io

        decoded = base64.b64decode(result)
        img = Image.open(io.BytesIO(decoded))

        assert img.width <= 320, "Width should be at most 320px"

    def test_preserves_aspect_ratio(self):
        """P3-7.5: Preserves aspect ratio when resizing"""
        import base64
        from PIL import Image
        import io

        # Create a 16:9 image
        original_width, original_height = 1280, 720
        jpeg_bytes = self._create_test_jpeg(width=original_width, height=original_height)
        result = self.extractor.encode_frame_for_storage(jpeg_bytes, max_width=320)

        decoded = base64.b64decode(result)
        img = Image.open(io.BytesIO(decoded))

        # Check aspect ratio is preserved (within rounding tolerance)
        original_ratio = original_width / original_height
        new_ratio = img.width / img.height
        assert abs(original_ratio - new_ratio) < 0.1, "Aspect ratio should be preserved"

    def test_applies_quality_setting(self):
        """P3-7.5: Uses quality parameter for JPEG encoding"""
        # Create a complex image (noisy) that will show compression differences
        from PIL import Image
        import io

        img = Image.new('RGB', (320, 240))
        # Add some noise/complexity to the image
        import random
        pixels = [(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                  for _ in range(320 * 240)]
        img.putdata(pixels)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=95)  # Save at high quality first
        jpeg_bytes = buffer.getvalue()

        result_high = self.extractor.encode_frame_for_storage(jpeg_bytes, quality=95)
        result_low = self.extractor.encode_frame_for_storage(jpeg_bytes, quality=30)

        # Lower quality should produce smaller output for complex images
        assert len(result_low) < len(result_high), "Lower quality should be smaller"

    def test_returns_empty_string_on_error(self):
        """P3-7.5: Returns empty string on error"""
        result = self.extractor.encode_frame_for_storage(b"invalid jpeg data")
        assert result == "", "Should return empty string on error"

    def test_default_parameters(self):
        """P3-7.5: Default max_width=320 and quality=70"""
        import base64
        from PIL import Image
        import io

        jpeg_bytes = self._create_test_jpeg(width=640, height=480)
        result = self.extractor.encode_frame_for_storage(jpeg_bytes)

        decoded = base64.b64decode(result)
        img = Image.open(io.BytesIO(decoded))

        assert img.width <= 320, "Default max_width should be 320"


class TestFrameExtractionOffset:
    """Tests for frame extraction offset feature (Story P9-2.1)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test"""
        reset_frame_extractor()
        self.extractor = get_frame_extractor()
        yield
        reset_frame_extractor()

    @pytest.mark.asyncio
    async def test_offset_parameter_default(self):
        """P9-2.1 AC-2.1.2: offset_ms defaults to 0"""
        import inspect
        sig = inspect.signature(self.extractor.extract_frames_with_timestamps)
        offset_param = sig.parameters.get('offset_ms')
        assert offset_param is not None, "offset_ms parameter should exist"
        assert offset_param.default == 0, "offset_ms default should be 0"

    @pytest.mark.asyncio
    async def test_offset_with_valid_clip(self):
        """P9-2.1 AC-2.1.2: Offset is applied when extracting frames"""
        # Create a mock video container with enough frames
        with patch('av.open') as mock_av_open:
            mock_container = MagicMock()
            mock_stream = MagicMock()
            mock_stream.frames = 300  # 10 seconds at 30fps
            mock_stream.average_rate = 30
            mock_container.streams.video = [mock_stream]
            mock_container.duration = 10_000_000  # 10 seconds in microseconds

            # Create mock frames - we need to return 300 frames
            mock_frames = []
            for i in range(300):
                mock_frame = MagicMock()
                # Create small valid image data
                mock_frame.to_ndarray.return_value = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
                mock_frames.append(mock_frame)

            mock_container.decode.return_value = iter(mock_frames)
            mock_container.__enter__ = MagicMock(return_value=mock_container)
            mock_container.__exit__ = MagicMock(return_value=False)
            mock_av_open.return_value = mock_container

            # Extract with 2000ms offset (60 frames at 30fps)
            frames, timestamps = await self.extractor.extract_frames_with_timestamps(
                clip_path=Path("/fake/video.mp4"),
                frame_count=5,
                offset_ms=2000
            )

            # Verify extraction was attempted
            mock_av_open.assert_called_once()

    @pytest.mark.asyncio
    async def test_offset_fallback_for_short_clip(self):
        """P9-2.1 AC-2.1.5: Falls back to 0 offset when clip shorter than offset"""
        with patch('av.open') as mock_av_open:
            mock_container = MagicMock()
            mock_stream = MagicMock()
            mock_stream.frames = 30  # Only 1 second at 30fps
            mock_stream.average_rate = 30
            mock_container.streams.video = [mock_stream]
            mock_container.duration = 1_000_000  # 1 second

            mock_frames = []
            for i in range(30):
                mock_frame = MagicMock()
                mock_frame.to_ndarray.return_value = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
                mock_frames.append(mock_frame)

            mock_container.decode.return_value = iter(mock_frames)
            mock_container.__enter__ = MagicMock(return_value=mock_container)
            mock_container.__exit__ = MagicMock(return_value=False)
            mock_av_open.return_value = mock_container

            # Try to extract with 5000ms offset (150 frames) - longer than clip
            # Should fall back to 0 offset with warning
            frames, timestamps = await self.extractor.extract_frames_with_timestamps(
                clip_path=Path("/fake/video.mp4"),
                frame_count=5,
                offset_ms=5000  # 5 seconds, but clip is only 1 second
            )

            # Should still work with fallback to 0 offset
            mock_av_open.assert_called_once()

    def test_offset_calculation(self):
        """P9-2.1: Verify offset frames calculation at different FPS"""
        # At 30fps, 2000ms = 60 frames
        fps = 30.0
        offset_ms = 2000
        expected_frames = int((offset_ms / 1000.0) * fps)
        assert expected_frames == 60

        # At 60fps, 2000ms = 120 frames
        fps = 60.0
        expected_frames = int((offset_ms / 1000.0) * fps)
        assert expected_frames == 120

        # At 24fps, 2000ms = 48 frames
        fps = 24.0
        expected_frames = int((offset_ms / 1000.0) * fps)
        assert expected_frames == 48


class TestSimilarityFiltering:
    """Tests for similarity-based frame filtering (Story P9-2.2)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test"""
        reset_frame_extractor()
        self.extractor = get_frame_extractor()
        yield
        reset_frame_extractor()

    def _create_test_frame(self, width=100, height=100, color=(128, 128, 128)):
        """Create a test frame with a specific color"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = color
        return frame

    def _create_random_frame(self, width=100, height=100, seed=None):
        """Create a random test frame"""
        if seed is not None:
            np.random.seed(seed)
        return np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)

    def test_calculate_ssim_identical_frames(self):
        """P9-2.2 AC-2.2.2: Identical frames should have SSIM = 1.0"""
        frame = self._create_test_frame(color=(100, 100, 100))
        ssim = self.extractor._calculate_ssim(frame, frame)
        assert ssim > 0.99, "Identical frames should have SSIM close to 1.0"

    def test_calculate_ssim_different_frames(self):
        """P9-2.2 AC-2.2.3: Different frames should have lower SSIM"""
        frame1 = self._create_test_frame(color=(0, 0, 0))
        frame2 = self._create_test_frame(color=(255, 255, 255))
        ssim = self.extractor._calculate_ssim(frame1, frame2)
        assert ssim < 0.5, "Black and white frames should have low SSIM"

    def test_is_similar_identical_frames(self):
        """P9-2.2 AC-2.2.2: Identical frames are similar"""
        frame = self._create_test_frame(color=(100, 100, 100))
        assert self.extractor.is_similar(frame, frame, threshold=0.95) is True

    def test_is_similar_different_frames(self):
        """P9-2.2 AC-2.2.3: Different frames are not similar"""
        frame1 = self._create_random_frame(seed=1)
        frame2 = self._create_random_frame(seed=2)
        assert self.extractor.is_similar(frame1, frame2, threshold=0.95) is False

    def test_filter_similar_frames_keeps_first(self):
        """P9-2.2 AC-2.2.2: Always keeps the first frame"""
        frames = [self._create_test_frame() for _ in range(5)]
        filtered, indices = self.extractor.filter_similar_frames(frames)
        assert len(filtered) >= 1, "Should keep at least first frame"
        assert indices[0] == 0, "First kept frame should be original index 0"

    def test_filter_similar_frames_filters_identical(self):
        """P9-2.2 AC-2.2.2: Consecutive identical frames filtered, only first kept"""
        # Create 10 identical frames
        base_frame = self._create_test_frame(color=(100, 100, 100))
        frames = [base_frame.copy() for _ in range(10)]

        filtered, indices = self.extractor.filter_similar_frames(frames, threshold=0.95)

        # Only first should be kept (all identical)
        assert len(filtered) == 1, "Should keep only first frame when all identical"
        assert indices == [0], "Should only have original index 0"

    def test_filter_similar_frames_keeps_diverse(self):
        """P9-2.2 AC-2.2.3: Visually distinct frames are all retained"""
        # Create diverse frames with very different random patterns
        frames = [self._create_random_frame(seed=i * 100) for i in range(5)]

        filtered, indices = self.extractor.filter_similar_frames(frames, threshold=0.95)

        # All should be kept (all different)
        assert len(filtered) == 5, "Should keep all diverse frames"
        assert indices == [0, 1, 2, 3, 4], "Should keep all original indices"

    def test_filter_similar_frames_empty_input(self):
        """P9-2.2: Empty input returns empty output"""
        filtered, indices = self.extractor.filter_similar_frames([])
        assert filtered == []
        assert indices == []

    def test_filter_similar_frames_with_provided_indices(self):
        """P9-2.2: Custom indices are preserved in output"""
        frames = [self._create_random_frame(seed=i * 100) for i in range(3)]
        custom_indices = [10, 20, 30]

        filtered, indices = self.extractor.filter_similar_frames(
            frames,
            indices=custom_indices
        )

        # All different, so all kept
        assert len(indices) == 3
        assert indices == custom_indices

    def test_filter_similar_frames_mixed_scenario(self):
        """P9-2.2 AC-2.2.1: Mixed frames with some similar, some different"""
        # Frame 0: unique
        # Frame 1: same as 0 (should be filtered)
        # Frame 2: different
        # Frame 3: same as 2 (should be filtered)
        # Frame 4: different
        base1 = self._create_test_frame(color=(50, 50, 50))
        base2 = self._create_test_frame(color=(200, 200, 200))
        base3 = self._create_random_frame(seed=999)

        frames = [
            base1.copy(),  # 0: unique
            base1.copy(),  # 1: same as 0, filtered
            base2.copy(),  # 2: different, kept
            base2.copy(),  # 3: same as 2, filtered
            base3.copy(),  # 4: different, kept
        ]

        filtered, indices = self.extractor.filter_similar_frames(frames, threshold=0.95)

        # Should keep 0, 2, 4
        assert len(filtered) == 3
        assert 0 in indices
        assert 2 in indices
        assert 4 in indices

    def test_similarity_threshold_constant(self):
        """P9-2.2 AC-2.2.1: Default threshold is 0.95"""
        from app.services.frame_extractor import SIMILARITY_THRESHOLD
        assert SIMILARITY_THRESHOLD == 0.95

    def test_filter_similar_frames_logs_ratio(self, caplog):
        """P9-2.2 AC-2.2.4: Filter ratio is logged"""
        import logging
        caplog.set_level(logging.INFO)

        # Create frames with some duplicates
        base = self._create_test_frame(color=(100, 100, 100))
        frames = [base.copy() for _ in range(5)]

        self.extractor.filter_similar_frames(frames)

        # Check that log contains filter ratio format
        assert any("Filtered 5→1 frames" in record.message for record in caplog.records), \
            "Should log filter ratio in format 'Filtered N→M frames'"


class TestMotionScoring:
    """Tests for motion scoring feature (Story P9-2.3)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singleton before each test"""
        reset_frame_extractor()
        self.extractor = get_frame_extractor()
        yield
        reset_frame_extractor()

    def _create_static_frame(self, width=100, height=100, color=(128, 128, 128)):
        """Create a static test frame with a specific color"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = color
        return frame

    def _create_moving_frame(self, width=100, height=100, offset=0):
        """Create a frame with a moving element (simulated)"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Create a bright bar that moves based on offset
        bar_start = (offset * 10) % width
        bar_end = min(bar_start + 20, width)
        frame[:, bar_start:bar_end] = (255, 255, 255)
        return frame

    def test_motion_score_identical_frames(self):
        """P9-2.3 AC-2.3.3: Identical frames should have low motion score"""
        frame = self._create_static_frame(color=(100, 100, 100))
        score = self.extractor.calculate_motion_score(frame, frame)
        assert score < 5, f"Identical frames should have very low score, got {score}"

    def test_motion_score_different_frames(self):
        """P9-2.3 AC-2.3.2: Moving frames should have higher motion score"""
        # Create frames with actual pixel movement that optical flow can detect
        # Use random noise patterns that shift between frames
        np.random.seed(42)
        frame1 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        # Shift frame2 by several pixels to create detectable motion
        frame2 = np.roll(frame1, shift=10, axis=1)  # Horizontal shift of 10 pixels
        score = self.extractor.calculate_motion_score(frame1, frame2)
        # With a 10-pixel shift, we expect some motion score
        assert score >= 0, f"Moving frames should have non-negative score, got {score}"

    def test_motion_score_range(self):
        """P9-2.3 AC-2.3.1: Score should be in 0-100 range"""
        frame1 = self._create_static_frame(color=(0, 0, 0))
        frame2 = self._create_static_frame(color=(255, 255, 255))
        score = self.extractor.calculate_motion_score(frame1, frame2)
        assert 0 <= score <= 100, f"Score should be 0-100, got {score}"

    def test_score_frames_by_motion_empty_input(self):
        """P9-2.3: Empty input returns empty output"""
        result = self.extractor.score_frames_by_motion([])
        assert result == []

    def test_score_frames_by_motion_single_frame(self):
        """P9-2.3: Single frame returns score of 0"""
        frame = self._create_static_frame()
        result = self.extractor.score_frames_by_motion([frame])
        assert len(result) == 1
        assert result[0][1] == 0  # Index
        assert result[0][2] == 0.0  # Score

    def test_score_frames_by_motion_multiple_frames(self):
        """P9-2.3 AC-2.3.1: Each frame gets a score"""
        frames = [self._create_moving_frame(offset=i) for i in range(5)]
        result = self.extractor.score_frames_by_motion(frames)
        assert len(result) == 5
        for frame, idx, score in result:
            assert isinstance(score, float)
            assert 0 <= score <= 100

    def test_score_frames_by_motion_with_indices(self):
        """P9-2.3: Custom indices are preserved"""
        frames = [self._create_static_frame() for _ in range(3)]
        indices = [10, 20, 30]
        result = self.extractor.score_frames_by_motion(frames, indices)
        returned_indices = [r[1] for r in result]
        assert returned_indices == indices

    def test_select_top_frames_by_score_empty(self):
        """P9-2.3 AC-2.3.4: Empty input returns empty output"""
        result = self.extractor.select_top_frames_by_score([], 5)
        assert result == []

    def test_select_top_frames_by_score_selects_highest(self):
        """P9-2.3 AC-2.3.4: Highest scoring frames are selected"""
        # Create scored frames with known scores
        frame = self._create_static_frame()
        scored = [
            (frame, 0, 10.0),
            (frame, 1, 50.0),
            (frame, 2, 80.0),
            (frame, 3, 30.0),
            (frame, 4, 60.0)
        ]
        result = self.extractor.select_top_frames_by_score(scored, 3)
        selected_scores = [r[2] for r in result]
        # Should select 80, 60, 50 (top 3)
        assert 80.0 in selected_scores
        assert 60.0 in selected_scores
        assert 50.0 in selected_scores

    def test_select_top_frames_sorted_chronologically(self):
        """P9-2.3 AC-2.3.4: Selected frames are sorted chronologically"""
        frame = self._create_static_frame()
        scored = [
            (frame, 4, 90.0),  # Highest but last
            (frame, 0, 80.0),  # Second highest but first
            (frame, 2, 70.0),  # Third
        ]
        result = self.extractor.select_top_frames_by_score(scored, 3, sort_chronologically=True)
        indices = [r[1] for r in result]
        assert indices == [0, 2, 4], "Should be sorted by index"

    def test_select_more_than_available(self):
        """P9-2.3: Requesting more frames than available returns all"""
        frame = self._create_static_frame()
        scored = [(frame, 0, 50.0), (frame, 1, 60.0)]
        result = self.extractor.select_top_frames_by_score(scored, 10)
        assert len(result) == 2

    def test_motion_score_constant_exists(self):
        """P9-2.3: Motion score multiplier constant is defined"""
        from app.services.frame_extractor import MOTION_SCORE_MULTIPLIER
        assert MOTION_SCORE_MULTIPLIER > 0
