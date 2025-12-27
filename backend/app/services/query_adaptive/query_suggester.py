"""
Query Suggester Service (Story P12-4.4)

Generates contextual query suggestions based on event type and detected objects.

Features:
    - Suggestions based on smart_detection_type (person, vehicle, package, animal)
    - Additional suggestions from detected objects
    - Auto-formatting of single-word queries (AC6)
    - Deduplication while preserving order

Usage:
    suggester = QuerySuggester()
    suggestions = suggester.get_suggestions("person", ["delivery person", "package"])
    formatted = suggester.format_query("dog")  # "a photo of dog"
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class QuerySuggester:
    """
    Generate query suggestions based on event type.

    Provides contextual query suggestions to help users ask focused
    questions about events during re-analysis.

    Attributes:
        SUGGESTIONS: Dict mapping event types to suggested queries
        MAX_SUGGESTIONS: Maximum number of suggestions to return (5)
    """

    MAX_SUGGESTIONS = 5

    # Query suggestions by smart detection type
    SUGGESTIONS = {
        "person": [
            "Is this a delivery person?",
            "What are they carrying?",
            "Are they wearing a uniform?",
            "Is this someone I know?",
            "What direction are they walking?",
        ],
        "vehicle": [
            "What color is the vehicle?",
            "Is it parked or moving?",
            "What type of vehicle is this?",
            "Can you read the license plate?",
            "Is this a delivery vehicle?",
        ],
        "package": [
            "What company is the package from?",
            "How large is the package?",
            "Where was it placed?",
            "Is there a shipping label visible?",
        ],
        "animal": [
            "What type of animal is this?",
            "Is it a pet or wildlife?",
            "What is the animal doing?",
            "Does it look friendly or aggressive?",
        ],
        "ring": [
            "Who is at the door?",
            "Are they holding anything?",
            "Do they look like a delivery person?",
            "Is this someone I know?",
        ],
    }

    # Object-based suggestions for detected objects
    OBJECT_SUGGESTIONS = {
        "car": ["What color is the car?", "Is it parked or moving?"],
        "truck": ["Is this a delivery truck?", "What company truck is it?"],
        "dog": ["What breed is the dog?", "Is it wearing a collar?"],
        "cat": ["What color is the cat?", "Is it my cat?"],
        "bicycle": ["Is someone riding the bicycle?", "Where is it parked?"],
        "motorcycle": ["Is it parked or moving?", "What make is the motorcycle?"],
        "backpack": ["Who is carrying the backpack?", "What color is it?"],
        "umbrella": ["Is it raining?", "What color is the umbrella?"],
        "suitcase": ["Who has the suitcase?", "Are they leaving or arriving?"],
    }

    def __init__(self):
        """Initialize QuerySuggester."""
        logger.debug(
            "QuerySuggester initialized",
            extra={"event_type": "query_suggester_init"}
        )

    def get_suggestions(
        self,
        smart_detection_type: Optional[str] = None,
        objects_detected: Optional[List[str]] = None,
        limit: int = MAX_SUGGESTIONS,
    ) -> List[str]:
        """
        Get relevant query suggestions for an event.

        Combines suggestions from smart detection type and detected objects,
        deduplicating while preserving order.

        Args:
            smart_detection_type: Protect smart detection type (person, vehicle, etc.)
            objects_detected: List of detected objects from AI analysis
            limit: Maximum number of suggestions (default: 5)

        Returns:
            List of suggested query strings (up to limit)
        """
        suggestions = []

        # Primary suggestions from smart detection type
        if smart_detection_type:
            detection_lower = smart_detection_type.lower()
            if detection_lower in self.SUGGESTIONS:
                suggestions.extend(self.SUGGESTIONS[detection_lower][:3])

        # Secondary suggestions from detected objects
        if objects_detected:
            for obj in objects_detected:
                obj_lower = obj.lower()

                # Check for direct matches in object suggestions
                for key, obj_suggestions in self.OBJECT_SUGGESTIONS.items():
                    if key in obj_lower:
                        suggestions.extend(obj_suggestions[:2])
                        break

                # Also check smart detection type suggestions
                for key in self.SUGGESTIONS:
                    if key in obj_lower:
                        suggestions.extend(self.SUGGESTIONS[key][:2])
                        break

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique.append(s)

        result = unique[:limit]

        logger.debug(
            f"Generated {len(result)} query suggestions",
            extra={
                "event_type": "query_suggestions_generated",
                "smart_detection_type": smart_detection_type,
                "objects_count": len(objects_detected) if objects_detected else 0,
                "suggestions_count": len(result),
            }
        )

        return result

    @staticmethod
    def format_query(query: str) -> str:
        """
        Auto-format single-word queries for better CLIP matching (AC6).

        CLIP was trained with "a photo of {object}" format, so short queries
        benefit from this prefix.

        Args:
            query: User's query string

        Returns:
            Formatted query string

        Examples:
            >>> QuerySuggester.format_query("dog")
            "a photo of dog"
            >>> QuerySuggester.format_query("delivery person")
            "a photo of delivery person"
            >>> QuerySuggester.format_query("Was there a package?")
            "Was there a package?"
        """
        query = query.strip()

        if not query:
            return query

        # Already has CLIP format prefix
        if query.lower().startswith("a photo of"):
            return query

        # Question - don't modify
        if query.endswith("?"):
            return query

        # Short queries (1-2 words) benefit from formatting
        word_count = len(query.split())
        if word_count <= 2:
            return f"a photo of {query}"

        return query

    def get_suggestions_for_event(
        self,
        event: "Event",
        limit: int = MAX_SUGGESTIONS,
    ) -> List[str]:
        """
        Get suggestions for a specific event.

        Convenience method that extracts smart_detection_type and
        objects_detected from an event object.

        Args:
            event: Event model instance
            limit: Maximum number of suggestions

        Returns:
            List of suggested query strings
        """
        import json

        smart_type = getattr(event, "smart_detection_type", None)

        objects_raw = getattr(event, "objects_detected", None)
        if isinstance(objects_raw, str):
            try:
                objects = json.loads(objects_raw)
            except json.JSONDecodeError:
                objects = []
        elif isinstance(objects_raw, list):
            objects = objects_raw
        else:
            objects = []

        return self.get_suggestions(smart_type, objects, limit)


# Global singleton instance
_query_suggester: Optional[QuerySuggester] = None


def get_query_suggester() -> QuerySuggester:
    """
    Get the global QuerySuggester instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        QuerySuggester singleton instance
    """
    global _query_suggester

    if _query_suggester is None:
        _query_suggester = QuerySuggester()
        logger.info(
            "Global QuerySuggester instance created",
            extra={"event_type": "query_suggester_singleton_created"}
        )

    return _query_suggester
