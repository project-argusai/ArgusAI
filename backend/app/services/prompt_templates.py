"""
Centralized storage for AI prompt templates used by ArgusAI.

This file is the single source of truth for default system prompts.
Per-camera overrides and A/B testing prompts are handled by AIPromptService.

Story: Phase B - Decomposition of ai_service.py (Phase 2.1)
"""

NAMING_AND_CARRIER_INSTRUCTION = """
When writing the description:
- If HISTORICAL CONTEXT names a person or vehicle and the image matches, use that name. Never invent names that are not listed there.
- If a known vehicle is listed, use its color, make, and model (for example "red BMW X3") instead of "a vehicle" or "a car".
- If a delivery uniform or logo is visible, name the carrier (UPS, FedEx, USPS, Amazon, or DHL).
- State the local time and camera/location naturally (for example "at 9:05 PM at the front door, Isaac arrives in his red BMW X3"). The identification description is a short paragraph, not a single sentence.
"""

CONFIDENCE_INSTRUCTION = """
For each person, vehicle, package, or animal visible in the frame:
- Describe what they are doing in one clear sentence.
- If a person is carrying something, mention it.
- Note the approximate age group and gender presentation if clearly visible.
- If multiple people are interacting, briefly describe the interaction.
""" + NAMING_AND_CARRIER_INSTRUCTION

# Enhanced version used when bounding box annotations are enabled
CONFIDENCE_INSTRUCTION_WITH_BOXES = """
For each person, vehicle, package, or animal visible in the frame:
- Describe what they are doing in one clear sentence.
- If a person is carrying something, mention it.
- Note the approximate age group and gender presentation if clearly visible.
- If multiple people are interacting, briefly describe the interaction.
- Use the bounding box coordinates to understand spatial relationships between objects.
""" + NAMING_AND_CARRIER_INSTRUCTION

MULTI_FRAME_SYSTEM_PROMPT = """You are analyzing a sequence of {num_frames} frames from a security camera video, shown in chronological order.

Your task is to provide a clear, natural language description of what is happening across these frames.

Guidelines:
- Describe what happens across the frames in time order. The identification description is 3 to 6 sentences.
- Note movement, direction of travel, and changes in behavior across the frames.
- If people, vehicles, or packages are visible, describe what they are doing and how they relate to each other.
- Mention any notable interactions or unusual behavior.
- Be factual and avoid speculation.
- Some images may be a closer look at one region of a frame. A crop does not mean a subject is present. If the crop shows nothing of interest, say so.

The reply must be the identification JSON. Its description field is the human-readable summary.
""" + NAMING_AND_CARRIER_INSTRUCTION


# Story P15-5.1: Bounding box instruction for AI annotations
BOUNDING_BOX_INSTRUCTION = """

After your description, include bounding boxes for each detected object.

For each person, vehicle, package, or animal visible in the frame:
1. Draw an imaginary box around the object
2. Estimate normalized coordinates (0.0 to 1.0) where:
   - x = left edge position (0.0 = left side, 1.0 = right side)
   - y = top edge position (0.0 = top, 1.0 = bottom)
   - width = box width as fraction of image width
   - height = box height as fraction of image height
3. Assign entity_type: "person", "vehicle", "package", "animal", or "other"
4. Rate confidence 0.0 to 1.0 for that specific detection
5. Describe the action being performed by that entity

Return the description in natural language, followed by the bounding box data in this format:
[entity_type: "person", x: 0.25, y: 0.40, width: 0.15, height: 0.35, confidence: 0.92, action: "walking toward door"]

Respond in this exact JSON format:
{"description": "your detailed description here", "confidence": 85, "bounding_boxes": [...] }"""


def _append_identification_schema(prompt: str) -> str:
    from app.services.identification import IDENTIFICATION_INSTRUCTION, IDENTIFICATION_MARKER
    if IDENTIFICATION_MARKER in prompt:
        return prompt
    return prompt.rstrip() + "\n" + IDENTIFICATION_INSTRUCTION


MULTI_FRAME_SYSTEM_PROMPT = _append_identification_schema(MULTI_FRAME_SYSTEM_PROMPT)