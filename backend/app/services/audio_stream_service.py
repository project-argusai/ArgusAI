"""
AudioStreamService for real-time audio extraction from RTSP streams (Story P6-3.1)

Provides functionality to:
- Extract audio streams from live RTSP feeds using PyAV
- Detect and validate audio codecs (AAC, G.711/PCMU, Opus)
- Maintain a thread-safe ring buffer for audio samples
- Support enable/disable per camera via configuration

This is distinct from audio_extractor.py which extracts audio from video clips.
This service handles live RTSP streams for real-time audio capture.

Architecture Reference: docs/epics-phase6.md#Story P6-3.1
"""
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

import av
import numpy as np

logger = logging.getLogger(__name__)

# Audio stream configuration
DEFAULT_AUDIO_BUFFER_SECONDS = 5  # Keep ~5 seconds of audio in buffer
AUDIO_SAMPLE_RATE = 16000  # Target sample rate for consistency with whisper
AUDIO_CHANNELS = 1  # Mono
AUDIO_SAMPLE_WIDTH = 2  # 16-bit signed PCM

# Supported audio codecs
SUPPORTED_CODECS = {
    'aac': 'Advanced Audio Coding (most common)',
    'pcm_mulaw': 'G.711 mu-law (PCMU)',
    'pcm_alaw': 'G.711 A-law (PCMA)',
    'opus': 'Opus codec (modern, efficient)',
    'mp3': 'MP3 audio',
    'pcm_s16le': 'PCM 16-bit little-endian',
    'pcm_s16be': 'PCM 16-bit big-endian',
}

# Codec name normalization map
CODEC_NORMALIZE_MAP = {
    'aac': 'aac',
    'aac_latm': 'aac',
    'pcm_mulaw': 'pcmu',
    'pcm_alaw': 'pcma',
    'opus': 'opus',
    'mp3': 'mp3',
    'mp3float': 'mp3',
    'pcm_s16le': 'pcm',
    'pcm_s16be': 'pcm',
}


@dataclass
class AudioChunk:
    """Container for audio data with metadata"""
    samples: np.ndarray  # Audio samples as int16 array
    timestamp: float  # Capture timestamp
    sample_rate: int
    channels: int


class AudioRingBuffer:
    """
    Thread-safe ring buffer for audio samples.

    Maintains a fixed-duration buffer of audio data that can be
    read asynchronously while being written to from the capture thread.
    """

    def __init__(self, buffer_seconds: float = DEFAULT_AUDIO_BUFFER_SECONDS, sample_rate: int = AUDIO_SAMPLE_RATE):
        """
        Initialize the audio ring buffer.

        Args:
            buffer_seconds: Duration of audio to keep in buffer
            sample_rate: Audio sample rate in Hz
        """
        self.buffer_seconds = buffer_seconds
        self.sample_rate = sample_rate
        self.max_samples = int(buffer_seconds * sample_rate)

        self._lock = threading.Lock()
        self._buffer: Deque[np.ndarray] = deque()
        self._total_samples = 0
        self._last_timestamp = 0.0

        logger.debug(
            "AudioRingBuffer initialized",
            extra={
                "event_type": "audio_buffer_init",
                "buffer_seconds": buffer_seconds,
                "sample_rate": sample_rate,
                "max_samples": self.max_samples
            }
        )

    def add(self, samples: np.ndarray, timestamp: float) -> None:
        """
        Add audio samples to the buffer.

        Args:
            samples: Audio samples as numpy array (int16)
            timestamp: Capture timestamp
        """
        with self._lock:
            self._buffer.append(samples)
            self._total_samples += len(samples)
            self._last_timestamp = timestamp

            # Trim buffer if it exceeds max duration
            while self._total_samples > self.max_samples and len(self._buffer) > 1:
                removed = self._buffer.popleft()
                self._total_samples -= len(removed)

    def get_latest(self, duration_seconds: float = 1.0) -> Optional[AudioChunk]:
        """
        Get the latest audio samples from the buffer.

        Args:
            duration_seconds: Duration of audio to retrieve

        Returns:
            AudioChunk with samples, or None if buffer is empty
        """
        samples_needed = int(duration_seconds * self.sample_rate)

        with self._lock:
            if self._total_samples == 0:
                return None

            # Collect samples from recent chunks
            collected = []
            collected_count = 0

            for chunk in reversed(self._buffer):
                collected.insert(0, chunk)
                collected_count += len(chunk)
                if collected_count >= samples_needed:
                    break

            if not collected:
                return None

            # Concatenate and trim to exact duration
            all_samples = np.concatenate(collected)
            if len(all_samples) > samples_needed:
                all_samples = all_samples[-samples_needed:]

            return AudioChunk(
                samples=all_samples,
                timestamp=self._last_timestamp,
                sample_rate=self.sample_rate,
                channels=AUDIO_CHANNELS
            )

    def get_all(self) -> Optional[AudioChunk]:
        """
        Get all audio samples currently in the buffer.

        Returns:
            AudioChunk with all samples, or None if buffer is empty
        """
        with self._lock:
            if self._total_samples == 0:
                return None

            all_samples = np.concatenate(list(self._buffer))

            return AudioChunk(
                samples=all_samples,
                timestamp=self._last_timestamp,
                sample_rate=self.sample_rate,
                channels=AUDIO_CHANNELS
            )

    def clear(self) -> None:
        """Clear all samples from the buffer."""
        with self._lock:
            self._buffer.clear()
            self._total_samples = 0
            self._last_timestamp = 0.0

    @property
    def duration_seconds(self) -> float:
        """Current duration of audio in buffer in seconds."""
        with self._lock:
            return self._total_samples / self.sample_rate if self.sample_rate > 0 else 0.0

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        with self._lock:
            return self._total_samples == 0


class AudioStreamExtractor:
    """
    Service for extracting audio from RTSP streams.

    Handles real-time audio extraction from RTSP feeds, detecting codecs,
    resampling to standard format, and maintaining audio buffers per camera.

    This is designed to be called from the camera capture loop when
    audio_enabled is True for a camera.
    """

    def __init__(self):
        """Initialize AudioStreamExtractor."""
        self._buffers: Dict[str, AudioRingBuffer] = {}
        self._codecs: Dict[str, str] = {}  # camera_id -> detected codec
        self._lock = threading.Lock()

        logger.info(
            "AudioStreamExtractor initialized",
            extra={"event_type": "audio_stream_extractor_init"}
        )

    def get_or_create_buffer(self, camera_id: str) -> AudioRingBuffer:
        """
        Get or create an audio buffer for a camera.

        Args:
            camera_id: Camera identifier

        Returns:
            AudioRingBuffer for the camera
        """
        with self._lock:
            if camera_id not in self._buffers:
                self._buffers[camera_id] = AudioRingBuffer()
                logger.debug(
                    f"Created audio buffer for camera {camera_id}",
                    extra={
                        "event_type": "audio_buffer_created",
                        "camera_id": camera_id
                    }
                )
            return self._buffers[camera_id]

    def remove_buffer(self, camera_id: str) -> None:
        """
        Remove audio buffer for a camera.

        Args:
            camera_id: Camera identifier
        """
        with self._lock:
            if camera_id in self._buffers:
                del self._buffers[camera_id]
                logger.debug(
                    f"Removed audio buffer for camera {camera_id}",
                    extra={
                        "event_type": "audio_buffer_removed",
                        "camera_id": camera_id
                    }
                )
            if camera_id in self._codecs:
                del self._codecs[camera_id]

    def detect_audio_codec(self, container: av.container.Container, camera_id: str) -> Optional[str]:
        """
        Detect audio codec from a PyAV container.

        Args:
            container: Open PyAV container (RTSP stream)
            camera_id: Camera identifier

        Returns:
            Normalized codec name ('aac', 'pcmu', 'opus', etc.) or None if no audio
        """
        try:
            if not container.streams.audio:
                logger.debug(
                    f"No audio stream in container for camera {camera_id}",
                    extra={
                        "event_type": "audio_no_stream",
                        "camera_id": camera_id
                    }
                )
                return None

            audio_stream = container.streams.audio[0]
            codec_context = audio_stream.codec_context

            if not codec_context:
                return None

            raw_codec = codec_context.name
            normalized = CODEC_NORMALIZE_MAP.get(raw_codec, raw_codec)

            # Store detected codec
            with self._lock:
                self._codecs[camera_id] = normalized

            logger.info(
                f"Detected audio codec for camera {camera_id}: {raw_codec} -> {normalized}",
                extra={
                    "event_type": "audio_codec_detected",
                    "camera_id": camera_id,
                    "raw_codec": raw_codec,
                    "normalized_codec": normalized,
                    "sample_rate": audio_stream.sample_rate,
                    "channels": audio_stream.channels
                }
            )

            return normalized

        except Exception as e:
            logger.warning(
                f"Error detecting audio codec for camera {camera_id}: {e}",
                extra={
                    "event_type": "audio_codec_detection_error",
                    "camera_id": camera_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return None

    def get_detected_codec(self, camera_id: str) -> Optional[str]:
        """
        Get the detected codec for a camera.

        Args:
            camera_id: Camera identifier

        Returns:
            Detected codec name or None
        """
        with self._lock:
            return self._codecs.get(camera_id)

    def extract_audio_frame(
        self,
        container: av.container.Container,
        camera_id: str,
        resampler: Optional[av.AudioResampler] = None
    ) -> Tuple[Optional[np.ndarray], Optional[av.AudioResampler]]:
        """
        Extract a single audio frame from the container.

        This should be called from the capture loop alongside video frame extraction.
        Returns a resampler that should be reused across calls for efficiency.

        Args:
            container: Open PyAV container
            camera_id: Camera identifier
            resampler: Optional resampler from previous call

        Returns:
            Tuple of (audio_samples, resampler) - samples may be None if no audio available
        """
        try:
            if not container.streams.audio:
                return None, resampler

            # Create resampler on first call
            if resampler is None:
                resampler = av.AudioResampler(
                    format='s16',
                    layout='mono',
                    rate=AUDIO_SAMPLE_RATE
                )

            # Decode one audio frame
            for frame in container.decode(audio=0):
                # Resample to target format
                resampled_frames = resampler.resample(frame)

                for resampled_frame in resampled_frames:
                    if resampled_frame is not None:
                        samples = resampled_frame.to_ndarray()

                        # Flatten if multi-dimensional
                        if samples.ndim > 1:
                            samples = samples.flatten()

                        # Add to buffer
                        buffer = self.get_or_create_buffer(camera_id)
                        buffer.add(samples.astype(np.int16), time.time())

                        return samples.astype(np.int16), resampler

                # Only process one frame per call to not block video capture
                break

            return None, resampler

        except av.error.EOFError:
            # End of stream
            return None, resampler
        except Exception as e:
            logger.warning(
                f"Error extracting audio frame for camera {camera_id}: {e}",
                extra={
                    "event_type": "audio_frame_extraction_error",
                    "camera_id": camera_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return None, resampler

    def process_audio_from_stream(
        self,
        rtsp_url: str,
        camera_id: str,
        timeout: float = 5.0
    ) -> Optional[str]:
        """
        Open RTSP stream, detect audio codec, and optionally capture initial samples.

        This is useful for testing audio availability and codec detection
        without integrating into the capture loop.

        Args:
            rtsp_url: RTSP URL to connect to
            camera_id: Camera identifier
            timeout: Connection timeout in seconds

        Returns:
            Detected codec name or None if no audio
        """
        try:
            # Configure input options for RTSP
            options = {
                'rtsp_transport': 'tcp',
                'stimeout': str(int(timeout * 1000000)),  # microseconds
            }

            container = av.open(rtsp_url, options=options, timeout=timeout)

            try:
                # Detect codec
                codec = self.detect_audio_codec(container, camera_id)

                if codec:
                    # Capture a few frames to populate buffer
                    resampler = None
                    for _ in range(10):  # Capture ~10 frames
                        _, resampler = self.extract_audio_frame(container, camera_id, resampler)

                return codec

            finally:
                container.close()

        except av.error.ExitError as e:
            logger.warning(
                f"RTSP stream exit for camera {camera_id}: {e}",
                extra={
                    "event_type": "audio_stream_exit",
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )
            return None
        except Exception as e:
            logger.error(
                f"Error processing audio stream for camera {camera_id}: {e}",
                extra={
                    "event_type": "audio_stream_error",
                    "camera_id": camera_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return None

    def get_latest_audio(self, camera_id: str, duration_seconds: float = 1.0) -> Optional[AudioChunk]:
        """
        Get the latest audio from a camera's buffer.

        Args:
            camera_id: Camera identifier
            duration_seconds: Duration of audio to retrieve

        Returns:
            AudioChunk with samples or None if no audio
        """
        with self._lock:
            buffer = self._buffers.get(camera_id)
            if buffer is None:
                return None

        return buffer.get_latest(duration_seconds)

    def get_buffer_status(self, camera_id: str) -> Dict:
        """
        Get status information about a camera's audio buffer.

        Args:
            camera_id: Camera identifier

        Returns:
            Dict with buffer status (duration, is_empty, codec)
        """
        with self._lock:
            buffer = self._buffers.get(camera_id)
            codec = self._codecs.get(camera_id)

        if buffer is None:
            return {
                "has_buffer": False,
                "duration_seconds": 0.0,
                "is_empty": True,
                "codec": None
            }

        return {
            "has_buffer": True,
            "duration_seconds": buffer.duration_seconds,
            "is_empty": buffer.is_empty,
            "codec": codec
        }


# Singleton instance
_audio_stream_extractor: Optional[AudioStreamExtractor] = None


def get_audio_stream_extractor() -> AudioStreamExtractor:
    """
    Get the singleton AudioStreamExtractor instance.

    Returns:
        AudioStreamExtractor singleton instance
    """
    global _audio_stream_extractor
    if _audio_stream_extractor is None:
        _audio_stream_extractor = AudioStreamExtractor()
    return _audio_stream_extractor


def reset_audio_stream_extractor() -> None:
    """
    Reset the singleton instance (useful for testing).
    """
    global _audio_stream_extractor
    _audio_stream_extractor = None
