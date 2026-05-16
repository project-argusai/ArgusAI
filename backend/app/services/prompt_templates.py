"""
Centralized storage for AI prompt templates used by ArgusAI.

This file is the single source of truth for default system prompts.
Per-camera overrides and A/B testing prompts are handled by AIPromptService.

Story: Phase B - Decomposition of ai_service.py (Phase 2.1)
"""

CONFIDENCE_INSTRUCTION = """
For each person, vehicle, package, or animal visible in the frame:
- Describe what they are doing in one clear sentence.
- If a person is carrying something, mention it.
- Note the approximate age group and gender presentation if clearly visible.
- If multiple people are interacting, briefly describe the interaction.
"""

# Enhanced version used when bounding box annotations are enabled
CONFIDENCE_INSTRUCTION_WITH_BOXES = """
For each person, vehicle, package, or animal visible in the frame:
- Describe what they are doing in one clear sentence.
- If a person is carrying something, mention it.
- Note the approximate age group and gender presentation if clearly visible.
- If multiple people are interacting, briefly describe the interaction.
- Use the bounding box coordinates to understand spatial relationships between objects.
"""

MULTI_FRAME_SYSTEM_PROMPT = """You are analyzing a sequence of {num_frames} frames from a security camera video, shown in chronological order.

Your task is to provide a clear, natural language description of what is happening across these frames.

Guidelines:
- Describe the overall event or activity in 1-2 concise sentences.
- Note any movement, direction of travel, or changes in behavior across the frames.
- If people, vehicles, or packages are visible, describe what they are doing and how they relate to each other.
- Mention any notable interactions or unusual behavior.
- Be factual and avoid speculation.

Return only the description. Do not include any preamble or explanation."""


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