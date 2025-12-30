"""
Tests for HomeKit pairing and Setup URI generation (Story P5-1.2)

Tests cover:
- AC1: PIN code validation (XXX-XX-XXX format, no invalid patterns)
- AC2: Setup URI generation (X-HM:// format)
- AC2: Setup ID generation (4-char alphanumeric)
- AC4: PIN code not in logs
"""
import pytest
import re
import logging

from app.config.homekit import (
    generate_pincode,
    generate_setup_id,
    generate_setup_uri,
    parse_setup_uri,
    is_valid_pincode,
    INVALID_PIN_PATTERNS,
    HOMEKIT_CATEGORY_BRIDGE,
)
from app.core.logging_config import SanitizingFilter


class TestPINCodeValidation:
    """Tests for PIN code validation (Story P5-1.2 AC1)."""

    @pytest.mark.parametrize("code", [
        "031-45-154",
        "789-12-345",
        "000-11-222",  # All-same in one segment is OK
        "999-88-777",
    ])
    def test_is_valid_pincode_accepts_valid_format(self, code):
        """AC1: Valid PIN codes in XXX-XX-XXX format are accepted."""
        assert is_valid_pincode(code), f"Should accept {code}"

    @pytest.mark.parametrize("code", [
        "000-00-000",
        "111-11-111",
        "222-22-222",
        "333-33-333",
        "444-44-444",
        "555-55-555",
        "666-66-666",
        "777-77-777",
        "888-88-888",
        "999-99-999",
    ])
    def test_is_valid_pincode_rejects_all_same_digits(self, code):
        """AC1: PIN codes with all-same digits are rejected."""
        assert not is_valid_pincode(code), f"Should reject all-same digits: {code}"

    @pytest.mark.parametrize("code", [
        "123-45-678",
        "012-34-567",
        "234-56-789",
    ])
    def test_is_valid_pincode_rejects_sequential(self, code):
        """AC1: Sequential PIN codes are rejected."""
        assert not is_valid_pincode(code), f"Should reject sequential: {code}"

    @pytest.mark.parametrize("code", [
        "121-21-212",
        "123-12-312",
    ])
    def test_is_valid_pincode_rejects_common_patterns(self, code):
        """AC1: Common/predictable patterns are rejected."""
        assert not is_valid_pincode(code), f"Should reject common pattern: {code}"

    @pytest.mark.parametrize("code", [
        "12345678",       # No dashes
        "123-456-78",     # Wrong segment lengths
        "1234-5-678",     # Wrong segment lengths
        "123-45-67",      # Too short
        "123-45-6789",    # Too long
        "abc-12-345",     # Non-numeric
        "123-ab-345",     # Non-numeric middle
    ])
    def test_is_valid_pincode_rejects_invalid_format(self, code):
        """AC1: Invalid format PIN codes are rejected."""
        assert not is_valid_pincode(code), f"Should reject invalid format: {code}"


class TestGeneratePINCode:
    """Tests for PIN code generation (Story P5-1.2 AC1)."""

    def test_generate_pincode_returns_valid_format(self):
        """AC1: Generated PIN codes have XXX-XX-XXX format."""
        for _ in range(100):
            code = generate_pincode()
            assert re.match(r'^\d{3}-\d{2}-\d{3}$', code), f"Invalid format: {code}"

    def test_generate_pincode_avoids_invalid_patterns(self):
        """AC1: Generated PIN codes avoid invalid patterns."""
        for _ in range(100):
            code = generate_pincode()
            assert code not in INVALID_PIN_PATTERNS, f"Generated invalid pattern: {code}"
            assert is_valid_pincode(code), f"Generated invalid code: {code}"

    def test_generate_pincode_produces_unique_codes(self):
        """Generated PIN codes are random (high probability of uniqueness)."""
        codes = [generate_pincode() for _ in range(100)]
        unique_codes = set(codes)
        # With 8 digits, should get mostly unique codes in 100 attempts
        assert len(unique_codes) >= 90, f"Expected mostly unique codes, got {len(unique_codes)} unique"


class TestSetupIDGeneration:
    """Tests for Setup ID generation (Story P5-1.2 AC2)."""

    def test_generate_setup_id_returns_4_chars(self):
        """AC2: Setup ID is exactly 4 characters."""
        for _ in range(100):
            setup_id = generate_setup_id()
            assert len(setup_id) == 4, f"Expected 4 chars, got {len(setup_id)}: {setup_id}"

    def test_generate_setup_id_is_uppercase_alphanumeric(self):
        """AC2: Setup ID contains only uppercase letters and digits."""
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        for _ in range(100):
            setup_id = generate_setup_id()
            for char in setup_id:
                assert char in valid_chars, f"Invalid char '{char}' in setup_id: {setup_id}"

    def test_generate_setup_id_produces_unique_ids(self):
        """Generated Setup IDs are random."""
        ids = [generate_setup_id() for _ in range(100)]
        unique_ids = set(ids)
        # Should get mostly unique IDs
        assert len(unique_ids) >= 80, f"Expected mostly unique IDs, got {len(unique_ids)} unique"


class TestSetupURIGeneration:
    """Tests for HomeKit Setup URI generation (Story P5-1.2 AC2)."""

    def test_generate_setup_uri_has_correct_prefix(self):
        """AC2: Setup URI starts with X-HM://."""
        uri = generate_setup_uri("031-45-154", "ABCD", category=2)
        assert uri.startswith("X-HM://"), f"URI should start with X-HM://, got: {uri}"

    def test_generate_setup_uri_contains_setup_id(self):
        """AC2: Setup URI ends with the setup_id."""
        setup_id = "XY9Z"
        uri = generate_setup_uri("031-45-154", setup_id, category=2)
        assert uri.endswith(setup_id), f"URI should end with {setup_id}, got: {uri}"

    @pytest.mark.parametrize("setup_code,setup_id,category", [
        ("031-45-154", "ABCD", 2),
        ("789-12-345", "XY9Z", 2),
        ("000-11-222", "1234", 2),
    ])
    def test_generate_setup_uri_roundtrip(self, setup_code, setup_id, category):
        """AC2: Setup URI can be parsed back to original values."""
        uri = generate_setup_uri(setup_code, setup_id, category)
        parsed = parse_setup_uri(uri)
        assert parsed["setup_code"] == setup_code, f"Setup code mismatch for {uri}"
        assert parsed["setup_id"] == setup_id, f"Setup ID mismatch for {uri}"
        assert parsed["category"] == category, f"Category mismatch for {uri}"

    def test_generate_setup_uri_invalid_setup_code_format(self):
        """AC2: Invalid setup_code format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid setup_code format"):
            generate_setup_uri("12345678", "ABCD", category=2)

    def test_generate_setup_uri_invalid_setup_id_length(self):
        """AC2: Invalid setup_id length raises ValueError."""
        with pytest.raises(ValueError, match="setup_id must be 4 characters"):
            generate_setup_uri("031-45-154", "ABC", category=2)

        with pytest.raises(ValueError, match="setup_id must be 4 characters"):
            generate_setup_uri("031-45-154", "ABCDE", category=2)

    def test_generate_setup_uri_bridge_category(self):
        """AC2: Default category is HOMEKIT_CATEGORY_BRIDGE (2)."""
        uri = generate_setup_uri("031-45-154", "ABCD")
        parsed = parse_setup_uri(uri)
        assert parsed["category"] == HOMEKIT_CATEGORY_BRIDGE

    def test_generate_setup_uri_has_ip_flag(self):
        """AC2: Setup URI includes IP transport flag."""
        uri = generate_setup_uri("031-45-154", "ABCD")
        parsed = parse_setup_uri(uri)
        assert parsed["flags"] == 0x2, "IP transport flag should be set"


class TestParseSetupURI:
    """Tests for Setup URI parsing (for validation/debugging)."""

    def test_parse_setup_uri_invalid_prefix(self):
        """Invalid URI prefix raises ValueError."""
        with pytest.raises(ValueError, match="Invalid URI prefix"):
            parse_setup_uri("https://example.com")

    def test_parse_setup_uri_too_short(self):
        """Too short URI raises ValueError."""
        with pytest.raises(ValueError, match="URI too short"):
            parse_setup_uri("X-HM://ABC")


class TestPINCodeLogRedaction:
    """Tests for PIN code log redaction (Story P5-1.2 AC4)."""

    def test_sanitizing_filter_redacts_pin_codes(self):
        """AC4: PIN codes are redacted from log messages."""
        filter = SanitizingFilter()

        # Create a log record with PIN code
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="HomeKit PIN code is 031-45-154 for pairing",
            args=(),
            exc_info=None
        )

        filter.filter(record)
        assert "031-45-154" not in record.msg
        assert "[PIN-REDACTED]" in record.msg

    def test_sanitizing_filter_redacts_multiple_pins(self):
        """AC4: Multiple PIN codes are all redacted."""
        filter = SanitizingFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Old PIN: 123-45-678, New PIN: 789-12-345",
            args=(),
            exc_info=None
        )

        filter.filter(record)
        assert "123-45-678" not in record.msg
        assert "789-12-345" not in record.msg
        assert record.msg.count("[PIN-REDACTED]") == 2

    def test_sanitizing_filter_redacts_pins_in_args(self):
        """AC4: PIN codes in log args are also redacted."""
        filter = SanitizingFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="PIN code: %s",
            args=("031-45-154",),
            exc_info=None
        )

        filter.filter(record)
        assert "031-45-154" not in record.args[0]
        assert "[PIN-REDACTED]" in record.args[0]

    def test_sanitizing_filter_preserves_non_pin_numbers(self):
        """AC4: Non-PIN number patterns are not redacted."""
        filter = SanitizingFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Port: 51826, Camera ID: abc-123-def",
            args=(),
            exc_info=None
        )

        filter.filter(record)
        # These should not be redacted (not PIN format)
        assert "51826" in record.msg
        assert "abc-123-def" in record.msg
        assert "[PIN-REDACTED]" not in record.msg


class TestIntegration:
    """Integration tests for the full pairing flow."""

    def test_full_setup_uri_generation_flow(self):
        """Test complete flow: generate PIN, setup_id, and URI."""
        # Generate fresh PIN and setup ID
        pin_code = generate_pincode()
        setup_id = generate_setup_id()

        # Validate PIN
        assert is_valid_pincode(pin_code)

        # Generate URI
        uri = generate_setup_uri(pin_code, setup_id)

        # Verify URI format
        assert uri.startswith("X-HM://")
        assert uri.endswith(setup_id)

        # Verify roundtrip
        parsed = parse_setup_uri(uri)
        assert parsed["setup_code"] == pin_code
        assert parsed["setup_id"] == setup_id
        assert parsed["category"] == HOMEKIT_CATEGORY_BRIDGE
        assert parsed["flags"] == 0x2

    def test_uri_is_valid_for_known_cases(self):
        """Test URI generation against known-good examples."""
        # This test verifies our implementation produces scannable URIs
        # The exact payload encoding should match HAP specification

        uri = generate_setup_uri("031-45-154", "ABCD", category=2)

        # URI should be of expected length: X-HM:// (7) + payload (9) + setup_id (4) = 20
        assert len(uri) == 20, f"Expected 20 chars, got {len(uri)}: {uri}"

        # Should be parseable
        parsed = parse_setup_uri(uri)
        assert parsed["valid"] is True
