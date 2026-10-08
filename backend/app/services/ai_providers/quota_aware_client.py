"""Vision-provider HTTP clients that do not retry quota failures.

The OpenAI and Anthropic SDKs retry HTTP 429 by default. A quota or no-credit
429 will not succeed on the next attempt, and those retries used to consume
the analysis budget before the fallback chain could move on. Rate-limit 429s
and server errors are still retried by the SDK. The orchestrator also refuses
to retry quota errors, and bounds every attempt with the remaining budget.
"""

from __future__ import annotations

import logging
from typing import Optional

import anthropic
import httpx
import openai

from app.services.ai_provider_order import is_quota_error

logger = logging.getLogger(__name__)

# Placeholder bearer value for local OpenAI-compatible servers (Ollama,
# mlx-vlm, LM Studio). They ignore it; the SDK requires a non-empty key.
LOCAL_PROVIDER_API_KEY = "local-no-key"


def response_body_is_quota(response: httpx.Response) -> bool:
    """True when an HTTP response body is a quota or no-credit failure.

    The body is not logged. A body that cannot be read is treated as not
    quota, so an ordinary rate-limit 429 is still retried by the SDK.
    """
    try:
        body: Optional[str] = response.text
    except Exception:
        return False
    return is_quota_error(body)


class _QuotaRetryMixin:
    """Refuse SDK retries when a 429 body is a quota or credit failure."""

    _quota_provider_name = "provider"

    def _should_retry(self, response: httpx.Response) -> bool:
        if response.status_code == 429 and response_body_is_quota(response):
            logger.info(
                "Not retrying quota or no-credit 429 for %s",
                self._quota_provider_name,
            )
            return False
        return super()._should_retry(response)


class QuotaAwareAsyncOpenAI(_QuotaRetryMixin, openai.AsyncOpenAI):
    """OpenAI-compatible client. An xAI base URL is logged as grok."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_url = str(kwargs.get("base_url") or "")
        if "x.ai" in base_url:
            self._quota_provider_name = "grok"
        elif kwargs.get("api_key") == LOCAL_PROVIDER_API_KEY:
            self._quota_provider_name = "local"
        else:
            self._quota_provider_name = "openai"


class QuotaAwareAsyncAnthropic(_QuotaRetryMixin, anthropic.AsyncAnthropic):
    """Anthropic client that does not retry quota or no-credit 429s."""

    _quota_provider_name = "claude"


def build_openai_client(
    api_key: str,
    base_url: Optional[str] = None,
    max_retries: Optional[int] = None,
) -> QuotaAwareAsyncOpenAI:
    """Async OpenAI-compatible client.

    ``base_url`` selects the xAI endpoint or a local OpenAI-compatible server.
    ``max_retries`` overrides the SDK default (2); a local server that is down
    should fail fast instead of retrying.
    """
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return QuotaAwareAsyncOpenAI(**kwargs)


def build_anthropic_client(api_key: str) -> QuotaAwareAsyncAnthropic:
    """Async Anthropic client that does not retry quota or no-credit 429s."""
    return QuotaAwareAsyncAnthropic(api_key=api_key)
