"""
Voice Query Service for natural language event queries (Story P4-6.3)

Enables voice assistant integration by parsing natural language queries
and generating spoken response text summarizing security events.

Example queries:
- "What's happening at the front door?"
- "Any activity this morning?"
- "Was there anyone at the back yard in the last hour?"

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import re
import logging
from app.core.decorators import singleton
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict, Any
from collections import Counter

from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.camera import Camera

logger = logging.getLogger(__name__)


@dataclass
class TimeRange:
    """Represents a parsed time range from a query."""
    start: datetime
    end: datetime
    description: str  # Human-readable description like "today", "last hour"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "description": self.description,
        }


@dataclass
class ParsedQuery:
    """Result of parsing a natural language query."""
    original_query: str
    time_range: TimeRange
    camera_filter: Optional[str] = None  # Camera ID if specific camera mentioned
    camera_name: Optional[str] = None  # Camera name for response
    query_type: str = "activity"  # activity, specific_event, count


@dataclass
class QueryResult:
    """Result of executing a parsed query."""
    events: List[Event] = field(default_factory=list)
    count: int = 0
    cameras_involved: List[str] = field(default_factory=list)  # Camera names
    objects_detected: Dict[str, int] = field(default_factory=dict)  # object -> count


@singleton
class VoiceQueryService:
    """
    Service for processing natural language voice queries about security events.

    Parses queries to extract:
    - Time range (today, last hour, this morning, etc.)
    - Camera filter (front door, back yard, etc.)

    Generates TTS-friendly responses summarizing matching events.
    """

    # Time expression patterns
    TIME_PATTERNS = [
        # Relative hours/minutes
        (r"last\s+(\d+)\s+hours?", "last_n_hours"),
        (r"last\s+(\d+)\s+minutes?", "last_n_minutes"),
        (r"past\s+(\d+)\s+hours?", "last_n_hours"),
        (r"past\s+(\d+)\s+minutes?", "last_n_minutes"),
        # Named periods
        (r"\btoday\b", "today"),
        (r"\byesterday\b", "yesterday"),
        (r"\bthis\s+morning\b", "this_morning"),
        (r"\bthis\s+afternoon\b", "this_afternoon"),
        (r"\bthis\s+evening\b", "this_evening"),
        (r"\btonight\b", "tonight"),
        (r"\blast\s+hour\b", "last_hour"),
        (r"\brecently\b", "last_hour"),
        (r"\bjust\s+now\b", "last_15_minutes"),
    ]

    # Camera name synonyms for fuzzy matching
    CAMERA_SYNONYMS = {
        "front": ["front door", "front entrance", "front porch", "main entrance"],
        "back": ["back door", "back yard", "backyard", "rear"],
        "garage": ["garage", "driveway", "car port"],
        "side": ["side door", "side entrance", "side yard"],
        "patio": ["patio", "deck", "terrace"],
        "garden": ["garden", "lawn"],
    }

    def __init__(self):
        """Initialize the voice query service."""
        pass

    def parse_query(self, query: str, cameras: List[Camera]) -> ParsedQuery:
        """
        Parse a natural language query into structured components.

        Args:
            query: Natural language query string
            cameras: List of available cameras for name matching

        Returns:
            ParsedQuery with extracted time range and camera filter
        """
        query_lower = query.lower().strip()

        # Parse time range
        time_range = self._parse_time_expression(query_lower)

        # Parse camera filter
        camera_id, camera_name = self._match_camera_name(query_lower, cameras)

        return ParsedQuery(
            original_query=query,
            time_range=time_range,
            camera_filter=camera_id,
            camera_name=camera_name,
            query_type="activity",
        )

    def execute_query(self, db: Session, parsed: ParsedQuery) -> QueryResult:
        """
        Execute a parsed query against the database.

        Args:
            db: Database session
            parsed: Parsed query with filters

        Returns:
            QueryResult with matching events and aggregations
        """
        # Build base query
        query = db.query(Event).filter(
            Event.timestamp >= parsed.time_range.start,
            Event.timestamp <= parsed.time_range.end,
        )

        # Apply camera filter if specified
        if parsed.camera_filter:
            query = query.filter(Event.camera_id == parsed.camera_filter)

        # Order by timestamp descending (most recent first)
        query = query.order_by(Event.timestamp.desc())

        # Execute query
        events = query.all()

        # Aggregate results
        cameras_involved = set()
        objects_counter: Counter = Counter()

        for event in events:
            # Get camera name
            camera = db.query(Camera).filter(Camera.id == event.camera_id).first()
            if camera:
                cameras_involved.add(camera.name)

            # Count detected objects
            if event.objects_detected:
                try:
                    import json
                    objects = json.loads(event.objects_detected) if isinstance(event.objects_detected, str) else event.objects_detected
                    for obj in objects:
                        if obj.lower() not in ("unknown", "motion"):
                            objects_counter[obj.lower()] += 1
                except (json.JSONDecodeError, TypeError):
                    pass

        return QueryResult(
            events=events,
            count=len(events),
            cameras_involved=list(cameras_involved),
            objects_detected=dict(objects_counter),
        )

    def generate_response(self, parsed: ParsedQuery, result: QueryResult) -> str:
        """
        Generate a TTS-friendly spoken response from query results.

        Args:
            parsed: The parsed query (for context)
            result: Query execution result

        Returns:
            Natural language response string optimized for text-to-speech
        """
        time_desc = parsed.time_range.description
        camera_desc = parsed.camera_name or "all cameras"

        # No events found
        if result.count == 0:
            return self._generate_no_events_response(time_desc, camera_desc)

        # Single event
        if result.count == 1:
            return self._generate_single_event_response(
                result.events[0], time_desc, camera_desc
            )

        # Multiple events
        return self._generate_multiple_events_response(
            result, time_desc, camera_desc
        )

    def _parse_time_expression(self, query: str) -> TimeRange:
        """
        Parse time expressions from a query string.

        Args:
            query: Lowercase query string

        Returns:
            TimeRange with start, end, and description
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        for pattern, time_type in self.TIME_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                if time_type == "last_n_hours":
                    n = int(match.group(1))
                    return TimeRange(
                        start=now - timedelta(hours=n),
                        end=now,
                        description=f"the last {n} hour{'s' if n > 1 else ''}",
                    )
                elif time_type == "last_n_minutes":
                    n = int(match.group(1))
                    return TimeRange(
                        start=now - timedelta(minutes=n),
                        end=now,
                        description=f"the last {n} minute{'s' if n > 1 else ''}",
                    )
                elif time_type == "today":
                    return TimeRange(
                        start=today_start,
                        end=now,
                        description="today",
                    )
                elif time_type == "yesterday":
                    yesterday_start = today_start - timedelta(days=1)
                    yesterday_end = today_start - timedelta(seconds=1)
                    return TimeRange(
                        start=yesterday_start,
                        end=yesterday_end,
                        description="yesterday",
                    )
                elif time_type == "this_morning":
                    morning_start = today_start.replace(hour=6)
                    morning_end = today_start.replace(hour=12)
                    # If it's before noon, end is now
                    if now.hour < 12:
                        morning_end = now
                    return TimeRange(
                        start=morning_start,
                        end=morning_end,
                        description="this morning",
                    )
                elif time_type == "this_afternoon":
                    afternoon_start = today_start.replace(hour=12)
                    afternoon_end = today_start.replace(hour=18)
                    if now.hour < 18:
                        afternoon_end = now
                    return TimeRange(
                        start=afternoon_start,
                        end=afternoon_end,
                        description="this afternoon",
                    )
                elif time_type == "this_evening":
                    evening_start = today_start.replace(hour=18)
                    evening_end = today_start.replace(hour=22)
                    if now.hour < 22:
                        evening_end = now
                    return TimeRange(
                        start=evening_start,
                        end=evening_end,
                        description="this evening",
                    )
                elif time_type == "tonight":
                    tonight_start = today_start.replace(hour=18)
                    tonight_end = today_start + timedelta(days=1)  # Midnight
                    return TimeRange(
                        start=tonight_start,
                        end=tonight_end,
                        description="tonight",
                    )
                elif time_type == "last_hour":
                    return TimeRange(
                        start=now - timedelta(hours=1),
                        end=now,
                        description="the last hour",
                    )
                elif time_type == "last_15_minutes":
                    return TimeRange(
                        start=now - timedelta(minutes=15),
                        end=now,
                        description="the last 15 minutes",
                    )

        # Default: last hour
        return TimeRange(
            start=now - timedelta(hours=1),
            end=now,
            description="the last hour",
        )

    def _match_camera_name(
        self, query: str, cameras: List[Camera]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Match camera name from query using fuzzy matching.

        Args:
            query: Query string (will be lowercased internally)
            cameras: List of available cameras

        Returns:
            Tuple of (camera_id, camera_name) or (None, None) if no match
        """
        # Ensure query is lowercase for matching
        query = query.lower()

        # Check for "all cameras" or no camera filter
        if "all camera" in query or "every camera" in query:
            return None, None

        # Try exact name matching first
        for camera in cameras:
            camera_name_lower = camera.name.lower()
            if camera_name_lower in query:
                return camera.id, camera.name

        # Try synonym matching
        for base_term, synonyms in self.CAMERA_SYNONYMS.items():
            for synonym in synonyms:
                if synonym in query:
                    # Find a camera that matches this term
                    for camera in cameras:
                        camera_name_lower = camera.name.lower()
                        if base_term in camera_name_lower or any(
                            s in camera_name_lower for s in synonyms
                        ):
                            return camera.id, camera.name

        # Try partial word matching
        query_words = set(query.split())
        for camera in cameras:
            camera_words = set(camera.name.lower().split())
            # If any significant word matches
            if query_words & camera_words:
                return camera.id, camera.name

        return None, None

    def _generate_no_events_response(self, time_desc: str, camera_desc: str) -> str:
        """Generate response when no events found."""
        if camera_desc == "all cameras":
            return f"No activity detected {time_desc}."
        return f"No activity detected at the {camera_desc} {time_desc}."

    def _generate_single_event_response(
        self, event: Event, time_desc: str, camera_desc: str
    ) -> str:
        """Generate response for a single event."""
        # Format time in spoken form
        event_time = event.timestamp.strftime("%-I:%M %p") if event.timestamp else "recently"

        # Get main object from description or objects_detected
        main_object = "activity"
        if event.description:
            # Extract key noun from description
            desc_lower = event.description.lower()
            if "person" in desc_lower:
                main_object = "a person"
            elif "vehicle" in desc_lower or "car" in desc_lower:
                main_object = "a vehicle"
            elif "package" in desc_lower or "delivery" in desc_lower:
                main_object = "a package"
            elif "animal" in desc_lower or "dog" in desc_lower or "cat" in desc_lower:
                main_object = "an animal"

        if camera_desc == "all cameras":
            return f"I found 1 event {time_desc}. {main_object.capitalize()} was detected at {event_time}."
        return f"I found 1 event at the {camera_desc} {time_desc}. {main_object.capitalize()} was detected at {event_time}."

    def _generate_multiple_events_response(
        self, result: QueryResult, time_desc: str, camera_desc: str
    ) -> str:
        """Generate response for multiple events."""
        count = result.count
        objects = result.objects_detected

        # Build object summary
        object_summary = ""
        if objects:
            sorted_objects = sorted(objects.items(), key=lambda x: x[1], reverse=True)
            top_objects = sorted_objects[:3]  # Top 3 object types

            parts = []
            for obj, obj_count in top_objects:
                if obj_count == 1:
                    parts.append(f"1 {obj}")
                else:
                    # Pluralize
                    plural = obj + "s" if not obj.endswith("s") else obj
                    parts.append(f"{obj_count} {plural}")

            if parts:
                object_summary = f" I saw {', '.join(parts[:-1])}" if len(parts) > 1 else f" I saw {parts[0]}"
                if len(parts) > 1:
                    object_summary += f" and {parts[-1]}"
                object_summary += "."

        # Build camera summary
        camera_summary = ""
        if len(result.cameras_involved) > 1:
            camera_summary = f" Activity was on {len(result.cameras_involved)} cameras."

        # Main response
        if camera_desc == "all cameras":
            return f"I found {count} events {time_desc}.{object_summary}{camera_summary}"
        return f"I found {count} events at the {camera_desc} {time_desc}.{object_summary}"

    def handle_ambiguous_query(self, query: str) -> str:
        """
        Handle vague or ambiguous queries.

        Args:
            query: The original query

        Returns:
            Helpful response for the user
        """
        # Check for common ambiguous patterns
        query_lower = query.lower()

        if any(word in query_lower for word in ["interesting", "important", "unusual"]):
            return "I can tell you about recent activity. Try asking 'What happened today?' or 'Any activity in the last hour?'"

        if any(word in query_lower for word in ["help", "what can"]):
            return "You can ask me things like 'What's happening at the front door?' or 'Any activity this morning?'"

        return "I didn't quite understand that. Try asking about activity at a specific camera or time, like 'What happened at the front door today?'"


# Backward compatible thin getter (delegates to @singleton decorator)
def get_voice_query_service() -> VoiceQueryService:
    """
    Get the global VoiceQueryService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer VoiceQueryService() directly.
    """
    return VoiceQueryService()


def reset_voice_query_service() -> None:
    """Reset the global VoiceQueryService instance (for testing)."""
    VoiceQueryService._reset_instance()
