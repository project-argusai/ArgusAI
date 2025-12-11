"""
Context API endpoints for Temporal Context Engine (Story P4-3.1, P4-3.2)

Provides endpoints for:
- Batch processing of embeddings for existing events
- Embedding status retrieval
- Similarity search for finding visually similar past events (P4-3.2)
"""
import base64
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.event import Event
from app.models.event_embedding import EventEmbedding
from app.services.embedding_service import get_embedding_service, EmbeddingService
from app.services.similarity_service import get_similarity_service, SimilarityService

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
