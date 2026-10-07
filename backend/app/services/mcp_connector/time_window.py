"""Time-window parsing and local-time formatting for MCP tools (issue #648).

Events are stored in UTC. Tools accept ``since`` as ISO 8601 or a relative
value (``15m``, ``1h``, ``24h``, ``7d``, ``2w``, ``today``, ``yesterday``) and
return ISO 8601 timestamps carrying the household's UTC offset.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo

MAX_LOOKBACK = timedelta(days=90)
MAX_INPUT_LENGTH = 40

_RELATIVE_RE = re.compile(
    r"^\s*(?:last\s+)?(\d{1,4})\s*"
    r"(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|wk|wks|week|weeks)\s*$",
    re.IGNORECASE,
)
_UNIT_SECONDS = {
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "wk": 604800, "wks": 604800, "week": 604800, "weeks": 604800,
}


class TimeWindowError(ValueError):
    """The caller supplied a window the tools cannot use. Message is safe to return."""


@dataclass(frozen=True)
class TimeWindow:
    start: datetime  # UTC, aware
    end: datetime  # UTC, aware
    label: str


def resolve_timezone(tz_name: Optional[str]) -> tzinfo:
    """ZoneInfo for the configured name, or UTC when unset or invalid."""
    if not tz_name:
        return timezone.utc
    try:
        return ZoneInfo(str(tz_name))
    except Exception:
        return timezone.utc


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Treat naive values (SQLite) as UTC and convert aware values to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_local_iso(value: Optional[datetime], tz: tzinfo) -> Optional[str]:
    """ISO 8601 with the local UTC offset, to the second."""
    utc_value = as_utc(value)
    if utc_value is None:
        return None
    return utc_value.astimezone(tz).replace(microsecond=0).isoformat()


def _local_midnight(now_utc: datetime, tz: tzinfo) -> datetime:
    local_now = now_utc.astimezone(tz)
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc)


def parse_window(
    value: Optional[str],
    *,
    default: str,
    tz: tzinfo,
    now: Optional[datetime] = None,
) -> TimeWindow:
    """Parse a ``since``/``window`` value into a UTC window ending now.

    ``yesterday`` is the one bounded window: local midnight yesterday to local
    midnight today. Every other value runs from its start to now.
    """
    now_utc = as_utc(now) if now is not None else datetime.now(timezone.utc)
    raw = default if value is None or not str(value).strip() else str(value)
    if len(raw) > MAX_INPUT_LENGTH:
        raise TimeWindowError("time value is too long")
    text = raw.strip()
    lowered = text.lower()

    if lowered == "today":
        return TimeWindow(_local_midnight(now_utc, tz), now_utc, "today")
    if lowered == "yesterday":
        today_start = _local_midnight(now_utc, tz)
        # Step back through local midnight so DST days stay correct.
        start = _local_midnight(today_start - timedelta(hours=12), tz)
        return TimeWindow(start, today_start, "yesterday")

    match = _RELATIVE_RE.match(text)
    if match:
        amount = int(match.group(1))
        if amount <= 0:
            raise TimeWindowError("relative time must be greater than zero")
        delta = timedelta(seconds=amount * _UNIT_SECONDS[match.group(2).lower()])
        if delta > MAX_LOOKBACK:
            raise TimeWindowError("time window may not exceed 90 days")
        return TimeWindow(now_utc - delta, now_utc, f"last {amount}{match.group(2).lower()}")

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise TimeWindowError(
            "use ISO 8601 (2026-10-06T08:00:00-05:00) or a relative value such as 1h, 24h, 7d, today"
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    start = parsed.astimezone(timezone.utc)
    if start > now_utc:
        raise TimeWindowError("time value is in the future")
    if now_utc - start > MAX_LOOKBACK:
        raise TimeWindowError("time window may not exceed 90 days")
    return TimeWindow(start, now_utc, "since " + to_local_iso(start, tz))
