"""
Tests for HomeKit Diagnostics API (Story P7-1.1, P7-1.2)

Tests cover:
- GET /api/v1/homekit/diagnostics endpoint
- POST /api/v1/homekit/test-connectivity endpoint (Story P7-1.2)
- Schema validation for diagnostic responses
- Diagnostic handler behavior
- Circular buffer functionality
"""
import pytest
import logging
from datetime import datetime

from app.schemas.homekit_diagnostics import (
    HomeKitDiagnosticEntry,
    HomeKitDiagnosticsResponse,
    HomeKitConnectivityTestResponse,
    NetworkBindingInfo,
    LastEventDeliveryInfo,
)
from app.services.homekit_diagnostics import (
    HomekitDiagnosticHandler,
    DEFAULT_DIAGNOSTIC_LOG_SIZE,
)


# ============================================================================
# Schema Tests (Story P7-1.1)
# ============================================================================


class TestHomeKitDiagnosticSchemas:
    """Tests for HomeKit diagnostic Pydantic schemas."""

    def test_diagnostic_entry_schema(self):
        """AC1-4: HomeKitDiagnosticEntry validates correctly."""
        entry = HomeKitDiagnosticEntry(
            timestamp=datetime.now(),
            level="info",
            category="event",
            message="Motion triggered for Front Door",
            details={"camera_id": "abc-123", "sensor_type": "motion"}
        )

        assert entry.level == "info"
        assert entry.category == "event"
        assert entry.message == "Motion triggered for Front Door"
        assert entry.details["camera_id"] == "abc-123"

    def test_diagnostic_entry_level_validation(self):
        """HomeKitDiagnosticEntry validates log levels."""
        valid_levels = ["debug", "info", "warning", "error"]
        for level in valid_levels:
            entry = HomeKitDiagnosticEntry(
                timestamp=datetime.now(),
                level=level,
                category="lifecycle",
                message="Test message"
            )
            assert entry.level == level

    def test_diagnostic_entry_category_validation(self):
        """HomeKitDiagnosticEntry validates categories."""
        valid_categories = ["lifecycle", "pairing", "event", "network", "mdns"]
        for category in valid_categories:
            entry = HomeKitDiagnosticEntry(
                timestamp=datetime.now(),
                level="info",
                category=category,
                message="Test message"
            )
            assert entry.category == category

    def test_diagnostic_entry_optional_details(self):
        """HomeKitDiagnosticEntry handles None details."""
        entry = HomeKitDiagnosticEntry(
            timestamp=datetime.now(),
            level="info",
            category="lifecycle",
            message="Test message",
            details=None
        )
        assert entry.details is None

    def test_network_binding_schema(self):
        """NetworkBindingInfo validates correctly."""
        binding = NetworkBindingInfo(
            ip="192.168.1.100",
            port=51826,
            interface="en0"
        )

        assert binding.ip == "192.168.1.100"
        assert binding.port == 51826
        assert binding.interface == "en0"

    def test_network_binding_optional_interface(self):
        """NetworkBindingInfo handles None interface."""
        binding = NetworkBindingInfo(
            ip="0.0.0.0",
            port=51826
        )

        assert binding.interface is None

    def test_last_event_delivery_schema(self):
        """LastEventDeliveryInfo validates correctly."""
        delivery = LastEventDeliveryInfo(
            camera_id="abc-123",
            sensor_type="motion",
            timestamp=datetime.now(),
            delivered=True
        )

        assert delivery.camera_id == "abc-123"
        assert delivery.sensor_type == "motion"
        assert delivery.delivered is True

    def test_diagnostics_response_schema(self):
        """AC5: HomeKitDiagnosticsResponse validates correctly."""
        response = HomeKitDiagnosticsResponse(
            bridge_running=True,
            mdns_advertising=True,
            network_binding=NetworkBindingInfo(ip="192.168.1.100", port=51826),
            connected_clients=2,
            last_event_delivery=LastEventDeliveryInfo(
                camera_id="abc-123",
                sensor_type="motion",
                timestamp=datetime.now(),
                delivered=True
            ),
            recent_logs=[
                HomeKitDiagnosticEntry(
                    timestamp=datetime.now(),
                    level="info",
                    category="event",
                    message="Motion triggered"
                )
            ],
            warnings=["Test warning"],
            errors=[]
        )

        assert response.bridge_running is True
        assert response.mdns_advertising is True
        assert response.connected_clients == 2
        assert len(response.recent_logs) == 1
        assert len(response.warnings) == 1
        assert len(response.errors) == 0

    def test_diagnostics_response_empty_lists(self):
        """HomeKitDiagnosticsResponse handles empty lists."""
        response = HomeKitDiagnosticsResponse(
            bridge_running=False,
            mdns_advertising=False,
            network_binding=None,
            connected_clients=0,
            last_event_delivery=None,
            recent_logs=[],
            warnings=[],
            errors=[]
        )

        assert response.bridge_running is False
        assert response.network_binding is None
        assert len(response.recent_logs) == 0


# ============================================================================
# Diagnostic Handler Tests (Story P7-1.1)
# ============================================================================


class TestHomekitDiagnosticHandler:
    """Tests for HomekitDiagnosticHandler."""

    def test_handler_initialization(self):
        """Handler initializes with correct max entries."""
        handler = HomekitDiagnosticHandler(max_entries=50)
        assert handler.max_entries == 50

    def test_handler_default_max_entries(self):
        """Handler uses default max entries."""
        handler = HomekitDiagnosticHandler()
        assert handler.max_entries == DEFAULT_DIAGNOSTIC_LOG_SIZE

    def test_handler_emit_captures_homekit_logs(self):
        """AC1: Handler captures HomeKit service logs."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        # Create a log record with homekit logger name
        record = logging.LogRecord(
            name="app.services.homekit_service",
            level=logging.INFO,
            pathname="homekit_service.py",
            lineno=100,
            msg="Test message",
            args=(),
            exc_info=None
        )

        handler.emit(record)

        logs = handler.get_recent_logs()
        assert len(logs) == 1
        assert logs[0].message == "Test message"

    def test_handler_ignores_non_homekit_logs(self):
        """Handler ignores logs from non-HomeKit loggers."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        # Create a log record with non-homekit logger name
        record = logging.LogRecord(
            name="app.services.camera_service",
            level=logging.INFO,
            pathname="camera_service.py",
            lineno=100,
            msg="Test message",
            args=(),
            exc_info=None
        )

        handler.emit(record)

        logs = handler.get_recent_logs()
        assert len(logs) == 0

    def test_handler_extracts_diagnostic_category(self):
        """Handler extracts diagnostic_category from extra fields."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        record = logging.LogRecord(
            name="app.services.homekit_service",
            level=logging.INFO,
            pathname="homekit_service.py",
            lineno=100,
            msg="Network binding",
            args=(),
            exc_info=None
        )
        record.diagnostic_category = "network"

        handler.emit(record)

        logs = handler.get_recent_logs()
        assert logs[0].category == "network"

    def test_handler_infers_category_from_message(self):
        """Handler infers category from message content."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        test_cases = [
            ("Bridge started", "lifecycle"),
            ("Pairing attempt", "pairing"),
            ("Motion triggered", "event"),
            ("mDNS advertising", "mdns"),
            ("Port binding", "network"),
        ]

        for msg, expected_category in test_cases:
            handler.clear()
            record = logging.LogRecord(
                name="app.services.homekit_service",
                level=logging.INFO,
                pathname="homekit_service.py",
                lineno=100,
                msg=msg,
                args=(),
                exc_info=None
            )

            handler.emit(record)

            logs = handler.get_recent_logs()
            assert logs[0].category == expected_category, f"Failed for message: {msg}"

    def test_handler_extracts_details(self):
        """Handler extracts details from extra fields."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        record = logging.LogRecord(
            name="app.services.homekit_service",
            level=logging.INFO,
            pathname="homekit_service.py",
            lineno=100,
            msg="Motion triggered",
            args=(),
            exc_info=None
        )
        record.camera_id = "abc-123"
        record.sensor_type = "motion"
        record.reset_seconds = 30

        handler.emit(record)

        logs = handler.get_recent_logs()
        assert logs[0].details is not None
        assert logs[0].details["camera_id"] == "abc-123"
        assert logs[0].details["sensor_type"] == "motion"
        assert logs[0].details["reset_seconds"] == 30

    def test_handler_circular_buffer_max_entries(self):
        """Handler circular buffer respects max entries."""
        handler = HomekitDiagnosticHandler(max_entries=5)

        # Add 10 log entries
        for i in range(10):
            record = logging.LogRecord(
                name="app.services.homekit_service",
                level=logging.INFO,
                pathname="homekit_service.py",
                lineno=100,
                msg=f"Message {i}",
                args=(),
                exc_info=None
            )
            handler.emit(record)

        logs = handler.get_recent_logs()
        assert len(logs) == 5  # Only last 5 entries

    def test_handler_circular_buffer_fifo_order(self):
        """Handler circular buffer drops oldest entries (FIFO)."""
        handler = HomekitDiagnosticHandler(max_entries=3)

        for i in range(5):
            record = logging.LogRecord(
                name="app.services.homekit_service",
                level=logging.INFO,
                pathname="homekit_service.py",
                lineno=100,
                msg=f"Message {i}",
                args=(),
                exc_info=None
            )
            handler.emit(record)

        logs = handler.get_recent_logs()
        # Should have messages 2, 3, 4 (newest first)
        assert logs[0].message == "Message 4"
        assert logs[1].message == "Message 3"
        assert logs[2].message == "Message 2"

    def test_handler_tracks_warnings(self):
        """Handler tracks warning messages separately."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        record = logging.LogRecord(
            name="app.services.homekit_service",
            level=logging.WARNING,
            pathname="homekit_service.py",
            lineno=100,
            msg="Test warning",
            args=(),
            exc_info=None
        )

        handler.emit(record)

        warnings = handler.get_warnings()
        assert len(warnings) == 1
        assert warnings[0] == "Test warning"

    def test_handler_tracks_errors(self):
        """Handler tracks error messages separately."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        record = logging.LogRecord(
            name="app.services.homekit_service",
            level=logging.ERROR,
            pathname="homekit_service.py",
            lineno=100,
            msg="Test error",
            args=(),
            exc_info=None
        )

        handler.emit(record)

        errors = handler.get_errors()
        assert len(errors) == 1
        assert errors[0] == "Test error"

    def test_handler_tracks_last_event_delivery(self):
        """Handler tracks last event delivery info."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        record = logging.LogRecord(
            name="app.services.homekit_service",
            level=logging.INFO,
            pathname="homekit_service.py",
            lineno=100,
            msg="Motion triggered",
            args=(),
            exc_info=None
        )
        record.diagnostic_category = "event"
        record.camera_id = "abc-123"
        record.sensor_type = "motion"
        record.delivered = True

        handler.emit(record)

        last_delivery = handler.get_last_event_delivery()
        assert last_delivery is not None
        assert last_delivery.camera_id == "abc-123"
        assert last_delivery.sensor_type == "motion"
        assert last_delivery.delivered is True

    def test_handler_clear(self):
        """Handler clear method removes all data."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        # Add some data
        record = logging.LogRecord(
            name="app.services.homekit_service",
            level=logging.ERROR,
            pathname="homekit_service.py",
            lineno=100,
            msg="Test error",
            args=(),
            exc_info=None
        )
        handler.emit(record)

        handler.clear()

        assert len(handler.get_recent_logs()) == 0
        assert len(handler.get_warnings()) == 0
        assert len(handler.get_errors()) == 0
        assert handler.get_last_event_delivery() is None

    def test_handler_get_recent_logs_with_limit(self):
        """Handler get_recent_logs respects limit parameter."""
        handler = HomekitDiagnosticHandler(max_entries=100)

        for i in range(10):
            record = logging.LogRecord(
                name="app.services.homekit_service",
                level=logging.INFO,
                pathname="homekit_service.py",
                lineno=100,
                msg=f"Message {i}",
                args=(),
                exc_info=None
            )
            handler.emit(record)

        logs = handler.get_recent_logs(limit=3)
        assert len(logs) == 3


# ============================================================================
# API Endpoint Tests (Story P7-1.1 AC5)
# ============================================================================


class TestHomeKitDiagnosticsAPI:
    """Tests for HomeKit diagnostics API endpoint behavior."""

    def test_diagnostics_response_format(self):
        """AC5: Diagnostics endpoint returns expected format."""
        # Simulate the response format
        diagnostics = {
            "bridge_running": True,
            "mdns_advertising": True,
            "network_binding": {"ip": "192.168.1.100", "port": 51826, "interface": None},
            "connected_clients": 2,
            "last_event_delivery": {
                "camera_id": "abc-123",
                "sensor_type": "motion",
                "timestamp": "2025-12-17T10:30:00Z",
                "delivered": True
            },
            "recent_logs": [
                {
                    "timestamp": "2025-12-17T10:30:00Z",
                    "level": "info",
                    "category": "event",
                    "message": "Motion triggered",
                    "details": {"camera_id": "abc-123"}
                }
            ],
            "warnings": [],
            "errors": []
        }

        response = HomeKitDiagnosticsResponse(**diagnostics)
        assert response.bridge_running is True
        assert response.connected_clients == 2
        assert len(response.recent_logs) == 1

    def test_diagnostics_response_with_empty_data(self):
        """Diagnostics endpoint handles empty/stopped state."""
        diagnostics = {
            "bridge_running": False,
            "mdns_advertising": False,
            "network_binding": None,
            "connected_clients": 0,
            "last_event_delivery": None,
            "recent_logs": [],
            "warnings": [],
            "errors": ["HAP-python not installed"]
        }

        response = HomeKitDiagnosticsResponse(**diagnostics)
        assert response.bridge_running is False
        assert len(response.errors) == 1


# ============================================================================
# Connectivity Test Schema Tests (Story P7-1.2)
# ============================================================================


class TestHomeKitConnectivityTestSchema:
    """Tests for HomeKit connectivity test Pydantic schema (Story P7-1.2)."""

    def test_connectivity_test_response_schema(self):
        """AC6: HomeKitConnectivityTestResponse validates correctly."""
        response = HomeKitConnectivityTestResponse(
            mdns_visible=True,
            discovered_as="ArgusAI._hap._tcp.local",
            port_accessible=True,
            network_binding=NetworkBindingInfo(ip="192.168.1.100", port=51826),
            firewall_issues=[],
            recommendations=[],
            test_duration_ms=1250
        )

        assert response.mdns_visible is True
        assert response.discovered_as == "ArgusAI._hap._tcp.local"
        assert response.port_accessible is True
        assert response.test_duration_ms == 1250
        assert len(response.firewall_issues) == 0
        assert len(response.recommendations) == 0

    def test_connectivity_test_response_with_issues(self):
        """AC6: Connectivity test response handles firewall issues."""
        response = HomeKitConnectivityTestResponse(
            mdns_visible=False,
            discovered_as=None,
            port_accessible=False,
            network_binding=NetworkBindingInfo(ip="0.0.0.0", port=51826),
            firewall_issues=[
                "mDNS service not visible - check UDP port 5353",
                "TCP port 51826 not accessible"
            ],
            recommendations=[
                "Ensure UDP port 5353 is open for mDNS multicast",
                "Check that avahi-daemon (Linux) or mDNSResponder (macOS) is running",
                "Ensure TCP port 51826 is open in your firewall"
            ],
            test_duration_ms=3500
        )

        assert response.mdns_visible is False
        assert response.discovered_as is None
        assert response.port_accessible is False
        assert len(response.firewall_issues) == 2
        assert len(response.recommendations) == 3
        assert "mDNS" in response.firewall_issues[0]

    def test_connectivity_test_response_with_null_binding(self):
        """Connectivity test response handles null network binding."""
        response = HomeKitConnectivityTestResponse(
            mdns_visible=False,
            discovered_as=None,
            port_accessible=False,
            network_binding=None,
            firewall_issues=["HomeKit bridge not running"],
            recommendations=["Enable HomeKit bridge first"],
            test_duration_ms=100
        )

        assert response.network_binding is None
        assert len(response.firewall_issues) == 1

    def test_connectivity_test_response_partial_success(self):
        """AC6: Connectivity test handles partial success (port ok, mDNS not)."""
        response = HomeKitConnectivityTestResponse(
            mdns_visible=False,
            discovered_as=None,
            port_accessible=True,
            network_binding=NetworkBindingInfo(ip="192.168.1.100", port=51826),
            firewall_issues=["mDNS service not visible - check UDP port 5353"],
            recommendations=[
                "Ensure UDP port 5353 is open for mDNS multicast",
                "Try restarting the HomeKit bridge"
            ],
            test_duration_ms=3200
        )

        assert response.mdns_visible is False
        assert response.port_accessible is True
        assert "5353" in response.firewall_issues[0]


# ============================================================================
# Config Tests (Story P7-1.2)
# ============================================================================


class TestHomeKitConfigNetworkBinding:
    """Tests for HomeKit config network binding options (Story P7-1.2)."""

    def test_config_default_bind_address(self):
        """AC3: Default bind_address is 0.0.0.0."""
        from app.config.homekit import HomekitConfig, DEFAULT_BIND_ADDRESS

        config = HomekitConfig()
        assert config.bind_address == "0.0.0.0"
        assert DEFAULT_BIND_ADDRESS == "0.0.0.0"

    def test_config_custom_bind_address(self):
        """AC4: bind_address can be set to specific IP."""
        from app.config.homekit import HomekitConfig

        config = HomekitConfig(bind_address="192.168.1.100")
        assert config.bind_address == "192.168.1.100"

    def test_config_mdns_interface_default(self):
        """AC3: Default mdns_interface is None."""
        from app.config.homekit import HomekitConfig

        config = HomekitConfig()
        assert config.mdns_interface is None

    def test_config_mdns_interface_custom(self):
        """AC3: mdns_interface can be set."""
        from app.config.homekit import HomekitConfig

        config = HomekitConfig(mdns_interface="eth0")
        assert config.mdns_interface == "eth0"

    def test_get_homekit_config_with_env_vars(self, monkeypatch):
        """AC3, AC4: get_homekit_config reads network env vars."""
        from app.config.homekit import get_homekit_config

        monkeypatch.setenv("HOMEKIT_BIND_ADDRESS", "10.0.0.50")
        monkeypatch.setenv("HOMEKIT_MDNS_INTERFACE", "wlan0")

        config = get_homekit_config()
        assert config.bind_address == "10.0.0.50"
        assert config.mdns_interface == "wlan0"

    def test_get_homekit_config_default_env_vars(self, monkeypatch):
        """get_homekit_config uses defaults when env vars not set."""
        from app.config.homekit import get_homekit_config, DEFAULT_BIND_ADDRESS

        # Ensure env vars are not set
        monkeypatch.delenv("HOMEKIT_BIND_ADDRESS", raising=False)
        monkeypatch.delenv("HOMEKIT_MDNS_INTERFACE", raising=False)

        config = get_homekit_config()
        assert config.bind_address == DEFAULT_BIND_ADDRESS
        assert config.mdns_interface is None
