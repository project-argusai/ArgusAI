"""
Tests for AudioStreamService (Story P6-3.1)

Tests audio extraction from RTSP streams, codec detection, and buffer operations.
"""
import pytest
import numpy as np
import time
from unittest.mock import Mock, MagicMock, patch

from app.services.audio_stream_service import (
    AudioRingBuffer,
    AudioStreamExtractor,
    AudioChunk,
    get_audio_stream_extractor,
    reset_audio_stream_extractor,
    DEFAULT_AUDIO_BUFFER_SECONDS,
    AUDIO_SAMPLE_RATE,
    CODEC_NORMALIZE_MAP,
    SUPPORTED_CODECS,
)


class TestAudioRingBuffer:
    """Tests for AudioRingBuffer class"""

    def test_init_creates_empty_buffer(self):
        """Test buffer initializes empty"""
        buffer = AudioRingBuffer()

        assert buffer.is_empty
        assert buffer.duration_seconds == 0.0
        assert buffer.max_samples == int(DEFAULT_AUDIO_BUFFER_SECONDS * AUDIO_SAMPLE_RATE)

    def test_init_with_custom_params(self):
        """Test buffer with custom buffer_seconds and sample_rate"""
        buffer = AudioRingBuffer(buffer_seconds=10.0, sample_rate=8000)

        assert buffer.buffer_seconds == 10.0
        assert buffer.sample_rate == 8000
        assert buffer.max_samples == 80000  # 10 * 8000

    def test_add_samples(self):
        """Test adding samples to buffer (AC#3)"""
        buffer = AudioRingBuffer(buffer_seconds=5.0, sample_rate=16000)

        # Add 1 second of samples (16000 samples)
        samples = np.zeros(16000, dtype=np.int16)
        buffer.add(samples, time.time())

        assert not buffer.is_empty
        assert buffer.duration_seconds == pytest.approx(1.0, rel=0.01)

    def test_buffer_overflow_trims_old_data(self):
        """Test buffer trims oldest data when exceeding max duration (AC#3)"""
        buffer = AudioRingBuffer(buffer_seconds=2.0, sample_rate=16000)

        # Add 3 seconds of samples (should only keep 2 seconds)
        for _ in range(3):
            samples = np.zeros(16000, dtype=np.int16)  # 1 second each
            buffer.add(samples, time.time())

        # Should be capped at approximately 2 seconds
        assert buffer.duration_seconds <= 2.5  # Allow some tolerance

    def test_get_latest_returns_audio_chunk(self):
        """Test get_latest returns AudioChunk with correct format"""
        buffer = AudioRingBuffer(buffer_seconds=5.0, sample_rate=16000)

        # Add samples
        samples = np.arange(16000, dtype=np.int16)  # 1 second
        buffer.add(samples, time.time())

        chunk = buffer.get_latest(duration_seconds=0.5)

        assert chunk is not None
        assert isinstance(chunk, AudioChunk)
        assert chunk.sample_rate == 16000
        assert chunk.channels == 1
        assert len(chunk.samples) == 8000  # 0.5 seconds worth

    def test_get_latest_returns_none_when_empty(self):
        """Test get_latest returns None when buffer empty"""
        buffer = AudioRingBuffer()

        assert buffer.get_latest() is None

    def test_get_all_returns_all_samples(self):
        """Test get_all returns entire buffer contents"""
        buffer = AudioRingBuffer(buffer_seconds=5.0, sample_rate=16000)

        # Add 2 seconds of samples
        samples1 = np.arange(16000, dtype=np.int16)
        samples2 = np.arange(16000, 32000, dtype=np.int16)
        buffer.add(samples1, time.time())
        buffer.add(samples2, time.time())

        chunk = buffer.get_all()

        assert chunk is not None
        assert len(chunk.samples) == 32000

    def test_clear_empties_buffer(self):
        """Test clear removes all data"""
        buffer = AudioRingBuffer()

        # Add samples
        samples = np.zeros(16000, dtype=np.int16)
        buffer.add(samples, time.time())

        assert not buffer.is_empty

        buffer.clear()

        assert buffer.is_empty
        assert buffer.duration_seconds == 0.0


class TestAudioStreamExtractor:
    """Tests for AudioStreamExtractor class"""

    def setup_method(self):
        """Reset singleton before each test"""
        reset_audio_stream_extractor()

    def test_singleton_pattern(self):
        """Test get_audio_stream_extractor returns same instance"""
        extractor1 = get_audio_stream_extractor()
        extractor2 = get_audio_stream_extractor()

        assert extractor1 is extractor2

    def test_get_or_create_buffer(self):
        """Test buffer creation for camera"""
        extractor = AudioStreamExtractor()

        buffer = extractor.get_or_create_buffer("cam-123")

        assert buffer is not None
        assert isinstance(buffer, AudioRingBuffer)

        # Same camera returns same buffer
        buffer2 = extractor.get_or_create_buffer("cam-123")
        assert buffer is buffer2

    def test_remove_buffer(self):
        """Test buffer removal"""
        extractor = AudioStreamExtractor()

        # Create buffer
        extractor.get_or_create_buffer("cam-123")

        # Remove it
        extractor.remove_buffer("cam-123")

        # New call creates new buffer
        buffer = extractor.get_or_create_buffer("cam-123")
        assert buffer is not None

    def test_detect_audio_codec_aac(self):
        """Test codec detection for AAC (AC#2)"""
        extractor = AudioStreamExtractor()

        # Mock PyAV container with AAC audio
        mock_container = Mock()
        mock_audio_stream = Mock()
        mock_audio_stream.codec_context.name = "aac"
        mock_audio_stream.sample_rate = 44100
        mock_audio_stream.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        codec = extractor.detect_audio_codec(mock_container, "cam-123")

        assert codec == "aac"

    def test_detect_audio_codec_pcmu(self):
        """Test codec detection for G.711 PCMU (AC#2)"""
        extractor = AudioStreamExtractor()

        mock_container = Mock()
        mock_audio_stream = Mock()
        mock_audio_stream.codec_context.name = "pcm_mulaw"
        mock_audio_stream.sample_rate = 8000
        mock_audio_stream.channels = 1
        mock_container.streams.audio = [mock_audio_stream]

        codec = extractor.detect_audio_codec(mock_container, "cam-123")

        assert codec == "pcmu"  # Normalized name

    def test_detect_audio_codec_opus(self):
        """Test codec detection for Opus (AC#2)"""
        extractor = AudioStreamExtractor()

        mock_container = Mock()
        mock_audio_stream = Mock()
        mock_audio_stream.codec_context.name = "opus"
        mock_audio_stream.sample_rate = 48000
        mock_audio_stream.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        codec = extractor.detect_audio_codec(mock_container, "cam-123")

        assert codec == "opus"

    def test_detect_audio_codec_no_audio(self):
        """Test codec detection when no audio stream present"""
        extractor = AudioStreamExtractor()

        mock_container = Mock()
        mock_container.streams.audio = []  # No audio streams

        codec = extractor.detect_audio_codec(mock_container, "cam-123")

        assert codec is None

    def test_get_detected_codec(self):
        """Test retrieving detected codec for camera"""
        extractor = AudioStreamExtractor()

        # Mock detection
        mock_container = Mock()
        mock_audio_stream = Mock()
        mock_audio_stream.codec_context.name = "aac"
        mock_audio_stream.sample_rate = 44100
        mock_audio_stream.channels = 2
        mock_container.streams.audio = [mock_audio_stream]

        extractor.detect_audio_codec(mock_container, "cam-123")

        assert extractor.get_detected_codec("cam-123") == "aac"
        assert extractor.get_detected_codec("cam-unknown") is None

    def test_get_buffer_status(self):
        """Test buffer status retrieval"""
        extractor = AudioStreamExtractor()

        # No buffer yet
        status = extractor.get_buffer_status("cam-123")
        assert status["has_buffer"] is False

        # Create buffer and add data
        buffer = extractor.get_or_create_buffer("cam-123")
        samples = np.zeros(16000, dtype=np.int16)
        buffer.add(samples, time.time())

        status = extractor.get_buffer_status("cam-123")
        assert status["has_buffer"] is True
        assert status["is_empty"] is False
        assert status["duration_seconds"] > 0

    def test_get_latest_audio(self):
        """Test getting latest audio from buffer"""
        extractor = AudioStreamExtractor()

        # Create buffer and add samples
        buffer = extractor.get_or_create_buffer("cam-123")
        samples = np.arange(16000, dtype=np.int16)
        buffer.add(samples, time.time())

        chunk = extractor.get_latest_audio("cam-123", duration_seconds=0.5)

        assert chunk is not None
        assert len(chunk.samples) == 8000

    def test_get_latest_audio_no_buffer(self):
        """Test get_latest_audio returns None when no buffer"""
        extractor = AudioStreamExtractor()

        chunk = extractor.get_latest_audio("cam-unknown")

        assert chunk is None


class TestCodecNormalization:
    """Tests for codec name normalization"""

    def test_aac_variants(self):
        """Test AAC codec variants are normalized"""
        assert CODEC_NORMALIZE_MAP.get("aac") == "aac"
        assert CODEC_NORMALIZE_MAP.get("aac_latm") == "aac"

    def test_pcm_variants(self):
        """Test PCM codec variants are normalized"""
        assert CODEC_NORMALIZE_MAP.get("pcm_mulaw") == "pcmu"
        assert CODEC_NORMALIZE_MAP.get("pcm_alaw") == "pcma"
        assert CODEC_NORMALIZE_MAP.get("pcm_s16le") == "pcm"
        assert CODEC_NORMALIZE_MAP.get("pcm_s16be") == "pcm"

    def test_supported_codecs_defined(self):
        """Test all supported codecs have descriptions"""
        assert "aac" in SUPPORTED_CODECS
        assert "pcm_mulaw" in SUPPORTED_CODECS
        assert "opus" in SUPPORTED_CODECS


class TestAudioChunk:
    """Tests for AudioChunk dataclass"""

    def test_audio_chunk_creation(self):
        """Test AudioChunk creation with expected fields"""
        samples = np.zeros(16000, dtype=np.int16)

        chunk = AudioChunk(
            samples=samples,
            timestamp=time.time(),
            sample_rate=16000,
            channels=1
        )

        assert chunk.samples is samples
        assert chunk.sample_rate == 16000
        assert chunk.channels == 1
        assert chunk.timestamp > 0


class TestPerformance:
    """Performance tests for audio extraction (AC#5)"""

    def test_buffer_add_performance(self):
        """Test buffer add operations are fast enough"""
        buffer = AudioRingBuffer(buffer_seconds=5.0, sample_rate=16000)
        samples = np.zeros(160, dtype=np.int16)  # 10ms of audio

        iterations = 1000
        start_time = time.time()

        for _ in range(iterations):
            buffer.add(samples, time.time())

        elapsed = time.time() - start_time
        per_iteration = (elapsed / iterations) * 1000  # ms

        # Should complete 1000 iterations in reasonable time
        # Each add should take < 1ms
        assert per_iteration < 1.0, f"Buffer add too slow: {per_iteration:.3f}ms"

    def test_buffer_get_latest_performance(self):
        """Test buffer get_latest is fast"""
        buffer = AudioRingBuffer(buffer_seconds=5.0, sample_rate=16000)

        # Fill buffer
        for _ in range(50):
            samples = np.zeros(16000, dtype=np.int16)
            buffer.add(samples, time.time())

        iterations = 1000
        start_time = time.time()

        for _ in range(iterations):
            buffer.get_latest(duration_seconds=1.0)

        elapsed = time.time() - start_time
        per_iteration = (elapsed / iterations) * 1000  # ms

        # Each get should take < 5ms
        assert per_iteration < 5.0, f"Buffer get too slow: {per_iteration:.3f}ms"


class TestAudioDisabled:
    """Tests verifying no impact when audio disabled (AC#5)"""

    def test_extractor_lazy_initialization(self):
        """Test extractor doesn't create resources until needed"""
        reset_audio_stream_extractor()

        # Getting the singleton doesn't create buffers
        extractor = get_audio_stream_extractor()

        # No buffers exist initially
        status = extractor.get_buffer_status("any-camera")
        assert status["has_buffer"] is False

    def test_buffer_operations_thread_safe(self):
        """Test buffer operations are thread-safe"""
        import threading

        buffer = AudioRingBuffer(buffer_seconds=2.0, sample_rate=16000)
        errors = []

        def writer():
            for _ in range(100):
                try:
                    samples = np.zeros(1600, dtype=np.int16)
                    buffer.add(samples, time.time())
                except Exception as e:
                    errors.append(e)

        def reader():
            for _ in range(100):
                try:
                    buffer.get_latest(duration_seconds=0.1)
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer) for _ in range(3)
        ] + [
            threading.Thread(target=reader) for _ in range(3)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
