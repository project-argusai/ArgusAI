"""
Request Logging Middleware (Story 6.2, AC: #2)

Middleware that:
- Generates unique request_id for each request
- Logs request start and end with timing
- Propagates request_id to all logs via contextvars
- Records metrics for Prometheus
"""
import time
import uuid
import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import set_request_id, clear_request_id, get_request_id

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs all HTTP requests with timing and correlation IDs.

    For each request:
    1. Generates a unique UUID as request_id
    2. Sets request_id in context for all downstream logs
    3. Logs request start (method, path)
    4. Logs request end (status code, response time in ms)
    """

    # Paths to exclude from detailed logging (health checks, etc.)
    EXCLUDED_PATHS = {'/health', '/metrics', '/docs', '/redoc', '/openapi.json'}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Set in context for all downstream logs
        token = set_request_id(request_id)

        # Add request_id to request state for access in routes
        request.state.request_id = request_id

        # Start timing
        start_time = time.perf_counter()

        # Get request details
        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"

        # Only log non-excluded paths
        should_log = path not in self.EXCLUDED_PATHS

        if should_log:
            logger.info(
                "Request started",
                extra={
                    "event_type": "request_start",
                    "method": method,
                    "path": path,
                    "client_ip": client_host,
                    "query_params": str(request.query_params) if request.query_params else None,
                }
            )

        try:
            # Process the request
            response = await call_next(request)

            # Calculate response time
            response_time_ms = (time.perf_counter() - start_time) * 1000

            # Add request_id to response headers for debugging
            response.headers["X-Request-ID"] = request_id

            if should_log:
                # Log completion
                log_level = logging.INFO if response.status_code < 400 else logging.WARNING
                if response.status_code >= 500:
                    log_level = logging.ERROR

                logger.log(
                    log_level,
                    "Request completed",
                    extra={
                        "event_type": "request_complete",
                        "method": method,
                        "path": path,
                        "status_code": response.status_code,
                        "response_time_ms": round(response_time_ms, 2),
                        "client_ip": client_host,
                    }
                )

            # Record metrics if available
            try:
                from app.core.metrics import record_request_metrics
                record_request_metrics(
                    method=method,
                    path=path,
                    status_code=response.status_code,
                    response_time_seconds=response_time_ms / 1000
                )
            except ImportError:
                pass  # Metrics not yet set up

            return response

        except Exception as e:
            # Calculate response time for error case
            response_time_ms = (time.perf_counter() - start_time) * 1000

            logger.error(
                "Request failed with exception",
                extra={
                    "event_type": "request_error",
                    "method": method,
                    "path": path,
                    "response_time_ms": round(response_time_ms, 2),
                    "client_ip": client_host,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True
            )

            # Record error metrics
            try:
                from app.core.metrics import record_request_metrics
                record_request_metrics(
                    method=method,
                    path=path,
                    status_code=500,
                    response_time_seconds=response_time_ms / 1000
                )
            except ImportError:
                pass

            raise

        finally:
            # Clear request ID context
            clear_request_id(token)


def get_current_request_id() -> str:
    """
    Get the current request ID from context.

    Returns:
        Current request ID or "no-request" if not in request context
    """
    return get_request_id() or "no-request"
