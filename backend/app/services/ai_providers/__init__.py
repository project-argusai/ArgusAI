"""
AI Providers Package

Contains the concrete implementations for all supported vision AI providers:
- OpenAI (GPT-4o mini)
- xAI Grok
- Anthropic Claude
- Google Gemini
- Local OpenAI-compatible server (Ollama, mlx-vlm, LM Studio). Not part of
  the cloud fallback chain; used only by the background local fallback.

This package was extracted from the original monolithic ai_service.py during
Phase 3.3 of the ai_service decomposition (issue #444).

Usage:
    from app.services.ai_providers import (
        AIProviderBase,
        OpenAIProvider,
        GrokProvider,
        ClaudeProvider,
        GeminiProvider,
    )
"""

from .base import AIProviderBase
from .openai_provider import OpenAIProvider
from .grok_provider import GrokProvider
from .claude_provider import ClaudeProvider
from .gemini_provider import GeminiProvider
from .local_provider import LocalVLMProvider

__all__ = [
    "AIProviderBase",
    "OpenAIProvider",
    "GrokProvider",
    "ClaudeProvider",
    "GeminiProvider",
    "LocalVLMProvider",
]

# Cloud provider registry for convenience. The local provider is deliberately
# not listed: it needs a base URL and model, not an API key.
ALL_PROVIDERS = {
    "openai": OpenAIProvider,
    "grok": GrokProvider,
    "claude": ClaudeProvider,
    "gemini": GeminiProvider,
}
