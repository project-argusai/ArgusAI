"""Shared data-retention settings.

The Settings UI stores ``settings_retention_days`` while the original cleanup
job read ``data_retention_days``. Both keys are the same policy: the UI value
wins when they disagree, and writers keep them in sync.

``settings_auto_cleanup`` gates the scheduled jobs. A retention value ``<= 0``
means keep forever (the job skips deletion).
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.models.system_setting import SystemSetting

SETTINGS_RETENTION_DAYS_KEY = "settings_retention_days"
DATA_RETENTION_DAYS_KEY = "data_retention_days"
AUTO_CLEANUP_KEY = "settings_auto_cleanup"
VIDEO_RETENTION_DAYS_KEY = "settings_video_retention_days"

DEFAULT_RETENTION_DAYS = 30
DEFAULT_VIDEO_RETENTION_DAYS = 30

_TRUE_VALUES = {"true", "1", "yes"}


def read_int_setting(db: Session, key: str) -> Optional[int]:
    """Return an integer setting, or None when missing or not an integer."""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting is None or setting.value is None:
        return None
    raw = str(setting.value).strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def read_raw_setting(db: Session, key: str) -> Optional[str]:
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting is None:
        return None
    return setting.value


def _write_setting(db: Session, key: str, value: str) -> None:
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting is None:
        db.add(SystemSetting(key=key, value=value))
    else:
        setting.value = value


def resolve_retention_days(db: Session) -> int:
    """Effective event retention. The Settings UI key wins over the legacy key."""
    ui_days = read_int_setting(db, SETTINGS_RETENTION_DAYS_KEY)
    if ui_days is not None:
        return ui_days
    job_days = read_int_setting(db, DATA_RETENTION_DAYS_KEY)
    if job_days is not None:
        return job_days
    return DEFAULT_RETENTION_DAYS


def set_retention_days(db: Session, retention_days: int) -> None:
    """Persist the same retention value to both the UI key and the legacy key."""
    stored = str(int(retention_days))
    _write_setting(db, SETTINGS_RETENTION_DAYS_KEY, stored)
    _write_setting(db, DATA_RETENTION_DAYS_KEY, stored)
    db.commit()


def reconcile_retention_policy(db: Optional[Session] = None) -> int:
    """Return the effective retention days and make the two keys match.

    When neither key is stored, the default (30) is returned and nothing is
    written. When one or both are stored and they differ, both are set to the
    UI value (or the legacy value when the UI key is absent).
    """

    def _reconcile(db_session: Session) -> int:
        days = resolve_retention_days(db_session)
        ui_days = read_int_setting(db_session, SETTINGS_RETENTION_DAYS_KEY)
        job_days = read_int_setting(db_session, DATA_RETENTION_DAYS_KEY)
        if ui_days is None and job_days is None:
            return days
        if ui_days != days or job_days != days:
            set_retention_days(db_session, days)
        return days

    if db is None:
        with get_db_session() as db_session:
            return _reconcile(db_session)
    return _reconcile(db)


def is_auto_cleanup_enabled(db: Optional[Session] = None) -> bool:
    """Scheduled retention runs only when auto-cleanup is on (default: on)."""

    def _enabled(db_session: Session) -> bool:
        raw = read_raw_setting(db_session, AUTO_CLEANUP_KEY)
        if raw is None or str(raw).strip() == "":
            return True
        return str(raw).strip().lower() in _TRUE_VALUES

    if db is None:
        with get_db_session() as db_session:
            return _enabled(db_session)
    return _enabled(db)


def get_video_retention_days(db: Optional[Session] = None) -> int:
    """Video retention from settings. Missing/invalid values default to 30.

    ``<= 0`` is returned as stored so the scheduled job can skip (keep forever).
    """

    def _days(db_session: Session) -> int:
        days = read_int_setting(db_session, VIDEO_RETENTION_DAYS_KEY)
        if days is None:
            return DEFAULT_VIDEO_RETENTION_DAYS
        return days

    if db is None:
        with get_db_session() as db_session:
            return _days(db_session)
    return _days(db)
