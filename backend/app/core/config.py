"""Application configuration using Pydantic Settings"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Optional
from pathlib import Path
import secrets
import os


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
    # Stored as string to avoid pydantic-settings JSON parsing; use cors_origins_list property
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Cookie Settings (for HTTP vs HTTPS deployments)
    # For HTTPS: COOKIE_SECURE=true, COOKIE_SAMESITE=none
    # For HTTP:  COOKIE_SECURE=false, COOKIE_SAMESITE=lax
    COOKIE_SECURE: bool = True  # Set to False for HTTP-only deployments
    COOKIE_SAMESITE: str = "none"  # Use "lax" for HTTP-only deployments

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

    # SSL/HTTPS Configuration (Story P9-5.1)
    SSL_ENABLED: bool = False
    SSL_CERT_FILE: Optional[str] = None  # Path to SSL certificate file (PEM format)
    SSL_KEY_FILE: Optional[str] = None  # Path to SSL private key file (PEM format)
    SSL_REDIRECT_HTTP: bool = True  # Redirect HTTP to HTTPS when SSL is enabled
    SSL_MIN_VERSION: str = "TLSv1_2"  # Minimum TLS version (TLSv1_2 or TLSv1_3)
    SSL_PORT: int = 443  # HTTPS port when SSL is enabled

    @field_validator('SSL_CERT_FILE', 'SSL_KEY_FILE', mode='after')
    @classmethod
    def validate_ssl_file_paths(cls, v: Optional[str]) -> Optional[str]:
        """Validate SSL certificate file paths exist when provided."""
        if v is not None and v.strip():
            path = Path(v)
            if not path.is_absolute():
                # Relative to working directory
                path = Path.cwd() / path
            if not path.exists():
                raise ValueError(f"SSL file not found: {v}")
        return v

    @field_validator('SSL_MIN_VERSION', mode='after')
    @classmethod
    def validate_ssl_min_version(cls, v: str) -> str:
        """Validate SSL minimum version."""
        valid_versions = ['TLSv1_2', 'TLSv1_3']
        if v not in valid_versions:
            raise ValueError(f"SSL_MIN_VERSION must be one of {valid_versions}")
        return v

    @property
    def ssl_ready(self) -> bool:
        """Check if SSL is properly configured and ready to use."""
        return (
            self.SSL_ENABLED
            and self.SSL_CERT_FILE is not None
            and self.SSL_KEY_FILE is not None
            and os.path.exists(self.SSL_CERT_FILE)
            and os.path.exists(self.SSL_KEY_FILE)
        )

    # APNS Configuration (Story P11-2.1)
    APNS_KEY_FILE: Optional[str] = None  # Path to .p8 auth key file
    APNS_KEY_ID: Optional[str] = None  # 10-character key identifier
    APNS_TEAM_ID: Optional[str] = None  # 10-character team identifier
    APNS_BUNDLE_ID: Optional[str] = None  # App bundle ID (e.g., com.argusai.app)
    APNS_USE_SANDBOX: bool = False  # Use sandbox for development

    @property
    def apns_ready(self) -> bool:
        """Check if APNS is properly configured and ready to use."""
        return (
            self.APNS_KEY_FILE is not None
            and self.APNS_KEY_ID is not None
            and self.APNS_TEAM_ID is not None
            and self.APNS_BUNDLE_ID is not None
            and os.path.exists(self.APNS_KEY_FILE)
        )

    # FCM Configuration (Story P11-2.2)
    FCM_PROJECT_ID: Optional[str] = None  # Firebase project ID
    FCM_CREDENTIALS_FILE: Optional[str] = None  # Path to service account JSON

    @property
    def fcm_ready(self) -> bool:
        """Check if FCM is properly configured and ready to use."""
        return (
            self.FCM_PROJECT_ID is not None
            and self.FCM_CREDENTIALS_FILE is not None
            and os.path.exists(self.FCM_CREDENTIALS_FILE)
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# Global settings instance
settings = Settings()
