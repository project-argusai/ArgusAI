"""
Cost Alert Service for Budget Notifications

Story P3-7.4: Add Cost Alerts and Notifications

Provides threshold-based alerts when AI costs approach or reach configured caps.
Integrates with CostCapService for cap status and WebSocket for real-time delivery.

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""

import logging
from app.core.decorators import singleton
from datetime import datetime, timezone
from typing import Optional, Literal, List
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting
from app.services.cost_cap_service import get_cost_cap_service, CostCapStatus

logger = logging.getLogger(__name__)

# Threshold levels for alerts
THRESHOLD_50 = 50.0
THRESHOLD_80 = 80.0
THRESHOLD_100 = 100.0

# Alert severity mapping
AlertSeverity = Literal["info", "warning", "error"]

# SystemSetting keys for alert state tracking
# Format: cost_alert_{period}_{threshold}_date - stores ISO date when alert was sent
ALERT_KEYS = {
    "daily_50": "cost_alert_daily_50_date",
    "daily_80": "cost_alert_daily_80_date",
    "daily_100": "cost_alert_daily_100_date",
    "monthly_50": "cost_alert_monthly_50_date",
    "monthly_80": "cost_alert_monthly_80_date",
    "monthly_100": "cost_alert_monthly_100_date",
}


@dataclass
class CostAlert:
    """Cost alert data structure for notification creation."""
    threshold: float
    period: Literal["daily", "monthly"]
    severity: AlertSeverity
    title: str
    message: str
    current_cost: float
    cap: float
    percent: float


@singleton
class CostAlertService:
    """
    Service for managing cost threshold alerts.

    Tracks which thresholds have been triggered per period (day/month)
    to avoid duplicate notifications. Resets automatically on period change.

    Uses SystemSetting keys for state persistence:
    - cost_alert_daily_50_date: Date when daily 50% alert was sent
    - cost_alert_daily_80_date: Date when daily 80% alert was sent
    - cost_alert_daily_100_date: Date when daily 100% alert was sent
    - cost_alert_monthly_50_date: Month when monthly 50% alert was sent
    - cost_alert_monthly_80_date: Month when monthly 80% alert was sent
    - cost_alert_monthly_100_date: Month when monthly 100% alert was sent
    """

    def __init__(self):
        """Initialize CostAlertService."""
        self._cost_cap_service = get_cost_cap_service()

    def _get_current_date_str(self) -> str:
        """Get current UTC date as ISO string (YYYY-MM-DD)."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _get_current_month_str(self) -> str:
        """Get current UTC month as string (YYYY-MM)."""
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _get_alert_state(self, db: Session, key: str) -> Optional[str]:
        """
        Get the date/month when an alert was last sent.

        Args:
            db: Database session
            key: Alert state key from ALERT_KEYS

        Returns:
            Date/month string when alert was sent, or None if never sent
        """
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == key
        ).first()

        return setting.value if setting and setting.value else None

    def _set_alert_state(self, db: Session, key: str, value: str) -> None:
        """
        Record when an alert was sent.

        Args:
            db: Database session
            key: Alert state key from ALERT_KEYS
            value: Date/month string to record
        """
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == key
        ).first()

        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=key, value=value)
            db.add(setting)

        db.commit()
        logger.debug(f"Alert state set: {key} = {value}")

    def _clear_alert_state(self, db: Session, key: str) -> None:
        """
        Clear an alert state (for manual reset or testing).

        Args:
            db: Database session
            key: Alert state key from ALERT_KEYS
        """
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == key
        ).first()

        if setting:
            setting.value = ""
            db.commit()
            logger.debug(f"Alert state cleared: {key}")

    def _should_send_daily_alert(self, db: Session, threshold: int) -> bool:
        """
        Check if daily alert should be sent for given threshold.

        Args:
            db: Database session
            threshold: Threshold percentage (50, 80, or 100)

        Returns:
            True if alert should be sent (not already sent today)
        """
        key = ALERT_KEYS[f"daily_{threshold}"]
        last_sent = self._get_alert_state(db, key)
        current_date = self._get_current_date_str()

        return last_sent != current_date

    def _should_send_monthly_alert(self, db: Session, threshold: int) -> bool:
        """
        Check if monthly alert should be sent for given threshold.

        Args:
            db: Database session
            threshold: Threshold percentage (50, 80, or 100)

        Returns:
            True if alert should be sent (not already sent this month)
        """
        key = ALERT_KEYS[f"monthly_{threshold}"]
        last_sent = self._get_alert_state(db, key)
        current_month = self._get_current_month_str()

        return last_sent != current_month

    def _mark_daily_alert_sent(self, db: Session, threshold: int) -> None:
        """Mark daily alert as sent for given threshold."""
        key = ALERT_KEYS[f"daily_{threshold}"]
        self._set_alert_state(db, key, self._get_current_date_str())

    def _mark_monthly_alert_sent(self, db: Session, threshold: int) -> None:
        """Mark monthly alert as sent for given threshold."""
        key = ALERT_KEYS[f"monthly_{threshold}"]
        self._set_alert_state(db, key, self._get_current_month_str())

    def reset_daily_alerts(self, db: Session) -> None:
        """
        Reset all daily alert states.

        Called when a new day begins to allow alerts to trigger again.
        """
        for threshold in [50, 80, 100]:
            key = ALERT_KEYS[f"daily_{threshold}"]
            self._clear_alert_state(db, key)

        logger.info("Daily alert states reset")

    def reset_monthly_alerts(self, db: Session) -> None:
        """
        Reset all monthly alert states.

        Called when a new month begins to allow alerts to trigger again.
        """
        for threshold in [50, 80, 100]:
            key = ALERT_KEYS[f"monthly_{threshold}"]
            self._clear_alert_state(db, key)

        logger.info("Monthly alert states reset")

    def _create_alert(
        self,
        threshold: float,
        period: Literal["daily", "monthly"],
        status: CostCapStatus
    ) -> CostAlert:
        """
        Create a CostAlert object for a given threshold.

        Args:
            threshold: Threshold percentage (50, 80, or 100)
            period: "daily" or "monthly"
            status: Current cost cap status

        Returns:
            CostAlert with appropriate message and severity
        """
        if period == "daily":
            current_cost = status.daily_cost
            cap = status.daily_cap
            percent = status.daily_percent
        else:
            current_cost = status.monthly_cost
            cap = status.monthly_cap
            percent = status.monthly_percent

        period_name = period.capitalize()

        if threshold == THRESHOLD_50:
            severity: AlertSeverity = "info"
            title = f"AI costs at 50% of {period} cap"
            message = f"AI analysis costs have reached 50% of your {period} cap (${current_cost:.2f} of ${cap:.2f}). Consider reviewing your usage."
        elif threshold == THRESHOLD_80:
            severity = "warning"
            title = f"AI costs at 80% of {period} cap"
            message = f"AI analysis costs have reached 80% of your {period} cap (${current_cost:.2f} of ${cap:.2f}). Analysis will pause when cap is reached."
        else:  # 100%
            severity = "error"
            title = f"AI analysis paused - {period} cap reached"
            if period == "daily":
                message = f"AI analysis has been paused. Your {period} cost cap of ${cap:.2f} has been reached. Increase cap in settings or wait until tomorrow."
            else:
                message = f"AI analysis has been paused. Your {period} cost cap of ${cap:.2f} has been reached. Increase cap in settings or wait until next month."

        return CostAlert(
            threshold=threshold,
            period=period,
            severity=severity,
            title=title,
            message=message,
            current_cost=current_cost,
            cap=cap,
            percent=percent
        )

    def check_thresholds(self, db: Session) -> List[CostAlert]:
        """
        Check all cost thresholds and return alerts that should be sent.

        This is the main method called after AI usage is recorded.
        Returns alerts for thresholds that:
        1. Have been crossed (percentage >= threshold)
        2. Have not already been notified in current period

        Args:
            db: Database session

        Returns:
            List of CostAlert objects for alerts to send
        """
        alerts: List[CostAlert] = []

        # Get current cap status
        status = self._cost_cap_service.get_cap_status(db, use_cache=False)

        # Check daily thresholds if daily cap is set
        if status.daily_cap is not None:
            for threshold in [THRESHOLD_100, THRESHOLD_80, THRESHOLD_50]:
                if status.daily_percent >= threshold:
                    if self._should_send_daily_alert(db, int(threshold)):
                        alert = self._create_alert(threshold, "daily", status)
                        alerts.append(alert)
                        self._mark_daily_alert_sent(db, int(threshold))
                        logger.info(
                            f"Daily {int(threshold)}% alert triggered",
                            extra={
                                "threshold": threshold,
                                "daily_cost": status.daily_cost,
                                "daily_cap": status.daily_cap,
                                "daily_percent": status.daily_percent
                            }
                        )
                    # Only trigger highest threshold that hasn't been sent
                    break

        # Check monthly thresholds if monthly cap is set
        if status.monthly_cap is not None:
            for threshold in [THRESHOLD_100, THRESHOLD_80, THRESHOLD_50]:
                if status.monthly_percent >= threshold:
                    if self._should_send_monthly_alert(db, int(threshold)):
                        alert = self._create_alert(threshold, "monthly", status)
                        alerts.append(alert)
                        self._mark_monthly_alert_sent(db, int(threshold))
                        logger.info(
                            f"Monthly {int(threshold)}% alert triggered",
                            extra={
                                "threshold": threshold,
                                "monthly_cost": status.monthly_cost,
                                "monthly_cap": status.monthly_cap,
                                "monthly_percent": status.monthly_percent
                            }
                        )
                    # Only trigger highest threshold that hasn't been sent
                    break

        return alerts

    async def check_and_notify(self, db: Session) -> List[CostAlert]:
        """
        Check thresholds and send notifications for any alerts.

        This is the main entry point called from event_processor after AI usage.
        It checks thresholds, creates notifications, and broadcasts via WebSocket.

        Args:
            db: Database session

        Returns:
            List of CostAlert objects that were sent
        """
        from app.models.system_notification import SystemNotification
        from app.services.websocket_manager import get_websocket_manager

        alerts = self.check_thresholds(db)

        if not alerts:
            return []

        websocket_manager = get_websocket_manager()

        for alert in alerts:
            # Create notification record
            notification = SystemNotification(
                notification_type="cost_alert",
                severity=alert.severity,
                title=alert.title,
                message=alert.message,
                action_url="/settings?tab=ai-usage",
                extra_data={
                    "threshold": alert.threshold,
                    "period": alert.period,
                    "current_cost": alert.current_cost,
                    "cap": alert.cap,
                    "percent": alert.percent
                }
            )
            db.add(notification)
            db.commit()
            db.refresh(notification)

            logger.info(
                f"Cost alert notification created: {alert.title}",
                extra={
                    "notification_id": notification.id,
                    "severity": alert.severity,
                    "period": alert.period,
                    "threshold": alert.threshold
                }
            )

            # Broadcast via WebSocket
            await websocket_manager.broadcast({
                "type": "COST_ALERT",
                "data": {
                    "notification": notification.to_dict(),
                    "alert": {
                        "threshold": alert.threshold,
                        "period": alert.period,
                        "severity": alert.severity,
                        "current_cost": alert.current_cost,
                        "cap": alert.cap,
                        "percent": alert.percent
                    }
                }
            })

        return alerts


# Backward compatible thin getter (delegates to @singleton decorator)
def get_cost_alert_service() -> CostAlertService:
    """
    Get the global CostAlertService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer CostAlertService() directly.
    """
    return CostAlertService()


def reset_cost_alert_service() -> None:
    """Reset the global CostAlertService instance (for testing)."""
    CostAlertService._reset_instance()
