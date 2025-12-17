"""Tests for AudioEventHandler Service (Story P6-3.2)

Tests the audio event handler including:
- Event enrichment with audio data (AC#4)
- Audio event creation
- Integration with AudioStreamService and AudioEventDetector
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from app.services.audio_event_handler import (
    AudioEventHandler,
    AudioEventCreationResult,
    get_audio_event_handler,
    initialize_audio_event_handler,
)
from app.services.audio_classifiers import AudioEventType, AudioClassificationResult
from app.services.audio_classifiers.mock import MockAudioClassifier
from app.services.audio_event_detector import AudioEventDetector, AudioDetectionResult
from app.services.audio_stream_service import AudioChunk


class TestAudioEventCreationResult:
    """Tests for AudioEventCreationResult dataclass"""

    def test_result_creation_success(self):
        """Test creating successful result"""
        result = AudioEventCreationResult(
            event_id="test-uuid",
            audio_event_type=AudioEventType.GLASS_BREAK,
            confidence=0.85,
            created=True,
            reason="created"
        )

        assert result.event_id == "test-uuid"
        assert result.audio_event_type == AudioEventType.GLASS_BREAK
        assert result.confidence == 0.85
        assert result.created is True
        assert result.reason == "created"

    def test_result_creation_no_event(self):
        """Test creating result when no event created"""
        result = AudioEventCreationResult(
            event_id=None,
            audio_event_type=None,
            confidence=None,
            created=False,
            reason="no_audio_buffer"
        )

        assert result.event_id is None
        assert result.created is False


class TestAudioEventHandler:
    """Tests for AudioEventHandler service"""

    @pytest.fixture
    def mock_audio_extractor(self):
        """Create mock audio stream extractor"""
        extractor = MagicMock()
        return extractor

    @pytest.fixture
    def mock_audio_detector(self):
        """Create mock audio event detector"""
        detector = MagicMock(spec=AudioEventDetector)
        return detector

    @pytest.fixture
    def mock_db(self):
        """Create mock database session"""
        db = MagicMock()
        return db

    @pytest.fixture
    def audio_chunk(self):
        """Create test audio chunk"""
        return AudioChunk(
            samples=np.zeros(16000, dtype=np.int16),
            timestamp=1234567890.0,
            sample_rate=16000,
            channels=1
        )

    @pytest.fixture
    def detection_result(self):
        """Create test detection result"""
        return AudioDetectionResult(
            event_type=AudioEventType.GLASS_BREAK,
            confidence=0.85,
            duration_ms=1000,
            classifier_name="mock_v1",
            passed_threshold=True,
            threshold_used=0.70,
        )

    @pytest.mark.asyncio
    async def test_process_camera_audio_disabled(self, mock_audio_extractor, mock_audio_detector, mock_db):
        """Test processing when audio disabled for camera"""
        handler = AudioEventHandler(
            audio_extractor=mock_audio_extractor,
            audio_detector=mock_audio_detector,
        )

        # Mock camera with audio_enabled=False
        mock_camera = MagicMock()
        mock_camera.audio_enabled = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_camera

        result = await handler.process_camera_audio(mock_db, "camera-123")

        assert result.created is False
        assert result.reason == "audio_disabled"

    @pytest.mark.asyncio
    async def test_process_camera_audio_no_buffer(self, mock_audio_extractor, mock_audio_detector, mock_db):
        """Test processing when no audio buffer available"""
        handler = AudioEventHandler(
            audio_extractor=mock_audio_extractor,
            audio_detector=mock_audio_detector,
        )

        # Mock camera with audio_enabled=True
        mock_camera = MagicMock()
        mock_camera.audio_enabled = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_camera

        # Mock no audio buffer
        mock_audio_extractor.get_latest_audio.return_value = None

        result = await handler.process_camera_audio(mock_db, "camera-123")

        assert result.created is False
        assert result.reason == "no_audio_buffer"

    @pytest.mark.asyncio
    async def test_process_camera_audio_no_detection(self, mock_audio_extractor, mock_audio_detector, mock_db, audio_chunk):
        """Test processing when no audio event detected"""
        handler = AudioEventHandler(
            audio_extractor=mock_audio_extractor,
            audio_detector=mock_audio_detector,
        )

        # Mock camera with audio_enabled=True
        mock_camera = MagicMock()
        mock_camera.audio_enabled = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_camera

        # Mock audio buffer available
        mock_audio_extractor.get_latest_audio.return_value = audio_chunk

        # Mock no detection
        mock_audio_detector.detect_audio_events.return_value = []

        result = await handler.process_camera_audio(mock_db, "camera-123")

        assert result.created is False
        assert result.reason == "no_detection"

    @pytest.mark.asyncio
    async def test_process_camera_audio_below_threshold(self, mock_audio_extractor, mock_audio_detector, mock_db, audio_chunk):
        """AC#3: Test processing when detection below threshold"""
        handler = AudioEventHandler(
            audio_extractor=mock_audio_extractor,
            audio_detector=mock_audio_detector,
        )

        # Mock camera with audio_enabled=True
        mock_camera = MagicMock()
        mock_camera.audio_enabled = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_camera

        # Mock audio buffer available
        mock_audio_extractor.get_latest_audio.return_value = audio_chunk

        # Mock detection below threshold
        detection = AudioDetectionResult(
            event_type=AudioEventType.GLASS_BREAK,
            confidence=0.60,  # Below 0.70 threshold
            duration_ms=1000,
            classifier_name="mock_v1",
            passed_threshold=False,
            threshold_used=0.70,
        )
        mock_audio_detector.detect_audio_events.return_value = [detection]

        result = await handler.process_camera_audio(mock_db, "camera-123")

        assert result.created is False
        assert result.audio_event_type == AudioEventType.GLASS_BREAK
        assert result.confidence == 0.60
        assert "below_threshold" in result.reason

    @pytest.mark.asyncio
    async def test_process_camera_audio_success(self, mock_audio_extractor, mock_audio_detector, mock_db, audio_chunk, detection_result):
        """AC#4: Test successful audio event creation"""
        handler = AudioEventHandler(
            audio_extractor=mock_audio_extractor,
            audio_detector=mock_audio_detector,
        )

        # Mock camera with audio_enabled=True
        mock_camera = MagicMock()
        mock_camera.audio_enabled = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_camera

        # Mock audio buffer available
        mock_audio_extractor.get_latest_audio.return_value = audio_chunk

        # Mock successful detection
        mock_audio_detector.detect_audio_events.return_value = [detection_result]

        result = await handler.process_camera_audio(mock_db, "camera-123", create_event=True)

        assert result.created is True
        assert result.audio_event_type == AudioEventType.GLASS_BREAK
        assert result.confidence == 0.85
        assert result.reason == "created"
        # Event should be added to DB
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_process_camera_audio_no_event_creation(self, mock_audio_extractor, mock_audio_detector, mock_db, audio_chunk, detection_result):
        """Test processing with create_event=False"""
        handler = AudioEventHandler(
            audio_extractor=mock_audio_extractor,
            audio_detector=mock_audio_detector,
        )

        # Mock camera with audio_enabled=True
        mock_camera = MagicMock()
        mock_camera.audio_enabled = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_camera

        # Mock audio buffer available
        mock_audio_extractor.get_latest_audio.return_value = audio_chunk

        # Mock successful detection
        mock_audio_detector.detect_audio_events.return_value = [detection_result]

        result = await handler.process_camera_audio(mock_db, "camera-123", create_event=False)

        assert result.created is False
        assert result.audio_event_type == AudioEventType.GLASS_BREAK
        assert result.confidence == 0.85
        assert result.reason == "create_event_disabled"
        # Event should NOT be added to DB
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_enrich_event_with_audio_disabled(self, mock_audio_extractor, mock_audio_detector, mock_db):
        """Test enrichment when audio disabled for camera"""
        handler = AudioEventHandler(
            audio_extractor=mock_audio_extractor,
            audio_detector=mock_audio_detector,
        )

        # Mock camera with audio_enabled=False
        mock_camera = MagicMock()
        mock_camera.audio_enabled = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_camera

        mock_event = MagicMock()

        enriched = await handler.enrich_event_with_audio(mock_db, mock_event, "camera-123")

        assert enriched is False

    @pytest.mark.asyncio
    async def test_enrich_event_with_audio_success(self, mock_audio_extractor, mock_audio_detector, mock_db, audio_chunk, detection_result):
        """AC#4: Test successful event enrichment"""
        handler = AudioEventHandler(
            audio_extractor=mock_audio_extractor,
            audio_detector=mock_audio_detector,
        )

        # Mock camera with audio_enabled=True
        mock_camera = MagicMock()
        mock_camera.audio_enabled = True

        # For _is_audio_enabled check
        mock_db.query.return_value.filter.return_value.first.return_value = mock_camera

        # Mock audio buffer available
        mock_audio_extractor.get_latest_audio.return_value = audio_chunk

        # Mock successful detection
        mock_audio_detector.detect_audio_events.return_value = [detection_result]

        # Mock event
        mock_event = MagicMock()
        mock_event.description = "Person walking"
        mock_event.audio_event_type = None

        enriched = await handler.enrich_event_with_audio(mock_db, mock_event, "camera-123")

        assert enriched is True
        assert mock_event.audio_event_type == "glass_break"
        assert mock_event.audio_confidence == 0.85
        assert mock_event.audio_duration_ms == 1000
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_enrich_event_enhances_description(self, mock_audio_extractor, mock_audio_detector, mock_db, audio_chunk, detection_result):
        """Test enrichment adds audio info to description"""
        handler = AudioEventHandler(
            audio_extractor=mock_audio_extractor,
            audio_detector=mock_audio_detector,
        )

        # Mock camera with audio_enabled=True
        mock_camera = MagicMock()
        mock_camera.audio_enabled = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_camera

        # Mock audio buffer available
        mock_audio_extractor.get_latest_audio.return_value = audio_chunk

        # Mock successful detection
        mock_audio_detector.detect_audio_events.return_value = [detection_result]

        # Mock event
        mock_event = MagicMock()
        mock_event.description = "Person at door"
        mock_event.audio_event_type = None

        await handler.enrich_event_with_audio(mock_db, mock_event, "camera-123")

        # Description should include audio info
        assert "[Audio:" in mock_event.description


class TestAudioEventHandlerSingleton:
    """Tests for singleton pattern"""

    def test_get_handler_returns_instance(self):
        """Test singleton getter returns instance"""
        handler = get_audio_event_handler()

        assert handler is not None
        assert isinstance(handler, AudioEventHandler)

    def test_get_returns_same_instance(self):
        """Test singleton returns same instance"""
        handler1 = get_audio_event_handler()
        handler2 = get_audio_event_handler()

        assert handler1 is handler2

    def test_initialize_replaces_singleton(self):
        """Test initialize creates new instance"""
        original = get_audio_event_handler()

        new_handler = initialize_audio_event_handler()

        assert new_handler is not original
