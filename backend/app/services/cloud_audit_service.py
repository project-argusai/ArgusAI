"""Sampled background cloud audit of key events (#736, #691 Phase 1 S2a).

Local is primary. For a deterministic sample of key events (person,
vehicle, package, doorbell ring) a background cloud call produces a second
opinion, stored with the frozen local result in ``shadow_results`` (#735)
with its score_pair numbers; the daily summary is rebuilt from rows by
``recompute_daily_summary``.

Claim row: before the cloud call the task inserts a ``claimed`` row (the
unique event_id dedupes concurrent audits and fallbacks). Success marks it
complete; a timeout, error, cloud failure or OOM marks it failed with the
exception class name only. Failed rows are kept, count against the cap and
the event is never audited again (a later fallback pair may fill it in as
source=fallback). Claims stuck over 5 minutes are failed at startup and by
the 02:30 job.

Rules:
- Never with ``AI_PRIMARY=cloud``; off unless ``CLOUD_AUDIT_ENABLED`` (kill
  switch). Both are re-checked inside the background task.
- The same event always gets the same sample decision (hash of the id).
- Daily cap (default 200) counts ``shadow_results`` rows with source=audit
  since local midnight, of any status (claimed, complete, failed), so it
  holds with audits in flight and survives a restart.
- At most ``max_pending`` (2) scheduled or running audits; a 3rd is dropped.
- One cloud call per audit, ``timeout_s`` (30 s), no retry.
- Steps aside while a #696 fallback call is running, when free memory is
  low, when the cost cap is hit, and while fewer than ``min_fallback_left``
  (10) fallback calls remain today (runs at 10, pauses at 9).
- A fallback that already called cloud is recorded free with
  source=fallback; no extra cloud call, and it does not use the audit cap.
- Never writes to ``events``. Logs carry ids, labels and counts only.
- ``maybe_schedule`` does no DB work; blocking DB work in the task runs in
  ``asyncio.to_thread``.

The hook into the live pipeline lands in #737: it calls ``maybe_schedule``
after the event is stored and ``record_fallback_pair`` when the fallback
already ran, and wraps the fallback call in ``track_cloud_fallback()``.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from app.models.shadow_result import ShadowResult
from app.services import shadow_audit_service as sas
from app.utils.json_safe import json_safe

logger = logging.getLogger(__name__)

KEY_EVENT_TYPES = frozenset({"person", "vehicle", "package", "ring"})
_OUTCOME_HISTORY = 50


@dataclass(frozen=True)
class AuditConfig:
    enabled: bool = False
    primary_local: bool = False
    sample_rate: float = 1.0
    daily_cap: int = 200
    max_pending: int = 2
    timeout_s: float = 30.0
    min_fallback_left: int = 10
    min_free_memory_mb: int = 1024

    @classmethod
    def from_settings(cls) -> "AuditConfig":
        from app.core.config import settings

        return cls(
            enabled=bool(getattr(settings, "CLOUD_AUDIT_ENABLED", False)),
            primary_local=str(getattr(settings, "AI_PRIMARY", "cloud")).lower() == "local",
            sample_rate=float(getattr(settings, "CLOUD_AUDIT_SAMPLE_RATE", 1.0)),
            daily_cap=int(getattr(settings, "CLOUD_AUDIT_DAILY_CAP", 200)),
            min_fallback_left=int(getattr(settings, "CLOUD_AUDIT_MIN_FALLBACK_LEFT", 10)),
            min_free_memory_mb=int(getattr(settings, "CLOUD_AUDIT_MIN_FREE_MEMORY_MB", 1024)),
        )


def _default_fallback_remaining() -> int:
    from app.services.local_first import get_cloud_fallback_budget

    budget = get_cloud_fallback_budget()
    return max(0, budget.cap - budget.used)


def _default_fallback_in_progress() -> bool:
    from app.services.local_first import cloud_fallback_in_progress

    return cloud_fallback_in_progress()


def _default_free_memory_mb() -> float:
    import psutil

    return psutil.virtual_memory().available / (1024 * 1024)


def _default_cost_ok(db) -> bool:
    from app.services.cost_cap_service import get_cost_cap_service

    allowed, _reason = get_cost_cap_service().can_analyze(db)
    return bool(allowed)


def _default_scorer():
    # score_pair comes from #743 (pair_metrics). Until that merges, pairs are
    # still recorded and counted; only the per-metric sums are skipped.
    try:
        from app.services.pair_metrics import score_pair
    except ImportError:
        return None
    return score_pair


def _local_midnight_utc(now: Optional[datetime] = None) -> datetime:
    local = (now or datetime.now(timezone.utc)).astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _as_dict(result: Any) -> Optional[Dict[str, Any]]:
    if result is None:
        return None
    if isinstance(result, dict):
        return dict(result)
    if dataclasses.is_dataclass(result):
        return dataclasses.asdict(result)
    return {k: v for k, v in vars(result).items() if not k.startswith("_")}


def _cloud_failed(result: Optional[Dict[str, Any]]) -> bool:
    return not result or result.get("success", True) is False


class CloudAuditService:
    def __init__(
        self,
        *,
        cloud_call: Callable[..., Awaitable[Any]],
        session_factory: Callable[[], Any],
        config_provider: Callable[[], AuditConfig] = AuditConfig.from_settings,
        fallback_remaining: Callable[[], int] = _default_fallback_remaining,
        fallback_in_progress: Callable[[], bool] = _default_fallback_in_progress,
        free_memory_mb: Callable[[], float] = _default_free_memory_mb,
        cost_ok: Callable[[Any], bool] = _default_cost_ok,
        scorer: Optional[Callable[[Any, Any], Dict[str, Any]]] = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.cloud_call = cloud_call
        self._session_factory = session_factory
        self._config = config_provider
        self._fallback_remaining = fallback_remaining
        self._fallback_in_progress = fallback_in_progress
        self._free_memory_mb = free_memory_mb
        self._cost_ok = cost_ok
        self._scorer = scorer if scorer is not None else _default_scorer()
        self._now = now
        self._tasks: Set[asyncio.Task] = set()
        self.pending = 0
        self._claim_lock = threading.Lock()
        # event_id -> token of the task that opened the claim and hasn't settled it
        self._owned_claims: Dict[str, object] = {}
        self.last_outcomes: List[str] = []

    # --- decisions -------------------------------------------------------

    @staticmethod
    def _is_key(event_type: Optional[str], is_doorbell_ring: bool = False) -> bool:
        return bool(is_doorbell_ring) or (str(event_type or "").lower() in KEY_EVENT_TYPES)

    def should_sample(self, event_id: str, event_type: Optional[str],
                      is_doorbell_ring: bool = False) -> bool:
        """Deterministic: the same event id always gets the same answer."""
        if not self._is_key(event_type, is_doorbell_ring):
            return False
        rate = self._config().sample_rate
        if rate <= 0:
            return False
        if rate >= 1:
            return True
        digest = hashlib.sha256(str(event_id).encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") / float(1 << 64)
        return bucket < rate

    def _note(self, event_id: str, outcome: str, **extra) -> str:
        self.last_outcomes.append(outcome)
        del self.last_outcomes[:-_OUTCOME_HISTORY]
        logger.info("Cloud audit outcome",
                    extra={"event_type": "cloud_audit", "event_id": event_id,
                           "outcome": outcome, **extra})
        return outcome

    # --- scheduling ------------------------------------------------------

    def maybe_schedule(self, *, event_id: str, event_type: Optional[str], local_result: Any,
                       image_base64: str, is_doorbell_ring: bool = False) -> str:
        """Quick in-memory checks, then start the background audit.

        No DB work here (dedupe and the cap happen in the task via the claim
        row). Never raises.
        """
        counted = False
        try:
            cfg = self._config()
            if not cfg.enabled:
                return self._note(event_id, "disabled")
            if not cfg.primary_local:
                return self._note(event_id, "primary_cloud")
            if not self._is_key(event_type, is_doorbell_ring):
                return self._note(event_id, "not_key_type")
            if not self.should_sample(event_id, event_type, is_doorbell_ring):
                return self._note(event_id, "not_sampled")
            if self.pending >= cfg.max_pending:
                return self._note(event_id, "dropped_busy")
            loop = asyncio.get_running_loop()
            self.pending += 1
            counted = True
            local_copy = json.loads(json.dumps(json_safe(_as_dict(local_result)), default=str))
            task = loop.create_task(self._run(
                event_id, str(event_type or ("ring" if is_doorbell_ring else "")),
                local_copy, image_base64))
        except RuntimeError:
            if counted:
                self.pending = max(0, self.pending - 1)
            return self._note(event_id, "no_loop")
        except Exception as exc:  # noqa: BLE001
            if counted:
                self.pending = max(0, self.pending - 1)
            return self._note(event_id, "error", error_type=type(exc).__name__)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        logger.debug("Cloud audit scheduled",
                     extra={"event_type": "cloud_audit_scheduled", "event_id": event_id,
                            "pending": self.pending})
        return "scheduled"

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def startup(self) -> int:
        """Fail claims left in ``claimed`` for over 5 minutes (e.g. a crash)."""
        db = self._session_factory()
        try:
            return sas.mark_stale_claims_failed(db, now=self._now())
        finally:
            db.close()

    # --- background task -------------------------------------------------

    def _gate(self, cfg: AuditConfig) -> Optional[str]:
        """In-memory gates; the DB gates run in ``_claim_sync``."""
        if not cfg.enabled:
            return "disabled"
        if not cfg.primary_local:
            return "primary_cloud"
        if self._fallback_in_progress():
            return "fallback_in_progress"
        if cfg.min_free_memory_mb and self._free_memory_mb() < cfg.min_free_memory_mb:
            return "low_memory"
        if self._fallback_remaining() < cfg.min_fallback_left:
            return "fallback_floor"
        return None

    def _claim_sync(self, event_id: str, cfg: AuditConfig,
                    local_result: Optional[Dict[str, Any]], token: object) -> Optional[str]:
        """Cost cap, daily cap and the claim insert. Returns a block reason or None.

        Claimed and failed rows count against the cap; the lock makes
        count-then-insert atomic within this process.
        """
        self._sweep_stale_if_due()
        with self._claim_lock:
            db = self._session_factory()
            try:
                if db.query(ShadowResult.id).filter(ShadowResult.event_id == event_id).first():
                    return "already_paired"
                if not self._cost_ok(db):
                    return "cost_cap"
                used = sas.count_audits_since(db, _local_midnight_utc(self._now()))
                if used >= cfg.daily_cap:
                    return "daily_cap"
                row = sas.claim_shadow_result(
                    db, event_id=event_id, source="audit", local_result=local_result,
                    local_provider=(local_result or {}).get("provider"), now=self._now())
                if row is None:
                    return "already_paired"
                # Recorded in the thread so a cancel during the await still
                # knows this task owns the claim.
                self._owned_claims[event_id] = token
                return None
            finally:
                db.close()

    def _sweep_stale_if_due(self) -> None:
        """Hourly stale-claim sweep from the gate path (#746).

        Runs inside ``_claim_sync``, which ``_run`` calls via
        ``asyncio.to_thread``, so the DB work never blocks the event loop.
        ``sweep_stale_claims_if_due`` is throttled per process and is a no-op
        when not due. It lands with #746 (#749); until then the lookup finds
        nothing and this is skipped. A sweep failure never blocks an audit.
        """
        sweep = getattr(sas, "sweep_stale_claims_if_due", None)
        if sweep is None:
            return
        db = self._session_factory()
        try:
            sweep(db, now=self._now())
        except Exception as e:  # noqa: BLE001 - the sweep must never block the gate
            db.rollback()
            logger.warning("Stale claim sweep failed", extra={"error_type": type(e).__name__})
        finally:
            db.close()

    def _fail_sync(self, event_id: str, error_type: str) -> None:
        db = self._session_factory()
        try:
            row = sas.fail_claim(db, event_id, error_type=error_type)
            if row is not None:
                self._recompute(db, row)  # keeps the day's ``failed`` count current
        finally:
            db.close()

    async def _run(self, event_id: str, event_type: str, local_result: Optional[Dict[str, Any]],
                   image_base64: str) -> str:
        settled = False
        token = object()
        try:
            cfg = self._config()  # re-read: kill switch / AI_PRIMARY may have changed
            blocked = self._gate(cfg)
            if blocked:
                return self._note(event_id, blocked)
            blocked = await asyncio.to_thread(self._claim_sync, event_id, cfg, local_result, token)
            if blocked:
                return self._note(event_id, blocked)
            failure: Optional[str] = None
            outcome = ""
            cloud_result = None
            try:
                raw = await asyncio.wait_for(
                    self.cloud_call(event_id=event_id, image_base64=image_base64,
                                    event_type=event_type),
                    timeout=cfg.timeout_s,
                )
                cloud_result = _as_dict(raw)
                if _cloud_failed(cloud_result):
                    failure, outcome = "cloud_failed", "cloud_failed"
            except asyncio.TimeoutError:
                failure, outcome = "TimeoutError", "timeout"
            except MemoryError:
                failure, outcome = "MemoryError", "out_of_memory"
            except Exception as exc:  # noqa: BLE001 - nothing escapes
                failure, outcome = type(exc).__name__, "error"
            if failure:
                await asyncio.to_thread(self._fail_sync, event_id, failure)
                settled = True
                if outcome == "error":
                    return self._note(event_id, "error", error_type=failure)
                return self._note(event_id, outcome)
            metrics = self._score(event_id, local_result, cloud_result)
            await asyncio.to_thread(self._store, event_id, cloud_result, metrics)
            settled = True
            return self._note(event_id, "recorded", source="audit")
        except MemoryError:
            return self._note(event_id, "out_of_memory")
        except Exception as exc:  # noqa: BLE001
            return self._note(event_id, "error", error_type=type(exc).__name__)
        finally:
            owner = self._owned_claims.get(event_id) is token
            if owner and not settled:
                # Crash or cancellation mid-audit: fail the claim (sync, best effort).
                try:
                    self._fail_sync(event_id, "interrupted")
                except Exception:  # noqa: BLE001
                    pass
            if owner:
                self._owned_claims.pop(event_id, None)
            self.pending = max(0, self.pending - 1)

    # --- storage -----------------------------------------------------------

    def _store(self, event_id: str, cloud_result: Dict[str, Any], metrics: Dict[str, Any]) -> None:
        """Complete the claim with the pair's numbers, then rebuild that day's summary."""
        db = self._session_factory()
        try:
            row = sas.complete_claim(db, event_id, cloud_result=cloud_result,
                                     cloud_provider=(cloud_result or {}).get("provider"),
                                     metrics=metrics)
            if row is not None:
                self._recompute(db, row)
        finally:
            db.close()

    @staticmethod
    def _recompute(db, row: ShadowResult, source: Optional[str] = None) -> Optional[Any]:
        """Rebuild the day's summary for ``row``.

        ``recompute_daily_summary`` returns None when the day has no pairs and
        no summary row yet (#746 zero-row skip); that is not an error, so
        callers must not dereference the result.
        """
        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return sas.recompute_daily_summary(db, created.astimezone().date(), source or row.source)

    def record_fallback_pair(self, *, event_id: str, local_result: Any, cloud_result: Any) -> str:
        """The #696 fallback already called cloud: record the pair free.

        Skipped while an audit claim is open or done; fills a failed audit
        claim in as source=fallback, complete.
        """
        try:
            if not self._config().enabled:
                return self._note(event_id, "disabled")
            cloud = _as_dict(cloud_result)
            if _cloud_failed(cloud):
                return self._note(event_id, "cloud_failed")
            local = _as_dict(local_result)
            metrics = self._score(event_id, local, cloud)
            db = self._session_factory()
            try:
                row = sas.record_fallback_pair(
                    db, event_id=event_id, local_result=local, cloud_result=cloud,
                    local_provider=(local or {}).get("provider"),
                    cloud_provider=(cloud or {}).get("provider"),
                    metrics=metrics, now=self._now())
                if row is None:
                    return self._note(event_id, "already_paired")
                self._recompute(db, row)
                self._recompute(db, row, source="audit")  # in case it filled a failed audit claim
            finally:
                db.close()
            return self._note(event_id, "recorded", source="fallback")
        except Exception as exc:  # noqa: BLE001
            return self._note(event_id, "error", error_type=type(exc).__name__)

    def _score(self, event_id: str, local_result, cloud_result) -> Dict[str, Any]:
        if self._scorer is None:
            return {}
        try:
            raw = dict(self._scorer(local_result, cloud_result) or {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cloud audit scoring failed",
                           extra={"event_id": event_id, "error_type": type(exc).__name__})
            return {}
        # Numbers only; anything else (or non-finite, via json_safe) is dropped.
        return {k: v for k, v in json_safe(raw).items()
                if isinstance(k, str) and not isinstance(v, bool) and isinstance(v, (int, float))}
