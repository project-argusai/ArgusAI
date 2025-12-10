"""
Description Quality Service (Story P3-6.2)

Detects vague AI descriptions using pattern matching and heuristics.
Pure function design with no external dependencies - easy to test in isolation.

Usage:
    from app.services.description_quality import detect_vague_description

    is_vague, reason = detect_vague_description("It appears to be something moving.")
    # is_vague = True
    # reason = "Contains vague phrase: 'appears to be'"
"""
import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Story P3-6.2 AC1: Vague phrase patterns (case-insensitive)
# These indicate uncertain or ambiguous descriptions
VAGUE_PHRASES = [
    (r"\bappears\s+to\s+be\b", "appears to be"),
    (r"\bpossibly\b", "possibly"),
    (r"\bunclear\b", "unclear"),
    (r"\bcannot\s+determine\b", "cannot determine"),
    (r"\bsomething\b", "something"),
    # "motion detected" only vague if not followed by specific subject
    (r"\bmotion\s+detected\b(?!.*\b(person|vehicle|animal|package|delivery|visitor|car|truck|dog|cat)\b)", "motion detected"),
    (r"\bmight\s+be\b", "might be"),
    (r"\bcould\s+be\b", "could be"),
    (r"\bseems\s+like\b", "seems like"),
    (r"\bhard\s+to\s+tell\b", "hard to tell"),
    (r"\bdifficult\s+to\s+identify\b", "difficult to identify"),
    (r"\bnot\s+sure\b", "not sure"),
    (r"\buncertain\b", "uncertain"),
]

# Story P3-6.2 AC2: Generic phrases that indicate no useful information
# These match the entire description (anchored)
GENERIC_PHRASES = [
    (r"^activity\s+detected\.?$", "activity detected"),
    (r"^movement\s+observed\.?$", "movement observed"),
    (r"^something\s+moved\.?$", "something moved"),
    (r"^motion\s+detected\.?$", "motion detected"),
    (r"^object\s+detected\.?$", "object detected"),
    (r"^movement\s+detected\.?$", "movement detected"),
]

# Story P3-6.2 AC2: Minimum word count for meaningful descriptions
MIN_WORD_COUNT = 10


def detect_vague_description(description: str) -> Tuple[bool, Optional[str]]:
    """
    Detect if an AI description is vague or lacks specificity.

    Story P3-6.2: Implements detection for:
    - AC1: Vague phrase patterns (case-insensitive)
    - AC2: Short descriptions (<10 words) and generic phrases
    - AC5: Allows specific descriptions through

    Args:
        description: AI-generated event description text

    Returns:
        Tuple of (is_vague: bool, reason: Optional[str])
        - is_vague: True if description is considered vague
        - reason: Human-readable explanation if vague, None otherwise

    Examples:
        >>> detect_vague_description("Person in blue jacket at front door")
        (False, None)

        >>> detect_vague_description("Something appears to be moving")
        (True, "Contains vague phrase: 'appears to be'")

        >>> detect_vague_description("Motion detected")
        (True, "Description too short (2 words, minimum 10)")
    """
    if not description:
        return True, "Description is empty"

    # Normalize whitespace for consistent word counting
    normalized = " ".join(description.split())

    # AC2: Check for generic phrases first (exact match after normalization)
    for pattern, phrase_name in GENERIC_PHRASES:
        if re.match(pattern, normalized, re.IGNORECASE):
            logger.debug(
                f"Vague description detected: generic phrase '{phrase_name}'",
                extra={
                    "event_type": "vague_description_detected",
                    "detection_type": "generic_phrase",
                    "phrase": phrase_name,
                    "description_preview": normalized[:50]
                }
            )
            return True, f"Generic phrase with no specifics: '{phrase_name}'"

    # AC2: Check word count (must have at least MIN_WORD_COUNT words)
    word_count = len(normalized.split())
    if word_count < MIN_WORD_COUNT:
        logger.debug(
            f"Vague description detected: too short ({word_count} words)",
            extra={
                "event_type": "vague_description_detected",
                "detection_type": "short_description",
                "word_count": word_count,
                "min_required": MIN_WORD_COUNT,
                "description_preview": normalized[:50]
            }
        )
        return True, f"Description too short ({word_count} words, minimum {MIN_WORD_COUNT})"

    # AC1: Check for vague phrases (case-insensitive)
    for pattern, phrase_name in VAGUE_PHRASES:
        if re.search(pattern, normalized, re.IGNORECASE):
            logger.debug(
                f"Vague description detected: contains '{phrase_name}'",
                extra={
                    "event_type": "vague_description_detected",
                    "detection_type": "vague_phrase",
                    "phrase": phrase_name,
                    "description_preview": normalized[:50]
                }
            )
            return True, f"Contains vague phrase: '{phrase_name}'"

    # AC5: Description passes all checks - not vague
    return False, None


def get_vague_phrases() -> list[str]:
    """Return list of vague phrase names for documentation/UI purposes."""
    return [phrase_name for _, phrase_name in VAGUE_PHRASES]


def get_generic_phrases() -> list[str]:
    """Return list of generic phrase names for documentation/UI purposes."""
    return [phrase_name for _, phrase_name in GENERIC_PHRASES]


def get_min_word_count() -> int:
    """Return minimum word count threshold."""
    return MIN_WORD_COUNT
