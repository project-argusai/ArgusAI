"""Unit tests for AI Service"""
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime

from app.services.ai_service import (
    AIService,
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    AIResult,
    AIProvider as AIProviderEnum
)
from app.models.system_setting import SystemSetting


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
        """Test that rate limits trigger exponential backoff"""
        provider = ai_service_instance.providers[AIProviderEnum.OPENAI]

        # First two calls fail with 429, third succeeds
        call_count = 0

        async def mock_generate(image_base64, camera_name, timestamp, detected_objects):
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
                max_retries=3
            )

        assert result.success is True
        assert call_count == 3  # Retried 3 times total


class TestEncryptedAPIKeyLoading:
    """Test encrypted API key loading from database"""

    def test_load_api_keys_from_db_success(self):
        """Test successful loading and decryption of API keys from database"""
        service = AIService()

        # Mock database session and query
        mock_db = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        # Mock system settings with encrypted keys
        mock_settings = [
            SystemSetting(key='ai_api_key_openai', value='encrypted:test_openai_key'),
            SystemSetting(key='ai_api_key_claude', value='encrypted:test_claude_key'),
            SystemSetting(key='ai_api_key_gemini', value='encrypted:test_gemini_key')
        ]
        mock_query.all.return_value = mock_settings

        # Mock decryption
        with patch('app.services.ai_service.decrypt_password') as mock_decrypt:
            mock_decrypt.side_effect = lambda x: x.replace('encrypted:', 'decrypted_')

            service.load_api_keys_from_db(mock_db)

        # Verify all 3 providers were configured
        assert len(service.providers) == 3
        assert AIProviderEnum.OPENAI in service.providers
        assert AIProviderEnum.CLAUDE in service.providers
        assert AIProviderEnum.GEMINI in service.providers

        # Verify decrypt was called for each key
        assert mock_decrypt.call_count == 3

    def test_load_api_keys_partial_configuration(self):
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

            service.load_api_keys_from_db(mock_db)

        # Only OpenAI should be configured
        assert len(service.providers) == 1
        assert AIProviderEnum.OPENAI in service.providers
        assert AIProviderEnum.CLAUDE not in service.providers
        assert AIProviderEnum.GEMINI not in service.providers

    def test_load_api_keys_decryption_error(self):
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
                service.load_api_keys_from_db(mock_db)

    def test_load_api_keys_no_keys_in_db(self):
        """Test loading when no API keys are configured in database"""
        service = AIService()

        mock_db = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []  # No settings

        service.load_api_keys_from_db(mock_db)

        # No providers should be configured
        assert len(service.providers) == 0
