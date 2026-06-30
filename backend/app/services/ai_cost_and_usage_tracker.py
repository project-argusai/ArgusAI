"""
AI Cost and Usage Tracker Service

Extracted as part of Phase B (#447) to separate cost tracking and usage recording
from analysis orchestration logic in AIService and VisionAnalysisOrchestrator.

# Migrated to @singleton as part of #450 (Lightweight DI Container).

Responsibilities:
- Record usage after every AI call (tokens, cost, provider, mode, camera, etc.)
- Query usage statistics (totals, breakdowns, time ranges)
- Support cost cap enforcement hooks
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.decorators import singleton
from app.core.database import get_db_session
from app.models.ai_usage import AIUsage

logger = logging.getLogger(__name__)


@singleton
class AICostAndUsageTracker:
    """
    Dedicated service for tracking and querying AI API usage and costs.

    This service owns all persistence and querying of AIUsage records.
    Cost *calculation* is delegated to CostTracker when needed.
    """

    def __init__(self):
        pass

    def record_usage(
        self,
        provider: str,
        success: bool,
        tokens_used: int = 0,
        response_time_ms: int = 0,
        cost_estimate: float = 0.0,
        error: Optional[str] = None,
        analysis_mode: Optional[str] = None,
        is_estimated: bool = False,
        image_count: Optional[int] = None,
    ) -> None:
        """
        Record a single AI API usage event.

        This is the canonical place where usage is persisted.
        """
        try:
            with get_db_session() as db:
                usage_record = AIUsage(
                    timestamp=datetime.now(timezone.utc),
                    provider=provider,
                    success=success,
                    tokens_used=tokens_used,
                    response_time_ms=response_time_ms,
                    cost_estimate=cost_estimate,
                    error=error,
                    analysis_mode=analysis_mode,
                    is_estimated=is_estimated,
                    image_count=image_count,
                )
                db.add(usage_record)
                db.commit()

            logger.debug(
                f"Recorded usage: provider={provider}, success={success}, "
                f"tokens={tokens_used}, cost=${cost_estimate:.6f}, mode={analysis_mode}"
            )

            # === Cost cap enforcement hook (Phase B #447) ===
            # Right after an expensive call, invalidate CostCapService cache
            # so the next `can_analyze()` call (in EventProcessor) sees the new total
            # and can pause AI automatically if a cap was crossed.
            try:
                from app.services.cost_cap_service import get_cost_cap_service
                cost_cap = get_cost_cap_service()
                cost_cap._invalidate_cache()
            except Exception as e:
                logger.error(f"Failed to invalidate cost cap cache after record: {e}")

        except Exception as e:
            logger.error(f"Failed to record AI usage: {e}", exc_info=True)

    def get_usage_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Return aggregated usage statistics.

        Returns totals and per-provider breakdowns.
        """
        try:
            with get_db_session() as db:
                query = db.query(AIUsage)

                if start_date:
                    query = query.filter(AIUsage.timestamp >= start_date)
                if end_date:
                    query = query.filter(AIUsage.timestamp <= end_date)

                records = query.all()

                if not records:
                    return self._empty_stats()

                total_calls = len(records)
                successful = sum(1 for r in records if r.success)
                total_tokens = sum(r.tokens_used for r in records)
                total_cost = sum(r.cost_estimate for r in records)
                avg_response_time = (
                    sum(r.response_time_ms for r in records) / total_calls
                    if total_calls > 0 else 0
                )

                # Per-provider breakdown
                provider_breakdown: Dict[str, Dict[str, Any]] = {}
                for r in records:
                    p = r.provider
                    if p not in provider_breakdown:
                        provider_breakdown[p] = {
                            "calls": 0,
                            "successful": 0,
                            "tokens": 0,
                            "cost": 0.0,
                        }
                    provider_breakdown[p]["calls"] += 1
                    if r.success:
                        provider_breakdown[p]["successful"] += 1
                    provider_breakdown[p]["tokens"] += r.tokens_used
                    provider_breakdown[p]["cost"] += r.cost_estimate

                return {
                    "total_calls": total_calls,
                    "successful_calls": successful,
                    "failed_calls": total_calls - successful,
                    "total_tokens": total_tokens,
                    "total_cost": round(total_cost, 6),
                    "avg_response_time_ms": round(avg_response_time, 1),
                    "provider_breakdown": provider_breakdown,
                }
        except Exception as e:
            logger.error(f"Failed to query usage stats: {e}", exc_info=True)
            return self._empty_stats()

    def _empty_stats(self) -> Dict[str, Any]:
        return {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "avg_response_time_ms": 0,
            "provider_breakdown": {},
        }

    # =====================================================================
    # Richer query methods for CostCapService and dashboards (Phase B #447)
    # =====================================================================

    def get_daily_cost(self) -> float:
        """Total successful AI cost for today (UTC)."""
        today = datetime.now(timezone.utc).date()
        try:
            with get_db_session() as db:
                result = db.query(func.sum(AIUsage.cost_estimate)).filter(
                    func.date(AIUsage.timestamp) == today,
                    AIUsage.success == True
                ).scalar()
                return float(result or 0.0)
        except Exception as e:
            logger.error(f"Failed to get daily cost: {e}")
            return 0.0

    def get_monthly_cost(self) -> float:
        """Total successful AI cost for current month (UTC)."""
        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        try:
            with get_db_session() as db:
                result = db.query(func.sum(AIUsage.cost_estimate)).filter(
                    AIUsage.timestamp >= start_of_month,
                    AIUsage.success == True
                ).scalar()
                return float(result or 0.0)
        except Exception as e:
            logger.error(f"Failed to get monthly cost: {e}")
            return 0.0

    def get_current_period_cost(self, period: str = "daily") -> float:
        """Convenience method: 'daily' or 'monthly'."""
        if period == "monthly":
            return self.get_monthly_cost()
        return self.get_daily_cost()

    def get_usage_by_camera(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Return usage broken down by camera_id."""
        # This can be expanded later. For now we return a basic structure.
        # Full implementation would require storing camera_id on AIUsage (future improvement).
        return {}  # Placeholder — camera-level breakdown not yet persisted on AIUsage

    def get_provider_breakdown(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Return detailed per-provider breakdown (calls, tokens, cost)."""
        stats = self.get_usage_stats(start_date, end_date)
        return stats.get("provider_breakdown", {})

    def get_daily_breakdown(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[Dict[str, Any]]:
        """
        Return daily aggregates for charts (date, calls, tokens, cost, success_rate).
        Useful for cost trend dashboards.
        """
        try:
            with get_db_session() as db:
                query = db.query(
                    func.date(AIUsage.timestamp).label("date"),
                    func.count(AIUsage.id).label("calls"),
                    func.sum(AIUsage.tokens_used).label("tokens"),
                    func.sum(AIUsage.cost_estimate).label("cost"),
                    func.sum(case((AIUsage.success == True, 1), else_=0)).label("successful"),
                )

                if start_date:
                    query = query.filter(AIUsage.timestamp >= start_date)
                if end_date:
                    query = query.filter(AIUsage.timestamp <= end_date)

                rows = query.group_by(func.date(AIUsage.timestamp)).order_by(func.date(AIUsage.timestamp)).all()

                return [
                    {
                        "date": str(row.date),
                        "calls": row.calls,
                        "tokens": row.tokens or 0,
                        "cost": round(float(row.cost or 0), 6),
                        "success_rate": round((row.successful or 0) / row.calls * 100, 1) if row.calls else 0,
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to get daily breakdown: {e}")
            return []

    def get_top_expensive_cameras(self, limit: int = 10, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> list[Dict[str, Any]]:
        """
        Top cameras by cost.
        Note: Requires camera_id on AIUsage records (not yet stored in current schema).
        Returns empty list for now.
        """
        # TODO: Once camera_id is stored on AIUsage (or joined via events), implement real query.
        logger.debug("get_top_expensive_cameras: camera_id not yet on AIUsage model — returning empty")
        return []

    def get_usage_summary_for_period(self, period: str = "daily") -> Dict[str, Any]:
        """Convenience for dashboards: current daily or monthly summary."""
        if period == "monthly":
            return {
                "period": "monthly",
                "total_cost": self.get_monthly_cost(),
                "breakdown": self.get_provider_breakdown(),
            }
        return {
            "period": "daily",
            "total_cost": self.get_daily_cost(),
            "breakdown": self.get_provider_breakdown(),
        }

    # ------------------------------------------------------------------
    # Even more granular stats (Phase B continuation)
    # ------------------------------------------------------------------

    def get_hourly_breakdown(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[Dict[str, Any]]:
        """
        Hourly aggregates for fine-grained charts (e.g. intra-day cost spikes).
        Groups by hour.
        """
        try:
            with get_db_session() as db:
                query = db.query(
                    func.date_trunc('hour', AIUsage.timestamp).label("hour"),
                    func.count(AIUsage.id).label("calls"),
                    func.sum(AIUsage.tokens_used).label("tokens"),
                    func.sum(AIUsage.cost_estimate).label("cost"),
                )

                if start_date:
                    query = query.filter(AIUsage.timestamp >= start_date)
                if end_date:
                    query = query.filter(AIUsage.timestamp <= end_date)

                rows = (
                    query.group_by(func.date_trunc('hour', AIUsage.timestamp))
                    .order_by(func.date_trunc('hour', AIUsage.timestamp))
                    .all()
                )

                return [
                    {
                        "hour": row.hour.isoformat(),
                        "calls": row.calls,
                        "tokens": row.tokens or 0,
                        "cost": round(float(row.cost or 0), 6),
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to get hourly breakdown: {e}")
            return []

    def get_top_cameras_by_cost(
        self, limit: int = 10, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[Dict[str, Any]]:
        """
        Top N cameras by total cost.

        NOTE: Requires `camera_id` column on AIUsage (not present in current schema).
        Returns empty list with a clear message for now.
        When camera_id is added to AIUsage (and passed in record_usage),
        this method will become fully functional.
        """
        logger.info(
            "get_top_cameras_by_cost called — camera_id is not yet stored on AIUsage. "
            "Returning empty list. Add camera_id to the model + pass it from callers to enable this."
        )
        return []

    def get_usage_trend(
        self, granularity: str = "daily", start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[Dict[str, Any]]:
        """Unified trend method (daily or hourly) for dashboards."""
        if granularity == "hourly":
            return self.get_hourly_breakdown(start_date, end_date)
        return self.get_daily_breakdown(start_date, end_date)


# Backward compatible thin getter (delegates to @singleton decorator)
def get_ai_cost_and_usage_tracker() -> "AICostAndUsageTracker":
    """
    Get the global AICostAndUsageTracker instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer AICostAndUsageTracker() directly
          or container.ai_cost_tracker.
    """
    return AICostAndUsageTracker()


def reset_ai_cost_and_usage_tracker() -> None:
    """Reset the global AICostAndUsageTracker instance (for testing)."""
    AICostAndUsageTracker._reset_instance()
