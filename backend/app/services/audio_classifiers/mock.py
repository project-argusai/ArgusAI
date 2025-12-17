"""Mock Audio Classifier for Testing (Story P6-3.2)

Provides a mock implementation of BaseAudioClassifier for testing
and demonstration purposes. Returns configurable or random results.

This classifier is useful for:
- Unit testing the audio event detection pipeline
- Demo/development without ML model dependencies
- Testing alert rule integration with audio events
"""

import random
from typing import List, Optional
import numpy as np

from app.services.audio_classifiers.base import (
    AudioEventType,
    AudioClassificationResult,
    BaseAudioClassifier,
)


class MockAudioClassifier(BaseAudioClassifier):
    """
    Mock audio classifier for testing and development (Story P6-3.2)

    Can be configured to:
    - Return random detections with configurable probability
    - Return specific detection results for deterministic testing
    - Simulate detection latency
    """

    def __init__(
        self,
        detection_probability: float = 0.1,
        fixed_result: Optional[AudioClassificationResult] = None,
        simulate_latency_ms: int = 0,
    ):
        """
        Initialize MockAudioClassifier.

        Args:
            detection_probability: Probability (0.0-1.0) of detecting an event
                when classifying audio. Default 0.1 (10%).
            fixed_result: If provided, always return this result instead of random.
                Useful for deterministic testing.
            simulate_latency_ms: Artificial delay in milliseconds to simulate
                processing time. Default 0.
        """
        if not 0.0 <= detection_probability <= 1.0:
            raise ValueError(f"detection_probability must be 0.0-1.0, got {detection_probability}")

        self.detection_probability = detection_probability
        self.fixed_result = fixed_result
        self.simulate_latency_ms = simulate_latency_ms

        # Statistics tracking
        self.classify_call_count = 0
        self.total_detections = 0

    def classify(
        self,
        audio_samples: np.ndarray,
        sample_rate: int,
        channels: int = 1,
    ) -> List[AudioClassificationResult]:
        """
        Mock classification - returns random or fixed detection results.

        Args:
            audio_samples: Audio samples (ignored in mock, but validates shape)
            sample_rate: Sample rate (used to calculate duration)
            channels: Number of channels

        Returns:
            List containing 0 or 1 AudioClassificationResult based on
            detection_probability or fixed_result configuration.
        """
        import time

        self.classify_call_count += 1

        # Simulate processing latency if configured
        if self.simulate_latency_ms > 0:
            time.sleep(self.simulate_latency_ms / 1000.0)

        # Return fixed result if configured
        if self.fixed_result is not None:
            self.total_detections += 1
            return [self.fixed_result]

        # Random detection based on probability
        if random.random() > self.detection_probability:
            return []  # No detection

        # Generate random detection
        self.total_detections += 1

        # Pick random event type
        event_type = random.choice(list(AudioEventType))

        # Generate realistic confidence (biased toward higher values for "detections")
        confidence = random.uniform(0.6, 0.95)

        # Calculate duration from audio samples
        num_samples = len(audio_samples) if audio_samples.ndim == 1 else audio_samples.shape[0]
        total_duration_ms = int((num_samples / sample_rate) * 1000)

        # Event duration is a portion of total audio
        duration_ms = random.randint(
            min(100, total_duration_ms),
            min(2000, total_duration_ms)
        )

        # Random start offset
        max_offset = max(0, total_duration_ms - duration_ms)
        start_offset_ms = random.randint(0, max_offset) if max_offset > 0 else 0

        return [AudioClassificationResult(
            event_type=event_type,
            confidence=confidence,
            duration_ms=duration_ms,
            start_offset_ms=start_offset_ms,
            metadata={"classifier": "mock", "mock_version": "1.0"}
        )]

    def get_supported_event_types(self) -> List[AudioEventType]:
        """Mock supports all event types."""
        return list(AudioEventType)

    def get_model_name(self) -> str:
        """Return mock classifier identifier."""
        return "mock_v1"

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self.classify_call_count = 0
        self.total_detections = 0

    def get_stats(self) -> dict:
        """Get classification statistics."""
        return {
            "classify_calls": self.classify_call_count,
            "total_detections": self.total_detections,
            "detection_rate": (
                self.total_detections / self.classify_call_count
                if self.classify_call_count > 0 else 0.0
            ),
        }


class DeterministicMockClassifier(MockAudioClassifier):
    """
    Deterministic mock classifier for testing specific scenarios.

    Unlike the random MockAudioClassifier, this returns predictable
    results based on audio content patterns for testing purposes.
    """

    def __init__(self):
        """Initialize with deterministic settings."""
        super().__init__(detection_probability=0.0, fixed_result=None)

        # Detection patterns: RMS thresholds that trigger specific events
        self.rms_thresholds = {
            AudioEventType.GLASS_BREAK: 0.8,  # Very loud
            AudioEventType.GUNSHOT: 0.9,      # Extremely loud
            AudioEventType.SCREAM: 0.6,       # Moderately loud
            AudioEventType.DOORBELL: 0.3,     # Medium volume
        }

    def classify(
        self,
        audio_samples: np.ndarray,
        sample_rate: int,
        channels: int = 1,
    ) -> List[AudioClassificationResult]:
        """
        Deterministic classification based on audio RMS level.

        Higher RMS values trigger more severe event types.
        This allows predictable testing by providing audio
        with specific amplitude levels.
        """
        self.classify_call_count += 1

        # Preprocess to float32
        processed = self.preprocess_audio(audio_samples, sample_rate)

        # Calculate RMS (root mean square) amplitude
        rms = np.sqrt(np.mean(processed ** 2))

        # Find matching event type based on RMS threshold
        detected_type = None
        for event_type, threshold in sorted(
            self.rms_thresholds.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            if rms >= threshold:
                detected_type = event_type
                break

        if detected_type is None:
            return []

        self.total_detections += 1

        # Calculate duration from samples
        num_samples = len(processed) if processed.ndim == 1 else processed.shape[0]
        duration_ms = int((num_samples / sample_rate) * 1000)

        # Confidence scales with how much RMS exceeds threshold
        threshold = self.rms_thresholds[detected_type]
        confidence = min(1.0, 0.5 + (rms - threshold) / 0.5)

        return [AudioClassificationResult(
            event_type=detected_type,
            confidence=confidence,
            duration_ms=duration_ms,
            start_offset_ms=0,
            metadata={
                "classifier": "deterministic_mock",
                "rms": float(rms),
                "threshold": threshold,
            }
        )]

    def get_model_name(self) -> str:
        """Return deterministic mock identifier."""
        return "deterministic_mock_v1"
