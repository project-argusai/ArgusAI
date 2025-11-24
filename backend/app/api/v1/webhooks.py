"""
Webhook API Endpoints (Story 5.3)

Provides endpoints for:
- Testing webhook configuration before saving
- Viewing webhook delivery logs with filtering
- Exporting logs as CSV

All endpoints follow established patterns from alert_rules.py
"""
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, HttpUrl, Field
from sqlalchemy import desc, and_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert_rule import WebhookLog, AlertRule
from app.services.webhook_service import (
    WebhookService,
    WebhookValidationError,
    WebhookRateLimitError,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class WebhookTestRequest(BaseModel):
    """Request schema for webhook test endpoint."""
    url: str = Field(..., description="Webhook URL to test")
    headers: Optional[dict] = Field(default=None, description="Custom headers")
    payload: Optional[dict] = Field(default=None, description="Custom payload (uses sample if not provided)")


class WebhookTestResponse(BaseModel):
    """Response schema for webhook test endpoint."""
    success: bool
    status_code: int
    response_body: str = Field(..., description="Response body (truncated to 200 chars)")
    response_time_ms: int
    error: Optional[str] = None


class WebhookLogResponse(BaseModel):
    """Response schema for a single webhook log entry."""
    id: int
    alert_rule_id: str
    rule_name: Optional[str] = None
    event_id: str
    url: str
    status_code: int
    response_time_ms: int
    retry_count: int
    success: bool
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WebhookLogsListResponse(BaseModel):
    """Response schema for webhook logs list."""
    data: list[WebhookLogResponse]
    total_count: int


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/test", response_model=WebhookTestResponse)
async def test_webhook(
    request: WebhookTestRequest,
    db: Session = Depends(get_db)
) -> WebhookTestResponse:
    """
    Test a webhook URL by sending a sample payload.

    Validates the URL, sends an HTTP POST request, and returns the result.
    Does not log to webhook_logs table (test only).

    Args:
        request: Webhook test request with URL, optional headers and payload

    Returns:
        Test result with status code, response body, and timing

    Raises:
        HTTPException: 400 if URL is invalid, 429 if rate limited
    """
    # Create service with allow_http=True for testing flexibility
    service = WebhookService(db, allow_http=True)

    # Validate URL first
    try:
        service.validate_url(request.url)
    except WebhookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Build sample payload if not provided
    payload = request.payload or {
        "event_id": "test-event-uuid",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera": {
            "id": "test-camera-uuid",
            "name": "Test Camera"
        },
        "description": "Test webhook payload - this is a sample event description for testing your webhook endpoint.",
        "confidence": 95,
        "objects_detected": ["person"],
        "thumbnail_url": "/api/v1/events/test-event-uuid/thumbnail",
        "rule": {
            "id": "test-rule-uuid",
            "name": "Test Rule"
        }
    }

    headers = request.headers or {}

    # Send webhook without logging (skip_validation=True since we already validated)
    result = await service.send_webhook(
        url=request.url,
        headers=headers,
        payload=payload,
        rule_id=None,  # Don't log test requests
        event_id=None,
        skip_validation=True
    )

    return WebhookTestResponse(
        success=result.success,
        status_code=result.status_code,
        response_body=result.response_body,
        response_time_ms=result.response_time_ms,
        error=result.error_message
    )


@router.get("/logs", response_model=WebhookLogsListResponse)
async def get_webhook_logs(
    rule_id: Optional[str] = Query(None, description="Filter by alert rule ID"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    start_date: Optional[datetime] = Query(None, description="Filter logs after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter logs before this date"),
    limit: int = Query(50, ge=1, le=200, description="Number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    db: Session = Depends(get_db)
) -> WebhookLogsListResponse:
    """
    Get webhook delivery logs with optional filtering.

    Supports filtering by rule, success status, and date range.
    Results are sorted by created_at descending (newest first).

    Args:
        rule_id: Filter by specific alert rule
        success: Filter by success/failure
        start_date: Only include logs after this date
        end_date: Only include logs before this date
        limit: Maximum number of logs to return
        offset: Number of logs to skip for pagination

    Returns:
        List of webhook logs with total count
    """
    # Build query with filters
    query = db.query(WebhookLog)

    filters = []
    if rule_id:
        filters.append(WebhookLog.alert_rule_id == rule_id)
    if success is not None:
        filters.append(WebhookLog.success == success)
    if start_date:
        filters.append(WebhookLog.created_at >= start_date)
    if end_date:
        filters.append(WebhookLog.created_at <= end_date)

    if filters:
        query = query.filter(and_(*filters))

    # Get total count
    total_count = query.count()

    # Get paginated results
    logs = query.order_by(desc(WebhookLog.created_at)).offset(offset).limit(limit).all()

    # Enrich with rule names
    rule_ids = list(set(log.alert_rule_id for log in logs))
    rules = db.query(AlertRule).filter(AlertRule.id.in_(rule_ids)).all()
    rule_name_map = {r.id: r.name for r in rules}

    response_logs = []
    for log in logs:
        response_logs.append(WebhookLogResponse(
            id=log.id,
            alert_rule_id=log.alert_rule_id,
            rule_name=rule_name_map.get(log.alert_rule_id),
            event_id=log.event_id,
            url=log.url,
            status_code=log.status_code,
            response_time_ms=log.response_time_ms,
            retry_count=log.retry_count,
            success=log.success,
            error_message=log.error_message,
            created_at=log.created_at
        ))

    return WebhookLogsListResponse(
        data=response_logs,
        total_count=total_count
    )


@router.get("/logs/export")
async def export_webhook_logs(
    rule_id: Optional[str] = Query(None, description="Filter by alert rule ID"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    start_date: Optional[datetime] = Query(None, description="Filter logs after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter logs before this date"),
    db: Session = Depends(get_db)
) -> Response:
    """
    Export webhook logs as CSV file.

    Applies the same filters as the list endpoint but returns all matching
    logs as a downloadable CSV file.

    Args:
        rule_id: Filter by specific alert rule
        success: Filter by success/failure
        start_date: Only include logs after this date
        end_date: Only include logs before this date

    Returns:
        CSV file download
    """
    # Build query with filters
    query = db.query(WebhookLog)

    filters = []
    if rule_id:
        filters.append(WebhookLog.alert_rule_id == rule_id)
    if success is not None:
        filters.append(WebhookLog.success == success)
    if start_date:
        filters.append(WebhookLog.created_at >= start_date)
    if end_date:
        filters.append(WebhookLog.created_at <= end_date)

    if filters:
        query = query.filter(and_(*filters))

    logs = query.order_by(desc(WebhookLog.created_at)).all()

    # Get rule names
    rule_ids = list(set(log.alert_rule_id for log in logs))
    rules = db.query(AlertRule).filter(AlertRule.id.in_(rule_ids)).all()
    rule_name_map = {r.id: r.name for r in rules}

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "ID",
        "Timestamp",
        "Rule ID",
        "Rule Name",
        "Event ID",
        "URL",
        "Status Code",
        "Response Time (ms)",
        "Retry Count",
        "Success",
        "Error Message"
    ])

    # Write data rows
    for log in logs:
        writer.writerow([
            log.id,
            log.created_at.isoformat() if log.created_at else "",
            log.alert_rule_id,
            rule_name_map.get(log.alert_rule_id, ""),
            log.event_id,
            log.url,
            log.status_code,
            log.response_time_ms,
            log.retry_count,
            "Yes" if log.success else "No",
            log.error_message or ""
        ])

    # Generate filename with timestamp
    filename = f"webhook_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
