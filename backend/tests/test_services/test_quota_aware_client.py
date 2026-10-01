"""SDK clients must not retry quota or no-credit 429s."""

import logging

import httpx

from app.services.ai_provider_order import (
    analysis_failure_log_detail,
    is_quota_error,
)
from app.services.ai_providers.quota_aware_client import (
    QuotaAwareAsyncAnthropic,
    QuotaAwareAsyncOpenAI,
    response_body_is_quota,
)


def _response(status_code: int, body: str) -> httpx.Response:
    return httpx.Response(status_code, text=body)


def test_chain_summary_is_logged_and_raw_bodies_are_not():
    summary = (
        "All providers failed (multi-frame). "
        "attempted=[grok:quota_exhausted, openai:http_429]"
    )
    assert analysis_failure_log_detail(summary) == summary
    raw = (
        "Error code: 429 - {'error': {'message': 'sk-live-secret-key-do-not-log'}}"
    )
    detail = analysis_failure_log_detail(raw)
    assert detail == "http_429"
    assert "sk-live-secret" not in detail
    body = "provider said sk-live-secret-key-do-not-log and nothing else"
    assert analysis_failure_log_detail(body) == "provider_error"
    assert analysis_failure_log_detail(None) == "unknown"


def test_is_quota_error_matches_no_credit_and_not_plain_rate_limits():
    assert is_quota_error("Error code: 429 insufficient_quota")
    assert is_quota_error("You have no credits remaining")
    assert is_quota_error("Your credit balance is too low")
    assert not is_quota_error("Error code: 429 Rate limit exceeded")
    assert not is_quota_error(None)


def test_openai_client_does_not_retry_quota_429(caplog):
    caplog.set_level(logging.INFO)
    client = QuotaAwareAsyncOpenAI(api_key="test-key-not-real")
    body = (
        '{"error":{"type":"insufficient_quota",'
        '"message":"no credits sk-live-secret-key-do-not-log"}}'
    )
    assert client._should_retry(_response(429, body)) is False
    assert "sk-live-secret" not in caplog.text
    assert response_body_is_quota(_response(429, body)) is True


def test_openai_client_still_retries_rate_limit_429():
    client = QuotaAwareAsyncOpenAI(api_key="test-key-not-real")
    assert client._should_retry(_response(429, "Rate limit exceeded")) is True


def test_anthropic_client_does_not_retry_quota_429():
    client = QuotaAwareAsyncAnthropic(api_key="test-key-not-real")
    body = '{"error":{"message":"You have no credits"}}'
    assert client._should_retry(_response(429, body)) is False


def test_unreadable_body_does_not_count_as_quota():
    class _Broken:
        status_code = 429

        @property
        def text(self):
            raise RuntimeError("unread")

        headers = {}

    assert response_body_is_quota(_Broken()) is False
