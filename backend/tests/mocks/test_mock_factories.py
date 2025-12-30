"""
Tests for Mock Factories (Story P14-8.3)

Verifies that mock factories produce correctly structured objects
that match real SDK types.
"""
import pytest
import json

from tests.mocks.ai_mocks import (
    create_openai_completion,
    create_anthropic_message,
    create_openai_error,
    create_gemini_response,
    MockChatCompletion,
    MockAnthropicMessage,
    MockRateLimitError,
)
from tests.mocks.http_mocks import (
    create_http_response,
    create_json_response,
    create_error_response,
    create_webhook_success_response,
    create_apns_success_response,
    create_fcm_success_response,
    MockHTTPResponse,
)


class TestOpenAIMocks:
    """Tests for OpenAI mock factories."""

    def test_create_completion_default(self):
        """Test creating a default OpenAI completion."""
        completion = create_openai_completion()

        assert completion.id.startswith("chatcmpl-")
        assert len(completion.choices) == 1
        assert completion.choices[0].message.content == "A person was detected walking toward the front door."
        assert completion.choices[0].message.role == "assistant"
        assert completion.choices[0].finish_reason == "stop"
        assert completion.model == "gpt-4o-mini"
        assert completion.object == "chat.completion"
        assert completion.usage.total_tokens == 150

    def test_create_completion_custom(self):
        """Test creating a custom OpenAI completion."""
        completion = create_openai_completion(
            content="A vehicle parked in the driveway.",
            model="gpt-4o",
            prompt_tokens=200,
            completion_tokens=100,
        )

        assert completion.choices[0].message.content == "A vehicle parked in the driveway."
        assert completion.model == "gpt-4o"
        assert completion.usage.prompt_tokens == 200
        assert completion.usage.completion_tokens == 100
        assert completion.usage.total_tokens == 300

    def test_completion_has_required_fields(self):
        """Test that completion has all required fields."""
        completion = create_openai_completion()

        # All required fields should be present
        assert hasattr(completion, "id")
        assert hasattr(completion, "choices")
        assert hasattr(completion, "created")
        assert hasattr(completion, "model")
        assert hasattr(completion, "object")
        assert hasattr(completion, "usage")

        # Nested fields
        assert hasattr(completion.choices[0], "finish_reason")
        assert hasattr(completion.choices[0], "index")
        assert hasattr(completion.choices[0], "message")
        assert hasattr(completion.choices[0].message, "content")
        assert hasattr(completion.choices[0].message, "role")

    def test_create_rate_limit_error(self):
        """Test creating a rate limit error."""
        error = create_openai_error(error_type="rate_limit")

        assert isinstance(error, MockRateLimitError)
        assert "rate limit" in error.message.lower()
        assert error.code == "rate_limit_exceeded"


class TestAnthropicMocks:
    """Tests for Anthropic mock factories."""

    def test_create_message_default(self):
        """Test creating a default Anthropic message."""
        message = create_anthropic_message()

        assert message.id.startswith("msg-")
        assert len(message.content) == 1
        assert message.content[0].text == "A person was detected at the entrance."
        assert message.content[0].type == "text"
        assert message.role == "assistant"
        assert message.stop_reason == "end_turn"
        assert message.type == "message"

    def test_create_message_custom(self):
        """Test creating a custom Anthropic message."""
        message = create_anthropic_message(
            content="A package was delivered to the porch.",
            model="claude-3-opus-20240229",
            input_tokens=500,
            output_tokens=200,
        )

        assert message.content[0].text == "A package was delivered to the porch."
        assert message.model == "claude-3-opus-20240229"
        assert message.usage.input_tokens == 500
        assert message.usage.output_tokens == 200


class TestGeminiMocks:
    """Tests for Gemini mock factories."""

    def test_create_response_default(self):
        """Test creating a default Gemini response."""
        response = create_gemini_response()

        assert len(response.candidates) == 1
        assert response.text == "A person was detected in the camera view."
        assert response.candidates[0].finish_reason == "STOP"

    def test_create_response_usage(self):
        """Test Gemini response usage metadata."""
        response = create_gemini_response(
            prompt_tokens=150,
            completion_tokens=75,
        )

        assert response.usage_metadata["prompt_token_count"] == 150
        assert response.usage_metadata["candidates_token_count"] == 75
        assert response.usage_metadata["total_token_count"] == 225


class TestHTTPMocks:
    """Tests for HTTP response mock factories."""

    def test_create_http_response_success(self):
        """Test creating a successful HTTP response."""
        response = create_http_response(
            status_code=200,
            json_data={"status": "ok"},
        )

        assert response.status_code == 200
        assert response.is_success is True
        assert response.is_error is False
        assert response.json() == {"status": "ok"}

    def test_create_http_response_error(self):
        """Test creating an error HTTP response."""
        response = create_http_response(
            status_code=500,
            json_data={"error": "Internal error"},
        )

        assert response.status_code == 500
        assert response.is_success is False
        assert response.is_error is True

    def test_response_raise_for_status(self):
        """Test raise_for_status behavior."""
        success = create_http_response(status_code=200)
        success.raise_for_status()  # Should not raise

        error = create_http_response(status_code=500)
        with pytest.raises(Exception):
            error.raise_for_status()

    def test_create_json_response(self):
        """Test JSON response factory."""
        response = create_json_response(
            data={"key": "value", "count": 42},
            status_code=201,
        )

        assert response.status_code == 201
        assert response.json() == {"key": "value", "count": 42}
        assert "application/json" in response.headers.get("content-type")

    def test_create_error_response(self):
        """Test error response factory."""
        response = create_error_response(
            status_code=400,
            error_message="Bad request",
            error_code="INVALID_INPUT",
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Bad request"
        assert data["code"] == "INVALID_INPUT"


class TestWebhookMocks:
    """Tests for webhook-specific mock factories."""

    def test_create_webhook_success(self):
        """Test webhook success response."""
        response = create_webhook_success_response(
            webhook_id="wh-test-123",
        )

        assert response.status_code == 200
        assert response.json()["status"] == "received"
        assert response.json()["webhook_id"] == "wh-test-123"


class TestPushNotificationMocks:
    """Tests for push notification mock factories."""

    def test_create_apns_success(self):
        """Test APNS success response."""
        response = create_apns_success_response(apns_id="test-apns-id")

        assert response.status_code == 200
        assert response.headers.get("apns-id") == "test-apns-id"

    def test_create_fcm_success(self):
        """Test FCM success response."""
        response = create_fcm_success_response(
            message_id="projects/test/messages/123"
        )

        assert response.status_code == 200
        assert response.json()["name"] == "projects/test/messages/123"
