"""
AIResilienceService

Owns and manages all AICircuitBreaker instances for AI providers.

Responsibilities (Phase B decomposition - Phase 3.1):
- Per-provider circuit breaker lifecycle (creation, config reload, reset)
- Loading per-provider CircuitBreakerConfig from SystemSetting JSON
  (keys: ai_circuit_breaker_config_{provider} and "default")
- Exposing can_use_provider() for the hot path in AIService
- Recording success/failure and driving state transitions + Prometheus metrics
- Providing full resilience status for the /api/v1/system/ai-resilience endpoints
- Supporting "Reset All" and per-provider reset (with global last_reset timestamp)

This extraction moves ~150 lines of resilience logic out of the 4200-line
ai_service.py God class, making both the circuit breaker behavior and the
AI orchestration easier to test and evolve independently.

Follows the same pattern as AIPromptService (Phase 2 extraction).

# Migrated to @singleton decorator (core.decorators) as part of #450 (Lightweight DI Container).

Story / Issue: #444 (ai_service.py decomposition tracking) + #450
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db_session
from app.core.decorators import singleton
from app.core.metrics import (
    ai_circuit_breaker_state,
    ai_circuit_breaker_transitions_total,
)
from app.models.system_setting import SystemSetting
from app.services.ai_circuit_breaker import (
    AICircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from app.services.ai_types import AIProvider  # used in get_ai_resilience_status / reset (was missing -> NameError)

logger = logging.getLogger(__name__)


def _cooldown_settings() -> tuple:
    """(quota base s, quota max s, rate-limit s) from settings, with safe defaults."""
    try:
        from app.core.config import settings

        base = float(getattr(settings, "AI_QUOTA_COOLDOWN_S", 3600.0))
        cap = max(base, float(getattr(settings, "AI_QUOTA_COOLDOWN_MAX_S", 21_600.0)))
        rate = float(getattr(settings, "AI_RATE_LIMIT_COOLDOWN_S", 300.0))
        return base, cap, rate
    except Exception:  # noqa: BLE001
        return 3600.0, 21_600.0, 300.0


# Default configuration used when no SystemSetting override exists
DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig()


@singleton
class AIResilienceService:
    """
    Central owner of AI provider circuit breakers.

    All stateful circuit breaker instances live here. AIService delegates
    the resilience checks and result recording to this service.

    The service is stateful (holds live AICircuitBreaker objects with
    failure windows and transition history) and is intended to be a
    long-lived singleton alongside AIService.
    """

    def __init__(self):
        """Initialize with empty breaker map. Breakers are created on configure."""
        self.circuit_breakers: Dict[str, AICircuitBreaker] = {}
        # Consecutive quota trips per provider (doubles the cooldown).
        self._quota_trips: Dict[str, int] = {}

    # =====================================================================
    # Configuration & Provider Initialization
    # =====================================================================

    def _load_circuit_breaker_config(self, provider_name: str) -> CircuitBreakerConfig:
        """
        Load per-provider (or "default") circuit breaker config from SystemSetting.

        Expected key format: ai_circuit_breaker_config_{provider_name}
        Value is JSON matching CircuitBreakerConfig fields.

        Falls back to DEFAULT_CIRCUIT_BREAKER_CONFIG on any error or missing setting.
        """
        key = f"ai_circuit_breaker_config_{provider_name}"
        try:
            with get_db_session() as db:
                setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
                if setting and setting.value:
                    data = json.loads(setting.value)
                    return CircuitBreakerConfig(**data)
        except Exception as e:
            logger.warning(
                f"Failed to load circuit breaker config for {provider_name}: {e}"
            )

        return DEFAULT_CIRCUIT_BREAKER_CONFIG

    def initialize_circuit_breakers(
        self,
        active_provider_names: List[str],
    ) -> None:
        """
        Create AICircuitBreaker instances for each currently configured AI provider.

        Called from AIService.configure_providers() after the vision providers
        have been instantiated.

        `active_provider_names` should be lowercase strings: ["openai", "grok", ...]

        Each breaker is initialized with its (possibly DB-overridden) config
        and the corresponding Prometheus gauge is set to CLOSED (0).
        """
        self.circuit_breakers.clear()

        for provider_name in active_provider_names:
            name = provider_name.lower()
            cb_config = self._load_circuit_breaker_config(name)

            breaker = AICircuitBreaker(name, cb_config)
            self.circuit_breakers[name] = breaker

            # Initialize Prometheus gauge
            ai_circuit_breaker_state.labels(provider=name).set(0)

            logger.info(
                f"Circuit breaker initialized for {name}",
                extra={"event_type": "ai_circuit_initialized", "provider": name},
            )

    # =====================================================================
    # Hot-path usage (called on every AI attempt)
    # =====================================================================

    def can_use_provider(self, provider: str) -> bool:
        """
        Check whether the circuit breaker for this provider currently allows calls.

        Returns True for CLOSED or (HALF_OPEN with remaining test slots).
        Returns False if OPEN (fast fail).

        `provider` should be a lowercase string ("openai", "grok", etc.).
        """
        name = provider.lower()
        breaker = self.circuit_breakers.get(name)
        if breaker is None:
            # No breaker configured for this provider -> allow (defensive)
            return True

        return breaker.can_execute()

    def record_result(self, provider: str, success: bool) -> None:
        """
        Record the outcome of an AI call for the given provider.

        - Updates the breaker internal state (may cause CLOSED -> OPEN or HALF_OPEN -> CLOSED)
        - Updates the Prometheus ai_circuit_breaker_state gauge
        - Increments ai_circuit_breaker_transitions_total on any state change

        This is the single place where circuit breaker metrics are emitted.

        `provider` should be a lowercase string.
        """
        name = provider.lower()
        breaker = self.circuit_breakers.get(name)
        if breaker is None:
            return

        previous_state = breaker.state.value

        if success:
            self._quota_trips.pop(name, None)
            breaker.record_success()
        else:
            breaker.record_failure()

        # Always update the gauge after state may have changed
        current_state_value = breaker.get_state_value()
        ai_circuit_breaker_state.labels(provider=name).set(current_state_value)

        # Record transition counter if state actually changed
        current_state = breaker.state.value
        if previous_state != current_state:
            ai_circuit_breaker_transitions_total.labels(
                provider=name,
                from_state=previous_state,
                to_state=current_state,
            ).inc()

            logger.info(
                f"Circuit breaker for {name} transitioned "
                f"{previous_state} -> {current_state}",
                extra={
                    "event_type": "ai_circuit_transition",
                    "provider": name,
                    "from": previous_state,
                    "to": current_state,
                },
            )

    def quota_cooldown_s(self, provider: str) -> float:
        """Cooldown for the next quota trip: base, doubled per repeat, capped."""
        base, cap = _cooldown_settings()[:2]
        trips = self._quota_trips.get(provider.lower(), 0)
        return min(cap, base * (2 ** min(trips, 16)))

    def trip_quota(
        self,
        provider: str,
        cooldown_s: Optional[float] = None,
        reason: str = "quota_exhausted",
    ) -> None:
        """Open the provider circuit immediately after quota or auth failure.

        Without an explicit ``cooldown_s`` the provider stays out for
        AI_QUOTA_COOLDOWN_S (1 h by default), doubling on each repeat trip up
        to AI_QUOTA_COOLDOWN_MAX_S, so an out-of-credit provider is retried a
        few times a day instead of every two minutes. A success resets the
        escalation. ``reason`` is a short class label; the provider error body
        is not accepted here and is not logged.
        """
        name = provider.lower()
        if cooldown_s is None:
            cooldown_s = self.quota_cooldown_s(name)
            self._quota_trips[name] = self._quota_trips.get(name, 0) + 1
        label = reason if reason in ("quota_exhausted", "auth_error") else "quota_exhausted"
        self._force_open(name, cooldown_s, label)

    def trip_rate_limit(self, provider: str, cooldown_s: Optional[float] = None) -> None:
        """Open the provider circuit for AI_RATE_LIMIT_COOLDOWN_S after an HTTP 429."""
        if cooldown_s is None:
            cooldown_s = _cooldown_settings()[2]
        self._force_open(provider.lower(), cooldown_s, "rate_limited")

    def _force_open(self, name: str, cooldown_s: float, label: str) -> None:
        breaker = self.circuit_breakers.get(name)
        if breaker is None:
            logger.info(
                "No circuit breaker for %s; %s is not cached",
                name,
                label,
                extra={"event_type": "ai_circuit_quota_untracked", "provider": name},
            )
            return

        previous_state = breaker.state.value
        breaker.force_open(cooldown_s, reason=label)

        ai_circuit_breaker_state.labels(provider=name).set(breaker.get_state_value())
        current_state = breaker.state.value
        if previous_state != current_state:
            ai_circuit_breaker_transitions_total.labels(
                provider=name,
                from_state=previous_state,
                to_state=current_state,
            ).inc()

    # =====================================================================
    # Status & Management APIs (used by /api/v1/system/ai-resilience*)
    # =====================================================================

    def get_ai_resilience_status(self, db: DBSession) -> dict:
        """
        Return the full resilience picture for the UI:

        - Per-provider config (from DB or default)
        - Live runtime state (from the in-memory breaker)
        - Recent transitions
        - Global "last_reset" timestamp

        Structure matches what the frontend AIResilienceSettings page expects.
        """
        providers = ["default", "openai", "grok", "claude", "gemini"]
        result: Dict[str, Any] = {}

        for p in providers:
            key = f"ai_circuit_breaker_config_{p}"
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()

            if setting and setting.value:
                try:
                    config_dict = json.loads(setting.value)
                    config = CircuitBreakerConfig(**config_dict)
                except Exception:
                    config = DEFAULT_CIRCUIT_BREAKER_CONFIG
            else:
                config = DEFAULT_CIRCUIT_BREAKER_CONFIG

            breaker = None
            if p != "default":
                try:
                    provider_enum = AIProvider[p.upper()]
                    breaker = self.circuit_breakers.get(provider_enum)
                except (KeyError, ValueError):
                    breaker = None

            status: Dict[str, Any] = {
                "provider": p,
                "config": config,  # Pydantic dataclass serializes nicely
                "state": breaker.state.value if breaker else "closed",
                "failure_count": 0,
                "current_failure_rate": None,
                "recent_window_size": 0,
                "last_failure_time": None,
            }

            if breaker:
                breaker_status = breaker.get_status()
                status.update(
                    {
                        "failure_count": breaker_status.get("failure_count", 0),
                        "current_failure_rate": breaker_status.get("current_failure_rate"),
                        "recent_window_size": breaker_status.get("recent_window_size", 0),
                        "last_failure_time": datetime.fromtimestamp(
                            breaker_status["last_failure_time"], tz=timezone.utc
                        )
                        if breaker_status.get("last_failure_time")
                        else None,
                        "recent_transitions": breaker_status.get("recent_transitions", []),
                    }
                )

            result[p] = status

        # Global last reset timestamp (persisted so every admin sees the same value)
        last_reset_setting = db.query(SystemSetting).filter(
            SystemSetting.key == "ai_circuit_breaker_last_reset"
        ).first()
        result["last_reset"] = last_reset_setting.value if last_reset_setting else None

        return result

    def update_circuit_breaker_config(
        self, provider: str, config_data: dict, db: DBSession
    ) -> dict:
        """
        Validate, persist, and (if the provider is active) hot-reload a new
        CircuitBreakerConfig for a provider (or "default").

        Returns the status dict for that provider after the change.
        """
        key = f"ai_circuit_breaker_config_{provider}"

        # Validate
        try:
            config = CircuitBreakerConfig(**config_data)
        except Exception as e:
            raise ValueError(f"Invalid circuit breaker config: {e}")

        # Persist (full replacement)
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting:
            setting.value = json.dumps(config.model_dump())
        else:
            setting = SystemSetting(key=key, value=json.dumps(config.model_dump()))
            db.add(setting)

        db.commit()

        # Hot-reload into memory for any currently active provider
        if provider != "default":
            try:
                provider_enum = AIProvider[provider.upper()]
                if provider_enum in self.circuit_breakers:
                    self.circuit_breakers[provider_enum] = AICircuitBreaker(
                        provider, config
                    )
                    ai_circuit_breaker_state.labels(provider=provider).set(
                        self.circuit_breakers[provider_enum].get_state_value()
                    )
            except Exception as e:
                logger.warning(f"Could not hot-reload circuit breaker for {provider}: {e}")

        # Return fresh status for the caller (UI)
        status = self.get_ai_resilience_status(db)
        return status.get(provider, status.get("default"))

    def reset_circuit_breaker(self, provider: str, db: Optional[DBSession] = None) -> None:
        """
        Reset one or all ("default") circuit breakers to CLOSED.

        When provider == "default", resets every active breaker and persists
        the current UTC timestamp into the ai_circuit_breaker_last_reset setting
        so the frontend can display "Last global reset".
        """
        from datetime import datetime as dt  # local alias to avoid shadowing

        if provider == "default":
            for breaker in self.circuit_breakers.values():
                breaker.reset()

            # Persist the reset event so all admins see the same "last reset" time
            now = dt.now(timezone.utc).isoformat()
            target_db = db
            close_db = False

            if not target_db:
                target_db = next(get_db_session())
                close_db = True

            try:
                setting = target_db.query(SystemSetting).filter(
                    SystemSetting.key == "ai_circuit_breaker_last_reset"
                ).first()

                if setting:
                    setting.value = now
                else:
                    setting = SystemSetting(key="ai_circuit_breaker_last_reset", value=now)
                    target_db.add(setting)

                target_db.commit()
            finally:
                if close_db and target_db:
                    target_db.close()
        else:
            name = provider.lower()
            if name in self.circuit_breakers:
                self.circuit_breakers[name].reset()
            else:
                logger.warning(f"Reset requested for unknown provider: {provider}")

    # =====================================================================
    # Convenience / Diagnostics
    # =====================================================================

    def get_provider_breaker(self, provider: str) -> Optional[AICircuitBreaker]:
        """Return the live breaker instance (primarily for testing)."""
        name = provider.lower()
        return self.circuit_breakers.get(name)

    def reset_all_for_testing(self) -> None:
        """Reset every breaker (test helper only)."""
        for breaker in self.circuit_breakers.values():
            breaker.reset()
        self.circuit_breakers.clear()


# Backward compatible getter (delegates to @singleton decorator)
# New code can also simply do AIResilienceService() — it always returns the same instance.
def get_ai_resilience_service() -> "AIResilienceService":
    """
    Get the global AIResilienceService instance.

    Returns:
        AIResilienceService singleton instance

    Note: This is a backward-compatible wrapper. New code should prefer
          AIResilienceService() directly (the @singleton decorator guarantees
          the same instance is returned).
    """
    return AIResilienceService()


def reset_ai_resilience_service() -> None:
    """
    Reset the global AIResilienceService instance.

    Useful for testing to ensure a fresh instance with clean circuit breaker state.
    """
    AIResilienceService._reset_instance()
