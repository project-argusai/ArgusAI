"""
HomeKit Diagnostics Service (Story P7-1.1)

Provides diagnostic logging and monitoring for the HomeKit bridge.
Uses a thread-safe circular buffer to capture and retain log entries.
"""
import logging
import threading
from collections import deque
from datetime import datetime
from typing import List, Optional, Deque

from app.schemas.homekit_diagnostics import (
    HomeKitDiagnosticEntry,
    HomeKitDiagnosticsResponse,
    NetworkBindingInfo,
    LastEventDeliveryInfo,
)


# Default maximum number of log entries to retain
DEFAULT_DIAGNOSTIC_LOG_SIZE = 100


class HomekitDiagnosticHandler(logging.Handler):
    """
    Custom logging handler that captures HomeKit-related logs into a circular buffer.

    Thread-safe implementation using a lock around the deque operations.
    Only captures logs from the 'app.services.homekit_service' logger or its children.

    Attributes:
        max_entries: Maximum number of log entries to retain
        _buffer: Thread-safe circular buffer (deque)
        _lock: Threading lock for buffer operations
    """

    # Map Python log levels to our level strings
    LEVEL_MAP = {
        logging.DEBUG: "debug",
        logging.INFO: "info",
        logging.WARNING: "warning",
        logging.ERROR: "error",
        logging.CRITICAL: "error",  # Map critical to error
    }

    def __init__(self, max_entries: int = DEFAULT_DIAGNOSTIC_LOG_SIZE):
        """
        Initialize the diagnostic handler.

        Args:
            max_entries: Maximum number of log entries to retain (default: 100)
        """
        super().__init__()
        self.max_entries = max_entries
        self._buffer: Deque[HomeKitDiagnosticEntry] = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._warnings: List[str] = []
        self._errors: List[str] = []
        self._last_event_delivery: Optional[LastEventDeliveryInfo] = None

    def emit(self, record: logging.LogRecord) -> None:
        """
        Process a log record and add it to the buffer if it's HomeKit-related.

        Args:
            record: The log record to process
        """
        # Only capture logs from homekit-related loggers
        if not record.name.startswith("app.services.homekit"):
            return

        try:
            # Extract category from extra fields, default to 'lifecycle'
            category = getattr(record, "diagnostic_category", None)
            if not category:
                # Infer category from message content
                category = self._infer_category(record.getMessage())

            # Extract additional details from extra fields
            details = {}
            for attr in ["camera_id", "event_id", "sensor_type", "reset_seconds",
                         "timeout_seconds", "port", "ip", "interface", "pairing_id",
                         "client_count", "delivered"]:
                if hasattr(record, attr):
                    details[attr] = getattr(record, attr)

            # Create diagnostic entry
            entry = HomeKitDiagnosticEntry(
                timestamp=datetime.fromtimestamp(record.created),
                level=self.LEVEL_MAP.get(record.levelno, "info"),
                category=category,
                message=record.getMessage(),
                details=details if details else None,
            )

            # Add to buffer (thread-safe)
            with self._lock:
                self._buffer.append(entry)

                # Track warnings and errors separately for quick access
                if record.levelno == logging.WARNING:
                    self._warnings.append(record.getMessage())
                    # Keep only last 10 warnings
                    if len(self._warnings) > 10:
                        self._warnings.pop(0)
                elif record.levelno >= logging.ERROR:
                    self._errors.append(record.getMessage())
                    # Keep only last 10 errors
                    if len(self._errors) > 10:
                        self._errors.pop(0)

                # Track last event delivery
                if category == "event" and "camera_id" in details:
                    self._last_event_delivery = LastEventDeliveryInfo(
                        camera_id=details.get("camera_id", "unknown"),
                        sensor_type=details.get("sensor_type", "motion"),
                        timestamp=datetime.fromtimestamp(record.created),
                        delivered=details.get("delivered", True),
                    )

        except Exception:
            # Don't let diagnostic logging crash the application
            self.handleError(record)

    def _infer_category(self, message: str) -> str:
        """
        Infer the category from the log message content.

        Args:
            message: The log message

        Returns:
            Inferred category string
        """
        message_lower = message.lower()

        if any(kw in message_lower for kw in ["start", "stop", "driver", "bridge"]):
            return "lifecycle"
        elif any(kw in message_lower for kw in ["pair", "unpair", "pairing"]):
            return "pairing"
        # Story P7-1.3: Add 'delivery' category for delivery confirmation logs
        elif any(kw in message_lower for kw in ["delivered", "delivery"]):
            return "delivery"
        elif any(kw in message_lower for kw in ["motion", "occupancy", "vehicle",
                                                 "animal", "package", "doorbell",
                                                 "triggered", "reset"]):
            return "event"
        elif any(kw in message_lower for kw in ["mdns", "bonjour", "advertis"]):
            return "mdns"
        elif any(kw in message_lower for kw in ["port", "bind", "network", "ip"]):
            return "network"

        return "lifecycle"  # Default

    def get_recent_logs(self, limit: Optional[int] = None) -> List[HomeKitDiagnosticEntry]:
        """
        Get recent log entries (newest first).

        Args:
            limit: Maximum number of entries to return (None for all)

        Returns:
            List of diagnostic entries, newest first
        """
        with self._lock:
            entries = list(self._buffer)

        # Reverse to get newest first
        entries.reverse()

        if limit:
            return entries[:limit]
        return entries

    def get_warnings(self) -> List[str]:
        """Get recent warning messages."""
        with self._lock:
            return list(self._warnings)

    def get_errors(self) -> List[str]:
        """Get recent error messages."""
        with self._lock:
            return list(self._errors)

    def get_last_event_delivery(self) -> Optional[LastEventDeliveryInfo]:
        """Get information about the most recent event delivery."""
        with self._lock:
            return self._last_event_delivery

    def clear(self) -> None:
        """Clear all diagnostic data."""
        with self._lock:
            self._buffer.clear()
            self._warnings.clear()
            self._errors.clear()
            self._last_event_delivery = None


# Global diagnostic handler instance
_diagnostic_handler: Optional[HomekitDiagnosticHandler] = None


def get_diagnostic_handler(max_entries: int = DEFAULT_DIAGNOSTIC_LOG_SIZE) -> HomekitDiagnosticHandler:
    """
    Get or create the global diagnostic handler.

    Args:
        max_entries: Maximum log entries to retain

    Returns:
        HomekitDiagnosticHandler singleton instance
    """
    global _diagnostic_handler
    if _diagnostic_handler is None:
        _diagnostic_handler = HomekitDiagnosticHandler(max_entries=max_entries)

        # Attach handler to the homekit service logger
        homekit_logger = logging.getLogger("app.services.homekit_service")
        homekit_logger.addHandler(_diagnostic_handler)

    return _diagnostic_handler


def initialize_diagnostic_handler(max_entries: int = DEFAULT_DIAGNOSTIC_LOG_SIZE) -> HomekitDiagnosticHandler:
    """
    Initialize the diagnostic handler and attach it to HomeKit loggers.

    Should be called during application startup.

    Args:
        max_entries: Maximum log entries to retain

    Returns:
        The initialized handler
    """
    handler = get_diagnostic_handler(max_entries)

    # Ensure handler is attached to all relevant loggers
    for logger_name in ["app.services.homekit_service",
                        "app.services.homekit_accessories",
                        "app.services.homekit_camera"]:
        logger = logging.getLogger(logger_name)
        if handler not in logger.handlers:
            logger.addHandler(handler)

    return handler


def shutdown_diagnostic_handler() -> None:
    """
    Remove the diagnostic handler from loggers and clear data.

    Should be called during application shutdown.
    """
    global _diagnostic_handler
    if _diagnostic_handler is not None:
        # Remove from all loggers
        for logger_name in ["app.services.homekit_service",
                            "app.services.homekit_accessories",
                            "app.services.homekit_camera"]:
            logger = logging.getLogger(logger_name)
            if _diagnostic_handler in logger.handlers:
                logger.removeHandler(_diagnostic_handler)

        _diagnostic_handler.clear()
        _diagnostic_handler = None
