"""
Context-Enhanced Prompt Service for AI Descriptions (Story P4-3.4, P11-3)

This module provides context-enhanced prompts for AI description generation.
It integrates with EntityService, SimilarityService, PatternService, and
MCPContextProvider to provide rich contextual information about recognized
visitors, patterns, user feedback, and camera-specific accuracy.

Architecture:
    - Orchestrates existing services: EntityService, SimilarityService, PatternService
    - Integrates MCPContextProvider for feedback/camera/time pattern context (Story P11-3)
    - Retrieves and formats historical context for AI prompts
    - Implements A/B testing capability for context inclusion
    - Graceful degradation if context retrieval fails (fail-open design)

Flow:
    Event Created → ContextEnhancedPromptService.build_context_enhanced_prompt()
                                    ↓
                         Check settings (enabled, A/B test)
                                    ↓
                         Get entity context (if matched)
                                    ↓
                         Get similar events (SimilarityService)
                                    ↓
                         Get time pattern context (PatternService)
                                    ↓
                         Get MCP context (MCPContextProvider) ← Story P11-3
                                    ↓
                         Format and return enhanced prompt

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import logging
from app.core.decorators import singleton
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.entity_service import EntityService, EntityMatchResult, get_entity_service
from app.services.similarity_service import SimilarityService, SimilarEvent, get_similarity_service
from app.services.pattern_service import PatternService, get_pattern_service
from app.services.mcp_context import (
    MCPContextProvider,
    AIContext,
    get_mcp_context_provider,
)

logger = logging.getLogger(__name__)


@dataclass
class ContextEnhancedPromptResult:
    """Result from context-enhanced prompt building."""
    prompt: str
    context_included: bool
    ab_test_skip: bool = False
    entity_context_included: bool = False
    similar_events_count: int = 0
    time_pattern_included: bool = False
    context_gather_time_ms: float = 0.0
    # Context components for logging
    entity_name: Optional[str] = None
    entity_occurrence_count: Optional[int] = None
    similarity_scores: list[float] = field(default_factory=list)
    # MCP context fields (Story P11-3 integration)
    mcp_context_included: bool = False
    mcp_feedback_included: bool = False
    mcp_camera_included: bool = False
    mcp_time_pattern_included: bool = False
    mcp_accuracy_rate: Optional[float] = None


@singleton
class ContextEnhancedPromptService:
    """
    Build context-enhanced prompts for AI description generation.

    This service orchestrates EntityService and SimilarityService to build
    rich contextual prompts that help AI generate more informative descriptions.

    Attributes:
        DEFAULT_SIMILARITY_THRESHOLD: Default threshold for including similar events (0.7)
        DEFAULT_TIME_WINDOW_DAYS: Default time window for historical context (30 days)
    """

    DEFAULT_SIMILARITY_THRESHOLD = 0.7
    DEFAULT_TIME_WINDOW_DAYS = 30

    def __init__(
        self,
        entity_service: Optional[EntityService] = None,
        similarity_service: Optional[SimilarityService] = None,
        pattern_service: Optional[PatternService] = None,
        mcp_context_provider: Optional[MCPContextProvider] = None,
    ):
        """
        Initialize ContextEnhancedPromptService.

        Args:
            entity_service: EntityService instance for entity lookups.
                          If None, will use the global singleton.
            similarity_service: SimilarityService instance for similar event lookups.
                              If None, will use the global singleton.
            pattern_service: PatternService instance for timing analysis.
                           If None, will use the global singleton. (Story P4-3.5)
            mcp_context_provider: MCPContextProvider instance for feedback/camera/time context.
                                If None, will use the global singleton. (Story P11-3)
        """
        self._entity_service = entity_service or get_entity_service()
        self._similarity_service = similarity_service or get_similarity_service()
        self._pattern_service = pattern_service or get_pattern_service()
        self._mcp_context_provider = mcp_context_provider
        logger.info(
            "ContextEnhancedPromptService initialized",
            extra={"event_type": "context_prompt_service_init"}
        )

    async def build_context_enhanced_prompt(
        self,
        db: Session,
        event_id: str,
        base_prompt: str,
        camera_id: str,
        event_time: datetime,
        matched_entity: Optional[EntityMatchResult] = None,
    ) -> ContextEnhancedPromptResult:
        """
        Build an AI prompt enhanced with historical context.

        Returns original prompt if context disabled or A/B test skips.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event being described
            base_prompt: Original AI prompt without context
            camera_id: UUID of the camera
            event_time: When the event occurred
            matched_entity: Optional EntityMatchResult from entity matching step

        Returns:
            ContextEnhancedPromptResult with enhanced prompt and metadata
        """
        start_time = time.time()

        # Step 1: Check if context enhancement is enabled
        if not self._is_context_enabled(db):
            return ContextEnhancedPromptResult(
                prompt=base_prompt,
                context_included=False,
            )

        # Step 2: Check A/B test (random skip for comparison)
        ab_percentage = self._get_ab_test_percentage(db)
        if ab_percentage > 0 and random.randint(1, 100) <= ab_percentage:
            logger.debug(
                f"Context skipped due to A/B test for event {event_id}",
                extra={
                    "event_type": "context_ab_test_skip",
                    "event_id": event_id,
                    "ab_percentage": ab_percentage,
                }
            )
            return ContextEnhancedPromptResult(
                prompt=base_prompt,
                context_included=False,
                ab_test_skip=True,
            )

        # Step 3: Gather context components (with graceful degradation)
        context_parts = []
        entity_context_included = False
        similar_events_count = 0
        time_pattern_included = False
        entity_name = None
        entity_occurrence_count = None
        similarity_scores = []
        # MCP context tracking (Story P11-3)
        mcp_context_included = False
        mcp_feedback_included = False
        mcp_camera_included = False
        mcp_time_pattern_included = False
        mcp_accuracy_rate = None

        threshold = self._get_similarity_threshold(db)
        time_window_days = self._get_time_window_days(db)

        # 3a: Entity context (from matched entity)
        try:
            if matched_entity and matched_entity.similarity_score >= threshold:
                entity_context = self._format_entity_context(matched_entity)
                if entity_context:
                    context_parts.append(entity_context)
                    entity_context_included = True
                    entity_name = matched_entity.name
                    entity_occurrence_count = matched_entity.occurrence_count
        except Exception as e:
            logger.warning(
                f"Failed to format entity context for event {event_id}: {e}",
                extra={"event_id": event_id, "error": str(e)}
            )

        # 3b: Similar events context (from SimilarityService)
        try:
            similar_events = await self._similarity_service.find_similar_events(
                db=db,
                event_id=event_id,
                limit=10,
                min_similarity=threshold,
                time_window_days=time_window_days,
            )
            if similar_events:
                similarity_context = self._format_similarity_context(
                    similar_events, time_window_days
                )
                if similarity_context:
                    context_parts.append(similarity_context)
                    similar_events_count = len(similar_events)
                    similarity_scores = [e.similarity_score for e in similar_events]
        except ValueError:
            # No embedding for this event - skip similarity search
            logger.debug(
                f"No embedding available for similarity search (event {event_id})",
                extra={"event_id": event_id}
            )
        except Exception as e:
            logger.warning(
                f"Failed to get similar events for event {event_id}: {e}",
                extra={"event_id": event_id, "error": str(e)}
            )

        # 3c: Time pattern context
        try:
            time_context = await self._get_time_pattern_context(
                db, camera_id, event_time, time_window_days
            )
            if time_context:
                context_parts.append(time_context)
                time_pattern_included = True
        except Exception as e:
            logger.warning(
                f"Failed to get time pattern context for event {event_id}: {e}",
                extra={"event_id": event_id, "error": str(e)}
            )

        # 3d: MCP context (Story P11-3 - feedback, camera, time patterns from MCPContextProvider)
        try:
            mcp_provider = self._mcp_context_provider or get_mcp_context_provider(db)
            entity_id = matched_entity.entity_id if matched_entity else None

            mcp_context: AIContext = await mcp_provider.get_context(
                camera_id=camera_id,
                event_time=event_time,
                entity_id=entity_id,
                db=db,
            )

            # Format MCP context and add to context parts
            mcp_formatted = mcp_provider.format_for_prompt(mcp_context)
            if mcp_formatted:
                # Add MCP context as separate lines
                for line in mcp_formatted.split("\n"):
                    if line.strip():
                        context_parts.append(line.strip())
                mcp_context_included = True

                # Track which MCP components were included
                if mcp_context.feedback and mcp_context.feedback.accuracy_rate is not None:
                    mcp_feedback_included = True
                    mcp_accuracy_rate = mcp_context.feedback.accuracy_rate
                if mcp_context.camera:
                    mcp_camera_included = True
                if mcp_context.time_pattern:
                    mcp_time_pattern_included = True

                logger.debug(
                    f"MCP context gathered for event {event_id}",
                    extra={
                        "event_type": "mcp_context_gathered",
                        "event_id": event_id,
                        "camera_id": camera_id,
                        "feedback_included": mcp_feedback_included,
                        "camera_included": mcp_camera_included,
                        "time_pattern_included": mcp_time_pattern_included,
                        "accuracy_rate": mcp_accuracy_rate,
                    }
                )
        except Exception as e:
            # Fail-open: MCP context failures don't block AI description
            logger.warning(
                f"Failed to get MCP context for event {event_id}: {e}",
                extra={"event_id": event_id, "camera_id": camera_id, "error": str(e)}
            )

        # Step 4: Build enhanced prompt
        context_gather_time_ms = (time.time() - start_time) * 1000

        if context_parts:
            context_section = "HISTORICAL CONTEXT:\n" + "\n".join(f"- {part}" for part in context_parts)
            context_section += "\n\nPlease incorporate this context naturally into your description if relevant. For example, refer to recognized visitors by name and mention if this is a regular occurrence."
            enhanced_prompt = f"{base_prompt}\n\n{context_section}"
        else:
            enhanced_prompt = base_prompt

        # Log context gathering details
        logger.info(
            f"Context gathered for event {event_id}",
            extra={
                "event_type": "context_gathered",
                "event_id": event_id,
                "context_included": bool(context_parts),
                "entity_context": entity_context_included,
                "similar_events": similar_events_count,
                "time_pattern": time_pattern_included,
                "context_gather_time_ms": round(context_gather_time_ms, 2),
                "entity_name": entity_name,
                "entity_occurrence_count": entity_occurrence_count,
                "similarity_scores": [round(s, 3) for s in similarity_scores[:5]],  # Top 5
                # MCP context (Story P11-3)
                "mcp_context_included": mcp_context_included,
                "mcp_feedback_included": mcp_feedback_included,
                "mcp_camera_included": mcp_camera_included,
                "mcp_time_pattern_included": mcp_time_pattern_included,
                "mcp_accuracy_rate": round(mcp_accuracy_rate, 3) if mcp_accuracy_rate else None,
            }
        )

        return ContextEnhancedPromptResult(
            prompt=enhanced_prompt,
            context_included=bool(context_parts),
            entity_context_included=entity_context_included,
            similar_events_count=similar_events_count,
            time_pattern_included=time_pattern_included,
            context_gather_time_ms=context_gather_time_ms,
            entity_name=entity_name,
            entity_occurrence_count=entity_occurrence_count,
            similarity_scores=similarity_scores,
            # MCP context fields (Story P11-3)
            mcp_context_included=mcp_context_included,
            mcp_feedback_included=mcp_feedback_included,
            mcp_camera_included=mcp_camera_included,
            mcp_time_pattern_included=mcp_time_pattern_included,
            mcp_accuracy_rate=mcp_accuracy_rate,
        )

    def _format_entity_context(self, entity: EntityMatchResult) -> Optional[str]:
        """
        Format entity context for inclusion in AI prompt.

        Args:
            entity: EntityMatchResult from entity matching

        Returns:
            Formatted context string, or None if no useful context
        """
        if not entity:
            return None

        # Build visitor name part
        if entity.name:
            visitor_name = f'Known visitor: "{entity.name}" (named by user)'
        else:
            visitor_name = f"Recognized visitor (unnamed {entity.entity_type})"

        # Format dates naturally
        first_seen_str = self._format_relative_date(entity.first_seen_at)
        last_seen_str = self._format_relative_date(entity.last_seen_at)

        # Build occurrence info
        if entity.occurrence_count == 1:
            occurrence_info = "This is their first recorded visit"
        elif entity.occurrence_count == 2:
            occurrence_info = f"Seen once before ({first_seen_str})"
        else:
            occurrence_info = f"Seen {entity.occurrence_count} times total (first: {first_seen_str}, last: {last_seen_str})"

        return f"{visitor_name}. {occurrence_info}"

    def _format_similarity_context(
        self,
        similar_events: list[SimilarEvent],
        time_window_days: int
    ) -> Optional[str]:
        """
        Format similar events context for inclusion in AI prompt.

        Args:
            similar_events: List of similar events from SimilarityService
            time_window_days: Time window used for search

        Returns:
            Formatted context string, or None if no similar events
        """
        if not similar_events:
            return None

        count = len(similar_events)
        best_score = max(e.similarity_score for e in similar_events)

        # Summarize event types if available
        descriptions = [e.description for e in similar_events if e.description]
        type_summary = self._summarize_event_types(descriptions)

        context = f"Similar events: {count} occurrences in last {time_window_days} days"

        if best_score >= 0.9:
            context += f" (highest match: {int(best_score * 100)}% - very similar)"
        elif best_score >= 0.8:
            context += f" (highest match: {int(best_score * 100)}% - quite similar)"
        else:
            context += f" (highest match: {int(best_score * 100)}%)"

        if type_summary:
            context += f". {type_summary}"

        # Add most recent similar event timing
        most_recent = min(similar_events, key=lambda e: abs((datetime.now(timezone.utc) - e.timestamp).total_seconds()))
        recent_str = self._format_relative_date(most_recent.timestamp)
        context += f". Most recent similar: {recent_str}"

        return context

    def _summarize_event_types(self, descriptions: list[str]) -> Optional[str]:
        """
        Summarize the types of events from descriptions.

        Args:
            descriptions: List of event descriptions

        Returns:
            Summary string like "mostly deliveries" or None
        """
        if not descriptions:
            return None

        # Count keywords
        keywords = {
            "delivery": ["delivery", "package", "parcel", "box", "dropped off"],
            "person": ["person", "someone", "visitor", "walked"],
            "vehicle": ["car", "vehicle", "truck", "drove"],
        }

        counts = {}
        for desc in descriptions:
            desc_lower = desc.lower()
            for category, words in keywords.items():
                if any(word in desc_lower for word in words):
                    counts[category] = counts.get(category, 0) + 1

        if counts:
            # Find most common type
            most_common = max(counts, key=counts.get)
            if counts[most_common] >= len(descriptions) * 0.5:  # 50%+ are this type
                return f"Mostly {most_common} events"

        return None

    async def _get_time_pattern_context(
        self,
        db: Session,
        camera_id: str,
        event_time: datetime,
        time_window_days: int,
    ) -> Optional[str]:
        """
        Get time-of-day pattern context for the camera using PatternService.

        Uses pre-calculated activity patterns to determine if the current
        event time is typical or unusual. This avoids expensive per-event
        queries and enables <50ms pattern lookups.

        Story P4-3.5: Pattern Detection (AC12) - Integrate with PatternService

        Args:
            db: SQLAlchemy database session
            camera_id: UUID of the camera
            event_time: Time of the current event
            time_window_days: Days of history to analyze (used by PatternService config)

        Returns:
            Context string describing timing pattern, or None if insufficient data
        """
        # Use PatternService for timing analysis (Story P4-3.5)
        timing_result = await self._pattern_service.is_typical_timing(
            db=db,
            camera_id=camera_id,
            timestamp=event_time,
        )

        # If insufficient history, return None (no timing context)
        if timing_result.is_typical is None:
            return None

        # Format timing context based on analysis result
        if timing_result.is_typical:
            # Typical activity time
            if timing_result.confidence >= 0.8:
                return f"Timing: {timing_result.reason}"
            else:
                # Lower confidence - still typical but don't emphasize
                return None
        else:
            # Unusual timing
            return f"Timing: {timing_result.reason}"

    def _format_relative_date(self, dt: datetime) -> str:
        """
        Format a datetime as a natural language relative date.

        Args:
            dt: Datetime to format

        Returns:
            Natural language string like "2 weeks ago" or "yesterday"
        """
        if dt is None:
            return "unknown"

        # Ensure timezone-aware comparison
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        delta = now - dt

        if delta.days == 0:
            if delta.seconds < 3600:
                return "just now"
            elif delta.seconds < 7200:
                return "1 hour ago"
            else:
                return f"{delta.seconds // 3600} hours ago"
        elif delta.days == 1:
            return "yesterday"
        elif delta.days < 7:
            return f"{delta.days} days ago"
        elif delta.days < 14:
            return "1 week ago"
        elif delta.days < 30:
            return f"{delta.days // 7} weeks ago"
        elif delta.days < 60:
            return "1 month ago"
        else:
            return f"{delta.days // 30} months ago"

    def _format_time_range(self, hour: int) -> str:
        """
        Format an hour as a natural time range.

        Args:
            hour: Hour of day (0-23)

        Returns:
            Natural language time range like "morning" or "evening"
        """
        if 5 <= hour < 9:
            return "early morning"
        elif 9 <= hour < 12:
            return "mid-morning"
        elif 12 <= hour < 14:
            return "around noon"
        elif 14 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 20:
            return "evening"
        elif 20 <= hour < 23:
            return "late evening"
        else:
            return "late night/early morning"

    def _is_context_enabled(self, db: Session) -> bool:
        """
        Check if context enhancement is enabled in settings.

        Args:
            db: SQLAlchemy database session

        Returns:
            True if enabled (default), False if explicitly disabled
        """
        from app.models.system_setting import SystemSetting

        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "enable_context_enhanced_prompts"
        ).first()

        if setting and setting.value.lower() in ("false", "0", "no", "disabled"):
            return False

        # Default: enabled
        return True

    def _get_ab_test_percentage(self, db: Session) -> int:
        """
        Get A/B test skip percentage from settings.

        Args:
            db: SQLAlchemy database session

        Returns:
            Percentage (0-100) of events to skip context for A/B testing.
            Default: 0 (disabled)
        """
        from app.models.system_setting import SystemSetting

        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "context_ab_test_percentage"
        ).first()

        if setting:
            try:
                value = int(setting.value)
                return max(0, min(100, value))  # Clamp to 0-100
            except ValueError:
                pass

        return 0  # Default: disabled

    def _get_similarity_threshold(self, db: Session) -> float:
        """
        Get similarity threshold from settings.

        Args:
            db: SQLAlchemy database session

        Returns:
            Similarity threshold (0.0-1.0). Default: 0.7
        """
        from app.models.system_setting import SystemSetting

        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "context_similarity_threshold"
        ).first()

        if setting:
            try:
                value = float(setting.value)
                return max(0.0, min(1.0, value))  # Clamp to 0.0-1.0
            except ValueError:
                pass

        return self.DEFAULT_SIMILARITY_THRESHOLD

    def _get_time_window_days(self, db: Session) -> int:
        """
        Get time window in days from settings.

        Args:
            db: SQLAlchemy database session

        Returns:
            Time window in days. Default: 30
        """
        from app.models.system_setting import SystemSetting

        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "context_time_window_days"
        ).first()

        if setting:
            try:
                value = int(setting.value)
                return max(1, min(365, value))  # Clamp to 1-365
            except ValueError:
                pass

        return self.DEFAULT_TIME_WINDOW_DAYS


# Backward compatible thin getter (delegates to @singleton decorator)
def get_context_prompt_service() -> ContextEnhancedPromptService:
    """
    Get the global ContextEnhancedPromptService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer ContextEnhancedPromptService() directly.
    """
    return ContextEnhancedPromptService()


def reset_context_prompt_service() -> None:
    """Reset the global ContextEnhancedPromptService instance (for testing)."""
    ContextEnhancedPromptService._reset_instance()

    if _context_prompt_service is None:
        _context_prompt_service = ContextEnhancedPromptService()
        logger.info(
            "Global ContextEnhancedPromptService instance created",
            extra={"event_type": "context_prompt_service_singleton_created"}
        )

    return _context_prompt_service


def reset_context_prompt_service() -> None:
    """Reset the global ContextEnhancedPromptService instance (for testing)."""
    ContextEnhancedPromptService._reset_instance()
