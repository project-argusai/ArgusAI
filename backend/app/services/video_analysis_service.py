"""
VideoAnalysisService

Responsible for generating natural language descriptions from video clips.

Handles:
- Routing to video-capable providers (primarily Gemini native upload)
- Fallback strategies (multi-frame → single-frame)
- SLA enforcement for video analysis
- Format detection and conversion helpers

Extracted from ai_service.py during Phase 3.5 of the decomposition.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any

from app.services.ai_types import AIProvider, AIResult, PROVIDER_CAPABILITIES

logger = logging.getLogger(__name__)


class VideoAnalysisService:
    """
    Service for video-based AI description generation.

    This service owns the video analysis pipeline, keeping the main AIService
    focused on configuration and orchestration.
    """

    def __init__(self, providers: Optional[dict] = None):
        self.providers = providers or {}

    def set_providers(self, providers: dict):
        """Update the provider map (called during AIService reconfiguration)."""
        self.providers = providers

    async def describe_video(
        self,
        video_path: "Path",
        camera_name: str,
        timestamp: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        sla_timeout_ms: int = 30000,
        custom_prompt: Optional[str] = None,
        description_prompt: Optional[str] = None,
    ) -> AIResult:
        """
        Generate natural language description from video clip.

        Routes to video-capable providers (Gemini native upload preferred).
        Falls back gracefully if no suitable providers are available.
        """
        from pathlib import Path as PathLib

        start_time = time.time()

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        if detected_objects is None:
            detected_objects = []

        if isinstance(video_path, str):
            video_path = PathLib(video_path)

        effective_prompt = custom_prompt
        if effective_prompt is None and description_prompt:
            effective_prompt = description_prompt
            logger.debug(
                "Using description prompt from settings for video analysis",
                extra={"prompt_preview": effective_prompt[:50] if effective_prompt else ""}
            )

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

        last_error = None
        for provider_name in video_providers:
            elapsed_ms = int((time.time() - start_time) * 1000)
            if elapsed_ms >= sla_timeout_ms:
                logger.warning(
                    f"Video SLA timeout ({sla_timeout_ms}ms) exceeded after {elapsed_ms}ms",
                    extra={"event_type": "ai_video_sla_timeout"},
                )
                break

            try:
                provider_enum = AIProvider(provider_name)
            except ValueError:
                continue

            provider = self.providers.get(provider_enum)
            if provider is None:
                continue

            caps = PROVIDER_CAPABILITIES.get(provider_name, {})
            if caps.get("video_method") != "native_upload":
                continue

            if not hasattr(provider, 'describe_video'):
                continue

            try:
                result = await provider.describe_video(
                    video_path=video_path,
                    camera_name=camera_name,
                    timestamp=timestamp,
                    detected_objects=detected_objects,
                    custom_prompt=effective_prompt
                )

                if result.success:
                    return result
                last_error = result.error

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Video analysis failed with {provider_name}: {e}")

        elapsed_ms = int((time.time() - start_time) * 1000)
        return AIResult(
            description="Failed to generate video description",
            confidence=0,
            objects_detected=detected_objects or ['unknown'],
            provider="none",
            tokens_used=0,
            response_time_ms=elapsed_ms,
            cost_estimate=0.0,
            success=False,
            error=last_error or "All video-capable providers failed"
        )

    def get_video_capable_providers(self) -> List[str]:
        """
        Get list of providers that support video AND have configured API keys.
        """
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


# Module-level singleton
video_analysis_service = VideoAnalysisService()