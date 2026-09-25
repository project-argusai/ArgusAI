"""
Structured JSON Logging Configuration (Story 6.2)

Provides centralized logging configuration with:
- JSON formatted output for machine parsing
- Request ID tracking via contextvars
- File rotation (7 days, 100MB max)
- Configurable log levels via environment
"""
import logging
import logging.handlers
import os
import contextvars
import re
from datetime import datetime, timezone
from typing import Optional
from pythonjsonlogger import jsonlogger

from app.core.config import settings

# Context variable for request ID propagation
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'request_id', default=None
)

# Application version (can be overridden)
APP_VERSION = "1.0.0"

# Log directory configuration
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'logs')


class RequestIdFilter(logging.Filter):
    """
    Logging filter that adds request_id to all log records.

    Uses contextvars to access the current request's ID, enabling
    correlation of all logs from a single request.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class SanitizingFilter(logging.Filter):
    """
    Filter that sanitizes log messages to prevent log injection attacks
    and redact sensitive information.

    Removes or escapes dangerous characters that could be used to
    forge log entries or inject malicious content.

    Story P5-1.2: Also redacts HomeKit PIN codes (XXX-XX-XXX format) from logs.
    """

    # Patterns that could be used for log injection
    DANGEROUS_PATTERNS = [
        (r'\r\n', ' '),  # CRLF injection
        (r'\n', ' '),    # Newline injection
        (r'\r', ' '),    # Carriage return injection
    ]

    # Story P5-1.2 AC4: Pattern to redact HomeKit PIN codes (XXX-XX-XXX format)
    # This matches 8-digit PINs with dashes like "123-45-678" or "031-45-154"
    HOMEKIT_PIN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{3}\b')
    PIN_REDACTION = '[PIN-REDACTED]'

    def _redact_sensitive(self, value: str) -> str:
        """Redact sensitive patterns from a string."""
        # Story P5-1.2 AC4: Redact HomeKit PIN codes
        return self.HOMEKIT_PIN_PATTERN.sub(self.PIN_REDACTION, value)

    def filter(self, record: logging.LogRecord) -> bool:
        # Sanitize the message
        if isinstance(record.msg, str):
            for pattern, replacement in self.DANGEROUS_PATTERNS:
                record.msg = re.sub(pattern, replacement, record.msg)
            # Story P5-1.2: Redact PIN codes
            record.msg = self._redact_sensitive(record.msg)

        # Sanitize args if present
        if record.args:
            sanitized_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    sanitized = arg
                    for pattern, replacement in self.DANGEROUS_PATTERNS:
                        sanitized = re.sub(pattern, replacement, sanitized)
                    # Story P5-1.2: Redact PIN codes from args
                    sanitized = self._redact_sensitive(sanitized)
                    sanitized_args.append(sanitized)
                else:
                    sanitized_args.append(arg)
            record.args = tuple(sanitized_args)

        return True


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter that adds standard fields to all log entries.

    Output format:
    {
        "timestamp": "2025-11-23T10:30:00.000Z",
        "level": "INFO",
        "message": "Event processed",
        "module": "event_processor",
        "request_id": "uuid-here",
        "logger": "app.services.event_processor",
        ...extra fields...
    }
    """

    def add_fields(
        self,
        log_record: dict,
        record: logging.LogRecord,
        message_dict: dict
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        # Standard timestamp in ISO format with UTC
        if not log_record.get('timestamp'):
            log_record['timestamp'] = datetime.now(timezone.utc).isoformat()

        # Standard fields
        log_record['level'] = record.levelname
        log_record['module'] = record.module
        log_record['logger'] = record.name

        # Request ID from context
        log_record['request_id'] = getattr(record, 'request_id', '-')

        # Add function name for debugging
        if record.funcName:
            log_record['function'] = record.funcName

        # Add line number for debugging
        if record.lineno:
            log_record['line'] = record.lineno

        # Ensure message is at consistent position
        if 'message' not in log_record:
            log_record['message'] = record.getMessage()


def configure_sqlalchemy_query_logging(echo: bool) -> None:
    """Set SQLAlchemy engine loggers for opt-in statement logging.

    SQLAlchemy emits each statement at INFO on ``sqlalchemy.engine`` when
    engine ``echo`` is enabled, and ``echo=True`` bypasses the logger level
    via ``Logger._log``. Callers must pass the same flag used for ``echo``.

    When echo is off, the engine loggers are pinned to WARNING so a DEBUG
    root log level does not surface every query.
    """
    level = logging.INFO if echo else logging.WARNING
    for name in ("sqlalchemy.engine", "sqlalchemy.engine.Engine"):
        logging.getLogger(name).setLevel(level)


def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[str] = None,
    app_version: Optional[str] = None
) -> logging.Logger:
    """
    Configure application-wide logging with JSON format and rotation.

    Args:
        log_level: Override log level (default from settings.LOG_LEVEL)
        log_dir: Override log directory (default: backend/data/logs)
        app_version: Application version to include in startup logs

    Returns:
        Root logger configured for the application
    """
    global APP_VERSION

    level = getattr(logging, (log_level or settings.LOG_LEVEL).upper(), logging.INFO)
    directory = log_dir or LOG_DIR
    if app_version:
        APP_VERSION = app_version

    # Ensure log directory exists
    os.makedirs(directory, exist_ok=True)

    # Create JSON formatter
    json_formatter = CustomJsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s'
    )

    # Create standard formatter for console (human-readable fallback)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] %(message)s',
        defaults={'request_id': '-'}
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler (JSON format for production, readable for development)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(json_formatter)
    console_handler.addFilter(RequestIdFilter())
    console_handler.addFilter(SanitizingFilter())
    root_logger.addHandler(console_handler)

    # File handler with rotation
    # Max 100MB per file, keep 7 days worth of logs
    log_file = os.path.join(directory, 'app.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=100 * 1024 * 1024,  # 100MB
        backupCount=7,  # Keep 7 backup files
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(json_formatter)
    file_handler.addFilter(RequestIdFilter())
    file_handler.addFilter(SanitizingFilter())
    root_logger.addHandler(file_handler)

    # Error-only file handler for critical issues
    error_log_file = os.path.join(directory, 'error.log')
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)
    error_handler.addFilter(RequestIdFilter())
    error_handler.addFilter(SanitizingFilter())
    root_logger.addHandler(error_handler)

    # Suppress noisy third-party loggers
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    # SQL statement logs stay off unless SQL_ECHO / DB_ECHO is set, even when
    # the root logger is DEBUG.
    configure_sqlalchemy_query_logging(settings.sql_echo_enabled)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the application's configuration.

    Args:
        name: Logger name (typically __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def set_request_id(request_id: str) -> contextvars.Token:
    """
    Set the request ID for the current context.

    Args:
        request_id: UUID string for the current request

    Returns:
        Token that can be used to reset the context
    """
    return request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """
    Get the current request ID from context.

    Returns:
        Current request ID or None if not set
    """
    return request_id_var.get()


def clear_request_id(token: contextvars.Token) -> None:
    """
    Clear the request ID context using the token from set_request_id.

    Args:
        token: Token returned from set_request_id
    """
    request_id_var.reset(token)


def sanitize_log_value(value: str) -> str:
    """
    Sanitize a value for safe logging, preventing log injection.

    Args:
        value: String value to sanitize

    Returns:
        Sanitized string safe for logging
    """
    if not isinstance(value, str):
        return str(value)

    # Remove/escape dangerous characters
    sanitized = value.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')

    # Limit length to prevent log flooding
    max_length = 10000
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + '...[truncated]'

    return sanitized
