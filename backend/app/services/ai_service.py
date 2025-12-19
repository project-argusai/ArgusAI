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
from app.services.cost_tracker import get_cost_tracker

logger = logging.getLogger(__name__)


# Multi-frame analysis system prompt (Story P3-2.4)
# Optimized for temporal narrative descriptions of video sequences
# Story P3-6.1: Confidence scoring instruction appended to all prompts
CONFIDENCE_INSTRUCTION = """

After your description, rate your confidence in this description from 0 to 100, where:
- 0-30: Very uncertain, limited visibility or unclear action
- 31-50: Somewhat uncertain, some ambiguity
- 51-70: Moderately confident
- 71-90: Confident
- 91-100: Very confident, clear view and obvious action

Respond in this exact JSON format:
{"description": "your detailed description here", "confidence": 85}"""


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

If you see a delivery person or truck, identify the carrier:
- FedEx (purple/orange colors, FedEx logo)
- UPS (brown uniform, brown truck)
- USPS (blue uniform, postal logo, mail truck)
- Amazon (blue vest, Amazon logo, Amazon van)
- DHL (yellow/red colors, DHL logo)
Include the carrier name in your description.

Be specific about the narrative - this is video showing motion over time, not a static photograph. Describe the complete sequence of what happened."""


# Token estimation constants per provider (Story P3-2.5)
# Approximate tokens per image for vision API calls
TOKENS_PER_IMAGE = {
    "openai": {"low_res": 85, "high_res": 765, "default": 85},
    "grok": {"low_res": 85, "high_res": 765, "default": 85},  # OpenAI-compatible
    "claude": {"default": 1334},  # Anthropic Claude
    "gemini": {"default": 258},  # Google Gemini estimate
}

# Cost rates per 1K tokens by provider (Story P3-2.5)
# Values from architecture.md CostTracker section (USD per 1K tokens)
COST_RATES = {
    "openai": {"input": 0.00015, "output": 0.00060},  # GPT-4o-mini
    "grok": {"input": 0.00005, "output": 0.00010},  # xAI Grok estimate
    "claude": {"input": 0.00025, "output": 0.00125},  # Claude 3 Haiku
    "gemini": {"input": 0.000075, "output": 0.0003},  # Gemini Flash
}

# Provider capabilities matrix (Story P3-4.1, P3-4.2)
# Static capability information for each AI provider
# - video: Whether provider supports native video file input (NOT frame extraction)
# - max_video_duration: Maximum video duration in seconds (0 if no video support)
# - max_video_size_mb: Maximum video file size in MB (0 if no video support)
# - supported_formats: List of supported video formats (empty if no video support)
# - max_images: Maximum number of images for multi-frame analysis
#
# NOTE (P3-4.2): Provider video capabilities
# - OpenAI: Supports video via FRAME EXTRACTION (not native upload). Extract frames + optional Whisper audio.
#   Source: https://cookbook.openai.com/examples/gpt4o/introduction_to_gpt4o
# - Gemini: Supports NATIVE VIDEO UPLOAD (file upload or inline data).
#   Source: https://ai.google.dev/gemini-api/docs/vision
PROVIDER_CAPABILITIES = {
    "openai": {
        "video": True,  # P3-4.2: OpenAI supports video via frame extraction
        "video_method": "frame_extraction",  # Extract frames, send as images
        "max_video_duration": 60,  # Practical limit for frame extraction
        "max_video_size_mb": 50,  # Larger files OK since we extract frames
        "max_frames": 10,  # Cost control: max frames to extract
        "supported_formats": ["mp4", "mov", "webm", "avi"],
        "max_images": 10,
        "supports_audio_transcription": True,  # Optional Whisper integration
    },
    "grok": {
        "video": True,  # Grok 2 Vision supports video via frame extraction (same as OpenAI pattern)
        "video_method": "frame_extraction",
        "max_video_duration": 60,
        "max_video_size_mb": 50,
        "max_frames": 10,
        "supported_formats": ["mp4", "mov", "webm", "avi"],
        "max_images": 10,
        "supports_audio_transcription": False,
    },
    "claude": {
        "video": False,  # Claude does not support video input
        "video_method": None,
        "max_video_duration": 0,
        "max_video_size_mb": 0,
        "max_frames": 0,
        "supported_formats": [],
        "max_images": 20,
        "supports_audio_transcription": False,
    },
    "gemini": {
        "video": True,
        "video_method": "native_upload",  # P3-4.3: Native video file upload
        "max_video_duration": 300,  # 5 min practical limit (tokens ~258/frame at 1fps)
        "max_video_size_mb": 2048,  # 2GB via File API
        "inline_max_size_mb": 20,  # Inline data limit (faster, no upload)
        "max_frames": 0,  # N/A for native upload
        "supported_formats": ["mp4", "mov", "webm", "avi", "flv", "mpg", "mpeg", "wmv"],
        "max_images": 16,
        "supports_audio": True,  # Gemini natively processes video audio
    },
}


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
    confidence: int  # 0-100 (computed from heuristics)
    objects_detected: List[str]  # person, vehicle, animal, package, unknown
    provider: str  # Which provider was used
    tokens_used: int
    response_time_ms: int
    cost_estimate: float  # USD
    success: bool
    error: Optional[str] = None
    # Story P3-6.1: AI self-reported confidence score
    ai_confidence: Optional[int] = None  # 0-100 (from AI response, None if not provided)
    # Story P4-5.4: A/B test variant tracking
    prompt_variant: Optional[str] = None  # 'control', 'experiment', or None


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
            "Be specific and detailed.\n\n"
            "If you see a delivery person or truck, identify the carrier:\n"
            "- FedEx (purple/orange colors, FedEx logo)\n"
            "- UPS (brown uniform, brown truck)\n"
            "- USPS (blue uniform, postal logo, mail truck)\n"
            "- Amazon (blue vest, Amazon logo, Amazon van)\n"
            "- DHL (yellow/red colors, DHL logo)\n"
            "Include the carrier name in your description."
        )

    @abstractmethod
    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> AIResult:
        """Generate description from base64-encoded image

        Args:
            image_base64: Base64-encoded JPEG image
            camera_name: Name of the camera for context
            timestamp: ISO 8601 timestamp
            detected_objects: List of detected object types
            custom_prompt: Optional custom prompt to override default (Story P2-4.1)
            audio_transcription: Optional transcribed speech from doorbell audio (Story P3-5.3)
        """
        pass

    @abstractmethod
    async def generate_multi_image_description(
        self,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
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
            audio_transcription: Optional transcribed speech from doorbell audio (Story P3-5.3)

        Returns:
            AIResult with combined description covering all frames
        """
        pass

    def _build_user_prompt(
        self,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> str:
        """Build user prompt with context

        Args:
            camera_name: Name of the camera
            timestamp: ISO 8601 timestamp
            detected_objects: List of detected object types
            custom_prompt: Optional custom prompt to override the base description instruction
                          (from Settings → AI Provider Configuration → Description prompt,
                           or from Story P2-4.1 doorbell ring events)
            audio_transcription: Optional transcribed speech from doorbell audio (Story P3-5.3)
        """
        # Build camera context
        context = f"\nContext: Camera '{camera_name}' at {timestamp}."
        if detected_objects:
            context += f" Motion detected: {', '.join(detected_objects)}."

        # Use custom prompt if provided (from Settings description_prompt or doorbell ring)
        # Otherwise use the default user_prompt_template
        base_prompt = custom_prompt if custom_prompt else self.user_prompt_template

        prompt = base_prompt + context

        # Story P3-5.3: Add audio transcription if available
        # Only include if transcription has actual content (not None, not empty string)
        if audio_transcription and audio_transcription.strip():
            prompt += f'\n\nAudio transcription: "{audio_transcription.strip()}"'

        # Story P3-6.1: Add confidence instruction to all prompts
        prompt += CONFIDENCE_INSTRUCTION

        return prompt

    def _build_multi_image_prompt(
        self,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        num_images: int,
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> str:
        """Build user prompt for multi-image analysis (Story P3-2.3, P3-2.4, P3-5.3)

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
            audio_transcription: Optional transcribed speech from doorbell audio (Story P3-5.3)
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

        prompt = base_prompt + context

        # Story P3-5.3: Add audio transcription if available
        # Only include if transcription has actual content (not None, not empty string)
        if audio_transcription and audio_transcription.strip():
            prompt += f'\n\nAudio transcription: "{audio_transcription.strip()}"'

        # Story P3-6.1: Add confidence instruction to all prompts
        prompt += CONFIDENCE_INSTRUCTION

        return prompt

    def _parse_confidence_response(self, response_text: str) -> tuple[str, Optional[int]]:
        """Parse AI response for description and confidence score (Story P3-6.1)

        Attempts to extract structured JSON response with description and confidence.
        Falls back to plain text parsing if JSON is not found.

        Args:
            response_text: Raw response text from AI provider

        Returns:
            Tuple of (description, ai_confidence) where ai_confidence may be None
        """
        import json
        import re

        # Try JSON parsing first - use json.loads for proper handling of escapes
        try:
            # Look for JSON that starts with { and ends with }
            brace_start = response_text.find('{')
            brace_end = response_text.rfind('}')
            if brace_start != -1 and brace_end > brace_start:
                json_str = response_text[brace_start:brace_end + 1]
                data = json.loads(json_str)
                description = data.get('description', '').strip()
                confidence = data.get('confidence')

                if isinstance(confidence, (int, float)) and 0 <= confidence <= 100:
                    if description:
                        return description, int(confidence)

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug(f"JSON parsing failed for confidence extraction: {e}")

        # Check for truncated JSON response (incomplete description)
        # Pattern: {"description": "some text without closing quote or brace
        truncated_match = re.search(r'\{\s*"description"\s*:\s*"([^"]+)$', response_text, re.DOTALL)
        if truncated_match:
            # Response was truncated - extract what we have and note it
            partial_desc = truncated_match.group(1).strip()
            logger.warning(f"Detected truncated JSON response, extracting partial description: {partial_desc[:50]}...")
            # Return partial description without confidence (since it was cut off)
            return partial_desc, None

        # Fallback: Try to extract confidence from plain text
        # Look for patterns like "85% confident", "confidence: 85", "confidence is 85"
        confidence_patterns = [
            r'confidence[:\s]+(\d{1,3})(?:%|\b)',  # "confidence: 85" or "confidence 85%"
            r'(\d{1,3})%?\s*confiden',  # "85% confident" or "85 confident"
            r'confidence\s*(?:score|level|rating)?[:\s]*(\d{1,3})',  # "confidence score: 85"
        ]

        for pattern in confidence_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                try:
                    confidence = int(match.group(1))
                    if 0 <= confidence <= 100:
                        logger.debug(f"Extracted confidence {confidence} from plain text")
                        return response_text, confidence
                except (ValueError, IndexError):
                    continue

        # No confidence found - return original text with None
        logger.debug("No confidence score found in AI response")
        return response_text, None

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
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> AIResult:
        """Generate description using OpenAI GPT-4o mini"""
        start_time = time.time()

        try:
            user_prompt = self._build_user_prompt(camera_name, timestamp, detected_objects, custom_prompt, audio_transcription)

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

            # Story P3-6.1: Parse response for description and AI confidence
            description, ai_confidence = self._parse_confidence_response(raw_response)

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
                    "ai_confidence": ai_confidence,
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
                success=True,
                ai_confidence=ai_confidence
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
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> AIResult:
        """Generate description from multiple images using OpenAI GPT-4o mini (Story P3-2.3 AC2)"""
        start_time = time.time()

        try:
            user_prompt = self._build_multi_image_prompt(
                camera_name, timestamp, detected_objects, len(images_base64), custom_prompt, audio_transcription
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
            raw_response = response.choices[0].message.content.strip()

            # Story P3-6.1: Parse response for description and AI confidence
            description, ai_confidence = self._parse_confidence_response(raw_response)

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
                    "ai_confidence": ai_confidence,
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
                success=True,
                ai_confidence=ai_confidence
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

    async def describe_video(
        self,
        video_path: "Path",
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        include_audio: bool = False,
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """
        Analyze video using frame extraction + optional audio transcription (Story P3-4.2).

        OpenAI does not support native video file upload. This method extracts frames
        using FrameExtractor (P3-2.1) and sends them via generate_multi_image_description().
        Optionally transcribes audio via Whisper API and includes in prompt context.

        Args:
            video_path: Path to the video file (MP4, MOV, etc.)
            camera_name: Name of the camera for context
            timestamp: Timestamp of the event
            detected_objects: Objects detected by motion analysis
            include_audio: If True, extract and transcribe audio via Whisper (AC3)
            custom_prompt: Optional custom prompt to append

        Returns:
            AIResult with video analysis description

        Implementation Notes:
            - Extracts max 10 frames for cost control (AC2)
            - Uses evenly_spaced strategy with blur filtering
            - Token usage is tracked accurately (AC5)
            - Frame extraction uses existing FrameExtractor (P3-2.1)
        """
        from pathlib import Path
        from app.services.frame_extractor import get_frame_extractor

        start_time = time.time()

        # Ensure video_path is a Path object
        if isinstance(video_path, str):
            video_path = Path(video_path)

        logger.info(
            "Starting video analysis via frame extraction",
            extra={
                "event_type": "video_describe_start",
                "provider": "openai",
                "video_path": str(video_path),
                "include_audio": include_audio,
                "camera_name": camera_name
            }
        )

        try:
            # Step 1: Extract frames using FrameExtractor (AC1, AC2)
            frame_extractor = get_frame_extractor()
            max_frames = PROVIDER_CAPABILITIES["openai"].get("max_frames", 10)

            frames_bytes = await frame_extractor.extract_frames(
                clip_path=video_path,
                frame_count=max_frames,
                strategy="evenly_spaced",
                filter_blur=True
            )

            if not frames_bytes:
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    "No frames extracted from video",
                    extra={
                        "event_type": "video_describe_no_frames",
                        "provider": "openai",
                        "video_path": str(video_path),
                        "response_time_ms": elapsed_ms
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
                    error="No frames could be extracted from video"
                )

            # Convert JPEG bytes to base64 strings
            frames_base64 = [base64.b64encode(fb).decode('utf-8') for fb in frames_bytes]

            # Step 2: Optional audio transcription via Whisper (AC3)
            transcript = None
            if include_audio:
                transcript = await self._transcribe_audio(video_path)

            # Step 3: Build enhanced prompt with transcript context
            enhanced_prompt = custom_prompt or ""
            if transcript:
                enhanced_prompt = f"Audio transcript from the video: {transcript}\n\n{enhanced_prompt}".strip()

            # Step 4: Use existing multi-image method (reuse P3-2.3 infrastructure)
            result = await self.generate_multi_image_description(
                images_base64=frames_base64,
                camera_name=camera_name,
                timestamp=timestamp,
                detected_objects=detected_objects,
                custom_prompt=enhanced_prompt if enhanced_prompt else None
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Video analysis via frame extraction completed",
                extra={
                    "event_type": "video_describe_success",
                    "provider": "openai",
                    "video_path": str(video_path),
                    "num_frames": len(frames_base64),
                    "audio_transcribed": transcript is not None,
                    "response_time_ms": elapsed_ms,
                    "tokens_used": result.tokens_used,
                    "success": result.success
                }
            )

            # Update response time to include frame extraction time
            result.response_time_ms = elapsed_ms

            return result

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Video analysis via frame extraction failed",
                extra={
                    "event_type": "video_describe_error",
                    "provider": "openai",
                    "video_path": str(video_path),
                    "response_time_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
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

    async def _transcribe_audio(self, video_path: "Path") -> Optional[str]:
        """
        Extract and transcribe audio from video using Whisper API (Story P3-4.2 AC3).

        Args:
            video_path: Path to the video file

        Returns:
            Transcribed text, or None if no audio or transcription fails
        """
        import tempfile
        import os
        import av

        temp_audio_path = None
        try:
            # Check if video has audio stream
            with av.open(str(video_path)) as container:
                audio_stream = next(
                    (s for s in container.streams if s.type == 'audio'),
                    None
                )
                if not audio_stream:
                    logger.debug(
                        "Video has no audio track",
                        extra={
                            "event_type": "audio_transcribe_no_track",
                            "video_path": str(video_path)
                        }
                    )
                    return None

            # Extract audio to temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_audio_path = temp_audio.name

            # Use PyAV to extract audio
            with av.open(str(video_path)) as in_container:
                audio_stream = next(s for s in in_container.streams if s.type == 'audio')

                # Create output container for WAV
                with av.open(temp_audio_path, 'w', format='wav') as out_container:
                    out_stream = out_container.add_stream('pcm_s16le', rate=16000)
                    out_stream.layout = 'mono'

                    # Resample and write audio
                    resampler = av.AudioResampler(
                        format='s16',
                        layout='mono',
                        rate=16000
                    )

                    for packet in in_container.demux(audio_stream):
                        for frame in packet.decode():
                            resampled = resampler.resample(frame)
                            for resampled_frame in resampled:
                                for out_packet in out_stream.encode(resampled_frame):
                                    out_container.mux(out_packet)

                    # Flush encoder
                    for out_packet in out_stream.encode():
                        out_container.mux(out_packet)

            # Transcribe with Whisper
            with open(temp_audio_path, "rb") as audio_file:
                transcript_response = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )

            transcript = transcript_response.text.strip() if transcript_response.text else None

            logger.info(
                "Audio transcription completed",
                extra={
                    "event_type": "audio_transcribe_success",
                    "video_path": str(video_path),
                    "transcript_length": len(transcript) if transcript else 0
                }
            )

            return transcript

        except Exception as e:
            logger.warning(
                f"Audio transcription failed: {e}",
                extra={
                    "event_type": "audio_transcribe_error",
                    "video_path": str(video_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

        finally:
            # Clean up temp file
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.unlink(temp_audio_path)
                except Exception:
                    pass


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
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> AIResult:
        """Generate description using Claude 3 Haiku"""
        start_time = time.time()

        try:
            user_prompt = self._build_user_prompt(camera_name, timestamp, detected_objects, custom_prompt, audio_transcription)

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
            raw_response = response.content[0].text.strip()

            # Story P3-6.1: Parse response for description and AI confidence
            description, ai_confidence = self._parse_confidence_response(raw_response)

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
                f"confidence={confidence}, ai_confidence={ai_confidence}"
            )

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.CLAUDE.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True,
                ai_confidence=ai_confidence
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
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> AIResult:
        """Generate description from multiple images using Claude 3 Haiku (Story P3-2.3 AC3)"""
        start_time = time.time()

        try:
            user_prompt = self._build_multi_image_prompt(
                camera_name, timestamp, detected_objects, len(images_base64), custom_prompt, audio_transcription
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
            raw_response = response.content[0].text.strip()

            # Story P3-6.1: Parse response for description and AI confidence
            description, ai_confidence = self._parse_confidence_response(raw_response)

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
                    "ai_confidence": ai_confidence,
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
                success=True,
                ai_confidence=ai_confidence
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
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        self.cost_per_1k_tokens = 0.0001  # Approximate (free tier available)

    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> AIResult:
        """Generate description using Gemini Flash"""
        start_time = time.time()

        try:
            user_prompt = self._build_user_prompt(camera_name, timestamp, detected_objects, custom_prompt, audio_transcription)
            full_prompt = f"{self.system_prompt}\n\n{user_prompt}"

            # Decode base64 to bytes for Gemini
            image_bytes = base64.b64decode(image_base64)
            image_part = {"mime_type": "image/jpeg", "data": image_bytes}

            response = await self.model.generate_content_async(
                [full_prompt, image_part],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=500,
                    temperature=0.4
                )
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Check if response was blocked by safety filters
            if not response.candidates or not response.candidates[0].content.parts:
                finish_reason = response.candidates[0].finish_reason if response.candidates else "unknown"
                raise ValueError(f"Response blocked by Gemini (finish_reason: {finish_reason})")

            raw_response = response.text.strip()

            # Story P3-6.1: Parse response for description and AI confidence
            description, ai_confidence = self._parse_confidence_response(raw_response)

            # Gemini doesn't provide detailed usage stats in all cases
            tokens_used = 150  # Estimate
            cost = tokens_used / 1000 * self.cost_per_1k_tokens

            confidence = 70
            objects = self._extract_objects(description)

            logger.info(
                f"Gemini success: {elapsed_ms}ms, ~{tokens_used} tokens, ${cost:.6f}, "
                f"confidence={confidence}, ai_confidence={ai_confidence}"
            )

            return AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider=AIProvider.GEMINI.value,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True,
                ai_confidence=ai_confidence
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
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> AIResult:
        """Generate description from multiple images using Gemini Flash (Story P3-2.3 AC4)"""
        start_time = time.time()

        try:
            user_prompt = self._build_multi_image_prompt(
                camera_name, timestamp, detected_objects, len(images_base64), custom_prompt, audio_transcription
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

            # Check if response was blocked by safety filters
            if not response.candidates or not response.candidates[0].content.parts:
                finish_reason = response.candidates[0].finish_reason if response.candidates else "unknown"
                raise ValueError(f"Response blocked by Gemini (finish_reason: {finish_reason})")

            raw_response = response.text.strip()

            # Story P3-6.1: Parse response for description and AI confidence
            description, ai_confidence = self._parse_confidence_response(raw_response)

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
                    "model": "gemini-2.5-flash",
                    "num_images": len(images_base64),
                    "response_time_ms": elapsed_ms,
                    "tokens_used": tokens_used,
                    "cost_usd": cost,
                    "confidence": confidence,
                    "ai_confidence": ai_confidence,
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
                success=True,
                ai_confidence=ai_confidence
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Gemini multi-image API call failed",
                extra={
                    "event_type": "ai_api_multi_image_error",
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
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

    async def describe_video(
        self,
        video_path: "Path",
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """
        Analyze video using Gemini's native video upload (Story P3-4.3).

        Gemini supports two methods:
        - Inline data: For videos under 20MB, send bytes directly
        - File API: For videos 20MB-2GB, upload to Google servers first

        This method automatically selects the appropriate method based on file size.

        Args:
            video_path: Path to the video file (MP4, MOV, WebM, etc.)
            camera_name: Name of the camera for context
            timestamp: Timestamp of the event
            detected_objects: Objects detected by motion analysis
            custom_prompt: Optional custom prompt to append

        Returns:
            AIResult with video analysis description

        Implementation Notes:
            - Uses inline_data for clips under 20MB (typical security clips)
            - Falls back to File API for larger videos (up to 2GB)
            - Token usage estimated at ~258 tokens/frame at 1fps (AC3)
            - Audio is processed natively by Gemini models
        """
        from pathlib import Path
        import os

        start_time = time.time()

        # Ensure video_path is a Path object
        if isinstance(video_path, str):
            video_path = Path(video_path)

        logger.info(
            "Starting video analysis via Gemini native upload",
            extra={
                "event_type": "video_describe_start",
                "provider": "gemini",
                "video_path": str(video_path),
                "camera_name": camera_name
            }
        )

        try:
            # Step 1: Validate video file exists
            if not video_path.exists():
                elapsed_ms = int((time.time() - start_time) * 1000)
                return AIResult(
                    description="",
                    confidence=0,
                    objects_detected=[],
                    provider=AIProvider.GEMINI.value,
                    tokens_used=0,
                    response_time_ms=elapsed_ms,
                    cost_estimate=0.0,
                    success=False,
                    error=f"Video file not found: {video_path}"
                )

            # Step 2: Get file size and validate against limits
            file_size_bytes = os.path.getsize(video_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            max_size_mb = PROVIDER_CAPABILITIES["gemini"].get("max_video_size_mb", 20)
            inline_max_mb = 20  # Gemini inline data limit

            if file_size_mb > max_size_mb:
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    f"Video exceeds size limit: {file_size_mb:.2f}MB > {max_size_mb}MB",
                    extra={
                        "event_type": "video_describe_size_exceeded",
                        "provider": "gemini",
                        "video_path": str(video_path),
                        "file_size_mb": file_size_mb,
                        "max_size_mb": max_size_mb
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
                    error=f"Video exceeds size limit: {file_size_mb:.2f}MB > {max_size_mb}MB"
                )

            # Step 3: Validate and convert video format if needed (AC2)
            converted_path = None
            working_video_path = video_path
            if not self._is_supported_video_format(video_path):
                logger.info(
                    f"Video format not natively supported, converting: {video_path.suffix}",
                    extra={
                        "event_type": "video_format_unsupported",
                        "provider": "gemini",
                        "video_path": str(video_path),
                        "format": video_path.suffix
                    }
                )
                converted_path = await self._convert_video_format(video_path)
                if converted_path is None:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    return AIResult(
                        description="",
                        confidence=0,
                        objects_detected=[],
                        provider=AIProvider.GEMINI.value,
                        tokens_used=0,
                        response_time_ms=elapsed_ms,
                        cost_estimate=0.0,
                        success=False,
                        error=f"Failed to convert unsupported video format: {video_path.suffix}"
                    )
                working_video_path = converted_path
                # Update file size after conversion
                file_size_bytes = os.path.getsize(working_video_path)
                file_size_mb = file_size_bytes / (1024 * 1024)

            try:
                # Step 4: Get video duration for token estimation
                video_duration_seconds = await self._get_video_duration(working_video_path)

                # Step 5: Determine MIME type
                mime_type = self._get_video_mime_type(working_video_path)

                # Step 6: Build prompt
                user_prompt = self._build_video_prompt(
                    camera_name, timestamp, detected_objects, video_duration_seconds, custom_prompt
                )
                full_prompt = f"{self.system_prompt}\n\n{user_prompt}"

                # Step 7: Choose method based on file size
                if file_size_mb <= inline_max_mb:
                    # Inline data method for small videos
                    result = await self._describe_video_inline(
                        working_video_path, full_prompt, mime_type, start_time, video_duration_seconds
                    )
                else:
                    # File API method for larger videos
                    result = await self._describe_video_file_api(
                        working_video_path, full_prompt, start_time, video_duration_seconds
                    )

                return result
            finally:
                # Clean up converted file if we created one
                if converted_path and converted_path.exists():
                    try:
                        converted_path.unlink()
                        logger.debug(f"Cleaned up converted video file: {converted_path}")
                    except Exception as e:
                        logger.warning(f"Could not clean up converted video: {e}")

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Video analysis via Gemini native upload failed",
                extra={
                    "event_type": "video_describe_error",
                    "provider": "gemini",
                    "video_path": str(video_path),
                    "response_time_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
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

    async def _describe_video_inline(
        self,
        video_path: "Path",
        prompt: str,
        mime_type: str,
        start_time: float,
        video_duration_seconds: float
    ) -> AIResult:
        """
        Send video as inline data (for videos under 20MB).
        """
        # Read video bytes
        video_bytes = video_path.read_bytes()

        # Create video part for Gemini
        video_part = {"mime_type": mime_type, "data": video_bytes}

        # Send to Gemini
        response = await self.model.generate_content_async(
            [prompt, video_part],
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=500,
                temperature=0.4
            )
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Check if response was blocked by safety filters
        if not response.candidates or not response.candidates[0].content.parts:
            finish_reason = response.candidates[0].finish_reason if response.candidates else "unknown"
            raise ValueError(f"Response blocked by Gemini (finish_reason: {finish_reason})")

        raw_response = response.text.strip()

        # Story P3-6.1: Parse response for description and AI confidence
        description, ai_confidence = self._parse_confidence_response(raw_response)

        # Estimate token usage: ~258 tokens/frame at 1fps
        estimated_frames = int(video_duration_seconds) if video_duration_seconds > 0 else 10
        tokens_used = 150 + (estimated_frames * 258)  # Base + video tokens
        cost = tokens_used / 1000 * self.cost_per_1k_tokens

        confidence = 75  # Higher confidence for native video
        objects = self._extract_objects(description)

        logger.info(
            "Gemini video analysis (inline) completed",
            extra={
                "event_type": "video_describe_success",
                "provider": "gemini",
                "method": "inline",
                "video_path": str(video_path),
                "video_duration_seconds": video_duration_seconds,
                "response_time_ms": elapsed_ms,
                "tokens_used": tokens_used,
                "cost_usd": cost,
                "confidence": confidence,
                "ai_confidence": ai_confidence
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
            success=True,
            ai_confidence=ai_confidence
        )

    async def _describe_video_file_api(
        self,
        video_path: "Path",
        prompt: str,
        start_time: float,
        video_duration_seconds: float
    ) -> AIResult:
        """
        Upload video via File API for larger videos (20MB-2GB).

        This method uploads the video to Google's servers, waits for processing,
        then sends to Gemini for analysis.
        """
        import asyncio

        # Upload the video file
        logger.info(
            "Uploading video to Gemini File API",
            extra={
                "event_type": "video_file_api_upload_start",
                "provider": "gemini",
                "video_path": str(video_path)
            }
        )

        video_file = genai.upload_file(path=str(video_path))

        # Wait for processing to complete (poll status)
        max_wait_seconds = 120
        poll_interval = 5
        waited = 0

        while video_file.state.name == "PROCESSING" and waited < max_wait_seconds:
            logger.debug(
                f"Video processing, waiting... ({waited}s)",
                extra={
                    "event_type": "video_file_api_processing",
                    "provider": "gemini",
                    "state": video_file.state.name,
                    "waited_seconds": waited
                }
            )
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.GEMINI.value,
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=f"Video processing failed: {video_file.state.name}"
            )

        if video_file.state.name == "PROCESSING":
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=AIProvider.GEMINI.value,
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=f"Video processing timed out after {max_wait_seconds}s"
            )

        # Video is ready, generate content
        response = await self.model.generate_content_async(
            [prompt, video_file],
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=500,
                temperature=0.4
            )
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Check if response was blocked by safety filters
        if not response.candidates or not response.candidates[0].content.parts:
            finish_reason = response.candidates[0].finish_reason if response.candidates else "unknown"
            raise ValueError(f"Response blocked by Gemini (finish_reason: {finish_reason})")

        raw_response = response.text.strip()

        # Story P3-6.1: Parse response for description and AI confidence
        description, ai_confidence = self._parse_confidence_response(raw_response)

        # Estimate token usage
        estimated_frames = int(video_duration_seconds) if video_duration_seconds > 0 else 10
        tokens_used = 150 + (estimated_frames * 258)
        cost = tokens_used / 1000 * self.cost_per_1k_tokens

        confidence = 75
        objects = self._extract_objects(description)

        logger.info(
            "Gemini video analysis (File API) completed",
            extra={
                "event_type": "video_describe_success",
                "provider": "gemini",
                "method": "file_api",
                "video_path": str(video_path),
                "video_duration_seconds": video_duration_seconds,
                "response_time_ms": elapsed_ms,
                "tokens_used": tokens_used,
                "cost_usd": cost,
                "confidence": confidence,
                "ai_confidence": ai_confidence
            }
        )

        # Clean up uploaded file (optional, auto-deleted after 48h)
        try:
            genai.delete_file(video_file.name)
        except Exception as e:
            logger.debug(f"Could not delete uploaded video file: {e}")

        return AIResult(
            description=description,
            confidence=confidence,
            objects_detected=objects,
            provider=AIProvider.GEMINI.value,
            tokens_used=tokens_used,
            response_time_ms=elapsed_ms,
            cost_estimate=cost,
            success=True,
            ai_confidence=ai_confidence
        )

    async def _get_video_duration(self, video_path: "Path") -> float:
        """Get video duration in seconds using PyAV."""
        import av

        try:
            with av.open(str(video_path)) as container:
                if container.duration is not None:
                    return container.duration / av.time_base
                # Fallback: estimate from stream
                for stream in container.streams.video:
                    if stream.duration and stream.time_base:
                        return float(stream.duration * stream.time_base)
            return 10.0  # Default estimate
        except Exception as e:
            logger.warning(f"Could not get video duration: {e}")
            return 10.0  # Default estimate

    def _get_video_mime_type(self, video_path: "Path") -> str:
        """Determine MIME type from file extension."""
        ext = video_path.suffix.lower()
        mime_types = {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
            ".avi": "video/x-msvideo",
            ".flv": "video/x-flv",
            ".mpg": "video/mpeg",
            ".mpeg": "video/mpeg",
            ".wmv": "video/x-ms-wmv",
            ".mkv": "video/x-matroska",
        }
        return mime_types.get(ext, "video/mp4")

    def _build_video_prompt(
        self,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        video_duration_seconds: float,
        custom_prompt: Optional[str] = None
    ) -> str:
        """Build prompt for video analysis with temporal narrative emphasis."""
        objects_str = ", ".join(detected_objects) if detected_objects else "motion"
        duration_str = f"{video_duration_seconds:.1f}" if video_duration_seconds > 0 else "several"

        prompt = f"""Analyze this {duration_str}-second video clip from security camera '{camera_name}' captured at {timestamp}.

Motion detection triggered on: {objects_str}

This is a security camera video clip. Describe what happens throughout the video in chronological order:
1. What activity or motion is occurring?
2. Who or what is moving and how?
3. What is the sequence of events from start to finish?
4. Any notable details about appearance, behavior, or items visible?

Provide a clear, temporal narrative of the events in the video."""

        if custom_prompt:
            prompt = f"{custom_prompt}\n\n{prompt}"

        return prompt

    def _is_supported_video_format(self, video_path: "Path") -> bool:
        """Check if video format is supported by Gemini (AC2)."""
        ext = video_path.suffix.lower().lstrip(".")
        supported = PROVIDER_CAPABILITIES["gemini"].get("supported_formats", [])
        return ext in supported

    async def _convert_video_format(self, video_path: "Path") -> Optional["Path"]:
        """
        Convert unsupported video format to MP4/H.264 using PyAV (AC2).

        Args:
            video_path: Path to the original video file

        Returns:
            Path to converted video file, or None if conversion failed.
            Caller is responsible for cleaning up the converted file.
        """
        import av
        from pathlib import Path
        import tempfile

        try:
            # Create temp file for converted video
            output_path = Path(tempfile.mktemp(suffix=".mp4"))

            logger.info(
                f"Converting video format: {video_path.suffix} -> .mp4",
                extra={
                    "event_type": "video_format_conversion_start",
                    "provider": "gemini",
                    "source_path": str(video_path),
                    "source_format": video_path.suffix,
                    "target_path": str(output_path)
                }
            )

            # Open input and output containers
            input_container = av.open(str(video_path))
            output_container = av.open(str(output_path), mode='w')

            # Get input video stream
            input_video_stream = None
            for stream in input_container.streams.video:
                input_video_stream = stream
                break

            if not input_video_stream:
                logger.warning("No video stream found in input file")
                input_container.close()
                output_container.close()
                return None

            # Create output stream with H.264 codec
            output_video_stream = output_container.add_stream('libx264', rate=input_video_stream.average_rate or 30)
            output_video_stream.width = input_video_stream.width
            output_video_stream.height = input_video_stream.height
            output_video_stream.pix_fmt = 'yuv420p'

            # Copy audio if present
            input_audio_stream = None
            output_audio_stream = None
            for stream in input_container.streams.audio:
                input_audio_stream = stream
                output_audio_stream = output_container.add_stream('aac', rate=stream.rate or 44100)
                break

            # Transcode video frames
            for frame in input_container.decode(video=0):
                for packet in output_video_stream.encode(frame):
                    output_container.mux(packet)

            # Flush encoder
            for packet in output_video_stream.encode():
                output_container.mux(packet)

            # Transcode audio if present
            if input_audio_stream:
                input_container.seek(0)
                for frame in input_container.decode(audio=0):
                    for packet in output_audio_stream.encode(frame):
                        output_container.mux(packet)
                for packet in output_audio_stream.encode():
                    output_container.mux(packet)

            input_container.close()
            output_container.close()

            logger.info(
                "Video format conversion completed",
                extra={
                    "event_type": "video_format_conversion_success",
                    "provider": "gemini",
                    "source_path": str(video_path),
                    "target_path": str(output_path)
                }
            )

            return output_path

        except Exception as e:
            logger.error(
                f"Video format conversion failed: {e}",
                extra={
                    "event_type": "video_format_conversion_error",
                    "provider": "gemini",
                    "source_path": str(video_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None


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
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> AIResult:
        """Generate description from multiple images using Grok Vision (Story P3-2.3 AC5)

        Uses OpenAI-compatible format with multiple image_url blocks.
        """
        start_time = time.time()

        try:
            user_prompt = self._build_multi_image_prompt(
                camera_name, timestamp, detected_objects, len(images_base64), custom_prompt, audio_transcription
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
            raw_response = response.choices[0].message.content.strip()

            # Story P3-6.1: Parse response for description and AI confidence
            description, ai_confidence = self._parse_confidence_response(raw_response)

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
                    "ai_confidence": ai_confidence,
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
                success=True,
                ai_confidence=ai_confidence
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
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
    ) -> AIResult:
        """Generate description using xAI Grok Vision API"""
        start_time = time.time()

        try:
            user_prompt = self._build_user_prompt(camera_name, timestamp, detected_objects, custom_prompt, audio_transcription)

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
            raw_response = response.choices[0].message.content.strip()

            # Story P3-6.1: Parse response for description and AI confidence
            description, ai_confidence = self._parse_confidence_response(raw_response)

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
                    "ai_confidence": ai_confidence,
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
                success=True,
                ai_confidence=ai_confidence
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
        # Story P4-5.4: A/B testing and camera-specific prompts
        self.ab_test_enabled: bool = False  # A/B test mode flag
        self.ab_test_prompt: Optional[str] = None  # Experiment prompt for A/B testing
        self.camera_prompts: Dict[str, str] = {}  # Camera-specific prompt overrides

    def _estimate_image_tokens(self, provider: str, num_images: int, resolution: str = "default") -> int:
        """
        Estimate token usage for multi-image requests when provider doesn't return counts.

        Uses provider-specific token estimates from TOKENS_PER_IMAGE constants.
        This is used when providers like Gemini don't return token usage in responses.

        Args:
            provider: Provider name (openai, grok, claude, gemini)
            num_images: Number of images in the request
            resolution: Image resolution hint ("low_res", "high_res", "default")

        Returns:
            Estimated token count for the images

        Story: P3-2.5
        """
        provider_tokens = TOKENS_PER_IMAGE.get(provider, {"default": 100})

        # Get tokens per image for the resolution
        if resolution in provider_tokens:
            tokens_per_image = provider_tokens[resolution]
        else:
            tokens_per_image = provider_tokens.get("default", 100)

        # Base prompt tokens (approximate)
        base_prompt_tokens = 200

        # Estimate: base prompt + (tokens per image * num images) + expected response (~100 tokens)
        estimated_tokens = base_prompt_tokens + (tokens_per_image * num_images) + 100

        logger.debug(
            f"Estimated {estimated_tokens} tokens for {num_images} images with {provider}",
            extra={
                "provider": provider,
                "num_images": num_images,
                "tokens_per_image": tokens_per_image,
                "estimated_total": estimated_tokens,
            }
        )

        return estimated_tokens

    def _calculate_cost(self, provider: str, tokens: int, input_ratio: float = 0.9) -> float:
        """
        Calculate estimated cost for token usage using provider-specific rates.

        Uses COST_RATES constants with provider-specific input/output pricing.
        Default assumes 90% input tokens, 10% output tokens (typical for vision analysis).

        Args:
            provider: Provider name (openai, grok, claude, gemini)
            tokens: Total token count
            input_ratio: Ratio of tokens that are input vs output (default 0.9)

        Returns:
            Estimated cost in USD

        Story: P3-2.5
        """
        rates = COST_RATES.get(provider, {"input": 0.0001, "output": 0.0003})

        input_tokens = int(tokens * input_ratio)
        output_tokens = tokens - input_tokens

        # Cost = (input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate)
        input_cost = (input_tokens / 1000) * rates["input"]
        output_cost = (output_tokens / 1000) * rates["output"]

        total_cost = input_cost + output_cost

        logger.debug(
            f"Calculated cost ${total_cost:.6f} for {tokens} tokens with {provider}",
            extra={
                "provider": provider,
                "total_tokens": tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": total_cost,
            }
        )

        return total_cost

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
                    'settings_description_prompt',  # Custom description prompt from AI Provider Configuration
                    'settings_ab_test_enabled',  # Story P4-5.4: A/B test toggle
                    'settings_ab_test_prompt',  # Story P4-5.4: Experiment prompt
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

            # Story P4-5.4: Load A/B test settings
            if 'settings_ab_test_enabled' in keys:
                self.ab_test_enabled = keys['settings_ab_test_enabled'].lower() == 'true'
                logger.info(f"A/B test mode: {'enabled' if self.ab_test_enabled else 'disabled'}")
            if 'settings_ab_test_prompt' in keys and keys['settings_ab_test_prompt']:
                self.ab_test_prompt = keys['settings_ab_test_prompt']
                logger.info(f"A/B test experiment prompt loaded: '{self.ab_test_prompt[:50]}...'")

            # Story P4-5.4: Load camera-specific prompt overrides
            from app.models.camera import Camera
            cameras_with_overrides = db.query(Camera).filter(
                Camera.prompt_override.isnot(None)
            ).all()
            self.camera_prompts = {
                cam.id: cam.prompt_override
                for cam in cameras_with_overrides
            }
            if self.camera_prompts:
                logger.info(f"Loaded {len(self.camera_prompts)} camera-specific prompt overrides")

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

        Opens a fresh database session for each query to avoid issues with
        closed sessions from load_api_keys_from_db().

        Returns:
            List of AIProvider enums in configured order
        """
        default_order = [AIProvider.OPENAI, AIProvider.GROK, AIProvider.CLAUDE, AIProvider.GEMINI]

        try:
            import json
            from app.core.database import SessionLocal

            # Open a fresh database session for this query
            # (self.db may be closed after load_api_keys_from_db completes)
            db = SessionLocal()
            try:
                order_setting = db.query(SystemSetting).filter(
                    SystemSetting.key == "ai_provider_order"
                ).first()

                logger.info(f"Provider order query result: setting exists={order_setting is not None}, value={order_setting.value if order_setting else None}")
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
                            logger.info(f"Using configured provider order: {[p.value for p in provider_order]}")
                            return provider_order
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Invalid provider order in settings: {e}, using default")

                return default_order
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to load provider order from database: {e}, using default")
            return default_order

    def _select_prompt_and_variant(
        self,
        camera_id: Optional[str] = None,
        custom_prompt: Optional[str] = None
    ) -> tuple:
        """
        Select the appropriate prompt based on camera override, A/B test, or settings.

        Story P4-5.4: Implements prompt selection logic for A/B testing and
        camera-specific overrides.

        Priority order:
        1. Explicit custom_prompt parameter (e.g., doorbell ring prompts)
        2. Camera-specific override (if camera_id provided and has override)
        3. A/B test selection (if A/B test enabled, 50/50 random)
        4. Global description_prompt from settings
        5. None (use provider's default prompt)

        Args:
            camera_id: Optional camera ID to check for override
            custom_prompt: Explicit custom prompt (highest priority)

        Returns:
            Tuple of (prompt_text, variant)
            - prompt_text: The selected prompt or None
            - variant: 'control', 'experiment', or None (if no A/B test)
        """
        import random

        # 1. If explicit custom_prompt provided, use it (no variant tracking)
        if custom_prompt is not None:
            return (custom_prompt, None)

        # 2. Check camera-specific override
        if camera_id and camera_id in self.camera_prompts:
            logger.debug(f"Using camera-specific prompt override for camera {camera_id[:8]}")
            return (self.camera_prompts[camera_id], None)

        # 3. A/B test selection
        if self.ab_test_enabled and self.ab_test_prompt:
            is_experiment = random.random() < 0.5
            variant = 'experiment' if is_experiment else 'control'
            prompt = self.ab_test_prompt if is_experiment else self.description_prompt
            logger.debug(f"A/B test: selected '{variant}' variant")
            return (prompt, variant)

        # 4. Global description_prompt from settings
        if self.description_prompt:
            return (self.description_prompt, None)

        # 5. No custom prompt
        return (None, None)

    async def generate_description(
        self,
        frame: np.ndarray,
        camera_name: str,
        timestamp: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        sla_timeout_ms: int = 5000,
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        camera_id: Optional[str] = None
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
            audio_transcription: Optional transcribed speech from doorbell audio (Story P3-5.3)
            camera_id: Optional camera ID for camera-specific prompts/A/B testing (Story P4-5.4)

        Returns:
            AIResult with description, confidence, objects, and usage stats
            Note: AIResult.prompt_variant contains A/B test variant if applicable
        """
        start_time = time.time()

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        if detected_objects is None:
            detected_objects = []

        # Story P4-5.4: Select prompt based on camera override, A/B test, or settings
        effective_prompt, prompt_variant = self._select_prompt_and_variant(
            camera_id=camera_id,
            custom_prompt=custom_prompt
        )
        if effective_prompt:
            logger.debug(f"Using selected prompt: '{effective_prompt[:50]}...', variant={prompt_variant}")

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
                provider_type=provider_enum,
                audio_transcription=audio_transcription
            )

            # Track usage with analysis mode (Story P3-2.5, P3-7.1)
            self._track_usage(result, analysis_mode="single_image", image_count=1)

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
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None
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
            audio_transcription: Optional transcribed speech from doorbell audio (Story P3-5.3)

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
                provider_type=provider_enum,
                audio_transcription=audio_transcription
            )

            # Track usage with multi_frame analysis mode (Story P3-2.5)
            # Check if tokens need estimation (e.g., Gemini may not return counts)
            is_estimated = result.tokens_used == 0 and result.success
            if is_estimated:
                # Estimate tokens if provider didn't return counts
                estimated_tokens = self._estimate_image_tokens(
                    result.provider, len(images_base64)
                )
                # Create new result with estimated tokens
                result = AIResult(
                    description=result.description,
                    confidence=result.confidence,
                    objects_detected=result.objects_detected,
                    provider=result.provider,
                    tokens_used=estimated_tokens,
                    response_time_ms=result.response_time_ms,
                    cost_estimate=self._calculate_cost(result.provider, estimated_tokens),
                    success=result.success,
                    error=result.error
                )
            self._track_usage(
                result,
                analysis_mode="multi_frame",
                is_estimated=is_estimated,
                image_count=len(images_base64)
            )

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
                        "is_estimated": is_estimated,
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

    async def describe_video(
        self,
        video_path: "Path",
        camera_name: str,
        timestamp: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        sla_timeout_ms: int = 30000,
        custom_prompt: Optional[str] = None
    ) -> AIResult:
        """
        Generate natural language description from video clip (Story P3-4.3 Task 7).

        Routes to video-capable providers (currently only Gemini supports native upload).
        Falls back to multi-frame or single-frame analysis if video analysis fails.

        Args:
            video_path: Path to video file (MP4, MOV, WebM, etc.)
            camera_name: Name of camera for context
            timestamp: ISO 8601 timestamp of the event (default: now)
            detected_objects: Objects detected by motion detection
            sla_timeout_ms: Maximum time allowed in milliseconds (default: 30000ms = 30s)
            custom_prompt: Optional custom prompt to use instead of default

        Returns:
            AIResult with video description, confidence, objects, and usage stats
        """
        from pathlib import Path

        start_time = time.time()

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        if detected_objects is None:
            detected_objects = []

        # Ensure video_path is a Path object
        if isinstance(video_path, str):
            video_path = Path(video_path)

        # Use custom prompt from settings if no explicit custom_prompt provided
        effective_prompt = custom_prompt
        if effective_prompt is None and self.description_prompt:
            effective_prompt = self.description_prompt
            logger.debug(
                "Using description prompt from settings for video analysis",
                extra={"prompt_preview": effective_prompt[:50] if effective_prompt else ""}
            )

        # Get video-capable providers (P3-4.1)
        video_providers = self.get_video_capable_providers()
        logger.info(
            f"Starting video analysis, {len(video_providers)} video-capable providers available",
            extra={
                "event_type": "ai_video_analysis_start",
                "video_path": str(video_path),
                "camera_name": camera_name,
                "video_providers": video_providers,
            }
        )

        if not video_providers:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "No video-capable providers available",
                extra={"event_type": "ai_video_no_providers"}
            )
            return AIResult(
                description="No video-capable AI providers configured",
                confidence=0,
                objects_detected=detected_objects or ['unknown'],
                provider="none",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error="No video-capable AI providers configured. Currently only Gemini supports native video."
            )

        # Try each video-capable provider
        last_error = None
        for provider_name in video_providers:
            # Check SLA timeout
            elapsed_ms = int((time.time() - start_time) * 1000)
            if elapsed_ms >= sla_timeout_ms:
                logger.warning(
                    f"Video SLA timeout ({sla_timeout_ms}ms) exceeded after {elapsed_ms}ms",
                    extra={
                        "event_type": "ai_video_sla_timeout",
                        "elapsed_ms": elapsed_ms,
                        "sla_timeout_ms": sla_timeout_ms,
                    }
                )
                break

            # Get provider enum and instance
            try:
                provider_enum = AIProvider(provider_name)
            except ValueError:
                logger.warning(f"Unknown provider: {provider_name}")
                continue

            provider = self.providers.get(provider_enum)
            if provider is None:
                logger.debug(
                    f"Provider {provider_name} not configured, skipping",
                    extra={"event_type": "ai_video_provider_not_configured"}
                )
                continue

            # Check if provider supports native video upload (P3-4.3)
            caps = PROVIDER_CAPABILITIES.get(provider_name, {})
            if caps.get("video_method") != "native_upload":
                logger.debug(
                    f"Provider {provider_name} uses {caps.get('video_method', 'none')}, skipping for native video",
                    extra={"event_type": "ai_video_provider_incompatible"}
                )
                continue

            # Check if provider has describe_video method
            if not hasattr(provider, 'describe_video'):
                logger.warning(
                    f"Provider {provider_name} lacks describe_video method",
                    extra={"event_type": "ai_video_provider_no_method"}
                )
                continue

            logger.info(
                f"Attempting video analysis with {provider_name}",
                extra={
                    "event_type": "ai_video_attempt",
                    "provider": provider_name,
                    "elapsed_ms": elapsed_ms,
                }
            )

            try:
                result = await provider.describe_video(
                    video_path=video_path,
                    camera_name=camera_name,
                    timestamp=timestamp,
                    detected_objects=detected_objects,
                    custom_prompt=effective_prompt
                )

                # Track usage with video_native analysis mode (no image_count for video)
                self._track_usage(
                    result,
                    analysis_mode="video_native",
                    is_estimated=True,
                    image_count=None  # Video native doesn't use separate images
                )

                if result.success:
                    total_elapsed_ms = int((time.time() - start_time) * 1000)
                    logger.info(
                        f"Video analysis success with {result.provider}",
                        extra={
                            "event_type": "ai_video_success",
                            "provider": result.provider,
                            "total_elapsed_ms": total_elapsed_ms,
                            "tokens_used": result.tokens_used,
                            "cost_usd": result.cost_estimate,
                            "description_preview": result.description[:50] if result.description else "",
                        }
                    )

                    # Log SLA violations
                    if total_elapsed_ms > sla_timeout_ms:
                        logger.warning(
                            f"Video SLA violation: {total_elapsed_ms}ms > {sla_timeout_ms}ms target",
                            extra={
                                "event_type": "ai_video_sla_violation",
                                "elapsed_ms": total_elapsed_ms,
                                "sla_timeout_ms": sla_timeout_ms,
                            }
                        )

                    return result
                else:
                    last_error = result.error
                    logger.warning(
                        f"{provider_name} video analysis failed: {result.error}",
                        extra={
                            "event_type": "ai_video_provider_failed",
                            "provider": provider_name,
                            "error": result.error,
                        }
                    )

            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"Video analysis exception with {provider_name}: {e}",
                    extra={
                        "event_type": "ai_video_exception",
                        "provider": provider_name,
                        "error_type": type(e).__name__,
                        "error": str(e),
                    }
                )

        # All video providers failed
        total_elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"All video providers failed after {total_elapsed_ms}ms",
            extra={
                "event_type": "ai_video_all_failed",
                "elapsed_ms": total_elapsed_ms,
                "last_error": last_error,
            }
        )
        return AIResult(
            description="Failed to analyze video - all video providers unavailable",
            confidence=0,
            objects_detected=detected_objects or ['unknown'],
            provider="none",
            tokens_used=0,
            response_time_ms=total_elapsed_ms,
            cost_estimate=0.0,
            success=False,
            error=f"All video providers failed. Last error: {last_error}"
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
        provider_type: Optional[AIProvider] = None,
        audio_transcription: Optional[str] = None
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
                custom_prompt=custom_prompt,
                audio_transcription=audio_transcription
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
        provider_type: Optional[AIProvider] = None,
        audio_transcription: Optional[str] = None
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
            audio_transcription: Optional transcribed speech from doorbell audio (Story P3-5.3)

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
                custom_prompt=custom_prompt,
                audio_transcription=audio_transcription
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

    def _track_usage(
        self,
        result: AIResult,
        analysis_mode: Optional[str] = None,
        is_estimated: bool = False,
        image_count: Optional[int] = None
    ):
        """
        Track API usage by persisting to database.

        Stores each AI API call in the ai_usage table for historical tracking
        and cost analysis. If database is not configured, logs a warning.

        Args:
            result: AIResult from provider with usage metadata
            analysis_mode: Type of analysis - "single_image" or "multi_frame" (Story P3-2.5)
            is_estimated: True if token count is estimated rather than from provider (Story P3-2.5)
            image_count: Number of images in multi-image requests (Story P3-7.1)
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
                error=result.error,
                analysis_mode=analysis_mode,
                is_estimated=is_estimated,
                image_count=image_count
            )

            self.db.add(usage_record)
            self.db.commit()

            logger.debug(
                f"Tracked usage: {result.provider} - "
                f"{'success' if result.success else 'failed'} - "
                f"{result.tokens_used} tokens - "
                f"${result.cost_estimate:.6f} - "
                f"mode={analysis_mode or 'unknown'} - "
                f"images={image_count or 1} - "
                f"estimated={is_estimated}",
                extra={
                    "provider": result.provider,
                    "tokens": result.tokens_used,
                    "analysis_mode": analysis_mode,
                    "image_count": image_count,
                    "is_estimated": is_estimated
                }
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

    # =========================================================================
    # Provider Capability Query Methods (Story P3-4.1)
    # =========================================================================

    def get_provider_capabilities(self, provider: str) -> Dict[str, Any]:
        """
        Get capability dictionary for a specific provider (Story P3-4.1 AC1).

        Returns static capability information from PROVIDER_CAPABILITIES constant.
        Does NOT check if provider has a configured API key.

        Args:
            provider: Provider name (openai, grok, claude, gemini)

        Returns:
            Dictionary with capability info:
            {
                "video": bool,
                "max_video_duration": int,
                "max_video_size_mb": int,
                "supported_formats": list[str],
                "max_images": int
            }
            Returns empty dict if provider not found.
        """
        return PROVIDER_CAPABILITIES.get(provider, {})

    def supports_video(self, provider: str) -> bool:
        """
        Check if a provider supports native video input (Story P3-4.1 AC1).

        Args:
            provider: Provider name (openai, grok, claude, gemini)

        Returns:
            True if provider supports video, False otherwise
        """
        capabilities = PROVIDER_CAPABILITIES.get(provider, {})
        return capabilities.get("video", False)

    def get_video_capable_providers(self) -> List[str]:
        """
        Get list of providers that support video AND have configured API keys (Story P3-4.1 AC2).

        This is the primary method for determining which providers can be used for
        video_native analysis mode. It combines static capability information with
        runtime API key configuration.

        Returns:
            List of provider names that support video and are configured.
            Example: ["openai", "gemini"] if both have API keys configured.
        """
        video_providers = []

        for provider_name, capabilities in PROVIDER_CAPABILITIES.items():
            if capabilities.get("video", False):
                # Check if provider has a configured API key
                try:
                    provider_enum = AIProvider(provider_name)
                    if self.providers.get(provider_enum) is not None:
                        video_providers.append(provider_name)
                except ValueError:
                    # Unknown provider enum value, skip
                    pass

        logger.debug(
            f"Video-capable providers with configured keys: {video_providers}",
            extra={"video_providers": video_providers}
        )

        return video_providers

    def get_max_video_duration(self, provider: str) -> int:
        """
        Get maximum video duration in seconds for a provider (Story P3-4.1 AC1).

        Args:
            provider: Provider name (openai, grok, claude, gemini)

        Returns:
            Maximum duration in seconds, or 0 if provider doesn't support video
        """
        capabilities = PROVIDER_CAPABILITIES.get(provider, {})
        return capabilities.get("max_video_duration", 0)

    def get_max_video_size(self, provider: str) -> int:
        """
        Get maximum video file size in MB for a provider (Story P3-4.1 AC1).

        Args:
            provider: Provider name (openai, grok, claude, gemini)

        Returns:
            Maximum size in MB, or 0 if provider doesn't support video
        """
        capabilities = PROVIDER_CAPABILITIES.get(provider, {})
        return capabilities.get("max_video_size_mb", 0)

    def get_provider_order(self) -> List[str]:
        """
        Get the configured provider order for fallback chain (Story P3-4.2).

        Returns the list of provider names in the order they should be tried.
        Uses system settings if configured, otherwise returns default order.

        Returns:
            List of provider names in priority order.
            Example: ["openai", "grok", "claude", "gemini"]
        """
        provider_enums = self._get_provider_order()
        return [p.value for p in provider_enums]

    def get_all_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """
        Get capabilities for all providers with configuration status (Story P3-4.1 AC1).

        Returns complete capability matrix including whether each provider
        has an API key configured. Used by the /api/v1/ai/capabilities endpoint.

        Returns:
            Dictionary mapping provider names to their capabilities with 'configured' flag:
            {
                "openai": {"video": True, ..., "configured": True},
                "claude": {"video": False, ..., "configured": False},
                ...
            }
        """
        result = {}

        for provider_name, capabilities in PROVIDER_CAPABILITIES.items():
            # Check if provider has a configured API key
            configured = False
            try:
                provider_enum = AIProvider(provider_name)
                configured = self.providers.get(provider_enum) is not None
            except ValueError:
                pass

            result[provider_name] = {
                **capabilities,
                "configured": configured
            }

        return result


# Global AI service instance
ai_service = AIService()
