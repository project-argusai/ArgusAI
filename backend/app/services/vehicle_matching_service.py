"""
Vehicle Matching Service for Vehicle Recognition (Story P4-8.3)

This module matches vehicle embeddings to known vehicles for recognition.
It bridges VehicleEmbeddingService (P4-8.3) and EntityService (P4-3.3) to enable
recognition of familiar vehicles with "Your car arrived" style notifications.

Architecture:
    - Uses VehicleEmbedding records from P4-8.3
    - Matches against RecognizedEntity records where entity_type='vehicle'
    - Creates EntityEvent links on successful matches
    - Optionally creates new vehicle entities when no match found
    - Handles multiple vehicles per event independently
    - Extracts vehicle characteristics (color, type) from AI descriptions

Privacy:
    - All vehicle data stored locally only
    - User controls via vehicle_recognition_enabled setting
    - New vehicles start unnamed (user names them later)
"""
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.orm import Session

from app.services.similarity_service import batch_cosine_similarity

logger = logging.getLogger(__name__)


# Known color words for extraction
VEHICLE_COLORS = [
    "black", "white", "gray", "grey", "silver", "red", "blue", "green",
    "brown", "beige", "tan", "gold", "yellow", "orange", "purple",
    "maroon", "navy", "dark", "light", "bright"
]

# Comprehensive list of vehicle makes for extraction
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
    # Other
    "honda", "mazda",
]

# Vehicle type keywords for extraction
VEHICLE_TYPE_KEYWORDS = {
    "sedan": ["sedan", "saloon", "coupe", "sports car"],
    "suv": ["suv", "crossover", "utility", "4x4"],
    "truck": ["truck", "pickup", "lorry", "flatbed"],
    "van": ["van", "minivan", "cargo van", "delivery"],
    "motorcycle": ["motorcycle", "motorbike", "scooter", "bike"],
    "bus": ["bus", "coach", "shuttle"],
    "hatchback": ["hatchback", "compact"],
    "convertible": ["convertible", "roadster", "cabriolet"],
}

# Common vehicle models for extraction (helps with pattern matching)
COMMON_MODELS = [
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


@dataclass
class VehicleMatchResult:
    """Result of vehicle-to-entity matching operation."""
    vehicle_embedding_id: str
    vehicle_id: Optional[str]  # None if no match and auto_create disabled
    vehicle_name: Optional[str]
    similarity_score: float
    is_new_vehicle: bool
    is_appearance_update: bool
    bounding_box: dict
    vehicle_type: Optional[str]
    extracted_characteristics: Optional[dict]


class VehicleMatchingService:
    """
    Match vehicle embeddings to known vehicles.

    Uses CLIP embeddings from VehicleEmbeddingService and matches against
    RecognizedEntity records with entity_type='vehicle'. Enables personalized
    alerts like "Your car arrived" instead of generic "Vehicle detected".

    Attributes:
        DEFAULT_THRESHOLD: Default similarity threshold (0.65, looser than faces)
        HIGH_CONFIDENCE_THRESHOLD: Threshold for appearance updates (0.85)
        APPEARANCE_DIFF_THRESHOLD: Embedding difference threshold for updates (0.15)
    """

    DEFAULT_THRESHOLD = 0.65  # Looser than faces due to vehicle variation
    HIGH_CONFIDENCE_THRESHOLD = 0.85
    APPEARANCE_DIFF_THRESHOLD = 0.15

    def __init__(self):
        """Initialize VehicleMatchingService."""
        self._vehicle_cache: dict[str, list[float]] = {}  # vehicle_id -> embedding
        self._cache_loaded = False
        logger.info(
            "VehicleMatchingService initialized",
            extra={"event_type": "vehicle_matching_service_init"}
        )

    def _load_vehicle_cache(self, db: Session) -> None:
        """
        Load all vehicle embeddings into memory cache.

        Only loads RecognizedEntity records where entity_type='vehicle'.

        Args:
            db: SQLAlchemy database session
        """
        from app.models.recognized_entity import RecognizedEntity

        start_time = time.time()

        vehicles = db.query(
            RecognizedEntity.id,
            RecognizedEntity.reference_embedding
        ).filter(
            RecognizedEntity.entity_type == "vehicle"
        ).all()

        self._vehicle_cache = {}
        for vehicle in vehicles:
            try:
                embedding = json.loads(vehicle.reference_embedding)
                self._vehicle_cache[vehicle.id] = embedding
            except json.JSONDecodeError:
                logger.warning(
                    f"Invalid embedding JSON for vehicle {vehicle.id}",
                    extra={"vehicle_id": vehicle.id}
                )

        self._cache_loaded = True
        load_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Vehicle cache loaded: {len(self._vehicle_cache)} vehicles in {load_time_ms:.2f}ms",
            extra={
                "event_type": "vehicle_cache_loaded",
                "vehicle_count": len(self._vehicle_cache),
                "load_time_ms": round(load_time_ms, 2),
            }
        )

    def _invalidate_cache(self) -> None:
        """Clear the vehicle embedding cache."""
        self._vehicle_cache = {}
        self._cache_loaded = False
        logger.debug(
            "Vehicle cache invalidated",
            extra={"event_type": "vehicle_cache_invalidated"}
        )

    def _extract_vehicle_characteristics(
        self,
        description: Optional[str],
        detected_type: Optional[str] = None,
    ) -> dict:
        """
        Extract vehicle characteristics from AI description.

        Parses the AI-generated event description to extract color,
        make, model, type, and creates a vehicle signature for matching.

        Args:
            description: AI-generated event description
            detected_type: Vehicle type from detection (car, truck, etc.)

        Returns:
            Dictionary with extracted characteristics including vehicle_signature
        """
        characteristics = {}

        if detected_type:
            characteristics["detected_type"] = detected_type

        if not description:
            return characteristics

        desc_lower = description.lower()

        # Extract colors
        found_colors = []
        for color in VEHICLE_COLORS:
            # Use word boundary to avoid partial matches
            if re.search(rf'\b{color}\b', desc_lower):
                found_colors.append(color)
        if found_colors:
            characteristics["colors"] = found_colors
            characteristics["primary_color"] = found_colors[0]

        # Extract vehicle type from description
        for type_name, keywords in VEHICLE_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    characteristics["described_type"] = type_name
                    break
            if "described_type" in characteristics:
                break

        # Extract make from known makes list - find FIRST occurrence in text
        extracted_make = None
        earliest_pos = len(desc_lower) + 1  # Start with position beyond end

        for make in VEHICLE_MAKES:
            # Use word boundary for accurate matching
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

        if extracted_make:
            characteristics["make"] = extracted_make.title()

        # Extract model from known models list
        extracted_model = None
        for model in COMMON_MODELS:
            # Handle models with special chars like F-150
            model_pattern = re.escape(model).replace(r'\-', r'[-\s]?')
            if re.search(rf'\b{model_pattern}\b', desc_lower):
                # Normalize model names (remove hyphens, standardize)
                normalized_model = model.replace("-", "").replace(" ", "")
                extracted_model = normalized_model
                break

        if extracted_model:
            characteristics["model"] = extracted_model.title()

        # Try pattern-based extraction for color + make + model
        # Pattern: "color make model" e.g., "white Toyota Camry"
        color_pattern = "|".join(VEHICLE_COLORS)
        make_pattern = "|".join([re.escape(m) for m in VEHICLE_MAKES])

        # Try to match "color make model" pattern
        full_pattern = rf'\b({color_pattern})\s+({make_pattern})\s+(\w+[-\w]*)\b'
        full_match = re.search(full_pattern, desc_lower)
        if full_match:
            color_from_pattern = full_match.group(1)
            make_from_pattern = full_match.group(2)
            model_from_pattern = full_match.group(3)

            # Update characteristics with pattern-matched values
            if not characteristics.get("primary_color"):
                characteristics["primary_color"] = color_from_pattern
                characteristics["colors"] = [color_from_pattern]

            if not characteristics.get("make"):
                # Normalize
                if make_from_pattern in ["chevy"]:
                    make_from_pattern = "chevrolet"
                elif make_from_pattern in ["vw"]:
                    make_from_pattern = "volkswagen"
                characteristics["make"] = make_from_pattern.title()

            if not characteristics.get("model"):
                # Don't use common words as models - comprehensive list
                skip_words = [
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
                if model_from_pattern not in skip_words:
                    normalized_model = model_from_pattern.replace("-", "")
                    characteristics["model"] = normalized_model.title()

        # Create vehicle signature for matching (color-make-model)
        signature_parts = []
        if characteristics.get("primary_color"):
            # Normalize gray/grey
            color = characteristics["primary_color"]
            if color == "grey":
                color = "gray"
            signature_parts.append(color.lower())

        if characteristics.get("make"):
            signature_parts.append(characteristics["make"].lower())

        if characteristics.get("model"):
            signature_parts.append(characteristics["model"].lower())

        if len(signature_parts) >= 2:  # Need at least 2 parts for meaningful signature
            characteristics["vehicle_signature"] = "-".join(signature_parts)

        logger.debug(
            f"Extracted vehicle characteristics: {characteristics}",
            extra={
                "event_type": "vehicle_characteristics_extracted",
                "has_signature": "vehicle_signature" in characteristics,
                "characteristics": characteristics,
            }
        )

        return characteristics

    def _find_vehicle_by_signature(
        self,
        db: Session,
        signature: str,
    ) -> Optional[str]:
        """
        Find a vehicle entity by its signature (color-make-model).

        Args:
            db: SQLAlchemy database session
            signature: Vehicle signature string (e.g., "white-toyota-camry")

        Returns:
            Vehicle entity ID if found, None otherwise
        """
        from app.models.recognized_entity import RecognizedEntity

        # Search for vehicles with matching signature in metadata
        vehicles = db.query(RecognizedEntity).filter(
            RecognizedEntity.entity_type == "vehicle"
        ).all()

        for vehicle in vehicles:
            if vehicle.metadata:
                try:
                    metadata = json.loads(vehicle.metadata)
                    if metadata.get("vehicle_signature") == signature:
                        logger.debug(
                            f"Found vehicle by signature: {signature} -> {vehicle.id}",
                            extra={
                                "event_type": "vehicle_signature_match",
                                "signature": signature,
                                "vehicle_id": vehicle.id,
                            }
                        )
                        return vehicle.id
                except json.JSONDecodeError:
                    pass

        return None

    async def match_vehicles_to_entities(
        self,
        db: Session,
        vehicle_embedding_ids: list[str],
        event_description: Optional[str] = None,
        auto_create: bool = True,
        threshold: float = DEFAULT_THRESHOLD,
        update_appearance: bool = True,
    ) -> list[VehicleMatchResult]:
        """
        Match multiple vehicle embeddings to known vehicles.

        Args:
            db: SQLAlchemy database session
            vehicle_embedding_ids: List of VehicleEmbedding IDs to match
            event_description: AI description for characteristics extraction
            auto_create: If True, create new vehicle when no match found
            threshold: Minimum similarity score for matching
            update_appearance: If True, update reference embedding on high-confidence match

        Returns:
            List of VehicleMatchResult, one per vehicle embedding (same order)
        """
        if not vehicle_embedding_ids:
            return []

        results = []
        for vehicle_id in vehicle_embedding_ids:
            try:
                result = await self.match_single_vehicle(
                    db,
                    vehicle_id,
                    event_description=event_description,
                    threshold=threshold,
                    auto_create=auto_create,
                    update_appearance=update_appearance,
                )
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Failed to match vehicle {vehicle_id}: {e}",
                    exc_info=True,
                    extra={
                        "event_type": "vehicle_match_error",
                        "vehicle_embedding_id": vehicle_id,
                        "error": str(e),
                    }
                )
                # Continue with remaining vehicles

        logger.info(
            f"Matched {len(results)}/{len(vehicle_embedding_ids)} vehicles to entities",
            extra={
                "event_type": "vehicle_matching_complete",
                "total_vehicles": len(vehicle_embedding_ids),
                "matched_count": sum(1 for r in results if r.vehicle_id),
                "new_vehicles": sum(1 for r in results if r.is_new_vehicle),
            }
        )

        return results

    async def match_single_vehicle(
        self,
        db: Session,
        vehicle_embedding_id: str,
        event_description: Optional[str] = None,
        threshold: float = DEFAULT_THRESHOLD,
        auto_create: bool = True,
        update_appearance: bool = True,
    ) -> VehicleMatchResult:
        """
        Match a single vehicle embedding to a known vehicle.

        Args:
            db: SQLAlchemy database session
            vehicle_embedding_id: ID of the VehicleEmbedding to match
            event_description: AI description for characteristics extraction
            threshold: Minimum similarity score for matching
            auto_create: If True, create new vehicle when no match found
            update_appearance: If True, update reference embedding on high-confidence match

        Returns:
            VehicleMatchResult with match details

        Raises:
            ValueError: If vehicle embedding not found
        """
        from app.models.vehicle_embedding import VehicleEmbedding
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        start_time = time.time()

        # Load vehicle embedding
        vehicle_embedding = db.query(VehicleEmbedding).filter(
            VehicleEmbedding.id == vehicle_embedding_id
        ).first()

        if not vehicle_embedding:
            raise ValueError(f"VehicleEmbedding {vehicle_embedding_id} not found")

        embedding_vector = json.loads(vehicle_embedding.embedding)
        bounding_box = json.loads(vehicle_embedding.bounding_box)
        vehicle_type = vehicle_embedding.vehicle_type

        # Extract characteristics from description
        characteristics = self._extract_vehicle_characteristics(
            event_description,
            detected_type=vehicle_type
        )

        # Load cache if needed
        if not self._cache_loaded:
            self._load_vehicle_cache(db)

        # SIGNATURE-BASED MATCHING (Story P9-1.8)
        # Try to match by vehicle signature first (color-make-model)
        # This ensures vehicles with same characteristics are grouped together
        vehicle_signature = characteristics.get("vehicle_signature")
        if vehicle_signature:
            signature_match_id = self._find_vehicle_by_signature(db, vehicle_signature)
            if signature_match_id:
                # Found vehicle with matching signature - use it
                match_time_ms = (time.time() - start_time) * 1000
                result = await self._update_existing_vehicle(
                    db,
                    vehicle_embedding,
                    signature_match_id,
                    0.9,  # High confidence for signature match
                    embedding_vector,
                    bounding_box,
                    vehicle_type,
                    characteristics,
                    update_appearance,
                )
                logger.info(
                    f"Vehicle matched by signature: {vehicle_signature} -> {signature_match_id}",
                    extra={
                        "event_type": "vehicle_signature_matched",
                        "vehicle_embedding_id": vehicle_embedding_id,
                        "vehicle_id": signature_match_id,
                        "vehicle_signature": vehicle_signature,
                        "match_time_ms": round(match_time_ms, 2),
                    }
                )
                return result

        # If no vehicles exist, create first one (if auto_create enabled)
        if not self._vehicle_cache:
            if auto_create:
                result = await self._create_new_vehicle(
                    db, vehicle_embedding, embedding_vector, bounding_box,
                    vehicle_type, characteristics
                )
                match_time_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"First vehicle created from embedding {vehicle_embedding_id}",
                    extra={
                        "event_type": "vehicle_created_first",
                        "vehicle_embedding_id": vehicle_embedding_id,
                        "vehicle_id": result.vehicle_id,
                        "match_time_ms": round(match_time_ms, 2),
                    }
                )
                return result
            else:
                return VehicleMatchResult(
                    vehicle_embedding_id=vehicle_embedding_id,
                    vehicle_id=None,
                    vehicle_name=None,
                    similarity_score=0.0,
                    is_new_vehicle=False,
                    is_appearance_update=False,
                    bounding_box=bounding_box,
                    vehicle_type=vehicle_type,
                    extracted_characteristics=characteristics,
                )

        # Calculate similarity with all known vehicles
        vehicle_ids = list(self._vehicle_cache.keys())
        vehicle_embeddings = [self._vehicle_cache[vid] for vid in vehicle_ids]

        similarities = batch_cosine_similarity(embedding_vector, vehicle_embeddings)

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
            matched_vehicle_id = vehicle_ids[best_idx]
            result = await self._update_existing_vehicle(
                db,
                vehicle_embedding,
                matched_vehicle_id,
                best_score,
                embedding_vector,
                bounding_box,
                vehicle_type,
                characteristics,
                update_appearance,
            )
            logger.info(
                f"Vehicle embedding {vehicle_embedding_id} matched to vehicle {matched_vehicle_id}",
                extra={
                    "event_type": "vehicle_matched",
                    "vehicle_embedding_id": vehicle_embedding_id,
                    "vehicle_id": matched_vehicle_id,
                    "vehicle_name": result.vehicle_name,
                    "similarity_score": round(best_score, 4),
                    "match_time_ms": round(match_time_ms, 2),
                }
            )
            return result
        else:
            # No match found
            if auto_create:
                result = await self._create_new_vehicle(
                    db, vehicle_embedding, embedding_vector, bounding_box,
                    vehicle_type, characteristics
                )
                logger.info(
                    f"New vehicle created from embedding {vehicle_embedding_id}",
                    extra={
                        "event_type": "vehicle_created_new",
                        "vehicle_embedding_id": vehicle_embedding_id,
                        "vehicle_id": result.vehicle_id,
                        "best_score_below_threshold": round(max(similarities) if similarities else 0, 4),
                        "threshold": threshold,
                        "match_time_ms": round(match_time_ms, 2),
                    }
                )
                return result
            else:
                logger.debug(
                    f"No vehicle match for embedding {vehicle_embedding_id} (auto_create disabled)",
                    extra={
                        "event_type": "vehicle_no_match",
                        "vehicle_embedding_id": vehicle_embedding_id,
                        "best_score": round(max(similarities) if similarities else 0, 4),
                        "threshold": threshold,
                    }
                )
                return VehicleMatchResult(
                    vehicle_embedding_id=vehicle_embedding_id,
                    vehicle_id=None,
                    vehicle_name=None,
                    similarity_score=max(similarities) if similarities else 0.0,
                    is_new_vehicle=False,
                    is_appearance_update=False,
                    bounding_box=bounding_box,
                    vehicle_type=vehicle_type,
                    extracted_characteristics=characteristics,
                )

    async def _create_new_vehicle(
        self,
        db: Session,
        vehicle_embedding,  # VehicleEmbedding model
        embedding_vector: list[float],
        bounding_box: dict,
        vehicle_type: Optional[str],
        characteristics: dict,
    ) -> VehicleMatchResult:
        """Create a new vehicle entity from a vehicle embedding."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.vehicle_embedding import VehicleEmbedding

        vehicle_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Get event timestamp for temporal tracking
        event_timestamp = now
        if vehicle_embedding.event:
            event_timestamp = vehicle_embedding.event.timestamp or now

        # Build metadata from characteristics
        metadata = {}
        if characteristics:
            metadata = characteristics.copy()
        if vehicle_type:
            metadata["detected_type"] = vehicle_type

        # Create vehicle entity
        new_vehicle = RecognizedEntity(
            id=vehicle_id,
            entity_type="vehicle",
            name=None,  # User names later
            reference_embedding=json.dumps(embedding_vector),
            metadata=json.dumps(metadata) if metadata else None,
            first_seen_at=event_timestamp,
            last_seen_at=event_timestamp,
            occurrence_count=1,
            created_at=now,
            updated_at=now,
        )
        db.add(new_vehicle)

        # Link vehicle embedding to entity
        vehicle_embedding.entity_id = vehicle_id

        # Create entity-event link (similarity 1.0 for first occurrence)
        entity_event = EntityEvent(
            entity_id=vehicle_id,
            event_id=vehicle_embedding.event_id,
            similarity_score=1.0,
            created_at=now,
        )
        db.add(entity_event)

        db.commit()

        # Update cache
        self._vehicle_cache[vehicle_id] = embedding_vector

        return VehicleMatchResult(
            vehicle_embedding_id=vehicle_embedding.id,
            vehicle_id=vehicle_id,
            vehicle_name=None,
            similarity_score=1.0,
            is_new_vehicle=True,
            is_appearance_update=False,
            bounding_box=bounding_box,
            vehicle_type=vehicle_type,
            extracted_characteristics=characteristics,
        )

    async def _update_existing_vehicle(
        self,
        db: Session,
        vehicle_embedding,  # VehicleEmbedding model
        vehicle_id: str,
        similarity_score: float,
        embedding_vector: list[float],
        bounding_box: dict,
        vehicle_type: Optional[str],
        characteristics: dict,
        update_appearance: bool,
    ) -> VehicleMatchResult:
        """Update an existing vehicle with new occurrence."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        now = datetime.now(timezone.utc)

        # Get event timestamp for temporal tracking
        event_timestamp = now
        if vehicle_embedding.event:
            event_timestamp = vehicle_embedding.event.timestamp or now

        # Get vehicle
        vehicle = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == vehicle_id
        ).first()

        if not vehicle:
            raise ValueError(f"Vehicle {vehicle_id} not found")

        # Check for appearance update
        is_appearance_update = False
        if update_appearance and similarity_score >= self.HIGH_CONFIDENCE_THRESHOLD:
            # Calculate embedding difference
            current_embedding = json.loads(vehicle.reference_embedding)
            diff_similarities = batch_cosine_similarity(embedding_vector, [current_embedding])
            embedding_diff = 1.0 - diff_similarities[0]

            if embedding_diff >= self.APPEARANCE_DIFF_THRESHOLD:
                # Update reference embedding (weighted average: 70% old, 30% new)
                import numpy as np
                old_emb = np.array(current_embedding, dtype=np.float32)
                new_emb = np.array(embedding_vector, dtype=np.float32)
                updated_emb = (0.7 * old_emb + 0.3 * new_emb).tolist()

                vehicle.reference_embedding = json.dumps(updated_emb)
                self._vehicle_cache[vehicle_id] = updated_emb
                is_appearance_update = True

                logger.info(
                    f"Vehicle {vehicle_id} appearance updated",
                    extra={
                        "event_type": "vehicle_appearance_updated",
                        "vehicle_id": vehicle_id,
                        "embedding_diff": round(embedding_diff, 4),
                        "similarity_score": round(similarity_score, 4),
                    }
                )

        # Merge characteristics into existing metadata
        if characteristics:
            existing_metadata = {}
            if vehicle.metadata:
                try:
                    existing_metadata = json.loads(vehicle.metadata)
                except json.JSONDecodeError:
                    pass
            # Update with new characteristics (don't overwrite user data)
            for key, value in characteristics.items():
                if key not in existing_metadata:
                    existing_metadata[key] = value
            vehicle.metadata = json.dumps(existing_metadata)

        # Update vehicle metadata
        vehicle.occurrence_count += 1
        vehicle.last_seen_at = event_timestamp
        vehicle.updated_at = now

        # Link vehicle embedding to entity
        vehicle_embedding.entity_id = vehicle_id

        # Check if EntityEvent already exists (same vehicle in same event)
        existing_link = db.query(EntityEvent).filter(
            EntityEvent.entity_id == vehicle_id,
            EntityEvent.event_id == vehicle_embedding.event_id,
        ).first()

        if not existing_link:
            # Create entity-event link
            entity_event = EntityEvent(
                entity_id=vehicle_id,
                event_id=vehicle_embedding.event_id,
                similarity_score=similarity_score,
                created_at=now,
            )
            db.add(entity_event)

        db.commit()
        db.refresh(vehicle)

        return VehicleMatchResult(
            vehicle_embedding_id=vehicle_embedding.id,
            vehicle_id=vehicle.id,
            vehicle_name=vehicle.name,
            similarity_score=similarity_score,
            is_new_vehicle=False,
            is_appearance_update=is_appearance_update,
            bounding_box=bounding_box,
            vehicle_type=vehicle_type,
            extracted_characteristics=characteristics,
        )

    async def get_vehicles(
        self,
        db: Session,
        limit: int = 50,
        offset: int = 0,
        named_only: bool = False,
    ) -> tuple[list[dict], int]:
        """
        Get all vehicles (RecognizedEntity with entity_type='vehicle').

        Args:
            db: SQLAlchemy database session
            limit: Maximum number to return
            offset: Pagination offset
            named_only: If True, only return named vehicles

        Returns:
            Tuple of (list of vehicle dicts with embedding_count, total count)
        """
        from app.models.recognized_entity import RecognizedEntity
        from app.models.vehicle_embedding import VehicleEmbedding
        from sqlalchemy import func, desc

        query = db.query(RecognizedEntity).filter(
            RecognizedEntity.entity_type == "vehicle"
        )

        if named_only:
            query = query.filter(RecognizedEntity.name.isnot(None))

        total = query.count()

        vehicles = query.order_by(
            desc(RecognizedEntity.last_seen_at)
        ).offset(offset).limit(limit).all()

        # Get embedding counts for each vehicle
        vehicle_ids = [v.id for v in vehicles]
        embedding_counts = {}
        if vehicle_ids:
            counts = db.query(
                VehicleEmbedding.entity_id,
                func.count(VehicleEmbedding.id).label("count")
            ).filter(
                VehicleEmbedding.entity_id.in_(vehicle_ids)
            ).group_by(VehicleEmbedding.entity_id).all()

            embedding_counts = {c.entity_id: c.count for c in counts}

        result = []
        for v in vehicles:
            metadata = {}
            if v.metadata:
                try:
                    metadata = json.loads(v.metadata)
                except json.JSONDecodeError:
                    pass

            result.append({
                "id": v.id,
                "name": v.name,
                "first_seen_at": v.first_seen_at,
                "last_seen_at": v.last_seen_at,
                "occurrence_count": v.occurrence_count,
                "embedding_count": embedding_counts.get(v.id, 0),
                "vehicle_type": metadata.get("detected_type"),
                "primary_color": metadata.get("primary_color"),
                "metadata": metadata,
            })

        return result, total

    async def get_vehicle(
        self,
        db: Session,
        vehicle_id: str,
        include_embeddings: bool = True,
        embedding_limit: int = 10,
    ) -> Optional[dict]:
        """
        Get a single vehicle with its embeddings.

        Args:
            db: SQLAlchemy database session
            vehicle_id: UUID of the vehicle
            include_embeddings: Whether to include recent vehicle matches
            embedding_limit: Maximum number of embeddings to include

        Returns:
            Vehicle dict with optional embeddings, or None if not found
        """
        from app.models.recognized_entity import RecognizedEntity
        from app.models.vehicle_embedding import VehicleEmbedding
        from app.models.event import Event
        from sqlalchemy import desc

        vehicle = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == vehicle_id,
            RecognizedEntity.entity_type == "vehicle",
        ).first()

        if not vehicle:
            return None

        metadata = {}
        if vehicle.metadata:
            try:
                metadata = json.loads(vehicle.metadata)
            except json.JSONDecodeError:
                pass

        result = {
            "id": vehicle.id,
            "name": vehicle.name,
            "first_seen_at": vehicle.first_seen_at,
            "last_seen_at": vehicle.last_seen_at,
            "occurrence_count": vehicle.occurrence_count,
            "created_at": vehicle.created_at,
            "updated_at": vehicle.updated_at,
            "vehicle_type": metadata.get("detected_type"),
            "primary_color": metadata.get("primary_color"),
            "metadata": metadata,
        }

        if include_embeddings:
            # Get recent vehicle embeddings for this entity
            embeddings = db.query(
                VehicleEmbedding.id,
                VehicleEmbedding.event_id,
                VehicleEmbedding.bounding_box,
                VehicleEmbedding.confidence,
                VehicleEmbedding.vehicle_type,
                VehicleEmbedding.created_at,
                Event.timestamp.label("event_timestamp"),
                Event.thumbnail_path,
            ).join(
                Event, Event.id == VehicleEmbedding.event_id
            ).filter(
                VehicleEmbedding.entity_id == vehicle_id
            ).order_by(
                desc(VehicleEmbedding.created_at)
            ).limit(embedding_limit).all()

            result["recent_detections"] = [
                {
                    "id": e.id,
                    "event_id": e.event_id,
                    "bounding_box": json.loads(e.bounding_box) if e.bounding_box else None,
                    "confidence": e.confidence,
                    "vehicle_type": e.vehicle_type,
                    "created_at": e.created_at,
                    "event_timestamp": e.event_timestamp,
                    "thumbnail_url": e.thumbnail_path,
                }
                for e in embeddings
            ]

        return result

    async def update_vehicle_name(
        self,
        db: Session,
        vehicle_id: str,
        name: Optional[str],
    ) -> Optional[dict]:
        """
        Update a vehicle's name.

        Args:
            db: SQLAlchemy database session
            vehicle_id: UUID of the vehicle
            name: New name (or None to clear)

        Returns:
            Updated vehicle dict, or None if not found
        """
        from app.models.recognized_entity import RecognizedEntity

        vehicle = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == vehicle_id,
            RecognizedEntity.entity_type == "vehicle",
        ).first()

        if not vehicle:
            return None

        vehicle.name = name
        vehicle.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(vehicle)

        metadata = {}
        if vehicle.metadata:
            try:
                metadata = json.loads(vehicle.metadata)
            except json.JSONDecodeError:
                pass

        logger.info(
            f"Vehicle {vehicle_id} name updated to: {name}",
            extra={
                "event_type": "vehicle_name_updated",
                "vehicle_id": vehicle_id,
                "vehicle_name": name,  # Use vehicle_name to avoid LogRecord 'name' conflict
            }
        )

        return {
            "id": vehicle.id,
            "name": vehicle.name,
            "first_seen_at": vehicle.first_seen_at,
            "last_seen_at": vehicle.last_seen_at,
            "occurrence_count": vehicle.occurrence_count,
            "vehicle_type": metadata.get("detected_type"),
            "primary_color": metadata.get("primary_color"),
        }

    async def update_vehicle_metadata(
        self,
        db: Session,
        vehicle_id: str,
        metadata_updates: dict,
    ) -> Optional[dict]:
        """
        Update a vehicle's metadata (characteristics).

        Args:
            db: SQLAlchemy database session
            vehicle_id: UUID of the vehicle
            metadata_updates: Dictionary of metadata to update

        Returns:
            Updated vehicle dict, or None if not found
        """
        from app.models.recognized_entity import RecognizedEntity

        vehicle = db.query(RecognizedEntity).filter(
            RecognizedEntity.id == vehicle_id,
            RecognizedEntity.entity_type == "vehicle",
        ).first()

        if not vehicle:
            return None

        # Merge with existing metadata
        existing_metadata = {}
        if vehicle.metadata:
            try:
                existing_metadata = json.loads(vehicle.metadata)
            except json.JSONDecodeError:
                pass

        existing_metadata.update(metadata_updates)
        vehicle.metadata = json.dumps(existing_metadata)
        vehicle.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(vehicle)

        logger.info(
            f"Vehicle {vehicle_id} metadata updated",
            extra={
                "event_type": "vehicle_metadata_updated",
                "vehicle_id": vehicle_id,
                "updated_keys": list(metadata_updates.keys()),
            }
        )

        return {
            "id": vehicle.id,
            "name": vehicle.name,
            "first_seen_at": vehicle.first_seen_at,
            "last_seen_at": vehicle.last_seen_at,
            "occurrence_count": vehicle.occurrence_count,
            "vehicle_type": existing_metadata.get("detected_type"),
            "primary_color": existing_metadata.get("primary_color"),
            "metadata": existing_metadata,
        }


# Global singleton instance
_vehicle_matching_service: Optional[VehicleMatchingService] = None


def get_vehicle_matching_service() -> VehicleMatchingService:
    """
    Get the global VehicleMatchingService instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        VehicleMatchingService singleton instance
    """
    global _vehicle_matching_service

    if _vehicle_matching_service is None:
        _vehicle_matching_service = VehicleMatchingService()
        logger.info(
            "Global VehicleMatchingService instance created",
            extra={"event_type": "vehicle_matching_service_singleton_created"}
        )

    return _vehicle_matching_service


def reset_vehicle_matching_service() -> None:
    """
    Reset the global VehicleMatchingService instance.

    Useful for testing to ensure a fresh instance.
    """
    global _vehicle_matching_service
    _vehicle_matching_service = None
