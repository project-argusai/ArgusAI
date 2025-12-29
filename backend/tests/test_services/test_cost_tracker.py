"""
Tests for CostTracker Service

Story P3-7.1: Implement Cost Tracking Service
"""

import os
import pytest
from decimal import Decimal
from unittest.mock import patch

from app.services.cost_tracker import (
    CostTracker,
    get_cost_tracker,
    PROVIDER_COST_RATES,
    TOKENS_PER_IMAGE,
)


class TestCostTracker:
    """Test suite for CostTracker service."""

    @pytest.fixture
    def tracker(self):
        """Create a fresh CostTracker instance for each test."""
        return CostTracker()

    # =========================================================================
    # AC1: Calculate and Store Cost Per AI Request
    # =========================================================================

    def test_calculate_cost_openai(self, tracker):
        """Test cost calculation for OpenAI with known token counts."""
        # 1000 input tokens, 500 output tokens
        # Input: (1000/1000) * 0.00015 = 0.00015
        # Output: (500/1000) * 0.0006 = 0.0003
        # Total: 0.00045
        cost = tracker.calculate_cost("openai", 1000, 500)
        assert cost == Decimal("0.000450")

    def test_calculate_cost_grok(self, tracker):
        """Test cost calculation for xAI Grok."""
        # 1000 input, 500 output
        # Input: (1000/1000) * 0.0001 = 0.0001
        # Output: (500/1000) * 0.0003 = 0.00015
        # Total: 0.00025
        cost = tracker.calculate_cost("grok", 1000, 500)
        assert cost == Decimal("0.000250")

    def test_calculate_cost_claude(self, tracker):
        """Test cost calculation for Claude Haiku."""
        # 1000 input, 500 output
        # Input: (1000/1000) * 0.00025 = 0.00025
        # Output: (500/1000) * 0.00125 = 0.000625
        # Total: 0.000875
        cost = tracker.calculate_cost("claude", 1000, 500)
        assert cost == Decimal("0.000875")

    def test_calculate_cost_gemini_free_tier(self, tracker):
        """Test cost calculation for Gemini Flash (free tier)."""
        cost = tracker.calculate_cost("gemini", 1000, 500)
        assert cost == Decimal("0.000000")

    def test_calculate_cost_zero_tokens(self, tracker):
        """Test cost with zero tokens returns zero."""
        cost = tracker.calculate_cost("openai", 0, 0)
        assert cost == Decimal("0.000000")

    def test_calculate_cost_unknown_provider(self, tracker):
        """Test unknown provider returns zero cost with warning."""
        cost = tracker.calculate_cost("unknown_provider", 1000, 500)
        assert cost == Decimal("0.000000")

    def test_calculate_cost_case_insensitive(self, tracker):
        """Test provider name is case insensitive."""
        cost_lower = tracker.calculate_cost("openai", 1000, 500)
        cost_upper = tracker.calculate_cost("OPENAI", 1000, 500)
        cost_mixed = tracker.calculate_cost("OpenAI", 1000, 500)
        assert cost_lower == cost_upper == cost_mixed

    def test_calculate_cost_precision(self, tracker):
        """Test cost is stored with 6 decimal places."""
        cost = tracker.calculate_cost("openai", 1, 1)
        # Very small cost should still have 6 decimal places
        assert isinstance(cost, Decimal)
        assert cost.as_tuple().exponent == -6

    # =========================================================================
    # AC2: Support Provider-Specific Cost Rates
    # =========================================================================

    def test_provider_rates_match_expected(self, tracker):
        """Test that default rates match expected values."""
        rates = tracker.get_all_rates()

        # OpenAI: $0.00015 input, $0.0006 output
        assert rates["openai"]["input"] == 0.00015
        assert rates["openai"]["output"] == 0.0006

        # Grok: $0.0001 input, $0.0003 output
        assert rates["grok"]["input"] == 0.0001
        assert rates["grok"]["output"] == 0.0003

        # Claude: $0.00025 input, $0.00125 output
        assert rates["claude"]["input"] == 0.00025
        assert rates["claude"]["output"] == 0.00125

        # Gemini: Free tier
        assert rates["gemini"]["input"] == 0.0
        assert rates["gemini"]["output"] == 0.0

    def test_rate_override_via_environment(self):
        """Test cost rates can be overridden via environment variables."""
        with patch.dict(os.environ, {
            "AI_COST_RATE_OPENAI_INPUT": "0.001",
            "AI_COST_RATE_OPENAI_OUTPUT": "0.002",
        }):
            tracker = CostTracker()
            rates = tracker.get_provider_rates("openai")
            assert rates["input"] == 0.001
            assert rates["output"] == 0.002

    def test_invalid_env_override_uses_default(self):
        """Test invalid env value falls back to default."""
        with patch.dict(os.environ, {
            "AI_COST_RATE_OPENAI_INPUT": "not_a_number",
        }):
            tracker = CostTracker()
            rates = tracker.get_provider_rates("openai")
            # Should use default
            assert rates["input"] == 0.00015

    def test_get_provider_rates_unknown_returns_none(self, tracker):
        """Test getting rates for unknown provider returns None."""
        rates = tracker.get_provider_rates("unknown")
        assert rates is None

    # =========================================================================
    # AC4: Track Image/Token Costs for Multi-Image Requests
    # =========================================================================

    def test_multi_image_cost_openai_low_res(self, tracker):
        """Test multi-image cost calculation for OpenAI low resolution."""
        # 3 images at 85 tokens each = 255 image tokens
        # Plus 50 base tokens = 305 input tokens
        # Output: 150 tokens (default)
        cost = tracker.calculate_multi_image_cost("openai", 3, "low_res")

        # Expected: input (305/1000)*0.00015 + output (150/1000)*0.0006
        # = 0.00004575 + 0.00009 = 0.00013575
        expected_input_tokens = 50 + (3 * 85)  # 305
        expected = tracker.calculate_cost("openai", expected_input_tokens, 150)
        assert cost == expected

    def test_multi_image_cost_openai_high_res(self, tracker):
        """Test multi-image cost calculation for OpenAI high resolution."""
        cost = tracker.calculate_multi_image_cost("openai", 3, "high_res")

        # 3 images at 765 tokens each = 2295 image tokens
        # Plus 50 base = 2345 input tokens
        expected_input_tokens = 50 + (3 * 765)  # 2345
        expected = tracker.calculate_cost("openai", expected_input_tokens, 150)
        assert cost == expected

    def test_multi_image_cost_claude(self, tracker):
        """Test multi-image cost calculation for Claude."""
        cost = tracker.calculate_multi_image_cost("claude", 3)

        # 3 images at 1334 tokens each = 4002 image tokens
        # Plus 50 base = 4052 input tokens
        expected_input_tokens = 50 + (3 * 1334)
        expected = tracker.calculate_cost("claude", expected_input_tokens, 150)
        assert cost == expected

    def test_multi_image_cost_single_image(self, tracker):
        """Test multi-image cost works for single image."""
        cost = tracker.calculate_multi_image_cost("openai", 1)
        assert cost > Decimal("0")

    def test_multi_image_cost_custom_output_tokens(self, tracker):
        """Test multi-image cost with custom output token count."""
        cost_default = tracker.calculate_multi_image_cost("openai", 3)
        cost_custom = tracker.calculate_multi_image_cost("openai", 3, "default", 300)
        # Custom output should result in higher cost
        assert cost_custom > cost_default

    # =========================================================================
    # AC5: Handle Missing Token Information
    # =========================================================================

    def test_estimate_tokens_returns_estimated_flag(self, tracker):
        """Test token estimation returns is_estimated=True."""
        input_tokens, output_tokens, is_estimated = tracker.estimate_tokens(
            image_count=3,
            response_length=200,
            provider="openai"
        )
        assert is_estimated is True
        assert input_tokens > 0
        assert output_tokens > 0

    def test_estimate_tokens_conservative(self, tracker):
        """Test token estimates are conservative (include safety margin)."""
        input_tokens, output_tokens, _ = tracker.estimate_tokens(
            image_count=3,
            response_length=200,
            provider="openai"
        )

        # 3 images * 85 tokens + 100 base = 355
        # With 20% safety margin: 355 * 1.2 = 426
        expected_base = (3 * 85) + 100
        expected_with_margin = int(expected_base * 1.2)
        assert input_tokens == expected_with_margin

    def test_estimate_tokens_uses_provider_image_rates(self, tracker):
        """Test estimation uses correct provider image token rates."""
        input_openai, _, _ = tracker.estimate_tokens(3, 200, "openai")
        input_claude, _, _ = tracker.estimate_tokens(3, 200, "claude")

        # Claude has higher token-per-image rate (1334 vs 85)
        assert input_claude > input_openai

    def test_estimate_tokens_minimum_output(self, tracker):
        """Test output tokens have a minimum value."""
        _, output_tokens, _ = tracker.estimate_tokens(
            image_count=1,
            response_length=10,  # Very short response
            provider="openai"
        )
        # Should be at least 50 * 1.2 = 60 (minimum with safety margin)
        assert output_tokens >= 60


class TestGetCostTracker:
    """Test the singleton getter function."""

    def test_returns_cost_tracker_instance(self):
        """Test get_cost_tracker returns a CostTracker."""
        tracker = get_cost_tracker()
        assert isinstance(tracker, CostTracker)

    def test_returns_singleton(self):
        """Test get_cost_tracker returns the same instance."""
        tracker1 = get_cost_tracker()
        tracker2 = get_cost_tracker()
        assert tracker1 is tracker2


class TestCostRateConstants:
    """Test the cost rate constants are properly defined."""

    @pytest.mark.parametrize("provider", ["openai", "grok", "claude", "gemini", "whisper"])
    def test_all_providers_have_rates(self, provider):
        """Test all expected providers have cost rates defined."""
        assert provider in PROVIDER_COST_RATES
        assert "input" in PROVIDER_COST_RATES[provider]
        assert "output" in PROVIDER_COST_RATES[provider]

    @pytest.mark.parametrize("provider", ["openai", "grok", "claude", "gemini"])
    def test_all_providers_have_image_tokens(self, provider):
        """Test all vision providers have image token estimates."""
        assert provider in TOKENS_PER_IMAGE
        assert "default" in TOKENS_PER_IMAGE[provider]

    @pytest.mark.parametrize("provider", ["openai", "grok", "claude", "gemini", "whisper"])
    def test_rates_are_non_negative(self, provider):
        """Test all rates are non-negative."""
        rates = PROVIDER_COST_RATES[provider]
        assert rates["input"] >= 0, f"{provider} input rate is negative"
        assert rates["output"] >= 0, f"{provider} output rate is negative"
