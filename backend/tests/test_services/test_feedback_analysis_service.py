"""
Tests for FeedbackAnalysisService - Story P4-5.4

Tests feedback pattern analysis, correction categorization,
and prompt suggestion generation.
"""
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from app.services.feedback_analysis_service import (
    FeedbackAnalysisService,
    CorrectionCategory,
    MIN_SAMPLES_FOR_SUGGESTIONS,
    LOW_ACCURACY_THRESHOLD,
)
from app.models.event_feedback import EventFeedback
from app.models.camera import Camera


class TestCategorizeCorrection:
    """Tests for categorize_feedback method."""

    def test_object_misidentification_pattern(self):
        """Test detection of object misidentification patterns."""
        service = FeedbackAnalysisService(MagicMock())

        # Pattern: "it was X, not Y"
        result = service.categorize_feedback("It was a cat, not a dog")
        assert result == CorrectionCategory.OBJECT_MISID

        # Pattern: "actually a X"
        result = service.categorize_feedback("Actually a delivery person")
        assert result == CorrectionCategory.OBJECT_MISID

        # Pattern: "not a X"
        result = service.categorize_feedback("That's not a person")
        assert result == CorrectionCategory.OBJECT_MISID

    def test_action_wrong_pattern(self):
        """Test detection of incorrect action patterns."""
        service = FeedbackAnalysisService(MagicMock())

        # Pattern: "was leaving"
        result = service.categorize_feedback("They were leaving the driveway")
        assert result == CorrectionCategory.ACTION_WRONG

        # Pattern: "wrong action"
        result = service.categorize_feedback("Wrong action described")
        assert result == CorrectionCategory.ACTION_WRONG

        # Pattern: "wrong movement"
        result = service.categorize_feedback("Wrong movement direction")
        assert result == CorrectionCategory.ACTION_WRONG

    def test_missing_detail_pattern(self):
        """Test detection of missing detail patterns."""
        service = FeedbackAnalysisService(MagicMock())

        # Pattern: "didn't mention"
        result = service.categorize_feedback("You didn't mention the box")
        assert result == CorrectionCategory.MISSING_DETAIL

        # Pattern: "should have mentioned"
        result = service.categorize_feedback("Should have mentioned the second item")
        assert result == CorrectionCategory.MISSING_DETAIL

        # Pattern: "omitted"
        result = service.categorize_feedback("Omitted important details")
        assert result == CorrectionCategory.MISSING_DETAIL

    def test_context_error_pattern(self):
        """Test detection of context error patterns."""
        service = FeedbackAnalysisService(MagicMock())

        # Pattern: "this is my/our X daily"
        result = service.categorize_feedback("This is our regular daily visitor")
        assert result == CorrectionCategory.CONTEXT_ERROR

        # Pattern: "wrong time"
        result = service.categorize_feedback("Wrong time shown")
        assert result == CorrectionCategory.CONTEXT_ERROR

        # Pattern: "familiar person"
        result = service.categorize_feedback("This is a familiar visitor")
        assert result == CorrectionCategory.CONTEXT_ERROR

    def test_general_category_fallback(self):
        """Test fallback to general category for unrecognized patterns."""
        service = FeedbackAnalysisService(MagicMock())

        result = service.categorize_feedback("The image quality was poor")
        assert result == CorrectionCategory.GENERAL

        result = service.categorize_feedback("Good description overall")
        assert result == CorrectionCategory.GENERAL

    def test_empty_correction(self):
        """Test handling of empty correction text."""
        service = FeedbackAnalysisService(MagicMock())

        result = service.categorize_feedback("")
        assert result == CorrectionCategory.GENERAL

        result = service.categorize_feedback(None)
        assert result == CorrectionCategory.GENERAL


class TestAnalyzeCorrectionPatterns:
    """Tests for analyze_correction_patterns method."""

    def test_insufficient_samples_returns_empty(self):
        """Test that fewer than MIN_SAMPLES returns empty suggestions."""
        mock_db = MagicMock(spec=Session)

        # Mock query to return only 5 corrections (below threshold)
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            MagicMock(correction="Test 1", camera_id="cam1"),
            MagicMock(correction="Test 2", camera_id="cam1"),
            MagicMock(correction="Test 3", camera_id="cam1"),
            MagicMock(correction="Test 4", camera_id="cam1"),
            MagicMock(correction="Test 5", camera_id="cam1"),
        ]
        mock_db.query.return_value = mock_query

        service = FeedbackAnalysisService(mock_db)
        result = service.analyze_correction_patterns()

        assert result.min_samples_met is False
        assert len(result.suggestions) == 0
        assert result.sample_count == 5
        assert result.confidence == 0.0

    def test_sufficient_samples_generates_suggestions(self):
        """Test that sufficient samples generate suggestions."""
        mock_db = MagicMock(spec=Session)

        # Create 15 corrections with object misidentification pattern - no camera_id to avoid insight generation
        corrections = [
            MagicMock(correction=f"It was a cat, not a dog (#{i})", camera_id=None)
            for i in range(15)
        ]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = corrections
        mock_db.query.return_value = mock_query

        service = FeedbackAnalysisService(mock_db)
        result = service.analyze_correction_patterns()

        assert result.min_samples_met is True
        assert result.sample_count == 15
        assert len(result.suggestions) > 0
        # Should have object misidentification suggestion
        categories = [s.category for s in result.suggestions]
        assert CorrectionCategory.OBJECT_MISID in categories

    def test_camera_filter_applied(self):
        """Test that camera_id filter is applied to query."""
        mock_db = MagicMock(spec=Session)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        service = FeedbackAnalysisService(mock_db)
        service.analyze_correction_patterns(camera_id="test-camera-123")

        # Verify filter was called
        assert mock_query.filter.called


class TestSuggestionGeneration:
    """Tests for suggestion generation logic."""

    def test_suggestion_includes_examples(self):
        """Test that suggestions include example corrections."""
        mock_db = MagicMock(spec=Session)

        # Create corrections with recognizable patterns - no camera_id to avoid insight generation
        corrections = [
            MagicMock(correction="It was a cat, not a dog", camera_id=None),
            MagicMock(correction="Actually a cat", camera_id=None),
            MagicMock(correction="Not a dog, that's a cat", camera_id=None),
        ] * 5  # 15 total samples

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = corrections
        mock_db.query.return_value = mock_query

        service = FeedbackAnalysisService(mock_db)
        result = service.analyze_correction_patterns()

        # Find object misidentification suggestion
        object_suggestion = next(
            (s for s in result.suggestions
             if s.category == CorrectionCategory.OBJECT_MISID),
            None
        )

        assert object_suggestion is not None
        assert len(object_suggestion.example_corrections) > 0
        assert len(object_suggestion.example_corrections) <= 5  # Max 5 examples

    def test_suggestions_sorted_by_impact(self):
        """Test that suggestions are sorted by impact score (highest first)."""
        mock_db = MagicMock(spec=Session)

        # Create mixed corrections - no camera_id to avoid insight generation issues
        corrections = [
            MagicMock(correction="It was a cat, not a dog", camera_id=None),
            MagicMock(correction="You didn't mention the box", camera_id=None),
            MagicMock(correction="They were leaving the driveway", camera_id=None),
        ] * 10  # 30 total

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = corrections
        mock_db.query.return_value = mock_query

        service = FeedbackAnalysisService(mock_db)
        result = service.analyze_correction_patterns()

        # Verify sorting
        if len(result.suggestions) > 1:
            for i in range(len(result.suggestions) - 1):
                assert result.suggestions[i].impact_score >= result.suggestions[i + 1].impact_score


class TestConfidenceCalculation:
    """Tests for confidence score calculation."""

    def test_confidence_increases_with_sample_size(self):
        """Test that confidence increases with more samples."""
        mock_db = MagicMock(spec=Session)
        service = FeedbackAnalysisService(mock_db)

        # Small sample confidence
        small_categorized = {
            CorrectionCategory.OBJECT_MISID: ["test"] * 10,
            CorrectionCategory.ACTION_WRONG: [],
            CorrectionCategory.MISSING_DETAIL: [],
            CorrectionCategory.CONTEXT_ERROR: [],
            CorrectionCategory.GENERAL: [],
        }
        small_confidence = service._calculate_confidence(10, small_categorized)

        # Large sample confidence
        large_categorized = {
            CorrectionCategory.OBJECT_MISID: ["test"] * 50,
            CorrectionCategory.ACTION_WRONG: [],
            CorrectionCategory.MISSING_DETAIL: [],
            CorrectionCategory.CONTEXT_ERROR: [],
            CorrectionCategory.GENERAL: [],
        }
        large_confidence = service._calculate_confidence(50, large_categorized)

        assert large_confidence > small_confidence

    def test_confidence_capped_at_max(self):
        """Test that confidence doesn't exceed 0.95."""
        mock_db = MagicMock(spec=Session)
        service = FeedbackAnalysisService(mock_db)

        # Very large sample with concentrated category
        categorized = {
            CorrectionCategory.OBJECT_MISID: ["test"] * 1000,
            CorrectionCategory.ACTION_WRONG: [],
            CorrectionCategory.MISSING_DETAIL: [],
            CorrectionCategory.CONTEXT_ERROR: [],
            CorrectionCategory.GENERAL: [],
        }
        confidence = service._calculate_confidence(1000, categorized)

        assert confidence <= 0.95


class TestConstants:
    """Tests for module constants."""

    def test_min_samples_threshold(self):
        """Test minimum samples constant is 10."""
        assert MIN_SAMPLES_FOR_SUGGESTIONS == 10

    def test_low_accuracy_threshold(self):
        """Test low accuracy threshold is 70%."""
        assert LOW_ACCURACY_THRESHOLD == 70.0
