"""Shared Pydantic field types for API schemas.

`UTCDateTime` makes the API self-describing about time zones. The backend stores
all timestamps in UTC, but SQLite returns *naive* datetimes, so Pydantic's default
serialization emits e.g. ``2026-06-29T09:08:20`` with no offset — a client cannot
tell that is UTC and may render it as local time (the bug fixed in PR #502).

`UTCDateTime` serializes every datetime as an explicit-UTC ISO-8601 string with a
``Z`` suffix (``2026-06-29T09:08:20.850453Z``):

  * naive datetime  -> assumed UTC (the project convention), tagged ``Z``
  * aware datetime  -> converted to UTC, tagged ``Z``

This is what native clients (e.g. the planned iOS app, whose
``ISO8601DateFormatter`` expects an offset) and JS ``new Date()`` both parse
unambiguously. Validation/parsing of inbound values is unchanged — only JSON
serialization is affected (``when_used='json'``) — so request bodies keep working
exactly as before.

OpenAPI still advertises ``{type: string, format: date-time}`` so generated client
models keep their date types.

Usage in a schema::

    from app.schemas.types import UTCDateTime

    class EventResponse(BaseModel):
        created_at: UTCDateTime
        ended_at: Optional[UTCDateTime] = None
"""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import PlainSerializer, WithJsonSchema


def serialize_utc_iso(value: datetime) -> str:
    """Render a datetime as an explicit-UTC ISO-8601 string with a ``Z`` suffix."""
    if value.tzinfo is None:
        # Project convention: naive datetimes are UTC.
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def iso_utc(value: Optional[datetime], *, default=None):
    """Manual-serialization helper for non-Pydantic paths (raw dict responses).

    Use instead of ``value.isoformat()`` so hand-built response dicts emit the same
    explicit-UTC ``...Z`` string as ``UTCDateTime`` fields. ``default`` is returned
    for ``None`` so each call site can preserve its existing empty-value contract
    (``iso_utc(x)`` -> ``None``; ``iso_utc(x, default="")`` -> ``""``).
    """
    return serialize_utc_iso(value) if value is not None else default


# Drop-in replacement for `datetime` in response (and request) schemas. Keeps the
# standard datetime validator; only changes JSON serialization + OpenAPI schema.
UTCDateTime = Annotated[
    datetime,
    PlainSerializer(serialize_utc_iso, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time"}, mode="serialization"),
]
