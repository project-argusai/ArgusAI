"""Consumed web refresh-token ledger for reuse detection (Issue #520).

Refresh tokens are single-use. On rotation the previous hash is recorded here
so a later replay can be recognized and the entire token family revoked.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class ConsumedRefreshToken(Base):
    """
    Previously-used web refresh token hashes, keyed for reuse detection.

    Session.refresh_token_hash is overwritten in place on rotation. Without this
    ledger, a stolen original token matches no session row and reuse-detection
    never fires. Each consumed hash stays recognizable until its session is
    deleted (logout / expiry cleanup).
    """

    __tablename__ = "consumed_refresh_tokens"

    token_hash = Column(String(64), primary_key=True)  # SHA-256 of the consumed token
    token_family = Column(String(36), nullable=False)
    session_id = Column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    consumed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session = relationship("Session", back_populates="consumed_refresh_tokens")

    __table_args__ = (
        Index("idx_consumed_refresh_family", "token_family"),
        Index("idx_consumed_refresh_session", "session_id"),
    )
