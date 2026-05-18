"""
Cost Cap Service for AI Budget Management

Story P3-7.3: Implement Daily/Monthly Cost Caps

Provides cap enforcement, status tracking, and automatic resume logic
for managing AI analysis costs.

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""

import logging
from app.core.decorators import singleton
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Optional, Literal
from dataclasses import dataclass
import time

from sqlalchemy.orm import Session

from app.services.ai_cost_and_usage_tracker import get_ai_cost_and_usage_tracker
from app.models.system_setting import SystemSetting
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 seconds to minimize DB queries while staying responsive)
CACHE_TTL_SECONDS = 5

# Setting keys for cost caps
SETTING_DAILY_CAP = "ai_daily_cost_cap"
SETTING_MONTHLY_CAP = "ai_monthly_cost_cap"


@dataclass
class CostCapStatus:
    """Cost cap status data structure."""
    daily_cost: float
    daily_cap: Optional[float]
    daily_percent: float
    monthly_cost: float
    monthly_cap: Optional[float]
    monthly_percent: float
    is_paused: bool
    pause_reason: Optional[Literal["cost_cap_daily", "cost_cap_monthly"]]


@singleton
class CostCapService:
    """
    Service for managing AI cost caps and enforcement.

    Provides methods to:
    - Check if within daily/monthly caps
    - Get current cap status with percentages
    - Determine if AI analysis should be paused

    Uses caching to minimize database queries during high-volume event processing.
    """

    def __init__(self):
        """Initialize CostCapService with cache state."""
        self._cache: Optional[CostCapStatus] = None
        self._cache_timestamp: float = 0

    def _is_cache_valid(self) -> bool:
        """Check if cached status is still valid."""
        return (
            self._cache is not None and
            time.time() - self._cache_timestamp < CACHE_TTL_SECONDS
        )

    def _invalidate_cache(self) -> None:
        """Invalidate the cache (call after cap settings change)."""
        self._cache = None
        self._cache_timestamp = 0
        logger.debug("Cost cap cache invalidated")

    def get_daily_cost(self, db: Session = None) -> Decimal:
        """
        Get total AI cost for current day (UTC).

        Delegates to AICostAndUsageTracker (#447).
        """
        tracker = get_ai_cost_and_usage_tracker()
        cost = tracker.get_daily_cost()
        return Decimal(str(cost))

    def get_monthly_cost(self, db: Session = None) -> Decimal:
        """
        Get total AI cost for current month (UTC).

        Delegates to AICostAndUsageTracker (#447).
        """
        tracker = get_ai_cost_and_usage_tracker()
        cost = tracker.get_monthly_cost()
        return Decimal(str(cost))

    def get_daily_cap(self, db: Session) -> Optional[float]:
        """
        Get daily cost cap setting.

        Args:
            db: Database session

        Returns:
            Daily cap in USD, or None if no limit
        """
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == SETTING_DAILY_CAP
        ).first()

        if setting and setting.value:
            try:
                value = float(setting.value)
                return value if value > 0 else None
            except (ValueError, TypeError):
                logger.warning(f"Invalid daily cap value: {setting.value}")
                return None
        return None

    def get_monthly_cap(self, db: Session) -> Optional[float]:
        """
        Get monthly cost cap setting.

        Args:
            db: Database session

        Returns:
            Monthly cap in USD, or None if no limit
        """
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == SETTING_MONTHLY_CAP
        ).first()

        if setting and setting.value:
            try:
                value = float(setting.value)
                return value if value > 0 else None
            except (ValueError, TypeError):
                logger.warning(f"Invalid monthly cap value: {setting.value}")
                return None
        return None

    def set_daily_cap(self, db: Session, cap: Optional[float]) -> None:
        """
        Set daily cost cap.

        Args:
            db: Database session
            cap: Cap in USD, or None/0 for no limit
        """
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == SETTING_DAILY_CAP
        ).first()

        value = str(cap) if cap and cap > 0 else ""

        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=SETTING_DAILY_CAP, value=value)
            db.add(setting)

        db.commit()
        self._invalidate_cache()
        logger.info(f"Daily cost cap set to: {cap}")

    def set_monthly_cap(self, db: Session, cap: Optional[float]) -> None:
        """
        Set monthly cost cap.

        Args:
            db: Database session
            cap: Cap in USD, or None/0 for no limit
        """
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == SETTING_MONTHLY_CAP
        ).first()

        value = str(cap) if cap and cap > 0 else ""

        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=SETTING_MONTHLY_CAP, value=value)
            db.add(setting)

        db.commit()
        self._invalidate_cache()
        logger.info(f"Monthly cost cap set to: {cap}")

    def get_cap_status(self, db: Session, use_cache: bool = True) -> CostCapStatus:
        """
        Get complete cost cap status.

        Args:
            db: Database session
            use_cache: Whether to use cached status (default True)

        Returns:
            CostCapStatus with current costs, caps, and pause status
        """
        # Return cached status if valid
        if use_cache and self._is_cache_valid():
            return self._cache

        # Get current costs
        daily_cost = float(self.get_daily_cost(db))
        monthly_cost = float(self.get_monthly_cost(db))

        # Get caps
        daily_cap = self.get_daily_cap(db)
        monthly_cap = self.get_monthly_cap(db)

        # Calculate percentages
        daily_percent = 0.0
        if daily_cap and daily_cap > 0:
            daily_percent = min((daily_cost / daily_cap) * 100, 100.0)

        monthly_percent = 0.0
        if monthly_cap and monthly_cap > 0:
            monthly_percent = min((monthly_cost / monthly_cap) * 100, 100.0)

        # Determine pause status
        is_paused = False
        pause_reason: Optional[Literal["cost_cap_daily", "cost_cap_monthly"]] = None

        if daily_cap and daily_cost >= daily_cap:
            is_paused = True
            pause_reason = "cost_cap_daily"
        elif monthly_cap and monthly_cost >= monthly_cap:
            is_paused = True
            pause_reason = "cost_cap_monthly"

        status = CostCapStatus(
            daily_cost=round(daily_cost, 6),
            daily_cap=daily_cap,
            daily_percent=round(daily_percent, 1),
            monthly_cost=round(monthly_cost, 6),
            monthly_cap=monthly_cap,
            monthly_percent=round(monthly_percent, 1),
            is_paused=is_paused,
            pause_reason=pause_reason
        )

        # Update cache
        self._cache = status
        self._cache_timestamp = time.time()

        return status

    def is_within_daily_cap(self, db: Session) -> bool:
        """
        Check if current daily cost is within cap.

        Args:
            db: Database session

        Returns:
            True if within cap or no cap set, False if exceeded
        """
        status = self.get_cap_status(db)
        if status.daily_cap is None:
            return True
        return status.daily_cost < status.daily_cap

    def is_within_monthly_cap(self, db: Session) -> bool:
        """
        Check if current monthly cost is within cap.

        Args:
            db: Database session

        Returns:
            True if within cap or no cap set, False if exceeded
        """
        status = self.get_cap_status(db)
        if status.monthly_cap is None:
            return True
        return status.monthly_cost < status.monthly_cap

    def can_analyze(self, db: Session) -> tuple[bool, Optional[str]]:
        """
        Check if AI analysis is allowed based on cost caps.

        This is the main method called by event processor before AI analysis.

        Args:
            db: Database session

        Returns:
            Tuple of (can_analyze: bool, skip_reason: Optional[str])
            skip_reason is "cost_cap_daily" or "cost_cap_monthly" if paused
        """
        status = self.get_cap_status(db)

        if status.is_paused:
            logger.info(f"AI analysis paused due to {status.pause_reason}")
            return False, status.pause_reason

        return True, None

    def is_approaching_cap(self, db: Session, threshold: float = 80.0) -> tuple[bool, Optional[str]]:
        """
        Check if approaching cost cap threshold.

        Args:
            db: Database session
            threshold: Percentage threshold to trigger warning (default 80%)

        Returns:
            Tuple of (approaching: bool, which_cap: Optional[str])
            which_cap is "daily", "monthly", or None
        """
        status = self.get_cap_status(db)

        if status.daily_cap and status.daily_percent >= threshold:
            return True, "daily"

        if status.monthly_cap and status.monthly_percent >= threshold:
            return True, "monthly"

        return False, None


# Backward compatible thin getter (delegates to @singleton decorator)
def get_cost_cap_service() -> CostCapService:
    """
    Get the global CostCapService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer CostCapService() directly.
    """
    return CostCapService()


def reset_cost_cap_service() -> None:
    """Reset the global CostCapService instance (for testing)."""
    CostCapService._reset_instance()
