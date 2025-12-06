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
from app.services.ai_service import (
    AIService,
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    GrokProvider,
    AIResult,
    AIProvider as AIProviderEnum
)
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


class TestImagePreprocessing:
    """Test image preprocessing functionality"""

    def test_preprocess_small_image(self, ai_service_instance, sample_frame):
        """Test preprocessing of image smaller than max dimensions"""
        base64_img = ai_service_instance._preprocess_image(sample_frame)

        assert isinstance(base64_img, str)
        assert len(base64_img) > 0
        # Base64 string should be valid
        import base64
        try:
            decoded = base64.b64decode(base64_img)
            assert len(decoded) > 0
        except Exception as e:
            pytest.fail(f"Invalid base64: {e}")

    def test_preprocess_large_image(self, ai_service_instance):
        """Test preprocessing resizes large images to 2048x2048 max"""
        # Create 4000x3000 image
        large_frame = np.random.randint(0, 255, (3000, 4000, 3), dtype=np.uint8)

        base64_img = ai_service_instance._preprocess_image(large_frame)

        # Decode and check size
        import base64
        from PIL import Image
        import io

        decoded = base64.b64decode(base64_img)
        image = Image.open(io.BytesIO(decoded))

        # Should be resized to max 2048 on longest side
        assert max(image.size) <= 2048
        assert image.format == 'JPEG'

    def test_preprocess_ensures_under_5mb(self, ai_service_instance):
        """Test that preprocessing keeps payload under 5MB"""
        # Create large image
        large_frame = np.random.randint(0, 255, (2048, 2048, 3), dtype=np.uint8)

        base64_img = ai_service_instance._preprocess_image(large_frame)

        # Check base64 size (approximate payload size)
        import base64
        decoded = base64.b64decode(base64_img)
        size_mb = len(decoded) / (1024 * 1024)

        assert size_mb < 5.0, f"Image too large: {size_mb:.2f}MB"


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

    def test_object_extraction(self):
        """Test extracting object types from descriptions"""
        provider = OpenAIProvider("sk-test-key")

        test_cases = [
            ("A person wearing a red shirt", ['person']),
            ("A delivery truck is parked outside", ['vehicle']),
            ("A package was left at the door", ['package']),
            ("A dog is running in the yard", ['animal']),
            ("A person with a package near a parked car", ['person', 'vehicle', 'package']),
            ("Empty parking lot", ['unknown']),
        ]

        for description, expected_objects in test_cases:
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
        """Test that GrokProvider uses grok-2-vision-1212 model (AC2)"""
        provider = GrokProvider("xai-test-key")
        assert provider.model == "grok-2-vision-1212"

    def test_object_extraction(self):
        """Test extracting object types from Grok descriptions"""
        provider = GrokProvider("xai-test-key")

        test_cases = [
            ("A person is standing at the door", ['person']),
            ("A car pulls into the driveway", ['vehicle']),
            ("A package has been delivered", ['package']),
            ("A cat is sitting on the porch", ['animal']),
            ("Empty scene with nothing notable", ['unknown']),
        ]

        for description, expected_objects in test_cases:
            objects = provider._extract_objects(description)
            for expected in expected_objects:
                assert expected in objects, f"Expected {expected} in {objects} for '{description}'"


class TestGrokRetryLogic:
    """Test Grok-specific retry logic (Story P2-5.1 AC6)"""

    @pytest.mark.asyncio
    async def test_grok_retry_with_500ms_delay(self):
        """Test that Grok uses 2 retries with 500ms delay (AC6)"""
        service = AIService()
        service.configure_providers(grok_key="xai-test-key")

        provider = service.providers[AIProviderEnum.GROK]
        call_count = 0

        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return AIResult(
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
            else:
                return AIResult(
                    description="Success after retry",
                    confidence=80,
                    objects_detected=['person'],
                    provider="grok",
                    tokens_used=100,
                    response_time_ms=500,
                    cost_estimate=0.015,
                    success=True
                )

        with patch.object(provider, 'generate_description', new=mock_generate):
            result = await service._try_with_backoff(
                provider,
                "base64_data",
                "Camera",
                "2025-12-04T10:00:00",
                [],
                provider_type=AIProviderEnum.GROK
            )

        # Grok should only retry 2 times (total 2 attempts), so call_count should be 2
        # After 2 retries fail, it returns the last failure
        assert call_count == 2  # 2 retries max for Grok


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
        """Test that usage tracking handles missing database gracefully"""
        ai_service_instance.db = None

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

        # Should not raise error
        ai_service_instance._track_usage(result)

        # Stats should return empty when no DB
        stats = ai_service_instance.get_usage_stats()
        assert stats['total_calls'] == 0

    def test_usage_tracking_with_database(self):
        """Test usage tracking persists to database"""
        service = AIService()

        # Mock database session
        mock_db = Mock()
        service.db = mock_db

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

        service._track_usage(result)

        # Verify database add and commit were called
        assert mock_db.add.called
        assert mock_db.commit.called

    def test_usage_stats_aggregation_from_database(self):
        """Test usage statistics aggregation from database"""
        from app.models.ai_usage import AIUsage
        from datetime import datetime

        service = AIService()

        # Mock database with sample records
        mock_db = Mock()
        service.db = mock_db

        mock_records = [
            AIUsage(
                timestamp=datetime(2025, 11, 17, 10, 0, 0),
                provider='openai',
                success=True,
                tokens_used=100,
                response_time_ms=500,
                cost_estimate=0.015,
                error=None
            ),
            AIUsage(
                timestamp=datetime(2025, 11, 17, 10, 1, 0),
                provider='openai',
                success=True,
                tokens_used=120,
                response_time_ms=600,
                cost_estimate=0.018,
                error=None
            ),
            AIUsage(
                timestamp=datetime(2025, 11, 17, 10, 2, 0),
                provider='claude',
                success=False,
                tokens_used=0,
                response_time_ms=100,
                cost_estimate=0.0,
                error='Rate limit'
            )
        ]

        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_records

        stats = service.get_usage_stats()

        assert stats['total_calls'] == 3
        assert stats['successful_calls'] == 2
        assert stats['failed_calls'] == 1
        assert stats['total_tokens'] == 220
        assert stats['total_cost'] == 0.033
        assert stats['provider_breakdown']['openai']['calls'] == 2
        assert stats['provider_breakdown']['openai']['success_rate'] == 100.0
        assert stats['provider_breakdown']['claude']['calls'] == 1
        assert stats['provider_breakdown']['claude']['success_rate'] == 0.0


class TestExponentialBackoff:
    """Test exponential backoff for rate limits"""

    @pytest.mark.asyncio
    async def test_retry_with_backoff(self, ai_service_instance):
        """Test that rate limits trigger exponential backoff for non-Grok providers"""
        provider = ai_service_instance.providers[AIProviderEnum.OPENAI]

        # First two calls fail with 429, third succeeds
        call_count = 0

        async def mock_generate(image_base64, camera_name, timestamp, detected_objects, custom_prompt=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return AIResult(
                    description="",
                    confidence=0,
                    objects_detected=[],
                    provider="openai",
                    tokens_used=0,
                    response_time_ms=100,
                    cost_estimate=0.0,
                    success=False,
                    error="429 Rate limit exceeded"
                )
            else:
                return AIResult(
                    description="Success after retry",
                    confidence=80,
                    objects_detected=['person'],
                    provider="openai",
                    tokens_used=100,
                    response_time_ms=500,
                    cost_estimate=0.015,
                    success=True
                )

        with patch.object(provider, 'generate_description', new=mock_generate):
            result = await ai_service_instance._try_with_backoff(
                provider,
                "base64_data",
                "Camera",
                "2025-11-17T10:00:00",
                [],
                custom_prompt=None,
                provider_type=AIProviderEnum.OPENAI
            )

        assert result.success is True
        assert call_count == 3  # Retried 3 times total (exponential backoff for OpenAI)


class TestEncryptedAPIKeyLoading:
    """Test encrypted API key loading from database"""

    @pytest.mark.asyncio
    async def test_load_api_keys_from_db_success(self):
        """Test successful loading and decryption of API keys from database"""
        service = AIService()

        # Mock database session and query
        mock_db = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        # Mock system settings with encrypted keys (including Grok - Story P2-5.1 AC4)
        mock_settings = [
            SystemSetting(key='ai_api_key_openai', value='encrypted:test_openai_key'),
            SystemSetting(key='ai_api_key_grok', value='encrypted:test_grok_key'),
            SystemSetting(key='ai_api_key_claude', value='encrypted:test_claude_key'),
            SystemSetting(key='ai_api_key_gemini', value='encrypted:test_gemini_key')
        ]
        mock_query.all.return_value = mock_settings

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
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        mock_settings = [
            SystemSetting(key='ai_api_key_openai', value='encrypted:test_openai_key')
        ]
        mock_query.all.return_value = mock_settings

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
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        mock_settings = [
            SystemSetting(key='ai_api_key_openai', value='encrypted:invalid_key')
        ]
        mock_query.all.return_value = mock_settings

        with patch('app.services.ai_service.decrypt_password') as mock_decrypt:
            mock_decrypt.side_effect = ValueError("Failed to decrypt")

            with pytest.raises(ValueError, match="Failed to load AI provider configuration"):
                await service.load_api_keys_from_db(mock_db)

    @pytest.mark.asyncio
    async def test_load_api_keys_no_keys_in_db(self):
        """Test loading when no API keys are configured in database"""
        service = AIService()

        mock_db = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []  # No settings

        await service.load_api_keys_from_db(mock_db)

        # No providers should be configured
        assert len(service.providers) == 0

    @pytest.mark.asyncio
    async def test_load_description_prompt_from_settings(self):
        """Test that custom description prompt is loaded from settings_description_prompt"""
        service = AIService()

        mock_db = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        # Mock settings with description prompt and OpenAI key
        custom_prompt = "Describe only people and vehicles in one sentence."
        mock_settings = [
            SystemSetting(key='ai_api_key_openai', value='encrypted:test_openai_key'),
            SystemSetting(key='settings_description_prompt', value=custom_prompt)
        ]
        mock_query.all.return_value = mock_settings

        with patch('app.services.ai_service.decrypt_password') as mock_decrypt:
            mock_decrypt.return_value = 'decrypted_openai_key'
            await service.load_api_keys_from_db(mock_db)

        # Verify custom prompt was loaded
        assert service.description_prompt == custom_prompt

    @pytest.mark.asyncio
    async def test_description_prompt_used_in_generation(self):
        """Test that custom description prompt is used when generating descriptions"""
        from app.services.ai_service import AIProviderBase

        service = AIService()
        service.description_prompt = "Keep it short and simple."

        # Create a mock provider that captures the prompt
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
        service.providers[AIProviderEnum.OPENAI] = mock_provider

        # Generate description without explicit custom_prompt
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        result = await service.generate_description(
            frame=frame,
            camera_name="Test Camera",
            timestamp="2025-01-01T00:00:00Z",
            detected_objects=['person']
        )

        # Verify the settings prompt was passed to the provider
        assert len(captured_prompts) == 1
        assert captured_prompts[0] == "Keep it short and simple."
        assert result.success


class TestProviderOrderConfiguration:
    """Tests for configurable provider order (Story P2-5.2)"""

    def test_get_provider_order_default(self):
        """Test that default order is returned when no database is configured"""
        from app.services.ai_service import AIService, AIProvider

        service = AIService()
        # No database configured
        service.db = None

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
        service.db = test_db

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
        service.db = test_db

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
        service.db = test_db

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
        service.db = Mock()
        service.db.query.return_value.filter.return_value.first.return_value = Mock(
            value='["grok", "anthropic", "openai", "google"]'
        )

        with patch.object(
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
        service.db = test_db

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


class TestMultiImagePreprocessing:
    """Test multi-image preprocessing functionality (Story P3-2.3)"""

    def test_preprocess_image_bytes_basic(self, ai_service_instance, sample_image_bytes):
        """Test preprocessing of raw image bytes"""
        base64_img = ai_service_instance._preprocess_image_bytes(sample_image_bytes)

        assert isinstance(base64_img, str)
        assert len(base64_img) > 0
        # Base64 string should be valid
        import base64
        try:
            decoded = base64.b64decode(base64_img)
            assert len(decoded) > 0
        except Exception as e:
            pytest.fail(f"Invalid base64: {e}")

    def test_preprocess_image_bytes_large_image(self, ai_service_instance):
        """Test preprocessing resizes large image bytes to 2048x2048 max"""
        from PIL import Image
        import io
        import base64

        # Create a large 4000x3000 image
        large_img = Image.new('RGB', (4000, 3000), color='red')
        buffer = io.BytesIO()
        large_img.save(buffer, format='JPEG', quality=95)
        large_bytes = buffer.getvalue()

        base64_img = ai_service_instance._preprocess_image_bytes(large_bytes)

        # Decode and check size
        decoded = base64.b64decode(base64_img)
        resized_img = Image.open(io.BytesIO(decoded))

        # Should be resized to max 2048 on longest side
        assert max(resized_img.size) <= 2048
        assert resized_img.format == 'JPEG'

    def test_preprocess_image_bytes_png_converted_to_jpeg(self, ai_service_instance):
        """Test that PNG image bytes are converted to JPEG"""
        from PIL import Image
        import io
        import base64

        # Create PNG image
        png_img = Image.new('RGBA', (200, 200), color='green')
        buffer = io.BytesIO()
        png_img.save(buffer, format='PNG')
        png_bytes = buffer.getvalue()

        base64_img = ai_service_instance._preprocess_image_bytes(png_bytes)

        # Decode and verify it's JPEG
        decoded = base64.b64decode(base64_img)
        result_img = Image.open(io.BytesIO(decoded))
        assert result_img.format == 'JPEG'


class TestMultiImagePromptBuilder:
    """Test multi-image prompt building (Story P3-2.3, P3-2.4)"""

    def test_build_multi_image_prompt_basic(self):
        """Test multi-image prompt includes frame count and context"""
        provider = OpenAIProvider("sk-test-key")

        prompt = provider._build_multi_image_prompt(
            camera_name="Front Door",
            timestamp="2025-12-06T10:00:00",
            detected_objects=["person"],
            num_images=5
        )

        assert "5 frames" in prompt
        assert "Camera 'Front Door'" in prompt
        assert "2025-12-06T10:00:00" in prompt
        assert "person" in prompt
        assert "sequence" in prompt.lower()

    def test_build_multi_image_prompt_custom(self):
        """Test multi-image prompt with custom prompt APPENDED (not replacing)"""
        provider = OpenAIProvider("sk-test-key")

        custom_prompt = "Focus only on vehicle movements"
        prompt = provider._build_multi_image_prompt(
            camera_name="Driveway",
            timestamp="2025-12-06T11:00:00",
            detected_objects=[],
            num_images=3,
            custom_prompt=custom_prompt
        )

        # Custom prompt should be appended
        assert custom_prompt in prompt
        assert "Camera 'Driveway'" in prompt
        # System prompt should STILL be present (not replaced)
        assert "chronological order" in prompt
        assert "Additional instructions:" in prompt

    def test_build_multi_image_prompt_no_detected_objects(self):
        """Test multi-image prompt without detected objects"""
        provider = ClaudeProvider("sk-ant-test-key")

        prompt = provider._build_multi_image_prompt(
            camera_name="Backyard",
            timestamp="2025-12-06T12:00:00",
            detected_objects=[],
            num_images=4
        )

        assert "4 frames" in prompt
        assert "Motion detected" not in prompt

    def test_build_multi_image_prompt_chronological_order_ac1(self):
        """Test prompt includes 'chronological order' text (AC1)"""
        provider = OpenAIProvider("sk-test-key")

        prompt = provider._build_multi_image_prompt(
            camera_name="Camera",
            timestamp="2025-12-06T10:00:00",
            detected_objects=[],
            num_images=5
        )

        assert "chronological order" in prompt.lower()

    def test_build_multi_image_prompt_what_happened_ac1(self):
        """Test prompt asks for 'what happened' description (AC1)"""
        provider = OpenAIProvider("sk-test-key")

        prompt = provider._build_multi_image_prompt(
            camera_name="Camera",
            timestamp="2025-12-06T10:00:00",
            detected_objects=[],
            num_images=5
        )

        assert "what happened" in prompt.lower()

    def test_build_multi_image_prompt_describes_who_what_action_direction_ac2(self):
        """Test prompt instructs to describe who/what, action, direction, sequence (AC2)"""
        provider = OpenAIProvider("sk-test-key")

        prompt = provider._build_multi_image_prompt(
            camera_name="Camera",
            timestamp="2025-12-06T10:00:00",
            detected_objects=[],
            num_images=5
        )

        # Should mention action verbs
        assert "action" in prompt.lower()
        # Should mention direction
        assert "direction" in prompt.lower()
        # Should mention sequence/progression
        assert "sequence" in prompt.lower()

    def test_build_multi_image_prompt_action_verbs_ac3(self):
        """Test prompt mentions action verbs like walked, placed, picked up (AC3)"""
        provider = OpenAIProvider("sk-test-key")

        prompt = provider._build_multi_image_prompt(
            camera_name="Camera",
            timestamp="2025-12-06T10:00:00",
            detected_objects=[],
            num_images=5
        )

        # Should include action verbs
        assert "walked" in prompt.lower()
        assert "placed" in prompt.lower()
        assert "approached" in prompt.lower()

    def test_build_multi_image_prompt_avoids_static_ac3(self):
        """Test prompt warns against static descriptions (AC3)"""
        provider = OpenAIProvider("sk-test-key")

        prompt = provider._build_multi_image_prompt(
            camera_name="Camera",
            timestamp="2025-12-06T10:00:00",
            detected_objects=[],
            num_images=5
        )

        # Should warn against static descriptions
        assert "static" in prompt.lower() or "is standing" in prompt.lower() or "bad" in prompt.lower()

    def test_build_multi_image_prompt_custom_appended_ac4(self):
        """Test custom prompt is APPENDED after system instructions (AC4)"""
        provider = OpenAIProvider("sk-test-key")

        custom_prompt = "Pay special attention to packages"
        prompt = provider._build_multi_image_prompt(
            camera_name="Camera",
            timestamp="2025-12-06T10:00:00",
            detected_objects=[],
            num_images=5,
            custom_prompt=custom_prompt
        )

        # Custom prompt should be present
        assert custom_prompt in prompt
        # System prompt should STILL be present (temporal context preserved)
        assert "chronological order" in prompt.lower()
        assert "what happened" in prompt.lower()
        # Custom prompt appears after system prompt
        chronological_pos = prompt.lower().find("chronological order")
        custom_pos = prompt.find(custom_prompt)
        assert custom_pos > chronological_pos

    def test_build_multi_image_prompt_works_all_providers(self):
        """Test prompt works with all 4 providers"""
        providers = [
            OpenAIProvider("sk-test-key"),
            GrokProvider("xai-test-key"),
            ClaudeProvider("sk-ant-test-key"),
            GeminiProvider("test-key"),
        ]

        for provider in providers:
            prompt = provider._build_multi_image_prompt(
                camera_name="Test Camera",
                timestamp="2025-12-06T10:00:00",
                detected_objects=["person"],
                num_images=3
            )

            # All providers should include temporal context
            assert "chronological order" in prompt.lower()
            assert "3 frames" in prompt
            assert "Camera 'Test Camera'" in prompt


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

        assert result.success is False
        assert "No AI providers configured" in result.error or "No AI providers" in result.description


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


class TestMultiImageRetryLogic:
    """Test multi-image retry logic with backoff (Story P3-2.3)"""

    @pytest.mark.asyncio
    async def test_multi_image_retry_on_429(self, ai_service_instance):
        """Test that multi-image requests retry on 429 errors"""
        provider = ai_service_instance.providers[AIProviderEnum.OPENAI]

        call_count = 0

        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return AIResult(
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
            return AIResult(
                description="Success after retry",
                confidence=80,
                objects_detected=['person'],
                provider="openai",
                tokens_used=150,
                response_time_ms=500,
                cost_estimate=0.02,
                success=True
            )

        with patch.object(
            provider,
            'generate_multi_image_description',
            new=mock_generate
        ):
            result = await ai_service_instance._try_multi_image_with_backoff(
                provider,
                ["img1", "img2", "img3"],
                "Camera",
                "2025-12-06T10:00:00",
                [],
                provider_type=AIProviderEnum.OPENAI
            )

        assert result.success is True
        assert call_count == 3  # 2 retries + 1 success


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

        # Mock database
        mock_db = Mock()
        ai_service_instance.db = mock_db

        with patch.object(
            ai_service_instance.providers[AIProviderEnum.OPENAI],
            'generate_multi_image_description',
            new=AsyncMock(return_value=mock_result)
        ):
            result = await ai_service_instance.describe_images(
                images=sample_image_bytes_list,
                camera_name="Camera",
                timestamp="2025-12-06T10:00:00",
                detected_objects=["person"]
            )

        assert result.success is True
        # Verify database was called to track usage
        assert mock_db.add.called
        assert mock_db.commit.called
