"""
AIProviderBase - Abstract base class for all vision AI providers.

Extracted from the monolithic ai_service.py during Phase 3.3.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging

# Temporary import during extraction phase.
# Long-term: AIResult should live in a shared ai_types module.
from app.services.ai_types import AIResult
from app.services.ocr_service import OCRResult

logger = logging.getLogger(__name__)


class AIProviderBase(ABC):
    """
    Base class for AI vision providers.

    All concrete providers (OpenAI, Grok, Claude, Gemini) inherit from this.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.system_prompt = (
            "You are describing video surveillance events for home security and accessibility. "
            "Provide detailed, accurate descriptions."
        )
        self.user_prompt_template = (
            "Describe what you see in this image. Include: "
            "WHO (people, their appearance, clothing), "
            "WHAT (objects, vehicles, packages), "
            "WHERE (location in frame), "
            "and ACTIONS (what is happening). "
            "Be specific and detailed.\n\n"
            "If you see a delivery person or truck, identify the carrier:\n"
            "- FedEx (purple/orange colors, FedEx logo)\n"
            "- UPS (brown uniform, brown truck)\n"
            "- USPS (blue uniform, postal logo, mail truck)\n"
            "- Amazon (blue vest, Amazon logo, Amazon van)\n"
            "- DHL (yellow/red colors, DHL logo)\n"
            "Include the carrier name in your description."
        )

        # Some providers (e.g. during transition) may have access to these
        self.prompt_service = None
        self.providers = {}  # Used in legacy multi-image fallback in base

    @abstractmethod
    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
    ) -> AIResult:
        """Generate description from base64-encoded image."""
        pass

    @abstractmethod
    async def generate_multi_image_description(
        self,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
    ) -> AIResult:
        """Generate description from multiple base64-encoded images."""
        pass

    def _parse_confidence_response(self, response_text: str) -> tuple[str, Optional[int], Optional[List[Dict[str, Any]]]]:
        """Parse AI response for description, confidence score, and bounding boxes."""
        import json
        import re

        bounding_boxes = None

        try:
            brace_start = response_text.find('{')
            brace_end = response_text.rfind('}')
            if brace_start != -1 and brace_end > brace_start:
                json_str = response_text[brace_start:brace_end + 1]
                data = json.loads(json_str)
                description = data.get('description', '').strip()
                confidence = data.get('confidence')

                raw_boxes = data.get('bounding_boxes')
                if raw_boxes and isinstance(raw_boxes, list):
                    validated_boxes = []
                    for box in raw_boxes:
                        if isinstance(box, dict):
                            x = box.get('x')
                            y = box.get('y')
                            width = box.get('width')
                            height = box.get('height')
                            if all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in [x, y, width, height] if v is not None):
                                validated_boxes.append({
                                    'x': float(x) if x is not None else 0,
                                    'y': float(y) if y is not None else 0,
                                    'width': float(width) if width is not None else 0,
                                    'height': float(height) if height is not None else 0,
                                    'entity_type': box.get('entity_type', 'other'),
                                    'confidence': float(box.get('confidence', 0.5)),
                                    'label': box.get('label', ''),
                                })
                    if validated_boxes:
                        bounding_boxes = validated_boxes

                if isinstance(confidence, (int, float)) and 0 <= confidence <= 100:
                    if description:
                        return description, int(confidence), bounding_boxes

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug(f"JSON parsing failed for confidence extraction: {e}")

        # Truncated JSON handling + plain text fallback (kept from original)
        truncated_match = re.search(r'\{\s*"description"\s*:\s*"([^"]+)$', response_text, re.DOTALL)
        if truncated_match:
            partial_desc = truncated_match.group(1).strip()
            return partial_desc, None, None

        confidence_patterns = [
            r'confidence[:\s]+(\d{1,3})(?:%|\b)',
            r'(\d{1,3})%?\s*confiden',
            r'confidence\s*(?:score|level|rating)?[:\s]*(\d{1,3})',
        ]
        for pattern in confidence_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                try:
                    confidence = int(match.group(1))
                    if 0 <= confidence <= 100:
                        return response_text, confidence, None
                except (ValueError, IndexError):
                    continue

        return response_text, None, None

    def _extract_objects(self, description: str) -> List[str]:
        """Extract object types from description text"""
        objects = []
        description_lower = description.lower()

        if any(word in description_lower for word in ['person', 'people', 'man', 'woman', 'child', 'human']):
            objects.append('person')
        if any(word in description_lower for word in ['vehicle', 'car', 'truck', 'van', 'motorcycle', 'bike']):
            objects.append('vehicle')
        if any(word in description_lower for word in ['animal', 'dog', 'cat', 'bird', 'pet']):
            objects.append('animal')
        if any(word in description_lower for word in ['package', 'box', 'delivery', 'parcel']):
            objects.append('package')

        if not objects:
            objects.append('unknown')

        return objects
