"""Application configuration using Pydantic Settings"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Optional
from pathlib import Path
from cryptography.fernet import Fernet
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # Security
    ENCRYPTION_KEY: str  # Required - no default for security
    JWT_SECRET_KEY: str  # Required - no default (was previously auto-generated, which was dangerous)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    # Application
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Debug Endpoints (Story P14-1.2)
    # SECURITY WARNING: Only enable for development - exposes sensitive info
    DEBUG_ENDPOINTS_ENABLED: bool = False

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

    # Live Streaming Settings (Story P16-2.2)
    STREAM_MAX_CONCURRENT: int = 10  # Max concurrent streams server-wide
    STREAM_DEFAULT_QUALITY: str = "medium"  # Default quality: low, medium, high
    STREAM_FRAME_BUFFER_SIZE: int = 5  # Frames to buffer for new clients
    STREAM_CONNECTION_TIMEOUT: int = 30  # Seconds before idle stream disconnects

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

    # Security key validation (Story for Phase A - Issue #421)
    @field_validator('JWT_SECRET_KEY', 'ENCRYPTION_KEY', mode='after')
    @classmethod
    def validate_required_secrets(cls, v: str, info) -> str:
        """Ensure critical security keys are provided and non-empty."""
        field_name = info.field_name
        if not v or not str(v).strip():
            raise ValueError(
                f"{field_name} is required and cannot be empty. "
                "Generate a secure value with: "
                "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' "
                "(for ENCRYPTION_KEY) or 'openssl rand -hex 32' (for JWT_SECRET_KEY)"
            )
        return v

    @field_validator('ENCRYPTION_KEY', mode='after')
    @classmethod
    def validate_encryption_key_format(cls, v: str) -> str:
        """Validate that ENCRYPTION_KEY is a valid Fernet key."""
        try:
            Fernet(v.encode() if isinstance(v, str) else v)
        except Exception as e:
            raise ValueError(
                f"ENCRYPTION_KEY is not a valid Fernet key: {e}. "
                "Generate a new one with: "
                "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        return v

    @property
    def secrets_ready(self) -> bool:
        """Check if critical secrets (JWT + Encryption) are properly configured."""
        return bool(
            getattr(self, 'JWT_SECRET_KEY', None)
            and getattr(self, 'ENCRYPTION_KEY', None)
        )

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

    # Rate Limiting Configuration (Story P14-2.6)
    RATE_LIMIT_ENABLED: bool = True  # Enable/disable global rate limiting
    RATE_LIMIT_DEFAULT: str = "100/minute"  # Default rate limit for all endpoints
    RATE_LIMIT_READS: str = "100/minute"  # Rate limit for GET requests
    RATE_LIMIT_WRITES: str = "20/minute"  # Rate limit for POST/PUT/DELETE requests
    RATE_LIMIT_STORAGE_URI: Optional[str] = None  # Redis URI for distributed rate limiting (e.g., "redis://localhost:6379")

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
