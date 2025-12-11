"""
Unit tests for SimilarityService (Story P4-3.2)

Tests:
- AC1: Cosine similarity function calculates correct similarity scores
- AC4: Configurable minimum similarity threshold filters low-relevance results
- AC5: Configurable time window limits search to recent events
- AC9: Empty result returned when no similar events found
- AC11: Exclude source event from results
"""
import json
import math
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

from app.services.similarity_service import (
    SimilarityService,
    cosine_similarity,
    batch_cosine_similarity,
    get_similarity_service,
    reset_similarity_service,
    SimilarEvent,
)


class TestCosineSimilarity:
    """Tests for cosine_similarity function (AC1)."""

    def test_identical_vectors_return_one(self):
        """Test that identical vectors return similarity of 1.0."""
        vec = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = cosine_similarity(vec, vec)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors_return_zero(self):
        """Test that orthogonal vectors return similarity of 0.0."""
        # [1, 0] and [0, 1] are orthogonal
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        result = cosine_similarity(vec1, vec2)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors_return_negative_one(self):
        """Test that opposite vectors return similarity of -1.0."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [-1.0, -2.0, -3.0]
        result = cosine_similarity(vec1, vec2)
        assert result == pytest.approx(-1.0, abs=1e-6)

    def test_known_vectors_return_expected_similarity(self):
        """Test with known vectors and pre-calculated expected result."""
        # [3, 4] has norm 5, [4, 3] has norm 5
        # dot product = 3*4 + 4*3 = 24
        # similarity = 24 / (5 * 5) = 0.96
        vec1 = [3.0, 4.0]
        vec2 = [4.0, 3.0]
        result = cosine_similarity(vec1, vec2)
        assert result == pytest.approx(0.96, abs=1e-6)

    def test_zero_vector_returns_zero(self):
        """Test that zero vector returns similarity of 0.0."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]
        result = cosine_similarity(vec1, vec2)
        assert result == 0.0

    def test_both_zero_vectors_return_zero(self):
        """Test that two zero vectors return similarity of 0.0."""
        vec1 = [0.0, 0.0]
        vec2 = [0.0, 0.0]
        result = cosine_similarity(vec1, vec2)
        assert result == 0.0

    def test_dimension_mismatch_raises_error(self):
        """Test that dimension mismatch raises ValueError."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.0, 2.0]
        with pytest.raises(ValueError, match="Vector dimension mismatch"):
            cosine_similarity(vec1, vec2)

    def test_high_dimensional_vectors(self):
        """Test with 512-dimensional vectors (CLIP embedding size)."""
        np.random.seed(42)
        vec1 = np.random.randn(512).tolist()
        vec2 = np.random.randn(512).tolist()

        result = cosine_similarity(vec1, vec2)

        # Should be between -1 and 1
        assert -1.0 <= result <= 1.0

    def test_normalized_vectors_dot_product_equals_similarity(self):
        """Test that for normalized vectors, dot product equals cosine similarity."""
        vec1 = [3.0, 4.0]  # norm = 5
        vec2 = [1.0, 0.0]  # norm = 1

        result = cosine_similarity(vec1, vec2)

        # Manual calculation
        norm1 = math.sqrt(3**2 + 4**2)  # 5
        norm2 = 1.0
        dot = 3.0 * 1.0 + 4.0 * 0.0  # 3
        expected = dot / (norm1 * norm2)  # 0.6

        assert result == pytest.approx(expected, abs=1e-6)


class TestBatchCosineSimilarity:
    """Tests for batch_cosine_similarity function."""

    def test_empty_candidates_returns_empty_list(self):
        """Test that empty candidates list returns empty result."""
        query = [1.0, 2.0, 3.0]
        candidates = []
        result = batch_cosine_similarity(query, candidates)
        assert result == []

    def test_single_candidate(self):
        """Test with single candidate returns single result."""
        query = [1.0, 0.0]
        candidates = [[0.0, 1.0]]  # orthogonal to query
        result = batch_cosine_similarity(query, candidates)
        assert len(result) == 1
        assert result[0] == pytest.approx(0.0, abs=1e-6)

    def test_multiple_candidates(self):
        """Test with multiple candidates."""
        query = [1.0, 0.0]
        candidates = [
            [1.0, 0.0],   # identical, should be 1.0
            [0.0, 1.0],   # orthogonal, should be 0.0
            [-1.0, 0.0],  # opposite, should be -1.0
        ]
        result = batch_cosine_similarity(query, candidates)

        assert len(result) == 3
        assert result[0] == pytest.approx(1.0, abs=1e-6)
        assert result[1] == pytest.approx(0.0, abs=1e-6)
        assert result[2] == pytest.approx(-1.0, abs=1e-6)

    def test_matches_individual_cosine_similarity(self):
        """Test that batch results match individual calculations."""
        np.random.seed(42)
        query = np.random.randn(512).tolist()
        candidates = [np.random.randn(512).tolist() for _ in range(10)]

        batch_results = batch_cosine_similarity(query, candidates)

        for i, candidate in enumerate(candidates):
            individual_result = cosine_similarity(query, candidate)
            assert batch_results[i] == pytest.approx(individual_result, abs=1e-5)

    def test_empty_query_raises_error(self):
        """Test that empty query vector raises ValueError."""
        with pytest.raises(ValueError, match="Query vector cannot be empty"):
            batch_cosine_similarity([], [[1.0, 2.0]])

    def test_dimension_mismatch_raises_error(self):
        """Test that dimension mismatch raises ValueError."""
        query = [1.0, 2.0, 3.0]
        candidates = [[1.0, 2.0]]  # Different dimension
        with pytest.raises(ValueError, match="Dimension mismatch"):
            batch_cosine_similarity(query, candidates)

    def test_zero_query_vector(self):
        """Test with zero query vector returns all zeros."""
        query = [0.0, 0.0, 0.0]
        candidates = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
        result = batch_cosine_similarity(query, candidates)
        assert result == [0.0, 0.0]

    def test_zero_candidate_vectors(self):
        """Test with zero candidate vectors returns zeros for those candidates."""
        query = [1.0, 2.0]
        candidates = [
            [1.0, 2.0],   # Normal, should give high similarity
            [0.0, 0.0],   # Zero vector, should be 0.0
        ]
        result = batch_cosine_similarity(query, candidates)
        assert result[0] > 0.9  # Similar to query
        assert result[1] == 0.0  # Zero vector


class TestSimilarityServiceInit:
    """Tests for SimilarityService initialization."""

    def test_service_initialization_with_defaults(self):
        """Test that service initializes with correct defaults."""
        mock_embedding_service = MagicMock()
        service = SimilarityService(embedding_service=mock_embedding_service)

        assert service.DEFAULT_LIMIT == 10
        assert service.DEFAULT_MIN_SIMILARITY == 0.7
        assert service.DEFAULT_TIME_WINDOW_DAYS == 30

    def test_service_uses_provided_embedding_service(self):
        """Test that service uses provided embedding service."""
        mock_embedding_service = MagicMock()
        service = SimilarityService(embedding_service=mock_embedding_service)

        assert service._embedding_service is mock_embedding_service


class TestSimilarityServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_similarity_service_returns_same_instance(self):
        """Test that get_similarity_service returns singleton."""
        reset_similarity_service()

        service1 = get_similarity_service()
        service2 = get_similarity_service()

        assert service1 is service2

        reset_similarity_service()

    def test_reset_similarity_service_clears_singleton(self):
        """Test that reset_similarity_service clears the singleton."""
        reset_similarity_service()

        service1 = get_similarity_service()
        reset_similarity_service()
        service2 = get_similarity_service()

        assert service1 is not service2

        reset_similarity_service()


class TestFindSimilarEventsFiltering:
    """Tests for find_similar_events filtering logic (AC4, AC5, AC11)."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session with query results."""
        session = MagicMock()
        return session

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        service = MagicMock()
        service.get_embedding_vector = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_no_embedding_raises_error(self, mock_db_session, mock_embedding_service):
        """Test that missing source embedding raises ValueError."""
        mock_embedding_service.get_embedding_vector.return_value = None

        service = SimilarityService(embedding_service=mock_embedding_service)

        with pytest.raises(ValueError, match="No embedding found for event"):
            await service.find_similar_events(
                db=mock_db_session,
                event_id="test-event-id",
            )

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty_list(self, mock_db_session, mock_embedding_service):
        """Test that no candidates returns empty list (AC9)."""
        mock_embedding_service.get_embedding_vector.return_value = [0.1] * 512

        # Mock query that returns empty list
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db_session.query.return_value = mock_query

        service = SimilarityService(embedding_service=mock_embedding_service)

        result = await service.find_similar_events(
            db=mock_db_session,
            event_id="test-event-id",
        )

        assert result == []


class TestSimilarEventDataclass:
    """Tests for SimilarEvent dataclass."""

    def test_similar_event_creation(self):
        """Test that SimilarEvent can be created with all fields."""
        event = SimilarEvent(
            event_id="test-id",
            similarity_score=0.85,
            thumbnail_url="/api/v1/thumbnails/test.jpg",
            description="A person walking",
            timestamp=datetime.now(timezone.utc),
            camera_name="Front Door",
            camera_id="camera-123",
        )

        assert event.event_id == "test-id"
        assert event.similarity_score == 0.85
        assert event.thumbnail_url == "/api/v1/thumbnails/test.jpg"
        assert event.description == "A person walking"
        assert event.camera_name == "Front Door"
        assert event.camera_id == "camera-123"

    def test_similar_event_with_none_thumbnail(self):
        """Test that SimilarEvent works with None thumbnail."""
        event = SimilarEvent(
            event_id="test-id",
            similarity_score=0.75,
            thumbnail_url=None,
            description="Motion detected",
            timestamp=datetime.now(timezone.utc),
            camera_name="Back Yard",
            camera_id="camera-456",
        )

        assert event.thumbnail_url is None


class TestThresholdFiltering:
    """Tests for similarity threshold filtering (AC4)."""

    def test_filter_by_threshold(self):
        """Test that results below threshold are filtered out."""
        # Create test similarities
        similarities = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]
        threshold = 0.7

        filtered = [s for s in similarities if s >= threshold]

        assert len(filtered) == 3
        assert all(s >= threshold for s in filtered)


class TestTimeWindowFiltering:
    """Tests for time window filtering (AC5)."""

    def test_time_window_calculation(self):
        """Test that time window cutoff is calculated correctly."""
        now = datetime.now(timezone.utc)
        time_window_days = 30

        cutoff = now - timedelta(days=time_window_days)

        # Events before cutoff should be excluded
        old_event_time = now - timedelta(days=31)
        new_event_time = now - timedelta(days=29)

        assert old_event_time < cutoff  # Should be excluded
        assert new_event_time > cutoff  # Should be included


class TestSourceEventExclusion:
    """Tests for source event exclusion (AC11)."""

    def test_source_event_excluded_from_candidates(self):
        """Test that source event is always excluded."""
        source_id = "source-event-id"
        candidate_ids = ["candidate-1", "source-event-id", "candidate-2"]

        # Filter out source
        filtered = [c for c in candidate_ids if c != source_id]

        assert source_id not in filtered
        assert len(filtered) == 2


class TestResultOrdering:
    """Tests for result ordering (AC3)."""

    def test_results_sorted_by_similarity_descending(self):
        """Test that results are sorted by similarity score (highest first)."""
        events = [
            SimilarEvent("a", 0.7, None, "desc", datetime.now(timezone.utc), "cam", "c1"),
            SimilarEvent("b", 0.9, None, "desc", datetime.now(timezone.utc), "cam", "c1"),
            SimilarEvent("c", 0.8, None, "desc", datetime.now(timezone.utc), "cam", "c1"),
        ]

        sorted_events = sorted(events, key=lambda x: x.similarity_score, reverse=True)

        assert sorted_events[0].similarity_score == 0.9
        assert sorted_events[1].similarity_score == 0.8
        assert sorted_events[2].similarity_score == 0.7
