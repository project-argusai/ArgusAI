"""Unit tests for AI Service"""
import pytest
import tempfile
import os
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services.ai_service import AIService
from app.services.ai_providers.openai_provider import OpenAIProvider
from app.services.ai_providers.claude_provider import ClaudeProvider
from app.services.ai_providers.gemini_provider import GeminiProvider
from app.services.ai_providers.grok_provider import GrokProvider
from app.services.ai_types import AIResult, AIProvider as AIProviderEnum
from app.models.system_setting import SystemSetting


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def sample_frame():
    """Generate a sample camera frame (640x480 RGB)"""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def ai_service_instance():
    """Create AI service instance with mock providers"""
    service = AIService()
    service.configure_providers(
        openai_key="sk-test-openai-key",
        grok_key="xai-test-grok-key",
        claude_key="sk-ant-test-claude-key",
        gemini_key="test-gemini-key"
    )
    return service


# TestImagePreprocessing removed: AIService._preprocess_image was removed in the
# ai_providers decomposition (Phase 4.11). Image preprocessing now lives on
# VisionAnalysisOrchestrator (_preprocess_image / _preprocess_image_bytes).


class TestOpenAIProvider:
    """Test OpenAI provider"""

    @pytest.mark.asyncio
    async def test_successful_description_generation(self):
        """Test successful description from OpenAI"""
        provider = OpenAIProvider("sk-test-key")

        # Mock OpenAI client response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A person wearing a blue jacket is standing at the front door."
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 85
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 35

        with patch.object(provider.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
            result = await provider.generate_description(
                "base64_encoded_image_data",
                "Front Door Camera",
                "2025-11-17T10:00:00",
                ["person"]
            )

        assert result.success is True
        assert result.provider == "openai"
        assert "person" in result.description.lower()
        assert result.confidence > 0
        assert result.tokens_used == 85
        assert result.cost_estimate > 0
        assert 'person' in result.objects_detected

    @pytest.mark.asyncio
    async def test_api_error_handling(self):
        """Test handling of API errors"""
        provider = OpenAIProvider("sk-test-key")

        # Mock API error - use generic Exception since OpenAI APIError signature changed
        with patch.object(
            provider.client.chat.completions,
            'create',
            new=AsyncMock(side_effect=Exception("Rate limit exceeded"))
        ):
            result = await provider.generate_description(
                "base64_data",
                "Camera",
                "2025-11-17T10:00:00",
                []
            )

        assert result.success is False
        assert result.error is not None
        assert "Rate limit" in result.error or "Exception" in result.error

    @pytest.mark.parametrize("description,expected_objects", [
        ("A person wearing a red shirt", ['person']),
        ("A delivery truck is parked outside", ['vehicle']),
        ("A package was left at the door", ['package']),
        ("A dog is running in the yard", ['animal']),
        ("A person with a package near a parked car", ['person', 'vehicle', 'package']),
        ("Empty parking lot", ['unknown']),
    ])
    def test_object_extraction(self, description, expected_objects):
        """Test extracting object types from descriptions"""
        provider = OpenAIProvider("sk-test-key")
        objects = provider._extract_objects(description)
        for expected in expected_objects:
            assert expected in objects, f"Expected {expected} in {objects} for '{description}'"


class TestClaudeProvider:
    """Test Claude provider"""

    @pytest.mark.asyncio
    async def test_successful_description_generation(self):
        """Test successful description from Claude"""
        provider = ClaudeProvider("sk-ant-test-key")

        # Mock Claude client response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "A vehicle approaches the driveway."
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 45
        mock_response.usage.output_tokens = 20

        with patch.object(provider.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
            result = await provider.generate_description(
                "base64_data",
                "Driveway Camera",
                "2025-11-17T10:00:00",
                ["vehicle"]
            )

        assert result.success is True
        assert result.provider == "claude"
        assert result.tokens_used == 65
        assert 'vehicle' in result.objects_detected


class TestGeminiProvider:
    """Test Gemini provider"""

    @pytest.mark.asyncio
    async def test_successful_description_generation(self):
        """Test successful description from Gemini"""
        provider = GeminiProvider("test-gemini-key")

        # Mock Gemini model response
        mock_response = MagicMock()
        mock_response.text = "An animal is visible near the fence."

        # Create valid base64 data (1x1 pixel JPEG)
        import base64
        import io
        from PIL import Image
        img = Image.new('RGB', (1, 1), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        valid_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        with patch.object(provider.model, 'generate_content_async', new=AsyncMock(return_value=mock_response)):
            result = await provider.generate_description(
                valid_base64,
                "Backyard Camera",
                "2025-11-17T10:00:00",
                []
            )

        assert result.success is True
        assert result.provider == "gemini"
        assert 'animal' in result.objects_detected


class TestGrokProvider:
    """Test xAI Grok provider (Story P2-5.1)"""

    @pytest.mark.asyncio
    async def test_successful_description_generation(self):
        """Test successful description from Grok (AC1, AC2, AC3)"""
        provider = GrokProvider("xai-test-key")

        # Mock OpenAI-compatible response (Grok uses OpenAI SDK with different base_url)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A person wearing a red jacket is walking on the driveway."
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 90
        mock_response.usage.prompt_tokens = 55
        mock_response.usage.completion_tokens = 35

        with patch.object(provider.client.chat.completions, 'create', new=AsyncMock(return_value=mock_response)):
            result = await provider.generate_description(
                "base64_encoded_image_data",
                "Driveway Camera",
                "2025-12-04T10:00:00",
                ["person"]
            )

        assert result.success is True
        assert result.provider == "grok"
        assert "person" in result.description.lower()
        assert result.confidence > 0
        assert result.tokens_used == 90
        assert result.cost_estimate > 0
        assert 'person' in result.objects_detected

    @pytest.mark.asyncio
    async def test_api_error_handling(self):
        """Test handling of API errors from Grok"""
        provider = GrokProvider("xai-test-key")

        # Mock API error
        with patch.object(
            provider.client.chat.completions,
            'create',
            new=AsyncMock(side_effect=Exception("429 Too Many Requests"))
        ):
            result = await provider.generate_description(
                "base64_data",
                "Camera",
                "2025-12-04T10:00:00",
                []
            )

        assert result.success is False
        assert result.error is not None
        assert "429" in result.error

    def test_grok_uses_correct_base_url(self):
        """Test that GrokProvider uses xAI base URL (AC2)"""
        provider = GrokProvider("xai-test-key")
        assert provider.client.base_url.host == "api.x.ai"
        assert "v1" in str(provider.client.base_url)

    def test_grok_uses_correct_model(self):
        """Test that GrokProvider resolves to a grok-family multimodal model (AC2).

        Model is resolved dynamically via resolve_model(); without a live xAI
        key it falls back to a known-good grok constant, so assert the family
        rather than a pinned version string.
        """
        provider = GrokProvider("xai-test-key")
        assert isinstance(provider.model, str)
        assert provider.model.startswith("grok")

    @pytest.mark.parametrize("description,expected_objects", [
        ("A person is standing at the door", ['person']),
        ("A car pulls into the driveway", ['vehicle']),
        ("A package has been delivered", ['package']),
        ("A cat is sitting on the porch", ['animal']),
        ("Empty scene with nothing notable", ['unknown']),
    ])
    def test_object_extraction(self, description, expected_objects):
        """Test extracting object types from Grok descriptions"""
        provider = GrokProvider("xai-test-key")
        objects = provider._extract_objects(description)
        for expected in expected_objects:
            assert expected in objects, f"Expected {expected} in {objects} for '{description}'"


# TestGrokRetryLogic removed: it exercised AIService._try_with_backoff, the
# per-provider retry helper removed during the ai_providers decomposition
# (Phase 4.13). Retry/backoff now lives in AIResilienceService.


class TestAIServiceFallback:
    """Test multi-provider fallback logic"""

    @pytest.mark.asyncio
    async def test_fallback_when_primary_fails(self, ai_service_instance, sample_frame):
        """Test fallback to secondary provider when primary fails"""
        # Mock OpenAI to fail
        openai_fail_result = AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider="openai",
            tokens_used=0,
            response_time_ms=100,
            cost_estimate=0.0,
            success=False,
            error="429 Rate limit"
        )

        # Mock Claude to succeed
        claude_success_result = AIResult(
            description="Successfully generated by Claude",
            confidence=75,
            objects_detected=['person'],
            provider="claude",
            tokens_used=50,
            response_time_ms=200,
            cost_estimate=0.01,
            success=True
        )

        with patch.object(
            ai_service_instance.providers[AIProviderEnum.OPENAI],
            'generate_description',
            new=AsyncMock(return_value=openai_fail_result)
        ), patch.object(
            ai_service_instance.providers[AIProviderEnum.CLAUDE],
            'generate_description',
            new=AsyncMock(return_value=claude_success_result)
        ):
            # Disable SLA timeout for this test (exponential backoff can take >5s)
            result = await ai_service_instance.generate_description(
                sample_frame,
                "Test Camera",
                None,
                ['person'],
                sla_timeout_ms=30000  # 30 seconds for testing
            )

        assert result.success is True
        assert result.provider == "claude"
        assert "Claude" in result.description

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, ai_service_instance, sample_frame):
        """Test graceful error when all providers fail"""
        fail_result = AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider="test",
            tokens_used=0,
            response_time_ms=100,
            cost_estimate=0.0,
            success=False,
            error="API error"
        )

        # Mock all providers to fail
        with patch.object(
            ai_service_instance.providers[AIProviderEnum.OPENAI],
            'generate_description',
            new=AsyncMock(return_value=fail_result)
        ), patch.object(
            ai_service_instance.providers[AIProviderEnum.CLAUDE],
            'generate_description',
            new=AsyncMock(return_value=fail_result)
        ), patch.object(
            ai_service_instance.providers[AIProviderEnum.GEMINI],
            'generate_description',
            new=AsyncMock(return_value=fail_result)
        ):
            result = await ai_service_instance.generate_description(
                sample_frame,
                "Test Camera",
                None,
                []
            )

        assert result.success is False
        assert "Failed to generate description" in result.description
        assert result.provider == "none"


class TestUsageTracking:
    """Test usage statistics tracking"""

    def test_usage_stats_no_database(self, ai_service_instance):
        """Usage tracking/stats delegate to AICostAndUsageTracker (#447), so they
        no longer depend on an AIService-held DB session."""
        from unittest.mock import MagicMock, patch

        result = AIResult(
            description="Test",
            confidence=80,
            objects_detected=['person'],
            provider="openai",
            tokens_used=100,
            response_time_ms=500,
            cost_estimate=0.015,
            success=True
        )

        with patch('app.services.ai_service.get_ai_cost_and_usage_tracker') as mock_get_tracker:
            mock_tracker = MagicMock()
            mock_tracker.get_usage_stats.return_value = {'total_calls': 0}
            mock_get_tracker.return_value = mock_tracker

            # Should not raise; delegates to the tracker
            ai_service_instance._track_usage(result)
            mock_tracker.record_usage.assert_called_once()

            stats = ai_service_instance.get_usage_stats()
            assert stats['total_calls'] == 0

    def test_usage_tracking_with_database(self):
        """Test usage tracking delegates to the AICostAndUsageTracker (#447)"""
        service = AIService()

        result = AIResult(
            description="Test description",
            confidence=80,
            objects_detected=['person'],
            provider="openai",
            tokens_used=100,
            response_time_ms=500,
            cost_estimate=0.015,
            success=True
        )

        # _track_usage now delegates to the singleton tracker, not service.db
        with patch('app.services.ai_service.get_ai_cost_and_usage_tracker') as mock_get_tracker:
            mock_tracker = Mock()
            mock_get_tracker.return_value = mock_tracker

            service._track_usage(result)

            # Verify usage was recorded via the tracker with the result fields
            mock_tracker.record_usage.assert_called_once()
            kwargs = mock_tracker.record_usage.call_args.kwargs
            assert kwargs['provider'] == "openai"
            assert kwargs['success'] is True
            assert kwargs['tokens_used'] == 100
            assert kwargs['cost_estimate'] == 0.015

    def test_usage_stats_aggregation_from_database(self):
        """Test usage stats are delegated to the AICostAndUsageTracker (#447)"""
        service = AIService()

        expected_stats = {
            'total_calls': 3,
            'successful_calls': 2,
            'failed_calls': 1,
            'total_tokens': 220,
            'total_cost': 0.033,
            'provider_breakdown': {
                'openai': {'calls': 2, 'success_rate': 100.0},
                'claude': {'calls': 1, 'success_rate': 0.0},
            },
        }

        # Aggregation now lives in the tracker; the facade delegates to it.
        with patch('app.services.ai_service.get_ai_cost_and_usage_tracker') as mock_get_tracker:
            mock_tracker = Mock()
            mock_tracker.get_usage_stats.return_value = expected_stats
            mock_get_tracker.return_value = mock_tracker

            stats = service.get_usage_stats()

        mock_tracker.get_usage_stats.assert_called_once()
        assert stats == expected_stats


# TestExponentialBackoff removed: it exercised AIService._try_with_backoff,
# removed during the ai_providers decomposition (Phase 4.13). Exponential
# backoff / retry now lives in AIResilienceService.


class TestEncryptedAPIKeyLoading:
    """Test encrypted API key loading from database"""

    @pytest.mark.asyncio
    async def test_load_api_keys_from_db_success(self):
        """Test successful loading and decryption of API keys from database"""
        service = AIService()

        # Mock database session and query
        mock_db = Mock()

        # Mock system settings with encrypted keys (including Grok - Story P2-5.1 AC4)
        mock_settings = [
            SystemSetting(key='ai_api_key_openai', value='encrypted:test_openai_key'),
            SystemSetting(key='ai_api_key_grok', value='encrypted:test_grok_key'),
            SystemSetting(key='ai_api_key_claude', value='encrypted:test_claude_key'),
            SystemSetting(key='ai_api_key_gemini', value='encrypted:test_gemini_key')
        ]

        # Create separate mocks for SystemSetting and Camera queries
        def mock_query(model):
            mock_q = Mock()
            mock_filter = Mock()
            mock_q.filter.return_value = mock_filter
            if model == SystemSetting:
                mock_filter.all.return_value = mock_settings
            else:
                # Camera query for prompt overrides returns empty list
                mock_filter.all.return_value = []
            return mock_q

        mock_db.query.side_effect = mock_query

        # Mock decryption
        with patch('app.services.ai_service.decrypt_password') as mock_decrypt:
            mock_decrypt.side_effect = lambda x: x.replace('encrypted:', 'decrypted_')

            await service.load_api_keys_from_db(mock_db)

        # Verify all 4 providers were configured (including Grok)
        assert len(service.providers) == 4
        assert AIProviderEnum.OPENAI in service.providers
        assert AIProviderEnum.GROK in service.providers
        assert AIProviderEnum.CLAUDE in service.providers
        assert AIProviderEnum.GEMINI in service.providers

        # Verify decrypt was called for each key
        assert mock_decrypt.call_count == 4

    @pytest.mark.asyncio
    async def test_load_api_keys_partial_configuration(self):
        """Test loading when only some API keys are configured"""
        service = AIService()

        # Mock database with only OpenAI key
        mock_db = Mock()

        mock_settings = [
            SystemSetting(key='ai_api_key_openai', value='encrypted:test_openai_key')
        ]

        # Create separate mocks for SystemSetting and Camera queries
        def mock_query(model):
            mock_q = Mock()
            mock_filter = Mock()
            mock_q.filter.return_value = mock_filter
            if model == SystemSetting:
                mock_filter.all.return_value = mock_settings
            else:
                # Camera query for prompt overrides returns empty list
                mock_filter.all.return_value = []
            return mock_q

        mock_db.query.side_effect = mock_query

        with patch('app.services.ai_service.decrypt_password') as mock_decrypt:
            mock_decrypt.return_value = 'decrypted_openai_key'

            await service.load_api_keys_from_db(mock_db)

        # Only OpenAI should be configured
        assert len(service.providers) == 1
        assert AIProviderEnum.OPENAI in service.providers
        assert AIProviderEnum.CLAUDE not in service.providers
        assert AIProviderEnum.GEMINI not in service.providers

    @pytest.mark.asyncio
    async def test_load_api_keys_decryption_error(self):
        """Test error handling when decryption fails"""
        service = AIService()

        mock_db = Mock()

        mock_settings = [
            SystemSetting(key='ai_api_key_openai', value='encrypted:invalid_key')
        ]

        # Create separate mocks for SystemSetting and Camera queries
        def mock_query(model):
            mock_q = Mock()
            mock_filter = Mock()
            mock_q.filter.return_value = mock_filter
            if model == SystemSetting:
                mock_filter.all.return_value = mock_settings
            else:
                # Camera query for prompt overrides returns empty list
                mock_filter.all.return_value = []
            return mock_q

        mock_db.query.side_effect = mock_query

        with patch('app.services.ai_service.decrypt_password') as mock_decrypt:
            mock_decrypt.side_effect = ValueError("Failed to decrypt")

            with pytest.raises(ValueError, match="Failed to load AI provider configuration"):
                await service.load_api_keys_from_db(mock_db)

    @pytest.mark.asyncio
    async def test_load_api_keys_no_keys_in_db(self):
        """Test loading when no API keys are configured in database"""
        service = AIService()

        mock_db = Mock()

        # Create separate mocks for SystemSetting and Camera queries
        def mock_query(model):
            mock_q = Mock()
            mock_filter = Mock()
            mock_q.filter.return_value = mock_filter
            mock_filter.all.return_value = []  # No settings or cameras
            return mock_q

        mock_db.query.side_effect = mock_query

        await service.load_api_keys_from_db(mock_db)

        # No providers should be configured
        assert len(service.providers) == 0

    @pytest.mark.asyncio
    async def test_load_description_prompt_from_settings(self):
        """Test that custom description prompt is loaded from settings_description_prompt"""
        service = AIService()

        mock_db = Mock()

        # Mock settings with description prompt and OpenAI key
        custom_prompt = "Describe only people and vehicles in one sentence."
        mock_settings = [
            SystemSetting(key='ai_api_key_openai', value='encrypted:test_openai_key'),
            SystemSetting(key='settings_description_prompt', value=custom_prompt)
        ]

        # Create separate mocks for SystemSetting and Camera queries
        def mock_query(model):
            mock_q = Mock()
            mock_filter = Mock()
            mock_q.filter.return_value = mock_filter
            if model == SystemSetting:
                mock_filter.all.return_value = mock_settings
            else:
                # Camera query for prompt overrides returns empty list
                mock_filter.all.return_value = []
            return mock_q

        mock_db.query.side_effect = mock_query

        with patch('app.services.ai_service.decrypt_password') as mock_decrypt:
            mock_decrypt.return_value = 'decrypted_openai_key'
            await service.load_api_keys_from_db(mock_db)

        # Verify custom prompt was loaded
        assert service.description_prompt == custom_prompt

    @pytest.mark.asyncio
    async def test_description_prompt_used_in_generation(self):
        """Test that custom description prompt is used when generating descriptions"""
        from app.services.ai_providers.base import AIProviderBase

        service = AIService()
        # Set the settings prompt BEFORE configuring providers so the wired
        # AIPromptService uses it as the default/base prompt.
        service.description_prompt = "Keep it short and simple."
        service.configure_providers(openai_key="sk-test-openai-key")

        # Create a mock provider that captures the prompt it receives
        mock_provider = Mock(spec=AIProviderBase)
        captured_prompts = []

        async def mock_generate(*args, **kwargs):
            captured_prompts.append(kwargs.get('custom_prompt'))
            return AIResult(
                description="Test description",
                confidence=80,
                objects_detected=['person'],
                provider='openai',
                tokens_used=100,
                response_time_ms=500,
                cost_estimate=0.001,
                success=True
            )

        mock_provider.generate_description = mock_generate
        # Generation now runs through the VisionAnalysisOrchestrator, which holds
        # the provider dict; swap the OpenAI provider it will call.
        service.providers[AIProviderEnum.OPENAI] = mock_provider
        service.vision_orchestrator.providers[AIProviderEnum.OPENAI] = mock_provider

        # Generate description without explicit custom_prompt
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        result = await service.generate_description(
            frame=frame,
            camera_name="Test Camera",
            timestamp="2025-01-01T00:00:00Z",
            detected_objects=['person']
        )

        # Verify the settings prompt flowed through to the provider. The prompt
        # service may wrap it with context, so assert containment.
        assert len(captured_prompts) == 1
        assert captured_prompts[0] is not None
        assert "Keep it short and simple." in captured_prompts[0]
        assert result.success


class TestProviderOrderConfiguration:
    """Tests for configurable provider order (Story P2-5.2)"""

    def test_get_provider_order_default(self, test_db):
        """Test that default order is returned when no database setting exists"""
        from app.services.ai_service import AIService, AIProvider

        service = AIService()

        # Mock SessionLocal to return test_db which has no ai_provider_order setting
        with patch('app.core.database.SessionLocal', return_value=test_db):
            order = service._get_provider_order()

        assert order == [AIProvider.OPENAI, AIProvider.GROK, AIProvider.CLAUDE, AIProvider.GEMINI]

    def test_get_provider_order_from_database(self, test_db):
        """Test that configured order is read from database"""
        from app.services.ai_service import AIService, AIProvider
        from app.models.system_setting import SystemSetting
        import json

        # Set custom order in database
        custom_order = ["grok", "anthropic", "openai", "google"]
        test_db.add(SystemSetting(key='ai_provider_order', value=json.dumps(custom_order)))
        test_db.commit()

        service = AIService()

        # Mock SessionLocal to return test_db
        with patch('app.core.database.SessionLocal', return_value=test_db):
            order = service._get_provider_order()

        assert order == [AIProvider.GROK, AIProvider.CLAUDE, AIProvider.OPENAI, AIProvider.GEMINI]

    def test_get_provider_order_invalid_json_falls_back(self, test_db):
        """Test that invalid JSON falls back to default order"""
        from app.services.ai_service import AIService, AIProvider
        from app.models.system_setting import SystemSetting

        # Set invalid JSON in database
        test_db.add(SystemSetting(key='ai_provider_order', value='not-valid-json'))
        test_db.commit()

        service = AIService()

        # Mock SessionLocal to return test_db
        with patch('app.core.database.SessionLocal', return_value=test_db):
            order = service._get_provider_order()

        # Should fall back to default
        assert order == [AIProvider.OPENAI, AIProvider.GROK, AIProvider.CLAUDE, AIProvider.GEMINI]

    def test_get_provider_order_empty_falls_back(self, test_db):
        """Test that empty value falls back to default order"""
        from app.services.ai_service import AIService, AIProvider
        from app.models.system_setting import SystemSetting

        # Set empty value in database
        test_db.add(SystemSetting(key='ai_provider_order', value=''))
        test_db.commit()

        service = AIService()

        # Mock SessionLocal to return test_db
        with patch('app.core.database.SessionLocal', return_value=test_db):
            order = service._get_provider_order()

        # Should fall back to default
        assert order == [AIProvider.OPENAI, AIProvider.GROK, AIProvider.CLAUDE, AIProvider.GEMINI]


class TestFallbackChainBehavior:
    """Tests for fallback chain behavior (Story P2-5.3)"""

    @pytest.mark.asyncio
    async def test_grok_429_triggers_fallback(self):
        """Test that Grok 429 rate limit triggers fallback to next provider (AC4)"""
        from app.services.ai_service import AIService, AIProvider as AIProviderEnum, AIResult

        service = AIService()
        service.configure_providers(
            openai_key="sk-test-openai",
            grok_key="xai-test-grok",
            claude_key="sk-ant-test-claude",
            gemini_key="test-gemini"
        )

        # Track which providers were called
        providers_called = []

        # Mock Grok to fail with 429
        grok_fail = AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider="grok",
            tokens_used=0,
            response_time_ms=100,
            cost_estimate=0.0,
            success=False,
            error="429 Rate limit exceeded"
        )

        # Mock Claude to succeed
        claude_success = AIResult(
            description="A person at the door",
            confidence=85,
            objects_detected=['person'],
            provider="claude",
            tokens_used=50,
            response_time_ms=300,
            cost_estimate=0.01,
            success=True
        )

        async def mock_grok_generate(*args, **kwargs):
            providers_called.append('grok')
            return grok_fail

        async def mock_claude_generate(*args, **kwargs):
            providers_called.append('claude')
            return claude_success

        # Set custom order: Grok first, then Claude
        # Create a mock session that returns the custom order
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = Mock(
            value='["grok", "anthropic", "openai", "google"]'
        )
        mock_db.close = Mock()

        with patch('app.core.database.SessionLocal', return_value=mock_db), patch.object(
            service.providers[AIProviderEnum.GROK],
            'generate_description',
            new=mock_grok_generate
        ), patch.object(
            service.providers[AIProviderEnum.CLAUDE],
            'generate_description',
            new=mock_claude_generate
        ):
            sample_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            result = await service.generate_description(
                sample_frame,
                "Test Camera",
                None,
                ['person'],
                sla_timeout_ms=30000
            )

        # Grok should have been tried first, then fell back to Claude
        assert 'grok' in providers_called
        assert 'claude' in providers_called
        assert result.success is True
        assert result.provider == "claude"

    @pytest.mark.asyncio
    async def test_providers_without_keys_are_skipped(self):
        """Test that providers without configured API keys are skipped (AC2)"""
        from app.services.ai_service import AIService, AIProvider as AIProviderEnum

        service = AIService()
        # Only configure OpenAI - others should be skipped
        service.configure_providers(openai_key="sk-test-openai")

        # Verify only OpenAI is configured
        assert AIProviderEnum.OPENAI in service.providers
        assert AIProviderEnum.GROK not in service.providers
        assert AIProviderEnum.CLAUDE not in service.providers
        assert AIProviderEnum.GEMINI not in service.providers

    @pytest.mark.asyncio
    async def test_fallback_chain_respects_configured_order(self, test_db):
        """Test that fallback chain respects ai_provider_order setting (AC1)"""
        from app.services.ai_service import AIService, AIProvider as AIProviderEnum
        from app.models.system_setting import SystemSetting
        import json

        # Set custom order: Gemini → Claude → OpenAI → Grok
        custom_order = ["google", "anthropic", "openai", "grok"]
        test_db.add(SystemSetting(key='ai_provider_order', value=json.dumps(custom_order)))
        test_db.commit()

        service = AIService()

        # Mock SessionLocal to return test_db
        with patch('app.core.database.SessionLocal', return_value=test_db):
            order = service._get_provider_order()

        assert order[0] == AIProviderEnum.GEMINI
        assert order[1] == AIProviderEnum.CLAUDE
        assert order[2] == AIProviderEnum.OPENAI
        assert order[3] == AIProviderEnum.GROK

    @pytest.mark.asyncio
    async def test_integration_first_fails_second_succeeds(self):
        """Integration test: First provider fails, second succeeds, verify result (AC8)"""
        from app.services.ai_service import AIService, AIProvider as AIProviderEnum, AIResult

        service = AIService()
        service.configure_providers(
            openai_key="sk-test-openai",
            grok_key="xai-test-grok"
        )

        call_order = []

        # Mock OpenAI to fail
        openai_fail = AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider="openai",
            tokens_used=0,
            response_time_ms=100,
            cost_estimate=0.0,
            success=False,
            error="Service unavailable"
        )

        # Mock Grok to succeed
        grok_success = AIResult(
            description="A vehicle approaching the driveway",
            confidence=80,
            objects_detected=['vehicle'],
            provider="grok",
            tokens_used=75,
            response_time_ms=400,
            cost_estimate=0.012,
            success=True
        )

        async def mock_openai(*args, **kwargs):
            call_order.append('openai')
            return openai_fail

        async def mock_grok(*args, **kwargs):
            call_order.append('grok')
            return grok_success

        with patch.object(
            service.providers[AIProviderEnum.OPENAI],
            'generate_description',
            new=mock_openai
        ), patch.object(
            service.providers[AIProviderEnum.GROK],
            'generate_description',
            new=mock_grok
        ):
            sample_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            result = await service.generate_description(
                sample_frame,
                "Driveway Camera",
                None,
                [],
                sla_timeout_ms=30000
            )

        # OpenAI tried first, then Grok
        assert call_order[0] == 'openai'
        assert 'grok' in call_order
        assert result.success is True
        assert result.provider == "grok"
        assert 'vehicle' in result.objects_detected

    @pytest.mark.asyncio
    async def test_all_providers_fail_returns_error(self):
        """Integration test: All providers fail returns graceful error (AC8)"""
        from app.services.ai_service import AIService, AIProvider as AIProviderEnum, AIResult

        service = AIService()
        service.configure_providers(
            openai_key="sk-test-openai",
            grok_key="xai-test-grok"
        )

        fail_result = AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider="test",
            tokens_used=0,
            response_time_ms=100,
            cost_estimate=0.0,
            success=False,
            error="API error"
        )

        with patch.object(
            service.providers[AIProviderEnum.OPENAI],
            'generate_description',
            new=AsyncMock(return_value=fail_result)
        ), patch.object(
            service.providers[AIProviderEnum.GROK],
            'generate_description',
            new=AsyncMock(return_value=fail_result)
        ):
            sample_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            result = await service.generate_description(
                sample_frame,
                "Test Camera",
                None,
                [],
                sla_timeout_ms=30000
            )

        assert result.success is False
        assert result.provider == "none"
        assert "Failed to generate" in result.description


# =============================================================================
# Story P3-2.3: Multi-Image Analysis Tests
# =============================================================================


@pytest.fixture
def sample_image_bytes():
    """Generate sample JPEG image bytes for testing multi-image analysis"""
    from PIL import Image
    import io

    # Create a simple test image
    img = Image.new('RGB', (100, 100), color='blue')
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    return buffer.getvalue()


@pytest.fixture
def sample_image_bytes_list():
    """Generate list of 3 sample JPEG image bytes for testing multi-image analysis"""
    from PIL import Image
    import io

    images = []
    colors = ['red', 'green', 'blue']
    for color in colors:
        img = Image.new('RGB', (100, 100), color=color)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        images.append(buffer.getvalue())
    return images


# TestMultiImagePreprocessing removed: AIService._preprocess_image_bytes was
# removed in the ai_providers decomposition (Phase 4.11). Byte preprocessing
# now lives on VisionAnalysisOrchestrator._preprocess_image_bytes.


# TestMultiImagePromptBuilder removed: the providers' _build_multi_image_prompt
# method was removed in the ai_providers decomposition. Prompt assembly now
# lives in AIPromptService; providers accept a finished custom_prompt and no
# longer build their own multi-image prompt strings.


class TestOpenAIMultiImageProvider:
    """Test OpenAI multi-image provider (Story P3-2.3 AC2)"""

    @pytest.mark.asyncio
    async def test_openai_multi_image_success(self):
        """Test successful multi-image description from OpenAI (AC2)"""
        provider = OpenAIProvider("sk-test-key")

        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "The sequence shows a person walking up the driveway, "
            "approaching the front door, and ringing the doorbell."
        )
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 200
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 50

        with patch.object(
            provider.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response)
        ) as mock_create:
            result = await provider.generate_multi_image_description(
                images_base64=["base64_img1", "base64_img2", "base64_img3"],
                camera_name="Front Door Camera",
                timestamp="2025-12-06T10:00:00",
                detected_objects=["person"]
            )

            # Verify API was called with multiple images
            call_args = mock_create.call_args
            messages = call_args.kwargs.get('messages') or call_args[1].get('messages') or call_args[0][0]
            user_content = messages[1]['content']

            # Count image_url blocks
            image_blocks = [c for c in user_content if c.get('type') == 'image_url']
            assert len(image_blocks) == 3  # 3 images sent

        assert result.success is True
        assert result.provider == "openai"
        assert "person" in result.description.lower()
        assert result.tokens_used == 200
        assert 'person' in result.objects_detected

    @pytest.mark.asyncio
    async def test_openai_multi_image_error_handling(self):
        """Test OpenAI multi-image error handling"""
        provider = OpenAIProvider("sk-test-key")

        with patch.object(
            provider.client.chat.completions,
            'create',
            new=AsyncMock(side_effect=Exception("API Error"))
        ):
            result = await provider.generate_multi_image_description(
                images_base64=["base64_img1", "base64_img2"],
                camera_name="Camera",
                timestamp="2025-12-06T10:00:00",
                detected_objects=[]
            )

        assert result.success is False
        assert result.error is not None
        assert "API Error" in result.error


class TestGrokMultiImageProvider:
    """Test Grok multi-image provider (Story P3-2.3 AC5)"""

    @pytest.mark.asyncio
    async def test_grok_multi_image_success(self):
        """Test successful multi-image description from Grok (AC5)"""
        provider = GrokProvider("xai-test-key")

        # Mock response (OpenAI-compatible format)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "A delivery truck arrives, driver exits with a package, "
            "walks to the door and leaves the package."
        )
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 180
        mock_response.usage.prompt_tokens = 130
        mock_response.usage.completion_tokens = 50

        with patch.object(
            provider.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response)
        ) as mock_create:
            result = await provider.generate_multi_image_description(
                images_base64=["img1", "img2", "img3", "img4"],
                camera_name="Driveway",
                timestamp="2025-12-06T14:00:00",
                detected_objects=["vehicle", "person"]
            )

            # Verify uses OpenAI-compatible format
            call_args = mock_create.call_args
            messages = call_args.kwargs.get('messages') or call_args[1].get('messages')
            user_content = messages[1]['content']

            # Verify image blocks
            image_blocks = [c for c in user_content if c.get('type') == 'image_url']
            assert len(image_blocks) == 4

        assert result.success is True
        assert result.provider == "grok"
        assert 'vehicle' in result.objects_detected or 'package' in result.objects_detected


class TestClaudeMultiImageProvider:
    """Test Claude multi-image provider (Story P3-2.3 AC3)"""

    @pytest.mark.asyncio
    async def test_claude_multi_image_success(self):
        """Test successful multi-image description from Claude (AC3)"""
        provider = ClaudeProvider("sk-ant-test-key")

        # Mock Claude response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = (
            "The frames capture a cat crossing the yard, pausing to look around, "
            "then continuing toward the fence."
        )
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 140
        mock_response.usage.output_tokens = 45

        with patch.object(
            provider.client.messages,
            'create',
            new=AsyncMock(return_value=mock_response)
        ) as mock_create:
            result = await provider.generate_multi_image_description(
                images_base64=["img1", "img2", "img3"],
                camera_name="Backyard",
                timestamp="2025-12-06T08:00:00",
                detected_objects=["animal"]
            )

            # Verify Claude-specific format with image blocks
            call_args = mock_create.call_args
            messages = call_args.kwargs.get('messages') or call_args[1].get('messages')
            content = messages[0]['content']

            # Verify image blocks use source.type=base64
            image_blocks = [c for c in content if c.get('type') == 'image']
            assert len(image_blocks) == 3
            for block in image_blocks:
                assert block['source']['type'] == 'base64'
                assert block['source']['media_type'] == 'image/jpeg'

        assert result.success is True
        assert result.provider == "claude"
        assert 'animal' in result.objects_detected


class TestGeminiMultiImageProvider:
    """Test Gemini multi-image provider (Story P3-2.3 AC4)"""

    @pytest.mark.asyncio
    async def test_gemini_multi_image_success(self):
        """Test successful multi-image description from Gemini (AC4)"""
        import base64
        from PIL import Image
        import io

        provider = GeminiProvider("test-gemini-key")

        # Create valid base64 images
        valid_base64_images = []
        for _ in range(3):
            img = Image.new('RGB', (10, 10), color='yellow')
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG')
            valid_base64_images.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))

        # Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = "Multiple frames show a person jogging past the house."

        with patch.object(
            provider.model,
            'generate_content_async',
            new=AsyncMock(return_value=mock_response)
        ) as mock_create:
            result = await provider.generate_multi_image_description(
                images_base64=valid_base64_images,
                camera_name="Street View",
                timestamp="2025-12-06T07:00:00",
                detected_objects=["person"]
            )

            # Verify Gemini parts format
            call_args = mock_create.call_args
            parts = call_args[0][0]

            # First part should be prompt text
            assert isinstance(parts[0], str)
            # Subsequent parts should be image dicts with inline_data
            image_parts = [p for p in parts[1:] if isinstance(p, dict)]
            assert len(image_parts) == 3
            for part in image_parts:
                assert 'mime_type' in part
                assert 'data' in part
                assert part['mime_type'] == 'image/jpeg'

        assert result.success is True
        assert result.provider == "gemini"
        assert 'person' in result.objects_detected


class TestDescribeImagesMethod:
    """Test AIService.describe_images facade method (Story P3-2.3 AC1)"""

    @pytest.mark.asyncio
    async def test_describe_images_returns_combined_description(
        self, ai_service_instance, sample_image_bytes_list
    ):
        """Test describe_images returns single combined description (AC1)"""
        mock_result = AIResult(
            description="A person walks across the driveway over multiple frames.",
            confidence=85,
            objects_detected=['person'],
            provider="openai",
            tokens_used=150,
            response_time_ms=800,
            cost_estimate=0.02,
            success=True
        )

        with patch.object(
            ai_service_instance.providers[AIProviderEnum.OPENAI],
            'generate_multi_image_description',
            new=AsyncMock(return_value=mock_result)
        ):
            result = await ai_service_instance.describe_images(
                images=sample_image_bytes_list,
                camera_name="Front Door",
                timestamp="2025-12-06T10:00:00",
                detected_objects=["person"]
            )

        assert result.success is True
        assert result.provider == "openai"
        assert "person" in result.description.lower()
        assert result.tokens_used > 0

    @pytest.mark.asyncio
    async def test_describe_images_empty_list_returns_error(self, ai_service_instance):
        """Test describe_images with empty image list returns error"""
        result = await ai_service_instance.describe_images(
            images=[],
            camera_name="Camera",
            timestamp="2025-12-06T10:00:00",
            detected_objects=[]
        )

        assert result.success is False
        assert "Empty image list" in result.error or "No images" in result.description

    @pytest.mark.asyncio
    async def test_describe_images_single_image_works(
        self, ai_service_instance, sample_image_bytes
    ):
        """Test describe_images works with single image (edge case)"""
        mock_result = AIResult(
            description="Single frame shows a package at the door.",
            confidence=80,
            objects_detected=['package'],
            provider="openai",
            tokens_used=100,
            response_time_ms=500,
            cost_estimate=0.01,
            success=True
        )

        with patch.object(
            ai_service_instance.providers[AIProviderEnum.OPENAI],
            'generate_multi_image_description',
            new=AsyncMock(return_value=mock_result)
        ):
            result = await ai_service_instance.describe_images(
                images=[sample_image_bytes],
                camera_name="Porch",
                timestamp="2025-12-06T15:00:00",
                detected_objects=["package"]
            )

        assert result.success is True
        assert 'package' in result.objects_detected

    @pytest.mark.asyncio
    async def test_describe_images_no_providers_configured(self, sample_image_bytes_list):
        """Test describe_images returns error when no providers configured"""
        service = AIService()
        # No providers configured

        result = await service.describe_images(
            images=sample_image_bytes_list,
            camera_name="Camera",
            timestamp="2025-12-06T10:00:00",
            detected_objects=[]
        )

        # A bare AIService has no providers/orchestrator wired, so the
        # multi-image path fails gracefully before any provider call.
        assert result.success is False
        assert result.provider == "none"
        assert result.error is not None


class TestMultiImageFallbackChain:
    """Test multi-image fallback chain behavior (Story P3-2.3)"""

    @pytest.mark.asyncio
    async def test_multi_image_fallback_when_primary_fails(
        self, ai_service_instance, sample_image_bytes_list
    ):
        """Test fallback chain works for multi-image requests"""
        # Mock OpenAI to fail
        openai_fail = AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider="openai",
            tokens_used=0,
            response_time_ms=100,
            cost_estimate=0.0,
            success=False,
            error="Rate limit exceeded"
        )

        # Mock Grok to succeed
        grok_success = AIResult(
            description="Sequential analysis shows person arriving with package.",
            confidence=80,
            objects_detected=['person', 'package'],
            provider="grok",
            tokens_used=180,
            response_time_ms=600,
            cost_estimate=0.02,
            success=True
        )

        with patch.object(
            ai_service_instance.providers[AIProviderEnum.OPENAI],
            'generate_multi_image_description',
            new=AsyncMock(return_value=openai_fail)
        ), patch.object(
            ai_service_instance.providers[AIProviderEnum.GROK],
            'generate_multi_image_description',
            new=AsyncMock(return_value=grok_success)
        ):
            result = await ai_service_instance.describe_images(
                images=sample_image_bytes_list,
                camera_name="Front Door",
                timestamp="2025-12-06T10:00:00",
                detected_objects=["person"],
                sla_timeout_ms=30000
            )

        assert result.success is True
        assert result.provider == "grok"

    @pytest.mark.asyncio
    async def test_multi_image_all_providers_fail(
        self, ai_service_instance, sample_image_bytes_list
    ):
        """Test graceful error when all providers fail for multi-image"""
        fail_result = AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider="test",
            tokens_used=0,
            response_time_ms=100,
            cost_estimate=0.0,
            success=False,
            error="API error"
        )

        with patch.object(
            ai_service_instance.providers[AIProviderEnum.OPENAI],
            'generate_multi_image_description',
            new=AsyncMock(return_value=fail_result)
        ), patch.object(
            ai_service_instance.providers[AIProviderEnum.GROK],
            'generate_multi_image_description',
            new=AsyncMock(return_value=fail_result)
        ), patch.object(
            ai_service_instance.providers[AIProviderEnum.CLAUDE],
            'generate_multi_image_description',
            new=AsyncMock(return_value=fail_result)
        ), patch.object(
            ai_service_instance.providers[AIProviderEnum.GEMINI],
            'generate_multi_image_description',
            new=AsyncMock(return_value=fail_result)
        ):
            result = await ai_service_instance.describe_images(
                images=sample_image_bytes_list,
                camera_name="Test Camera",
                timestamp="2025-12-06T10:00:00",
                detected_objects=[]
            )

        assert result.success is False
        assert result.provider == "none"
        assert "Failed to generate" in result.description


# TestMultiImageRetryLogic removed: it exercised
# AIService._try_multi_image_with_backoff, removed during the ai_providers
# decomposition (Phase 4.13). Retry/backoff now lives in AIResilienceService.


class TestMultiImageUsageTracking:
    """Test usage tracking for multi-image requests (Story P3-2.3)"""

    @pytest.mark.asyncio
    async def test_multi_image_usage_tracked(
        self, ai_service_instance, sample_image_bytes_list
    ):
        """Test that usage is tracked for multi-image requests"""
        mock_result = AIResult(
            description="Multi-image analysis complete.",
            confidence=85,
            objects_detected=['person'],
            provider="openai",
            tokens_used=250,
            response_time_ms=900,
            cost_estimate=0.03,
            success=True
        )

        # The multi-image path runs through VisionAnalysisOrchestrator, which
        # records usage via the singleton AICostAndUsageTracker (#447), not
        # service.db. Patch the tracker where the orchestrator imports it.
        with patch('app.services.vision_analysis_orchestrator.get_ai_cost_and_usage_tracker') as mock_get_tracker, \
            patch.object(
                ai_service_instance.providers[AIProviderEnum.OPENAI],
                'generate_multi_image_description',
                new=AsyncMock(return_value=mock_result)
            ):
            mock_tracker = Mock()
            mock_get_tracker.return_value = mock_tracker

            result = await ai_service_instance.describe_images(
                images=sample_image_bytes_list,
                camera_name="Camera",
                timestamp="2025-12-06T10:00:00",
                detected_objects=["person"]
            )

        assert result.success is True
        # Verify usage was recorded via the tracker
        assert mock_tracker.record_usage.called


# TestTokenEstimation removed: AIService._estimate_image_tokens was removed in
# the ai_providers decomposition. Token estimation now lives in CostTracker
# (get_cost_tracker().estimate_image_tokens(...)).


# TestCostCalculation removed: AIService._calculate_cost was removed in the
# ai_providers decomposition. Cost calculation now lives in CostTracker
# (get_cost_tracker().calculate_cost(...)) with a different signature.


class TestAnalysisModeTracking:
    """Test analysis_mode tracking in AIUsage records (Story P3-2.5)"""

    @pytest.mark.asyncio
    async def test_single_image_tracking_sets_analysis_mode(self, ai_service_instance):
        """Test single-image tracking sets analysis_mode='single_image' (AC2)"""
        mock_result = AIResult(
            description="Single image analysis.",
            confidence=90,
            objects_detected=['person'],
            provider="openai",
            tokens_used=100,
            response_time_ms=500,
            cost_estimate=0.01,
            success=True
        )

        # _track_usage delegates to the singleton tracker (#447)
        with patch('app.services.ai_service.get_ai_cost_and_usage_tracker') as mock_get_tracker:
            mock_tracker = Mock()
            mock_get_tracker.return_value = mock_tracker

            ai_service_instance._track_usage(mock_result, analysis_mode="single_image")

        # Check that usage was recorded with analysis_mode
        mock_tracker.record_usage.assert_called_once()
        kwargs = mock_tracker.record_usage.call_args.kwargs
        assert kwargs["analysis_mode"] == "single_image"
        assert kwargs["is_estimated"] is False

    @pytest.mark.asyncio
    async def test_multi_image_tracking_sets_analysis_mode(
        self, ai_service_instance, sample_image_bytes_list
    ):
        """Test multi-image tracking sets analysis_mode='multi_frame' (AC2)"""
        mock_result = AIResult(
            description="Multi-frame analysis complete.",
            confidence=85,
            objects_detected=['person'],
            provider="openai",
            tokens_used=250,
            response_time_ms=900,
            cost_estimate=0.03,
            success=True
        )

        # _track_usage delegates to the singleton tracker (#447)
        with patch('app.services.ai_service.get_ai_cost_and_usage_tracker') as mock_get_tracker:
            mock_tracker = Mock()
            mock_get_tracker.return_value = mock_tracker

            ai_service_instance._track_usage(mock_result, analysis_mode="multi_frame")

        # Check that usage was recorded with analysis_mode
        mock_tracker.record_usage.assert_called_once()
        kwargs = mock_tracker.record_usage.call_args.kwargs
        assert kwargs["analysis_mode"] == "multi_frame"
        assert kwargs["is_estimated"] is False

    @pytest.mark.asyncio
    async def test_multi_image_estimation_when_no_tokens_returned(
        self, ai_service_instance, sample_image_bytes_list
    ):
        """Test is_estimated=True when provider returns no token count (AC3)"""
        # Simulate Gemini returning 0 tokens (needs estimation)
        mock_result = AIResult(
            description="Gemini analysis complete.",
            confidence=85,
            objects_detected=['person'],
            provider="gemini",
            tokens_used=0,  # No tokens returned by provider
            response_time_ms=900,
            cost_estimate=0.0,
            success=True
        )

        # _track_usage delegates to the singleton tracker (#447)
        with patch('app.services.ai_service.get_ai_cost_and_usage_tracker') as mock_get_tracker:
            mock_tracker = Mock()
            mock_get_tracker.return_value = mock_tracker

            ai_service_instance._track_usage(
                mock_result,
                analysis_mode="multi_frame",
                is_estimated=True
            )

        # Check that the estimation flag was set
        mock_tracker.record_usage.assert_called_once()
        kwargs = mock_tracker.record_usage.call_args.kwargs
        assert kwargs["is_estimated"] is True
        assert kwargs["analysis_mode"] == "multi_frame"


# =============================================================================
# Story P3-4.1: Provider Capability Detection Tests
# =============================================================================


class TestProviderCapabilities:
    """Test provider capability detection (Story P3-4.1 AC1)"""

    def test_provider_capabilities_constant_contains_all_providers(self):
        """Test PROVIDER_CAPABILITIES contains all four providers"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        expected_providers = ["openai", "grok", "claude", "gemini"]
        assert set(PROVIDER_CAPABILITIES.keys()) == set(expected_providers)

    def test_provider_capabilities_openai_video_via_frame_extraction(self):
        """Test OpenAI capabilities have video=True with frame_extraction method (P3-4.2)"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        openai_caps = PROVIDER_CAPABILITIES["openai"]
        # P3-4.2: OpenAI supports video via frame extraction, not native upload
        assert openai_caps["video"] is True
        assert openai_caps["video_method"] == "frame_extraction"
        assert openai_caps["max_video_duration"] == 60
        assert openai_caps["max_video_size_mb"] == 50
        assert openai_caps["max_frames"] == 10
        assert "mp4" in openai_caps["supported_formats"]
        assert openai_caps["max_images"] == 10
        assert openai_caps["supports_audio_transcription"] is True

    def test_provider_capabilities_gemini_supports_video(self):
        """Test Gemini capabilities include video=True with native_upload (AC1, P3-4.3)"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        gemini_caps = PROVIDER_CAPABILITIES["gemini"]
        assert gemini_caps["video"] is True
        assert gemini_caps["video_method"] == "native_upload"  # Gemini uploads video directly
        assert gemini_caps["max_video_duration"] == 300  # 5 min practical limit (tokens)
        assert gemini_caps["max_video_size_mb"] == 2048  # 2GB via File API
        assert gemini_caps["inline_max_size_mb"] == 20  # Inline data limit
        assert gemini_caps["max_frames"] == 0  # N/A for native upload
        assert "mp4" in gemini_caps["supported_formats"]
        assert gemini_caps["max_images"] == 16
        assert gemini_caps["supports_audio"] is True  # Gemini handles video audio natively

    def test_provider_capabilities_claude_no_video(self):
        """Test Claude capabilities have video=False (AC1)"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        claude_caps = PROVIDER_CAPABILITIES["claude"]
        assert claude_caps["video"] is False
        assert claude_caps["video_method"] is None
        assert claude_caps["max_video_duration"] == 0
        assert claude_caps["max_video_size_mb"] == 0
        assert claude_caps["max_frames"] == 0
        assert claude_caps["supported_formats"] == []
        assert claude_caps["max_images"] == 20
        assert claude_caps["supports_audio_transcription"] is False

    def test_provider_capabilities_grok_video_via_frame_extraction(self):
        """Test Grok capabilities have video=True with frame_extraction method (P3-4.2)"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        grok_caps = PROVIDER_CAPABILITIES["grok"]
        # Grok supports video via frame extraction (same pattern as OpenAI)
        assert grok_caps["video"] is True
        assert grok_caps["video_method"] == "frame_extraction"
        assert grok_caps["max_video_duration"] == 60
        assert grok_caps["max_video_size_mb"] == 50
        assert grok_caps["max_frames"] == 10
        assert "mp4" in grok_caps["supported_formats"]
        assert grok_caps["max_images"] == 10


class TestAIServiceCapabilityMethods:
    """Test AIService capability query methods (Story P3-4.1 AC1, AC2)"""

    def test_get_provider_capabilities_openai(self, ai_service_instance):
        """Test get_provider_capabilities returns correct data for OpenAI"""
        caps = ai_service_instance.get_provider_capabilities("openai")

        # P3-4.2: OpenAI supports video via frame extraction
        assert caps["video"] is True
        assert caps["video_method"] == "frame_extraction"
        assert caps["max_video_duration"] == 60
        assert caps["max_video_size_mb"] == 50
        assert caps["max_frames"] == 10
        assert "mp4" in caps["supported_formats"]
        assert caps["max_images"] == 10

    def test_get_provider_capabilities_claude(self, ai_service_instance):
        """Test get_provider_capabilities returns correct data for Claude"""
        caps = ai_service_instance.get_provider_capabilities("claude")

        assert caps["video"] is False
        assert caps["max_video_duration"] == 0
        assert caps["max_images"] == 20

    def test_get_provider_capabilities_unknown_provider(self, ai_service_instance):
        """Test get_provider_capabilities returns empty dict for unknown provider"""
        caps = ai_service_instance.get_provider_capabilities("unknown_provider")
        assert caps == {}

    def test_supports_video_openai(self, ai_service_instance):
        """Test supports_video returns True for OpenAI (P3-4.2: supports via frame extraction)"""
        # P3-4.2: OpenAI supports video via frame extraction
        assert ai_service_instance.supports_video("openai") is True

    def test_supports_video_gemini(self, ai_service_instance):
        """Test supports_video returns True for Gemini"""
        assert ai_service_instance.supports_video("gemini") is True

    def test_supports_video_claude(self, ai_service_instance):
        """Test supports_video returns False for Claude"""
        assert ai_service_instance.supports_video("claude") is False

    def test_supports_video_grok(self, ai_service_instance):
        """Test supports_video returns True for Grok (P3-4.2: supports via frame extraction)"""
        assert ai_service_instance.supports_video("grok") is True

    def test_supports_video_unknown_provider(self, ai_service_instance):
        """Test supports_video returns False for unknown provider"""
        assert ai_service_instance.supports_video("unknown") is False

    def test_get_video_capable_providers_all_configured(self, ai_service_instance):
        """Test get_video_capable_providers returns OpenAI, Grok, and Gemini when configured"""
        video_providers = ai_service_instance.get_video_capable_providers()

        # ai_service_instance fixture configures all providers
        # P3-4.2: OpenAI and Grok support video via frame extraction
        # P3-4.3: Gemini supports native video upload
        assert "openai" in video_providers
        assert "grok" in video_providers
        assert "gemini" in video_providers
        # Claude does not support video
        assert "claude" not in video_providers

    def test_get_video_capable_providers_none_configured(self):
        """Test get_video_capable_providers returns empty list when no providers configured"""
        service = AIService()
        # Don't configure any providers

        video_providers = service.get_video_capable_providers()
        assert video_providers == []

    def test_get_video_capable_providers_only_non_video_configured(self):
        """Test get_video_capable_providers returns Grok when only Claude and Grok configured"""
        service = AIService()
        # Configure Claude (no video) and Grok (video via frame extraction)
        service.configure_providers(
            openai_key=None,
            grok_key="xai-test-grok-key",
            claude_key="sk-ant-test-claude-key",
            gemini_key=None
        )

        video_providers = service.get_video_capable_providers()
        # Grok now supports video via frame extraction (P3-4.2)
        assert "grok" in video_providers
        assert "claude" not in video_providers

    def test_get_max_video_duration_openai(self, ai_service_instance):
        """Test get_max_video_duration returns 60 for OpenAI (P3-4.2: frame extraction)"""
        # P3-4.2: OpenAI supports video via frame extraction
        assert ai_service_instance.get_max_video_duration("openai") == 60

    def test_get_max_video_duration_claude(self, ai_service_instance):
        """Test get_max_video_duration returns 0 for Claude (no video)"""
        assert ai_service_instance.get_max_video_duration("claude") == 0

    def test_get_max_video_size_gemini(self, ai_service_instance):
        """Test get_max_video_size returns 2048 for Gemini (2GB via File API)"""
        # P3-4.3: Gemini supports up to 2GB via File API
        assert ai_service_instance.get_max_video_size("gemini") == 2048

    def test_get_max_video_size_grok(self, ai_service_instance):
        """Test get_max_video_size returns 50 for Grok (P3-4.2: frame extraction)"""
        # Grok supports video via frame extraction
        assert ai_service_instance.get_max_video_size("grok") == 50

    def test_get_all_capabilities_structure(self, ai_service_instance):
        """Test get_all_capabilities returns correct structure with configured flag"""
        all_caps = ai_service_instance.get_all_capabilities()

        # Should have all four providers
        assert set(all_caps.keys()) == {"openai", "grok", "claude", "gemini"}

    @pytest.mark.parametrize("provider", ["openai", "grok", "claude", "gemini"])
    def test_get_all_capabilities_provider_structure(self, ai_service_instance, provider):
        """Test each provider has required capability fields"""
        all_caps = ai_service_instance.get_all_capabilities()
        caps = all_caps[provider]
        assert "configured" in caps
        assert "video" in caps
        assert "max_video_duration" in caps
        assert "max_video_size_mb" in caps
        assert "supported_formats" in caps
        assert "max_images" in caps

    def test_get_all_capabilities_configured_flags(self, ai_service_instance):
        """Test get_all_capabilities shows correct configured status"""
        # ai_service_instance fixture configures all providers
        all_caps = ai_service_instance.get_all_capabilities()

        assert all_caps["openai"]["configured"] is True
        assert all_caps["grok"]["configured"] is True
        assert all_caps["claude"]["configured"] is True
        assert all_caps["gemini"]["configured"] is True

    def test_get_all_capabilities_unconfigured(self):
        """Test get_all_capabilities shows configured=False for unconfigured providers"""
        service = AIService()
        # Only configure OpenAI
        service.configure_providers(
            openai_key="sk-test-openai-key",
            grok_key=None,
            claude_key=None,
            gemini_key=None
        )

        all_caps = service.get_all_capabilities()

        assert all_caps["openai"]["configured"] is True
        assert all_caps["grok"]["configured"] is False
        assert all_caps["claude"]["configured"] is False
        assert all_caps["gemini"]["configured"] is False


# =============================================================================
# Story P3-4.2: OpenAI Video Analysis via Frame Extraction Tests
# =============================================================================


# TestOpenAIDescribeVideo removed: OpenAIProvider.describe_video and
# OpenAIProvider._transcribe_audio were removed in the ai_providers
# decomposition. Frame-extraction video analysis now lives in
# VideoAnalysisService; OpenAI/Grok providers no longer expose describe_video.


# TestOpenAITranscribeAudio removed: OpenAIProvider._transcribe_audio was
# removed in the ai_providers decomposition (audio transcription is no longer
# a provider method).


class TestProviderCapabilitiesVideoMethod:
    """Test PROVIDER_CAPABILITIES video_method field (Story P3-4.2 Task 7.5)"""

    def test_openai_video_method_is_frame_extraction(self):
        """Test OpenAI video_method is 'frame_extraction'"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        assert PROVIDER_CAPABILITIES["openai"]["video_method"] == "frame_extraction"

    def test_grok_video_method_is_frame_extraction(self):
        """Test Grok video_method is 'frame_extraction'"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        assert PROVIDER_CAPABILITIES["grok"]["video_method"] == "frame_extraction"

    def test_gemini_video_method_is_native_upload(self):
        """Test Gemini video_method is 'native_upload'"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        assert PROVIDER_CAPABILITIES["gemini"]["video_method"] == "native_upload"

    def test_claude_video_method_is_none(self):
        """Test Claude video_method is None (no video support)"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        assert PROVIDER_CAPABILITIES["claude"]["video_method"] is None

    def test_openai_supports_audio_transcription(self):
        """Test OpenAI supports_audio_transcription is True"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        assert PROVIDER_CAPABILITIES["openai"]["supports_audio_transcription"] is True

    def test_grok_no_audio_transcription(self):
        """Test Grok supports_audio_transcription is False"""
        from app.services.ai_service import PROVIDER_CAPABILITIES

        assert PROVIDER_CAPABILITIES["grok"]["supports_audio_transcription"] is False


class TestGetProviderOrder:
    """Test AIService.get_provider_order() public method"""

    def test_get_provider_order_returns_string_list(self, test_db):
        """Test get_provider_order returns list of string provider names"""
        service = AIService()

        # Mock SessionLocal to return test_db which has no ai_provider_order setting
        with patch('app.core.database.SessionLocal', return_value=test_db):
            order = service.get_provider_order()

        assert isinstance(order, list)
        assert all(isinstance(p, str) for p in order)
        assert order == ["openai", "grok", "claude", "gemini"]

    def test_get_provider_order_from_database(self, test_db):
        """Test get_provider_order reads from database"""
        from app.models.system_setting import SystemSetting
        import json

        # Set custom order in database
        custom_order = ["grok", "anthropic", "openai", "google"]
        test_db.add(SystemSetting(key='ai_provider_order', value=json.dumps(custom_order)))
        test_db.commit()

        service = AIService()

        # Mock SessionLocal to return test_db
        with patch('app.core.database.SessionLocal', return_value=test_db):
            order = service.get_provider_order()

        assert order == ["grok", "claude", "openai", "gemini"]


# TestGeminiDescribeVideo removed: this class tested GeminiProvider's native
# video-upload path (format helpers _is_supported_video_format /
# _get_video_mime_type / _build_video_prompt / _get_video_duration, plus
# file-not-found and size-limit checks). Those methods were removed in the
# ai_providers decomposition. GeminiProvider.describe_video still exists but now
# simply frame-extracts and reuses the multi-image path, so the old
# native-upload assertions no longer apply. (It also imported GeminiProvider
# from app.services.ai_service, which no longer re-exports provider classes.)


class TestAIServiceDescribeVideo:
    """Tests for AIService.describe_video() orchestration (Story P3-4.3 Task 7)"""

    @pytest.fixture
    def ai_service_with_gemini(self):
        """Create AIService with only Gemini configured"""
        service = AIService()
        service.configure_providers(
            openai_key=None,
            grok_key=None,
            claude_key=None,
            gemini_key="test-gemini-key"
        )
        return service

    @pytest.mark.asyncio
    async def test_describe_video_no_video_providers(self):
        """Test describe_video returns error when no video providers configured"""
        service = AIService()
        # Wire the services (VideoAnalysisService) but configure no API keys,
        # so there are no video-capable providers available.
        service.configure_providers()

        result = await service.describe_video(
            video_path="/fake/path.mp4",
            camera_name="Test Camera"
        )

        assert result.success is False
        assert "No video-capable" in result.error

    @pytest.mark.asyncio
    async def test_describe_video_routes_to_gemini(self, ai_service_with_gemini, tmp_path):
        """Test describe_video routes to Gemini provider"""
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.services.ai_service import AIProvider

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video" * 100)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.description = "Test description"
        mock_result.provider = "gemini"
        mock_result.tokens_used = 1000
        mock_result.cost_estimate = 0.001
        mock_result.confidence = 75
        mock_result.objects_detected = ["person"]
        mock_result.response_time_ms = 500
        mock_result.error = None

        # Mock the Gemini provider's describe_video method
        gemini_provider = ai_service_with_gemini.providers[AIProvider.GEMINI]
        with patch.object(gemini_provider, 'describe_video', new_callable=AsyncMock) as mock_describe:
            mock_describe.return_value = mock_result

            result = await ai_service_with_gemini.describe_video(
                video_path=video_path,
                camera_name="Front Door",
                detected_objects=["person"]
            )

        assert result.success is True
        assert result.provider == "gemini"
        mock_describe.assert_called_once()


# TestGeminiVideoFormatConversion removed: GeminiProvider._convert_video_format
# was removed in the ai_providers decomposition (the current describe_video
# frame-extracts and does not attempt format conversion). It also imported
# GeminiProvider from app.services.ai_service, which no longer re-exports it.


# TestPromptBuildingWithContext removed: it tested the providers'
# _build_user_prompt / _build_multi_image_prompt methods, removed in the
# ai_providers decomposition. Context-aware prompt assembly now lives in
# AIPromptService; providers no longer build their own prompt strings.
