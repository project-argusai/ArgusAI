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
from app.models.camera import Camera
from app.schemas.event import (
    EventCreate,
    EventResponse,
    EventListResponse,
    EventStatsResponse,
    EventFilterParams,
    ReanalyzeRequest
)
from app.schemas.system import CleanupResponse
from app.services.cleanup_service import get_cleanup_service
from app.models.event_feedback import EventFeedback
from app.schemas.feedback import FeedbackCreate, FeedbackUpdate, FeedbackResponse

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger(f"{__name__}.audit")  # Dedicated audit logger for compliance

router = APIRouter(prefix="/events", tags=["events"])

# Thumbnail storage directory
THUMBNAIL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'thumbnails')


def _save_thumbnail_to_filesystem(thumbnail_base64: str, event_id: str) -> str:
    """
    Save base64-encoded thumbnail to filesystem

    Args:
        thumbnail_base64: Base64-encoded JPEG image (with or without data URI prefix)
        event_id: Event UUID for filename

    Returns:
        Relative path to saved thumbnail

    Raises:
        ValueError: If thumbnail data is invalid
    """
    try:
        # Strip data URI prefix if present (e.g., "data:image/jpeg;base64,")
        if thumbnail_base64.startswith('data:'):
            # Find the base64 data after the comma
            comma_idx = thumbnail_base64.find(',')
            if comma_idx != -1:
                thumbnail_base64 = thumbnail_base64[comma_idx + 1:]

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

        # Return relative path (without thumbnails/ prefix since the endpoint adds it)
        relative_path = f"{date_str}/{filename}"
        logger.debug(f"Saved thumbnail to thumbnails/{relative_path}")

        return relative_path

    except Exception as e:
        logger.error(f"Failed to save thumbnail for event {event_id}: {e}")
        raise ValueError(f"Invalid thumbnail data: {e}")


async def _broadcast_new_event(event_id: str, camera_id: str, description: str):
    """
    Broadcast new event notification via WebSocket.

    Notifies all connected dashboard clients that a new event was created.

    Args:
        event_id: UUID of the new event
        camera_id: Camera that captured the event
        description: Event description
    """
    try:
        from app.services.websocket_manager import get_websocket_manager

        ws_manager = get_websocket_manager()
        await ws_manager.broadcast({
            "type": "NEW_EVENT",
            "data": {
                "event_id": event_id,
                "camera_id": camera_id,
                "description": description[:100] if description else None,
            }
        })
        logger.debug(f"Broadcasted new event notification for {event_id}")
    except Exception as e:
        logger.warning(f"Failed to broadcast new event: {e}")


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

        # Broadcast new event to WebSocket clients for instant dashboard updates
        background_tasks.add_task(
            _broadcast_new_event,
            event_id,
            event_data.camera_id,
            event_data.description
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
    source_type: Optional[str] = Query(None, description="Filter by event source type: 'rtsp', 'usb', 'protect' (comma-separated for multiple)"),
    smart_detection_type: Optional[str] = Query(None, description="Filter by smart detection type: 'person', 'vehicle', 'package', 'animal', 'motion', 'ring' (comma-separated for multiple)"),
    # Story P3-7.6: Analysis mode filtering
    analysis_mode: Optional[str] = Query(None, description="Filter by analysis mode: 'single_frame', 'multi_frame', 'video_native' (comma-separated for multiple)"),
    has_fallback: Optional[bool] = Query(None, description="Filter events with fallback (True = has fallback_reason, False = no fallback)"),
    low_confidence: Optional[bool] = Query(None, description="Filter by low confidence flag (True = uncertain descriptions)"),
    # Story P4-7.3: Anomaly severity filtering
    anomaly_severity: Optional[str] = Query(None, description="Filter by anomaly severity: 'low', 'medium', 'high' (comma-separated for multiple)"),
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

        # Apply source type filter (Phase 2: UniFi Protect integration)
        if source_type:
            source_type_list = [src.strip().lower() for src in source_type.split(',')]
            # Validate source types
            valid_sources = {'rtsp', 'usb', 'protect'}
            source_type_list = [src for src in source_type_list if src in valid_sources]
            if source_type_list:
                if len(source_type_list) == 1:
                    query = query.filter(Event.source_type == source_type_list[0])
                else:
                    query = query.filter(Event.source_type.in_(source_type_list))

        # Apply smart detection type filter (Phase 2: Story P2-4.2)
        if smart_detection_type:
            detection_type_list = [dt.strip().lower() for dt in smart_detection_type.split(',')]
            # Validate detection types
            valid_detections = {'person', 'vehicle', 'package', 'animal', 'motion', 'ring'}
            detection_type_list = [dt for dt in detection_type_list if dt in valid_detections]
            if detection_type_list:
                # Special handling for 'ring' - filter by is_doorbell_ring column
                if 'ring' in detection_type_list:
                    ring_filter = Event.is_doorbell_ring == True
                    other_types = [dt for dt in detection_type_list if dt != 'ring']
                    if other_types:
                        # Combine ring filter with other smart detection types
                        if len(other_types) == 1:
                            query = query.filter(or_(ring_filter, Event.smart_detection_type == other_types[0]))
                        else:
                            query = query.filter(or_(ring_filter, Event.smart_detection_type.in_(other_types)))
                    else:
                        # Only filtering by ring
                        query = query.filter(ring_filter)
                else:
                    # No ring filter, just smart detection types
                    if len(detection_type_list) == 1:
                        query = query.filter(Event.smart_detection_type == detection_type_list[0])
                    else:
                        query = query.filter(Event.smart_detection_type.in_(detection_type_list))

        # Story P3-7.6: Apply analysis mode filter
        if analysis_mode:
            mode_list = [m.strip().lower() for m in analysis_mode.split(',')]
            # Validate analysis modes
            valid_modes = {'single_frame', 'multi_frame', 'video_native'}
            mode_list = [m for m in mode_list if m in valid_modes]
            if mode_list:
                if len(mode_list) == 1:
                    query = query.filter(Event.analysis_mode == mode_list[0])
                else:
                    query = query.filter(Event.analysis_mode.in_(mode_list))

        # Story P3-7.6: Apply fallback filter
        if has_fallback is not None:
            if has_fallback:
                # Events that fell back to a simpler mode (have fallback_reason)
                query = query.filter(Event.fallback_reason.isnot(None))
            else:
                # Events without fallback
                query = query.filter(Event.fallback_reason.is_(None))

        # Story P3-7.6: Apply low confidence filter
        if low_confidence is not None:
            query = query.filter(Event.low_confidence == low_confidence)

        # Story P4-7.3: Apply anomaly severity filter
        if anomaly_severity:
            severity_list = [s.strip().lower() for s in anomaly_severity.split(',')]
            # Validate severities
            valid_severities = {'low', 'medium', 'high'}
            severity_list = [s for s in severity_list if s in valid_severities]
            if severity_list:
                # Build filter based on score thresholds
                # low: < 0.3, medium: 0.3-0.6, high: > 0.6
                from app.services.anomaly_scoring_service import AnomalyScoringService
                low_threshold = AnomalyScoringService.LOW_THRESHOLD
                high_threshold = AnomalyScoringService.HIGH_THRESHOLD

                severity_filters = []
                for severity in severity_list:
                    if severity == 'low':
                        severity_filters.append(
                            and_(
                                Event.anomaly_score.isnot(None),
                                Event.anomaly_score < low_threshold
                            )
                        )
                    elif severity == 'medium':
                        severity_filters.append(
                            and_(
                                Event.anomaly_score >= low_threshold,
                                Event.anomaly_score < high_threshold
                            )
                        )
                    elif severity == 'high':
                        severity_filters.append(Event.anomaly_score >= high_threshold)

                if severity_filters:
                    query = query.filter(or_(*severity_filters))

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

        # FF-003: Fetch camera names for all events
        camera_ids = list(set(e.camera_id for e in events))
        camera_map = {}
        if camera_ids:
            cameras = db.query(Camera.id, Camera.name).filter(Camera.id.in_(camera_ids)).all()
            camera_map = {c.id: c.name for c in cameras}

        # Enrich events with camera_name and feedback
        enriched_events = []
        for event in events:
            event_dict = {
                "id": event.id,
                "camera_id": event.camera_id,
                "camera_name": camera_map.get(event.camera_id, f"Camera {event.camera_id[:8]}"),
                "timestamp": event.timestamp,
                "description": event.description,
                "confidence": event.confidence,
                "objects_detected": event.objects_detected,
                "thumbnail_path": event.thumbnail_path,
                "thumbnail_base64": event.thumbnail_base64,
                "alert_triggered": event.alert_triggered,
                "source_type": event.source_type,
                "protect_event_id": event.protect_event_id,
                "smart_detection_type": event.smart_detection_type,
                "is_doorbell_ring": event.is_doorbell_ring,
                "created_at": event.created_at,
                "correlation_group_id": event.correlation_group_id,
                "correlated_events": None,
                "provider_used": event.provider_used,
                "fallback_reason": event.fallback_reason,
                "analysis_mode": event.analysis_mode,
                "frame_count_used": event.frame_count_used,
                "audio_transcription": getattr(event, 'audio_transcription', None),
                "ai_confidence": event.ai_confidence,
                "low_confidence": event.low_confidence,
                "vague_reason": event.vague_reason,
                "reanalyzed_at": event.reanalyzed_at,
                "reanalysis_count": event.reanalysis_count or 0,
                # Story P7-2.1: Delivery carrier detection
                "delivery_carrier": getattr(event, 'delivery_carrier', None),
            }
            # BUG-004: Include feedback if exists so UI can show persisted state
            if event.feedback:
                event_dict["feedback"] = FeedbackResponse.model_validate(event.feedback)
            enriched_events.append(EventResponse(**event_dict))

        logger.info(
            f"Listed {len(events)} events (total={total_count}, filters: "
            f"camera={camera_id}, search={search_query}, limit={limit}, offset={offset})"
        )

        return EventListResponse(
            events=enriched_events,
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

# Story P7-2.4: Package Delivery Dashboard Widget Endpoint
@router.get("/packages/today")
def get_package_deliveries_today(
    db: Session = Depends(get_db)
):
    """
    Get today's package delivery summary for dashboard widget (Story P7-2.4)

    Returns a summary of package deliveries detected today, including:
    - Total count of package deliveries
    - Breakdown by carrier (FedEx, UPS, USPS, Amazon, DHL, unknown)
    - Recent 5 package delivery events with camera name and timestamp

    Package events are identified by:
    - smart_detection_type = 'package', OR
    - objects_detected contains 'package'

    Args:
        db: Database session

    Returns:
        PackageDeliveriesTodayResponse with total_count, by_carrier, and recent_events

    Examples:
        GET /events/packages/today

    Response:
        {
            "total_count": 5,
            "by_carrier": {"fedex": 2, "ups": 1, "amazon": 1, "unknown": 1},
            "recent_events": [...]
        }
    """
    from app.schemas.event import PackageDeliveriesTodayResponse, PackageEventSummary, CARRIER_DISPLAY_NAMES
    from collections import Counter

    try:
        # Calculate today's date range in UTC
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Query for package events today
        # Package events: smart_detection_type='package' OR objects_detected contains 'package'
        query = db.query(Event).filter(
            Event.timestamp >= today_start,
            Event.timestamp < today_end,
            or_(
                Event.smart_detection_type == 'package',
                Event.objects_detected.like('%"package"%')
            )
        ).order_by(desc(Event.timestamp))

        # Get all matching events
        all_package_events = query.all()
        total_count = len(all_package_events)

        # Count by carrier
        carrier_counts: Counter = Counter()
        for event in all_package_events:
            carrier = event.delivery_carrier if event.delivery_carrier else 'unknown'
            carrier_counts[carrier] += 1

        by_carrier = dict(carrier_counts)

        # Get camera names for recent events
        camera_ids = list(set(e.camera_id for e in all_package_events[:5]))
        camera_map = {}
        if camera_ids:
            cameras = db.query(Camera.id, Camera.name).filter(Camera.id.in_(camera_ids)).all()
            camera_map = {c.id: c.name for c in cameras}

        # Build recent events list (limit to 5)
        recent_events = []
        for event in all_package_events[:5]:
            carrier_code = event.delivery_carrier
            carrier_display = CARRIER_DISPLAY_NAMES.get(carrier_code, 'Unknown') if carrier_code else 'Unknown'

            recent_events.append(PackageEventSummary(
                id=event.id,
                timestamp=event.timestamp,
                delivery_carrier=carrier_code,
                delivery_carrier_display=carrier_display,
                camera_name=camera_map.get(event.camera_id, f"Camera {event.camera_id[:8]}"),
                thumbnail_path=event.thumbnail_path
            ))

        logger.info(
            f"Package deliveries today: total={total_count}, by_carrier={by_carrier}",
            extra={"total_count": total_count, "by_carrier": by_carrier}
        )

        return PackageDeliveriesTodayResponse(
            total_count=total_count,
            by_carrier=by_carrier,
            recent_events=recent_events
        )

    except Exception as e:
        logger.error(f"Failed to get package deliveries today: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get package deliveries"
        )


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


@router.delete("/bulk")
async def bulk_delete_events(
    event_ids: list[str] = Query(..., description="List of event UUIDs to delete"),
    db: Session = Depends(get_db)
):
    """
    Delete multiple events by ID (FF-010)

    Deletes multiple events and their associated thumbnails/frames in a single request.
    Supports batch deletion for bulk cleanup operations from the UI.

    Args:
        event_ids: List of event UUIDs to delete
        db: Database session

    Returns:
        Deletion statistics including count and space freed

    Raises:
        400: No event IDs provided or invalid IDs
        500: Deletion failed

    Example:
        DELETE /events/bulk?event_ids=123&event_ids=456&event_ids=789
    """
    try:
        if not event_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one event ID is required"
            )

        # Limit bulk deletion to 100 events per request to prevent abuse
        if len(event_ids) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 100 events can be deleted per request"
            )

        # Find all events that exist
        events = db.query(Event).filter(Event.id.in_(event_ids)).all()

        if not events:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No events found with the provided IDs"
            )

        deleted_count = 0
        thumbnails_deleted = 0
        frames_deleted = 0
        space_freed_bytes = 0

        # Delete thumbnails and frames for each event
        for event in events:
            # Delete thumbnail file if exists
            if event.thumbnail_path:
                thumbnail_file = os.path.join(THUMBNAIL_DIR, event.thumbnail_path)
                if os.path.exists(thumbnail_file):
                    try:
                        space_freed_bytes += os.path.getsize(thumbnail_file)
                        os.remove(thumbnail_file)
                        thumbnails_deleted += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete thumbnail {thumbnail_file}: {e}")

            # Delete frame files if event has frames (multi-frame analysis)
            if hasattr(event, 'frame_paths') and event.frame_paths:
                try:
                    frame_paths = json.loads(event.frame_paths) if isinstance(event.frame_paths, str) else event.frame_paths
                    frames_dir = os.path.join(os.path.dirname(THUMBNAIL_DIR), 'frames')
                    for frame_path in frame_paths:
                        frame_file = os.path.join(frames_dir, frame_path)
                        if os.path.exists(frame_file):
                            space_freed_bytes += os.path.getsize(frame_file)
                            os.remove(frame_file)
                            frames_deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to delete frames for event {event.id}: {e}")

            deleted_count += 1

        # Delete events from database
        db.query(Event).filter(Event.id.in_([e.id for e in events])).delete(synchronize_session=False)
        db.commit()

        space_freed_mb = round(space_freed_bytes / (1024 * 1024), 2)

        logger.info(
            f"Bulk delete complete: {deleted_count} events deleted, "
            f"{thumbnails_deleted} thumbnails, {frames_deleted} frames, {space_freed_mb} MB freed",
            extra={
                "deleted_count": deleted_count,
                "thumbnails_deleted": thumbnails_deleted,
                "frames_deleted": frames_deleted,
                "space_freed_mb": space_freed_mb,
                "requested_ids": len(event_ids)
            }
        )

        # Audit log
        audit_logger.warning(
            "AUDIT: Bulk event deletion completed",
            extra={
                "audit_event": "bulk_delete",
                "operation": "DELETE /events/bulk",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "parameters": {"event_ids_count": len(event_ids)},
                "result": {
                    "deleted_count": deleted_count,
                    "thumbnails_deleted": thumbnails_deleted,
                    "frames_deleted": frames_deleted,
                    "space_freed_mb": space_freed_mb
                },
                "source": "api_endpoint",
                "status": "success"
            }
        )

        return {
            "deleted_count": deleted_count,
            "thumbnails_deleted": thumbnails_deleted,
            "frames_deleted": frames_deleted,
            "space_freed_mb": space_freed_mb,
            "not_found_count": len(event_ids) - deleted_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bulk delete events: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete events"
        )


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete a single event by ID

    Deletes an event and its associated thumbnail/frame files.

    Args:
        event_id: Event UUID to delete
        db: Database session

    Returns:
        204 No Content on success

    Raises:
        404: Event not found
        500: Deletion failed

    Example:
        DELETE /events/123e4567-e89b-12d3-a456-426614174000
    """
    try:
        event = db.query(Event).filter(Event.id == event_id).first()

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        # Delete thumbnail file if exists
        if event.thumbnail_path:
            thumbnail_file = os.path.join(THUMBNAIL_DIR, event.thumbnail_path)
            if os.path.exists(thumbnail_file):
                try:
                    os.remove(thumbnail_file)
                    logger.debug(f"Deleted thumbnail for event {event_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete thumbnail {thumbnail_file}: {e}")

        # Delete frame files if event has frames
        if hasattr(event, 'frame_paths') and event.frame_paths:
            try:
                frame_paths = json.loads(event.frame_paths) if isinstance(event.frame_paths, str) else event.frame_paths
                frames_dir = os.path.join(os.path.dirname(THUMBNAIL_DIR), 'frames')
                for frame_path in frame_paths:
                    frame_file = os.path.join(frames_dir, frame_path)
                    if os.path.exists(frame_file):
                        os.remove(frame_file)
                        logger.debug(f"Deleted frame {frame_path} for event {event_id}")
            except Exception as e:
                logger.warning(f"Failed to delete frames for event {event_id}: {e}")

        # Delete event from database
        db.delete(event)
        db.commit()

        logger.info(f"Deleted event {event_id}")

        # Return 204 No Content (no response body)
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete event {event_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete event"
        )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    db: Session = Depends(get_db)
):
    """
    Get single event by ID

    Args:
        event_id: Event UUID
        db: Database session

    Returns:
        Event with full details including thumbnail, correlated events (Story P2-4.4),
        and matched entity (Story P4-3.3)

    Raises:
        404: Event not found
        500: Database error

    Example:
        GET /events/123e4567-e89b-12d3-a456-426614174000
    """
    from app.schemas.event import CorrelatedEventResponse, MatchedEntitySummary
    from app.services.entity_service import get_entity_service

    try:
        event = db.query(Event).filter(Event.id == event_id).first()

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        logger.debug(f"Retrieved event {event_id}")

        # Story P2-4.4: Populate correlated_events if event has correlation_group_id
        correlated_events = None
        if event.correlation_group_id:
            # Find all events in the same correlation group, excluding this event
            related_events = db.query(Event).filter(
                Event.correlation_group_id == event.correlation_group_id,
                Event.id != event_id
            ).all()

            if related_events:
                correlated_events = []
                for related in related_events:
                    # Get camera name
                    camera = db.query(Camera).filter(Camera.id == related.camera_id).first()
                    camera_name = camera.name if camera else f"Camera {related.camera_id[:8]}"

                    # Build thumbnail URL
                    thumbnail_url = None
                    if related.thumbnail_path:
                        thumbnail_url = f"/api/v1/thumbnails/{related.thumbnail_path}"

                    correlated_events.append(CorrelatedEventResponse(
                        id=related.id,
                        camera_name=camera_name,
                        thumbnail_url=thumbnail_url,
                        timestamp=related.timestamp
                    ))

        # FF-003: Get camera name for this event
        event_camera = db.query(Camera).filter(Camera.id == event.camera_id).first()
        event_camera_name = event_camera.name if event_camera else f"Camera {event.camera_id[:8]}"

        # Convert to dict and add correlated_events
        event_dict = {
            "id": event.id,
            "camera_id": event.camera_id,
            "camera_name": event_camera_name,
            "timestamp": event.timestamp,
            "description": event.description,
            "confidence": event.confidence,
            "objects_detected": event.objects_detected,
            "thumbnail_path": event.thumbnail_path,
            "thumbnail_base64": event.thumbnail_base64,
            "alert_triggered": event.alert_triggered,
            "source_type": event.source_type,
            "protect_event_id": event.protect_event_id,
            "smart_detection_type": event.smart_detection_type,
            "is_doorbell_ring": event.is_doorbell_ring,
            "created_at": event.created_at,
            "correlation_group_id": event.correlation_group_id,
            "correlated_events": correlated_events,
            "provider_used": event.provider_used,
            "fallback_reason": event.fallback_reason,
            "analysis_mode": event.analysis_mode,
            "frame_count_used": event.frame_count_used,
            "audio_transcription": getattr(event, 'audio_transcription', None),
            "ai_confidence": event.ai_confidence,
            "low_confidence": event.low_confidence,
            "vague_reason": event.vague_reason,
            "reanalyzed_at": event.reanalyzed_at,
            "reanalysis_count": event.reanalysis_count or 0,
            # Story P7-2.1: Delivery carrier detection
            "delivery_carrier": getattr(event, 'delivery_carrier', None),
        }

        # Story P4-3.3: Add matched entity if available (AC12)
        try:
            entity_service = get_entity_service()
            entity_data = await entity_service.get_entity_for_event(db, event_id)
            if entity_data:
                event_dict["matched_entity"] = MatchedEntitySummary(
                    id=entity_data["id"],
                    entity_type=entity_data["entity_type"],
                    name=entity_data["name"],
                    first_seen_at=entity_data["first_seen_at"],
                    occurrence_count=entity_data["occurrence_count"],
                    similarity_score=entity_data.get("similarity_score"),
                )
        except Exception as entity_error:
            logger.debug(f"Could not get entity for event {event_id}: {entity_error}")

        # Story P4-5.1: Add feedback if exists
        if event.feedback:
            event_dict["feedback"] = FeedbackResponse.model_validate(event.feedback)

        return EventResponse(**event_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get event {event_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get event"
        )


@router.post("/{event_id}/reanalyze", response_model=EventResponse)
async def reanalyze_event(
    event_id: str,
    request: ReanalyzeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Re-analyze an event with a different analysis mode (Story P3-6.4)

    Triggers re-analysis of an existing event using a different AI analysis mode.
    This is useful for improving low-confidence descriptions.

    Rate limiting: Max 3 re-analyses per event per hour.

    Args:
        event_id: Event UUID to re-analyze
        request: ReanalyzeRequest with analysis_mode
        background_tasks: FastAPI background tasks
        db: Database session

    Returns:
        Updated EventResponse with new description and confidence

    Raises:
        404: Event not found
        400: Invalid analysis mode for camera type
        429: Rate limit exceeded (max 3 per hour)
        500: Re-analysis failed

    Example:
        POST /events/123e4567-e89b-12d3-a456-426614174000/reanalyze
        {"analysis_mode": "multi_frame"}
    """
    from app.models.camera import Camera
    from app.services.ai_service import AIService
    from app.services.clip_service import ClipService
    from app.services.protect_service import ProtectService
    from app.services.frame_extractor import FrameExtractor
    from app.services.vagueness_detector import VaguenessDetector
    import cv2
    import numpy as np
    from pathlib import Path

    try:
        # 1. Find the event
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        # 2. Check rate limiting (max 3 per hour)
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        # Handle timezone-naive datetime from DB by making it aware
        reanalyzed_at = event.reanalyzed_at
        if reanalyzed_at and reanalyzed_at.tzinfo is None:
            reanalyzed_at = reanalyzed_at.replace(tzinfo=timezone.utc)
        if reanalyzed_at and reanalyzed_at > one_hour_ago:
            if event.reanalysis_count >= 3:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded: maximum 3 re-analyses per event per hour"
                )

        # 3. Get camera to determine available modes
        camera = db.query(Camera).filter(Camera.id == event.camera_id).first()
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Camera {event.camera_id} not found"
            )

        # 4. Validate analysis mode availability
        analysis_mode = request.analysis_mode
        source_type = event.source_type or camera.source_type or 'rtsp'

        # For RTSP/USB cameras, only single_frame is available
        if source_type in ['rtsp', 'usb'] and analysis_mode != 'single_frame':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Analysis mode '{analysis_mode}' is not available for {source_type} cameras. Only 'single_frame' is supported."
            )

        # 5. Get image/video for re-analysis
        image_base64 = None
        frames = []
        video_path = None

        if analysis_mode == 'single_frame':
            # Use stored thumbnail
            if event.thumbnail_base64:
                image_base64 = event.thumbnail_base64
            elif event.thumbnail_path:
                # Load thumbnail from file
                thumbnail_full_path = os.path.join(THUMBNAIL_DIR, event.thumbnail_path)
                if os.path.exists(thumbnail_full_path):
                    with open(thumbnail_full_path, 'rb') as f:
                        image_base64 = base64.b64encode(f.read()).decode('utf-8')
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Thumbnail not available for re-analysis"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No thumbnail available for re-analysis"
                )

        elif analysis_mode in ['multi_frame', 'video_native']:
            # For Protect cameras, download clip
            if source_type != 'protect':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Analysis mode '{analysis_mode}' requires a UniFi Protect camera"
                )

            # Get protect controller for this camera
            from app.models.protect_controller import ProtectController

            # Find controller by camera's protect_camera_id
            protect_camera_id = getattr(camera, 'protect_camera_id', None)
            controller_id = getattr(camera, 'controller_id', None)

            if not protect_camera_id or not controller_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Camera is not properly configured for Protect integration"
                )

            # Download clip for re-analysis
            protect_service = ProtectService()
            await protect_service.load_controllers_from_db(db)

            clip_service = ClipService(protect_service)

            # Determine clip time range (use event timestamp +/- 5 seconds)
            event_start = event.timestamp - timedelta(seconds=5)
            event_end = event.timestamp + timedelta(seconds=5)

            try:
                clip_path = await clip_service.download_clip(
                    controller_id=controller_id,
                    camera_id=protect_camera_id,
                    event_start=event_start,
                    event_end=event_end,
                    event_id=f"reanalyze_{event_id}"
                )

                if not clip_path or not clip_path.exists():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to download video clip for re-analysis"
                    )

                video_path = clip_path

            except Exception as e:
                logger.error(f"Failed to download clip for re-analysis: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to download video clip: {str(e)}"
                )

        # 6. Initialize AI service
        ai_service = AIService()
        await ai_service.load_api_keys_from_db(db)

        # 7. Perform re-analysis based on mode
        result = None
        frame_count_used = None

        if analysis_mode == 'single_frame' and image_base64:
            # Decode base64 to numpy array for AI service
            import io
            from PIL import Image as PILImage

            image_data = base64.b64decode(image_base64)
            pil_image = PILImage.open(io.BytesIO(image_data))
            frame = np.array(pil_image)
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            result = await ai_service.generate_description(
                frame=frame,
                camera_name=camera.name,
                timestamp=event.timestamp.isoformat(),
                detected_objects=json.loads(event.objects_detected) if isinstance(event.objects_detected, str) else event.objects_detected
            )

        elif analysis_mode == 'multi_frame' and video_path:
            # Extract frames and analyze
            frame_extractor = FrameExtractor()
            extracted_frames = await frame_extractor.extract_frames(
                video_path=video_path,
                max_frames=5,
                skip_blur=True
            )

            if not extracted_frames:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to extract frames from video clip"
                )

            frame_count_used = len(extracted_frames)

            # Convert frames to base64 for multi-image analysis
            frames_base64 = []
            for frame in extracted_frames:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                frames_base64.append(base64.b64encode(buffer).decode('utf-8'))

            result = await ai_service.describe_images(
                images_base64=frames_base64,
                camera_name=camera.name,
                timestamp=event.timestamp.isoformat(),
                detected_objects=json.loads(event.objects_detected) if isinstance(event.objects_detected, str) else event.objects_detected
            )

        elif analysis_mode == 'video_native' and video_path:
            # Native video analysis
            result = await ai_service.describe_video(
                video_path=str(video_path),
                camera_name=camera.name,
                timestamp=event.timestamp.isoformat(),
                detected_objects=json.loads(event.objects_detected) if isinstance(event.objects_detected, str) else event.objects_detected
            )

        if not result or not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI re-analysis failed"
            )

        # 8. Check for vagueness in new description
        vagueness_detector = VaguenessDetector()
        vague_result = vagueness_detector.is_vague(result.description)

        # Determine low_confidence flag
        ai_confidence = result.ai_confidence
        low_confidence = (ai_confidence is not None and ai_confidence < 50) or vague_result.is_vague

        # 9. Update event with new description
        event.description = result.description
        event.confidence = result.confidence
        event.ai_confidence = ai_confidence
        event.low_confidence = low_confidence
        event.vague_reason = vague_result.reason if vague_result.is_vague else None
        event.analysis_mode = analysis_mode
        event.provider_used = result.provider
        event.reanalyzed_at = datetime.now(timezone.utc)
        event.reanalysis_count = (event.reanalysis_count or 0) + 1

        if frame_count_used:
            event.frame_count_used = frame_count_used

        db.commit()
        db.refresh(event)

        logger.info(
            f"Event {event_id} re-analyzed successfully",
            extra={
                "event_type": "event_reanalyzed",
                "event_id": event_id,
                "analysis_mode": analysis_mode,
                "new_confidence": ai_confidence,
                "provider": result.provider,
                "reanalysis_count": event.reanalysis_count
            }
        )

        # 10. Clean up temporary clip if downloaded
        if video_path and video_path.exists():
            try:
                video_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up temp clip: {e}")

        # 11. Build response
        return EventResponse(
            id=event.id,
            camera_id=event.camera_id,
            timestamp=event.timestamp,
            description=event.description,
            confidence=event.confidence,
            objects_detected=json.loads(event.objects_detected) if isinstance(event.objects_detected, str) else event.objects_detected,
            thumbnail_path=event.thumbnail_path,
            thumbnail_base64=event.thumbnail_base64,
            alert_triggered=event.alert_triggered,
            source_type=event.source_type,
            protect_event_id=event.protect_event_id,
            smart_detection_type=event.smart_detection_type,
            is_doorbell_ring=event.is_doorbell_ring,
            created_at=event.created_at,
            correlation_group_id=event.correlation_group_id,
            correlated_events=None,
            provider_used=event.provider_used,
            fallback_reason=event.fallback_reason,
            analysis_mode=event.analysis_mode,
            frame_count_used=event.frame_count_used,
            audio_transcription=event.audio_transcription,
            ai_confidence=event.ai_confidence,
            low_confidence=event.low_confidence,
            vague_reason=event.vague_reason,
            reanalyzed_at=event.reanalyzed_at,
            reanalysis_count=event.reanalysis_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to re-analyze event {event_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Re-analysis failed: {str(e)}"
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


# ============================================================================
# Story P4-5.1: Event Feedback Endpoints
# ============================================================================

@router.post("/{event_id}/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    event_id: str,
    feedback_data: FeedbackCreate,
    db: Session = Depends(get_db)
):
    """
    Create feedback for an event (Story P4-5.1)

    Allows users to rate AI descriptions as helpful/not helpful and optionally
    provide correction text.

    Args:
        event_id: Event UUID
        feedback_data: Rating and optional correction
        db: Database session

    Returns:
        Created feedback with ID and timestamps

    Raises:
        404: Event not found
        409: Feedback already exists for this event
        500: Database error

    Example:
        POST /events/123/feedback
        {"rating": "helpful"}

        POST /events/123/feedback
        {"rating": "not_helpful", "correction": "This was actually a delivery driver"}
    """
    try:
        # Verify event exists
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        # Check if feedback already exists
        existing = db.query(EventFeedback).filter(EventFeedback.event_id == event_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Feedback already exists for this event. Use PUT to update."
            )

        # Create feedback with camera_id auto-populated from event (Story P4-5.2, AC7)
        feedback = EventFeedback(
            event_id=event_id,
            camera_id=event.camera_id,  # Denormalized for efficient aggregate queries
            rating=feedback_data.rating,
            correction=feedback_data.correction
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Created feedback for event {event_id}: rating={feedback_data.rating}, camera_id={event.camera_id}",
            extra={"event_id": event_id, "camera_id": event.camera_id, "rating": feedback_data.rating}
        )

        return FeedbackResponse.model_validate(feedback)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create feedback for event {event_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create feedback"
        )


@router.get("/{event_id}/feedback", response_model=FeedbackResponse)
async def get_feedback(
    event_id: str,
    db: Session = Depends(get_db)
):
    """
    Get feedback for an event (Story P4-5.1)

    Args:
        event_id: Event UUID
        db: Database session

    Returns:
        Feedback data if exists

    Raises:
        404: Event or feedback not found

    Example:
        GET /events/123/feedback
    """
    try:
        # Verify event exists
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        feedback = db.query(EventFeedback).filter(EventFeedback.event_id == event_id).first()
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No feedback found for event {event_id}"
            )

        return FeedbackResponse.model_validate(feedback)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get feedback for event {event_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get feedback"
        )


@router.put("/{event_id}/feedback", response_model=FeedbackResponse)
async def update_feedback(
    event_id: str,
    feedback_data: FeedbackUpdate,
    db: Session = Depends(get_db)
):
    """
    Update existing feedback for an event (Story P4-5.1)

    Args:
        event_id: Event UUID
        feedback_data: Updated rating and/or correction
        db: Database session

    Returns:
        Updated feedback

    Raises:
        404: Event or feedback not found
        500: Database error

    Example:
        PUT /events/123/feedback
        {"rating": "not_helpful", "correction": "Wrong description"}
    """
    try:
        # Verify event exists
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        feedback = db.query(EventFeedback).filter(EventFeedback.event_id == event_id).first()
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No feedback found for event {event_id}"
            )

        # Update fields if provided
        if feedback_data.rating is not None:
            feedback.rating = feedback_data.rating
        if feedback_data.correction is not None:
            feedback.correction = feedback_data.correction

        db.commit()
        db.refresh(feedback)

        logger.info(
            f"Updated feedback for event {event_id}",
            extra={"event_id": event_id, "rating": feedback.rating}
        )

        return FeedbackResponse.model_validate(feedback)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update feedback for event {event_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update feedback"
        )


@router.delete("/{event_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feedback(
    event_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete feedback for an event (Story P4-5.1)

    Args:
        event_id: Event UUID
        db: Database session

    Returns:
        204 No Content on success

    Raises:
        404: Event or feedback not found
        500: Database error

    Example:
        DELETE /events/123/feedback
    """
    try:
        # Verify event exists
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        feedback = db.query(EventFeedback).filter(EventFeedback.event_id == event_id).first()
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No feedback found for event {event_id}"
            )

        db.delete(feedback)
        db.commit()

        logger.info(f"Deleted feedback for event {event_id}")

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete feedback for event {event_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete feedback"
        )
