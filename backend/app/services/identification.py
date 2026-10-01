"""Structured identification fields parsed from a vision-model response.

The human-readable description stays in ``AIResult.description``. These fields
are optional and never replace that sentence. Missing or unusable values become
``unknown`` or ``cannot_tell`` rather than a guess.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.services.ai_types import AIResult

OBJECT_TYPES = ("person", "vehicle", "package", "animal", "unknown", "none")
_NONE_OBJECT_ALIASES = {
    "none",
    "no_subject",
    "false_alarm",
    "false_positive",
    "nothing",
    "absent",
    "no_object",
    "empty",
}
CARRIERS = ("ups", "fedex", "usps", "amazon", "dhl")
PACKAGE_VALUES = ("none", "package", "unknown", "cannot_tell", *CARRIERS)
CANNOT_TELL = "cannot_tell"
UNKNOWN = "unknown"

IDENTIFICATION_MARKER = "IDENTIFICATION_FIELDS"

# Output budget for a 3–6 sentence description plus the identification JSON.
# 300–500 tokens truncated that paragraph on the live comparison.
DESCRIPTION_MAX_OUTPUT_TOKENS = 1024

IDENTIFICATION_INSTRUCTION = f"""
{IDENTIFICATION_MARKER}
Reply with one JSON object and no other text. The description field is the only
text shown to people. Write it as 3 to 6 sentences, a short paragraph, with the
detail of a full security-camera description. If an earlier line asked for one
or two sentences, follow this length instead.

Cover what is visible:
- who or what: clothing, apparent age or build, vehicle make, model and color, or animal type
- what they do across the frames, in time order
- where they are in the scene
- direction of travel
- anything carried or delivered
- other activity that matters to the event

Do not inventory static scenery such as furniture, plants, or decorations unless
it matters to the event. Do not read, transcribe, or quote a licence plate or
license plate. Do not guess an identity. Use a name only when HISTORICAL CONTEXT
lists that person or vehicle and the image matches. Never invent a name. Do not
infer motion, identity, or an object you cannot see. A camera label, a detector
type, or a closer crop is not evidence that a subject is present.

Fields:
- description: the 3 to 6 sentence paragraph. When object_type is "none", say plainly that no person, vehicle, animal, or package is visible, and do not invent one
- object_type: person, vehicle, package, animal, "none" when nothing of interest is there, or unknown
- count: integer count of that subject, 0 when object_type is "none", or null if you cannot tell
- identity: the matching name from context, otherwise "unknown". Use "cannot_tell" when a subject is visible but you cannot decide whether it is a known one
- action: a short action you can actually see, or "cannot_tell"
- direction: toward camera, away, left, right, or "cannot_tell"
- package_or_carrier: UPS, FedEx, USPS, Amazon, DHL, "package", or "none". Use "cannot_tell" when unsure

If the frames show no person, vehicle, package, or animal, set object_type to
"none", count to 0, and action and direction to "cannot_tell". The description
must say that plainly and must not invent a subject. If a subject is too small
or too dark to identify, use "unknown" or "cannot_tell" instead of guessing.
"""


def ensure_identification_prompt(prompt: Optional[str]) -> str:
    """Append the identification contract once."""
    text = (prompt or "").strip()
    if IDENTIFICATION_MARKER in text:
        return text
    if not text:
        return IDENTIFICATION_INSTRUCTION.strip()
    return text + "\n" + IDENTIFICATION_INSTRUCTION.strip()


_CROP_NOTE_MARKER = "A closer crop does not mean a subject is present."


def append_subject_crop_note(prompt: str, full_count: int, crop_count: int) -> str:
    """Tell an image-only model which images are closer looks at a region.

    The crop is not evidence that anything is there. A tiny static region can
    be a leaf, a highlight, or an empty patch of frame.
    """
    if crop_count <= 0:
        return prompt
    note = (
        f"The first {full_count} image(s) are full frames in time order. "
        f"The last {crop_count} image(s) are a closer look at one region of the "
        "peak frame. "
        f"{_CROP_NOTE_MARKER} "
        "If that region shows nothing of interest, set object_type to none. "
        "Do not infer motion or identity from the crop. Use the full frames for "
        "the wider scene."
    )
    if _CROP_NOTE_MARKER in (prompt or ""):
        return prompt
    return (prompt or "").rstrip() + "\n\n" + note


def _clip_text(value: Any, *, empty: str, limit: int = 80) -> str:
    if value is None:
        return empty
    text = str(value).strip().replace("\n", " ")
    if not text:
        return empty
    return text[:limit]


def _parse_object_type(value: Any) -> str:
    text = _clip_text(value, empty=UNKNOWN, limit=32).lower().replace(" ", "_").replace("-", "_")
    if text in _NONE_OBJECT_ALIASES:
        return "none"
    if text in OBJECT_TYPES:
        return text
    if text in ("cannot_tell", "cant_tell", "can't_tell", "unsure"):
        return UNKNOWN
    return UNKNOWN


def _parse_count(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip().lower() in {CANNOT_TELL, UNKNOWN, "null", "none"}:
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    if count < 0 or count > 20:
        return None
    return count


def _parse_identity(value: Any) -> str:
    text = _clip_text(value, empty=UNKNOWN)
    lowered = text.lower()
    if lowered in {UNKNOWN, CANNOT_TELL, "unk", "n/a", "none"}:
        return UNKNOWN if lowered != CANNOT_TELL else CANNOT_TELL
    return text


def _parse_package(value: Any) -> str:
    text = _clip_text(value, empty=CANNOT_TELL, limit=40).lower()
    if text in PACKAGE_VALUES:
        return text
    for carrier in CARRIERS:
        if carrier in text:
            return carrier
    if "package" in text or "parcel" in text or "box" in text:
        return "package"
    if text in {"no", "false", "n/a"}:
        return "none"
    return CANNOT_TELL


def empty_identification() -> Dict[str, Any]:
    return {
        "object_type": UNKNOWN,
        "count": None,
        "identity": UNKNOWN,
        "action": CANNOT_TELL,
        "direction": CANNOT_TELL,
        "package_or_carrier": CANNOT_TELL,
    }


def _from_mapping(data: dict) -> Dict[str, Any]:
    ident = empty_identification()
    ident["object_type"] = _parse_object_type(data.get("object_type"))
    ident["count"] = _parse_count(data.get("count"))
    ident["identity"] = _parse_identity(data.get("identity"))
    ident["action"] = _clip_text(data.get("action"), empty=CANNOT_TELL).lower()
    if ident["action"] in {"unknown", "n/a", "none"}:
        ident["action"] = CANNOT_TELL
    ident["direction"] = _clip_text(data.get("direction"), empty=CANNOT_TELL).lower()
    if ident["direction"] in {"unknown", "n/a", "none"}:
        ident["direction"] = CANNOT_TELL
    ident["package_or_carrier"] = _parse_package(data.get("package_or_carrier"))
    if ident["object_type"] == "none":
        # A false alarm is not a counted subject and has no visible motion.
        ident["count"] = 0
        ident["identity"] = UNKNOWN
        ident["action"] = CANNOT_TELL
        ident["direction"] = CANNOT_TELL
        ident["package_or_carrier"] = "none"
    return ident


def parse_identification(response_text: Optional[str]) -> Dict[str, Any]:
    """Parse structured fields. Unparseable text yields the unknown/cannot-tell set."""
    ident = empty_identification()
    if not response_text:
        return ident
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start == -1 or end <= start:
        return ident
    try:
        data = json.loads(response_text[start:end + 1])
    except (json.JSONDecodeError, ValueError, TypeError):
        return ident
    if not isinstance(data, dict):
        return ident
    return _from_mapping(data)


def apply_identification(result: AIResult, raw_response: Optional[str]) -> AIResult:
    """Attach parsed fields. A known object type fills in keyword extraction."""
    ident = parse_identification(raw_response)
    result.identification = ident
    object_type = ident.get("object_type")
    if object_type in {"person", "vehicle", "package", "animal"}:
        current = [o for o in (result.objects_detected or []) if o and o != UNKNOWN]
        if object_type not in current:
            current.insert(0, object_type)
        result.objects_detected = current or [object_type]
    return result


def dumps_identification(value: Any) -> Optional[str]:
    """Serialize a parsed identification dict. Anything else is omitted.

    Mock results used in tests expose every attribute, so a truthiness check
    would try to encode a non-dict and fail the store.
    """
    if not isinstance(value, dict):
        return None
    return json.dumps(value)


def loads_identification(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Read a stored identification JSON value. Malformed text is None."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return _from_mapping(data)


def carrier_from_identification(ident: Optional[Dict[str, Any]]) -> Optional[str]:
    if not ident:
        return None
    value = str(ident.get("package_or_carrier") or "").lower()
    if value in CARRIERS:
        return value
    return None
