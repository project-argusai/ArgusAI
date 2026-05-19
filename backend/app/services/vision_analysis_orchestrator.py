"""
VisionAnalysisOrchestrator

Central orchestrator for all AI vision analysis (single-frame and multi-frame).

This service owns the complex logic that used to live in AIService:

- Provider fallback chain (configurable order from DB)
- SLA timeout enforcement (<5s p95 target for single image, 10s for multi)
- Circuit breaker integration (via AIResilienceService)
- Rate-limit backoff with provider-specific policies
- Usage/cost tracking
- Final result construction and error aggregation

After Phase 3.2, AIService becomes a much thinner facade responsible for:
- Configuration and provider instantiation
- Wiring PromptService + ResilienceService + this orchestrator
- Exposing high-level APIs to EventProcessor, reanalysis jobs, etc.

This is the second major extraction in the ai_service.py decomposition
(Phase 3.2 following the successful AIResilienceService in 3.1).

# Migrated to @singleton decorator (core.decorators) as part of #450 (Lightweight DI Container).

Story / Issue: Part of #444 + #446 + #450
"""

import asyncio
import base64
import io
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

import numpy as np
from PIL import Image

from app.services.ai_prompt_service import AIPromptService
from app.services.ai_resilience_service import AIResilienceService
from app.services.ai_types import AIProvider, AIResult, PROVIDER_CAPABILITIES
from app.services.ai_providers.base import AIProviderBase
from app.services.ocr_service import OCRResult
from app.core.database import get_db_session
from app.services.ai_cost_and_usage_tracker import get_ai_cost_and_usage_tracker
from app.core.decorators import singleton

logger = logging.getLogger(__name__)


@singleton
class VisionAnalysisOrchestrator:
    """
    Orchestrates vision-based AI description generation across multiple providers
    with resilience, SLA enforcement, and observability.

    Designed to be long-lived and stateless with respect to any single request
    (all per-request state lives in the call).
    """

    def __init__(
        self,
        providers: Optional[Dict[AIProvider, AIProviderBase]] = None,
        prompt_service: Optional[AIPromptService] = None,
        resilience_service: Optional[AIResilienceService] = None,
    ):
        """
        Args:
            providers: Map of AIProvider enum -> concrete provider instance.
                       Usually injected from AIService after configure_providers().
            prompt_service: For prompt selection + context enrichment.
            resilience_service: For circuit breaker checks and result recording.
        """
        self.providers: Dict[AIProvider, AIProviderBase] = providers or {}
        self.prompt_service = prompt_service
        self.resilience_service = resilience_service

        # Default SLA targets (can be overridden per call)
        self.default_single_image_sla_ms = 5000
        self.default_multi_image_sla_ms = 10000

    def set_providers(self, providers: Dict[AIProvider, AIProviderBase]) -> None:
        """Update the provider map (called during AIService reconfiguration)."""
        self.providers = providers

    def set_prompt_service(self, prompt_service: AIPromptService) -> None:
        self.prompt_service = prompt_service

    def set_resilience_service(self, resilience_service: AIResilienceService) -> None:
        self.resilience_service = resilience_service

    # =====================================================================
    # Public Analysis Entry Points (the ones AIService will delegate to)
    # =====================================================================

    async def analyze_image(
        self,
        frame: np.ndarray,
        camera_name: str,
        timestamp: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        sla_timeout_ms: Optional[int] = None,
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        camera_id: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
        analysis_mode: str = "single_image",
    ) -> AIResult:
        """
        Main entry point for single-frame analysis (Phase 3.2).

        This is the extracted version of the old AIService.generate_description.
        Owns SLA enforcement, provider fallback, resilience checks, and backoff.
        """
        if sla_timeout_ms is None:
            sla_timeout_ms = self.default_single_image_sla_ms

        start_time = time.time()

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        if detected_objects is None:
            detected_objects = []

        # Use AIPromptService for prompt selection + context
        if self.prompt_service:
            effective_prompt, prompt_variant = self.prompt_service.select_and_build_prompt(
                camera_id=camera_id,
                custom_prompt=custom_prompt,
                detected_objects=detected_objects,
                timestamp=timestamp,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result,
                analysis_mode=analysis_mode,
            )
        else:
            effective_prompt, prompt_variant = None, None

        if effective_prompt:
            logger.debug(f"Using selected prompt: '{effective_prompt[:50]}...', variant={prompt_variant}")

        # Preprocess image (now owned here)
        image_base64 = self._preprocess_image(frame)

        # Get provider order
        provider_order = self._get_provider_order()
        last_error = None

        # Check configured providers
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
            # SLA check
            elapsed_ms = int((time.time() - start_time) * 1000)
            if elapsed_ms >= sla_timeout_ms:
                logger.warning(
                    f"SLA timeout ({sla_timeout_ms}ms) exceeded after {elapsed_ms}ms. "
                    f"Aborting fallback chain."
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
                logger.warning(f"{provider_enum.value} not configured, skipping")
                continue

            # Circuit breaker (delegated to ResilienceService)
            provider_name = provider_enum.value
            can_use = True
            if self.resilience_service:
                can_use = self.resilience_service.can_use_provider(provider_name)

            if not can_use:
                breaker = self.resilience_service.get_provider_breaker(provider_name) if self.resilience_service else None
                state = breaker.state.value if breaker else "open"
                logger.warning(
                    f"Skipping {provider_name} - circuit breaker is OPEN",
                    extra={"event_type": "ai_circuit_skipped", "provider": provider_name, "state": state},
                )
                continue

            logger.info(f"Attempting {provider_name}... (elapsed: {elapsed_ms}ms)")

            # Backoff + call (now owned by orchestrator)
            result = await self._try_with_backoff(
                provider,
                image_base64,
                camera_name,
                timestamp,
                detected_objects,
                custom_prompt=effective_prompt,
                provider_type=provider_enum,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result
            )

            # Track usage (now owned here)
            self._track_usage(result, analysis_mode="single_image", image_count=1)

            # Record resilience result
            if self.resilience_service and result is not None:
                self.resilience_service.record_result(provider_name, result.success)

            if result.success:
                total_elapsed_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    f"Success with {result.provider}: '{result.description[:50]}...' "
                    f"(total: {total_elapsed_ms}ms, {result.tokens_used} tokens, "
                    f"${result.cost_estimate:.6f})"
                )
                if total_elapsed_ms > sla_timeout_ms:
                    logger.warning(f"SLA violation: {total_elapsed_ms}ms > {sla_timeout_ms}ms target")
                return result
            else:
                last_error = result.error
                logger.warning(f"{provider_enum.value} failed: {result.error}. Trying next provider...")

        # All failed
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

    async def analyze_images(
        self,
        images: List[bytes],
        camera_name: str,
        timestamp: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        sla_timeout_ms: Optional[int] = None,
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
    ) -> AIResult:
        """
        Multi-frame / multi-image analysis (Phase 3.2).

        Extracted from the old describe_images path. Supports 3-20 frames.
        """
        if sla_timeout_ms is None:
            sla_timeout_ms = self.default_multi_image_sla_ms

        start_time = time.time()

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        if detected_objects is None:
            detected_objects = []

        if not images:
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

        # Preprocess all images
        images_base64 = []
        for i, img_bytes in enumerate(images):
            try:
                base64_img = self._preprocess_image_bytes(img_bytes)
                images_base64.append(base64_img)
            except Exception as e:
                logger.warning(f"Failed to preprocess image {i+1}/{len(images)}: {e}")
                continue

        if not images_base64:
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

        # Prompt handling (simplified for multi-frame; full A/B + camera overrides can be added)
        effective_prompt = custom_prompt
        if effective_prompt is None and self.prompt_service:
            # Use prompt service for consistency
            effective_prompt, _ = self.prompt_service.select_and_build_prompt(
                camera_name=camera_name,
                detected_objects=detected_objects,
                timestamp=timestamp,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result,
                analysis_mode="multi_frame",
            )

        # Provider order + fallback loop
        provider_order = self._get_provider_order()
        last_error = None

        configured_providers = [p for p in provider_order if self.providers.get(p) is not None]
        if not configured_providers:
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
            elapsed_ms = int((time.time() - start_time) * 1000)
            if elapsed_ms >= sla_timeout_ms:
                return AIResult(
                    description=f"Failed to generate description - SLA timeout exceeded ({elapsed_ms}ms)",
                    confidence=0,
                    objects_detected=detected_objects or ['unknown'],
                    provider="timeout",
                    tokens_used=0,
                    response_time_ms=elapsed_ms,
                    cost_estimate=0.0,
                    success=False,
                    error=f"Multi-image SLA timeout: {elapsed_ms}ms > {sla_timeout_ms}ms"
                )

            provider = self.providers.get(provider_enum)
            if provider is None:
                continue

            provider_name = provider_enum.value
            can_use = True
            if self.resilience_service:
                can_use = self.resilience_service.can_use_provider(provider_name)

            if not can_use:
                continue

            logger.info(f"Attempting multi-image with {provider_name}...")

            result = await self._try_multi_image_with_backoff(
                provider,
                images_base64,
                camera_name,
                timestamp,
                detected_objects,
                custom_prompt=effective_prompt,
                provider_type=provider_enum,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result
            )

            self._track_usage(result, analysis_mode="multi_frame", image_count=len(images_base64))

            if self.resilience_service and result is not None:
                self.resilience_service.record_result(provider_name, result.success)

            if result.success:
                return result
            else:
                last_error = result.error

        total_elapsed_ms = int((time.time() - start_time) * 1000)
        return AIResult(
            description="Failed to generate description - all AI providers unavailable",
            confidence=0,
            objects_detected=detected_objects or ['unknown'],
            provider="none",
            tokens_used=0,
            response_time_ms=total_elapsed_ms,
            cost_estimate=0.0,
            success=False,
            error=f"All providers failed (multi-frame). Last error: {last_error}"
        )

    # =====================================================================
    # Internal Orchestration Helpers (will be moved/adapted)
    # =====================================================================

    def _get_provider_order(self) -> List[AIProvider]:
        """
        Get the current provider fallback order (from DB settings or default).
        This may eventually move to a dedicated settings service, but for now
        we keep it close to the orchestration logic.
        """
        # Placeholder – actual implementation will be ported from AIService
        return [AIProvider.OPENAI, AIProvider.GROK, AIProvider.CLAUDE, AIProvider.GEMINI]

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
        """
        # Load image from bytes
        image = Image.open(io.BytesIO(image_bytes))

        # Resize if necessary
        max_dim = 2048
        if max(image.size) > max_dim:
            ratio = max_dim / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(f"Resized image from bytes to {new_size}")

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
            logger.warning(f"Image bytes too large ({size_mb:.2f}MB), re-encoded at 70% quality")

        # Base64 encode
        image_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')

        logger.debug(f"Preprocessed image bytes: {len(image_base64)} chars base64, {size_mb:.2f}MB")
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
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
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
                audio_transcription=audio_transcription,
                ocr_result=ocr_result
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
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
    ) -> AIResult:
        """Try multi-image API call with backoff for rate limits (Story P3-2.3).

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
            result = await provider.generate_multi_image_description(
                images_base64,
                camera_name,
                timestamp,
                detected_objects,
                custom_prompt=custom_prompt,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result
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

    # =====================================================================
    # Provider Capability Query Methods (moved from AIService - Phase 4.17)
    # =====================================================================

    def get_provider_capabilities(self, provider: str) -> Dict[str, Any]:
        """Get capability dictionary for a specific provider."""
        return PROVIDER_CAPABILITIES.get(provider, {})

    def supports_video(self, provider: str) -> bool:
        """Check if a provider supports native video input."""
        capabilities = PROVIDER_CAPABILITIES.get(provider, {})
        return capabilities.get("video", False)

    def get_video_capable_providers(self) -> List[str]:
        """Get providers that support video AND have configured API keys."""
        video_providers = []
        for provider_name, capabilities in PROVIDER_CAPABILITIES.items():
            if capabilities.get("video", False):
                try:
                    provider_enum = AIProvider(provider_name)
                    if self.providers.get(provider_enum) is not None:
                        video_providers.append(provider_name)
                except ValueError:
                    pass
        return video_providers

    def get_max_video_duration(self, provider: str) -> int:
        """Get maximum video duration in seconds for a provider."""
        capabilities = PROVIDER_CAPABILITIES.get(provider, {})
        return capabilities.get("max_video_duration", 0)

    def get_max_video_size(self, provider: str) -> int:
        """Get maximum video file size in MB for a provider."""
        capabilities = PROVIDER_CAPABILITIES.get(provider, {})
        return capabilities.get("max_video_size_mb", 0)

    def get_all_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """Get full capabilities matrix with 'configured' status."""
        result = {}
        for provider_name, capabilities in PROVIDER_CAPABILITIES.items():
            configured = False
            try:
                provider_enum = AIProvider(provider_name)
                configured = self.providers.get(provider_enum) is not None
            except ValueError:
                pass
            result[provider_name] = {**capabilities, "configured": configured}
        return result

    def _track_usage(
        self,
        result: AIResult,
        analysis_mode: Optional[str] = None,
        is_estimated: bool = False,
        image_count: Optional[int] = None
    ):
        """
        Track API usage by delegating to AICostAndUsageTracker (#447).
        """
        tracker = get_ai_cost_and_usage_tracker()
        tracker.record_usage(
            provider=result.provider,
            success=result.success,
            tokens_used=result.tokens_used,
            response_time_ms=result.response_time_ms,
            cost_estimate=result.cost_estimate,
            error=result.error,
            analysis_mode=analysis_mode,
            is_estimated=is_estimated,
            image_count=image_count,
        )

    # =====================================================================
    # Diagnostics / Testing Helpers
    # =====================================================================

    def get_configured_providers(self) -> List[str]:
        """Return list of currently configured provider names (for health/debug)."""
        return [p.value for p in self.providers.keys()]

    async def health_check(self) -> Dict[str, Any]:
        """Quick diagnostic for the orchestrator state."""
        return {
            "configured_providers": self.get_configured_providers(),
            "has_prompt_service": self.prompt_service is not None,
            "has_resilience_service": self.resilience_service is not None,
            "status": "ready" if self.providers else "no_providers",
        }


# Backward compatible getter (delegates to @singleton decorator)
def get_vision_analysis_orchestrator() -> "VisionAnalysisOrchestrator":
    """
    Get the global VisionAnalysisOrchestrator instance.

    Returns:
        VisionAnalysisOrchestrator singleton instance

    Note: This is a backward-compatible wrapper. New code should prefer
          VisionAnalysisOrchestrator() directly.
    """
    return VisionAnalysisOrchestrator()


def reset_vision_analysis_orchestrator() -> None:
    """
    Reset the global VisionAnalysisOrchestrator instance.

    Useful for testing (clears provider map, prompt/resilience service references).
    """
    VisionAnalysisOrchestrator._reset_instance()
