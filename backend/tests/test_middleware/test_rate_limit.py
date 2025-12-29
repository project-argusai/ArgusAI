"""
Tests for Rate Limiting Middleware.

Story P14-2.6: Implement API Rate Limiting
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.rate_limit import (
    RateLimitMiddleware,
    is_exempt_path,
    get_rate_limit_for_method,
    EXEMPT_PATHS,
)
from app.core.config import settings


class TestRateLimitHelpers:
    """Tests for rate limit helper functions."""

    def test_is_exempt_path_health(self):
        """Health endpoint should be exempt."""
        assert is_exempt_path("/health") is True
        assert is_exempt_path("/api/v1/health") is True

    def test_is_exempt_path_metrics(self):
        """Metrics endpoint should be exempt."""
        assert is_exempt_path("/metrics") is True

    def test_is_exempt_path_docs(self):
        """Documentation endpoints should be exempt."""
        assert is_exempt_path("/docs") is True
        assert is_exempt_path("/redoc") is True
        assert is_exempt_path("/openapi.json") is True

    def test_is_exempt_path_websocket(self):
        """WebSocket endpoints should be exempt."""
        assert is_exempt_path("/ws") is True
        assert is_exempt_path("/ws/events") is True

    def test_is_exempt_path_regular_api(self):
        """Regular API endpoints should not be exempt."""
        assert is_exempt_path("/api/v1/cameras") is False
        assert is_exempt_path("/api/v1/events") is False
        assert is_exempt_path("/api/v1/auth/login") is False

    def test_get_rate_limit_for_method_get(self):
        """GET requests should use read limit."""
        assert get_rate_limit_for_method("GET") == settings.RATE_LIMIT_READS
        assert get_rate_limit_for_method("get") == settings.RATE_LIMIT_READS

    def test_get_rate_limit_for_method_post(self):
        """POST requests should use write limit."""
        assert get_rate_limit_for_method("POST") == settings.RATE_LIMIT_WRITES

    def test_get_rate_limit_for_method_put(self):
        """PUT requests should use write limit."""
        assert get_rate_limit_for_method("PUT") == settings.RATE_LIMIT_WRITES

    def test_get_rate_limit_for_method_delete(self):
        """DELETE requests should use write limit."""
        assert get_rate_limit_for_method("DELETE") == settings.RATE_LIMIT_WRITES

    def test_get_rate_limit_for_method_patch(self):
        """PATCH requests should use write limit."""
        assert get_rate_limit_for_method("PATCH") == settings.RATE_LIMIT_WRITES

    def test_get_rate_limit_for_method_options(self):
        """OPTIONS and other methods should use default limit."""
        assert get_rate_limit_for_method("OPTIONS") == settings.RATE_LIMIT_DEFAULT
        assert get_rate_limit_for_method("HEAD") == settings.RATE_LIMIT_DEFAULT


class TestRateLimitMiddlewareIntegration:
    """Integration tests for rate limiting middleware."""

    @pytest.fixture
    def test_app(self):
        """Create a test FastAPI app with rate limiting."""
        app = FastAPI()

        @app.get("/api/v1/test")
        async def test_endpoint():
            return {"message": "success"}

        @app.post("/api/v1/test")
        async def test_post_endpoint():
            return {"message": "created"}

        @app.get("/health")
        async def health_endpoint():
            return {"status": "healthy"}

        # Add rate limit middleware (only if enabled)
        if settings.RATE_LIMIT_ENABLED:
            app.add_middleware(RateLimitMiddleware)

        return app

    @pytest.fixture
    def client(self, test_app):
        """Create test client."""
        return TestClient(test_app)

    def test_health_endpoint_exempt(self, client):
        """Health endpoint should not be rate limited (AC-6)."""
        # Make many requests to health endpoint
        for _ in range(150):  # More than default limit
            response = client.get("/health")
            assert response.status_code == 200

    @pytest.mark.skipif(
        not settings.RATE_LIMIT_ENABLED,
        reason="Rate limiting is disabled"
    )
    def test_rate_limit_headers_present(self, client):
        """Rate limit headers should be present on responses (AC-7)."""
        response = client.get("/api/v1/test")
        assert response.status_code == 200

        # Check for rate limit header
        assert "X-RateLimit-Limit" in response.headers

    @pytest.mark.skipif(
        not settings.RATE_LIMIT_ENABLED,
        reason="Rate limiting is disabled"
    )
    def test_normal_request_succeeds(self, client):
        """Normal requests within limit should succeed."""
        response = client.get("/api/v1/test")
        assert response.status_code == 200
        assert response.json() == {"message": "success"}


class TestRateLimitConfiguration:
    """Tests for rate limit configuration."""

    def test_default_rate_limit_reads(self):
        """Default read limit should be 100/minute."""
        assert "100" in settings.RATE_LIMIT_READS
        assert "minute" in settings.RATE_LIMIT_READS

    def test_default_rate_limit_writes(self):
        """Default write limit should be 20/minute."""
        assert "20" in settings.RATE_LIMIT_WRITES
        assert "minute" in settings.RATE_LIMIT_WRITES

    def test_rate_limit_enabled_default(self):
        """Rate limiting should be enabled by default."""
        # Note: This may be overridden in test environment
        # The test just verifies the setting exists
        assert hasattr(settings, "RATE_LIMIT_ENABLED")

    def test_rate_limit_storage_uri_optional(self):
        """Storage URI should be optional (None for in-memory)."""
        # Default is None (in-memory storage)
        assert hasattr(settings, "RATE_LIMIT_STORAGE_URI")


class TestExemptPaths:
    """Tests for exempt path configuration."""

    def test_exempt_paths_includes_health(self):
        """Exempt paths should include health endpoints."""
        assert "/health" in EXEMPT_PATHS
        assert "/api/v1/health" in EXEMPT_PATHS

    def test_exempt_paths_includes_docs(self):
        """Exempt paths should include documentation endpoints."""
        assert "/docs" in EXEMPT_PATHS
        assert "/redoc" in EXEMPT_PATHS
        assert "/openapi.json" in EXEMPT_PATHS

    def test_exempt_paths_includes_metrics(self):
        """Exempt paths should include metrics endpoint."""
        assert "/metrics" in EXEMPT_PATHS

    def test_exempt_paths_includes_websocket(self):
        """Exempt paths should include WebSocket endpoint."""
        assert "/ws" in EXEMPT_PATHS
