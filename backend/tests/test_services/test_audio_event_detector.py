"""Tests for AudioEventDetector Service (Story P6-3.2)

Tests the audio event detection service including:
- Audio classification with mock classifier (AC#1)
- Confidence threshold filtering (AC#3)
- All supported event types (AC#2)
- Threshold configuration and persistence
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm import Session

from app.services.audio_event_detector import (
    AudioEventDetector,
    AudioDetectionResult,
    get_audio_event_detector,
    initialize_audio_event_detector,
    DEFAULT_THRESHOLDS,
)
from app.services.audio_classifiers import (
    AudioEventType,
    AudioClassificationResult,
    BaseAudioClassifier,
    MockAudioClassifier,
)
from app.services.audio_classifiers.mock import DeterministicMockClassifier


class TestAudioEventType:
    """Tests for AudioEventType enum"""

    def test_all_supported_types_exist(self):
        """AC#2: Verify all required event types are supported"""
        assert hasattr(AudioEventType, 'GLASS_BREAK')
        assert hasattr(AudioEventType, 'GUNSHOT')
        assert hasattr(AudioEventType, 'SCREAM')
        assert hasattr(AudioEventType, 'DOORBELL')
        assert hasattr(AudioEventType, 'OTHER')

    def test_event_type_values(self):
        """Verify string values match expected format"""
        assert AudioEventType.GLASS_BREAK.value == "glass_break"
        assert AudioEventType.GUNSHOT.value == "gunshot"
        assert AudioEventType.SCREAM.value == "scream"
        assert AudioEventType.DOORBELL.value == "doorbell"
        assert AudioEventType.OTHER.value == "other"

    def test_from_string_valid(self):
        """Test conversion from string to enum"""
        assert AudioEventType.from_string("glass_break") == AudioEventType.GLASS_BREAK
        assert AudioEventType.from_string("GUNSHOT") == AudioEventType.GUNSHOT
        assert AudioEventType.from_string("Scream") == AudioEventType.SCREAM

    def test_from_string_invalid(self):
        """Test invalid string returns None"""
        assert AudioEventType.from_string("invalid_type") is None
        assert AudioEventType.from_string("") is None


class TestAudioClassificationResult:
    """Tests for AudioClassificationResult dataclass"""

    def test_valid_result_creation(self):
        """Test creating valid classification result"""
        result = AudioClassificationResult(
            event_type=AudioEventType.GLASS_BREAK,
            confidence=0.85,
            duration_ms=1000,
            start_offset_ms=500,
        )

        assert result.event_type == AudioEventType.GLASS_BREAK
        assert result.confidence == 0.85
        assert result.duration_ms == 1000
        assert result.start_offset_ms == 500

    def test_invalid_confidence_raises(self):
        """Test that invalid confidence raises ValueError"""
        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            AudioClassificationResult(
                event_type=AudioEventType.GLASS_BREAK,
                confidence=1.5,  # Invalid: > 1.0
                duration_ms=1000,
            )

        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            AudioClassificationResult(
                event_type=AudioEventType.GLASS_BREAK,
                confidence=-0.1,  # Invalid: < 0.0
                duration_ms=1000,
            )

    def test_invalid_duration_raises(self):
        """Test that negative duration raises ValueError"""
        with pytest.raises(ValueError, match="Duration must be non-negative"):
            AudioClassificationResult(
                event_type=AudioEventType.GLASS_BREAK,
                confidence=0.5,
                duration_ms=-100,
            )

    def test_passes_threshold(self):
        """AC#3: Test threshold comparison"""
        result = AudioClassificationResult(
            event_type=AudioEventType.GLASS_BREAK,
            confidence=0.75,
            duration_ms=1000,
        )

        assert result.passes_threshold(0.70) is True
        assert result.passes_threshold(0.75) is True
        assert result.passes_threshold(0.80) is False


class TestMockAudioClassifier:
    """Tests for MockAudioClassifier"""

    def test_classifier_with_fixed_result(self):
        """Test classifier returns fixed result when configured"""
        fixed_result = AudioClassificationResult(
            event_type=AudioEventType.GUNSHOT,
            confidence=0.95,
            duration_ms=500,
        )

        classifier = MockAudioClassifier(fixed_result=fixed_result)

        # Generate test audio
        audio_samples = np.zeros(16000, dtype=np.int16)  # 1 second

        results = classifier.classify(audio_samples, sample_rate=16000)

        assert len(results) == 1
        assert results[0].event_type == AudioEventType.GUNSHOT
        assert results[0].confidence == 0.95
        assert results[0].duration_ms == 500

    def test_classifier_with_zero_probability(self):
        """Test classifier returns no results with zero probability"""
        classifier = MockAudioClassifier(detection_probability=0.0)

        audio_samples = np.zeros(16000, dtype=np.int16)

        results = classifier.classify(audio_samples, sample_rate=16000)

        assert len(results) == 0

    def test_classifier_invalid_probability_raises(self):
        """Test invalid probability raises ValueError"""
        with pytest.raises(ValueError):
            MockAudioClassifier(detection_probability=1.5)

        with pytest.raises(ValueError):
            MockAudioClassifier(detection_probability=-0.1)

    def test_classifier_supports_all_event_types(self):
        """AC#2: Test mock classifier supports all event types"""
        classifier = MockAudioClassifier()

        supported = classifier.get_supported_event_types()

        # Use exhaustive check for all event types
        assert len(supported) >= len(AudioEventType)
        assert AudioEventType.GLASS_BREAK in supported
        assert AudioEventType.GUNSHOT in supported
        assert AudioEventType.SCREAM in supported
        assert AudioEventType.DOG_BARK in supported
        assert AudioEventType.SMOKE_ALARM in supported
        assert AudioEventType.SIREN in supported
        assert AudioEventType.BABY_CRY in supported

    def test_classifier_model_name(self):
        """Test classifier returns model name"""
        classifier = MockAudioClassifier()
        assert classifier.get_model_name() == "mock_v1"

    def test_classifier_stats_tracking(self):
        """Test classifier tracks statistics"""
        classifier = MockAudioClassifier(detection_probability=1.0)
        classifier.reset_stats()

        audio_samples = np.zeros(16000, dtype=np.int16)

        classifier.classify(audio_samples, sample_rate=16000)
        classifier.classify(audio_samples, sample_rate=16000)

        stats = classifier.get_stats()

        assert stats["classify_calls"] == 2
        assert stats["total_detections"] == 2
        assert stats["detection_rate"] == 1.0


class TestDeterministicMockClassifier:
    """Tests for DeterministicMockClassifier"""

    def test_high_rms_triggers_gunshot(self):
        """Test high RMS triggers most severe event type"""
        classifier = DeterministicMockClassifier()

        # Create very loud audio (high RMS)
        audio_samples = np.full(16000, 30000, dtype=np.int16)  # Near max amplitude

        results = classifier.classify(audio_samples, sample_rate=16000)

        assert len(results) == 1
        # Should be gunshot (highest threshold)
        assert results[0].event_type == AudioEventType.GUNSHOT

    def test_low_rms_no_detection(self):
        """Test low RMS triggers no detection"""
        classifier = DeterministicMockClassifier()

        # Create very quiet audio
        audio_samples = np.full(16000, 100, dtype=np.int16)

        results = classifier.classify(audio_samples, sample_rate=16000)

        assert len(results) == 0

    def test_model_name(self):
        """Test deterministic mock returns correct model name"""
        classifier = DeterministicMockClassifier()
        assert classifier.get_model_name() == "deterministic_mock_v1"


class TestAudioEventDetector:
    """Tests for AudioEventDetector service"""

    def test_default_initialization(self):
        """Test detector initializes with default mock classifier"""
        detector = AudioEventDetector()

        assert detector.classifier is not None
        assert isinstance(detector.classifier, MockAudioClassifier)

    def test_custom_classifier(self):
        """AC#1: Test detector accepts custom classifier"""
        custom_classifier = MockAudioClassifier(detection_probability=0.5)
        detector = AudioEventDetector(classifier=custom_classifier)

        assert detector.classifier is custom_classifier

    def test_set_classifier(self):
        """Test classifier can be replaced"""
        detector = AudioEventDetector()
        new_classifier = DeterministicMockClassifier()

        detector.set_classifier(new_classifier)

        assert detector.classifier is new_classifier

    def test_default_thresholds(self):
        """AC#3: Test default thresholds are 70%"""
        detector = AudioEventDetector()
        thresholds = detector.get_thresholds()
        # Check that all event types have default threshold
        assert len(thresholds) >= 7  # 7 event types

    @pytest.mark.parametrize("event_type", [
        AudioEventType.GLASS_BREAK,
        AudioEventType.GUNSHOT,
        AudioEventType.SCREAM,
        AudioEventType.DOG_BARK,
        AudioEventType.SMOKE_ALARM,
        AudioEventType.SIREN,
        AudioEventType.BABY_CRY,
    ])
    def test_default_threshold_per_type(self, event_type):
        """AC#3: Test each event type has 70% default threshold"""
        detector = AudioEventDetector()
        assert detector.get_threshold(event_type) == 0.70

    def test_get_threshold_per_type(self):
        """Test getting threshold for specific event type"""
        detector = AudioEventDetector()

        threshold = detector.get_threshold(AudioEventType.GLASS_BREAK)

        assert threshold == 0.70

    def test_set_threshold(self):
        """AC#3: Test threshold can be set per event type"""
        detector = AudioEventDetector()

        detector.set_threshold(AudioEventType.GUNSHOT, 0.90)

        assert detector.get_threshold(AudioEventType.GUNSHOT) == 0.90
        # Other thresholds unchanged
        assert detector.get_threshold(AudioEventType.GLASS_BREAK) == 0.70

    def test_set_threshold_invalid_range_raises(self):
        """Test invalid threshold value raises ValueError"""
        detector = AudioEventDetector()

        with pytest.raises(ValueError):
            detector.set_threshold(AudioEventType.GUNSHOT, 1.5)

        with pytest.raises(ValueError):
            detector.set_threshold(AudioEventType.GUNSHOT, -0.1)

    def test_detect_audio_events_returns_results(self):
        """Test detection returns results with threshold info"""
        fixed_result = AudioClassificationResult(
            event_type=AudioEventType.GLASS_BREAK,
            confidence=0.85,
            duration_ms=1000,
        )
        classifier = MockAudioClassifier(fixed_result=fixed_result)
        detector = AudioEventDetector(classifier=classifier)

        audio_samples = np.zeros(16000, dtype=np.int16)
        results = detector.detect_audio_events(audio_samples, sample_rate=16000)

        assert len(results) == 1
        assert isinstance(results[0], AudioDetectionResult)
        assert results[0].event_type == AudioEventType.GLASS_BREAK
        assert results[0].confidence == 0.85
        assert results[0].passed_threshold is True
        assert results[0].threshold_used == 0.70

    def test_detect_events_below_threshold(self):
        """AC#3: Test events below threshold are marked as not passing"""
        fixed_result = AudioClassificationResult(
            event_type=AudioEventType.GLASS_BREAK,
            confidence=0.60,  # Below 0.70 threshold
            duration_ms=1000,
        )
        classifier = MockAudioClassifier(fixed_result=fixed_result)
        detector = AudioEventDetector(classifier=classifier)

        audio_samples = np.zeros(16000, dtype=np.int16)
        results = detector.detect_audio_events(audio_samples, sample_rate=16000)

        assert len(results) == 1
        assert results[0].confidence == 0.60
        assert results[0].passed_threshold is False
        assert results[0].threshold_used == 0.70

    def test_detect_events_above_custom_threshold(self):
        """AC#3: Test custom threshold is used"""
        fixed_result = AudioClassificationResult(
            event_type=AudioEventType.GUNSHOT,
            confidence=0.85,
            duration_ms=500,
        )
        classifier = MockAudioClassifier(fixed_result=fixed_result)
        detector = AudioEventDetector(classifier=classifier)

        # Set high threshold
        detector.set_threshold(AudioEventType.GUNSHOT, 0.90)

        audio_samples = np.zeros(16000, dtype=np.int16)
        results = detector.detect_audio_events(audio_samples, sample_rate=16000)

        assert len(results) == 1
        assert results[0].confidence == 0.85
        assert results[0].passed_threshold is False  # 0.85 < 0.90
        assert results[0].threshold_used == 0.90

    def test_detect_events_handles_classifier_error(self):
        """Test graceful handling of classifier errors"""
        # Create a classifier that raises an exception
        class FailingClassifier(BaseAudioClassifier):
            def classify(self, audio_samples, sample_rate, channels=1):
                raise RuntimeError("Classification failed")

            def get_supported_event_types(self):
                return []

            def get_model_name(self):
                return "failing"

        detector = AudioEventDetector(classifier=FailingClassifier())

        audio_samples = np.zeros(16000, dtype=np.int16)
        results = detector.detect_audio_events(audio_samples, sample_rate=16000)

        # Should return empty list, not raise
        assert results == []

    def test_classifier_name_in_result(self):
        """Test classifier name is included in result"""
        fixed_result = AudioClassificationResult(
            event_type=AudioEventType.DOORBELL,
            confidence=0.80,
            duration_ms=200,
        )
        classifier = MockAudioClassifier(fixed_result=fixed_result)
        detector = AudioEventDetector(classifier=classifier)

        audio_samples = np.zeros(16000, dtype=np.int16)
        results = detector.detect_audio_events(audio_samples, sample_rate=16000)

        assert results[0].classifier_name == "mock_v1"


class TestAudioEventDetectorSingleton:
    """Tests for singleton pattern"""

    def test_get_audio_event_detector_returns_instance(self):
        """Test singleton getter returns instance"""
        detector = get_audio_event_detector()

        assert detector is not None
        assert isinstance(detector, AudioEventDetector)

    def test_get_returns_same_instance(self):
        """Test singleton returns same instance"""
        detector1 = get_audio_event_detector()
        detector2 = get_audio_event_detector()

        assert detector1 is detector2

    def test_initialize_replaces_singleton(self):
        """Test initialize creates new instance"""
        original = get_audio_event_detector()

        new_classifier = DeterministicMockClassifier()
        new_detector = initialize_audio_event_detector(classifier=new_classifier)

        assert new_detector is not original
        assert new_detector.classifier is new_classifier

        # Subsequent get returns new instance
        current = get_audio_event_detector()
        assert current is new_detector


class TestAudioEventDetectorDatabaseIntegration:
    """Tests for database threshold persistence"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session"""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    def test_load_thresholds_from_empty_db(self, mock_db):
        """Test loading thresholds from empty database uses defaults"""
        detector = AudioEventDetector()

        detector.load_thresholds_from_db(mock_db)

        # Should still have default thresholds
        assert detector.get_threshold(AudioEventType.GLASS_BREAK) == 0.70

    def test_save_threshold_to_db(self, mock_db):
        """Test saving threshold to database"""
        detector = AudioEventDetector()

        # Mock no existing setting
        mock_db.query.return_value.filter.return_value.first.return_value = None

        detector.save_threshold_to_db(mock_db, AudioEventType.GLASS_BREAK, 0.85)

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify in-memory update
        assert detector.get_threshold(AudioEventType.GLASS_BREAK) == 0.85

    def test_save_threshold_validates_range(self, mock_db):
        """Test save validates threshold range"""
        detector = AudioEventDetector()

        with pytest.raises(ValueError):
            detector.save_threshold_to_db(mock_db, AudioEventType.GLASS_BREAK, 1.5)
