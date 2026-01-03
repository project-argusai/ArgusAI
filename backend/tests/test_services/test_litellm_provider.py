"""Unit tests for LiteLLM Provider

Story: LiteLLM Integration
Tests for: backend/app/services/litellm_provider.py

Tests cover:
- Provider initialization and configuration
- Single and multi-image description generation
- Response parsing (JSON and plain text)
- Object extraction from descriptions
- Error handling and fallback behavior
- Cost tracking integration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.litellm_provider import (
    LiteLLMProvider,
    LiteLLMResult,
    configure_litellm_provider,
    get_litellm_provider,
    MODEL_MAPPINGS,
    DEFAULT_PROVIDER_ORDER,
)


class TestLiteLLMProviderInit:
    """Test LiteLLM provider initialization"""

    def test_init_with_no_keys(self):
        """Provider initializes but is not configured without API keys"""
        provider = LiteLLMProvider()

        assert provider.is_configured() is False
        assert provider.router is None
        assert len(provider.get_configured_providers()) == 0

    def test_init_with_openai_key(self):
        """Provider configures OpenAI when key is provided"""
        provider = LiteLLMProvider(openai_key="sk-test-key")

        assert provider.is_configured() is True
        assert "openai" in provider.configured_providers
        assert provider.router is not None
        assert len(provider.model_list) == 1

    def test_init_with_all_keys(self):
        """Provider configures all providers when all keys provided"""
        provider = LiteLLMProvider(
            openai_key="sk-test-openai",
            grok_key="xai-test-grok",
            claude_key="sk-ant-test-claude",
            gemini_key="test-gemini",
        )

        assert provider.is_configured() is True
        assert len(provider.configured_providers) == 4
        assert "openai" in provider.configured_providers
        assert "grok" in provider.configured_providers
        assert "claude" in provider.configured_providers
        assert "gemini" in provider.configured_providers
        assert len(provider.model_list) == 4

    def test_init_with_custom_claude_model(self):
        """Provider uses custom Claude model when specified"""
        provider = LiteLLMProvider(
            claude_key="sk-ant-test",
            claude_model="claude-3-5-sonnet-20241022",
        )

        assert provider.is_configured() is True
        # Check model list has the custom model with prefix
        claude_config = provider.model_list[0]
        assert "anthropic/claude-3-5-sonnet-20241022" in claude_config["litellm_params"]["model"]

    def test_init_preserves_provider_order(self):
        """Provider order is preserved from initialization"""
        custom_order = ["gemini", "claude", "openai", "grok"]
        provider = LiteLLMProvider(
            openai_key="sk-test",
            provider_order=custom_order,
        )

        assert provider.provider_order == custom_order


class TestLiteLLMProviderDescribe:
    """Test description generation"""

    @pytest.fixture
    def configured_provider(self):
        """Create a provider with mocked router"""
        provider = LiteLLMProvider(openai_key="sk-test-key")
        return provider

    @pytest.mark.asyncio
    async def test_describe_image_without_router(self):
        """Returns error result when no providers configured"""
        provider = LiteLLMProvider()

        result = await provider.describe_image(
            image_base64="base64data",
            system_prompt="You are a security camera AI.",
            user_prompt="Describe what you see.",
        )

        assert result.success is False
        assert result.provider == "none"
        assert "No AI providers configured" in result.error

    @pytest.mark.asyncio
    async def test_describe_images_success(self, configured_provider):
        """Successfully generates description via LiteLLM"""
        # Mock router response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A person is walking towards the front door carrying a package."
        mock_response.model = "gpt-4o-mini"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 150

        with patch.object(
            configured_provider.router,
            'acompletion',
            new=AsyncMock(return_value=mock_response)
        ):
            with patch('app.services.litellm_provider.completion_cost', return_value=0.001):
                result = await configured_provider.describe_images(
                    images_base64=["base64data1", "base64data2"],
                    system_prompt="You are a security camera AI.",
                    user_prompt="Describe what you see.",
                )

        assert result.success is True
        assert result.provider == "openai"
        assert "person" in result.description.lower()
        assert "package" in result.description.lower()
        assert result.tokens_used == 150
        assert result.cost_estimate == 0.001
        assert "person" in result.objects_detected
        assert "package" in result.objects_detected

    @pytest.mark.asyncio
    async def test_describe_images_api_error(self, configured_provider):
        """Handles API errors gracefully"""
        with patch.object(
            configured_provider.router,
            'acompletion',
            new=AsyncMock(side_effect=Exception("API rate limit exceeded"))
        ):
            result = await configured_provider.describe_images(
                images_base64=["base64data"],
                system_prompt="System prompt",
                user_prompt="User prompt",
            )

        assert result.success is False
        assert result.provider == "error"
        assert "API rate limit exceeded" in result.error
        assert result.confidence == 0

    @pytest.mark.asyncio
    async def test_single_image_calls_multi_image(self, configured_provider):
        """describe_image delegates to describe_images"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test description"
        mock_response.model = "gpt-4o-mini"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50

        with patch.object(
            configured_provider.router,
            'acompletion',
            new=AsyncMock(return_value=mock_response)
        ) as mock_acompletion:
            with patch('app.services.litellm_provider.completion_cost', return_value=0.0005):
                await configured_provider.describe_image(
                    image_base64="single_image_base64",
                    system_prompt="System",
                    user_prompt="User",
                )

        # Verify acompletion was called with single image in list
        mock_acompletion.assert_called_once()
        call_args = mock_acompletion.call_args
        messages = call_args.kwargs.get('messages', call_args[1].get('messages', []))
        user_content = messages[1]['content']
        # Should have text + 1 image
        assert len([c for c in user_content if c.get('type') == 'image_url']) == 1


class TestLiteLLMResponseParsing:
    """Test response parsing logic"""

    @pytest.fixture
    def provider(self):
        return LiteLLMProvider(openai_key="sk-test")

    def test_parse_plain_text_response(self, provider):
        """Parses plain text description"""
        response = "A delivery truck is parked in the driveway."

        description, confidence, bboxes = provider._parse_response(response)

        assert description == response
        assert confidence is None
        assert bboxes is None

    def test_parse_json_response(self, provider):
        """Parses JSON response with description and confidence"""
        response = '{"description": "A person at the door", "confidence": 85}'

        description, confidence, bboxes = provider._parse_response(response)

        assert description == "A person at the door"
        assert confidence == 85
        assert bboxes is None

    def test_parse_json_with_bounding_boxes(self, provider):
        """Parses JSON response with bounding boxes"""
        response = '''{"description": "A person at the door", "confidence": 90, "bounding_boxes": [{"label": "person", "x": 100, "y": 200, "width": 50, "height": 100}]}'''

        description, confidence, bboxes = provider._parse_response(response)

        assert description == "A person at the door"
        assert confidence == 90
        assert bboxes is not None
        assert len(bboxes) == 1
        assert bboxes[0]["label"] == "person"

    def test_parse_confidence_from_text(self, provider):
        """Extracts confidence from plain text pattern"""
        response = "A car is backing out of the garage. Confidence: 75"

        description, confidence, bboxes = provider._parse_response(response)

        assert "car" in description.lower()
        assert confidence == 75
        assert "confidence" not in description.lower()  # Removed from description

    def test_parse_invalid_json_falls_back(self, provider):
        """Falls back to plain text on invalid JSON"""
        response = '{"description": "partial json'

        description, confidence, bboxes = provider._parse_response(response)

        assert description == response
        assert confidence is None


class TestLiteLLMObjectExtraction:
    """Test object extraction from descriptions"""

    @pytest.fixture
    def provider(self):
        return LiteLLMProvider(openai_key="sk-test")

    def test_extract_person(self, provider):
        """Extracts person-related objects"""
        objects = provider._extract_objects("A man is walking towards the house")
        assert "person" in objects

        objects = provider._extract_objects("The delivery driver left a package")
        assert "person" in objects

    def test_extract_vehicle(self, provider):
        """Extracts vehicle-related objects"""
        objects = provider._extract_objects("A red car is parked in the driveway")
        assert "vehicle" in objects

        objects = provider._extract_objects("A delivery truck arrived")
        assert "vehicle" in objects

    def test_extract_package(self, provider):
        """Extracts package-related objects"""
        objects = provider._extract_objects("An Amazon box was left at the door")
        assert "package" in objects

    def test_extract_animal(self, provider):
        """Extracts animal-related objects"""
        objects = provider._extract_objects("A dog is running across the yard")
        assert "animal" in objects

        objects = provider._extract_objects("A cat is sitting on the porch")
        assert "animal" in objects

    def test_extract_multiple_objects(self, provider):
        """Extracts multiple object types"""
        objects = provider._extract_objects(
            "A person is walking their dog to a parked car"
        )
        assert "person" in objects
        assert "animal" in objects
        assert "vehicle" in objects

    def test_extract_unknown_when_no_match(self, provider):
        """Returns unknown when no objects detected"""
        objects = provider._extract_objects("The wind is blowing leaves around")
        assert objects == ["unknown"]


class TestLiteLLMProviderDetection:
    """Test provider detection from model names"""

    @pytest.fixture
    def provider(self):
        return LiteLLMProvider(openai_key="sk-test")

    @pytest.mark.asyncio
    async def test_detect_openai_provider(self, provider):
        """Correctly identifies OpenAI from model name"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test"
        mock_response.model = "gpt-4o-mini"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50

        with patch.object(provider.router, 'acompletion', new=AsyncMock(return_value=mock_response)):
            with patch('app.services.litellm_provider.completion_cost', return_value=0.001):
                result = await provider.describe_image("img", "sys", "user")

        assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_detect_grok_provider(self, provider):
        """Correctly identifies Grok from model name"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test"
        mock_response.model = "xai/grok-2-vision"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50

        with patch.object(provider.router, 'acompletion', new=AsyncMock(return_value=mock_response)):
            with patch('app.services.litellm_provider.completion_cost', return_value=0.001):
                result = await provider.describe_image("img", "sys", "user")

        assert result.provider == "grok"

    @pytest.mark.asyncio
    async def test_detect_claude_provider(self, provider):
        """Correctly identifies Claude from model name"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test"
        mock_response.model = "anthropic/claude-3-haiku"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50

        with patch.object(provider.router, 'acompletion', new=AsyncMock(return_value=mock_response)):
            with patch('app.services.litellm_provider.completion_cost', return_value=0.001):
                result = await provider.describe_image("img", "sys", "user")

        assert result.provider == "claude"

    @pytest.mark.asyncio
    async def test_detect_gemini_provider(self, provider):
        """Correctly identifies Gemini from model name"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test"
        mock_response.model = "gemini/gemini-2.5-flash"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50

        with patch.object(provider.router, 'acompletion', new=AsyncMock(return_value=mock_response)):
            with patch('app.services.litellm_provider.completion_cost', return_value=0.001):
                result = await provider.describe_image("img", "sys", "user")

        assert result.provider == "gemini"


class TestLiteLLMSingleton:
    """Test singleton configuration functions"""

    def test_configure_returns_provider(self):
        """configure_litellm_provider returns configured provider"""
        provider = configure_litellm_provider(openai_key="sk-test")

        assert provider is not None
        assert provider.is_configured() is True
        assert "openai" in provider.configured_providers

    def test_get_returns_configured_provider(self):
        """get_litellm_provider returns the singleton"""
        configure_litellm_provider(openai_key="sk-test-2")
        provider = get_litellm_provider()

        assert provider is not None
        assert provider.is_configured() is True

    def test_reconfigure_replaces_instance(self):
        """Reconfiguring creates new instance"""
        provider1 = configure_litellm_provider(openai_key="sk-key-1")
        provider2 = configure_litellm_provider(
            openai_key="sk-key-1",
            claude_key="sk-ant-key",
        )

        # Should have more providers now
        assert len(provider2.configured_providers) > len(provider1.configured_providers)


class TestModelMappings:
    """Test model mapping constants"""

    def test_all_providers_mapped(self):
        """All expected providers have mappings"""
        assert "openai" in MODEL_MAPPINGS
        assert "grok" in MODEL_MAPPINGS
        assert "claude" in MODEL_MAPPINGS
        assert "gemini" in MODEL_MAPPINGS

    def test_default_provider_order(self):
        """Default provider order is correct"""
        assert DEFAULT_PROVIDER_ORDER == ["openai", "grok", "claude", "gemini"]

    def test_model_format_correct(self):
        """Model names have correct provider prefix format"""
        assert MODEL_MAPPINGS["openai"].startswith("openai/")
        assert MODEL_MAPPINGS["grok"].startswith("xai/")
        assert MODEL_MAPPINGS["claude"].startswith("anthropic/")
        assert MODEL_MAPPINGS["gemini"].startswith("gemini/")
