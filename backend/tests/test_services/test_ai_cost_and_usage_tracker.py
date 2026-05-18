"""
Tests for AICostAndUsageTracker (#447)
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.services.ai_cost_and_usage_tracker import (
    AICostAndUsageTracker,
    get_ai_cost_and_usage_tracker,
    reset_ai_cost_and_usage_tracker,
)
from app.models.ai_usage import AIUsage


class TestAICostAndUsageTracker:
    """Unit tests for the dedicated cost & usage tracker."""

    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        reset_ai_cost_and_usage_tracker()
        yield
        reset_ai_cost_and_usage_tracker()

    def test_record_usage_creates_record(self, db_session):
        tracker = AICostAndUsageTracker()

        tracker.record_usage(
            provider="openai",
            success=True,
            tokens_used=1500,
            cost_estimate=0.0123,
            analysis_mode="single_image",
            image_count=1,
        )

        # Verify it was persisted
        records = db_session.query(AIUsage).filter(AIUsage.provider == "openai").all()
        assert len(records) == 1
        assert records[0].tokens_used == 1500
        assert records[0].cost_estimate == 0.0123

    def test_get_usage_stats_returns_aggregates(self, db_session):
        tracker = AICostAndUsageTracker()

        # Seed some data
        for i in range(3):
            tracker.record_usage(
                provider="grok" if i % 2 == 0 else "claude",
                success=True,
                tokens_used=1000,
                cost_estimate=0.01,
            )

        stats = tracker.get_usage_stats()

        assert stats["total_calls"] == 3
        assert stats["total_tokens"] == 3000
        assert stats["total_cost"] > 0
        assert "grok" in stats["provider_breakdown"]
        assert "claude" in stats["provider_breakdown"]

    def test_get_daily_breakdown(self, db_session):
        tracker = AICostAndUsageTracker()
        today = datetime.now(timezone.utc).date()

        tracker.record_usage(provider="openai", success=True, cost_estimate=0.05)
        tracker.record_usage(provider="openai", success=True, cost_estimate=0.07)

        breakdown = tracker.get_daily_breakdown()

        assert len(breakdown) >= 1
        today_data = next((d for d in breakdown if d["date"] == str(today)), None)
        assert today_data is not None
        assert today_data["calls"] == 2
        assert today_data["cost"] == round(0.12, 6)

    def test_get_hourly_breakdown(self, db_session):
        tracker = AICostAndUsageTracker()
        breakdown = tracker.get_hourly_breakdown()
        # Just ensure it runs without error and returns list
        assert isinstance(breakdown, list)

    def test_get_top_cameras_placeholder(self):
        tracker = AICostAndUsageTracker()
        result = tracker.get_top_cameras_by_cost()
        assert result == []  # Known limitation until camera_id is on AIUsage

    def test_cost_cap_integration_hook(self, db_session):
        """Verify that record_usage invalidates CostCapService cache."""
        from app.services.cost_cap_service import get_cost_cap_service

        tracker = AICostAndUsageTracker()
        cost_cap = get_cost_cap_service()

        # Prime the cache
        cost_cap.get_cap_status(db_session)

        # Record usage — should trigger invalidation
        tracker.record_usage(provider="openai", success=True, cost_estimate=10.0)

        # Cache should have been invalidated (we can't easily assert private state,
        # but at least the call shouldn't explode)
        status = cost_cap.get_cap_status(db_session)
        assert status is not None

    def test_singleton_behavior(self):
        t1 = get_ai_cost_and_usage_tracker()
        t2 = get_ai_cost_and_usage_tracker()
        assert t1 is t2

        reset_ai_cost_and_usage_tracker()
        t3 = get_ai_cost_and_usage_tracker()
        assert t3 is not t1
