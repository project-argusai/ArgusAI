"""
Tests for Story P3-6.1: Extract Confidence Score from AI Responses

Tests cover:
- AC1: Prompt includes confidence instruction
- AC2: Parse confidence from AI response
- AC3: Flag low confidence events
- AC4: Handle missing/invalid confidence
- AC5: Support all AI providers
- AC6: Store confidence in Event model
"""
import pytest
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from app.services.ai_providers.base import AIProviderBase
from app.services.ai_providers.openai_provider import OpenAIProvider
from app.services.ai_providers.claude_provider import ClaudeProvider
from app.services.ai_providers.gemini_provider import GeminiProvider
from app.services.ai_providers.grok_provider import GrokProvider
from app.services.ai_types import AIResult
from app.services.prompt_templates import BOUNDING_BOX_INSTRUCTION


class TestConfidenceInstruction:
    """AC1: Verify the confidence/JSON instruction injected into prompts.

    After the ai_providers decomposition the confidence-score JSON instruction
    lives in BOUNDING_BOX_INSTRUCTION (prompt_templates.py). The old
    CONFIDENCE_INSTRUCTION constant was repurposed to a plain
    people/vehicle/package description instruction and no longer carries the
    JSON/confidence contract, so these assertions target the current source.
    """

    def test_confidence_instruction_defined(self):
        """The confidence instruction constant should request a 0-100 score"""
        assert BOUNDING_BOX_INSTRUCTION is not None
        assert "confidence" in BOUNDING_BOX_INSTRUCTION.lower()
        # 0-100 scale appears as the example value `"confidence": 85`
        assert '"confidence": 85' in BOUNDING_BOX_INSTRUCTION

    def test_confidence_instruction_includes_json_format(self):
        """Instruction should request JSON format"""
        assert '{"description"' in BOUNDING_BOX_INSTRUCTION
        assert '"confidence"' in BOUNDING_BOX_INSTRUCTION


class TestParseConfidenceResponse:
    """AC2, AC4: Test response parsing for confidence extraction"""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing parse method"""
        provider = OpenAIProvider.__new__(OpenAIProvider)
        AIProviderBase.__init__(provider, "test-api-key")
        return provider

    def test_parse_valid_json_response(self, provider):
        """AC2: Should extract description and confidence from JSON"""
        response = '{"description": "A person walked to the door", "confidence": 85}'
        description, confidence, _ = provider._parse_confidence_response(response)

        assert description == "A person walked to the door"
        assert confidence == 85

    def test_parse_json_with_high_confidence(self, provider):
        """AC2: Should handle high confidence scores"""
        response = '{"description": "Clear view of delivery truck", "confidence": 95}'
        description, confidence, _ = provider._parse_confidence_response(response)

        assert confidence == 95
        assert "delivery truck" in description

    def test_parse_json_with_low_confidence(self, provider):
        """AC3: Should extract low confidence (< 50)"""
        response = '{"description": "Something moving in shadows", "confidence": 25}'
        description, confidence, _ = provider._parse_confidence_response(response)

        assert confidence == 25
        assert confidence < 50

    def test_parse_json_embedded_in_text(self, provider):
        """AC2: Should extract JSON embedded in text"""
        response = 'Here is my analysis:\n{"description": "A car arrived", "confidence": 78}'
        description, confidence, _ = provider._parse_confidence_response(response)

        assert description == "A car arrived"
        assert confidence == 78

    def test_parse_plain_text_with_confidence_pattern(self, provider):
        """AC4: Should fallback to pattern matching for plain text"""
        response = "A person is at the door. I am 85% confident in this description."
        description, confidence, _ = provider._parse_confidence_response(response)

        assert confidence == 85
        # Plain text fallback returns original response as description
        assert "person is at the door" in description

    def test_parse_confidence_colon_pattern(self, provider):
        """AC4: Should match 'confidence: 85' pattern"""
        response = "Someone walking on sidewalk. Confidence: 75"
        description, confidence, _ = provider._parse_confidence_response(response)

        assert confidence == 75

    def test_parse_missing_confidence_returns_none(self, provider):
        """AC4: Missing confidence should return None, not fail"""
        response = "A person approached the front door and rang the doorbell."
        description, confidence, _ = provider._parse_confidence_response(response)

        assert confidence is None
        assert "person approached" in description

    def test_parse_invalid_confidence_range_returns_none(self, provider):
        """AC4: Confidence outside 0-100 should return None"""
        response = '{"description": "Test", "confidence": 150}'
        description, confidence, _ = provider._parse_confidence_response(response)

        # Invalid range, should return None
        assert confidence is None

    def test_parse_negative_confidence_returns_none(self, provider):
        """AC4: Negative confidence should return None"""
        response = '{"description": "Test", "confidence": -10}'
        description, confidence, _ = provider._parse_confidence_response(response)

        assert confidence is None

    def test_parse_boundary_confidence_zero(self, provider):
        """AC2: Should accept confidence of 0"""
        response = '{"description": "Cannot see anything", "confidence": 0}'
        description, confidence, _ = provider._parse_confidence_response(response)

        assert confidence == 0

    def test_parse_boundary_confidence_hundred(self, provider):
        """AC2: Should accept confidence of 100"""
        response = '{"description": "Crystal clear view of person", "confidence": 100}'
        description, confidence, _ = provider._parse_confidence_response(response)

        assert confidence == 100

    def test_parse_float_confidence_truncated(self, provider):
        """AC2: Float confidence should be truncated to int"""
        response = '{"description": "Test", "confidence": 85.7}'
        description, confidence, _ = provider._parse_confidence_response(response)

        assert confidence == 85
        assert isinstance(confidence, int)


class TestAIResultWithConfidence:
    """AC6: Test AIResult dataclass includes ai_confidence field"""

    def test_ai_result_has_ai_confidence_field(self):
        """AIResult should have ai_confidence optional field"""
        result = AIResult(
            description="Test description",
            confidence=75,
            objects_detected=["person"],
            provider="openai",
            tokens_used=100,
            response_time_ms=500,
            cost_estimate=0.001,
            success=True,
            ai_confidence=85
        )

        assert result.ai_confidence == 85

    def test_ai_result_ai_confidence_defaults_to_none(self):
        """ai_confidence should default to None"""
        result = AIResult(
            description="Test",
            confidence=75,
            objects_detected=["person"],
            provider="openai",
            tokens_used=100,
            response_time_ms=500,
            cost_estimate=0.001,
            success=True
        )

        assert result.ai_confidence is None

    def test_ai_result_low_confidence_value(self):
        """ai_confidence can hold low values (< 50)"""
        result = AIResult(
            description="Uncertain",
            confidence=70,  # Heuristic confidence
            objects_detected=["unknown"],
            provider="openai",
            tokens_used=50,
            response_time_ms=500,
            cost_estimate=0.001,
            success=True,
            ai_confidence=30  # AI self-reported low confidence
        )

        assert result.ai_confidence == 30
        assert result.ai_confidence < 50


class TestLowConfidenceFlag:
    """AC3: Test low_confidence flag is set correctly"""

    def test_low_confidence_flag_set_when_under_50(self):
        """low_confidence should be True when ai_confidence < 50"""
        ai_confidence = 40
        low_confidence = ai_confidence is not None and ai_confidence < 50

        assert low_confidence is True

    def test_low_confidence_flag_not_set_when_50_or_above(self):
        """low_confidence should be False when ai_confidence >= 50"""
        ai_confidence = 50
        low_confidence = ai_confidence is not None and ai_confidence < 50

        assert low_confidence is False

    def test_low_confidence_flag_not_set_when_none(self):
        """low_confidence should be False when ai_confidence is None (AC4)"""
        ai_confidence = None
        low_confidence = ai_confidence is not None and ai_confidence < 50

        assert low_confidence is False

    def test_low_confidence_boundary_49(self):
        """49 should be flagged as low confidence"""
        ai_confidence = 49
        low_confidence = ai_confidence is not None and ai_confidence < 50

        assert low_confidence is True

    def test_low_confidence_boundary_51(self):
        """51 should NOT be flagged as low confidence"""
        ai_confidence = 51
        low_confidence = ai_confidence is not None and ai_confidence < 50

        assert low_confidence is False


class TestEventSchemaWithConfidence:
    """AC6: Test Event schemas include confidence fields"""

    def test_event_create_schema_has_ai_confidence(self):
        """EventCreate should have ai_confidence field"""
        from app.schemas.event import EventCreate

        # Check field exists in model_fields
        assert "ai_confidence" in EventCreate.model_fields
        assert "low_confidence" in EventCreate.model_fields

    def test_event_response_schema_has_ai_confidence(self):
        """EventResponse should have ai_confidence field"""
        from app.schemas.event import EventResponse

        assert "ai_confidence" in EventResponse.model_fields
        assert "low_confidence" in EventResponse.model_fields


class TestEventModelWithConfidence:
    """AC6: Test Event model includes confidence fields"""

    def test_event_model_has_ai_confidence_column(self):
        """Event model should have ai_confidence column"""
        from app.models.event import Event

        assert hasattr(Event, 'ai_confidence')
        assert hasattr(Event, 'low_confidence')


@pytest.mark.asyncio
class TestProviderConfidenceIntegration:
    """AC5: Test all providers return confidence scores"""

    async def test_openai_provider_returns_ai_confidence(self):
        """OpenAI provider should include ai_confidence in result"""
        with patch(
            "app.services.ai_providers.openai_provider.build_openai_client"
        ) as mock_build, patch(
            "app.services.ai_providers.model_resolver.resolve_model",
            return_value="gpt-4o-mini",
        ):
            mock_client = AsyncMock()
            mock_build.return_value = mock_client

            # Mock response with JSON containing confidence
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '{"description": "Person at door", "confidence": 82}'
            mock_response.usage = MagicMock(total_tokens=100, prompt_tokens=80, completion_tokens=20)
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            provider = OpenAIProvider("test-key")
            result = await provider.generate_description(
                image_base64="base64data",
                camera_name="Front Door",
                timestamp="2025-12-08T10:00:00Z",
                detected_objects=["person"]
            )

            assert result.success is True
            assert result.ai_confidence == 82
            assert result.description == "Person at door"

    async def test_provider_handles_missing_confidence(self):
        """Provider should handle response without confidence gracefully"""
        with patch(
            "app.services.ai_providers.openai_provider.build_openai_client"
        ) as mock_build, patch(
            "app.services.ai_providers.model_resolver.resolve_model",
            return_value="gpt-4o-mini",
        ):
            mock_client = AsyncMock()
            mock_build.return_value = mock_client

            # Mock response without structured confidence
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "A person is standing at the front door."
            mock_response.usage = MagicMock(total_tokens=50, prompt_tokens=40, completion_tokens=10)
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            provider = OpenAIProvider("test-key")
            result = await provider.generate_description(
                image_base64="base64data",
                camera_name="Front Door",
                timestamp="2025-12-08T10:00:00Z",
                detected_objects=["person"]
            )

            assert result.success is True
            assert result.ai_confidence is None  # AC4: defaults to None
            assert "person" in result.description.lower()


class TestConfidenceScale745:
    """#745: a 0-1 confidence must not become 0 and trigger the #696 fallback."""

    @pytest.fixture
    def provider(self):
        provider = OpenAIProvider.__new__(OpenAIProvider)
        AIProviderBase.__init__(provider, "test-api-key")
        return provider

    def _conf(self, provider, value):
        return provider._parse_confidence_response(
            json.dumps({"description": "A person at the door.", "confidence": value}))[1]

    @pytest.mark.parametrize("value,expected", [
        (0.85, 85), (0.9, 90), (0.6, 60), (0.005, 1), (0.994, 99), (0.5, 50),
        (85, 85), (85.0, 85), (85.7, 85), (100, 100), (2, 2),
        (1, 1), (1.0, 1),  # exactly 1: 1%, see normalize_confidence
        (0, 0), (0.0, 0),
    ])
    def test_scale(self, provider, value, expected):
        got = self._conf(provider, value)
        assert got == expected and type(got) is int

    @pytest.mark.parametrize("raw", ['NaN', 'Infinity', '-Infinity', '101', '-0.5', '1e9', 'true',
                                     '"NaN"', '"inf"', '"-5"', '"abc"', '"101"', '""'])
    def test_rejected_like_before(self, provider, raw):
        text = '{"description": "A person at the door.", "confidence": %s}' % raw
        description, confidence, _ = provider._parse_confidence_response(text)
        assert confidence is None and description == "A person at the door."

    def test_numpy_values(self):
        import numpy as np
        from app.services.ai_providers.base import normalize_confidence
        assert normalize_confidence(np.float32(0.85)) == 85
        assert normalize_confidence(np.int64(85)) == 85
        assert normalize_confidence(np.float64("nan")) is None
        assert normalize_confidence(np.bool_(True)) is None

    def test_point_nine_vs_point_six_does_not_trigger_fallback(self, provider):
        from app.services.local_first import local_answer_problem
        local = AIResult(description="A person at the door.", confidence=0, objects_detected=["person"],
                         provider="local", tokens_used=0, response_time_ms=1, cost_estimate=0.0,
                         success=True, ai_confidence=self._conf(provider, 0.6))
        cloud_conf = self._conf(provider, 0.9)
        assert (local.ai_confidence, cloud_conf) == (60, 90)
        assert cloud_conf - local.ai_confidence == 30
        assert local_answer_problem(local, min_confidence=50) is None
        # Before #745 this was int(0.6) == 0 -> "low_confidence".
        local_low = AIResult(description="x", confidence=0, objects_detected=[], provider="local",
                             tokens_used=0, response_time_ms=1, cost_estimate=0.0, success=True,
                             ai_confidence=self._conf(provider, 0.3))
        assert local_low.ai_confidence == 30
        assert local_answer_problem(local_low, min_confidence=50) == "low_confidence"


class TestConfidenceScale747Review:
    """#747 review (Gracie/Terry): text path, LiteLLM path, Decimal rounding, strings, counter."""

    @pytest.fixture
    def provider(self):
        provider = OpenAIProvider.__new__(OpenAIProvider)
        AIProviderBase.__init__(provider, "test-api-key")
        return provider

    @pytest.mark.parametrize("value,expected", [
        (0.285, 29), (0.125, 13), (0.004, 0), (0.005, 1), (0.995, 100),
    ])
    def test_half_up_decimal_rounding(self, value, expected):
        from app.services.ai_providers.base import normalize_confidence
        assert normalize_confidence(value) == expected

    @pytest.mark.parametrize("value,expected", [
        ("85", 85), (" 85 ", 85), ("0.85", 85), ("85.7", 85), ("1", 1),
        (__import__("decimal").Decimal("0.85"), 85), (__import__("decimal").Decimal("85"), 85),
        ("NaN", None), ("inf", None), ("-1", None), ("1e2", None), ("85%", None),
        (__import__("decimal").Decimal("NaN"), None), (__import__("decimal").Decimal("Infinity"), None),
    ])
    def test_strings_and_decimals(self, value, expected):
        from app.services.ai_providers.base import normalize_confidence
        assert normalize_confidence(value) == expected

    def test_json_string_confidence_now_accepted(self, provider):
        text = '{"description": "A person at the door.", "confidence": "85"}'
        assert provider._parse_confidence_response(text)[1] == 85

    @pytest.mark.parametrize("text,expected", [
        ("A person at the door. Confidence: 0.85", 85),
        ("A person at the door. Confidence: 85", 85),
        ("A person at the door. 0.9 confidence", 90),
        ("A person at the door. Confidence: 0.285", 29),
    ])
    def test_text_path(self, provider, text, expected):
        assert provider._parse_confidence_response(text)[1] == expected

    def test_litellm_paths(self):
        from app.services.litellm_provider import LiteLLMProvider
        p = LiteLLMProvider.__new__(LiteLLMProvider)
        assert p._parse_response('{"description": "A cat.", "confidence": 0.85}')[1] == 85
        assert p._parse_response('Note {"description": "A cat.", "confidence": 0.85} end')[1] == 85
        desc, conf, _ = p._parse_response("A cat on the porch. Confidence: 0.85")
        assert conf == 85 and "0.85" not in desc and "onfidence" not in desc
        assert p._parse_response('{"description": "A cat.", "confidence": 85}')[1] == 85
        assert p._parse_response('{"description": "A cat.", "confidence": NaN}')[1] is None
        assert p._parse_response("A cat. Confidence: 150")[1] is None

    def test_exactly_one_counter(self):
        from app.core.metrics import REGISTRY
        from app.services.ai_providers.base import normalize_confidence

        def count():
            return REGISTRY.get_sample_value("ai_confidence_exactly_one_total") or 0.0
        before = count()
        assert normalize_confidence(1) == 1
        assert normalize_confidence(1.0) == 1
        assert normalize_confidence("1") == 1
        normalize_confidence(0.85)
        normalize_confidence(100)
        assert count() - before == 3
