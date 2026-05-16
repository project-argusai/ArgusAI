"""
Grok Provider (xAI) Implementation

Extracted during Phase 3.3.
"""

import time
from typing import List, Optional

import openai

from .base import AIProviderBase
from app.services.ai_types import AIResult
from app.services.ocr_service import OCRResult
from app.services.prompt_templates import MULTI_FRAME_SYSTEM_PROMPT


class GrokProvider(AIProviderBase):
    """xAI Grok vision provider (OpenAI-compatible API)"""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )
        self.model = "grok-2-vision-1212"
        self.cost_per_1k_input_tokens = 0.00010
        self.cost_per_1k_output_tokens = 0.00040

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
        start_time = time.time()

        try:
            if not custom_prompt:
                custom_prompt = getattr(self, 'multi_frame_prompt', None) or MULTI_FRAME_SYSTEM_PROMPT.format(num_images=len(images_base64))

            user_prompt = custom_prompt
            content = [{"type": "text", "text": user_prompt}]
            for img_base64 in images_base64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
                })

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": content}
                ],
                max_tokens=500,
                timeout=30.0
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.choices[0].message.content.strip()

            description, ai_confidence, bounding_boxes = self._parse_confidence_response(raw_response)

            tokens_used = response.usage.total_tokens if response.usage else 0
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            cost = (
                (input_tokens / 1000 * self.cost_per_1k_input_tokens) +
                (output_tokens / 1000 * self.cost_per_1k_output_tokens)
            )

            confidence = self._calculate_confidence(description, tokens_used)
            objects = self._extract_objects(description)

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider="grok",
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
                provider="grok",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )

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
            if not custom_prompt:
                custom_prompt = getattr(self, 'user_prompt_template', None) or "Describe what you see in this security camera image."

            user_prompt = custom_prompt

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                            }
                        ]
                    }
                ],
                max_tokens=300,
                timeout=30.0
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.choices[0].message.content.strip()

            description, ai_confidence, bounding_boxes = self._parse_confidence_response(raw_response)

            tokens_used = response.usage.total_tokens if response.usage else 0
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            cost = (
                (input_tokens / 1000 * self.cost_per_1k_input_tokens) +
                (output_tokens / 1000 * self.cost_per_1k_output_tokens)
            )

            confidence = self._calculate_confidence(description, tokens_used)
            objects = self._extract_objects(description)

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider="grok",
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
                provider="grok",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )

    def _calculate_confidence(self, description: str, tokens_used: int) -> int:
        confidence = 72
        if len(description) > 140:
            confidence += 8
        if tokens_used > 90:
            confidence += 5
        return min(confidence, 93)
