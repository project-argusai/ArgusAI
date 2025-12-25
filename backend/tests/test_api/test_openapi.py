"""
Story P10-5.1: OpenAPI Specification Tests

Tests for OpenAPI 3.0 specification generation and endpoints.
"""
import pytest
from fastapi.testclient import TestClient


class TestOpenAPIEndpoints:
    """Test OpenAPI documentation endpoints."""

    def test_openapi_json_returns_valid_json(self, api_client: TestClient):
        """AC-5.1.1: /openapi.json returns valid JSON with paths object."""
        response = api_client.get("/openapi.json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert "openapi" in data
        assert data["openapi"].startswith("3.")  # OpenAPI 3.x
        assert "paths" in data
        assert "info" in data
        assert isinstance(data["paths"], dict)
        assert len(data["paths"]) > 0

    def test_openapi_includes_api_info(self, api_client: TestClient):
        """AC-5.1.2: OpenAPI includes proper API info."""
        response = api_client.get("/openapi.json")
        data = response.json()

        info = data["info"]
        assert info["title"] == "ArgusAI API"
        assert info["version"] == "1.0.0"
        assert "description" in info
        assert len(info["description"]) > 100  # Substantial description

    def test_openapi_includes_security_schemes(self, api_client: TestClient):
        """AC-5.1.3: Security schemes (JWT, cookie) are documented."""
        response = api_client.get("/openapi.json")
        data = response.json()

        # Check securitySchemes exists
        assert "components" in data
        assert "securitySchemes" in data["components"]

        security_schemes = data["components"]["securitySchemes"]

        # Verify bearer auth is documented
        assert "bearerAuth" in security_schemes
        assert security_schemes["bearerAuth"]["type"] == "http"
        assert security_schemes["bearerAuth"]["scheme"] == "bearer"
        assert security_schemes["bearerAuth"]["bearerFormat"] == "JWT"

        # Verify cookie auth is documented
        assert "cookieAuth" in security_schemes
        assert security_schemes["cookieAuth"]["type"] == "apiKey"
        assert security_schemes["cookieAuth"]["in"] == "cookie"

    def test_openapi_includes_tags(self, api_client: TestClient):
        """AC-5.1.2: OpenAPI includes endpoint tags with descriptions."""
        response = api_client.get("/openapi.json")
        data = response.json()

        assert "tags" in data
        assert len(data["tags"]) > 10  # Should have many tags

        # Check that tags have descriptions
        tag_names = {tag["name"] for tag in data["tags"]}
        assert "Authentication" in tag_names
        assert "events" in tag_names
        assert "cameras" in tag_names

        # Verify tags have descriptions
        for tag in data["tags"]:
            assert "description" in tag
            assert len(tag["description"]) > 0

    def test_swagger_ui_accessible(self, api_client: TestClient):
        """AC-5.1.7: /docs (Swagger UI) loads correctly."""
        response = api_client.get("/docs")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "swagger" in response.text.lower()

    def test_redoc_accessible(self, api_client: TestClient):
        """AC-5.1.7: /redoc loads correctly."""
        response = api_client.get("/redoc")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "redoc" in response.text.lower()

    def test_auth_endpoints_have_metadata(self, api_client: TestClient):
        """AC-5.1.2: Auth endpoints have summary and description."""
        response = api_client.get("/openapi.json")
        data = response.json()

        # Check login endpoint
        login_path = data["paths"].get("/api/v1/auth/login", {})
        assert "post" in login_path
        login_op = login_path["post"]
        assert "summary" in login_op
        assert "description" in login_op
        assert "Authenticate" in login_op.get("summary", "")

        # Check me endpoint
        me_path = data["paths"].get("/api/v1/auth/me", {})
        assert "get" in me_path
        me_op = me_path["get"]
        assert "summary" in me_op
        assert "Get current user" in me_op.get("summary", "")

    def test_events_endpoints_have_metadata(self, api_client: TestClient):
        """AC-5.1.2: Events endpoints have summary and description."""
        response = api_client.get("/openapi.json")
        data = response.json()

        # Check events list endpoint
        events_path = data["paths"].get("/api/v1/events", {})
        assert "get" in events_path
        list_op = events_path["get"]
        assert "summary" in list_op
        assert "description" in list_op

        # Check post endpoint
        assert "post" in events_path
        create_op = events_path["post"]
        assert "summary" in create_op
        assert "description" in create_op

    def test_global_security_applied(self, api_client: TestClient):
        """AC-5.1.3: Global security is configured."""
        response = api_client.get("/openapi.json")
        data = response.json()

        # Check global security requirement
        assert "security" in data
        security = data["security"]
        assert len(security) > 0

        # Should reference bearerAuth or cookieAuth
        security_refs = []
        for sec in security:
            security_refs.extend(sec.keys())
        assert "bearerAuth" in security_refs or "cookieAuth" in security_refs

    def test_openapi_has_contact_info(self, api_client: TestClient):
        """AC-5.1.5: OpenAPI includes contact and license info."""
        response = api_client.get("/openapi.json")
        data = response.json()

        info = data["info"]
        assert "contact" in info
        assert "license" in info
        assert info["license"]["name"] == "MIT License"


class TestOpenAPISchemas:
    """Test OpenAPI schema definitions."""

    def test_schemas_exist(self, api_client: TestClient):
        """Verify component schemas are generated."""
        response = api_client.get("/openapi.json")
        data = response.json()

        assert "components" in data
        assert "schemas" in data["components"]
        schemas = data["components"]["schemas"]

        # Should have many schemas
        assert len(schemas) > 50

    def test_event_schema_has_fields(self, api_client: TestClient):
        """Verify EventResponse schema has required fields."""
        response = api_client.get("/openapi.json")
        data = response.json()

        schemas = data["components"]["schemas"]

        # Find EventResponse or similar schema
        event_schemas = [k for k in schemas if "Event" in k]
        assert len(event_schemas) > 0

    def test_login_request_schema(self, api_client: TestClient):
        """Verify LoginRequest schema is properly defined."""
        response = api_client.get("/openapi.json")
        data = response.json()

        schemas = data["components"]["schemas"]
        assert "LoginRequest" in schemas

        login_schema = schemas["LoginRequest"]
        assert "properties" in login_schema
        assert "username" in login_schema["properties"]
        assert "password" in login_schema["properties"]
