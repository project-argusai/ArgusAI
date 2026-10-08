"""Background re-description of failed Protect events with a local vision model.

When every cloud provider fails, the Protect handler stores the event as
"AI analysis unavailable", broadcasts it, runs entity linking and alert
rules, and sends push and MQTT. Only after all of that does it hand the
in-memory snapshot to this service. The service then asks a local
OpenAI-compatible model (Ollama on the same host) for the same structured
description, fills in the stored row, and re-runs entity linking plus any
alert rules that did not already fire for the event.

Why background and not a longer live budget: a 4B local model takes about
7-12 s per image on a base M4, so it cannot fit the 5 s live single-image
SLA, and waiting for it would hold notifications. Here a slow, stopped, or
misconfigured local server only means the event keeps its placeholder.

Safety rails:
- Off unless ``LOCAL_VLM_ENABLED`` is true.
- The base URL must be loopback unless ``LOCAL_VLM_ALLOW_REMOTE`` is true,
  so household images stay on this host by default. No API key is sent.
- One local call at a time, a bounded queue (``LOCAL_VLM_MAX_PENDING``),
  a per-call budget (``LOCAL_VLM_TIMEOUT_MS``), and stale jobs are dropped.
- A row someone already described (manual re-analysis) is never overwritten.
- Push and MQTT are not sent again. Logs carry ids and error classes only,
  never the description text or the response body.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, ContextManager, Dict, Optional
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.services.ai_provider_order import classify_provider_error
from app.services.ai_types import AIResult

logger = logging.getLogger(__name__)

UNAVAILABLE_DESCRIPTION = "AI analysis unavailable"
# A job older than this when it reaches the model is skipped. The event is
# long past and the queue was clearly backed up.
MAX_JOB_AGE_S = 600.0
# Low confidence matches the manual re-analysis rule.
LOW_CONFIDENCE_BELOW = 50

SessionFactory = Callable[[], ContextManager[Session]]
FieldsBuilder = Callable[[AIResult, Session], Dict[str, Any]]


@dataclass(frozen=True)
class LocalVLMConfig:
    enabled: bool = False
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "qwen3-vl:4b-instruct"
    timeout_ms: int = 60_000
    max_image_side: int = 1024
    max_pending: int = 4
    allow_remote: bool = False

    @classmethod
    def from_settings(cls) -> "LocalVLMConfig":
        from app.core.config import settings

        return cls(
            enabled=bool(settings.LOCAL_VLM_ENABLED),
            base_url=str(settings.LOCAL_VLM_BASE_URL or "").strip(),
            model=str(settings.LOCAL_VLM_MODEL or "").strip(),
            timeout_ms=int(settings.LOCAL_VLM_TIMEOUT_MS),
            max_image_side=int(settings.LOCAL_VLM_MAX_IMAGE_SIDE),
            max_pending=int(settings.LOCAL_VLM_MAX_PENDING),
            allow_remote=bool(settings.LOCAL_VLM_ALLOW_REMOTE),
        )

    def problem(self) -> Optional[str]:
        """Why this config cannot be used, or None when it is usable."""
        if not self.enabled:
            return "disabled"
        if not self.model:
            return "no model configured"
        try:
            parts = urlsplit(self.base_url)
        except ValueError:
            return "base URL is not a valid URL"
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return "base URL must be http(s)://host[:port]/..."
        if parts.username or parts.password:
            return "base URL must not contain credentials"
        if not self.allow_remote and not is_loopback_host(parts.hostname):
            return "base URL is not loopback and LOCAL_VLM_ALLOW_REMOTE is false"
        return None


def is_loopback_host(host: str) -> bool:
    """True for localhost and loopback addresses (127.0.0.0/8, ::1)."""
    host = (host or "").strip().lower().rstrip(".")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class RedescribeJob:
    """Everything the background call needs, captured before the handler returns."""

    event_id: str
    image_base64: str
    camera_id: Optional[str]
    camera_name: str
    event_type: Optional[str]
    local_timestamp: Optional[str] = None
    custom_prompt: Optional[str] = None
    # Handler naming step (verified entities, carrier, enriched text) bound to
    # this event's pre-AI context. Optional so the service works without it.
    fields_builder: Optional[FieldsBuilder] = None
    created_monotonic: float = field(default_factory=time.monotonic)


class LocalVLMFallbackService:
    """Bounded background queue that re-describes failed events locally."""

    def __init__(
        self,
        config: Optional[LocalVLMConfig] = None,
        provider: Any = None,
        session_factory: Optional[SessionFactory] = None,
    ):
        self.config = config or LocalVLMConfig.from_settings()
        self._provider = provider
        self._session_factory = session_factory
        self._tasks: set = set()
        self._pending = 0
        self._semaphore: Optional[asyncio.Semaphore] = None
        self.stats: Dict[str, int] = {
            "scheduled": 0,
            "skipped_queue_full": 0,
            "skipped_stale": 0,
            "failed": 0,
            "applied": 0,
            "skipped_already_described": 0,
        }
        problem = self.config.problem()
        self.disabled_reason = problem
        if problem and problem != "disabled":
            logger.warning(
                "Local VLM fallback disabled: %s",
                problem,
                extra={"event_type": "local_vlm_config_invalid"},
            )
        elif not problem:
            logger.info(
                "Local VLM fallback enabled (model=%s, timeout=%sms)",
                self.config.model,
                self.config.timeout_ms,
                extra={"event_type": "local_vlm_enabled"},
            )

    @property
    def enabled(self) -> bool:
        return self.disabled_reason is None

    @property
    def pending(self) -> int:
        return self._pending

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def schedule(self, job: RedescribeJob) -> bool:
        """Queue a re-description. Never blocks and never raises.

        Returns True when a background task was started.
        """
        try:
            if not self.enabled or not job.event_id or not job.image_base64:
                return False
            if self._pending >= self.config.max_pending:
                self.stats["skipped_queue_full"] += 1
                logger.warning(
                    "Local VLM queue full; event keeps its placeholder",
                    extra={"event_type": "local_vlm_queue_full", "event_id": job.event_id},
                )
                return False
            loop = asyncio.get_running_loop()
            self._pending += 1
            try:
                task = loop.create_task(self._run(job), name=f"local-vlm-{job.event_id[:8]}")
            except Exception:
                self._pending -= 1
                raise
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            self.stats["scheduled"] += 1
            return True
        except Exception as exc:  # noqa: BLE001 - must never affect ingest
            logger.warning(
                "Local VLM scheduling failed",
                extra={
                    "event_type": "local_vlm_schedule_failed",
                    "event_id": getattr(job, "event_id", None),
                    "error_type": type(exc).__name__,
                },
            )
            return False

    async def drain(self) -> None:
        """Wait for queued work (tests and shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ------------------------------------------------------------------
    # Work
    # ------------------------------------------------------------------

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(1)
        return self._semaphore

    def _get_provider(self):
        if self._provider is None:
            from app.services.ai_providers.local_provider import LocalVLMProvider

            self._provider = LocalVLMProvider(
                base_url=self.config.base_url,
                model=self.config.model,
                max_image_side=self.config.max_image_side,
                default_timeout_s=self.config.timeout_ms / 1000.0,
            )
        return self._provider

    def _sessions(self) -> SessionFactory:
        if self._session_factory is not None:
            return self._session_factory
        from app.core.database import get_db_session

        return get_db_session

    async def _run(self, job: RedescribeJob) -> None:
        try:
            async with self._get_semaphore():
                age = time.monotonic() - job.created_monotonic
                if age > MAX_JOB_AGE_S:
                    self.stats["skipped_stale"] += 1
                    logger.warning(
                        "Local VLM job too old; skipped",
                        extra={"event_type": "local_vlm_stale", "event_id": job.event_id, "age_s": int(age)},
                    )
                    return
                result = await self.redescribe(job)
            if not result.success:
                self.stats["failed"] += 1
                logger.warning(
                    "Local VLM re-description failed (%s)",
                    classify_provider_error(result.error),
                    extra={
                        "event_type": "local_vlm_failed",
                        "event_id": job.event_id,
                        "elapsed_ms": result.response_time_ms,
                    },
                )
                return
            if self._apply(job, result):
                self.stats["applied"] += 1
                logger.info(
                    "Local VLM described event %s in %sms",
                    job.event_id,
                    result.response_time_ms,
                    extra={
                        "event_type": "local_vlm_applied",
                        "event_id": job.event_id,
                        "elapsed_ms": result.response_time_ms,
                        "model": self.config.model,
                    },
                )
                await self._rerun_entity_steps(job.event_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - background work never raises
            self.stats["failed"] += 1
            logger.warning(
                "Local VLM background job failed",
                extra={"event_type": "local_vlm_job_error", "event_id": job.event_id, "error_type": type(exc).__name__},
            )
        finally:
            self._pending = max(0, self._pending - 1)

    def build_prompt(self, job: RedescribeJob) -> str:
        """The same prompt the live single-image path builds for this event."""
        from app.services.ai_prompt_service import AIPromptService
        from app.services.identification import ensure_identification_prompt
        from app.services.vision_analysis_orchestrator import get_vision_analysis_orchestrator

        prompt_service = None
        try:
            prompt_service = get_vision_analysis_orchestrator().prompt_service
        except Exception:  # noqa: BLE001 - fall back to the default prompt service
            prompt_service = None
        prompt_service = prompt_service or AIPromptService()
        prompt, _variant = prompt_service.select_and_build_prompt(
            camera_id=job.camera_id,
            camera_name=job.camera_name,
            custom_prompt=job.custom_prompt,
            detected_objects=[],
            timestamp=job.local_timestamp,
            analysis_mode="single_image",
        )
        return ensure_identification_prompt(prompt)

    async def redescribe(self, job: RedescribeJob) -> AIResult:
        """One bounded local call. Returns a failed AIResult instead of raising."""
        from app.services.ai_providers.local_provider import (
            LOCAL_PROVIDER_NAME,
            downscale_image_base64,
        )

        start = time.time()
        timeout_s = self.config.timeout_ms / 1000.0
        try:
            prompt = self.build_prompt(job)
            # PIL work off the event loop; the provider then sees a small image.
            image = await asyncio.to_thread(
                downscale_image_base64, job.image_base64, self.config.max_image_side
            )
            return await asyncio.wait_for(
                self._get_provider().generate_description(
                    image,
                    job.camera_name,
                    job.local_timestamp or "",
                    [],
                    custom_prompt=prompt,
                    request_timeout_s=timeout_s,
                ),
                timeout=timeout_s + 2.0,
            )
        except asyncio.TimeoutError:
            error = f"timeout after {int(timeout_s * 1000)}ms"
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}"
        return AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider=LOCAL_PROVIDER_NAME,
            tokens_used=0,
            response_time_ms=int((time.time() - start) * 1000),
            cost_estimate=0.0,
            success=False,
            error=error,
        )

    def _apply(self, job: RedescribeJob, result: AIResult) -> bool:
        """Write the local description onto the stored row. True when written."""
        from app.models.event import Event
        from app.services.ai_providers.local_provider import LOCAL_PROVIDER_NAME
        from app.services.identification import dumps_identification
        from app.services.protect_event_storage_service import _objects_for_new_event
        from app.services.vagueness_detector import VaguenessDetector

        with self._sessions()() as db:
            event = db.query(Event).filter(Event.id == job.event_id).first()
            if event is None:
                return False
            if event.provider_used or (event.description or "") != UNAVAILABLE_DESCRIPTION:
                # Someone (manual re-analysis, a later update) already described it.
                self.stats["skipped_already_described"] += 1
                return False

            fields: Dict[str, Any] = {}
            if job.fields_builder is not None:
                try:
                    fields = job.fields_builder(result, db) or {}
                except Exception as exc:  # noqa: BLE001 - naming is best effort
                    logger.warning(
                        "Local VLM naming step failed; storing unnamed description",
                        extra={"event_type": "local_vlm_naming_failed", "event_id": job.event_id,
                               "error_type": type(exc).__name__},
                    )
                    fields = {}

            description = (result.description or "").strip()
            if not description:
                return False
            vague = VaguenessDetector().is_vague(description)
            ai_confidence = result.ai_confidence

            event.description = description
            event.enriched_description = fields.get("enriched_description") or description
            event.confidence = result.confidence
            event.ai_confidence = ai_confidence
            event.low_confidence = (
                ai_confidence is not None and ai_confidence < LOW_CONFIDENCE_BELOW
            ) or vague.is_vague
            event.vague_reason = vague.reason if vague.is_vague else None
            event.objects_detected = json.dumps(_objects_for_new_event(result, job.event_type))
            identification = dumps_identification(getattr(result, "identification", None))
            if identification is not None:
                event.identification = identification
            if fields.get("matched_entity_ids") and not event.matched_entity_ids:
                event.matched_entity_ids = fields["matched_entity_ids"]
            if fields.get("recognition_status") and not event.recognition_status:
                event.recognition_status = fields["recognition_status"]
            if fields.get("delivery_carrier") and not event.delivery_carrier:
                event.delivery_carrier = fields["delivery_carrier"]
            event.provider_used = LOCAL_PROVIDER_NAME
            event.ai_fallback_used = True
            event.ai_cost = 0.0
            db.commit()
            return True

    async def _rerun_entity_steps(self, event_id: str) -> None:
        """Link newly verified entities, then fire only rules that did not fire yet."""
        from app.services.event_entity_linking import (
            ALERT_RULES_TIMEOUT_S,
            ENTITY_LINK_TIMEOUT_S,
            link_stored_matches,
        )

        sessions = self._sessions()
        try:
            await asyncio.wait_for(link_stored_matches(event_id, sessions), ENTITY_LINK_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - includes TimeoutError
            logger.warning(
                "Local VLM entity linking failed",
                extra={"event_type": "local_vlm_link_failed", "event_id": event_id, "error_type": type(exc).__name__},
            )
        try:
            await asyncio.wait_for(self._fire_new_alert_rules(event_id), ALERT_RULES_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Local VLM alert rule evaluation failed",
                extra={"event_type": "local_vlm_alerts_failed", "event_id": event_id, "error_type": type(exc).__name__},
            )

    async def _fire_new_alert_rules(self, event_id: str) -> int:
        """Run alert rules again, skipping rules that already fired for this event.

        ``execute_actions`` overwrites ``alert_rule_ids`` with the rules it ran,
        so the earlier ids are merged back afterwards.
        """
        from app.models.event import Event
        from app.services.alert_engine import AlertEngine

        with self._sessions()() as db:
            event = db.query(Event).filter(Event.id == event_id).first()
            if event is None:
                return 0
            try:
                already = [str(x) for x in json.loads(event.alert_rule_ids or "[]")]
            except (TypeError, ValueError):
                already = []
            engine = AlertEngine(db)
            new_rules = [r for r in engine.evaluate_all_rules(event) if str(r.id) not in already]
            if not new_rules:
                return 0
            await engine.execute_actions(event, new_rules)
            event.alert_triggered = True
            event.alert_rule_ids = json.dumps(already + [str(r.id) for r in new_rules])
            db.commit()
            return len(new_rules)


_service: Optional[LocalVLMFallbackService] = None


def get_local_vlm_fallback_service() -> LocalVLMFallbackService:
    global _service
    if _service is None:
        _service = LocalVLMFallbackService()
    return _service


def reset_local_vlm_fallback_service() -> None:
    global _service
    _service = None
