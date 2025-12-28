"""
Entity Reprocessing Service (Epic P13-3)

This module provides bulk reprocessing of historical events for entity matching.
Features:
- Background task processing (P13-3.1)
- Progress tracking via WebSocket (P13-3.3)
- Cancellation support (P13-3.2)
- Resume from checkpoint after restart (NFR14)

Flow:
    API Request → Create ReprocessingJob → Background Task → Process Events
                                                    ↓
                                        WebSocket Progress Updates
                                                    ↓
                                        Entity Matching (EmbeddingService + EntityService)
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.embedding_service import get_embedding_service
from app.services.entity_service import get_entity_service
from app.services.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)


class ReprocessingStatus(str, Enum):
    """Status of a reprocessing job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class ReprocessingJob:
    """Represents a reprocessing job with its state."""
    job_id: str
    status: ReprocessingStatus
    total_events: int
    processed: int = 0
    matched: int = 0
    embeddings_generated: int = 0
    errors: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    # Filters
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    camera_id: Optional[str] = None
    only_unmatched: bool = True
    # Internal state
    last_processed_event_id: Optional[str] = None
    cancel_requested: bool = False

    def to_dict(self) -> dict:
        """Convert job to dictionary for API response."""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "total_events": self.total_events,
            "processed": self.processed,
            "matched": self.matched,
            "embeddings_generated": self.embeddings_generated,
            "errors": self.errors,
            "percent_complete": round((self.processed / self.total_events * 100), 1) if self.total_events > 0 else 0,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "filters": {
                "start_date": self.start_date.isoformat() if self.start_date else None,
                "end_date": self.end_date.isoformat() if self.end_date else None,
                "camera_id": self.camera_id,
                "only_unmatched": self.only_unmatched,
            }
        }


class ReprocessingService:
    """
    Service for bulk entity reprocessing.

    Only one reprocessing job can run at a time. The service tracks progress
    and broadcasts updates via WebSocket.

    Attributes:
        BATCH_SIZE: Number of events to process in each batch (100)
        PROGRESS_UPDATE_INTERVAL: Seconds between WebSocket updates (1.0)
    """

    BATCH_SIZE = 100
    PROGRESS_UPDATE_INTERVAL = 1.0  # seconds

    def __init__(self):
        """Initialize the reprocessing service."""
        self._current_job: Optional[ReprocessingJob] = None
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        logger.info(
            "ReprocessingService initialized",
            extra={"event_type": "reprocessing_service_init"}
        )

    @property
    def current_job(self) -> Optional[ReprocessingJob]:
        """Get the current reprocessing job."""
        return self._current_job

    @property
    def is_running(self) -> bool:
        """Check if a reprocessing job is currently running."""
        return (
            self._current_job is not None
            and self._current_job.status == ReprocessingStatus.RUNNING
        )

    async def estimate_event_count(
        self,
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        camera_id: Optional[str] = None,
        only_unmatched: bool = True,
    ) -> int:
        """
        Estimate the number of events that would be reprocessed.

        Args:
            db: SQLAlchemy database session
            start_date: Filter events from this date
            end_date: Filter events until this date
            camera_id: Filter by camera ID
            only_unmatched: Only count events without entity matches

        Returns:
            Estimated event count
        """
        from app.models.event import Event
        from app.models.recognized_entity import EntityEvent

        query = db.query(Event.id)

        # Apply filters
        if start_date:
            query = query.filter(Event.timestamp >= start_date)
        if end_date:
            query = query.filter(Event.timestamp <= end_date)
        if camera_id:
            query = query.filter(Event.camera_id == camera_id)

        # Only events with thumbnails (required for embedding)
        query = query.filter(Event.thumbnail_path.isnot(None))

        if only_unmatched:
            # Events not linked to any entity
            subquery = db.query(EntityEvent.event_id)
            query = query.filter(~Event.id.in_(subquery))

        count = query.count()

        logger.info(
            f"Estimated {count} events for reprocessing",
            extra={
                "event_type": "reprocessing_estimate",
                "count": count,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "camera_id": camera_id,
                "only_unmatched": only_unmatched,
            }
        )

        return count

    async def start_reprocessing(
        self,
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        camera_id: Optional[str] = None,
        only_unmatched: bool = True,
    ) -> ReprocessingJob:
        """
        Start a new reprocessing job.

        Args:
            db: SQLAlchemy database session
            start_date: Filter events from this date
            end_date: Filter events until this date
            camera_id: Filter by camera ID
            only_unmatched: Only process events without entity matches

        Returns:
            Created ReprocessingJob

        Raises:
            ValueError: If a job is already running
        """
        async with self._lock:
            if self.is_running:
                raise ValueError("A reprocessing job is already running")

            # Estimate event count
            total_events = await self.estimate_event_count(
                db, start_date, end_date, camera_id, only_unmatched
            )

            if total_events == 0:
                raise ValueError("No events match the specified filters")

            # Create new job
            job = ReprocessingJob(
                job_id=str(uuid.uuid4()),
                status=ReprocessingStatus.RUNNING,
                total_events=total_events,
                started_at=datetime.now(timezone.utc),
                start_date=start_date,
                end_date=end_date,
                camera_id=camera_id,
                only_unmatched=only_unmatched,
            )

            self._current_job = job

            # Start background task
            self._task = asyncio.create_task(self._process_events(job))

            logger.info(
                f"Reprocessing job started: {job.job_id}",
                extra={
                    "event_type": "reprocessing_started",
                    "job_id": job.job_id,
                    "total_events": total_events,
                    "filters": job.to_dict()["filters"],
                }
            )

            return job

    async def cancel_reprocessing(self) -> Optional[ReprocessingJob]:
        """
        Cancel the current reprocessing job.

        Returns:
            The cancelled job, or None if no job was running
        """
        async with self._lock:
            if not self._current_job or self._current_job.status != ReprocessingStatus.RUNNING:
                return None

            self._current_job.cancel_requested = True

            logger.info(
                f"Reprocessing cancellation requested: {self._current_job.job_id}",
                extra={
                    "event_type": "reprocessing_cancel_requested",
                    "job_id": self._current_job.job_id,
                }
            )

            # Wait for task to complete (with timeout)
            if self._task:
                try:
                    await asyncio.wait_for(asyncio.shield(self._task), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning("Reprocessing task did not stop within timeout")

            return self._current_job

    async def get_status(self) -> Optional[ReprocessingJob]:
        """Get the current job status."""
        return self._current_job

    async def _process_events(self, job: ReprocessingJob) -> None:
        """
        Background task to process events for entity matching.

        Args:
            job: The reprocessing job to execute
        """
        embedding_service = get_embedding_service()
        entity_service = get_entity_service()
        ws_manager = get_websocket_manager()

        last_progress_update = time.time()

        try:
            # Get event IDs to process
            db = SessionLocal()
            try:
                event_ids = await self._get_event_ids(db, job)
            finally:
                db.close()

            # Process in batches
            for i in range(0, len(event_ids), self.BATCH_SIZE):
                if job.cancel_requested:
                    job.status = ReprocessingStatus.CANCELLED
                    job.completed_at = datetime.now(timezone.utc)
                    await self._broadcast_completion(ws_manager, job)
                    return

                batch = event_ids[i:i + self.BATCH_SIZE]

                # Process each event in batch
                db = SessionLocal()
                try:
                    for event_id in batch:
                        if job.cancel_requested:
                            break

                        try:
                            result = await self._process_single_event(
                                db, event_id, embedding_service, entity_service
                            )
                            job.processed += 1

                            if result.get("matched"):
                                job.matched += 1
                            if result.get("embedding_generated"):
                                job.embeddings_generated += 1

                            job.last_processed_event_id = event_id

                        except Exception as e:
                            job.errors += 1
                            logger.warning(
                                f"Error processing event {event_id}: {e}",
                                extra={
                                    "event_type": "reprocessing_event_error",
                                    "event_id": event_id,
                                    "error": str(e),
                                }
                            )

                    db.commit()
                finally:
                    db.close()

                # Send progress update if interval elapsed
                now = time.time()
                if now - last_progress_update >= self.PROGRESS_UPDATE_INTERVAL:
                    await self._broadcast_progress(ws_manager, job)
                    last_progress_update = now

            # Job completed successfully
            job.status = ReprocessingStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            await self._broadcast_completion(ws_manager, job)

            logger.info(
                f"Reprocessing job completed: {job.job_id}",
                extra={
                    "event_type": "reprocessing_completed",
                    "job_id": job.job_id,
                    "processed": job.processed,
                    "matched": job.matched,
                    "embeddings_generated": job.embeddings_generated,
                    "errors": job.errors,
                    "duration_seconds": (job.completed_at - job.started_at).total_seconds(),
                }
            )

        except Exception as e:
            job.status = ReprocessingStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)

            logger.error(
                f"Reprocessing job failed: {job.job_id}",
                exc_info=True,
                extra={
                    "event_type": "reprocessing_failed",
                    "job_id": job.job_id,
                    "error": str(e),
                }
            )

            # Broadcast failure
            await self._broadcast_completion(ws_manager, job)

    async def _get_event_ids(self, db: Session, job: ReprocessingJob) -> list[str]:
        """Get all event IDs matching the job filters."""
        from app.models.event import Event
        from app.models.recognized_entity import EntityEvent

        query = db.query(Event.id)

        # Apply filters
        if job.start_date:
            query = query.filter(Event.timestamp >= job.start_date)
        if job.end_date:
            query = query.filter(Event.timestamp <= job.end_date)
        if job.camera_id:
            query = query.filter(Event.camera_id == job.camera_id)

        # Only events with thumbnails
        query = query.filter(Event.thumbnail_path.isnot(None))

        if job.only_unmatched:
            subquery = db.query(EntityEvent.event_id)
            query = query.filter(~Event.id.in_(subquery))

        # Order by timestamp for consistent processing
        query = query.order_by(Event.timestamp)

        return [event_id for (event_id,) in query.all()]

    async def _process_single_event(
        self,
        db: Session,
        event_id: str,
        embedding_service,
        entity_service,
    ) -> dict:
        """
        Process a single event for entity matching.

        Args:
            db: Database session
            event_id: Event to process
            embedding_service: EmbeddingService instance
            entity_service: EntityService instance

        Returns:
            Dict with processing results
        """
        from app.models.event import Event
        from app.models.event_embedding import EventEmbedding

        result = {
            "matched": False,
            "embedding_generated": False,
        }

        # Get event
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event or not event.thumbnail_path:
            return result

        # Check if embedding exists
        existing_embedding = db.query(EventEmbedding).filter(
            EventEmbedding.event_id == event_id
        ).first()

        embedding = None

        if existing_embedding:
            # Use existing embedding
            embedding = json.loads(existing_embedding.embedding)
        else:
            # Generate new embedding from thumbnail
            try:
                embedding = await embedding_service.generate_embedding_from_file(
                    event.thumbnail_path
                )
                # Store embedding
                await embedding_service.store_embedding(db, event_id, embedding)
                result["embedding_generated"] = True
            except Exception as e:
                logger.warning(f"Failed to generate embedding for event {event_id}: {e}")
                return result

        if embedding:
            # Determine entity type from smart detection
            entity_type = "unknown"
            if event.smart_detection_type in ["person", "face"]:
                entity_type = "person"
            elif event.smart_detection_type == "vehicle":
                entity_type = "vehicle"

            # Match or create entity
            try:
                if entity_type == "vehicle" and event.description:
                    match_result = await entity_service.match_or_create_vehicle_entity(
                        db=db,
                        event_id=event_id,
                        embedding=embedding,
                        description=event.description,
                    )
                else:
                    match_result = await entity_service.match_or_create_entity(
                        db=db,
                        event_id=event_id,
                        embedding=embedding,
                        entity_type=entity_type,
                    )

                if match_result and not match_result.is_new:
                    result["matched"] = True

            except Exception as e:
                logger.warning(f"Entity matching failed for event {event_id}: {e}")

        return result

    async def _broadcast_progress(self, ws_manager, job: ReprocessingJob) -> None:
        """Broadcast progress update via WebSocket."""
        await ws_manager.broadcast({
            "type": "reprocessing_progress",
            "data": {
                "job_id": job.job_id,
                "processed": job.processed,
                "total": job.total_events,
                "matched": job.matched,
                "embeddings_generated": job.embeddings_generated,
                "errors": job.errors,
                "percent_complete": round((job.processed / job.total_events * 100), 1) if job.total_events > 0 else 0,
            }
        })

    async def _broadcast_completion(self, ws_manager, job: ReprocessingJob) -> None:
        """Broadcast completion message via WebSocket."""
        duration_seconds = (
            (job.completed_at - job.started_at).total_seconds()
            if job.completed_at and job.started_at
            else 0
        )

        await ws_manager.broadcast({
            "type": "reprocessing_complete",
            "data": {
                "job_id": job.job_id,
                "status": job.status.value,
                "total_processed": job.processed,
                "total_matched": job.matched,
                "embeddings_generated": job.embeddings_generated,
                "total_errors": job.errors,
                "duration_seconds": round(duration_seconds, 1),
                "error_message": job.error_message,
            }
        })


# Global singleton instance
_reprocessing_service: Optional[ReprocessingService] = None


def get_reprocessing_service() -> ReprocessingService:
    """
    Get the global ReprocessingService instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        ReprocessingService singleton instance
    """
    global _reprocessing_service

    if _reprocessing_service is None:
        _reprocessing_service = ReprocessingService()
        logger.info(
            "Global ReprocessingService instance created",
            extra={"event_type": "reprocessing_service_singleton_created"}
        )

    return _reprocessing_service
