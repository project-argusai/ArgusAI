"""
HTTP Response Mock Factories (Story P14-8.3)

Factory functions for creating realistic HTTP response objects
that match httpx.Response and similar structures.
"""
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import json


@dataclass
class MockHeaders:
    """Mock HTTP headers object with dict-like access."""
    _headers: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        # Ensure default headers
        defaults = {
            "content-type": "application/json",
            "x-request-id": "mock-request-id-12345",
        }
        for key, value in defaults.items():
            if key not in self._headers:
                self._headers[key] = value

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._headers.get(key.lower(), default)

    def __getitem__(self, key: str) -> str:
        return self._headers[key.lower()]

    def __contains__(self, key: str) -> bool:
        return key.lower() in self._headers

    def items(self):
        return self._headers.items()


@dataclass
class MockRequest:
    """Mock HTTP request object."""
    method: str = "POST"
    url: str = "https://api.example.com/endpoint"
    headers: MockHeaders = field(default_factory=MockHeaders)


@dataclass
class MockHTTPResponse:
    """
    Mock HTTP response object.

    Designed to match httpx.Response structure for use in tests.
    """
    status_code: int = 200
    headers: MockHeaders = field(default_factory=MockHeaders)
    _content: bytes = b""
    _json_data: Optional[Dict] = None
    request: MockRequest = field(default_factory=MockRequest)
    is_success: bool = True
    is_error: bool = False
    reason_phrase: str = "OK"

    def __post_init__(self):
        self.is_success = 200 <= self.status_code < 300
        self.is_error = self.status_code >= 400

        if self.status_code >= 400:
            self.reason_phrase = "Error"
        elif self.status_code == 201:
            self.reason_phrase = "Created"
        elif self.status_code == 204:
            self.reason_phrase = "No Content"

    @property
    def content(self) -> bytes:
        """Return response content as bytes."""
        if self._json_data is not None:
            return json.dumps(self._json_data).encode()
        return self._content

    @property
    def text(self) -> str:
        """Return response content as text."""
        return self.content.decode("utf-8")

    def json(self) -> Dict:
        """Parse response content as JSON."""
        if self._json_data is not None:
            return self._json_data
        return json.loads(self.content)

    def raise_for_status(self):
        """Raise exception if status indicates error."""
        if self.is_error:
            raise MockHTTPStatusError(
                message=f"HTTP {self.status_code}: {self.reason_phrase}",
                response=self
            )


class MockHTTPStatusError(Exception):
    """Mock HTTP status error for failed requests."""
    def __init__(self, message: str, response: MockHTTPResponse):
        self.response = response
        self.request = response.request
        super().__init__(message)


def create_http_response(
    status_code: int = 200,
    json_data: Optional[Dict] = None,
    content: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    request_url: str = "https://api.example.com/endpoint",
    request_method: str = "POST",
) -> MockHTTPResponse:
    """
    Create a mock HTTP response.

    Args:
        status_code: HTTP status code
        json_data: JSON response data (will be serialized)
        content: Raw response content (mutually exclusive with json_data)
        headers: Response headers
        request_url: URL of the original request
        request_method: HTTP method of the original request

    Returns:
        MockHTTPResponse matching httpx.Response structure
    """
    return MockHTTPResponse(
        status_code=status_code,
        headers=MockHeaders(_headers=headers or {}),
        _content=content or b"",
        _json_data=json_data,
        request=MockRequest(
            method=request_method,
            url=request_url,
        ),
    )


def create_json_response(
    data: Dict[str, Any],
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None,
) -> MockHTTPResponse:
    """
    Create a mock JSON response.

    Convenience wrapper for create_http_response with JSON data.

    Args:
        data: Response data to serialize as JSON
        status_code: HTTP status code
        headers: Additional headers

    Returns:
        MockHTTPResponse with JSON content
    """
    default_headers = {"content-type": "application/json"}
    if headers:
        default_headers.update(headers)

    return create_http_response(
        status_code=status_code,
        json_data=data,
        headers=default_headers,
    )


def create_error_response(
    status_code: int = 500,
    error_message: str = "Internal Server Error",
    error_code: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> MockHTTPResponse:
    """
    Create a mock error response.

    Args:
        status_code: HTTP error status code
        error_message: Error message
        error_code: Optional error code
        headers: Additional headers

    Returns:
        MockHTTPResponse with error content
    """
    error_data = {
        "error": error_message,
    }
    if error_code:
        error_data["code"] = error_code

    return create_http_response(
        status_code=status_code,
        json_data=error_data,
        headers=headers,
    )


# ============================================================================
# Webhook-Specific Response Factories
# ============================================================================

def create_webhook_success_response(
    webhook_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> MockHTTPResponse:
    """
    Create a successful webhook delivery response.

    Args:
        webhook_id: Optional webhook delivery ID
        timestamp: Optional delivery timestamp

    Returns:
        MockHTTPResponse indicating successful delivery
    """
    return create_json_response(
        data={
            "status": "received",
            "webhook_id": webhook_id or "wh-12345",
            "timestamp": timestamp or "2025-01-01T00:00:00Z",
        },
        status_code=200,
    )


def create_webhook_retry_response(
    retry_after: int = 60,
) -> MockHTTPResponse:
    """
    Create a webhook response indicating retry is needed.

    Args:
        retry_after: Seconds to wait before retry

    Returns:
        MockHTTPResponse with 429 status
    """
    return create_http_response(
        status_code=429,
        json_data={"error": "Rate limit exceeded"},
        headers={"retry-after": str(retry_after)},
    )


# ============================================================================
# Push Notification Response Factories
# ============================================================================

def create_apns_success_response(
    apns_id: str = "mock-apns-id-12345",
) -> MockHTTPResponse:
    """
    Create a successful APNS response.

    Args:
        apns_id: APNS delivery ID

    Returns:
        MockHTTPResponse for successful APNS delivery
    """
    return create_http_response(
        status_code=200,
        content=b"",  # APNS returns empty body on success
        headers={"apns-id": apns_id},
    )


def create_apns_error_response(
    reason: str = "BadDeviceToken",
    status_code: int = 400,
) -> MockHTTPResponse:
    """
    Create an APNS error response.

    Args:
        reason: APNS error reason
        status_code: HTTP status code

    Returns:
        MockHTTPResponse for APNS error
    """
    return create_json_response(
        data={"reason": reason},
        status_code=status_code,
    )


def create_fcm_success_response(
    message_id: str = "projects/mock/messages/12345",
) -> MockHTTPResponse:
    """
    Create a successful FCM response.

    Args:
        message_id: FCM message ID

    Returns:
        MockHTTPResponse for successful FCM delivery
    """
    return create_json_response(
        data={"name": message_id},
        status_code=200,
    )


def create_fcm_error_response(
    error_code: str = "INVALID_ARGUMENT",
    error_message: str = "Invalid registration token",
    status_code: int = 400,
) -> MockHTTPResponse:
    """
    Create an FCM error response.

    Args:
        error_code: FCM error code
        error_message: Error message
        status_code: HTTP status code

    Returns:
        MockHTTPResponse for FCM error
    """
    return create_json_response(
        data={
            "error": {
                "code": status_code,
                "message": error_message,
                "status": error_code,
            }
        },
        status_code=status_code,
    )
