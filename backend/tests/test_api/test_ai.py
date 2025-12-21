"""Integration tests for AI API endpoints"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
from unittest.mock import patch, Mock, MagicMock, AsyncMock

from main import app
from app.services.ai_service import ai_service, AIService, AIProvider


client = TestClient(app)


class TestAIUsageEndpoint:
    """Test GET /api/v1/ai/usage endpoint"""

    def test_get_usage_stats_empty(self):
        """Test usage stats with no API calls"""
        # Mock empty database response
        ai_service.db = None  # Simulate no database configured

        response = client.get("/api/v1/ai/usage")

        assert response.status_code == 200
        data = response.json()

        assert data['total_calls'] == 0
        assert data['successful_calls'] == 0
        assert data['failed_calls'] == 0
        assert data['total_tokens'] == 0
        assert data['total_cost'] == 0.0
        assert isinstance(data['provider_breakdown'], dict)

    def test_get_usage_stats_with_data(self):
        """Test usage stats with API call history"""
        # Mock get_usage_stats to return sample data
        mock_stats = {
            'total_calls': 3,
            'successful_calls': 3,
            'failed_calls': 0,
            'total_tokens': 300,
            'total_cost': 0.053,
            'avg_response_time_ms': 600.0,
            'provider_breakdown': {
                'openai': {
                    'calls': 2,
                    'success_rate': 100.0,
                    'tokens': 220,
                    'cost': 0.033
                },
                'claude': {
                    'calls': 1,
                    'success_rate': 100.0,
                    'tokens': 80,
                    'cost': 0.02
                }
            }
        }

        with patch.object(ai_service, 'get_usage_stats', return_value=mock_stats):
            response = client.get("/api/v1/ai/usage")

        assert response.status_code == 200
        data = response.json()

        assert data['total_calls'] == 3
        assert data['successful_calls'] == 3
        assert data['failed_calls'] == 0
        assert data['total_tokens'] == 300
        assert data['total_cost'] == 0.053
        assert 'openai' in data['provider_breakdown']
        assert data['provider_breakdown']['openai']['calls'] == 2
        assert data['provider_breakdown']['claude']['calls'] == 1

    def test_get_usage_stats_with_date_filter(self):
        """Test usage stats with date range filtering"""
        # Mock filtered stats
        mock_stats = {
            'total_calls': 1,
            'successful_calls': 1,
            'failed_calls': 0,
            'total_tokens': 120,
            'total_cost': 0.018,
            'avg_response_time_ms': 600.0,
            'provider_breakdown': {
                'openai': {
                    'calls': 1,
                    'success_rate': 100.0,
                    'tokens': 120,
                    'cost': 0.018
                }
            }
        }

        with patch.object(ai_service, 'get_usage_stats', return_value=mock_stats):
            # Query for November 5-15 (should only get middle entry)
            response = client.get("/api/v1/ai/usage?start_date=2025-11-05&end_date=2025-11-15")

        assert response.status_code == 200
        data = response.json()

        assert data['total_calls'] == 1
        assert data['total_tokens'] == 120

    def test_get_usage_stats_provider_breakdown(self):
        """Test provider breakdown in usage stats"""
        # Mock stats with mixed success/failure
        mock_stats = {
            'total_calls': 3,
            'successful_calls': 2,
            'failed_calls': 1,
            'total_tokens': 180,
            'total_cost': 0.035,
            'avg_response_time_ms': 433.33,
            'provider_breakdown': {
                'openai': {
                    'calls': 2,
                    'success_rate': 50.0,  # 1 out of 2
                    'tokens': 100,
                    'cost': 0.015
                },
                'claude': {
                    'calls': 1,
                    'success_rate': 100.0,
                    'tokens': 80,
                    'cost': 0.02
                }
            }
        }

        with patch.object(ai_service, 'get_usage_stats', return_value=mock_stats):
            response = client.get("/api/v1/ai/usage")

        assert response.status_code == 200
        data = response.json()

        # Check provider breakdown
        openai_stats = data['provider_breakdown']['openai']
        assert openai_stats['calls'] == 2
        assert openai_stats['success_rate'] == 50.0  # 1 out of 2
        assert openai_stats['tokens'] == 100
        assert openai_stats['cost'] == 0.015

        claude_stats = data['provider_breakdown']['claude']
        assert claude_stats['calls'] == 1
        assert claude_stats['success_rate'] == 100.0
        assert claude_stats['tokens'] == 80
        assert claude_stats['cost'] == 0.02


# =============================================================================
# Story P3-4.1: Capabilities Endpoint Tests
# =============================================================================


class TestAICapabilitiesEndpoint:
    """Test GET /api/v1/ai/capabilities endpoint (Story P3-4.1)"""

    def test_get_capabilities_returns_all_providers(self):
        """Test capabilities endpoint returns info for all four providers"""
        # Mock get_all_capabilities to return expected data
        mock_capabilities = {
            "openai": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 10,
                "configured": True
            },
            "grok": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 10,
                "configured": True
            },
            "claude": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 20,
                "configured": False
            },
            "gemini": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 16,
                "configured": False
            }
        }

        with patch.object(ai_service, 'get_all_capabilities', return_value=mock_capabilities):
            response = client.get("/api/v1/ai/capabilities")

        assert response.status_code == 200
        data = response.json()

        # Check all providers are present
        assert "providers" in data
        assert set(data["providers"].keys()) == {"openai", "grok", "claude", "gemini"}

    def test_get_capabilities_video_providers(self):
        """Test capabilities shows correct video support (AC1)"""
        mock_capabilities = {
            "openai": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 10,
                "configured": True
            },
            "grok": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 10,
                "configured": True
            },
            "claude": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 20,
                "configured": True
            },
            "gemini": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 16,
                "configured": True
            }
        }

        with patch.object(ai_service, 'get_all_capabilities', return_value=mock_capabilities):
            response = client.get("/api/v1/ai/capabilities")

        assert response.status_code == 200
        data = response.json()

        # OpenAI and Gemini support video
        assert data["providers"]["openai"]["video"] is True
        assert data["providers"]["gemini"]["video"] is True

        # Claude and Grok do not
        assert data["providers"]["claude"]["video"] is False
        assert data["providers"]["grok"]["video"] is False

    def test_get_capabilities_video_limits(self):
        """Test capabilities shows correct video duration and size limits"""
        mock_capabilities = {
            "openai": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 10,
                "configured": True
            },
            "grok": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 10,
                "configured": False
            },
            "claude": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 20,
                "configured": False
            },
            "gemini": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 16,
                "configured": False
            }
        }

        with patch.object(ai_service, 'get_all_capabilities', return_value=mock_capabilities):
            response = client.get("/api/v1/ai/capabilities")

        assert response.status_code == 200
        data = response.json()

        # Video-capable providers have correct limits
        assert data["providers"]["openai"]["max_video_duration"] == 60
        assert data["providers"]["openai"]["max_video_size_mb"] == 20
        assert "mp4" in data["providers"]["openai"]["supported_formats"]

        # Non-video providers have zero limits
        assert data["providers"]["claude"]["max_video_duration"] == 0
        assert data["providers"]["claude"]["max_video_size_mb"] == 0
        assert data["providers"]["claude"]["supported_formats"] == []

    def test_get_capabilities_configured_flag(self):
        """Test capabilities shows correct configured status"""
        mock_capabilities = {
            "openai": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 10,
                "configured": True  # Has API key
            },
            "grok": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 10,
                "configured": False  # No API key
            },
            "claude": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 20,
                "configured": True  # Has API key
            },
            "gemini": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 16,
                "configured": False  # No API key
            }
        }

        with patch.object(ai_service, 'get_all_capabilities', return_value=mock_capabilities):
            response = client.get("/api/v1/ai/capabilities")

        assert response.status_code == 200
        data = response.json()

        assert data["providers"]["openai"]["configured"] is True
        assert data["providers"]["grok"]["configured"] is False
        assert data["providers"]["claude"]["configured"] is True
        assert data["providers"]["gemini"]["configured"] is False

    def test_get_capabilities_max_images(self):
        """Test capabilities shows correct max_images for multi-frame analysis"""
        mock_capabilities = {
            "openai": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 10,
                "configured": True
            },
            "grok": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 10,
                "configured": True
            },
            "claude": {
                "video": False,
                "max_video_duration": 0,
                "max_video_size_mb": 0,
                "supported_formats": [],
                "max_images": 20,
                "configured": True
            },
            "gemini": {
                "video": True,
                "max_video_duration": 60,
                "max_video_size_mb": 20,
                "supported_formats": ["mp4", "mov", "webm"],
                "max_images": 16,
                "configured": True
            }
        }

        with patch.object(ai_service, 'get_all_capabilities', return_value=mock_capabilities):
            response = client.get("/api/v1/ai/capabilities")

        assert response.status_code == 200
        data = response.json()

        # Check max_images for each provider
        assert data["providers"]["openai"]["max_images"] == 10
        assert data["providers"]["grok"]["max_images"] == 10
        assert data["providers"]["claude"]["max_images"] == 20
        assert data["providers"]["gemini"]["max_images"] == 16


# =============================================================================
# Story P8-3.3: Prompt Refinement Endpoint Tests
# =============================================================================


class TestPromptRefinementEndpoint:
    """Test POST /api/v1/ai/refine-prompt endpoint (Story P8-3.3)"""

    def test_refine_prompt_no_feedback_returns_400(self):
        """AC3.10: Test that 400 is returned when no feedback data available"""
        request_data = {
            "current_prompt": "Describe what you see in this image.",
            "include_feedback": True,
            "max_feedback_samples": 50
        }

        response = client.post("/api/v1/ai/refine-prompt", json=request_data)

        # Should return 400 when no feedback data
        assert response.status_code == 400
        data = response.json()
        assert "No feedback data available" in data["detail"]

    def test_refine_prompt_request_validation(self):
        """Test request validation for prompt refinement"""
        # Test with missing current_prompt
        response = client.post("/api/v1/ai/refine-prompt", json={})
        assert response.status_code == 422  # Validation error

        # Test with empty prompt (should still work - validation only requires presence)
        request_data = {
            "current_prompt": "",
            "include_feedback": True
        }
        response = client.post("/api/v1/ai/refine-prompt", json=request_data)
        # Still returns 400 due to no feedback, not 422
        assert response.status_code == 400

    def test_refine_prompt_max_samples_validation(self):
        """Test max_feedback_samples validation (1-100)"""
        # Test with invalid max_feedback_samples (too low)
        request_data = {
            "current_prompt": "Test prompt",
            "max_feedback_samples": 0
        }
        response = client.post("/api/v1/ai/refine-prompt", json=request_data)
        assert response.status_code == 422  # Validation error

        # Test with invalid max_feedback_samples (too high)
        request_data = {
            "current_prompt": "Test prompt",
            "max_feedback_samples": 150
        }
        response = client.post("/api/v1/ai/refine-prompt", json=request_data)
        assert response.status_code == 422  # Validation error


class TestPromptRefinementHelpers:
    """Test helper functions for prompt refinement (Story P8-3.3)"""

    def test_build_refinement_meta_prompt_with_positive_examples(self):
        """Test meta-prompt includes positive feedback examples"""
        from app.api.v1.ai import _build_refinement_meta_prompt

        current_prompt = "Describe what you see."
        positive_examples = [
            {"description": "A person walking on the driveway", "rating": "helpful", "correction": None},
            {"description": "Delivery truck parked at the curb", "rating": "helpful", "correction": None},
        ]
        negative_examples = []

        result = _build_refinement_meta_prompt(current_prompt, positive_examples, negative_examples)

        assert "CURRENT PROMPT:" in result
        assert current_prompt in result
        assert "POSITIVE FEEDBACK" in result
        assert "A person walking on the driveway" in result
        assert "Delivery truck parked at the curb" in result

    def test_build_refinement_meta_prompt_with_negative_examples(self):
        """Test meta-prompt includes negative feedback with corrections"""
        from app.api.v1.ai import _build_refinement_meta_prompt

        current_prompt = "Describe what you see."
        positive_examples = []
        negative_examples = [
            {"description": "Motion detected", "rating": "not_helpful", "correction": "Should mention the car"},
            {"description": "Person visible", "rating": "not_helpful", "correction": "Too vague"},
        ]

        result = _build_refinement_meta_prompt(current_prompt, positive_examples, negative_examples)

        assert "NEGATIVE FEEDBACK" in result
        assert "Motion detected" in result
        assert "Should mention the car" in result
        assert "Person visible" in result
        assert "Too vague" in result

    def test_build_refinement_meta_prompt_limits_examples(self):
        """Test meta-prompt limits to 10 examples each"""
        from app.api.v1.ai import _build_refinement_meta_prompt

        current_prompt = "Describe what you see."
        # Create 15 positive examples
        positive_examples = [
            {"description": f"Description {i}", "rating": "helpful", "correction": None}
            for i in range(15)
        ]
        negative_examples = []

        result = _build_refinement_meta_prompt(current_prompt, positive_examples, negative_examples)

        # Count how many descriptions are included
        count = sum(1 for i in range(15) if f"Description {i}" in result)
        assert count == 10  # Should be limited to 10

    def test_parse_refinement_response_valid_format(self):
        """Test parsing of well-formatted AI response"""
        from app.api.v1.ai import _parse_refinement_response

        response_text = """
SUGGESTED_PROMPT:
You are analyzing a home security camera image. Describe people, vehicles, and actions.

CHANGES_SUMMARY:
Added structured format based on positive feedback patterns.
"""

        result = _parse_refinement_response(response_text)

        assert "suggested_prompt" in result
        assert "changes_summary" in result
        assert "home security camera" in result["suggested_prompt"]
        assert "structured format" in result["changes_summary"]

    def test_parse_refinement_response_fallback_format(self):
        """Test parsing handles response without expected format"""
        from app.api.v1.ai import _parse_refinement_response

        # Response without proper sections
        response_text = "Just improve the prompt by adding more detail about vehicles and people."

        result = _parse_refinement_response(response_text)

        # Should use entire response as prompt with generic summary
        assert "suggested_prompt" in result
        assert "changes_summary" in result
        assert "vehicles and people" in result["suggested_prompt"]

    def test_parse_refinement_response_cleans_formatting(self):
        """Test parsing removes formatting artifacts"""
        from app.api.v1.ai import _parse_refinement_response

        response_text = """SUGGESTED_PROMPT:
```
"Clean prompt text here"
```

CHANGES_SUMMARY:
Made improvements."""

        result = _parse_refinement_response(response_text)

        # Should clean up backticks and quotes
        assert "`" not in result["suggested_prompt"]
        assert result["suggested_prompt"].strip() == "Clean prompt text here"
