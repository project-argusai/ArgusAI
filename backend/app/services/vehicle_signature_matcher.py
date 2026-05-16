"""
Vehicle Signature Matcher (Story P9-4.1)

Extracted from EntityService during Phase 6 decomposition.

This class handles signature-based vehicle entity matching using
color + make + model extracted from AI descriptions. It provides
a more reliable way to group the same vehicle across events even
when CLIP embeddings vary slightly due to lighting/angle.

Responsibilities:
- Extract vehicle info (color, make, model) from descriptions
- Generate normalized signatures (e.g. "white-toyota-camry")
- Find existing vehicle entities by exact signature match
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Vehicle Extraction Constants (moved from entity_service.py)
# =============================================================================

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

VEHICLE_MODELS = [
    # Toyota
    "camry", "corolla", "rav4", "highlander", "tacoma", "tundra", "prius", "4runner",
    # Honda
    "civic", "accord", "cr-v", "pilot", "odyssey", "fit", "hr-v",
    # Ford
    "f-150", "f150", "mustang", "explorer", "escape", "edge", "focus",
    # Chevrolet
    "silverado", "tahoe", "suburban", "malibu", "equinox", "traverse",
    # Tesla
    "model 3", "model y", "model s", "model x",
    # Others
    "crv", "rav", "f150", "4runner",
]

SKIP_WORDS = [
    # Vehicle types
    "car", "truck", "van", "suv", "vehicle", "auto", "sedan", "coupe",
    "hatchback", "convertible", "wagon", "crossover", "pickup", "minivan",
    # Verbs/actions
    "pulling", "parked", "driving", "arrived", "leaving", "stopped",
    "passing", "turning", "slowing", "speeding",
    # Common words
    "the", "and", "with", "from", "into", "on", "at", "by",
]


@dataclass
class VehicleEntityInfo:
    """Extracted vehicle entity information from AI description."""
    color: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    signature: Optional[str] = None

    def is_valid(self) -> bool:
        """Check if minimum data requirements are met (color+make OR make+model)."""
        has_color = self.color is not None
        has_make = self.make is not None
        has_model = self.model is not None
        return (has_color and has_make) or (has_make and has_model)


class VehicleSignatureMatcher:
    """
    Handles signature-based vehicle entity matching.

    This class encapsulates all logic related to extracting vehicle
    information from descriptions and matching vehicles using
    color/make/model signatures (Story P9-4.1).

    It is intentionally separate from pure embedding-based matching
    so the two strategies can evolve independently.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def generate_signature(self, description: str) -> Optional[VehicleEntityInfo]:
        """
        Extract vehicle details from AI description and build a signature.

        Returns VehicleEntityInfo with signature if sufficient data is found,
        otherwise returns None.
        """
        if not description:
            return None

        desc_lower = description.lower()

        # Extract color
        extracted_color = None
        for color in VEHICLE_COLORS:
            if re.search(rf'\b{color}\b', desc_lower):
                if color == "grey":
                    color = "gray"
                extracted_color = color
                break

        # Extract make (first occurrence wins)
        extracted_make = None
        earliest_pos = len(desc_lower) + 1

        for make in VEHICLE_MAKES:
            match = re.search(rf'\b{re.escape(make)}\b', desc_lower)
            if match and match.start() < earliest_pos:
                earliest_pos = match.start()
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

        # Extract model from known list
        extracted_model = None
        for model in VEHICLE_MODELS:
            model_pattern = re.escape(model).replace(r'\-', r'[-\s]?')
            if re.search(rf'\b{model_pattern}\b', desc_lower):
                normalized_model = model.replace("-", "").replace(" ", "")
                extracted_model = normalized_model
                break

        # Fallback: try "make + word" pattern for unknown models
        if not extracted_model and extracted_make:
            make_pattern = re.escape(extracted_make)
            pattern = rf'\b{make_pattern}\s+(\w+[-\w]*)\b'
            match = re.search(pattern, desc_lower)
            if match:
                potential_model = match.group(1)
                if potential_model not in SKIP_WORDS and len(potential_model) >= 2:
                    extracted_model = potential_model.replace("-", "")

        info = VehicleEntityInfo(
            color=extracted_color,
            make=extracted_make,
            model=extracted_model,
            signature=None
        )

        if info.is_valid():
            parts = []
            if info.color:
                parts.append(info.color.lower())
            if info.make:
                parts.append(info.make.lower())
            if info.model:
                parts.append(info.model.lower())
            info.signature = "-".join(parts)

            self.logger.debug(
                f"Vehicle entity extracted: {info.signature}",
                extra={
                    "event_type": "vehicle_entity_extracted",
                    "color": info.color,
                    "make": info.make,
                    "model": info.model,
                }
            )

        return info if info.is_valid() else None

    def find_entity_by_signature(self, db: Session, signature: str) -> Optional[str]:
        """
        Find an existing vehicle entity by its exact signature.
        """
        from app.models.recognized_entity import RecognizedEntity

        entity = db.query(RecognizedEntity.id).filter(
            RecognizedEntity.entity_type == "vehicle",
            RecognizedEntity.vehicle_signature == signature
        ).first()

        if entity:
            self.logger.debug(
                f"Found vehicle entity by signature: {signature} -> {entity.id}",
                extra={
                    "event_type": "vehicle_signature_match",
                    "signature": signature,
                    "entity_id": entity.id,
                }
            )
            return entity.id

        return None
