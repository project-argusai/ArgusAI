"""
Tests for CostAlertService

Story P3-7.4: Add Cost Alerts and Notifications
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from app.services.cost_alert_service import (
    CostAlertService,
    CostAlert,
    get_cost_alert_service,
    ALERT_KEYS,
    THRESHOLD_50,
    THRESHOLD_80,
    THRESHOLD_100,
)
from app.services.cost_cap_service import CostCapStatus
from app.models.system_setting import SystemSetting


class TestCostAlertService:
    """Test suite for CostAlertService."""

    @pytest.fixture
    def service(self):
        """Create a fresh CostAlertService instance for each test."""
        return CostAlertService()

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def mock_cap_status_50_percent(self):
        """Cap status at 50% daily usage."""
        return CostCapStatus(
            daily_cost=0.50,
            daily_cap=1.00,
            daily_percent=50.0,
            monthly_cost=5.00,
            monthly_cap=20.00,
            monthly_percent=25.0,
            is_paused=False,
            pause_reason=None
        )

    @pytest.fixture
    def mock_cap_status_80_percent(self):
        """Cap status at 80% daily usage."""
        return CostCapStatus(
            daily_cost=0.80,
            daily_cap=1.00,
            daily_percent=80.0,
            monthly_cost=8.00,
            monthly_cap=20.00,
            monthly_percent=40.0,
            is_paused=False,
            pause_reason=None
        )

    @pytest.fixture
    def mock_cap_status_100_percent(self):
        """Cap status at 100% daily usage (paused)."""
        return CostCapStatus(
            daily_cost=1.00,
            daily_cap=1.00,
            daily_percent=100.0,
            monthly_cost=10.00,
            monthly_cap=20.00,
            monthly_percent=50.0,
            is_paused=True,
            pause_reason="cost_cap_daily"
        )

    @pytest.fixture
    def mock_cap_status_no_cap(self):
        """Cap status with no caps set."""
        return CostCapStatus(
            daily_cost=1.00,
            daily_cap=None,
            daily_percent=0.0,
            monthly_cost=10.00,
            monthly_cap=None,
            monthly_percent=0.0,
            is_paused=False,
            pause_reason=None
        )

    # =========================================================================
    # Alert State Tracking Tests (AC5: Notification Cycle Reset)
    # =========================================================================

    def test_should_send_daily_alert_first_time(self, service, mock_db):
        """Test daily alert should be sent if never sent before."""
        # Mock no existing alert state
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = service._should_send_daily_alert(mock_db, 50)

        assert result is True

    def test_should_not_send_daily_alert_if_already_sent_today(self, service, mock_db):
        """Test daily alert should NOT be sent if already sent today."""
        # Mock existing alert state with today's date
        mock_setting = Mock()
        mock_setting.value = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        result = service._should_send_daily_alert(mock_db, 50)

        assert result is False

    def test_should_send_daily_alert_if_sent_yesterday(self, service, mock_db):
        """Test daily alert should be sent if last sent yesterday (new cycle)."""
        # Mock existing alert state with yesterday's date
        mock_setting = Mock()
        mock_setting.value = "2025-12-09"  # Yesterday
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        # Mock today's date
        with patch.object(service, '_get_current_date_str', return_value="2025-12-10"):
            result = service._should_send_daily_alert(mock_db, 50)

        assert result is True

    def test_should_send_monthly_alert_first_time(self, service, mock_db):
        """Test monthly alert should be sent if never sent before."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = service._should_send_monthly_alert(mock_db, 50)

        assert result is True

    def test_should_not_send_monthly_alert_if_already_sent_this_month(self, service, mock_db):
        """Test monthly alert should NOT be sent if already sent this month."""
        mock_setting = Mock()
        mock_setting.value = datetime.now(timezone.utc).strftime("%Y-%m")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        result = service._should_send_monthly_alert(mock_db, 50)

        assert result is False

    def test_should_send_monthly_alert_if_sent_last_month(self, service, mock_db):
        """Test monthly alert should be sent if last sent last month (new cycle)."""
        mock_setting = Mock()
        mock_setting.value = "2025-11"  # Last month
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        with patch.object(service, '_get_current_month_str', return_value="2025-12"):
            result = service._should_send_monthly_alert(mock_db, 50)

        assert result is True

    def test_mark_daily_alert_sent_creates_new_setting(self, service, mock_db):
        """Test marking daily alert as sent creates new SystemSetting."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(service, '_get_current_date_str', return_value="2025-12-10"):
            service._mark_daily_alert_sent(mock_db, 50)

        # Verify new setting was added
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_mark_daily_alert_sent_updates_existing_setting(self, service, mock_db):
        """Test marking daily alert as sent updates existing SystemSetting."""
        mock_setting = Mock()
        mock_setting.value = "2025-12-09"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        with patch.object(service, '_get_current_date_str', return_value="2025-12-10"):
            service._mark_daily_alert_sent(mock_db, 50)

        assert mock_setting.value == "2025-12-10"
        mock_db.commit.assert_called_once()

    # =========================================================================
    # Reset Logic Tests (AC5: Notification Cycle Reset)
    # =========================================================================

    def test_reset_daily_alerts_calls_clear_for_all_thresholds(self, service, mock_db):
        """Test reset_daily_alerts clears all daily alert states."""
        mock_setting = Mock(value="2025-12-10")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        service.reset_daily_alerts(mock_db)

        # Verify commit was called (clearing happens via setting value to "")
        assert mock_db.commit.call_count >= 3  # Once per threshold

    def test_reset_monthly_alerts_calls_clear_for_all_thresholds(self, service, mock_db):
        """Test reset_monthly_alerts clears all monthly alert states."""
        mock_setting = Mock(value="2025-12")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        service.reset_monthly_alerts(mock_db)

        # Verify commit was called (clearing happens via setting value to "")
        assert mock_db.commit.call_count >= 3  # Once per threshold

    # =========================================================================
    # Alert Creation Tests (AC1, AC2, AC3, AC4)
    # =========================================================================

    def test_create_alert_50_percent_daily(self, service, mock_cap_status_50_percent):
        """Test 50% daily alert has correct severity and message (AC1)."""
        alert = service._create_alert(THRESHOLD_50, "daily", mock_cap_status_50_percent)

        assert alert.threshold == 50.0
        assert alert.period == "daily"
        assert alert.severity == "info"
        assert "50%" in alert.title
        assert "daily" in alert.title
        assert "$0.50" in alert.message
        assert "$1.00" in alert.message

    def test_create_alert_80_percent_daily(self, service, mock_cap_status_80_percent):
        """Test 80% daily alert has correct severity and message (AC2)."""
        alert = service._create_alert(THRESHOLD_80, "daily", mock_cap_status_80_percent)

        assert alert.threshold == 80.0
        assert alert.period == "daily"
        assert alert.severity == "warning"
        assert "80%" in alert.title
        assert "pause" in alert.message.lower()

    def test_create_alert_100_percent_daily(self, service, mock_cap_status_100_percent):
        """Test 100% daily alert has correct severity, message, and action (AC3)."""
        alert = service._create_alert(THRESHOLD_100, "daily", mock_cap_status_100_percent)

        assert alert.threshold == 100.0
        assert alert.period == "daily"
        assert alert.severity == "error"
        assert "paused" in alert.title.lower()
        assert "settings" in alert.message.lower()
        assert "tomorrow" in alert.message.lower()

    def test_create_alert_monthly_differentiates_from_daily(self, service, mock_cap_status_80_percent):
        """Test monthly alert messages differentiate from daily (AC4)."""
        alert = service._create_alert(THRESHOLD_80, "monthly", mock_cap_status_80_percent)

        assert alert.period == "monthly"
        assert "monthly" in alert.title.lower()
        assert "$8.00" in alert.message  # Uses monthly_cost
        assert "$20.00" in alert.message  # Uses monthly_cap

    def test_create_alert_100_percent_monthly_mentions_next_month(self, service):
        """Test 100% monthly alert suggests waiting until next month."""
        status = CostCapStatus(
            daily_cost=0.50,
            daily_cap=1.00,
            daily_percent=50.0,
            monthly_cost=20.00,
            monthly_cap=20.00,
            monthly_percent=100.0,
            is_paused=True,
            pause_reason="cost_cap_monthly"
        )

        alert = service._create_alert(THRESHOLD_100, "monthly", status)

        assert "next month" in alert.message.lower()

    # =========================================================================
    # Threshold Checking Tests (AC1, AC2, AC3, AC4)
    # =========================================================================

    def test_check_thresholds_triggers_daily_50_alert(self, service, mock_db, mock_cap_status_50_percent):
        """Test check_thresholds triggers 50% daily alert."""
        # Mock no previous alerts
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(service._cost_cap_service, 'get_cap_status', return_value=mock_cap_status_50_percent):
            alerts = service.check_thresholds(mock_db)

        assert len(alerts) == 1
        assert alerts[0].threshold == 50.0
        assert alerts[0].period == "daily"
        assert alerts[0].severity == "info"

    def test_check_thresholds_triggers_daily_80_alert(self, service, mock_db, mock_cap_status_80_percent):
        """Test check_thresholds triggers 80% daily alert (highest first)."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(service._cost_cap_service, 'get_cap_status', return_value=mock_cap_status_80_percent):
            alerts = service.check_thresholds(mock_db)

        # Should only trigger 80%, not 50%
        daily_alerts = [a for a in alerts if a.period == "daily"]
        assert len(daily_alerts) == 1
        assert daily_alerts[0].threshold == 80.0
        assert daily_alerts[0].severity == "warning"

    def test_check_thresholds_triggers_daily_100_alert(self, service, mock_db, mock_cap_status_100_percent):
        """Test check_thresholds triggers 100% daily alert (highest first)."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(service._cost_cap_service, 'get_cap_status', return_value=mock_cap_status_100_percent):
            alerts = service.check_thresholds(mock_db)

        daily_alerts = [a for a in alerts if a.period == "daily"]
        assert len(daily_alerts) == 1
        assert daily_alerts[0].threshold == 100.0
        assert daily_alerts[0].severity == "error"

    def test_check_thresholds_no_alerts_when_no_cap(self, service, mock_db, mock_cap_status_no_cap):
        """Test check_thresholds returns no alerts when no caps are set."""
        with patch.object(service._cost_cap_service, 'get_cap_status', return_value=mock_cap_status_no_cap):
            alerts = service.check_thresholds(mock_db)

        assert len(alerts) == 0

    def test_check_thresholds_no_duplicate_alerts_same_period(self, service, mock_db, mock_cap_status_80_percent):
        """Test check_thresholds doesn't send duplicate alerts in same period."""
        # Mock that 80% alert was already sent today
        mock_setting = Mock()
        mock_setting.value = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        with patch.object(service._cost_cap_service, 'get_cap_status', return_value=mock_cap_status_80_percent):
            alerts = service.check_thresholds(mock_db)

        # Should not send daily 80% alert (already sent today)
        daily_alerts = [a for a in alerts if a.period == "daily"]
        assert len(daily_alerts) == 0

    def test_check_thresholds_daily_and_monthly_independent(self, service, mock_db):
        """Test daily and monthly alerts trigger independently (AC4)."""
        # Status: daily at 80%, monthly at 50%
        status = CostCapStatus(
            daily_cost=0.80,
            daily_cap=1.00,
            daily_percent=80.0,
            monthly_cost=10.00,
            monthly_cap=20.00,
            monthly_percent=50.0,
            is_paused=False,
            pause_reason=None
        )

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(service._cost_cap_service, 'get_cap_status', return_value=status):
            alerts = service.check_thresholds(mock_db)

        # Should have both daily (80%) and monthly (50%) alerts
        assert len(alerts) == 2
        periods = {a.period for a in alerts}
        assert periods == {"daily", "monthly"}

    # =========================================================================
    # Check and Notify Integration Tests (AC6: WebSocket Delivery)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_check_and_notify_creates_notification_and_broadcasts(self, service, mock_db, mock_cap_status_80_percent):
        """Test check_and_notify creates notification and broadcasts via WebSocket (AC6)."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_notification = Mock()
        mock_notification.id = "test-notification-id"
        mock_notification.to_dict.return_value = {"id": "test-notification-id", "title": "Test"}

        mock_websocket_manager = Mock()
        mock_websocket_manager.broadcast = AsyncMock(return_value=1)

        with patch.object(service._cost_cap_service, 'get_cap_status', return_value=mock_cap_status_80_percent):
            # Patch at the module where it's imported inside the method
            with patch('app.models.system_notification.SystemNotification', return_value=mock_notification):
                with patch('app.services.websocket_manager.get_websocket_manager', return_value=mock_websocket_manager):
                    alerts = await service.check_and_notify(mock_db)

        # Verify alerts were returned
        assert len(alerts) >= 1

        # Verify notification was added to DB
        mock_db.add.assert_called()
        mock_db.commit.assert_called()

        # Verify WebSocket broadcast was called with COST_ALERT type
        mock_websocket_manager.broadcast.assert_called()
        broadcast_call = mock_websocket_manager.broadcast.call_args[0][0]
        assert broadcast_call["type"] == "COST_ALERT"
        assert "notification" in broadcast_call["data"]
        assert "alert" in broadcast_call["data"]

    @pytest.mark.asyncio
    async def test_check_and_notify_returns_empty_when_no_alerts(self, service, mock_db, mock_cap_status_no_cap):
        """Test check_and_notify returns empty list when no alerts needed."""
        with patch.object(service._cost_cap_service, 'get_cap_status', return_value=mock_cap_status_no_cap):
            alerts = await service.check_and_notify(mock_db)

        assert len(alerts) == 0

    # =========================================================================
    # Singleton Tests
    # =========================================================================

    def test_get_cost_alert_service_returns_singleton(self):
        """Test get_cost_alert_service returns singleton instance."""
        service1 = get_cost_alert_service()
        service2 = get_cost_alert_service()

        assert service1 is service2

    # =========================================================================
    # Alert Key Configuration Tests
    # =========================================================================

    def test_alert_keys_configured_correctly(self):
        """Test ALERT_KEYS has all required keys."""
        expected_keys = [
            "daily_50", "daily_80", "daily_100",
            "monthly_50", "monthly_80", "monthly_100"
        ]

        for key in expected_keys:
            assert key in ALERT_KEYS
            assert ALERT_KEYS[key].startswith("cost_alert_")
