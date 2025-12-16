"""
Schedule Manager Service - Singleton service for detection schedule validation

Features:
- Time-based schedule validation (HH:MM format)
- Day-of-week filtering (0=Monday, 6=Sunday)
- Overnight schedule support (e.g., 22:00-06:00)
- Thread-safe singleton pattern
- Fail-open strategy (invalid config → always active)
"""
import json
import logging
import threading
from datetime import datetime, time
from typing import Optional

logger = logging.getLogger(__name__)


class ScheduleManager:
    """
    Singleton service for validating detection schedules

    Thread Safety:
    - Uses Lock for singleton instantiation
    - Stateless validation (no shared mutable state)

    Performance:
    - Target: <1ms per validation call
    - Uses Python datetime comparison (fast)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern: Only one instance exists"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize service (only runs once due to singleton pattern)"""
        if self._initialized:
            return

        self._initialized = True
        logger.info("ScheduleManager initialized (singleton)")

    def is_detection_active(
        self,
        camera_id: str,
        detection_schedule: Optional[str]
    ) -> bool:
        """
        Check if motion detection should be active based on schedule

        Args:
            camera_id: UUID of camera (for logging)
            detection_schedule: JSON string from Camera.detection_schedule or None

        Returns:
            True if detection should be active, False otherwise

        Logic:
            - If detection_schedule is None → return True (no schedule = always active)
            - If enabled=false → return True (schedule disabled = always active)
            - Check current day_of_week in days_of_week list (0=Mon, 6=Sun)
            - Check current time against time_ranges array (Phase 5: multiple ranges)
            - Supports legacy single range format (start_time/end_time at root)
            - Return True if day matches AND current time is within ANY range

        Performance:
            - Target: <1ms average execution time
            - Early exits for common cases (None, disabled)

        Examples:
            >>> # No schedule configured
            >>> manager.is_detection_active("cam-1", None)
            True

            >>> # Schedule disabled
            >>> schedule = '{"enabled": false, "days_of_week": [0,1,2,3,4], "start_time": "08:00", "end_time": "18:00"}'
            >>> manager.is_detection_active("cam-1", schedule)
            True

            >>> # Weekday 9am-5pm schedule (Monday 10:00am) - legacy format
            >>> schedule = '{"enabled": true, "days_of_week": [0,1,2,3,4], "start_time": "09:00", "end_time": "17:00"}'
            >>> manager.is_detection_active("cam-1", schedule)
            True  # (if current time is Monday 10:00)

            >>> # Multiple time ranges (Phase 5) - morning and evening
            >>> schedule = '{"enabled": true, "days_of_week": [0,1,2,3,4], "time_ranges": [{"start_time": "06:00", "end_time": "09:00"}, {"start_time": "18:00", "end_time": "22:00"}]}'
            >>> manager.is_detection_active("cam-1", schedule)
            True  # (if current time is Monday 07:00 or 19:00)

            >>> # Overnight schedule 22:00-06:00 (Tuesday 23:00)
            >>> schedule = '{"enabled": true, "days_of_week": [0,1,2,3,4], "start_time": "22:00", "end_time": "06:00"}'
            >>> manager.is_detection_active("cam-1", schedule)
            True  # (if current time is Tuesday 23:00)
        """

        # No schedule = always active (backward compatible)
        if not detection_schedule:
            logger.debug(f"Camera {camera_id}: No schedule configured, always active")
            return True

        try:
            # Parse JSON schedule
            schedule = json.loads(detection_schedule)

            # Schedule disabled = always active
            if not schedule.get('enabled', False):
                logger.debug(f"Camera {camera_id}: Schedule disabled, always active")
                return True

            # Get current day and time
            now = datetime.now()
            current_day = now.weekday()  # 0=Monday, 6=Sunday
            current_time = now.time()

            # Check day of week - support both 'days_of_week' (legacy) and 'days' (new format)
            days_of_week = schedule.get('days_of_week') or schedule.get('days', [])
            if not days_of_week:
                logger.warning(f"Camera {camera_id}: Schedule has no days configured, defaulting to always active")
                return True

            if current_day not in days_of_week:
                logger.debug(f"Camera {camera_id}: Current day {current_day} not in schedule days {days_of_week}")
                return False

            # Phase 5: Support multiple time ranges
            time_ranges = schedule.get('time_ranges')

            if time_ranges and isinstance(time_ranges, list) and len(time_ranges) > 0:
                # New format: multiple time ranges
                for i, range_obj in enumerate(time_ranges):
                    start_time_str = range_obj.get('start_time')
                    end_time_str = range_obj.get('end_time')

                    if not start_time_str or not end_time_str:
                        continue  # Skip invalid range entries

                    if self._is_time_in_range(current_time, start_time_str, end_time_str):
                        logger.debug(
                            f"Camera {camera_id}: Within schedule range {i+1} "
                            f"(day={current_day}, time={current_time.strftime('%H:%M')}, "
                            f"range={start_time_str}-{end_time_str})"
                        )
                        return True

                # Not in any range
                logger.debug(
                    f"Camera {camera_id}: Outside all {len(time_ranges)} schedule time ranges "
                    f"(current={current_time.strftime('%H:%M')})"
                )
                return False

            # Legacy format: single start_time/end_time at root level
            start_time_str = schedule.get('start_time')
            end_time_str = schedule.get('end_time')

            if not start_time_str or not end_time_str:
                logger.warning(f"Camera {camera_id}: Schedule missing start/end time, defaulting to always active")
                return True

            # For legacy format, check if time format is valid first
            start_time = self._parse_time(start_time_str)
            end_time = self._parse_time(end_time_str)

            if start_time is None or end_time is None:
                logger.warning(f"Camera {camera_id}: Invalid time format in schedule, defaulting to always active")
                return True

            if self._is_time_in_range(current_time, start_time_str, end_time_str):
                logger.debug(
                    f"Camera {camera_id}: Within schedule "
                    f"(day={current_day}, time={current_time.strftime('%H:%M')}, "
                    f"range={start_time_str}-{end_time_str})"
                )
                return True
            else:
                logger.debug(
                    f"Camera {camera_id}: Outside schedule time range "
                    f"(current={current_time.strftime('%H:%M')}, range={start_time_str}-{end_time_str})"
                )
                return False

        except json.JSONDecodeError as e:
            logger.error(f"Camera {camera_id}: Failed to parse schedule JSON: {e}")
            return True  # Fail open (graceful degradation)
        except Exception as e:
            logger.error(f"Camera {camera_id}: Unexpected error checking schedule: {e}", exc_info=True)
            return True  # Fail open (graceful degradation)

    def _is_time_in_range(
        self,
        current_time: time,
        start_time_str: str,
        end_time_str: str
    ) -> bool:
        """
        Check if current time falls within a time range

        Args:
            current_time: Current time object
            start_time_str: Start time string in HH:MM format
            end_time_str: End time string in HH:MM format

        Returns:
            True if current_time is within the range, False otherwise
            Handles overnight ranges (e.g., 22:00-06:00)
        """
        start_time = self._parse_time(start_time_str)
        end_time = self._parse_time(end_time_str)

        if start_time is None or end_time is None:
            return False

        # Check if current time is within range
        # Handle overnight schedules (e.g., 22:00-06:00)
        if start_time <= end_time:
            # Normal range (e.g., 09:00-17:00)
            return start_time <= current_time <= end_time
        else:
            # Overnight range (e.g., 22:00-06:00)
            # Current time is in range if:
            # - After start_time (e.g., 23:00 >= 22:00) OR
            # - Before end_time (e.g., 01:00 <= 06:00)
            return current_time >= start_time or current_time <= end_time

    def _parse_time(self, time_str: str) -> Optional[time]:
        """
        Parse time string in HH:MM format to datetime.time object

        Args:
            time_str: Time string in HH:MM format (24-hour)

        Returns:
            datetime.time object or None if invalid

        Examples:
            >>> manager._parse_time("09:00")
            time(9, 0)
            >>> manager._parse_time("23:59")
            time(23, 59)
            >>> manager._parse_time("invalid")
            None
        """
        try:
            hour, minute = time_str.split(':')
            return time(int(hour), int(minute))
        except (ValueError, AttributeError) as e:
            logger.error(f"Failed to parse time '{time_str}': {e}")
            return None


# Global singleton instance
schedule_manager = ScheduleManager()
