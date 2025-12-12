"""
Summaries API endpoints for Activity Summaries (Story P4-4.1)

Provides endpoints for:
- Generating activity summaries for time periods
- Retrieving daily summaries
- Caching generated summaries

AC Coverage:
- AC13: POST /api/v1/summaries/generate endpoint
- AC14: GET /api/v1/summaries/daily endpoint
- AC15: Validation errors (400 for invalid date ranges)
- AC16: Response schema with required fields
"""
import json
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.activity_summary import ActivitySummary
from app.services.summary_service import get_summary_service, SummaryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/summaries", tags=["summaries"])


# Request/Response Models (AC16)

class SummaryGenerateRequest(BaseModel):
    """Request model for summary generation."""
    start_time: datetime = Field(description="Start of time period (ISO 8601)")
    end_time: datetime = Field(description="End of time period (ISO 8601)")
    camera_ids: Optional[List[str]] = Field(
        default=None,
        description="List of camera UUIDs to include (null = all cameras)"
    )

    @field_validator('end_time')
    @classmethod
    def validate_end_time(cls, v: datetime, info) -> datetime:
        """Validate end_time is after start_time and not too far in future."""
        # Note: start_time may not be available yet in field_validator
        # We'll do cross-field validation in the endpoint
        return v


class SummaryStats(BaseModel):
    """Statistical breakdown of events in summary."""
    total_events: int = Field(description="Total number of events")
    by_type: Dict[str, int] = Field(default_factory=dict, description="Event counts by object type")
    by_camera: Dict[str, int] = Field(default_factory=dict, description="Event counts by camera")
    alerts_triggered: int = Field(default=0, description="Number of events that triggered alerts")
    doorbell_rings: int = Field(default=0, description="Number of doorbell ring events")


class SummaryResponse(BaseModel):
    """Response model for generated summary (AC16)."""
    summary_text: str = Field(description="Generated natural language summary")
    period_start: datetime = Field(description="Start of summarized period")
    period_end: datetime = Field(description="End of summarized period")
    event_count: int = Field(description="Number of events in summary")
    generated_at: datetime = Field(description="When the summary was generated")
    stats: Optional[SummaryStats] = Field(default=None, description="Event statistics breakdown")
    ai_cost: float = Field(default=0.0, description="Cost of AI generation (USD)")
    provider_used: Optional[str] = Field(default=None, description="AI provider used")


class DailySummaryResponse(SummaryResponse):
    """Response for daily summary endpoint."""
    date: str = Field(description="Date of summary (YYYY-MM-DD)")
    cached: bool = Field(default=False, description="Whether this was from cache")


class SummaryListResponse(BaseModel):
    """Response for listing summaries."""
    summaries: List[SummaryResponse] = Field(description="List of summaries")
    total: int = Field(description="Total number of summaries")


# Helper functions

def _validate_date_range(start_time: datetime, end_time: datetime) -> None:
    """
    Validate date range for summary generation (AC15).

    Raises:
        HTTPException: 400 if validation fails
    """
    # End time must be after start time
    if end_time <= start_time:
        raise HTTPException(
            status_code=400,
            detail="end_time must be after start_time"
        )

    # Don't allow future dates more than 1 day ahead
    now = datetime.now(timezone.utc)
    max_future = now + timedelta(days=1)
    if end_time > max_future:
        raise HTTPException(
            status_code=400,
            detail="end_time cannot be more than 1 day in the future"
        )

    # Don't allow unreasonably long time ranges (max 90 days)
    max_range = timedelta(days=90)
    if end_time - start_time > max_range:
        raise HTTPException(
            status_code=400,
            detail="Time range cannot exceed 90 days"
        )


def _find_cached_summary(
    db: Session,
    start_time: datetime,
    end_time: datetime,
    camera_ids: Optional[List[str]] = None
) -> Optional[ActivitySummary]:
    """Find a cached summary matching the criteria."""
    # For exact match, we need same time range within 1 minute tolerance
    tolerance = timedelta(minutes=1)

    query = db.query(ActivitySummary).filter(
        ActivitySummary.period_start >= start_time - tolerance,
        ActivitySummary.period_start <= start_time + tolerance,
        ActivitySummary.period_end >= end_time - tolerance,
        ActivitySummary.period_end <= end_time + tolerance,
    )

    # Check camera_ids match (null = all cameras)
    if camera_ids:
        # Need to match JSON array
        camera_ids_json = json.dumps(sorted(camera_ids))
        query = query.filter(ActivitySummary.camera_ids == camera_ids_json)
    else:
        query = query.filter(ActivitySummary.camera_ids.is_(None))

    # Get most recent
    return query.order_by(ActivitySummary.generated_at.desc()).first()


def _save_summary_to_db(
    db: Session,
    result,
    camera_ids: Optional[List[str]] = None
) -> ActivitySummary:
    """Save a generated summary to the database for caching."""
    summary = ActivitySummary(
        summary_text=result.summary_text,
        period_start=result.period_start,
        period_end=result.period_end,
        event_count=result.event_count,
        camera_ids=json.dumps(sorted(camera_ids)) if camera_ids else None,
        generated_at=result.generated_at,
        ai_cost=float(result.ai_cost),
        provider_used=result.provider_used,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


# Endpoints

@router.post("/generate", response_model=SummaryResponse)
async def generate_summary(
    request: SummaryGenerateRequest,
    db: Session = Depends(get_db),
    summary_service: SummaryService = Depends(get_summary_service),
):
    """
    Generate a natural language summary for a time period.

    AC13: POST /api/v1/summaries/generate accepts time_period params and returns summary

    Args:
        request: Summary generation parameters
        db: Database session
        summary_service: Summary service instance

    Returns:
        SummaryResponse with generated summary

    Raises:
        400: Invalid date range (AC15)
        500: Summary generation failed
    """
    # Validate date range (AC15)
    _validate_date_range(request.start_time, request.end_time)

    logger.info(
        "Summary generation request",
        extra={
            "event_type": "summary_generate_request",
            "start_time": request.start_time.isoformat(),
            "end_time": request.end_time.isoformat(),
            "camera_ids": request.camera_ids
        }
    )

    # Check for cached summary
    cached = _find_cached_summary(db, request.start_time, request.end_time, request.camera_ids)
    if cached:
        logger.info(
            "Returning cached summary",
            extra={"event_type": "summary_cache_hit", "summary_id": cached.id}
        )
        return SummaryResponse(
            summary_text=cached.summary_text,
            period_start=cached.period_start,
            period_end=cached.period_end,
            event_count=cached.event_count,
            generated_at=cached.generated_at,
            stats=None,  # Stats not stored in cache
            ai_cost=cached.ai_cost,
            provider_used=cached.provider_used,
        )

    # Generate new summary
    result = await summary_service.generate_summary(
        db=db,
        start_time=request.start_time,
        end_time=request.end_time,
        camera_ids=request.camera_ids
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Summary generation failed: {result.error}"
        )

    # Save to database for caching
    _save_summary_to_db(db, result, request.camera_ids)

    # Build stats response
    stats = SummaryStats(
        total_events=result.stats.total_events,
        by_type=result.stats.by_type,
        by_camera=result.stats.by_camera,
        alerts_triggered=result.stats.alerts_triggered,
        doorbell_rings=result.stats.doorbell_rings,
    )

    return SummaryResponse(
        summary_text=result.summary_text,
        period_start=result.period_start,
        period_end=result.period_end,
        event_count=result.event_count,
        generated_at=result.generated_at,
        stats=stats,
        ai_cost=float(result.ai_cost),
        provider_used=result.provider_used,
    )


@router.get("/daily", response_model=DailySummaryResponse)
async def get_daily_summary(
    date: str = Query(..., description="Date to summarize (YYYY-MM-DD format)"),
    camera_ids: Optional[str] = Query(None, description="Comma-separated camera UUIDs"),
    db: Session = Depends(get_db),
    summary_service: SummaryService = Depends(get_summary_service),
):
    """
    Get or generate a summary for a specific day.

    AC14: GET /api/v1/summaries/daily?date=YYYY-MM-DD returns summary for specific day

    This endpoint returns a cached summary if one exists for the date,
    otherwise generates a new one.

    Args:
        date: Date string in YYYY-MM-DD format
        camera_ids: Optional comma-separated camera UUIDs
        db: Database session
        summary_service: Summary service instance

    Returns:
        DailySummaryResponse with summary for the day

    Raises:
        400: Invalid date format or future date (AC15)
        500: Summary generation failed
    """
    # Parse date
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

    # Don't allow future dates more than 1 day ahead (AC15)
    today = datetime.now(timezone.utc).date()
    if target_date > today + timedelta(days=1):
        raise HTTPException(
            status_code=400,
            detail="Cannot generate summary for dates more than 1 day in the future"
        )

    # Calculate midnight-to-midnight range in UTC
    start_time = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_time = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    # Parse camera_ids if provided
    camera_id_list = None
    if camera_ids:
        camera_id_list = [cid.strip() for cid in camera_ids.split(",") if cid.strip()]

    logger.info(
        "Daily summary request",
        extra={
            "event_type": "summary_daily_request",
            "date": date,
            "camera_ids": camera_id_list
        }
    )

    # Check for cached summary
    cached = _find_cached_summary(db, start_time, end_time, camera_id_list)
    if cached:
        logger.info(
            "Returning cached daily summary",
            extra={"event_type": "summary_daily_cache_hit", "summary_id": cached.id}
        )
        return DailySummaryResponse(
            summary_text=cached.summary_text,
            period_start=cached.period_start,
            period_end=cached.period_end,
            event_count=cached.event_count,
            generated_at=cached.generated_at,
            stats=None,
            ai_cost=cached.ai_cost,
            provider_used=cached.provider_used,
            date=date,
            cached=True,
        )

    # Generate new summary
    result = await summary_service.generate_summary(
        db=db,
        start_time=start_time,
        end_time=end_time,
        camera_ids=camera_id_list
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Summary generation failed: {result.error}"
        )

    # Save to database for caching
    _save_summary_to_db(db, result, camera_id_list)

    # Build stats response
    stats = SummaryStats(
        total_events=result.stats.total_events,
        by_type=result.stats.by_type,
        by_camera=result.stats.by_camera,
        alerts_triggered=result.stats.alerts_triggered,
        doorbell_rings=result.stats.doorbell_rings,
    )

    return DailySummaryResponse(
        summary_text=result.summary_text,
        period_start=result.period_start,
        period_end=result.period_end,
        event_count=result.event_count,
        generated_at=result.generated_at,
        stats=stats,
        ai_cost=float(result.ai_cost),
        provider_used=result.provider_used,
        date=date,
        cached=False,
    )


@router.get("", response_model=SummaryListResponse)
async def list_summaries(
    limit: int = Query(20, ge=1, le=100, description="Number of summaries to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """
    List generated summaries.

    Returns recent summaries ordered by generation time.

    Args:
        limit: Maximum number of summaries to return
        offset: Pagination offset
        db: Database session

    Returns:
        SummaryListResponse with list of summaries
    """
    # Count total
    total = db.query(ActivitySummary).count()

    # Get summaries
    summaries = db.query(ActivitySummary)\
        .order_by(ActivitySummary.generated_at.desc())\
        .offset(offset)\
        .limit(limit)\
        .all()

    return SummaryListResponse(
        summaries=[
            SummaryResponse(
                summary_text=s.summary_text,
                period_start=s.period_start,
                period_end=s.period_end,
                event_count=s.event_count,
                generated_at=s.generated_at,
                stats=None,
                ai_cost=s.ai_cost,
                provider_used=s.provider_used,
            )
            for s in summaries
        ],
        total=total,
    )


@router.get("/{summary_id}", response_model=SummaryResponse)
async def get_summary(
    summary_id: str,
    db: Session = Depends(get_db),
):
    """
    Get a specific summary by ID.

    Args:
        summary_id: Summary UUID
        db: Database session

    Returns:
        SummaryResponse

    Raises:
        404: Summary not found
    """
    summary = db.query(ActivitySummary).filter(ActivitySummary.id == summary_id).first()

    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    return SummaryResponse(
        summary_text=summary.summary_text,
        period_start=summary.period_start,
        period_end=summary.period_end,
        event_count=summary.event_count,
        generated_at=summary.generated_at,
        stats=None,
        ai_cost=summary.ai_cost,
        provider_used=summary.provider_used,
    )
