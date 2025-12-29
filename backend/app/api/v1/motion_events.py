"""
Motion Events API endpoints

Provides REST API for motion event retrieval and management:
- GET /motion-events - List all motion events with filters
- GET /motion-events/export - Export motion events to CSV format
- GET /motion-events/{id} - Get single motion event
- DELETE /motion-events/{id} - Delete motion event
- GET /motion-events/stats - Get motion event statistics
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from datetime import datetime, date, timedelta, timezone
import logging
import json
import csv
import io

from app.core.database import get_db
from app.models.motion_event import MotionEvent
from app.models.camera import Camera
from app.schemas.motion import MotionEventResponse, MotionEventStatsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/motion-events", tags=["motion-events"])


# IMPORTANT: Export route must come BEFORE /{event_id} to avoid path parameter shadowing
@router.get("/export")
async def export_motion_events(
    format: str = Query(..., pattern="^csv$", description="Export format (currently only csv supported)"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    camera_id: Optional[str] = Query(None, description="Filter by camera UUID"),
    db: Session = Depends(get_db)
):
    """
    Export motion events to CSV format

    Streams motion events in batches for memory efficiency. Supports filtering by date range
    and camera. Returns a downloadable CSV file with motion detection data.

    Args:
        format: Export format - must be "csv"
        start_date: Optional start date filter (inclusive)
        end_date: Optional end date filter (inclusive)
        camera_id: Optional filter by camera UUID
        db: Database session

    Returns:
        StreamingResponse with Content-Disposition header for download

    **CSV Columns:**
    - timestamp: ISO 8601 timestamp of motion detection
    - camera_id: UUID of the camera
    - camera_name: Human-readable camera name
    - confidence: Motion detection confidence (0.0-1.0)
    - algorithm: Detection algorithm used (mog2, knn, frame_diff)
    - x, y, width, height: Bounding box coordinates (if available)
    - zone_id: Detection zone ID (if applicable)

    **Status Codes:**
    - 200: Success (streaming response)
    - 422: Invalid format parameter
    - 500: Internal server error

    **Examples:**
    - GET /motion-events/export?format=csv
    - GET /motion-events/export?format=csv&start_date=2025-11-01&end_date=2025-11-17
    - GET /motion-events/export?format=csv&camera_id=abc123
    """
    try:
        # Build query with filters, joining Camera table for camera names
        query = db.query(MotionEvent, Camera.name.label("camera_name")).outerjoin(
            Camera, MotionEvent.camera_id == Camera.id
        )

        # Date range filters
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            query = query.filter(MotionEvent.timestamp >= start_datetime)

        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            query = query.filter(MotionEvent.timestamp <= end_datetime)

        # Camera filter
        if camera_id:
            query = query.filter(MotionEvent.camera_id == camera_id)

        # Sort by timestamp
        query = query.order_by(MotionEvent.timestamp)

        # Generate filename with date range
        if start_date and end_date:
            filename = f"motion_events_{start_date.isoformat()}_{end_date.isoformat()}.csv"
        elif start_date:
            filename = f"motion_events_{start_date.isoformat()}_latest.csv"
        elif end_date:
            filename = f"motion_events_earliest_{end_date.isoformat()}.csv"
        else:
            filename = "motion_events_all.csv"

        logger.info(
            f"Starting motion events export: format={format}, start_date={start_date}, "
            f"end_date={end_date}, camera={camera_id}"
        )

        def generate_csv():
            """Generate CSV with headers, streaming in batches"""
            batch_size = 100
            offset = 0

            # CSV headers per AC#2
            fieldnames = [
                "timestamp", "camera_id", "camera_name", "confidence",
                "algorithm", "x", "y", "width", "height", "zone_id"
            ]

            # Write headers
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            yield buffer.getvalue()

            # Stream rows in batches
            while True:
                results = query.offset(offset).limit(batch_size).all()

                if not results:
                    break

                buffer = io.StringIO()
                writer = csv.DictWriter(buffer, fieldnames=fieldnames)

                for motion_event, camera_name in results:
                    # Parse bounding_box JSON if present
                    x, y, width, height = "", "", "", ""
                    if motion_event.bounding_box:
                        try:
                            bbox = json.loads(motion_event.bounding_box)
                            x = bbox.get("x", "")
                            y = bbox.get("y", "")
                            width = bbox.get("width", "")
                            height = bbox.get("height", "")
                        except (json.JSONDecodeError, TypeError):
                            pass  # Leave as empty strings

                    writer.writerow({
                        "timestamp": motion_event.timestamp.isoformat() if motion_event.timestamp else "",
                        "camera_id": motion_event.camera_id or "",
                        "camera_name": camera_name or motion_event.camera_id or "",  # Fallback to camera_id
                        "confidence": motion_event.confidence if motion_event.confidence is not None else "",
                        "algorithm": motion_event.algorithm_used or "",
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                        "zone_id": ""  # zone_id not currently stored on MotionEvent
                    })

                yield buffer.getvalue()
                offset += batch_size

        return StreamingResponse(
            generate_csv(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.error(f"Failed to export motion events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export motion events"
        )


@router.get("", response_model=List[MotionEventResponse])
def list_motion_events(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (ISO 8601)"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum confidence score"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip (pagination)"),
    db: Session = Depends(get_db)
):
    """
    List motion events with optional filtering and pagination

    Args:
        camera_id: Optional filter by camera UUID
        start_date: Optional filter by start date (inclusive)
        end_date: Optional filter by end date (inclusive)
        min_confidence: Optional minimum confidence threshold
        limit: Maximum events to return (default 50, max 200)
        offset: Pagination offset (default 0)
        db: Database session

    Returns:
        List of motion events ordered by timestamp DESC (most recent first)

    Examples:
        - GET /motion-events?limit=10
        - GET /motion-events?camera_id=abc123&start_date=2025-11-01T00:00:00Z
        - GET /motion-events?min_confidence=0.8&limit=20&offset=40
    """
    try:
        # Build query
        query = db.query(MotionEvent)

        # Apply filters
        if camera_id:
            query = query.filter(MotionEvent.camera_id == camera_id)

        if start_date:
            query = query.filter(MotionEvent.timestamp >= start_date)

        if end_date:
            query = query.filter(MotionEvent.timestamp <= end_date)

        if min_confidence is not None:
            query = query.filter(MotionEvent.confidence >= min_confidence)

        # Order by timestamp DESC (most recent first)
        query = query.order_by(MotionEvent.timestamp.desc())

        # Apply pagination
        query = query.offset(offset).limit(limit)

        # Execute query
        events = query.all()

        logger.info(f"Listed {len(events)} motion events (filters: camera={camera_id}, limit={limit}, offset={offset})")

        return events

    except Exception as e:
        logger.error(f"Failed to list motion events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list motion events"
        )


@router.get("/{event_id}", response_model=MotionEventResponse)
def get_motion_event(
    event_id: str,
    db: Session = Depends(get_db)
):
    """
    Get single motion event by ID

    Args:
        event_id: UUID of motion event
        db: Database session

    Returns:
        Motion event with full details (including frame thumbnail)

    Raises:
        404: Motion event not found
    """
    try:
        event = db.query(MotionEvent).filter(MotionEvent.id == event_id).first()

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Motion event {event_id} not found"
            )

        logger.debug(f"Retrieved motion event {event_id}")

        return event

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get motion event {event_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get motion event"
        )


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_motion_event(
    event_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete motion event (user data ownership)

    Args:
        event_id: UUID of motion event to delete
        db: Database session

    Returns:
        Success confirmation

    Raises:
        404: Motion event not found
    """
    try:
        event = db.query(MotionEvent).filter(MotionEvent.id == event_id).first()

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Motion event {event_id} not found"
            )

        # Delete from database
        db.delete(event)
        db.commit()

        logger.info(f"Deleted motion event {event_id}")

        # Story P14-2.4: Return 204 No Content (no body)
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete motion event {event_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete motion event"
        )


@router.get("/stats", response_model=MotionEventStatsResponse)
def get_motion_event_stats(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    days: int = Query(7, ge=1, le=90, description="Number of days to include (default 7)"),
    db: Session = Depends(get_db)
):
    """
    Get motion event statistics

    Args:
        camera_id: Optional filter by camera ID
        days: Number of days to include in stats (default 7, max 90)
        db: Database session

    Returns:
        Statistics including:
        - total_events: Total event count
        - events_by_camera: Event counts grouped by camera
        - events_by_hour: Event counts by hour of day (0-23)
        - average_confidence: Average confidence score

    Examples:
        - GET /motion-events/stats
        - GET /motion-events/stats?camera_id=abc123&days=30
    """
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Build base query
        query = db.query(MotionEvent).filter(
            MotionEvent.timestamp >= start_date
        )

        if camera_id:
            query = query.filter(MotionEvent.camera_id == camera_id)

        # Total events
        total_events = query.count()

        # Events by camera
        events_by_camera = {}
        if not camera_id:  # Only compute if not filtering by single camera
            camera_counts = db.query(
                MotionEvent.camera_id,
                func.count(MotionEvent.id).label('count')
            ).filter(
                MotionEvent.timestamp >= start_date
            ).group_by(MotionEvent.camera_id).all()

            events_by_camera = {
                camera_id: count for camera_id, count in camera_counts
            }
        else:
            events_by_camera[camera_id] = total_events

        # Events by hour (0-23)
        # Extract hour from timestamp and count
        hour_counts = db.query(
            func.extract('hour', MotionEvent.timestamp).label('hour'),
            func.count(MotionEvent.id).label('count')
        ).filter(
            and_(
                MotionEvent.timestamp >= start_date,
                MotionEvent.camera_id == camera_id if camera_id else True
            )
        ).group_by('hour').all()

        events_by_hour = {hour: 0 for hour in range(24)}  # Initialize all hours to 0
        for hour, count in hour_counts:
            events_by_hour[int(hour)] = count

        # Average confidence
        avg_confidence_result = db.query(
            func.avg(MotionEvent.confidence).label('avg_confidence')
        ).filter(
            and_(
                MotionEvent.timestamp >= start_date,
                MotionEvent.camera_id == camera_id if camera_id else True
            )
        ).first()

        average_confidence = float(avg_confidence_result.avg_confidence) if avg_confidence_result.avg_confidence else 0.0

        logger.info(
            f"Motion event stats: total={total_events}, cameras={len(events_by_camera)}, "
            f"avg_confidence={average_confidence:.3f}, days={days}"
        )

        return MotionEventStatsResponse(
            total_events=total_events,
            events_by_camera=events_by_camera,
            events_by_hour=events_by_hour,
            average_confidence=average_confidence
        )

    except Exception as e:
        logger.error(f"Failed to get motion event stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get motion event statistics"
        )
