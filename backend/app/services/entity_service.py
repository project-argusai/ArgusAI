"""
Entity Service for Recurring Visitor Detection (Story P4-3.3)

This module provides entity matching functionality for identifying and tracking
recurring visitors using CLIP embeddings. It enables recognition of familiar
faces/vehicles with "first seen", "last seen", and visit count.

Story P9-4.1: Added vehicle entity extraction with signature-based matching
for improved vehicle separation based on color, make, and model.

Architecture:
    - Uses SimilarityService for batch cosine similarity calculations
    - Caches entity embeddings in memory for fast matching
    - Configurable similarity threshold (default 0.75)
    - SQLite-compatible (no pgvector required)
    - P9-4.1: Signature-based matching for vehicles takes priority over embeddings

Flow:
    Event → EmbeddingService (P4-3.1) → EntityService.match_or_create_entity()
                                               ↓
                                    Load entity embeddings (cache or DB)
                                               ↓
                        [Vehicle?] → Try signature-based matching first (P9-4.1)
                                               ↓
                                    Batch cosine similarity (fallback)
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

# Migrated to @singleton decorator (core.decorators) as a core service
reference example for #450 (Lightweight DI Container).
"""
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import uuid

from app.core.decorators import singleton

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.services.similarity_service import (
    SimilarityService,
    get_similarity_service,
    batch_cosine_similarity,
)
from app.services.vehicle_signature_matcher import (
    VehicleSignatureMatcher,
    VehicleEntityInfo,
    extract_vehicle_entity,
)

logger = logging.getLogger(__name__)

# Vehicle signature matching logic has been extracted to VehicleSignatureMatcher

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
    # Copied so the vision prompt can tell a label from stored attributes.
    # Matching itself does not read these.
    vehicle_color: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None


def _text_attr(entity, name: str) -> Optional[str]:
    value = getattr(entity, name, None)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _vehicle_api_fields(entity) -> dict:
    """Read-only vehicle attributes for entity API payloads."""
    return {
        "vehicle_color": _text_attr(entity, "vehicle_color"),
        "vehicle_make": _text_attr(entity, "vehicle_make"),
        "vehicle_model": _text_attr(entity, "vehicle_model"),
        "vehicle_signature": _text_attr(entity, "vehicle_signature"),
    }


def _entity_text_search(search: str):
    """Match every token against name or vehicle color, make, model, or signature.

    LIKE wildcards in the caller's text are escaped so a search for '%' does
    not match every row. Returns None when the query has no tokens.
    """
    from sqlalchemy import and_, or_

    from app.models.recognized_entity import RecognizedEntity

    tokens = [token for token in search.split() if token.strip()][:8]
    if not tokens:
        return None

    columns = (
        RecognizedEntity.name,
        RecognizedEntity.vehicle_color,
        RecognizedEntity.vehicle_make,
        RecognizedEntity.vehicle_model,
        RecognizedEntity.vehicle_signature,
        RecognizedEntity.id,
    )
    clauses = []
    for token in tokens:
        escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        clauses.append(or_(*(column.ilike(pattern, escape="\\") for column in columns)))
    return and_(*clauses)


def _match_result(entity, *, similarity_score: float, is_new: bool) -> EntityMatchResult:
    """Build a match result, including vehicle attributes when the row has them."""
    vehicle = getattr(entity, "entity_type", None) == "vehicle"
    return EntityMatchResult(
        entity_id=entity.id,
        entity_type=entity.entity_type,
        name=entity.name,
        first_seen_at=entity.first_seen_at,
        last_seen_at=entity.last_seen_at,
        occurrence_count=entity.occurrence_count,
        similarity_score=similarity_score,
        is_new=is_new,
        vehicle_color=_text_attr(entity, "vehicle_color") if vehicle else None,
        vehicle_make=_text_attr(entity, "vehicle_make") if vehicle else None,
        vehicle_model=_text_attr(entity, "vehicle_model") if vehicle else None,
    )


def apply_event_thumbnail_to_entity(entity, event) -> None:
    """Copy a sighting thumbnail onto the entity so it survives event retention.

    Writes ``recognized_entities.thumbnail_path`` when the event has a path.
    Prefers the most recent sighting: a newer (or equally recent) event with
    a thumbnail overwrites the stored path. An event without a thumbnail
    never clears an existing path.
    """
    if entity is None or event is None:
        return

    thumbnail = getattr(event, "thumbnail_path", None)
    if not isinstance(thumbnail, str) or not thumbnail.strip():
        return

    event_ts = getattr(event, "timestamp", None)
    last_seen = getattr(entity, "last_seen_at", None)
    if entity.thumbnail_path and event_ts is not None and last_seen is not None:
        try:
            if event_ts < last_seen:
                return
        except TypeError:
            # Mixed aware/naive datetimes — still prefer this sighting.
            pass

    entity.thumbnail_path = thumbnail


# Issue #652: one event can belong to several entities (a person and their car).
# The cap keeps a misclick loop or a scripted client from piling links onto
# one event. Automatic matching rarely produces more than two.
MAX_ENTITIES_PER_EVENT = 4


# Adjustment action names before and after issue #652.
_ADJUSTMENT_ACTION_ALIASES = {
    "add": ("add", "assign"),
    "assign": ("add", "assign"),
    "remove": ("remove", "unlink"),
    "unlink": ("remove", "unlink"),
}


class EventEntityLimitError(Exception):
    """Adding another entity would exceed MAX_ENTITIES_PER_EVENT."""


def parse_entity_id_list(raw) -> list[str]:
    """Parse a stored JSON entity-id list. Malformed values yield no ids.

    Ids are kept as strings (UUIDs or other text ids) and de-duplicated in
    order. Non-string values are dropped so a numeric id can never turn into
    a different entity.
    """
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            values = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
    else:
        return []
    if not isinstance(values, list):
        return []
    ids: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            ids.append(value.strip())
    return list(dict.fromkeys(ids))


def _store_entity_id_list(event, ids: list[str]) -> None:
    """Write ``matched_entity_ids`` (NULL when empty, same as ingest)."""
    cleaned = list(dict.fromkeys(i for i in ids if isinstance(i, str) and i))
    event.matched_entity_ids = json.dumps(cleaned) if cleaned else None


def _set_primary_entity(event, entity, *, similarity_score: Optional[float]) -> None:
    """Point the legacy single-entity ``final_entity_*`` columns at ``entity``."""
    event.final_entity_id = entity.id
    event.final_entity_type = entity.entity_type
    event.final_entity_name = entity.name
    event.final_entity_similarity_score = similarity_score
    event.final_entity_occurrence_count = entity.occurrence_count
    event.final_entity_is_new = False


def _clear_primary_entity(event) -> None:
    event.final_entity_id = None
    event.final_entity_type = None
    event.final_entity_name = None
    event.final_entity_similarity_score = None
    event.final_entity_occurrence_count = None
    event.final_entity_is_new = None


def event_entity_summary(
    entity,
    *,
    similarity_score: Optional[float] = None,
    linked: bool = True,
    is_primary: bool = False,
) -> dict:
    """API shape for one entity on an event (``EventResponse.entities``)."""
    return {
        "id": str(entity.id),
        "name": entity.name,
        "entity_type": entity.entity_type,
        "display_name": entity.display_name,
        **_vehicle_api_fields(entity),
        "similarity_score": similarity_score,
        "linked": linked,
        "is_primary": is_primary,
    }


def build_event_entities(db: Session, events) -> dict[str, list[dict]]:
    """Entities on each event, keyed by event id (issue #652).

    Sources, in display order:
    1. The primary entity (``final_entity_id``) when it is linked or matched.
    2. ``entity_events`` links, oldest first.
    3. Ids in ``matched_entity_ids`` that have no link row. Live Protect
       ingest records named face and vehicle matches only there.

    Ids that no longer resolve to an entity (deleted entities) are skipped.
    Two queries total, regardless of how many events are passed.
    """
    from app.models.recognized_entity import RecognizedEntity, EntityEvent

    events = [e for e in (events or []) if getattr(e, "id", None)]
    if not events:
        return {}
    event_ids = [e.id for e in events]

    link_rows = (
        db.query(
            EntityEvent.event_id,
            EntityEvent.similarity_score,
            RecognizedEntity,
        )
        .join(RecognizedEntity, EntityEvent.entity_id == RecognizedEntity.id)
        .filter(EntityEvent.event_id.in_(event_ids))
        .order_by(EntityEvent.created_at, EntityEvent.entity_id)
        .all()
    )
    links: dict[str, list[tuple]] = {}
    for event_id, similarity, entity in link_rows:
        links.setdefault(event_id, []).append((entity, similarity))

    matched_by_event = {e.id: parse_entity_id_list(getattr(e, "matched_entity_ids", None)) for e in events}
    linked_ids = {eid: {ent.id for ent, _ in rows} for eid, rows in links.items()}
    missing = {
        mid
        for eid, mids in matched_by_event.items()
        for mid in mids
        if mid not in linked_ids.get(eid, set())
    }
    matched_entities: dict[str, object] = {}
    if missing:
        for entity in (
            db.query(RecognizedEntity)
            .filter(RecognizedEntity.id.in_(list(missing)))
            .all()
        ):
            matched_entities[entity.id] = entity

    result: dict[str, list[dict]] = {}
    for event in events:
        primary_id = getattr(event, "final_entity_id", None)
        entries: list[dict] = []
        seen: set[str] = set()
        for entity, similarity in links.get(event.id, []):
            if entity.id in seen:
                continue
            seen.add(entity.id)
            entries.append(
                event_entity_summary(
                    entity,
                    similarity_score=similarity,
                    linked=True,
                    is_primary=entity.id == primary_id,
                )
            )
        for mid in matched_by_event.get(event.id, []):
            entity = matched_entities.get(mid)
            if entity is None or mid in seen:
                continue
            seen.add(mid)
            entries.append(
                event_entity_summary(
                    entity,
                    similarity_score=None,
                    linked=False,
                    is_primary=mid == primary_id,
                )
            )
        # Primary first; the rest keep link/match order.
        entries.sort(key=lambda item: 0 if item["is_primary"] else 1)
        result[event.id] = entries
    return result


def legacy_entity_fields(entities: list[dict]) -> dict:
    """Single-entity ``entity_*`` response fields, taken from the first entity."""
    first = entities[0] if entities else {}
    return {
        "entity_id": first.get("id"),
        "entity_name": first.get("name"),
        "entity_type": first.get("entity_type"),
        "entity_vehicle_color": first.get("vehicle_color"),
        "entity_vehicle_make": first.get("vehicle_make"),
        "entity_vehicle_model": first.get("vehicle_model"),
        "entity_vehicle_signature": first.get("vehicle_signature"),
    }


@singleton
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
        skipped_count = 0
        for entity in entities:
            try:
                if not entity.reference_embedding:
                    skipped_count += 1
                    logger.warning(
                        f"Entity {entity.id} has no reference embedding, skipping",
                        extra={"entity_id": entity.id}
                    )
                    continue
                embedding = json.loads(entity.reference_embedding)
                # Skip empty or invalid embeddings
                if not embedding or not isinstance(embedding, list) or len(embedding) != 512:
                    skipped_count += 1
                    logger.warning(
                        f"Entity {entity.id} has invalid embedding (length={len(embedding) if embedding else 0}), skipping",
                        extra={"entity_id": entity.id, "embedding_length": len(embedding) if embedding else 0}
                    )
                    continue
                self._entity_cache[entity.id] = embedding
            except json.JSONDecodeError:
                skipped_count += 1
                logger.warning(
                    f"Invalid embedding JSON for entity {entity.id}",
                    extra={"entity_id": entity.id}
                )

        self._cache_loaded = True
        load_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Entity cache loaded: {len(self._entity_cache)} entities in {load_time_ms:.2f}ms"
            + (f" ({skipped_count} skipped due to invalid embeddings)" if skipped_count > 0 else ""),
            extra={
                "event_type": "entity_cache_loaded",
                "entity_count": len(self._entity_cache),
                "skipped_count": skipped_count,
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

        # Get event timestamp and thumbnail for temporal tracking / durable copy
        event = db.query(Event).filter(Event.id == event_id).first()
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

            return _match_result(entity, similarity_score=best_score, is_new=False)
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

    # _find_entity_by_vehicle_signature has been moved to VehicleSignatureMatcher
    # (see vehicle_signature_matcher.py)

    async def match_or_create_vehicle_entity(
        self,
        db: Session,
        event_id: str,
        embedding: list[float],
        description: Optional[str] = None,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> EntityMatchResult:
        """
        Match or create a vehicle entity with signature-based matching (Story P9-4.1).

        This method first attempts signature-based matching before falling back to
        embedding-based matching. This ensures vehicles with the same color/make/model
        are grouped together even if their embeddings differ slightly.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event being matched
            embedding: CLIP embedding vector (512-dim)
            description: AI-generated event description for vehicle extraction
            threshold: Minimum similarity score for embedding matching (default 0.75)

        Returns:
            EntityMatchResult with entity details and match info
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.event import Event

        start_time = time.time()

        # Get event timestamp and thumbnail for temporal tracking / durable copy
        event = db.query(Event).filter(Event.id == event_id).first()
        event_timestamp = event.timestamp if event else datetime.now(timezone.utc)

        # Try to extract vehicle info from description
        vehicle_info = None
        if description:
            vehicle_info = extract_vehicle_entity(description)

        # Priority 1: Signature-based matching (P9-4.1)
        if vehicle_info and vehicle_info.signature:
            matcher = VehicleSignatureMatcher()
            existing_entity_id = matcher.find_entity_by_signature(db, vehicle_info.signature)
            if existing_entity_id:
                result = await self._update_existing_entity(
                    db, existing_entity_id, event_id, 0.95, event_timestamp
                )
                match_time_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"Vehicle matched by signature: {vehicle_info.signature}",
                    extra={
                        "event_type": "vehicle_signature_matched",
                        "event_id": event_id,
                        "entity_id": existing_entity_id,
                        "signature": vehicle_info.signature,
                        "match_time_ms": round(match_time_ms, 2),
                    }
                )
                return result

        # Priority 2: Embedding-based matching (fallback)
        if not self._cache_loaded:
            self._load_entity_cache(db)

        # If no entities exist, create first one
        if not self._entity_cache:
            result = await self._create_new_entity(
                db, event_id, embedding, "vehicle", event_timestamp, vehicle_info
            )
            match_time_ms = (time.time() - start_time) * 1000
            logger.info(
                f"First vehicle entity created for event {event_id}",
                extra={
                    "event_type": "vehicle_entity_created_first",
                    "event_id": event_id,
                    "entity_id": result.entity_id,
                    "signature": vehicle_info.signature if vehicle_info else None,
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
            matched_entity_id = entity_ids[best_idx]
            result = await self._update_existing_entity(
                db, matched_entity_id, event_id, best_score, event_timestamp
            )
            logger.info(
                f"Vehicle matched by embedding for event {event_id}",
                extra={
                    "event_type": "vehicle_embedding_matched",
                    "event_id": event_id,
                    "entity_id": matched_entity_id,
                    "similarity_score": round(best_score, 4),
                    "match_time_ms": round(match_time_ms, 2),
                }
            )
            return result
        else:
            result = await self._create_new_entity(
                db, event_id, embedding, "vehicle", event_timestamp, vehicle_info
            )
            logger.info(
                f"New vehicle entity created for event {event_id}",
                extra={
                    "event_type": "vehicle_entity_created_new",
                    "event_id": event_id,
                    "entity_id": result.entity_id,
                    "signature": vehicle_info.signature if vehicle_info else None,
                    "match_time_ms": round(match_time_ms, 2),
                }
            )
            return result

    async def _create_new_entity(
        self,
        db: Session,
        event_id: str,
        embedding: list[float],
        entity_type: str,
        event_timestamp: datetime,
        vehicle_info: Optional[VehicleEntityInfo] = None,
        event=None,
    ) -> EntityMatchResult:
        """Create a new entity and link it to the event."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.event import Event

        entity_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        if event is None:
            event = db.query(Event).filter(Event.id == event_id).first()

        # Create entity with vehicle fields if applicable (P9-4.1)
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
        apply_event_thumbnail_to_entity(new_entity, event)

        # Set vehicle-specific fields if available
        if vehicle_info and entity_type == "vehicle":
            new_entity.vehicle_color = vehicle_info.color
            new_entity.vehicle_make = vehicle_info.make
            new_entity.vehicle_model = vehicle_info.model
            new_entity.vehicle_signature = vehicle_info.signature

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

        return _match_result(
            new_entity,
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
        event=None,
    ) -> EntityMatchResult:
        """Update an existing entity with new occurrence and link to event."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.event import Event

        now = datetime.now(timezone.utc)

        # Update entity
        entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity:
            raise ValueError(f"Entity {entity_id} not found")

        if event is None:
            event = db.query(Event).filter(Event.id == event_id).first()

        # Copy thumbnail before last_seen so an older sighting cannot overwrite
        apply_event_thumbnail_to_entity(entity, event)

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

        return _match_result(entity, similarity_score=similarity_score, is_new=False)

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
            search: Case-insensitive match on name or vehicle color, make, model, or signature

        Returns:
            Tuple of (list of entity dicts, total count)
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.event import Event

        query = db.query(RecognizedEntity)

        if entity_type:
            query = query.filter(RecognizedEntity.entity_type == entity_type)

        if named_only:
            query = query.filter(RecognizedEntity.name.isnot(None))

        if search and search.strip():
            text_filter = _entity_text_search(search)
            if text_filter is not None:
                query = query.filter(text_filter)

        total = query.count()

        entities = query.order_by(
            desc(RecognizedEntity.last_seen_at)
        ).offset(offset).limit(limit).all()

        # Get the most recent event thumbnail for each entity
        entity_ids = [e.id for e in entities]
        entity_thumbnails = {}

        if entity_ids:
            # Get the most recent event's thumbnail for each entity
            for entity_id in entity_ids:
                most_recent_event = db.query(Event.thumbnail_path).join(
                    EntityEvent, EntityEvent.event_id == Event.id
                ).filter(
                    EntityEvent.entity_id == entity_id,
                    Event.thumbnail_path.isnot(None)
                ).order_by(
                    desc(Event.timestamp)
                ).first()

                if most_recent_event and most_recent_event.thumbnail_path:
                    entity_thumbnails[entity_id] = most_recent_event.thumbnail_path

        return [
            {
                "id": e.id,
                "entity_type": e.entity_type,
                "name": e.name,
                "notes": e.notes,
                "thumbnail_path": e.thumbnail_path or entity_thumbnails.get(e.id),
                "first_seen_at": e.first_seen_at,
                "last_seen_at": e.last_seen_at,
                "occurrence_count": e.occurrence_count,
                "is_vip": e.is_vip,
                "is_blocked": e.is_blocked,
                **_vehicle_api_fields(e),
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
            **_vehicle_api_fields(entity),
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
        vehicle_color: Optional[str] = None,
        vehicle_make: Optional[str] = None,
        vehicle_model: Optional[str] = None,
        reference_image: Optional[str] = None,
    ) -> dict:
        """
        Create a new entity manually (Story P7-4.1, P10-4.2).

        Args:
            db: SQLAlchemy database session
            entity_type: Type of entity (person, vehicle, unknown)
            name: User-assigned name (optional)
            notes: User notes about the entity (optional)
            thumbnail_path: Path to thumbnail image (optional)
            is_vip: Whether entity is VIP (default False)
            is_blocked: Whether entity is blocked (default False)
            vehicle_color: Vehicle color for vehicle entities (optional)
            vehicle_make: Vehicle make for vehicle entities (optional)
            vehicle_model: Vehicle model for vehicle entities (optional)
            reference_image: Base64 encoded reference image (optional)

        Returns:
            Created entity dict
        """
        from app.models.recognized_entity import RecognizedEntity

        now = datetime.now(timezone.utc)
        entity_id = str(uuid.uuid4())

        # Story P10-4.2: Generate vehicle signature from color, make, model
        vehicle_signature = None
        if entity_type == "vehicle":
            signature_parts = []
            if vehicle_color:
                signature_parts.append(vehicle_color.lower().strip())
            if vehicle_make:
                signature_parts.append(vehicle_make.lower().strip())
            if vehicle_model:
                # Remove special characters from model
                model_clean = vehicle_model.lower().strip().replace("-", "").replace(" ", "")
                signature_parts.append(model_clean)
            if signature_parts:
                vehicle_signature = "-".join(signature_parts)

        # Story P10-4.2: Handle reference image upload
        saved_thumbnail_path = thumbnail_path
        if reference_image:
            saved_thumbnail_path = await self._save_reference_image(entity_id, reference_image)

        # Create entity with placeholder embedding (empty JSON array)
        new_entity = RecognizedEntity(
            id=entity_id,
            entity_type=entity_type,
            name=name,
            notes=notes,
            thumbnail_path=saved_thumbnail_path,
            reference_embedding="[]",  # Placeholder until recognition assigns real embedding
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=0,  # 0 until matched via recognition
            is_vip=is_vip,
            is_blocked=is_blocked,
            vehicle_color=vehicle_color.lower().strip() if vehicle_color else None,
            vehicle_make=vehicle_make.lower().strip() if vehicle_make else None,
            vehicle_model=vehicle_model.lower().strip() if vehicle_model else None,
            vehicle_signature=vehicle_signature,
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
                "entity_name": name,
                "vehicle_signature": vehicle_signature,
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
            **_vehicle_api_fields(new_entity),
            "created_at": new_entity.created_at,
            "updated_at": new_entity.updated_at,
        }

    async def _save_reference_image(
        self,
        entity_id: str,
        base64_image: str,
    ) -> Optional[str]:
        """
        Save a base64 encoded reference image for an entity (Story P10-4.2).

        Args:
            entity_id: Entity UUID
            base64_image: Base64 encoded image data

        Returns:
            Path to saved image or None if failed
        """
        import base64
        import os
        from pathlib import Path

        try:
            # Decode base64 image
            # Handle data URL format: "data:image/jpeg;base64,..."
            if "," in base64_image:
                base64_image = base64_image.split(",", 1)[1]

            image_data = base64.b64decode(base64_image)

            # Check size limit (2MB)
            if len(image_data) > 2 * 1024 * 1024:
                logger.warning(f"Reference image too large for entity {entity_id}")
                return None

            # Create entity images directory
            images_dir = Path("data/entity-images")
            images_dir.mkdir(parents=True, exist_ok=True)

            # Save image
            image_path = images_dir / f"{entity_id}.jpg"
            with open(image_path, "wb") as f:
                f.write(image_data)

            logger.info(f"Saved reference image for entity {entity_id}")
            return str(image_path)

        except Exception as e:
            logger.error(f"Failed to save reference image for entity {entity_id}: {e}")
            return None

    async def update_entity(
        self,
        db: Session,
        entity_id: str,
        name: Optional[str] = None,
        entity_type: Optional[str] = None,
        notes: Optional[str] = None,
        is_vip: Optional[bool] = None,
        is_blocked: Optional[bool] = None,
    ) -> Optional[dict]:
        """
        Update an entity's metadata.

        Story P16-3.1: Create Entity Update API Endpoint

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity
            name: New name for the entity (None to keep unchanged)
            entity_type: Entity type (person, vehicle, unknown) (None to keep unchanged)
            notes: New notes for the entity (None to keep unchanged)
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
        if entity_type is not None:
            entity.entity_type = entity_type
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
            **_vehicle_api_fields(entity),
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

    async def get_entity_events_paginated(
        self,
        db: Session,
        entity_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """
        Get paginated events for an entity (Story P9-4.2).

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity
            limit: Maximum number of events per page (default 20)
            offset: Pagination offset

        Returns:
            Dict with "events" list and "total" count
        """
        events, total = await self.get_entity_events(
            db=db,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )
        return {
            "events": events,
            "total": total,
        }

    async def get_entity_thumbnail_path(
        self,
        db: Session,
        entity_id: str,
    ) -> Optional[str]:
        """
        Get the thumbnail path for an entity (Story P7-4.1).

        Prefers the durable column on recognized_entities, then falls back
        to the latest live Event.thumbnail_path via EntityEvent (same as
        get_all_entities). The column is what survives event retention.

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity

        Returns:
            Thumbnail file path, or None if entity not found or has no thumbnail
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.event import Event

        entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity:
            return None

        if entity.thumbnail_path:
            return entity.thumbnail_path

        most_recent_event = db.query(Event.thumbnail_path).join(
            EntityEvent, EntityEvent.event_id == Event.id
        ).filter(
            EntityEvent.entity_id == entity_id,
            Event.thumbnail_path.isnot(None)
        ).order_by(
            desc(Event.timestamp)
        ).first()

        if most_recent_event and most_recent_event.thumbnail_path:
            return most_recent_event.thumbnail_path

        return None

    async def unlink_event(
        self,
        db: Session,
        entity_id: str,
        event_id: str,
    ) -> bool:
        """
        Remove one entity from an event (Story P9-4.3, issue #652).

        Other entities on the event stay. Removes the ``entity_events`` row
        when there is one, drops the id from ``matched_entity_ids``, and
        moves the primary (``final_entity_*``) to the next remaining entity
        when the removed one was primary. Writes an EntityAdjustment with
        action="remove" for ML training.

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity
            event_id: UUID of the event to unlink

        Returns:
            True if removed, False if the entity was not on this event

        Note:
            - Does NOT delete the event itself, only the association
            - Decrements occurrence_count only when a link row is deleted
              (a match-only entry never incremented it)
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.entity_adjustment import EntityAdjustment
        from app.models.event import Event

        entity_event = db.query(EntityEvent).filter(
            EntityEvent.entity_id == entity_id,
            EntityEvent.event_id == event_id,
        ).first()

        event = db.query(Event).filter(Event.id == event_id).first()
        matched_ids = parse_entity_id_list(event.matched_entity_ids) if event else []
        is_primary = bool(event is not None and event.final_entity_id == entity_id)

        if not entity_event and entity_id not in matched_ids and not is_primary:
            logger.warning(
                "Entity is not on this event; nothing to remove",
                extra={
                    "event_type": "unlink_event_not_found",
                    "entity_id": entity_id,
                    "event_id": event_id,
                }
            )
            return False

        entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity:
            logger.warning(
                "Entity not found for unlink",
                extra={
                    "event_type": "unlink_entity_not_found",
                    "entity_id": entity_id,
                }
            )
            return False

        db.add(EntityAdjustment(
            event_id=event_id,
            old_entity_id=entity_id,
            new_entity_id=None,
            action="remove",
            event_description=event.description if event else None,
        ))

        if entity_event:
            db.delete(entity_event)
            if entity.occurrence_count > 0:
                entity.occurrence_count -= 1
                entity.updated_at = datetime.now(timezone.utc)

        if event is not None:
            _store_entity_id_list(event, [i for i in matched_ids if i != entity_id])
            if is_primary:
                self._promote_next_primary(db, event, exclude_entity_id=entity_id)

        db.commit()

        logger.info(
            "Entity removed from event",
            extra={
                "event_type": "event_unlinked",
                "entity_id": entity_id,
                "event_id": event_id,
                "had_link": bool(entity_event),
                "new_occurrence_count": entity.occurrence_count,
            }
        )

        return True

    def _promote_next_primary(self, db: Session, event, *, exclude_entity_id: str) -> None:
        """Make the oldest remaining entity primary, or clear the primary."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        row = (
            db.query(RecognizedEntity, EntityEvent.similarity_score)
            .join(EntityEvent, EntityEvent.entity_id == RecognizedEntity.id)
            .filter(
                EntityEvent.event_id == event.id,
                EntityEvent.entity_id != exclude_entity_id,
            )
            .order_by(EntityEvent.created_at, EntityEvent.entity_id)
            .first()
        )
        if row is not None:
            _set_primary_entity(event, row[0], similarity_score=row[1])
            return

        for candidate_id in parse_entity_id_list(event.matched_entity_ids):
            if candidate_id == exclude_entity_id:
                continue
            candidate = db.query(RecognizedEntity).filter(
                RecognizedEntity.id == candidate_id
            ).first()
            if candidate is not None:
                _set_primary_entity(event, candidate, similarity_score=None)
                return

        _clear_primary_entity(event)

    async def get_event_entities(self, db: Session, event_id: str) -> list[dict]:
        """All entities on one event, primary first (issue #652)."""
        from app.models.event import Event

        event = db.query(Event).filter(Event.id == event_id).first()
        if event is None:
            return []
        return build_event_entities(db, [event]).get(event.id, [])

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

    async def assign_event(
        self,
        db: Session,
        event_id: str,
        entity_id: str,
        replace: bool = False,
    ) -> dict:
        """
        Add an entity to an event, or replace the event's entities
        (Story P9-4.4, issue #652).

        Default (``replace=False``): *adds* a link. Entities already on the
        event stay. At most ``MAX_ENTITIES_PER_EVENT`` entities per event.

        ``replace=True``: the correction path. Every other entity is removed
        from the event (``move_from`` adjustments, occurrence counts
        decremented) and the target becomes the only, primary entity.

        Both paths keep ``matched_entity_ids`` in sync with the links so
        alert rules see the same set, and set the primary
        (``final_entity_*``) when the event had none.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event to assign
            entity_id: UUID of the target entity
            replace: Remove other entities from the event first

        Returns:
            Dict with success, message, action ("add", "replace" or "none"),
            entity_id, entity_name, and the event's ``entities`` afterwards

        Raises:
            ValueError: If event or entity not found
            EventEntityLimitError: If adding would exceed the per-event cap
        """
        from sqlalchemy.exc import IntegrityError

        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.entity_adjustment import EntityAdjustment
        from app.models.event import Event

        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise ValueError(f"Event not found: {event_id}")

        target_entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()
        if not target_entity:
            raise ValueError(f"Entity not found: {entity_id}")

        existing_links = db.query(EntityEvent).filter(
            EntityEvent.event_id == event_id
        ).all()
        links_by_entity = {link.entity_id: link for link in existing_links}
        matched_ids = parse_entity_id_list(event.matched_entity_ids)
        current_ids = list(dict.fromkeys(list(links_by_entity) + matched_ids))

        target_link = links_by_entity.get(entity_id)
        others = [i for i in current_ids if i != entity_id]
        now = datetime.now(timezone.utc)
        label = target_entity.display_name

        if not replace or not others:
            if target_link is not None:
                # Already linked. Heal matched_entity_ids if it drifted.
                if entity_id not in matched_ids:
                    _store_entity_id_list(event, matched_ids + [entity_id])
                    db.commit()
                return {
                    "success": True,
                    "message": f"Event already linked to {label}",
                    "action": "none",
                    "entity_id": entity_id,
                    "entity_name": target_entity.name,
                    "entities": build_event_entities(db, [event]).get(event.id, []),
                }
            if entity_id not in current_ids and len(current_ids) >= MAX_ENTITIES_PER_EVENT:
                raise EventEntityLimitError(
                    f"An event can have at most {MAX_ENTITIES_PER_EVENT} entities. "
                    "Remove one before adding another."
                )
            action = "add"
            removed_ids: list[str] = []
        else:
            action = "replace"
            removed_ids = others

        # Replace: take every other entity off the event first.
        for old_id in removed_ids:
            db.add(EntityAdjustment(
                event_id=event_id,
                old_entity_id=old_id,
                new_entity_id=entity_id,
                action="move_from",
                event_description=event.description,
            ))
            old_link = links_by_entity.get(old_id)
            if old_link is not None:
                old_entity = db.query(RecognizedEntity).filter(
                    RecognizedEntity.id == old_id
                ).first()
                if old_entity and old_entity.occurrence_count > 0:
                    old_entity.occurrence_count -= 1
                    old_entity.updated_at = now
                db.delete(old_link)

        if target_link is None:
            db.add(EntityEvent(
                entity_id=entity_id,
                event_id=event_id,
                similarity_score=1.0,  # Manual assignment = 100% match
                created_at=now,
            ))
            db.add(EntityAdjustment(
                event_id=event_id,
                old_entity_id=removed_ids[0] if removed_ids else None,
                new_entity_id=entity_id,
                action="move_to" if removed_ids else "add",
                event_description=event.description,
            ))
            apply_event_thumbnail_to_entity(target_entity, event)
            target_entity.occurrence_count = (target_entity.occurrence_count or 0) + 1
            last_seen = target_entity.last_seen_at
            try:
                if last_seen is None or (event.timestamp and event.timestamp > last_seen):
                    target_entity.last_seen_at = event.timestamp
            except TypeError:
                # Mixed aware/naive datetimes: keep the old behavior.
                target_entity.last_seen_at = event.timestamp
            target_entity.updated_at = now

        if action == "replace":
            _store_entity_id_list(event, [entity_id])
            _set_primary_entity(event, target_entity, similarity_score=1.0)
        else:
            _store_entity_id_list(event, matched_ids + [entity_id])
            if not event.final_entity_id:
                _set_primary_entity(event, target_entity, similarity_score=1.0)

        try:
            db.commit()
        except IntegrityError:
            # Another request linked the same pair first. Treat as no-op.
            db.rollback()
            event = db.query(Event).filter(Event.id == event_id).first()
            return {
                "success": True,
                "message": f"Event already linked to {label}",
                "action": "none",
                "entity_id": entity_id,
                "entity_name": target_entity.name,
                "entities": build_event_entities(db, [event]).get(event_id, []) if event else [],
            }

        logger.info(
            "Entity assigned to event",
            extra={
                "event_type": "event_moved" if action == "replace" else "event_assigned",
                "event_id": event_id,
                "entity_id": entity_id,
                "action": action,
                "removed_entity_count": len(removed_ids),
            }
        )

        message = f"Event {'moved to' if action == 'replace' else 'added to'} {label}"

        return {
            "success": True,
            "message": message,
            "action": action,
            "entity_id": entity_id,
            "entity_name": target_entity.name,
            "entities": build_event_entities(db, [event]).get(event.id, []),
        }

    async def merge_entities(
        self,
        db: Session,
        primary_entity_id: str,
        secondary_entity_id: str,
    ) -> dict:
        """
        Merge two entities into one (Story P9-4.5).

        Moves all events from the secondary entity to the primary entity,
        creates EntityAdjustment records for ML training, updates occurrence
        counts, and deletes the secondary entity.

        Args:
            db: SQLAlchemy database session
            primary_entity_id: UUID of the entity to keep (receives all events)
            secondary_entity_id: UUID of the entity to merge and delete

        Returns:
            Dict with success status, merged entity info, events moved count

        Raises:
            ValueError: If entities not found or are the same
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.entity_adjustment import EntityAdjustment
        from app.models.event import Event

        # Validate inputs
        if primary_entity_id == secondary_entity_id:
            raise ValueError("Cannot merge an entity with itself")

        # Get both entities
        primary = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == primary_entity_id
        ).first()
        if not primary:
            raise ValueError(f"Primary entity not found: {primary_entity_id}")

        secondary = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == secondary_entity_id
        ).first()
        if not secondary:
            raise ValueError(f"Secondary entity not found: {secondary_entity_id}")

        # Get all events linked to secondary entity
        secondary_event_links = db.query(EntityEvent).filter(
            EntityEvent.entity_id == secondary_entity_id
        ).all()

        events_moved = 0
        now = datetime.now(timezone.utc)

        # Issue #652: an event can already be linked to both entities. Those
        # links collapse into the primary's existing row instead of moving
        # (the (entity_id, event_id) primary key allows only one).
        overlap_event_ids: set[str] = set()
        secondary_event_ids = [link.event_id for link in secondary_event_links]
        if secondary_event_ids:
            overlap_event_ids = {
                row[0]
                for row in db.query(EntityEvent.event_id).filter(
                    EntityEvent.entity_id == primary_entity_id,
                    EntityEvent.event_id.in_(secondary_event_ids),
                ).all()
            }

        # Move each event and create adjustment records
        for link in secondary_event_links:
            # Get event description for ML training
            event = db.query(Event.description).filter(
                Event.id == link.event_id
            ).first()
            event_description = event.description if event else None

            # Create EntityAdjustment record for merge operation
            adjustment = EntityAdjustment(
                event_id=link.event_id,
                old_entity_id=secondary_entity_id,
                new_entity_id=primary_entity_id,
                action="merge",
                event_description=event_description,
            )
            db.add(adjustment)

            if link.event_id in overlap_event_ids:
                # Primary already on this event: drop the duplicate link.
                db.delete(link)
            else:
                # Update the link to point to primary entity
                link.entity_id = primary_entity_id
                link.created_at = now  # Update timestamp

            events_moved += 1

        # Update primary entity occurrence count. An event both entities were
        # on is one sighting of the merged entity, not two.
        primary.occurrence_count += max(
            (secondary.occurrence_count or 0) - len(overlap_event_ids), 0
        )
        primary.updated_at = now

        # Keep alert-rule ids and the primary column pointing at a live entity.
        self._repoint_event_entity_refs(db, secondary_entity_id, primary)

        # Update last_seen_at if secondary was seen more recently
        if secondary.last_seen_at > primary.last_seen_at:
            primary.last_seen_at = secondary.last_seen_at
            if secondary.thumbnail_path:
                primary.thumbnail_path = secondary.thumbnail_path
        elif not primary.thumbnail_path and secondary.thumbnail_path:
            primary.thumbnail_path = secondary.thumbnail_path

        # Update first_seen_at if secondary was seen earlier
        if secondary.first_seen_at < primary.first_seen_at:
            primary.first_seen_at = secondary.first_seen_at

        # Store secondary info before deletion
        secondary_id = secondary.id
        secondary_name = secondary.name

        # Write the moved links before deleting the secondary. Sessions run
        # with autoflush=False, and the entity_events relationship cascades
        # deletes: without this flush the cascade still sees the old rows and
        # deletes every link that was just moved to the primary.
        db.flush()

        # Delete secondary entity (EntityEvent links already moved)
        db.delete(secondary)

        db.commit()

        # Remove secondary from cache
        if secondary_id in self._entity_cache:
            del self._entity_cache[secondary_id]

        logger.info(
            f"Entities merged: {secondary_id} -> {primary_entity_id}",
            extra={
                "event_type": "entities_merged",
                "primary_entity_id": primary_entity_id,
                "secondary_entity_id": secondary_id,
                "events_moved": events_moved,
                "new_occurrence_count": primary.occurrence_count,
            }
        )

        return {
            "success": True,
            "merged_entity_id": primary_entity_id,
            "merged_entity_name": primary.name,
            "events_moved": events_moved,
            "deleted_entity_id": secondary_id,
            "deleted_entity_name": secondary_name,
            "message": f"Merged {events_moved} event(s) into {primary.name or 'entity'}",
        }

    def _repoint_event_entity_refs(self, db: Session, old_entity_id: str, new_entity) -> None:
        """Rewrite ``matched_entity_ids`` / ``final_entity_*`` after a merge."""
        from sqlalchemy import or_

        from app.models.event import Event

        events = db.query(Event).filter(
            or_(
                Event.final_entity_id == old_entity_id,
                Event.matched_entity_ids.contains(json.dumps(old_entity_id), autoescape=True),
            )
        ).all()
        for event in events:
            ids = parse_entity_id_list(event.matched_entity_ids)
            if old_entity_id in ids:
                _store_entity_id_list(
                    event,
                    [new_entity.id if i == old_entity_id else i for i in ids],
                )
            if event.final_entity_id == old_entity_id:
                _set_primary_entity(
                    event,
                    new_entity,
                    similarity_score=event.final_entity_similarity_score,
                )

    async def get_adjustments(
        self,
        db: Session,
        limit: int = 50,
        offset: int = 0,
        action: Optional[str] = None,
        entity_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[dict], int]:
        """
        Get entity adjustments with pagination and filtering (Story P9-4.6).

        Args:
            db: SQLAlchemy database session
            limit: Maximum number of adjustments to return (default 50)
            offset: Pagination offset
            action: Filter by action type (add, remove, move_from, move_to, merge;
                "assign"/"unlink" are aliases for add/remove, "move" for move_*)
            entity_id: Filter by entity ID (matches old or new entity)
            start_date: Filter adjustments from this date
            end_date: Filter adjustments until this date

        Returns:
            Tuple of (list of adjustment dicts, total count)
        """
        from app.models.entity_adjustment import EntityAdjustment
        from sqlalchemy import or_

        query = db.query(EntityAdjustment)

        # Apply filters
        if action:
            # Handle "move" as alias for move_from/move_to
            if action == "move":
                query = query.filter(
                    or_(
                        EntityAdjustment.action == "move_from",
                        EntityAdjustment.action == "move_to"
                    )
                )
            elif action in _ADJUSTMENT_ACTION_ALIASES:
                # Issue #652 renamed assign/unlink to add/remove. Filtering by
                # either name returns old and new rows.
                query = query.filter(
                    EntityAdjustment.action.in_(_ADJUSTMENT_ACTION_ALIASES[action])
                )
            else:
                query = query.filter(EntityAdjustment.action == action)

        if entity_id:
            query = query.filter(
                or_(
                    EntityAdjustment.old_entity_id == entity_id,
                    EntityAdjustment.new_entity_id == entity_id
                )
            )

        if start_date:
            query = query.filter(EntityAdjustment.created_at >= start_date)

        if end_date:
            query = query.filter(EntityAdjustment.created_at <= end_date)

        # Get total count
        total = query.count()

        # Get paginated results
        adjustments = query.order_by(
            desc(EntityAdjustment.created_at)
        ).offset(offset).limit(limit).all()

        logger.debug(
            f"Retrieved {len(adjustments)} adjustments (total: {total})",
            extra={
                "event_type": "adjustments_retrieved",
                "count": len(adjustments),
                "total": total,
                "action_filter": action,
                "entity_filter": entity_id,
            }
        )

        return [
            {
                "id": a.id,
                "event_id": a.event_id,
                "old_entity_id": a.old_entity_id,
                "new_entity_id": a.new_entity_id,
                "action": a.action,
                "event_description": a.event_description,
                "created_at": a.created_at,
            }
            for a in adjustments
        ], total

    async def export_adjustments(
        self,
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Export all adjustments for ML training (Story P9-4.6).

        Returns adjustment records in a format suitable for JSON Lines export,
        including event descriptions for training context.

        Args:
            db: SQLAlchemy database session
            start_date: Filter adjustments from this date
            end_date: Filter adjustments until this date

        Returns:
            List of adjustment dicts suitable for ML training
        """
        from app.models.entity_adjustment import EntityAdjustment
        from app.models.recognized_entity import RecognizedEntity

        query = db.query(EntityAdjustment)

        if start_date:
            query = query.filter(EntityAdjustment.created_at >= start_date)

        if end_date:
            query = query.filter(EntityAdjustment.created_at <= end_date)

        adjustments = query.order_by(EntityAdjustment.created_at).all()

        # Get entity types for enrichment
        entity_ids = set()
        for a in adjustments:
            if a.old_entity_id:
                entity_ids.add(a.old_entity_id)
            if a.new_entity_id:
                entity_ids.add(a.new_entity_id)

        entity_types = {}
        if entity_ids:
            entities = db.query(
                RecognizedEntity.id, RecognizedEntity.entity_type
            ).filter(RecognizedEntity.id.in_(entity_ids)).all()
            entity_types = {e.id: e.entity_type for e in entities}

        logger.info(
            f"Exporting {len(adjustments)} adjustments for ML training",
            extra={
                "event_type": "adjustments_exported",
                "count": len(adjustments),
            }
        )

        return [
            {
                "event_id": a.event_id,
                "action": a.action,
                "old_entity_id": a.old_entity_id,
                "new_entity_id": a.new_entity_id,
                "old_entity_type": entity_types.get(a.old_entity_id) if a.old_entity_id else None,
                "new_entity_type": entity_types.get(a.new_entity_id) if a.new_entity_id else None,
                "event_description": a.event_description,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in adjustments
        ]


# Backward compatible thin getter (delegates to @singleton decorator)
def get_entity_service() -> EntityService:
    """
    Get the global EntityService instance.

    Returns:
        EntityService singleton instance

    Note: This is now a thin backward-compatible wrapper.
          New code can simply use EntityService() directly.
    """
    return EntityService()


def reset_entity_service() -> None:
    """
    Reset the global EntityService instance.

    Useful for testing to ensure a fresh instance (clears embedding caches, etc.).
    """
    EntityService._reset_instance()
