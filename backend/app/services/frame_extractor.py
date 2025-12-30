"""
FrameExtractor for extracting frames from video clips (Story P3-2.1, P3-2.2, P8-2.4)

Provides functionality to:
- Extract multiple frames from video clips for AI analysis
- Select frames using evenly-spaced or adaptive strategy (P8-2.4)
- Filter out blurry or empty frames using Laplacian variance (Story P3-2.2)
- Encode frames as JPEG with configurable quality
- Resize frames to max width for optimal AI token cost

Sampling Strategies (P8-2.4):
- uniform: Evenly-spaced frame selection (first/last guaranteed)
- adaptive: Content-aware selection using histogram + SSIM comparison
- hybrid: Extract more candidates uniformly, then filter adaptively

Architecture Reference: docs/architecture.md#Phase-3-Service-Architecture
Migrated to @singleton: Story P14-5.3
"""
import io
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import av
import cv2
import numpy as np
from PIL import Image

from app.core.decorators import singleton

logger = logging.getLogger(__name__)

# Similarity filtering configuration (Story P9-2.2)
SIMILARITY_THRESHOLD = 0.95  # SSIM threshold for filtering similar frames
SIMILARITY_RESIZE_DIM = 256  # Resize frames for faster SSIM comparison

# Motion scoring configuration (Story P9-2.3)
MOTION_SCORE_MULTIPLIER = 10.0  # Multiplier to normalize optical flow magnitude to 0-100

# Frame extraction configuration (Story P3-2.1, FR8, P8-2.3)
FRAME_EXTRACT_DEFAULT_COUNT = 10  # Story P8-2.3: Changed from 5 to 10
FRAME_EXTRACT_MIN_COUNT = 3
FRAME_EXTRACT_MAX_COUNT = 20  # Story P8-2.3: Changed from 10 to 20 to support configurable count
FRAME_JPEG_QUALITY = 85
FRAME_MAX_WIDTH = 1280

# Blur detection configuration (Story P3-2.2, FR9)
FRAME_BLUR_THRESHOLD = 100  # Laplacian variance threshold for blur detection
FRAME_EMPTY_STD_THRESHOLD = 10  # Std deviation threshold for empty/single-color frames


@singleton
class FrameExtractor:
    """
    Service for extracting frames from video clips.

    Extracts evenly-spaced frames from video files for multi-frame AI analysis.
    Returns JPEG-encoded bytes suitable for sending to vision AI providers.

    Key features:
    - Evenly-spaced frame selection (first and last frames always included)
    - JPEG encoding at configurable quality (default 85%)
    - Automatic resize to max width (default 1280px)
    - Graceful error handling (returns empty list on failure)

    Follows singleton pattern matching ClipService for consistency.

    Attributes:
        default_frame_count: Default number of frames to extract (5)
        jpeg_quality: JPEG encoding quality 0-100 (85)
        max_width: Maximum frame width in pixels (1280)
    """

    def __init__(self):
        """
        Initialize FrameExtractor with default configuration.
        """
        self.default_frame_count = FRAME_EXTRACT_DEFAULT_COUNT
        self.jpeg_quality = FRAME_JPEG_QUALITY
        self.max_width = FRAME_MAX_WIDTH

        logger.info(
            "FrameExtractor initialized",
            extra={
                "event_type": "frame_extractor_init",
                "default_frame_count": self.default_frame_count,
                "jpeg_quality": self.jpeg_quality,
                "max_width": self.max_width
            }
        )

    def _calculate_frame_indices(self, total_frames: int, frame_count: int) -> List[int]:
        """
        Calculate evenly spaced frame indices.

        Always includes first frame (index 0) and last frame (total_frames - 1).
        Intermediate frames are evenly distributed.

        Args:
            total_frames: Total number of frames in the video
            frame_count: Number of frames to extract

        Returns:
            List of frame indices to extract

        Example:
            total_frames=300, frame_count=5 -> [0, 74, 149, 224, 299]
        """
        if total_frames <= 0:
            return []

        if frame_count <= 0:
            return []

        # If requesting more frames than available, return all
        if frame_count >= total_frames:
            return list(range(total_frames))

        # If only 1 frame requested, return first frame
        if frame_count == 1:
            return [0]

        # Calculate evenly spaced indices
        # Formula ensures first frame is 0 and last frame is total_frames - 1
        indices = []
        for i in range(frame_count):
            # Spread frames evenly across the video
            index = int((i * (total_frames - 1)) / (frame_count - 1))
            indices.append(index)

        return indices

    def _encode_frame(self, frame: np.ndarray) -> bytes:
        """
        Encode a frame as JPEG bytes.

        Resizes frame to max_width if larger, maintaining aspect ratio.
        Uses PIL for high-quality JPEG encoding.

        Args:
            frame: RGB numpy array (H, W, 3)

        Returns:
            JPEG-encoded bytes
        """
        # Convert numpy array to PIL Image
        img = Image.fromarray(frame)

        # Resize if needed (maintain aspect ratio)
        if img.width > self.max_width:
            ratio = self.max_width / img.width
            new_size = (self.max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # Encode as JPEG
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=self.jpeg_quality)
        return buffer.getvalue()

    def _get_frame_quality_score(self, frame: np.ndarray) -> float:
        """
        Calculate quality score for a frame using Laplacian variance.

        Higher scores indicate sharper/clearer images.
        Used for blur detection and frame ranking.

        Args:
            frame: RGB numpy array (H, W, 3)

        Returns:
            Laplacian variance (float). Higher = sharper.
        """
        # Convert RGB to grayscale for analysis
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

        # Calculate Laplacian variance (measure of sharpness)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        return float(laplacian_var)

    def _calculate_ssim(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        resize_dim: int = SIMILARITY_RESIZE_DIM
    ) -> float:
        """
        Calculate Structural Similarity Index (SSIM) between two frames (Story P9-2.2).

        Implements SSIM for perceptual similarity measurement. Frames are resized
        for faster comparison.

        Args:
            frame1: First frame as RGB numpy array (H, W, 3)
            frame2: Second frame as RGB numpy array (H, W, 3)
            resize_dim: Dimension to resize frames to for comparison (default 256)

        Returns:
            SSIM score between 0.0 and 1.0
            - 1.0 = identical images
            - 0.0 = completely different images
        """
        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_RGB2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_RGB2GRAY)

        # Resize for faster comparison
        gray1 = cv2.resize(gray1, (resize_dim, resize_dim))
        gray2 = cv2.resize(gray2, (resize_dim, resize_dim))

        # SSIM constants
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2

        # Convert to float
        img1 = gray1.astype(np.float64)
        img2 = gray2.astype(np.float64)

        # Calculate means using Gaussian blur
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

        ssim = float(np.mean(ssim_map))
        return max(0.0, min(1.0, ssim))

    def is_similar(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        threshold: float = SIMILARITY_THRESHOLD
    ) -> bool:
        """
        Check if two frames are too similar using SSIM (Story P9-2.2).

        Args:
            frame1: First frame as RGB numpy array
            frame2: Second frame as RGB numpy array
            threshold: SSIM threshold (default 0.95). Frames above this are similar.

        Returns:
            True if frames are too similar (SSIM > threshold), False otherwise
        """
        ssim = self._calculate_ssim(frame1, frame2)
        return ssim > threshold

    def filter_similar_frames(
        self,
        frames: List[np.ndarray],
        threshold: float = SIMILARITY_THRESHOLD,
        indices: Optional[List[int]] = None
    ) -> Tuple[List[np.ndarray], List[int]]:
        """
        Filter out consecutive frames that are too similar (Story P9-2.2).

        Compares each frame to the last kept frame. If similarity > threshold,
        the frame is discarded. Always keeps the first frame.

        Args:
            frames: List of frames as RGB numpy arrays
            threshold: SSIM threshold (default 0.95). Frames above this are filtered.
            indices: Optional list of original frame indices. If provided, filtered
                    indices are returned alongside filtered frames.

        Returns:
            Tuple of (filtered_frames, filtered_indices)
            - filtered_frames: List of unique frames
            - filtered_indices: List of original indices for kept frames

        Example:
            100 raw frames → filter_similar_frames() → 45 unique frames
        """
        import time
        start_time = time.time()

        if not frames:
            logger.warning(
                "No frames provided to filter_similar_frames",
                extra={"event_type": "similarity_filter_empty_input"}
            )
            return [], []

        input_count = len(frames)

        # Generate indices if not provided
        if indices is None:
            indices = list(range(len(frames)))

        # Always keep the first frame
        filtered_frames = [frames[0]]
        filtered_indices = [indices[0]]
        last_kept_frame = frames[0]

        # Compare each subsequent frame to the last kept frame
        for i in range(1, len(frames)):
            if not self.is_similar(frames[i], last_kept_frame, threshold):
                # Frame is different enough, keep it
                filtered_frames.append(frames[i])
                filtered_indices.append(indices[i])
                last_kept_frame = frames[i]

        output_count = len(filtered_frames)
        elapsed_ms = (time.time() - start_time) * 1000

        # AC-2.2.4: Log filter ratio
        logger.info(
            f"Filtered {input_count}→{output_count} frames (threshold={threshold})",
            extra={
                "event_type": "similarity_filter_complete",
                "input_count": input_count,
                "output_count": output_count,
                "filtered_count": input_count - output_count,
                "threshold": threshold,
                "elapsed_ms": round(elapsed_ms, 2)
            }
        )

        return filtered_frames, filtered_indices

    def calculate_motion_score(
        self,
        prev_frame: np.ndarray,
        curr_frame: np.ndarray,
        resize_dim: int = 256
    ) -> float:
        """
        Calculate motion score between two consecutive frames (Story P9-2.3).

        Uses optical flow (Farneback algorithm) to measure motion magnitude
        between frames. Normalized to 0-100 scale.

        Args:
            prev_frame: Previous frame as RGB numpy array (H, W, 3)
            curr_frame: Current frame as RGB numpy array (H, W, 3)
            resize_dim: Dimension to resize frames for faster processing (default 256)

        Returns:
            Motion score between 0 and 100
            - 0 = no motion (identical frames)
            - 100 = maximum motion (high speed movement)
        """
        # Convert to grayscale
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_RGB2GRAY)
        curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_RGB2GRAY)

        # Resize for faster computation
        prev_gray = cv2.resize(prev_gray, (resize_dim, resize_dim))
        curr_gray = cv2.resize(curr_gray, (resize_dim, resize_dim))

        # Calculate optical flow using Farneback algorithm
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, curr_gray, None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0
        )

        # Calculate magnitude of flow vectors
        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])

        # Calculate mean magnitude and normalize to 0-100
        mean_magnitude = float(np.mean(magnitude))
        score = min(100.0, mean_magnitude * MOTION_SCORE_MULTIPLIER)

        return round(score, 2)

    def score_frames_by_motion(
        self,
        frames: List[np.ndarray],
        indices: Optional[List[int]] = None
    ) -> List[Tuple[np.ndarray, int, float]]:
        """
        Score a list of frames by motion activity (Story P9-2.3).

        Calculates motion score for each frame based on optical flow to
        adjacent frames. First frame gets score based on comparison to second.

        Args:
            frames: List of frames as RGB numpy arrays
            indices: Optional list of original frame indices

        Returns:
            List of tuples (frame, index, motion_score)
            Sorted by original index (chronological order)

        Example:
            frames -> [(frame1, 0, 45.2), (frame2, 1, 78.3), (frame3, 2, 12.1)]
        """
        if not frames:
            logger.warning(
                "No frames provided to score_frames_by_motion",
                extra={"event_type": "motion_scoring_empty_input"}
            )
            return []

        if len(frames) == 1:
            # Single frame, no motion can be calculated
            idx = indices[0] if indices else 0
            return [(frames[0], idx, 0.0)]

        # Generate indices if not provided
        if indices is None:
            indices = list(range(len(frames)))

        scored_frames: List[Tuple[np.ndarray, int, float]] = []

        for i in range(len(frames)):
            if i == 0:
                # First frame: compare to second frame
                score = self.calculate_motion_score(frames[0], frames[1])
            elif i == len(frames) - 1:
                # Last frame: compare to previous frame
                score = self.calculate_motion_score(frames[-2], frames[-1])
            else:
                # Middle frame: average of motion to prev and next
                score_prev = self.calculate_motion_score(frames[i - 1], frames[i])
                score_next = self.calculate_motion_score(frames[i], frames[i + 1])
                score = (score_prev + score_next) / 2

            scored_frames.append((frames[i], indices[i], round(score, 2)))

        # Log scoring results
        scores = [s[2] for s in scored_frames]
        logger.info(
            f"Motion scoring complete: {len(frames)} frames, scores range {min(scores):.1f}-{max(scores):.1f}",
            extra={
                "event_type": "motion_scoring_complete",
                "frame_count": len(frames),
                "min_score": min(scores),
                "max_score": max(scores),
                "avg_score": round(sum(scores) / len(scores), 2)
            }
        )

        return scored_frames

    def select_top_frames_by_score(
        self,
        scored_frames: List[Tuple[np.ndarray, int, float]],
        target_count: int,
        sort_chronologically: bool = True
    ) -> List[Tuple[np.ndarray, int, float]]:
        """
        Select top N frames by motion score (Story P9-2.3).

        Args:
            scored_frames: List of (frame, index, score) tuples
            target_count: Number of frames to select
            sort_chronologically: If True, sort by index before returning

        Returns:
            List of top-scoring frames, optionally sorted by index
        """
        if not scored_frames:
            return []

        if target_count >= len(scored_frames):
            result = scored_frames
        else:
            # Sort by score descending, select top N
            sorted_by_score = sorted(scored_frames, key=lambda x: x[2], reverse=True)
            result = sorted_by_score[:target_count]

        # AC-2.3.4: Sort chronologically for context
        if sort_chronologically:
            result = sorted(result, key=lambda x: x[1])

        logger.debug(
            f"Selected top {len(result)} frames from {len(scored_frames)}",
            extra={
                "event_type": "frame_selection_by_score",
                "input_count": len(scored_frames),
                "output_count": len(result),
                "selected_indices": [f[1] for f in result],
                "selected_scores": [f[2] for f in result]
            }
        )

        return result

    def _is_frame_usable(self, frame: np.ndarray) -> bool:
        """
        Check if frame is usable for AI analysis.

        Returns False if:
        - Frame is too blurry (Laplacian variance < FRAME_BLUR_THRESHOLD)
        - Frame is empty/single-color (std deviation < FRAME_EMPTY_STD_THRESHOLD)

        Args:
            frame: RGB numpy array (H, W, 3)

        Returns:
            True if frame passes quality checks, False otherwise
        """
        # Convert RGB to grayscale for analysis
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

        # Check for blur using Laplacian variance
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if laplacian_var < FRAME_BLUR_THRESHOLD:
            logger.debug(
                f"Frame is blurry (variance={laplacian_var:.2f} < {FRAME_BLUR_THRESHOLD})",
                extra={
                    "event_type": "frame_blur_detected",
                    "laplacian_variance": laplacian_var,
                    "threshold": FRAME_BLUR_THRESHOLD
                }
            )
            return False

        # Check for empty/single-color frames
        std_dev = np.std(gray)
        if std_dev < FRAME_EMPTY_STD_THRESHOLD:
            logger.debug(
                f"Frame is empty/single-color (std_dev={std_dev:.2f} < {FRAME_EMPTY_STD_THRESHOLD})",
                extra={
                    "event_type": "frame_empty_detected",
                    "std_deviation": std_dev,
                    "threshold": FRAME_EMPTY_STD_THRESHOLD
                }
            )
            return False

        return True

    async def extract_frames(
        self,
        clip_path: Path,
        frame_count: int = 5,
        strategy: str = "evenly_spaced",
        filter_blur: bool = True
    ) -> List[bytes]:
        """
        Extract frames from a video clip.

        Extracts evenly-spaced frames from the video for AI analysis.
        First and last frames are always included.
        Optionally filters out blurry/empty frames and replaces them.

        Args:
            clip_path: Path to the video file (MP4)
            frame_count: Number of frames to extract (3-10, default 5)
            strategy: Selection strategy (currently only "evenly_spaced")
            filter_blur: If True (default), filter out blurry/empty frames
                        and attempt to replace them with better alternatives

        Returns:
            List of JPEG-encoded frame bytes.
            Returns empty list on any error (never raises).
            Always returns at least min_frames (3) when possible.

        Note:
            - Extraction completes within 2 seconds for 10-second clips (NFR2)
            - JPEG quality is 85% (configurable)
            - Frames are resized to max 1280px width
            - When filter_blur=True, blurry frames are replaced with adjacent frames
        """
        logger.info(
            "Starting frame extraction",
            extra={
                "event_type": "frame_extraction_start",
                "clip_path": str(clip_path),
                "frame_count": frame_count,
                "strategy": strategy,
                "filter_blur": filter_blur
            }
        )

        if not filter_blur:
            logger.debug(
                "Blur filtering is disabled",
                extra={
                    "event_type": "blur_filter_disabled",
                    "clip_path": str(clip_path)
                }
            )

        # Validate frame_count within bounds
        if frame_count < FRAME_EXTRACT_MIN_COUNT:
            frame_count = FRAME_EXTRACT_MIN_COUNT
            logger.debug(
                f"Frame count adjusted to minimum: {FRAME_EXTRACT_MIN_COUNT}",
                extra={
                    "event_type": "frame_count_adjusted",
                    "original": frame_count,
                    "adjusted": FRAME_EXTRACT_MIN_COUNT
                }
            )
        elif frame_count > FRAME_EXTRACT_MAX_COUNT:
            frame_count = FRAME_EXTRACT_MAX_COUNT
            logger.debug(
                f"Frame count adjusted to maximum: {FRAME_EXTRACT_MAX_COUNT}",
                extra={
                    "event_type": "frame_count_adjusted",
                    "original": frame_count,
                    "adjusted": FRAME_EXTRACT_MAX_COUNT
                }
            )

        try:
            # Open video file with PyAV
            with av.open(str(clip_path)) as container:
                # Get video stream
                if not container.streams.video:
                    logger.warning(
                        "No video stream found in file",
                        extra={
                            "event_type": "frame_extraction_no_video",
                            "clip_path": str(clip_path)
                        }
                    )
                    return []

                stream = container.streams.video[0]

                # Get total frame count
                # Try stream.frames first, fall back to duration estimate
                total_frames = stream.frames
                if total_frames is None or total_frames <= 0:
                    # Estimate from duration and frame rate
                    if container.duration and stream.average_rate:
                        duration_seconds = container.duration / 1_000_000.0
                        total_frames = int(duration_seconds * float(stream.average_rate))
                    else:
                        logger.warning(
                            "Cannot determine total frames",
                            extra={
                                "event_type": "frame_extraction_unknown_frames",
                                "clip_path": str(clip_path)
                            }
                        )
                        return []

                if total_frames <= 0:
                    logger.warning(
                        "Video has no frames",
                        extra={
                            "event_type": "frame_extraction_no_frames",
                            "clip_path": str(clip_path)
                        }
                    )
                    return []

                # Calculate which frames to extract
                indices = self._calculate_frame_indices(total_frames, frame_count)

                if not indices:
                    logger.warning(
                        "No frame indices calculated",
                        extra={
                            "event_type": "frame_extraction_no_indices",
                            "clip_path": str(clip_path),
                            "total_frames": total_frames,
                            "frame_count": frame_count
                        }
                    )
                    return []

                logger.debug(
                    f"Extracting {len(indices)} frames from {total_frames} total",
                    extra={
                        "event_type": "frame_extraction_indices",
                        "clip_path": str(clip_path),
                        "total_frames": total_frames,
                        "indices": indices
                    }
                )

                # Extract frames at calculated indices
                # Store as tuples: (frame_index, quality_score, rgb_array, jpeg_bytes)
                extracted_frames: List[Tuple[int, float, np.ndarray, bytes]] = []
                current_frame_index = 0
                indices_set = set(indices)

                # Decode all frames and pick the ones we need
                # This is more reliable than seeking for many codecs
                for frame in container.decode(video=0):
                    if current_frame_index in indices_set:
                        # Convert to RGB numpy array
                        img_array = frame.to_ndarray(format='rgb24')

                        # Calculate quality score
                        quality_score = self._get_frame_quality_score(img_array)

                        # Encode as JPEG
                        jpeg_bytes = self._encode_frame(img_array)

                        extracted_frames.append(
                            (current_frame_index, quality_score, img_array, jpeg_bytes)
                        )

                        # Remove this index from the set we're looking for
                        indices_set.remove(current_frame_index)

                        # If we've got all frames, stop early
                        if not indices_set:
                            break

                    current_frame_index += 1

                # If blur filtering is disabled, return all frames as-is
                if not filter_blur:
                    frames = [jpeg_bytes for _, _, _, jpeg_bytes in extracted_frames]
                    logger.info(
                        f"Frame extraction complete (no filtering): {len(frames)} frames",
                        extra={
                            "event_type": "frame_extraction_success",
                            "clip_path": str(clip_path),
                            "frames_extracted": len(frames),
                            "total_bytes": sum(len(f) for f in frames),
                            "filter_blur": False
                        }
                    )
                    return frames

                # Apply blur filtering
                usable_frames: List[Tuple[int, float, bytes]] = []
                unusable_frames: List[Tuple[int, float, bytes]] = []

                for frame_idx, quality_score, img_array, jpeg_bytes in extracted_frames:
                    if self._is_frame_usable(img_array):
                        usable_frames.append((frame_idx, quality_score, jpeg_bytes))
                    else:
                        unusable_frames.append((frame_idx, quality_score, jpeg_bytes))

                # Log filtering results
                if unusable_frames:
                    logger.debug(
                        f"Filtered out {len(unusable_frames)} low-quality frames",
                        extra={
                            "event_type": "frame_filtering_result",
                            "clip_path": str(clip_path),
                            "usable_count": len(usable_frames),
                            "unusable_count": len(unusable_frames)
                        }
                    )

                # If all frames are usable, return them
                if len(usable_frames) >= frame_count:
                    frames = [jpeg_bytes for _, _, jpeg_bytes in usable_frames[:frame_count]]
                    logger.info(
                        f"Frame extraction complete: {len(frames)} frames (all passed quality check)",
                        extra={
                            "event_type": "frame_extraction_success",
                            "clip_path": str(clip_path),
                            "frames_extracted": len(frames),
                            "total_bytes": sum(len(f) for f in frames),
                            "filter_blur": True,
                            "all_usable": True
                        }
                    )
                    return frames

                # Check if all frames are below quality threshold
                if len(usable_frames) == 0:
                    # All frames are blurry - return best available by quality score
                    logger.warning(
                        "All frames below quality threshold",
                        extra={
                            "event_type": "all_frames_below_threshold",
                            "clip_path": str(clip_path),
                            "total_frames": len(extracted_frames)
                        }
                    )

                    # Sort by quality score (highest first) and return best available
                    all_frames_sorted = sorted(
                        extracted_frames,
                        key=lambda x: x[1],  # quality_score
                        reverse=True
                    )

                    # Return up to requested count, but at least min_frames
                    count_to_return = max(
                        min(frame_count, len(all_frames_sorted)),
                        min(FRAME_EXTRACT_MIN_COUNT, len(all_frames_sorted))
                    )
                    frames = [jpeg_bytes for _, _, _, jpeg_bytes in all_frames_sorted[:count_to_return]]

                    logger.info(
                        f"Frame extraction complete: {len(frames)} frames (best available, all below threshold)",
                        extra={
                            "event_type": "frame_extraction_success",
                            "clip_path": str(clip_path),
                            "frames_extracted": len(frames),
                            "total_bytes": sum(len(f) for f in frames),
                            "filter_blur": True,
                            "all_below_threshold": True
                        }
                    )
                    return frames

                # We have some usable frames but not enough
                # Ensure we return at least min_frames by including best of unusable
                frames_needed = max(FRAME_EXTRACT_MIN_COUNT, frame_count) - len(usable_frames)

                if frames_needed > 0 and unusable_frames:
                    # Sort unusable frames by quality (highest first)
                    unusable_sorted = sorted(
                        unusable_frames,
                        key=lambda x: x[1],  # quality_score
                        reverse=True
                    )

                    # Add best unusable frames to meet minimum
                    for frame_idx, quality_score, jpeg_bytes in unusable_sorted[:frames_needed]:
                        usable_frames.append((frame_idx, quality_score, jpeg_bytes))
                        logger.debug(
                            f"Including low-quality frame {frame_idx} (quality={quality_score:.2f}) to meet minimum",
                            extra={
                                "event_type": "low_quality_frame_included",
                                "frame_index": frame_idx,
                                "quality_score": quality_score
                            }
                        )

                # Sort by frame index to maintain temporal order
                usable_frames.sort(key=lambda x: x[0])

                frames = [jpeg_bytes for _, _, jpeg_bytes in usable_frames]

                logger.info(
                    f"Frame extraction complete: {len(frames)} frames",
                    extra={
                        "event_type": "frame_extraction_success",
                        "clip_path": str(clip_path),
                        "frames_extracted": len(frames),
                        "total_bytes": sum(len(f) for f in frames),
                        "filter_blur": True
                    }
                )

                return frames

        except FileNotFoundError as e:
            logger.error(
                f"Video file not found: {clip_path}",
                extra={
                    "event_type": "frame_extraction_file_not_found",
                    "clip_path": str(clip_path),
                    "error": str(e)
                }
            )
            return []

        except av.FFmpegError as e:
            logger.error(
                f"PyAV error processing video: {e}",
                extra={
                    "event_type": "frame_extraction_av_error",
                    "clip_path": str(clip_path),
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return []

        except Exception as e:
            logger.error(
                f"Unexpected error extracting frames: {type(e).__name__}",
                extra={
                    "event_type": "frame_extraction_error",
                    "clip_path": str(clip_path),
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return []


    async def extract_frames_with_timestamps(
        self,
        clip_path: Path,
        frame_count: int = 5,
        strategy: str = "evenly_spaced",
        filter_blur: bool = True,
        sampling_strategy: str = "uniform",
        offset_ms: int = 0
    ) -> Tuple[List[bytes], List[float]]:
        """
        Extract frames from a video clip with their timestamps (Story P3-7.5, P8-2.4, P9-2.1).

        Similar to extract_frames but also returns frame timestamps in seconds
        for display in the key frames gallery.

        Args:
            clip_path: Path to the video file (MP4)
            frame_count: Number of frames to extract (3-20, default 5)
            strategy: DEPRECATED - use sampling_strategy instead
            filter_blur: If True (default), filter out blurry/empty frames
            sampling_strategy: Frame selection strategy (Story P8-2.4):
                - "uniform": Evenly-spaced selection (default, legacy behavior)
                - "adaptive": Content-aware selection using histogram + SSIM
                - "hybrid": Extract more candidates, then filter adaptively
            offset_ms: Milliseconds to skip from clip start before extracting (Story P9-2.1)
                - Default 0 (no offset)
                - Helps capture subject when fully in frame instead of entering/exiting

        Returns:
            Tuple of (frames, timestamps):
            - frames: List of JPEG-encoded frame bytes
            - timestamps: List of float seconds from video start for each frame
        """
        logger.info(
            "Starting frame extraction with timestamps",
            extra={
                "event_type": "frame_extraction_with_timestamps_start",
                "clip_path": str(clip_path),
                "frame_count": frame_count,
                "sampling_strategy": sampling_strategy,
                "offset_ms": offset_ms
            }
        )

        # Validate frame_count within bounds
        if frame_count < FRAME_EXTRACT_MIN_COUNT:
            frame_count = FRAME_EXTRACT_MIN_COUNT
        elif frame_count > FRAME_EXTRACT_MAX_COUNT:
            frame_count = FRAME_EXTRACT_MAX_COUNT

        # Validate sampling_strategy
        valid_strategies = ["uniform", "adaptive", "hybrid"]
        if sampling_strategy not in valid_strategies:
            logger.warning(
                f"Invalid sampling_strategy '{sampling_strategy}', using 'uniform'",
                extra={
                    "event_type": "invalid_sampling_strategy",
                    "provided": sampling_strategy,
                    "fallback": "uniform"
                }
            )
            sampling_strategy = "uniform"

        try:
            with av.open(str(clip_path)) as container:
                if not container.streams.video:
                    logger.warning(
                        "No video stream found in file",
                        extra={
                            "event_type": "frame_extraction_no_video",
                            "clip_path": str(clip_path)
                        }
                    )
                    return [], []

                stream = container.streams.video[0]

                # Get total frame count and frame rate for timestamp calculation
                total_frames = stream.frames
                fps = float(stream.average_rate) if stream.average_rate else 30.0

                if total_frames is None or total_frames <= 0:
                    if container.duration and stream.average_rate:
                        duration_seconds = container.duration / 1_000_000.0
                        total_frames = int(duration_seconds * fps)
                    else:
                        return [], []

                if total_frames <= 0:
                    return [], []

                # Story P9-2.1: Apply extraction offset
                # Skip initial frames to capture subject when fully in frame
                offset_frames = 0
                effective_offset_ms = offset_ms

                if offset_ms > 0:
                    offset_frames = int((offset_ms / 1000.0) * fps)

                    # Handle edge case: clip shorter than offset
                    if offset_frames >= total_frames:
                        # Fall back to 0 offset with warning
                        logger.warning(
                            f"Clip too short for offset ({total_frames} frames < {offset_frames} offset frames), using offset=0",
                            extra={
                                "event_type": "frame_extraction_offset_fallback",
                                "clip_path": str(clip_path),
                                "total_frames": total_frames,
                                "offset_frames": offset_frames,
                                "offset_ms": offset_ms,
                                "fps": fps
                            }
                        )
                        offset_frames = 0
                        effective_offset_ms = 0
                    else:
                        logger.debug(
                            f"Applying extraction offset: skipping first {offset_frames} frames ({offset_ms}ms)",
                            extra={
                                "event_type": "frame_extraction_offset_applied",
                                "clip_path": str(clip_path),
                                "offset_frames": offset_frames,
                                "offset_ms": offset_ms,
                                "fps": fps,
                                "total_frames": total_frames,
                                "remaining_frames": total_frames - offset_frames
                            }
                        )

                # Calculate available frames after offset
                available_frames = total_frames - offset_frames

                if available_frames <= 0:
                    logger.warning(
                        "No frames available after offset",
                        extra={
                            "event_type": "frame_extraction_no_frames_after_offset",
                            "clip_path": str(clip_path),
                            "total_frames": total_frames,
                            "offset_frames": offset_frames
                        }
                    )
                    return [], []

                # Story P8-2.4: For adaptive/hybrid, extract more candidate frames
                # Story P9-2.1: Use available_frames (after offset) for index calculation
                if sampling_strategy in ["adaptive", "hybrid"]:
                    # Extract 3x the target count as candidates for adaptive selection
                    candidate_count = min(available_frames, frame_count * 3)
                    relative_indices = self._calculate_frame_indices(available_frames, candidate_count)
                else:
                    # Calculate which frames to extract (uniform strategy)
                    relative_indices = self._calculate_frame_indices(available_frames, frame_count)

                if not relative_indices:
                    return [], []

                # Story P9-2.1: Add offset to get actual frame indices in the video
                indices = [idx + offset_frames for idx in relative_indices]

                # Extract frames at calculated indices
                # Store as tuples: (frame_index, quality_score, rgb_array, jpeg_bytes)
                extracted_frames: List[Tuple[int, float, np.ndarray, bytes]] = []
                current_frame_index = 0
                indices_set = set(indices)

                for frame in container.decode(video=0):
                    if current_frame_index in indices_set:
                        img_array = frame.to_ndarray(format='rgb24')
                        quality_score = self._get_frame_quality_score(img_array)
                        jpeg_bytes = self._encode_frame(img_array)

                        extracted_frames.append(
                            (current_frame_index, quality_score, img_array, jpeg_bytes)
                        )

                        indices_set.remove(current_frame_index)
                        if not indices_set:
                            break

                    current_frame_index += 1

                # Story P8-2.4: Apply adaptive sampling if enabled
                if sampling_strategy in ["adaptive", "hybrid"] and len(extracted_frames) > frame_count:
                    from app.services.adaptive_sampler import get_adaptive_sampler

                    adaptive_sampler = get_adaptive_sampler()

                    # Prepare frames and timestamps for adaptive selection
                    candidate_frames = [f[2] for f in extracted_frames]  # rgb arrays
                    candidate_timestamps_ms = [f[0] * (1000.0 / fps) for f in extracted_frames]

                    # Select diverse frames
                    selected = await adaptive_sampler.select_diverse_frames(
                        frames=candidate_frames,
                        timestamps_ms=candidate_timestamps_ms,
                        target_count=frame_count,
                        fps=fps
                    )

                    # Build final frames list from selection
                    # Map selected indices back to extracted_frames
                    selected_indices = set()
                    final_extracted = []
                    for idx, _, ts_ms in selected:
                        # Find the extracted frame with matching original index
                        for ef in extracted_frames:
                            ef_ts_ms = ef[0] * (1000.0 / fps)
                            if abs(ef_ts_ms - ts_ms) < 1.0:  # Within 1ms tolerance
                                final_extracted.append(ef)
                                break

                    extracted_frames = final_extracted

                    logger.info(
                        f"Adaptive sampling selected {len(extracted_frames)} diverse frames from {len(candidate_frames)} candidates",
                        extra={
                            "event_type": "adaptive_sampling_applied",
                            "candidate_count": len(candidate_frames),
                            "selected_count": len(extracted_frames),
                            "sampling_strategy": sampling_strategy
                        }
                    )

                # Apply blur filtering if enabled
                if filter_blur:
                    usable_frames: List[Tuple[int, float, bytes]] = []
                    unusable_frames: List[Tuple[int, float, bytes]] = []

                    for frame_idx, quality_score, img_array, jpeg_bytes in extracted_frames:
                        if self._is_frame_usable(img_array):
                            usable_frames.append((frame_idx, quality_score, jpeg_bytes))
                        else:
                            unusable_frames.append((frame_idx, quality_score, jpeg_bytes))

                    # Use usable frames first, then best unusable if needed
                    if len(usable_frames) == 0:
                        all_frames_sorted = sorted(
                            extracted_frames,
                            key=lambda x: x[1],
                            reverse=True
                        )
                        count_to_return = max(
                            min(frame_count, len(all_frames_sorted)),
                            min(FRAME_EXTRACT_MIN_COUNT, len(all_frames_sorted))
                        )
                        final_frames = [
                            (idx, jpeg_bytes)
                            for idx, _, _, jpeg_bytes in all_frames_sorted[:count_to_return]
                        ]
                    elif len(usable_frames) >= frame_count:
                        final_frames = [
                            (idx, jpeg_bytes)
                            for idx, _, jpeg_bytes in usable_frames[:frame_count]
                        ]
                    else:
                        frames_needed = max(FRAME_EXTRACT_MIN_COUNT, frame_count) - len(usable_frames)
                        if frames_needed > 0 and unusable_frames:
                            unusable_sorted = sorted(
                                unusable_frames,
                                key=lambda x: x[1],
                                reverse=True
                            )
                            for frame_idx, quality_score, jpeg_bytes in unusable_sorted[:frames_needed]:
                                usable_frames.append((frame_idx, quality_score, jpeg_bytes))

                        usable_frames.sort(key=lambda x: x[0])
                        final_frames = [
                            (idx, jpeg_bytes)
                            for idx, _, jpeg_bytes in usable_frames
                        ]
                else:
                    final_frames = [
                        (idx, jpeg_bytes)
                        for idx, _, _, jpeg_bytes in extracted_frames
                    ]

                # Sort by frame index and extract frames and timestamps
                final_frames.sort(key=lambda x: x[0])
                frames = [jpeg_bytes for _, jpeg_bytes in final_frames]
                timestamps = [round(idx / fps, 2) for idx, _ in final_frames]

                logger.info(
                    f"Frame extraction with timestamps complete: {len(frames)} frames",
                    extra={
                        "event_type": "frame_extraction_with_timestamps_success",
                        "clip_path": str(clip_path),
                        "frames_extracted": len(frames),
                        "timestamps": timestamps,
                        "sampling_strategy": sampling_strategy
                    }
                )

                return frames, timestamps

        except Exception as e:
            logger.error(
                f"Error extracting frames with timestamps: {e}",
                extra={
                    "event_type": "frame_extraction_with_timestamps_error",
                    "clip_path": str(clip_path),
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            return [], []

    def encode_frame_for_storage(self, frame_bytes: bytes, max_width: int = 320, quality: int = 70) -> str:
        """
        Re-encode a frame as a smaller thumbnail for database storage (Story P3-7.5).

        Resizes frame to max_width and re-encodes at lower quality to minimize storage.

        Args:
            frame_bytes: JPEG-encoded frame bytes
            max_width: Maximum thumbnail width (default 320px)
            quality: JPEG quality 0-100 (default 70)

        Returns:
            Base64-encoded JPEG string (without data URI prefix)
        """
        import base64

        try:
            # Decode JPEG to PIL Image
            img = Image.open(io.BytesIO(frame_bytes))

            # Resize if needed (maintain aspect ratio)
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            # Encode as JPEG with lower quality
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')

        except Exception as e:
            logger.error(
                f"Error encoding frame for storage: {e}",
                extra={
                    "event_type": "frame_storage_encode_error",
                    "error_type": type(e).__name__
                }
            )
            return ""


# Backward compatible getter (delegates to @singleton decorator)
def get_frame_extractor() -> FrameExtractor:
    """
    Get the singleton FrameExtractor instance.

    Returns:
        FrameExtractor singleton instance

    Note: This is a backward-compatible wrapper. New code should use
          FrameExtractor() directly, which returns the singleton instance.
    """
    return FrameExtractor()


def reset_frame_extractor() -> None:
    """
    Reset the singleton instance (useful for testing).

    Note: This is a backward-compatible wrapper. New code should use
          FrameExtractor._reset_instance() directly.
    """
    FrameExtractor._reset_instance()
