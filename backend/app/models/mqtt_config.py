"""MQTTConfig SQLAlchemy ORM model for MQTT broker configuration (Story P4-2.1)"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import validates
from app.core.database import Base
from app.utils.encryption import encrypt_password, decrypt_password
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class MQTTConfig(Base):
    """
    MQTT configuration model for Home Assistant integration.

    Stores MQTT broker connection settings and publishing options.
    Only one configuration record should exist (singleton pattern).

    Attributes:
        id: UUID primary key
        broker_host: MQTT broker hostname or IP address
        broker_port: MQTT broker port (default 1883, 8883 for TLS)
        username: Optional authentication username
        password: Encrypted password (Fernet AES-256)
        topic_prefix: Prefix for all MQTT topics (default "liveobject")
        discovery_prefix: Home Assistant discovery prefix (default "homeassistant")
        discovery_enabled: Whether to publish HA discovery messages
        qos: Quality of Service level (0, 1, or 2)
        enabled: Whether MQTT publishing is enabled
        retain_messages: Whether to retain messages on broker
        use_tls: Whether to use TLS/SSL connection
        is_connected: Current connection status (runtime, not persisted preference)
        last_connected_at: Last successful connection timestamp
        last_error: Last connection error message
        messages_published: Total messages published (runtime counter)
        created_at: Record creation timestamp (UTC)
        updated_at: Last modification timestamp (UTC)
    """

    __tablename__ = "mqtt_config"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    broker_host = Column(String(255), nullable=False, default="")
    broker_port = Column(Integer, nullable=False, default=1883)
    username = Column(String(100), nullable=True)
    password = Column(String(500), nullable=True)  # Encrypted with Fernet
    topic_prefix = Column(String(100), nullable=False, default="liveobject")
    discovery_prefix = Column(String(100), nullable=False, default="homeassistant")
    discovery_enabled = Column(Boolean, nullable=False, default=True)
    qos = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=False)
    retain_messages = Column(Boolean, nullable=False, default=True)
    use_tls = Column(Boolean, nullable=False, default=False)
    is_connected = Column(Boolean, nullable=False, default=False)
    last_connected_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    messages_published = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    @validates('password')
    def encrypt_password_validator(self, key, value):
        """
        Automatically encrypt password before storing in database.

        Validator runs on:
        - Model instantiation: MQTTConfig(password="plain")
        - Attribute assignment: config.password = "plain"

        Args:
            key: Column name ('password')
            value: Password value to validate/encrypt

        Returns:
            Encrypted password with 'encrypted:' prefix, or None/empty string
        """
        if not value:
            return value

        # Avoid double encryption
        if value.startswith('encrypted:'):
            return value

        try:
            encrypted = encrypt_password(value)
            logger.debug("MQTT password encrypted")
            return encrypted
        except Exception as e:
            logger.error(f"MQTT password encryption failed: {e}")
            raise ValueError("Failed to encrypt password")

    @validates('qos')
    def validate_qos(self, key, value):
        """Validate QoS is 0, 1, or 2."""
        if value not in (0, 1, 2):
            raise ValueError(f"QoS must be 0, 1, or 2, got {value}")
        return value

    @validates('broker_port')
    def validate_port(self, key, value):
        """Validate port is in valid range."""
        if not (1 <= value <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {value}")
        return value

    def get_decrypted_password(self) -> str | None:
        """
        Decrypt password for use in MQTT connection.

        Returns:
            Plain text password or None if not set

        Example:
            >>> config = db.query(MQTTConfig).first()
            >>> password = config.get_decrypted_password()
            >>> # Use password for MQTT authentication
        """
        if not self.password:
            return None

        try:
            return decrypt_password(self.password)
        except Exception as e:
            logger.error(f"MQTT password decryption failed: {e}")
            raise ValueError("Failed to decrypt password")

    def get_broker_url(self) -> str:
        """Get broker URL in format suitable for display."""
        protocol = "mqtts" if self.use_tls else "mqtt"
        return f"{protocol}://{self.broker_host}:{self.broker_port}"

    def to_dict(self, include_password: bool = False) -> dict:
        """
        Convert config to dictionary for API responses.

        Args:
            include_password: If True, includes '***' placeholder for password presence

        Returns:
            Dictionary representation (password always excluded for security)
        """
        result = {
            "id": self.id,
            "broker_host": self.broker_host,
            "broker_port": self.broker_port,
            "username": self.username,
            "topic_prefix": self.topic_prefix,
            "discovery_prefix": self.discovery_prefix,
            "discovery_enabled": self.discovery_enabled,
            "qos": self.qos,
            "enabled": self.enabled,
            "retain_messages": self.retain_messages,
            "use_tls": self.use_tls,
            "is_connected": self.is_connected,
            "last_connected_at": self.last_connected_at.isoformat() if self.last_connected_at else None,
            "last_error": self.last_error,
            "messages_published": self.messages_published,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_password:
            result["has_password"] = bool(self.password)

        return result

    def __repr__(self):
        return (
            f"<MQTTConfig(id={self.id}, broker={self.broker_host}:{self.broker_port}, "
            f"enabled={self.enabled}, connected={self.is_connected})>"
        )
