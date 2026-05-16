"""
AI Service (thin facade / wiring layer).

After Phase 3-4 decomposition, AIService is primarily responsible for:
- Provider configuration and API key management (load_api_keys_from_db, configure_providers)
- Legacy API compatibility (generate_description, describe_images, describe_video)
- Delegation to specialized services:
  - VisionAnalysisOrchestrator (image/video analysis, SLA, fallback)
  - AIPromptService (prompt selection & A/B testing)
  - AIResilienceService (circuit breakers)
  - LiteLLMService (optional multi-provider routing)
  - VideoAnalysisService (native video analysis)
  - Cost tracking via get_cost_tracker()

Most heavy logic has been extracted to dedicated services (see ai_providers/, vision_analysis_orchestrator.py, etc.).
"""

import logging
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

import numpy as np
from sqlalchemy.orm import Session

from app.utils.encryption import decrypt_password
from app.models.system_setting import SystemSetting
from app.models.ai_usage import AIUsage
from app.services.cost_tracker import get_cost_tracker
from app.services.ocr_service import OCRResult, extract_overlay_text, is_ocr_available
from app.services.ai_prompt_service import AIPromptService
from app.services.ai_types import AIProvider, AIResult, PROVIDER_CAPABILITIES
from app.services.video_analysis_service import VideoAnalysisService, video_analysis_service
from app.services.litellm_service import LiteLLMService, litellm_service


logger = logging.getLogger(__name__)

# =============================================================================
# Note: Prompt logic fully extracted to AIPromptService (Phase 2, completed).
# Old prompt builder methods were removed in Phase 2.8.
# =============================================================================

# See: AIPromptService, prompt_templates.py, and the Phase B decomposition plan.
# =============================================================================


# Prompt templates have been extracted to prompt_templates.py (Phase 2 - AIPromptService extraction)
# New code should import from there. These are kept temporarily for backward compatibility.
from app.services.prompt_templates import (
    CONFIDENCE_INSTRUCTION,
    CONFIDENCE_INSTRUCTION_WITH_BOXES,
    MULTI_FRAME_SYSTEM_PROMPT,
    BOUNDING_BOX_INSTRUCTION,
)

# The prompt constants have been successfully moved to prompt_templates.py (Phase 2.4 cleanup).
# The old definitions have been removed. Import from prompt_templates instead.


# Token estimation and cost constants moved to cost_tracker.py (Phase 3.8)

# AI types moved to ai_types.py (Phase 3.4)
# AIProvider, AIResult, and PROVIDER_CAPABILITIES now come from there.


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
        # Story P15-5.1: AI annotations (bounding boxes)
        self.annotations_enabled: bool = False  # Enable bounding box detection
        # LiteLLM Integration (fully delegated to LiteLLMService - Phase 3.6)
        self.use_litellm: bool = False

        # Prompt service (Phase 2)
        self.prompt_service: Optional[AIPromptService] = None

        # Resilience + Orchestrator (Phases 3.1/3.2)
        self.resilience_service: Optional[AIResilienceService] = None
        self.vision_orchestrator: Optional[VisionAnalysisOrchestrator] = None

        # Video Analysis Service (Phase 3.5)
        self.video_analysis_service: Optional[VideoAnalysisService] = None

        # LiteLLM Service (Phase 3.6)
        self.litellm_service: Optional[LiteLLMService] = None

    # _estimate_image_tokens and _calculate_cost moved to cost_tracker.py (Phase 3.8)
    # Use get_cost_tracker().estimate_image_tokens(...) and .calculate_cost(...) instead

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
                    'enable_ai_annotations',  # Story P15-5.1: Enable bounding box annotations
                    'use_litellm',  # LiteLLM Integration: Use unified provider
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

            # Story P15-5.1: Load AI annotations setting
            if 'enable_ai_annotations' in keys:
                self.annotations_enabled = keys['enable_ai_annotations'].lower() == 'true'
            else:
                self.annotations_enabled = False
            # Also update the global singleton so prompt builders can access it
            global ai_service
            if ai_service is not self:
                ai_service.annotations_enabled = self.annotations_enabled
            logger.info(f"AI annotations: {'enabled' if self.annotations_enabled else 'disabled'}")

            # LiteLLM Integration: Load use_litellm setting (delegated to LiteLLMService)
            if 'use_litellm' in keys:
                self.use_litellm = keys['use_litellm'].lower() == 'true'
            else:
                self.use_litellm = False
            logger.info(f"LiteLLM mode flag: {'enabled' if self.use_litellm else 'disabled'} (actual config handled by LiteLLMService)")

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

            # Load Claude model selection
            claude_model = keys.get('settings_claude_model', None)
            if claude_model:
                logger.info(f"Claude model setting loaded: {claude_model}")

            # Configure providers with decrypted keys
            self.configure_providers(
                openai_key=openai_key,
                grok_key=grok_key,
                claude_key=claude_key,
                gemini_key=gemini_key,
                claude_model=claude_model
            )

            logger.info(f"AI providers configured: {len(self.providers)} providers loaded")

            # LiteLLM Integration: Configure LiteLLM provider if enabled
            if self.use_litellm:
                try:
                    from app.services.litellm_provider import configure_litellm_provider
                    self.litellm_provider = configure_litellm_provider(
                        openai_key=openai_key,
                        grok_key=grok_key,
                        claude_key=claude_key,
                        gemini_key=gemini_key,
                        claude_model=claude_model,
                    )
                    if self.litellm_provider.is_configured():
                        logger.info(f"LiteLLM provider configured with: {self.litellm_provider.get_configured_providers()}")
                    else:
                        logger.warning("LiteLLM enabled but no providers configured, falling back to legacy")
                        self.use_litellm = False
                except Exception as e:
                    logger.error(f"Failed to configure LiteLLM, falling back to legacy: {e}")
                    self.use_litellm = False

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
        gemini_key: Optional[str] = None,
        claude_model: Optional[str] = None
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
            claude_model: Claude model to use (e.g., "claude-opus-4-20250514")
        """
        # Initialize resilience service (Phase 3.1)
        self.resilience_service = resilience_service

        active_provider_names = []

        if openai_key:
            self.providers[AIProvider.OPENAI] = OpenAIProvider(openai_key)
            active_provider_names.append("openai")

        if grok_key:
            self.providers[AIProvider.GROK] = GrokProvider(grok_key)
            active_provider_names.append("grok")

        if claude_key:
            self.providers[AIProvider.CLAUDE] = ClaudeProvider(claude_key, model=claude_model)
            active_provider_names.append("claude")

        if gemini_key:
            self.providers[AIProvider.GEMINI] = GeminiProvider(gemini_key)
            active_provider_names.append("gemini")

        if active_provider_names:
            self.resilience_service.initialize_circuit_breakers(active_provider_names)

        # Initialize Prompt Service (Phase 2)
        self.prompt_service = AIPromptService(
            default_prompt=self.description_prompt,
            ab_test_prompt=self.ab_test_prompt,
            ab_test_enabled=self.ab_test_enabled,
            camera_prompts=self.camera_prompts,
            annotations_enabled=self.annotations_enabled,
        )
        logger.info("AIPromptService initialized")

        # Initialize Vision Orchestrator (Phase 3.2)
        self.vision_orchestrator = vision_orchestrator
        self.vision_orchestrator.set_providers(self.providers)
        self.vision_orchestrator.set_prompt_service(self.prompt_service)
        self.vision_orchestrator.set_resilience_service(self.resilience_service)
        logger.info("VisionAnalysisOrchestrator wired")

        # Initialize Video Analysis Service (Phase 3.5)
        self.video_analysis_service = video_analysis_service
        self.video_analysis_service.set_providers(self.providers)
        logger.info("VideoAnalysisService wired")

        # Initialize LiteLLM Service (Phase 3.6)
        self.litellm_service = litellm_service
        if self.use_litellm:
            configured = self.litellm_service.configure(
                openai_key=openai_key,
                grok_key=grok_key,
                claude_key=claude_key,
                gemini_key=gemini_key,
                claude_model=claude_model,
            )
            if not configured:
                self.use_litellm = False
                logger.warning("LiteLLM requested but configuration failed - disabled")

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
            from app.core.database import get_db_session

            # Open a fresh database session for this query
            # (self.db may be closed after load_api_keys_from_db completes)
            with get_db_session() as db:
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
        except Exception as e:
            logger.warning(f"Failed to load provider order from database: {e}, using default")
            return default_order

    # _select_prompt_and_variant has been removed in Phase 2.8.
    # All prompt selection logic now lives in AIPromptService.
    # (Duplicate broken _get_provider_order removed during Phase 3.3 cleanup)

    async def generate_description(
        self,
        frame: np.ndarray,
        camera_name: str,
        timestamp: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        sla_timeout_ms: int = 5000,
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        camera_id: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None
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
            ocr_result: Optional OCR extraction from frame overlay (Story P9-3.2)

        Returns:
            AIResult with description, confidence, objects, and usage stats
            Note: AIResult.prompt_variant contains A/B test variant if applicable
        """
        # Thin delegation to VisionAnalysisOrchestrator (Phase 4.15)
        # All analysis logic (prompt selection, preprocessing, SLA, fallback,
        # circuit breakers, backoff, tracking, resilience) now lives in the orchestrator.
        if not self.vision_orchestrator:
            raise RuntimeError("VisionAnalysisOrchestrator not initialized in AIService")

        return await self.vision_orchestrator.analyze_image(
            frame=frame,
            camera_name=camera_name,
            timestamp=timestamp,
            detected_objects=detected_objects,
            sla_timeout_ms=sla_timeout_ms,
            custom_prompt=custom_prompt,
            audio_transcription=audio_transcription,
            camera_id=camera_id,
            ocr_result=ocr_result,
        )

    async def describe_images(
        self,
        images: List[bytes],
        camera_name: str,
        timestamp: Optional[str] = None,
        detected_objects: Optional[List[str]] = None,
        sla_timeout_ms: int = 10000,
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None
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
            ocr_result: Optional OCR extraction from frame overlay (Story P9-3.2)

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
                # Preprocess via orchestrator (Phase 4.11 - removed duplicate from AIService)
                base64_img = self.vision_orchestrator._preprocess_image_bytes(img_bytes)
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
                "use_litellm": self.use_litellm,
            }
        )

        # LiteLLM Integration (Phase 3.6): Use LiteLLMService if enabled
        if self.use_litellm and self.litellm_service and self.litellm_service.is_enabled():
            return await self.litellm_service.describe_images(
                images_base64=images_base64,
                camera_name=camera_name,
                timestamp=timestamp,
                detected_objects=detected_objects,
                custom_prompt=effective_prompt,
                audio_transcription=audio_transcription,
                ocr_result=ocr_result,
            )

        # Main path: delegate to VisionAnalysisOrchestrator (Phase 4.16)
        # The orchestrator handles preprocessing, provider fallback, SLA, backoff,
        # usage tracking, and resilience. LiteLLM path is handled above.
        return await self.vision_orchestrator.analyze_images(
            images=images,
            camera_name=camera_name,
            timestamp=timestamp,
            detected_objects=detected_objects,
            sla_timeout_ms=sla_timeout_ms,
            custom_prompt=custom_prompt,
            audio_transcription=audio_transcription,
            ocr_result=ocr_result,
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
        """Thin delegation to VideoAnalysisService (Phase 3.5)."""
        if self.video_analysis_service:
            return await self.video_analysis_service.describe_video(
                video_path, camera_name,
                timestamp=timestamp,
                detected_objects=detected_objects,
                sla_timeout_ms=sla_timeout_ms,
                custom_prompt=custom_prompt,
                description_prompt=self.description_prompt,
            )
        raise RuntimeError("VideoAnalysisService not initialized")

    # _preprocess_image / _preprocess_image_bytes removed (Phase 4.11)
    # _try_with_backoff / _try_multi_image_with_backoff removed (Phase 4.13)
    # All analysis, preprocessing, and retry logic now lives in VisionAnalysisOrchestrator.
    # AIService is a thin facade that wires and delegates.

    def _track_usage(
        self,
        result: AIResult,
        analysis_mode: Optional[str] = None,
        is_estimated: bool = False,
        image_count: Optional[int] = None
    ):
        """
        Track API usage by persisting to database.

        Thin delegation to VisionAnalysisOrchestrator (Phase 4.14).
        The canonical implementation lives in the orchestrator (uses get_db_session context).
        """
        if self.vision_orchestrator:
            self.vision_orchestrator._track_usage(
                result,
                analysis_mode=analysis_mode,
                is_estimated=is_estimated,
                image_count=image_count
            )
        else:
            logger.warning("VisionAnalysisOrchestrator not initialized, usage tracking skipped")

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
    # AI Resilience (delegated to AIResilienceService - Phase 3.1)
    # =========================================================================

    def get_ai_resilience_status(self, db: Session) -> dict:
        if self.resilience_service:
            return self.resilience_service.get_ai_resilience_status(db)
        return {"last_reset": None}

    def update_circuit_breaker_config(self, provider: str, config_data: dict, db: Session) -> dict:
        if self.resilience_service:
            return self.resilience_service.update_circuit_breaker_config(provider, config_data, db)
        raise RuntimeError("AIResilienceService not initialized")

    def reset_circuit_breaker(self, provider: str, db: Session = None):
        if self.resilience_service:
            self.resilience_service.reset_circuit_breaker(provider, db)
        else:
            logger.warning("reset_circuit_breaker called before resilience_service initialized")

    # =========================================================================
    # Provider Capability Query Methods (Story P3-4.1)
    # =========================================================================

    def get_provider_capabilities(self, provider: str) -> Dict[str, Any]:
        """Thin delegation to VisionAnalysisOrchestrator (Phase 4.17)."""
        if self.vision_orchestrator:
            return self.vision_orchestrator.get_provider_capabilities(provider)
        return PROVIDER_CAPABILITIES.get(provider, {})

    def supports_video(self, provider: str) -> bool:
        """Thin delegation to VisionAnalysisOrchestrator (Phase 4.17)."""
        if self.vision_orchestrator:
            return self.vision_orchestrator.supports_video(provider)
        capabilities = PROVIDER_CAPABILITIES.get(provider, {})
        return capabilities.get("video", False)

    def get_video_capable_providers(self) -> List[str]:
        """Thin delegation to VisionAnalysisOrchestrator (Phase 4.17)."""
        if self.vision_orchestrator:
            return self.vision_orchestrator.get_video_capable_providers()
        # Fallback (should rarely happen)
        return []

    def get_max_video_duration(self, provider: str) -> int:
        """Thin delegation to VisionAnalysisOrchestrator (Phase 4.17)."""
        if self.vision_orchestrator:
            return self.vision_orchestrator.get_max_video_duration(provider)
        capabilities = PROVIDER_CAPABILITIES.get(provider, {})
        return capabilities.get("max_video_duration", 0)

    def get_max_video_size(self, provider: str) -> int:
        """Thin delegation to VisionAnalysisOrchestrator (Phase 4.17)."""
        if self.vision_orchestrator:
            return self.vision_orchestrator.get_max_video_size(provider)
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
        """Thin delegation to VisionAnalysisOrchestrator (Phase 4.17)."""
        if self.vision_orchestrator:
            return self.vision_orchestrator.get_all_capabilities()
        return {}


# Global AI service instance
ai_service = AIService()
