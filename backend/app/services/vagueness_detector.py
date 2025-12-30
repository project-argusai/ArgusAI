"""
Vagueness Detector Service (Story P4-6)

Wrapper class for vagueness detection to provide a structured result.
This wraps the underlying detect_vague_description function to provide
a consistent object-based interface.

Usage:
    from app.services.vagueness_detector import VaguenessDetector

    detector = VaguenessDetector()
    result = detector.is_vague("It appears to be something moving.")
    if result.is_vague:
        print(f"Vague: {result.reason}")

Migrated to @singleton: Story P14-5.3
"""
from dataclasses import dataclass
from typing import Optional

from app.core.decorators import singleton
from app.services.description_quality import detect_vague_description


@dataclass
class VaguenessResult:
    """Result of vagueness detection."""
    is_vague: bool
    reason: Optional[str]


@singleton
class VaguenessDetector:
    """
    Vagueness detector wrapper class.

    Provides an object-oriented interface to the vagueness detection
    functionality for use in API endpoints.
    """

    def is_vague(self, description: str) -> VaguenessResult:
        """
        Check if a description is vague.

        Args:
            description: AI-generated event description text

        Returns:
            VaguenessResult with is_vague flag and optional reason
        """
        is_vague, reason = detect_vague_description(description)
        return VaguenessResult(is_vague=is_vague, reason=reason)


# Backward compatible getter (delegates to @singleton decorator)
def get_vagueness_detector() -> VaguenessDetector:
    """
    Get or create the vagueness detector singleton.

    Note: This is a backward-compatible wrapper. New code should use
          VaguenessDetector() directly, which returns the singleton instance.
    """
    return VaguenessDetector()
