"""
API Key SQLAlchemy ORM model for external integrations.

Story P13-1.1: Create APIKey Database Model and Migration

API keys provide secure programmatic access to ArgusAI for:
- Third-party integrations
- Automation scripts
- External dashboards
- Machine-to-machine communication

Security:
- The full key is NEVER stored - only bcrypt hash
- Prefix (first 8 chars) stored separately for identification
- Key displayed once at creation only
"""
from sqlalchemy import Column, String, Boolean, DateTime, Integer, JSON, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class APIKey(Base):
    """
    API Key model for external integrations.

    Attributes:
        id: UUID primary key
        name: Descriptive name for the key
        prefix: First 8 characters of key (after 'argus_') for identification
        key_hash: bcrypt hash of full key (never store plaintext)
        scopes: JSON array of permissions
        is_active: Whether key is currently valid
        expires_at: Optional expiration timestamp
        last_used_at: Last time key was used
        last_used_ip: IP address of last use
        usage_count: Total number of API calls
        rate_limit_per_minute: Max requests per minute
        created_at: When key was created
        created_by: User ID who created the key
        revoked_at: When key was revoked (if applicable)
        revoked_by: User ID who revoked the key
    """

    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    prefix = Column(String(8), nullable=False, index=True)
    key_hash = Column(String(255), nullable=False)  # bcrypt hash

    # Scopes: ["read:events", "read:cameras", "write:cameras", "admin"]
    scopes = Column(JSON, nullable=False, default=list)

    # Status and lifecycle
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Usage tracking
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_used_ip = Column(String(45), nullable=True)  # IPv6 compatible
    usage_count = Column(Integer, default=0, nullable=False)

    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=100, nullable=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def is_expired(self) -> bool:
        """Check if API key has expired."""
        if not self.expires_at:
            return False
        # Handle both timezone-aware and naive datetimes
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            # Assume naive datetime is UTC
            expires = expires.replace(tzinfo=timezone.utc)
        return now > expires

    def is_valid(self) -> bool:
        """Check if API key is valid for use."""
        return self.is_active and not self.is_expired()

    def has_scope(self, scope: str) -> bool:
        """Check if API key has a specific scope.

        ``admin`` includes the other scope names. It does not admit the key to
        routes outside ``API_KEY_ROUTE_SCOPES``; the auth middleware enforces
        that allowlist before a handler runs.
        """
        if not self.scopes:
            return False
        # Admin scope grants all permissions
        if "admin" in self.scopes:
            return True
        return scope in self.scopes

    def record_usage(self, ip_address: str | None = None) -> None:
        """Record API key usage (call db.commit() after)."""
        self.last_used_at = datetime.now(timezone.utc)
        self.last_used_ip = ip_address
        self.usage_count += 1

    def revoke(self, revoked_by_user_id: str | None = None) -> None:
        """Revoke this API key (call db.commit() after)."""
        self.is_active = False
        self.revoked_at = datetime.now(timezone.utc)
        self.revoked_by = revoked_by_user_id

    def __repr__(self):
        return f"<APIKey(id={self.id}, name={self.name}, prefix=argus_{self.prefix}..., active={self.is_active})>"
