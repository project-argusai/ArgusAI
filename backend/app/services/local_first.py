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
    escalate_vehicle_no_make: bool = True

    @classmethod
    def from_settings(cls) -> "LocalFirstConfig":
        from app.core.config import settings

        return cls(
            enabled=str(getattr(settings, "AI_PRIMARY", "cloud")).lower() == "local"
            and bool(getattr(settings, "LOCAL_VLM_ENABLED", False)),
            max_wait_ms=int(getattr(settings, "LOCAL_PRIMARY_MAX_WAIT_MS", 120_000)),
            min_confidence=int(getattr(settings, "LOCAL_PRIMARY_MIN_CONFIDENCE", 50)),
            daily_cloud_cap=int(getattr(settings, "CLOUD_FALLBACK_DAILY_CAP", 50)),
            escalate_vehicle_no_make=bool(
                getattr(settings, "LOCAL_PRIMARY_ESCALATE_VEHICLE_NO_MAKE", True)
            ),
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


_VEHICLE_EVENT_TYPES = frozenset({"vehicle", "car", "truck", "van", "suv"})


def result_names_vehicle_make(result: Optional[AIResult]) -> bool:
    """Whether the description or structured identification names a make."""
    from app.services.entity_alert_service import identified_vehicle_text, visible_vehicle_details

    if result is None:
        return False
    text = identified_vehicle_text(result.description, getattr(result, "identification", None))
    _color, make, _model = visible_vehicle_details(text)
    return make is not None


def _cloud_provider_available() -> bool:
    from app.services.ai_provider_order import disabled_providers

    return len(disabled_providers()) < len(CLOUD_PROVIDER_NAMES)


def should_escalate_vehicle_make(
    result: Optional[AIResult], event_type: Optional[str], config: LocalFirstConfig
) -> bool:
    """A usable local answer for a vehicle event that names no make (#755).

    Make-based vehicle entity linking needs the make in the description or
    identification; the small local model often leaves it out. Returns False
    when the option is off, the event is not a vehicle event, the local model
    saw nothing (object_type none), a make is named, or every cloud provider
    is disabled. Never logs description text.
    """
    if not config.escalate_vehicle_no_make or config.daily_cloud_cap <= 0:
        return False
    if result is None or not result.success:
        return False
    if not (isinstance(event_type, str) and event_type.lower() in _VEHICLE_EVENT_TYPES):
        return False
    ident = getattr(result, "identification", None)
    if isinstance(ident, dict) and ident.get("object_type") == "none":
        return False
    if result_names_vehicle_make(result):
        return False
    return _cloud_provider_available()


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


# A person waits on a manual re-analysis, so cap the local wait below the
# live-event budget.
REANALYZE_LOCAL_MAX_WAIT_S = 60.0


async def try_local_reanalysis(
    image_base64: str,
    *,
    event_id: str,
    camera,
    local_timestamp: Optional[str],
    config: Optional[LocalFirstConfig] = None,
):
    """Ask the local model for a manual re-analysis. Returns (result, problem).

    ``problem`` is None when the answer is usable (see ``local_answer_problem``),
    otherwise a short label (``busy``, ``local_error``, ``blank``, ...). Never
    raises and never logs description text.
    """
    from app.services.local_vlm_fallback import RedescribeJob, get_local_vlm_fallback_service

    config = config or LocalFirstConfig.from_settings()
    job = RedescribeJob(
        event_id=event_id,
        image_base64=image_base64,
        camera_id=getattr(camera, "id", None),
        camera_name=getattr(camera, "name", "") or "",
        event_type=None,
        local_timestamp=local_timestamp,
    )
    max_wait_s = min(config.max_wait_ms / 1000.0, REANALYZE_LOCAL_MAX_WAIT_S)
    outcome = await get_local_vlm_fallback_service().describe_now(job, max_wait_s)
    if outcome.result is None:
        problem = "busy" if outcome.reason == "busy" else f"local_{outcome.reason}".split(":")[0]
    else:
        problem = local_answer_problem(outcome.result, config.min_confidence)
    logger.info(
        "Local-first re-analysis: %s (waited %.1fs)",
        problem or "ok",
        outcome.waited_s,
        extra={"event_type": "reanalyze_local_result", "outcome": problem or "ok"},
    )
    return outcome.result, problem
