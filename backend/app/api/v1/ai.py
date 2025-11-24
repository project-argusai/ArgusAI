"""
AI Service API endpoints

Provides:
- GET /ai/usage - Usage statistics and cost tracking
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query
import logging

from app.schemas.ai import AIUsageStatsResponse
from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/usage", response_model=AIUsageStatsResponse)
async def get_ai_usage_stats(
    start_date: Optional[str] = Query(
        None,
        description="Start date filter (ISO 8601 format: YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None,
        description="End date filter (ISO 8601 format: YYYY-MM-DD)"
    )
):
    """
    Get AI usage statistics and cost tracking.

    Returns aggregated statistics including:
    - Total API calls (successful and failed)
    - Token usage
    - Cost estimates
    - Average response time
    - Per-provider breakdown

    Supports optional date range filtering.

    Example:
        GET /api/v1/ai/usage
        GET /api/v1/ai/usage?start_date=2025-11-01&end_date=2025-11-16
    """
    # Parse dates if provided
    start_datetime = datetime.fromisoformat(start_date) if start_date else None
    end_datetime = datetime.fromisoformat(end_date) if end_date else None

    # Get stats from AI service
    stats = ai_service.get_usage_stats(start_datetime, end_datetime)

    logger.info(
        f"AI usage stats requested: {stats['total_calls']} calls, "
        f"${stats['total_cost']:.4f} cost"
    )

    return AIUsageStatsResponse(**stats)
