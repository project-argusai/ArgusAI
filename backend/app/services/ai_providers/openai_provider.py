"""
OpenAI Provider Implementation

Extracted during Phase 3.3.
"""

import time
from typing import List, Optional, Dict, Any

import openai

from .base import AIProviderBase
from app.services.ai_types import AIResult
from app.services.ocr_service import OCRResult


class OpenAIProvider(AIProviderBase):
    """OpenAI GPT-4o mini vision provider"""

    def __init__(self, api_key: str, model: str = None):
        super().__init__(api_key)
        self.client = openai.AsyncOpenAI(api_key=api_key)
        from app.services.ai_providers.model_resolver import resolve_model
        self.model = resolve_model("openai", api_key, override=model)
        self.cost_per_1k_input_tokens = 0.00015
        self.cost_per_1k_output_tokens = 0.00060

    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
    ) -> AIResult:
        """Generate description using OpenAI GPT-4o mini"""
        start_time = time.time()

        try:
            user_prompt = custom_prompt or "Describe what is happening in the image in detail."

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
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300,
                timeout=10.0
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

            confidence = ai_confidence if ai_confidence else self._calculate_confidence(description, tokens_used)
            objects = self._extract_objects(description)

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider="openai",
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
                provider="openai",
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
        ocr_result: Optional[OCRResult] = None,
    ) -> AIResult:
        """Multi-image support for OpenAI"""
        start_time = time.time()

        try:
            user_prompt = custom_prompt or "Describe what is happening across these images in sequence."

            content = [{"type": "text", "text": user_prompt}]
            for img in images_base64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"}
                })

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": content}
                ],
                max_tokens=500,
                timeout=15.0
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.choices[0].message.content.strip()

            description, ai_confidence, bounding_boxes = self._parse_confidence_response(raw_response)

            tokens_used = response.usage.total_tokens if response.usage else 0
            cost = (tokens_used / 1000) * 0.0003  # rough multi-image cost

            confidence = ai_confidence if ai_confidence else 70
            objects = self._extract_objects(description)

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider="openai",
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
                provider="openai",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )

    def _calculate_confidence(self, description: str, tokens_used: int) -> int:
        """Simple confidence heuristic for OpenAI"""
        confidence = 70
        if len(description) > 150:
            confidence += 10
        if tokens_used > 100:
            confidence += 5
        return min(confidence, 95)
