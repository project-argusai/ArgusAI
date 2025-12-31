"""Session SQLAlchemy ORM model for session tracking (Story P15-2.2)"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone
import hashlib
import logging

logger = logging.getLogger(__name__)


class Session(Base):
    """
    Session model for tracking active user sessions (Story P15-2.2)

    Tracks all active user sessions with metadata for security monitoring
    and session management. Each session corresponds to a JWT token.

    Attributes:
        id: UUID primary key
        user_id: Foreign key to users table
        token_hash: SHA-256 hash of JWT token for validation
        device_info: Parsed device description from User-Agent
        ip_address: Client IP address
        user_agent: Full User-Agent string
        created_at: Session creation timestamp (login time)
        last_active_at: Last request timestamp (for expiry calculation)
        expires_at: Session expiration timestamp

    ADR-P15-001: Session-based auth with JWT
    - HTTP-only cookies prevent XSS
    - Server-side tracking enables session management
    - Token hash stored (not token itself) for security
    """

    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)  # SHA-256 hash
    device_info = Column(String(255), nullable=True)  # Parsed from User-Agent
    ip_address = Column(String(45), nullable=True)  # IPv6 can be 45 chars
    user_agent = Column(String(512), nullable=True)  # Full User-Agent
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    last_active_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Relationship to User
    user = relationship("User", back_populates="sessions")

    # Composite indexes for common queries
    __table_args__ = (
        Index('idx_sessions_user_expires', 'user_id', 'expires_at'),
        Index('idx_sessions_user_created', 'user_id', 'created_at'),
    )

    @classmethod
    def hash_token(cls, token: str) -> str:
        """
        Create SHA-256 hash of JWT token

        Args:
            token: JWT token string

        Returns:
            Hex-encoded SHA-256 hash (64 characters)
        """
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def is_expired(self) -> bool:
        """Check if session has expired"""
        # Handle both naive and aware datetimes (SQLite stores naive)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires_at

    def update_activity(self) -> None:
        """Update last_active_at to current time"""
        self.last_active_at = datetime.now(timezone.utc)

    def __repr__(self):
        return f"<Session(id={self.id}, user_id={self.user_id}, device={self.device_info})>"
