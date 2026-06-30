"""Settings Service

Provides access to system settings stored in the database.
Used by email_service and other services that need configuration values.

Story P16-1.7: Created to support SMTP configuration for email invitations.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting
from app.utils.encryption import decrypt_password, is_encrypted

logger = logging.getLogger(__name__)

# Frame-extraction config — keys, allowed values, and defaults mirror the
# SystemSettings schema (app/schemas/system.py). These three admin settings drive
# multi-frame AI analysis cost/quality; they are read here so the live pipeline
# and the reanalyze endpoint share one validated source of truth.
_FRAME_COUNT_KEY = "settings_analysis_frame_count"
_FRAME_COUNT_ALLOWED = (5, 10, 15, 20)
_FRAME_COUNT_DEFAULT = 10

_SAMPLING_KEY = "settings_frame_sampling_strategy"
_SAMPLING_ALLOWED = ("uniform", "adaptive", "hybrid")
_SAMPLING_DEFAULT = "uniform"

_OFFSET_KEY = "settings_frame_extraction_offset_ms"
_OFFSET_MIN_MS = 0
_OFFSET_MAX_MS = 10000
_OFFSET_DEFAULT_MS = 2000


class SettingsService:
    """
    Service for accessing system settings from the database.

    Provides methods to:
    - Get plain text settings
    - Get and decrypt encrypted settings (API keys, passwords)

    Usage:
        service = SettingsService(db)
        smtp_host = service.get_setting("smtp_host")
        smtp_password = service.get_encrypted_setting("smtp_password")
    """

    def __init__(self, db: Session):
        """
        Initialize SettingsService with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def get_setting(self, key: str) -> Optional[str]:
        """
        Get a setting value by key.

        Args:
            key: The setting key to look up

        Returns:
            The setting value, or None if not found
        """
        setting = self.db.query(SystemSetting).filter(
            SystemSetting.key == key
        ).first()

        if setting is None:
            return None

        return setting.value

    def get_encrypted_setting(self, key: str) -> Optional[str]:
        """
        Get and decrypt an encrypted setting value.

        For settings like API keys and passwords that are stored encrypted.

        Args:
            key: The setting key to look up

        Returns:
            The decrypted setting value, or None if not found.
            Returns the raw value if not encrypted.
        """
        value = self.get_setting(key)

        if value is None:
            return None

        # If the value is encrypted, decrypt it
        if is_encrypted(value):
            try:
                return decrypt_password(value)
            except ValueError as e:
                logger.error(f"Failed to decrypt setting {key}: {e}")
                return None

        # Return raw value if not encrypted
        return value

    def get_frame_extraction_config(self) -> dict:
        """
        Resolve the admin-configured frame-extraction settings into validated
        values safe to hand directly to FrameExtractor.

        Returns a dict: {"frame_count": int, "sampling_strategy": str,
        "offset_ms": int}. Missing, non-numeric, or out-of-range values fall back
        to the SystemSettings schema defaults rather than reaching the extractor.
        """
        # Frame count — must be one of the allowed discrete choices.
        frame_count = _FRAME_COUNT_DEFAULT
        raw_count = self.get_setting(_FRAME_COUNT_KEY)
        if raw_count is not None:
            try:
                parsed = int(raw_count)
                if parsed in _FRAME_COUNT_ALLOWED:
                    frame_count = parsed
                else:
                    logger.warning(
                        f"{_FRAME_COUNT_KEY}={raw_count!r} not in {_FRAME_COUNT_ALLOWED}; "
                        f"using default {_FRAME_COUNT_DEFAULT}"
                    )
            except (TypeError, ValueError):
                logger.warning(
                    f"{_FRAME_COUNT_KEY}={raw_count!r} is not an int; "
                    f"using default {_FRAME_COUNT_DEFAULT}"
                )

        # Sampling strategy — must be one of the allowed names.
        sampling_strategy = _SAMPLING_DEFAULT
        raw_strategy = self.get_setting(_SAMPLING_KEY)
        if raw_strategy is not None:
            if raw_strategy in _SAMPLING_ALLOWED:
                sampling_strategy = raw_strategy
            else:
                logger.warning(
                    f"{_SAMPLING_KEY}={raw_strategy!r} not in {_SAMPLING_ALLOWED}; "
                    f"using default {_SAMPLING_DEFAULT}"
                )

        # Offset — numeric, clamped to the schema range.
        offset_ms = _OFFSET_DEFAULT_MS
        raw_offset = self.get_setting(_OFFSET_KEY)
        if raw_offset is not None:
            try:
                offset_ms = max(_OFFSET_MIN_MS, min(_OFFSET_MAX_MS, int(raw_offset)))
            except (TypeError, ValueError):
                logger.warning(
                    f"{_OFFSET_KEY}={raw_offset!r} is not an int; "
                    f"using default {_OFFSET_DEFAULT_MS}"
                )

        return {
            "frame_count": frame_count,
            "sampling_strategy": sampling_strategy,
            "offset_ms": offset_ms,
        }

    def set_setting(self, key: str, value: str) -> None:
        """
        Set a setting value.

        Args:
            key: The setting key
            value: The value to store
        """
        setting = self.db.query(SystemSetting).filter(
            SystemSetting.key == key
        ).first()

        if setting is None:
            setting = SystemSetting(key=key, value=value)
            self.db.add(setting)
        else:
            setting.value = value

        self.db.commit()
