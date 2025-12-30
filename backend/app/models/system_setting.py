"""System settings model for configuration key-value storage"""
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime

from app.core.database import Base


class SystemSetting(Base):
    """
    System configuration settings stored as key-value pairs.

    Used for:
    - AI provider configuration (ai_model_primary)
    - Encrypted API keys (ai_api_key_openai, ai_api_key_claude, ai_api_key_gemini)
    - System defaults (data_retention_days, motion_sensitivity, thumbnail_storage_mode)
    - Usage tracking metadata
    """
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True, nullable=False)
    value = Column(String(2000), nullable=False)  # JSON or encrypted: prefix for sensitive data
    # Story P14-5.7: Use Python UTC default instead of server_default for consistent timezone handling
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        # Don't expose value in repr for security
        return f"<SystemSetting(key='{self.key}')>"
