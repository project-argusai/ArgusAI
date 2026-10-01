"""Structured identification fields parsed from a vision-model response.

The human-readable description stays in ``AIResult.description``. These fields
are optional and never replace that sentence. Missing or unusable values become
``unknown`` or ``cannot_tell`` rather than a guess.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.services.ai_types import AIResult

OBJECT_TYPES = ("person", "vehicle", "package", "animal", "unknown", "none")
# Categories that can appear in events.objects_detected. "none" is not one of them.
SUBJECT_TYPES = ("person", "vehicle", "animal", "package")

# Provider keyword lists. Matching is word-boundary and negation-aware; these
# tuples stay the words each provider already treated as a hit.
BASE_OBJECT_KEYWORDS: Dict[str, tuple] = {
    "person": ("person", "people", "man", "woman", "child", "human"),
    "vehicle": ("vehicle", "car", "truck", "van", "motorcycle", "bike"),
    "animal": ("animal", "dog", "cat", "bird", "pet"),
    "package": ("package", "box", "delivery", "parcel"),
}
LITELLM_OBJECT_KEYWORDS: Dict[str, tuple] = {
    "person": (
        "person", "man", "woman", "child", "people", "someone", "individual",
        "pedestrian", "visitor", "delivery", "driver", "worker",
    ),
    "vehicle": (
        "car", "truck", "van", "suv", "vehicle", "automobile", "motorcycle",
        "bike", "bicycle", "scooter", "bus",
    ),
    "package": ("package", "box", "parcel", "delivery", "amazon", "fedex", "ups", "usps"),
    "animal": ("dog", "cat", "bird", "animal", "pet", "squirrel", "rabbit", "deer"),
}

_FUNCTION_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "visible", "seen", "present", "of", "interest", "in", "frame", "there",
    "any", "this", "that", "to", "on", "at", "it", "its", "with", "for",
})
_NEGATION_RE = re.compile(
    r"\b(?:no|not|without|neither|nor|nothing|none|never|cannot|can't)\b|n't\b",
    re.IGNORECASE,
)
_CONTRAST_RE = re.compile(r"\b(?:but|however|although|except|whereas)\b", re.IGNORECASE)
_BACKGROUND_RE = re.compile(
    r"\b(?:in the background|in the distance|background)\b",
    re.IGNORECASE,
)
_EMPTY_SCENE_RE = re.compile(
    r"\bnothing visible\b|\bnothing of interest\b|\bno (?:person|people|vehicles?|animals?|packages?)\b",
    re.IGNORECASE,
)
_KEYWORD_PATTERNS: Dict[str, re.Pattern] = {}
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
lists that person or vehicle and the image matches. A vehicle label is not its
make or model: describe the color, make, and model you can see, and mention the
label only when they agree. Never invent a name. Do not infer motion, identity,
or an object you cannot see. A camera label, a detector type, or a closer crop
is not evidence that a subject is present.

Fields:
- description: the 3 to 6 sentence paragraph. When object_type is "none", say plainly that no person, vehicle, animal, or package is visible, and do not invent one
- object_type: person, vehicle, package, animal, "none" when nothing of interest is there, or unknown
- count: integer count of that subject, 0 when object_type is "none", or null if you cannot tell
- identity: a HISTORICAL CONTEXT name only when the visible person or vehicle matches that label. If a vehicle's visible color, make, or model disagrees with the label, or the label has no stored color, make, or model and you cannot confirm it from the image, use "cannot_tell". Otherwise "unknown" when nothing in context matches. Never copy a stored name into identity when it conflicts with the image
- action: a short action you can actually see, or "cannot_tell"
- direction: toward camera, away, left, right, or "cannot_tell"
- package_or_carrier: "package", UPS, FedEx, USPS, Amazon, DHL, "none", or "cannot_tell"

A package is a parcel, box, padded mailer, or delivery bag that is carried, dropped off or picked up, or lying at the door. Ordinary handheld items are not packages: paper, mail, a phone, an ordinary bag, a cup, a sheet of paper, or a small book. Use object_type "package" only for that same kind of item. Name a carrier (UPS, FedEx, USPS, Amazon, or DHL) only when a delivery-service cue is visible, such as a uniform, a branded vehicle, or a scanner. When you are unsure whether an item is a package, use "none" or "cannot_tell" rather than "package".

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


# Description words that support package_or_carrier == "package".
# "mail" and a plain "bag" are ordinary items; "mailer" and "delivery bag" are not.
_PACKAGE_WORDING = re.compile(
    r"\b(?:packages?|parcels?|boxes|box|mailers?)\b|\bdelivery bags?\b",
    re.IGNORECASE,
)


def _description_supports_package(description: Any) -> bool:
    text = description if isinstance(description, str) else ""
    return _PACKAGE_WORDING.search(text) is not None


def _downgrade_unsupported_package(ident: Dict[str, Any], description: Any) -> None:
    """Drop a package label the description does not support.

    A sheet of paper or a book was stored as package. Keep "package" only when
    the description itself uses package-like wording. Otherwise use "none".
    "cannot_tell" is left as the model sent it.
    """
    if ident.get("package_or_carrier") != "package":
        return
    if _description_supports_package(description):
        return
    ident["package_or_carrier"] = "none"


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


def _from_mapping(data: dict, *, check_package_wording: bool = False) -> Dict[str, Any]:
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
    if check_package_wording:
        # Fresh model JSON only. Stored rows have no description, and re-checking
        # them would clear a package that was already accepted.
        _downgrade_unsupported_package(ident, data.get("description"))
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
    return _from_mapping(data, check_package_wording=True)


def _package_is_subject(ident: Mapping[str, Any]) -> bool:
    """Package counts only when it is the subject or a real carrier/package value.

    ``none`` and ``cannot_tell`` are not a visible or delivered package.
    """
    if ident.get("object_type") == "package":
        return True
    value = str(ident.get("package_or_carrier") or "").strip().lower()
    return bool(value) and value not in {"none", CANNOT_TELL}


def objects_from_identification(ident: Optional[Mapping[str, Any]]) -> Optional[List[str]]:
    """Categories implied by a parsed identification, or None when it has no subject.

    ``object_type`` ``none`` is an empty frame: an empty list, not ``unknown``.
    ``unknown`` (or a missing dict) returns None so the caller can fall back.
    """
    if not isinstance(ident, Mapping):
        return None
    object_type = ident.get("object_type")
    if object_type == "none":
        return []
    if object_type not in SUBJECT_TYPES:
        return None
    objects: List[str] = []
    if object_type != "package":
        objects.append(str(object_type))
    if _package_is_subject(ident):
        objects.append("package")
    return objects


def subjects_from_smart_types(types: Optional[Any]) -> List[str]:
    """Protect smart-detect labels that are real subjects. Motion and ring are not."""
    if isinstance(types, str):
        types = [types]
    found: List[str] = []
    for item in types or []:
        if not isinstance(item, str):
            continue
        key = item.strip().lower()
        if key in SUBJECT_TYPES and key not in found:
            found.append(key)
    return found


def _keyword_pattern(word: str) -> re.Pattern:
    cached = _KEYWORD_PATTERNS.get(word)
    if cached is not None:
        return cached
    if word.endswith("s"):
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
    else:
        pattern = re.compile(rf"\b{re.escape(word)}(?:es|s)?\b", re.IGNORECASE)
    _KEYWORD_PATTERNS[word] = pattern
    return pattern


def _clause_bounds(text: str, pos: int) -> tuple:
    start = 0
    for sep in ".!?;":
        idx = text.rfind(sep, 0, pos)
        if idx >= start:
            start = idx + 1
    for match in _CONTRAST_RE.finditer(text, start, pos):
        start = match.end()
    end = len(text)
    for sep in ".!?;":
        idx = text.find(sep, pos)
        if idx != -1 and idx < end:
            end = idx
    contrast = _CONTRAST_RE.search(text, pos, end)
    if contrast:
        end = contrast.start()
    return start, end


def _is_category_token(token: str, words: set) -> bool:
    if token in words:
        return True
    if len(token) > 2 and token.endswith("es") and token[:-2] in words:
        return True
    if len(token) > 1 and token.endswith("s") and token[:-1] in words:
        return True
    return False


def _negation_reaches(text: str, keyword_start: int, words: set) -> bool:
    """True when a negation in this clause covers the keyword.

    Scope runs from the nearest negation through a coordinated list
    ("no person, vehicle, or package") and stops at a new noun phrase
    ("and a person").
    """
    clause_start, _clause_end = _clause_bounds(text, keyword_start)
    window = text[clause_start:keyword_start]
    negations = list(_NEGATION_RE.finditer(window))
    if not negations:
        return False
    between = window[negations[-1].end():]
    tokens = re.findall(r"[a-zA-Z']+", between.lower())
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _FUNCTION_WORDS:
            index += 1
            continue
        if token in {"and", "or"}:
            nxt = tokens[index + 1] if index + 1 < len(tokens) else None
            if nxt is None or _is_category_token(nxt, words):
                index += 1
                continue
            return False
        if not _is_category_token(token, words):
            return False
        index += 1
    return True


def _incidental_background(text: str, keyword_start: int, keyword_end: int, words: set) -> bool:
    """A car mentioned only as background is not the subject of the event."""
    _clause_start, clause_end = _clause_bounds(text, keyword_start)
    after = text[keyword_end:min(clause_end, keyword_end + 48)]
    background = _BACKGROUND_RE.search(after)
    if background:
        preceding = after[:background.start()]
        earlier = re.findall(r"[a-zA-Z']+", preceding.lower())
        if any(_is_category_token(token, words) for token in earlier):
            return False
        return True
    before = text[max(_clause_start, keyword_start - 36):keyword_start]
    return _BACKGROUND_RE.search(before) is not None


def _keyword_words(keywords: Mapping[str, Sequence[str]]) -> set:
    words = set()
    for group in keywords.values():
        words.update(word.lower() for word in group)
    return words


def extract_objects_from_description(
    description: str,
    keywords: Optional[Mapping[str, Sequence[str]]] = None,
) -> List[str]:
    """Text fallback. Negated mentions and background asides do not count.

    An empty frame ("nothing visible", or every mention negated) is an empty
    list. Text with no subject words stays ``["unknown"]``.
    """
    text = description or ""
    if not text.strip():
        return ["unknown"]
    table = keywords or BASE_OBJECT_KEYWORDS
    words = _keyword_words(table)
    objects: List[str] = []
    saw_negated = False
    for category, group in table.items():
        present = False
        for word in group:
            for match in _keyword_pattern(word).finditer(text):
                if _negation_reaches(text, match.start(), words):
                    saw_negated = True
                    continue
                if _incidental_background(text, match.start(), match.end(), words):
                    continue
                present = True
                break
            if present:
                break
        if present and category not in objects:
            objects.append(category)
    if objects:
        return objects
    if saw_negated or _EMPTY_SCENE_RE.search(text):
        return []
    return ["unknown"]


def resolve_objects_detected(
    *,
    identification: Optional[Mapping[str, Any]] = None,
    description: str = "",
    smart_detection_types: Optional[Any] = None,
    keywords: Optional[Mapping[str, Sequence[str]]] = None,
) -> List[str]:
    """Subjects for a new event.

    Structured identification wins. Protect smart-detect types are the fallback
    when identification has no subject. Negation-aware text is last.
    """
    derived = objects_from_identification(identification)
    if derived is not None:
        return derived
    smart = subjects_from_smart_types(smart_detection_types)
    if smart:
        return smart
    return extract_objects_from_description(description, keywords=keywords)


def apply_identification(
    result: AIResult,
    raw_response: Optional[str],
    smart_detection_types: Optional[Any] = None,
) -> AIResult:
    """Attach parsed fields and replace keyword objects with the resolved list.

    A known subject, including an explicit empty frame, replaces whatever
    substring matching found in the description. Missing identification keeps
    the smart-detect or text fallback.
    """
    ident = parse_identification(raw_response)
    result.identification = ident
    result.objects_detected = resolve_objects_detected(
        identification=ident,
        description=result.description or "",
        smart_detection_types=smart_detection_types,
    )
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
