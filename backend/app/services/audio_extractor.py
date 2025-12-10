"""
AudioExtractor for extracting audio tracks from video clips (Story P3-5.1, P3-5.2)

Provides functionality to:
- Extract audio tracks from video clips for speech transcription
- Output audio as WAV bytes (16kHz, mono) for OpenAI Whisper compatibility
- Handle videos without audio tracks gracefully
- Detect audio levels and log metrics for diagnostics
- Transcribe audio to text using OpenAI Whisper API (Story P3-5.2)

Architecture Reference: docs/architecture.md#Phase-3-Service-Architecture
"""
import asyncio
from datetime import datetime, timezone
import io
import logging
import math
import struct
import time
import wave
from pathlib import Path
from typing import Optional, Tuple

import av
import numpy as np
import openai

logger = logging.getLogger(__name__)

# Audio extraction configuration (Story P3-5.1)
AUDIO_SAMPLE_RATE = 16000  # 16kHz for Whisper compatibility
AUDIO_CHANNELS = 1  # Mono
AUDIO_SAMPLE_WIDTH = 2  # 16-bit signed PCM (2 bytes per sample)

# Silence detection thresholds
SILENCE_RMS_THRESHOLD = 0.001  # RMS threshold for silence detection (linear scale)
SILENCE_DB_THRESHOLD = -60  # dB threshold for logging (corresponds to ~0.001 RMS)

# Whisper API configuration (Story P3-5.2)
WHISPER_MODEL = "whisper-1"
WHISPER_COST_PER_MINUTE = 0.006  # $0.006 per minute
WHISPER_TIMEOUT_SECONDS = 30  # Max timeout for transcription


class AudioExtractor:
    """
    Service for extracting audio tracks from video clips and transcribing speech.

    Extracts audio from video files and converts it to WAV format
    suitable for speech transcription with OpenAI Whisper.

    Key features:
    - Extracts audio and resamples to 16kHz mono WAV
    - Handles videos without audio tracks (returns None)
    - Detects silence and logs audio level metrics
    - Transcribes audio to text using OpenAI Whisper (Story P3-5.2)
    - Graceful error handling (returns None, never raises)
    - Follows singleton pattern matching FrameExtractor

    Attributes:
        sample_rate: Target sample rate in Hz (16000)
        channels: Number of audio channels (1 for mono)
        sample_width: Sample width in bytes (2 for 16-bit PCM)
        openai_client: OpenAI client for Whisper API (initialized lazily)
    """

    def __init__(self):
        """
        Initialize AudioExtractor with default configuration.
        """
        self.sample_rate = AUDIO_SAMPLE_RATE
        self.channels = AUDIO_CHANNELS
        self.sample_width = AUDIO_SAMPLE_WIDTH
        self._openai_client: Optional[openai.OpenAI] = None

        logger.info(
            "AudioExtractor initialized",
            extra={
                "event_type": "audio_extractor_init",
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "sample_width": self.sample_width
            }
        )

    def _calculate_audio_level(self, samples: np.ndarray) -> Tuple[float, float]:
        """
        Calculate RMS level and peak amplitude from audio samples.

        Args:
            samples: Audio samples as numpy array (normalized to -1.0 to 1.0)

        Returns:
            Tuple of (rms_level, peak_amplitude) as linear values (0.0 to 1.0)
        """
        if len(samples) == 0:
            return 0.0, 0.0

        # Ensure float array for calculations
        samples = samples.astype(np.float64)

        # Calculate RMS (Root Mean Square)
        rms = np.sqrt(np.mean(samples ** 2))

        # Calculate peak amplitude
        peak = np.max(np.abs(samples))

        return float(rms), float(peak)

    def _rms_to_db(self, rms: float) -> float:
        """
        Convert RMS level to decibels.

        Args:
            rms: RMS level as linear value (0.0 to 1.0)

        Returns:
            Level in dB (0 dB = full scale, negative = quieter)
        """
        if rms <= 0:
            return -96.0  # Below noise floor
        db = 20 * math.log10(rms)
        return max(-96.0, db)  # Clamp to reasonable range

    def _is_silent(self, rms: float) -> bool:
        """
        Determine if audio is silent based on RMS level.

        Args:
            rms: RMS level as linear value

        Returns:
            True if audio is considered silent
        """
        return rms < SILENCE_RMS_THRESHOLD

    def _encode_wav(self, samples: np.ndarray, sample_rate: int) -> bytes:
        """
        Encode audio samples as WAV bytes.

        Args:
            samples: Audio samples as numpy array (int16 values)
            sample_rate: Sample rate in Hz

        Returns:
            WAV file bytes
        """
        buffer = io.BytesIO()

        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(self.sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.tobytes())

        return buffer.getvalue()

    async def extract_audio(self, clip_path: Path) -> Optional[bytes]:
        """
        Extract audio from a video clip as WAV bytes.

        Extracts the audio track from the video file, resamples to 16kHz mono,
        and returns as WAV bytes suitable for OpenAI Whisper transcription.

        Args:
            clip_path: Path to the video file (MP4)

        Returns:
            WAV-encoded audio bytes on success, None if:
            - No audio track in video
            - File not found
            - Any error during extraction

        Note:
            - Extraction completes within 2 seconds for 10-second clips (NFR)
            - WAV format: 16kHz, mono, 16-bit PCM
            - Silent audio is still returned (downstream handles silence)
            - All errors are logged with structured format
        """
        logger.info(
            "Starting audio extraction",
            extra={
                "event_type": "audio_extraction_start",
                "clip_path": str(clip_path)
            }
        )

        try:
            # Open video file with PyAV
            with av.open(str(clip_path)) as container:
                # Check for audio stream
                if not container.streams.audio:
                    logger.info(
                        "No audio track found in clip",
                        extra={
                            "event_type": "audio_extraction_no_audio",
                            "clip_path": str(clip_path)
                        }
                    )
                    return None

                audio_stream = container.streams.audio[0]

                # Log source audio format
                logger.debug(
                    "Source audio stream detected",
                    extra={
                        "event_type": "audio_stream_info",
                        "clip_path": str(clip_path),
                        "codec": audio_stream.codec_context.name if audio_stream.codec_context else "unknown",
                        "sample_rate": audio_stream.sample_rate,
                        "channels": audio_stream.channels,
                        "format": str(audio_stream.format.name) if audio_stream.format else "unknown"
                    }
                )

                # Create resampler to convert to target format
                # Target: 16kHz, mono, signed 16-bit PCM
                resampler = av.AudioResampler(
                    format='s16',  # Signed 16-bit
                    layout='mono',  # Mono channel
                    rate=self.sample_rate  # 16kHz
                )

                # Decode and resample all audio frames
                audio_samples = []
                total_samples = 0

                for frame in container.decode(audio=0):
                    # Resample frame to target format
                    resampled_frames = resampler.resample(frame)

                    for resampled_frame in resampled_frames:
                        if resampled_frame is not None:
                            # Get audio data as numpy array
                            # s16 format: signed 16-bit integers
                            samples = resampled_frame.to_ndarray()

                            # Flatten if multi-dimensional (should be 1D after mono resample)
                            if samples.ndim > 1:
                                samples = samples.flatten()

                            audio_samples.append(samples)
                            total_samples += len(samples)

                # Check if we got any audio
                if not audio_samples:
                    logger.warning(
                        "No audio frames decoded from clip",
                        extra={
                            "event_type": "audio_extraction_no_frames",
                            "clip_path": str(clip_path)
                        }
                    )
                    return None

                # Concatenate all samples
                all_samples = np.concatenate(audio_samples)

                # Calculate audio levels for diagnostics
                # Convert int16 to float for level calculation
                samples_float = all_samples.astype(np.float64) / 32768.0
                rms_level, peak_level = self._calculate_audio_level(samples_float)
                rms_db = self._rms_to_db(rms_level)
                peak_db = self._rms_to_db(peak_level)
                is_silent = self._is_silent(rms_level)

                # Log audio level metrics (AC3, AC5)
                logger.info(
                    "Audio level analysis complete",
                    extra={
                        "event_type": "audio_level_analysis",
                        "clip_path": str(clip_path),
                        "rms_level": rms_level,
                        "rms_db": rms_db,
                        "peak_level": peak_level,
                        "peak_db": peak_db,
                        "is_silent": is_silent,
                        "total_samples": len(all_samples),
                        "duration_seconds": len(all_samples) / self.sample_rate
                    }
                )

                # Encode as WAV
                wav_bytes = self._encode_wav(all_samples.astype(np.int16), self.sample_rate)

                logger.info(
                    "Audio extraction complete",
                    extra={
                        "event_type": "audio_extraction_success",
                        "clip_path": str(clip_path),
                        "wav_size_bytes": len(wav_bytes),
                        "duration_seconds": len(all_samples) / self.sample_rate,
                        "is_silent": is_silent
                    }
                )

                return wav_bytes

        except FileNotFoundError as e:
            logger.error(
                f"Audio file not found: {clip_path}",
                extra={
                    "event_type": "audio_extraction_file_not_found",
                    "clip_path": str(clip_path),
                    "error": str(e)
                }
            )
            return None

        except av.FFmpegError as e:
            logger.error(
                f"PyAV error processing audio: {e}",
                extra={
                    "event_type": "audio_extraction_av_error",
                    "clip_path": str(clip_path),
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return None

        except Exception as e:
            logger.error(
                f"Unexpected error extracting audio: {type(e).__name__}",
                extra={
                    "event_type": "audio_extraction_error",
                    "clip_path": str(clip_path),
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return None


    def _get_openai_client(self) -> Optional[openai.OpenAI]:
        """
        Get or create OpenAI client for Whisper API.

        Lazily initializes the client on first use, loading API key from database.

        Returns:
            OpenAI client instance, or None if no API key is configured
        """
        if self._openai_client is not None:
            return self._openai_client

        try:
            # Import here to avoid circular imports
            from app.core.database import SessionLocal
            from app.models.settings import Settings
            from app.utils.encryption import decrypt_password

            db = SessionLocal()
            try:
                # Load OpenAI API key from settings (same pattern as AIService)
                setting = db.query(Settings).filter(
                    Settings.key == "ai_api_key_openai"
                ).first()

                if not setting or not setting.value:
                    logger.warning(
                        "OpenAI API key not configured for Whisper transcription",
                        extra={"event_type": "whisper_no_api_key"}
                    )
                    return None

                # Decrypt the API key
                api_key = setting.value
                if api_key.startswith("encrypted:"):
                    api_key = decrypt_password(api_key)

                self._openai_client = openai.OpenAI(api_key=api_key)
                logger.info(
                    "OpenAI client initialized for Whisper",
                    extra={"event_type": "whisper_client_init"}
                )
                return self._openai_client

            finally:
                db.close()

        except Exception as e:
            logger.error(
                f"Failed to initialize OpenAI client: {e}",
                extra={
                    "event_type": "whisper_client_init_error",
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return None

    def _calculate_rms_from_wav_bytes(self, audio_bytes: bytes) -> float:
        """
        Calculate RMS level from WAV bytes.

        Args:
            audio_bytes: WAV-encoded audio bytes

        Returns:
            RMS level as linear value (0.0 to 1.0)
        """
        try:
            # Read WAV header and extract audio samples
            buffer = io.BytesIO(audio_bytes)
            with wave.open(buffer, 'rb') as wav_file:
                n_frames = wav_file.getnframes()
                if n_frames == 0:
                    return 0.0

                # Read all frames
                raw_data = wav_file.readframes(n_frames)

                # Convert to numpy array (16-bit signed PCM)
                samples = np.frombuffer(raw_data, dtype=np.int16)

                # Normalize to -1.0 to 1.0
                samples_float = samples.astype(np.float64) / 32768.0

                # Calculate RMS
                rms = np.sqrt(np.mean(samples_float ** 2))
                return float(rms)

        except Exception as e:
            logger.warning(
                f"Error calculating RMS from WAV bytes: {e}",
                extra={
                    "event_type": "rms_calculation_error",
                    "error": str(e)
                }
            )
            return 0.0

    def _calculate_duration_from_wav_bytes(self, audio_bytes: bytes) -> float:
        """
        Calculate audio duration in seconds from WAV bytes.

        Args:
            audio_bytes: WAV-encoded audio bytes

        Returns:
            Duration in seconds
        """
        try:
            buffer = io.BytesIO(audio_bytes)
            with wave.open(buffer, 'rb') as wav_file:
                n_frames = wav_file.getnframes()
                framerate = wav_file.getframerate()
                if framerate == 0:
                    return 0.0
                return n_frames / framerate
        except Exception:
            # Fallback calculation for raw PCM data
            # WAV header is typically 44 bytes
            header_size = 44
            audio_data_size = len(audio_bytes) - header_size
            if audio_data_size <= 0:
                return 0.0
            # 16-bit mono at 16kHz = 32000 bytes per second
            return audio_data_size / (self.sample_rate * self.sample_width)

    async def _track_whisper_usage(
        self,
        duration_seconds: float,
        response_time_ms: int,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """
        Track Whisper API usage in the ai_usage table.

        Args:
            duration_seconds: Audio duration in seconds
            response_time_ms: API response time in milliseconds
            success: Whether transcription succeeded
            error: Error message if failed
        """
        try:
            # Import here to avoid circular imports
            from app.core.database import SessionLocal
            from app.models.ai_usage import AIUsage

            # Calculate cost: $0.006 per minute
            cost_estimate = (duration_seconds / 60.0) * WHISPER_COST_PER_MINUTE

            db = SessionLocal()
            try:
                usage = AIUsage(
                    timestamp=datetime.now(timezone.utc),
                    provider="whisper",
                    success=success,
                    tokens_used=0,  # Whisper doesn't use tokens
                    response_time_ms=response_time_ms,
                    cost_estimate=cost_estimate,
                    error=error[:500] if error else None,
                    analysis_mode="transcription",
                    is_estimated=False
                )
                db.add(usage)
                db.commit()

                logger.info(
                    "Whisper usage tracked",
                    extra={
                        "event_type": "whisper_usage_tracked",
                        "duration_seconds": duration_seconds,
                        "response_time_ms": response_time_ms,
                        "cost_estimate": cost_estimate,
                        "success": success
                    }
                )

            finally:
                db.close()

        except Exception as e:
            # Don't fail transcription if usage tracking fails
            logger.warning(
                f"Failed to track Whisper usage: {e}",
                extra={
                    "event_type": "whisper_usage_track_error",
                    "error": str(e)
                }
            )

    async def transcribe(self, audio_bytes: bytes) -> Optional[str]:
        """
        Transcribe audio bytes to text using OpenAI Whisper API.

        Takes WAV-encoded audio bytes (16kHz, mono, 16-bit PCM) and returns
        the transcribed text. Handles silent audio, API errors, and timeouts
        gracefully.

        Args:
            audio_bytes: WAV-encoded audio bytes from extract_audio()

        Returns:
            Transcription text on success
            Empty string ("") if audio is silent or no speech detected
            None if transcription fails (API error, timeout, etc.)

        Note:
            - Uses whisper-1 model
            - Transcription completes within 5 seconds for typical 10-30s audio
            - Silent audio (RMS below threshold) skips API call and returns ""
            - All errors are logged with structured format
            - Usage is tracked in ai_usage table with provider="whisper"
        """
        start_time = time.time()

        # Calculate audio duration for usage tracking
        duration_seconds = self._calculate_duration_from_wav_bytes(audio_bytes)

        logger.info(
            "Starting audio transcription",
            extra={
                "event_type": "transcription_start",
                "audio_size_bytes": len(audio_bytes),
                "duration_seconds": duration_seconds
            }
        )

        # Check if audio is silent (AC3: Handle ambient noise)
        rms_level = self._calculate_rms_from_wav_bytes(audio_bytes)
        if self._is_silent(rms_level):
            logger.info(
                "No speech detected in audio",
                extra={
                    "event_type": "transcription_silent_audio",
                    "rms_level": rms_level,
                    "threshold": SILENCE_RMS_THRESHOLD
                }
            )
            # Track as successful with 0 cost (no API call made)
            elapsed_ms = int((time.time() - start_time) * 1000)
            await self._track_whisper_usage(
                duration_seconds=duration_seconds,
                response_time_ms=elapsed_ms,
                success=True,
                error=None
            )
            return ""

        # Get OpenAI client
        client = self._get_openai_client()
        if client is None:
            logger.error(
                "Cannot transcribe: OpenAI client not available",
                extra={"event_type": "transcription_no_client"}
            )
            return None

        try:
            # Create file-like object for OpenAI API
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "audio.wav"

            # Call Whisper API in thread pool (blocking call)
            # Use asyncio.wait_for for timeout handling
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.audio.transcriptions.create,
                    model=WHISPER_MODEL,
                    file=audio_file,
                    response_format="text"
                ),
                timeout=WHISPER_TIMEOUT_SECONDS
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Process transcription result
            transcription = response.strip() if response else ""

            # Handle empty response (no speech in audio)
            if not transcription:
                logger.info(
                    "No speech detected in audio",
                    extra={
                        "event_type": "transcription_no_speech",
                        "response_time_ms": elapsed_ms
                    }
                )
                await self._track_whisper_usage(
                    duration_seconds=duration_seconds,
                    response_time_ms=elapsed_ms,
                    success=True,
                    error=None
                )
                return ""

            # Successful transcription
            logger.info(
                "Audio transcription complete",
                extra={
                    "event_type": "transcription_success",
                    "response_time_ms": elapsed_ms,
                    "transcription_length": len(transcription),
                    "duration_seconds": duration_seconds
                }
            )

            await self._track_whisper_usage(
                duration_seconds=duration_seconds,
                response_time_ms=elapsed_ms,
                success=True,
                error=None
            )

            return transcription

        except asyncio.TimeoutError:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Transcription timeout after {WHISPER_TIMEOUT_SECONDS}s"
            logger.error(
                error_msg,
                extra={
                    "event_type": "transcription_timeout",
                    "timeout_seconds": WHISPER_TIMEOUT_SECONDS,
                    "response_time_ms": elapsed_ms
                }
            )
            await self._track_whisper_usage(
                duration_seconds=duration_seconds,
                response_time_ms=elapsed_ms,
                success=False,
                error=error_msg
            )
            return None

        except openai.RateLimitError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Whisper rate limit exceeded: {e}"
            logger.error(
                error_msg,
                extra={
                    "event_type": "transcription_rate_limit",
                    "error": str(e),
                    "response_time_ms": elapsed_ms
                }
            )
            await self._track_whisper_usage(
                duration_seconds=duration_seconds,
                response_time_ms=elapsed_ms,
                success=False,
                error=error_msg
            )
            return None

        except openai.APIError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Whisper API error: {e}"
            logger.error(
                error_msg,
                extra={
                    "event_type": "transcription_api_error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "response_time_ms": elapsed_ms
                }
            )
            await self._track_whisper_usage(
                duration_seconds=duration_seconds,
                response_time_ms=elapsed_ms,
                success=False,
                error=error_msg
            )
            return None

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Transcription failed: {type(e).__name__}: {e}"
            logger.error(
                error_msg,
                extra={
                    "event_type": "transcription_error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "response_time_ms": elapsed_ms
                }
            )
            await self._track_whisper_usage(
                duration_seconds=duration_seconds,
                response_time_ms=elapsed_ms,
                success=False,
                error=error_msg
            )
            return None


# Singleton instance
_audio_extractor: Optional[AudioExtractor] = None


def get_audio_extractor() -> AudioExtractor:
    """
    Get the singleton AudioExtractor instance.

    Creates the instance on first call.

    Returns:
        AudioExtractor singleton instance
    """
    global _audio_extractor
    if _audio_extractor is None:
        _audio_extractor = AudioExtractor()
    return _audio_extractor


def reset_audio_extractor() -> None:
    """
    Reset the singleton instance (useful for testing).
    """
    global _audio_extractor
    _audio_extractor = None
