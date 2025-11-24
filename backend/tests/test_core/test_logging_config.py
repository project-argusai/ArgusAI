"""
Unit tests for logging configuration (Story 6.2, AC: #1)
"""
import json
import logging
import pytest
import uuid
from io import StringIO

from app.core.logging_config import (
    setup_logging,
    get_logger,
    set_request_id,
    get_request_id,
    clear_request_id,
    sanitize_log_value,
    CustomJsonFormatter,
    RequestIdFilter,
    SanitizingFilter,
)


class TestRequestIdContext:
    """Test request ID context variable functionality"""

    def test_set_and_get_request_id(self):
        """request_id should be retrievable after setting"""
        test_id = str(uuid.uuid4())
        token = set_request_id(test_id)

        assert get_request_id() == test_id

        clear_request_id(token)

    def test_get_request_id_returns_none_when_not_set(self):
        """request_id should return None when not in context"""
        # Clear any existing context
        token = set_request_id(None)
        clear_request_id(token)

        result = get_request_id()
        assert result is None

    def test_clear_request_id_resets_context(self):
        """clear_request_id should reset to previous value"""
        original_id = str(uuid.uuid4())
        token1 = set_request_id(original_id)

        new_id = str(uuid.uuid4())
        token2 = set_request_id(new_id)
        assert get_request_id() == new_id

        clear_request_id(token2)
        assert get_request_id() == original_id

        clear_request_id(token1)


class TestRequestIdFilter:
    """Test request ID logging filter"""

    def test_filter_adds_request_id_to_record(self):
        """Filter should add request_id attribute to log records"""
        filter = RequestIdFilter()

        # Create a log record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )

        # Set request ID in context
        test_id = str(uuid.uuid4())
        token = set_request_id(test_id)

        # Apply filter
        result = filter.filter(record)

        assert result is True
        assert hasattr(record, 'request_id')
        assert record.request_id == test_id

        clear_request_id(token)

    def test_filter_uses_dash_when_no_request_id(self):
        """Filter should use '-' when request_id is not set"""
        filter = RequestIdFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )

        # Ensure no request_id is set
        token = set_request_id(None)
        clear_request_id(token)

        result = filter.filter(record)

        assert result is True
        assert record.request_id == "-"


class TestSanitizingFilter:
    """Test log sanitization filter"""

    def test_filter_removes_newlines(self):
        """Filter should remove newline characters"""
        filter = SanitizingFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Line 1\nLine 2\nLine 3",
            args=(),
            exc_info=None
        )

        filter.filter(record)

        assert "\n" not in record.msg
        assert record.msg == "Line 1 Line 2 Line 3"

    def test_filter_removes_crlf(self):
        """Filter should remove CRLF sequences"""
        filter = SanitizingFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Line 1\r\nLine 2",
            args=(),
            exc_info=None
        )

        filter.filter(record)

        assert "\r\n" not in record.msg
        assert record.msg == "Line 1 Line 2"

    def test_filter_sanitizes_args(self):
        """Filter should sanitize string args"""
        filter = SanitizingFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="User input: %s",
            args=("malicious\ninjection",),
            exc_info=None
        )

        filter.filter(record)

        assert "\n" not in record.args[0]


class TestSanitizeLogValue:
    """Test sanitize_log_value helper function"""

    def test_sanitize_removes_newlines(self):
        """sanitize_log_value should remove newline characters"""
        result = sanitize_log_value("hello\nworld")
        assert "\n" not in result
        assert result == "hello world"

    def test_sanitize_truncates_long_strings(self):
        """sanitize_log_value should truncate very long strings"""
        long_string = "a" * 20000
        result = sanitize_log_value(long_string)

        assert len(result) < len(long_string)
        assert "[truncated]" in result

    def test_sanitize_handles_non_strings(self):
        """sanitize_log_value should convert non-strings"""
        result = sanitize_log_value(12345)
        assert result == "12345"

    def test_sanitize_removes_carriage_returns(self):
        """sanitize_log_value should remove carriage return characters"""
        result = sanitize_log_value("hello\r\nworld\rtest")
        assert "\r" not in result


class TestCustomJsonFormatter:
    """Test custom JSON log formatter"""

    def test_formatter_produces_valid_json(self):
        """Formatter should produce valid JSON output"""
        formatter = CustomJsonFormatter()

        record = logging.LogRecord(
            name="app.services.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.request_id = "test-uuid"

        output = formatter.format(record)

        # Should be valid JSON
        parsed = json.loads(output)

        assert "timestamp" in parsed
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert parsed["logger"] == "app.services.test"

    def test_formatter_includes_extra_fields(self):
        """Formatter should include extra fields in output"""
        formatter = CustomJsonFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Event processed",
            args=(),
            exc_info=None
        )
        record.request_id = "uuid-123"
        record.event_id = "event-456"
        record.processing_time_ms = 150

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed.get("event_id") == "event-456"
        assert parsed.get("processing_time_ms") == 150


class TestSetupLogging:
    """Test logging setup function"""

    def test_setup_logging_returns_logger(self):
        """setup_logging should return a configured logger"""
        logger = setup_logging(log_level="INFO")

        assert isinstance(logger, logging.Logger)

    def test_setup_logging_respects_log_level(self):
        """setup_logging should configure the specified log level"""
        logger = setup_logging(log_level="WARNING")

        # Root logger should be at WARNING level
        root = logging.getLogger()
        assert root.level == logging.WARNING

        # Reset to INFO for other tests
        setup_logging(log_level="INFO")


class TestGetLogger:
    """Test get_logger helper function"""

    def test_get_logger_returns_logger_instance(self):
        """get_logger should return a logger with the specified name"""
        logger = get_logger("test.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"
