"""
Summaries API endpoints for Activity Summaries (Story P4-4.1, P9-3.4)

Provides endpoints for:
- Generating activity summaries for time periods
- Retrieving daily summaries
- Caching generated summaries
- Summary feedback (Story P9-3.4)

AC Coverage:
- AC13: POST /api/v1/summaries/generate endpoint
- AC14: GET /api/v1/summaries/daily endpoint
- AC15: Validation errors (400 for invalid date ranges)
- AC16: Response schema with required fields
- AC-3.4.1-6: Summary feedback endpoints (Story P9-3.4)
"""
import json
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.activity_summary import ActivitySummary
from app.models.summary_feedback import SummaryFeedback
from app.models.event import Event
from app.services.summary_service import get_summary_service, SummaryService
from app.schemas.feedback import (
    SummaryFeedbackCreate,
    SummaryFeedbackUpdate,
    SummaryFeedbackResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/summaries", tags=["summaries"])


# Request/Response Models (AC16)

class SummaryGenerateRequest(BaseModel):
    """
    Request model for on-demand summary generation (Story P4-4.5).

    Accepts EITHER:
    - hours_back: Shorthand for "last N hours" (e.g., hours_back=3 for last 3 hours)
    - OR start_time + end_time: Explicit time range

    Both modes are mutually exclusive.
    """
    hours_back: Optional[int] = Field(
        default=None,
        ge=1,
        le=168,  # Max 1 week
        description="Generate summary for last N hours (1-168). Mutually exclusive with start_time/end_time."
    )
    start_time: Optional[datetime] = Field(
        default=None,
        description="Start of time period (ISO 8601). Required if hours_back not provided."
    )
    end_time: Optional[datetime] = Field(
        default=None,
        description="End of time period (ISO 8601). Required if hours_back not provided."
    )
    camera_ids: Optional[List[str]] = Field(
        default=None,
        description="List of camera UUIDs to include (null = all cameras)"
    )

    @model_validator(mode='after')
    def validate_time_params(self) -> 'SummaryGenerateRequest':
        """Validate that either hours_back OR start_time+end_time is provided, not both."""
        has_hours_back = self.hours_back is not None
        has_explicit_times = self.start_time is not None or self.end_time is not None

        if has_hours_back and has_explicit_times:
            raise ValueError(
                "Cannot specify both hours_back and start_time/end_time. Use one or the other."
            )

        if not has_hours_back and not has_explicit_times:
            raise ValueError(
                "Must provide either hours_back OR both start_time and end_time."
            )

        if not has_hours_back:
            # Explicit times mode - both must be provided
            if self.start_time is None or self.end_time is None:
                raise ValueError(
                    "When not using hours_back, both start_time and end_time are required."
                )

        return self


class SummaryStats(BaseModel):
    """Statistical breakdown of events in summary."""
    total_events: int = Field(description="Total number of events")
    by_type: Dict[str, int] = Field(default_factory=dict, description="Event counts by object type")
    by_camera: Dict[str, int] = Field(default_factory=dict, description="Event counts by camera")
    alerts_triggered: int = Field(default=0, description="Number of events that triggered alerts")
    doorbell_rings: int = Field(default=0, description="Number of doorbell ring events")


class SummaryResponse(BaseModel):
    """Response model for generated summary (AC16, Story P4-4.5)."""
    id: Optional[str] = Field(default=None, description="Summary UUID (for saved summaries)")
    summary_text: str = Field(description="Generated natural language summary")
    period_start: datetime = Field(description="Start of summarized period")
    period_end: datetime = Field(description="End of summarized period")
    event_count: int = Field(description="Number of events in summary")
    generated_at: datetime = Field(description="When the summary was generated")
    stats: Optional[SummaryStats] = Field(default=None, description="Event statistics breakdown")
    ai_cost: float = Field(default=0.0, description="Cost of AI generation (USD)")
    provider_used: Optional[str] = Field(default=None, description="AI provider used")
    camera_count: int = Field(default=0, description="Number of cameras with events")
    alert_count: int = Field(default=0, description="Number of alerts triggered")
    doorbell_count: int = Field(default=0, description="Number of doorbell ring events")
    person_count: int = Field(default=0, description="Number of person detections")
    vehicle_count: int = Field(default=0, description="Number of vehicle detections")


class DailySummaryResponse(SummaryResponse):
    """Response for daily summary endpoint."""
    date: str = Field(description="Date of summary (YYYY-MM-DD)")
    cached: bool = Field(default=False, description="Whether this was from cache")


class SummaryListResponse(BaseModel):
    """Response for listing summaries."""
    summaries: List[SummaryResponse] = Field(description="List of summaries")
    total: int = Field(description="Total number of summaries")


class RecentSummaryItem(BaseModel):
    """A single summary item for recent summaries endpoint (Story P4-4.4)."""
    id: str = Field(description="Summary UUID")
    date: str = Field(description="Date in ISO format (YYYY-MM-DD)")
    summary_text: str = Field(description="Generated summary text")
    event_count: int = Field(description="Number of events in summary")
    camera_count: int = Field(default=0, description="Number of cameras with events")
    alert_count: int = Field(default=0, description="Number of alerts triggered")
    doorbell_count: int = Field(default=0, description="Number of doorbell rings")
    person_count: int = Field(default=0, description="Number of person detections")
    vehicle_count: int = Field(default=0, description="Number of vehicle detections")
    generated_at: datetime = Field(description="When the summary was generated")


class RecentSummariesResponse(BaseModel):
    """Response for recent summaries endpoint (Story P4-4.4)."""
    summaries: List[RecentSummaryItem] = Field(description="List of recent summaries (today and yesterday)")


# Helper functions

def _get_event_stats_for_date(db: Session, target_date: date) -> dict:
    """
    Get event statistics for a specific date (Story P4-4.4).

    Queries the events table to calculate:
    - Total event count
    - Unique camera count
    - Alert count
    - Doorbell ring count
    - Person detection count
    - Vehicle detection count

    Args:
        db: Database session
        target_date: The date to get stats for

    Returns:
        Dict with stats
    """
    start_time = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_time = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)

    # Query events for the date
    events = db.query(Event).filter(
        Event.timestamp >= start_time,
        Event.timestamp < end_time
    ).all()

    # Calculate stats
    camera_ids = set()
    alert_count = 0
    doorbell_count = 0
    person_count = 0
    vehicle_count = 0

    for event in events:
        camera_ids.add(event.camera_id)

        if event.alert_triggered:
            alert_count += 1

        if event.is_doorbell_ring:
            doorbell_count += 1

        # Parse objects_detected for person/vehicle counts
        if event.objects_detected:
            try:
                objects = json.loads(event.objects_detected)
                for obj in objects:
                    obj_lower = obj.lower()
                    if 'person' in obj_lower or 'human' in obj_lower:
                        person_count += 1
                    elif 'vehicle' in obj_lower or 'car' in obj_lower or 'truck' in obj_lower:
                        vehicle_count += 1
            except (json.JSONDecodeError, TypeError):
                pass

    return {
        "event_count": len(events),
        "camera_count": len(camera_ids),
        "alert_count": alert_count,
        "doorbell_count": doorbell_count,
        "person_count": person_count,
        "vehicle_count": vehicle_count,
    }


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
    camera_ids: Optional[List[str]] = None,
    digest_type: Optional[str] = None
) -> ActivitySummary:
    """
    Save a generated summary to the database for caching.

    Args:
        db: Database session
        result: SummaryResult from SummaryService
        camera_ids: Optional list of camera IDs to filter
        digest_type: Type of digest ('daily', 'weekly', 'on_demand', etc.)

    Returns:
        Saved ActivitySummary model instance
    """
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
        digest_type=digest_type,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def _get_event_stats_for_range(db: Session, start_time: datetime, end_time: datetime) -> dict:
    """
    Get event statistics for a time range (Story P4-4.5).

    Queries the events table to calculate counts for a specific time range.

    Args:
        db: Database session
        start_time: Start of range (inclusive)
        end_time: End of range (exclusive)

    Returns:
        Dict with stats
    """
    # Query events for the range
    events = db.query(Event).filter(
        Event.timestamp >= start_time,
        Event.timestamp < end_time
    ).all()

    # Calculate stats
    camera_ids = set()
    alert_count = 0
    doorbell_count = 0
    person_count = 0
    vehicle_count = 0

    for event in events:
        camera_ids.add(event.camera_id)

        if event.alert_triggered:
            alert_count += 1

        if event.is_doorbell_ring:
            doorbell_count += 1

        # Parse objects_detected for person/vehicle counts
        if event.objects_detected:
            try:
                objects = json.loads(event.objects_detected)
                for obj in objects:
                    obj_lower = obj.lower()
                    if 'person' in obj_lower or 'human' in obj_lower:
                        person_count += 1
                    elif 'vehicle' in obj_lower or 'car' in obj_lower or 'truck' in obj_lower:
                        vehicle_count += 1
            except (json.JSONDecodeError, TypeError):
                pass

    return {
        "event_count": len(events),
        "camera_count": len(camera_ids),
        "alert_count": alert_count,
        "doorbell_count": doorbell_count,
        "person_count": person_count,
        "vehicle_count": vehicle_count,
    }


# Endpoints

@router.get("/recent", response_model=RecentSummariesResponse)
async def get_recent_summaries(
    db: Session = Depends(get_db),
):
    """
    Get recent summaries for dashboard display (Story P4-4.4).

    Returns today's and yesterday's activity summaries if they exist.
    Includes event statistics (counts by type) for each summary.

    AC10: GET /api/v1/summaries/recent returns today's and yesterday's summaries

    Returns:
        RecentSummariesResponse with list of recent summaries (may be empty)
    """
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    summaries = []

    for target_date in [today, yesterday]:
        # Calculate start/end times for the date
        start_time = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_time = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)

        # Query for existing summary (prefer daily digest, then any digest)
        summary = db.query(ActivitySummary).filter(
            ActivitySummary.period_start >= start_time,
            ActivitySummary.period_start < end_time,
            ActivitySummary.digest_type.isnot(None)
        ).order_by(ActivitySummary.generated_at.desc()).first()

        if summary:
            # Get event stats for the date
            stats = _get_event_stats_for_date(db, target_date)

            summaries.append(RecentSummaryItem(
                id=summary.id,
                date=target_date.isoformat(),
                summary_text=summary.summary_text,
                event_count=summary.event_count or stats["event_count"],
                camera_count=stats["camera_count"],
                alert_count=stats["alert_count"],
                doorbell_count=stats["doorbell_count"],
                person_count=stats["person_count"],
                vehicle_count=stats["vehicle_count"],
                generated_at=summary.generated_at,
            ))

    logger.info(
        f"Returning {len(summaries)} recent summaries",
        extra={
            "event_type": "recent_summaries_fetch",
            "summary_count": len(summaries),
            "dates": [s.date for s in summaries]
        }
    )

    return RecentSummariesResponse(summaries=summaries)


@router.post("/generate", response_model=SummaryResponse, status_code=201)
async def generate_summary(
    request: SummaryGenerateRequest,
    db: Session = Depends(get_db),
    summary_service: SummaryService = Depends(get_summary_service),
):
    """
    Generate an on-demand natural language summary for a time period (Story P4-4.5).

    Accepts EITHER:
    - hours_back: Shorthand for "last N hours" (e.g., hours_back=3 for last 3 hours)
    - OR start_time + end_time: Explicit time range in ISO 8601 format

    AC1: Accepts time range parameters
    AC2: Accepts hours_back shorthand
    AC3: Accepts start_datetime and end_datetime
    AC4: Returns summary with summary_text, event_count, time range
    AC5: Uses existing SummaryService.generate_summary()
    AC12: Saves to history with digest_type='on_demand'

    Args:
        request: Summary generation parameters (hours_back OR start_time+end_time)
        db: Database session
        summary_service: Summary service instance

    Returns:
        SummaryResponse with generated summary (201 Created)

    Raises:
        400: Invalid date range or parameter combination
        500: Summary generation failed
    """
    # Calculate time range based on request type
    if request.hours_back is not None:
        # hours_back mode - calculate range from now
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=request.hours_back)
    else:
        # Explicit times mode
        start_time = request.start_time
        end_time = request.end_time

    # Validate date range
    _validate_date_range(start_time, end_time)

    logger.info(
        "On-demand summary generation request",
        extra={
            "event_type": "summary_generate_on_demand",
            "hours_back": request.hours_back,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "camera_ids": request.camera_ids
        }
    )

    # For on-demand summaries, we skip cache and always generate fresh
    # This ensures users get the most up-to-date summary for their requested time range

    # Generate new summary
    result = await summary_service.generate_summary(
        db=db,
        start_time=start_time,
        end_time=end_time,
        camera_ids=request.camera_ids
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Summary generation failed: {result.error}"
        )

    # Save to database with digest_type='on_demand' (AC12)
    saved_summary = _save_summary_to_db(db, result, request.camera_ids, digest_type='on_demand')

    # Get event stats for the time range
    event_stats = _get_event_stats_for_range(db, start_time, end_time)

    # Build stats response
    stats = SummaryStats(
        total_events=result.stats.total_events,
        by_type=result.stats.by_type,
        by_camera=result.stats.by_camera,
        alerts_triggered=result.stats.alerts_triggered,
        doorbell_rings=result.stats.doorbell_rings,
    )

    return SummaryResponse(
        id=saved_summary.id,
        summary_text=result.summary_text,
        period_start=result.period_start,
        period_end=result.period_end,
        event_count=result.event_count,
        generated_at=result.generated_at,
        stats=stats,
        ai_cost=float(result.ai_cost),
        provider_used=result.provider_used,
        camera_count=event_stats["camera_count"],
        alert_count=event_stats["alert_count"],
        doorbell_count=event_stats["doorbell_count"],
        person_count=event_stats["person_count"],
        vehicle_count=event_stats["vehicle_count"],
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


# ============================================================================
# Story P9-3.4: Summary Feedback Endpoints
# ============================================================================

@router.post("/{summary_id}/feedback", response_model=SummaryFeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_summary_feedback(
    summary_id: str,
    feedback_data: SummaryFeedbackCreate,
    db: Session = Depends(get_db)
):
    """
    Create feedback for a summary (Story P9-3.4).

    Allows users to rate summaries as positive/negative and optionally
    provide correction text.

    AC-3.4.2: Given I click thumbs up, when submitted, then positive feedback stored
    AC-3.4.5: Given I submit thumbs down with text, when stored, then correction_text saved
    AC-3.4.6: Given I submit feedback, when complete, then brief toast "Thanks for the feedback!"

    Args:
        summary_id: Summary UUID
        feedback_data: Rating and optional correction text
        db: Database session

    Returns:
        Created feedback with ID and timestamps

    Raises:
        404: Summary not found
        409: Feedback already exists for this summary
        500: Database error
    """
    try:
        # Verify summary exists
        summary = db.query(ActivitySummary).filter(ActivitySummary.id == summary_id).first()
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Summary {summary_id} not found"
            )

        # Check if feedback already exists
        existing = db.query(SummaryFeedback).filter(SummaryFeedback.summary_id == summary_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Feedback already exists for this summary. Use PUT to update."
            )

        # Create feedback
        feedback = SummaryFeedback(
            summary_id=summary_id,
            rating=feedback_data.rating,
            correction_text=feedback_data.correction_text
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Created feedback for summary {summary_id}: rating={feedback_data.rating}",
            extra={"summary_id": summary_id, "rating": feedback_data.rating}
        )

        return SummaryFeedbackResponse.model_validate(feedback)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create feedback for summary {summary_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create feedback"
        )


@router.get("/{summary_id}/feedback", response_model=SummaryFeedbackResponse)
async def get_summary_feedback(
    summary_id: str,
    db: Session = Depends(get_db)
):
    """
    Get feedback for a summary (Story P9-3.4).

    AC-3.4.3: Given I click thumbs up, when viewing, then button shows selected state

    Args:
        summary_id: Summary UUID
        db: Database session

    Returns:
        Feedback data if exists

    Raises:
        404: Summary or feedback not found
    """
    try:
        # Verify summary exists
        summary = db.query(ActivitySummary).filter(ActivitySummary.id == summary_id).first()
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Summary {summary_id} not found"
            )

        feedback = db.query(SummaryFeedback).filter(SummaryFeedback.summary_id == summary_id).first()
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No feedback found for summary {summary_id}"
            )

        return SummaryFeedbackResponse.model_validate(feedback)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get feedback for summary {summary_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get feedback"
        )


@router.put("/{summary_id}/feedback", response_model=SummaryFeedbackResponse)
async def update_summary_feedback(
    summary_id: str,
    feedback_data: SummaryFeedbackUpdate,
    db: Session = Depends(get_db)
):
    """
    Update existing feedback for a summary (Story P9-3.4).

    Args:
        summary_id: Summary UUID
        feedback_data: Updated rating and/or correction text
        db: Database session

    Returns:
        Updated feedback

    Raises:
        404: Summary or feedback not found
        500: Database error
    """
    try:
        # Verify summary exists
        summary = db.query(ActivitySummary).filter(ActivitySummary.id == summary_id).first()
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Summary {summary_id} not found"
            )

        feedback = db.query(SummaryFeedback).filter(SummaryFeedback.summary_id == summary_id).first()
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No feedback found for summary {summary_id}"
            )

        # Update fields if provided
        if feedback_data.rating is not None:
            feedback.rating = feedback_data.rating
        if feedback_data.correction_text is not None:
            feedback.correction_text = feedback_data.correction_text

        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Updated feedback for summary {summary_id}",
            extra={"summary_id": summary_id}
        )

        return SummaryFeedbackResponse.model_validate(feedback)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update feedback for summary {summary_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update feedback"
        )


@router.delete("/{summary_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def delete_summary_feedback(
    summary_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete feedback for a summary (Story P9-3.4).

    Args:
        summary_id: Summary UUID
        db: Database session

    Raises:
        404: Summary or feedback not found
        500: Database error
    """
    try:
        # Verify summary exists
        summary = db.query(ActivitySummary).filter(ActivitySummary.id == summary_id).first()
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Summary {summary_id} not found"
            )

        feedback = db.query(SummaryFeedback).filter(SummaryFeedback.summary_id == summary_id).first()
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No feedback found for summary {summary_id}"
            )

        db.delete(feedback)
        db.commit()

        logger.info(
            f"Deleted feedback for summary {summary_id}",
            extra={"summary_id": summary_id}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete feedback for summary {summary_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete feedback"
        )
