"""
AI Provider Circuit Breaker

Implements a classic circuit breaker pattern to prevent cascading failures
when an AI provider is degraded or down.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Provider is failing, requests are rejected immediately
- HALF_OPEN: Testing if provider has recovered

This is the implementation for Story #436 (Circuit Breakers for AI Providers).
"""

import time
import threading
from enum import Enum
from typing import Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    failure_threshold: int = 5                    # Consecutive failures → fast open
    recovery_timeout: float = 60.0                # Seconds before trying HALF_OPEN
    half_open_max_calls: int = 1                  # Test calls allowed in HALF_OPEN

    # Refined error detection (time-window failure rate)
    failure_rate_threshold: float = 0.5           # Open if failure rate >= 50%
    minimum_calls_in_window: int = 6              # Need at least this many calls to evaluate rate
    window_duration_seconds: float = 60.0         # Look back window for failure rate


class AICircuitBreaker:
    """
    Circuit breaker for an individual AI provider.

    Thread-safe implementation suitable for use in async environments.
    """

    def __init__(
        self,
        provider_name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        self.provider_name = provider_name
        self.config = config or CircuitBreakerConfig()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = threading.Lock()

        # For time-window failure rate detection
        self._recent_outcomes: list[tuple[float, bool]] = []  # (timestamp, was_success)

        # Keep a short history of state transitions for UI / auditing
        self._transitions: list[dict] = []  # last 30 transitions

    @property
    def state(self) -> CircuitState:
        """Current state of the circuit breaker."""
        with self._lock:
            self._update_state()
            return self._state

    def _update_state(self) -> None:
        """Check if we should transition from OPEN to HALF_OPEN."""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            if time.time() - self._last_failure_time >= self.config.recovery_timeout:
                old_state = self._state.value
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._record_transition(old_state, "half_open", "recovery_timeout_reached")
                logger.info(
                    f"Circuit breaker for {self.provider_name} moved to HALF_OPEN",
                    extra={"event_type": "ai_circuit_half_opened", "provider": self.provider_name}
                )

    def _cleanup_old_outcomes(self) -> None:
        """Remove outcomes older than the window."""
        now = time.time()
        cutoff = now - self.config.window_duration_seconds
        self._recent_outcomes = [
            (ts, success) for ts, success in self._recent_outcomes if ts >= cutoff
        ]

    def _should_open_due_to_failure_rate(self) -> bool:
        """
        Returns True if the failure rate in the recent window exceeds the threshold.
        """
        self._cleanup_old_outcomes()

        if len(self._recent_outcomes) < self.config.minimum_calls_in_window:
            return False

        failures = sum(1 for _, success in self._recent_outcomes if not success)
        failure_rate = failures / len(self._recent_outcomes)

        return failure_rate >= self.config.failure_rate_threshold

    def can_execute(self) -> bool:
        """
        Check if a call should be allowed through.

        Returns:
            True if the call should proceed, False if circuit is OPEN
        """
        with self._lock:
            self._update_state()

            if self._state == CircuitState.OPEN:
                return False

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    return False
                self._half_open_calls += 1
                return True

            # CLOSED state
            return True

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            now = time.time()
            self._recent_outcomes.append((now, True))
            self._cleanup_old_outcomes()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
                self._record_transition("half_open", "closed", "recovered")
                logger.info(
                    f"Circuit breaker for {self.provider_name} CLOSED after recovery",
                    extra={"event_type": "ai_circuit_closed", "provider": self.provider_name}
                )
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            now = time.time()
            self._recent_outcomes.append((now, False))
            self._cleanup_old_outcomes()

            self._failure_count += 1
            self._last_failure_time = now

            # Fast path: consecutive failures
            consecutive_trigger = self._failure_count >= self.config.failure_threshold

            # Refined path: failure rate in time window
            rate_trigger = self._should_open_due_to_failure_rate()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._record_transition("half_open", "open", "failed_recovery_test")
                logger.warning(
                    f"Circuit breaker for {self.provider_name} reopened after failed recovery",
                    extra={"event_type": "ai_circuit_reopened", "provider": self.provider_name}
                )
            elif (consecutive_trigger or rate_trigger) and self._state != CircuitState.OPEN:
                old_state = self._state.value
                self._state = CircuitState.OPEN
                self._record_transition(old_state, "open", "rate_or_consecutive_failures")
                failure_rate = None
                if len(self._recent_outcomes) >= self.config.minimum_calls_in_window:
                    failures = sum(1 for _, s in self._recent_outcomes if not s)
                    failure_rate = failures / len(self._recent_outcomes)

                logger.warning(
                    f"Circuit breaker for {self.provider_name} OPENED "
                    f"(consecutive={self._failure_count}, rate_trigger={rate_trigger})",
                    extra={
                        "event_type": "ai_circuit_opened",
                        "provider": self.provider_name,
                        "failure_count": self._failure_count,
                        "failure_rate": round(failure_rate, 3) if failure_rate else None,
                        "window_size": len(self._recent_outcomes),
                    }
                )

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            old_state = self._state.value
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None
            self._recent_outcomes.clear()
            self._transitions.clear()
            self._record_transition(old_state, "closed", "manual_reset")
            logger.info(
                f"Circuit breaker for {self.provider_name} manually reset",
                extra={"event_type": "ai_circuit_reset", "provider": self.provider_name}
            )

    def _record_transition(self, from_state: str, to_state: str, reason: str = "") -> None:
        """Record a state transition for history."""
        self._transitions.append({
            "timestamp": time.time(),
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
        })
        if len(self._transitions) > 30:
            self._transitions = self._transitions[-30:]

    def get_status(self) -> dict:
        """Return current status for monitoring and debugging."""
        with self._lock:
            self._update_state()
            self._cleanup_old_outcomes()

            failure_rate = None
            if len(self._recent_outcomes) >= self.config.minimum_calls_in_window:
                failures = sum(1 for _, success in self._recent_outcomes if not success)
                failure_rate = round(failures / len(self._recent_outcomes), 3)

            # Return recent transitions (most recent first)
            recent_transitions = sorted(self._transitions, key=lambda x: x["timestamp"], reverse=True)[:10]

            return {
                "provider": self.provider_name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "last_failure_time": self._last_failure_time,
                "recent_window_size": len(self._recent_outcomes),
                "current_failure_rate": failure_rate,
                "recent_transitions": recent_transitions,
            }

    def get_state_value(self) -> int:
        """Return numeric state for Prometheus (0=Closed, 1=Open, 2=HalfOpen)."""
        with self._lock:
            self._update_state()
            state_map = {
                CircuitState.CLOSED: 0,
                CircuitState.OPEN: 1,
                CircuitState.HALF_OPEN: 2,
            }
            return state_map[self._state]
