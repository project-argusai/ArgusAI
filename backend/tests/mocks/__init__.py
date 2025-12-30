"""
Mock Factories Package (Story P14-8.3)

Provides factory functions for creating realistic mock objects
that match actual SDK types and API response structures.
"""
from tests.mocks.ai_mocks import (
    create_openai_completion,
    create_anthropic_message,
    create_openai_error,
)
from tests.mocks.http_mocks import (
    create_http_response,
    create_json_response,
    create_error_response,
)

__all__ = [
    # AI Mocks
    "create_openai_completion",
    "create_anthropic_message",
    "create_openai_error",
    # HTTP Mocks
    "create_http_response",
    "create_json_response",
    "create_error_response",
]
