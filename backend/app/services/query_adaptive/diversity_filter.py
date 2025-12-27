"""
Diversity Filter Service (Story P12-4.2)

Prevents selection of near-duplicate frames during query-adaptive frame
selection. Uses greedy selection with cosine similarity threshold.

Algorithm:
    1. Sort frames by relevance score (descending)
    2. For each frame, check similarity to already selected frames
    3. Skip if similarity > threshold (0.92 by default)
    4. Continue until top_k diverse frames selected

Performance:
    - Adds <10ms overhead to frame selection
    - O(n*k) where n = total frames, k = selected frames
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FilteredFrame:
    """Represents a frame after diversity filtering."""
    frame_index: int
    relevance_score: float
    quality_score: float
    combined_score: float
    was_filtered: bool = False  # True if similar to a selected frame


class DiversityFilter:
    """
    Prevents selection of near-duplicate frames.

    Uses greedy selection: picks the highest-scoring frame, then filters
    out similar frames before picking the next.

    Attributes:
        DEFAULT_SIMILARITY_THRESHOLD: Default threshold (0.92)
        RELEVANCE_WEIGHT: Weight for relevance in combined score (0.7)
        QUALITY_WEIGHT: Weight for quality in combined score (0.3)
    """

    DEFAULT_SIMILARITY_THRESHOLD = 0.92
    RELEVANCE_WEIGHT = 0.7
    QUALITY_WEIGHT = 0.3

    def __init__(self, similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        """
        Initialize DiversityFilter.

        Args:
            similarity_threshold: Frames with similarity > threshold are
                                considered duplicates (default: 0.92)
        """
        self.similarity_threshold = similarity_threshold
        logger.debug(
            "DiversityFilter initialized",
            extra={
                "event_type": "diversity_filter_init",
                "similarity_threshold": similarity_threshold,
            }
        )

    def filter_diverse_frames(
        self,
        embeddings: list[list[float]],
        relevance_scores: list[float],
        quality_scores: Optional[list[float]] = None,
        top_k: int = 5,
    ) -> list[int]:
        """
        Select top-k frames while maintaining diversity.

        Uses greedy selection: pick highest combined score, then filter
        similar frames before picking the next.

        Args:
            embeddings: List of frame embeddings (512-dim each)
            relevance_scores: Relevance scores (0-100) for each frame
            quality_scores: Optional quality scores (0-100) for each frame.
                          If None, combined score = relevance score.
            top_k: Maximum number of frames to select

        Returns:
            List of selected frame indices (sorted by combined score)

        Note:
            Adds <10ms overhead for typical frame counts (10-20 frames).
        """
        start_time = time.time()

        if len(embeddings) <= top_k:
            # No filtering needed if we want all frames
            return list(range(len(embeddings)))

        # Calculate combined scores (AC3: combined = relevance*0.7 + quality*0.3)
        combined_scores = self._calculate_combined_scores(
            relevance_scores, quality_scores
        )

        # Convert to numpy for efficient similarity computation
        embeddings_np = [np.array(e, dtype=np.float32) for e in embeddings]

        # Sort by combined score descending
        scored_indices = sorted(
            range(len(combined_scores)),
            key=lambda i: combined_scores[i],
            reverse=True,
        )

        selected = []
        selected_embeddings = []
        filtered_count = 0

        for idx in scored_indices:
            if len(selected) >= top_k:
                break

            # Check similarity to already selected frames
            is_diverse = True
            for sel_emb in selected_embeddings:
                similarity = self._cosine_similarity(embeddings_np[idx], sel_emb)
                if similarity > self.similarity_threshold:
                    is_diverse = False
                    filtered_count += 1
                    break

            if is_diverse:
                selected.append(idx)
                selected_embeddings.append(embeddings_np[idx])

        duration_ms = (time.time() - start_time) * 1000
        logger.debug(
            f"Diversity filtering complete: {len(selected)}/{len(embeddings)} frames selected",
            extra={
                "event_type": "diversity_filter_complete",
                "frames_total": len(embeddings),
                "frames_selected": len(selected),
                "frames_filtered": filtered_count,
                "top_k": top_k,
                "duration_ms": round(duration_ms, 2),
            }
        )

        return selected

    def _calculate_combined_scores(
        self,
        relevance_scores: list[float],
        quality_scores: Optional[list[float]],
    ) -> list[float]:
        """
        Calculate combined scores from relevance and quality.

        Formula: combined = (relevance * 0.7) + (quality * 0.3)

        Args:
            relevance_scores: Relevance scores (0-100)
            quality_scores: Quality scores (0-100) or None

        Returns:
            List of combined scores (0-100)
        """
        if quality_scores is None:
            # No quality scores available - use relevance only
            return list(relevance_scores)

        combined = []
        for i in range(len(relevance_scores)):
            rel = relevance_scores[i]
            qual = quality_scores[i] if i < len(quality_scores) else 50.0  # Default quality
            combined.append(
                (rel * self.RELEVANCE_WEIGHT) + (qual * self.QUALITY_WEIGHT)
            )
        return combined

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            a: First vector (numpy array)
            b: Second vector (numpy array)

        Returns:
            Cosine similarity in range [-1, 1]
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    def get_filtered_frames_with_details(
        self,
        embeddings: list[list[float]],
        relevance_scores: list[float],
        quality_scores: Optional[list[float]] = None,
        top_k: int = 5,
    ) -> tuple[list[int], list[FilteredFrame]]:
        """
        Select frames with detailed filtering information.

        Like filter_diverse_frames but also returns why frames were filtered.

        Args:
            embeddings: List of frame embeddings
            relevance_scores: Relevance scores (0-100)
            quality_scores: Quality scores (0-100) or None
            top_k: Maximum number of frames to select

        Returns:
            Tuple of (selected_indices, all_frames_with_details)
        """
        combined_scores = self._calculate_combined_scores(
            relevance_scores, quality_scores
        )

        embeddings_np = [np.array(e, dtype=np.float32) for e in embeddings]

        # All frames with details
        all_frames = [
            FilteredFrame(
                frame_index=i,
                relevance_score=relevance_scores[i],
                quality_score=quality_scores[i] if quality_scores and i < len(quality_scores) else 50.0,
                combined_score=combined_scores[i],
                was_filtered=False,
            )
            for i in range(len(embeddings))
        ]

        # Sort by combined score
        sorted_frames = sorted(all_frames, key=lambda f: f.combined_score, reverse=True)

        selected_indices = []
        selected_embeddings = []

        for frame in sorted_frames:
            if len(selected_indices) >= top_k:
                break

            is_diverse = True
            for sel_emb in selected_embeddings:
                similarity = self._cosine_similarity(
                    embeddings_np[frame.frame_index], sel_emb
                )
                if similarity > self.similarity_threshold:
                    frame.was_filtered = True
                    is_diverse = False
                    break

            if is_diverse:
                selected_indices.append(frame.frame_index)
                selected_embeddings.append(embeddings_np[frame.frame_index])

        return selected_indices, all_frames
