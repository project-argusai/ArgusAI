"""Cloud-audit shadow storage and retention (#735, #691 Phase 1 S1).

- ``record_shadow_result``: one frozen local/cloud pair per event.
- ``count_audits_since``: the audit cap counts ``shadow_results`` rows, so it
  survives a restart (no in-memory counter).
- ``upsert_daily_summary``: numbers only, one row per (day, source).
- ``purge_expired``: after 30 days the paired text is nulled (the row keeps
  its source, verdict and timestamps); rows and summaries are deleted after
  365 days.
- ``recompute_daily_summary``: recomputable counts for any past day. Verdicts
  count by ``verdict_at``, so a verdict given after a day's summary ran is
  counted in the summary for the day it was given.

All stored numbers go through the numpy-safe helper (#708). Logs carry ids,
counts and outcomes only: never descriptions, image paths, names or plates.
"""
from __future__ import annotations

import json
import logging
import numbers
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.shadow_result import (
    SHADOW_SOURCES,
    SHADOW_VERDICTS,
    ShadowDailySummary,
    ShadowResult,
)
from app.utils.json_safe import json_safe

logger = logging.getLogger(__name__)

PAIR_RETENTION_DAYS = 30
SUMMARY_RETENTION_DAYS = 365


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(json_safe(value), allow_nan=False)


def _check_source(source: str) -> None:
    if source not in SHADOW_SOURCES:
        raise ValueError("invalid shadow source")


def record_shadow_result(
    db: Session,
    *,
    event_id: str,
    source: str,
    local_result: Any,
    cloud_result: Any,
    local_provider: Optional[str] = None,
    cloud_provider: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ShadowResult:
    """Store the frozen pair for ``event_id``; an existing row is returned as is."""
    _check_source(source)
    existing = db.query(ShadowResult).filter(ShadowResult.event_id == event_id).first()
    if existing is not None:
        return existing
    row = ShadowResult(
        event_id=event_id,
        source=source,
        local_result=_dumps(local_result),
        cloud_result=_dumps(cloud_result),
        local_provider=local_provider,
        cloud_provider=cloud_provider,
        created_at=_now(now),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.query(ShadowResult).filter(ShadowResult.event_id == event_id).one()
    logger.info("Shadow result recorded",
                extra={"event_type": "shadow_result_recorded", "event_id": event_id,
                       "source": source})
    return row


def set_verdict(db: Session, event_id: str, verdict: str,
                now: Optional[datetime] = None) -> Optional[ShadowResult]:
    if verdict not in SHADOW_VERDICTS:
        raise ValueError("invalid verdict")
    row = db.query(ShadowResult).filter(ShadowResult.event_id == event_id).first()
    if row is None:
        return None
    row.verdict = verdict
    row.verdict_at = _now(now)
    db.commit()
    logger.info("Shadow verdict set",
                extra={"event_type": "shadow_verdict", "event_id": event_id, "verdict": verdict})
    return row


def count_audits_since(db: Session, since: datetime, source: str = "audit") -> int:
    """Rows recorded since ``since``. Backed by the table, so restart-safe."""
    _check_source(source)
    return (
        db.query(ShadowResult)
        .filter(ShadowResult.source == source, ShadowResult.created_at >= since)
        .count()
    )


def _numbers_only(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, numbers.Number):
        return True
    if isinstance(value, dict):
        return all(isinstance(k, str) and _numbers_only(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_numbers_only(v) for v in value)
    return False


def upsert_daily_summary(db: Session, day: date, source: str,
                         metrics: Dict[str, Any]) -> ShadowDailySummary:
    """Write the numbers-only summary for (day, source); text is rejected."""
    _check_source(source)
    safe = json_safe(metrics)
    if not isinstance(safe, dict) or not _numbers_only(safe):
        raise ValueError("daily summary metrics must be numbers only")
    payload = json.dumps(safe, allow_nan=False)
    row = (
        db.query(ShadowDailySummary)
        .filter(ShadowDailySummary.day == day, ShadowDailySummary.source == source)
        .first()
    )
    if row is None:
        row = ShadowDailySummary(day=day, source=source, metrics=payload)
        db.add(row)
    else:
        row.metrics = payload
    db.commit()
    return row


def _local_day_bounds(day: date):
    start = datetime.combine(day, datetime.min.time()).astimezone()
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def recompute_daily_summary(db: Session, day: date, source: str) -> ShadowDailySummary:
    """Recount ``day`` (box-local) from ``shadow_results`` and merge into its summary.

    ``pairs_recorded`` counts rows created that day; ``verdicts_<v>`` counts
    verdicts whose ``verdict_at`` falls on that day. Other keys already in the
    summary (e.g. metric sums from the audit service) are kept. Safe to re-run.
    """
    _check_source(source)
    start, end = _local_day_bounds(day)
    base = db.query(ShadowResult).filter(ShadowResult.source == source)
    counts = {"pairs_recorded": base.filter(ShadowResult.created_at >= start,
                                            ShadowResult.created_at < end).count()}
    for verdict in SHADOW_VERDICTS:
        counts[f"verdicts_{verdict}"] = base.filter(
            ShadowResult.verdict == verdict,
            ShadowResult.verdict_at >= start,
            ShadowResult.verdict_at < end,
        ).count()
    row = (db.query(ShadowDailySummary)
           .filter(ShadowDailySummary.day == day, ShadowDailySummary.source == source)
           .first())
    merged = json.loads(row.metrics) if row is not None else {}
    merged.update(counts)
    return upsert_daily_summary(db, day, source, merged)


def purge_expired(
    db: Session,
    now: Optional[datetime] = None,
    pair_days: int = PAIR_RETENTION_DAYS,
    summary_days: int = SUMMARY_RETENTION_DAYS,
) -> Dict[str, int]:
    """Null paired text after ``pair_days``; delete rows and summaries after ``summary_days``."""
    current = _now(now)
    pair_cutoff = current - timedelta(days=pair_days)
    row_cutoff = current - timedelta(days=summary_days)
    summary_cutoff = row_cutoff.date()
    redacted = (
        db.query(ShadowResult)
        .filter(ShadowResult.created_at < pair_cutoff,
                (ShadowResult.local_result.isnot(None)) | (ShadowResult.cloud_result.isnot(None)))
        .update({ShadowResult.local_result: None, ShadowResult.cloud_result: None},
                synchronize_session=False)
    )
    deleted = (
        db.query(ShadowResult)
        .filter(ShadowResult.created_at < row_cutoff)
        .delete(synchronize_session=False)
    )
    summaries = (
        db.query(ShadowDailySummary)
        .filter(ShadowDailySummary.day < summary_cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    result = {"shadow_results_redacted": int(redacted or 0),
              "shadow_results_deleted": int(deleted or 0),
              "shadow_summaries_deleted": int(summaries or 0)}
    logger.info("Shadow retention complete", extra={"event_type": "shadow_retention", **result})
    return result
