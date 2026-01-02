"""
Context API endpoints for Temporal Context Engine (Stories P4-3.1, P4-3.2, P4-3.3, P4-3.5, P4-7.2, P4-8.2, P9-4.6)

Provides endpoints for:
- Batch processing of embeddings for existing events
- Embedding status retrieval
- Similarity search for finding visually similar past events (P4-3.2)
- Entity management for recurring visitor detection (P4-3.3)
- Activity pattern retrieval for cameras (P4-3.5)
- Anomaly scoring for events (P4-7.2)
- Person matching for face recognition (P4-8.2)
- Entity adjustment history for ML training (P9-4.6)
"""
import base64
import logging
import os
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.event import Event
from app.models.event_embedding import EventEmbedding
from app.services.embedding_service import get_embedding_service, EmbeddingService
from app.services.similarity_service import get_similarity_service, SimilarityService
from app.services.entity_service import get_entity_service, EntityService
from app.services.pattern_service import get_pattern_service, PatternService
from app.services.anomaly_scoring_service import get_anomaly_scoring_service, AnomalyScoringService, AnomalyScoreResult
from app.services.person_matching_service import get_person_matching_service, PersonMatchingService
from app.models.camera import Camera

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/context", tags=["context"])


# Request/Response Models
class BatchEmbeddingRequest(BaseModel):
    """Request model for batch embedding generation."""
    limit: int = Field(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of events to process (max 100 per request)"
    )


class BatchEmbeddingResponse(BaseModel):
    """Response model for batch embedding generation."""
    processed: int = Field(description="Number of embeddings successfully generated")
    failed: int = Field(description="Number of embeddings that failed to generate")
    total: int = Field(description="Total number of events processed")
    remaining: int = Field(description="Number of events still without embeddings")


class EmbeddingStatusResponse(BaseModel):
    """Response model for embedding status."""
    event_id: str = Field(description="Event UUID")
    exists: bool = Field(description="Whether an embedding exists for this event")
    model_version: Optional[str] = Field(default=None, description="Model version used")
    created_at: Optional[str] = Field(default=None, description="When the embedding was created")


class EmbeddingStatsResponse(BaseModel):
    """Response model for embedding statistics."""
    total_events: int = Field(description="Total number of events in database")
    events_with_embeddings: int = Field(description="Number of events with embeddings")
    events_without_embeddings: int = Field(description="Number of events without embeddings")
    coverage_percent: float = Field(description="Percentage of events with embeddings")
    model_version: str = Field(description="Current model version")
    embedding_dimension: int = Field(description="Embedding vector dimension")


@router.post("/embeddings/batch", response_model=BatchEmbeddingResponse)
async def batch_generate_embeddings(
    request: BatchEmbeddingRequest = BatchEmbeddingRequest(),
    db: Session = Depends(get_db),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Generate embeddings for events that don't have them yet.

    AC8: Batch processing endpoint for generating embeddings on existing events
    AC9: Batch processing respects rate limiting (max 100 events per request)

    Args:
        request: Batch processing parameters (limit 1-100)
        db: Database session
        embedding_service: Embedding service instance

    Returns:
        BatchEmbeddingResponse with processed/failed/remaining counts
    """
    # AC9: Enforce max 100 events per request
    limit = min(request.limit, 100)

    # Find events without embeddings
    # Subquery to get event_ids that already have embeddings
    events_with_embeddings = db.query(EventEmbedding.event_id).subquery()

    # Get events that don't have embeddings and have thumbnails
    events_without_embeddings = db.query(Event).filter(
        ~Event.id.in_(events_with_embeddings),
        (Event.thumbnail_base64.isnot(None)) | (Event.thumbnail_path.isnot(None))
    ).limit(limit).all()

    processed = 0
    failed = 0

    for event in events_without_embeddings:
        try:
            # Get thumbnail bytes
            thumbnail_bytes = None

            if event.thumbnail_base64:
                # Use base64 thumbnail
                b64_str = event.thumbnail_base64
                if b64_str.startswith("data:"):
                    comma_idx = b64_str.find(",")
                    if comma_idx != -1:
                        b64_str = b64_str[comma_idx + 1:]
                thumbnail_bytes = base64.b64decode(b64_str)

            elif event.thumbnail_path:
                # AC10: Works for file-path thumbnails
                # Resolve file path (handle relative paths like /api/v1/thumbnails/...)
                if event.thumbnail_path.startswith("/api/v1/thumbnails/"):
                    # Extract date and filename from path
                    parts = event.thumbnail_path.split("/")
                    if len(parts) >= 5:
                        date_str = parts[-2]
                        filename = parts[-1]
                        file_path = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                            "data", "thumbnails", date_str, filename
                        )
                        if os.path.exists(file_path):
                            with open(file_path, "rb") as f:
                                thumbnail_bytes = f.read()

            if thumbnail_bytes:
                # Generate embedding
                embedding_vector = await embedding_service.generate_embedding(thumbnail_bytes)

                # Store embedding
                await embedding_service.store_embedding(
                    db=db,
                    event_id=event.id,
                    embedding=embedding_vector,
                )
                processed += 1
            else:
                # No valid thumbnail
                failed += 1
                logger.warning(
                    f"No valid thumbnail for event {event.id}",
                    extra={"event_id": event.id}
                )

        except Exception as e:
            failed += 1
            logger.error(
                f"Batch embedding failed for event {event.id}: {e}",
                extra={"event_id": event.id, "error": str(e)}
            )

    # Count remaining events without embeddings
    remaining = db.query(Event).filter(
        ~Event.id.in_(db.query(EventEmbedding.event_id)),
        (Event.thumbnail_base64.isnot(None)) | (Event.thumbnail_path.isnot(None))
    ).count()

    logger.info(
        f"Batch embedding complete: {processed} processed, {failed} failed, {remaining} remaining",
        extra={
            "event_type": "batch_embedding_complete",
            "processed": processed,
            "failed": failed,
            "remaining": remaining,
        }
    )

    return BatchEmbeddingResponse(
        processed=processed,
        failed=failed,
        total=len(events_without_embeddings),
        remaining=remaining,
    )


@router.get("/embeddings/{event_id}", response_model=EmbeddingStatusResponse)
async def get_embedding_status(
    event_id: str,
    db: Session = Depends(get_db),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Get embedding status for a specific event.

    AC12: API endpoint to check embedding status for an event

    Args:
        event_id: UUID of the event
        db: Database session
        embedding_service: Embedding service instance

    Returns:
        EmbeddingStatusResponse with embedding metadata

    Raises:
        404: If event not found
    """
    # Verify event exists
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Get embedding metadata
    embedding_meta = await embedding_service.get_embedding(db, event_id)

    if embedding_meta:
        return EmbeddingStatusResponse(
            event_id=event_id,
            exists=True,
            model_version=embedding_meta["model_version"],
            created_at=embedding_meta["created_at"],
        )
    else:
        return EmbeddingStatusResponse(
            event_id=event_id,
            exists=False,
            model_version=None,
            created_at=None,
        )


@router.get("/embeddings/stats", response_model=EmbeddingStatsResponse)
async def get_embedding_stats(
    db: Session = Depends(get_db),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Get statistics about embedding coverage.

    Returns counts of events with/without embeddings and coverage percentage.

    Args:
        db: Database session
        embedding_service: Embedding service instance

    Returns:
        EmbeddingStatsResponse with coverage statistics
    """
    total_events = db.query(Event).count()
    events_with_embeddings = db.query(EventEmbedding).count()
    events_without = total_events - events_with_embeddings

    coverage = (events_with_embeddings / total_events * 100) if total_events > 0 else 0.0

    return EmbeddingStatsResponse(
        total_events=total_events,
        events_with_embeddings=events_with_embeddings,
        events_without_embeddings=events_without,
        coverage_percent=round(coverage, 2),
        model_version=embedding_service.get_model_version(),
        embedding_dimension=embedding_service.get_embedding_dimension(),
    )


# Story P4-3.2: Similarity Search Response Models
class SimilarEventResponse(BaseModel):
    """Response model for a similar event."""
    event_id: str = Field(description="UUID of the similar event")
    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Cosine similarity score (0.0 to 1.0, higher is more similar)"
    )
    thumbnail_url: Optional[str] = Field(
        default=None,
        description="URL to event thumbnail image"
    )
    description: str = Field(description="AI-generated description of the event")
    timestamp: datetime = Field(description="When the event occurred")
    camera_name: str = Field(description="Name of the camera that captured the event")
    camera_id: str = Field(description="UUID of the camera")


class SimilarEventsResponse(BaseModel):
    """Response model for similarity search results."""
    source_event_id: str = Field(description="UUID of the source event searched against")
    similar_events: list[SimilarEventResponse] = Field(
        description="List of similar events sorted by similarity score (highest first)"
    )
    total_results: int = Field(description="Number of similar events found")
    query_params: dict = Field(description="Query parameters used for the search")


@router.get("/similar/{event_id}", response_model=SimilarEventsResponse)
async def find_similar_events(
    event_id: str,
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of similar events to return"
    ),
    min_similarity: float = Query(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold (0.0 to 1.0)"
    ),
    time_window_days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of days to search back"
    ),
    camera_id: Optional[str] = Query(
        default=None,
        description="Optional camera UUID to filter results to same camera"
    ),
    db: Session = Depends(get_db),
    similarity_service: SimilarityService = Depends(get_similarity_service),
):
    """
    Find events visually similar to the specified event.

    Story P4-3.2: Similarity Search

    Uses CLIP embeddings and cosine similarity to find past events that look
    similar to the source event. Useful for identifying recurring visitors
    or patterns.

    Args:
        event_id: UUID of the source event to find similar events for
        limit: Maximum number of results (1-100, default 10)
        min_similarity: Minimum similarity threshold (0.0-1.0, default 0.7)
        time_window_days: Days to search back (1-365, default 30)
        camera_id: Optional camera filter
        db: Database session
        similarity_service: Similarity service instance

    Returns:
        SimilarEventsResponse with list of similar events

    Raises:
        404: If event not found or event has no embedding
    """
    # Verify event exists
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Check if embedding exists
    embedding = db.query(EventEmbedding).filter(
        EventEmbedding.event_id == event_id
    ).first()
    if not embedding:
        raise HTTPException(
            status_code=404,
            detail="Event has no embedding. Generate embeddings first using /context/embeddings/batch"
        )

    try:
        # Find similar events
        similar_events = await similarity_service.find_similar_events(
            db=db,
            event_id=event_id,
            limit=limit,
            min_similarity=min_similarity,
            time_window_days=time_window_days,
            camera_id=camera_id,
        )

        # Convert to response models
        similar_responses = [
            SimilarEventResponse(
                event_id=se.event_id,
                similarity_score=se.similarity_score,
                thumbnail_url=se.thumbnail_url,
                description=se.description,
                timestamp=se.timestamp,
                camera_name=se.camera_name,
                camera_id=se.camera_id,
            )
            for se in similar_events
        ]

        return SimilarEventsResponse(
            source_event_id=event_id,
            similar_events=similar_responses,
            total_results=len(similar_responses),
            query_params={
                "limit": limit,
                "min_similarity": min_similarity,
                "time_window_days": time_window_days,
                "camera_id": camera_id,
            },
        )

    except ValueError as e:
        # This shouldn't happen since we checked for embedding above,
        # but handle it gracefully
        logger.error(
            f"Similarity search failed: {e}",
            extra={"event_id": event_id, "error": str(e)}
        )
        raise HTTPException(status_code=404, detail=str(e))


# Story P4-3.3: Entity Management Response Models
class EntitySummary(BaseModel):
    """Summary of an entity for embedding in event responses."""
    id: str = Field(description="Entity UUID")
    entity_type: str = Field(description="Entity type: person, vehicle, or unknown")
    name: Optional[str] = Field(default=None, description="User-assigned name")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    occurrence_count: int = Field(description="Number of times this entity has been seen")
    similarity_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Match similarity score for this occurrence"
    )


class EntityResponse(BaseModel):
    """Response model for an entity."""
    id: str = Field(description="Entity UUID")
    entity_type: str = Field(description="Entity type: person, vehicle, or unknown")
    name: Optional[str] = Field(default=None, description="User-assigned name")
    notes: Optional[str] = Field(default=None, description="User notes about this entity")
    thumbnail_path: Optional[str] = Field(default=None, description="Path to entity thumbnail")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    last_seen_at: datetime = Field(description="Most recent occurrence timestamp")
    occurrence_count: int = Field(description="Number of times this entity has been seen")
    is_vip: bool = Field(default=False, description="VIP status for priority notifications")
    is_blocked: bool = Field(default=False, description="Blocked status to suppress notifications")


class EventSummaryForEntity(BaseModel):
    """Event summary for entity detail responses."""
    id: str = Field(description="Event UUID")
    timestamp: datetime = Field(description="Event timestamp")
    description: str = Field(description="AI-generated event description")
    thumbnail_url: Optional[str] = Field(default=None, description="Thumbnail URL")
    camera_id: str = Field(description="Camera UUID")
    similarity_score: float = Field(description="Similarity score when matched")


class EntityDetailResponse(BaseModel):
    """Detailed entity response with recent events."""
    id: str = Field(description="Entity UUID")
    entity_type: str = Field(description="Entity type: person, vehicle, or unknown")
    name: Optional[str] = Field(default=None, description="User-assigned name")
    notes: Optional[str] = Field(default=None, description="User notes about this entity")
    thumbnail_path: Optional[str] = Field(default=None, description="Path to entity thumbnail")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    last_seen_at: datetime = Field(description="Most recent occurrence timestamp")
    occurrence_count: int = Field(description="Number of times this entity has been seen")
    is_vip: bool = Field(default=False, description="VIP status for priority notifications")
    is_blocked: bool = Field(default=False, description="Blocked status to suppress notifications")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Record update timestamp")
    recent_events: list[EventSummaryForEntity] = Field(
        default=[],
        description="Recent events associated with this entity"
    )


class EntityListResponse(BaseModel):
    """Response model for entity list."""
    entities: list[EntityResponse] = Field(description="List of entities")
    total: int = Field(description="Total entity count")


class EntityEventsResponse(BaseModel):
    """Response model for paginated entity events (Story P9-4.2)."""
    entity_id: str = Field(description="Entity UUID")
    events: list[EventSummaryForEntity] = Field(description="List of events for this entity")
    total: int = Field(description="Total event count for this entity")
    page: int = Field(description="Current page number (1-indexed)")
    limit: int = Field(description="Events per page")
    has_more: bool = Field(description="Whether more events exist beyond current page")


class EntityCreateRequest(BaseModel):
    """Request model for creating an entity (Story P7-4.1, P10-4.2)."""
    entity_type: str = Field(
        description="Entity type: person, vehicle, or unknown"
    )
    name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Name for the entity"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Notes about this entity"
    )
    is_vip: bool = Field(
        default=False,
        description="VIP status for priority notifications"
    )
    is_blocked: bool = Field(
        default=False,
        description="Blocked status to suppress notifications"
    )
    # Story P10-4.2: Vehicle-specific fields for manual entity creation
    vehicle_color: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Vehicle color (e.g., 'white', 'black', 'silver')"
    )
    vehicle_make: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Vehicle make (e.g., 'toyota', 'ford', 'honda')"
    )
    vehicle_model: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Vehicle model (e.g., 'camry', 'f150', 'civic')"
    )
    reference_image: Optional[str] = Field(
        default=None,
        description="Base64 encoded reference image (max 2MB, jpeg/png/webp)"
    )


class EntityUpdateRequest(BaseModel):
    """Request model for updating an entity (Story P16-3.1)."""
    name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="New name for the entity"
    )
    entity_type: Optional[Literal["person", "vehicle", "unknown"]] = Field(
        default=None,
        description="Entity type (person, vehicle, or unknown)"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Notes about this entity"
    )
    is_vip: Optional[bool] = Field(
        default=None,
        description="VIP status for priority notifications"
    )
    is_blocked: Optional[bool] = Field(
        default=None,
        description="Blocked status to suppress notifications"
    )


@router.get("/entities", response_model=EntityListResponse)
async def list_entities(
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of entities to return"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Pagination offset"
    ),
    entity_type: Optional[str] = Query(
        default=None,
        description="Filter by entity type (person, vehicle)"
    ),
    named_only: bool = Query(
        default=False,
        description="Only return named entities"
    ),
    search: Optional[str] = Query(
        default=None,
        description="Search by entity name (case-insensitive partial match)"
    ),
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Get all recognized entities with pagination.

    Story P4-3.3: Recurring Visitor Detection (AC7)
    Story P7-4.2: Search functionality added

    Returns a list of all entities that have been recognized, sorted by
    most recently seen. Supports filtering by type, named-only, and search.

    Args:
        limit: Maximum number of entities (1-100, default 50)
        offset: Pagination offset
        entity_type: Filter by entity type
        named_only: Only return entities that have been named
        search: Search string to filter by name
        db: Database session
        entity_service: Entity service instance

    Returns:
        EntityListResponse with entities and total count
    """
    entities, total = await entity_service.get_all_entities(
        db=db,
        limit=limit,
        offset=offset,
        entity_type=entity_type,
        named_only=named_only,
        search=search,
    )

    return EntityListResponse(
        entities=[EntityResponse(**e) for e in entities],
        total=total,
    )


@router.post("/entities", response_model=EntityDetailResponse, status_code=201)
async def create_entity(
    request: EntityCreateRequest,
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Create a new entity manually.

    Story P7-4.1: Design Entities Data Model (AC4)
    Story P10-4.2: Implement Manual Entity Creation

    Allows manual creation of entities (person, vehicle) before automatic
    recognition assigns them. Useful for pre-registering known individuals
    or vehicles.

    For vehicle entities, vehicle_color, vehicle_make, and vehicle_model
    can be specified. At least color+make or make+model is recommended.
    A vehicle_signature is auto-generated from these fields.

    Args:
        request: Entity creation parameters
        db: Database session
        entity_service: Entity service instance

    Returns:
        EntityDetailResponse with created entity details

    Raises:
        HTTPException 400: If vehicle entity missing required fields
    """
    # Story P10-4.2: Validate vehicle entities have at least some vehicle data
    if request.entity_type == "vehicle":
        has_color_make = request.vehicle_color and request.vehicle_make
        has_make_model = request.vehicle_make and request.vehicle_model
        if not (has_color_make or has_make_model):
            raise HTTPException(
                status_code=400,
                detail="Vehicle entities require at least color+make or make+model"
            )

    entity = await entity_service.create_entity(
        db=db,
        entity_type=request.entity_type,
        name=request.name,
        notes=request.notes,
        is_vip=request.is_vip,
        is_blocked=request.is_blocked,
        vehicle_color=request.vehicle_color,
        vehicle_make=request.vehicle_make,
        vehicle_model=request.vehicle_model,
        reference_image=request.reference_image,
    )

    return EntityDetailResponse(
        id=entity["id"],
        entity_type=entity["entity_type"],
        name=entity["name"],
        notes=entity["notes"],
        thumbnail_path=entity["thumbnail_path"],
        first_seen_at=entity["first_seen_at"],
        last_seen_at=entity["last_seen_at"],
        occurrence_count=entity["occurrence_count"],
        is_vip=entity["is_vip"],
        is_blocked=entity["is_blocked"],
        created_at=entity["created_at"],
        updated_at=entity["updated_at"],
        recent_events=[],
    )


# =============================================================================
# VIP and Blocked Entity List Endpoints (Story P4-8.4)
# IMPORTANT: These routes MUST be defined before /entities/{entity_id}
# =============================================================================


class EntityListItem(BaseModel):
    """Single entity in VIP/blocked list."""
    id: str = Field(description="Entity UUID")
    entity_type: str = Field(description="Entity type: 'person' or 'vehicle'")
    name: Optional[str] = Field(default=None, description="Entity name")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    last_seen_at: datetime = Field(description="Most recent occurrence timestamp")
    occurrence_count: int = Field(description="Number of times seen")
    is_vip: bool = Field(default=False, description="VIP status")
    is_blocked: bool = Field(default=False, description="Blocked status")


class VipBlockedEntityListResponse(BaseModel):
    """Response for VIP/blocked entity list endpoints."""
    entities: list[EntityListItem] = Field(description="List of entities")
    total: int = Field(description="Total count matching filter")
    limit: int = Field(description="Page size")
    offset: int = Field(description="Pagination offset")


@router.get("/entities/vip", response_model=VipBlockedEntityListResponse)
async def list_vip_entities(
    limit: int = Query(default=50, ge=1, le=100, description="Maximum entities to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """
    List all VIP entities (persons and vehicles).

    Story P4-8.4: Named Entity Alerts

    Returns all entities marked as VIP, sorted by last_seen_at descending.
    VIP entities trigger priority notifications with distinct styling.

    Args:
        limit: Maximum number of entities to return (1-100)
        offset: Pagination offset
        db: Database session

    Returns:
        VipBlockedEntityListResponse with list of VIP entities
    """
    from app.services.entity_alert_service import get_entity_alert_service

    entity_service = get_entity_alert_service()
    entities, total = await entity_service.get_all_vip_entities(
        db=db, limit=limit, offset=offset
    )

    return VipBlockedEntityListResponse(
        entities=[
            EntityListItem(
                id=e["id"],
                entity_type=e["entity_type"],
                name=e["name"],
                first_seen_at=e["first_seen_at"],
                last_seen_at=e["last_seen_at"],
                occurrence_count=e["occurrence_count"],
                is_vip=e["is_vip"],
                is_blocked=e["is_blocked"],
            )
            for e in entities
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/entities/blocked", response_model=VipBlockedEntityListResponse)
async def list_blocked_entities(
    limit: int = Query(default=50, ge=1, le=100, description="Maximum entities to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """
    List all blocked entities (persons and vehicles).

    Story P4-8.4: Named Entity Alerts

    Returns all entities on the blocklist, sorted by last_seen_at descending.
    Blocked entities have their notifications suppressed, but events are
    still recorded in the system.

    Args:
        limit: Maximum number of entities to return (1-100)
        offset: Pagination offset
        db: Database session

    Returns:
        VipBlockedEntityListResponse with list of blocked entities
    """
    from app.services.entity_alert_service import get_entity_alert_service

    entity_service = get_entity_alert_service()
    entities, total = await entity_service.get_all_blocked_entities(
        db=db, limit=limit, offset=offset
    )

    return VipBlockedEntityListResponse(
        entities=[
            EntityListItem(
                id=e["id"],
                entity_type=e["entity_type"],
                name=e["name"],
                first_seen_at=e["first_seen_at"],
                last_seen_at=e["last_seen_at"],
                occurrence_count=e["occurrence_count"],
                is_vip=e["is_vip"],
                is_blocked=e["is_blocked"],
            )
            for e in entities
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/entities/{entity_id}", response_model=EntityDetailResponse)
async def get_entity(
    entity_id: str,
    event_limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of recent events to include"
    ),
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Get a single entity with its associated events.

    Story P4-3.3: Recurring Visitor Detection (AC8)

    Returns detailed information about an entity, including recent events
    that have been associated with it.

    Args:
        entity_id: UUID of the entity
        event_limit: Maximum number of recent events (1-50, default 10)
        db: Database session
        entity_service: Entity service instance

    Returns:
        EntityDetailResponse with entity details and recent events

    Raises:
        404: If entity not found
    """
    entity = await entity_service.get_entity(
        db=db,
        entity_id=entity_id,
        include_events=True,
        event_limit=event_limit,
    )

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return EntityDetailResponse(
        id=entity["id"],
        entity_type=entity["entity_type"],
        name=entity["name"],
        notes=entity.get("notes"),
        thumbnail_path=entity.get("thumbnail_path"),
        first_seen_at=entity["first_seen_at"],
        last_seen_at=entity["last_seen_at"],
        occurrence_count=entity["occurrence_count"],
        is_vip=entity.get("is_vip", False),
        is_blocked=entity.get("is_blocked", False),
        created_at=entity["created_at"],
        updated_at=entity["updated_at"],
        recent_events=[
            EventSummaryForEntity(
                id=e["id"],
                timestamp=e["timestamp"],
                description=e["description"],
                thumbnail_url=e["thumbnail_url"],
                camera_id=e["camera_id"],
                similarity_score=e["similarity_score"],
            )
            for e in entity.get("recent_events", [])
        ],
    )


@router.get("/entities/{entity_id}/events", response_model=EntityEventsResponse)
async def get_entity_events(
    entity_id: str,
    page: int = Query(
        default=1,
        ge=1,
        description="Page number (1-indexed)"
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=50,
        description="Number of events per page"
    ),
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Get paginated events for an entity.

    Story P9-4.2: Build Entity Event List View

    Returns paginated list of events associated with an entity,
    sorted by timestamp descending (newest first).

    Args:
        entity_id: UUID of the entity
        page: Page number (1-indexed, default 1)
        limit: Events per page (1-50, default 20)
        db: Database session
        entity_service: Entity service instance

    Returns:
        EntityEventsResponse with paginated events and metadata

    Raises:
        404: If entity not found
    """
    # Verify entity exists
    entity = await entity_service.get_entity(
        db=db,
        entity_id=entity_id,
        include_events=False,
    )

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Get paginated events
    offset = (page - 1) * limit
    events_data = await entity_service.get_entity_events_paginated(
        db=db,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )

    events = events_data.get("events", [])
    total = events_data.get("total", 0)

    return EntityEventsResponse(
        entity_id=entity_id,
        events=[
            EventSummaryForEntity(
                id=e["id"],
                timestamp=e["timestamp"],
                description=e["description"],
                thumbnail_url=e["thumbnail_url"],
                camera_id=e["camera_id"],
                similarity_score=e.get("similarity_score", 0.0),
            )
            for e in events
        ],
        total=total,
        page=page,
        limit=limit,
        has_more=(offset + len(events)) < total,
    )


class UnlinkEventResponse(BaseModel):
    """Response for event unlink operation (Story P9-4.3)."""
    success: bool
    message: str


class AssignEventRequest(BaseModel):
    """Request for event assignment operation (Story P9-4.4)."""
    entity_id: str = Field(description="UUID of the entity to assign the event to")


class AssignEventResponse(BaseModel):
    """Response for event assignment operation (Story P9-4.4)."""
    success: bool = Field(description="Whether the operation succeeded")
    message: str = Field(description="Human-readable result message")
    action: str = Field(description="Action taken: 'assign', 'move', or 'none'")
    entity_id: str = Field(description="UUID of the target entity")
    entity_name: Optional[str] = Field(default=None, description="Name of the target entity")


@router.post("/events/{event_id}/entity", response_model=AssignEventResponse)
async def assign_event_to_entity(
    event_id: str,
    request: AssignEventRequest,
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Assign or move an event to an entity.

    Story P9-4.4: Implement Event-Entity Assignment

    If the event has no entity, assigns it to the specified entity.
    If the event already has an entity, moves it to the new entity.
    Creates EntityAdjustment record(s) for ML training.

    Args:
        event_id: UUID of the event to assign
        request: Request body with target entity_id
        db: Database session
        entity_service: Entity service instance

    Returns:
        AssignEventResponse with success status, message, and entity info

    Raises:
        404: If event or entity not found
    """
    try:
        result = await entity_service.assign_event(
            db=db,
            event_id=event_id,
            entity_id=request.entity_id,
        )
        return AssignEventResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/entities/{entity_id}/events/{event_id}", response_model=UnlinkEventResponse)
async def unlink_event_from_entity(
    entity_id: str,
    event_id: str,
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Unlink an event from an entity.

    Story P9-4.3: Implement Event-Entity Unlinking

    Removes the association between an event and an entity. This does NOT
    delete the event itself, only the EntityEvent junction record. Also
    creates an EntityAdjustment record for ML training.

    Args:
        entity_id: UUID of the entity
        event_id: UUID of the event to unlink
        db: Database session
        entity_service: Entity service instance

    Returns:
        UnlinkEventResponse with success status and message

    Raises:
        404: If entity or event link not found
    """
    # Verify entity exists
    entity = await entity_service.get_entity(
        db=db,
        entity_id=entity_id,
        include_events=False,
    )

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Attempt to unlink the event
    success = await entity_service.unlink_event(
        db=db,
        entity_id=entity_id,
        event_id=event_id,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Event not linked to this entity"
        )

    return UnlinkEventResponse(
        success=True,
        message="Event removed from entity"
    )


@router.get("/entities/{entity_id}/thumbnail")
async def get_entity_thumbnail(
    entity_id: str,
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Get thumbnail image for an entity.

    Story P7-4.1: Design Entities Data Model (AC4)

    Returns the entity's thumbnail image as JPEG. If no thumbnail exists,
    returns 404.

    Args:
        entity_id: UUID of the entity
        db: Database session
        entity_service: Entity service instance

    Returns:
        JPEG image response

    Raises:
        404: If entity not found or has no thumbnail
    """
    from fastapi.responses import FileResponse

    thumbnail_path = await entity_service.get_entity_thumbnail_path(db, entity_id)

    if not thumbnail_path:
        raise HTTPException(
            status_code=404,
            detail="Entity not found or has no thumbnail"
        )

    # Validate path to prevent directory traversal
    if ".." in thumbnail_path:
        raise HTTPException(status_code=400, detail="Invalid thumbnail path")

    # Resolve to full path if needed
    import os
    if not os.path.isabs(thumbnail_path):
        # Assume relative to data directory
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        thumbnail_path = os.path.join(base_path, "data", thumbnail_path)

    if not os.path.exists(thumbnail_path):
        raise HTTPException(status_code=404, detail="Thumbnail file not found")

    return FileResponse(
        thumbnail_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=3600"}
    )


@router.put("/entities/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: str,
    request: EntityUpdateRequest,
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Update an entity's metadata.

    Story P4-3.3: Recurring Visitor Detection (AC9)
    Story P7-4.1: Design Entities Data Model (AC4)
    Story P16-3.1: Create Entity Update API Endpoint

    Allows users to update entity properties including name, entity_type, notes,
    VIP status, and blocked status. Partial updates are supported - only provided
    fields are updated.

    Args:
        entity_id: UUID of the entity
        request: Update request with new values (all fields optional)
        db: Database session
        entity_service: Entity service instance

    Returns:
        Updated EntityResponse

    Raises:
        404: If entity not found
        422: If entity_type is invalid
    """
    entity = await entity_service.update_entity(
        db=db,
        entity_id=entity_id,
        name=request.name,
        entity_type=request.entity_type,
        notes=request.notes,
        is_vip=request.is_vip,
        is_blocked=request.is_blocked,
    )

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return EntityResponse(**entity)


@router.delete("/entities/{entity_id}", status_code=204)
async def delete_entity(
    entity_id: str,
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Delete an entity.

    Story P4-3.3: Recurring Visitor Detection (AC10)

    Deletes an entity and unlinks all associated events. Events themselves
    are not deleted, only the entity-event associations.

    Args:
        entity_id: UUID of the entity
        db: Database session
        entity_service: Entity service instance

    Raises:
        404: If entity not found
    """
    deleted = await entity_service.delete_entity(db=db, entity_id=entity_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Return 204 No Content on success (implicit)


# Story P9-4.5: Merge Entities Request/Response Models
class MergeEntitiesRequest(BaseModel):
    """Request model for merging two entities (Story P9-4.5)."""
    primary_entity_id: str = Field(
        description="UUID of the entity to keep (receives all events)"
    )
    secondary_entity_id: str = Field(
        description="UUID of the entity to merge into primary and delete"
    )


class MergeEntitiesResponse(BaseModel):
    """Response model for entity merge operation (Story P9-4.5)."""
    success: bool = Field(description="Whether the merge succeeded")
    merged_entity_id: str = Field(description="UUID of the primary entity that was kept")
    merged_entity_name: Optional[str] = Field(
        default=None, description="Name of the primary entity"
    )
    events_moved: int = Field(description="Number of events moved to primary entity")
    deleted_entity_id: str = Field(description="UUID of the deleted secondary entity")
    deleted_entity_name: Optional[str] = Field(
        default=None, description="Name of the deleted entity"
    )
    message: str = Field(description="Human-readable result message")


# Story P9-4.6: Entity Adjustment Response Models
class AdjustmentResponse(BaseModel):
    """Response model for a single entity adjustment record."""
    id: str = Field(description="UUID of the adjustment record")
    event_id: str = Field(description="UUID of the event that was adjusted")
    old_entity_id: Optional[str] = Field(
        default=None, description="UUID of the entity before adjustment (null for new assignments)"
    )
    new_entity_id: Optional[str] = Field(
        default=None, description="UUID of the entity after adjustment (null for unlinks)"
    )
    action: str = Field(description="Type of adjustment: unlink, assign, move_from, move_to, merge")
    event_description: Optional[str] = Field(
        default=None, description="Snapshot of event description at time of adjustment"
    )
    created_at: datetime = Field(description="When the adjustment was made")


class AdjustmentListResponse(BaseModel):
    """Response model for paginated list of entity adjustments (Story P9-4.6)."""
    adjustments: list[AdjustmentResponse] = Field(
        description="List of adjustment records"
    )
    total: int = Field(description="Total number of adjustments matching filters")
    page: int = Field(description="Current page number (1-indexed)")
    limit: int = Field(description="Number of items per page")


@router.post("/entities/merge", response_model=MergeEntitiesResponse)
async def merge_entities(
    request: MergeEntitiesRequest,
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Merge two entities into one (Story P9-4.5).

    Moves all events from the secondary entity to the primary entity,
    creates adjustment records for ML training, updates occurrence counts,
    and deletes the secondary entity.

    Args:
        request: Merge request with primary and secondary entity IDs
        db: Database session
        entity_service: Entity service instance

    Returns:
        MergeEntitiesResponse with merge results

    Raises:
        400: If attempting to merge an entity with itself
        404: If either entity not found
    """
    try:
        result = await entity_service.merge_entities(
            db=db,
            primary_entity_id=request.primary_entity_id,
            secondary_entity_id=request.secondary_entity_id,
        )
        return MergeEntitiesResponse(**result)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)


# Story P4-3.5: Pattern Detection Response Models
# Story P4-7.1: Extended with object type distribution
class PatternResponse(BaseModel):
    """Response model for camera activity patterns."""
    camera_id: str = Field(description="UUID of the camera")
    hourly_distribution: dict[str, int] = Field(
        description="Events per hour (0-23) across all days"
    )
    daily_distribution: dict[str, int] = Field(
        description="Events per day-of-week (0=Monday, 6=Sunday)"
    )
    peak_hours: list[str] = Field(
        description="Hours with above-average activity (zero-padded, e.g., '09', '14', '17')"
    )
    quiet_hours: list[str] = Field(
        description="Hours with minimal activity (zero-padded, e.g., '02', '03', '04')"
    )
    average_events_per_day: float = Field(description="Mean daily event count")
    last_calculated_at: datetime = Field(description="When patterns were last calculated")
    calculation_window_days: int = Field(description="Number of days used for calculation")
    insufficient_data: bool = Field(
        default=False,
        description="True if camera has insufficient history for meaningful patterns"
    )
    # Story P4-7.1: Object type distribution for anomaly detection
    object_type_distribution: Optional[dict[str, int]] = Field(
        default=None,
        description="Object type counts, e.g., {'person': 150, 'vehicle': 45, 'package': 12}"
    )
    dominant_object_type: Optional[str] = Field(
        default=None,
        description="Most frequently detected object type"
    )


class RecalculatePatternResponse(BaseModel):
    """Response model for pattern recalculation."""
    camera_id: str = Field(description="UUID of the camera")
    success: bool = Field(description="Whether recalculation succeeded")
    message: str = Field(description="Status message")
    insufficient_data: bool = Field(
        default=False,
        description="True if camera has insufficient history"
    )


class BatchPatternResponse(BaseModel):
    """Response model for batch pattern calculation."""
    total_cameras: int = Field(description="Total cameras processed")
    patterns_calculated: int = Field(description="Patterns successfully calculated")
    patterns_skipped: int = Field(description="Patterns skipped (insufficient data)")
    elapsed_ms: float = Field(description="Total processing time in milliseconds")


@router.get("/patterns/{camera_id}", response_model=PatternResponse)
async def get_camera_patterns(
    camera_id: str,
    db: Session = Depends(get_db),
    pattern_service: PatternService = Depends(get_pattern_service),
):
    """
    Get activity patterns for a camera.

    Story P4-3.5: Pattern Detection (AC10, AC11)

    Returns pre-calculated time-based activity patterns including hourly and
    daily distributions, peak hours, quiet hours, and average events per day.

    Patterns are recalculated hourly and enable AI descriptions to include
    timing context like "Typical activity time" or "Unusual timing".

    Args:
        camera_id: UUID of the camera
        db: Database session
        pattern_service: Pattern service instance

    Returns:
        PatternResponse with activity patterns

    Raises:
        404: If camera not found or no patterns available
    """
    # Verify camera exists
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Get patterns
    pattern_data = await pattern_service.get_patterns(db, camera_id)

    if not pattern_data:
        # Camera exists but no patterns (insufficient data)
        raise HTTPException(
            status_code=404,
            detail="No activity patterns available for this camera. Patterns require at least 10 events over 7+ days."
        )

    return PatternResponse(
        camera_id=pattern_data.camera_id,
        hourly_distribution=pattern_data.hourly_distribution,
        daily_distribution=pattern_data.daily_distribution,
        peak_hours=pattern_data.peak_hours,
        quiet_hours=pattern_data.quiet_hours,
        average_events_per_day=pattern_data.average_events_per_day,
        last_calculated_at=pattern_data.last_calculated_at,
        calculation_window_days=pattern_data.calculation_window_days,
        insufficient_data=pattern_data.insufficient_data,
        object_type_distribution=pattern_data.object_type_distribution,
        dominant_object_type=pattern_data.dominant_object_type,
    )


@router.post("/patterns/{camera_id}/recalculate", response_model=RecalculatePatternResponse)
async def recalculate_camera_patterns(
    camera_id: str,
    window_days: int = Query(
        default=30,
        ge=7,
        le=365,
        description="Number of days to analyze"
    ),
    db: Session = Depends(get_db),
    pattern_service: PatternService = Depends(get_pattern_service),
):
    """
    Force recalculation of activity patterns for a camera.

    Story P4-3.5: Pattern Detection (AC15)

    Immediately recalculates patterns regardless of when they were last
    calculated. Useful for testing or after significant event activity changes.

    Args:
        camera_id: UUID of the camera
        window_days: Number of days to analyze (7-365, default 30)
        db: Database session
        pattern_service: Pattern service instance

    Returns:
        RecalculatePatternResponse with status

    Raises:
        404: If camera not found
    """
    # Verify camera exists
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Force recalculation
    pattern = await pattern_service.recalculate_patterns(
        db=db,
        camera_id=camera_id,
        window_days=window_days,
        force=True
    )

    if pattern:
        return RecalculatePatternResponse(
            camera_id=camera_id,
            success=True,
            message=f"Patterns recalculated using {window_days}-day window",
            insufficient_data=False,
        )
    else:
        return RecalculatePatternResponse(
            camera_id=camera_id,
            success=False,
            message="Insufficient data for pattern calculation. Requires at least 10 events over 7+ days.",
            insufficient_data=True,
        )


@router.post("/patterns/batch", response_model=BatchPatternResponse)
async def batch_recalculate_patterns(
    window_days: int = Query(
        default=30,
        ge=7,
        le=365,
        description="Number of days to analyze"
    ),
    db: Session = Depends(get_db),
    pattern_service: PatternService = Depends(get_pattern_service),
):
    """
    Recalculate activity patterns for all enabled cameras.

    Story P4-3.5: Pattern Detection (AC9)

    Triggers batch pattern recalculation for all enabled cameras. This
    operation respects the rate limiting (skips cameras calculated within
    the last hour unless forced).

    Args:
        window_days: Number of days to analyze (7-365, default 30)
        db: Database session
        pattern_service: Pattern service instance

    Returns:
        BatchPatternResponse with calculation statistics
    """
    result = await pattern_service.recalculate_all_patterns(
        db=db,
        window_days=window_days
    )

    return BatchPatternResponse(
        total_cameras=result["total_cameras"],
        patterns_calculated=result["patterns_calculated"],
        patterns_skipped=result["patterns_skipped"],
        elapsed_ms=result["elapsed_ms"],
    )


# Story P4-7.2: Anomaly Scoring Response Models
class AnomalyScoreResponse(BaseModel):
    """Response model for anomaly score calculation."""
    event_id: Optional[str] = Field(
        default=None,
        description="Event UUID (null for ad-hoc scoring)"
    )
    total_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Combined anomaly score (0.0=normal, 1.0=highly anomalous)"
    )
    timing_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Timing component score based on hourly patterns"
    )
    day_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Day-of-week component score"
    )
    object_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Object type component score"
    )
    severity: str = Field(
        description="Severity classification: 'low', 'medium', or 'high'"
    )
    has_baseline: bool = Field(
        description="Whether baseline patterns were available for scoring"
    )


class AnomalyScoreRequest(BaseModel):
    """Request model for ad-hoc anomaly scoring."""
    camera_id: str = Field(description="Camera UUID for baseline lookup")
    timestamp: datetime = Field(description="Event timestamp for timing analysis")
    objects_detected: list[str] = Field(
        default=[],
        description="List of detected object types (e.g., ['person', 'vehicle'])"
    )


@router.get("/anomaly/score/{event_id}", response_model=AnomalyScoreResponse)
async def score_event(
    event_id: str,
    db: Session = Depends(get_db),
    anomaly_service: AnomalyScoringService = Depends(get_anomaly_scoring_service),
):
    """
    Calculate and persist anomaly score for an existing event.

    Story P4-7.2: Anomaly Scoring (AC6, AC7)

    Calculates how unusual an event is compared to the camera's baseline
    activity patterns. Score is persisted to the event record.

    Scoring components:
    - Timing: Is this hour unusual for events? (40% weight)
    - Day: Is this day-of-week unusual? (20% weight)
    - Object: Are the detected objects unusual? (40% weight)

    Severity thresholds:
    - Low: score < 0.3
    - Medium: 0.3 <= score < 0.6
    - High: score >= 0.6

    Args:
        event_id: UUID of the event to score
        db: Database session
        anomaly_service: Anomaly scoring service instance

    Returns:
        AnomalyScoreResponse with detailed score breakdown

    Raises:
        404: If event not found
        500: If scoring fails
    """
    # Verify event exists
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Calculate and persist score
    result = await anomaly_service.score_event(db, event)

    if result is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to calculate anomaly score"
        )

    return AnomalyScoreResponse(
        event_id=event_id,
        total_score=result.total,
        timing_score=result.timing_score,
        day_score=result.day_score,
        object_score=result.object_score,
        severity=result.severity,
        has_baseline=result.has_baseline,
    )


@router.post("/anomaly/score", response_model=AnomalyScoreResponse)
async def calculate_anomaly_score(
    request: AnomalyScoreRequest,
    db: Session = Depends(get_db),
    pattern_service: PatternService = Depends(get_pattern_service),
    anomaly_service: AnomalyScoringService = Depends(get_anomaly_scoring_service),
):
    """
    Calculate anomaly score for arbitrary event data without persisting.

    Story P4-7.2: Anomaly Scoring (AC8)

    Useful for preview/testing of anomaly detection without creating events.
    Does not persist the score to any event record.

    Args:
        request: Anomaly score request with camera_id, timestamp, and objects
        db: Database session
        pattern_service: Pattern service for baseline lookup
        anomaly_service: Anomaly scoring service instance

    Returns:
        AnomalyScoreResponse with detailed score breakdown

    Raises:
        404: If camera not found
    """
    # Verify camera exists
    camera = db.query(Camera).filter(Camera.id == request.camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Get baseline patterns
    patterns = await pattern_service.get_patterns(db, request.camera_id)

    # Calculate score (without persisting)
    result = await anomaly_service.calculate_anomaly_score(
        patterns=patterns,
        event_timestamp=request.timestamp,
        objects_detected=request.objects_detected,
    )

    return AnomalyScoreResponse(
        event_id=None,
        total_score=result.total,
        timing_score=result.timing_score,
        day_score=result.day_score,
        object_score=result.object_score,
        severity=result.severity,
        has_baseline=result.has_baseline,
    )


# Story P4-8.1: Face Embedding API Endpoints
from app.services.face_embedding_service import get_face_embedding_service, FaceEmbeddingService


class FaceEmbeddingResponse(BaseModel):
    """Response model for a single face embedding."""
    id: str = Field(description="UUID of the face embedding")
    event_id: str = Field(description="UUID of the associated event")
    entity_id: Optional[str] = Field(default=None, description="UUID of linked entity (if any)")
    bounding_box: dict = Field(description="Face bounding box: {x, y, width, height}")
    confidence: float = Field(ge=0.0, le=1.0, description="Face detection confidence")
    model_version: str = Field(description="Model version used for embedding")
    created_at: str = Field(description="When the face embedding was created (ISO 8601)")


class FaceEmbeddingsResponse(BaseModel):
    """Response model for face embeddings list."""
    event_id: str = Field(description="UUID of the event")
    face_count: int = Field(description="Number of face embeddings")
    faces: list[FaceEmbeddingResponse] = Field(description="List of face embeddings")


class DeleteFacesResponse(BaseModel):
    """Response model for face deletion."""
    deleted_count: int = Field(description="Number of face embeddings deleted")
    message: str = Field(description="Status message")


class FaceStatsResponse(BaseModel):
    """Response model for face embedding statistics."""
    total_face_embeddings: int = Field(description="Total face embeddings in database")
    face_recognition_enabled: bool = Field(description="Whether face recognition is enabled")
    model_version: str = Field(description="Current face embedding model version")


@router.get("/faces/{event_id}", response_model=FaceEmbeddingsResponse)
async def get_face_embeddings(
    event_id: str,
    db: Session = Depends(get_db),
    face_service: FaceEmbeddingService = Depends(get_face_embedding_service),
):
    """
    Get all face embeddings for an event.

    Story P4-8.1: Face Embedding Storage (AC7)

    Returns face embeddings detected in the event thumbnail, including
    bounding box coordinates and confidence scores.

    Args:
        event_id: UUID of the event
        db: Database session
        face_service: Face embedding service instance

    Returns:
        FaceEmbeddingsResponse with list of face embeddings

    Raises:
        404: If event not found
    """
    # Verify event exists
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    faces = await face_service.get_face_embeddings(db, event_id)

    return FaceEmbeddingsResponse(
        event_id=event_id,
        face_count=len(faces),
        faces=[
            FaceEmbeddingResponse(
                id=f["id"],
                event_id=f["event_id"],
                entity_id=f.get("entity_id"),
                bounding_box=f["bounding_box"],
                confidence=f["confidence"],
                model_version=f["model_version"],
                created_at=f["created_at"],
            )
            for f in faces
        ],
    )


@router.delete("/faces/{event_id}", response_model=DeleteFacesResponse)
async def delete_event_faces(
    event_id: str,
    db: Session = Depends(get_db),
    face_service: FaceEmbeddingService = Depends(get_face_embedding_service),
):
    """
    Delete all face embeddings for an event.

    Story P4-8.1: Face Embedding Storage (AC7)

    Removes face embedding data for a specific event. Event itself is not deleted.

    Args:
        event_id: UUID of the event
        db: Database session
        face_service: Face embedding service instance

    Returns:
        DeleteFacesResponse with count of deleted embeddings

    Raises:
        404: If event not found
    """
    # Verify event exists
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    count = await face_service.delete_event_faces(db, event_id)

    return DeleteFacesResponse(
        deleted_count=count,
        message=f"Deleted {count} face embedding(s) for event {event_id}"
    )


@router.delete("/faces", response_model=DeleteFacesResponse)
async def delete_all_faces(
    db: Session = Depends(get_db),
    face_service: FaceEmbeddingService = Depends(get_face_embedding_service),
):
    """
    Delete all face embeddings from the database.

    Story P4-8.1: Face Embedding Storage (AC5)

    Privacy control endpoint - allows users to clear all stored face data.
    This is an admin-level operation that removes ALL face embeddings.

    Args:
        db: Database session
        face_service: Face embedding service instance

    Returns:
        DeleteFacesResponse with count of deleted embeddings
    """
    count = await face_service.delete_all_faces(db)

    logger.info(
        "All face embeddings deleted via API",
        extra={
            "event_type": "all_faces_deleted_api",
            "count": count,
        }
    )

    return DeleteFacesResponse(
        deleted_count=count,
        message=f"Deleted all {count} face embedding(s) from database"
    )


@router.get("/faces/stats", response_model=FaceStatsResponse)
async def get_face_stats(
    db: Session = Depends(get_db),
    face_service: FaceEmbeddingService = Depends(get_face_embedding_service),
):
    """
    Get face embedding statistics.

    Story P4-8.1: Face Embedding Storage

    Returns statistics about face embeddings including total count
    and current settings.

    Args:
        db: Database session
        face_service: Face embedding service instance

    Returns:
        FaceStatsResponse with statistics
    """
    from app.models.system_setting import SystemSetting

    total_faces = await face_service.get_total_face_count(db)

    # Get face_recognition_enabled setting
    setting = db.query(SystemSetting).filter(
        SystemSetting.key == "face_recognition_enabled"
    ).first()
    enabled = setting.value.lower() == "true" if setting else False

    return FaceStatsResponse(
        total_face_embeddings=total_faces,
        face_recognition_enabled=enabled,
        model_version=face_service.get_model_version(),
    )


# =============================================================================
# Person Matching Endpoints (Story P4-8.2)
# =============================================================================

class PersonListItem(BaseModel):
    """Single person in list response."""
    id: str = Field(description="Person UUID")
    name: Optional[str] = Field(default=None, description="User-assigned name")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    last_seen_at: datetime = Field(description="Most recent occurrence timestamp")
    occurrence_count: int = Field(description="Number of times seen")
    face_count: int = Field(description="Number of face embeddings linked to this person")


class PersonListResponse(BaseModel):
    """Response for GET /persons endpoint."""
    persons: list[PersonListItem] = Field(description="List of persons")
    total: int = Field(description="Total number of persons")
    limit: int = Field(description="Maximum returned")
    offset: int = Field(description="Pagination offset")


class PersonFaceItem(BaseModel):
    """Face embedding linked to a person."""
    id: str = Field(description="Face embedding UUID")
    event_id: str = Field(description="Event UUID")
    bounding_box: Optional[dict] = Field(default=None, description="Face bounding box coordinates")
    confidence: float = Field(description="Face detection confidence")
    created_at: datetime = Field(description="When face was detected")
    event_timestamp: Optional[datetime] = Field(default=None, description="Event timestamp")
    thumbnail_url: Optional[str] = Field(default=None, description="Event thumbnail URL")


class PersonDetailResponse(BaseModel):
    """Response for GET /persons/{id} endpoint."""
    id: str = Field(description="Person UUID")
    name: Optional[str] = Field(default=None, description="User-assigned name")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    last_seen_at: datetime = Field(description="Most recent occurrence timestamp")
    occurrence_count: int = Field(description="Number of times seen")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    recent_faces: list[PersonFaceItem] = Field(default=[], description="Recent face detections")


class PersonUpdateRequest(BaseModel):
    """Request for PUT /persons/{id} endpoint."""
    name: Optional[str] = Field(default=None, description="New name for the person (None to clear)")
    is_vip: Optional[bool] = Field(default=None, description="Mark as VIP for priority alerts (Story P4-8.4)")
    is_blocked: Optional[bool] = Field(default=None, description="Block alerts for this person (Story P4-8.4)")


class PersonUpdateResponse(BaseModel):
    """Response for PUT /persons/{id} endpoint."""
    id: str = Field(description="Person UUID")
    name: Optional[str] = Field(default=None, description="Updated name")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    last_seen_at: datetime = Field(description="Most recent occurrence timestamp")
    occurrence_count: int = Field(description="Number of times seen")
    is_vip: bool = Field(default=False, description="VIP status (Story P4-8.4)")
    is_blocked: bool = Field(default=False, description="Blocked status (Story P4-8.4)")


@router.get("/persons", response_model=PersonListResponse)
async def list_persons(
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of persons to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    named_only: bool = Query(default=False, description="Only return named persons"),
    db: Session = Depends(get_db),
    person_service: PersonMatchingService = Depends(get_person_matching_service),
):
    """
    List all known persons.

    Story P4-8.2: Person Matching

    Returns persons (RecognizedEntity with entity_type='person') sorted by
    last_seen_at descending. Includes face_count for each person.

    Args:
        limit: Maximum number of persons to return (1-100)
        offset: Pagination offset
        named_only: If True, only return persons with names assigned
        db: Database session
        person_service: Person matching service instance

    Returns:
        PersonListResponse with list of persons and pagination info
    """
    persons, total = await person_service.get_persons(
        db,
        limit=limit,
        offset=offset,
        named_only=named_only,
    )

    return PersonListResponse(
        persons=[
            PersonListItem(
                id=p["id"],
                name=p["name"],
                first_seen_at=p["first_seen_at"],
                last_seen_at=p["last_seen_at"],
                occurrence_count=p["occurrence_count"],
                face_count=p["face_count"],
            )
            for p in persons
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/persons/{person_id}", response_model=PersonDetailResponse)
async def get_person(
    person_id: str,
    include_faces: bool = Query(default=True, description="Include recent face detections"),
    face_limit: int = Query(default=10, ge=1, le=50, description="Maximum faces to include"),
    db: Session = Depends(get_db),
    person_service: PersonMatchingService = Depends(get_person_matching_service),
):
    """
    Get person details.

    Story P4-8.2: Person Matching

    Returns detailed information about a specific person including
    recent face detections linked to them.

    Args:
        person_id: UUID of the person
        include_faces: Whether to include recent face detections
        face_limit: Maximum number of faces to include
        db: Database session
        person_service: Person matching service instance

    Returns:
        PersonDetailResponse with person details and faces

    Raises:
        HTTPException 404: If person not found
    """
    person = await person_service.get_person(
        db,
        person_id,
        include_faces=include_faces,
        face_limit=face_limit,
    )

    if not person:
        raise HTTPException(
            status_code=404,
            detail=f"Person {person_id} not found"
        )

    recent_faces = []
    if "recent_faces" in person:
        recent_faces = [
            PersonFaceItem(
                id=f["id"],
                event_id=f["event_id"],
                bounding_box=f["bounding_box"],
                confidence=f["confidence"],
                created_at=f["created_at"],
                event_timestamp=f["event_timestamp"],
                thumbnail_url=f["thumbnail_url"],
            )
            for f in person["recent_faces"]
        ]

    return PersonDetailResponse(
        id=person["id"],
        name=person["name"],
        first_seen_at=person["first_seen_at"],
        last_seen_at=person["last_seen_at"],
        occurrence_count=person["occurrence_count"],
        created_at=person["created_at"],
        updated_at=person["updated_at"],
        recent_faces=recent_faces,
    )


@router.put("/persons/{person_id}", response_model=PersonUpdateResponse)
async def update_person(
    person_id: str,
    request: PersonUpdateRequest,
    db: Session = Depends(get_db),
    person_service: PersonMatchingService = Depends(get_person_matching_service),
):
    """
    Update a person's name, VIP status, or blocked status.

    Story P4-8.2: Person Matching
    Story P4-8.4: Named Entity Alerts (VIP and blocked)

    Allows users to:
    - Name recognized persons for personalized alerts like "John is at the door"
    - Mark persons as VIP for priority notifications
    - Block persons to suppress alerts (events still recorded)

    Args:
        person_id: UUID of the person
        request: Update request with new values
        db: Database session
        person_service: Person matching service instance

    Returns:
        PersonUpdateResponse with updated person info

    Raises:
        HTTPException 404: If person not found
    """
    from app.services.entity_alert_service import get_entity_alert_service

    # Update name via person service (handles face matching updates)
    person = await person_service.update_person_name(
        db,
        person_id,
        name=request.name,
    )

    if not person:
        raise HTTPException(
            status_code=404,
            detail=f"Person {person_id} not found"
        )

    # Story P4-8.4: Update VIP/blocked status if provided
    if request.is_vip is not None or request.is_blocked is not None:
        entity_service = get_entity_alert_service()
        updated_entity = await entity_service.update_entity_alert_settings(
            db=db,
            entity_id=person_id,
            is_vip=request.is_vip,
            is_blocked=request.is_blocked,
        )
        if updated_entity:
            person["is_vip"] = updated_entity.get("is_vip", False)
            person["is_blocked"] = updated_entity.get("is_blocked", False)

    return PersonUpdateResponse(
        id=person["id"],
        name=person["name"],
        first_seen_at=person["first_seen_at"],
        last_seen_at=person["last_seen_at"],
        occurrence_count=person["occurrence_count"],
        is_vip=person.get("is_vip", False),
        is_blocked=person.get("is_blocked", False),
    )


# =============================================================================
# Vehicle Recognition Endpoints (Story P4-8.3)
# =============================================================================

from app.services.vehicle_matching_service import get_vehicle_matching_service, VehicleMatchingService
from app.services.vehicle_embedding_service import get_vehicle_embedding_service, VehicleEmbeddingService


class VehicleListItem(BaseModel):
    """Single vehicle in list response."""
    id: str = Field(description="Vehicle UUID")
    name: Optional[str] = Field(default=None, description="User-assigned name")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    last_seen_at: datetime = Field(description="Most recent occurrence timestamp")
    occurrence_count: int = Field(description="Number of times seen")
    embedding_count: int = Field(description="Number of vehicle embeddings linked")
    vehicle_type: Optional[str] = Field(default=None, description="Detected vehicle type (car, truck, etc.)")
    primary_color: Optional[str] = Field(default=None, description="Primary color if detected")


class VehicleListResponse(BaseModel):
    """Response for GET /vehicles endpoint."""
    vehicles: list[VehicleListItem] = Field(description="List of vehicles")
    total: int = Field(description="Total number of vehicles")
    limit: int = Field(description="Maximum returned")
    offset: int = Field(description="Pagination offset")


class VehicleDetectionItem(BaseModel):
    """Vehicle detection linked to a vehicle entity."""
    id: str = Field(description="Vehicle embedding UUID")
    event_id: str = Field(description="Event UUID")
    bounding_box: Optional[dict] = Field(default=None, description="Vehicle bounding box coordinates")
    confidence: float = Field(description="Vehicle detection confidence")
    vehicle_type: Optional[str] = Field(default=None, description="Detected vehicle type")
    created_at: datetime = Field(description="When vehicle was detected")
    event_timestamp: Optional[datetime] = Field(default=None, description="Event timestamp")
    thumbnail_url: Optional[str] = Field(default=None, description="Event thumbnail URL")


class VehicleDetailResponse(BaseModel):
    """Response for GET /vehicles/{id} endpoint."""
    id: str = Field(description="Vehicle UUID")
    name: Optional[str] = Field(default=None, description="User-assigned name")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    last_seen_at: datetime = Field(description="Most recent occurrence timestamp")
    occurrence_count: int = Field(description="Number of times seen")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    vehicle_type: Optional[str] = Field(default=None, description="Detected vehicle type")
    primary_color: Optional[str] = Field(default=None, description="Primary color if detected")
    metadata: dict = Field(default={}, description="Additional metadata (colors, make, etc.)")
    recent_detections: list[VehicleDetectionItem] = Field(default=[], description="Recent detections")


class VehicleUpdateRequest(BaseModel):
    """Request for PUT /vehicles/{id} endpoint."""
    name: Optional[str] = Field(default=None, description="New name for the vehicle (None to clear)")
    metadata: Optional[dict] = Field(default=None, description="Optional metadata updates")
    is_vip: Optional[bool] = Field(default=None, description="Mark as VIP for priority alerts (Story P4-8.4)")
    is_blocked: Optional[bool] = Field(default=None, description="Block alerts for this vehicle (Story P4-8.4)")


class VehicleUpdateResponse(BaseModel):
    """Response for PUT /vehicles/{id} endpoint."""
    id: str = Field(description="Vehicle UUID")
    name: Optional[str] = Field(default=None, description="Updated name")
    first_seen_at: datetime = Field(description="First occurrence timestamp")
    last_seen_at: datetime = Field(description="Most recent occurrence timestamp")
    occurrence_count: int = Field(description="Number of times seen")
    vehicle_type: Optional[str] = Field(default=None, description="Detected vehicle type")
    primary_color: Optional[str] = Field(default=None, description="Primary color")
    is_vip: bool = Field(default=False, description="VIP status (Story P4-8.4)")
    is_blocked: bool = Field(default=False, description="Blocked status (Story P4-8.4)")


class VehicleEmbeddingResponse(BaseModel):
    """Response model for a single vehicle embedding."""
    id: str = Field(description="UUID of the vehicle embedding")
    event_id: str = Field(description="UUID of the associated event")
    entity_id: Optional[str] = Field(default=None, description="UUID of linked vehicle entity")
    bounding_box: dict = Field(description="Vehicle bounding box: {x, y, width, height}")
    confidence: float = Field(ge=0.0, le=1.0, description="Vehicle detection confidence")
    vehicle_type: Optional[str] = Field(default=None, description="Detected vehicle type")
    model_version: str = Field(description="Model version used for embedding")
    created_at: str = Field(description="When the vehicle embedding was created (ISO 8601)")


class VehicleEmbeddingsResponse(BaseModel):
    """Response model for vehicle embeddings list."""
    event_id: str = Field(description="UUID of the event")
    vehicle_count: int = Field(description="Number of vehicle embeddings")
    vehicles: list[VehicleEmbeddingResponse] = Field(description="List of vehicle embeddings")


class DeleteVehiclesResponse(BaseModel):
    """Response model for vehicle deletion."""
    deleted_count: int = Field(description="Number of vehicle embeddings deleted")
    message: str = Field(description="Status message")


class VehicleStatsResponse(BaseModel):
    """Response model for vehicle embedding statistics."""
    total_vehicle_embeddings: int = Field(description="Total vehicle embeddings in database")
    vehicle_recognition_enabled: bool = Field(description="Whether vehicle recognition is enabled")
    model_version: str = Field(description="Current vehicle embedding model version")


@router.get("/vehicles", response_model=VehicleListResponse)
async def list_vehicles(
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of vehicles to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    named_only: bool = Query(default=False, description="Only return named vehicles"),
    db: Session = Depends(get_db),
    vehicle_service: VehicleMatchingService = Depends(get_vehicle_matching_service),
):
    """
    List all known vehicles.

    Story P4-8.3: Vehicle Recognition

    Returns vehicles (RecognizedEntity with entity_type='vehicle') sorted by
    last_seen_at descending. Includes embedding_count for each vehicle.

    Args:
        limit: Maximum number of vehicles to return (1-100)
        offset: Pagination offset
        named_only: If True, only return vehicles with names assigned
        db: Database session
        vehicle_service: Vehicle matching service instance

    Returns:
        VehicleListResponse with list of vehicles and pagination info
    """
    vehicles, total = await vehicle_service.get_vehicles(
        db,
        limit=limit,
        offset=offset,
        named_only=named_only,
    )

    return VehicleListResponse(
        vehicles=[
            VehicleListItem(
                id=v["id"],
                name=v["name"],
                first_seen_at=v["first_seen_at"],
                last_seen_at=v["last_seen_at"],
                occurrence_count=v["occurrence_count"],
                embedding_count=v["embedding_count"],
                vehicle_type=v.get("vehicle_type"),
                primary_color=v.get("primary_color"),
            )
            for v in vehicles
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/vehicles/{vehicle_id}", response_model=VehicleDetailResponse)
async def get_vehicle(
    vehicle_id: str,
    include_detections: bool = Query(default=True, description="Include recent detections"),
    detection_limit: int = Query(default=10, ge=1, le=50, description="Maximum detections to include"),
    db: Session = Depends(get_db),
    vehicle_service: VehicleMatchingService = Depends(get_vehicle_matching_service),
):
    """
    Get vehicle details.

    Story P4-8.3: Vehicle Recognition

    Returns detailed information about a specific vehicle including
    recent detections linked to it.

    Args:
        vehicle_id: UUID of the vehicle
        include_detections: Whether to include recent detections
        detection_limit: Maximum number of detections to include
        db: Database session
        vehicle_service: Vehicle matching service instance

    Returns:
        VehicleDetailResponse with vehicle details and detections

    Raises:
        HTTPException 404: If vehicle not found
    """
    vehicle = await vehicle_service.get_vehicle(
        db,
        vehicle_id,
        include_embeddings=include_detections,
        embedding_limit=detection_limit,
    )

    if not vehicle:
        raise HTTPException(
            status_code=404,
            detail=f"Vehicle {vehicle_id} not found"
        )

    recent_detections = []
    if "recent_detections" in vehicle:
        recent_detections = [
            VehicleDetectionItem(
                id=d["id"],
                event_id=d["event_id"],
                bounding_box=d["bounding_box"],
                confidence=d["confidence"],
                vehicle_type=d["vehicle_type"],
                created_at=d["created_at"],
                event_timestamp=d["event_timestamp"],
                thumbnail_url=d["thumbnail_url"],
            )
            for d in vehicle["recent_detections"]
        ]

    return VehicleDetailResponse(
        id=vehicle["id"],
        name=vehicle["name"],
        first_seen_at=vehicle["first_seen_at"],
        last_seen_at=vehicle["last_seen_at"],
        occurrence_count=vehicle["occurrence_count"],
        created_at=vehicle["created_at"],
        updated_at=vehicle["updated_at"],
        vehicle_type=vehicle.get("vehicle_type"),
        primary_color=vehicle.get("primary_color"),
        metadata=vehicle.get("metadata", {}),
        recent_detections=recent_detections,
    )


@router.put("/vehicles/{vehicle_id}", response_model=VehicleUpdateResponse)
async def update_vehicle(
    vehicle_id: str,
    request: VehicleUpdateRequest,
    db: Session = Depends(get_db),
    vehicle_service: VehicleMatchingService = Depends(get_vehicle_matching_service),
):
    """
    Update a vehicle's name, metadata, VIP status, or blocked status.

    Story P4-8.3: Vehicle Recognition
    Story P4-8.4: Named Entity Alerts (VIP and blocked)

    Allows users to:
    - Name recognized vehicles for personalized alerts like "Your car arrived"
    - Update vehicle metadata (color, type, etc.)
    - Mark vehicles as VIP for priority notifications
    - Block vehicles to suppress alerts (events still recorded)

    Args:
        vehicle_id: UUID of the vehicle
        request: Update request with new values
        db: Database session
        vehicle_service: Vehicle matching service instance

    Returns:
        VehicleUpdateResponse with updated vehicle info

    Raises:
        HTTPException 404: If vehicle not found
    """
    from app.services.entity_alert_service import get_entity_alert_service

    # Update name if provided
    if request.name is not None:
        vehicle = await vehicle_service.update_vehicle_name(
            db,
            vehicle_id,
            name=request.name,
        )
    else:
        # Just get current vehicle data
        vehicle = await vehicle_service.get_vehicle(db, vehicle_id, include_embeddings=False)

    if not vehicle:
        raise HTTPException(
            status_code=404,
            detail=f"Vehicle {vehicle_id} not found"
        )

    # Update metadata if provided
    if request.metadata is not None:
        vehicle = await vehicle_service.update_vehicle_metadata(
            db,
            vehicle_id,
            metadata_updates=request.metadata,
        )

    # Story P4-8.4: Update VIP/blocked status if provided
    if request.is_vip is not None or request.is_blocked is not None:
        entity_service = get_entity_alert_service()
        updated_entity = await entity_service.update_entity_alert_settings(
            db=db,
            entity_id=vehicle_id,
            is_vip=request.is_vip,
            is_blocked=request.is_blocked,
        )
        if updated_entity:
            vehicle["is_vip"] = updated_entity.get("is_vip", False)
            vehicle["is_blocked"] = updated_entity.get("is_blocked", False)

    return VehicleUpdateResponse(
        id=vehicle["id"],
        name=vehicle["name"],
        first_seen_at=vehicle["first_seen_at"],
        last_seen_at=vehicle["last_seen_at"],
        occurrence_count=vehicle["occurrence_count"],
        vehicle_type=vehicle.get("vehicle_type"),
        primary_color=vehicle.get("primary_color"),
        is_vip=vehicle.get("is_vip", False),
        is_blocked=vehicle.get("is_blocked", False),
    )


# NOTE: /stats endpoint must be defined BEFORE /{event_id} to prevent route conflicts
@router.get("/vehicle-embeddings/stats", response_model=VehicleStatsResponse)
async def get_vehicle_stats(
    db: Session = Depends(get_db),
    vehicle_service: VehicleEmbeddingService = Depends(get_vehicle_embedding_service),
):
    """
    Get vehicle embedding statistics.

    Story P4-8.3: Vehicle Recognition

    Returns statistics about vehicle embeddings including total count
    and current settings.

    Args:
        db: Database session
        vehicle_service: Vehicle embedding service instance

    Returns:
        VehicleStatsResponse with statistics
    """
    from app.models.system_setting import SystemSetting

    total_vehicles = await vehicle_service.get_total_vehicle_count(db)

    # Get vehicle_recognition_enabled setting
    setting = db.query(SystemSetting).filter(
        SystemSetting.key == "vehicle_recognition_enabled"
    ).first()
    enabled = setting.value.lower() == "true" if setting else False

    return VehicleStatsResponse(
        total_vehicle_embeddings=total_vehicles,
        vehicle_recognition_enabled=enabled,
        model_version=vehicle_service.get_model_version(),
    )


@router.get("/vehicle-embeddings/{event_id}", response_model=VehicleEmbeddingsResponse)
async def get_vehicle_embeddings(
    event_id: str,
    db: Session = Depends(get_db),
    vehicle_service: VehicleEmbeddingService = Depends(get_vehicle_embedding_service),
):
    """
    Get all vehicle embeddings for an event.

    Story P4-8.3: Vehicle Recognition

    Returns vehicle embeddings detected in the event thumbnail, including
    bounding box coordinates and confidence scores.

    Args:
        event_id: UUID of the event
        db: Database session
        vehicle_service: Vehicle embedding service instance

    Returns:
        VehicleEmbeddingsResponse with list of vehicle embeddings

    Raises:
        404: If event not found
    """
    # Verify event exists
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    vehicles = await vehicle_service.get_vehicle_embeddings(db, event_id)

    return VehicleEmbeddingsResponse(
        event_id=event_id,
        vehicle_count=len(vehicles),
        vehicles=[
            VehicleEmbeddingResponse(
                id=v["id"],
                event_id=v["event_id"],
                entity_id=v.get("entity_id"),
                bounding_box=v["bounding_box"],
                confidence=v["confidence"],
                vehicle_type=v.get("vehicle_type"),
                model_version=v["model_version"],
                created_at=v["created_at"],
            )
            for v in vehicles
        ],
    )


@router.delete("/vehicle-embeddings/{event_id}", response_model=DeleteVehiclesResponse)
async def delete_event_vehicles(
    event_id: str,
    db: Session = Depends(get_db),
    vehicle_service: VehicleEmbeddingService = Depends(get_vehicle_embedding_service),
):
    """
    Delete all vehicle embeddings for an event.

    Story P4-8.3: Vehicle Recognition

    Removes vehicle embedding data for a specific event. Event itself is not deleted.

    Args:
        event_id: UUID of the event
        db: Database session
        vehicle_service: Vehicle embedding service instance

    Returns:
        DeleteVehiclesResponse with count of deleted embeddings

    Raises:
        404: If event not found
    """
    # Verify event exists
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    count = await vehicle_service.delete_event_vehicles(db, event_id)

    return DeleteVehiclesResponse(
        deleted_count=count,
        message=f"Deleted {count} vehicle embedding(s) for event {event_id}"
    )


@router.delete("/vehicle-embeddings", response_model=DeleteVehiclesResponse)
async def delete_all_vehicles(
    db: Session = Depends(get_db),
    vehicle_service: VehicleEmbeddingService = Depends(get_vehicle_embedding_service),
):
    """
    Delete all vehicle embeddings from the database.

    Story P4-8.3: Vehicle Recognition

    Privacy control endpoint - allows users to clear all stored vehicle data.
    This is an admin-level operation that removes ALL vehicle embeddings.

    Args:
        db: Database session
        vehicle_service: Vehicle embedding service instance

    Returns:
        DeleteVehiclesResponse with count of deleted embeddings
    """
    count = await vehicle_service.delete_all_vehicles(db)

    logger.info(
        "All vehicle embeddings deleted via API",
        extra={
            "event_type": "all_vehicles_deleted_api",
            "count": count,
        }
    )

    return DeleteVehiclesResponse(
        deleted_count=count,
        message=f"Deleted all {count} vehicle embedding(s) from database"
    )


# Story P9-4.6: Entity Adjustment Endpoints
@router.get("/adjustments", response_model=AdjustmentListResponse)
async def get_adjustments(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    action: Optional[str] = Query(
        default=None,
        description="Filter by action type: unlink, assign, move, merge"
    ),
    entity_id: Optional[str] = Query(
        default=None,
        description="Filter by entity ID (matches old or new entity)"
    ),
    start_date: Optional[datetime] = Query(
        default=None,
        description="Filter adjustments from this date (ISO format)"
    ),
    end_date: Optional[datetime] = Query(
        default=None,
        description="Filter adjustments until this date (ISO format)"
    ),
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Get paginated list of entity adjustments (Story P9-4.6).

    Returns manual entity corrections (unlink, assign, move, merge) for
    auditing and future ML training. Supports filtering by action type,
    entity, and date range.

    Args:
        page: Page number (1-indexed, default 1)
        limit: Items per page (1-100, default 50)
        action: Filter by action type (unlink, assign, move, merge)
        entity_id: Filter by entity ID (matches old or new)
        start_date: Filter from this date
        end_date: Filter until this date
        db: Database session
        entity_service: Entity service instance

    Returns:
        AdjustmentListResponse with paginated adjustments
    """
    # Validate action if provided
    valid_actions = ["unlink", "assign", "move", "move_from", "move_to", "merge"]
    if action and action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}"
        )

    offset = (page - 1) * limit

    adjustments, total = await entity_service.get_adjustments(
        db=db,
        limit=limit,
        offset=offset,
        action=action,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )

    return AdjustmentListResponse(
        adjustments=[AdjustmentResponse(**a) for a in adjustments],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/adjustments/export")
async def export_adjustments(
    start_date: Optional[datetime] = Query(
        default=None,
        description="Filter adjustments from this date (ISO format)"
    ),
    end_date: Optional[datetime] = Query(
        default=None,
        description="Filter adjustments until this date (ISO format)"
    ),
    db: Session = Depends(get_db),
    entity_service: EntityService = Depends(get_entity_service),
):
    """
    Export adjustments for ML training (Story P9-4.6).

    Returns all adjustment records in JSON Lines format suitable for
    ML training pipelines. Each line is a complete JSON object with
    event descriptions, entity types, and correction details.

    Args:
        start_date: Filter from this date
        end_date: Filter until this date
        db: Database session
        entity_service: Entity service instance

    Returns:
        StreamingResponse with JSON Lines (application/x-ndjson)
    """
    from fastapi.responses import StreamingResponse
    import json

    adjustments = await entity_service.export_adjustments(
        db=db,
        start_date=start_date,
        end_date=end_date,
    )

    def generate_jsonl():
        for adjustment in adjustments:
            yield json.dumps(adjustment) + "\n"

    return StreamingResponse(
        generate_jsonl(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": "attachment; filename=adjustments.jsonl"
        }
    )


# ============================================================================
# Story P12-1.5: Entity Alert Rules Endpoint
# ============================================================================

class EntityAlertRuleResponse(BaseModel):
    """Alert rule targeting a specific entity."""
    id: str = Field(description="Alert rule UUID")
    name: str = Field(description="Rule name")
    is_enabled: bool = Field(description="Whether rule is active")
    entity_match_mode: str = Field(description="Entity match mode")
    cooldown_minutes: int = Field(description="Cooldown period in minutes")
    last_triggered_at: Optional[datetime] = Field(default=None, description="When rule last triggered")
    trigger_count: int = Field(default=0, description="Total trigger count")
    created_at: datetime = Field(description="Creation timestamp")


class EntityAlertRulesResponse(BaseModel):
    """Response for entity's alert rules."""
    rules: list[EntityAlertRuleResponse] = Field(description="Alert rules targeting this entity")
    total: int = Field(description="Total number of rules")


@router.get(
    "/entities/{entity_id}/alert-rules",
    response_model=EntityAlertRulesResponse,
    summary="Get alert rules for entity",
    description="Returns all alert rules that target a specific entity (entity_match_mode='specific')."
)
async def get_entity_alert_rules(
    entity_id: str = Path(description="Entity UUID"),
    db: Session = Depends(get_db),
):
    """
    Get alert rules targeting a specific entity (Story P12-1.5).

    Returns all alert rules configured with entity_match_mode='specific'
    that target the given entity. This is displayed on the entity detail page.

    Args:
        entity_id: UUID of the entity
        db: Database session

    Returns:
        EntityAlertRulesResponse with list of matching rules
    """
    from app.models.alert_rule import AlertRule

    # Query rules targeting this specific entity
    rules = db.query(AlertRule).filter(
        AlertRule.entity_id == entity_id,
        AlertRule.entity_match_mode == 'specific'
    ).order_by(AlertRule.created_at.desc()).all()

    return EntityAlertRulesResponse(
        rules=[
            EntityAlertRuleResponse(
                id=str(rule.id),
                name=rule.name,
                is_enabled=rule.is_enabled,
                entity_match_mode=rule.entity_match_mode or 'any',
                cooldown_minutes=rule.cooldown_minutes,
                last_triggered_at=rule.last_triggered_at,
                trigger_count=rule.trigger_count,
                created_at=rule.created_at,
            )
            for rule in rules
        ],
        total=len(rules)
    )
