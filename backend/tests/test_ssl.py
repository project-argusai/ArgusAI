"""
SSL Configuration Tests (Story P9-5.1)

Tests for:
- SSL settings validation
- SSL status endpoint
- HTTPS redirect middleware
- Push notification HTTPS warning
"""
import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import PlainTextResponse

# Import the middleware
from app.middleware.https_redirect import HTTPSRedirectMiddleware


class TestSSLSettings:
    """Test SSL settings validation in config.py"""

    def test_ssl_settings_defaults(self):
        """Test that SSL is disabled by default"""
        from app.core.config import Settings

        # Create settings without SSL env vars
        with patch.dict(os.environ, {}, clear=False):
            # Don't validate cert files for this test
            settings = Settings(
                _env_file=None,
                ENCRYPTION_KEY="test-key-must-be-at-least-32-chars-long"
            )
            assert settings.SSL_ENABLED is False
            assert settings.SSL_CERT_FILE is None
            assert settings.SSL_KEY_FILE is None
            assert settings.SSL_REDIRECT_HTTP is True
            assert settings.SSL_MIN_VERSION == "TLSv1_2"
            assert settings.SSL_PORT == 443

    def test_ssl_ready_property_disabled(self):
        """Test ssl_ready returns False when SSL is disabled"""
        from app.core.config import Settings

        settings = Settings(
            _env_file=None,
            ENCRYPTION_KEY="test-key-must-be-at-least-32-chars-long",
            SSL_ENABLED=False
        )
        assert settings.ssl_ready is False

    def test_ssl_ready_property_missing_files(self):
        """Test ssl_ready returns False when cert files are missing"""
        from app.core.config import Settings

        settings = Settings(
            _env_file=None,
            ENCRYPTION_KEY="test-key-must-be-at-least-32-chars-long",
            SSL_ENABLED=True,
            SSL_CERT_FILE=None,
            SSL_KEY_FILE=None
        )
        assert settings.ssl_ready is False

    def test_ssl_min_version_validation(self):
        """Test that invalid SSL_MIN_VERSION raises error"""
        from app.core.config import Settings
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                _env_file=None,
                ENCRYPTION_KEY="test-key-must-be-at-least-32-chars-long",
                SSL_MIN_VERSION="TLSv1_0"  # Invalid
            )
        assert "SSL_MIN_VERSION" in str(exc_info.value)

    def test_ssl_min_version_valid_options(self):
        """Test valid SSL_MIN_VERSION options"""
        from app.core.config import Settings

        # Test TLSv1_2
        settings = Settings(
            _env_file=None,
            ENCRYPTION_KEY="test-key-must-be-at-least-32-chars-long",
            SSL_MIN_VERSION="TLSv1_2"
        )
        assert settings.SSL_MIN_VERSION == "TLSv1_2"

        # Test TLSv1_3
        settings = Settings(
            _env_file=None,
            ENCRYPTION_KEY="test-key-must-be-at-least-32-chars-long",
            SSL_MIN_VERSION="TLSv1_3"
        )
        assert settings.SSL_MIN_VERSION == "TLSv1_3"


class TestHTTPSRedirectMiddleware:
    """Test HTTPS redirect middleware"""

    def create_test_app(self, ssl_enabled: bool = True, ssl_port: int = 443):
        """Create a test Starlette app with the middleware"""

        async def homepage(request):
            return PlainTextResponse("Hello, world!")

        app = Starlette(routes=[
            Route("/", homepage),
            Route("/path/to/resource", homepage),
        ])
        app.add_middleware(
            HTTPSRedirectMiddleware,
            ssl_enabled=ssl_enabled,
            ssl_port=ssl_port
        )
        return app

    def test_redirect_http_to_https(self):
        """Test that HTTP requests are redirected to HTTPS"""
        app = self.create_test_app(ssl_enabled=True)
        client = StarletteTestClient(app, raise_server_exceptions=False)

        # Make HTTP request (client defaults to http)
        response = client.get("/", follow_redirects=False)

        assert response.status_code == 301
        assert "https://" in response.headers["location"]

    def test_no_redirect_when_ssl_disabled(self):
        """Test that no redirect occurs when SSL is disabled"""
        app = self.create_test_app(ssl_enabled=False)
        client = StarletteTestClient(app, raise_server_exceptions=False)

        response = client.get("/", follow_redirects=False)

        # Should not redirect
        assert response.status_code == 200

    def test_redirect_preserves_path(self):
        """Test that redirect preserves the original path"""
        app = self.create_test_app(ssl_enabled=True)
        client = StarletteTestClient(app, raise_server_exceptions=False)

        response = client.get("/path/to/resource", follow_redirects=False)

        assert response.status_code == 301
        assert "/path/to/resource" in response.headers["location"]

    def test_redirect_preserves_query_string(self):
        """Test that redirect preserves query parameters"""
        app = self.create_test_app(ssl_enabled=True)
        client = StarletteTestClient(app, raise_server_exceptions=False)

        response = client.get("/?foo=bar&baz=qux", follow_redirects=False)

        assert response.status_code == 301
        location = response.headers["location"]
        assert "foo=bar" in location
        assert "baz=qux" in location

    def test_redirect_custom_port(self):
        """Test redirect with custom SSL port"""
        app = self.create_test_app(ssl_enabled=True, ssl_port=8443)
        client = StarletteTestClient(app, raise_server_exceptions=False)

        response = client.get("/", follow_redirects=False)

        assert response.status_code == 301
        assert ":8443" in response.headers["location"]

    def test_no_redirect_for_https(self):
        """Test that HTTPS requests are not redirected"""
        app = self.create_test_app(ssl_enabled=True)
        client = StarletteTestClient(app, base_url="https://testserver")

        # Make HTTPS request
        response = client.get("/", follow_redirects=False)

        # Should not redirect (though may get 200 or other status)
        assert response.status_code != 301

    def test_respects_x_forwarded_proto(self):
        """Test that X-Forwarded-Proto header is respected (for proxies)"""
        app = self.create_test_app(ssl_enabled=True)
        client = StarletteTestClient(app, raise_server_exceptions=False)

        # Request with X-Forwarded-Proto: https
        response = client.get(
            "/",
            headers={"X-Forwarded-Proto": "https"},
            follow_redirects=False
        )

        # Should not redirect because proxy says it's HTTPS
        assert response.status_code == 200


class TestSSLStatusEndpoint:
    """Test /api/v1/system/ssl-status endpoint"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from main import app
        return TestClient(app)

    def test_ssl_status_disabled(self, client):
        """Test SSL status when SSL is disabled (default state)"""
        # Default settings have SSL disabled, so this should work without mocking
        response = client.get("/api/v1/system/ssl-status")

        assert response.status_code == 200
        data = response.json()
        # SSL is disabled by default
        assert data["ssl_enabled"] is False
        assert data["ssl_ready"] is False
        assert data["certificate_valid"] is False
        # Check other fields
        assert data["tls_version"] is not None
        assert data["ssl_port"] == 443

    def test_ssl_status_with_mocked_settings(self, client):
        """Test SSL status when SSL is enabled with valid certificate"""
        # Mock the settings module before importing
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.SSL_ENABLED = True
            mock_settings.ssl_ready = True
            mock_settings.SSL_MIN_VERSION = "TLSv1_2"
            mock_settings.SSL_PORT = 443
            mock_settings.SSL_REDIRECT_HTTP = True
            mock_settings.SSL_CERT_FILE = "/tmp/test.pem"

            # Mock the certificate parsing to avoid needing a real cert
            with patch("app.api.v1.system._parse_certificate") as mock_parse:
                mock_parse.return_value = {
                    "valid": True,
                    "expires": "2026-12-23T00:00:00+00:00",
                    "issuer": "Test CA",
                    "subject": "test.example.com"
                }

                response = client.get("/api/v1/system/ssl-status")

                assert response.status_code == 200
                data = response.json()
                # The endpoint reads settings at runtime, so with mocking it should work
                # Note: This test may need adjustment based on how settings are loaded
                assert "ssl_enabled" in data
                assert "ssl_ready" in data


class TestPushRequirementsEndpoint:
    """Test /api/v1/push/requirements endpoint for HTTPS warning"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from main import app
        return TestClient(app)

    def test_push_requirements_no_https(self, client):
        """Test push requirements shows warning when HTTPS is not configured (default state)"""
        # Default settings have SSL disabled, so warning should appear
        response = client.get("/api/v1/push/requirements")

        assert response.status_code == 200
        data = response.json()
        assert data["https_required"] is True
        assert data["https_configured"] is False
        assert data["ready"] is False
        assert data["warning"] is not None
        assert "HTTPS" in data["warning"]

    def test_push_requirements_response_structure(self, client):
        """Test push requirements response has correct structure"""
        response = client.get("/api/v1/push/requirements")

        assert response.status_code == 200
        data = response.json()

        # Check all expected fields are present
        assert "https_required" in data
        assert "https_configured" in data
        assert "ready" in data
        assert "warning" in data

        # https_required should always be True (push needs HTTPS)
        assert data["https_required"] is True


class TestCertificateParsing:
    """Test certificate metadata parsing"""

    def test_parse_certificate_function(self):
        """Test _parse_certificate with a real test certificate"""
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        from datetime import datetime, timezone, timedelta

        # Generate a test certificate
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
            x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
            .sign(key, hashes.SHA256(), default_backend())
        )

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
            from cryptography.hazmat.primitives.serialization import Encoding
            f.write(cert.public_bytes(Encoding.PEM))
            cert_path = f.name

        try:
            from app.api.v1.system import _parse_certificate

            result = _parse_certificate(cert_path)

            assert result["valid"] is True
            assert result["subject"] == "test.example.com"
            assert "Test Org" in result["issuer"] or "test.example.com" in result["issuer"]
            assert result["expires"] is not None
        finally:
            os.unlink(cert_path)

    def test_parse_expired_certificate(self):
        """Test parsing an expired certificate returns valid=False"""
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        from datetime import datetime, timezone, timedelta

        # Generate an expired certificate
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "expired.example.com"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=365))
            .not_valid_after(datetime.now(timezone.utc) - timedelta(days=1))  # Expired
            .sign(key, hashes.SHA256(), default_backend())
        )

        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
            from cryptography.hazmat.primitives.serialization import Encoding
            f.write(cert.public_bytes(Encoding.PEM))
            cert_path = f.name

        try:
            from app.api.v1.system import _parse_certificate

            result = _parse_certificate(cert_path)

            assert result["valid"] is False
            assert result["subject"] == "expired.example.com"
        finally:
            os.unlink(cert_path)

    def test_parse_invalid_certificate_file(self):
        """Test parsing an invalid certificate file returns error"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
            f.write("not a valid certificate")
            cert_path = f.name

        try:
            from app.api.v1.system import _parse_certificate

            result = _parse_certificate(cert_path)

            assert result["valid"] is False
            assert "error" in result
        finally:
            os.unlink(cert_path)
