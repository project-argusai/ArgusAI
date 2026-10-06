"""``since`` / ``window`` parsing for MCP tools (issue #648)."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.mcp_connector.time_window import (
    TimeWindowError,
    parse_window,
    resolve_timezone,
    to_local_iso,
)

EASTERN = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 6, 18, 30, tzinfo=timezone.utc)  # 14:30 EDT


def test_relative_values():
    assert parse_window("1h", default="1h", tz=EASTERN, now=NOW).start == NOW - timedelta(hours=1)
    assert parse_window("15m", default="1h", tz=EASTERN, now=NOW).start == NOW - timedelta(minutes=15)
    assert parse_window("last 7 days", default="1h", tz=EASTERN, now=NOW).start == NOW - timedelta(days=7)
    assert parse_window(None, default="24h", tz=EASTERN, now=NOW).start == NOW - timedelta(hours=24)


def test_today_and_yesterday_use_household_midnight():
    today = parse_window("today", default="1h", tz=EASTERN, now=NOW)
    assert today.start == datetime(2026, 10, 6, 4, 0, tzinfo=timezone.utc)  # 00:00 EDT
    assert today.end == NOW
    yesterday = parse_window("yesterday", default="1h", tz=EASTERN, now=NOW)
    assert yesterday.start == datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)
    assert yesterday.end == today.start


def test_yesterday_across_dst_change():
    now = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)  # day after DST ends
    window = parse_window("yesterday", default="1h", tz=EASTERN, now=now)
    assert window.start == datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc)  # 00:00 EDT
    assert window.end == datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc)  # 00:00 EST


def test_iso_values():
    aware = parse_window("2026-10-06T08:00:00-04:00", default="1h", tz=EASTERN, now=NOW)
    assert aware.start == datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    naive = parse_window("2026-10-06T08:00:00", default="1h", tz=EASTERN, now=NOW)
    assert naive.start == aware.start  # naive input is household local time
    zulu = parse_window("2026-10-06T12:00:00Z", default="1h", tz=EASTERN, now=NOW)
    assert zulu.start == aware.start


@pytest.mark.parametrize("value", ["banana", "0h", "91d", "2026-10-07T00:00:00Z", "2020-01-01", "x" * 41, "-1h"])
def test_invalid_values(value):
    with pytest.raises(TimeWindowError):
        parse_window(value, default="1h", tz=EASTERN, now=NOW)


def test_local_iso_formatting_and_tz_fallback():
    assert to_local_iso(datetime(2026, 10, 6, 13, 0), EASTERN) == "2026-10-06T09:00:00-04:00"
    assert to_local_iso(None, EASTERN) is None
    assert resolve_timezone("Not/AZone") == timezone.utc
    assert resolve_timezone(None) == timezone.utc
