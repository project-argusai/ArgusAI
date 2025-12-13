"""
HomeKit configuration module (Story P4-6.1)

Defines HomeKit-related settings for the HAP-python accessory server.
"""
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Default HomeKit port (standard HAP port)
DEFAULT_HOMEKIT_PORT = 51826

# Default bridge name
DEFAULT_BRIDGE_NAME = "ArgusAI"

# Default manufacturer
DEFAULT_MANUFACTURER = "ArgusAI"


def generate_pincode() -> str:
    """
    Generate a random 8-digit HomeKit pairing code in XXX-XX-XXX format.

    Returns:
        str: Pincode in format "123-45-678"
    """
    # Generate random digits (avoiding invalid codes like 000-00-000)
    while True:
        code = f"{random.randint(0, 999):03d}-{random.randint(0, 99):02d}-{random.randint(0, 999):03d}"
        # Avoid codes that are all zeros or too simple
        if code not in ("000-00-000", "111-11-111", "123-45-678"):
            return code


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
    """
    enabled: bool = False
    port: int = DEFAULT_HOMEKIT_PORT
    bridge_name: str = DEFAULT_BRIDGE_NAME
    manufacturer: str = DEFAULT_MANUFACTURER
    persist_dir: str = "data/homekit"
    pincode: Optional[str] = None

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
    )
