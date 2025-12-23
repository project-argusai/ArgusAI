"""
HTTPS Redirect Middleware (Story P9-5.1)

Middleware to redirect HTTP requests to HTTPS when SSL is enabled.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
import logging

logger = logging.getLogger(__name__)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Middleware that redirects HTTP requests to HTTPS.

    Only active when SSL is enabled and SSL_REDIRECT_HTTP is True.
    Returns 301 Permanent Redirect to preserve SEO and caching.
    """

    def __init__(self, app, ssl_enabled: bool = False, ssl_port: int = 443):
        """
        Initialize the HTTPS redirect middleware.

        Args:
            app: The ASGI application
            ssl_enabled: Whether SSL is enabled
            ssl_port: The HTTPS port to redirect to
        """
        super().__init__(app)
        self.ssl_enabled = ssl_enabled
        self.ssl_port = ssl_port

    async def dispatch(self, request: Request, call_next):
        """
        Process the request and redirect to HTTPS if needed.

        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain

        Returns:
            Response object (either redirect or normal response)
        """
        # Only redirect if SSL is enabled
        if not self.ssl_enabled:
            return await call_next(request)

        # Check if request is already HTTPS
        # Check both the scheme and X-Forwarded-Proto header (for reverse proxies)
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        is_secure = request.url.scheme == "https" or forwarded_proto == "https"

        if is_secure:
            return await call_next(request)

        # Build HTTPS URL preserving path and query string
        https_url = self._build_https_url(request)

        logger.debug(
            f"Redirecting HTTP to HTTPS: {request.url} -> {https_url}",
            extra={
                "event_type": "https_redirect",
                "original_url": str(request.url),
                "redirect_url": https_url
            }
        )

        # Return 301 Permanent Redirect
        return RedirectResponse(
            url=https_url,
            status_code=301,
            headers={"Location": https_url}
        )

    def _build_https_url(self, request: Request) -> str:
        """
        Build the HTTPS URL from the original request.

        Args:
            request: The incoming HTTP request

        Returns:
            The HTTPS URL string
        """
        # Get the host (without port)
        host = request.url.hostname or request.headers.get("host", "localhost")

        # If host includes a port, strip it
        if ":" in host:
            host = host.split(":")[0]

        # Build the new URL
        port_suffix = "" if self.ssl_port == 443 else f":{self.ssl_port}"
        path = request.url.path
        query = request.url.query

        if query:
            return f"https://{host}{port_suffix}{path}?{query}"
        return f"https://{host}{port_suffix}{path}"
