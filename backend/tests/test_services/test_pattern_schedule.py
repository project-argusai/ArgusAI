"""Scheduled pattern calculation must resolve pattern_service from the container."""
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.pattern_service import PatternService
from app.services.service_container import ServiceContainer, container


def test_container_registers_pattern_service():
    service = container.pattern_service
    assert isinstance(service, PatternService)


@pytest.mark.asyncio
async def test_scheduled_pattern_calculation_job_runs_without_attribute_error(
    monkeypatch, caplog
):
    from main import scheduled_pattern_calculation_job

    mock_service = MagicMock()
    mock_service.recalculate_all_patterns = AsyncMock(
        return_value={
            "patterns_calculated": 2,
            "patterns_skipped": 1,
            "total_cameras": 3,
            "elapsed_ms": 4.0,
        }
    )
    monkeypatch.setattr(
        ServiceContainer,
        "pattern_service",
        property(lambda self: mock_service),
    )

    class _SessionCtx:
        def __enter__(self):
            return MagicMock()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.core.database.get_db_session", lambda: _SessionCtx())

    with caplog.at_level(logging.INFO):
        await scheduled_pattern_calculation_job()

    assert "AttributeError" not in caplog.text
    assert "Scheduled pattern calculation failed" not in caplog.text
    assert "Scheduled pattern calculation complete" in caplog.text
    mock_service.recalculate_all_patterns.assert_awaited_once()
