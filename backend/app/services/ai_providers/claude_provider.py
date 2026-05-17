"""
Claude Provider (Anthropic) Implementation

Extracted during Phase 3.3.
"""

import time
from typing import List, Optional

import anthropic

from .base import AIProviderBase
from app.services.ai_types import AIResult
from app.services.ocr_service import OCRResult


class ClaudeProvider(AIProviderBase):
    """Anthropic Claude Haiku vision provider"""

    def __init__(self, api_key: str, model: str = None):
        super().__init__(api_key)
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model or "claude-3-haiku-20240307"
        self.cost_per_1k_input_tokens = 0.00025
        self.cost_per_1k_output_tokens = 0.00125

    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None
    ) -> AIResult:
        start_time = time.time()

        try:
            user_prompt = custom_prompt or "Describe what you see in this image in detail for security monitoring."

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_base64
                                }
                            }
                        ]
                    }
                ],
                timeout=15.0
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.content[0].text.strip()

            description, ai_confidence, bounding_boxes = self._parse_confidence_response(raw_response)

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            tokens_used = input_tokens + output_tokens

            cost = (
                (input_tokens / 1000 * self.cost_per_1k_input_tokens) +
                (output_tokens / 1000 * self.cost_per_1k_output_tokens)
            )

            confidence = ai_confidence or self._calculate_confidence(description, tokens_used)
            objects = self._extract_objects(description)

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider="claude",
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True,
                ai_confidence=ai_confidence,
                bounding_boxes=bounding_boxes
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider="claude",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )

    async def generate_multi_image_description(
        self,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None
    ) -> AIResult:
        # Similar multi-image implementation for Claude
        start_time = time.time()

        try:
            user_prompt = custom_prompt or "Analyze these images in sequence and describe what happened."

            content = []
            for img in images_base64:
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": img}
                })
            content.append({"type": "text", "text": user_prompt})

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": content}],
                timeout=20.0
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.content[0].text.strip()

            description, ai_confidence, bounding_boxes = self._parse_confidence_response(raw_response)

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            tokens_used = input_tokens + output_tokens

            cost = ((input_tokens + output_tokens) / 1000) * 0.0008

            confidence = ai_confidence or 75
            objects = self._extract_objects(description)

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider="claude",
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True,
                ai_confidence=ai_confidence
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider="claude",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )

    def _calculate_confidence(self, description: str, tokens_used: int) -> int:
        confidence = 68
        if len(description) > 130:
            confidence += 10
        return min(confidence, 92)
