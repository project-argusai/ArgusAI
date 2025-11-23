"""
Events API endpoints

Provides REST API for AI-generated semantic event management:
- POST /events - Create new event with AI description
- GET /events - List events with filtering, pagination, and full-text search
- GET /events/{id} - Get single event
- GET /events/stats - Get event statistics and aggregations
- GET /events/export - Export events to JSON or CSV
- DELETE /events/cleanup - Manual cleanup of old events
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc, asc, text
from typing import Optional
from datetime import datetime, timezone, timedelta, date
import logging
import json
import os
import base64
import uuid
import csv
import io
import asyncio

from app.core.database import get_db
from app.models.event import Event
from app.schemas.event import (
    EventCreate,
    EventResponse,
    EventListResponse,
    EventStatsResponse,
    EventFilterParams
)
from app.schemas.system import CleanupResponse
from app.services.cleanup_service import get_cleanup_service

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger(f"{__name__}.audit")  # Dedicated audit logger for compliance

router = APIRouter(prefix="/events", tags=["events"])

# Thumbnail storage directory
THUMBNAIL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'thumbnails')


def _save_thumbnail_to_filesystem(thumbnail_base64: str, event_id: str) -> str:
    """
    Save base64-encoded thumbnail to filesystem

    Args:
        thumbnail_base64: Base64-encoded JPEG image
        event_id: Event UUID for filename

    Returns:
        Relative path to saved thumbnail

    Raises:
        ValueError: If thumbnail data is invalid
    """
    try:
        # Decode base64 to bytes
        thumbnail_bytes = base64.b64decode(thumbnail_base64)

        # Create date-based subdirectory (YYYY-MM-DD)
        date_str = datetime.now().strftime('%Y-%m-%d')
        date_dir = os.path.join(THUMBNAIL_DIR, date_str)
        os.makedirs(date_dir, exist_ok=True)

        # Save to filesystem
        filename = f"event_{event_id}.jpg"
        file_path = os.path.join(date_dir, filename)

        with open(file_path, 'wb') as f:
            f.write(thumbnail_bytes)

        # Return relative path from data directory
        relative_path = f"thumbnails/{date_str}/{filename}"
        logger.debug(f"Saved thumbnail to {relative_path}")

        return relative_path

    except Exception as e:
        logger.error(f"Failed to save thumbnail for event {event_id}: {e}")
        raise ValueError(f"Invalid thumbnail data: {e}")


async def _process_event_alerts_background(event_id: str):
    """
    Background task to process alert rules for a new event.

    Creates a new database session for the background task since
    the original session may be closed by the time this runs.

    Args:
        event_id: UUID of the event to process
    """
    from app.core.database import SessionLocal
    from app.services.alert_engine import process_event_alerts

    db = SessionLocal()
    try:
        await process_event_alerts(event_id, db)
    except Exception as e:
        logger.error(
            f"Background alert processing failed for event {event_id}: {e}",
            exc_info=True,
            extra={"event_id": event_id}
        )
    finally:
        db.close()


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_data: EventCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create new AI-generated semantic event

    Args:
        event_data: Event creation data (camera_id, timestamp, description, etc.)
        db: Database session

    Returns:
        Created event with assigned UUID

    Raises:
        400: Invalid input data (e.g., invalid camera_id, bad thumbnail)
        500: Database error

    Examples:
        POST /events
        {
            "camera_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2025-11-17T14:30:00Z",
            "description": "Person walking towards front door carrying a package",
            "confidence": 85,
            "objects_detected": ["person", "package"],
            "thumbnail_base64": "/9j/4AAQSkZJRg...",
            "alert_triggered": true
        }
    """
    try:
        # Generate UUID for event
        event_id = str(uuid.uuid4())

        # Handle thumbnail storage
        thumbnail_path = None
        thumbnail_base64 = None

        if event_data.thumbnail_base64:
            try:
                # Save to filesystem
                thumbnail_path = _save_thumbnail_to_filesystem(event_data.thumbnail_base64, event_id)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )
        elif event_data.thumbnail_path:
            # Use provided filesystem path
            thumbnail_path = event_data.thumbnail_path

        # Convert objects_detected list to JSON string
        objects_detected_json = json.dumps(event_data.objects_detected)

        # Create event model
        event = Event(
            id=event_id,
            camera_id=event_data.camera_id,
            timestamp=event_data.timestamp,
            description=event_data.description,
            confidence=event_data.confidence,
            objects_detected=objects_detected_json,
            thumbnail_path=thumbnail_path,
            thumbnail_base64=thumbnail_base64,
            alert_triggered=event_data.alert_triggered
        )

        # Save to database
        db.add(event)
        db.commit()
        db.refresh(event)

        logger.info(
            f"Created event {event_id} for camera {event_data.camera_id} "
            f"(confidence={event_data.confidence}, objects={event_data.objects_detected})"
        )

        # Trigger alert rule evaluation in background (Epic 5)
        background_tasks.add_task(_process_event_alerts_background, event_id)

        return event

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create event: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create event"
        )


@router.get("", response_model=EventListResponse)
def list_events(
    camera_id: Optional[str] = Query(None, description="Filter by camera UUID"),
    start_time: Optional[datetime] = Query(None, description="Filter events after this timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter events before this timestamp"),
    min_confidence: Optional[int] = Query(None, ge=0, le=100, description="Minimum confidence score"),
    object_types: Optional[str] = Query(None, description="Comma-separated object types (e.g., 'person,vehicle')"),
    alert_triggered: Optional[bool] = Query(None, description="Filter by alert status"),
    search_query: Optional[str] = Query(None, min_length=1, max_length=500, description="Full-text search in descriptions"),
    limit: int = Query(50, ge=1, le=500, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort by timestamp"),
    db: Session = Depends(get_db)
):
    """
    List events with filtering, pagination, and full-text search

    Args:
        camera_id: Optional filter by camera UUID
        start_time: Filter events after this timestamp (inclusive)
        end_time: Filter events before this timestamp (inclusive)
        min_confidence: Minimum confidence score (0-100)
        object_types: Comma-separated object types to filter
        alert_triggered: Filter by alert status (true/false)
        search_query: Full-text search in event descriptions (uses FTS5)
        limit: Results per page (default 50, max 500)
        offset: Pagination offset (default 0)
        sort_order: Sort order - "asc" or "desc" (default desc - newest first)
        db: Database session

    Returns:
        EventListResponse with events array and pagination metadata

    Examples:
        - GET /events?limit=10
        - GET /events?camera_id=abc123&start_time=2025-11-01T00:00:00Z
        - GET /events?min_confidence=80&object_types=person,vehicle
        - GET /events?search_query=front+door&limit=20
    """
    try:
        # Build base query
        query = db.query(Event)

        # Apply camera filter
        if camera_id:
            query = query.filter(Event.camera_id == camera_id)

        # Apply time range filters
        if start_time:
            query = query.filter(Event.timestamp >= start_time)
        if end_time:
            query = query.filter(Event.timestamp <= end_time)

        # Apply confidence filter
        if min_confidence is not None:
            query = query.filter(Event.confidence >= min_confidence)

        # Apply alert filter
        if alert_triggered is not None:
            query = query.filter(Event.alert_triggered == alert_triggered)

        # Apply object type filter
        if object_types:
            object_type_list = [obj.strip() for obj in object_types.split(',')]
            # Use OR logic - match any of the specified object types
            object_filters = [
                Event.objects_detected.like(f'%"{obj}"%') for obj in object_type_list
            ]
            query = query.filter(or_(*object_filters))

        # Apply full-text search using FTS5
        if search_query:
            # Query FTS5 virtual table for matching event IDs
            fts_query = db.execute(
                text("SELECT id FROM events_fts WHERE description MATCH :query"),
                {"query": search_query}
            )
            matching_ids = [row[0] for row in fts_query.fetchall()]

            if matching_ids:
                query = query.filter(Event.id.in_(matching_ids))
            else:
                # No FTS5 matches - return empty result
                return EventListResponse(
                    events=[],
                    total_count=0,
                    has_more=False,
                    next_offset=None,
                    limit=limit,
                    offset=offset
                )

        # Get total count before pagination
        total_count = query.count()

        # Apply sorting
        if sort_order == "desc":
            query = query.order_by(desc(Event.timestamp))
        else:
            query = query.order_by(asc(Event.timestamp))

        # Apply pagination
        query = query.offset(offset).limit(limit)

        # Execute query
        events = query.all()

        # Calculate pagination metadata
        has_more = (offset + limit) < total_count
        next_offset = (offset + limit) if has_more else None

        logger.info(
            f"Listed {len(events)} events (total={total_count}, filters: "
            f"camera={camera_id}, search={search_query}, limit={limit}, offset={offset})"
        )

        return EventListResponse(
            events=events,
            total_count=total_count,
            has_more=has_more,
            next_offset=next_offset,
            limit=limit,
            offset=offset
        )

    except Exception as e:
        logger.error(f"Failed to list events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list events"
        )


# IMPORTANT: These routes must come BEFORE /{event_id} to avoid path parameter shadowing
@router.get("/export")
async def export_events(
    format: str = Query(..., pattern="^(json|csv)$", description="Export format (json or csv)"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    camera_id: Optional[str] = Query(None, description="Filter by camera UUID"),
    min_confidence: Optional[int] = Query(None, ge=0, le=100, description="Minimum confidence score"),
    db: Session = Depends(get_db)
):
    """
    Export events to JSON or CSV format

    Streams events in batches for memory efficiency. Supports filtering by date range,
    camera, and confidence level.

    Args:
        format: Export format - "json" (newline-delimited) or "csv"
        start_date: Optional start date filter (inclusive)
        end_date: Optional end date filter (inclusive)
        camera_id: Optional filter by camera UUID
        min_confidence: Optional minimum confidence score (0-100)
        db: Database session

    Returns:
        StreamingResponse with Content-Disposition header for download

    **JSON Format** (newline-delimited JSON):
    ```json
    {"id": "...", "camera_id": "...", "timestamp": "...", ...}
    {"id": "...", "camera_id": "...", "timestamp": "...", ...}
    ```

    **CSV Format**:
    ```csv
    id,camera_id,timestamp,description,confidence,objects_detected,alert_triggered
    123,abc,2025-11-17T14:30:00Z,Person walking,85,"person,package",true
    ```

    **Status Codes:**
    - 200: Success (streaming response)
    - 400: Invalid format or date range
    - 500: Internal server error

    **Examples:**
    - GET /events/export?format=json
    - GET /events/export?format=csv&start_date=2025-11-01&end_date=2025-11-17
    - GET /events/export?format=csv&camera_id=abc123&min_confidence=80
    """
    try:
        # Build query with filters
        query = db.query(Event)

        # Date range filters
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            query = query.filter(Event.timestamp >= start_datetime)

        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            query = query.filter(Event.timestamp <= end_datetime)

        # Camera filter
        if camera_id:
            query = query.filter(Event.camera_id == camera_id)

        # Confidence filter
        if min_confidence is not None:
            query = query.filter(Event.confidence >= min_confidence)

        # Sort by timestamp
        query = query.order_by(Event.timestamp)

        # Generate filename
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"events_export_{timestamp_str}.{format}"

        logger.info(
            f"Starting export: format={format}, start_date={start_date}, "
            f"end_date={end_date}, camera={camera_id}, min_confidence={min_confidence}"
        )

        # Stream generator functions
        def generate_json():
            """Generate newline-delimited JSON"""
            batch_size = 100
            offset = 0

            while True:
                events = query.offset(offset).limit(batch_size).all()

                if not events:
                    break

                for event in events:
                    event_dict = {
                        "id": event.id,
                        "camera_id": event.camera_id,
                        "timestamp": event.timestamp.isoformat(),
                        "description": event.description,
                        "confidence": event.confidence,
                        "objects_detected": json.loads(event.objects_detected),
                        "thumbnail_path": event.thumbnail_path,
                        "alert_triggered": event.alert_triggered,
                        "created_at": event.created_at.isoformat()
                    }
                    yield json.dumps(event_dict) + "\n"

                offset += batch_size

        def generate_csv():
            """Generate CSV with headers"""
            batch_size = 100
            offset = 0

            # CSV headers
            buffer = io.StringIO()
            writer = csv.DictWriter(
                buffer,
                fieldnames=[
                    "id", "camera_id", "timestamp", "description",
                    "confidence", "objects_detected", "thumbnail_path",
                    "alert_triggered", "created_at"
                ]
            )
            writer.writeheader()
            yield buffer.getvalue()

            # Stream rows
            while True:
                events = query.offset(offset).limit(batch_size).all()

                if not events:
                    break

                buffer = io.StringIO()
                writer = csv.DictWriter(
                    buffer,
                    fieldnames=[
                        "id", "camera_id", "timestamp", "description",
                        "confidence", "objects_detected", "thumbnail_path",
                        "alert_triggered", "created_at"
                    ]
                )

                for event in events:
                    writer.writerow({
                        "id": event.id,
                        "camera_id": event.camera_id,
                        "timestamp": event.timestamp.isoformat(),
                        "description": event.description,
                        "confidence": event.confidence,
                        "objects_detected": ",".join(json.loads(event.objects_detected)),
                        "thumbnail_path": event.thumbnail_path or "",
                        "alert_triggered": event.alert_triggered,
                        "created_at": event.created_at.isoformat()
                    })

                yield buffer.getvalue()
                offset += batch_size

        # Select generator and media type
        if format == "json":
            generator = generate_json()
            media_type = "application/x-ndjson"
        else:  # csv
            generator = generate_csv()
            media_type = "text/csv"

        return StreamingResponse(
            generator,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.error(f"Failed to export events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export events"
        )


@router.delete("/cleanup", response_model=CleanupResponse)
async def manual_cleanup(
    before_date: date = Query(..., description="Delete events before this date (YYYY-MM-DD)"),
    confirm: bool = Query(False, description="Must be true to confirm deletion"),
    db: Session = Depends(get_db)
):
    """
    Manually trigger cleanup of events before a specific date

    Deletes all events (and associated thumbnails) that occurred before the specified
    date. Requires explicit confirmation via confirm=true parameter.

    **CAUTION**: This operation is permanent and cannot be undone. Always verify the
    before_date parameter before confirming.

    Args:
        before_date: Delete events before this date (exclusive)
        confirm: Must be explicitly set to true to proceed with deletion
        db: Database session

    Returns:
        CleanupResponse with deletion statistics:
        - deleted_count: Number of events deleted
        - thumbnails_deleted: Number of thumbnail files deleted
        - space_freed_mb: Amount of disk space freed in megabytes

    **Request:**
    ```
    DELETE /events/cleanup?before_date=2025-10-01&confirm=true
    ```

    **Response:**
    ```json
    {
        "deleted_count": 450,
        "thumbnails_deleted": 380,
        "space_freed_mb": 12.3
    }
    ```

    **Status Codes:**
    - 200: Success (cleanup completed)
    - 400: Invalid date (future date) or missing confirmation
    - 500: Internal server error

    **Examples:**
    - DELETE /events/cleanup?before_date=2025-10-01&confirm=true
    - DELETE /events/cleanup?before_date=2025-11-01&confirm=true
    """
    try:
        # Validate confirmation
        if not confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deletion must be explicitly confirmed with confirm=true"
            )

        # Validate date is not in future
        today = date.today()
        if before_date >= today:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"before_date must be in the past (today is {today})"
            )

        # Calculate retention days from before_date to now
        days_ago = (datetime.now(timezone.utc) - datetime.combine(before_date, datetime.min.time()).replace(tzinfo=timezone.utc)).days

        logger.warning(
            f"Manual cleanup triggered: deleting events before {before_date} ({days_ago} days ago)",
            extra={"before_date": str(before_date), "days_ago": days_ago, "confirmed": confirm}
        )

        # Execute cleanup
        cleanup_service = get_cleanup_service()
        stats = await cleanup_service.cleanup_old_events(retention_days=days_ago)

        logger.info(
            f"Manual cleanup complete: {stats['events_deleted']} events deleted, "
            f"{stats['space_freed_mb']} MB freed",
            extra=stats
        )

        # Audit log entry for compliance (AC #6 requirement)
        # Use WARNING level to ensure permanent retention in production logging
        audit_logger.warning(
            "AUDIT: Manual cleanup operation completed",
            extra={
                "audit_event": "manual_cleanup",
                "operation": "DELETE /events/cleanup",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "parameters": {
                    "before_date": str(before_date),
                    "confirm": confirm,
                    "days_ago": days_ago
                },
                "result": {
                    "deleted_count": stats["events_deleted"],
                    "thumbnails_deleted": stats["thumbnails_deleted"],
                    "space_freed_mb": stats["space_freed_mb"],
                    "batches_processed": stats.get("batches_processed", 0)
                },
                "source": "api_endpoint",
                "status": "success"
            }
        )

        return CleanupResponse(
            deleted_count=stats["events_deleted"],
            thumbnails_deleted=stats["thumbnails_deleted"],
            space_freed_mb=stats["space_freed_mb"]
        )

    except HTTPException as e:
        # Audit log for rejected/failed operations
        audit_logger.warning(
            "AUDIT: Manual cleanup operation rejected",
            extra={
                "audit_event": "manual_cleanup",
                "operation": "DELETE /events/cleanup",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "parameters": {
                    "before_date": str(before_date),
                    "confirm": confirm
                },
                "result": {"error": str(e.detail)},
                "source": "api_endpoint",
                "status": "rejected"
            }
        )
        raise
    except Exception as e:
        # Audit log for system failures
        audit_logger.error(
            "AUDIT: Manual cleanup operation failed",
            extra={
                "audit_event": "manual_cleanup",
                "operation": "DELETE /events/cleanup",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "parameters": {
                    "before_date": str(before_date),
                    "confirm": confirm
                },
                "result": {"error": str(e)},
                "source": "api_endpoint",
                "status": "failed"
            },
            exc_info=True
        )
        logger.error(f"Failed to perform manual cleanup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to perform cleanup"
        )


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: str,
    db: Session = Depends(get_db)
):
    """
    Get single event by ID

    Args:
        event_id: Event UUID
        db: Database session

    Returns:
        Event with full details including thumbnail

    Raises:
        404: Event not found
        500: Database error

    Example:
        GET /events/123e4567-e89b-12d3-a456-426614174000
    """
    try:
        event = db.query(Event).filter(Event.id == event_id).first()

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        logger.debug(f"Retrieved event {event_id}")

        return event

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get event {event_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get event"
        )


@router.get("/stats/aggregate", response_model=EventStatsResponse)
def get_event_stats(
    camera_id: Optional[str] = Query(None, description="Filter by camera UUID"),
    start_time: Optional[datetime] = Query(None, description="Start of time range"),
    end_time: Optional[datetime] = Query(None, description="End of time range"),
    db: Session = Depends(get_db)
):
    """
    Get event statistics and aggregations

    Args:
        camera_id: Optional filter by camera UUID
        start_time: Start of time range (default: all time)
        end_time: End of time range (default: now)
        db: Database session

    Returns:
        EventStatsResponse with aggregated statistics:
        - total_events: Total event count
        - events_by_camera: Event counts grouped by camera
        - events_by_object_type: Event counts by detected object type
        - average_confidence: Average confidence score
        - alerts_triggered: Number of events that triggered alerts
        - time_range: Actual time range of events

    Examples:
        - GET /events/stats/aggregate
        - GET /events/stats/aggregate?camera_id=abc123
        - GET /events/stats/aggregate?start_time=2025-11-01T00:00:00Z&end_time=2025-11-17T23:59:59Z
    """
    try:
        # Build base query
        query = db.query(Event)

        # Apply filters
        if camera_id:
            query = query.filter(Event.camera_id == camera_id)
        if start_time:
            query = query.filter(Event.timestamp >= start_time)
        if end_time:
            query = query.filter(Event.timestamp <= end_time)

        # Total events
        total_events = query.count()

        # Events by camera
        events_by_camera = {}
        if not camera_id:
            camera_counts = db.query(
                Event.camera_id,
                func.count(Event.id).label('count')
            ).group_by(Event.camera_id)

            if start_time:
                camera_counts = camera_counts.filter(Event.timestamp >= start_time)
            if end_time:
                camera_counts = camera_counts.filter(Event.timestamp <= end_time)

            camera_counts = camera_counts.all()
            events_by_camera = {camera_id: count for camera_id, count in camera_counts}
        else:
            events_by_camera[camera_id] = total_events

        # Events by object type (aggregate from JSON arrays)
        events_by_object_type = {}
        all_events = query.all()
        for event in all_events:
            objects = json.loads(event.objects_detected)
            for obj in objects:
                events_by_object_type[obj] = events_by_object_type.get(obj, 0) + 1

        # Average confidence
        avg_result = query.with_entities(
            func.avg(Event.confidence).label('avg_confidence')
        ).first()
        average_confidence = float(avg_result.avg_confidence) if avg_result.avg_confidence else 0.0

        # Alerts triggered
        alerts_triggered = query.filter(Event.alert_triggered == True).count()

        # Actual time range
        time_range_result = query.with_entities(
            func.min(Event.timestamp).label('min_time'),
            func.max(Event.timestamp).label('max_time')
        ).first()

        time_range = {
            "start": time_range_result.min_time if time_range_result.min_time else None,
            "end": time_range_result.max_time if time_range_result.max_time else None
        }

        logger.info(
            f"Event stats: total={total_events}, cameras={len(events_by_camera)}, "
            f"avg_confidence={average_confidence:.1f}, alerts={alerts_triggered}"
        )

        return EventStatsResponse(
            total_events=total_events,
            events_by_camera=events_by_camera,
            events_by_object_type=events_by_object_type,
            average_confidence=average_confidence,
            alerts_triggered=alerts_triggered,
            time_range=time_range
        )

    except Exception as e:
        logger.error(f"Failed to get event stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get event statistics"
        )
