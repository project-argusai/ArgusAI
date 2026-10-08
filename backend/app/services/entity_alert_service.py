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
from app.services.vehicle_signature_matcher import (
    SKIP_WORDS,
    VEHICLE_COLORS,
    VEHICLE_MAKES,
    VEHICLE_MODELS,
)

logger = logging.getLogger(__name__)

_MAKE_ALIASES = {
    "chevy": "chevrolet",
    "vw": "volkswagen",
    "mercedes-benz": "mercedes",
    "range rover": "land rover",
}
_COLOR_ALIASES = {"grey": "gray"}


def _norm_token(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("-", "").replace(" ", "")
    return text or None


def _earliest_vocab(text: str, vocab: List[str], aliases: Dict[str, str]) -> Optional[str]:
    lowered = text.lower()
    best = None
    best_at = len(lowered) + 1
    surface = None
    for word in vocab:
        match = re.search(rf"\b{re.escape(word)}\b", lowered)
        if match and match.start() < best_at:
            best_at = match.start()
            surface = word
            best = aliases.get(word, word)
    return best if surface else None


def _model_after_make(text: str, make: Optional[str]) -> Optional[str]:
    if not make:
        return None
    match = re.search(rf"\b{re.escape(make)}\s+(\w+[-\w]*)\b", text.lower())
    if not match:
        return None
    token = match.group(1)
    if token in SKIP_WORDS or len(token) < 2:
        return None
    return token.replace("-", "")


def visible_vehicle_details(description: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Color, make, and model actually named in a description. Any may be missing."""
    text = description or ""
    color = _earliest_vocab(text, VEHICLE_COLORS, _COLOR_ALIASES)
    make = _earliest_vocab(text, VEHICLE_MAKES, _MAKE_ALIASES)
    model = _earliest_vocab(text, VEHICLE_MODELS, {})
    if model:
        model = _norm_token(model)
    elif make:
        model = _model_after_make(text, make)
    return color, make, model


def vehicle_label_agrees(description: str, entity) -> bool:
    """Whether a stored vehicle name can be shown for this description.

    The name is a hint. A make or model written into the name (or stored on
    the entity) is used only when the description shows that same make.
    A different visible make, model, or stored color disagrees. A nickname
    with no make or model agrees unless the description names some other make.
    """
    name = entity.name if isinstance(getattr(entity, "name", None), str) else ""
    name = name.strip()
    if not name:
        return False
    visible_color, visible_make, visible_model = visible_vehicle_details(description or "")
    label_make = _earliest_vocab(name, VEHICLE_MAKES, _MAKE_ALIASES)
    label_model = _earliest_vocab(name, VEHICLE_MODELS, {})
    if label_model:
        label_model = _norm_token(label_model)
    elif label_make:
        label_model = _model_after_make(name, label_make)
    stored_color = _norm_token(getattr(entity, "vehicle_color", None))
    if stored_color == "grey":
        stored_color = "gray"
    raw_make = getattr(entity, "vehicle_make", None)
    if isinstance(raw_make, str):
        raw_make = _MAKE_ALIASES.get(raw_make.strip().lower(), raw_make)
    stored_make = _norm_token(raw_make if isinstance(raw_make, str) else None)
    stored_model = _norm_token(getattr(entity, "vehicle_model", None))

    expected_makes = {token for token in (label_make, stored_make) if token}
    expected_models = {token for token in (label_model, stored_model) if token}

    if visible_make and expected_makes and visible_make not in expected_makes:
        return False
    if visible_make and not expected_makes:
        return False
    if visible_model and expected_models and visible_model not in expected_models:
        return False
    if visible_color and stored_color and visible_color != stored_color:
        return False
    if expected_makes and visible_make not in expected_makes:
        # "BMW X3" is not confirmed by "a red SUV" or "a vehicle".
        return False
    return True


def _all_vocab(text: str, vocab: List[str], aliases: Dict[str, str]) -> set:
    lowered = (text or "").lower()
    return {
        _norm_token(aliases.get(word, word))
        for word in vocab
        if re.search(rf"\b{re.escape(word)}\b", lowered)
    }


def vehicle_description_signal(description: Optional[str], entity) -> str:
    """How a description bears on a saved vehicle: 'agree', 'contradict' or 'none'.

    Unlike ``vehicle_label_agrees`` (one make/colour, the earliest named),
    this looks at every make, model and colour the description names, so
    "a white van passes as a red Tesla pulls in" neither contradicts the red
    Tesla nor credits the van with it. Only vocabulary models count, so a
    verb after the make ("Tesla pulls in") is not read as a model.

    'agree': the saved make is among the makes named and nothing contradicts.
    'contradict': makes (or vocabulary models, or colours) are named and the
    saved one is not among them. 'none': nothing either way, e.g. "a red
    SUV", or an entity with no make (a nickname never counts as positive
    evidence).
    """
    from app.services.vehicle_color import color_agreement, normalize_color_name

    text = description or ""
    if not text.strip():
        return "none"
    name = entity.name if isinstance(getattr(entity, "name", None), str) else ""
    makes_seen = _all_vocab(text, VEHICLE_MAKES, _MAKE_ALIASES)
    models_seen = _all_vocab(text, VEHICLE_MODELS, {})
    colors_seen = {
        c for c in (normalize_color_name(w) for w in _all_vocab(text, VEHICLE_COLORS, _COLOR_ALIASES)) if c
    }

    label_make = _norm_token(_earliest_vocab(name, VEHICLE_MAKES, _MAKE_ALIASES))
    raw_make = getattr(entity, "vehicle_make", None)
    if isinstance(raw_make, str):
        raw_make = _MAKE_ALIASES.get(raw_make.strip().lower(), raw_make)
    stored_make = _norm_token(raw_make if isinstance(raw_make, str) else None)
    expected_makes = {t for t in (label_make, stored_make) if t}
    label_model = _norm_token(_earliest_vocab(name, VEHICLE_MODELS, {}))
    expected_models = {t for t in (label_model, _norm_token(getattr(entity, "vehicle_model", None))) if t}
    stored_color = normalize_color_name(getattr(entity, "vehicle_color", None))

    if makes_seen and expected_makes and not (makes_seen & expected_makes):
        return "contradict"
    if models_seen and expected_models and not (models_seen & expected_models):
        return "contradict"
    if colors_seen and stored_color and all(
        color_agreement(c, stored_color) == "conflict" for c in colors_seen
    ):
        return "contradict"
    if expected_makes and makes_seen & expected_makes:
        return "agree"
    return "none"


def suppress_inconsistent_vehicle_identity(
    description: str,
    identification: Optional[dict],
    entities: List,
) -> None:
    """Drop a vehicle label from identity when the description does not support it."""
    if not isinstance(identification, dict):
        return
    identity = identification.get("identity")
    if not isinstance(identity, str):
        return
    token = identity.strip()
    if not token or token.lower() in {"unknown", "cannot_tell"}:
        return
    for entity in entities or []:
        if getattr(entity, "entity_type", None) != "vehicle":
            continue
        name = getattr(entity, "name", None)
        if not isinstance(name, str) or token.lower() != name.strip().lower():
            continue
        if not vehicle_label_agrees(description, entity):
            identification["identity"] = "cannot_tell"
        return



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

        named_persons = [
            e for e in named_entities
            if getattr(e, "entity_type", None) == "person"
        ]
        named_vehicles = [
            e for e in named_entities
            if getattr(e, "entity_type", None) == "vehicle"
            and vehicle_label_agrees(original_description, e)
        ]
        # Fall back to the old "all named entities" list when type is missing
        # (some callers/tests only set .name). A vehicle the description
        # disagrees with stays out of that list.
        if not named_persons and not named_vehicles:
            untyped = [
                e for e in named_entities
                if getattr(e, "entity_type", None) not in ("person", "vehicle")
            ]
            if untyped:
                named_persons = untyped

        person_str = self._join_entity_names(named_persons)
        vehicle_phrase = self._format_vehicle_phrase(named_vehicles, person_str)

        enriched = original_description

        if vehicle_phrase:
            vehicle_patterns = [
                r'\b[Aa] vehicle\b',
                r'\b[Vv]ehicle\b',
                r'\b[Aa] car\b',
                r'\b[Cc]ar\b',
                r'\b[Aa] (?:red|blue|white|black|silver|gray|grey|green)\s+(?:suv|sedan|truck|van|coupe|hatchback)\b',
            ]
            for pattern in vehicle_patterns:
                updated = self._replace_vehicle_phrase(enriched, pattern, vehicle_phrase)
                if updated != enriched:
                    enriched = updated
                    break

        if person_str:
            person_patterns = [
                (r'\b[Aa] person\b', person_str),
                (r'\b[Pp]erson\b', person_str),
                (r'\b[Aa] man\b', person_str),
                (r'\b[Aa] woman\b', person_str),
                (r'\b[Ss]omeone\b', person_str),
                (r'\b[Aa]n individual\b', person_str),
                (r'\b[Aa] visitor\b', person_str),
            ]
            for pattern, replacement in person_patterns:
                updated = re.sub(pattern, replacement, enriched, count=1, flags=re.IGNORECASE)
                if updated != enriched:
                    enriched = updated
                    break

        return enriched

    @staticmethod
    def _optional_str(value) -> Optional[str]:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _join_entity_names(self, entities: List[RecognizedEntity]) -> Optional[str]:
        names = [e.name for e in entities if e.name and str(e.name).strip()]
        if not names:
            return None
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return ", ".join(names[:-1]) + f", and {names[-1]}"

    def _format_vehicle_phrase(
        self,
        vehicles: List[RecognizedEntity],
        person_str: Optional[str],
    ) -> Optional[str]:
        if not vehicles:
            return None
        vehicle = vehicles[0]
        color = self._optional_str(getattr(vehicle, "vehicle_color", None))
        make = self._optional_str(getattr(vehicle, "vehicle_make", None))
        model = self._optional_str(getattr(vehicle, "vehicle_model", None))
        details = " ".join(p for p in (color, make, model) if p)
        if details and person_str:
            return f"{person_str}'s {details}"
        if details:
            return f"the {details}"
        name = self._optional_str(getattr(vehicle, "name", None))
        if person_str and name:
            return f"{person_str}'s {name}"
        if name:
            return f"the {name}"
        return None

    @staticmethod
    def _replace_vehicle_phrase(text: str, pattern: str, phrase: str) -> str:
        """Swap one generic vehicle mention for a natural noun phrase."""

        def _repl(match: re.Match) -> str:
            replacement = phrase
            start = match.start()
            at_boundary = start == 0 or (start >= 2 and text[start - 2] in ".!?")
            if at_boundary and replacement[:1].islower():
                replacement = replacement[0].upper() + replacement[1:]
            return replacement

        return re.sub(pattern, _repl, text, count=1, flags=re.IGNORECASE)

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

    async def rewrite_reanalysis_description(
        self,
        db: Session,
        event: Event,
        description: str,
        identification: Optional[dict] = None,
    ) -> str:
        """Apply the live Protect named rewrite to a fresh reanalysis sentence.

        Uses ``enrich_description`` on entities already linked to the event.
        The returned text is what both ``description`` and
        ``enriched_description`` should store. When no linked name changes
        the sentence, that text is the new description, so a previous
        enriched description cannot stay behind.

        ``identification`` is updated in place when a vehicle label is not
        supported by the new sentence, the same as live ingest.
        """
        if not description:
            return description
        try:
            entity_ids = collect_linked_entity_ids(db, event)
            entities = (
                await self.get_entities_by_ids(db, entity_ids) if entity_ids else []
            )
            if entities:
                suppress_inconsistent_vehicle_identity(
                    description, identification, entities
                )
                rewritten = self.enrich_description(description, entities)
                if rewritten:
                    if rewritten != description:
                        logger.info(
                            "Reanalysis description rewritten with linked entities",
                            extra={
                                "event_type": "reanalyze_description_enriched",
                                "event_id": getattr(event, "id", None),
                                "entity_count": len(entities),
                            },
                        )
                    return rewritten
            return description
        except Exception as exc:
            logger.warning(
                "Reanalysis description enrichment failed; keeping the new description",
                extra={
                    "event_type": "reanalyze_enrichment_failed",
                    "event_id": getattr(event, "id", None),
                    "error_type": type(exc).__name__,
                },
            )
            return description


# Backward compatible thin getter (delegates to @singleton decorator)
def _entity_ids_from_json(raw) -> List[str]:
    """Parse a stored entity-id list. Malformed values yield no ids."""
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
    ids = []
    for value in values:
        if isinstance(value, str) and value.strip():
            ids.append(value.strip())
    return ids


def collect_linked_entity_ids(db: Session, event: Event) -> List[str]:
    """Entity ids already linked to this event.

    Live Protect ingest stores ``matched_entity_ids`` and a final link.
    The entity-alert path reads face and vehicle embeddings. A manual
    assignment is an ``entity_events`` row. Reanalysis uses all of those
    so a known name is still applied to the new sentence. An event can have
    several entities (issue #652), so every one of them is returned.

    An entity the user removed from this event (a "remove", "unlink" or
    "move_from" adjustment) is left out unless it is linked again, so a
    stale face or vehicle embedding cannot bring a removed name back.
    """
    from app.models.entity_adjustment import EntityAdjustment
    from app.models.face_embedding import FaceEmbedding
    from app.models.recognized_entity import EntityEvent
    from app.models.vehicle_embedding import VehicleEmbedding

    ids: List[str] = []
    matched = _entity_ids_from_json(getattr(event, "matched_entity_ids", None))
    ids.extend(matched)
    final_id = getattr(event, "final_entity_id", None)
    if isinstance(final_id, str) and final_id.strip():
        ids.append(final_id.strip())

    event_id = getattr(event, "id", None)
    if isinstance(event_id, str) and event_id:
        linked: List[str] = []
        for model in (FaceEmbedding, VehicleEmbedding, EntityEvent):
            rows = (
                db.query(model.entity_id)
                .filter(model.event_id == event_id, model.entity_id.isnot(None))
                .all()
            )
            for (entity_id,) in rows:
                if isinstance(entity_id, str) and entity_id.strip():
                    ids.append(entity_id.strip())
                    if model is EntityEvent:
                        linked.append(entity_id.strip())

        removed_rows = (
            db.query(EntityAdjustment.old_entity_id)
            .filter(
                EntityAdjustment.event_id == event_id,
                EntityAdjustment.action.in_(("remove", "unlink", "move_from")),
                EntityAdjustment.old_entity_id.isnot(None),
            )
            .all()
        )
        keep = set(linked) | set(matched)
        removed = {
            row[0] for row in removed_rows
            if isinstance(row[0], str) and row[0] not in keep
        }
        if removed:
            ids = [i for i in ids if i not in removed]

    return list(dict.fromkeys(ids))


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
