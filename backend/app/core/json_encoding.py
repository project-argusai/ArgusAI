"""Global JSON encoding policy for the API.

Pydantic response models get explicit-UTC datetimes via the ``UTCDateTime`` field
type (``app.schemas.types``). But endpoints that return plain ``dict``s (or any
value FastAPI runs through ``jsonable_encoder`` rather than a Pydantic model) would
still serialize a datetime with ``.isoformat()`` — which emits no ``Z`` for the
naive datetimes SQLite returns. A client then can't tell the value is UTC.

``install_utc_datetime_encoder()`` overrides FastAPI's process-wide datetime
encoder so EVERY datetime that flows through ``jsonable_encoder`` is rendered as an
explicit-UTC ISO-8601 string (``...Z``) — the same format as ``UTCDateTime``. This
is the safety net for non-model response paths; together they guarantee the API is
self-describing about time zones for native clients (e.g. the iOS app).

Note: this only affects datetime *objects* handed to the encoder. Code that calls
``.isoformat()`` itself produces a string the encoder never sees — those few sites
use ``app.schemas.types.iso_utc()`` instead.

Call once at startup, before any request is served.
"""

import logging
from datetime import datetime

import fastapi.encoders as _fastapi_encoders

from app.schemas.types import serialize_utc_iso

logger = logging.getLogger(__name__)


def install_utc_datetime_encoder() -> None:
    """Patch FastAPI's global datetime encoder to emit explicit-UTC ISO-8601."""
    _fastapi_encoders.ENCODERS_BY_TYPE[datetime] = serialize_utc_iso

    # FastAPI derives a (encoder -> tuple-of-types) cache from ENCODERS_BY_TYPE at
    # import time; jsonable_encoder consults that cache, so rebuild it after the
    # override or the change is ignored.
    if hasattr(_fastapi_encoders, "encoders_by_class_tuples"):
        from collections import defaultdict

        rebuilt = defaultdict(tuple)
        for type_, encoder in _fastapi_encoders.ENCODERS_BY_TYPE.items():
            rebuilt[encoder] += (type_,)
        _fastapi_encoders.encoders_by_class_tuples = rebuilt

    logger.info("Installed UTC datetime JSON encoder (jsonable_encoder -> ...Z)")
