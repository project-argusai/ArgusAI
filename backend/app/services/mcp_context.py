"""
MCPContextProvider for AI Context Enhancement (Story P11-3.1, P11-3.2)

This module provides the MCPContextProvider class that gathers context
from user feedback history and known entities to enhance AI description prompts.

Architecture:
    - Queries EventFeedback by camera_id for feedback history
    - Queries RecognizedEntity for entity context (P11-3.2)
    - Calculates camera-specific accuracy rates
    - Extracts common correction patterns
    - Formats context for AI prompt injection
    - Fail-open design ensures AI works even if context fails

Flow:
    Event → MCPContextProvider.get_context(camera_id, event_time, entity_id)
                                    ↓
                      Query recent feedback (last 50)
                                    ↓
                      Query entity details if entity_id provided
                                    ↓
                      Calculate accuracy rate
                                    ↓
                      Extract common corrections
                                    ↓
                      Build FeedbackContext and EntityContext
                                    ↓
                      Return AIContext
"""
import asyncio
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class FeedbackContext:
    """Context gathered from user feedback history."""
    accuracy_rate: Optional[float]  # 0.0-1.0, None if no feedback
    total_feedback: int
    common_corrections: List[str]  # Top 3 correction patterns
    recent_negative_reasons: List[str]  # Last 5 negative feedback reasons


@dataclass
class EntityContext:
    """Context about a matched entity (Story P11-3.2)."""
    entity_id: str
    name: str
    entity_type: str  # person, vehicle, unknown
    attributes: Dict[str, str]  # color, make, model for vehicles
    last_seen: Optional[datetime]
    sighting_count: int
    similar_entities: List[Dict[str, Any]] = field(default_factory=list)  # Top 3 similar by occurrence


@dataclass
class CameraContext:
    """Context about camera location and patterns (placeholder for P11-3.3)."""
    camera_id: str
    location_hint: Optional[str]
    typical_objects: List[str]
    false_positive_patterns: List[str]


@dataclass
class TimePatternContext:
    """Context about time-of-day patterns (placeholder for P11-3.3)."""
    hour: int
    typical_activity_level: str  # low, medium, high
    is_unusual: bool
    typical_event_count: float


@dataclass
class AIContext:
    """Combined context for AI prompt generation."""
    feedback: Optional[FeedbackContext] = None
    entity: Optional[EntityContext] = None
    camera: Optional[CameraContext] = None
    time_pattern: Optional[TimePatternContext] = None


class MCPContextProvider:
    """
    Provides context for AI prompts based on accumulated feedback and entities.

    This implementation includes feedback context (P11-3.1) and entity context (P11-3.2).
    Camera and time pattern context will be added in subsequent stories.

    Attributes:
        FEEDBACK_LIMIT: Number of recent feedback items to query (50)
        MAX_ENTITY_CONTEXT_CHARS: Maximum characters for entity context to prevent prompt overflow (500)
        MAX_SIMILAR_ENTITIES: Maximum similar entities to suggest (3)
    """

    FEEDBACK_LIMIT = 50
    MAX_ENTITY_CONTEXT_CHARS = 500
    MAX_SIMILAR_ENTITIES = 3

    def __init__(self, db: Session = None):
        """
        Initialize MCPContextProvider.

        Args:
            db: Optional SQLAlchemy session. If None, must be provided to get_context().
        """
        self._db = db
        logger.info(
            "MCPContextProvider initialized",
            extra={"event_type": "mcp_context_provider_init"}
        )

    async def get_context(
        self,
        camera_id: str,
        event_time: datetime,
        entity_id: Optional[str] = None,
        db: Session = None,
    ) -> AIContext:
        """
        Gather context for AI prompt generation.

        Uses fail-open design: if any context component fails, returns
        partial context with None for failed components.

        Args:
            camera_id: UUID of the camera
            event_time: When the event occurred
            entity_id: Optional UUID of matched entity (for future P11-3.2)
            db: SQLAlchemy session (uses instance db if not provided)

        Returns:
            AIContext with available context components
        """
        start_time = time.time()
        session = db or self._db

        if not session:
            logger.warning(
                "No database session provided to get_context",
                extra={"event_type": "mcp_context_no_session", "camera_id": camera_id}
            )
            return AIContext()

        # Gather context components in parallel (fail-open)
        feedback_ctx = await self._safe_get_feedback_context(session, camera_id)

        # Entity context (P11-3.2) - only if entity_id provided
        entity_ctx = None
        if entity_id:
            entity_ctx = await self._safe_get_entity_context(session, entity_id)

        # Camera and time pattern context are placeholders for future stories
        camera_ctx = None  # P11-3.3
        time_ctx = None    # P11-3.3

        context_gather_time_ms = (time.time() - start_time) * 1000

        # Log context gathering
        logger.info(
            f"MCP context gathered for camera {camera_id}",
            extra={
                "event_type": "mcp.context_gathered",
                "camera_id": camera_id,
                "duration_ms": round(context_gather_time_ms, 2),
                "has_feedback": feedback_ctx is not None,
                "has_entity": entity_ctx is not None,
                "has_camera": camera_ctx is not None,
                "has_time_pattern": time_ctx is not None,
            }
        )

        return AIContext(
            feedback=feedback_ctx,
            entity=entity_ctx,
            camera=camera_ctx,
            time_pattern=time_ctx,
        )

    async def _safe_get_feedback_context(
        self,
        db: Session,
        camera_id: str,
    ) -> Optional[FeedbackContext]:
        """
        Safely get feedback context with error handling.

        Implements fail-open: returns None on any error instead of propagating.

        Args:
            db: SQLAlchemy session
            camera_id: UUID of the camera

        Returns:
            FeedbackContext or None if error occurs
        """
        try:
            return await self._get_feedback_context(db, camera_id)
        except Exception as e:
            logger.warning(
                f"Failed to get feedback context for camera {camera_id}: {e}",
                extra={
                    "event_type": "mcp.context_error",
                    "component": "feedback",
                    "camera_id": camera_id,
                    "error": str(e),
                }
            )
            return None

    async def _get_feedback_context(
        self,
        db: Session,
        camera_id: str,
    ) -> Optional[FeedbackContext]:
        """
        Get feedback context for a camera.

        Queries recent feedback (last 50 items), calculates accuracy rate,
        and extracts common correction patterns.

        Args:
            db: SQLAlchemy session
            camera_id: UUID of the camera

        Returns:
            FeedbackContext with accuracy and correction patterns
        """
        from app.models.event_feedback import EventFeedback

        # Query recent feedback for this camera
        query = (
            db.query(EventFeedback)
            .filter(EventFeedback.camera_id == camera_id)
            .order_by(desc(EventFeedback.created_at))
            .limit(self.FEEDBACK_LIMIT)
        )

        feedbacks = query.all()
        total = len(feedbacks)

        if total == 0:
            return FeedbackContext(
                accuracy_rate=None,
                total_feedback=0,
                common_corrections=[],
                recent_negative_reasons=[],
            )

        # Calculate accuracy rate
        positive_count = sum(1 for f in feedbacks if f.rating == 'helpful')
        accuracy_rate = positive_count / total

        # Extract correction texts
        corrections = [f.correction for f in feedbacks if f.correction]

        # Get common correction patterns
        common_patterns = self._extract_common_patterns(corrections)

        # Get recent negative feedback reasons (last 5 with text)
        recent_negative = [
            f.correction for f in feedbacks[:5]
            if f.rating == 'not_helpful' and f.correction
        ]

        return FeedbackContext(
            accuracy_rate=accuracy_rate,
            total_feedback=total,
            common_corrections=common_patterns[:3],
            recent_negative_reasons=recent_negative[:5],
        )

    async def _safe_get_entity_context(
        self,
        db: Session,
        entity_id: str,
    ) -> Optional[EntityContext]:
        """
        Safely get entity context with error handling.

        Implements fail-open: returns None on any error instead of propagating.

        Args:
            db: SQLAlchemy session
            entity_id: UUID of the entity

        Returns:
            EntityContext or None if error occurs
        """
        try:
            return await self._get_entity_context(db, entity_id)
        except Exception as e:
            logger.warning(
                f"Failed to get entity context for entity {entity_id}: {e}",
                extra={
                    "event_type": "mcp.context_error",
                    "component": "entity",
                    "entity_id": entity_id,
                    "error": str(e),
                }
            )
            return None

    async def _get_entity_context(
        self,
        db: Session,
        entity_id: str,
    ) -> Optional[EntityContext]:
        """
        Get entity context for a matched entity (Story P11-3.2).

        Queries the RecognizedEntity model to get entity details including
        name, type, attributes, and sighting count. Also queries for similar
        entities of the same type.

        Args:
            db: SQLAlchemy session
            entity_id: UUID of the entity

        Returns:
            EntityContext with entity details, or None if entity not found
        """
        from app.models.recognized_entity import RecognizedEntity

        # Query entity by ID
        entity = (
            db.query(RecognizedEntity)
            .filter(RecognizedEntity.id == entity_id)
            .first()
        )

        if not entity:
            logger.debug(
                f"Entity not found: {entity_id}",
                extra={
                    "event_type": "mcp.entity_not_found",
                    "entity_id": entity_id,
                }
            )
            return None

        # Build attributes dict from entity fields
        attributes = {}
        if entity.vehicle_color:
            attributes['color'] = entity.vehicle_color
        if entity.vehicle_make:
            attributes['make'] = entity.vehicle_make
        if entity.vehicle_model:
            attributes['model'] = entity.vehicle_model

        # Get similar entities (for context)
        similar_entities = await self._get_similar_entities(
            db, entity_id, entity.entity_type, entity.vehicle_signature
        )

        # Use display_name if name is not set
        name = entity.name or entity.display_name

        logger.debug(
            f"Entity context gathered for {entity_id}",
            extra={
                "event_type": "mcp.entity_context_gathered",
                "entity_id": entity_id,
                "entity_type": entity.entity_type,
                "has_name": entity.name is not None,
                "attribute_count": len(attributes),
                "similar_count": len(similar_entities),
            }
        )

        return EntityContext(
            entity_id=entity.id,
            name=name,
            entity_type=entity.entity_type,
            attributes=attributes,
            last_seen=entity.last_seen_at,
            sighting_count=entity.occurrence_count,
            similar_entities=similar_entities,
        )

    async def _get_similar_entities(
        self,
        db: Session,
        entity_id: str,
        entity_type: str,
        vehicle_signature: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get similar entities of the same type (Story P11-3.2 AC-3.2.2).

        For vehicles, matches by vehicle_signature pattern.
        For persons, returns other persons sorted by occurrence count.

        Args:
            db: SQLAlchemy session
            entity_id: UUID of current entity (to exclude from results)
            entity_type: Type of entity (person, vehicle)
            vehicle_signature: Optional vehicle signature for matching

        Returns:
            List of top 3 similar entities with id, name, type, occurrence_count
        """
        from app.models.recognized_entity import RecognizedEntity

        # Build query for similar entities
        query = (
            db.query(RecognizedEntity)
            .filter(RecognizedEntity.id != entity_id)  # Exclude current entity
            .filter(RecognizedEntity.entity_type == entity_type)
        )

        # For vehicles, try to match by similar signature pattern
        if entity_type == "vehicle" and vehicle_signature:
            # Extract color from signature (first part before dash)
            sig_parts = vehicle_signature.split("-")
            if len(sig_parts) >= 1:
                color = sig_parts[0]
                # Find vehicles with same color or similar signature
                query = query.filter(
                    RecognizedEntity.vehicle_signature.ilike(f"{color}%")
                )

        # Order by occurrence count (most seen first) and limit
        query = (
            query.order_by(desc(RecognizedEntity.occurrence_count))
            .limit(self.MAX_SIMILAR_ENTITIES)
        )

        similar = query.all()

        return [
            {
                "id": e.id,
                "name": e.name or e.display_name,
                "entity_type": e.entity_type,
                "occurrence_count": e.occurrence_count,
            }
            for e in similar
        ]

    def _extract_common_patterns(self, corrections: List[str]) -> List[str]:
        """
        Extract common patterns from correction texts.

        Tokenizes corrections and finds most frequent meaningful words.

        Args:
            corrections: List of correction texts

        Returns:
            List of top 3 most common patterns
        """
        if not corrections:
            return []

        # Common words to exclude
        stop_words = {
            'the', 'a', 'an', 'is', 'was', 'it', 'this', 'that', 'not',
            'and', 'or', 'but', 'of', 'in', 'to', 'for', 'on', 'with',
            'be', 'are', 'were', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'could', 'should',
            'i', 'you', 'he', 'she', 'we', 'they', 'my', 'your', 'its',
            'there', 'here', 'where', 'when', 'what', 'which', 'who',
            'actually', 'just', 'really', 'very', 'so', 'too', 'also',
        }

        # Count word frequencies
        word_counts: Counter = Counter()
        for correction in corrections:
            # Tokenize: lowercase, remove punctuation, split on whitespace
            words = re.findall(r'\b[a-z]+\b', correction.lower())
            # Filter stop words and short words
            meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]
            word_counts.update(meaningful_words)

        # Get top patterns
        top_patterns = [word for word, _ in word_counts.most_common(5)]
        return top_patterns[:3]

    def format_for_prompt(self, context: AIContext) -> str:
        """
        Format context for inclusion in AI prompt.

        Generates human-readable context text that can be injected into
        AI prompts to improve description accuracy.

        Args:
            context: AIContext with gathered context components

        Returns:
            Formatted context string, empty string if no context
        """
        parts = []

        # Feedback context
        if context.feedback and context.feedback.accuracy_rate is not None:
            accuracy_pct = int(context.feedback.accuracy_rate * 100)
            parts.append(f"Previous accuracy for this camera: {accuracy_pct}%")

            if context.feedback.common_corrections:
                corrections_str = ", ".join(context.feedback.common_corrections)
                parts.append(f"Common corrections: {corrections_str}")

        # Entity context (Story P11-3.2)
        if context.entity:
            entity_parts = self._format_entity_context(context.entity)
            parts.extend(entity_parts)

        # Camera context (placeholder for P11-3.3)
        if context.camera and context.camera.location_hint:
            parts.append(f"Camera location: {context.camera.location_hint}")

        # Time pattern context (placeholder for P11-3.3)
        if context.time_pattern and context.time_pattern.is_unusual:
            parts.append("Note: This is unusual activity for this time of day")

        return "\n".join(parts) if parts else ""

    def _format_entity_context(self, entity: EntityContext) -> List[str]:
        """
        Format entity context for inclusion in AI prompt (Story P11-3.2 AC-3.2.3, AC-3.2.4).

        Includes entity name, type, attributes, sighting history, and similar entities.
        Limits context size to MAX_ENTITY_CONTEXT_CHARS to prevent prompt overflow (AC-3.2.5).

        Args:
            entity: EntityContext with entity details

        Returns:
            List of formatted context strings
        """
        parts = []
        total_chars = 0

        # Primary entity identification (always included)
        primary = f"Known entity: {entity.name} ({entity.entity_type})"
        parts.append(primary)
        total_chars += len(primary)

        # Vehicle-specific attributes (color, make, model)
        if entity.attributes:
            attrs = ", ".join(f"{k}={v}" for k, v in entity.attributes.items())
            attr_str = f"Entity attributes: {attrs}"
            if total_chars + len(attr_str) <= self.MAX_ENTITY_CONTEXT_CHARS:
                parts.append(attr_str)
                total_chars += len(attr_str)

        # Sighting history (AC-3.2.4)
        if entity.sighting_count > 0:
            sighting_str = f"Seen {entity.sighting_count} time"
            if entity.sighting_count != 1:
                sighting_str += "s"

            # Add last seen time if available
            if entity.last_seen:
                try:
                    last_seen_str = self._format_time_ago(entity.last_seen)
                    if last_seen_str:
                        sighting_str += f", last seen {last_seen_str}"
                except Exception:
                    # Fallback if formatting fails
                    pass

            if total_chars + len(sighting_str) <= self.MAX_ENTITY_CONTEXT_CHARS:
                parts.append(sighting_str)
                total_chars += len(sighting_str)

        # Similar entities (AC-3.2.2) - only if space permits
        if entity.similar_entities and total_chars < self.MAX_ENTITY_CONTEXT_CHARS - 50:
            similar_names = [e["name"] for e in entity.similar_entities[:2]]
            if similar_names:
                similar_str = f"Similar known entities: {', '.join(similar_names)}"
                if total_chars + len(similar_str) <= self.MAX_ENTITY_CONTEXT_CHARS:
                    parts.append(similar_str)

        # Log if truncation occurred
        if total_chars > self.MAX_ENTITY_CONTEXT_CHARS:
            logger.debug(
                f"Entity context truncated to {self.MAX_ENTITY_CONTEXT_CHARS} chars",
                extra={
                    "event_type": "mcp.entity_context_truncated",
                    "entity_id": entity.entity_id,
                    "original_chars": total_chars,
                }
            )

        return parts

    def _format_time_ago(self, dt: datetime) -> str:
        """
        Format a datetime as a human-readable "time ago" string.

        Args:
            dt: The datetime to format

        Returns:
            String like "2 hours ago", "3 days ago", etc.
        """
        now = datetime.now(timezone.utc)

        # Handle timezone-naive datetimes
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        diff = now - dt

        seconds = diff.total_seconds()

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds < 2592000:
            weeks = int(seconds / 604800)
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        else:
            months = int(seconds / 2592000)
            return f"{months} month{'s' if months != 1 else ''} ago"


# Global singleton instance
_mcp_context_provider: Optional[MCPContextProvider] = None


def get_mcp_context_provider(db: Session = None) -> MCPContextProvider:
    """
    Get the global MCPContextProvider instance.

    Creates the instance on first call (lazy initialization).

    Args:
        db: Optional SQLAlchemy session to use

    Returns:
        MCPContextProvider singleton instance
    """
    global _mcp_context_provider

    if _mcp_context_provider is None:
        _mcp_context_provider = MCPContextProvider(db=db)
        logger.info(
            "Global MCPContextProvider instance created",
            extra={"event_type": "mcp_context_provider_singleton_created"}
        )

    return _mcp_context_provider


def reset_mcp_context_provider() -> None:
    """
    Reset the global MCPContextProvider instance.

    Useful for testing to ensure a fresh instance.
    """
    global _mcp_context_provider
    _mcp_context_provider = None
