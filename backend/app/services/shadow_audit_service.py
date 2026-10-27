"""Cloud-audit shadow storage and retention (#735, #691 Phase 1 S1).

- ``record_shadow_result``: one frozen local/cloud pair per event (complete).
- Claims (#744): ``claim_shadow_result`` inserts a ``claimed`` row before the
  cloud call (the unique event_id dedupes), then ``complete_claim`` or
  ``fail_claim`` (exception class name only; never deleted).
  ``mark_stale_claims_failed`` fails claims stuck over 5 minutes.
  ``record_fallback_pair`` stores a free fallback pair, or fills a failed
  claim in as source=fallback, complete.
- ``count_audits_since``: the audit cap counts rows with ``was_audit_claim``
  (set when the audit claims a row, never cleared), whatever their source or
  status, so it survives a restart and a fallback filling a failed claim.
- ``sweep_stale_claims_if_due``: the stale-claim sweep, throttled to once an
  hour per process, for the audit gate path (#746).
- ``upsert_daily_summary``: numbers only, one row per (day, source). Summaries
  are built by ``recompute_daily_summary`` only.
- ``purge_expired``: after 30 days the paired text is nulled (the row keeps
  its source, verdict and timestamps); rows and summaries are deleted after
  365 days.
- ``recompute_daily_summary``: recomputable counts for any past day. Each
  pair's current verdict counts on the day the pair was created, so a late or
  changed verdict is counted once, as its final value, when that day is
  recomputed (the daily job recomputes the last 30 days).

All stored numbers go through the numpy-safe helper (#708). Logs carry ids,
counts and outcomes only: never descriptions, image paths, names or plates.
"""
from __future__ import annotations

import json
import logging
import numbers
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.shadow_result import (
    SHADOW_SOURCES,
    SHADOW_VERDICTS,
    SHADOW_STATUSES,
    ShadowDailySummary,
    ShadowResult,
)
from app.utils.json_safe import json_safe

logger = logging.getLogger(__name__)

PAIR_RETENTION_DAYS = 30
RECOMPUTE_DAYS = 30
SUMMARY_RETENTION_DAYS = 365
STALE_CLAIM_MINUTES = 5
GATE_SWEEP_INTERVAL = timedelta(hours=1)

_gate_sweep_lock = threading.Lock()
_gate_sweep_last: Optional[datetime] = None


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
    metrics: Optional[Dict[str, Any]] = None,
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
        status="complete",
        was_audit_claim=(source == "audit"),
        metrics=_metrics(metrics),
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


def _metrics(metrics: Optional[Dict[str, Any]]) -> Optional[str]:
    if metrics is None:
        return None
    safe = json_safe(metrics)
    if not isinstance(safe, dict) or not _numbers_only(safe):
        raise ValueError("pair metrics must be numbers only")
    return json.dumps(safe, allow_nan=False)


def _row(db: Session, event_id: str) -> Optional[ShadowResult]:
    return db.query(ShadowResult).filter(ShadowResult.event_id == event_id).first()


def claim_shadow_result(db: Session, *, event_id: str, source: str, local_result: Any,
                        local_provider: Optional[str] = None,
                        now: Optional[datetime] = None) -> Optional[ShadowResult]:
    """Insert a ``claimed`` row; None if the event already has a row."""
    _check_source(source)
    if _row(db, event_id) is not None:
        return None
    row = ShadowResult(event_id=event_id, source=source, status="claimed",
                       was_audit_claim=(source == "audit"),
                       local_result=_dumps(local_result), local_provider=local_provider,
                       created_at=_now(now))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return row


def complete_claim(db: Session, event_id: str, *, cloud_result: Any,
                   cloud_provider: Optional[str] = None,
                   metrics: Optional[Dict[str, Any]] = None) -> Optional[ShadowResult]:
    row = _row(db, event_id)
    if row is None or row.status != "claimed":
        return None
    row.cloud_result = _dumps(cloud_result)
    row.cloud_provider = cloud_provider
    row.metrics = _metrics(metrics)
    row.status = "complete"
    db.commit()
    return row


def fail_claim(db: Session, event_id: str, *, error_type: str) -> Optional[ShadowResult]:
    """Mark a claim failed. The row stays: it counts toward the cap."""
    row = _row(db, event_id)
    if row is None or row.status != "claimed":
        return None
    row.status = "failed"
    row.error_type = str(error_type)[:64]
    db.commit()
    return row


def mark_stale_claims_failed(db: Session, now: Optional[datetime] = None,
                             minutes: int = STALE_CLAIM_MINUTES) -> int:
    cutoff = _now(now) - timedelta(minutes=minutes)
    count = (db.query(ShadowResult)
             .filter(ShadowResult.status == "claimed", ShadowResult.created_at < cutoff)
             .update({ShadowResult.status: "failed", ShadowResult.error_type: "stale_claim"},
                     synchronize_session=False))
    db.commit()
    if count:
        logger.info("Stale shadow claims failed",
                    extra={"event_type": "shadow_stale_claims", "count": int(count)})
    return int(count or 0)


def reset_gate_sweep() -> None:
    """Forget the last gate-path sweep (tests, or after a restart)."""
    global _gate_sweep_last
    with _gate_sweep_lock:
        _gate_sweep_last = None


def sweep_stale_claims_if_due(db: Session, now: Optional[datetime] = None,
                              interval: timedelta = GATE_SWEEP_INTERVAL) -> int:
    """Run ``mark_stale_claims_failed`` at most once per ``interval`` per process.

    Cheap when not due (no DB work); safe to call twice or concurrently: the
    update only touches rows still ``claimed`` and older than 5 minutes.
    """
    global _gate_sweep_last
    current = _now(now)
    with _gate_sweep_lock:
        if _gate_sweep_last is not None and current - _gate_sweep_last < interval:
            return 0
        _gate_sweep_last = current
    return mark_stale_claims_failed(db, now=current)


def record_fallback_pair(db: Session, *, event_id: str, local_result: Any, cloud_result: Any,
                         local_provider: Optional[str] = None,
                         cloud_provider: Optional[str] = None,
                         metrics: Optional[Dict[str, Any]] = None,
                         now: Optional[datetime] = None) -> Optional[ShadowResult]:
    """Free fallback pair: new row, or fill a failed claim. None if claimed/complete."""
    row = _row(db, event_id)
    if row is None:
        created = record_shadow_result(db, event_id=event_id, source="fallback",
                                       local_result=local_result, cloud_result=cloud_result,
                                       local_provider=local_provider,
                                       cloud_provider=cloud_provider, now=now, metrics=metrics)
        return created if created.source == "fallback" and created.status == "complete" else None
    if row.status != "failed":
        return None
    row.source = "fallback"
    row.status = "complete"
    row.error_type = None
    row.local_result = _dumps(local_result)
    row.cloud_result = _dumps(cloud_result)
    row.local_provider = local_provider
    row.cloud_provider = cloud_provider
    row.metrics = _metrics(metrics)
    db.commit()
    return row


def set_verdict(db: Session, event_id: str, verdict: str,
                now: Optional[datetime] = None) -> Optional[ShadowResult]:
    if verdict not in SHADOW_VERDICTS:
        raise ValueError("invalid verdict")
    row = db.query(ShadowResult).filter(ShadowResult.event_id == event_id).first()
    if row is None or row.status != "complete":
        return None
    row.verdict = verdict
    row.verdict_at = _now(now)
    db.commit()
    logger.info("Shadow verdict set",
                extra={"event_type": "shadow_verdict", "event_id": event_id, "verdict": verdict})
    return row


def count_audits_since(db: Session, since: datetime) -> int:
    """Audit claims since ``since``, any source or status (#746). Restart-safe."""
    return (
        db.query(ShadowResult)
        .filter(ShadowResult.was_audit_claim.is_(True), ShadowResult.created_at >= since)
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


def recompute_daily_summary(db: Session, day: date, source: str) -> Optional[ShadowDailySummary]:
    """Rebuild the summary for ``day`` (box-local) from ``shadow_results``.

    Over the complete rows created that day: ``pairs_recorded``,
    ``verdicts_<v>`` (each row's current verdict, so a changed verdict never
    lands on two days) and ``sum_<metric>`` from the stored score_pair
    numbers. ``failed`` counts that day's failed rows. Claimed rows are left
    out. Replaces the stored summary; safe to re-run. When every count is
    zero and no summary exists for that day and source, nothing is written
    and None is returned (#746).
    """
    _check_source(source)
    start, end = _local_day_bounds(day)
    day_rows = db.query(ShadowResult).filter(ShadowResult.source == source,
                                             ShadowResult.created_at >= start,
                                             ShadowResult.created_at < end)
    complete = day_rows.filter(ShadowResult.status == "complete")
    summary: Dict[str, Any] = {"pairs_recorded": complete.count(),
                               "failed": day_rows.filter(ShadowResult.status == "failed").count()}
    for verdict in SHADOW_VERDICTS:
        summary[f"verdicts_{verdict}"] = complete.filter(ShadowResult.verdict == verdict).count()
    sums: Dict[str, float] = {}
    for (raw,) in complete.with_entities(ShadowResult.metrics):
        if not raw:
            continue
        for key, value in json.loads(raw).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            sums[f"sum_{key}"] = sums.get(f"sum_{key}", 0) + value
    summary.update(sums)
    if not any(summary.values()):
        existing = (db.query(ShadowDailySummary.id)
                    .filter(ShadowDailySummary.day == day, ShadowDailySummary.source == source)
                    .first())
        if existing is None:
            return None
    return upsert_daily_summary(db, day, source, summary)


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
