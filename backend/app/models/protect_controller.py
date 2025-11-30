"""ProtectController SQLAlchemy ORM model for UniFi Protect controller management"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import validates, relationship
from app.core.database import Base
from app.utils.encryption import encrypt_password, decrypt_password
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class ProtectController(Base):
    """
    ProtectController model representing UniFi Protect controller configuration

    Attributes:
        id: UUID primary key
        name: User-friendly controller name (e.g., "Home UDM Pro")
        host: IP address or hostname of the controller
        port: HTTPS port (default 443)
        username: Protect authentication username
        password: Encrypted password (Fernet AES-256)
        verify_ssl: Whether to verify SSL certificates (default False for self-signed)
        is_connected: Current connection status
        last_connected_at: Last successful connection timestamp
        last_error: Last connection error message
        created_at: Record creation timestamp (UTC)
        updated_at: Last modification timestamp (UTC)
    """

    __tablename__ = "protect_controllers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, default=443, nullable=False)
    username = Column(String(100), nullable=False)
    password = Column(String(500), nullable=False)  # Encrypted with Fernet
    verify_ssl = Column(Boolean, default=False, nullable=False)
    is_connected = Column(Boolean, default=False, nullable=False)
    last_connected_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    cameras = relationship("Camera", back_populates="protect_controller", cascade="all, delete-orphan")

    @validates('password')
    def encrypt_password_validator(self, key, value):
        """
        Automatically encrypt password before storing in database

        Validator runs on:
        - Model instantiation: ProtectController(password="plain")
        - Attribute assignment: controller.password = "plain"

        Args:
            key: Column name ('password')
            value: Password value to validate/encrypt

        Returns:
            Encrypted password with 'encrypted:' prefix
        """
        if not value:
            return None

        # Avoid double encryption
        if value.startswith('encrypted:'):
            return value

        try:
            encrypted = encrypt_password(value)
            logger.debug(f"Password encrypted for controller {getattr(self, 'id', 'new')}")
            return encrypted
        except Exception as e:
            logger.error(f"Password encryption failed: {e}")
            raise ValueError("Failed to encrypt password")

    def get_decrypted_password(self) -> str:
        """
        Decrypt password for use in Protect API connection

        Returns:
            Plain text password or None if not set

        Example:
            >>> controller = db.query(ProtectController).first()
            >>> password = controller.get_decrypted_password()
            >>> # Use password for API authentication
        """
        if not self.password:
            return None

        try:
            return decrypt_password(self.password)
        except Exception as e:
            logger.error(f"Password decryption failed for controller {self.id}: {e}")
            raise ValueError("Failed to decrypt password")

    def __repr__(self):
        return f"<ProtectController(id={self.id}, name={self.name}, host={self.host}, connected={self.is_connected})>"
