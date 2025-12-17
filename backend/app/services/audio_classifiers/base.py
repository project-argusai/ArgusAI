"""Base Audio Classifier Interface (Story P6-3.2)

Defines the abstract interface for audio event classification.
Implementations can use various ML models or rule-based approaches.

Supported event types:
- glass_break: Sound of glass shattering
- gunshot: Sound of gunfire
- scream: Human screaming or distress call
- doorbell: Doorbell ringing sound
- other: Other significant audio event
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import numpy as np


class AudioEventType(str, Enum):
    """Supported audio event types for detection (Story P6-3.2 AC#2)"""
    GLASS_BREAK = "glass_break"
    GUNSHOT = "gunshot"
    SCREAM = "scream"
    DOORBELL = "doorbell"
    OTHER = "other"

    @classmethod
    def from_string(cls, value: str) -> Optional["AudioEventType"]:
        """Convert string to AudioEventType, returns None if invalid"""
        try:
            return cls(value.lower())
        except ValueError:
            return None


@dataclass
class AudioClassificationResult:
    """
    Result from audio classification (Story P6-3.2 AC#1)

    Attributes:
        event_type: Detected audio event type
        confidence: Confidence score (0.0 to 1.0)
        duration_ms: Duration of the detected audio event in milliseconds
        start_offset_ms: Offset from start of audio buffer where event begins
        metadata: Optional additional data from the classifier
    """
    event_type: AudioEventType
    confidence: float
    duration_ms: int
    start_offset_ms: int = 0
    metadata: Optional[dict] = None

    def __post_init__(self):
        """Validate confidence is in valid range"""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        if self.duration_ms < 0:
            raise ValueError(f"Duration must be non-negative, got {self.duration_ms}")

    def passes_threshold(self, threshold: float) -> bool:
        """Check if detection confidence meets the threshold (Story P6-3.2 AC#3)"""
        return self.confidence >= threshold


class BaseAudioClassifier(ABC):
    """
    Abstract base class for audio event classifiers (Story P6-3.2 AC#1)

    Implementations should override the classify() method to provide
    actual audio event detection logic.

    Example usage:
        classifier = MockAudioClassifier()
        results = classifier.classify(audio_samples, sample_rate)
        for result in results:
            if result.passes_threshold(0.7):
                # Handle detected audio event
                pass
    """

    @abstractmethod
    def classify(
        self,
        audio_samples: np.ndarray,
        sample_rate: int,
        channels: int = 1,
    ) -> List[AudioClassificationResult]:
        """
        Classify audio samples and detect audio events.

        Args:
            audio_samples: Audio samples as numpy array (int16 or float32)
            sample_rate: Sample rate of the audio (e.g., 48000 Hz)
            channels: Number of audio channels (1=mono, 2=stereo)

        Returns:
            List of AudioClassificationResult for detected events.
            Returns empty list if no events detected.
        """
        pass

    @abstractmethod
    def get_supported_event_types(self) -> List[AudioEventType]:
        """
        Get list of event types this classifier can detect.

        Returns:
            List of AudioEventType values supported by this classifier.
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get the name/identifier of this classifier model.

        Returns:
            String identifier for the classifier (e.g., "yamnet_v1", "mock_v1")
        """
        pass

    def preprocess_audio(
        self,
        audio_samples: np.ndarray,
        sample_rate: int,
        target_sample_rate: int = 16000,
    ) -> np.ndarray:
        """
        Optional preprocessing helper for audio normalization.

        Subclasses can override or extend this method for custom preprocessing.

        Args:
            audio_samples: Raw audio samples
            sample_rate: Current sample rate
            target_sample_rate: Desired sample rate for model

        Returns:
            Preprocessed audio samples
        """
        # Default implementation: normalize to float32 [-1, 1]
        if audio_samples.dtype == np.int16:
            audio_samples = audio_samples.astype(np.float32) / 32768.0
        elif audio_samples.dtype != np.float32:
            audio_samples = audio_samples.astype(np.float32)

        return audio_samples
