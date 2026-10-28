"""#748: one 0-100 confidence scale in the prompt; box and event conversions.

All data synthetic.
"""
import math

import pytest

from app.services.prompt_templates import BOUNDING_BOX_INSTRUCTION


class TestPromptScale:
    def test_box_confidence_asks_for_0_100(self):
        assert "0.0 to 1.0 for that specific detection" not in BOUNDING_BOX_INSTRUCTION
        assert "Rate confidence 0 to 100" in BOUNDING_BOX_INSTRUCTION
        assert "confidence: 0.92" not in BOUNDING_BOX_INSTRUCTION
        assert "confidence: 92" in BOUNDING_BOX_INSTRUCTION
        assert '"confidence": 85' in BOUNDING_BOX_INSTRUCTION

    def test_coordinates_still_normalized(self):
        assert "normalized coordinates (0.0 to 1.0)" in BOUNDING_BOX_INSTRUCTION


class TestBoxConfidence:
    @pytest.mark.parametrize("value,expected", [
        (92, 0.92), (92.0, 0.92), (100, 1.0), (50, 0.5), (2, 0.02),
        (0.92, 0.92), (1, 1.0), (1.0, 1.0), (0, 0.0),  # old 0-1 replies still read
        (None, 0.5), (float("nan"), 0.5), (float("inf"), 0.5), (150, 0.5), (-3, 0.5),
        (True, 0.5), ("92", 0.92), (" 92 ", 0.92), ("1", 1.0), ("0.9", 0.9),
        (0.005, 0.01), ("abc", 0.5), ("-3", 0.5), ("150", 0.5),
    ])
    def test_box_confidence_to_fraction(self, value, expected):
        from app.services.ai_providers.base import box_confidence_fraction
        got = box_confidence_fraction(value)
        assert isinstance(got, float) and math.isclose(got, expected)

    def test_parsed_boxes_store_fraction(self):
        from app.services.ai_providers.base import AIProviderBase
        from app.services.ai_providers.openai_provider import OpenAIProvider
        p = OpenAIProvider.__new__(OpenAIProvider)
        AIProviderBase.__init__(p, "test-api-key")
        text = ('{"description": "A person.", "confidence": 85, "bounding_boxes": ['
                '{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4, "entity_type": "person", "confidence": 92},'
                '{"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.1, "entity_type": "vehicle", "confidence": 0.7}]}')
        _, conf, boxes = p._parse_confidence_response(text)
        assert conf == 85
        assert [b["confidence"] for b in boxes] == [0.92, 0.7]


class TestEventConfidence:
    @pytest.mark.parametrize("value,expected", [
        (85, 85), (1, 1), (1.0, 1), (0, 0), (100, 100), (0.85, 85), (0.285, 29), (85.7, 85),
        (None, 0), (float("nan"), 0), (float("inf"), 0), (-5, 0), (150, 0), (100.5, 0), (True, 0),
        ("85", 85), ("0.85", 85), ("abc", 0),
    ])
    def test_event_confidence(self, value, expected):
        from app.services.event_processor import _event_confidence
        got = _event_confidence(value)
        assert got == expected and type(got) is int


class TestNoDoubleCount:
    def test_box_and_event_do_not_count_exact_one(self):
        from app.core.metrics import ai_confidence_exactly_one_total
        from app.services.ai_providers.base import box_confidence_fraction
        from app.services.event_processor import _event_confidence
        before = ai_confidence_exactly_one_total._value.get()
        assert box_confidence_fraction(1) == 1.0
        assert _event_confidence(1) == 1
        assert ai_confidence_exactly_one_total._value.get() == before


class TestLiteLLMEventConfidence:
    @pytest.mark.parametrize("raw,expected", [("85", 85), ("0.85", 85), ("150", None), ("1", 1)])
    def test_json_confidence_normalized(self, raw, expected):
        from app.services.litellm_provider import LiteLLMProvider
        p = LiteLLMProvider.__new__(LiteLLMProvider)
        text = '{"description": "A person.", "confidence": %s, "bounding_boxes": [{"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2, "entity_type": "person", "confidence": "92"}]}' % raw
        _, conf, boxes = p._parse_response(text)
        assert conf == expected
        assert boxes[0]["confidence"] == 0.92
