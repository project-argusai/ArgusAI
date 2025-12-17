"""Audio Classifiers Package (Story P6-3.2)

This package provides pluggable audio classification implementations
for detecting audio events like glass breaking, gunshots, screams, etc.

Available classifiers:
- BaseAudioClassifier: Abstract base class for all classifiers
- MockAudioClassifier: Testing/demo classifier with random results
"""

from app.services.audio_classifiers.base import (
    AudioEventType,
    AudioClassificationResult,
    BaseAudioClassifier,
)
from app.services.audio_classifiers.mock import MockAudioClassifier

__all__ = [
    "AudioEventType",
    "AudioClassificationResult",
    "BaseAudioClassifier",
    "MockAudioClassifier",
]
