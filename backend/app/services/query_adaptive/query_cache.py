"""
Query Cache Service (Story P12-4.4)

In-memory cache for query-adaptive frame selection results with TTL.

Features:
    - 5-minute TTL by default (AC5)
    - Cache hits return in <5ms (AC4)
    - Automatic cleanup of expired entries
    - Thread-safe operations

Usage:
    cache = QueryCache(ttl_seconds=300)
    cached = cache.get(event_id, query)
    if cached:
        return cached.frame_indices, cached.relevance_scores
    # ... compute results ...
    cache.set(event_id, query, frame_indices, scores)
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CachedQueryResult:
    """
    Cached result from query-adaptive frame selection.

    Stores the selected frame indices and their scores for quick retrieval.

    Attributes:
        event_id: Event UUID
        query: Normalized query string
        frame_indices: Selected frame indices
        relevance_scores: Scores for selected frames (0-100)
        quality_scores: Quality scores for selected frames (0-100)
        combined_scores: Combined scores for selected frames (0-100)
        cached_at: When the result was cached
        ttl_seconds: Time-to-live in seconds (default: 300 = 5 minutes)
    """
    event_id: str
    query: str
    frame_indices: List[int]
    relevance_scores: List[float]
    quality_scores: List[float] = field(default_factory=list)
    combined_scores: List[float] = field(default_factory=list)
    cached_at: datetime = field(default_factory=lambda: datetime.utcnow())
    ttl_seconds: int = 300  # 5 minutes (AC5)

    @property
    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return datetime.utcnow() > self.cached_at + timedelta(seconds=self.ttl_seconds)

    @property
    def age_seconds(self) -> float:
        """Get the age of this cache entry in seconds."""
        return (datetime.utcnow() - self.cached_at).total_seconds()


class QueryCache:
    """
    In-memory cache for query results with TTL.

    Provides fast retrieval of query-adaptive frame selection results,
    reducing computation for repeated queries on the same event.

    Thread-safe implementation using locks for concurrent access.

    Attributes:
        DEFAULT_TTL_SECONDS: Default TTL (300 = 5 minutes)
        CLEANUP_INTERVAL: Cleanup expired entries every N operations
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes (AC5)
    CLEANUP_INTERVAL = 100  # Cleanup every 100 operations

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        """
        Initialize QueryCache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 300)
        """
        self._cache: Dict[str, CachedQueryResult] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds
        self._operation_count = 0

        logger.info(
            "QueryCache initialized",
            extra={
                "event_type": "query_cache_init",
                "ttl_seconds": ttl_seconds,
            }
        )

    def get(self, event_id: str, query: str) -> Optional[CachedQueryResult]:
        """
        Get cached result if not expired.

        Target: <5ms for cache hits (AC4)

        Args:
            event_id: Event UUID
            query: User query string

        Returns:
            CachedQueryResult if found and not expired, None otherwise
        """
        start_time = time.time()
        key = self._make_key(event_id, query)

        with self._lock:
            result = self._cache.get(key)

            if result and not result.is_expired:
                duration_ms = (time.time() - start_time) * 1000
                logger.debug(
                    f"Cache hit for event {event_id}",
                    extra={
                        "event_type": "query_cache_hit",
                        "event_id": event_id,
                        "query_length": len(query),
                        "cache_age_seconds": result.age_seconds,
                        "duration_ms": round(duration_ms, 2),
                    }
                )
                return result

            elif result:
                # Expired - remove it
                del self._cache[key]
                logger.debug(
                    f"Cache expired for event {event_id}",
                    extra={
                        "event_type": "query_cache_expired",
                        "event_id": event_id,
                        "age_seconds": result.age_seconds,
                    }
                )

        return None

    def set(
        self,
        event_id: str,
        query: str,
        frame_indices: List[int],
        relevance_scores: List[float],
        quality_scores: Optional[List[float]] = None,
        combined_scores: Optional[List[float]] = None,
    ) -> None:
        """
        Cache query result.

        Args:
            event_id: Event UUID
            query: User query string
            frame_indices: Selected frame indices
            relevance_scores: Relevance scores (0-100)
            quality_scores: Quality scores (0-100), optional
            combined_scores: Combined scores (0-100), optional
        """
        key = self._make_key(event_id, query)

        with self._lock:
            self._cache[key] = CachedQueryResult(
                event_id=event_id,
                query=self._normalize_query(query),
                frame_indices=frame_indices,
                relevance_scores=relevance_scores,
                quality_scores=quality_scores or [],
                combined_scores=combined_scores or [],
                cached_at=datetime.utcnow(),
                ttl_seconds=self.ttl_seconds,
            )

            self._operation_count += 1
            if self._operation_count >= self.CLEANUP_INTERVAL:
                self._cleanup_expired()
                self._operation_count = 0

        logger.debug(
            f"Cached result for event {event_id}",
            extra={
                "event_type": "query_cache_set",
                "event_id": event_id,
                "query_length": len(query),
                "frames_cached": len(frame_indices),
            }
        )

    def invalidate(self, event_id: str, query: Optional[str] = None) -> int:
        """
        Invalidate cache entries.

        Args:
            event_id: Event UUID
            query: If provided, only invalidate this specific query.
                  If None, invalidate all queries for the event.

        Returns:
            Number of entries invalidated
        """
        count = 0

        with self._lock:
            if query:
                # Invalidate specific query
                key = self._make_key(event_id, query)
                if key in self._cache:
                    del self._cache[key]
                    count = 1
            else:
                # Invalidate all queries for event
                keys_to_remove = [
                    k for k in self._cache.keys()
                    if k.startswith(f"{event_id}:")
                ]
                for key in keys_to_remove:
                    del self._cache[key]
                    count += 1

        if count > 0:
            logger.debug(
                f"Invalidated {count} cache entries for event {event_id}",
                extra={
                    "event_type": "query_cache_invalidate",
                    "event_id": event_id,
                    "entries_removed": count,
                }
            )

        return count

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()

        logger.info(
            f"Cleared {count} cache entries",
            extra={
                "event_type": "query_cache_clear",
                "entries_cleared": count,
            }
        )

        return count

    def size(self) -> int:
        """Get the current number of cache entries."""
        with self._lock:
            return len(self._cache)

    def stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats (size, oldest_entry_age, etc.)
        """
        with self._lock:
            if not self._cache:
                return {
                    "size": 0,
                    "oldest_age_seconds": 0,
                    "newest_age_seconds": 0,
                }

            ages = [r.age_seconds for r in self._cache.values()]
            return {
                "size": len(self._cache),
                "oldest_age_seconds": max(ages),
                "newest_age_seconds": min(ages),
                "average_age_seconds": sum(ages) / len(ages),
            }

    def _make_key(self, event_id: str, query: str) -> str:
        """Create cache key from event_id and normalized query."""
        return f"{event_id}:{self._normalize_query(query)}"

    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent cache lookup."""
        return query.lower().strip()

    def _cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.

        Called periodically during set operations.

        Returns:
            Number of entries removed
        """
        expired_keys = [
            key for key, result in self._cache.items()
            if result.is_expired
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(
                f"Cleaned up {len(expired_keys)} expired cache entries",
                extra={
                    "event_type": "query_cache_cleanup",
                    "entries_removed": len(expired_keys),
                }
            )

        return len(expired_keys)


# Global singleton instance
_query_cache: Optional[QueryCache] = None


def get_query_cache() -> QueryCache:
    """
    Get the global QueryCache instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        QueryCache singleton instance
    """
    global _query_cache

    if _query_cache is None:
        _query_cache = QueryCache()
        logger.info(
            "Global QueryCache instance created",
            extra={"event_type": "query_cache_singleton_created"}
        )

    return _query_cache


def reset_query_cache() -> None:
    """
    Reset the global QueryCache instance.

    Useful for testing to ensure a fresh instance.
    """
    global _query_cache
    _query_cache = None
