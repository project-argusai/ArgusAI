"""Audio Event Detection Service (Story P6-3.2)

This service orchestrates audio event detection by:
1. Receiving audio buffers from AudioStreamService
2. Running classification through pluggable audio classifiers
3. Filtering results by configurable confidence thresholds
4. Returning detection results for event creation

Architecture:
- Pluggable classifier interface (BaseAudioClassifier)
- Per-event-type confidence thresholds (AC#3)
- Singleton pattern with get_audio_event_detector()
- Thread-safe for concurrent camera processing
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from threading import Lock

import numpy as np
from sqlalchemy.orm import Session

from app.services.audio_classifiers import (
    AudioEventType,
    AudioClassificationResult,
    BaseAudioClassifier,
    MockAudioClassifier,
)
from app.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)


# Default confidence thresholds per event type (Story P6-3.2 AC#3)
DEFAULT_THRESHOLDS: Dict[AudioEventType, float] = {
    AudioEventType.GLASS_BREAK: 0.70,
    AudioEventType.GUNSHOT: 0.70,
    AudioEventType.SCREAM: 0.70,
    AudioEventType.DOORBELL: 0.70,
    AudioEventType.OTHER: 0.70,
}

# System settings keys for thresholds
THRESHOLD_SETTING_PREFIX = "audio_threshold_"


@dataclass
class AudioDetectionResult:
    """
    Result from audio event detection, ready for event creation.

    Attributes:
        event_type: Type of detected audio event
        confidence: Confidence score (0.0-1.0)
        duration_ms: Duration of the audio event in milliseconds
        classifier_name: Name of the classifier that made the detection
        passed_threshold: Whether the detection passed confidence threshold
        threshold_used: The threshold value that was applied
    """
    event_type: AudioEventType
    confidence: float
    duration_ms: int
    classifier_name: str
    passed_threshold: bool
    threshold_used: float
    metadata: Optional[dict] = None


class AudioEventDetector:
    """
    Main audio event detection service (Story P6-3.2)

    Manages audio classification and threshold filtering for
    creating audio-triggered events.

    Thread Safety:
        - Threshold updates are protected by lock
        - Classifier is stateless after initialization
        - Safe for concurrent calls from multiple camera handlers

    Usage:
        detector = get_audio_event_detector()
        results = detector.detect_audio_events(audio_samples, sample_rate, db)
        for result in results:
            if result.passed_threshold:
                # Create event with audio_event_type field
                pass
    """

    def __init__(
        self,
        classifier: Optional[BaseAudioClassifier] = None,
    ):
        """
        Initialize AudioEventDetector.

        Args:
            classifier: Audio classifier implementation. Defaults to MockAudioClassifier.
        """
        self._classifier = classifier or MockAudioClassifier(detection_probability=0.1)
        self._thresholds = DEFAULT_THRESHOLDS.copy()
        self._threshold_lock = Lock()
        self._thresholds_loaded = False

        logger.info(
            f"AudioEventDetector initialized with classifier: {self._classifier.get_model_name()}"
        )

    @property
    def classifier(self) -> BaseAudioClassifier:
        """Get the current classifier instance."""
        return self._classifier

    def set_classifier(self, classifier: BaseAudioClassifier) -> None:
        """
        Replace the audio classifier (for testing or upgrades).

        Args:
            classifier: New classifier implementation
        """
        self._classifier = classifier
        logger.info(f"Classifier changed to: {classifier.get_model_name()}")

    def get_thresholds(self) -> Dict[str, float]:
        """
        Get current confidence thresholds for all event types.

        Returns:
            Dict mapping event type string to threshold float
        """
        with self._threshold_lock:
            return {k.value: v for k, v in self._thresholds.items()}

    def get_threshold(self, event_type: AudioEventType) -> float:
        """
        Get confidence threshold for specific event type.

        Args:
            event_type: The audio event type

        Returns:
            Threshold value (0.0-1.0)
        """
        with self._threshold_lock:
            return self._thresholds.get(event_type, DEFAULT_THRESHOLDS.get(event_type, 0.70))

    def set_threshold(self, event_type: AudioEventType, threshold: float) -> None:
        """
        Set confidence threshold for an event type (in-memory only).

        Args:
            event_type: The audio event type
            threshold: New threshold value (0.0-1.0)

        Raises:
            ValueError: If threshold is out of valid range
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"Threshold must be 0.0-1.0, got {threshold}")

        with self._threshold_lock:
            self._thresholds[event_type] = threshold

        logger.info(f"Threshold for {event_type.value} set to {threshold}")

    def load_thresholds_from_db(self, db: Session) -> None:
        """
        Load confidence thresholds from database settings.

        Args:
            db: SQLAlchemy database session
        """
        with self._threshold_lock:
            for event_type in AudioEventType:
                setting_key = f"{THRESHOLD_SETTING_PREFIX}{event_type.value}"
                setting = db.query(SystemSetting).filter(
                    SystemSetting.key == setting_key
                ).first()

                if setting:
                    try:
                        threshold = float(setting.value)
                        if 0.0 <= threshold <= 1.0:
                            self._thresholds[event_type] = threshold
                            logger.debug(f"Loaded threshold {event_type.value}={threshold}")
                        else:
                            logger.warning(
                                f"Invalid threshold value for {event_type.value}: {threshold}"
                            )
                    except ValueError:
                        logger.warning(
                            f"Failed to parse threshold for {event_type.value}: {setting.value}"
                        )

            self._thresholds_loaded = True
            logger.info(f"Audio thresholds loaded from database")

    def save_threshold_to_db(
        self,
        db: Session,
        event_type: AudioEventType,
        threshold: float,
    ) -> None:
        """
        Save a threshold value to database and update in-memory.

        Args:
            db: SQLAlchemy database session
            event_type: The audio event type
            threshold: New threshold value (0.0-1.0)
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"Threshold must be 0.0-1.0, got {threshold}")

        setting_key = f"{THRESHOLD_SETTING_PREFIX}{event_type.value}"

        setting = db.query(SystemSetting).filter(
            SystemSetting.key == setting_key
        ).first()

        if setting:
            setting.value = str(threshold)
        else:
            setting = SystemSetting(key=setting_key, value=str(threshold))
            db.add(setting)

        db.commit()

        # Update in-memory threshold
        with self._threshold_lock:
            self._thresholds[event_type] = threshold

        logger.info(f"Saved threshold {event_type.value}={threshold} to database")

    def detect_audio_events(
        self,
        audio_samples: np.ndarray,
        sample_rate: int,
        db: Optional[Session] = None,
        channels: int = 1,
    ) -> List[AudioDetectionResult]:
        """
        Detect audio events in audio samples.

        This is the main entry point for audio event detection.
        Runs classification and applies threshold filtering.

        Args:
            audio_samples: Audio samples as numpy array (int16 or float32)
            sample_rate: Sample rate in Hz (e.g., 48000)
            db: Optional database session to load thresholds from
            channels: Number of audio channels (default 1=mono)

        Returns:
            List of AudioDetectionResult with threshold filtering applied.
            Results include passed_threshold flag indicating if detection
            meets the configured confidence threshold.

        Example:
            detector = get_audio_event_detector()
            results = detector.detect_audio_events(
                audio_chunk.samples,
                audio_chunk.sample_rate,
                db_session
            )
            for result in results:
                if result.passed_threshold:
                    print(f"Detected {result.event_type}: {result.confidence:.2%}")
        """
        # Load thresholds from DB if session provided and not yet loaded
        if db is not None and not self._thresholds_loaded:
            self.load_thresholds_from_db(db)

        # Run classification
        try:
            classification_results = self._classifier.classify(
                audio_samples,
                sample_rate,
                channels,
            )
        except Exception as e:
            logger.error(f"Audio classification failed: {e}", exc_info=True)
            return []

        # Process results with threshold filtering
        detection_results: List[AudioDetectionResult] = []

        for result in classification_results:
            threshold = self.get_threshold(result.event_type)
            passed = result.passes_threshold(threshold)

            detection_results.append(AudioDetectionResult(
                event_type=result.event_type,
                confidence=result.confidence,
                duration_ms=result.duration_ms,
                classifier_name=self._classifier.get_model_name(),
                passed_threshold=passed,
                threshold_used=threshold,
                metadata=result.metadata,
            ))

            if passed:
                logger.info(
                    f"Audio event detected: {result.event_type.value} "
                    f"(confidence={result.confidence:.2%}, threshold={threshold:.2%})",
                    extra={
                        "event_type": "audio_event_detected",
                        "audio_event_type": result.event_type.value,
                        "confidence": result.confidence,
                        "threshold": threshold,
                        "duration_ms": result.duration_ms,
                        "classifier": self._classifier.get_model_name(),
                    }
                )
            else:
                logger.debug(
                    f"Audio event below threshold: {result.event_type.value} "
                    f"(confidence={result.confidence:.2%} < threshold={threshold:.2%})"
                )

        return detection_results


# Singleton instance
_audio_event_detector: Optional[AudioEventDetector] = None


def get_audio_event_detector() -> AudioEventDetector:
    """
    Get the global AudioEventDetector singleton.

    Returns:
        AudioEventDetector instance (creates one if not exists)
    """
    global _audio_event_detector

    if _audio_event_detector is None:
        _audio_event_detector = AudioEventDetector()

    return _audio_event_detector


def initialize_audio_event_detector(
    classifier: Optional[BaseAudioClassifier] = None,
) -> AudioEventDetector:
    """
    Initialize (or reinitialize) the global AudioEventDetector.

    Args:
        classifier: Optional custom classifier implementation

    Returns:
        Newly initialized AudioEventDetector instance
    """
    global _audio_event_detector

    _audio_event_detector = AudioEventDetector(classifier=classifier)
    logger.info("Global AudioEventDetector initialized")

    return _audio_event_detector
