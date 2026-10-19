"""Local-first analysis policy (#691).

With ``AI_PRIMARY=local`` every Protect event is described by the local
vision model first. The cloud chain runs only when the local answer is not
usable (error, blank, confidence below ``LOCAL_PRIMARY_MIN_CONFIDENCE``, or no
answer within ``LOCAL_PRIMARY_MAX_WAIT_MS``) and the daily cloud fallback cap
(``CLOUD_FALLBACK_DAILY_CAP``) still has room.

This module holds the pure decisions so the pipeline stays small and the
rules are unit-testable. Nothing here logs description text.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Optional

from app.services.ai_types import AIResult

logger = logging.getLogger(__name__)

# Cloud providers as stored in events.provider_used.
CLOUD_PROVIDER_NAMES = ("openai", "grok", "claude", "gemini")


@dataclass(frozen=True)
class LocalFirstConfig:
    enabled: bool = False
    max_wait_ms: int = 120_000
    min_confidence: int = 50
    daily_cloud_cap: int = 50

    @classmethod
    def from_settings(cls) -> "LocalFirstConfig":
        from app.core.config import settings

        return cls(
            enabled=str(getattr(settings, "AI_PRIMARY", "cloud")).lower() == "local"
            and bool(getattr(settings, "LOCAL_VLM_ENABLED", False)),
            max_wait_ms=int(getattr(settings, "LOCAL_PRIMARY_MAX_WAIT_MS", 120_000)),
            min_confidence=int(getattr(settings, "LOCAL_PRIMARY_MIN_CONFIDENCE", 50)),
            daily_cloud_cap=int(getattr(settings, "CLOUD_FALLBACK_DAILY_CAP", 50)),
        )


def local_answer_problem(result: Optional[AIResult], min_confidence: int) -> Optional[str]:
    """Why a local answer needs the cloud fallback, or None when it is usable.

    Labels: ``no_result``, ``error``, ``blank``, ``low_confidence``.
    A missing confidence is not treated as low (the rule is "below N").
    """
    if result is None:
        return "no_result"
    if not result.success:
        return "error"
    if not (result.description or "").strip():
        return "blank"
    confidence = result.ai_confidence
    if confidence is not None and confidence < min_confidence:
        return "low_confidence"
    return None


class CloudFallbackBudget:
    """Per-local-day count of cloud fallbacks with a hard cap. Thread-safe.

    The count lives in memory. On first use each day it is seeded from
    ``seed()`` (today's cloud-described events) so a restart does not reset it
    to zero; the seed is best effort.
    """

    def __init__(
        self,
        cap: int,
        today: Callable[[], date] = lambda: datetime.now().date(),
        seed: Optional[Callable[[date], int]] = None,
    ):
        self.cap = max(0, int(cap))
        self._today = today
        self._seed = seed
        self._day: Optional[date] = None
        self._used = 0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        day = self._today()
        if day != self._day:
            self._day = day
            self._used = 0
            if self._seed is not None:
                try:
                    self._used = max(0, int(self._seed(day)))
                except Exception as exc:  # noqa: BLE001 - seeding is best effort
                    logger.debug("Cloud fallback budget seed failed (%s)", type(exc).__name__)

    @property
    def used(self) -> int:
        with self._lock:
            self._roll()
            return self._used

    def try_acquire(self) -> bool:
        """Count one cloud fallback if the cap allows it."""
        with self._lock:
            self._roll()
            if self._used >= self.cap:
                return False
            self._used += 1
            return True


def _seed_from_db(day: date) -> int:
    """Today's events (box-local day) described by a cloud provider."""
    from app.core.database import get_db_session
    from app.models.event import Event

    start_local = datetime.combine(day, datetime.min.time()).astimezone()
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    with get_db_session() as db:
        return (
            db.query(Event)
            .filter(Event.created_at >= start_utc, Event.provider_used.in_(CLOUD_PROVIDER_NAMES))
            .count()
        )


_budget: Optional[CloudFallbackBudget] = None
_budget_lock = threading.Lock()


def get_cloud_fallback_budget(cap: Optional[int] = None) -> CloudFallbackBudget:
    global _budget
    with _budget_lock:
        if _budget is None:
            if cap is None:
                cap = LocalFirstConfig.from_settings().daily_cloud_cap
            _budget = CloudFallbackBudget(cap, seed=_seed_from_db)
        return _budget


def reset_cloud_fallback_budget() -> None:
    global _budget
    with _budget_lock:
        _budget = None
