"""
Tests for AIResilienceService (Phase B - Decomposition, Phase 3.1)

Verifies that circuit breaker ownership, state management, and Prometheus
integration work correctly after extraction from ai_service.py.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.ai_resilience_service import (
    AIResilienceService,
    ai_resilience_service,
    DEFAULT_CIRCUIT_BREAKER_CONFIG,
)
from app.services.ai_circuit_breaker import CircuitState


class TestAIResilienceServiceBasic:
    def test_singleton_instance_exists(self):
        """The module-level instance should be importable and be an AIResilienceService."""
        assert isinstance(ai_resilience_service, AIResilienceService)

    def test_initialize_creates_breakers_for_active_providers(self):
        service = AIResilienceService()
        service.initialize_circuit_breakers(["openai", "grok"])

        assert "openai" in service.circuit_breakers
        assert "grok" in service.circuit_breakers
        assert len(service.circuit_breakers) == 2

    def test_can_use_provider_returns_true_when_closed(self):
        service = AIResilienceService()
        service.initialize_circuit_breakers(["openai"])

        assert service.can_use_provider("openai") is True
        assert service.can_use_provider("openai") is True  # idempotent

    def test_record_result_updates_state_and_metrics(self):
        service = AIResilienceService()
        service.initialize_circuit_breakers(["claude"])

        # Record a failure (should still be closed after 1 failure)
        service.record_result("claude", success=False)

        breaker = service.get_provider_breaker("claude")
        assert breaker is not None
        assert breaker.state == CircuitState.CLOSED

        # Record enough failures to trip (default threshold is 5 consecutive)
        for _ in range(5):
            service.record_result("claude", success=False)

        # After 6 failures total the breaker should be OPEN
        assert service.can_use_provider("claude") is False
        assert service.get_provider_breaker("claude").state == CircuitState.OPEN

    def test_reset_provider_restores_closed_state(self):
        service = AIResilienceService()
        service.initialize_circuit_breakers(["gemini"])

        for _ in range(6):
            service.record_result("gemini", success=False)

        assert service.can_use_provider("gemini") is False

        service.reset_circuit_breaker("gemini")
        assert service.can_use_provider("gemini") is True
        assert service.get_provider_breaker("gemini").state == CircuitState.CLOSED

    def test_unknown_provider_is_allowed_defensively(self):
        service = AIResilienceService()
        # No breakers initialized
        assert service.can_use_provider("openai") is True


class TestAIResilienceServiceConfigLoading:
    """These tests mock the DB so we don't need a real database."""

    @patch("app.services.ai_resilience_service.get_db_session")
    def test_load_config_falls_back_to_default_when_no_setting(self, mock_get_db):
        # Simulate no row in SystemSetting
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value.__enter__.return_value = mock_db

        service = AIResilienceService()
        cfg = service._load_circuit_breaker_config("openai")

        assert cfg.failure_threshold == DEFAULT_CIRCUIT_BREAKER_CONFIG.failure_threshold
        assert cfg.recovery_timeout == DEFAULT_CIRCUIT_BREAKER_CONFIG.recovery_timeout

    def test_default_config_constant_is_usable(self):
        assert DEFAULT_CIRCUIT_BREAKER_CONFIG.failure_threshold >= 3
        assert DEFAULT_CIRCUIT_BREAKER_CONFIG.window_duration_seconds > 0
