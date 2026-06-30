"""
Tests for AIPromptService (Phase B - Decomposition)
"""

import pytest
from app.services.ai_prompt_service import AIPromptService
from app.services.ocr_service import OCRResult


class TestAIPromptServiceBasic:
    def test_returns_default_prompt_when_no_overrides(self):
        service = AIPromptService(default_prompt="Describe the scene.")
        prompt, variant = service.select_and_build_prompt()
        assert "Describe the scene." in prompt
        assert variant is None

    def test_camera_specific_prompt_takes_priority(self):
        service = AIPromptService(
            default_prompt="Default prompt",
            camera_prompts={"cam-001": "Custom prompt for front door"}
        )
        prompt, variant = service.select_and_build_prompt(camera_id="cam-001")
        assert "Custom prompt for front door" in prompt
        assert variant is None

    def test_custom_prompt_takes_highest_priority(self):
        service = AIPromptService(default_prompt="Default")
        prompt, variant = service.select_and_build_prompt(
            camera_id="cam-001",
            custom_prompt="Analyze this specific image"
        )
        assert "Analyze this specific image" in prompt

    def test_builds_context_string_with_objects_and_audio(self):
        service = AIPromptService(default_prompt="Base prompt")
        prompt, _ = service.select_and_build_prompt(
            camera_id="Backyard",
            detected_objects=["person", "package"],
            audio_transcription="Someone is at the door"
        )
        assert "Backyard" in prompt
        assert "person, package" in prompt
        assert "Someone is at the door" in prompt

    def test_includes_confidence_instruction(self):
        service = AIPromptService(default_prompt="Base")
        prompt, _ = service.select_and_build_prompt()
        assert "For each person, vehicle, package" in prompt.lower() or "describe what they are doing" in prompt.lower()
