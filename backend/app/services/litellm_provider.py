"""
LiteLLM Provider Wrapper for ArgusAI

Provides unified AI provider management using LiteLLM SDK with:
- Multi-provider fallback (OpenAI → Grok → Claude → Gemini)
- Automatic retries with exponential backoff
- Built-in cost tracking
- Vision model support with base64 images

Story: LiteLLM Integration
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from litellm import Router, completion_cost
import litellm

logger = logging.getLogger(__name__)

# LiteLLM model mappings for ArgusAI providers
# Format: provider/model-name
MODEL_MAPPINGS = {
    "openai": "openai/gpt-4o-mini",
    "grok": "xai/grok-2-vision-1212",
    "claude": "anthropic/claude-3-haiku-20240307",
    "gemini": "gemini/gemini-2.5-flash",
}

# Default fallback order (configurable via settings)
DEFAULT_PROVIDER_ORDER = ["openai", "grok", "claude", "gemini"]


@dataclass
class LiteLLMResult:
    """Result from LiteLLM API call"""
    description: str
    confidence: int  # 0-100 (computed from heuristics)
    objects_detected: List[str]
    provider: str  # Which provider was used
    model: str  # Full model name used
    tokens_used: int
    response_time_ms: int
    cost_estimate: float  # USD
    success: bool
    error: Optional[str] = None
    ai_confidence: Optional[int] = None  # 0-100 (from AI response)
    bounding_boxes: Optional[List[Dict[str, Any]]] = None


class LiteLLMProvider:
    """
    Unified AI provider using LiteLLM SDK.

    Handles multi-provider fallback, retries, and cost tracking
    for vision API calls.
    """

    def __init__(
        self,
        openai_key: Optional[str] = None,
        grok_key: Optional[str] = None,
        claude_key: Optional[str] = None,
        gemini_key: Optional[str] = None,
        claude_model: Optional[str] = None,
        provider_order: Optional[List[str]] = None,
        timeout: int = 30,
        num_retries: int = 2,
    ):
        """
        Initialize LiteLLM provider with API keys.

        Args:
            openai_key: OpenAI API key
            grok_key: xAI Grok API key
            claude_key: Anthropic Claude API key
            gemini_key: Google Gemini API key
            claude_model: Optional Claude model override
            provider_order: Order of providers to try (default: openai, grok, claude, gemini)
            timeout: Request timeout in seconds
            num_retries: Number of retries per provider
        """
        self.timeout = timeout
        self.num_retries = num_retries
        self.provider_order = provider_order or DEFAULT_PROVIDER_ORDER
        self.claude_model = claude_model

        # Build model list for Router
        self.model_list = []
        self.configured_providers = set()

        if openai_key:
            self.model_list.append({
                "model_name": "vision",
                "litellm_params": {
                    "model": MODEL_MAPPINGS["openai"],
                    "api_key": openai_key,
                }
            })
            self.configured_providers.add("openai")
            logger.info("LiteLLM: OpenAI provider configured")

        if grok_key:
            self.model_list.append({
                "model_name": "vision",
                "litellm_params": {
                    "model": MODEL_MAPPINGS["grok"],
                    "api_key": grok_key,
                }
            })
            self.configured_providers.add("grok")
            logger.info("LiteLLM: Grok provider configured")

        if claude_key:
            claude_model_name = claude_model or MODEL_MAPPINGS["claude"]
            # Ensure it has the anthropic/ prefix
            if not claude_model_name.startswith("anthropic/"):
                claude_model_name = f"anthropic/{claude_model_name}"
            self.model_list.append({
                "model_name": "vision",
                "litellm_params": {
                    "model": claude_model_name,
                    "api_key": claude_key,
                }
            })
            self.configured_providers.add("claude")
            logger.info(f"LiteLLM: Claude provider configured with model {claude_model_name}")

        if gemini_key:
            self.model_list.append({
                "model_name": "vision",
                "litellm_params": {
                    "model": MODEL_MAPPINGS["gemini"],
                    "api_key": gemini_key,
                }
            })
            self.configured_providers.add("gemini")
            logger.info("LiteLLM: Gemini provider configured")

        # Initialize Router if any providers configured
        self.router = None
        if self.model_list:
            self.router = Router(
                model_list=self.model_list,
                num_retries=num_retries,
                timeout=timeout,
                # Enable fallback through all configured models
                fallbacks=[{"vision": ["vision"]}],
            )
            logger.info(f"LiteLLM Router initialized with {len(self.model_list)} providers")
        else:
            logger.warning("LiteLLM: No providers configured")

    def is_configured(self) -> bool:
        """Check if at least one provider is configured"""
        return bool(self.configured_providers)

    def get_configured_providers(self) -> List[str]:
        """Get list of configured provider names"""
        return list(self.configured_providers)

    async def describe_image(
        self,
        image_base64: str,
        system_prompt: str,
        user_prompt: str,
    ) -> LiteLLMResult:
        """
        Generate description for a single image.

        Args:
            image_base64: Base64-encoded JPEG image
            system_prompt: System prompt for AI
            user_prompt: User prompt with context

        Returns:
            LiteLLMResult with description and metadata
        """
        return await self.describe_images(
            images_base64=[image_base64],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    async def describe_images(
        self,
        images_base64: List[str],
        system_prompt: str,
        user_prompt: str,
    ) -> LiteLLMResult:
        """
        Generate description for multiple images.

        Args:
            images_base64: List of base64-encoded JPEG images
            system_prompt: System prompt for AI
            user_prompt: User prompt with context

        Returns:
            LiteLLMResult with combined description and metadata
        """
        if not self.router:
            return LiteLLMResult(
                description="No AI providers configured",
                confidence=0,
                objects_detected=["unknown"],
                provider="none",
                model="none",
                tokens_used=0,
                response_time_ms=0,
                cost_estimate=0.0,
                success=False,
                error="No AI providers configured. Please add API keys in Settings."
            )

        start_time = time.time()

        # Build message content with images
        content = [{"type": "text", "text": user_prompt}]
        for img_b64 in images_base64:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}"
                }
            })

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ]

        try:
            # Make async completion request
            response = await self.router.acompletion(
                model="vision",
                messages=messages,
                max_tokens=500,
                temperature=0.4,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Extract response text
            response_text = response.choices[0].message.content.strip()

            # Parse confidence and bounding boxes from response
            description, ai_confidence, bounding_boxes = self._parse_response(response_text)

            # Get token usage
            tokens_used = 0
            if hasattr(response, 'usage') and response.usage:
                tokens_used = response.usage.total_tokens or 0

            # Calculate cost using LiteLLM's built-in cost tracking
            try:
                cost = completion_cost(completion_response=response)
            except Exception:
                # Fallback to manual estimation
                cost = tokens_used * 0.00002  # Rough estimate

            # Determine which provider was actually used
            provider = "unknown"
            model = response.model or "unknown"
            if "gpt" in model.lower() or "openai" in model.lower():
                provider = "openai"
            elif "grok" in model.lower() or "xai" in model.lower():
                provider = "grok"
            elif "claude" in model.lower() or "anthropic" in model.lower():
                provider = "claude"
            elif "gemini" in model.lower() or "google" in model.lower():
                provider = "gemini"

            # Extract detected objects from description
            objects = self._extract_objects(description)

            logger.info(
                f"LiteLLM success: {provider}/{model} in {elapsed_ms}ms, "
                f"{tokens_used} tokens, ${cost:.6f}"
            )

            return LiteLLMResult(
                description=description,
                confidence=70,  # Default heuristic confidence
                objects_detected=objects,
                provider=provider,
                model=model,
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True,
                ai_confidence=ai_confidence,
                bounding_boxes=bounding_boxes,
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            logger.error(f"LiteLLM error after {elapsed_ms}ms: {error_msg}")

            return LiteLLMResult(
                description="",
                confidence=0,
                objects_detected=["unknown"],
                provider="error",
                model="none",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=error_msg,
            )

    def _parse_response(self, response_text: str) -> tuple[str, Optional[int], Optional[List[Dict[str, Any]]]]:
        """
        Parse AI response for description, confidence, and bounding boxes.

        Attempts to extract structured JSON response. Falls back to plain text.

        Args:
            response_text: Raw response text from AI

        Returns:
            Tuple of (description, ai_confidence, bounding_boxes)
        """
        import json
        import re

        ai_confidence = None
        bounding_boxes = None

        # First, try to parse the entire response as JSON (handles nested structures)
        try:
            # Find the outermost JSON object
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = response_text[start:end]
                data = json.loads(json_str)
                if "description" in data:
                    description = data.get("description", response_text)
                    ai_confidence = data.get("confidence")
                    bounding_boxes = data.get("bounding_boxes")

                    if isinstance(ai_confidence, (int, float)):
                        ai_confidence = int(ai_confidence)
                    else:
                        ai_confidence = None

                    return description, ai_confidence, bounding_boxes
        except json.JSONDecodeError:
            pass

        # Fallback: Try simple JSON regex (for responses with extra text around JSON)
        json_match = re.search(r'\{[^{}]*"description"[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                description = data.get("description", response_text)
                ai_confidence = data.get("confidence")

                if isinstance(ai_confidence, (int, float)):
                    ai_confidence = int(ai_confidence)
                else:
                    ai_confidence = None

                return description, ai_confidence, None
            except json.JSONDecodeError:
                pass

        # Fallback: look for confidence pattern in plain text
        confidence_match = re.search(r'confidence[:\s]+(\d+)', response_text.lower())
        if confidence_match:
            ai_confidence = int(confidence_match.group(1))
            # Remove confidence statement from description
            description = re.sub(r'\s*confidence[:\s]+\d+\s*', '', response_text, flags=re.IGNORECASE).strip()
        else:
            description = response_text

        return description, ai_confidence, bounding_boxes

    def _extract_objects(self, description: str) -> List[str]:
        """
        Extract detected object types from description.

        Args:
            description: AI-generated description text

        Returns:
            List of detected object types
        """
        objects = []
        description_lower = description.lower()

        # Object detection keywords
        object_keywords = {
            "person": ["person", "man", "woman", "child", "people", "someone", "individual",
                      "pedestrian", "visitor", "delivery", "driver", "worker"],
            "vehicle": ["car", "truck", "van", "suv", "vehicle", "automobile", "motorcycle",
                       "bike", "bicycle", "scooter", "bus"],
            "package": ["package", "box", "parcel", "delivery", "amazon", "fedex", "ups", "usps"],
            "animal": ["dog", "cat", "bird", "animal", "pet", "squirrel", "rabbit", "deer"],
        }

        for obj_type, keywords in object_keywords.items():
            if any(kw in description_lower for kw in keywords):
                objects.append(obj_type)

        return objects if objects else ["unknown"]


# Singleton instance for easy access
_provider_instance: Optional[LiteLLMProvider] = None


def get_litellm_provider() -> Optional[LiteLLMProvider]:
    """Get the singleton LiteLLM provider instance"""
    return _provider_instance


def configure_litellm_provider(
    openai_key: Optional[str] = None,
    grok_key: Optional[str] = None,
    claude_key: Optional[str] = None,
    gemini_key: Optional[str] = None,
    claude_model: Optional[str] = None,
    provider_order: Optional[List[str]] = None,
) -> LiteLLMProvider:
    """
    Configure and return the LiteLLM provider singleton.

    Args:
        openai_key: OpenAI API key
        grok_key: xAI Grok API key
        claude_key: Anthropic Claude API key
        gemini_key: Google Gemini API key
        claude_model: Optional Claude model override
        provider_order: Order of providers to try

    Returns:
        Configured LiteLLMProvider instance
    """
    global _provider_instance

    _provider_instance = LiteLLMProvider(
        openai_key=openai_key,
        grok_key=grok_key,
        claude_key=claude_key,
        gemini_key=gemini_key,
        claude_model=claude_model,
        provider_order=provider_order,
    )

    return _provider_instance
