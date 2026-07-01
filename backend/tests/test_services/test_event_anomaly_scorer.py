"""
Unit tests for EventAnomalyScorer.

Extracted from EventProcessor (#530 / #443 Phase B decomposition): owns the two
fire-and-forget post-storage tasks — incremental activity-baseline updates and
per-event anomaly scoring — each using its own DB session with errors contained.
"""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.event_anomaly_scorer import (
    EventAnomalyScorer,
    reset_event_anomaly_scorer,
)


@pytest.fixture
def scorer():
    reset_event_anomaly_scorer()
    return EventAnomalyScorer()


@contextmanager
def _fake_session(db):
    yield db


def _patch(module_container, db):
    return (
        patch("app.services.event_anomaly_scorer._get_container", return_value=module_container),
        patch("app.services.event_anomaly_scorer.get_db_session", lambda: _fake_session(db)),
    )


@pytest.mark.asyncio
async def test_update_activity_baseline_calls_pattern_service(scorer):
    pattern_service = MagicMock()
    pattern_service.update_baseline_incremental = AsyncMock()
    container = SimpleNamespace(pattern_service=pattern_service)
    db = MagicMock()
    event = SimpleNamespace(id="evt-1")

    p_c, p_db = _patch(container, db)
    with p_c, p_db:
        await scorer.update_activity_baseline("cam-1", event)

    pattern_service.update_baseline_incremental.assert_awaited_once_with(db, "cam-1", event)


@pytest.mark.asyncio
async def test_calculate_anomaly_score_refetches_and_scores(scorer):
    refetched = SimpleNamespace(id="evt-2")
    anomaly_service = MagicMock()
    anomaly_service.score_event = AsyncMock()
    container = SimpleNamespace(anomaly_scoring_service=anomaly_service)
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = refetched
    event = SimpleNamespace(id="evt-2")

    p_c, p_db = _patch(container, db)
    with p_c, p_db:
        await scorer.calculate_anomaly_score(event)

    anomaly_service.score_event.assert_awaited_once_with(db, refetched)


@pytest.mark.asyncio
async def test_calculate_anomaly_score_skips_when_event_missing(scorer):
    anomaly_service = MagicMock()
    anomaly_service.score_event = AsyncMock()
    container = SimpleNamespace(anomaly_scoring_service=anomaly_service)
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None
    event = SimpleNamespace(id="gone")

    p_c, p_db = _patch(container, db)
    with p_c, p_db:
        await scorer.calculate_anomaly_score(event)

    anomaly_service.score_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_errors_are_swallowed(scorer):
    pattern_service = MagicMock()
    pattern_service.update_baseline_incremental = AsyncMock(side_effect=RuntimeError("db down"))
    container = SimpleNamespace(pattern_service=pattern_service)
    db = MagicMock()
    event = SimpleNamespace(id="evt-3")

    p_c, p_db = _patch(container, db)
    with p_c, p_db:
        # Must not raise.
        await scorer.update_activity_baseline("cam-1", event)
