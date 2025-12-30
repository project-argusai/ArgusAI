"""
AI Service Mock Factories (Story P14-8.3)

Factory functions for creating realistic AI API response objects
that match the actual SDK types used by OpenAI, Anthropic, etc.
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import time


# ============================================================================
# OpenAI Mock Types
# ============================================================================

@dataclass
class MockCompletionUsage:
    """Mock OpenAI CompletionUsage object."""
    completion_tokens: int = 50
    prompt_tokens: int = 100
    total_tokens: int = 150


@dataclass
class MockChatCompletionMessage:
    """Mock OpenAI ChatCompletionMessage object."""
    content: str
    role: str = "assistant"
    function_call: Optional[Dict] = None
    tool_calls: Optional[List] = None


@dataclass
class MockChoice:
    """Mock OpenAI Choice object."""
    finish_reason: str = "stop"
    index: int = 0
    message: MockChatCompletionMessage = None
    logprobs: Optional[Any] = None

    def __post_init__(self):
        if self.message is None:
            self.message = MockChatCompletionMessage(content="Mock response")


@dataclass
class MockChatCompletion:
    """
    Mock OpenAI ChatCompletion object.

    Matches the structure of openai.types.chat.ChatCompletion.
    """
    id: str = "chatcmpl-mock-12345"
    choices: List[MockChoice] = field(default_factory=list)
    created: int = field(default_factory=lambda: int(time.time()))
    model: str = "gpt-4o-mini"
    object: str = "chat.completion"
    usage: MockCompletionUsage = field(default_factory=MockCompletionUsage)
    system_fingerprint: Optional[str] = None

    def __post_init__(self):
        if not self.choices:
            self.choices = [MockChoice()]


def create_openai_completion(
    content: str = "A person was detected walking toward the front door.",
    model: str = "gpt-4o-mini",
    finish_reason: str = "stop",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    completion_id: Optional[str] = None,
) -> MockChatCompletion:
    """
    Create a realistic OpenAI ChatCompletion mock.

    Args:
        content: The response content
        model: Model name
        finish_reason: Why the completion stopped
        prompt_tokens: Tokens in the prompt
        completion_tokens: Tokens in the response
        completion_id: Optional custom completion ID

    Returns:
        MockChatCompletion that matches OpenAI SDK structure
    """
    return MockChatCompletion(
        id=completion_id or f"chatcmpl-{int(time.time())}",
        choices=[
            MockChoice(
                finish_reason=finish_reason,
                index=0,
                message=MockChatCompletionMessage(
                    content=content,
                    role="assistant",
                ),
            )
        ],
        created=int(time.time()),
        model=model,
        object="chat.completion",
        usage=MockCompletionUsage(
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


# ============================================================================
# OpenAI Error Mocks
# ============================================================================

class MockOpenAIError(Exception):
    """Mock OpenAI API error."""
    def __init__(
        self,
        message: str = "API Error",
        code: Optional[str] = None,
        param: Optional[str] = None,
        type: str = "api_error"
    ):
        self.message = message
        self.code = code
        self.param = param
        self.type = type
        super().__init__(message)


class MockRateLimitError(MockOpenAIError):
    """Mock OpenAI rate limit error."""
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            message=message,
            code="rate_limit_exceeded",
            type="rate_limit_error"
        )


class MockAuthenticationError(MockOpenAIError):
    """Mock OpenAI authentication error."""
    def __init__(self, message: str = "Invalid API key"):
        super().__init__(
            message=message,
            code="invalid_api_key",
            type="authentication_error"
        )


def create_openai_error(
    error_type: str = "api_error",
    message: Optional[str] = None,
) -> MockOpenAIError:
    """
    Create a mock OpenAI error.

    Args:
        error_type: Type of error (api_error, rate_limit, auth)
        message: Error message (uses type-specific default if not provided)

    Returns:
        Appropriate mock error object
    """
    if error_type == "rate_limit":
        return MockRateLimitError(message or "Rate limit exceeded")
    elif error_type == "auth":
        return MockAuthenticationError(message or "Invalid API key")
    else:
        return MockOpenAIError(message=message or "An error occurred", type=error_type)


# ============================================================================
# Anthropic Mock Types
# ============================================================================

@dataclass
class MockAnthropicUsage:
    """Mock Anthropic Usage object."""
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class MockContentBlock:
    """Mock Anthropic ContentBlock object."""
    type: str = "text"
    text: str = "Mock response"


@dataclass
class MockAnthropicMessage:
    """
    Mock Anthropic Message object.

    Matches the structure of anthropic.types.Message.
    """
    id: str = "msg-mock-12345"
    content: List[MockContentBlock] = field(default_factory=list)
    model: str = "claude-3-haiku-20240307"
    role: str = "assistant"
    stop_reason: str = "end_turn"
    stop_sequence: Optional[str] = None
    type: str = "message"
    usage: MockAnthropicUsage = field(default_factory=MockAnthropicUsage)

    def __post_init__(self):
        if not self.content:
            self.content = [MockContentBlock(text="Mock response")]


def create_anthropic_message(
    content: str = "A person was detected at the entrance.",
    model: str = "claude-3-haiku-20240307",
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
    message_id: Optional[str] = None,
) -> MockAnthropicMessage:
    """
    Create a realistic Anthropic Message mock.

    Args:
        content: The response content
        model: Model name
        stop_reason: Why the response stopped
        input_tokens: Tokens in the prompt
        output_tokens: Tokens in the response
        message_id: Optional custom message ID

    Returns:
        MockAnthropicMessage that matches Anthropic SDK structure
    """
    return MockAnthropicMessage(
        id=message_id or f"msg-{int(time.time())}",
        content=[MockContentBlock(type="text", text=content)],
        model=model,
        role="assistant",
        stop_reason=stop_reason,
        type="message",
        usage=MockAnthropicUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


# ============================================================================
# Google Gemini Mock Types (for completeness)
# ============================================================================

@dataclass
class MockGeminiCandidate:
    """Mock Gemini Candidate object."""
    content: Dict = field(default_factory=dict)
    finish_reason: str = "STOP"
    safety_ratings: List = field(default_factory=list)

    def __post_init__(self):
        if not self.content:
            self.content = {
                "parts": [{"text": "Mock Gemini response"}],
                "role": "model"
            }


@dataclass
class MockGeminiResponse:
    """Mock Google Gemini response object."""
    candidates: List[MockGeminiCandidate] = field(default_factory=list)
    usage_metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.candidates:
            self.candidates = [MockGeminiCandidate()]
        if not self.usage_metadata:
            self.usage_metadata = {
                "prompt_token_count": 100,
                "candidates_token_count": 50,
                "total_token_count": 150,
            }

    @property
    def text(self) -> str:
        """Get text content from first candidate."""
        if self.candidates and self.candidates[0].content:
            parts = self.candidates[0].content.get("parts", [])
            if parts:
                return parts[0].get("text", "")
        return ""


def create_gemini_response(
    content: str = "A person was detected in the camera view.",
    finish_reason: str = "STOP",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> MockGeminiResponse:
    """
    Create a realistic Gemini response mock.

    Args:
        content: The response content
        finish_reason: Why the response stopped
        prompt_tokens: Tokens in the prompt
        completion_tokens: Tokens in the response

    Returns:
        MockGeminiResponse that matches Gemini SDK structure
    """
    return MockGeminiResponse(
        candidates=[
            MockGeminiCandidate(
                content={
                    "parts": [{"text": content}],
                    "role": "model"
                },
                finish_reason=finish_reason,
            )
        ],
        usage_metadata={
            "prompt_token_count": prompt_tokens,
            "candidates_token_count": completion_tokens,
            "total_token_count": prompt_tokens + completion_tokens,
        },
    )
