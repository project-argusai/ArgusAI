"""
Notification API Endpoints (Story 5.4)

Provides endpoints for:
- Listing notifications with filtering and pagination
- Marking notifications as read (single or all)
- Deleting notifications

All endpoints follow established patterns from alert_rules.py
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.notification import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class NotificationResponse(BaseModel):
    """Response schema for a single notification."""
    id: str
    event_id: str
    rule_id: str
    rule_name: str
    event_description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Response schema for notification list."""
    data: List[NotificationResponse]
    total_count: int
    unread_count: int


class MarkReadResponse(BaseModel):
    """Response for mark as read operations."""
    success: bool
    updated_count: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    read: Optional[bool] = Query(None, description="Filter by read status"),
    limit: int = Query(20, ge=1, le=100, description="Number of notifications to return"),
    offset: int = Query(0, ge=0, description="Number of notifications to skip"),
    db: Session = Depends(get_db)
) -> NotificationListResponse:
    """
    Get notifications with optional filtering.

    Supports filtering by read/unread status and pagination.
    Results are sorted by created_at descending (newest first).

    Args:
        read: Filter by read status (true/false/null for all)
        limit: Maximum number of notifications to return
        offset: Number of notifications to skip for pagination

    Returns:
        List of notifications with total and unread counts
    """
    query = db.query(Notification)

    # Apply read filter if specified
    if read is not None:
        query = query.filter(Notification.read == read)

    # Get total count
    total_count = query.count()

    # Get unread count (always from all notifications)
    unread_count = db.query(Notification).filter(Notification.read == False).count()

    # Get paginated results
    notifications = (
        query
        .order_by(desc(Notification.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return NotificationListResponse(
        data=[NotificationResponse.model_validate(n) for n in notifications],
        total_count=total_count,
        unread_count=unread_count
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db)
) -> NotificationResponse:
    """
    Mark a single notification as read.

    Args:
        notification_id: UUID of the notification to mark as read

    Returns:
        Updated notification

    Raises:
        HTTPException: 404 if notification not found
    """
    notification = db.query(Notification).filter(Notification.id == notification_id).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.read = True
    db.commit()
    db.refresh(notification)

    return NotificationResponse.model_validate(notification)


@router.patch("/mark-all-read", response_model=MarkReadResponse)
async def mark_all_notifications_read(
    db: Session = Depends(get_db)
) -> MarkReadResponse:
    """
    Mark all unread notifications as read.

    Returns:
        Success status and count of updated notifications
    """
    updated_count = (
        db.query(Notification)
        .filter(Notification.read == False)
        .update({"read": True})
    )
    db.commit()

    return MarkReadResponse(success=True, updated_count=updated_count)


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db)
) -> dict:
    """
    Delete a single notification.

    Args:
        notification_id: UUID of the notification to delete

    Returns:
        Success confirmation

    Raises:
        HTTPException: 404 if notification not found
    """
    notification = db.query(Notification).filter(Notification.id == notification_id).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.delete(notification)
    db.commit()

    return {"deleted": True, "id": notification_id}


@router.delete("")
async def delete_all_notifications(
    read_only: bool = Query(False, description="Only delete read notifications"),
    db: Session = Depends(get_db)
) -> dict:
    """
    Delete notifications in bulk.

    Args:
        read_only: If true, only delete read notifications

    Returns:
        Success confirmation with count
    """
    query = db.query(Notification)

    if read_only:
        query = query.filter(Notification.read == True)

    deleted_count = query.delete()
    db.commit()

    return {"deleted": True, "count": deleted_count}
