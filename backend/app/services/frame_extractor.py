"""
FrameExtractor for extracting frames from video clips (Story P3-2.1, P3-2.2)

Provides functionality to:
- Extract multiple frames from video clips for AI analysis
- Select frames using evenly-spaced strategy (first/last guaranteed)
- Filter out blurry or empty frames using Laplacian variance (Story P3-2.2)
- Encode frames as JPEG with configurable quality
- Resize frames to max width for optimal AI token cost

Architecture Reference: docs/architecture.md#Phase-3-Service-Architecture
"""
import io
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import av
import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Frame extraction configuration (Story P3-2.1, FR8)
FRAME_EXTRACT_DEFAULT_COUNT = 5
FRAME_EXTRACT_MIN_COUNT = 3
FRAME_EXTRACT_MAX_COUNT = 10
FRAME_JPEG_QUALITY = 85
FRAME_MAX_WIDTH = 1280

# Blur detection configuration (Story P3-2.2, FR9)
FRAME_BLUR_THRESHOLD = 100  # Laplacian variance threshold for blur detection
FRAME_EMPTY_STD_THRESHOLD = 10  # Std deviation threshold for empty/single-color frames


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
        filter_blur: bool = True
    ) -> Tuple[List[bytes], List[float]]:
        """
        Extract frames from a video clip with their timestamps (Story P3-7.5).

        Similar to extract_frames but also returns frame timestamps in seconds
        for display in the key frames gallery.

        Args:
            clip_path: Path to the video file (MP4)
            frame_count: Number of frames to extract (3-10, default 5)
            strategy: Selection strategy (currently only "evenly_spaced")
            filter_blur: If True (default), filter out blurry/empty frames

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
                "frame_count": frame_count
            }
        )

        # Validate frame_count within bounds
        if frame_count < FRAME_EXTRACT_MIN_COUNT:
            frame_count = FRAME_EXTRACT_MIN_COUNT
        elif frame_count > FRAME_EXTRACT_MAX_COUNT:
            frame_count = FRAME_EXTRACT_MAX_COUNT

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

                # Calculate which frames to extract
                indices = self._calculate_frame_indices(total_frames, frame_count)
                if not indices:
                    return [], []

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
                        "timestamps": timestamps
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


# Singleton instance
_frame_extractor: Optional[FrameExtractor] = None


def get_frame_extractor() -> FrameExtractor:
    """
    Get the singleton FrameExtractor instance.

    Creates the instance on first call.

    Returns:
        FrameExtractor singleton instance
    """
    global _frame_extractor
    if _frame_extractor is None:
        _frame_extractor = FrameExtractor()
    return _frame_extractor


def reset_frame_extractor() -> None:
    """
    Reset the singleton instance (useful for testing).
    """
    global _frame_extractor
    _frame_extractor = None
