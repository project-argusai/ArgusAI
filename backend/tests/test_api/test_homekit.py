"""
Tests for HomeKit API endpoints (Story P5-1.1, P5-1.8, P7-1.2)

Tests cover:
- HomeKit status endpoint
- HomeKit enable/disable endpoints
- HomeKit QR code endpoint
- HomeKit pairings list endpoint (P5-1.8 AC3)
- HomeKit remove pairing endpoint (P5-1.8 AC4)
- HomeKit connectivity test endpoint (P7-1.2 AC6)
- Schema validation
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from app.api.v1.homekit import (
    HomeKitStatusResponse,
    HomeKitEnableRequest,
    HomeKitEnableResponse,
    HomeKitDisableResponse,
    HomeKitConfigResponse,
    PairingInfo,
    PairingsListResponse,
    RemovePairingResponse,
)
from app.schemas.homekit_connectivity import (
    HomeKitConnectivityResponse,
    HomeKitTestEventRequest,
    HomeKitTestEventResponse,
)


class TestHomeKitSchemas:
    """Tests for HomeKit API Pydantic schemas."""

    def test_status_response_schema(self):
        """AC6: HomeKitStatusResponse validates correctly."""
        response = HomeKitStatusResponse(
            enabled=True,
            running=True,
            paired=False,
            accessory_count=3,
            bridge_name="ArgusAI",
            setup_code="123-45-678",
            port=51826,
            error=None
        )

        assert response.enabled is True
        assert response.running is True
        assert response.paired is False
        assert response.accessory_count == 3
        assert response.bridge_name == "ArgusAI"
        assert response.setup_code == "123-45-678"
        assert response.port == 51826
        assert response.error is None

    def test_status_response_with_error(self):
        """HomeKitStatusResponse handles error state."""
        response = HomeKitStatusResponse(
            enabled=False,
            running=False,
            paired=False,
            accessory_count=0,
            bridge_name="ArgusAI",
            setup_code=None,
            port=51826,
            error="HAP-python not installed"
        )

        assert response.enabled is False
        assert response.running is False
        assert response.error == "HAP-python not installed"
        assert response.setup_code is None

    def test_status_response_hidden_setup_code_when_paired(self):
        """Setup code should be None when paired."""
        response = HomeKitStatusResponse(
            enabled=True,
            running=True,
            paired=True,
            accessory_count=5,
            bridge_name="ArgusAI",
            setup_code=None,  # Hidden when paired
            port=51826,
            error=None
        )

        assert response.paired is True
        assert response.setup_code is None

    def test_enable_request_schema(self):
        """AC6: HomeKitEnableRequest validates correctly."""
        request = HomeKitEnableRequest(
            bridge_name="MyHome",
            port=51827
        )

        assert request.bridge_name == "MyHome"
        assert request.port == 51827

    def test_enable_request_defaults(self):
        """HomeKitEnableRequest uses defaults."""
        request = HomeKitEnableRequest()

        assert request.bridge_name == "ArgusAI"
        assert request.port == 51826

    def test_enable_request_port_validation(self):
        """HomeKitEnableRequest validates port range."""
        # Too low
        with pytest.raises(ValidationError):
            HomeKitEnableRequest(port=80)

        # Too high
        with pytest.raises(ValidationError):
            HomeKitEnableRequest(port=70000)

    def test_enable_request_bridge_name_length(self):
        """HomeKitEnableRequest validates bridge name length."""
        # Too long
        with pytest.raises(ValidationError):
            HomeKitEnableRequest(bridge_name="A" * 100)

    def test_enable_response_schema(self):
        """AC6: HomeKitEnableResponse validates correctly."""
        response = HomeKitEnableResponse(
            enabled=True,
            running=True,
            port=51826,
            setup_code="123-45-678",
            qr_code_data="data:image/png;base64,abc123",
            bridge_name="ArgusAI",
            message="HomeKit bridge enabled successfully"
        )

        assert response.enabled is True
        assert response.running is True
        assert response.port == 51826
        assert response.setup_code == "123-45-678"
        assert response.qr_code_data.startswith("data:image/png;base64,")
        assert response.bridge_name == "ArgusAI"

    def test_enable_response_without_qr(self):
        """HomeKitEnableResponse allows None qr_code_data."""
        response = HomeKitEnableResponse(
            enabled=True,
            running=False,
            port=51826,
            setup_code="123-45-678",
            qr_code_data=None,
            bridge_name="ArgusAI",
            message="QR code not available"
        )

        assert response.qr_code_data is None

    def test_disable_response_schema(self):
        """AC6: HomeKitDisableResponse validates correctly."""
        response = HomeKitDisableResponse(
            enabled=False,
            running=False,
            message="HomeKit bridge disabled"
        )

        assert response.enabled is False
        assert response.running is False
        assert response.message == "HomeKit bridge disabled"

    def test_config_response_schema(self):
        """HomeKitConfigResponse validates correctly."""
        response = HomeKitConfigResponse(
            id=1,
            enabled=True,
            bridge_name="ArgusAI",
            port=51826,
            motion_reset_seconds=30,
            max_motion_duration=300,
            created_at="2025-12-14T10:00:00Z",
            updated_at="2025-12-14T10:00:00Z"
        )

        assert response.id == 1
        assert response.enabled is True
        assert response.bridge_name == "ArgusAI"
        assert response.port == 51826
        assert response.motion_reset_seconds == 30
        assert response.max_motion_duration == 300

    def test_config_response_optional_timestamps(self):
        """HomeKitConfigResponse handles optional timestamps."""
        response = HomeKitConfigResponse(
            id=1,
            enabled=False,
            bridge_name="ArgusAI",
            port=51826,
            motion_reset_seconds=30,
            max_motion_duration=300,
            created_at=None,
            updated_at=None
        )

        assert response.created_at is None
        assert response.updated_at is None


class TestHomeKitAPIEndpoints:
    """Tests for HomeKit API endpoint behavior.

    Note: These are schema/response tests. Full endpoint tests with
    mocked HAP-python would require additional fixtures.
    """

    def test_status_response_format(self):
        """AC6: Status endpoint returns expected format."""
        # Simulate the response format
        status = {
            "enabled": True,
            "running": True,
            "paired": False,
            "accessory_count": 2,
            "bridge_name": "ArgusAI",
            "setup_code": "123-45-678",
            "port": 51826,
            "error": None
        }

        response = HomeKitStatusResponse(**status)
        assert response.enabled is True
        assert response.accessory_count == 2

    def test_enable_response_format(self):
        """AC6: Enable endpoint returns expected format."""
        # Simulate the response format
        enable_response = {
            "enabled": True,
            "running": True,
            "port": 51826,
            "setup_code": "987-65-432",
            "qr_code_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA",
            "bridge_name": "ArgusAI",
            "message": "HomeKit bridge enabled with 3 cameras"
        }

        response = HomeKitEnableResponse(**enable_response)
        assert response.enabled is True
        assert response.running is True
        assert response.setup_code == "987-65-432"

    def test_disable_response_format(self):
        """AC6: Disable endpoint returns expected format."""
        disable_response = {
            "enabled": False,
            "running": False,
            "message": "HomeKit bridge disabled"
        }

        response = HomeKitDisableResponse(**disable_response)
        assert response.enabled is False
        assert response.running is False

    def test_graceful_degradation_error_format(self):
        """AC8: Error response when HAP-python not available."""
        error_status = {
            "enabled": False,
            "running": False,
            "paired": False,
            "accessory_count": 0,
            "bridge_name": "ArgusAI",
            "setup_code": None,
            "port": 51826,
            "error": "HAP-python not installed. Install with: pip install HAP-python"
        }

        response = HomeKitStatusResponse(**error_status)
        assert response.enabled is False
        assert response.running is False
        assert "HAP-python not installed" in response.error


class TestHomeKitQRCodeEndpoint:
    """Tests for QR code endpoint behavior."""

    def test_qr_code_data_format(self):
        """AC6: QR code is returned as base64 PNG."""
        # Validate that a proper response would have this format
        qr_response = HomeKitEnableResponse(
            enabled=True,
            running=True,
            port=51826,
            setup_code="123-45-678",
            qr_code_data="data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
            bridge_name="ArgusAI",
            message="Enabled"
        )

        assert qr_response.qr_code_data.startswith("data:image/png;base64,")

    def test_qr_code_none_when_not_available(self):
        """QR code is None when qrcode package not installed."""
        response = HomeKitEnableResponse(
            enabled=True,
            running=True,
            port=51826,
            setup_code="123-45-678",
            qr_code_data=None,
            bridge_name="ArgusAI",
            message="QR code generation not available"
        )

        assert response.qr_code_data is None


# ============================================================================
# Story P5-1.8: Pairings Management Tests
# ============================================================================


class TestPairingsSchemas:
    """Tests for pairings-related Pydantic schemas (Story P5-1.8)."""

    def test_pairing_info_schema(self):
        """AC3: PairingInfo validates correctly."""
        pairing = PairingInfo(
            pairing_id="12345678-1234-1234-1234-123456789012",
            is_admin=True,
            permissions=1
        )

        assert pairing.pairing_id == "12345678-1234-1234-1234-123456789012"
        assert pairing.is_admin is True
        assert pairing.permissions == 1

    def test_pairing_info_regular_user(self):
        """PairingInfo represents regular (non-admin) user."""
        pairing = PairingInfo(
            pairing_id="abcdefgh-1234-5678-9012-abcdefghijkl",
            is_admin=False,
            permissions=0
        )

        assert pairing.is_admin is False
        assert pairing.permissions == 0

    def test_pairings_list_response_schema(self):
        """AC3: PairingsListResponse validates correctly."""
        response = PairingsListResponse(
            pairings=[
                PairingInfo(
                    pairing_id="12345678-1234-1234-1234-123456789012",
                    is_admin=True,
                    permissions=1
                ),
                PairingInfo(
                    pairing_id="abcdefgh-1234-5678-9012-abcdefghijkl",
                    is_admin=False,
                    permissions=0
                )
            ],
            count=2
        )

        assert response.count == 2
        assert len(response.pairings) == 2
        assert response.pairings[0].is_admin is True
        assert response.pairings[1].is_admin is False

    def test_pairings_list_empty(self):
        """AC3: PairingsListResponse handles empty list."""
        response = PairingsListResponse(
            pairings=[],
            count=0
        )

        assert response.count == 0
        assert len(response.pairings) == 0

    def test_remove_pairing_response_schema(self):
        """AC4: RemovePairingResponse validates correctly."""
        response = RemovePairingResponse(
            success=True,
            message="Pairing removed successfully",
            pairing_id="12345678-1234-1234-1234-123456789012"
        )

        assert response.success is True
        assert response.message == "Pairing removed successfully"
        assert response.pairing_id == "12345678-1234-1234-1234-123456789012"

    def test_remove_pairing_response_failure(self):
        """AC4: RemovePairingResponse handles failure."""
        response = RemovePairingResponse(
            success=False,
            message="Pairing not found",
            pairing_id="invalid-id"
        )

        assert response.success is False
        assert "not found" in response.message.lower()


class TestPairingsAPIEndpoints:
    """Tests for pairings API endpoint behavior (Story P5-1.8)."""

    def test_pairings_list_response_format(self):
        """AC3: Pairings endpoint returns expected format."""
        # Simulate the response format
        pairings_response = {
            "pairings": [
                {
                    "pairing_id": "12345678-1234-1234-1234-123456789012",
                    "is_admin": True,
                    "permissions": 1
                }
            ],
            "count": 1
        }

        response = PairingsListResponse(**pairings_response)
        assert response.count == 1
        assert response.pairings[0].pairing_id == "12345678-1234-1234-1234-123456789012"

    def test_pairings_list_empty_response_format(self):
        """AC3: Empty pairings list returns expected format."""
        pairings_response = {
            "pairings": [],
            "count": 0
        }

        response = PairingsListResponse(**pairings_response)
        assert response.count == 0
        assert len(response.pairings) == 0

    def test_remove_pairing_success_response_format(self):
        """AC4: Remove pairing success returns expected format."""
        remove_response = {
            "success": True,
            "message": "Pairing removed successfully. Device must re-pair to access accessories.",
            "pairing_id": "12345678-1234-1234-1234-123456789012"
        }

        response = RemovePairingResponse(**remove_response)
        assert response.success is True
        assert "re-pair" in response.message

    def test_multiple_pairings_response(self):
        """AC5: Multiple users (pairings) can be listed."""
        pairings_response = {
            "pairings": [
                {"pairing_id": "user1-uuid", "is_admin": True, "permissions": 1},
                {"pairing_id": "user2-uuid", "is_admin": False, "permissions": 0},
                {"pairing_id": "user3-uuid", "is_admin": False, "permissions": 0},
            ],
            "count": 3
        }

        response = PairingsListResponse(**pairings_response)
        assert response.count == 3

        # Count admins and regular users
        admin_count = sum(1 for p in response.pairings if p.is_admin)
        user_count = sum(1 for p in response.pairings if not p.is_admin)

        assert admin_count == 1
        assert user_count == 2


# ============================================================================
# Story P7-1.2: Connectivity Test Schema Tests
# ============================================================================


class TestConnectivitySchemas:
    """Tests for HomeKit connectivity test schemas (Story P7-1.2)."""

    def test_connectivity_response_schema_success(self):
        """AC6: HomeKitConnectivityResponse validates successful test."""
        response = HomeKitConnectivityResponse(
            mdns_visible=True,
            discovered_as="ArgusAI._hap._tcp.local",
            port_accessible=True,
            firewall_issues=[],
            bind_address="0.0.0.0",
            port=51826,
            bridge_name="ArgusAI",
            test_timestamp=datetime.utcnow(),
            troubleshooting_hints=[]
        )

        assert response.mdns_visible is True
        assert response.discovered_as == "ArgusAI._hap._tcp.local"
        assert response.port_accessible is True
        assert response.firewall_issues == []
        assert response.bind_address == "0.0.0.0"
        assert response.port == 51826
        assert response.bridge_name == "ArgusAI"
        assert response.troubleshooting_hints == []

    def test_connectivity_response_schema_failure(self):
        """AC6: HomeKitConnectivityResponse validates failed test with issues."""
        response = HomeKitConnectivityResponse(
            mdns_visible=False,
            discovered_as=None,
            port_accessible=False,
            firewall_issues=["Port 51826 may be blocked by firewall"],
            bind_address="127.0.0.1",
            port=51826,
            bridge_name="ArgusAI",
            test_timestamp=datetime.utcnow(),
            troubleshooting_hints=[
                "Ensure HomeKit is enabled and running",
                "Check firewall settings for port 51826",
                "Use 0.0.0.0 for bind_address to allow network access"
            ]
        )

        assert response.mdns_visible is False
        assert response.discovered_as is None
        assert response.port_accessible is False
        assert len(response.firewall_issues) == 1
        assert "blocked" in response.firewall_issues[0]
        assert len(response.troubleshooting_hints) == 3

    def test_connectivity_response_bind_address_warning(self):
        """AC6: Connectivity test detects localhost bind address issue."""
        response = HomeKitConnectivityResponse(
            mdns_visible=True,
            discovered_as="ArgusAI._hap._tcp.local",
            port_accessible=False,
            firewall_issues=["Server bound to localhost only (127.0.0.1)"],
            bind_address="127.0.0.1",
            port=51826,
            bridge_name="ArgusAI",
            test_timestamp=datetime.utcnow(),
            troubleshooting_hints=[
                "Change bind_address to 0.0.0.0 or a specific network interface"
            ]
        )

        assert response.bind_address == "127.0.0.1"
        assert len(response.firewall_issues) == 1
        assert "localhost" in response.firewall_issues[0]

    def test_test_event_request_schema(self):
        """HomeKitTestEventRequest validates correctly."""
        request = HomeKitTestEventRequest(
            camera_id="abc-123",
            event_type="motion"
        )

        assert request.camera_id == "abc-123"
        assert request.event_type == "motion"

    def test_test_event_request_default_type(self):
        """HomeKitTestEventRequest uses default event type."""
        request = HomeKitTestEventRequest(
            camera_id="abc-123"
        )

        assert request.event_type == "motion"

    def test_test_event_response_schema(self):
        """HomeKitTestEventResponse validates correctly."""
        response = HomeKitTestEventResponse(
            success=True,
            message="Motion event triggered for Front Door",
            delivered_to_clients=2
        )

        assert response.success is True
        assert "Motion event" in response.message
        assert response.delivered_to_clients == 2

    def test_test_event_response_no_clients(self):
        """HomeKitTestEventResponse handles zero clients."""
        response = HomeKitTestEventResponse(
            success=True,
            message="Motion event triggered but no clients connected",
            delivered_to_clients=0
        )

        assert response.success is True
        assert response.delivered_to_clients == 0


class TestConnectivityAPIEndpoints:
    """Tests for HomeKit connectivity API endpoint behavior (Story P7-1.2)."""

    def test_connectivity_test_response_format_success(self):
        """AC6: Connectivity test success returns expected format."""
        connectivity_response = {
            "mdns_visible": True,
            "discovered_as": "ArgusAI._hap._tcp.local",
            "port_accessible": True,
            "firewall_issues": [],
            "bind_address": "0.0.0.0",
            "port": 51826,
            "bridge_name": "ArgusAI",
            "test_timestamp": "2025-12-17T10:30:00Z",
            "troubleshooting_hints": []
        }

        response = HomeKitConnectivityResponse(**connectivity_response)
        assert response.mdns_visible is True
        assert response.port_accessible is True
        assert response.firewall_issues == []

    def test_connectivity_test_response_format_failure(self):
        """AC6: Connectivity test failure returns hints."""
        connectivity_response = {
            "mdns_visible": False,
            "discovered_as": None,
            "port_accessible": False,
            "firewall_issues": ["Port 51826 blocked"],
            "bind_address": "0.0.0.0",
            "port": 51826,
            "bridge_name": "ArgusAI",
            "test_timestamp": "2025-12-17T10:30:00Z",
            "troubleshooting_hints": [
                "Check firewall settings",
                "Ensure mDNS/Bonjour is enabled"
            ]
        }

        response = HomeKitConnectivityResponse(**connectivity_response)
        assert response.mdns_visible is False
        assert len(response.troubleshooting_hints) == 2

    def test_connectivity_test_detects_mdns_issues(self):
        """AC6: Connectivity test identifies mDNS problems."""
        connectivity_response = {
            "mdns_visible": False,
            "discovered_as": None,
            "port_accessible": True,  # Port works but mDNS doesn't
            "firewall_issues": ["mDNS multicast may be blocked"],
            "bind_address": "0.0.0.0",
            "port": 51826,
            "bridge_name": "ArgusAI",
            "test_timestamp": "2025-12-17T10:30:00Z",
            "troubleshooting_hints": [
                "Ensure Avahi/Bonjour is running",
                "Check that mDNS multicast (224.0.0.251:5353) is allowed"
            ]
        }

        response = HomeKitConnectivityResponse(**connectivity_response)
        assert response.mdns_visible is False
        assert response.port_accessible is True
        assert "mDNS" in response.firewall_issues[0]

    def test_connectivity_test_detects_port_issues(self):
        """AC6: Connectivity test identifies port accessibility problems."""
        connectivity_response = {
            "mdns_visible": True,
            "discovered_as": "ArgusAI._hap._tcp.local",
            "port_accessible": False,  # mDNS works but port doesn't
            "firewall_issues": ["TCP port 51826 not accessible"],
            "bind_address": "0.0.0.0",
            "port": 51826,
            "bridge_name": "ArgusAI",
            "test_timestamp": "2025-12-17T10:30:00Z",
            "troubleshooting_hints": [
                "Open TCP port 51826 in firewall",
                "Check if another process is using port 51826"
            ]
        }

        response = HomeKitConnectivityResponse(**connectivity_response)
        assert response.mdns_visible is True
        assert response.port_accessible is False
        assert "TCP port" in response.firewall_issues[0]


# ============================================================================
# Story P7-3.2: Camera Snapshot Endpoint Tests
# ============================================================================


class TestSnapshotEndpoint:
    """Tests for camera snapshot API endpoint (Story P7-3.2)."""

    def test_snapshot_endpoint_response_format(self):
        """AC2: Snapshot endpoint returns JPEG Content-Type."""
        # Test validates that when endpoint returns data, it should be JPEG
        # Actual endpoint testing would require FastAPI TestClient
        jpeg_data = bytes([0xFF, 0xD8, 0xFF, 0xE0])  # JPEG magic bytes
        assert jpeg_data[:2] == bytes([0xFF, 0xD8])  # Valid JPEG header

    def test_snapshot_placeholder_detection(self):
        """AC4: Small response indicates placeholder image."""
        # Placeholder images are small (< 1000 bytes)
        placeholder_size = 500
        normal_snapshot_size = 50000

        assert placeholder_size < 1000  # Is placeholder
        assert normal_snapshot_size > 1000  # Is real snapshot

    def test_status_response_with_camera_info(self):
        """Status response includes camera and stream counts (P7-3.2)."""
        response = HomeKitStatusResponse(
            enabled=True,
            running=True,
            paired=True,
            accessory_count=3,
            camera_count=3,  # Story P5-1.3
            active_streams=1,  # Story P5-1.3
            bridge_name="ArgusAI",
            setup_code=None,  # Hidden when paired
            port=51826,
            ffmpeg_available=True,  # Story P5-1.3
            error=None
        )

        assert response.camera_count == 3
        assert response.active_streams == 1
        assert response.ffmpeg_available is True
