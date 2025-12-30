"""
AdaptiveSampler for content-aware frame selection (Story P8-2.4)

Implements adaptive frame sampling using a two-stage algorithm:
1. Fast histogram comparison as pre-filter (reject highly similar frames quickly)
2. SSIM (Structural Similarity Index) for borderline cases

The algorithm prioritizes frames with visual differences while maintaining
temporal coverage (minimum 500ms spacing). This improves AI analysis quality
by avoiding redundant frames while still capturing key moments.

Architecture Reference: docs/sprint-artifacts/tech-spec-epic-P8-2.md
Migrated to @singleton: Story P14-5.3
"""
import logging
from typing import List, Tuple

import cv2
import numpy as np

from app.core.decorators import singleton

logger = logging.getLogger(__name__)

# Adaptive sampling configuration (Story P8-2.4)
HISTOGRAM_SIMILARITY_THRESHOLD = 0.98  # Fast reject highly similar frames
SSIM_SIMILARITY_THRESHOLD = 0.95  # Detailed check for borderline cases
MIN_TEMPORAL_SPACING_MS = 500.0  # Minimum spacing between selected frames


@singleton
class AdaptiveSampler:
    """
    Service for content-aware frame selection.

    Uses a two-stage filtering approach:
    1. Fast histogram comparison to quickly reject very similar frames
    2. SSIM for borderline cases when histogram similarity is high

    Key features:
    - Always selects first frame as anchor
    - Enforces minimum temporal spacing between frames
    - Falls back to uniform sampling when video is static
    - Logs selection decisions for debugging

    Attributes:
        histogram_threshold: Similarity threshold for histogram comparison (0.98)
        ssim_threshold: Similarity threshold for SSIM comparison (0.95)
        min_spacing_ms: Minimum temporal spacing in milliseconds (500)
    """

    def __init__(
        self,
        histogram_threshold: float = HISTOGRAM_SIMILARITY_THRESHOLD,
        ssim_threshold: float = SSIM_SIMILARITY_THRESHOLD,
        min_spacing_ms: float = MIN_TEMPORAL_SPACING_MS
    ):
        """
        Initialize AdaptiveSampler with configurable thresholds.

        Args:
            histogram_threshold: Threshold for histogram similarity (0-1, default 0.98)
            ssim_threshold: Threshold for SSIM similarity (0-1, default 0.95)
            min_spacing_ms: Minimum temporal spacing in milliseconds (default 500)
        """
        self.histogram_threshold = histogram_threshold
        self.ssim_threshold = ssim_threshold
        self.min_spacing_ms = min_spacing_ms

        logger.info(
            "AdaptiveSampler initialized",
            extra={
                "event_type": "adaptive_sampler_init",
                "histogram_threshold": self.histogram_threshold,
                "ssim_threshold": self.ssim_threshold,
                "min_spacing_ms": self.min_spacing_ms
            }
        )

    def calculate_histogram_similarity(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray
    ) -> float:
        """
        Calculate histogram similarity between two frames.

        Uses normalized histogram correlation on all RGB channels which is fast
        and provides a good initial filter for very similar frames.

        Args:
            frame1: First frame as RGB numpy array (H, W, 3)
            frame2: Second frame as RGB numpy array (H, W, 3)

        Returns:
            Similarity score between 0.0 and 1.0
            - 1.0 = identical histograms
            - 0.0 = completely different histograms
        """
        # Calculate histograms for each RGB channel separately
        similarities = []

        for channel in range(3):
            hist1 = cv2.calcHist([frame1], [channel], None, [256], [0, 256])
            hist2 = cv2.calcHist([frame2], [channel], None, [256], [0, 256])

            # Normalize histograms
            cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
            cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)

            # Compare using correlation method
            # HISTCMP_CORREL returns value between -1 and 1
            similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            similarities.append(similarity)

        # Average similarity across channels
        avg_similarity = sum(similarities) / len(similarities)

        # Normalize to 0-1 range (correlation can be negative)
        avg_similarity = max(0.0, min(1.0, (avg_similarity + 1) / 2))

        return float(avg_similarity)

    def calculate_ssim_similarity(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray
    ) -> float:
        """
        Calculate Structural Similarity Index (SSIM) between two frames.

        SSIM provides a more accurate measure of perceived visual similarity
        than histogram comparison, but is computationally more expensive.

        Args:
            frame1: First frame as RGB numpy array (H, W, 3)
            frame2: Second frame as RGB numpy array (H, W, 3)

        Returns:
            SSIM score between 0.0 and 1.0
            - 1.0 = identical images
            - 0.0 = completely different images
        """
        # Convert to grayscale for SSIM
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_RGB2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_RGB2GRAY)

        # Resize to same dimensions if needed
        if gray1.shape != gray2.shape:
            h = min(gray1.shape[0], gray2.shape[0])
            w = min(gray1.shape[1], gray2.shape[1])
            gray1 = cv2.resize(gray1, (w, h))
            gray2 = cv2.resize(gray2, (w, h))

        # Calculate SSIM using OpenCV (simplified implementation)
        # OpenCV doesn't have built-in SSIM, so we implement it manually

        # Constants for SSIM calculation
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2

        # Convert to float
        img1 = gray1.astype(np.float64)
        img2 = gray2.astype(np.float64)

        # Calculate means
        mu1 = cv2.GaussianBlur(img1, (11, 11), 1.5)
        mu2 = cv2.GaussianBlur(img2, (11, 11), 1.5)

        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2

        # Calculate variances and covariance
        sigma1_sq = cv2.GaussianBlur(img1 ** 2, (11, 11), 1.5) - mu1_sq
        sigma2_sq = cv2.GaussianBlur(img2 ** 2, (11, 11), 1.5) - mu2_sq
        sigma12 = cv2.GaussianBlur(img1 * img2, (11, 11), 1.5) - mu1_mu2

        # Calculate SSIM
        ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
                   ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))

        # Return mean SSIM
        ssim = float(np.mean(ssim_map))

        # Ensure value is in valid range
        return max(0.0, min(1.0, ssim))

    def _is_frame_different(
        self,
        frame: np.ndarray,
        reference_frame: np.ndarray
    ) -> Tuple[bool, float, float]:
        """
        Determine if a frame is sufficiently different from the reference.

        Uses two-stage filtering:
        1. Fast histogram comparison
        2. SSIM for borderline cases

        Args:
            frame: Frame to evaluate
            reference_frame: Reference frame to compare against

        Returns:
            Tuple of (is_different, histogram_similarity, ssim_similarity)
            - is_different: True if frame should be included
            - histogram_similarity: Histogram similarity score
            - ssim_similarity: SSIM score (0.0 if not computed)
        """
        # Stage 1: Fast histogram comparison
        hist_sim = self.calculate_histogram_similarity(frame, reference_frame)

        # If very different by histogram, definitely include
        if hist_sim < self.histogram_threshold:
            logger.debug(
                f"Frame accepted (histogram={hist_sim:.3f} < {self.histogram_threshold})",
                extra={
                    "event_type": "frame_accepted_histogram",
                    "histogram_similarity": hist_sim
                }
            )
            return True, hist_sim, 0.0

        # Stage 2: Borderline case - use SSIM for accurate comparison
        ssim_sim = self.calculate_ssim_similarity(frame, reference_frame)

        if ssim_sim < self.ssim_threshold:
            logger.debug(
                f"Frame accepted (histogram={hist_sim:.3f}, ssim={ssim_sim:.3f} < {self.ssim_threshold})",
                extra={
                    "event_type": "frame_accepted_ssim",
                    "histogram_similarity": hist_sim,
                    "ssim_similarity": ssim_sim
                }
            )
            return True, hist_sim, ssim_sim

        # Frame is too similar - reject
        logger.debug(
            f"Frame rejected (histogram={hist_sim:.3f}, ssim={ssim_sim:.3f} >= {self.ssim_threshold})",
            extra={
                "event_type": "frame_rejected_similar",
                "histogram_similarity": hist_sim,
                "ssim_similarity": ssim_sim
            }
        )
        return False, hist_sim, ssim_sim

    async def select_diverse_frames(
        self,
        frames: List[np.ndarray],
        timestamps_ms: List[float],
        target_count: int,
        fps: float = 30.0
    ) -> List[Tuple[int, np.ndarray, float]]:
        """
        Select diverse frames using adaptive content-aware sampling.

        Algorithm:
        1. Always select first frame as anchor
        2. For each subsequent frame:
           a. Check temporal spacing (min 500ms from last selected)
           b. Fast histogram comparison vs last selected
           c. If histogram similarity < threshold, accept
           d. If borderline, run SSIM comparison
           e. Accept if SSIM < threshold
        3. If insufficient frames selected, fill with uniform sampling
        4. Return selected frames with original indices

        Args:
            frames: List of frames as RGB numpy arrays
            timestamps_ms: List of timestamps in milliseconds for each frame
            target_count: Number of frames to select
            fps: Frames per second for timestamp calculation if timestamps_ms empty

        Returns:
            List of tuples (original_index, frame, timestamp_ms) for selected frames
        """
        if not frames:
            logger.warning(
                "No frames provided to select_diverse_frames",
                extra={"event_type": "adaptive_sampler_empty_input"}
            )
            return []

        if target_count <= 0:
            logger.warning(
                f"Invalid target_count: {target_count}",
                extra={"event_type": "adaptive_sampler_invalid_count"}
            )
            return []

        # Generate timestamps if not provided
        if not timestamps_ms or len(timestamps_ms) != len(frames):
            timestamps_ms = [i * (1000.0 / fps) for i in range(len(frames))]

        logger.info(
            f"Starting adaptive frame selection: {len(frames)} candidates -> {target_count} targets",
            extra={
                "event_type": "adaptive_selection_start",
                "candidate_count": len(frames),
                "target_count": target_count,
                "total_duration_ms": timestamps_ms[-1] if timestamps_ms else 0
            }
        )

        # If we have fewer frames than target, return all
        if len(frames) <= target_count:
            result = [(i, frame, timestamps_ms[i]) for i, frame in enumerate(frames)]
            logger.info(
                f"Returning all {len(frames)} frames (fewer than target {target_count})",
                extra={
                    "event_type": "adaptive_selection_all",
                    "frames_selected": len(result)
                }
            )
            return result

        # Selected frames: (original_index, frame, timestamp_ms)
        selected: List[Tuple[int, np.ndarray, float]] = []

        # Always select first frame
        selected.append((0, frames[0], timestamps_ms[0]))
        last_selected_timestamp = timestamps_ms[0]
        last_selected_frame = frames[0]

        # Track statistics for logging
        frames_evaluated = 0
        frames_skipped_temporal = 0
        frames_skipped_similar = 0
        histogram_calls = 0
        ssim_calls = 0

        # Evaluate remaining frames
        for i in range(1, len(frames)):
            frames_evaluated += 1

            # Check temporal spacing
            time_since_last = timestamps_ms[i] - last_selected_timestamp
            if time_since_last < self.min_spacing_ms:
                frames_skipped_temporal += 1
                continue

            # Check if frame is different enough
            is_different, hist_sim, ssim_sim = self._is_frame_different(
                frames[i], last_selected_frame
            )
            histogram_calls += 1
            if ssim_sim > 0:
                ssim_calls += 1

            if is_different:
                selected.append((i, frames[i], timestamps_ms[i]))
                last_selected_timestamp = timestamps_ms[i]
                last_selected_frame = frames[i]

                # If we have enough frames, stop
                if len(selected) >= target_count:
                    break
            else:
                frames_skipped_similar += 1

        # Log intermediate results
        logger.debug(
            f"Adaptive selection found {len(selected)} diverse frames",
            extra={
                "event_type": "adaptive_selection_intermediate",
                "selected_count": len(selected),
                "target_count": target_count,
                "frames_evaluated": frames_evaluated,
                "skipped_temporal": frames_skipped_temporal,
                "skipped_similar": frames_skipped_similar,
                "histogram_calls": histogram_calls,
                "ssim_calls": ssim_calls
            }
        )

        # If we don't have enough frames, fill with uniform sampling
        if len(selected) < target_count:
            selected = self._fill_with_uniform(
                frames, timestamps_ms, selected, target_count
            )

        # Sort by original index to maintain temporal order
        selected.sort(key=lambda x: x[0])

        # Log final selection
        selected_indices = [s[0] for s in selected]
        selected_timestamps = [s[2] for s in selected]
        logger.info(
            f"Adaptive selection complete: {len(selected)} frames",
            extra={
                "event_type": "adaptive_selection_complete",
                "frames_selected": len(selected),
                "selected_indices": selected_indices,
                "selected_timestamps_ms": selected_timestamps,
                "frames_evaluated": frames_evaluated,
                "histogram_calls": histogram_calls,
                "ssim_calls": ssim_calls,
                "used_fallback": len(selected) > len([s for s in selected if s in selected])
            }
        )

        return selected

    def _fill_with_uniform(
        self,
        frames: List[np.ndarray],
        timestamps_ms: List[float],
        selected: List[Tuple[int, np.ndarray, float]],
        target_count: int
    ) -> List[Tuple[int, np.ndarray, float]]:
        """
        Fill remaining frame slots with uniform sampling.

        Used when adaptive sampling doesn't find enough diverse frames
        (e.g., static video).

        Args:
            frames: All available frames
            timestamps_ms: Timestamps for all frames
            selected: Already selected frames
            target_count: Target number of frames

        Returns:
            Updated list of selected frames
        """
        if len(selected) >= target_count:
            return selected

        needed = target_count - len(selected)
        selected_indices = set(s[0] for s in selected)

        logger.debug(
            f"Filling {needed} slots with uniform sampling (static video fallback)",
            extra={
                "event_type": "uniform_fallback",
                "needed": needed,
                "already_selected": len(selected)
            }
        )

        # Calculate uniform indices excluding already selected
        available_indices = [i for i in range(len(frames)) if i not in selected_indices]

        if not available_indices:
            return selected

        # Select uniformly spaced frames from available
        step = len(available_indices) / needed if needed > 0 else 1
        uniform_indices = []
        for i in range(needed):
            idx = int(i * step)
            if idx < len(available_indices):
                uniform_indices.append(available_indices[idx])

        # Add uniform frames to selected
        for idx in uniform_indices:
            selected.append((idx, frames[idx], timestamps_ms[idx]))

        return selected


# Backward compatible getter (delegates to @singleton decorator)
def get_adaptive_sampler() -> AdaptiveSampler:
    """
    Get the singleton AdaptiveSampler instance.

    Returns:
        AdaptiveSampler singleton instance

    Note: This is a backward-compatible wrapper. New code should use
          AdaptiveSampler() directly, which returns the singleton instance.
    """
    return AdaptiveSampler()


def reset_adaptive_sampler() -> None:
    """
    Reset the singleton instance (useful for testing).

    Note: This is a backward-compatible wrapper. New code should use
          AdaptiveSampler._reset_instance() directly.
    """
    AdaptiveSampler._reset_instance()
