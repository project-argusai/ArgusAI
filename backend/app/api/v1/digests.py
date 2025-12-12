"""
Digests API endpoints for Daily Digest Scheduler (Story P4-4.2)

Provides endpoints for:
- Triggering manual digest generation
- Getting scheduler status
- Listing generated digests

AC Coverage:
- AC10: POST /api/v1/digests/trigger endpoint
- AC11: GET /api/v1/digests/status endpoint
"""
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.activity_summary import ActivitySummary
from app.services.digest_scheduler import get_digest_scheduler, DigestStatus

logger = logging.getLogger(__name__)


def _parse_delivery_status(delivery_status_json: Optional[str]) -> Optional[dict]:
    """Parse delivery_status JSON string to dict."""
    if not delivery_status_json:
        return None
    try:
        import json
        return json.loads(delivery_status_json)
    except (json.JSONDecodeError, TypeError):
        return None


def _digest_to_response(digest: ActivitySummary) -> "DigestResponse":
    """Convert ActivitySummary to DigestResponse."""
    delivery_status = None
    parsed = _parse_delivery_status(digest.delivery_status)
    if parsed:
        delivery_status = DeliveryStatusResponse(
            success=parsed.get("success", False),
            channels_attempted=parsed.get("channels_attempted", []),
            channels_succeeded=parsed.get("channels_succeeded", []),
            errors=parsed.get("errors", {}),
            delivery_time_ms=parsed.get("delivery_time_ms", 0)
        )

    return DigestResponse(
        id=digest.id,
        summary_text=digest.summary_text,
        period_start=digest.period_start,
        period_end=digest.period_end,
        event_count=digest.event_count,
        generated_at=digest.generated_at,
        digest_type=digest.digest_type,
        ai_cost=digest.ai_cost,
        provider_used=digest.provider_used,
        delivery_status=delivery_status
    )

router = APIRouter(prefix="/digests", tags=["digests"])


# Request/Response Models

class DigestTriggerRequest(BaseModel):
    """Request model for triggering digest generation."""
    date: Optional[str] = Field(
        default=None,
        description="Date to generate digest for (YYYY-MM-DD). Defaults to yesterday."
    )


class DeliveryStatusResponse(BaseModel):
    """Delivery status for a digest."""
    success: bool = Field(description="Whether delivery was successful")
    channels_attempted: List[str] = Field(default_factory=list, description="Channels attempted")
    channels_succeeded: List[str] = Field(default_factory=list, description="Channels that succeeded")
    errors: dict = Field(default_factory=dict, description="Errors per channel")
    delivery_time_ms: int = Field(default=0, description="Delivery time in milliseconds")


class DigestResponse(BaseModel):
    """Response model for a digest."""
    id: str = Field(description="Digest UUID")
    summary_text: str = Field(description="Generated summary text")
    period_start: datetime = Field(description="Start of period")
    period_end: datetime = Field(description="End of period")
    event_count: int = Field(description="Number of events")
    generated_at: datetime = Field(description="When generated")
    digest_type: Optional[str] = Field(description="Type of digest")
    ai_cost: float = Field(default=0.0, description="AI generation cost")
    provider_used: Optional[str] = Field(default=None, description="AI provider used")
    delivery_status: Optional[DeliveryStatusResponse] = Field(default=None, description="Delivery status")


class DigestTriggerResponse(BaseModel):
    """Response for digest trigger endpoint."""
    message: str = Field(description="Status message")
    digest: Optional[DigestResponse] = Field(
        default=None,
        description="Generated digest if successful"
    )
    skipped: bool = Field(default=False, description="Whether generation was skipped")


class DigestStatusResponse(BaseModel):
    """Response for digest status endpoint."""
    enabled: bool = Field(description="Whether scheduler is enabled")
    schedule_time: str = Field(description="Scheduled time (HH:MM)")
    last_run: Optional[datetime] = Field(description="Last execution time")
    last_status: str = Field(description="Status of last run")
    last_error: Optional[str] = Field(description="Error from last run if any")
    next_run: Optional[datetime] = Field(description="Next scheduled run time")


class DigestListResponse(BaseModel):
    """Response for listing digests."""
    digests: List[DigestResponse] = Field(description="List of digests")
    total: int = Field(description="Total number of digests")


# Endpoints

@router.post("/trigger", response_model=DigestTriggerResponse)
async def trigger_digest(
    request: Optional[DigestTriggerRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Trigger immediate digest generation.

    AC10: POST /api/v1/digests/trigger forces immediate digest generation

    Args:
        request: Optional request with target date
        db: Database session

    Returns:
        DigestTriggerResponse with generated digest or skip status
    """
    # Parse target date
    target_date = None
    if request and request.date:
        try:
            target_date = datetime.strptime(request.date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD"
            )

        # Don't allow future dates
        today = datetime.now(timezone.utc).date()
        if target_date > today:
            raise HTTPException(
                status_code=400,
                detail="Cannot generate digest for future dates"
            )

    # Default to yesterday
    if target_date is None:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    logger.info(
        f"Manual digest trigger for {target_date}",
        extra={
            "event_type": "digest_manual_trigger",
            "target_date": target_date.isoformat()
        }
    )

    # Run digest generation
    scheduler = get_digest_scheduler()

    try:
        result = await scheduler.run_scheduled_digest(target_date=target_date)

        if result is None:
            # Digest was skipped (already exists)
            return DigestTriggerResponse(
                message=f"Digest for {target_date} already exists, skipped generation",
                digest=None,
                skipped=True
            )

        # Find the created digest in database
        digest = db.query(ActivitySummary).filter(
            ActivitySummary.digest_type == 'daily',
            ActivitySummary.period_start >= datetime.combine(target_date, datetime.min.time()),
            ActivitySummary.period_start < datetime.combine(target_date + timedelta(days=1), datetime.min.time()),
        ).order_by(ActivitySummary.generated_at.desc()).first()

        if digest:
            return DigestTriggerResponse(
                message=f"Digest generated successfully for {target_date}",
                digest=_digest_to_response(digest),
                skipped=False
            )
        else:
            return DigestTriggerResponse(
                message=f"Digest generated for {target_date} but could not retrieve from database",
                digest=None,
                skipped=False
            )

    except Exception as e:
        logger.error(f"Digest trigger failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Digest generation failed: {str(e)}"
        )


@router.get("/status", response_model=DigestStatusResponse)
async def get_digest_status():
    """
    Get digest scheduler status.

    AC11: GET /api/v1/digests/status returns last generation info and next scheduled time

    Returns:
        DigestStatusResponse with scheduler status
    """
    scheduler = get_digest_scheduler()
    status = scheduler.get_status()

    return DigestStatusResponse(
        enabled=status.enabled,
        schedule_time=status.schedule_time,
        last_run=status.last_run,
        last_status=status.last_status,
        last_error=status.last_error,
        next_run=status.next_run,
    )


@router.get("", response_model=DigestListResponse)
async def list_digests(
    limit: int = Query(20, ge=1, le=100, description="Number of digests to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    digest_type: Optional[str] = Query(None, description="Filter by digest type"),
    db: Session = Depends(get_db),
):
    """
    List generated digests.

    Returns recent digests ordered by generation time.

    Args:
        limit: Maximum number of digests to return
        offset: Pagination offset
        digest_type: Optional filter by type ('daily', 'weekly', 'manual')
        db: Database session

    Returns:
        DigestListResponse with list of digests
    """
    query = db.query(ActivitySummary)

    # Filter by digest_type if specified
    if digest_type:
        query = query.filter(ActivitySummary.digest_type == digest_type)
    else:
        # By default, only show digests (not on-demand summaries)
        query = query.filter(ActivitySummary.digest_type.isnot(None))

    # Count total
    total = query.count()

    # Get digests
    digests = query.order_by(
        ActivitySummary.generated_at.desc()
    ).offset(offset).limit(limit).all()

    return DigestListResponse(
        digests=[_digest_to_response(d) for d in digests],
        total=total,
    )


@router.get("/{digest_id}", response_model=DigestResponse)
async def get_digest(
    digest_id: str,
    db: Session = Depends(get_db),
):
    """
    Get a specific digest by ID.

    Args:
        digest_id: Digest UUID
        db: Database session

    Returns:
        DigestResponse

    Raises:
        404: Digest not found
    """
    digest = db.query(ActivitySummary).filter(
        ActivitySummary.id == digest_id
    ).first()

    if not digest:
        raise HTTPException(status_code=404, detail="Digest not found")

    return _digest_to_response(digest)
