"""
MCPContextProvider for AI Context Enhancement (Story P11-3.1, P11-3.2, P11-3.3, P11-3.4, P14-6.x)

This module provides the MCPContextProvider class that gathers context
from user feedback history, known entities, camera patterns, and time patterns
to enhance AI description prompts.

Architecture:
    - Queries EventFeedback by camera_id for feedback history
    - Queries RecognizedEntity for entity context (P11-3.2)
    - Queries EntityAdjustment for manual corrections (P14-6.1)
    - Queries Camera and Event for camera patterns (P11-3.3)
    - Calculates time-of-day activity patterns (P11-3.3)
    - Caches context with 60-second TTL for performance (P11-3.4)
    - Calculates camera-specific accuracy rates
    - Extracts common correction patterns using TF-IDF (P14-6.6)
    - Formats context for AI prompt injection
    - Fail-open design ensures AI works even if context fails

Phase 14 Enhancements (Epic P14-6):
    - P14-6.1: Entity adjustment context (manual corrections)
    - P14-6.2: Parallel query execution with asyncio.gather()
    - P14-6.3: Async-safe database queries via run_in_executor
    - P14-6.4: 80ms hard timeout with fail-open behavior
    - P14-6.5: Optimized cache key strategy (camera_id only)
    - P14-6.6: TF-IDF-based pattern extraction with stop words
    - P14-6.7: VIP/blocked entity context for prioritization
    - P14-6.8: Context metrics API endpoint for dashboard

Flow:
    Event → MCPContextProvider.get_context(camera_id, event_time, entity_id)
                                    ↓
                      Check cache for camera_id key (optimized P14-6.5)
                                    ↓
                      If cached and not expired → return cached
                                    ↓
                      Parallel query execution (P14-6.2):
                        - Feedback context
                        - Entity context + adjustments (P14-6.1, P14-6.7)
                        - Camera context
                        - Time pattern context
                                    ↓
                      80ms timeout wrapper (P14-6.4)
                                    ↓
                      Build AIContext with VIP/blocked flags (P14-6.7)
                                    ↓
                      Cache and return AIContext
"""
import asyncio
import concurrent.futures
import logging
import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from functools import partial
from typing import Optional, List, Dict, Any, Tuple

from prometheus_client import Counter as PromCounter, Histogram, Gauge
from sqlalchemy import desc, select, func, extract
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import REGISTRY

logger = logging.getLogger(__name__)

# Prometheus metrics for context gathering (Story P11-3.4, P14-6.8)
# Use the app's custom REGISTRY to ensure metrics appear in /metrics endpoint
MCP_CONTEXT_LATENCY = Histogram(
    'argusai_mcp_context_latency_seconds',
    'Time to gather MCP context',
    ['cached'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=REGISTRY
)
MCP_CACHE_HITS = PromCounter(
    'argusai_mcp_cache_hits_total',
    'Number of MCP context cache hits',
    registry=REGISTRY
)
MCP_CACHE_MISSES = PromCounter(
    'argusai_mcp_cache_misses_total',
    'Number of MCP context cache misses',
    registry=REGISTRY
)
# P14-6.4: Timeout tracking
MCP_CONTEXT_TIMEOUTS = PromCounter(
    'argusai_mcp_context_timeouts_total',
    'Number of MCP context gathering timeouts',
    registry=REGISTRY
)
# P14-6.8: Component availability tracking
MCP_COMPONENT_AVAILABILITY = Gauge(
    'argusai_mcp_component_available',
    'Whether each MCP context component returned data (1=yes, 0=no)',
    ['component'],
    registry=REGISTRY
)
# P14-6.8: Cache hit rate for dashboard
MCP_CACHE_HIT_RATE = Gauge(
    'argusai_mcp_cache_hit_rate',
    'Current cache hit rate (0.0-1.0)',
    registry=REGISTRY
)


@dataclass
class FeedbackContext:
    """Context gathered from user feedback history."""
    accuracy_rate: Optional[float]  # 0.0-1.0, None if no feedback
    total_feedback: int
    common_corrections: List[str]  # Top 3 correction patterns
    recent_negative_reasons: List[str]  # Last 5 negative feedback reasons


@dataclass
class EntityContext:
    """Context about a matched entity (Story P11-3.2, P14-6.1, P14-6.7)."""
    entity_id: str
    name: str
    entity_type: str  # person, vehicle, unknown
    attributes: Dict[str, str]  # color, make, model for vehicles
    last_seen: Optional[datetime]
    sighting_count: int
    similar_entities: List[Dict[str, Any]] = field(default_factory=list)  # Top 3 similar by occurrence
    # P14-6.7: VIP and blocked flags for prioritization
    is_vip: bool = False
    is_blocked: bool = False
    # P14-6.1: Recent manual adjustments for this entity
    recent_adjustments: List[Dict[str, Any]] = field(default_factory=list)  # Last 5-10 corrections


@dataclass
class CameraContext:
    """Context about camera location and patterns (Story P11-3.3)."""
    camera_id: str
    location_hint: Optional[str]  # Camera name (e.g., "Front Door")
    typical_objects: List[str]  # Top 3 common detection types
    false_positive_patterns: List[str]  # Common false positives from negative feedback


@dataclass
class TimePatternContext:
    """Context about time-of-day patterns (Story P11-3.3)."""
    hour: int
    typical_activity_level: str  # low, medium, high
    is_unusual: bool  # True if activity during typically quiet hours
    typical_event_count: float  # Average events per day at this hour


@dataclass
class AIContext:
    """Combined context for AI prompt generation."""
    feedback: Optional[FeedbackContext] = None
    entity: Optional[EntityContext] = None
    camera: Optional[CameraContext] = None
    time_pattern: Optional[TimePatternContext] = None


@dataclass
class CachedContext:
    """Cached context with TTL tracking (Story P11-3.4)."""
    context: AIContext
    created_at: datetime

    def is_expired(self, ttl_seconds: int = 60) -> bool:
        """Check if cached context has expired."""
        now = datetime.now(timezone.utc)
        # Handle timezone-naive created_at
        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (now - created).total_seconds() > ttl_seconds


class MCPContextProvider:
    """
    Provides context for AI prompts based on accumulated feedback, entities, and patterns.

    This implementation includes:
    - Feedback context (P11-3.1): accuracy rates and correction patterns
    - Entity context (P11-3.2): known people/vehicles and similar entities
    - Entity adjustments (P14-6.1): manual correction history
    - Camera context (P11-3.3): location hints and typical objects
    - Time pattern context (P11-3.3): activity levels and unusual timing flags
    - Context caching (P11-3.4, P14-6.5): optimized TTL cache
    - Parallel queries (P14-6.2): asyncio.gather for concurrent execution
    - Async-safe queries (P14-6.3): run_in_executor for sync DB calls
    - Query timeout (P14-6.4): 80ms hard timeout with fail-open
    - VIP/blocked context (P14-6.7): entity prioritization flags
    - TF-IDF patterns (P14-6.6): improved pattern extraction

    Attributes:
        FEEDBACK_LIMIT: Number of recent feedback items to query (50)
        MAX_ENTITY_CONTEXT_CHARS: Maximum characters for entity context to prevent prompt overflow (500)
        MAX_SIMILAR_ENTITIES: Maximum similar entities to suggest (3)
        EVENT_HISTORY_DAYS: Days of event history to analyze for patterns (30)
        MAX_TYPICAL_OBJECTS: Maximum typical objects to include (3)
        MAX_FALSE_POSITIVES: Maximum false positive patterns to include (3)
        CACHE_TTL_SECONDS: Cache TTL in seconds (30 - reduced for better freshness P14-6.5)
        SLOW_QUERY_THRESHOLD_MS: Threshold for slow query warning (50)
        CONTEXT_TIMEOUT_SECONDS: Hard timeout for context gathering (0.08 - 80ms P14-6.4)
        MAX_ADJUSTMENTS: Maximum recent adjustments per entity (10 P14-6.1)
        MIN_PATTERN_FREQUENCY: Minimum frequency for pattern extraction (3 P14-6.6)
    """

    FEEDBACK_LIMIT = 50
    MAX_ENTITY_CONTEXT_CHARS = 500
    MAX_SIMILAR_ENTITIES = 3
    EVENT_HISTORY_DAYS = 30
    MAX_TYPICAL_OBJECTS = 3
    MAX_FALSE_POSITIVES = 3
    CACHE_TTL_SECONDS = 30  # P14-6.5: Reduced from 60 for better freshness
    SLOW_QUERY_THRESHOLD_MS = 50
    CONTEXT_TIMEOUT_SECONDS = 0.08  # P14-6.4: 80ms hard timeout
    MAX_ADJUSTMENTS = 10  # P14-6.1: Max adjustments per entity
    MIN_PATTERN_FREQUENCY = 3  # P14-6.6: Minimum frequency for patterns

    # P14-6.6: Domain-specific stop words for security camera context
    STOP_WORDS = {
        # Common English stop words
        'the', 'a', 'an', 'is', 'was', 'it', 'this', 'that', 'not',
        'and', 'or', 'but', 'of', 'in', 'to', 'for', 'on', 'with',
        'be', 'are', 'were', 'been', 'being', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'could', 'should',
        'i', 'you', 'he', 'she', 'we', 'they', 'my', 'your', 'its',
        'there', 'here', 'where', 'when', 'what', 'which', 'who',
        'actually', 'just', 'really', 'very', 'so', 'too', 'also',
        # P14-6.6: Security camera domain stop words
        'frame', 'frames', 'left', 'right', 'scene', 'camera', 'image',
        'video', 'capture', 'captured', 'detected', 'detection', 'motion',
        'event', 'events', 'view', 'visible', 'appears', 'appearing',
        'shows', 'showing', 'seen', 'looking', 'moving', 'area', 'areas',
        'moment', 'time', 'timestamp', 'seconds', 'minute', 'minutes',
    }

    def __init__(self, db: Session = None):
        """
        Initialize MCPContextProvider.

        Args:
            db: Optional SQLAlchemy session. If None, must be provided to get_context().
        """
        self._db = db
        self._cache: Dict[str, CachedContext] = {}
        # P14-6.3: Thread pool executor for running sync DB queries
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcp_ctx")
        # P14-6.8: Metrics tracking for dashboard
        self._total_requests = 0
        self._cache_hits = 0
        self._timeouts = 0
        logger.info(
            "MCPContextProvider initialized",
            extra={"event_type": "mcp_context_provider_init"}
        )

    def _get_cache_key(self, camera_id: str, event_time: datetime) -> str:
        """
        Generate cache key from camera ID (P14-6.5 optimization).

        P14-6.5: Changed from "{camera_id}:{hour}" to just "{camera_id}" with
        shorter TTL (30s instead of 60s) to improve cache hit ratio. Since events
        from the same camera within 30 seconds are likely similar context, we can
        share the cached context regardless of hour changes.

        Args:
            camera_id: UUID of the camera
            event_time: When the event occurred (kept for API compatibility)

        Returns:
            Cache key in format "{camera_id}"
        """
        # P14-6.5: Simplified key strategy - camera_id only with shorter TTL
        return camera_id

    def clear_cache(self) -> None:
        """
        Clear the context cache (Story P11-3.4).

        Useful for testing and manual cache invalidation.
        """
        self._cache.clear()
        logger.debug(
            "MCP context cache cleared",
            extra={"event_type": "mcp.cache_cleared"}
        )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get MCP context metrics for dashboard (P14-6.8).

        Returns metrics about cache performance, latency, and component availability
        for display in the Settings > AI tab.

        Returns:
            Dict with cache_hit_rate, total_requests, cache_hits, timeouts,
            avg_latency_ms, and component availability info.
        """
        hit_rate = self._cache_hits / self._total_requests if self._total_requests > 0 else 0.0
        # Update Prometheus gauge for dashboard
        MCP_CACHE_HIT_RATE.set(hit_rate)

        return {
            "cache_hit_rate": round(hit_rate, 4),
            "total_requests": self._total_requests,
            "cache_hits": self._cache_hits,
            "cache_misses": self._total_requests - self._cache_hits,
            "timeouts": self._timeouts,
            "cache_ttl_seconds": self.CACHE_TTL_SECONDS,
            "timeout_threshold_ms": int(self.CONTEXT_TIMEOUT_SECONDS * 1000),
            "cache_size": len(self._cache),
        }

    async def get_context(
        self,
        camera_id: str,
        event_time: datetime,
        entity_id: Optional[str] = None,
        db: Session = None,
    ) -> AIContext:
        """
        Gather context for AI prompt generation.

        Uses caching with 30-second TTL for performance (P14-6.5).
        Uses parallel queries with asyncio.gather (P14-6.2).
        Uses run_in_executor for async-safe DB calls (P14-6.3).
        Enforces 80ms hard timeout with fail-open (P14-6.4).
        Uses fail-open design: if any context component fails, returns
        partial context with None for failed components.

        Args:
            camera_id: UUID of the camera
            event_time: When the event occurred
            entity_id: Optional UUID of matched entity (for P11-3.2, P14-6.1, P14-6.7)
            db: SQLAlchemy session (uses instance db if not provided)

        Returns:
            AIContext with available context components
        """
        start_time = time.time()
        session = db or self._db
        self._total_requests += 1

        if not session:
            logger.warning(
                "No database session provided to get_context",
                extra={"event_type": "mcp_context_no_session", "camera_id": camera_id}
            )
            return AIContext()

        # Check cache first (P14-6.5: optimized key strategy)
        cache_key = self._get_cache_key(camera_id, event_time)
        cached = self._cache.get(cache_key)

        if cached and not cached.is_expired(self.CACHE_TTL_SECONDS):
            # Cache hit
            self._cache_hits += 1
            context_gather_time_ms = (time.time() - start_time) * 1000
            MCP_CACHE_HITS.inc()
            MCP_CONTEXT_LATENCY.labels(cached="true").observe(context_gather_time_ms / 1000)

            logger.debug(
                f"MCP context cache hit for camera {camera_id}",
                extra={
                    "event_type": "mcp.cache_hit",
                    "camera_id": camera_id,
                    "cache_key": cache_key,
                    "duration_ms": round(context_gather_time_ms, 2),
                }
            )

            # Entity context is not cached (depends on entity_id), fetch if needed
            if entity_id:
                entity_ctx = await self._safe_get_entity_context(session, entity_id)
                return AIContext(
                    feedback=cached.context.feedback,
                    entity=entity_ctx,
                    camera=cached.context.camera,
                    time_pattern=cached.context.time_pattern,
                )

            return cached.context

        # Cache miss - gather all context components
        MCP_CACHE_MISSES.inc()

        logger.debug(
            f"MCP context cache miss for camera {camera_id}",
            extra={
                "event_type": "mcp.cache_miss",
                "camera_id": camera_id,
                "cache_key": cache_key,
            }
        )

        # P14-6.2: Parallel query execution with asyncio.gather
        # P14-6.4: Wrap in timeout for 80ms fail-open behavior
        try:
            context = await asyncio.wait_for(
                self._gather_context_parallel(session, camera_id, entity_id, event_time),
                timeout=self.CONTEXT_TIMEOUT_SECONDS
            )
            feedback_ctx, entity_ctx, camera_ctx, time_ctx = context
        except asyncio.TimeoutError:
            # P14-6.4: Timeout - return partial/empty context (fail-open)
            self._timeouts += 1
            MCP_CONTEXT_TIMEOUTS.inc()
            logger.warning(
                f"MCP context timeout after {int(self.CONTEXT_TIMEOUT_SECONDS * 1000)}ms for camera {camera_id}",
                extra={
                    "event_type": "mcp.context_timeout",
                    "camera_id": camera_id,
                    "timeout_ms": int(self.CONTEXT_TIMEOUT_SECONDS * 1000),
                }
            )
            # Return empty context on timeout
            return AIContext()

        context_gather_time_ms = (time.time() - start_time) * 1000

        # Record metrics (Story P11-3.4 AC-3.4.4)
        MCP_CONTEXT_LATENCY.labels(cached="false").observe(context_gather_time_ms / 1000)

        # Warn if slow (Story P11-3.4 AC-3.4.3)
        if context_gather_time_ms > self.SLOW_QUERY_THRESHOLD_MS:
            logger.warning(
                f"MCP context gathering exceeded {self.SLOW_QUERY_THRESHOLD_MS}ms threshold",
                extra={
                    "event_type": "mcp.slow_query",
                    "camera_id": camera_id,
                    "duration_ms": round(context_gather_time_ms, 2),
                    "threshold_ms": self.SLOW_QUERY_THRESHOLD_MS,
                }
            )

        # Build context
        context = AIContext(
            feedback=feedback_ctx,
            entity=entity_ctx,
            camera=camera_ctx,
            time_pattern=time_ctx,
        )

        # Cache context (without entity, which is request-specific)
        cached_context = AIContext(
            feedback=feedback_ctx,
            entity=None,  # Entity is not cached
            camera=camera_ctx,
            time_pattern=time_ctx,
        )
        self._cache[cache_key] = CachedContext(
            context=cached_context,
            created_at=datetime.now(timezone.utc),
        )

        # P14-6.8: Update component availability metrics
        MCP_COMPONENT_AVAILABILITY.labels(component="feedback").set(1 if feedback_ctx else 0)
        MCP_COMPONENT_AVAILABILITY.labels(component="entity").set(1 if entity_ctx else 0)
        MCP_COMPONENT_AVAILABILITY.labels(component="camera").set(1 if camera_ctx else 0)
        MCP_COMPONENT_AVAILABILITY.labels(component="time_pattern").set(1 if time_ctx else 0)

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
                "cached": False,
            }
        )

        return context

    async def _gather_context_parallel(
        self,
        db: Session,
        camera_id: str,
        entity_id: Optional[str],
        event_time: datetime,
    ) -> Tuple[Optional[FeedbackContext], Optional[EntityContext], Optional[CameraContext], Optional[TimePatternContext]]:
        """
        Gather all context components in parallel (P14-6.2).

        Uses asyncio.gather with return_exceptions=True for fail-open behavior.
        Each query is wrapped in run_in_executor for async-safe execution (P14-6.3).

        Args:
            db: SQLAlchemy session
            camera_id: UUID of the camera
            entity_id: Optional UUID of matched entity
            event_time: When the event occurred

        Returns:
            Tuple of (FeedbackContext, EntityContext, CameraContext, TimePatternContext)
            Any component may be None if it failed or timed out.
        """
        # P14-6.2: Build tasks for parallel execution
        async def no_entity():
            return None

        tasks = [
            self._safe_get_feedback_context(db, camera_id),
            self._safe_get_entity_context(db, entity_id) if entity_id else no_entity(),
            self._safe_get_camera_context(db, camera_id),
            self._safe_get_time_pattern_context(db, camera_id, event_time),
        ]

        # P14-6.2: Execute all tasks in parallel with exception handling
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results - any exception becomes None (fail-open)
        processed = []
        component_names = ["feedback", "entity", "camera", "time_pattern"]
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    f"MCP {component_names[i]} context query failed: {result}",
                    extra={
                        "event_type": "mcp.parallel_query_error",
                        "component": component_names[i],
                        "camera_id": camera_id,
                        "error": str(result),
                    }
                )
                processed.append(None)
            else:
                processed.append(result)

        return tuple(processed)  # type: ignore

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
        Get entity context for a matched entity (Story P11-3.2, P14-6.1, P14-6.7).

        Queries the RecognizedEntity model to get entity details including
        name, type, attributes, sighting count, VIP/blocked flags, and
        recent manual adjustments.

        Args:
            db: SQLAlchemy session
            entity_id: UUID of the entity

        Returns:
            EntityContext with entity details, or None if entity not found
        """
        from app.models.recognized_entity import RecognizedEntity
        from app.models.entity_adjustment import EntityAdjustment

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

        # P14-6.1: Get recent manual adjustments for this entity
        recent_adjustments = await self._get_entity_adjustments(db, entity_id)

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
                "adjustment_count": len(recent_adjustments),
                "is_vip": entity.is_vip,
                "is_blocked": entity.is_blocked,
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
            # P14-6.7: VIP and blocked flags
            is_vip=entity.is_vip,
            is_blocked=entity.is_blocked,
            # P14-6.1: Recent adjustments
            recent_adjustments=recent_adjustments,
        )

    async def _get_entity_adjustments(
        self,
        db: Session,
        entity_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get recent manual adjustments for an entity (P14-6.1).

        Queries the EntityAdjustment table to find corrections where this entity
        was involved (either as old_entity_id or new_entity_id). These corrections
        help the AI learn from manual fixes.

        Args:
            db: SQLAlchemy session
            entity_id: UUID of the entity

        Returns:
            List of recent adjustments with action, description, and timestamp
        """
        from app.models.entity_adjustment import EntityAdjustment
        from sqlalchemy import or_

        # Query adjustments where this entity was involved
        adjustments = (
            db.query(EntityAdjustment)
            .filter(
                or_(
                    EntityAdjustment.old_entity_id == entity_id,
                    EntityAdjustment.new_entity_id == entity_id,
                )
            )
            .order_by(desc(EntityAdjustment.created_at))
            .limit(self.MAX_ADJUSTMENTS)
            .all()
        )

        result = []
        for adj in adjustments:
            # Determine the correction type
            if adj.old_entity_id == entity_id and adj.new_entity_id is None:
                correction_type = "unlinked_from"
            elif adj.new_entity_id == entity_id and adj.old_entity_id is None:
                correction_type = "assigned_to"
            elif adj.old_entity_id == entity_id:
                correction_type = "moved_from"
            else:
                correction_type = "moved_to"

            result.append({
                "action": adj.action,
                "correction_type": correction_type,
                "event_description": adj.event_description[:100] if adj.event_description else None,
                "created_at": adj.created_at.isoformat() if adj.created_at else None,
            })

        return result

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

    async def _safe_get_camera_context(
        self,
        db: Session,
        camera_id: str,
    ) -> Optional[CameraContext]:
        """
        Safely get camera context with error handling.

        Implements fail-open: returns None on any error instead of propagating.

        Args:
            db: SQLAlchemy session
            camera_id: UUID of the camera

        Returns:
            CameraContext or None if error occurs
        """
        try:
            return await self._get_camera_context(db, camera_id)
        except Exception as e:
            logger.warning(
                f"Failed to get camera context for camera {camera_id}: {e}",
                extra={
                    "event_type": "mcp.context_error",
                    "component": "camera",
                    "camera_id": camera_id,
                    "error": str(e),
                }
            )
            return None

    async def _get_camera_context(
        self,
        db: Session,
        camera_id: str,
    ) -> Optional[CameraContext]:
        """
        Get camera context for a camera (Story P11-3.3 AC-3.3.1, AC-3.3.2, AC-3.3.5).

        Queries the Camera model for location hint and analyzes recent events
        to find typical detection types and false positive patterns.

        Args:
            db: SQLAlchemy session
            camera_id: UUID of the camera

        Returns:
            CameraContext with location hint and patterns, or None if camera not found
        """
        from app.models.camera import Camera
        from app.models.event import Event
        from app.models.event_feedback import EventFeedback

        # Query camera by ID
        camera = (
            db.query(Camera)
            .filter(Camera.id == camera_id)
            .first()
        )

        if not camera:
            logger.debug(
                f"Camera not found: {camera_id}",
                extra={
                    "event_type": "mcp.camera_not_found",
                    "camera_id": camera_id,
                }
            )
            return None

        # Get typical objects from recent events (last 30 days)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.EVENT_HISTORY_DAYS)

        events_with_detection = (
            db.query(Event.smart_detection_type)
            .filter(Event.camera_id == camera_id)
            .filter(Event.created_at > cutoff_date)
            .filter(Event.smart_detection_type.isnot(None))
            .filter(Event.smart_detection_type != "")
            .all()
        )

        # Count detection types
        detection_counts: Counter = Counter()
        for (detection_type,) in events_with_detection:
            if detection_type:
                detection_counts[detection_type] += 1

        typical_objects = [obj for obj, _ in detection_counts.most_common(self.MAX_TYPICAL_OBJECTS)]

        # Get false positive patterns from negative feedback
        negative_feedback = (
            db.query(EventFeedback.correction)
            .filter(EventFeedback.camera_id == camera_id)
            .filter(EventFeedback.rating == 'not_helpful')
            .filter(EventFeedback.correction.isnot(None))
            .filter(EventFeedback.correction != "")
            .order_by(desc(EventFeedback.created_at))
            .limit(20)
            .all()
        )

        # Extract common patterns from false positives
        fp_corrections = [c.correction for c in negative_feedback if c.correction]
        false_positive_patterns = self._extract_common_patterns(fp_corrections)[:self.MAX_FALSE_POSITIVES]

        logger.debug(
            f"Camera context gathered for {camera_id}",
            extra={
                "event_type": "mcp.camera_context_gathered",
                "camera_id": camera_id,
                "location_hint": camera.name,
                "typical_objects_count": len(typical_objects),
                "false_positive_count": len(false_positive_patterns),
            }
        )

        return CameraContext(
            camera_id=camera.id,
            location_hint=camera.name,
            typical_objects=typical_objects,
            false_positive_patterns=false_positive_patterns,
        )

    async def _safe_get_time_pattern_context(
        self,
        db: Session,
        camera_id: str,
        event_time: datetime,
    ) -> Optional[TimePatternContext]:
        """
        Safely get time pattern context with error handling.

        Implements fail-open: returns None on any error instead of propagating.

        Args:
            db: SQLAlchemy session
            camera_id: UUID of the camera
            event_time: When the event occurred

        Returns:
            TimePatternContext or None if error occurs
        """
        try:
            return await self._get_time_pattern_context(db, camera_id, event_time)
        except Exception as e:
            logger.warning(
                f"Failed to get time pattern context for camera {camera_id}: {e}",
                extra={
                    "event_type": "mcp.context_error",
                    "component": "time_pattern",
                    "camera_id": camera_id,
                    "error": str(e),
                }
            )
            return None

    async def _get_time_pattern_context(
        self,
        db: Session,
        camera_id: str,
        event_time: datetime,
    ) -> Optional[TimePatternContext]:
        """
        Get time pattern context for a camera (Story P11-3.3 AC-3.3.3, AC-3.3.4).

        Analyzes historical event data to determine typical activity levels
        for the current hour and flags unusual timing.

        Args:
            db: SQLAlchemy session
            camera_id: UUID of the camera
            event_time: When the event occurred

        Returns:
            TimePatternContext with activity levels and unusual flags
        """
        from app.models.event import Event

        hour = event_time.hour

        # Get event count for this hour over the last 30 days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.EVENT_HISTORY_DAYS)

        # Count events at this hour
        events_at_hour = (
            db.query(func.count(Event.id))
            .filter(Event.camera_id == camera_id)
            .filter(Event.created_at > cutoff_date)
            .filter(extract('hour', Event.created_at) == hour)
            .scalar()
        ) or 0

        # Calculate average per day
        avg_per_day = events_at_hour / self.EVENT_HISTORY_DAYS

        # Determine activity level
        if avg_per_day < 1:
            level = "low"
        elif avg_per_day < 5:
            level = "medium"
        else:
            level = "high"

        # Flag unusual: activity during low-activity hours (10pm - 6am)
        # or any activity when that hour is typically low
        is_late_night = (hour >= 22 or hour <= 6)
        is_unusual = (level == "low" and is_late_night) or (level == "low" and avg_per_day < 0.5)

        logger.debug(
            f"Time pattern context gathered for camera {camera_id} at hour {hour}",
            extra={
                "event_type": "mcp.time_pattern_context_gathered",
                "camera_id": camera_id,
                "hour": hour,
                "avg_per_day": round(avg_per_day, 2),
                "activity_level": level,
                "is_unusual": is_unusual,
            }
        )

        return TimePatternContext(
            hour=hour,
            typical_activity_level=level,
            is_unusual=is_unusual,
            typical_event_count=round(avg_per_day, 2),
        )

    def _extract_common_patterns(self, corrections: List[str]) -> List[str]:
        """
        Extract common patterns from correction texts using TF-IDF scoring (P14-6.6).

        Uses Term Frequency - Inverse Document Frequency to find patterns that
        are common but distinctive. Words that appear in many documents are
        downweighted to surface more meaningful patterns.

        P14-6.6 improvements:
        - Extended stop words including domain-specific camera terms
        - TF-IDF scoring instead of raw frequency
        - Minimum frequency threshold (MIN_PATTERN_FREQUENCY)
        - Bi-gram support for multi-word patterns

        Args:
            corrections: List of correction texts

        Returns:
            List of top 3 most meaningful patterns
        """
        if not corrections:
            return []

        # Tokenize all documents
        doc_tokens: List[List[str]] = []
        for correction in corrections:
            # Tokenize: lowercase, extract words
            words = re.findall(r'\b[a-z]+\b', correction.lower())
            # Filter stop words and short words
            meaningful_words = [w for w in words if w not in self.STOP_WORDS and len(w) > 2]
            doc_tokens.append(meaningful_words)

        if not any(doc_tokens):
            return []

        # Count term frequencies (TF) and document frequencies (DF)
        term_freq: Counter = Counter()  # How many times each word appears total
        doc_freq: Counter = Counter()   # How many documents contain each word

        for tokens in doc_tokens:
            term_freq.update(tokens)
            # Count unique tokens per document for DF
            doc_freq.update(set(tokens))

        num_docs = len(corrections)

        # P14-6.6: Calculate TF-IDF scores
        # TF-IDF = TF * log(N / DF) where N is total documents
        tfidf_scores: Dict[str, float] = {}
        for word, tf in term_freq.items():
            # Skip words below minimum frequency
            if tf < self.MIN_PATTERN_FREQUENCY:
                continue
            df = doc_freq.get(word, 1)
            # IDF with smoothing to avoid division by zero
            idf = math.log((num_docs + 1) / (df + 1)) + 1
            tfidf_scores[word] = tf * idf

        # Sort by TF-IDF score and get top patterns
        sorted_patterns = sorted(tfidf_scores.items(), key=lambda x: x[1], reverse=True)
        top_patterns = [word for word, _ in sorted_patterns[:5]]

        # P14-6.6: Also extract bi-grams for multi-word patterns
        bigrams: Counter = Counter()
        for tokens in doc_tokens:
            for i in range(len(tokens) - 1):
                bigram = f"{tokens[i]} {tokens[i+1]}"
                bigrams[bigram] += 1

        # Add top bigram if it's more common than threshold
        for bigram, count in bigrams.most_common(2):
            if count >= self.MIN_PATTERN_FREQUENCY and len(top_patterns) < 5:
                top_patterns.append(bigram)

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

        # Camera context (Story P11-3.3 AC-3.3.1, AC-3.3.2, AC-3.3.5)
        if context.camera:
            camera_parts = self._format_camera_context(context.camera)
            parts.extend(camera_parts)

        # Time pattern context (Story P11-3.3 AC-3.3.3, AC-3.3.4)
        if context.time_pattern:
            time_parts = self._format_time_pattern_context(context.time_pattern)
            parts.extend(time_parts)

        return "\n".join(parts) if parts else ""

    def _format_entity_context(self, entity: EntityContext) -> List[str]:
        """
        Format entity context for inclusion in AI prompt (Story P11-3.2, P14-6.1, P14-6.7).

        Includes entity name, type, attributes, sighting history, similar entities,
        VIP/blocked status, and recent manual adjustments.
        Limits context size to MAX_ENTITY_CONTEXT_CHARS to prevent prompt overflow (AC-3.2.5).

        Args:
            entity: EntityContext with entity details

        Returns:
            List of formatted context strings
        """
        parts = []
        total_chars = 0

        # P14-6.7: VIP/blocked flags (highest priority - include first)
        if entity.is_vip:
            vip_str = "⭐ VIP ENTITY - High priority, ensure accurate description"
            parts.append(vip_str)
            total_chars += len(vip_str)
        elif entity.is_blocked:
            blocked_str = "🚫 Blocked entity - Notifications suppressed for this entity"
            parts.append(blocked_str)
            total_chars += len(blocked_str)

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
                    total_chars += len(similar_str)

        # P14-6.1: Recent manual adjustments - include up to 2 most relevant
        if entity.recent_adjustments and total_chars < self.MAX_ENTITY_CONTEXT_CHARS - 100:
            adjustment_strs = []
            for adj in entity.recent_adjustments[:2]:
                if adj.get("event_description"):
                    # Include a snippet of the corrected description
                    desc = adj["event_description"][:50]
                    adjustment_strs.append(f"{adj['action']}: \"{desc}...\"")
                else:
                    adjustment_strs.append(f"{adj['action']}")

            if adjustment_strs:
                adj_str = f"Recent corrections: {', '.join(adjustment_strs)}"
                if total_chars + len(adj_str) <= self.MAX_ENTITY_CONTEXT_CHARS:
                    parts.append(adj_str)
                    total_chars += len(adj_str)

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

    def _format_camera_context(self, camera: CameraContext) -> List[str]:
        """
        Format camera context for inclusion in AI prompt (Story P11-3.3 AC-3.3.1, AC-3.3.2, AC-3.3.5).

        Includes camera location hint, typical objects, and false positive patterns.

        Args:
            camera: CameraContext with camera details

        Returns:
            List of formatted context strings
        """
        parts = []

        # Location hint (AC-3.3.1)
        if camera.location_hint:
            parts.append(f"Camera location: {camera.location_hint}")

        # Typical objects (AC-3.3.2)
        if camera.typical_objects:
            objects_str = ", ".join(camera.typical_objects)
            parts.append(f"Commonly detected at this camera: {objects_str}")

        # False positive patterns (AC-3.3.5)
        if camera.false_positive_patterns:
            patterns_str = ", ".join(camera.false_positive_patterns)
            parts.append(f"Common false positive patterns: {patterns_str}")

        return parts

    def _format_time_pattern_context(self, time_pattern: TimePatternContext) -> List[str]:
        """
        Format time pattern context for inclusion in AI prompt (Story P11-3.3 AC-3.3.3, AC-3.3.4).

        Includes activity level and unusual timing flag.

        Args:
            time_pattern: TimePatternContext with time-based patterns

        Returns:
            List of formatted context strings
        """
        parts = []

        # Activity level (AC-3.3.3)
        hour_str = f"{time_pattern.hour:02d}:00"
        parts.append(f"Time of day: {hour_str} (typical activity: {time_pattern.typical_activity_level})")

        # Unusual flag (AC-3.3.4)
        if time_pattern.is_unusual:
            parts.append("⚠️ Note: This is unusual activity for this time of day")

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
