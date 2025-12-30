"""
Tests for AnomalyScoringService (Story P4-7.2)

Tests cover:
- Scoring components (timing, day, object)
- Score combination with weights
- Severity classification
- Edge cases (no baseline, empty data)
- Event scoring with persistence
"""
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.anomaly_scoring_service import (
    AnomalyScoringService,
    AnomalyScoreResult,
    get_anomaly_scoring_service,
    reset_anomaly_scoring_service,
)
from app.services.pattern_service import PatternData


@pytest.fixture
def anomaly_service():
    """Create a fresh anomaly scoring service for each test."""
    reset_anomaly_scoring_service()
    service = AnomalyScoringService()
    yield service
    reset_anomaly_scoring_service()


@pytest.fixture
def sample_patterns():
    """Create sample pattern data with realistic distributions."""
    return PatternData(
        camera_id="test-camera-1",
        hourly_distribution={
            "00": 2, "01": 1, "02": 1, "03": 0, "04": 0, "05": 1,
            "06": 3, "07": 8, "08": 15, "09": 12, "10": 10, "11": 8,
            "12": 6, "13": 5, "14": 7, "15": 9, "16": 12, "17": 15,
            "18": 10, "19": 8, "20": 6, "21": 4, "22": 3, "23": 2,
        },
        daily_distribution={
            "0": 45, "1": 48, "2": 42, "3": 50, "4": 52, "5": 30, "6": 25,
        },
        peak_hours=["08", "09", "16", "17"],
        quiet_hours=["02", "03", "04"],
        average_events_per_day=41.7,
        last_calculated_at=datetime.now(timezone.utc),
        calculation_window_days=30,
        insufficient_data=False,
        object_type_distribution={
            "person": 150,
            "vehicle": 45,
            "package": 12,
            "animal": 8,
        },
        dominant_object_type="person",
    )


@pytest.fixture
def sparse_patterns():
    """Create sparse pattern data with uniform distributions."""
    return PatternData(
        camera_id="test-camera-2",
        hourly_distribution={
            "08": 5, "09": 5, "10": 5, "11": 5, "12": 5,
        },
        daily_distribution={
            "0": 10, "1": 10, "2": 10, "3": 10, "4": 10, "5": 10, "6": 10,
        },
        peak_hours=[],
        quiet_hours=[],
        average_events_per_day=10.0,
        last_calculated_at=datetime.now(timezone.utc),
        calculation_window_days=30,
        insufficient_data=False,
        object_type_distribution={"person": 50, "vehicle": 50},
        dominant_object_type="person",
    )


class TestTimingScore:
    """Tests for timing score calculation."""

    @pytest.mark.asyncio
    async def test_timing_score_peak_hour(self, anomaly_service, sample_patterns):
        """Events during peak hours should have low timing scores."""
        # Hour 08 has 15 events (above average)
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 15, 8, 30, tzinfo=timezone.utc),
            objects_detected=["person"],
        )
        assert result.timing_score < 0.3, "Peak hour should have low timing score"

    @pytest.mark.asyncio
    async def test_timing_score_quiet_hour(self, anomaly_service, sample_patterns):
        """Events during quiet hours should have high timing scores."""
        # Hour 03 has 0 events (well below average)
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 15, 3, 30, tzinfo=timezone.utc),
            objects_detected=["person"],
        )
        assert result.timing_score > 0.3, "Quiet hour should have higher timing score"

    @pytest.mark.asyncio
    async def test_timing_score_uniform_distribution(self, anomaly_service, sparse_patterns):
        """Uniform distribution should return 0 timing score."""
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sparse_patterns,
            event_timestamp=datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc),
            objects_detected=["person"],
        )
        assert result.timing_score == 0.0, "Uniform distribution should have zero timing score"


class TestDayScore:
    """Tests for day-of-week score calculation."""

    @pytest.mark.asyncio
    async def test_day_score_busy_day(self, anomaly_service, sample_patterns):
        """Events on busy days (Friday=4) should have low day scores."""
        # Friday (day 4) has 52 events (above average)
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 12, 12, 0, tzinfo=timezone.utc),  # Friday
            objects_detected=["person"],
        )
        assert result.day_score < 0.3, "Busy day should have low day score"

    @pytest.mark.asyncio
    async def test_day_score_quiet_day(self, anomaly_service, sample_patterns):
        """Events on quiet days (Sunday=6) should have higher day scores."""
        # Sunday (day 6) has 25 events (below average)
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 14, 12, 0, tzinfo=timezone.utc),  # Sunday
            objects_detected=["person"],
        )
        assert result.day_score > 0.1, "Quiet day should have higher day score"


class TestObjectScore:
    """Tests for object type score calculation."""

    @pytest.mark.asyncio
    async def test_object_score_common_object(self, anomaly_service, sample_patterns):
        """Common objects (person=70%) should have low object scores."""
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            objects_detected=["person"],
        )
        assert result.object_score < 0.2, "Common object should have low object score"

    @pytest.mark.asyncio
    async def test_object_score_rare_object(self, anomaly_service, sample_patterns):
        """Rare objects (<5%) should have moderate object scores."""
        # animal is 8/215 = 3.7% (rare)
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            objects_detected=["animal"],
        )
        assert result.object_score >= 0.3, "Rare object should have moderate object score"

    @pytest.mark.asyncio
    async def test_object_score_novel_object(self, anomaly_service, sample_patterns):
        """Novel objects (never seen) should have high object scores."""
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            objects_detected=["bear"],  # Never seen before
        )
        assert result.object_score >= 0.5, "Novel object should have high object score"

    @pytest.mark.asyncio
    async def test_object_score_multiple_objects(self, anomaly_service, sample_patterns):
        """Multiple unusual objects should accumulate scores."""
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            objects_detected=["bear", "wolf"],  # Two novel objects
        )
        assert result.object_score == 1.0, "Multiple novel objects should max out score"

    @pytest.mark.asyncio
    async def test_object_score_empty_objects(self, anomaly_service, sample_patterns):
        """Empty object list should return 0 object score."""
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            objects_detected=[],
        )
        assert result.object_score == 0.0, "Empty objects should have zero object score"


class TestSeverityClassification:
    """Tests for severity classification."""

    @pytest.mark.asyncio
    async def test_severity_low(self, anomaly_service, sample_patterns):
        """Low scores should be classified as 'low' severity."""
        # Peak hour, busy day, common object = low score
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 12, 8, 30, tzinfo=timezone.utc),  # Friday 8:30 AM
            objects_detected=["person"],
        )
        assert result.severity == "low", f"Expected low severity, got {result.severity} (score={result.total})"

    @pytest.mark.asyncio
    async def test_severity_high(self, anomaly_service, sample_patterns):
        """High scores should be classified as 'high' severity."""
        # Quiet hour, quiet day, novel objects = high score
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 14, 3, 30, tzinfo=timezone.utc),  # Sunday 3:30 AM
            objects_detected=["bear", "wolf"],
        )
        assert result.severity == "high", f"Expected high severity, got {result.severity} (score={result.total})"


class TestNoBaseline:
    """Tests for cases with no baseline data."""

    @pytest.mark.asyncio
    async def test_no_patterns_returns_neutral(self, anomaly_service):
        """No patterns should return neutral score."""
        result = await anomaly_service.calculate_anomaly_score(
            patterns=None,
            event_timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            objects_detected=["person"],
        )
        assert result.total == 0.0, "No patterns should return zero score"
        assert result.has_baseline is False
        assert result.severity == "low"

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_neutral(self, anomaly_service):
        """Insufficient data patterns should return neutral score."""
        patterns = PatternData(
            camera_id="test-camera",
            hourly_distribution={},
            daily_distribution={},
            peak_hours=[],
            quiet_hours=[],
            average_events_per_day=0.0,
            last_calculated_at=datetime.now(timezone.utc),
            calculation_window_days=7,
            insufficient_data=True,
            object_type_distribution=None,
            dominant_object_type=None,
        )
        result = await anomaly_service.calculate_anomaly_score(
            patterns=patterns,
            event_timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            objects_detected=["person"],
        )
        assert result.total == 0.0, "Insufficient data should return zero score"
        assert result.has_baseline is False


class TestWeightedCombination:
    """Tests for weighted score combination."""

    @pytest.mark.asyncio
    async def test_weights_sum_to_one(self, anomaly_service):
        """Verify scoring weights sum to 1.0."""
        total_weight = (
            anomaly_service.TIMING_WEIGHT +
            anomaly_service.DAY_WEIGHT +
            anomaly_service.OBJECT_WEIGHT
        )
        assert total_weight == 1.0, f"Weights should sum to 1.0, got {total_weight}"

    @pytest.mark.asyncio
    async def test_score_bounded(self, anomaly_service, sample_patterns):
        """Scores should always be between 0.0 and 1.0."""
        # Test edge case that combines multiple factors
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=datetime(2024, 1, 15, 3, 0, tzinfo=timezone.utc),
            objects_detected=["bear", "wolf", "lion"],
        )
        assert 0.0 <= result.total <= 1.0, f"Score {result.total} out of bounds"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("timestamp,objects", [
        (datetime(2024, 1, 15, 3, 0, tzinfo=timezone.utc), ["bear", "wolf", "lion"]),  # Max anomaly
        (datetime(2024, 1, 12, 8, 0, tzinfo=timezone.utc), ["person"]),  # Min anomaly
        (datetime(2024, 1, 14, 3, 0, tzinfo=timezone.utc), []),  # Mixed
        (datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc), ["vehicle"]),  # Midday
        (datetime(2024, 1, 12, 0, 0, tzinfo=timezone.utc), ["dog", "cat"]),  # Midnight
    ])
    async def test_score_edge_cases(self, anomaly_service, sample_patterns, timestamp, objects):
        """Test various edge cases produce valid scores."""
        result = await anomaly_service.calculate_anomaly_score(
            patterns=sample_patterns,
            event_timestamp=timestamp,
            objects_detected=objects,
        )
        assert 0.0 <= result.total <= 1.0, f"Score {result.total} out of bounds for {objects}"


class TestEventScoring:
    """Tests for full event scoring with persistence."""

    @pytest.mark.asyncio
    async def test_score_event_persists(self, anomaly_service):
        """Score should be persisted to event record."""
        # Mock event
        mock_event = MagicMock()
        mock_event.id = "event-123"
        mock_event.camera_id = "camera-456"
        mock_event.timestamp = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        mock_event.objects_detected = json.dumps(["person"])
        mock_event.anomaly_score = None

        # Mock db session
        mock_db = MagicMock()

        # Mock pattern service
        with patch.object(
            anomaly_service._pattern_service,
            'get_patterns',
            new_callable=AsyncMock
        ) as mock_get_patterns:
            mock_get_patterns.return_value = PatternData(
                camera_id="camera-456",
                hourly_distribution={"12": 10},
                daily_distribution={"0": 20},
                peak_hours=[],
                quiet_hours=[],
                average_events_per_day=10.0,
                last_calculated_at=datetime.now(timezone.utc),
                calculation_window_days=30,
                insufficient_data=False,
                object_type_distribution={"person": 100},
                dominant_object_type="person",
            )

            result = await anomaly_service.score_event(mock_db, mock_event)

            # Verify score was set on event
            assert mock_event.anomaly_score is not None
            assert mock_db.commit.called
            assert result is not None
            assert result.has_baseline is True

    @pytest.mark.asyncio
    async def test_score_event_handles_json_parse_error(self, anomaly_service):
        """Should handle invalid JSON in objects_detected."""
        mock_event = MagicMock()
        mock_event.id = "event-123"
        mock_event.camera_id = "camera-456"
        mock_event.timestamp = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        mock_event.objects_detected = "invalid json"  # Invalid JSON
        mock_event.anomaly_score = None

        mock_db = MagicMock()

        with patch.object(
            anomaly_service._pattern_service,
            'get_patterns',
            new_callable=AsyncMock
        ) as mock_get_patterns:
            mock_get_patterns.return_value = None  # No patterns

            result = await anomaly_service.score_event(mock_db, mock_event)

            # Should succeed with empty objects list
            assert result is not None
            assert result.total == 0.0  # No baseline

    @pytest.mark.asyncio
    async def test_score_event_handles_exception(self, anomaly_service):
        """Should handle exceptions gracefully."""
        mock_event = MagicMock()
        mock_event.id = "event-123"
        mock_event.camera_id = "camera-456"

        mock_db = MagicMock()

        with patch.object(
            anomaly_service._pattern_service,
            'get_patterns',
            new_callable=AsyncMock
        ) as mock_get_patterns:
            mock_get_patterns.side_effect = Exception("Database error")

            result = await anomaly_service.score_event(mock_db, mock_event)

            # Should return None on exception
            assert result is None
            assert mock_db.rollback.called


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_anomaly_scoring_service_singleton(self):
        """Should return same instance."""
        reset_anomaly_scoring_service()
        service1 = get_anomaly_scoring_service()
        service2 = get_anomaly_scoring_service()
        assert service1 is service2

    def test_reset_anomaly_scoring_service(self):
        """Should reset singleton."""
        reset_anomaly_scoring_service()
        service1 = get_anomaly_scoring_service()
        reset_anomaly_scoring_service()
        service2 = get_anomaly_scoring_service()
        assert service1 is not service2
