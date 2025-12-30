"""
HomeKit database models for persistent configuration (Story P5-1.1)

Provides database-backed storage for HomeKit bridge configuration,
replacing the environment-variable-based configuration for runtime changes.
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship, validates
from app.core.database import Base
from app.utils.encryption import encrypt_password, decrypt_password
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class HomeKitConfig(Base):
    """
    HomeKit bridge configuration stored in database.

    This is a singleton table - only one row should exist.
    Falls back to environment variables if no database config exists.

    Attributes:
        id: Primary key (always 1 for singleton)
        enabled: Whether HomeKit integration is enabled
        bridge_name: Display name for the HomeKit bridge (shown in Apple Home)
        pin_code: Encrypted 8-digit pairing code in XXX-XX-XXX format
        setup_id: 4-character alphanumeric ID for HomeKit Setup URI (P5-1.2)
        port: HAP server port (default 51826)
        motion_reset_seconds: Seconds before motion sensor resets to False
        max_motion_duration: Maximum continuous motion duration in seconds
        created_at: Record creation timestamp
        updated_at: Last modification timestamp
    """

    __tablename__ = "homekit_config"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=False, nullable=False)
    bridge_name = Column(String(64), default="ArgusAI", nullable=False)
    pin_code = Column(String(256), nullable=True)  # Fernet encrypted XXX-XX-XXX format
    setup_id = Column(String(4), nullable=True)  # 4-char alphanumeric for HomeKit Setup URI (P5-1.2)
    port = Column(Integer, default=51826, nullable=False)
    motion_reset_seconds = Column(Integer, default=30, nullable=False)
    max_motion_duration = Column(Integer, default=300, nullable=False)
    # Story P14-5.7: Add timezone=True for consistent UTC handling
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationship to accessories
    accessories = relationship(
        "HomeKitAccessory",
        back_populates="config",
        cascade="all, delete-orphan"
    )

    @validates('port')
    def validate_port(self, key, port):
        """Validate port is in valid range."""
        if port is not None and (port < 1024 or port > 65535):
            raise ValueError(f"Port must be between 1024 and 65535, got {port}")
        return port

    @validates('motion_reset_seconds')
    def validate_motion_reset(self, key, seconds):
        """Validate motion reset is positive."""
        if seconds is not None and seconds < 1:
            raise ValueError(f"motion_reset_seconds must be >= 1, got {seconds}")
        return seconds

    @validates('max_motion_duration')
    def validate_max_duration(self, key, seconds):
        """Validate max motion duration is positive."""
        if seconds is not None and seconds < 1:
            raise ValueError(f"max_motion_duration must be >= 1, got {seconds}")
        return seconds

    def set_pin_code(self, pin_code: str) -> None:
        """
        Set PIN code with encryption.

        Args:
            pin_code: Plain text PIN code in XXX-XX-XXX format
        """
        if pin_code:
            self.pin_code = encrypt_password(pin_code)
        else:
            self.pin_code = None

    def get_pin_code(self) -> str | None:
        """
        Get decrypted PIN code.

        Returns:
            Plain text PIN code or None if not set
        """
        if self.pin_code:
            return decrypt_password(self.pin_code)
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary (without sensitive data)."""
        return {
            "id": self.id,
            "enabled": self.enabled,
            "bridge_name": self.bridge_name,
            "setup_id": self.setup_id,
            "port": self.port,
            "motion_reset_seconds": self.motion_reset_seconds,
            "max_motion_duration": self.max_motion_duration,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<HomeKitConfig(id={self.id}, enabled={self.enabled}, "
            f"bridge_name='{self.bridge_name}', port={self.port})>"
        )


class HomeKitAccessory(Base):
    """
    HomeKit accessory mapping to cameras.

    Tracks which cameras are exposed as HomeKit accessories and their
    configuration (accessory type, enabled state, HAP accessory ID).

    Attributes:
        id: Primary key
        config_id: Foreign key to HomeKitConfig (always 1)
        camera_id: Foreign key to cameras table
        accessory_aid: HAP accessory ID (assigned by bridge)
        accessory_type: Type of HomeKit accessory exposed
        enabled: Whether this accessory is active in HomeKit
        created_at: Record creation timestamp
    """

    __tablename__ = "homekit_accessories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("homekit_config.id", ondelete="CASCADE"), default=1, nullable=False)
    camera_id = Column(String(36), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    accessory_aid = Column(Integer, nullable=True)  # HAP accessory ID, assigned when added to bridge
    accessory_type = Column(String(32), default="motion", nullable=False)  # camera, motion, occupancy, doorbell
    enabled = Column(Boolean, default=True, nullable=False)
    # Story P14-5.7: Add timezone=True for consistent UTC handling
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    config = relationship("HomeKitConfig", back_populates="accessories")
    camera = relationship("Camera", back_populates="homekit_accessories")

    @validates('accessory_type')
    def validate_accessory_type(self, key, type_value):
        """Validate accessory type is valid."""
        valid_types = ('camera', 'motion', 'occupancy', 'doorbell')
        if type_value and type_value not in valid_types:
            raise ValueError(f"accessory_type must be one of {valid_types}, got '{type_value}'")
        return type_value

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "config_id": self.config_id,
            "camera_id": self.camera_id,
            "accessory_aid": self.accessory_aid,
            "accessory_type": self.accessory_type,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<HomeKitAccessory(id={self.id}, camera_id='{self.camera_id}', "
            f"type='{self.accessory_type}', enabled={self.enabled})>"
        )
