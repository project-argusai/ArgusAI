"""
Person Matching Service for Face-to-Person Recognition (Story P4-8.2)

This module matches face embeddings to known persons for personalized alerts.
It bridges FaceEmbeddingService (P4-8.1) and EntityService (P4-3.3) to enable
recognition of familiar faces with "John is at the door" style notifications.

Architecture:
    - Uses FaceEmbedding records from P4-8.1
    - Matches against RecognizedEntity records where entity_type='person'
    - Creates EntityEvent links on successful matches
    - Optionally creates new person entities when no match found
    - Handles multiple faces per event independently

Privacy:
    - All face data stored locally only
    - User controls via face_recognition_enabled setting
    - New persons start unnamed (user names them later)
"""
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.orm import Session

from app.services.similarity_service import batch_cosine_similarity

logger = logging.getLogger(__name__)


@dataclass
class PersonMatchResult:
    """Result of face-to-person matching operation."""
    face_embedding_id: str
    person_id: Optional[str]  # None if no match and auto_create disabled
    person_name: Optional[str]
    similarity_score: float
    is_new_person: bool
    is_appearance_update: bool
    bounding_box: dict


class PersonMatchingService:
    """
    Match face embeddings to known persons.

    Uses CLIP embeddings from FaceEmbeddingService and matches against
    RecognizedEntity records with entity_type='person'. Enables personalized
    alerts like "John is at the door" instead of generic "Person detected".

    Attributes:
        DEFAULT_THRESHOLD: Default similarity threshold (0.70, tighter than entity default)
        HIGH_CONFIDENCE_THRESHOLD: Threshold for appearance updates (0.90)
        APPEARANCE_DIFF_THRESHOLD: Embedding difference threshold for updates (0.15)
    """

    DEFAULT_THRESHOLD = 0.70
    HIGH_CONFIDENCE_THRESHOLD = 0.90
    APPEARANCE_DIFF_THRESHOLD = 0.15  # If embedding differs by this much, consider update

    def __init__(self):
        """Initialize PersonMatchingService."""
        self._person_cache: dict[str, list[float]] = {}  # person_id -> embedding
        self._cache_loaded = False
        logger.info(
            "PersonMatchingService initialized",
            extra={"event_type": "person_matching_service_init"}
        )

    def _load_person_cache(self, db: Session) -> None:
        """
        Load all person embeddings into memory cache.

        Only loads RecognizedEntity records where entity_type='person'.

        Args:
            db: SQLAlchemy database session
        """
        from app.models.recognized_entity import RecognizedEntity

        start_time = time.time()

        persons = db.query(
            RecognizedEntity.id,
            RecognizedEntity.reference_embedding
        ).filter(
            RecognizedEntity.entity_type == "person"
        ).all()

        self._person_cache = {}
        for person in persons:
            try:
                embedding = json.loads(person.reference_embedding)
                self._person_cache[person.id] = embedding
            except json.JSONDecodeError:
                logger.warning(
                    f"Invalid embedding JSON for person {person.id}",
                    extra={"person_id": person.id}
                )

        self._cache_loaded = True
        load_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Person cache loaded: {len(self._person_cache)} persons in {load_time_ms:.2f}ms",
            extra={
                "event_type": "person_cache_loaded",
                "person_count": len(self._person_cache),
                "load_time_ms": round(load_time_ms, 2),
            }
        )

    def _invalidate_cache(self) -> None:
        """Clear the person embedding cache."""
        self._person_cache = {}
        self._cache_loaded = False
        logger.debug(
            "Person cache invalidated",
            extra={"event_type": "person_cache_invalidated"}
        )

    async def match_faces_to_persons(
        self,
        db: Session,
        face_embedding_ids: list[str],
        auto_create: bool = True,
        threshold: float = DEFAULT_THRESHOLD,
        update_appearance: bool = True,
    ) -> list[PersonMatchResult]:
        """
        Match multiple face embeddings to known persons.

        Args:
            db: SQLAlchemy database session
            face_embedding_ids: List of FaceEmbedding IDs to match
            auto_create: If True, create new person when no match found
            threshold: Minimum similarity score for matching
            update_appearance: If True, update reference embedding on high-confidence match

        Returns:
            List of PersonMatchResult, one per face embedding (same order)
        """
        if not face_embedding_ids:
            return []

        results = []
        for face_id in face_embedding_ids:
            try:
                result = await self.match_single_face(
                    db,
                    face_id,
                    threshold=threshold,
                    auto_create=auto_create,
                    update_appearance=update_appearance,
                )
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Failed to match face {face_id}: {e}",
                    exc_info=True,
                    extra={
                        "event_type": "person_match_error",
                        "face_embedding_id": face_id,
                        "error": str(e),
                    }
                )
                # Continue with remaining faces

        logger.info(
            f"Matched {len(results)}/{len(face_embedding_ids)} faces to persons",
            extra={
                "event_type": "person_matching_complete",
                "total_faces": len(face_embedding_ids),
                "matched_count": sum(1 for r in results if r.person_id),
                "new_persons": sum(1 for r in results if r.is_new_person),
            }
        )

        return results

    async def match_single_face(
        self,
        db: Session,
        face_embedding_id: str,
        threshold: float = DEFAULT_THRESHOLD,
        auto_create: bool = True,
        update_appearance: bool = True,
    ) -> PersonMatchResult:
        """
        Match a single face embedding to a known person.

        Args:
            db: SQLAlchemy database session
            face_embedding_id: ID of the FaceEmbedding to match
            threshold: Minimum similarity score for matching
            auto_create: If True, create new person when no match found
            update_appearance: If True, update reference embedding on high-confidence match

        Returns:
            PersonMatchResult with match details

        Raises:
            ValueError: If face embedding not found
        """
        from app.models.face_embedding import FaceEmbedding
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        start_time = time.time()

        # Load face embedding
        face_embedding = db.query(FaceEmbedding).filter(
            FaceEmbedding.id == face_embedding_id
        ).first()

        if not face_embedding:
            raise ValueError(f"FaceEmbedding {face_embedding_id} not found")

        embedding_vector = json.loads(face_embedding.embedding)
        bounding_box = json.loads(face_embedding.bounding_box)

        # Load cache if needed
        if not self._cache_loaded:
            self._load_person_cache(db)

        # If no persons exist, create first one (if auto_create enabled)
        if not self._person_cache:
            if auto_create:
                result = await self._create_new_person(
                    db, face_embedding, embedding_vector, bounding_box
                )
                match_time_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"First person created from face {face_embedding_id}",
                    extra={
                        "event_type": "person_created_first",
                        "face_embedding_id": face_embedding_id,
                        "person_id": result.person_id,
                        "match_time_ms": round(match_time_ms, 2),
                    }
                )
                return result
            else:
                return PersonMatchResult(
                    face_embedding_id=face_embedding_id,
                    person_id=None,
                    person_name=None,
                    similarity_score=0.0,
                    is_new_person=False,
                    is_appearance_update=False,
                    bounding_box=bounding_box,
                )

        # Calculate similarity with all known persons
        person_ids = list(self._person_cache.keys())
        person_embeddings = [self._person_cache[pid] for pid in person_ids]

        similarities = batch_cosine_similarity(embedding_vector, person_embeddings)

        # Find best match above threshold
        best_idx = -1
        best_score = -1.0
        for i, score in enumerate(similarities):
            if score >= threshold and score > best_score:
                best_idx = i
                best_score = score

        match_time_ms = (time.time() - start_time) * 1000

        if best_idx >= 0:
            # Match found
            matched_person_id = person_ids[best_idx]
            result = await self._update_existing_person(
                db,
                face_embedding,
                matched_person_id,
                best_score,
                embedding_vector,
                bounding_box,
                update_appearance,
            )
            logger.info(
                f"Face {face_embedding_id} matched to person {matched_person_id}",
                extra={
                    "event_type": "person_matched",
                    "face_embedding_id": face_embedding_id,
                    "person_id": matched_person_id,
                    "person_name": result.person_name,
                    "similarity_score": round(best_score, 4),
                    "match_time_ms": round(match_time_ms, 2),
                }
            )
            return result
        else:
            # No match found
            if auto_create:
                result = await self._create_new_person(
                    db, face_embedding, embedding_vector, bounding_box
                )
                logger.info(
                    f"New person created from face {face_embedding_id}",
                    extra={
                        "event_type": "person_created_new",
                        "face_embedding_id": face_embedding_id,
                        "person_id": result.person_id,
                        "best_score_below_threshold": round(max(similarities) if similarities else 0, 4),
                        "threshold": threshold,
                        "match_time_ms": round(match_time_ms, 2),
                    }
                )
                return result
            else:
                logger.debug(
                    f"No person match for face {face_embedding_id} (auto_create disabled)",
                    extra={
                        "event_type": "person_no_match",
                        "face_embedding_id": face_embedding_id,
                        "best_score": round(max(similarities) if similarities else 0, 4),
                        "threshold": threshold,
                    }
                )
                return PersonMatchResult(
                    face_embedding_id=face_embedding_id,
                    person_id=None,
                    person_name=None,
                    similarity_score=max(similarities) if similarities else 0.0,
                    is_new_person=False,
                    is_appearance_update=False,
                    bounding_box=bounding_box,
                )

    async def _create_new_person(
        self,
        db: Session,
        face_embedding,  # FaceEmbedding model
        embedding_vector: list[float],
        bounding_box: dict,
    ) -> PersonMatchResult:
        """Create a new person entity from a face embedding."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.face_embedding import FaceEmbedding

        person_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Get event timestamp for temporal tracking
        event_timestamp = now
        if face_embedding.event:
            event_timestamp = face_embedding.event.timestamp or now

        # Create person entity
        new_person = RecognizedEntity(
            id=person_id,
            entity_type="person",
            name=None,  # User names later
            reference_embedding=json.dumps(embedding_vector),
            first_seen_at=event_timestamp,
            last_seen_at=event_timestamp,
            occurrence_count=1,
            created_at=now,
            updated_at=now,
        )
        db.add(new_person)

        # Link face embedding to person
        face_embedding.entity_id = person_id

        # Create entity-event link (similarity 1.0 for first occurrence)
        entity_event = EntityEvent(
            entity_id=person_id,
            event_id=face_embedding.event_id,
            similarity_score=1.0,
            created_at=now,
        )
        db.add(entity_event)

        db.commit()

        # Update cache
        self._person_cache[person_id] = embedding_vector

        return PersonMatchResult(
            face_embedding_id=face_embedding.id,
            person_id=person_id,
            person_name=None,
            similarity_score=1.0,
            is_new_person=True,
            is_appearance_update=False,
            bounding_box=bounding_box,
        )

    async def _update_existing_person(
        self,
        db: Session,
        face_embedding,  # FaceEmbedding model
        person_id: str,
        similarity_score: float,
        embedding_vector: list[float],
        bounding_box: dict,
        update_appearance: bool,
    ) -> PersonMatchResult:
        """Update an existing person with new face occurrence."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        now = datetime.now(timezone.utc)

        # Get event timestamp for temporal tracking
        event_timestamp = now
        if face_embedding.event:
            event_timestamp = face_embedding.event.timestamp or now

        # Get person
        person = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == person_id
        ).first()

        if not person:
            raise ValueError(f"Person {person_id} not found")

        # Check for appearance update
        is_appearance_update = False
        if update_appearance and similarity_score >= self.HIGH_CONFIDENCE_THRESHOLD:
            # Calculate embedding difference
            current_embedding = json.loads(person.reference_embedding)
            diff_similarities = batch_cosine_similarity(embedding_vector, [current_embedding])
            embedding_diff = 1.0 - diff_similarities[0]

            if embedding_diff >= self.APPEARANCE_DIFF_THRESHOLD:
                # Update reference embedding (weighted average: 70% old, 30% new)
                import numpy as np
                old_emb = np.array(current_embedding, dtype=np.float32)
                new_emb = np.array(embedding_vector, dtype=np.float32)
                updated_emb = (0.7 * old_emb + 0.3 * new_emb).tolist()

                person.reference_embedding = json.dumps(updated_emb)
                self._person_cache[person_id] = updated_emb
                is_appearance_update = True

                logger.info(
                    f"Person {person_id} appearance updated",
                    extra={
                        "event_type": "person_appearance_updated",
                        "person_id": person_id,
                        "embedding_diff": round(embedding_diff, 4),
                        "similarity_score": round(similarity_score, 4),
                    }
                )

        # Update person metadata
        person.occurrence_count += 1
        person.last_seen_at = event_timestamp
        person.updated_at = now

        # Link face embedding to person
        face_embedding.entity_id = person_id

        # Check if EntityEvent already exists (same person in same event)
        existing_link = db.query(EntityEvent).filter(
            EntityEvent.entity_id == person_id,
            EntityEvent.event_id == face_embedding.event_id,
        ).first()

        if not existing_link:
            # Create entity-event link
            entity_event = EntityEvent(
                entity_id=person_id,
                event_id=face_embedding.event_id,
                similarity_score=similarity_score,
                created_at=now,
            )
            db.add(entity_event)

        db.commit()
        db.refresh(person)

        return PersonMatchResult(
            face_embedding_id=face_embedding.id,
            person_id=person.id,
            person_name=person.name,
            similarity_score=similarity_score,
            is_new_person=False,
            is_appearance_update=is_appearance_update,
            bounding_box=bounding_box,
        )

    async def get_persons(
        self,
        db: Session,
        limit: int = 50,
        offset: int = 0,
        named_only: bool = False,
    ) -> tuple[list[dict], int]:
        """
        Get all persons (RecognizedEntity with entity_type='person').

        Args:
            db: SQLAlchemy database session
            limit: Maximum number to return
            offset: Pagination offset
            named_only: If True, only return named persons

        Returns:
            Tuple of (list of person dicts with face_count, total count)
        """
        from app.models.recognized_entity import RecognizedEntity
        from app.models.face_embedding import FaceEmbedding
        from sqlalchemy import func, desc

        query = db.query(RecognizedEntity).filter(
            RecognizedEntity.entity_type == "person"
        )

        if named_only:
            query = query.filter(RecognizedEntity.name.isnot(None))

        total = query.count()

        persons = query.order_by(
            desc(RecognizedEntity.last_seen_at)
        ).offset(offset).limit(limit).all()

        # Get face counts for each person
        person_ids = [p.id for p in persons]
        face_counts = {}
        if person_ids:
            counts = db.query(
                FaceEmbedding.entity_id,
                func.count(FaceEmbedding.id).label("count")
            ).filter(
                FaceEmbedding.entity_id.in_(person_ids)
            ).group_by(FaceEmbedding.entity_id).all()

            face_counts = {c.entity_id: c.count for c in counts}

        return [
            {
                "id": p.id,
                "name": p.name,
                "first_seen_at": p.first_seen_at,
                "last_seen_at": p.last_seen_at,
                "occurrence_count": p.occurrence_count,
                "face_count": face_counts.get(p.id, 0),
            }
            for p in persons
        ], total

    async def get_person(
        self,
        db: Session,
        person_id: str,
        include_faces: bool = True,
        face_limit: int = 10,
    ) -> Optional[dict]:
        """
        Get a single person with their face embeddings.

        Args:
            db: SQLAlchemy database session
            person_id: UUID of the person
            include_faces: Whether to include recent face matches
            face_limit: Maximum number of faces to include

        Returns:
            Person dict with optional faces, or None if not found
        """
        from app.models.recognized_entity import RecognizedEntity
        from app.models.face_embedding import FaceEmbedding
        from app.models.event import Event
        from sqlalchemy import desc

        person = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == person_id,
            RecognizedEntity.entity_type == "person",
        ).first()

        if not person:
            return None

        result = {
            "id": person.id,
            "name": person.name,
            "first_seen_at": person.first_seen_at,
            "last_seen_at": person.last_seen_at,
            "occurrence_count": person.occurrence_count,
            "created_at": person.created_at,
            "updated_at": person.updated_at,
        }

        if include_faces:
            # Get recent face embeddings for this person
            faces = db.query(
                FaceEmbedding.id,
                FaceEmbedding.event_id,
                FaceEmbedding.bounding_box,
                FaceEmbedding.confidence,
                FaceEmbedding.created_at,
                Event.timestamp.label("event_timestamp"),
                Event.thumbnail_path,
            ).join(
                Event, Event.id == FaceEmbedding.event_id
            ).filter(
                FaceEmbedding.entity_id == person_id
            ).order_by(
                desc(FaceEmbedding.created_at)
            ).limit(face_limit).all()

            result["recent_faces"] = [
                {
                    "id": f.id,
                    "event_id": f.event_id,
                    "bounding_box": json.loads(f.bounding_box) if f.bounding_box else None,
                    "confidence": f.confidence,
                    "created_at": f.created_at,
                    "event_timestamp": f.event_timestamp,
                    "thumbnail_url": f.thumbnail_path,
                }
                for f in faces
            ]

        return result

    async def update_person_name(
        self,
        db: Session,
        person_id: str,
        name: Optional[str],
    ) -> Optional[dict]:
        """
        Update a person's name.

        Args:
            db: SQLAlchemy database session
            person_id: UUID of the person
            name: New name (or None to clear)

        Returns:
            Updated person dict, or None if not found
        """
        from app.models.recognized_entity import RecognizedEntity

        person = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == person_id,
            RecognizedEntity.entity_type == "person",
        ).first()

        if not person:
            return None

        person.name = name
        person.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(person)

        logger.info(
            f"Person {person_id} name updated to: {name}",
            extra={
                "event_type": "person_name_updated",
                "person_id": person_id,
                "name": name,
            }
        )

        return {
            "id": person.id,
            "name": person.name,
            "first_seen_at": person.first_seen_at,
            "last_seen_at": person.last_seen_at,
            "occurrence_count": person.occurrence_count,
        }


# Global singleton instance
_person_matching_service: Optional[PersonMatchingService] = None


def get_person_matching_service() -> PersonMatchingService:
    """
    Get the global PersonMatchingService instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        PersonMatchingService singleton instance
    """
    global _person_matching_service

    if _person_matching_service is None:
        _person_matching_service = PersonMatchingService()
        logger.info(
            "Global PersonMatchingService instance created",
            extra={"event_type": "person_matching_service_singleton_created"}
        )

    return _person_matching_service


def reset_person_matching_service() -> None:
    """
    Reset the global PersonMatchingService instance.

    Useful for testing to ensure a fresh instance.
    """
    global _person_matching_service
    _person_matching_service = None
