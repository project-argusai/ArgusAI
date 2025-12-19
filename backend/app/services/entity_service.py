"""
Entity Service for Recurring Visitor Detection (Story P4-3.3)

This module provides entity matching functionality for identifying and tracking
recurring visitors using CLIP embeddings. It enables recognition of familiar
faces/vehicles with "first seen", "last seen", and visit count.

Architecture:
    - Uses SimilarityService for batch cosine similarity calculations
    - Caches entity embeddings in memory for fast matching
    - Configurable similarity threshold (default 0.75)
    - SQLite-compatible (no pgvector required)

Flow:
    Event → EmbeddingService (P4-3.1) → EntityService.match_or_create_entity()
                                               ↓
                                    Load entity embeddings (cache or DB)
                                               ↓
                                    Batch cosine similarity
                                               ↓
                              ┌───────────────┴───────────────┐
                              │                               │
                   Match found (>=threshold)       No match (<threshold)
                              │                               │
                   Update existing entity          Create new entity
                              │                               │
                              └───────────────┬───────────────┘
                                              ↓
                                   Create EntityEvent link
                                              ↓
                                   Return EntityMatchResult
"""
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.services.similarity_service import (
    SimilarityService,
    get_similarity_service,
    batch_cosine_similarity,
)

logger = logging.getLogger(__name__)


@dataclass
class EntityMatchResult:
    """Result of entity matching operation."""
    entity_id: str
    entity_type: str
    name: Optional[str]
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
    similarity_score: float
    is_new: bool


class EntityService:
    """
    Recognize and track recurring visitors.

    This service provides the core entity matching functionality for the
    Temporal Context Engine. It uses CLIP embeddings and cosine similarity
    to identify if a detected entity (person/vehicle) has been seen before.

    Attributes:
        DEFAULT_THRESHOLD: Default similarity threshold for matching (0.75)
    """

    DEFAULT_THRESHOLD = 0.75

    def __init__(self, similarity_service: Optional[SimilarityService] = None):
        """
        Initialize EntityService.

        Args:
            similarity_service: SimilarityService instance for similarity calculations.
                              If None, will use the global singleton.
        """
        self._similarity_service = similarity_service or get_similarity_service()
        self._entity_cache: dict[str, list[float]] = {}  # entity_id -> embedding
        self._cache_loaded = False
        logger.info(
            "EntityService initialized",
            extra={"event_type": "entity_service_init"}
        )

    def _load_entity_cache(self, db: Session) -> None:
        """
        Load all entity embeddings into memory cache.

        Args:
            db: SQLAlchemy database session
        """
        from app.models.recognized_entity import RecognizedEntity

        start_time = time.time()

        entities = db.query(
            RecognizedEntity.id,
            RecognizedEntity.reference_embedding
        ).all()

        self._entity_cache = {}
        for entity in entities:
            try:
                embedding = json.loads(entity.reference_embedding)
                self._entity_cache[entity.id] = embedding
            except json.JSONDecodeError:
                logger.warning(
                    f"Invalid embedding JSON for entity {entity.id}",
                    extra={"entity_id": entity.id}
                )

        self._cache_loaded = True
        load_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Entity cache loaded: {len(self._entity_cache)} entities in {load_time_ms:.2f}ms",
            extra={
                "event_type": "entity_cache_loaded",
                "entity_count": len(self._entity_cache),
                "load_time_ms": round(load_time_ms, 2),
            }
        )

    def _invalidate_cache(self) -> None:
        """Clear the entity embedding cache."""
        self._entity_cache = {}
        self._cache_loaded = False
        logger.debug(
            "Entity cache invalidated",
            extra={"event_type": "entity_cache_invalidated"}
        )

    async def match_or_create_entity(
        self,
        db: Session,
        event_id: str,
        embedding: list[float],
        entity_type: str = "unknown",
        threshold: float = DEFAULT_THRESHOLD,
    ) -> EntityMatchResult:
        """
        Match event to existing entity or create new one.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event being matched
            embedding: CLIP embedding vector (512-dim)
            entity_type: Type of entity (person, vehicle, unknown)
            threshold: Minimum similarity score for matching (default 0.75)

        Returns:
            EntityMatchResult with entity details and match info

        Note:
            - If a match is found: updates occurrence_count and last_seen_at
            - If no match: creates new entity with this event's embedding as reference
            - Always creates EntityEvent link
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.event import Event

        start_time = time.time()

        # Load cache if needed
        if not self._cache_loaded:
            self._load_entity_cache(db)

        # Get event timestamp for temporal tracking
        event = db.query(Event.timestamp).filter(Event.id == event_id).first()
        event_timestamp = event.timestamp if event else datetime.now(timezone.utc)

        # If no entities exist, create first one
        if not self._entity_cache:
            result = await self._create_new_entity(
                db, event_id, embedding, entity_type, event_timestamp
            )
            match_time_ms = (time.time() - start_time) * 1000
            logger.info(
                f"First entity created for event {event_id}",
                extra={
                    "event_type": "entity_created_first",
                    "event_id": event_id,
                    "entity_id": result.entity_id,
                    "match_time_ms": round(match_time_ms, 2),
                }
            )
            return result

        # Calculate similarity with all existing entities
        entity_ids = list(self._entity_cache.keys())
        entity_embeddings = [self._entity_cache[eid] for eid in entity_ids]

        similarities = batch_cosine_similarity(embedding, entity_embeddings)

        # Find best match above threshold
        best_idx = -1
        best_score = -1.0
        for i, score in enumerate(similarities):
            if score >= threshold and score > best_score:
                best_idx = i
                best_score = score

        match_time_ms = (time.time() - start_time) * 1000

        if best_idx >= 0:
            # Match found - update existing entity
            matched_entity_id = entity_ids[best_idx]
            result = await self._update_existing_entity(
                db, matched_entity_id, event_id, best_score, event_timestamp
            )
            logger.info(
                f"Entity matched for event {event_id}",
                extra={
                    "event_type": "entity_matched",
                    "event_id": event_id,
                    "entity_id": matched_entity_id,
                    "similarity_score": round(best_score, 4),
                    "occurrence_count": result.occurrence_count,
                    "match_time_ms": round(match_time_ms, 2),
                }
            )
            return result
        else:
            # No match - create new entity
            result = await self._create_new_entity(
                db, event_id, embedding, entity_type, event_timestamp
            )
            logger.info(
                f"New entity created for event {event_id}",
                extra={
                    "event_type": "entity_created_new",
                    "event_id": event_id,
                    "entity_id": result.entity_id,
                    "best_score_below_threshold": round(max(similarities) if similarities else 0, 4),
                    "threshold": threshold,
                    "match_time_ms": round(match_time_ms, 2),
                }
            )
            return result

    async def match_entity_only(
        self,
        db: Session,
        embedding: list[float],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> Optional[EntityMatchResult]:
        """
        Match embedding to existing entity without creating any links (Story P4-3.4).

        This is a read-only operation used for context building during AI prompt
        generation BEFORE the event is stored in the database.

        Args:
            db: SQLAlchemy database session
            embedding: CLIP embedding vector (512-dim)
            threshold: Minimum similarity score for matching (default 0.75)

        Returns:
            EntityMatchResult if a match is found above threshold, None otherwise

        Note:
            - Does NOT create entity-event links
            - Does NOT update occurrence counts
            - Does NOT create new entities
            - Pure read operation for context lookup
        """
        from app.models.recognized_entity import RecognizedEntity

        start_time = time.time()

        # Load cache if needed
        if not self._cache_loaded:
            self._load_entity_cache(db)

        # If no entities exist, nothing to match
        if not self._entity_cache:
            return None

        # Calculate similarity with all existing entities
        entity_ids = list(self._entity_cache.keys())
        entity_embeddings = [self._entity_cache[eid] for eid in entity_ids]

        similarities = batch_cosine_similarity(embedding, entity_embeddings)

        # Find best match above threshold
        best_idx = -1
        best_score = -1.0
        for i, score in enumerate(similarities):
            if score >= threshold and score > best_score:
                best_idx = i
                best_score = score

        match_time_ms = (time.time() - start_time) * 1000

        if best_idx >= 0:
            # Match found - get entity details (read-only)
            matched_entity_id = entity_ids[best_idx]

            entity = db.query(RecognizedEntity).filter(
                RecognizedEntity.id == matched_entity_id
            ).first()

            if not entity:
                logger.warning(
                    f"Entity {matched_entity_id} in cache but not in DB",
                    extra={"entity_id": matched_entity_id}
                )
                return None

            logger.debug(
                f"Entity match found for context (read-only)",
                extra={
                    "event_type": "entity_match_context",
                    "entity_id": matched_entity_id,
                    "entity_name": entity.name,
                    "similarity_score": round(best_score, 4),
                    "occurrence_count": entity.occurrence_count,
                    "match_time_ms": round(match_time_ms, 2),
                }
            )

            return EntityMatchResult(
                entity_id=entity.id,
                entity_type=entity.entity_type,
                name=entity.name,
                first_seen_at=entity.first_seen_at,
                last_seen_at=entity.last_seen_at,
                occurrence_count=entity.occurrence_count,
                similarity_score=best_score,
                is_new=False,
            )
        else:
            logger.debug(
                f"No entity match found for context (best score: {max(similarities) if similarities else 0:.4f})",
                extra={
                    "event_type": "entity_no_match_context",
                    "best_score": round(max(similarities) if similarities else 0, 4),
                    "threshold": threshold,
                    "match_time_ms": round(match_time_ms, 2),
                }
            )
            return None

    async def _create_new_entity(
        self,
        db: Session,
        event_id: str,
        embedding: list[float],
        entity_type: str,
        event_timestamp: datetime,
    ) -> EntityMatchResult:
        """Create a new entity and link it to the event."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        entity_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Create entity
        new_entity = RecognizedEntity(
            id=entity_id,
            entity_type=entity_type,
            name=None,
            reference_embedding=json.dumps(embedding),
            first_seen_at=event_timestamp,
            last_seen_at=event_timestamp,
            occurrence_count=1,
            created_at=now,
            updated_at=now,
        )
        db.add(new_entity)

        # Create entity-event link (similarity 1.0 for first occurrence)
        entity_event = EntityEvent(
            entity_id=entity_id,
            event_id=event_id,
            similarity_score=1.0,
            created_at=now,
        )
        db.add(entity_event)

        db.commit()

        # Update cache
        self._entity_cache[entity_id] = embedding

        return EntityMatchResult(
            entity_id=entity_id,
            entity_type=entity_type,
            name=None,
            first_seen_at=event_timestamp,
            last_seen_at=event_timestamp,
            occurrence_count=1,
            similarity_score=1.0,
            is_new=True,
        )

    async def _update_existing_entity(
        self,
        db: Session,
        entity_id: str,
        event_id: str,
        similarity_score: float,
        event_timestamp: datetime,
    ) -> EntityMatchResult:
        """Update an existing entity with new occurrence and link to event."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        now = datetime.now(timezone.utc)

        # Update entity
        entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity:
            raise ValueError(f"Entity {entity_id} not found")

        entity.occurrence_count += 1
        entity.last_seen_at = event_timestamp
        entity.updated_at = now

        # Create entity-event link
        entity_event = EntityEvent(
            entity_id=entity_id,
            event_id=event_id,
            similarity_score=similarity_score,
            created_at=now,
        )
        db.add(entity_event)

        db.commit()
        db.refresh(entity)

        return EntityMatchResult(
            entity_id=entity.id,
            entity_type=entity.entity_type,
            name=entity.name,
            first_seen_at=entity.first_seen_at,
            last_seen_at=entity.last_seen_at,
            occurrence_count=entity.occurrence_count,
            similarity_score=similarity_score,
            is_new=False,
        )

    async def get_all_entities(
        self,
        db: Session,
        limit: int = 50,
        offset: int = 0,
        entity_type: Optional[str] = None,
        named_only: bool = False,
        search: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """
        Get all recognized entities with pagination.

        Args:
            db: SQLAlchemy database session
            limit: Maximum number of entities to return
            offset: Pagination offset
            entity_type: Filter by entity type (person, vehicle, etc.)
            named_only: If True, only return named entities
            search: Search string to filter by name (case-insensitive partial match)

        Returns:
            Tuple of (list of entity dicts, total count)
        """
        from app.models.recognized_entity import RecognizedEntity

        query = db.query(RecognizedEntity)

        if entity_type:
            query = query.filter(RecognizedEntity.entity_type == entity_type)

        if named_only:
            query = query.filter(RecognizedEntity.name.isnot(None))

        if search:
            # Case-insensitive search on name field
            query = query.filter(RecognizedEntity.name.ilike(f"%{search}%"))

        total = query.count()

        entities = query.order_by(
            desc(RecognizedEntity.last_seen_at)
        ).offset(offset).limit(limit).all()

        return [
            {
                "id": e.id,
                "entity_type": e.entity_type,
                "name": e.name,
                "notes": e.notes,
                "thumbnail_path": e.thumbnail_path,
                "first_seen_at": e.first_seen_at,
                "last_seen_at": e.last_seen_at,
                "occurrence_count": e.occurrence_count,
                "is_vip": e.is_vip,
                "is_blocked": e.is_blocked,
            }
            for e in entities
        ], total

    async def get_entity(
        self,
        db: Session,
        entity_id: str,
        include_events: bool = True,
        event_limit: int = 10,
    ) -> Optional[dict]:
        """
        Get a single entity with its associated events.

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity
            include_events: Whether to include recent events
            event_limit: Maximum number of events to include

        Returns:
            Entity dict with optional events, or None if not found
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.event import Event

        entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity:
            return None

        result = {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "name": entity.name,
            "notes": entity.notes,
            "thumbnail_path": entity.thumbnail_path,
            "first_seen_at": entity.first_seen_at,
            "last_seen_at": entity.last_seen_at,
            "occurrence_count": entity.occurrence_count,
            "is_vip": entity.is_vip,
            "is_blocked": entity.is_blocked,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

        if include_events:
            # Get recent events associated with this entity
            events = db.query(
                Event.id,
                Event.timestamp,
                Event.description,
                Event.thumbnail_path,
                Event.camera_id,
                EntityEvent.similarity_score,
            ).join(
                EntityEvent, EntityEvent.event_id == Event.id
            ).filter(
                EntityEvent.entity_id == entity_id
            ).order_by(
                desc(Event.timestamp)
            ).limit(event_limit).all()

            result["recent_events"] = [
                {
                    "id": e.id,
                    "timestamp": e.timestamp,
                    "description": e.description,
                    "thumbnail_url": e.thumbnail_path,
                    "camera_id": e.camera_id,
                    "similarity_score": e.similarity_score,
                }
                for e in events
            ]

        return result

    async def create_entity(
        self,
        db: Session,
        entity_type: str,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
        is_vip: bool = False,
        is_blocked: bool = False,
    ) -> dict:
        """
        Create a new entity manually (Story P7-4.1).

        Args:
            db: SQLAlchemy database session
            entity_type: Type of entity (person, vehicle, unknown)
            name: User-assigned name (optional)
            notes: User notes about the entity (optional)
            thumbnail_path: Path to thumbnail image (optional)
            is_vip: Whether entity is VIP (default False)
            is_blocked: Whether entity is blocked (default False)

        Returns:
            Created entity dict
        """
        from app.models.recognized_entity import RecognizedEntity

        now = datetime.now(timezone.utc)
        entity_id = str(uuid.uuid4())

        # Create entity with placeholder embedding (empty JSON array)
        new_entity = RecognizedEntity(
            id=entity_id,
            entity_type=entity_type,
            name=name,
            notes=notes,
            thumbnail_path=thumbnail_path,
            reference_embedding="[]",  # Placeholder until recognition assigns real embedding
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=0,  # 0 until matched via recognition
            is_vip=is_vip,
            is_blocked=is_blocked,
            created_at=now,
            updated_at=now,
        )
        db.add(new_entity)
        db.commit()
        db.refresh(new_entity)

        logger.info(
            f"Entity created manually: {entity_id}",
            extra={
                "event_type": "entity_created_manual",
                "entity_id": entity_id,
                "entity_type": entity_type,
                "name": name,
            }
        )

        return {
            "id": new_entity.id,
            "entity_type": new_entity.entity_type,
            "name": new_entity.name,
            "notes": new_entity.notes,
            "thumbnail_path": new_entity.thumbnail_path,
            "first_seen_at": new_entity.first_seen_at,
            "last_seen_at": new_entity.last_seen_at,
            "occurrence_count": new_entity.occurrence_count,
            "is_vip": new_entity.is_vip,
            "is_blocked": new_entity.is_blocked,
            "created_at": new_entity.created_at,
            "updated_at": new_entity.updated_at,
        }

    async def update_entity(
        self,
        db: Session,
        entity_id: str,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        is_vip: Optional[bool] = None,
        is_blocked: Optional[bool] = None,
    ) -> Optional[dict]:
        """
        Update an entity's name, notes, VIP status, or blocked status.

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity
            name: New name for the entity (None to clear)
            notes: New notes for the entity (None to clear)
            is_vip: VIP status (None to keep unchanged)
            is_blocked: Blocked status (None to keep unchanged)

        Returns:
            Updated entity dict, or None if not found
        """
        from app.models.recognized_entity import RecognizedEntity

        entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity:
            return None

        # Update provided fields
        if name is not None:
            entity.name = name
        if notes is not None:
            entity.notes = notes
        if is_vip is not None:
            entity.is_vip = is_vip
        if is_blocked is not None:
            entity.is_blocked = is_blocked

        entity.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(entity)

        return {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "name": entity.name,
            "notes": entity.notes,
            "thumbnail_path": entity.thumbnail_path,
            "first_seen_at": entity.first_seen_at,
            "last_seen_at": entity.last_seen_at,
            "occurrence_count": entity.occurrence_count,
            "is_vip": entity.is_vip,
            "is_blocked": entity.is_blocked,
        }

    async def delete_entity(self, db: Session, entity_id: str) -> bool:
        """
        Delete an entity and its event links.

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity to delete

        Returns:
            True if deleted, False if not found

        Note:
            EntityEvent links are automatically deleted via CASCADE.
        """
        from app.models.recognized_entity import RecognizedEntity

        entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity:
            return False

        db.delete(entity)
        db.commit()

        # Remove from cache
        if entity_id in self._entity_cache:
            del self._entity_cache[entity_id]

        logger.info(
            f"Entity deleted: {entity_id}",
            extra={
                "event_type": "entity_deleted",
                "entity_id": entity_id,
            }
        )

        return True

    async def get_entity_events(
        self,
        db: Session,
        entity_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """
        Get all events associated with an entity.

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity
            limit: Maximum number of events to return
            offset: Pagination offset

        Returns:
            Tuple of (list of event dicts, total count)
        """
        from app.models.recognized_entity import EntityEvent
        from app.models.event import Event

        query = db.query(
            Event.id,
            Event.timestamp,
            Event.description,
            Event.thumbnail_path,
            Event.camera_id,
            EntityEvent.similarity_score,
            EntityEvent.created_at.label("matched_at"),
        ).join(
            EntityEvent, EntityEvent.event_id == Event.id
        ).filter(
            EntityEvent.entity_id == entity_id
        )

        total = query.count()

        events = query.order_by(
            desc(Event.timestamp)
        ).offset(offset).limit(limit).all()

        return [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "description": e.description,
                "thumbnail_url": e.thumbnail_path,
                "camera_id": e.camera_id,
                "similarity_score": e.similarity_score,
                "matched_at": e.matched_at,
            }
            for e in events
        ], total

    async def get_entity_thumbnail_path(
        self,
        db: Session,
        entity_id: str,
    ) -> Optional[str]:
        """
        Get the thumbnail path for an entity (Story P7-4.1).

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity

        Returns:
            Thumbnail file path, or None if entity not found or has no thumbnail
        """
        from app.models.recognized_entity import RecognizedEntity

        entity = db.query(RecognizedEntity.thumbnail_path).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity or not entity.thumbnail_path:
            return None

        return entity.thumbnail_path

    async def get_entity_for_event(
        self,
        db: Session,
        event_id: str,
    ) -> Optional[dict]:
        """
        Get the entity associated with an event.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            Entity summary dict, or None if no entity linked
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        result = db.query(
            RecognizedEntity.id,
            RecognizedEntity.entity_type,
            RecognizedEntity.name,
            RecognizedEntity.first_seen_at,
            RecognizedEntity.occurrence_count,
            EntityEvent.similarity_score,
        ).join(
            EntityEvent, EntityEvent.entity_id == RecognizedEntity.id
        ).filter(
            EntityEvent.event_id == event_id
        ).first()

        if not result:
            return None

        return {
            "id": result.id,
            "entity_type": result.entity_type,
            "name": result.name,
            "first_seen_at": result.first_seen_at,
            "occurrence_count": result.occurrence_count,
            "similarity_score": result.similarity_score,
        }


# Global singleton instance
_entity_service: Optional[EntityService] = None


def get_entity_service() -> EntityService:
    """
    Get the global EntityService instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        EntityService singleton instance
    """
    global _entity_service

    if _entity_service is None:
        _entity_service = EntityService()
        logger.info(
            "Global EntityService instance created",
            extra={"event_type": "entity_service_singleton_created"}
        )

    return _entity_service


def reset_entity_service() -> None:
    """
    Reset the global EntityService instance.

    Useful for testing to ensure a fresh instance.
    """
    global _entity_service
    _entity_service = None
