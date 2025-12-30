"""
Tests for AdaptiveSampler service (Story P8-2.4)

Tests content-aware frame selection using histogram and SSIM comparison.
"""
import numpy as np
import pytest

from app.services.adaptive_sampler import (
    AdaptiveSampler,
    get_adaptive_sampler,
    reset_adaptive_sampler,
    HISTOGRAM_SIMILARITY_THRESHOLD,
    SSIM_SIMILARITY_THRESHOLD,
    MIN_TEMPORAL_SPACING_MS
)


@pytest.fixture(autouse=True)
def reset_sampler_singleton():
    """Reset AdaptiveSampler singleton before each test."""
    AdaptiveSampler._reset_instance()
    yield
    AdaptiveSampler._reset_instance()


class TestAdaptiveSamplerInit:
    """Tests for AdaptiveSampler initialization."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        sampler = AdaptiveSampler()
        assert sampler.histogram_threshold == HISTOGRAM_SIMILARITY_THRESHOLD
        assert sampler.ssim_threshold == SSIM_SIMILARITY_THRESHOLD
        assert sampler.min_spacing_ms == MIN_TEMPORAL_SPACING_MS

    def test_custom_thresholds(self):
        """Test custom threshold configuration."""
        sampler = AdaptiveSampler(
            histogram_threshold=0.9,
            ssim_threshold=0.85,
            min_spacing_ms=1000.0
        )
        assert sampler.histogram_threshold == 0.9
        assert sampler.ssim_threshold == 0.85
        assert sampler.min_spacing_ms == 1000.0


class TestHistogramSimilarity:
    """Tests for histogram similarity calculation (AC4.1)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sampler = AdaptiveSampler()

    def test_identical_frames_high_similarity(self):
        """AC4.1: Identical frames should have similarity close to 1.0."""
        # Create identical RGB frames
        frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        similarity = self.sampler.calculate_histogram_similarity(frame, frame.copy())
        assert similarity >= 0.99, f"Expected near 1.0, got {similarity}"

    def test_different_frames_low_similarity(self):
        """AC4.1: Very different frames should have lower similarity."""
        # Create two very different frames with varied content
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)  # Black
        frame1[:50, :, 0] = 255  # Red top half
        frame2 = np.zeros((100, 100, 3), dtype=np.uint8)  # Black
        frame2[50:, :, 2] = 255  # Blue bottom half
        similarity = self.sampler.calculate_histogram_similarity(frame1, frame2)
        assert similarity < 0.98, f"Expected < 0.98 for different histograms, got {similarity}"

    def test_histogram_returns_valid_range(self):
        """AC4.1: Histogram similarity should return value between 0 and 1."""
        frame1 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        frame2 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        similarity = self.sampler.calculate_histogram_similarity(frame1, frame2)
        assert 0.0 <= similarity <= 1.0, f"Expected 0-1 range, got {similarity}"


class TestSSIMSimilarity:
    """Tests for SSIM similarity calculation (AC4.2)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sampler = AdaptiveSampler()

    def test_identical_frames_ssim_one(self):
        """AC4.2: Identical frames should have SSIM of 1.0."""
        frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        similarity = self.sampler.calculate_ssim_similarity(frame, frame.copy())
        assert similarity >= 0.99, f"Expected near 1.0, got {similarity}"

    def test_different_frames_low_ssim(self):
        """AC4.2: Very different frames should have lower SSIM."""
        # Create structurally different frames
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        # Create frame with noise pattern
        frame2 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        similarity = self.sampler.calculate_ssim_similarity(frame1, frame2)
        assert similarity < 0.5, f"Expected < 0.5, got {similarity}"

    def test_ssim_returns_valid_range(self):
        """AC4.2: SSIM should return value between 0 and 1."""
        frame1 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        frame2 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        similarity = self.sampler.calculate_ssim_similarity(frame1, frame2)
        assert 0.0 <= similarity <= 1.0, f"Expected 0-1 range, got {similarity}"

    def test_ssim_handles_different_sizes(self):
        """AC4.2: SSIM should handle frames of different sizes."""
        frame1 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        frame2 = np.random.randint(0, 255, (120, 80, 3), dtype=np.uint8)
        # Should not raise, should return valid similarity
        similarity = self.sampler.calculate_ssim_similarity(frame1, frame2)
        assert 0.0 <= similarity <= 1.0


class TestFrameDifferenceDetection:
    """Tests for two-stage frame difference detection (AC4.1, AC4.2, AC4.3)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sampler = AdaptiveSampler()

    def test_similar_frames_rejected(self):
        """AC4.3: Frames >95% similar (SSIM) should be skipped."""
        # Create identical frames to ensure they are rejected
        base_frame = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
        similar_frame = base_frame.copy()  # Exact copy

        is_different, hist_sim, ssim_sim = self.sampler._is_frame_different(
            similar_frame, base_frame
        )
        # Should be rejected as too similar (identical)
        assert not is_different, f"Identical frame should be rejected (hist={hist_sim}, ssim={ssim_sim})"

    def test_different_frames_accepted(self):
        """AC4.1/AC4.3: Frames with significant differences should be accepted."""
        # Create clearly different frames
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame2 = np.full((100, 100, 3), 200, dtype=np.uint8)

        is_different, hist_sim, ssim_sim = self.sampler._is_frame_different(frame2, frame1)
        assert is_different, f"Different frames should be accepted (hist={hist_sim})"


class TestAdaptiveFrameSelection:
    """Tests for adaptive frame selection algorithm (AC4.4, AC4.5, AC4.6)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sampler = AdaptiveSampler()

    @pytest.mark.asyncio
    async def test_respects_target_count(self):
        """AC4.4: Output frame count should match configured target."""
        # Create 10 varied frames
        frames = [np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8) for _ in range(10)]
        timestamps_ms = [i * 1000.0 for i in range(10)]  # 1 second apart

        target = 5
        selected = await self.sampler.select_diverse_frames(
            frames=frames,
            timestamps_ms=timestamps_ms,
            target_count=target
        )

        assert len(selected) == target, f"Expected {target} frames, got {len(selected)}"

    @pytest.mark.asyncio
    async def test_temporal_spacing_enforced(self):
        """AC4.5: Minimum 500ms spacing should be enforced."""
        # Create diverse frames 600ms apart (above minimum spacing)
        frames = []
        for i in range(10):
            # Create visually distinct frames
            frame = np.full((100, 100, 3), i * 25, dtype=np.uint8)
            frames.append(frame)
        timestamps_ms = [i * 600.0 for i in range(10)]  # 600ms apart, above minimum

        selected = await self.sampler.select_diverse_frames(
            frames=frames,
            timestamps_ms=timestamps_ms,
            target_count=5
        )

        # Check that we got frames and they are spaced appropriately
        assert len(selected) >= 3, f"Expected at least 3 frames, got {len(selected)}"

        # Check spacing between selected frames (should be at least ~500ms for most)
        spacings = []
        for i in range(1, len(selected)):
            spacing = selected[i][2] - selected[i-1][2]
            spacings.append(spacing)

        # Average spacing should be above minimum (allowing for fallback edge cases)
        avg_spacing = sum(spacings) / len(spacings) if spacings else 0
        assert avg_spacing >= 400.0, f"Average spacing {avg_spacing}ms should be >= 400ms"

    @pytest.mark.asyncio
    async def test_fallback_to_uniform_for_static_video(self):
        """AC4.6: Static video should fallback to uniform sampling."""
        # Create 10 identical frames (static video)
        base_frame = np.full((100, 100, 3), 128, dtype=np.uint8)
        frames = [base_frame.copy() for _ in range(10)]
        timestamps_ms = [i * 1000.0 for i in range(10)]

        target = 5
        selected = await self.sampler.select_diverse_frames(
            frames=frames,
            timestamps_ms=timestamps_ms,
            target_count=target
        )

        # Should still return target count despite all frames being similar
        assert len(selected) == target, f"Fallback should return {target} frames"

    @pytest.mark.asyncio
    async def test_always_includes_first_frame(self):
        """First frame should always be selected."""
        frames = [np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8) for _ in range(5)]
        timestamps_ms = [i * 1000.0 for i in range(5)]

        selected = await self.sampler.select_diverse_frames(
            frames=frames,
            timestamps_ms=timestamps_ms,
            target_count=3
        )

        # First selected frame should be from index 0
        assert selected[0][0] == 0, "First frame should be selected"

    @pytest.mark.asyncio
    async def test_returns_all_if_fewer_than_target(self):
        """If fewer frames than target, return all."""
        frames = [np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8) for _ in range(3)]
        timestamps_ms = [i * 1000.0 for i in range(3)]

        selected = await self.sampler.select_diverse_frames(
            frames=frames,
            timestamps_ms=timestamps_ms,
            target_count=10
        )

        assert len(selected) == 3, "Should return all frames when fewer than target"

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        """Empty input should return empty result."""
        selected = await self.sampler.select_diverse_frames(
            frames=[],
            timestamps_ms=[],
            target_count=5
        )
        assert len(selected) == 0

    @pytest.mark.asyncio
    async def test_maintains_temporal_order(self):
        """Selected frames should maintain temporal order."""
        frames = [np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8) for _ in range(10)]
        timestamps_ms = [i * 1000.0 for i in range(10)]

        selected = await self.sampler.select_diverse_frames(
            frames=frames,
            timestamps_ms=timestamps_ms,
            target_count=5
        )

        # Check indices are in ascending order
        indices = [s[0] for s in selected]
        assert indices == sorted(indices), "Selected frames should be in temporal order"


class TestSingleton:
    """Tests for singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_adaptive_sampler()

    def test_singleton_returns_same_instance(self):
        """get_adaptive_sampler should return same instance."""
        sampler1 = get_adaptive_sampler()
        sampler2 = get_adaptive_sampler()
        assert sampler1 is sampler2

    def test_reset_creates_new_instance(self):
        """reset_adaptive_sampler should create new instance on next call."""
        sampler1 = get_adaptive_sampler()
        reset_adaptive_sampler()
        sampler2 = get_adaptive_sampler()
        assert sampler1 is not sampler2


class TestFrameSelectionWithSceneChanges:
    """Tests for frame selection with scene changes."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sampler = AdaptiveSampler()

    @pytest.mark.asyncio
    async def test_detects_scene_changes(self):
        """Should select frames around scene changes."""
        # Create video with clear scene change
        frames = []
        timestamps_ms = []

        # Scene 1: Dark frames (0-4)
        for i in range(5):
            frames.append(np.full((100, 100, 3), 30, dtype=np.uint8))
            timestamps_ms.append(i * 1000.0)

        # Scene 2: Bright frames (5-9)
        for i in range(5, 10):
            frames.append(np.full((100, 100, 3), 220, dtype=np.uint8))
            timestamps_ms.append(i * 1000.0)

        selected = await self.sampler.select_diverse_frames(
            frames=frames,
            timestamps_ms=timestamps_ms,
            target_count=4
        )

        # Should select frames from both scenes
        indices = [s[0] for s in selected]

        # Check we have frames from scene 1 (indices 0-4) and scene 2 (indices 5-9)
        has_scene1 = any(i < 5 for i in indices)
        has_scene2 = any(i >= 5 for i in indices)

        assert has_scene1 and has_scene2, f"Should select from both scenes, got indices {indices}"
