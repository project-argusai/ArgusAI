"""System settings model for configuration key-value storage"""
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
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
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        # Don't expose value in repr for security
        return f"<SystemSetting(key='{self.key}')>"
