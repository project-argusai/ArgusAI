"""
AI Vision Service for generating natural language descriptions from camera frames.

Supports multiple AI providers with automatic fallback:
- Primary: OpenAI GPT-4o mini (vision capable)
- Secondary: xAI Grok (vision capable, OpenAI-compatible API)
- Tertiary: Anthropic Claude 3 Haiku
- Quaternary: Google Gemini Flash

Features:
- Multi-provider fallback for reliability
- Image preprocessing (resize, JPEG conversion, base64 encoding)
- Encrypted API key storage
- Usage tracking and cost monitoring
- Exponential backoff for rate limits
- Performance logging (<5s SLA)
"""

import asyncio
import base64
import io
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

import numpy as np
from PIL import Image
import openai
import anthropic
import google.generativeai as genai
from sqlalchemy.orm import Session

from app.utils.encryption import decrypt_password
from app.models.system_setting import SystemSetting
from app.models.ai_usage import AIUsage

logger = logging.getLogger(__name__)


# Multi-frame analysis system prompt (Story P3-2.4)
# Optimized for temporal narrative descriptions of video sequences
MULTI_FRAME_SYSTEM_PROMPT = """You are analyzing a sequence of {num_frames} frames from a security camera video, shown in chronological order.

Your task is to describe WHAT HAPPENED - focus on the narrative and action over time:

1. **Actions and movements** - Use action verbs: walked, arrived, departed, placed, picked up, approached, entered, exited, turned, stopped, ran, carried, delivered, rang, opened, closed
2. **Direction of travel** - entering frame, exiting frame, left to right, right to left, approaching camera, moving away, circling, pacing
3. **Sequence of events** - First... then... next... finally... Describe the progression
4. **Who or what is present** - People (appearance, clothing, items carried), vehicles, animals, packages, objects

IMPORTANT - Use dynamic descriptions, NOT static ones:
- GOOD: "A delivery person approached the front door, placed a package on the step, then departed walking left toward the street."
- BAD: "A person is visible near the front door. There is a package on the ground."
- GOOD: "A car pulled into the driveway and parked. The driver exited and walked toward the house."
- BAD: "A car is parked in the driveway. A person is standing nearby."

Be specific about the narrative - this is video showing motion over time, not a static photograph. Describe the complete sequence of what happened."""


class AIProvider(Enum):
    """Supported AI vision providers"""
    OPENAI = "openai"
    GROK = "grok"
    CLAUDE = "claude"
    GEMINI = "gemini"


@dataclass
class AIResult:
    """Result from AI description generation"""
    description: str
    confidence: int  # 0-100
    objects_detected: List[str]  # person, vehicle, animal, package, unknown
    provider: str  # Which provider was used
    tokens_used: int
    response_time_ms: int
    cost_estimate: float  # USD
    success: bool
    error: Optional[str] = None


class AIProviderBase(ABC):
    """Base class for AI vision providers"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.system_prompt = (
            "You are describing video surveillance events for home security and accessibility. "
            "Provide detailed, accurate descriptions."
        )
        self.user_prompt_template = (
            "Describe what you see in this image. Include: "
            "WHO (people, their appearance, clothing), "
            "WHAT (objects, vehicles, packages), "
            "WHERE (location in frame), "
            "and ACTIONS (what is happening). "
            "Be specific and detailed."
        )

    @abstractmethod
    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description from base64-encoded image

        Args:
            image_base64: Base64-encoded JPEG image
            camera_name: Name of the camera for context
            timestamp: ISO 8601 timestamp
            detected_objects: List of detected object types
            custom_prompt: Optional custom prompt to override default (Story P2-4.1)
        """
        pass

    @abstractmethod
    async def generate_multi_image_description(
        self,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description from multiple base64-encoded images (Story P3-2.3)

        Analyzes a sequence of frames together and returns a single combined description
        covering all frames. Useful for multi-frame analysis of motion clips.

        Args:
            images_base64: List of base64-encoded JPEG images (3-5 frames typical)
            camera_name: Name of the camera for context
            timestamp: ISO 8601 timestamp of the first frame
            detected_objects: List of detected object types
            custom_prompt: Optional custom prompt to override default

        Returns:
            AIResult with combined description covering all frames
        """
        pass

    def _build_user_prompt(
        self,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None
    ) -> str:
        """Build user prompt with context

        Args:
            camera_name: Name of the camera
            timestamp: ISO 8601 timestamp
            detected_objects: List of detected object types
            custom_prompt: Optional custom prompt to override the base description instruction
                          (from Settings → AI Provider Configuration → Description prompt,
                           or from Story P2-4.1 doorbell ring events)
        """
        # Build camera context
        context = f"\nContext: Camera '{camera_name}' at {timestamp}."
        if detected_objects:
            context += f" Motion detected: {', '.join(detected_objects)}."

        # Use custom prompt if provided (from Settings description_prompt or doorbell ring)
        # Otherwise use the default user_prompt_template
        base_prompt = custom_prompt if custom_prompt else self.user_prompt_template

        return base_prompt + context

    def _build_multi_image_prompt(
        self,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        num_images: int,
        custom_prompt: Optional[str] = None
    ) -> str:
        """Build user prompt for multi-image analysis (Story P3-2.3, P3-2.4)

        Uses MULTI_FRAME_SYSTEM_PROMPT optimized for temporal narrative descriptions.
        Custom prompts are APPENDED after system instructions, not replacing them,
        to ensure temporal context is always included.

        Args:
            camera_name: Name of the camera
            timestamp: ISO 8601 timestamp of first frame
            detected_objects: List of detected object types
            num_images: Number of images being analyzed
            custom_prompt: Optional custom prompt to APPEND after system instructions
                          (from Settings → multi_frame_description_prompt or per-camera config)
        """
        # Build camera context suffix
        context = f"\n\nContext: Camera '{camera_name}' at {timestamp}."
        if detected_objects:
            context += f" Motion detected: {', '.join(detected_objects)}."

        # Use optimized multi-frame system prompt with frame count (Story P3-2.4)
        base_prompt = MULTI_FRAME_SYSTEM_PROMPT.format(num_frames=num_images)

        # APPEND custom prompt after system instructions (not replace)
        # This ensures temporal context is always preserved (AC4)
        if custom_prompt:
            base_prompt += f"\n\nAdditional instructions: {custom_prompt}"

        return base_prompt + context

    def _extract_objects(self, description: str) -> List[str]:
        """Extract object types from description text"""
        objects = []
        description_lower = description.lower()

        # Check for each object type
        if any(word in description_lower for word in ['person', 'people', 'man', 'woman', 'child', 'human']):
            objects.append('person')
        if any(word in description_lower for word in ['vehicle', 'car', 'truck', 'van', 'motorcycle', 'bike']):
            objects.append('vehicle')
        if any(word in description_lower for word in ['animal', 'dog', 'cat', 'bird', 'pet']):
            objects.append('animal')
        if any(word in description_lower for word in ['package', 'box', 'delivery', 'parcel']):
            objects.append('package')

        # Default to unknown if nothing detected
        if not objects:
            objects.append('unknown')

        return objects


class OpenAIProvider(AIProviderBase):
    """OpenAI GPT-4o mini vision provider"""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"
        self.cost_per_1k_input_tokens = 0.00015  # Approximate
        self.cost_per_1k_output_tokens = 0.00060

    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description using OpenAI GPT-4o mini"""
        start_time = time.time()

        try:
            user_prompt = self._build_user_prompt(camera_name, timestamp, detected_objects, custom_prompt)

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
            description = response.choices[0].message.content.strip()

            # Extract usage stats
            tokens_used = response.usage.total_tokens if response.usage else 0
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            # Calculate cost
            cost = (
                (input_tokens / 1000 * self.cost_per_1k_input_tokens) +
                (output_tokens / 1000 * self.cost_per_1k_output_tokens)
            )

            # Generate confidence score (OpenAI doesn't provide one, use heuristic)
            confidence = self._calculate_confidence(description, tokens_used)

            # Extract objects from description
            objects = self._extract_objects(description)

            logger.info(
                "AI API call successful",
                extra={
                    "event_type": "ai_api_success",
                    "provider": "openai",
                    "model": self.model,
                    "response_time_ms": elapsed_ms,
                    "tokens_used": tokens_used,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost,
                    "confidence": confidence,
                }
            )

            # Record metrics
            try:
                from app.core.metrics import record_ai_api_call
                record_ai_api_call(
                    provider="openai",
                    model=self.model,
                    status="success",
                    duration_seconds=elapsed_ms / 1000,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost
                )
            except ImportError:
                pass

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.OPENAI.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True
            )

        except Exception as e:
            # Catch all exceptions (openai.APIError, network errors, etc.)
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "AI API call failed",
                extra={
                    "event_type": "ai_api_error",
                    "provider": "openai",
                    "model": self.model,
                    "response_time_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )

            # Record error metrics
            try:
                from app.core.metrics import record_ai_api_call
                record_ai_api_call(
                    provider="openai",
                    model=self.model,
                    status="error",
                    duration_seconds=elapsed_ms / 1000
                )
            except ImportError:
                pass

            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.OPENAI.value,
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )

    def _calculate_confidence(self, description: str, tokens_used: int) -> int:
        """Calculate confidence score based on response quality"""
        confidence = 70  # Base confidence

        # Longer descriptions are more confident
        if tokens_used > 100:
            confidence += 10
        elif tokens_used > 50:
            confidence += 5

        # Contains specific details
        if any(word in description.lower() for word in ['wearing', 'holding', 'standing', 'walking']):
            confidence += 10

        # Cap at 100
        return min(confidence, 100)

    async def generate_multi_image_description(
        self,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description from multiple images using OpenAI GPT-4o mini (Story P3-2.3 AC2)"""
        start_time = time.time()

        try:
            user_prompt = self._build_multi_image_prompt(
                camera_name, timestamp, detected_objects, len(images_base64), custom_prompt
            )

            # Build content array with text prompt and multiple images
            content = [{"type": "text", "text": user_prompt}]
            for img_base64 in images_base64:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_base64}"
                    }
                })

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": content}
                ],
                max_tokens=500,  # More tokens for multi-image
                timeout=15.0  # Longer timeout for multi-image
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            description = response.choices[0].message.content.strip()

            # Extract usage stats
            tokens_used = response.usage.total_tokens if response.usage else 0
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            # Calculate cost
            cost = (
                (input_tokens / 1000 * self.cost_per_1k_input_tokens) +
                (output_tokens / 1000 * self.cost_per_1k_output_tokens)
            )

            confidence = self._calculate_confidence(description, tokens_used)
            objects = self._extract_objects(description)

            logger.info(
                "OpenAI multi-image API call successful",
                extra={
                    "event_type": "ai_api_multi_image_success",
                    "provider": "openai",
                    "model": self.model,
                    "num_images": len(images_base64),
                    "response_time_ms": elapsed_ms,
                    "tokens_used": tokens_used,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost,
                    "confidence": confidence,
                }
            )

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.OPENAI.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "OpenAI multi-image API call failed",
                extra={
                    "event_type": "ai_api_multi_image_error",
                    "provider": "openai",
                    "model": self.model,
                    "num_images": len(images_base64),
                    "response_time_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.OPENAI.value,
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )


class ClaudeProvider(AIProviderBase):
    """Anthropic Claude 3 Haiku vision provider"""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = "claude-3-haiku-20240307"
        self.cost_per_1k_input_tokens = 0.00025
        self.cost_per_1k_output_tokens = 0.00125

    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description using Claude 3 Haiku"""
        start_time = time.time()

        try:
            user_prompt = self._build_user_prompt(camera_name, timestamp, detected_objects, custom_prompt)

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": f"{self.system_prompt}\n\n{user_prompt}"
                            }
                        ]
                    }
                ],
                timeout=10.0
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            description = response.content[0].text.strip()

            # Extract usage stats
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            tokens_used = input_tokens + output_tokens

            # Calculate cost
            cost = (
                (input_tokens / 1000 * self.cost_per_1k_input_tokens) +
                (output_tokens / 1000 * self.cost_per_1k_output_tokens)
            )

            confidence = 75  # Claude is generally reliable
            objects = self._extract_objects(description)

            logger.info(
                f"Claude success: {elapsed_ms}ms, {tokens_used} tokens, ${cost:.6f}, "
                f"confidence={confidence}"
            )

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.CLAUDE.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True
            )

        except Exception as e:
            # Catch all exceptions (anthropic.APIError, network errors, etc.)
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Claude API error after {elapsed_ms}ms: {e}")
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.CLAUDE.value,
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
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description from multiple images using Claude 3 Haiku (Story P3-2.3 AC3)"""
        start_time = time.time()

        try:
            user_prompt = self._build_multi_image_prompt(
                camera_name, timestamp, detected_objects, len(images_base64), custom_prompt
            )

            # Build content array with multiple image blocks followed by text
            content = []
            for img_base64 in images_base64:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img_base64
                    }
                })
            content.append({
                "type": "text",
                "text": f"{self.system_prompt}\n\n{user_prompt}"
            })

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=500,  # More tokens for multi-image
                messages=[{"role": "user", "content": content}],
                timeout=15.0  # Longer timeout for multi-image
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            description = response.content[0].text.strip()

            # Extract usage stats
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            tokens_used = input_tokens + output_tokens

            # Calculate cost
            cost = (
                (input_tokens / 1000 * self.cost_per_1k_input_tokens) +
                (output_tokens / 1000 * self.cost_per_1k_output_tokens)
            )

            confidence = 75
            objects = self._extract_objects(description)

            logger.info(
                "Claude multi-image API call successful",
                extra={
                    "event_type": "ai_api_multi_image_success",
                    "provider": "claude",
                    "model": self.model,
                    "num_images": len(images_base64),
                    "response_time_ms": elapsed_ms,
                    "tokens_used": tokens_used,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost,
                    "confidence": confidence,
                }
            )

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.CLAUDE.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Claude multi-image API call failed",
                extra={
                    "event_type": "ai_api_multi_image_error",
                    "provider": "claude",
                    "model": self.model,
                    "num_images": len(images_base64),
                    "response_time_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.CLAUDE.value,
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )


class GeminiProvider(AIProviderBase):
    """Google Gemini Flash vision provider"""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.cost_per_1k_tokens = 0.0001  # Approximate (free tier available)

    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description using Gemini Flash"""
        start_time = time.time()

        try:
            user_prompt = self._build_user_prompt(camera_name, timestamp, detected_objects, custom_prompt)
            full_prompt = f"{self.system_prompt}\n\n{user_prompt}"

            # Decode base64 to bytes for Gemini
            image_bytes = base64.b64decode(image_base64)
            image_part = {"mime_type": "image/jpeg", "data": image_bytes}

            response = await self.model.generate_content_async(
                [full_prompt, image_part],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=300,
                    temperature=0.4
                )
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            description = response.text.strip()

            # Gemini doesn't provide detailed usage stats in all cases
            tokens_used = 150  # Estimate
            cost = tokens_used / 1000 * self.cost_per_1k_tokens

            confidence = 70
            objects = self._extract_objects(description)

            logger.info(
                f"Gemini success: {elapsed_ms}ms, ~{tokens_used} tokens, ${cost:.6f}, "
                f"confidence={confidence}"
            )

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.GEMINI.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Gemini API error after {elapsed_ms}ms: {e}")
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.GEMINI.value,
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
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description from multiple images using Gemini Flash (Story P3-2.3 AC4)"""
        start_time = time.time()

        try:
            user_prompt = self._build_multi_image_prompt(
                camera_name, timestamp, detected_objects, len(images_base64), custom_prompt
            )
            full_prompt = f"{self.system_prompt}\n\n{user_prompt}"

            # Build parts array with prompt and multiple images
            parts = [full_prompt]
            for img_base64 in images_base64:
                # Decode base64 to bytes for Gemini
                image_bytes = base64.b64decode(img_base64)
                parts.append({"mime_type": "image/jpeg", "data": image_bytes})

            response = await self.model.generate_content_async(
                parts,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=500,  # More tokens for multi-image
                    temperature=0.4
                )
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            description = response.text.strip()

            # Gemini doesn't provide detailed usage stats in all cases
            # Estimate based on number of images (more images = more tokens)
            tokens_used = 150 + (len(images_base64) * 50)  # Estimate
            cost = tokens_used / 1000 * self.cost_per_1k_tokens

            confidence = 70
            objects = self._extract_objects(description)

            logger.info(
                "Gemini multi-image API call successful",
                extra={
                    "event_type": "ai_api_multi_image_success",
                    "provider": "gemini",
                    "model": "gemini-1.5-flash",
                    "num_images": len(images_base64),
                    "response_time_ms": elapsed_ms,
                    "tokens_used": tokens_used,
                    "cost_usd": cost,
                    "confidence": confidence,
                }
            )

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.GEMINI.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Gemini multi-image API call failed",
                extra={
                    "event_type": "ai_api_multi_image_error",
                    "provider": "gemini",
                    "model": "gemini-1.5-flash",
                    "num_images": len(images_base64),
                    "response_time_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.GEMINI.value,
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )


class GrokProvider(AIProviderBase):
    """xAI Grok vision provider (OpenAI-compatible API)"""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        # Use OpenAI client with xAI base URL
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )
        self.model = "grok-2-vision-1212"
        self.cost_per_1k_input_tokens = 0.00010  # Approximate (similar to GPT-4o mini)
        self.cost_per_1k_output_tokens = 0.00040

    async def generate_multi_image_description(
        self,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description from multiple images using Grok Vision (Story P3-2.3 AC5)

        Uses OpenAI-compatible format with multiple image_url blocks.
        """
        start_time = time.time()

        try:
            user_prompt = self._build_multi_image_prompt(
                camera_name, timestamp, detected_objects, len(images_base64), custom_prompt
            )

            # Build content array with text prompt and multiple images (OpenAI-compatible format)
            content = [{"type": "text", "text": user_prompt}]
            for img_base64 in images_base64:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_base64}"
                    }
                })

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": content}
                ],
                max_tokens=500,  # More tokens for multi-image
                timeout=30.0  # Longer timeout for Grok multi-image
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            description = response.choices[0].message.content.strip()

            # Extract usage stats
            tokens_used = response.usage.total_tokens if response.usage else 0
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            # Calculate cost
            cost = (
                (input_tokens / 1000 * self.cost_per_1k_input_tokens) +
                (output_tokens / 1000 * self.cost_per_1k_output_tokens)
            )

            confidence = self._calculate_confidence(description, tokens_used)
            objects = self._extract_objects(description)

            logger.info(
                "Grok multi-image API call successful",
                extra={
                    "event_type": "ai_api_multi_image_success",
                    "provider": "grok",
                    "model": self.model,
                    "num_images": len(images_base64),
                    "response_time_ms": elapsed_ms,
                    "tokens_used": tokens_used,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost,
                    "confidence": confidence,
                }
            )

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.GROK.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Grok multi-image API call failed",
                extra={
                    "event_type": "ai_api_multi_image_error",
                    "provider": "grok",
                    "model": self.model,
                    "num_images": len(images_base64),
                    "response_time_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.GROK.value,
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
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """Generate description using xAI Grok Vision API"""
        start_time = time.time()

        try:
            user_prompt = self._build_user_prompt(camera_name, timestamp, detected_objects, custom_prompt)

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
                timeout=30.0  # 30-second timeout for Grok
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            description = response.choices[0].message.content.strip()

            # Extract usage stats
            tokens_used = response.usage.total_tokens if response.usage else 0
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            # Calculate cost
            cost = (
                (input_tokens / 1000 * self.cost_per_1k_input_tokens) +
                (output_tokens / 1000 * self.cost_per_1k_output_tokens)
            )

            # Generate confidence score
            confidence = self._calculate_confidence(description, tokens_used)

            # Extract objects from description
            objects = self._extract_objects(description)

            logger.info(
                "Grok API call successful",
                extra={
                    "event_type": "ai_api_success",
                    "provider": "grok",
                    "model": self.model,
                    "response_time_ms": elapsed_ms,
                    "tokens_used": tokens_used,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost,
                    "confidence": confidence,
                }
            )

            # Record metrics
            try:
                from app.core.metrics import record_ai_api_call
                record_ai_api_call(
                    provider="grok",
                    model=self.model,
                    status="success",
                    duration_seconds=elapsed_ms / 1000,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost
                )
            except ImportError:
                pass

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.GROK.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Grok API call failed",
                extra={
                    "event_type": "ai_api_error",
                    "provider": "grok",
                    "model": self.model,
                    "response_time_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )

            # Record error metrics
            try:
                from app.core.metrics import record_ai_api_call
                record_ai_api_call(
                    provider="grok",
                    model=self.model,
                    status="error",
                    duration_seconds=elapsed_ms / 1000
                )
            except ImportError:
                pass

            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.GROK.value,
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=str(e)
            )

    def _calculate_confidence(self, description: str, tokens_used: int) -> int:
        """Calculate confidence score based on response quality"""
        confidence = 70  # Base confidence

        # Longer descriptions are more confident
        if tokens_used > 100:
            confidence += 10
        elif tokens_used > 50:
            confidence += 5

        # Contains specific details
        if any(word in description.lower() for word in ['wearing', 'holding', 'standing', 'walking']):
            confidence += 10

        # Cap at 100
        return min(confidence, 100)


class AIService:
    """Main AI service with multi-provider fallback and usage tracking"""

    def __init__(self):
        self.providers: Dict[AIProvider, Optional[AIProviderBase]] = {}
        self.db: Optional[Session] = None  # Database session for usage tracking
        self.description_prompt: Optional[str] = None  # Custom description prompt from settings

    async def load_api_keys_from_db(self, db: Session):
        """
        Load and decrypt API keys from system_settings table.

        Loads encrypted API keys from database and configures all available providers.
        Keys are stored with 'encrypted:' prefix and decrypted using Fernet encryption.

        Args:
            db: SQLAlchemy database session

        Expected database keys:
            - ai_api_key_openai: encrypted:... (OpenAI GPT-4o mini)
            - ai_api_key_grok: encrypted:... (xAI Grok)
            - ai_api_key_claude: encrypted:... (Anthropic Claude 3 Haiku)
            - ai_api_key_gemini: encrypted:... (Google Gemini Flash)
        """
        logger.info("Loading AI provider API keys from database...")

        try:
            # Query all AI API key settings and description prompt
            settings = db.query(SystemSetting).filter(
                SystemSetting.key.in_([
                    'ai_api_key_openai',
                    'ai_api_key_grok',
                    'ai_api_key_claude',
                    'ai_api_key_gemini',
                    'settings_description_prompt'  # Custom description prompt from AI Provider Configuration
                ])
            ).all()

            # Build key mapping
            keys = {setting.key: setting.value for setting in settings}

            # Load custom description prompt if configured
            if 'settings_description_prompt' in keys and keys['settings_description_prompt']:
                self.description_prompt = keys['settings_description_prompt']
                logger.info(f"Custom description prompt loaded: '{self.description_prompt[:50]}...'")
            else:
                self.description_prompt = None
                logger.info("Using default description prompt")

            # Decrypt and configure each provider
            openai_key = None
            grok_key = None
            claude_key = None
            gemini_key = None

            if 'ai_api_key_openai' in keys:
                openai_key = decrypt_password(keys['ai_api_key_openai'])
                logger.info("OpenAI API key loaded from database")

            if 'ai_api_key_grok' in keys:
                grok_key = decrypt_password(keys['ai_api_key_grok'])
                logger.info("Grok API key loaded from database")

            if 'ai_api_key_claude' in keys:
                claude_key = decrypt_password(keys['ai_api_key_claude'])
                logger.info("Claude API key loaded from database")

            if 'ai_api_key_gemini' in keys:
                gemini_key = decrypt_password(keys['ai_api_key_gemini'])
                logger.info("Gemini API key loaded from database")

            # Configure providers with decrypted keys
            self.configure_providers(
                openai_key=openai_key,
                grok_key=grok_key,
                claude_key=claude_key,
                gemini_key=gemini_key
            )

            logger.info(f"AI providers configured: {len(self.providers)} providers loaded")

            # Store database session for usage tracking
            self.db = db

        except Exception as e:
            logger.error(f"Failed to load API keys from database: {e}")
            raise ValueError(f"Failed to load AI provider configuration: {e}")

    def configure_providers(
        self,
        openai_key: Optional[str] = None,
        grok_key: Optional[str] = None,
        claude_key: Optional[str] = None,
        gemini_key: Optional[str] = None
    ):
        """
        Configure AI providers with API keys.

        Can be called directly with plaintext keys (for testing) or via load_api_keys_from_db()
        for production use with encrypted keys from database.

        Args:
            openai_key: OpenAI API key (plaintext)
            grok_key: xAI Grok API key (plaintext)
            claude_key: Anthropic API key (plaintext)
            gemini_key: Google API key (plaintext)
        """
        if openai_key:
            self.providers[AIProvider.OPENAI] = OpenAIProvider(openai_key)
            logger.info("OpenAI provider configured")

        if grok_key:
            self.providers[AIProvider.GROK] = GrokProvider(grok_key)
            logger.info("Grok provider configured")

        if claude_key:
            self.providers[AIProvider.CLAUDE] = ClaudeProvider(claude_key)
            logger.info("Claude provider configured")

        if gemini_key:
            self.providers[AIProvider.GEMINI] = GeminiProvider(gemini_key)
            logger.info("Gemini provider configured")

    def _get_provider_order(self) -> List[AIProvider]:
        """
        Get provider order from database settings or return default order.
        (Story P2-5.2: Configurable provider fallback chain)

        Returns:
            List of AIProvider enums in configured order
        """
        default_order = [AIProvider.OPENAI, AIProvider.GROK, AIProvider.CLAUDE, AIProvider.GEMINI]

        if self.db is None:
            return default_order

        try:
            import json
            order_setting = self.db.query(SystemSetting).filter(
                SystemSetting.key == "ai_provider_order"
            ).first()

            if order_setting and order_setting.value:
                try:
                    order_list = json.loads(order_setting.value)
                    # Convert string names to AIProvider enums
                    provider_map = {
                        "openai": AIProvider.OPENAI,
                        "grok": AIProvider.GROK,
                        "anthropic": AIProvider.CLAUDE,
                        "google": AIProvider.GEMINI,
                    }
                    provider_order = []
                    for name in order_list:
                        if name in provider_map:
                            provider_order.append(provider_map[name])
                    # If we got a valid order, use it
                    if provider_order:
                        logger.debug(f"Using configured provider order: {[p.value for p in provider_order]}")
                        return provider_order
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Invalid provider order in settings: {e}, using default")

            return default_order
        except Exception as e:
            logger.warning(f"Failed to load provider order from database: {e}, using default")
            return default_order

    async def generate_description(
        self,
        frame: np.ndarray,
        camera_name: str,
        timestamp: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        sla_timeout_ms: int = 5000,
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """
        Generate natural language description from camera frame.

        Enforces <5s SLA (p95) by tracking total elapsed time across provider attempts
        and aborting fallback chain if approaching the timeout limit.

        Args:
            frame: numpy array (BGR format from OpenCV)
            camera_name: Name of camera for context
            timestamp: ISO 8601 timestamp (default: now)
            detected_objects: Objects detected by motion detection
            sla_timeout_ms: Maximum time allowed in milliseconds (default: 5000ms = 5s)
            custom_prompt: Optional custom prompt to use instead of default (Story P2-4.1)

        Returns:
            AIResult with description, confidence, objects, and usage stats
        """
        start_time = time.time()

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        if detected_objects is None:
            detected_objects = []

        # Use custom prompt from settings if no explicit custom_prompt provided
        # This allows the AI Provider Configuration "Description prompt" setting to be used
        effective_prompt = custom_prompt
        if effective_prompt is None and self.description_prompt:
            effective_prompt = self.description_prompt
            logger.debug(f"Using description prompt from settings: '{effective_prompt[:50]}...'")

        # Preprocess image
        image_base64 = self._preprocess_image(frame)

        # Get provider order from database settings or use default (Story P2-5.2)
        provider_order = self._get_provider_order()
        last_error = None

        # Check if any providers are actually configured (Story P2-5.3: clearer error message)
        configured_providers = [p for p in provider_order if self.providers.get(p) is not None]
        if not configured_providers:
            logger.error("No AI providers configured - cannot generate description")
            return AIResult(
                description="No AI providers configured",
                confidence=0,
                objects_detected=detected_objects or ['unknown'],
                provider="none",
                tokens_used=0,
                response_time_ms=0,
                cost_estimate=0.0,
                success=False,
                error="No AI providers configured. Please add an API key in Settings."
            )

        for provider_enum in provider_order:
            # Check SLA timeout before trying next provider
            elapsed_ms = int((time.time() - start_time) * 1000)
            if elapsed_ms >= sla_timeout_ms:
                logger.warning(
                    f"SLA timeout ({sla_timeout_ms}ms) exceeded after {elapsed_ms}ms. "
                    f"Aborting fallback chain."
                )
                # Return last error result with SLA violation note
                return AIResult(
                    description=f"Failed to generate description - SLA timeout exceeded ({elapsed_ms}ms)",
                    confidence=0,
                    objects_detected=detected_objects or ['unknown'],
                    provider="timeout",
                    tokens_used=0,
                    response_time_ms=elapsed_ms,
                    cost_estimate=0.0,
                    success=False,
                    error=f"SLA timeout: {elapsed_ms}ms > {sla_timeout_ms}ms"
                )

            provider = self.providers.get(provider_enum)
            if provider is None:
                logger.warning(f"{provider_enum.value} not configured, skipping")
                continue

            logger.info(f"Attempting {provider_enum.value}... (elapsed: {elapsed_ms}ms)")

            # Try with provider-specific backoff for rate limits
            result = await self._try_with_backoff(
                provider,
                image_base64,
                camera_name,
                timestamp,
                detected_objects,
                custom_prompt=effective_prompt,
                provider_type=provider_enum
            )

            # Track usage
            self._track_usage(result)

            if result.success:
                total_elapsed_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    f"Success with {result.provider}: '{result.description[:50]}...' "
                    f"(total: {total_elapsed_ms}ms, {result.tokens_used} tokens, "
                    f"${result.cost_estimate:.6f})"
                )

                # Log SLA violations (>5s p95 target)
                if total_elapsed_ms > sla_timeout_ms:
                    logger.warning(
                        f"SLA violation: {total_elapsed_ms}ms > {sla_timeout_ms}ms target"
                    )

                return result
            else:
                last_error = result.error
                logger.warning(
                    f"{provider_enum.value} failed: {result.error}. "
                    f"Trying next provider..."
                )

        # All providers failed
        total_elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(f"All AI providers failed after {total_elapsed_ms}ms")
        return AIResult(
            description="Failed to generate description - all AI providers unavailable",
            confidence=0,
            objects_detected=detected_objects or ['unknown'],
            provider="none",
            tokens_used=0,
            response_time_ms=total_elapsed_ms,
            cost_estimate=0.0,
            success=False,
            error=f"All providers failed. Last error: {last_error}"
        )

    async def describe_images(
        self,
        images: List[bytes],
        camera_name: str,
        timestamp: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        sla_timeout_ms: int = 10000,
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """
        Generate natural language description from multiple camera frames (Story P3-2.3 AC1).

        Analyzes a sequence of frames together and returns a single combined description
        covering all frames. Useful for multi-frame analysis of motion clips.

        Enforces SLA timeout by tracking total elapsed time across provider attempts
        and aborting fallback chain if approaching the timeout limit.

        Args:
            images: List of raw image bytes (from FrameExtractor, 3-5 frames typical)
            camera_name: Name of camera for context
            timestamp: ISO 8601 timestamp of first frame (default: now)
            detected_objects: Objects detected by motion detection
            sla_timeout_ms: Maximum time allowed in milliseconds (default: 10000ms = 10s)
            custom_prompt: Optional custom prompt to use instead of default

        Returns:
            AIResult with combined description, confidence, objects, and usage stats
        """
        start_time = time.time()

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        if detected_objects is None:
            detected_objects = []

        # Validate input
        if not images:
            logger.error(
                "describe_images called with empty image list",
                extra={"event_type": "ai_multi_image_error", "error": "empty_image_list"}
            )
            return AIResult(
                description="No images provided for analysis",
                confidence=0,
                objects_detected=['unknown'],
                provider="none",
                tokens_used=0,
                response_time_ms=0,
                cost_estimate=0.0,
                success=False,
                error="Empty image list provided"
            )

        # Use custom prompt from settings if no explicit custom_prompt provided
        effective_prompt = custom_prompt
        if effective_prompt is None and self.description_prompt:
            effective_prompt = self.description_prompt
            logger.debug(
                "Using description prompt from settings for multi-image",
                extra={"prompt_preview": effective_prompt[:50]}
            )

        # Preprocess all images to base64
        images_base64 = []
        for i, img_bytes in enumerate(images):
            try:
                base64_img = self._preprocess_image_bytes(img_bytes)
                images_base64.append(base64_img)
            except Exception as e:
                logger.warning(
                    f"Failed to preprocess image {i + 1}/{len(images)}: {e}",
                    extra={
                        "event_type": "ai_multi_image_preprocess_error",
                        "image_index": i,
                        "error": str(e)
                    }
                )
                # Skip failed images but continue with others
                continue

        if not images_base64:
            logger.error(
                "All images failed preprocessing",
                extra={"event_type": "ai_multi_image_error", "num_images": len(images)}
            )
            return AIResult(
                description="Failed to preprocess images for analysis",
                confidence=0,
                objects_detected=detected_objects or ['unknown'],
                provider="none",
                tokens_used=0,
                response_time_ms=int((time.time() - start_time) * 1000),
                cost_estimate=0.0,
                success=False,
                error="All images failed preprocessing"
            )

        logger.info(
            "Starting multi-image analysis",
            extra={
                "event_type": "ai_multi_image_start",
                "num_images": len(images_base64),
                "camera_name": camera_name,
            }
        )

        # Get provider order from database settings or use default (Story P2-5.2)
        provider_order = self._get_provider_order()
        last_error = None

        # Check if any providers are actually configured
        configured_providers = [p for p in provider_order if self.providers.get(p) is not None]
        if not configured_providers:
            logger.error("No AI providers configured - cannot generate multi-image description")
            return AIResult(
                description="No AI providers configured",
                confidence=0,
                objects_detected=detected_objects or ['unknown'],
                provider="none",
                tokens_used=0,
                response_time_ms=0,
                cost_estimate=0.0,
                success=False,
                error="No AI providers configured. Please add an API key in Settings."
            )

        for provider_enum in provider_order:
            # Check SLA timeout before trying next provider
            elapsed_ms = int((time.time() - start_time) * 1000)
            if elapsed_ms >= sla_timeout_ms:
                logger.warning(
                    f"Multi-image SLA timeout ({sla_timeout_ms}ms) exceeded after {elapsed_ms}ms. "
                    f"Aborting fallback chain.",
                    extra={
                        "event_type": "ai_multi_image_sla_timeout",
                        "elapsed_ms": elapsed_ms,
                        "sla_timeout_ms": sla_timeout_ms,
                    }
                )
                return AIResult(
                    description=f"Failed to generate description - SLA timeout exceeded ({elapsed_ms}ms)",
                    confidence=0,
                    objects_detected=detected_objects or ['unknown'],
                    provider="timeout",
                    tokens_used=0,
                    response_time_ms=elapsed_ms,
                    cost_estimate=0.0,
                    success=False,
                    error=f"SLA timeout: {elapsed_ms}ms > {sla_timeout_ms}ms"
                )

            provider = self.providers.get(provider_enum)
            if provider is None:
                logger.debug(
                    f"{provider_enum.value} not configured, skipping for multi-image",
                    extra={"provider": provider_enum.value}
                )
                continue

            logger.info(
                f"Attempting multi-image analysis with {provider_enum.value}...",
                extra={
                    "event_type": "ai_multi_image_attempt",
                    "provider": provider_enum.value,
                    "elapsed_ms": elapsed_ms,
                    "num_images": len(images_base64),
                }
            )

            # Try with provider-specific backoff for rate limits
            result = await self._try_multi_image_with_backoff(
                provider,
                images_base64,
                camera_name,
                timestamp,
                detected_objects,
                custom_prompt=effective_prompt,
                provider_type=provider_enum
            )

            # Track usage
            self._track_usage(result)

            if result.success:
                total_elapsed_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    f"Multi-image analysis success with {result.provider}",
                    extra={
                        "event_type": "ai_multi_image_success",
                        "provider": result.provider,
                        "num_images": len(images_base64),
                        "total_elapsed_ms": total_elapsed_ms,
                        "tokens_used": result.tokens_used,
                        "cost_usd": result.cost_estimate,
                        "description_preview": result.description[:50],
                    }
                )

                # Log SLA violations
                if total_elapsed_ms > sla_timeout_ms:
                    logger.warning(
                        f"Multi-image SLA violation: {total_elapsed_ms}ms > {sla_timeout_ms}ms target",
                        extra={
                            "event_type": "ai_multi_image_sla_violation",
                            "elapsed_ms": total_elapsed_ms,
                            "sla_timeout_ms": sla_timeout_ms,
                        }
                    )

                return result
            else:
                last_error = result.error
                logger.warning(
                    f"{provider_enum.value} multi-image failed: {result.error}. Trying next provider...",
                    extra={
                        "event_type": "ai_multi_image_provider_failed",
                        "provider": provider_enum.value,
                        "error": result.error,
                    }
                )

        # All providers failed
        total_elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"All AI providers failed for multi-image analysis after {total_elapsed_ms}ms",
            extra={
                "event_type": "ai_multi_image_all_failed",
                "elapsed_ms": total_elapsed_ms,
                "num_images": len(images_base64),
                "last_error": last_error,
            }
        )
        return AIResult(
            description="Failed to generate description - all AI providers unavailable",
            confidence=0,
            objects_detected=detected_objects or ['unknown'],
            provider="none",
            tokens_used=0,
            response_time_ms=total_elapsed_ms,
            cost_estimate=0.0,
            success=False,
            error=f"All providers failed. Last error: {last_error}"
        )

    def _preprocess_image(self, frame: np.ndarray) -> str:
        """
        Preprocess frame for AI API transmission.

        - Resize to max 2048x2048
        - Convert to JPEG (85% quality)
        - Base64 encode
        - Ensure <5MB payload
        """
        # Convert BGR (OpenCV) to RGB (PIL)
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            frame_rgb = frame[:, :, ::-1]  # BGR to RGB
        else:
            frame_rgb = frame

        # Create PIL image
        image = Image.fromarray(frame_rgb)

        # Resize if necessary
        max_dim = 2048
        if max(image.size) > max_dim:
            ratio = max_dim / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(f"Resized image to {new_size}")

        # Convert to JPEG with 85% quality
        buffer = io.BytesIO()
        image.convert('RGB').save(buffer, format='JPEG', quality=85)
        jpeg_bytes = buffer.getvalue()

        # Check size
        size_mb = len(jpeg_bytes) / (1024 * 1024)
        if size_mb > 5:
            # Re-encode with lower quality
            buffer = io.BytesIO()
            image.convert('RGB').save(buffer, format='JPEG', quality=70)
            jpeg_bytes = buffer.getvalue()
            logger.warning(f"Image too large ({size_mb:.2f}MB), re-encoded at 70% quality")

        # Base64 encode
        image_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')

        logger.debug(f"Preprocessed image: {len(image_base64)} chars base64, {size_mb:.2f}MB")
        return image_base64

    def _preprocess_image_bytes(self, image_bytes: bytes) -> str:
        """
        Preprocess raw image bytes for AI API transmission (Story P3-2.3).

        Similar to _preprocess_image but accepts raw bytes instead of numpy array.
        Used for multi-image analysis with frames from FrameExtractor.

        - Resize to max 2048x2048
        - Convert to JPEG (85% quality)
        - Base64 encode
        - Ensure <5MB payload

        Args:
            image_bytes: Raw image bytes (JPEG or PNG from FrameExtractor)

        Returns:
            Base64-encoded JPEG string
        """
        # Load image from bytes
        image = Image.open(io.BytesIO(image_bytes))

        # Resize if necessary
        max_dim = 2048
        if max(image.size) > max_dim:
            ratio = max_dim / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(
                f"Resized image from bytes to {new_size}",
                extra={"new_size": new_size}
            )

        # Convert to JPEG with 85% quality
        buffer = io.BytesIO()
        image.convert('RGB').save(buffer, format='JPEG', quality=85)
        jpeg_bytes = buffer.getvalue()

        # Check size
        size_mb = len(jpeg_bytes) / (1024 * 1024)
        if size_mb > 5:
            # Re-encode with lower quality
            buffer = io.BytesIO()
            image.convert('RGB').save(buffer, format='JPEG', quality=70)
            jpeg_bytes = buffer.getvalue()
            logger.warning(
                f"Image bytes too large ({size_mb:.2f}MB), re-encoded at 70% quality",
                extra={"original_size_mb": size_mb}
            )

        # Base64 encode
        image_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')

        logger.debug(
            f"Preprocessed image bytes: {len(image_base64)} chars base64",
            extra={"base64_len": len(image_base64), "size_mb": size_mb}
        )
        return image_base64

    async def _try_with_backoff(
        self,
        provider: AIProviderBase,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        max_retries: int = 3,
        custom_prompt: Optional[str] = None,
        provider_type: Optional[AIProvider] = None
    ) -> AIResult:
        """Try API call with backoff for rate limits.

        Uses provider-specific retry configuration:
        - Grok: 2 retries with 0.5s delay (per Story P2-5.1 AC6)
        - Others: 3 retries with 2/4/8s exponential backoff
        """
        # Provider-specific retry configuration
        if provider_type == AIProvider.GROK:
            delays = [0.5, 0.5]  # 2 retries, 500ms each (AC6)
            max_retries = 2
        else:
            delays = [2, 4, 8]  # Exponential backoff delays (seconds)

        for attempt in range(max_retries):
            result = await provider.generate_description(
                image_base64,
                camera_name,
                timestamp,
                detected_objects,
                custom_prompt=custom_prompt
            )

            # Check if rate limited (429) or transient error (500/503)
            is_retryable = (
                result.error and
                (
                    '429' in str(result.error) or
                    '500' in str(result.error) or
                    '503' in str(result.error)
                )
            )
            if is_retryable:
                if attempt < max_retries - 1:
                    delay = delays[attempt] if attempt < len(delays) else delays[-1]
                    logger.warning(
                        f"Retryable error, waiting {delay}s before retry {attempt + 2}/{max_retries}"
                    )
                    await asyncio.sleep(delay)
                    continue

            # Return result (success or non-retryable failure)
            return result

        # Max retries exhausted
        return result

    async def _try_multi_image_with_backoff(
        self,
        provider: AIProviderBase,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        max_retries: int = 3,
        custom_prompt: Optional[str] = None,
        provider_type: Optional[AIProvider] = None
    ) -> AIResult:
        """Try multi-image API call with backoff for rate limits (Story P3-2.3).

        Uses provider-specific retry configuration:
        - Grok: 2 retries with 0.5s delay (per Story P2-5.1 AC6)
        - Others: 3 retries with 2/4/8s exponential backoff

        Args:
            provider: The AI provider to use
            images_base64: List of base64-encoded JPEG images
            camera_name: Name of the camera
            timestamp: ISO 8601 timestamp
            detected_objects: List of detected object types
            max_retries: Maximum number of retry attempts
            custom_prompt: Optional custom prompt
            provider_type: AIProvider enum for provider-specific logic

        Returns:
            AIResult from the provider
        """
        # Provider-specific retry configuration
        if provider_type == AIProvider.GROK:
            delays = [0.5, 0.5]  # 2 retries, 500ms each (AC6)
            max_retries = 2
        else:
            delays = [2, 4, 8]  # Exponential backoff delays (seconds)

        for attempt in range(max_retries):
            result = await provider.generate_multi_image_description(
                images_base64,
                camera_name,
                timestamp,
                detected_objects,
                custom_prompt=custom_prompt
            )

            # Check if rate limited (429) or transient error (500/503)
            is_retryable = (
                result.error and
                (
                    '429' in str(result.error) or
                    '500' in str(result.error) or
                    '503' in str(result.error)
                )
            )
            if is_retryable:
                if attempt < max_retries - 1:
                    delay = delays[attempt] if attempt < len(delays) else delays[-1]
                    logger.warning(
                        f"Multi-image retryable error, waiting {delay}s before retry {attempt + 2}/{max_retries}",
                        extra={
                            "event_type": "ai_multi_image_retry",
                            "provider": provider_type.value if provider_type else "unknown",
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "delay_seconds": delay,
                        }
                    )
                    await asyncio.sleep(delay)
                    continue

            # Return result (success or non-retryable failure)
            return result

        # Max retries exhausted
        return result

    def _track_usage(self, result: AIResult):
        """
        Track API usage by persisting to database.

        Stores each AI API call in the ai_usage table for historical tracking
        and cost analysis. If database is not configured, logs a warning.

        Args:
            result: AIResult from provider with usage metadata
        """
        if self.db is None:
            logger.warning("Database not configured, usage tracking disabled")
            return

        try:
            usage_record = AIUsage(
                timestamp=datetime.utcnow(),
                provider=result.provider,
                success=result.success,
                tokens_used=result.tokens_used,
                response_time_ms=result.response_time_ms,
                cost_estimate=result.cost_estimate,
                error=result.error
            )

            self.db.add(usage_record)
            self.db.commit()

            logger.debug(
                f"Tracked usage: {result.provider} - "
                f"{'success' if result.success else 'failed'} - "
                f"{result.tokens_used} tokens - "
                f"${result.cost_estimate:.6f}"
            )

        except Exception as e:
            logger.error(f"Failed to track usage: {e}")
            # Don't fail the API call just because tracking failed
            self.db.rollback()

    def get_usage_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get usage statistics from database.

        Queries ai_usage table for aggregated statistics including total calls,
        costs, tokens, and per-provider breakdowns.

        Args:
            start_date: Optional start of date range filter
            end_date: Optional end of date range filter

        Returns:
            Dictionary with aggregated usage statistics
        """
        if self.db is None:
            logger.warning("Database not configured, returning empty stats")
            return {
                'total_calls': 0,
                'successful_calls': 0,
                'failed_calls': 0,
                'total_tokens': 0,
                'total_cost': 0.0,
                'avg_response_time_ms': 0,
                'provider_breakdown': {}
            }

        try:
            # Build query with date filters
            query = self.db.query(AIUsage)

            if start_date:
                query = query.filter(AIUsage.timestamp >= start_date)
            if end_date:
                query = query.filter(AIUsage.timestamp <= end_date)

            records = query.all()

            if not records:
                return {
                    'total_calls': 0,
                    'successful_calls': 0,
                    'failed_calls': 0,
                    'total_tokens': 0,
                    'total_cost': 0.0,
                    'avg_response_time_ms': 0,
                    'provider_breakdown': {}
                }

            # Calculate aggregates
            total_calls = len(records)
            successful_calls = sum(1 for r in records if r.success)
            failed_calls = total_calls - successful_calls
            total_tokens = sum(r.tokens_used for r in records)
            total_cost = sum(r.cost_estimate for r in records)
            avg_response_time = sum(r.response_time_ms for r in records) / total_calls if total_calls > 0 else 0

            # Provider breakdown
            providers = {}
            for provider_enum in [AIProvider.OPENAI, AIProvider.GROK, AIProvider.CLAUDE, AIProvider.GEMINI]:
                provider_records = [r for r in records if r.provider == provider_enum.value]
                if provider_records:
                    providers[provider_enum.value] = {
                        'calls': len(provider_records),
                        'success_rate': sum(1 for r in provider_records if r.success) / len(provider_records) * 100,
                        'tokens': sum(r.tokens_used for r in provider_records),
                        'cost': sum(r.cost_estimate for r in provider_records)
                    }

            return {
                'total_calls': total_calls,
                'successful_calls': successful_calls,
                'failed_calls': failed_calls,
                'total_tokens': total_tokens,
                'total_cost': round(total_cost, 4),
                'avg_response_time_ms': round(avg_response_time, 2),
                'provider_breakdown': providers
            }

        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}")
            return {
                'total_calls': 0,
                'successful_calls': 0,
                'failed_calls': 0,
                'total_tokens': 0,
                'total_cost': 0.0,
                'avg_response_time_ms': 0,
                'provider_breakdown': {}
            }


# Global AI service instance
ai_service = AIService()
