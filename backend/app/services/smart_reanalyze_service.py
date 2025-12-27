"""
Smart Reanalyze Service for Query-Adaptive Frame Selection (Story P11-4.3, P12-4)

This module provides query-adaptive re-analysis functionality. When users ask
targeted questions about events (e.g., "Was there a package delivery?"), this
service selects the most relevant frames based on semantic similarity to the
query before sending them to AI for analysis.

Architecture:
    - Text queries encoded via EmbeddingService.encode_text()
    - Frame embeddings scored via batch_cosine_similarity()
    - Top-K relevant frames selected for AI analysis
    - Query context passed to AI for focused analysis
    - Query caching with 5-minute TTL (Story P12-4.4)

Flow:
    User Query → format_query() → Check Cache
                                       ↓
                        encode_text() → Query Embedding
                                       ↓
              get_frame_embeddings() → Frame Embeddings
                                       ↓
                  batch_cosine_similarity() → Scores
                                       ↓
              DiversityFilter → select_top_k() → Selected Frames
                                       ↓
                  Cache Result → AI Analysis → New Description
"""
import logging
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.similarity_service import batch_cosine_similarity

logger = logging.getLogger(__name__)


@dataclass
class ScoredFrame:
    """Data class representing a scored frame."""
    frame_index: int
    similarity_score: float
    embedding_id: str
    quality_score: float = 50.0  # Default quality score
    combined_score: float = 0.0  # Calculated from similarity and quality


@dataclass
class SmartReanalyzeResult:
    """Data class representing the result of smart reanalysis."""
    selected_frames: list[int]  # Indices of selected frames
    frame_scores: list[ScoredFrame]  # All frame scores
    query_embedding_time_ms: float
    frame_scoring_time_ms: float
    formatted_query: str = ""  # Query after auto-formatting
    cached: bool = False  # Whether result was from cache


class SmartReanalyzeService:
    """
    Query-adaptive frame selection for event re-analysis.

    This service enables users to ask targeted questions about events
    and get focused AI analysis based on the most relevant frames.

    Attributes:
        DEFAULT_TOP_K: Default number of frames to select (5)
        DEFAULT_MIN_SIMILARITY: Default minimum similarity threshold (0.2)
        RELEVANCE_WEIGHT: Weight for relevance in combined scoring (0.7)
        QUALITY_WEIGHT: Weight for quality in combined scoring (0.3)
    """

    DEFAULT_TOP_K = 5
    DEFAULT_MIN_SIMILARITY = 0.2
    DIVERSITY_THRESHOLD = 0.92  # Skip near-duplicate frames (AC2)
    RELEVANCE_WEIGHT = 0.7  # AC3
    QUALITY_WEIGHT = 0.3  # AC3

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        query_cache: Optional["QueryCache"] = None,
    ):
        """
        Initialize SmartReanalyzeService.

        Args:
            embedding_service: EmbeddingService instance for encoding.
                             If None, will use the global singleton.
            query_cache: QueryCache instance for caching results.
                        If None, will use the global singleton.
        """
        self._embedding_service = embedding_service or get_embedding_service()
        self._query_cache = query_cache
        logger.info(
            "SmartReanalyzeService initialized",
            extra={"event_type": "smart_reanalyze_service_init"}
        )

    @property
    def query_cache(self):
        """Get the query cache instance (lazy loaded)."""
        if self._query_cache is None:
            from app.services.query_adaptive.query_cache import get_query_cache
            self._query_cache = get_query_cache()
        return self._query_cache

    async def select_relevant_frames(
        self,
        db: Session,
        event_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        use_cache: bool = True,
    ) -> SmartReanalyzeResult:
        """
        Select the most relevant frames for a query.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event to analyze
            query: User's natural language query
            top_k: Maximum number of frames to select
            min_similarity: Minimum similarity threshold
            use_cache: Whether to use cached results (default: True)

        Returns:
            SmartReanalyzeResult with selected frame indices and scores

        Raises:
            ValueError: If no frame embeddings exist for the event
        """
        from app.services.query_adaptive.query_suggester import QuerySuggester

        start_time = time.time()

        # Step 0: Format query for CLIP (AC6)
        formatted_query = QuerySuggester.format_query(query)

        # Step 1: Check cache (AC4 - cache hits in <5ms)
        if use_cache:
            cached_result = self.query_cache.get(event_id, query)
            if cached_result:
                # Build result from cache
                logger.debug(
                    f"Cache hit for event {event_id}",
                    extra={
                        "event_type": "smart_reanalyze_cache_hit",
                        "event_id": event_id,
                        "query": query,
                    }
                )
                return SmartReanalyzeResult(
                    selected_frames=cached_result.frame_indices,
                    frame_scores=[
                        ScoredFrame(
                            frame_index=cached_result.frame_indices[i],
                            similarity_score=cached_result.relevance_scores[i] if i < len(cached_result.relevance_scores) else 0,
                            embedding_id="",
                            quality_score=cached_result.quality_scores[i] if i < len(cached_result.quality_scores) else 50.0,
                            combined_score=cached_result.combined_scores[i] if i < len(cached_result.combined_scores) else 0,
                        )
                        for i in range(len(cached_result.frame_indices))
                    ],
                    query_embedding_time_ms=0,
                    frame_scoring_time_ms=0,
                    formatted_query=formatted_query,
                    cached=True,
                )

        # Step 2: Encode the query
        query_start = time.time()
        query_embedding = await self._embedding_service.encode_text(formatted_query)
        query_time_ms = (time.time() - query_start) * 1000

        # Step 3: Get frame embeddings for the event
        frame_embeddings = await self._embedding_service.get_frame_embeddings(
            db, event_id
        )

        if not frame_embeddings:
            logger.warning(
                f"No frame embeddings found for event {event_id}",
                extra={
                    "event_type": "smart_reanalyze_no_embeddings",
                    "event_id": event_id,
                }
            )
            # Return empty result - caller should fall back to uniform sampling
            return SmartReanalyzeResult(
                selected_frames=[],
                frame_scores=[],
                query_embedding_time_ms=query_time_ms,
                frame_scoring_time_ms=0,
                formatted_query=formatted_query,
                cached=False,
            )

        # Step 4: Score frames against query
        scoring_start = time.time()
        embeddings = [f["embedding"] for f in frame_embeddings]
        similarities = batch_cosine_similarity(query_embedding, embeddings)

        # Scale similarities to 0-100 for relevance scores
        relevance_scores = [round(s * 100, 2) for s in similarities]

        # Build scored frames list with combined scores (AC3)
        scored_frames = []
        for i in range(len(frame_embeddings)):
            relevance = relevance_scores[i]
            quality = 50.0  # Default quality - could be enhanced with frame quality data
            combined = (relevance * self.RELEVANCE_WEIGHT) + (quality * self.QUALITY_WEIGHT)

            scored_frames.append(
                ScoredFrame(
                    frame_index=frame_embeddings[i]["frame_index"],
                    similarity_score=round(similarities[i], 4),
                    embedding_id=frame_embeddings[i]["id"],
                    quality_score=quality,
                    combined_score=round(combined, 2),
                )
            )

        # Sort by combined score (highest first)
        scored_frames.sort(key=lambda x: x.combined_score, reverse=True)

        scoring_time_ms = (time.time() - scoring_start) * 1000

        # Step 5: Select top-K frames with diversity filtering (AC2)
        selected_frames = self._select_diverse_frames(
            scored_frames=scored_frames,
            frame_embeddings=frame_embeddings,
            top_k=top_k,
            min_similarity=min_similarity,
        )

        total_time_ms = (time.time() - start_time) * 1000

        # Step 6: Cache the result (AC5 - 5-minute TTL)
        if use_cache and selected_frames:
            selected_relevance = [
                next(
                    (sf.similarity_score * 100 for sf in scored_frames if sf.frame_index == idx),
                    0.0
                )
                for idx in selected_frames
            ]
            selected_quality = [50.0] * len(selected_frames)
            selected_combined = [
                next(
                    (sf.combined_score for sf in scored_frames if sf.frame_index == idx),
                    0.0
                )
                for idx in selected_frames
            ]
            self.query_cache.set(
                event_id=event_id,
                query=query,
                frame_indices=selected_frames,
                relevance_scores=selected_relevance,
                quality_scores=selected_quality,
                combined_scores=selected_combined,
            )

        logger.info(
            f"Smart frame selection completed for event {event_id}",
            extra={
                "event_type": "smart_reanalyze_complete",
                "event_id": event_id,
                "query_length": len(query),
                "formatted_query": formatted_query,
                "frames_scored": len(frame_embeddings),
                "frames_selected": len(selected_frames),
                "top_score": scored_frames[0].similarity_score if scored_frames else 0,
                "query_time_ms": round(query_time_ms, 2),
                "scoring_time_ms": round(scoring_time_ms, 2),
                "total_time_ms": round(total_time_ms, 2),
            }
        )

        return SmartReanalyzeResult(
            selected_frames=selected_frames,
            frame_scores=scored_frames,
            query_embedding_time_ms=query_time_ms,
            frame_scoring_time_ms=scoring_time_ms,
            formatted_query=formatted_query,
            cached=False,
        )

    def _select_diverse_frames(
        self,
        scored_frames: list[ScoredFrame],
        frame_embeddings: list[dict],
        top_k: int,
        min_similarity: float,
    ) -> list[int]:
        """
        Select top-K frames with diversity filtering.

        Avoids selecting near-duplicate frames that might contain
        the same visual information.

        Args:
            scored_frames: Frames sorted by similarity score
            frame_embeddings: Original embeddings data for diversity check
            top_k: Maximum number of frames to select
            min_similarity: Minimum similarity threshold

        Returns:
            List of selected frame indices
        """
        selected = []
        selected_embeddings = []

        # Build lookup for frame embeddings by index
        embedding_by_index = {
            f["frame_index"]: f["embedding"]
            for f in frame_embeddings
        }

        for scored in scored_frames:
            # Skip below threshold
            if scored.similarity_score < min_similarity:
                break

            # Check diversity (skip near-duplicates)
            frame_emb = embedding_by_index[scored.frame_index]
            is_diverse = True

            for sel_emb in selected_embeddings:
                similarity = self._cosine_similarity_single(frame_emb, sel_emb)
                if similarity > self.DIVERSITY_THRESHOLD:
                    is_diverse = False
                    break

            if is_diverse:
                selected.append(scored.frame_index)
                selected_embeddings.append(frame_emb)

            if len(selected) >= top_k:
                break

        return selected

    def _cosine_similarity_single(
        self, vec1: list[float], vec2: list[float]
    ) -> float:
        """Calculate cosine similarity between two vectors."""
        import numpy as np

        a = np.array(vec1, dtype=np.float32)
        b = np.array(vec2, dtype=np.float32)

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))


# Global singleton instance
_smart_reanalyze_service: Optional[SmartReanalyzeService] = None


def get_smart_reanalyze_service() -> SmartReanalyzeService:
    """
    Get the global SmartReanalyzeService instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        SmartReanalyzeService singleton instance
    """
    global _smart_reanalyze_service

    if _smart_reanalyze_service is None:
        _smart_reanalyze_service = SmartReanalyzeService()
        logger.info(
            "Global SmartReanalyzeService instance created",
            extra={"event_type": "smart_reanalyze_service_singleton_created"}
        )

    return _smart_reanalyze_service


def reset_smart_reanalyze_service() -> None:
    """
    Reset the global SmartReanalyzeService instance.

    Useful for testing to ensure a fresh instance.
    """
    global _smart_reanalyze_service
    _smart_reanalyze_service = None
