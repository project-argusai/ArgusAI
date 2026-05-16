"""
Anomaly Scoring Service (Story P4-7.2)

This module provides anomaly detection by scoring events based on how much
they deviate from a camera's established baseline patterns.

Architecture:
    - Uses baseline patterns from PatternService (P4-7.1)
    - Calculates timing, day-of-week, and object type anomaly scores
    - Combines scores with configurable weights
    - Classifies events into low/medium/high severity

Flow:
    New Event -> AnomalyScoringService.calculate_anomaly_score()
                                    |
                                    v
                    PatternService.get_patterns() -> baseline
                                    |
                                    v
                    Calculate timing_score, day_score, object_score
                                    |
                                    v
                    Combine with weights -> total_score + severity

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import json
import logging
from app.core.decorators import singleton
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.event import Event
from app.services.pattern_service import PatternService, PatternData, get_pattern_service

logger = logging.getLogger(__name__)


@dataclass
class AnomalyScoreResult:
    """Result from anomaly scoring calculation."""
    total: float  # Combined score 0.0-1.0
    timing_score: float  # Timing component 0.0-1.0
    day_score: float  # Day-of-week component 0.0-1.0
    object_score: float  # Object type component 0.0-1.0
    severity: str  # 'low', 'medium', 'high'
    has_baseline: bool  # False if no baseline data available


@singleton
class AnomalyScoringService:
    """
    Calculate anomaly scores for events based on baseline patterns.

    Scores indicate how unusual an event is compared to historical patterns:
    - 0.0 = completely normal/expected
    - 1.0 = highly anomalous/unusual

    Scoring Components:
        - Timing score: Is this hour unusual for events?
        - Day score: Is this day-of-week unusual?
        - Object score: Are the detected objects unusual?

    Attributes:
        TIMING_WEIGHT: Weight for timing component (default: 0.4)
        DAY_WEIGHT: Weight for day-of-week component (default: 0.2)
        OBJECT_WEIGHT: Weight for object type component (default: 0.4)
        LOW_THRESHOLD: Score below this is 'low' severity (default: 0.3)
        HIGH_THRESHOLD: Score above this is 'high' severity (default: 0.6)
    """

    # Scoring weights (sum should equal 1.0)
    TIMING_WEIGHT = 0.4
    DAY_WEIGHT = 0.2
    OBJECT_WEIGHT = 0.4

    # Severity thresholds
    LOW_THRESHOLD = 0.3
    HIGH_THRESHOLD = 0.6

    def __init__(self):
        """Initialize AnomalyScoringService."""
        self._pattern_service = get_pattern_service()
        logger.info(
            "AnomalyScoringService initialized",
            extra={"event_type": "anomaly_service_init"}
        )

    async def calculate_anomaly_score(
        self,
        patterns: Optional[PatternData],
        event_timestamp: datetime,
        objects_detected: list[str]
    ) -> AnomalyScoreResult:
        """
        Calculate anomaly score for an event based on baseline patterns.

        Args:
            patterns: Baseline patterns from PatternService (None if no baseline)
            event_timestamp: When the event occurred
            objects_detected: List of object types detected in event

        Returns:
            AnomalyScoreResult with total score, component scores, and severity
        """
        # No baseline = return neutral score
        if patterns is None or patterns.insufficient_data:
            logger.debug(
                "No baseline available, returning neutral score",
                extra={"has_patterns": patterns is not None}
            )
            return AnomalyScoreResult(
                total=0.0,
                timing_score=0.0,
                day_score=0.0,
                object_score=0.0,
                severity="low",
                has_baseline=False
            )

        # Calculate component scores
        timing_score = self._calculate_timing_score(
            patterns.hourly_distribution,
            event_timestamp.hour
        )
        day_score = self._calculate_day_score(
            patterns.daily_distribution,
            event_timestamp.weekday()
        )
        object_score = self._calculate_object_score(
            patterns.object_type_distribution,
            objects_detected
        )

        # Combine with weights
        total = (
            timing_score * self.TIMING_WEIGHT +
            day_score * self.DAY_WEIGHT +
            object_score * self.OBJECT_WEIGHT
        )

        # Clamp to [0.0, 1.0]
        total = max(0.0, min(1.0, total))

        # Classify severity
        severity = self._classify_severity(total)

        logger.debug(
            f"Anomaly score calculated: {total:.3f} ({severity})",
            extra={
                "total_score": round(total, 3),
                "timing_score": round(timing_score, 3),
                "day_score": round(day_score, 3),
                "object_score": round(object_score, 3),
                "severity": severity
            }
        )

        return AnomalyScoreResult(
            total=round(total, 3),
            timing_score=round(timing_score, 3),
            day_score=round(day_score, 3),
            object_score=round(object_score, 3),
            severity=severity,
            has_baseline=True
        )

    async def score_event(
        self,
        db: Session,
        event: Event
    ) -> Optional[AnomalyScoreResult]:
        """
        Calculate and persist anomaly score for an event.

        Args:
            db: SQLAlchemy database session
            event: Event to score

        Returns:
            AnomalyScoreResult, or None if scoring failed
        """
        try:
            # Get baseline patterns for camera
            patterns = await self._pattern_service.get_patterns(db, event.camera_id)

            # Parse objects detected
            objects_detected = []
            if event.objects_detected:
                try:
                    objects_detected = json.loads(event.objects_detected)
                    if not isinstance(objects_detected, list):
                        objects_detected = []
                except (json.JSONDecodeError, TypeError):
                    objects_detected = []

            # Calculate score
            result = await self.calculate_anomaly_score(
                patterns,
                event.timestamp,
                objects_detected
            )

            # Persist score to event
            event.anomaly_score = result.total
            db.commit()

            logger.info(
                f"Event {event.id} scored: {result.total:.3f} ({result.severity})",
                extra={
                    "event_id": event.id,
                    "camera_id": event.camera_id,
                    "anomaly_score": result.total,
                    "severity": result.severity,
                    "has_baseline": result.has_baseline
                }
            )

            return result

        except Exception as e:
            logger.error(
                f"Failed to score event {event.id}: {e}",
                extra={"event_id": event.id, "error": str(e)}
            )
            db.rollback()
            return None

    def _calculate_timing_score(
        self,
        hourly_distribution: dict[str, int],
        event_hour: int
    ) -> float:
        """
        Calculate timing anomaly score.

        Events during quiet hours (low activity) score higher.
        Events during peak hours (high activity) score lower.

        Args:
            hourly_distribution: Dict of hour -> event count
            event_hour: Hour of the event (0-23)

        Returns:
            Timing score 0.0-1.0
        """
        if not hourly_distribution:
            return 0.0

        # Get counts for all hours
        counts = list(hourly_distribution.values())

        if len(counts) < 2:
            return 0.0

        # Calculate statistics
        mean_count = statistics.mean(counts)
        try:
            std_count = statistics.stdev(counts)
        except statistics.StatisticsError:
            std_count = 0.0

        if std_count == 0:
            return 0.0  # Uniform distribution = no anomaly signal

        # Get count for event's hour
        hour_key = str(event_hour).zfill(2)
        event_count = hourly_distribution.get(hour_key, 0)

        # Calculate z-score (inverted: low count = high anomaly)
        # If event_count is much lower than mean, z_score is positive (unusual)
        z_score = (mean_count - event_count) / std_count

        # Normalize z-score to 0-1 (using 3 standard deviations as max)
        # z_score of 3 or higher maps to 1.0
        timing_score = min(1.0, max(0.0, z_score / 3))

        return timing_score

    def _calculate_day_score(
        self,
        daily_distribution: dict[str, int],
        event_day: int
    ) -> float:
        """
        Calculate day-of-week anomaly score.

        Events on low-activity days score higher.
        Events on high-activity days score lower.

        Args:
            daily_distribution: Dict of day (0-6) -> event count
            event_day: Day of week (0=Monday, 6=Sunday)

        Returns:
            Day score 0.0-1.0
        """
        if not daily_distribution:
            return 0.0

        # Get counts for all days
        counts = list(daily_distribution.values())

        if len(counts) < 2:
            return 0.0

        # Calculate statistics
        mean_count = statistics.mean(counts)
        try:
            std_count = statistics.stdev(counts)
        except statistics.StatisticsError:
            std_count = 0.0

        if std_count == 0:
            return 0.0  # Uniform distribution = no anomaly signal

        # Get count for event's day
        day_key = str(event_day)
        event_count = daily_distribution.get(day_key, 0)

        # Calculate z-score (inverted: low count = high anomaly)
        z_score = (mean_count - event_count) / std_count

        # Normalize z-score to 0-1
        day_score = min(1.0, max(0.0, z_score / 3))

        return day_score

    def _calculate_object_score(
        self,
        object_type_distribution: Optional[dict[str, int]],
        objects_detected: list[str]
    ) -> float:
        """
        Calculate object type anomaly score.

        Novel objects (not in baseline) score highly.
        Rare objects (<5% of baseline) score moderately.
        Common objects score low.

        Args:
            object_type_distribution: Dict of object type -> count
            objects_detected: List of objects detected in event

        Returns:
            Object score 0.0-1.0
        """
        if not objects_detected:
            return 0.0

        if not object_type_distribution:
            # No baseline = treat all objects as novel
            return min(1.0, len(objects_detected) * 0.3)

        total_objects = sum(object_type_distribution.values())
        if total_objects == 0:
            return min(1.0, len(objects_detected) * 0.3)

        object_score = 0.0

        for obj_type in objects_detected:
            if obj_type not in object_type_distribution:
                # Novel object (never seen before) - high anomaly
                object_score += 0.5
            else:
                # Calculate how common this object type is
                obj_count = object_type_distribution[obj_type]
                obj_pct = obj_count / total_objects

                if obj_pct < 0.05:
                    # Rare object (<5% of events) - moderate anomaly
                    object_score += 0.3
                elif obj_pct < 0.20:
                    # Uncommon object (5-20% of events) - small anomaly
                    object_score += 0.1
                # Common objects (>20%) contribute ~0

        # Cap at 1.0
        return min(1.0, object_score)

    def _classify_severity(self, score: float) -> str:
        """
        Classify anomaly score into severity level.

        Args:
            score: Anomaly score 0.0-1.0

        Returns:
            'low', 'medium', or 'high'
        """
        if score < self.LOW_THRESHOLD:
            return "low"
        elif score < self.HIGH_THRESHOLD:
            return "medium"
        else:
            return "high"


# Backward compatible thin getter (delegates to @singleton decorator)
def get_anomaly_scoring_service() -> AnomalyScoringService:
    """
    Get the global AnomalyScoringService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer AnomalyScoringService() directly.
    """
    return AnomalyScoringService()


def reset_anomaly_scoring_service() -> None:
    """Reset the global AnomalyScoringService instance (for testing)."""
    AnomalyScoringService._reset_instance()
