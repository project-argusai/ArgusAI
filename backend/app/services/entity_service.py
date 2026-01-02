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
"""
import json
import logging
import re
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

# Story P9-4.1: Vehicle extraction constants
VEHICLE_COLORS = [
    "white", "black", "silver", "gray", "grey", "red", "blue",
    "green", "brown", "tan", "beige", "gold", "yellow", "orange",
    "purple", "maroon", "navy", "dark", "light", "bright"
]

VEHICLE_MAKES = [
    # American
    "ford", "chevrolet", "chevy", "gmc", "dodge", "ram", "jeep", "chrysler",
    "lincoln", "cadillac", "buick", "tesla", "rivian",
    # Japanese
    "toyota", "honda", "nissan", "mazda", "subaru", "mitsubishi", "lexus",
    "acura", "infiniti", "suzuki",
    # Korean
    "hyundai", "kia", "genesis",
    # German
    "bmw", "mercedes", "mercedes-benz", "audi", "volkswagen", "vw", "porsche",
    # European
    "volvo", "jaguar", "land rover", "range rover", "mini", "fiat", "alfa romeo",
]

# Common vehicle models for extraction
VEHICLE_MODELS = [
    # Toyota
    "camry", "corolla", "rav4", "highlander", "tacoma", "tundra", "prius", "4runner",
    # Honda
    "civic", "accord", "cr-v", "pilot", "odyssey", "fit", "hr-v",
    # Ford
    "f-150", "f150", "f-250", "f250", "mustang", "explorer", "escape", "bronco", "ranger",
    # Chevrolet
    "silverado", "malibu", "equinox", "tahoe", "suburban", "colorado", "camaro", "corvette",
    # Nissan
    "altima", "sentra", "rogue", "pathfinder", "frontier", "maxima", "murano",
    # BMW
    "3 series", "5 series", "x3", "x5", "m3", "m5",
    # Tesla
    "model 3", "model s", "model x", "model y", "cybertruck",
    # Jeep
    "wrangler", "grand cherokee", "cherokee", "compass", "gladiator",
    # Others
    "outback", "forester", "cx-5", "cx-9", "elantra", "sonata", "tucson", "santa fe",
]

# Words to skip when extracting models (common words that aren't models)
SKIP_WORDS = [
    # Vehicle types
    "car", "truck", "van", "suv", "vehicle", "auto", "sedan", "coupe",
    "hatchback", "convertible", "wagon", "crossover", "pickup", "minivan",
    # Verbs/actions
    "pulling", "parked", "driving", "arrived", "leaving", "stopped",
    "turning", "moving", "approaching", "backing", "entering", "exiting",
    # Common words
    "is", "was", "has", "had", "the", "at", "in", "on", "to", "from",
    "just", "still", "now", "then", "here", "there", "this", "that",
    # Adjectives
    "small", "large", "big", "old", "new", "used", "nice", "beautiful",
]


@dataclass
class VehicleEntityInfo:
    """Extracted vehicle entity information from AI description."""
    color: Optional[str]
    make: Optional[str]
    model: Optional[str]
    signature: Optional[str]

    def is_valid(self) -> bool:
        """Check if minimum data requirements are met (color+make OR make+model)."""
        has_color = self.color is not None
        has_make = self.make is not None
        has_model = self.model is not None
        return (has_color and has_make) or (has_make and has_model)


def extract_vehicle_entity(description: str) -> Optional[VehicleEntityInfo]:
    """
    Extract vehicle details from AI description (Story P9-4.1).

    Args:
        description: AI-generated event description

    Returns:
        VehicleEntityInfo with color, make, model, signature if sufficient data.
        None if insufficient data (need color+make OR make+model).

    Examples:
        >>> extract_vehicle_entity("A white Toyota Camry pulled into the driveway")
        VehicleEntityInfo(color='white', make='toyota', model='camry', signature='white-toyota-camry')

        >>> extract_vehicle_entity("Black Ford F-150 parked on street")
        VehicleEntityInfo(color='black', make='ford', model='f150', signature='black-ford-f150')

        >>> extract_vehicle_entity("A red car passed by")  # Only color, no make/model
        None
    """
    if not description:
        return None

    desc_lower = description.lower()

    # Extract color
    extracted_color = None
    for color in VEHICLE_COLORS:
        if re.search(rf'\b{color}\b', desc_lower):
            # Normalize gray/grey
            if color == "grey":
                color = "gray"
            extracted_color = color
            break

    # Extract make - find first occurrence in text
    extracted_make = None
    earliest_pos = len(desc_lower) + 1

    for make in VEHICLE_MAKES:
        match = re.search(rf'\b{re.escape(make)}\b', desc_lower)
        if match and match.start() < earliest_pos:
            earliest_pos = match.start()
            # Normalize make names
            if make in ["chevy"]:
                extracted_make = "chevrolet"
            elif make in ["vw"]:
                extracted_make = "volkswagen"
            elif make in ["mercedes-benz"]:
                extracted_make = "mercedes"
            elif make in ["range rover"]:
                extracted_make = "land rover"
            else:
                extracted_make = make

    # Extract model from known models list
    extracted_model = None
    for model in VEHICLE_MODELS:
        # Handle models with special chars like F-150
        model_pattern = re.escape(model).replace(r'\-', r'[-\s]?')
        if re.search(rf'\b{model_pattern}\b', desc_lower):
            # Normalize model names (remove hyphens, standardize)
            normalized_model = model.replace("-", "").replace(" ", "")
            extracted_model = normalized_model
            break

    # If no model from known list, try pattern-based extraction
    if not extracted_model and extracted_make:
        # Try to match "make model" pattern
        make_pattern = re.escape(extracted_make)
        pattern = rf'\b{make_pattern}\s+(\w+[-\w]*)\b'
        match = re.search(pattern, desc_lower)
        if match:
            potential_model = match.group(1)
            if potential_model not in SKIP_WORDS and len(potential_model) >= 2:
                extracted_model = potential_model.replace("-", "")

    # Build VehicleEntityInfo
    info = VehicleEntityInfo(
        color=extracted_color,
        make=extracted_make,
        model=extracted_model,
        signature=None
    )

    # Only set signature if minimum data requirements met
    if info.is_valid():
        # Build signature from parts
        signature_parts = []
        if info.color:
            signature_parts.append(info.color.lower())
        if info.make:
            signature_parts.append(info.make.lower())
        if info.model:
            signature_parts.append(info.model.lower())
        info.signature = "-".join(signature_parts)

        logger.debug(
            f"Vehicle entity extracted: {info.signature}",
            extra={
                "event_type": "vehicle_entity_extracted",
                "color": info.color,
                "make": info.make,
                "model": info.model,
                "signature": info.signature,
            }
        )
        return info

    logger.debug(
        f"Insufficient vehicle data for entity: color={extracted_color}, make={extracted_make}, model={extracted_model}",
        extra={
            "event_type": "vehicle_entity_insufficient_data",
            "color": extracted_color,
            "make": extracted_make,
            "model": extracted_model,
        }
    )
    return None


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

    def _find_entity_by_vehicle_signature(
        self,
        db: Session,
        signature: str,
    ) -> Optional[str]:
        """
        Find a vehicle entity by its signature (Story P9-4.1).

        Args:
            db: SQLAlchemy database session
            signature: Vehicle signature string (e.g., "white-toyota-camry")

        Returns:
            Entity ID if found, None otherwise
        """
        from app.models.recognized_entity import RecognizedEntity

        entity = db.query(RecognizedEntity.id).filter(
            RecognizedEntity.entity_type == "vehicle",
            RecognizedEntity.vehicle_signature == signature
        ).first()

        if entity:
            logger.debug(
                f"Found vehicle entity by signature: {signature} -> {entity.id}",
                extra={
                    "event_type": "vehicle_signature_match",
                    "signature": signature,
                    "entity_id": entity.id,
                }
            )
            return entity.id
        return None

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

        # Get event timestamp
        event = db.query(Event.timestamp).filter(Event.id == event_id).first()
        event_timestamp = event.timestamp if event else datetime.now(timezone.utc)

        # Try to extract vehicle info from description
        vehicle_info = None
        if description:
            vehicle_info = extract_vehicle_entity(description)

        # Priority 1: Signature-based matching (P9-4.1)
        if vehicle_info and vehicle_info.signature:
            existing_entity_id = self._find_entity_by_vehicle_signature(
                db, vehicle_info.signature
            )
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
    ) -> EntityMatchResult:
        """Create a new entity and link it to the event."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        entity_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

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
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.event import Event

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
            "vehicle_color": new_entity.vehicle_color,
            "vehicle_make": new_entity.vehicle_make,
            "vehicle_model": new_entity.vehicle_model,
            "vehicle_signature": new_entity.vehicle_signature,
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

    async def unlink_event(
        self,
        db: Session,
        entity_id: str,
        event_id: str,
    ) -> bool:
        """
        Unlink an event from an entity (Story P9-4.3).

        Removes the EntityEvent junction record and creates an EntityAdjustment
        record for ML training. Also decrements the entity's occurrence_count.

        Args:
            db: SQLAlchemy database session
            entity_id: UUID of the entity
            event_id: UUID of the event to unlink

        Returns:
            True if successfully unlinked, False if link not found

        Note:
            - Does NOT delete the event itself, only removes the association
            - Creates EntityAdjustment record with action="unlink"
            - Decrements entity occurrence_count
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.entity_adjustment import EntityAdjustment
        from app.models.event import Event

        # Find the EntityEvent link
        entity_event = db.query(EntityEvent).filter(
            EntityEvent.entity_id == entity_id,
            EntityEvent.event_id == event_id,
        ).first()

        if not entity_event:
            logger.warning(
                f"EntityEvent link not found for entity={entity_id}, event={event_id}",
                extra={
                    "event_type": "unlink_event_not_found",
                    "entity_id": entity_id,
                    "event_id": event_id,
                }
            )
            return False

        # Get event description for ML training snapshot
        event = db.query(Event.description).filter(Event.id == event_id).first()
        event_description = event.description if event else None

        # Get entity for occurrence count update
        entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity:
            logger.warning(
                f"Entity not found for unlink: {entity_id}",
                extra={
                    "event_type": "unlink_entity_not_found",
                    "entity_id": entity_id,
                }
            )
            return False

        # Create EntityAdjustment record for ML training
        adjustment = EntityAdjustment(
            event_id=event_id,
            old_entity_id=entity_id,
            new_entity_id=None,
            action="unlink",
            event_description=event_description,
        )
        db.add(adjustment)

        # Delete the EntityEvent link
        db.delete(entity_event)

        # Decrement occurrence count (but not below 0)
        if entity.occurrence_count > 0:
            entity.occurrence_count -= 1
            entity.updated_at = datetime.now(timezone.utc)

        db.commit()

        logger.info(
            f"Event unlinked from entity: event={event_id}, entity={entity_id}",
            extra={
                "event_type": "event_unlinked",
                "entity_id": entity_id,
                "event_id": event_id,
                "new_occurrence_count": entity.occurrence_count,
            }
        )

        return True

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
    ) -> dict:
        """
        Assign or move an event to an entity (Story P9-4.4).

        If the event is already linked to another entity, this becomes a "move"
        operation that unlinks from the old entity and links to the new one.
        Creates EntityAdjustment record(s) for ML training.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event to assign
            entity_id: UUID of the target entity

        Returns:
            Dict with success status, message, action type, and entity info

        Raises:
            ValueError: If event or entity not found
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.entity_adjustment import EntityAdjustment
        from app.models.event import Event

        # Verify event exists
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise ValueError(f"Event not found: {event_id}")

        # Verify target entity exists
        target_entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()
        if not target_entity:
            raise ValueError(f"Entity not found: {entity_id}")

        # Check if event is already linked to an entity
        existing_link = db.query(EntityEvent).filter(
            EntityEvent.event_id == event_id
        ).first()

        old_entity_id = None
        action = "assign"

        if existing_link:
            # This is a move operation
            old_entity_id = existing_link.entity_id

            if old_entity_id == entity_id:
                # Already linked to this entity
                return {
                    "success": True,
                    "message": f"Event already linked to {target_entity.name or 'this entity'}",
                    "action": "none",
                    "entity_id": entity_id,
                    "entity_name": target_entity.name,
                }

            action = "move"

            # Get old entity to update occurrence count
            old_entity = db.query(RecognizedEntity).filter(
                RecognizedEntity.id == old_entity_id
            ).first()

            # Create adjustment record for move_from
            adjustment_from = EntityAdjustment(
                event_id=event_id,
                old_entity_id=old_entity_id,
                new_entity_id=entity_id,
                action="move_from",
                event_description=event.description,
            )
            db.add(adjustment_from)

            # Decrement old entity occurrence count
            if old_entity and old_entity.occurrence_count > 0:
                old_entity.occurrence_count -= 1
                old_entity.updated_at = datetime.now(timezone.utc)

            # Update the existing link to point to new entity
            existing_link.entity_id = entity_id
            existing_link.similarity_score = 1.0  # Manual assignment = 100% match
            existing_link.created_at = datetime.now(timezone.utc)

            # Create adjustment record for move_to
            adjustment_to = EntityAdjustment(
                event_id=event_id,
                old_entity_id=old_entity_id,
                new_entity_id=entity_id,
                action="move_to",
                event_description=event.description,
            )
            db.add(adjustment_to)

            logger.info(
                f"Event moved from entity {old_entity_id} to {entity_id}",
                extra={
                    "event_type": "event_moved",
                    "event_id": event_id,
                    "old_entity_id": old_entity_id,
                    "new_entity_id": entity_id,
                }
            )
        else:
            # New assignment
            entity_event = EntityEvent(
                entity_id=entity_id,
                event_id=event_id,
                similarity_score=1.0,  # Manual assignment = 100% match
            )
            db.add(entity_event)

            # Create adjustment record for assign
            adjustment = EntityAdjustment(
                event_id=event_id,
                old_entity_id=None,
                new_entity_id=entity_id,
                action="assign",
                event_description=event.description,
            )
            db.add(adjustment)

            logger.info(
                f"Event assigned to entity: event={event_id}, entity={entity_id}",
                extra={
                    "event_type": "event_assigned",
                    "event_id": event_id,
                    "entity_id": entity_id,
                }
            )

        # Increment target entity occurrence count
        target_entity.occurrence_count += 1
        target_entity.last_seen_at = event.timestamp
        target_entity.updated_at = datetime.now(timezone.utc)

        db.commit()

        entity_name = target_entity.name or f"{target_entity.entity_type.title()} entity"
        message = f"Event {'moved to' if action == 'move' else 'added to'} {entity_name}"

        return {
            "success": True,
            "message": message,
            "action": action,
            "entity_id": entity_id,
            "entity_name": target_entity.name,
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

            # Update the link to point to primary entity
            link.entity_id = primary_entity_id
            link.created_at = now  # Update timestamp

            events_moved += 1

        # Update primary entity occurrence count
        primary.occurrence_count += secondary.occurrence_count
        primary.updated_at = now

        # Update last_seen_at if secondary was seen more recently
        if secondary.last_seen_at > primary.last_seen_at:
            primary.last_seen_at = secondary.last_seen_at

        # Update first_seen_at if secondary was seen earlier
        if secondary.first_seen_at < primary.first_seen_at:
            primary.first_seen_at = secondary.first_seen_at

        # Store secondary info before deletion
        secondary_id = secondary.id
        secondary_name = secondary.name

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
            action: Filter by action type (unlink, assign, move_from, move_to, merge)
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
