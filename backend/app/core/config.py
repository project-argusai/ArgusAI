"""Application configuration using Pydantic Settings"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List
import secrets


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # Security
    ENCRYPTION_KEY: str  # Required - no default for security
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)  # Auto-generate if not set
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    # Application
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # API
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS_ORIGINS from comma-separated string or list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Camera Settings
    MAX_CAMERAS: int = 1  # MVP limitation
    DEFAULT_FRAME_RATE: int = 5

    # HomeKit Integration (Story P4-6.1, P4-6.2)
    HOMEKIT_ENABLED: bool = False
    HOMEKIT_PORT: int = 51826
    HOMEKIT_BRIDGE_NAME: str = "ArgusAI"
    HOMEKIT_MANUFACTURER: str = "ArgusAI"
    HOMEKIT_PERSIST_DIR: str = "data/homekit"
    HOMEKIT_PINCODE: str | None = None  # Auto-generated if not set
    HOMEKIT_MOTION_RESET_SECONDS: int = 30  # Story P4-6.2: Motion sensor reset timeout
    HOMEKIT_MAX_MOTION_DURATION: int = 300  # Story P4-6.2: Max motion duration (5 min)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# Global settings instance
settings = Settings()
