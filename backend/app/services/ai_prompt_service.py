"""
AIPromptService

Responsible for prompt selection and context enrichment for AI vision analysis.

This service handles:
- Default prompt templates
- Camera-specific prompt overrides
- A/B testing prompt selection
- Building the final prompt with dynamic context (camera name, objects, audio, OCR, etc.)

Story: Phase B - Decomposition of ai_service.py (Phase 2.1)
"""

from typing import Optional, List, Tuple
from dataclasses import dataclass

from app.services.ocr_service import OCRResult
from app.services.prompt_templates import (
    CONFIDENCE_INSTRUCTION,
    CONFIDENCE_INSTRUCTION_WITH_BOXES,
    MULTI_FRAME_SYSTEM_PROMPT,
)


@dataclass
class PromptContext:
    """Context available for building the final prompt."""
    camera_name: Optional[str] = None
    timestamp: Optional[str] = None
    detected_objects: Optional[List[str]] = None
    audio_transcription: Optional[str] = None
    ocr_result: Optional[OCRResult] = None
    annotations_enabled: bool = False
    custom_prompt: Optional[str] = None


class AIPromptService:
    """
    Service responsible for selecting and building prompts for AI vision models.

    This service is intentionally kept separate from the actual vision model calls
    to make prompt logic easier to test and evolve independently.
    """

    def __init__(
        self,
        default_prompt: Optional[str] = None,
        ab_test_prompt: Optional[str] = None,
        ab_test_enabled: bool = False,
        camera_prompts: Optional[dict] = None,
        annotations_enabled: bool = False,
    ):
        """
        Args:
            default_prompt: Default prompt to use when no override exists.
            ab_test_prompt: Prompt used for A/B testing (experiment variant).
            ab_test_enabled: Whether A/B testing is active.
            camera_prompts: Dict mapping camera_id -> custom prompt.
            annotations_enabled: Whether bounding box annotations are enabled.
        """
        self.default_prompt = default_prompt
        self.ab_test_prompt = ab_test_prompt
        self.ab_test_enabled = ab_test_enabled
        self.camera_prompts = camera_prompts or {}
        self.annotations_enabled = annotations_enabled

    def select_and_build_prompt(
        self,
        *,
        camera_id: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        timestamp: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
        analysis_mode: str = "single_image",
    ) -> Tuple[str, Optional[str]]:
        """
        Selects the appropriate base prompt and enriches it with available context.

        Returns:
            Tuple of (final_prompt, prompt_variant)
            - prompt_variant is "control", "experiment", or None
        """
        # 1. Determine base prompt
        base_prompt, variant = self._select_base_prompt(
            camera_id=camera_id,
            custom_prompt=custom_prompt,
            analysis_mode=analysis_mode,
        )

        # 2. Build context string
        context_str = self._build_context_string(
            camera_id=camera_id,
            detected_objects=detected_objects,
            timestamp=timestamp,
            audio_transcription=audio_transcription,
            ocr_result=ocr_result,
        )

        # 3. Combine base prompt + context + confidence instruction
        final_prompt = self._assemble_final_prompt(
            base_prompt=base_prompt,
            context_str=context_str,
            analysis_mode=analysis_mode,
        )

        return final_prompt, variant

    def _select_base_prompt(
        self,
        *,
        camera_id: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        analysis_mode: str = "single_image",
    ) -> Tuple[str, Optional[str]]:
        """Select the base system prompt and determine A/B variant."""

        # Priority 1: Custom prompt passed at request time
        if custom_prompt:
            return custom_prompt.strip(), None

        # Priority 2: Camera-specific override
        if camera_id and camera_id in self.camera_prompts:
            return self.camera_prompts[camera_id].strip(), None

        # Priority 3: A/B testing
        if self.ab_test_enabled and self.ab_test_prompt:
            import random
            is_experiment = random.random() < 0.5
            if is_experiment:
                return self.ab_test_prompt.strip(), "experiment"
            else:
                # Fall through to default for control group
                pass

        # Priority 4: Default prompt based on analysis mode
        if analysis_mode == "multi_frame":
            return MULTI_FRAME_SYSTEM_PROMPT, None

        # Default single-image prompt (can be set via settings)
        if self.default_prompt:
            return self.default_prompt.strip(), None

        # Fallback generic prompt
        return "Describe what is happening in this security camera image.", None

    def _build_context_string(
        self,
        *,
        camera_id: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        timestamp: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
    ) -> str:
        """Builds a natural language context string from available signals."""
        parts = []

        if camera_id:
            parts.append(f"Camera: {camera_id}")

        if timestamp:
            parts.append(f"Time: {timestamp}")

        if detected_objects:
            objects_str = ", ".join(detected_objects)
            parts.append(f"Detected objects: {objects_str}")

        if audio_transcription:
            parts.append(f"Audio detected: \"{audio_transcription}\"")

        if ocr_result and ocr_result.text:
            parts.append(f"Text visible in frame: \"{ocr_result.text}\"")

        return "\n".join(parts) if parts else ""

    def _assemble_final_prompt(
        self,
        *,
        base_prompt: str,
        context_str: str,
        analysis_mode: str,
    ) -> str:
        """Combines the base prompt, context, and confidence instructions."""
        parts = [base_prompt]

        if context_str:
            parts.append("\nAdditional context:\n" + context_str)

        # Add confidence / annotation instructions
        if self.annotations_enabled:
            parts.append("\n" + CONFIDENCE_INSTRUCTION_WITH_BOXES)
        else:
            parts.append("\n" + CONFIDENCE_INSTRUCTION)

        return "\n".join(parts).strip()
