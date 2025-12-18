"""
HomeKit configuration module (Story P4-6.1, P4-6.2, P5-1.2, P5-1.5, P5-1.6, P7-1.2)

Defines HomeKit-related settings for the HAP-python accessory server.
Story P5-1.2 adds Setup URI generation and enhanced PIN validation.
Story P5-1.5 adds occupancy sensor configuration for person detection.
Story P5-1.6 adds vehicle/animal/package sensor configuration.
Story P7-1.2 adds network binding configuration (bind_address, mdns_interface).
"""
import os
import random
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set

# Default HomeKit port (standard HAP port)
DEFAULT_HOMEKIT_PORT = 51826

# Default bridge name
DEFAULT_BRIDGE_NAME = "ArgusAI"

# Default manufacturer
DEFAULT_MANUFACTURER = "ArgusAI"

# Story P4-6.2: Motion reset defaults
DEFAULT_MOTION_RESET_SECONDS = 30
DEFAULT_MAX_MOTION_DURATION = 300  # 5 minutes

# Story P5-1.5: Occupancy sensor defaults (person detection only)
DEFAULT_OCCUPANCY_TIMEOUT_SECONDS = 300  # 5 minutes
DEFAULT_MAX_OCCUPANCY_DURATION = 1800  # 30 minutes

# Story P5-1.6: Detection-type-specific sensor defaults
DEFAULT_VEHICLE_RESET_SECONDS = 30  # 30 seconds
DEFAULT_ANIMAL_RESET_SECONDS = 30  # 30 seconds
DEFAULT_PACKAGE_RESET_SECONDS = 60  # 60 seconds (packages persist longer)

# Story P7-1.1: Diagnostic logging defaults
DEFAULT_DIAGNOSTIC_LOG_SIZE = 100  # Maximum diagnostic log entries to retain

# Story P7-1.2: Network binding defaults
DEFAULT_BIND_ADDRESS = "0.0.0.0"  # Bind to all interfaces by default

# Story P5-1.2: HomeKit category constants
HOMEKIT_CATEGORY_BRIDGE = 2  # HAP category for Bridge accessory

# Story P5-1.2: Invalid PIN code patterns per HomeKit restrictions
INVALID_PIN_PATTERNS: Set[str] = {
    # All same digits
    "000-00-000", "111-11-111", "222-22-222", "333-33-333",
    "444-44-444", "555-55-555", "666-66-666", "777-77-777",
    "888-88-888", "999-99-999",
    # Sequential patterns
    "123-45-678", "012-34-567", "234-56-789",
    # Common patterns
    "121-21-212", "123-12-312",
}


def is_valid_pincode(code: str) -> bool:
    """
    Validate a PIN code against HomeKit restrictions (Story P5-1.2 AC1).

    HomeKit restricts certain PIN patterns:
    - All same digits (e.g., 000-00-000, 111-11-111)
    - Sequential patterns (e.g., 123-45-678)
    - Common/predictable patterns

    Args:
        code: PIN code in XXX-XX-XXX format

    Returns:
        True if valid, False if matches restricted pattern
    """
    if code in INVALID_PIN_PATTERNS:
        return False

    # Check for format validity
    parts = code.split("-")
    if len(parts) != 3 or len(parts[0]) != 3 or len(parts[1]) != 2 or len(parts[2]) != 3:
        return False

    # Check all digits
    digits_only = code.replace("-", "")
    if not digits_only.isdigit() or len(digits_only) != 8:
        return False

    return True


def generate_pincode() -> str:
    """
    Generate a random 8-digit HomeKit pairing code in XXX-XX-XXX format.

    Validates against HomeKit restrictions per Story P5-1.2 AC1:
    - No all-same digits (000-00-000, etc.)
    - No sequential patterns (123-45-678)
    - No common/predictable patterns

    Returns:
        str: Validated pincode in format "123-45-678"
    """
    max_attempts = 100  # Prevent infinite loops
    for _ in range(max_attempts):
        code = f"{random.randint(0, 999):03d}-{random.randint(0, 99):02d}-{random.randint(0, 999):03d}"
        if is_valid_pincode(code):
            return code

    # Fallback to a known-valid code if somehow all attempts fail
    return "031-45-154"


def generate_setup_id() -> str:
    """
    Generate a 4-character alphanumeric Setup ID for HomeKit URI (Story P5-1.2 AC2).

    The Setup ID is used in the X-HM:// URI format for QR code pairing.
    It must be uppercase alphanumeric (0-9, A-Z).

    Returns:
        str: 4-character uppercase alphanumeric string (e.g., "AB1C")
    """
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(4))


def generate_setup_uri(setup_code: str, setup_id: str, category: int = HOMEKIT_CATEGORY_BRIDGE) -> str:
    """
    Generate HomeKit Setup URI for QR code pairing (Story P5-1.2 AC2).

    The HomeKit Setup URI format is X-HM://[payload][setup_id] where:
    - payload is base36-encoded value containing setup_code, category, and flags
    - setup_id is the 4-character alphanumeric identifier

    The payload encodes:
    - Setup code (27 bits): The 8-digit PIN without dashes
    - Flags (4 bits): 0x2 for IP transport
    - Category (8 bits): HAP accessory category (2 = Bridge)

    Reference: HAP specification and HAP-python implementation.

    Args:
        setup_code: PIN code in XXX-XX-XXX format
        setup_id: 4-character alphanumeric setup ID
        category: HAP category (default 2 for Bridge)

    Returns:
        str: X-HM:// URI string (e.g., "X-HM://0023B6WQLAB1C")

    Raises:
        ValueError: If setup_code format is invalid or setup_id is not 4 chars
    """
    # Validate inputs
    if not is_valid_pincode(setup_code):
        # Allow any format-valid code even if in "simple" list, for flexibility
        parts = setup_code.split("-")
        if len(parts) != 3:
            raise ValueError(f"Invalid setup_code format: {setup_code}. Expected XXX-XX-XXX")

    if len(setup_id) != 4:
        raise ValueError(f"setup_id must be 4 characters, got {len(setup_id)}")

    # Remove dashes and convert to integer
    code_digits = setup_code.replace("-", "")
    code_int = int(code_digits)

    # Build payload per HAP specification:
    # Bits 0-7: Category (8 bits)
    # Bits 8-11: Flags (4 bits) - 0x2 = IP transport
    # Bits 12-38: Setup code (27 bits)
    #
    # Total payload = (setup_code << 12) | (flags << 8) | category
    flags = 0x2  # IP transport flag
    payload = (code_int << 12) | (flags << 8) | (category & 0xFF)

    # Encode as base36 (0-9, A-Z)
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    encoded = ""
    temp = payload
    while temp > 0:
        encoded = chars[temp % 36] + encoded
        temp //= 36

    # Pad to 9 characters (standard HomeKit payload length)
    encoded = encoded.zfill(9)

    return f"X-HM://{encoded}{setup_id}"


def parse_setup_uri(uri: str) -> dict:
    """
    Parse a HomeKit Setup URI to extract components (for testing/debugging).

    Args:
        uri: X-HM:// URI string

    Returns:
        dict with keys: setup_code, setup_id, category, flags, valid

    Raises:
        ValueError: If URI format is invalid
    """
    if not uri.startswith("X-HM://"):
        raise ValueError(f"Invalid URI prefix, expected X-HM://")

    content = uri[7:]  # Remove "X-HM://"
    if len(content) < 13:  # 9 payload + 4 setup_id minimum
        raise ValueError(f"URI too short: {len(content)} chars")

    payload_str = content[:-4]
    setup_id = content[-4:]

    # Decode base36 payload
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    payload = 0
    for char in payload_str:
        payload = payload * 36 + chars.index(char.upper())

    # Extract components
    category = payload & 0xFF
    flags = (payload >> 8) & 0xF
    setup_code_int = payload >> 12

    # Format setup code as XXX-XX-XXX
    setup_code_str = f"{setup_code_int:08d}"
    setup_code = f"{setup_code_str[:3]}-{setup_code_str[3:5]}-{setup_code_str[5:]}"

    return {
        "setup_code": setup_code,
        "setup_id": setup_id,
        "category": category,
        "flags": flags,
        "valid": True
    }


@dataclass
class HomekitConfig:
    """
    Configuration for HomeKit accessory server.

    Attributes:
        enabled: Whether HomeKit integration is enabled
        port: HAP server port (default 51826)
        bridge_name: Display name for the HomeKit bridge
        manufacturer: Manufacturer name shown in Home app
        persist_dir: Directory for storing pairing state
        pincode: 8-digit pairing code in XXX-XX-XXX format
        motion_reset_seconds: Seconds before motion sensor resets to False (Story P4-6.2)
        max_motion_duration: Maximum duration for continuous motion (Story P4-6.2)
        occupancy_timeout_seconds: Seconds before occupancy sensor resets to False (Story P5-1.5)
        max_occupancy_duration: Maximum duration for continuous occupancy (Story P5-1.5)
        vehicle_reset_seconds: Seconds before vehicle sensor resets to False (Story P5-1.6)
        animal_reset_seconds: Seconds before animal sensor resets to False (Story P5-1.6)
        package_reset_seconds: Seconds before package sensor resets to False (Story P5-1.6)
        diagnostic_log_size: Maximum diagnostic log entries to retain (Story P7-1.1)
        bind_address: IP address to bind the HAP server to (Story P7-1.2)
        mdns_interface: Network interface for mDNS advertisement (Story P7-1.2)
    """
    enabled: bool = False
    port: int = DEFAULT_HOMEKIT_PORT
    bridge_name: str = DEFAULT_BRIDGE_NAME
    manufacturer: str = DEFAULT_MANUFACTURER
    persist_dir: str = "data/homekit"
    pincode: Optional[str] = None
    motion_reset_seconds: int = DEFAULT_MOTION_RESET_SECONDS
    max_motion_duration: int = DEFAULT_MAX_MOTION_DURATION
    occupancy_timeout_seconds: int = DEFAULT_OCCUPANCY_TIMEOUT_SECONDS
    max_occupancy_duration: int = DEFAULT_MAX_OCCUPANCY_DURATION
    vehicle_reset_seconds: int = DEFAULT_VEHICLE_RESET_SECONDS
    animal_reset_seconds: int = DEFAULT_ANIMAL_RESET_SECONDS
    package_reset_seconds: int = DEFAULT_PACKAGE_RESET_SECONDS
    diagnostic_log_size: int = DEFAULT_DIAGNOSTIC_LOG_SIZE
    bind_address: str = DEFAULT_BIND_ADDRESS
    mdns_interface: Optional[str] = None

    @property
    def persist_file(self) -> str:
        """Get the full path to the persistence file."""
        return os.path.join(self.persist_dir, "accessory.state")

    @property
    def pincode_bytes(self) -> bytes:
        """Get pincode as bytes for HAP-python."""
        if self.pincode:
            return self.pincode.encode('utf-8')
        return b"031-45-154"  # Default pincode if none set

    def ensure_persist_dir(self) -> None:
        """Create persistence directory if it doesn't exist."""
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)


def get_homekit_config() -> HomekitConfig:
    """
    Load HomeKit configuration from environment variables.

    Environment variables:
        HOMEKIT_ENABLED: Enable HomeKit integration (default: false)
        HOMEKIT_PORT: HAP server port (default: 51826)
        HOMEKIT_BRIDGE_NAME: Bridge display name (default: ArgusAI)
        HOMEKIT_MANUFACTURER: Manufacturer name (default: ArgusAI)
        HOMEKIT_PERSIST_DIR: Directory for state persistence (default: data/homekit)
        HOMEKIT_PINCODE: Pairing code in XXX-XX-XXX format (auto-generated if not set)
        HOMEKIT_MOTION_RESET_SECONDS: Motion sensor reset timeout (default: 30)
        HOMEKIT_MAX_MOTION_DURATION: Max continuous motion duration (default: 300)
        HOMEKIT_OCCUPANCY_TIMEOUT_SECONDS: Occupancy sensor reset timeout (default: 300, Story P5-1.5)
        HOMEKIT_MAX_OCCUPANCY_DURATION: Max continuous occupancy duration (default: 1800, Story P5-1.5)
        HOMEKIT_VEHICLE_RESET_SECONDS: Vehicle sensor reset timeout (default: 30, Story P5-1.6)
        HOMEKIT_ANIMAL_RESET_SECONDS: Animal sensor reset timeout (default: 30, Story P5-1.6)
        HOMEKIT_PACKAGE_RESET_SECONDS: Package sensor reset timeout (default: 60, Story P5-1.6)
        HOMEKIT_DIAGNOSTIC_LOG_SIZE: Max diagnostic log entries (default: 100, Story P7-1.1)
        HOMEKIT_BIND_ADDRESS: IP address to bind HAP server (default: 0.0.0.0, Story P7-1.2)
        HOMEKIT_MDNS_INTERFACE: Network interface for mDNS (default: None, Story P7-1.2)

    Returns:
        HomekitConfig: Configuration instance
    """
    return HomekitConfig(
        enabled=os.getenv("HOMEKIT_ENABLED", "false").lower() in ("true", "1", "yes"),
        port=int(os.getenv("HOMEKIT_PORT", str(DEFAULT_HOMEKIT_PORT))),
        bridge_name=os.getenv("HOMEKIT_BRIDGE_NAME", DEFAULT_BRIDGE_NAME),
        manufacturer=os.getenv("HOMEKIT_MANUFACTURER", DEFAULT_MANUFACTURER),
        persist_dir=os.getenv("HOMEKIT_PERSIST_DIR", "data/homekit"),
        pincode=os.getenv("HOMEKIT_PINCODE"),
        motion_reset_seconds=int(os.getenv("HOMEKIT_MOTION_RESET_SECONDS", str(DEFAULT_MOTION_RESET_SECONDS))),
        max_motion_duration=int(os.getenv("HOMEKIT_MAX_MOTION_DURATION", str(DEFAULT_MAX_MOTION_DURATION))),
        occupancy_timeout_seconds=int(os.getenv("HOMEKIT_OCCUPANCY_TIMEOUT_SECONDS", str(DEFAULT_OCCUPANCY_TIMEOUT_SECONDS))),
        max_occupancy_duration=int(os.getenv("HOMEKIT_MAX_OCCUPANCY_DURATION", str(DEFAULT_MAX_OCCUPANCY_DURATION))),
        vehicle_reset_seconds=int(os.getenv("HOMEKIT_VEHICLE_RESET_SECONDS", str(DEFAULT_VEHICLE_RESET_SECONDS))),
        animal_reset_seconds=int(os.getenv("HOMEKIT_ANIMAL_RESET_SECONDS", str(DEFAULT_ANIMAL_RESET_SECONDS))),
        package_reset_seconds=int(os.getenv("HOMEKIT_PACKAGE_RESET_SECONDS", str(DEFAULT_PACKAGE_RESET_SECONDS))),
        diagnostic_log_size=int(os.getenv("HOMEKIT_DIAGNOSTIC_LOG_SIZE", str(DEFAULT_DIAGNOSTIC_LOG_SIZE))),
        bind_address=os.getenv("HOMEKIT_BIND_ADDRESS", DEFAULT_BIND_ADDRESS),
        mdns_interface=os.getenv("HOMEKIT_MDNS_INTERFACE"),
    )
