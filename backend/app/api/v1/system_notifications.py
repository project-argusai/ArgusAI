"""
System Notifications API Endpoints (Story P3-7.4)

Provides endpoints for system-level notifications like cost alerts.
Separate from event-based notifications (alert rules).
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.system_notification import SystemNotification

router = APIRouter(prefix="/system-notifications", tags=["system-notifications"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class SystemNotificationResponse(BaseModel):
    """Response schema for a single system notification."""
    id: str
    notification_type: str
    severity: str
    title: str
    message: str
    action_url: Optional[str] = None
    extra_data: Optional[dict] = None
    read: bool
    dismissed: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SystemNotificationListResponse(BaseModel):
    """Response schema for system notification list."""
    data: List[SystemNotificationResponse]
    total_count: int
    unread_count: int


class MarkReadResponse(BaseModel):
    """Response for mark as read operations."""
    success: bool
    updated_count: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=SystemNotificationListResponse)
async def list_system_notifications(
    notification_type: Optional[str] = Query(None, description="Filter by notification type (cost_alert, etc.)"),
    read: Optional[bool] = Query(None, description="Filter by read status"),
    dismissed: Optional[bool] = Query(False, description="Include dismissed notifications"),
    limit: int = Query(20, ge=1, le=100, description="Number of notifications to return"),
    offset: int = Query(0, ge=0, description="Number of notifications to skip"),
    db: Session = Depends(get_db)
) -> SystemNotificationListResponse:
    """
    Get system notifications with optional filtering.

    Supports filtering by type, read/unread status, and pagination.
    Results are sorted by created_at descending (newest first).
    """
    query = db.query(SystemNotification)

    # Filter out dismissed by default
    if not dismissed:
        query = query.filter(SystemNotification.dismissed == False)

    # Apply type filter if specified
    if notification_type:
        query = query.filter(SystemNotification.notification_type == notification_type)

    # Apply read filter if specified
    if read is not None:
        query = query.filter(SystemNotification.read == read)

    # Get total count
    total_count = query.count()

    # Get unread count (from filtered set)
    unread_count = db.query(SystemNotification).filter(
        SystemNotification.read == False,
        SystemNotification.dismissed == False
    ).count()

    # Get paginated results
    notifications = (
        query
        .order_by(desc(SystemNotification.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return SystemNotificationListResponse(
        data=[SystemNotificationResponse.model_validate(n) for n in notifications],
        total_count=total_count,
        unread_count=unread_count
    )


@router.patch("/{notification_id}/read", response_model=SystemNotificationResponse)
async def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db)
) -> SystemNotificationResponse:
    """Mark a single system notification as read."""
    notification = db.query(SystemNotification).filter(
        SystemNotification.id == notification_id
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.read = True
    db.commit()
    db.refresh(notification)

    return SystemNotificationResponse.model_validate(notification)


@router.patch("/{notification_id}/dismiss", response_model=SystemNotificationResponse)
async def dismiss_notification(
    notification_id: str,
    db: Session = Depends(get_db)
) -> SystemNotificationResponse:
    """Dismiss a single system notification (hides it from default view)."""
    notification = db.query(SystemNotification).filter(
        SystemNotification.id == notification_id
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.dismissed = True
    notification.read = True  # Dismissing also marks as read
    db.commit()
    db.refresh(notification)

    return SystemNotificationResponse.model_validate(notification)


@router.patch("/mark-all-read", response_model=MarkReadResponse)
async def mark_all_notifications_read(
    notification_type: Optional[str] = Query(None, description="Only mark this type as read"),
    db: Session = Depends(get_db)
) -> MarkReadResponse:
    """Mark all unread system notifications as read."""
    query = db.query(SystemNotification).filter(SystemNotification.read == False)

    if notification_type:
        query = query.filter(SystemNotification.notification_type == notification_type)

    updated_count = query.update({"read": True})
    db.commit()

    return MarkReadResponse(success=True, updated_count=updated_count)


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db)
) -> dict:
    """Delete a single system notification."""
    notification = db.query(SystemNotification).filter(
        SystemNotification.id == notification_id
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.delete(notification)
    db.commit()

    return {"deleted": True, "id": notification_id}


@router.delete("")
async def delete_all_notifications(
    notification_type: Optional[str] = Query(None, description="Only delete this type"),
    read_only: bool = Query(False, description="Only delete read notifications"),
    db: Session = Depends(get_db)
) -> dict:
    """Delete system notifications in bulk."""
    query = db.query(SystemNotification)

    if notification_type:
        query = query.filter(SystemNotification.notification_type == notification_type)

    if read_only:
        query = query.filter(SystemNotification.read == True)

    deleted_count = query.delete()
    db.commit()

    return {"deleted": True, "count": deleted_count}
