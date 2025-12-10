"""
Tests for CostCapService

Story P3-7.3: Implement Daily/Monthly Cost Caps
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
import time

from app.services.cost_cap_service import (
    CostCapService,
    CostCapStatus,
    get_cost_cap_service,
    SETTING_DAILY_CAP,
    SETTING_MONTHLY_CAP,
)
from app.models.system_setting import SystemSetting
from app.models.ai_usage import AIUsage


class TestCostCapService:
    """Test suite for CostCapService."""

    @pytest.fixture
    def service(self):
        """Create a fresh CostCapService instance for each test."""
        return CostCapService()

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    # =========================================================================
    # Get Daily/Monthly Cost Tests
    # =========================================================================

    def test_get_daily_cost_returns_sum(self, service, mock_db):
        """Test get_daily_cost returns sum of today's costs."""
        # Mock query result
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("1.50")

        cost = service.get_daily_cost(mock_db)

        assert cost == Decimal("1.50")
        mock_db.query.assert_called_once()

    def test_get_daily_cost_returns_zero_when_no_data(self, service, mock_db):
        """Test get_daily_cost returns 0 when no usage data."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = None

        cost = service.get_daily_cost(mock_db)

        assert cost == Decimal("0")

    def test_get_monthly_cost_returns_sum(self, service, mock_db):
        """Test get_monthly_cost returns sum of this month's costs."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("15.00")

        cost = service.get_monthly_cost(mock_db)

        assert cost == Decimal("15.00")
        mock_db.query.assert_called_once()

    def test_get_monthly_cost_returns_zero_when_no_data(self, service, mock_db):
        """Test get_monthly_cost returns 0 when no usage data."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = None

        cost = service.get_monthly_cost(mock_db)

        assert cost == Decimal("0")

    # =========================================================================
    # Get/Set Cap Settings Tests
    # =========================================================================

    def test_get_daily_cap_returns_value(self, service, mock_db):
        """Test get_daily_cap returns configured value."""
        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        cap = service.get_daily_cap(mock_db)

        assert cap == 5.00

    def test_get_daily_cap_returns_none_when_not_set(self, service, mock_db):
        """Test get_daily_cap returns None when not configured."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        cap = service.get_daily_cap(mock_db)

        assert cap is None

    def test_get_daily_cap_returns_none_for_zero(self, service, mock_db):
        """Test get_daily_cap returns None for zero value."""
        mock_setting = Mock()
        mock_setting.value = "0"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        cap = service.get_daily_cap(mock_db)

        assert cap is None

    def test_get_daily_cap_handles_invalid_value(self, service, mock_db):
        """Test get_daily_cap returns None for invalid value."""
        mock_setting = Mock()
        mock_setting.value = "not_a_number"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        cap = service.get_daily_cap(mock_db)

        assert cap is None

    def test_get_monthly_cap_returns_value(self, service, mock_db):
        """Test get_monthly_cap returns configured value."""
        mock_setting = Mock()
        mock_setting.value = "50.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        cap = service.get_monthly_cap(mock_db)

        assert cap == 50.00

    def test_set_daily_cap_creates_setting(self, service, mock_db):
        """Test set_daily_cap creates new setting when not exists."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service.set_daily_cap(mock_db, 5.00)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_set_daily_cap_updates_existing(self, service, mock_db):
        """Test set_daily_cap updates existing setting."""
        mock_setting = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        service.set_daily_cap(mock_db, 10.00)

        assert mock_setting.value == "10.0"
        mock_db.commit.assert_called_once()

    def test_set_daily_cap_clears_with_none(self, service, mock_db):
        """Test set_daily_cap clears value with None."""
        mock_setting = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        service.set_daily_cap(mock_db, None)

        assert mock_setting.value == ""
        mock_db.commit.assert_called_once()

    def test_set_daily_cap_invalidates_cache(self, service, mock_db):
        """Test set_daily_cap invalidates the cache."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Simulate having a cached value
        service._cache = CostCapStatus(
            daily_cost=0, daily_cap=1.0, daily_percent=0,
            monthly_cost=0, monthly_cap=None, monthly_percent=0,
            is_paused=False, pause_reason=None
        )
        service._cache_timestamp = time.time()

        service.set_daily_cap(mock_db, 5.00)

        assert service._cache is None
        assert service._cache_timestamp == 0

    # =========================================================================
    # Cap Status Tests
    # =========================================================================

    def test_get_cap_status_returns_correct_structure(self, service, mock_db):
        """Test get_cap_status returns CostCapStatus with all fields."""
        # Mock costs
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("2.50")

        # Mock caps
        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        status = service.get_cap_status(mock_db, use_cache=False)

        assert isinstance(status, CostCapStatus)
        assert hasattr(status, 'daily_cost')
        assert hasattr(status, 'daily_cap')
        assert hasattr(status, 'daily_percent')
        assert hasattr(status, 'monthly_cost')
        assert hasattr(status, 'monthly_cap')
        assert hasattr(status, 'monthly_percent')
        assert hasattr(status, 'is_paused')
        assert hasattr(status, 'pause_reason')

    def test_get_cap_status_calculates_percentage(self, service, mock_db):
        """Test get_cap_status calculates correct percentage."""
        # Mock: $2.50 daily cost, $5.00 cap = 50%
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("2.50")

        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        status = service.get_cap_status(mock_db, use_cache=False)

        assert status.daily_percent == 50.0

    def test_get_cap_status_caps_percentage_at_100(self, service, mock_db):
        """Test percentage is capped at 100 even when exceeded."""
        # Mock: $7.50 daily cost, $5.00 cap = would be 150%, capped at 100%
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("7.50")

        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        status = service.get_cap_status(mock_db, use_cache=False)

        assert status.daily_percent == 100.0

    def test_get_cap_status_uses_cache(self, service, mock_db):
        """Test get_cap_status uses cached value when valid."""
        # Set up cache
        cached_status = CostCapStatus(
            daily_cost=1.0, daily_cap=5.0, daily_percent=20.0,
            monthly_cost=10.0, monthly_cap=50.0, monthly_percent=20.0,
            is_paused=False, pause_reason=None
        )
        service._cache = cached_status
        service._cache_timestamp = time.time()

        status = service.get_cap_status(mock_db, use_cache=True)

        assert status is cached_status
        mock_db.query.assert_not_called()

    def test_get_cap_status_ignores_expired_cache(self, service, mock_db):
        """Test get_cap_status ignores expired cache."""
        # Set up expired cache (10 seconds old)
        cached_status = CostCapStatus(
            daily_cost=1.0, daily_cap=5.0, daily_percent=20.0,
            monthly_cost=10.0, monthly_cap=50.0, monthly_percent=20.0,
            is_paused=False, pause_reason=None
        )
        service._cache = cached_status
        service._cache_timestamp = time.time() - 10  # 10 seconds old

        # Mock fresh data
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("2.50")
        mock_db.query.return_value.filter.return_value.first.return_value = None

        status = service.get_cap_status(mock_db, use_cache=True)

        assert status is not cached_status
        assert status.daily_cost == 2.5

    # =========================================================================
    # Pause/Resume Logic Tests
    # =========================================================================

    def test_is_paused_when_daily_cap_exceeded(self, service, mock_db):
        """Test is_paused is True when daily cap exceeded."""
        # Mock: $6.00 daily cost, $5.00 cap
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("6.00")

        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        status = service.get_cap_status(mock_db, use_cache=False)

        assert status.is_paused is True
        assert status.pause_reason == "cost_cap_daily"

    def test_is_paused_when_monthly_cap_exceeded(self, service, mock_db):
        """Test is_paused is True when monthly cap exceeded."""
        # Daily under cap, monthly over cap
        def mock_scalar():
            if mock_db.query.call_count == 1:
                return Decimal("1.00")  # Daily cost (under cap)
            return Decimal("60.00")  # Monthly cost (over cap)

        mock_db.query.return_value.filter.return_value.scalar.side_effect = mock_scalar

        # No daily cap, monthly cap of $50
        def mock_first():
            if mock_db.query.call_count <= 2:
                return None  # No daily cap
            mock_setting = Mock()
            mock_setting.value = "50.00"
            return mock_setting

        mock_db.query.return_value.filter.return_value.first.side_effect = mock_first

        status = service.get_cap_status(mock_db, use_cache=False)

        assert status.is_paused is True
        assert status.pause_reason == "cost_cap_monthly"

    def test_is_not_paused_when_under_caps(self, service, mock_db):
        """Test is_paused is False when under all caps."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("1.00")

        mock_setting = Mock()
        mock_setting.value = "10.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        status = service.get_cap_status(mock_db, use_cache=False)

        assert status.is_paused is False
        assert status.pause_reason is None

    def test_is_not_paused_when_no_caps_set(self, service, mock_db):
        """Test is_paused is False when no caps configured."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("100.00")
        mock_db.query.return_value.filter.return_value.first.return_value = None

        status = service.get_cap_status(mock_db, use_cache=False)

        assert status.is_paused is False
        assert status.pause_reason is None

    # =========================================================================
    # Can Analyze Tests
    # =========================================================================

    def test_can_analyze_returns_true_when_not_paused(self, service, mock_db):
        """Test can_analyze returns (True, None) when not paused."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("1.00")
        mock_db.query.return_value.filter.return_value.first.return_value = None

        can_analyze, reason = service.can_analyze(mock_db)

        assert can_analyze is True
        assert reason is None

    def test_can_analyze_returns_false_when_paused(self, service, mock_db):
        """Test can_analyze returns (False, reason) when paused."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("10.00")

        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        can_analyze, reason = service.can_analyze(mock_db)

        assert can_analyze is False
        assert reason == "cost_cap_daily"

    # =========================================================================
    # Approaching Cap Tests
    # =========================================================================

    def test_is_approaching_cap_at_80_percent(self, service, mock_db):
        """Test is_approaching_cap returns True at 80% threshold."""
        # Mock: $4.00 daily cost, $5.00 cap = 80%
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("4.00")

        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        approaching, which_cap = service.is_approaching_cap(mock_db, threshold=80.0)

        assert approaching is True
        assert which_cap == "daily"

    def test_is_approaching_cap_at_custom_threshold(self, service, mock_db):
        """Test is_approaching_cap works with custom threshold."""
        # Mock: $4.50 daily cost, $5.00 cap = 90%
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("4.50")

        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        # Should be approaching at 90% threshold
        approaching, _ = service.is_approaching_cap(mock_db, threshold=90.0)
        assert approaching is True

        # Should not be approaching at 95% threshold
        approaching, _ = service.is_approaching_cap(mock_db, threshold=95.0)
        assert approaching is False

    def test_is_approaching_cap_returns_false_when_under(self, service, mock_db):
        """Test is_approaching_cap returns False when under threshold."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("2.00")

        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        approaching, which_cap = service.is_approaching_cap(mock_db)

        assert approaching is False
        assert which_cap is None

    # =========================================================================
    # Within Cap Tests
    # =========================================================================

    def test_is_within_daily_cap_true_when_under(self, service, mock_db):
        """Test is_within_daily_cap returns True when under cap."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("2.00")

        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        within = service.is_within_daily_cap(mock_db)

        assert within is True

    def test_is_within_daily_cap_false_when_at_cap(self, service, mock_db):
        """Test is_within_daily_cap returns False when at/over cap."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("5.00")

        mock_setting = Mock()
        mock_setting.value = "5.00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        within = service.is_within_daily_cap(mock_db)

        assert within is False

    def test_is_within_daily_cap_true_when_no_cap(self, service, mock_db):
        """Test is_within_daily_cap returns True when no cap set."""
        mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal("100.00")
        mock_db.query.return_value.filter.return_value.first.return_value = None

        within = service.is_within_daily_cap(mock_db)

        assert within is True


class TestGetCostCapService:
    """Test the singleton getter function."""

    def test_returns_cost_cap_service_instance(self):
        """Test get_cost_cap_service returns a CostCapService."""
        service = get_cost_cap_service()
        assert isinstance(service, CostCapService)

    def test_returns_singleton(self):
        """Test get_cost_cap_service returns the same instance."""
        service1 = get_cost_cap_service()
        service2 = get_cost_cap_service()
        assert service1 is service2
