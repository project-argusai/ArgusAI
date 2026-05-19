"""
Entity Alert Service for Named Entity Alerts (Story P4-8.4)

Provides entity-aware alert handling including:
- Description enrichment with entity names
- Recognition status classification (known/stranger/unknown)
- VIP alert detection
- Blocklist alert suppression

# Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import json
import logging
from app.core.decorators import singleton
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.recognized_entity import RecognizedEntity
from app.models.event import Event

logger = logging.getLogger(__name__)


# Singleton instance



@dataclass
class EntityAlertResult:
    """Result of entity alert processing."""
    recognition_status: Optional[str]  # 'known', 'stranger', 'unknown', None
    enriched_description: Optional[str]
    matched_entity_ids: List[str]
    has_vip: bool
    vip_entity_ids: List[str]
    should_suppress: bool  # True if any matched entity is blocked
    entity_names: List[str]  # Names of matched entities (for notifications)


@singleton
class EntityAlertService:
    """
    Service for entity-aware alert handling.

    Enriches event descriptions with entity names, classifies recognition
    status, detects VIP entities, and handles blocklist suppression.
    """

    def __init__(self):
        """Initialize EntityAlertService."""
        self._entity_cache: Dict[str, RecognizedEntity] = {}
        self._cache_loaded = False
        logger.info("EntityAlertService initialized")

    def _invalidate_cache(self) -> None:
        """Clear the entity cache."""
        self._entity_cache = {}
        self._cache_loaded = False

    async def _load_entity_cache(self, db: Session) -> None:
        """Load all entities into cache for fast lookup."""
        if self._cache_loaded:
            return

        try:
            entities = db.query(RecognizedEntity).all()
            self._entity_cache = {entity.id: entity for entity in entities}
            self._cache_loaded = True
            logger.debug(f"Loaded {len(self._entity_cache)} entities into cache")
        except Exception as e:
            logger.error(f"Failed to load entity cache: {e}")
            self._entity_cache = {}

    async def get_entities_by_ids(
        self, db: Session, entity_ids: List[str]
    ) -> List[RecognizedEntity]:
        """
        Get entities by their IDs.

        Args:
            db: Database session
            entity_ids: List of entity UUIDs

        Returns:
            List of RecognizedEntity objects
        """
        if not entity_ids:
            return []

        await self._load_entity_cache(db)

        entities = []
        for entity_id in entity_ids:
            if entity_id in self._entity_cache:
                entities.append(self._entity_cache[entity_id])
            else:
                # Try to fetch from database if not in cache
                entity = db.query(RecognizedEntity).filter(
                    RecognizedEntity.id == entity_id
                ).first()
                if entity:
                    self._entity_cache[entity_id] = entity
                    entities.append(entity)

        return entities

    def classify_recognition_status(
        self, matched_entities: List[RecognizedEntity]
    ) -> Optional[str]:
        """
        Classify recognition status based on matched entities.

        Status definitions:
        - 'known': Matched to a named entity (has user-assigned name)
        - 'stranger': Matched to an unnamed entity (seen before but not identified)
        - 'unknown': No match found (first-time visitor)
        - None: No recognition performed (no person/vehicle in event)

        Args:
            matched_entities: List of matched RecognizedEntity objects

        Returns:
            Recognition status string or None
        """
        if not matched_entities:
            return 'unknown'

        # Check if any matched entity has a name
        has_named_entity = any(
            entity.name and entity.name.strip()
            for entity in matched_entities
        )

        if has_named_entity:
            return 'known'
        else:
            return 'stranger'

    def enrich_description(
        self,
        original_description: str,
        matched_entities: List[RecognizedEntity]
    ) -> str:
        """
        Enrich event description with entity names.

        Replaces generic terms like "person" or "A person" with entity names.

        Args:
            original_description: Original AI-generated description
            matched_entities: List of matched entities

        Returns:
            Enriched description with entity names
        """
        if not matched_entities or not original_description:
            return original_description

        # Get named entities only
        named_entities = [
            entity for entity in matched_entities
            if entity.name and entity.name.strip()
        ]

        if not named_entities:
            return original_description

        enriched = original_description

        # Build name list for replacement
        entity_names = [entity.name for entity in named_entities]

        if len(entity_names) == 1:
            name_str = entity_names[0]
        elif len(entity_names) == 2:
            name_str = f"{entity_names[0]} and {entity_names[1]}"
        else:
            name_str = ", ".join(entity_names[:-1]) + f", and {entity_names[-1]}"

        # Replace common generic terms at the start of descriptions
        # Patterns to replace: "A person", "Person", "A man", "A woman", "Someone", etc.
        patterns = [
            (r'^A person\b', name_str),
            (r'^Person\b', name_str),
            (r'^A man\b', name_str),
            (r'^A woman\b', name_str),
            (r'^Someone\b', name_str),
            (r'^An individual\b', name_str),
            (r'^A visitor\b', name_str),
            # Vehicle patterns
            (r'^A vehicle\b', f"{name_str}'s vehicle"),
            (r'^Vehicle\b', f"{name_str}'s vehicle"),
            (r'^A car\b', f"{name_str}'s car"),
            (r'^Car\b', f"{name_str}'s car"),
        ]

        for pattern, replacement in patterns:
            enriched = re.sub(pattern, replacement, enriched, flags=re.IGNORECASE)
            if enriched != original_description:
                break  # Only apply first matching pattern

        return enriched

    async def should_suppress_alert(
        self, db: Session, matched_entity_ids: List[str]
    ) -> bool:
        """
        Check if alert should be suppressed due to blocked entities.

        Args:
            db: Database session
            matched_entity_ids: List of matched entity IDs

        Returns:
            True if any matched entity is blocked
        """
        if not matched_entity_ids:
            return False

        entities = await self.get_entities_by_ids(db, matched_entity_ids)

        return any(entity.is_blocked for entity in entities)

    async def get_vip_entities(
        self, db: Session, matched_entity_ids: List[str]
    ) -> List[RecognizedEntity]:
        """
        Get VIP entities from matched entity list.

        Args:
            db: Database session
            matched_entity_ids: List of matched entity IDs

        Returns:
            List of VIP RecognizedEntity objects
        """
        if not matched_entity_ids:
            return []

        entities = await self.get_entities_by_ids(db, matched_entity_ids)

        return [entity for entity in entities if entity.is_vip]

    async def process_event_entities(
        self,
        db: Session,
        event_id: str,
        matched_entity_ids: List[str],
        original_description: str,
        has_person_or_vehicle: bool = True
    ) -> EntityAlertResult:
        """
        Process entity alert for an event.

        This is the main entry point that:
        1. Classifies recognition status
        2. Enriches description with entity names
        3. Checks for VIP entities
        4. Checks blocklist for suppression

        Args:
            db: Database session
            event_id: Event UUID
            matched_entity_ids: List of matched entity IDs
            original_description: Original AI description
            has_person_or_vehicle: Whether event has person or vehicle detection

        Returns:
            EntityAlertResult with all alert processing results
        """
        # If no person/vehicle detection, no recognition to process
        if not has_person_or_vehicle:
            return EntityAlertResult(
                recognition_status=None,
                enriched_description=None,
                matched_entity_ids=[],
                has_vip=False,
                vip_entity_ids=[],
                should_suppress=False,
                entity_names=[]
            )

        # Get matched entities
        matched_entities = await self.get_entities_by_ids(db, matched_entity_ids)

        # Classify recognition status
        recognition_status = self.classify_recognition_status(matched_entities)

        # Enrich description
        enriched_description = self.enrich_description(
            original_description, matched_entities
        )

        # Check for VIP entities
        vip_entities = [e for e in matched_entities if e.is_vip]
        vip_entity_ids = [e.id for e in vip_entities]

        # Check for blocked entities
        should_suppress = any(e.is_blocked for e in matched_entities)

        # Get entity names for notifications
        entity_names = [
            e.name for e in matched_entities
            if e.name and e.name.strip()
        ]

        logger.info(
            f"Processed entity alert for event {event_id}: "
            f"status={recognition_status}, has_vip={len(vip_entities) > 0}, "
            f"suppressed={should_suppress}",
            extra={
                "event_type": "entity_alert_processed",
                "event_id": event_id,
                "recognition_status": recognition_status,
                "matched_count": len(matched_entities),
                "vip_count": len(vip_entities),
                "suppressed": should_suppress
            }
        )

        return EntityAlertResult(
            recognition_status=recognition_status,
            enriched_description=enriched_description,
            matched_entity_ids=matched_entity_ids,
            has_vip=len(vip_entities) > 0,
            vip_entity_ids=vip_entity_ids,
            should_suppress=should_suppress,
            entity_names=entity_names
        )

    async def update_event_with_entity_info(
        self,
        db: Session,
        event_id: str,
        result: EntityAlertResult
    ) -> None:
        """
        Update event record with entity alert information.

        Args:
            db: Database session
            event_id: Event UUID
            result: EntityAlertResult from process_event_entities
        """
        try:
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                logger.warning(f"Event {event_id} not found for entity update")
                return

            event.recognition_status = result.recognition_status
            event.enriched_description = result.enriched_description
            event.matched_entity_ids = json.dumps(result.matched_entity_ids) if result.matched_entity_ids else None

            db.commit()

            logger.debug(
                f"Updated event {event_id} with entity info: status={result.recognition_status}"
            )

        except Exception as e:
            logger.error(f"Failed to update event {event_id} with entity info: {e}")
            db.rollback()

    async def get_all_vip_entities(
        self, db: Session, limit: int = 100, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get all VIP entities with pagination.

        Args:
            db: Database session
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Tuple of (list of entity dicts, total count)
        """
        query = db.query(RecognizedEntity).filter(RecognizedEntity.is_vip == True)
        total = query.count()

        entities = query.order_by(
            RecognizedEntity.last_seen_at.desc()
        ).offset(offset).limit(limit).all()

        return [self._entity_to_dict(e) for e in entities], total

    async def get_all_blocked_entities(
        self, db: Session, limit: int = 100, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get all blocked entities with pagination.

        Args:
            db: Database session
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Tuple of (list of entity dicts, total count)
        """
        query = db.query(RecognizedEntity).filter(RecognizedEntity.is_blocked == True)
        total = query.count()

        entities = query.order_by(
            RecognizedEntity.last_seen_at.desc()
        ).offset(offset).limit(limit).all()

        return [self._entity_to_dict(e) for e in entities], total

    def _entity_to_dict(self, entity: RecognizedEntity) -> Dict[str, Any]:
        """Convert entity to dictionary for API response."""
        return {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "name": entity.name,
            "first_seen_at": entity.first_seen_at.isoformat() if entity.first_seen_at else None,
            "last_seen_at": entity.last_seen_at.isoformat() if entity.last_seen_at else None,
            "occurrence_count": entity.occurrence_count,
            "is_vip": entity.is_vip,
            "is_blocked": entity.is_blocked,
            "entity_metadata": json.loads(entity.entity_metadata) if entity.entity_metadata else None,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }

    async def update_entity_alert_settings(
        self,
        db: Session,
        entity_id: str,
        name: Optional[str] = None,
        is_vip: Optional[bool] = None,
        is_blocked: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update entity VIP/blocked settings.

        Args:
            db: Database session
            entity_id: Entity UUID
            name: New name (optional)
            is_vip: VIP status (optional)
            is_blocked: Blocked status (optional)

        Returns:
            Updated entity dict or None if not found
        """
        entity = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        if not entity:
            return None

        if name is not None:
            entity.name = name
        if is_vip is not None:
            entity.is_vip = is_vip
        if is_blocked is not None:
            entity.is_blocked = is_blocked

        entity.updated_at = datetime.now(timezone.utc)
        db.commit()

        # Invalidate cache to pick up changes
        self._invalidate_cache()

        logger.info(
            f"Updated entity {entity_id} alert settings: "
            f"name={name}, is_vip={is_vip}, is_blocked={is_blocked}",
            extra={
                "event_type": "entity_alert_settings_updated",
                "entity_id": entity_id,
                "is_vip": is_vip,
                "is_blocked": is_blocked
            }
        )

        return self._entity_to_dict(entity)


# Backward compatible thin getter (delegates to @singleton decorator)
def get_entity_alert_service() -> EntityAlertService:
    """
    Get the global EntityAlertService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer EntityAlertService() directly.
    """
    return EntityAlertService()


def reset_entity_alert_service() -> None:
    """Reset the global EntityAlertService instance (for testing)."""
    EntityAlertService._reset_instance()
