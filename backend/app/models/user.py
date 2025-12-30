"""User SQLAlchemy ORM model for authentication"""
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.orm import validates, relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone
import re
import logging

logger = logging.getLogger(__name__)


class User(Base):
    """
    User model for authentication

    Attributes:
        id: UUID primary key
        username: Unique login username (3-50 chars, alphanumeric + underscore)
        password_hash: bcrypt hash (60 chars)
        is_active: Whether account is enabled
        created_at: Record creation timestamp (UTC)
        last_login: Last successful login timestamp (UTC)
    """

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(60), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # Story P14-5.7: Add timezone=True for consistent UTC handling
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationship to Device (Story P11-2.4)
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")

    @validates('username')
    def validate_username(self, key, value):
        """
        Validate username format

        Requirements:
        - 3-50 characters
        - Alphanumeric and underscore only
        """
        if not value:
            raise ValueError("Username is required")

        if len(value) < 3 or len(value) > 50:
            raise ValueError("Username must be 3-50 characters")

        if not re.match(r'^[a-zA-Z0-9_]+$', value):
            raise ValueError("Username must contain only letters, numbers, and underscores")

        return value.lower()  # Normalize to lowercase

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, active={self.is_active})>"
