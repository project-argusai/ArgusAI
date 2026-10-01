"""
VisionAnalysisOrchestrator

Central orchestrator for all AI vision analysis (single-frame and multi-frame).

This service owns the complex logic that used to live in AIService:

- Provider fallback chain (configurable order from DB)
- SLA timeout enforcement (5s single image, 25s multi-frame by default)
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
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import numpy as np
from PIL import Image

from app.services.ai_prompt_service import AIPromptService
from app.services.ai_provider_order import (
    classify_provider_error,
    format_chain_failure,
    is_quota_error,
    load_ai_provider_order,
)
from app.services.ai_resilience_service import AIResilienceService
from app.services.ai_types import AIProvider, AIResult, PROVIDER_CAPABILITIES
from app.services.ai_providers.base import AIProviderBase
from app.services.ocr_service import OCRResult
from app.services.ai_cost_and_usage_tracker import get_ai_cost_and_usage_tracker
from app.core.decorators import singleton

logger = logging.getLogger(__name__)

# Oct 1 2026 timings on main (after event-aligned frames and the structured
# prompt): Grok multi-frame calls took 5.5–9.7s, and about 1 in 20 exceeded
# the old 10s budget, so the chain never fell back and the event was saved
# with no description. 25s covers a capped first call plus one fallback.
DEFAULT_MULTI_IMAGE_SLA_MS = 25_000
DEFAULT_SINGLE_IMAGE_SLA_MS = 5_000

# First multi-frame call. 15s covers the observed band and the slow tail,
# and leaves 10s of the 25s budget for a fallback.
MAX_FIRST_PROVIDER_MS = 15_000
MAX_FALLBACK_PROVIDER_MS = 12_000
MIN_PROVIDER_CALL_MS = 2_000
FALLBACK_RESERVE_MS = 10_000
# One more attempt after the first real call fails or times out, even when
# that call already consumed the wall-clock budget.
FALLBACK_GRACE_MS = 10_000

# Single-image chain stays a 5s target. Cap the first call so a hang cannot
# consume it, and keep a short grace for one fallback.
MAX_FIRST_SINGLE_MS = 3_000
MAX_FALLBACK_SINGLE_MS = 3_000
SINGLE_FALLBACK_RESERVE_MS = 2_000
SINGLE_FALLBACK_GRACE_MS = 3_000


def _sla_from_env(name: str, default: int) -> int:
    """Read a positive millisecond budget from the environment.

    A missing value uses ``default``. A malformed or non-positive value also
    uses ``default`` and is not logged (the raw value might not be a number).
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        logger.warning("Ignoring invalid %s; using default %s ms", name, default)
        return default
    if value <= 0:
        logger.warning("Ignoring non-positive %s; using default %s ms", name, default)
        return default
    return value


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

        # Default SLA targets (can be overridden per call).
        # Multi-frame is configurable via AI_MULTI_IMAGE_SLA_MS.
        self.default_single_image_sla_ms = DEFAULT_SINGLE_IMAGE_SLA_MS
        self.default_multi_image_sla_ms = _sla_from_env(
            "AI_MULTI_IMAGE_SLA_MS", DEFAULT_MULTI_IMAGE_SLA_MS
        )
        self.max_first_provider_ms = MAX_FIRST_PROVIDER_MS
        self.max_fallback_provider_ms = MAX_FALLBACK_PROVIDER_MS
        self.min_provider_call_ms = MIN_PROVIDER_CALL_MS
        self.fallback_reserve_ms = FALLBACK_RESERVE_MS
        self.fallback_grace_ms = FALLBACK_GRACE_MS
        self.max_first_single_ms = MAX_FIRST_SINGLE_MS
        self.max_fallback_single_ms = MAX_FALLBACK_SINGLE_MS
        self.single_fallback_reserve_ms = SINGLE_FALLBACK_RESERVE_MS
        self.single_fallback_grace_ms = SINGLE_FALLBACK_GRACE_MS

    def set_providers(self, providers: Dict[AIProvider, AIProviderBase]) -> None:
        """Update the provider map (called during AIService reconfiguration)."""
        self.providers = providers

    def set_prompt_service(self, prompt_service: AIPromptService) -> None:
        self.prompt_service = prompt_service

    def set_resilience_service(self, resilience_service: AIResilienceService) -> None:
        self.resilience_service = resilience_service

    def provider_call_timeout_ms(
        self,
        *,
        elapsed_ms: int,
        sla_timeout_ms: int,
        calls_started: int,
        multi: bool,
    ) -> Optional[int]:
        """Milliseconds to give the next provider call, or None to stop.

        The first call is capped and a reserve is held back so a slow provider
        cannot consume the whole budget. After that first real attempt fails
        or times out, exactly one fallback is still started (using whatever
        budget remains, or a grace window when the budget is already spent).
        Further providers run only while budget remains.
        """
        remaining = sla_timeout_ms - elapsed_ms
        if multi:
            first_cap = self.max_first_provider_ms
            later_cap = self.max_fallback_provider_ms
            reserve = self.fallback_reserve_ms
            grace = self.fallback_grace_ms
        else:
            first_cap = self.max_first_single_ms
            later_cap = self.max_fallback_single_ms
            reserve = self.single_fallback_reserve_ms
            grace = self.single_fallback_grace_ms
        floor = self.min_provider_call_ms

        if calls_started <= 0:
            if remaining <= 0:
                return None
            held = min(reserve, max(0, remaining // 2))
            budget = remaining - held
            if budget >= floor:
                return min(budget, first_cap)
            # Tight budget: still place the call. The fallback uses grace.
            return min(remaining, first_cap)

        if calls_started == 1:
            if remaining >= floor:
                return min(remaining, later_cap)
            if remaining > 0:
                return min(remaining, later_cap)
            return min(grace, later_cap)

        if remaining < floor:
            return None
        return min(remaining, later_cap)

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
            timestamp = datetime.now(timezone.utc).isoformat()
        if detected_objects is None:
            detected_objects = []

        # Use AIPromptService for prompt selection + context
        if self.prompt_service:
            effective_prompt, prompt_variant = self.prompt_service.select_and_build_prompt(
                camera_id=camera_id,
                camera_name=camera_name,
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
            from app.services.identification import ensure_identification_prompt
            effective_prompt = ensure_identification_prompt(effective_prompt)
            logger.debug(f"Using selected prompt: '{effective_prompt[:50]}...', variant={prompt_variant}")

        # Preprocess image (now owned here)
        image_base64 = self._preprocess_image(frame)

        # Get provider order (same helper AIService uses)
        provider_order = self._get_provider_order()
        attempts: List[str] = []
        calls_started = 0

        # Check configured providers
        configured_providers = [p for p in provider_order if self.providers.get(p) is not None]
        if not configured_providers:
            return self._failure_result(
                mode="single_image",
                reason="No AI providers configured. Please add an API key in Settings.",
                attempts=[f"{p.value}:not_configured" for p in provider_order],
                detected_objects=detected_objects,
                response_time_ms=0,
                description="No AI providers configured",
                level="error",
            )

        for provider_enum in provider_order:
            elapsed_ms = int((time.time() - start_time) * 1000)
            provider = self.providers.get(provider_enum)
            if provider is None:
                attempts.append(f"{provider_enum.value}:not_configured")
                logger.warning("%s not configured, skipping", provider_enum.value)
                continue

            # Circuit breaker (delegated to ResilienceService)
            provider_name = provider_enum.value
            can_use = True
            if self.resilience_service:
                can_use = self.resilience_service.can_use_provider(provider_name)

            if not can_use:
                breaker = self.resilience_service.get_provider_breaker(provider_name) if self.resilience_service else None
                state = breaker.state.value if breaker else "open"
                attempts.append(f"{provider_name}:circuit_open")
                logger.warning(
                    f"Skipping {provider_name} - circuit breaker is OPEN",
                    extra={"event_type": "ai_circuit_skipped", "provider": provider_name, "state": state},
                )
                continue

            timeout_ms = self.provider_call_timeout_ms(
                elapsed_ms=elapsed_ms,
                sla_timeout_ms=sla_timeout_ms,
                calls_started=calls_started,
                multi=False,
            )
            if timeout_ms is None:
                return self._failure_result(
                    mode="single_image",
                    reason=f"SLA timeout: {elapsed_ms}ms > {sla_timeout_ms}ms",
                    attempts=attempts,
                    detected_objects=detected_objects,
                    response_time_ms=elapsed_ms,
                    provider="timeout",
                    description=(
                        f"Failed to generate description - SLA timeout exceeded ({elapsed_ms}ms)"
                    ),
                )

            logger.info(
                "Attempting %s (elapsed %dms, call budget %dms)",
                provider_name,
                elapsed_ms,
                timeout_ms,
            )
            calls_started += 1
            result = await self._run_with_deadline(
                provider_name,
                timeout_ms,
                lambda timeout_s, _provider=provider: self._try_with_backoff(
                    _provider,
                    image_base64,
                    camera_name,
                    timestamp,
                    detected_objects,
                    custom_prompt=effective_prompt,
                    provider_type=provider_enum,
                    audio_transcription=audio_transcription,
                    ocr_result=ocr_result,
                    call_timeout_s=timeout_s,
                ),
            )

            # Track usage (now owned here)
            self._track_usage(result, analysis_mode="single_image", image_count=1)
            self._record_provider_outcome(provider_name, result)

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

            failure_class = classify_provider_error(result.error)
            attempts.append(f"{provider_enum.value}:{failure_class}")
            logger.warning(
                "%s failed (%s). Trying next provider...",
                provider_enum.value,
                failure_class,
            )

        total_elapsed_ms = int((time.time() - start_time) * 1000)
        return self._failure_result(
            mode="single_image",
            reason="All providers failed",
            attempts=attempts,
            detected_objects=detected_objects,
            response_time_ms=total_elapsed_ms,
            description="Failed to generate description - all AI providers unavailable",
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
        camera_id: Optional[str] = None,
        subject_crop_count: int = 0,
    ) -> AIResult:
        """
        Multi-frame / multi-image analysis (Phase 3.2).

        Extracted from the old describe_images path. Supports 3-20 frames.
        """
        if sla_timeout_ms is None:
            sla_timeout_ms = self.default_multi_image_sla_ms

        start_time = time.time()

        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
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
            # NOTE: select_and_build_prompt takes camera_id (optional), not
            # camera_name (which this multi-image path doesn't have). Passing
            # camera_name raised TypeError on every multi_frame analysis — the
            # last bug keeping multi-frame from ever completing. Omit it; a
            # missing camera_id just means no camera-specific prompt override.
            effective_prompt, _ = self.prompt_service.select_and_build_prompt(
                camera_id=camera_id,
                camera_name=camera_name,
                custom_prompt=custom_prompt,
                detected_objects=detected_objects,
                timestamp=timestamp,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result,
                analysis_mode="multi_frame",
                num_frames=len(images_base64),
            )

        from app.services.identification import (
            append_subject_crop_note,
            ensure_identification_prompt,
        )
        effective_prompt = ensure_identification_prompt(effective_prompt)
        crop_count = max(0, int(subject_crop_count or 0))
        if crop_count and crop_count < len(images_base64):
            effective_prompt = append_subject_crop_note(
                effective_prompt,
                len(images_base64) - crop_count,
                crop_count,
            )

        # Provider order + fallback loop (same helper AIService uses)
        provider_order = self._get_provider_order()
        attempts: List[str] = []
        calls_started = 0

        configured_providers = [p for p in provider_order if self.providers.get(p) is not None]
        if not configured_providers:
            return self._failure_result(
                mode="multi_frame",
                reason="No AI providers configured. Please add an API key in Settings.",
                attempts=[f"{p.value}:not_configured" for p in provider_order],
                detected_objects=detected_objects,
                response_time_ms=0,
                description="No AI providers configured",
                level="error",
            )

        for provider_enum in provider_order:
            elapsed_ms = int((time.time() - start_time) * 1000)
            provider = self.providers.get(provider_enum)
            if provider is None:
                attempts.append(f"{provider_enum.value}:not_configured")
                logger.warning("%s not configured, skipping", provider_enum.value)
                continue

            provider_name = provider_enum.value
            can_use = True
            if self.resilience_service:
                can_use = self.resilience_service.can_use_provider(provider_name)

            if not can_use:
                attempts.append(f"{provider_name}:circuit_open")
                logger.warning(
                    "Skipping %s - circuit breaker is OPEN",
                    provider_name,
                    extra={"event_type": "ai_circuit_skipped", "provider": provider_name},
                )
                continue

            timeout_ms = self.provider_call_timeout_ms(
                elapsed_ms=elapsed_ms,
                sla_timeout_ms=sla_timeout_ms,
                calls_started=calls_started,
                multi=True,
            )
            if timeout_ms is None:
                return self._failure_result(
                    mode="multi_frame",
                    reason=f"Multi-image SLA timeout: {elapsed_ms}ms > {sla_timeout_ms}ms",
                    attempts=attempts,
                    detected_objects=detected_objects,
                    response_time_ms=elapsed_ms,
                    provider="timeout",
                    description=(
                        f"Failed to generate description - SLA timeout exceeded ({elapsed_ms}ms)"
                    ),
                )

            logger.info(
                "Attempting multi-image with %s (elapsed %dms, call budget %dms)",
                provider_name,
                elapsed_ms,
                timeout_ms,
            )
            calls_started += 1
            result = await self._run_with_deadline(
                provider_name,
                timeout_ms,
                lambda timeout_s, _provider=provider: self._try_multi_image_with_backoff(
                    _provider,
                    images_base64,
                    camera_name,
                    timestamp,
                    detected_objects,
                    custom_prompt=effective_prompt,
                    provider_type=provider_enum,
                    audio_transcription=audio_transcription,
                    ocr_result=ocr_result,
                    call_timeout_s=timeout_s,
                ),
            )

            self._track_usage(result, analysis_mode="multi_frame", image_count=len(images_base64))
            self._record_provider_outcome(provider_name, result)

            if result.success:
                return result

            failure_class = classify_provider_error(result.error)
            attempts.append(f"{provider_enum.value}:{failure_class}")
            logger.warning(
                "%s failed (%s). Trying next provider...",
                provider_enum.value,
                failure_class,
            )

        total_elapsed_ms = int((time.time() - start_time) * 1000)
        return self._failure_result(
            mode="multi_frame",
            reason="All providers failed (multi-frame)",
            attempts=attempts,
            detected_objects=detected_objects,
            response_time_ms=total_elapsed_ms,
            description="Failed to generate description - all AI providers unavailable",
        )

    # =====================================================================
    # Internal Orchestration Helpers (will be moved/adapted)
    # =====================================================================

    def _get_provider_order(self) -> List[AIProvider]:
        """Provider fallback order from ``ai_provider_order``, via the shared helper."""
        return load_ai_provider_order()

    def _failure_result(
        self,
        *,
        mode: str,
        reason: str,
        attempts: List[str],
        detected_objects: Optional[List[str]],
        response_time_ms: int,
        description: str,
        provider: str = "none",
        level: str = "warning",
    ) -> AIResult:
        """Log a chain failure (never success) and return an unsuccessful result.

        ``reason`` and ``attempts`` are status/error-class labels only.
        """
        error = format_chain_failure(reason, attempts)
        log = logger.error if level == "error" else logger.warning
        log("Vision analysis failed (%s): %s", mode, error)
        return AIResult(
            description=description,
            confidence=0,
            objects_detected=detected_objects or ['unknown'],
            provider=provider,
            tokens_used=0,
            response_time_ms=response_time_ms,
            cost_estimate=0.0,
            success=False,
            error=error,
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

    def _retry_policy(self, provider_type: Optional[AIProvider]) -> tuple:
        """Provider-specific retry delays and attempt counts.

        Grok: 2 retries with 0.5s delay (Story P2-5.1 AC6).
        Others: 3 attempts with 2/4/8s exponential backoff.
        Quota and no-credit errors are never retried; see ``_is_retryable``.
        """
        if provider_type == AIProvider.GROK:
            return [0.5, 0.5], 2
        return [2.0, 4.0, 8.0], 3

    @staticmethod
    def _is_retryable(result: AIResult) -> bool:
        """Transient 429/500/503 only. Quota and no-credit errors fail fast."""
        if not result.error or is_quota_error(result.error):
            return False
        err = result.error
        return "429" in err or "500" in err or "503" in err

    def _timed_out_result(self, provider_name: str, elapsed_ms: int) -> AIResult:
        return AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider=provider_name,
            tokens_used=0,
            response_time_ms=elapsed_ms,
            cost_estimate=0.0,
            success=False,
            error="timed out",
        )

    async def _run_with_deadline(self, provider_name: str, timeout_ms: int, factory) -> AIResult:
        """Run one provider attempt and cancel it when ``timeout_ms`` elapses.

        ``factory`` receives the timeout in seconds and returns a coroutine.
        The error body is not logged; only the failure class is.
        """
        timeout_s = max(timeout_ms, 1) / 1000.0
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(factory(timeout_s), timeout=timeout_s)
        except (asyncio.TimeoutError, TimeoutError):
            elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
            logger.warning(
                "%s timed out after %dms (limit %dms)",
                provider_name,
                elapsed_ms,
                timeout_ms,
                extra={
                    "event_type": "ai_provider_timeout",
                    "provider": provider_name,
                    "response_time_ms": elapsed_ms,
                    "timeout_ms": timeout_ms,
                },
            )
            return self._timed_out_result(provider_name, elapsed_ms)

        call_ms = max(0, int((time.perf_counter() - started) * 1000))
        if not result.response_time_ms:
            result.response_time_ms = call_ms
        failure_class = None if result.success else classify_provider_error(result.error)
        logger.info(
            "%s call finished in %dms (limit %dms, success=%s%s)",
            provider_name,
            call_ms,
            timeout_ms,
            result.success,
            "" if failure_class is None else f", {failure_class}",
            extra={
                "event_type": "ai_provider_call_timing",
                "provider": provider_name,
                "response_time_ms": call_ms,
                "timeout_ms": timeout_ms,
                "success": result.success,
                "failure_class": failure_class,
            },
        )
        return result

    def _record_provider_outcome(self, provider_name: str, result: AIResult) -> None:
        """Record the attempt and open a brief circuit on quota or no-credit."""
        if result is not None and not result.success and is_quota_error(result.error):
            self._trip_quota_breaker(provider_name)
        if self.resilience_service and result is not None:
            self.resilience_service.record_result(provider_name, result.success)

    def _trip_quota_breaker(self, provider_name: str) -> None:
        if self.resilience_service is None:
            return
        trip = getattr(self.resilience_service, "trip_quota", None)
        if trip is None:
            return
        try:
            trip(provider_name)
        except Exception as exc:
            logger.warning(
                "Failed to open quota circuit for %s (%s)",
                provider_name,
                type(exc).__name__,
            )

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
        call_timeout_s: Optional[float] = None,
    ) -> AIResult:
        """Try API call with backoff for rate limits.

        Uses provider-specific retry configuration:
        - Grok: 2 retries with 0.5s delay (per Story P2-5.1 AC6)
        - Others: 3 retries with 2/4/8s exponential backoff

        Quota and no-credit errors are not retried. Retries that would run
        past ``call_timeout_s`` are skipped so the fallback chain can proceed.
        """
        delays, max_retries = self._retry_policy(provider_type)
        deadline = None if call_timeout_s is None else time.monotonic() + call_timeout_s
        provider_name = provider_type.value if provider_type else "unknown"
        result = self._timed_out_result(provider_name, 0)

        for attempt in range(max_retries):
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            if deadline is not None and remaining <= 0:
                return self._timed_out_result(provider_name, int((call_timeout_s or 0) * 1000))
            result = await provider.generate_description(
                image_base64,
                camera_name,
                timestamp,
                detected_objects,
                custom_prompt=custom_prompt,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result,
                request_timeout_s=remaining,
            )

            if self._is_retryable(result) and attempt < max_retries - 1:
                delay = delays[attempt] if attempt < len(delays) else delays[-1]
                if deadline is not None and time.monotonic() + delay >= deadline:
                    return result
                logger.warning(
                    "Retryable error, waiting %ss before retry %s/%s",
                    delay,
                    attempt + 2,
                    max_retries,
                )
                await asyncio.sleep(delay)
                continue

            return result

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
        call_timeout_s: Optional[float] = None,
    ) -> AIResult:
        """Try multi-image API call with backoff for rate limits (Story P3-2.3).

        Uses provider-specific retry configuration:
        - Grok: 2 retries with 0.5s delay (per Story P2-5.1 AC6)
        - Others: 3 retries with 2/4/8s exponential backoff

        Quota and no-credit errors are not retried. The whole attempt, including
        retries, is bounded by ``call_timeout_s``.
        """
        delays, max_retries = self._retry_policy(provider_type)
        deadline = None if call_timeout_s is None else time.monotonic() + call_timeout_s
        provider_name = provider_type.value if provider_type else "unknown"
        result = self._timed_out_result(provider_name, 0)

        for attempt in range(max_retries):
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            if deadline is not None and remaining <= 0:
                return self._timed_out_result(provider_name, int((call_timeout_s or 0) * 1000))
            result = await provider.generate_multi_image_description(
                images_base64,
                camera_name,
                timestamp,
                detected_objects,
                custom_prompt=custom_prompt,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result,
                request_timeout_s=remaining,
            )

            if self._is_retryable(result) and attempt < max_retries - 1:
                delay = delays[attempt] if attempt < len(delays) else delays[-1]
                if deadline is not None and time.monotonic() + delay >= deadline:
                    return result
                logger.warning(
                    "Multi-image retryable error, waiting %ss before retry %s/%s",
                    delay,
                    attempt + 2,
                    max_retries,
                    extra={
                        "event_type": "ai_multi_image_retry",
                        "provider": provider_name,
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "delay_seconds": delay,
                    },
                )
                await asyncio.sleep(delay)
                continue

            return result

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
