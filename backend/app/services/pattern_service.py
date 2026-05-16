"""
Pattern Service for Activity Pattern Detection (Story P4-3.5)

This module provides time-based activity pattern analysis for cameras.
Patterns are pre-calculated periodically and persisted for fast lookup (<50ms)
during event processing.

Architecture:
    - Calculates hourly and daily event distributions per camera
    - Identifies peak hours (above-average activity) and quiet hours (minimal activity)
    - Persists patterns to camera_activity_patterns table
    - Provides timing analysis for AI context enhancement

Flow:
    Historical Events (30 days) -> PatternService.recalculate_patterns()
                                                    |
                                                    v
                                   CameraActivityPattern (persisted)
                                                    |
                                                    v
    Event Processing -> PatternService.is_typical_timing() -> TimingAnalysisResult

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import json
import logging
from app.core.decorators import singleton
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import statistics

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.camera_activity_pattern import CameraActivityPattern
from app.models.event import Event
from app.models.camera import Camera

logger = logging.getLogger(__name__)


@dataclass
class PatternData:
    """Structured pattern data for API responses."""
    camera_id: str
    hourly_distribution: dict[str, int]
    daily_distribution: dict[str, int]
    peak_hours: list[str]
    quiet_hours: list[str]
    average_events_per_day: float
    last_calculated_at: datetime
    calculation_window_days: int
    insufficient_data: bool = False
    object_type_distribution: Optional[dict[str, int]] = None
    dominant_object_type: Optional[str] = None


@dataclass
class TimingAnalysisResult:
    """Result from timing analysis."""
    is_typical: Optional[bool]  # None if insufficient data
    confidence: float           # 0.0 to 1.0
    reason: str                 # Human-readable explanation


@singleton
class PatternService:
    """
    Analyze and store activity patterns for cameras.

    This service calculates time-based patterns from historical event data
    and provides timing analysis for AI context enhancement.

    Attributes:
        MIN_EVENTS_FOR_PATTERNS: Minimum events required for meaningful patterns (10)
        MIN_DAYS_FOR_PATTERNS: Minimum days of history for meaningful patterns (7)
        DEFAULT_WINDOW_DAYS: Default time window for pattern calculation (30 days)
    """

    MIN_EVENTS_FOR_PATTERNS = 10
    MIN_DAYS_FOR_PATTERNS = 7
    DEFAULT_WINDOW_DAYS = 30

    def __init__(self):
        """Initialize PatternService."""
        logger.info(
            "PatternService initialized",
            extra={"event_type": "pattern_service_init"}
        )

    async def get_patterns(
        self, db: Session, camera_id: str
    ) -> Optional[PatternData]:
        """
        Get activity patterns for a camera.

        Retrieves pre-calculated patterns from the database. Returns None if
        no patterns exist (camera has insufficient history or patterns haven't
        been calculated yet).

        Args:
            db: SQLAlchemy database session
            camera_id: UUID of the camera

        Returns:
            PatternData with activity patterns, or None if no patterns exist
        """
        start_time = time.time()

        pattern = db.query(CameraActivityPattern).filter_by(
            camera_id=camera_id
        ).first()

        lookup_time_ms = (time.time() - start_time) * 1000

        if not pattern:
            logger.debug(
                f"No patterns found for camera {camera_id}",
                extra={
                    "camera_id": camera_id,
                    "lookup_time_ms": round(lookup_time_ms, 2)
                }
            )
            return None

        logger.debug(
            f"Patterns retrieved for camera {camera_id} in {lookup_time_ms:.2f}ms",
            extra={
                "camera_id": camera_id,
                "lookup_time_ms": round(lookup_time_ms, 2),
                "avg_events_per_day": pattern.average_events_per_day,
            }
        )

        # Parse object type distribution and compute dominant type
        object_type_dist = None
        dominant_type = None
        if pattern.object_type_distribution:
            object_type_dist = json.loads(pattern.object_type_distribution)
            if object_type_dist:
                dominant_type = max(object_type_dist, key=object_type_dist.get)

        return PatternData(
            camera_id=camera_id,
            hourly_distribution=json.loads(pattern.hourly_distribution),
            daily_distribution=json.loads(pattern.daily_distribution),
            peak_hours=json.loads(pattern.peak_hours),
            quiet_hours=json.loads(pattern.quiet_hours),
            average_events_per_day=pattern.average_events_per_day,
            last_calculated_at=pattern.last_calculated_at,
            calculation_window_days=pattern.calculation_window_days,
            insufficient_data=False,
            object_type_distribution=object_type_dist,
            dominant_object_type=dominant_type,
        )

    async def is_typical_timing(
        self, db: Session, camera_id: str, timestamp: datetime
    ) -> TimingAnalysisResult:
        """
        Determine if the given timestamp represents typical activity timing.

        Compares the event time against the camera's historical patterns to
        determine if activity at this time is typical or unusual.

        Args:
            db: SQLAlchemy database session
            camera_id: UUID of the camera
            timestamp: Time of the event to analyze

        Returns:
            TimingAnalysisResult with is_typical, confidence, and reason
        """
        pattern = await self.get_patterns(db, camera_id)

        if not pattern:
            return TimingAnalysisResult(
                is_typical=None,
                confidence=0.0,
                reason="Insufficient history for timing analysis"
            )

        # Get current hour (zero-padded string) and day of week
        hour = str(timestamp.hour).zfill(2)
        day_of_week = str(timestamp.weekday())  # 0=Monday

        # Check if current hour is in quiet hours (highest priority - unusual)
        if hour in pattern.quiet_hours:
            return TimingAnalysisResult(
                is_typical=False,
                confidence=0.8,
                reason=f"This camera is normally quiet at {timestamp.strftime('%H:%M')}"
            )

        # Check if current hour is in peak hours (typical)
        if hour in pattern.peak_hours:
            return TimingAnalysisResult(
                is_typical=True,
                confidence=0.9,
                reason="Typical activity time for this camera"
            )

        # Check daily pattern
        daily_counts = list(pattern.daily_distribution.values())
        if daily_counts:
            daily_avg = sum(daily_counts) / 7
            current_day_count = pattern.daily_distribution.get(day_of_week, 0)

            # If this day has less than half the average activity
            if daily_avg > 0 and current_day_count < daily_avg * 0.5:
                return TimingAnalysisResult(
                    is_typical=False,
                    confidence=0.6,
                    reason=f"Less typical on {timestamp.strftime('%A')}s"
                )

        # Default: normal activity period
        return TimingAnalysisResult(
            is_typical=True,
            confidence=0.5,
            reason="Normal activity period"
        )

    async def recalculate_patterns(
        self,
        db: Session,
        camera_id: str,
        window_days: int = DEFAULT_WINDOW_DAYS,
        force: bool = False
    ) -> Optional[CameraActivityPattern]:
        """
        Recalculate and persist activity patterns for a camera.

        Analyzes historical events within the time window and calculates
        hourly/daily distributions, peak hours, and quiet hours.

        Args:
            db: SQLAlchemy database session
            camera_id: UUID of the camera
            window_days: Number of days to analyze (default: 30)
            force: If True, recalculate even if recently calculated

        Returns:
            Updated CameraActivityPattern, or None if insufficient data
        """
        start_time = time.time()

        # Check if camera exists
        camera = db.query(Camera).filter_by(id=camera_id).first()
        if not camera:
            logger.warning(
                f"Camera not found for pattern calculation: {camera_id}",
                extra={"camera_id": camera_id}
            )
            return None

        # Check if patterns were recently calculated (skip if within last hour unless forced)
        existing_pattern = db.query(CameraActivityPattern).filter_by(
            camera_id=camera_id
        ).first()

        if existing_pattern and not force:
            time_since_calc = datetime.now(timezone.utc) - existing_pattern.last_calculated_at.replace(tzinfo=timezone.utc)
            if time_since_calc < timedelta(hours=1):
                logger.debug(
                    f"Skipping pattern recalculation for camera {camera_id} - recently calculated",
                    extra={
                        "camera_id": camera_id,
                        "last_calculated": existing_pattern.last_calculated_at.isoformat(),
                        "minutes_ago": round(time_since_calc.total_seconds() / 60, 1)
                    }
                )
                return existing_pattern

        # Query events within time window
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        events = db.query(Event).filter(
            Event.camera_id == camera_id,
            Event.timestamp >= cutoff
        ).all()

        # Check minimum thresholds
        if len(events) < self.MIN_EVENTS_FOR_PATTERNS:
            logger.info(
                f"Insufficient events for pattern calculation: {len(events)} events for camera {camera_id}",
                extra={
                    "camera_id": camera_id,
                    "event_count": len(events),
                    "min_required": self.MIN_EVENTS_FOR_PATTERNS
                }
            )
            return None

        # Check if we have enough days of history
        if events:
            first_event = min(events, key=lambda e: e.timestamp)
            days_of_history = (datetime.now(timezone.utc) - first_event.timestamp.replace(tzinfo=timezone.utc)).days
            if days_of_history < self.MIN_DAYS_FOR_PATTERNS:
                logger.info(
                    f"Insufficient history for pattern calculation: {days_of_history} days for camera {camera_id}",
                    extra={
                        "camera_id": camera_id,
                        "days_of_history": days_of_history,
                        "min_required": self.MIN_DAYS_FOR_PATTERNS
                    }
                )
                return None

        # Calculate distributions
        hourly = self._calculate_hourly_distribution(events)
        daily = self._calculate_daily_distribution(events)
        peak = self._calculate_peak_hours(hourly)
        quiet = self._calculate_quiet_hours(hourly)
        object_types = self._calculate_object_type_distribution(events)
        avg_per_day = len(events) / window_days

        # Upsert pattern record
        now = datetime.now(timezone.utc)

        if existing_pattern:
            existing_pattern.hourly_distribution = json.dumps(hourly)
            existing_pattern.daily_distribution = json.dumps(daily)
            existing_pattern.peak_hours = json.dumps(peak)
            existing_pattern.quiet_hours = json.dumps(quiet)
            existing_pattern.object_type_distribution = json.dumps(object_types) if object_types else None
            existing_pattern.average_events_per_day = avg_per_day
            existing_pattern.calculation_window_days = window_days
            existing_pattern.last_calculated_at = now
            existing_pattern.updated_at = now
            pattern = existing_pattern
        else:
            pattern = CameraActivityPattern(
                camera_id=camera_id,
                hourly_distribution=json.dumps(hourly),
                daily_distribution=json.dumps(daily),
                peak_hours=json.dumps(peak),
                quiet_hours=json.dumps(quiet),
                object_type_distribution=json.dumps(object_types) if object_types else None,
                average_events_per_day=avg_per_day,
                calculation_window_days=window_days,
                last_calculated_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(pattern)

        db.commit()
        db.refresh(pattern)

        calc_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Pattern calculation complete for camera {camera_id}",
            extra={
                "event_type": "pattern_calculation_complete",
                "camera_id": camera_id,
                "event_count": len(events),
                "window_days": window_days,
                "avg_events_per_day": round(avg_per_day, 2),
                "peak_hours_count": len(peak),
                "quiet_hours_count": len(quiet),
                "calc_time_ms": round(calc_time_ms, 2),
            }
        )

        return pattern

    async def recalculate_all_patterns(
        self,
        db: Session,
        window_days: int = DEFAULT_WINDOW_DAYS
    ) -> dict:
        """
        Recalculate patterns for all cameras.

        Useful for batch updates scheduled by the pattern recalculation job.

        Args:
            db: SQLAlchemy database session
            window_days: Number of days to analyze (default: 30)

        Returns:
            Dictionary with calculation results:
            - total_cameras: Number of cameras processed
            - patterns_calculated: Number of successful calculations
            - patterns_skipped: Number skipped (insufficient data)
            - elapsed_ms: Total time in milliseconds
        """
        start_time = time.time()

        # Get all cameras
        cameras = db.query(Camera).filter(Camera.is_enabled == True).all()

        total_cameras = len(cameras)
        patterns_calculated = 0
        patterns_skipped = 0

        for camera in cameras:
            try:
                pattern = await self.recalculate_patterns(
                    db=db,
                    camera_id=camera.id,
                    window_days=window_days,
                    force=False  # Respect rate limiting
                )
                if pattern:
                    patterns_calculated += 1
                else:
                    patterns_skipped += 1
            except Exception as e:
                logger.error(
                    f"Failed to calculate patterns for camera {camera.id}: {e}",
                    extra={"camera_id": camera.id, "error": str(e)}
                )
                patterns_skipped += 1

        elapsed_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Batch pattern calculation complete",
            extra={
                "event_type": "batch_pattern_calculation_complete",
                "total_cameras": total_cameras,
                "patterns_calculated": patterns_calculated,
                "patterns_skipped": patterns_skipped,
                "elapsed_ms": round(elapsed_ms, 2),
            }
        )

        return {
            "total_cameras": total_cameras,
            "patterns_calculated": patterns_calculated,
            "patterns_skipped": patterns_skipped,
            "elapsed_ms": round(elapsed_ms, 2),
        }

    def _calculate_hourly_distribution(self, events: list[Event]) -> dict[str, int]:
        """
        Calculate events per hour (0-23) across all days.

        Args:
            events: List of events to analyze

        Returns:
            Dictionary mapping hour (zero-padded string) to event count
        """
        hourly = {str(h).zfill(2): 0 for h in range(24)}

        for event in events:
            hour = str(event.timestamp.hour).zfill(2)
            hourly[hour] = hourly.get(hour, 0) + 1

        return hourly

    def _calculate_daily_distribution(self, events: list[Event]) -> dict[str, int]:
        """
        Calculate events per day-of-week (0-6, Monday=0).

        Args:
            events: List of events to analyze

        Returns:
            Dictionary mapping day-of-week (string) to event count
        """
        daily = {str(d): 0 for d in range(7)}

        for event in events:
            day = str(event.timestamp.weekday())
            daily[day] = daily.get(day, 0) + 1

        return daily

    def _calculate_peak_hours(self, hourly_distribution: dict[str, int]) -> list[str]:
        """
        Identify peak activity hours (above mean + 0.5 * std_dev).

        Args:
            hourly_distribution: Dictionary of hour -> event count

        Returns:
            List of peak hours (zero-padded strings, e.g., ["09", "14", "17"])
        """
        counts = list(hourly_distribution.values())

        if not counts or sum(counts) == 0:
            return []

        mean = statistics.mean(counts)

        # Handle edge case where all values are the same
        if len(set(counts)) == 1:
            return []

        try:
            std_dev = statistics.stdev(counts)
        except statistics.StatisticsError:
            return []

        threshold = mean + (0.5 * std_dev)

        peak_hours = [
            hour for hour, count in hourly_distribution.items()
            if count > threshold
        ]

        return sorted(peak_hours)

    def _calculate_quiet_hours(self, hourly_distribution: dict[str, int]) -> list[str]:
        """
        Identify quiet hours (below 10% of max hour activity).

        Args:
            hourly_distribution: Dictionary of hour -> event count

        Returns:
            List of quiet hours (zero-padded strings, e.g., ["02", "03", "04"])
        """
        counts = list(hourly_distribution.values())

        if not counts or max(counts) == 0:
            # If no events, all hours are quiet
            return [str(h).zfill(2) for h in range(24)]

        max_count = max(counts)
        threshold = max_count * 0.1

        quiet_hours = [
            hour for hour, count in hourly_distribution.items()
            if count < threshold
        ]

        return sorted(quiet_hours)

    def _calculate_object_type_distribution(self, events: list[Event]) -> dict[str, int]:
        """
        Calculate frequency of each detected object type.

        Args:
            events: List of events to analyze

        Returns:
            Dictionary mapping object type to count, e.g., {"person": 150, "vehicle": 45}
        """
        object_types: dict[str, int] = {}

        for event in events:
            if event.objects_detected:
                try:
                    objects = json.loads(event.objects_detected)
                    if isinstance(objects, list):
                        for obj_type in objects:
                            if obj_type and isinstance(obj_type, str):
                                object_types[obj_type] = object_types.get(obj_type, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    # Skip events with invalid JSON
                    continue

        return object_types

    async def update_baseline_incremental(
        self,
        db: Session,
        camera_id: str,
        event: Event
    ) -> Optional[CameraActivityPattern]:
        """
        Incrementally update activity baseline for a camera when a new event occurs.

        This method provides fast (<50ms target) incremental updates to the baseline
        without requiring a full recalculation. It updates hourly, daily, and object
        type distributions atomically.

        Args:
            db: SQLAlchemy database session
            camera_id: UUID of the camera
            event: The new event that triggered this update

        Returns:
            Updated CameraActivityPattern, or None if update failed
        """
        start_time = time.time()

        try:
            # Get existing pattern or return None (incremental updates only work if pattern exists)
            pattern = db.query(CameraActivityPattern).filter_by(
                camera_id=camera_id
            ).first()

            if not pattern:
                # No existing pattern - incremental update not applicable
                # Full recalculation should be done via recalculate_patterns()
                logger.debug(
                    f"No existing pattern for camera {camera_id}, skipping incremental update",
                    extra={"camera_id": camera_id}
                )
                return None

            # Update hourly distribution
            hourly = json.loads(pattern.hourly_distribution)
            hour_key = str(event.timestamp.hour).zfill(2)
            hourly[hour_key] = hourly.get(hour_key, 0) + 1
            pattern.hourly_distribution = json.dumps(hourly)

            # Update daily distribution
            daily = json.loads(pattern.daily_distribution)
            day_key = str(event.timestamp.weekday())
            daily[day_key] = daily.get(day_key, 0) + 1
            pattern.daily_distribution = json.dumps(daily)

            # Update object type distribution
            if event.objects_detected:
                try:
                    objects = json.loads(event.objects_detected)
                    if isinstance(objects, list):
                        object_types = json.loads(pattern.object_type_distribution) if pattern.object_type_distribution else {}
                        for obj_type in objects:
                            if obj_type and isinstance(obj_type, str):
                                object_types[obj_type] = object_types.get(obj_type, 0) + 1
                        pattern.object_type_distribution = json.dumps(object_types)
                except (json.JSONDecodeError, TypeError):
                    pass  # Skip invalid JSON

            # Recalculate peak and quiet hours (lightweight calculation)
            pattern.peak_hours = json.dumps(self._calculate_peak_hours(hourly))
            pattern.quiet_hours = json.dumps(self._calculate_quiet_hours(hourly))

            # Update average events per day (approximate - based on total count)
            total_events = sum(hourly.values())
            if pattern.calculation_window_days > 0:
                pattern.average_events_per_day = total_events / pattern.calculation_window_days

            pattern.updated_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(pattern)

            update_time_ms = (time.time() - start_time) * 1000

            logger.debug(
                f"Incremental baseline update for camera {camera_id} in {update_time_ms:.2f}ms",
                extra={
                    "camera_id": camera_id,
                    "update_time_ms": round(update_time_ms, 2),
                    "total_events": total_events,
                }
            )

            return pattern

        except Exception as e:
            logger.error(
                f"Failed to update baseline incrementally for camera {camera_id}: {e}",
                extra={"camera_id": camera_id, "error": str(e)}
            )
            db.rollback()
            return None


# Backward compatible thin getter (delegates to @singleton decorator)
def get_pattern_service() -> PatternService:
    """
    Get the global PatternService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer PatternService() directly.
    """
    return PatternService()


def reset_pattern_service() -> None:
    """Reset the global PatternService instance (for testing)."""
    PatternService._reset_instance()

    return _pattern_service


def reset_pattern_service() -> None:
    """
    Reset the global PatternService instance.

    Useful for testing to ensure a fresh instance.
    """
    PatternService._reset_instance()
