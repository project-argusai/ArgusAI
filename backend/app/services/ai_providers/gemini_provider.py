"""
Gemini Provider (Google) Implementation

Extracted during Phase 3.3.
"""

import time
from pathlib import Path
from typing import List, Optional

import google.generativeai as genai
import numpy as np

from .base import AIProviderBase
from app.services.ai_types import AIResult
from app.services.ocr_service import OCRResult


class GeminiProvider(AIProviderBase):
    """Google Gemini Flash vision provider"""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.cost_per_1k_input_tokens = 0.000075
        self.cost_per_1k_output_tokens = 0.0003

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
            user_prompt = custom_prompt or "Describe the security camera image in detail."

            response = await self.model.generate_content_async(
                [
                    user_prompt,
                    {"mime_type": "image/jpeg", "data": image_base64}
                ],
                generation_config={"max_output_tokens": 300}
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.text.strip() if response.text else ""

            description, ai_confidence, bounding_boxes = self._parse_confidence_response(raw_response)

            # Gemini token estimation is rough
            tokens_used = len(raw_response.split()) * 1.3
            cost = tokens_used / 1000 * 0.0002

            confidence = ai_confidence or self._calculate_confidence(description, int(tokens_used))
            objects = self._extract_objects(description)

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider="gemini",
                tokens_used=int(tokens_used),
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
                provider="gemini",
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
        start_time = time.time()

        try:
            user_prompt = custom_prompt or "Analyze this sequence of images and describe the event."

            parts = [user_prompt]
            for img in images_base64:
                parts.append({"mime_type": "image/jpeg", "data": img})

            response = await self.model.generate_content_async(parts)

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.text.strip() if response.text else ""

            description, ai_confidence, _ = self._parse_confidence_response(raw_response)

            tokens_used = len(raw_response.split()) * 1.5
            cost = tokens_used / 1000 * 0.00035

            return AIResult(
                description=description,
                confidence=ai_confidence or 72,
                objects_detected=self._extract_objects(description),
                provider="gemini",
                tokens_used=int(tokens_used),
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider="gemini",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )

    def _calculate_confidence(self, description: str, tokens_used: int) -> int:
        confidence = 65
        if len(description) > 120:
            confidence += 12
        return min(confidence, 90)

    async def describe_video(
        self,
        video_path: "Path",
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
    ) -> AIResult:
        """
        Native video analysis using Gemini (Story P3-4.3).

        For now this extracts frames and falls back to multi-image analysis.
        Full native video upload can be implemented later using Gemini's File API.
        """
        # Basic implementation: extract a few frames and use multi-image path
        try:
            from app.services.frame_extractor import get_frame_extractor

            extractor = get_frame_extractor()
            frames, _ = await extractor.extract_frames(
                video_path=video_path,
                max_frames=5,
                strategy="adaptive"
            )

            if not frames:
                return AIResult(
                    description="Failed to extract frames from video",
                    confidence=0,
                    objects_detected=detected_objects,
                    provider="gemini",
                    tokens_used=0,
                    response_time_ms=0,
                    cost_estimate=0.0,
                    success=False,
                    error="No frames extracted from video clip"
                )

            # Convert to bytes if needed and call multi-image
            frame_bytes = []
            for f in frames:
                if isinstance(f, np.ndarray):
                    import cv2
                    _, buf = cv2.imencode('.jpg', f)
                    frame_bytes.append(buf.tobytes())
                else:
                    frame_bytes.append(f)

            # Reuse the existing multi-image method
            return await self.generate_multi_image_description(
                images_base64=frame_bytes,
                camera_name=camera_name,
                timestamp=timestamp,
                detected_objects=detected_objects,
                custom_prompt=custom_prompt,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result,
            )

        except Exception as e:
            return AIResult(
                description="",
                confidence=0,
                objects_detected=detected_objects,
                provider="gemini",
                tokens_used=0,
                response_time_ms=0,
                cost_estimate=0.0,
                success=False,
                error=f"Video analysis failed: {str(e)}"
            )
