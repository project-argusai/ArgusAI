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

    # Database connection pool (12-Factor IV/VIII; tuned for Postgres prod deploys).
    # Defaults match SQLAlchemy's own defaults so existing behavior is unchanged.
    # pool_pre_ping eliminates stale-connection errors after idle periods; size/overflow
    # are only applied to non-SQLite engines (SQLite is single-writer and ignores them).
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # seconds; recycle connections older than 30 min
    DB_POOL_PRE_PING: bool = True

    # Security
    ENCRYPTION_KEY: str  # Required - primary key used for new encryptions
    ENCRYPTION_KEY_PREVIOUS: Optional[str] = None  # Previous key (used for decryption during rotation)
    JWT_SECRET_KEY: str  # Required - no default (was previously auto-generated, which was dangerous)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    # Application
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Per-statement SQL logging. Independent of DEBUG and LOG_LEVEL.
    # Off unless explicitly opted in, so production query volume does not fill
    # app logs. SQL_ECHO is the canonical name; DB_ECHO is an accepted alias.
    SQL_ECHO: bool = False
    DB_ECHO: bool = False

    # Event media roots. Unset keeps the historical backend/data directories.
    # Event deletion refuses stored paths that resolve outside these roots.
    MEDIA_THUMBNAIL_DIR: Optional[str] = None
    MEDIA_FRAMES_DIR: Optional[str] = None
    MEDIA_VIDEO_DIR: Optional[str] = None
    MEDIA_CLIPS_DIR: Optional[str] = None

    # Debug Endpoints (Story P14-1.2)
    # SECURITY WARNING: Only enable for development.
    # Even when enabled, endpoints require admin role + optional DEBUG_TOKEN.
    DEBUG_ENDPOINTS_ENABLED: bool = False
    DEBUG_TOKEN: Optional[str] = None  # Optional extra secret required for debug endpoints

    # API
    API_V1_PREFIX: str = "/api/v1"
    # Stored as string to avoid pydantic-settings JSON parsing; use cors_origins_list property
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def sql_echo_enabled(self) -> bool:
        """True only when SQL statement logging was explicitly opted in."""
        return bool(self.SQL_ECHO or self.DB_ECHO)

    # Session cookie flags.
    # The native install (LAN HTTPS frontend on :3000 and the Cloudflare tunnel
    # hostname) proxies /api/v1 through the frontend, so browser cookie requests
    # are same-site. Lax is the default. Set COOKIE_SAMESITE=none only when the
    # browser calls the API on a different site (requires COOKIE_SECURE=true).
    # For plain HTTP, set COOKIE_SECURE=false.
    COOKIE_SECURE: bool = True  # Set to False for HTTP-only deployments
    COOKIE_SAMESITE: str = "lax"

    # Camera Settings
    MAX_CAMERAS: int = 1  # MVP limitation
    DEFAULT_FRAME_RATE: int = 5

    # Live Streaming Settings (Story P16-2.2)
    STREAM_MAX_CONCURRENT: int = 10  # Max concurrent streams server-wide
    STREAM_DEFAULT_QUALITY: str = "medium"  # Default quality: low, medium, high
    STREAM_FRAME_BUFFER_SIZE: int = 5  # Frames to buffer for new clients
    STREAM_CONNECTION_TIMEOUT: int = 30  # Seconds before idle stream disconnects

    # Authenticated WebSocket bounds (issue #594).
    # Counts /ws notification sockets and camera WebSocket streams only.
    # HomeKit HAP sessions use a separate ffmpeg path and are not counted.
    # Per-camera default follows STREAM_MAX_CONCURRENT so it does not reject
    # a camera viewer the existing server-wide cap would still allow.
    WS_MAX_CONNECTIONS_PER_USER: int = 32
    WS_MAX_CONNECTIONS_PER_CAMERA: Optional[int] = None

    @field_validator("WS_MAX_CONNECTIONS_PER_USER", mode="after")
    @classmethod
    def validate_ws_user_limit(cls, v: int) -> int:
        if v < 1:
            raise ValueError("WS_MAX_CONNECTIONS_PER_USER must be >= 1")
        return v

    @field_validator("WS_MAX_CONNECTIONS_PER_CAMERA", mode="before")
    @classmethod
    def blank_ws_camera_limit(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return v

    @field_validator("WS_MAX_CONNECTIONS_PER_CAMERA", mode="after")
    @classmethod
    def validate_ws_camera_limit(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("WS_MAX_CONNECTIONS_PER_CAMERA must be >= 1")
        return v

    @property
    def ws_max_connections_per_camera(self) -> int:
        """Per-camera WebSocket cap. Unset follows the server-wide stream cap."""
        if self.WS_MAX_CONNECTIONS_PER_CAMERA is None:
            return self.STREAM_MAX_CONCURRENT
        return self.WS_MAX_CONNECTIONS_PER_CAMERA

    # Limits for untrusted backup uploads and ZIP expansion.
    # Override with environment variables of the same name (12-factor III).
    BACKUP_MAX_UPLOAD_BYTES: int = 512 * 1024 * 1024
    BACKUP_UPLOAD_TIMEOUT_SECONDS: int = 120
    BACKUP_MAX_MEMBERS: int = 10000
    BACKUP_MAX_EXPANDED_BYTES: int = 2 * 1024 * 1024 * 1024
    BACKUP_MAX_MEMBER_BYTES: int = 1024 * 1024 * 1024
    BACKUP_MAX_COMPRESSION_RATIO: int = 500

    @field_validator(
        "BACKUP_MAX_UPLOAD_BYTES",
        "BACKUP_UPLOAD_TIMEOUT_SECONDS",
        "BACKUP_MAX_MEMBERS",
        "BACKUP_MAX_EXPANDED_BYTES",
        "BACKUP_MAX_MEMBER_BYTES",
        "BACKUP_MAX_COMPRESSION_RATIO",
        mode="after",
    )
    @classmethod
    def validate_backup_limits(cls, v: int) -> int:
        """Reject limits that would disable the upload and ZIP guards."""
        if v < 1:
            raise ValueError("backup limits must be >= 1")
        return v

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

    @field_validator('COOKIE_SAMESITE', mode='before')
    @classmethod
    def validate_cookie_samesite(cls, v: object) -> str:
        """Accept lax, strict, or none. Cross-site browsers need none."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return "lax"
        normalized = str(v).strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict, or none")
        return normalized

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

    # Refresh Token Endpoint Rate Limit (Phase A - Web Auth Refresh)
    REFRESH_RATE_LIMIT: str = "20/minute"  # Rate limit specifically for /auth/refresh (sensitive endpoint)

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
