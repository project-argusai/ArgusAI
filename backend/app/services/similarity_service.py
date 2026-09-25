"""
Similarity Service for Temporal Context Engine (Story P4-3.2)

This module provides similarity search functionality for finding visually similar
past events using CLIP embeddings. It enables pattern recognition like recurring
visitors and understanding if someone has been seen before.

Architecture:
    - Cosine similarity using numpy for efficient vector operations
    - Batch processing for comparing against multiple embeddings
    - Configurable similarity threshold and time window
    - SQLite-compatible (no pgvector required for MVP)

Flow:
    Event → EmbeddingService.get_embedding_vector() → SimilarityService.find_similar_events()
                                                              ↓
                                                      Query event_embeddings (time window)
                                                              ↓
                                                      Batch cosine similarity
                                                              ↓
                                                      Filter, sort, return top-N
"""
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.decorators import singleton
from app.schemas.types import ensure_utc
from app.services.embedding_service import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


@dataclass
class SimilarEvent:
    """Data class representing a similar event result."""
    event_id: str
    similarity_score: float
    thumbnail_url: Optional[str]
    description: str
    timestamp: datetime
    camera_name: str
    camera_id: str


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Cosine similarity = (A · B) / (||A|| * ||B||)

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Similarity score between 0.0 and 1.0
        - 1.0 = identical vectors
        - 0.0 = orthogonal vectors
        - Negative values possible for opposing vectors (rare with embeddings)

    Raises:
        ValueError: If vectors have different dimensions
    """
    if len(vec1) != len(vec2):
        raise ValueError(
            f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}"
        )

    a = np.array(vec1, dtype=np.float32)
    b = np.array(vec2, dtype=np.float32)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    # Handle zero vectors
    if norm_a == 0 or norm_b == 0:
        return 0.0

    dot_product = np.dot(a, b)
    return float(dot_product / (norm_a * norm_b))


def batch_cosine_similarity(query: list[float], candidates: list[list[float]]) -> list[float]:
    """
    Calculate cosine similarity between query and all candidates efficiently.

    Uses numpy vectorized operations for performance.

    Args:
        query: Query embedding vector
        candidates: List of candidate embedding vectors

    Returns:
        List of similarity scores (same order as candidates)

    Raises:
        ValueError: If query or candidates are empty, or dimensions mismatch
    """
    if not candidates:
        return []

    if not query:
        raise ValueError("Query vector cannot be empty")

    query_vec = np.array(query, dtype=np.float32)
    candidate_matrix = np.array(candidates, dtype=np.float32)

    # Validate dimensions
    if candidate_matrix.ndim != 2:
        raise ValueError("Candidates must be a 2D array")
    if candidate_matrix.shape[1] != len(query):
        raise ValueError(
            f"Dimension mismatch: query={len(query)}, candidates={candidate_matrix.shape[1]}"
        )

    # Handle zero query vector
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return [0.0] * len(candidates)

    # Normalize query vector
    query_normalized = query_vec / query_norm

    # Normalize all candidate vectors (handle zero vectors)
    candidate_norms = np.linalg.norm(candidate_matrix, axis=1, keepdims=True)
    # Replace zero norms with 1 to avoid division by zero (result will be 0 anyway)
    candidate_norms = np.where(candidate_norms == 0, 1, candidate_norms)
    candidates_normalized = candidate_matrix / candidate_norms

    # Batch dot product gives similarity scores
    similarities = np.dot(candidates_normalized, query_normalized)

    # Zero out similarities for zero-norm candidates
    zero_mask = np.squeeze(candidate_norms) == 0
    if candidate_norms.shape[0] == 1:
        zero_mask = np.array([zero_mask])
    similarities = np.where(zero_mask, 0.0, similarities)

    return similarities.tolist()


@singleton
class SimilarityService:
    """
    Find similar events using embedding cosine similarity.

    This service provides the core similarity search functionality for the
    Temporal Context Engine. It enables finding visually similar past events
    within a configurable time window.

    Attributes:
        DEFAULT_LIMIT: Default number of results to return (10)
        DEFAULT_MIN_SIMILARITY: Default minimum similarity threshold (0.7)
        DEFAULT_TIME_WINDOW_DAYS: Default time window in days (30)
    """

    DEFAULT_LIMIT = 10
    DEFAULT_MIN_SIMILARITY = 0.7
    DEFAULT_TIME_WINDOW_DAYS = 30

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        """
        Initialize SimilarityService.

        Args:
            embedding_service: EmbeddingService instance for retrieving embeddings.
                             If None, will use the global singleton.
        """
        self._embedding_service = embedding_service or get_embedding_service()
        logger.info(
            "SimilarityService initialized",
            extra={"event_type": "similarity_service_init"}
        )

    async def find_similar_events(
        self,
        db: Session,
        event_id: str,
        limit: int = DEFAULT_LIMIT,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        time_window_days: int = DEFAULT_TIME_WINDOW_DAYS,
        camera_id: Optional[str] = None,
    ) -> list[SimilarEvent]:
        """
        Find visually similar past events for a persisted event id.

        Looks up the stored embedding for ``event_id`` then delegates to
        ``find_similar_events_by_embedding``. Pre-persist callers (Protect/RTSP
        vision path) must pass the in-memory CLIP vector instead of a
        throwaway UUID — a not-yet-stored id has no embedding.

        Raises:
            ValueError: If source event has no embedding
        """
        source_embedding = await self._embedding_service.get_embedding_vector(
            db, event_id
        )

        if source_embedding is None:
            logger.warning(
                f"No embedding found for source event {event_id}",
                extra={"event_type": "similarity_no_source_embedding", "event_id": event_id}
            )
            raise ValueError(f"No embedding found for event {event_id}")

        return await self.find_similar_events_by_embedding(
            db=db,
            embedding=source_embedding,
            exclude_event_id=event_id,
            limit=limit,
            min_similarity=min_similarity,
            time_window_days=time_window_days,
            camera_id=camera_id,
        )

    async def find_similar_events_by_embedding(
        self,
        db: Session,
        embedding: list[float],
        exclude_event_id: Optional[str] = None,
        limit: int = DEFAULT_LIMIT,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        time_window_days: int = DEFAULT_TIME_WINDOW_DAYS,
        camera_id: Optional[str] = None,
    ) -> list[SimilarEvent]:
        """
        Find visually similar past events from an in-memory CLIP vector.

        Use this on the live vision path: the current event is not persisted
        yet, so there is no event_id to look up.
        """
        if not embedding:
            raise ValueError("Query embedding cannot be empty")

        start_time = time.time()

        from app.models.event import Event
        from app.models.event_embedding import EventEmbedding
        from app.models.camera import Camera

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=time_window_days)

        query = db.query(
            EventEmbedding.event_id,
            EventEmbedding.embedding,
            Event.description,
            Event.timestamp,
            Event.thumbnail_path,
            Event.thumbnail_base64,
            Event.camera_id,
            Camera.name.label("camera_name"),
        ).join(
            Event, Event.id == EventEmbedding.event_id
        ).join(
            Camera, Camera.id == Event.camera_id
        ).filter(
            Event.timestamp >= cutoff_time,
        )

        if exclude_event_id:
            query = query.filter(EventEmbedding.event_id != exclude_event_id)

        if camera_id:
            query = query.filter(Event.camera_id == camera_id)

        candidates = query.all()

        if not candidates:
            logger.debug(
                "No candidate embeddings found for in-memory similarity search",
                extra={
                    "event_type": "similarity_no_candidates",
                    "event_id": exclude_event_id,
                    "time_window_days": time_window_days,
                    "camera_id": camera_id,
                }
            )
            return []

        candidate_embeddings = [
            json.loads(c.embedding) for c in candidates
        ]
        similarities = batch_cosine_similarity(embedding, candidate_embeddings)

        results = []
        for i, similarity in enumerate(similarities):
            if similarity >= min_similarity:
                candidate = candidates[i]

                thumbnail_url = None
                if candidate.thumbnail_path:
                    thumbnail_url = candidate.thumbnail_path
                elif candidate.thumbnail_base64:
                    thumbnail_url = f"/api/v1/events/{candidate.event_id}/thumbnail"

                # Normalize in memory only. SQLite hands back naive UTC
                # datetimes; do not assign back onto the row.
                raw_timestamp = candidate.timestamp
                timestamp = (
                    ensure_utc(raw_timestamp)
                    if isinstance(raw_timestamp, datetime)
                    else raw_timestamp
                )
                results.append(SimilarEvent(
                    event_id=candidate.event_id,
                    similarity_score=round(similarity, 4),
                    thumbnail_url=thumbnail_url,
                    description=candidate.description,
                    timestamp=timestamp,
                    camera_name=candidate.camera_name,
                    camera_id=candidate.camera_id,
                ))

        results.sort(key=lambda x: x.similarity_score, reverse=True)
        results = results[:limit]

        query_time_ms = (time.time() - start_time) * 1000
        logger.info(
            "Similarity search completed from in-memory embedding",
            extra={
                "event_type": "similarity_search_complete",
                "event_id": exclude_event_id,
                "candidates_checked": len(candidates),
                "results_found": len(results),
                "query_time_ms": round(query_time_ms, 2),
                "time_window_days": time_window_days,
                "min_similarity": min_similarity,
                "camera_id": camera_id,
            }
        )

        return results


# Backward compatible thin getter (delegates to @singleton decorator)
def get_similarity_service() -> SimilarityService:
    """
    Get the global SimilarityService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer SimilarityService() directly.
    """
    return SimilarityService()


def reset_similarity_service() -> None:
    """Reset the global SimilarityService instance (for testing)."""
    SimilarityService._reset_instance()
