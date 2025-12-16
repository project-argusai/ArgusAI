"""Unit tests for ScheduleManager service"""
import pytest
import json
import time
from datetime import datetime, time as time_obj
from unittest.mock import patch
from app.services.schedule_manager import schedule_manager, ScheduleManager


class TestScheduleManager:
    """Test suite for ScheduleManager schedule validation logic"""

    def test_singleton_pattern(self):
        """Test that ScheduleManager follows singleton pattern"""
        instance1 = ScheduleManager()
        instance2 = ScheduleManager()

        assert instance1 is instance2
        assert instance1 is schedule_manager

    def test_no_schedule_returns_true(self):
        """Test that no schedule configured returns always active"""
        # Test with None
        result = schedule_manager.is_detection_active("test-cam", None)
        assert result is True

        # Test with empty string
        result = schedule_manager.is_detection_active("test-cam", "")
        assert result is True

    def test_schedule_disabled_returns_true(self):
        """Test that disabled schedule returns always active"""
        schedule = {
            "id": "schedule-1",
            "name": "Test Schedule",
            "days_of_week": [0, 1, 2, 3, 4],
            "start_time": "08:00",
            "end_time": "18:00",
            "enabled": False
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_day_match_time_match_returns_true(self, mock_datetime):
        """Test that matching day and time returns true"""
        # Monday 10:00am
        mock_datetime.now.return_value = datetime(2025, 11, 17, 10, 0)  # Monday

        schedule = {
            "id": "schedule-1",
            "name": "Weekday Business Hours",
            "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
            "start_time": "09:00",
            "end_time": "17:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_day_match_time_outside_returns_false(self, mock_datetime):
        """Test that matching day but outside time returns false"""
        # Monday 07:00am (before start time)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 7, 0)  # Monday 7am

        schedule = {
            "id": "schedule-1",
            "name": "Weekday Business Hours",
            "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
            "start_time": "09:00",
            "end_time": "17:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is False

    @patch('app.services.schedule_manager.datetime')
    def test_day_outside_returns_false(self, mock_datetime):
        """Test that non-matching day returns false regardless of time"""
        # Saturday 10:00am (not in Mon-Fri schedule)
        mock_datetime.now.return_value = datetime(2025, 11, 22, 10, 0)  # Saturday

        schedule = {
            "id": "schedule-1",
            "name": "Weekday Business Hours",
            "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
            "start_time": "09:00",
            "end_time": "17:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is False

    @patch('app.services.schedule_manager.datetime')
    def test_overnight_schedule_before_midnight(self, mock_datetime):
        """Test overnight schedule: time before midnight"""
        # Monday 23:00 (11pm)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 23, 0)  # Monday 11pm

        schedule = {
            "id": "schedule-1",
            "name": "Overnight Schedule",
            "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
            "start_time": "22:00",
            "end_time": "06:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_overnight_schedule_after_midnight(self, mock_datetime):
        """Test overnight schedule: time after midnight"""
        # Monday 01:00 (1am)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 1, 0)  # Monday 1am

        schedule = {
            "id": "schedule-1",
            "name": "Overnight Schedule",
            "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
            "start_time": "22:00",
            "end_time": "06:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_overnight_schedule_outside_range(self, mock_datetime):
        """Test overnight schedule: time outside range"""
        # Monday 12:00pm (noon)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 12, 0)  # Monday noon

        schedule = {
            "id": "schedule-1",
            "name": "Overnight Schedule",
            "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
            "start_time": "22:00",
            "end_time": "06:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is False

    @patch('app.services.schedule_manager.datetime')
    def test_midnight_exact(self, mock_datetime):
        """Test that midnight exactly is handled correctly"""
        # Monday 00:00 (midnight)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 0, 0)  # Monday midnight

        schedule = {
            "id": "schedule-1",
            "name": "Overnight Schedule",
            "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
            "start_time": "23:00",
            "end_time": "01:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_boundary_start_time_inclusive(self, mock_datetime):
        """Test that start time is inclusive"""
        # Monday 09:00 (exactly at start time)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 9, 0)  # Monday 9am

        schedule = {
            "id": "schedule-1",
            "name": "Business Hours",
            "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
            "start_time": "09:00",
            "end_time": "17:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_boundary_end_time_inclusive(self, mock_datetime):
        """Test that end time is inclusive"""
        # Monday 17:00 (exactly at end time)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 17, 0)  # Monday 5pm

        schedule = {
            "id": "schedule-1",
            "name": "Business Hours",
            "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
            "start_time": "09:00",
            "end_time": "17:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    def test_invalid_json_returns_true(self):
        """Test that invalid JSON fails open (returns true)"""
        invalid_json = "{ this is not valid json }"

        result = schedule_manager.is_detection_active("test-cam", invalid_json)
        assert result is True  # Fail open (graceful degradation)

    @patch('app.services.schedule_manager.datetime')
    def test_multiple_days_selected(self, mock_datetime):
        """Test schedule with multiple specific days"""
        # Monday 10:00 (in schedule)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 10, 0)  # Monday

        schedule = {
            "id": "schedule-1",
            "name": "MWF Schedule",
            "days_of_week": [0, 2, 4],  # Mon, Wed, Fri
            "start_time": "08:00",
            "end_time": "18:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        # Monday - should be active
        assert schedule_manager.is_detection_active("test-cam", schedule_json) is True

        # Tuesday - should not be active
        mock_datetime.now.return_value = datetime(2025, 11, 18, 10, 0)  # Tuesday
        assert schedule_manager.is_detection_active("test-cam", schedule_json) is False

        # Wednesday - should be active
        mock_datetime.now.return_value = datetime(2025, 11, 19, 10, 0)  # Wednesday
        assert schedule_manager.is_detection_active("test-cam", schedule_json) is True

    @patch('app.services.schedule_manager.datetime')
    def test_all_days_selected(self, mock_datetime):
        """Test schedule with all days selected (7 days a week)"""
        # Sunday 10:00
        mock_datetime.now.return_value = datetime(2025, 11, 23, 10, 0)  # Sunday

        schedule = {
            "id": "schedule-1",
            "name": "24/7 Schedule",
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],  # All days
            "start_time": "08:00",
            "end_time": "18:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_missing_days_field_returns_true(self, mock_datetime):
        """Test that missing days_of_week field defaults to always active"""
        mock_datetime.now.return_value = datetime(2025, 11, 17, 10, 0)  # Monday

        schedule = {
            "id": "schedule-1",
            "name": "Broken Schedule",
            "start_time": "08:00",
            "end_time": "18:00",
            "enabled": True
            # Missing days_of_week
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True  # Fail open

    @patch('app.services.schedule_manager.datetime')
    def test_missing_time_fields_returns_true(self, mock_datetime):
        """Test that missing time fields defaults to always active"""
        mock_datetime.now.return_value = datetime(2025, 11, 17, 10, 0)  # Monday

        schedule = {
            "id": "schedule-1",
            "name": "Broken Schedule",
            "days_of_week": [0, 1, 2, 3, 4],
            "enabled": True
            # Missing start_time and end_time
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True  # Fail open

    @patch('app.services.schedule_manager.datetime')
    def test_invalid_time_format_returns_true(self, mock_datetime):
        """Test that invalid time format fails open"""
        mock_datetime.now.return_value = datetime(2025, 11, 17, 10, 0)  # Monday

        schedule = {
            "id": "schedule-1",
            "name": "Bad Time Format",
            "days_of_week": [0, 1, 2, 3, 4],
            "start_time": "invalid",
            "end_time": "also-invalid",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True  # Fail open

    def test_performance_under_1ms(self):
        """Benchmark test: schedule validation should complete in <1ms"""
        schedule = {
            "id": "schedule-1",
            "name": "Test Schedule",
            "days_of_week": [0, 1, 2, 3, 4],
            "start_time": "08:00",
            "end_time": "18:00",
            "enabled": True
        }
        schedule_json = json.dumps(schedule)

        # Run 1000 iterations and measure time
        iterations = 1000
        start_time = time.time()

        for _ in range(iterations):
            schedule_manager.is_detection_active("test-cam", schedule_json)

        elapsed_time = (time.time() - start_time) / iterations * 1000  # ms

        # Should average <1ms per call
        assert elapsed_time < 1.0, f"Schedule validation took {elapsed_time:.3f}ms (exceeds 1ms limit)"

    def test_parse_time_valid_formats(self):
        """Test _parse_time helper with valid time formats"""
        assert schedule_manager._parse_time("00:00") == time_obj(0, 0)
        assert schedule_manager._parse_time("09:30") == time_obj(9, 30)
        assert schedule_manager._parse_time("23:59") == time_obj(23, 59)

    def test_parse_time_invalid_formats(self):
        """Test _parse_time helper with invalid time formats"""
        assert schedule_manager._parse_time("invalid") is None
        assert schedule_manager._parse_time("25:00") is None  # Invalid hour
        assert schedule_manager._parse_time("12:60") is None  # Invalid minute
        assert schedule_manager._parse_time("") is None
        assert schedule_manager._parse_time(None) is None


class TestMultipleTimeRanges:
    """
    Test suite for Phase 5 (P5-5.4) multiple time ranges feature
    Tests the time_ranges array format and backward compatibility with legacy format
    """

    @patch('app.services.schedule_manager.datetime')
    def test_multiple_ranges_active_in_first_range(self, mock_datetime):
        """Test that detection is active when current time is in first range"""
        # Monday 07:30 (in morning range 06:00-09:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 7, 30)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "06:00", "end_time": "09:00"},
                {"start_time": "18:00", "end_time": "22:00"}
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_multiple_ranges_active_in_second_range(self, mock_datetime):
        """Test that detection is active when current time is in second range"""
        # Monday 19:00 (in evening range 18:00-22:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 19, 0)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "06:00", "end_time": "09:00"},
                {"start_time": "18:00", "end_time": "22:00"}
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_multiple_ranges_inactive_between_ranges(self, mock_datetime):
        """Test that detection is inactive when current time is between ranges"""
        # Monday 12:00 (between morning and evening ranges)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 12, 0)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "06:00", "end_time": "09:00"},
                {"start_time": "18:00", "end_time": "22:00"}
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is False

    @patch('app.services.schedule_manager.datetime')
    def test_multiple_ranges_with_overnight_range(self, mock_datetime):
        """Test multiple ranges including an overnight range"""
        # Monday 23:30 (in overnight range 22:00-06:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 23, 30)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "08:00", "end_time": "12:00"},
                {"start_time": "22:00", "end_time": "06:00"}  # Overnight
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_multiple_ranges_overnight_after_midnight(self, mock_datetime):
        """Test overnight range - time after midnight"""
        # Monday 03:00 (in overnight range 22:00-06:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 3, 0)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "08:00", "end_time": "12:00"},
                {"start_time": "22:00", "end_time": "06:00"}  # Overnight
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_three_ranges(self, mock_datetime):
        """Test schedule with three time ranges"""
        # Monday 14:30 (in afternoon range 14:00-16:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 14, 30)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "07:00", "end_time": "09:00"},
                {"start_time": "14:00", "end_time": "16:00"},
                {"start_time": "19:00", "end_time": "22:00"}
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_four_ranges_max(self, mock_datetime):
        """Test schedule with four time ranges (max allowed)"""
        # Monday 11:30 (in late morning range 10:00-12:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 11, 30)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "06:00", "end_time": "08:00"},
                {"start_time": "10:00", "end_time": "12:00"},
                {"start_time": "14:00", "end_time": "17:00"},
                {"start_time": "19:00", "end_time": "22:00"}
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_multiple_ranges_inactive_before_all(self, mock_datetime):
        """Test inactive when before all ranges"""
        # Monday 05:00 (before first range 06:00-09:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 5, 0)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "06:00", "end_time": "09:00"},
                {"start_time": "18:00", "end_time": "22:00"}
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is False

    @patch('app.services.schedule_manager.datetime')
    def test_multiple_ranges_inactive_after_all(self, mock_datetime):
        """Test inactive when after all ranges"""
        # Monday 23:00 (after last range 18:00-22:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 23, 0)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "06:00", "end_time": "09:00"},
                {"start_time": "18:00", "end_time": "22:00"}
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is False

    @patch('app.services.schedule_manager.datetime')
    def test_legacy_format_still_works(self, mock_datetime):
        """Test backward compatibility with legacy single-range format"""
        # Monday 10:00 (in range 09:00-17:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 10, 0)

        # Legacy format: start_time/end_time at root level
        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "start_time": "09:00",
            "end_time": "17:00"
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_legacy_format_outside_range(self, mock_datetime):
        """Test legacy format returns false when outside range"""
        # Monday 07:00 (before range 09:00-17:00)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 7, 0)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "start_time": "09:00",
            "end_time": "17:00"
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is False

    @patch('app.services.schedule_manager.datetime')
    def test_new_format_with_days_key(self, mock_datetime):
        """Test new format using 'days' key instead of 'days_of_week'"""
        # Monday 07:30 (in range)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 7, 30)

        schedule = {
            "enabled": True,
            "days": [0, 1, 2, 3, 4],  # New format uses 'days'
            "time_ranges": [
                {"start_time": "06:00", "end_time": "09:00"}
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_empty_time_ranges_array(self, mock_datetime):
        """Test empty time_ranges array falls back to always active"""
        mock_datetime.now.return_value = datetime(2025, 11, 17, 10, 0)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": []  # Empty array
        }
        schedule_json = json.dumps(schedule)

        # Falls through to legacy check, finds no start/end time, returns True (fail-open)
        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    @patch('app.services.schedule_manager.datetime')
    def test_invalid_range_entry_skipped(self, mock_datetime):
        """Test that invalid range entries are skipped"""
        # Monday 07:30 (in first valid range)
        mock_datetime.now.return_value = datetime(2025, 11, 17, 7, 30)

        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "time_ranges": [
                {"start_time": "06:00", "end_time": "09:00"},  # Valid
                {"start_time": None, "end_time": "12:00"},     # Invalid - missing start
                {"start_time": "18:00"},                        # Invalid - missing end
            ]
        }
        schedule_json = json.dumps(schedule)

        result = schedule_manager.is_detection_active("test-cam", schedule_json)
        assert result is True

    def test_multiple_ranges_performance(self):
        """Benchmark test: multiple ranges validation should still complete in <1ms"""
        schedule = {
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
            "time_ranges": [
                {"start_time": "06:00", "end_time": "09:00"},
                {"start_time": "12:00", "end_time": "14:00"},
                {"start_time": "18:00", "end_time": "21:00"},
                {"start_time": "22:00", "end_time": "02:00"}  # Overnight
            ]
        }
        schedule_json = json.dumps(schedule)

        # Run 1000 iterations and measure time
        iterations = 1000
        start_time = time.time()

        for _ in range(iterations):
            schedule_manager.is_detection_active("test-cam", schedule_json)

        elapsed_time = (time.time() - start_time) / iterations * 1000  # ms

        # Should average <1ms per call even with multiple ranges
        assert elapsed_time < 1.0, f"Multiple ranges validation took {elapsed_time:.3f}ms (exceeds 1ms limit)"
