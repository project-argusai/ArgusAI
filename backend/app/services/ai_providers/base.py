"""
AIProviderBase - Abstract base class for all vision AI providers.

Extracted from the monolithic ai_service.py during Phase 3.3.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging
import math
import numbers
import re
from decimal import ROUND_HALF_UP, Decimal

import numpy as np

# Temporary import during extraction phase.
# Long-term: AIResult should live in a shared ai_types module.
from app.services.ai_types import AIResult
from app.services.ocr_service import OCRResult

logger = logging.getLogger(__name__)


def resolve_request_timeout(requested: Optional[float], default: float) -> float:
    """HTTP timeout for one provider call.

    ``requested`` is the orchestrator's remaining budget for this attempt.
    A missing or non-positive value keeps the provider's own default.
    """
    if requested is None:
        return default
    try:
        value = float(requested)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return value


_NUMERIC_STRING = re.compile(r"\d{1,3}(?:\.\d+)?")


def normalize_confidence(value: Any) -> Optional[int]:
    """Map a model's confidence to an int on the 0-100 scale (#745, #747).

    - Accepts int, float, ``Decimal``, numpy scalars and plain numeric
      strings such as ``"85"`` or ``"0.85"`` (digits with an optional
      decimal part; no sign, exponent, ``%``, NaN or inf).
    - A non-integer value strictly between 0 and 1 (e.g. 0.85) is a 0-1
      score: scaled by 100 and rounded half up on the decimal string
      (``Decimal(str(v))``), so 0.285 -> 29 and 0.005 -> 1. Values below
      0.005 round to 0. Before #745, ``int(0.85)`` gave 0 and could trigger
      the #696 cloud fallback.
    - Anything else from 0 to 100 is already 0-100 and is truncated as
      before (85.7 -> 85).
    - Exactly 1 / 1.0 / "1" is kept as 1 (1%), not 100: a low reading at
      worst costs one capped cloud fallback with a correct result, while
      reading it as 100% could silently skip the fallback for an answer the
      model rated near zero. Each such value bumps the count-only metric
      ``ai_confidence_exactly_one_total``. 0 stays 0.
    - NaN, inf, out-of-range values, bools and anything else return None
      (the existing "no usable score" path).
    """
    if value is None or isinstance(value, (bool, np.bool_)):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not _NUMERIC_STRING.fullmatch(text):
            return None
        number = Decimal(text)
    elif isinstance(value, Decimal):
        number = value
    elif isinstance(value, (numbers.Real, np.integer, np.floating)):
        as_float = float(value)
        if not math.isfinite(as_float):
            return None
        number = Decimal(str(as_float)) if not isinstance(value, (int, np.integer)) else Decimal(int(value))
    else:
        return None
    if not number.is_finite() or number < 0 or number > 100:
        return None
    if number == 1:
        try:
            from app.core.metrics import ai_confidence_exactly_one_total
            ai_confidence_exactly_one_total.inc()
        except Exception:  # noqa: BLE001 - metrics must never break parsing
            pass
        return 1
    if 0 < number < 1:
        return int((number * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return int(number)


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
        request_timeout_s: Optional[float] = None,
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
        request_timeout_s: Optional[float] = None,
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

                confidence = normalize_confidence(confidence)
                if confidence is not None:
                    if description:
                        return description, confidence, bounding_boxes
                # A structured identification reply always has a description.
                # Keep that sentence even when the model omits a usable score,
                # so the UI never stores the raw JSON object.
                if description:
                    return description, None, bounding_boxes

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug(f"JSON parsing failed for confidence extraction: {e}")

        # Truncated JSON handling + plain text fallback (kept from original)
        truncated_match = re.search(r'\{\s*"description"\s*:\s*"([^"]+)$', response_text, re.DOTALL)
        if truncated_match:
            partial_desc = truncated_match.group(1).strip()
            return partial_desc, None, None

        number = r'(\d{1,3}(?:\.\d+)?)'  # "85" or "0.85" (#747)
        confidence_patterns = [
            r'confidence[:\s]+' + number + r'(?:%|\b)',
            number + r'%?\s*confiden',
            r'confidence\s*(?:score|level|rating)?[:\s]*' + number,
        ]
        for pattern in confidence_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                confidence = normalize_confidence(match.group(1))
                if confidence is not None:
                    return response_text, confidence, None

        return response_text, None, None

    def _with_identification(self, result: AIResult, raw_response: Optional[str]) -> AIResult:
        """Attach structured identification and set confidence from it.

        ``apply_identification`` parses fields, resolves objects_detected, and
        replaces length-heuristic ``confidence`` with
        ``confidence_from_identification`` (honoring ``ai_confidence``).
        """
        from app.services.identification import apply_identification
        return apply_identification(result, raw_response)

    def _extract_objects(self, description: str) -> List[str]:
        """Extract object types from description text.

        Fallback for replies that have no structured identification. Negated
        mentions ("no package", "nothing visible") and background asides are
        not subjects.
        """
        from app.services.identification import (
            BASE_OBJECT_KEYWORDS,
            extract_objects_from_description,
        )
        return extract_objects_from_description(description, keywords=BASE_OBJECT_KEYWORDS)
