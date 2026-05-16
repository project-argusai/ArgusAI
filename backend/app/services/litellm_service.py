"""
LiteLLMService

Owns the LiteLLM integration path for unified multi-provider AI calls.

Extracted from ai_service.py during Phase 3.6 of the decomposition.
"""

import logging
from typing import Optional, List, Any

from app.services.litellm_provider import LiteLLMProvider, LiteLLMResult
from app.services.ai_types import AIResult

logger = logging.getLogger(__name__)


class LiteLLMService:
    """
    Service responsible for LiteLLM-based vision analysis.

    Handles:
    - Configuration of the LiteLLMProvider
    - describe_images via LiteLLM (multi-frame path)
    - Usage tracking for LiteLLM calls
    """

    def __init__(self):
        self.litellm_provider: Optional[LiteLLMProvider] = None
        self.enabled: bool = False

    def configure(
        self,
        openai_key: Optional[str] = None,
        grok_key: Optional[str] = None,
        claude_key: Optional[str] = None,
        gemini_key: Optional[str] = None,
        claude_model: Optional[str] = None,
        provider_order: Optional[List[str]] = None,
    ) -> bool:
        """Configure the underlying LiteLLMProvider."""
        try:
            from app.services.litellm_provider import configure_litellm_provider

            self.litellm_provider = configure_litellm_provider(
                openai_key=openai_key,
                grok_key=grok_key,
                claude_key=claude_key,
                gemini_key=gemini_key,
                claude_model=claude_model,
                provider_order=provider_order,
            )

            if self.litellm_provider and self.litellm_provider.is_configured():
                self.enabled = True
                logger.info(f"LiteLLMService configured with providers: {self.litellm_provider.get_configured_providers()}")
                return True
            else:
                self.enabled = False
                logger.warning("LiteLLM enabled but no providers successfully configured")
                return False

        except Exception as e:
            logger.error(f"Failed to configure LiteLLMService: {e}")
            self.enabled = False
            self.litellm_provider = None
            return False

    async def describe_images(
        self,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[Any] = None,
    ) -> AIResult:
        """Run multi-image (or single) analysis through LiteLLM."""
        if not self.enabled or not self.litellm_provider:
            raise RuntimeError("LiteLLMService is not enabled/configured")

        try:
            litellm_result: LiteLLMResult = await self.litellm_provider.describe_images(
                images_base64=images_base64,
                camera_name=camera_name,
                timestamp=timestamp,
                detected_objects=detected_objects,
                custom_prompt=custom_prompt,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result,
            )

            # Convert LiteLLMResult → AIResult
            return AIResult(
                description=litellm_result.description,
                confidence=litellm_result.confidence,
                objects_detected=litellm_result.objects_detected,
                provider=litellm_result.provider,
                tokens_used=litellm_result.tokens_used,
                response_time_ms=litellm_result.response_time_ms,
                cost_estimate=litellm_result.cost_estimate,
                success=litellm_result.success,
                error=litellm_result.error,
                ai_confidence=litellm_result.ai_confidence,
                bounding_boxes=litellm_result.bounding_boxes,
            )

        except Exception as e:
            logger.error(f"LiteLLM describe_images failed: {e}")
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider="litellm",
                tokens_used=0,
                response_time_ms=0,
                cost_estimate=0.0,
                success=False,
                error=str(e),
            )

    def is_enabled(self) -> bool:
        return self.enabled and self.litellm_provider is not None

    def get_configured_providers(self) -> List[str]:
        if self.litellm_provider:
            return self.litellm_provider.get_configured_providers()
        return []


# Module-level singleton
litellm_service = LiteLLMService()