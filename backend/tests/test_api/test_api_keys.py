"""
Integration tests for API Key management endpoints.

Story P14-3.9: Add Missing API Route Tests
Tests for: backend/app/api/v1/api_keys.py

Endpoints tested:
- POST /api/v1/api-keys (create key)
- GET /api/v1/api-keys (list keys)
- GET /api/v1/api-keys/{key_id} (get single key)
- DELETE /api/v1/api-keys/{key_id} (revoke key)
- GET /api/v1/api-keys/{key_id}/usage (get usage stats)
"""
import pytest
import tempfile
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.database import Base, get_db
from app.models.user import User
from app.models.api_key import APIKey
from app.utils.auth import hash_password
from app.api.v1.auth import get_current_user


# Create module-level temp database
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

TEST_DATABASE_URL = f"sqlite:///{_test_db_path}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    """Override database dependency for testing"""
    db = TestingSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Test user for authentication override
_test_user = None


def _override_get_current_user():
    """Override authentication for testing"""
    return _test_user


@pytest.fixture(scope="module", autouse=True)
def setup_module_database():
    """Set up database at module level"""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)


client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    db = TestingSessionLocal()
    try:
        db.query(APIKey).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def authenticated_user():
    """Create a test user and set up authentication override"""
    global _test_user
    db = TestingSessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()),
            username="testuser",
            password_hash=hash_password("TestPass123!"),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _test_user = user

        # Apply auth override
        app.dependency_overrides[get_current_user] = _override_get_current_user

        yield user
    finally:
        db.close()
        if get_current_user in app.dependency_overrides:
            del app.dependency_overrides[get_current_user]
        _test_user = None


@pytest.fixture
def sample_api_key(authenticated_user):
    """Create a sample API key for testing"""
    db = TestingSessionLocal()
    try:
        import bcrypt
        key_id = str(uuid.uuid4())
        # Create a bcrypt hash of a fake key
        fake_key = "argus_12345678abcdefgh"
        key_hash = bcrypt.hashpw(fake_key.encode(), bcrypt.gensalt()).decode()

        api_key = APIKey(
            id=key_id,
            name="Test API Key",
            prefix="12345678",
            key_hash=key_hash,
            scopes=["read:events", "read:cameras"],
            created_by=authenticated_user.id,
            is_active=True,
            usage_count=5,
            rate_limit_per_minute=60,
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        yield api_key
    finally:
        db.close()


class TestCreateAPIKey:
    """Test POST /api/v1/api-keys endpoint"""

    def test_create_api_key_success(self, authenticated_user):
        """Successfully create an API key with valid scopes"""
        response = client.post(
            "/api/v1/api-keys",
            json={
                "name": "My Test Key",
                "scopes": ["read:events", "read:cameras"],
                "rate_limit_per_minute": 100,
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Test Key"
        assert "key" in data  # Full key only returned once
        assert data["key"].startswith("argus_")
        assert "prefix" in data
        assert set(data["scopes"]) == {"read:events", "read:cameras"}
        assert data["rate_limit_per_minute"] == 100

    def test_create_api_key_with_expiration(self, authenticated_user):
        """Create API key with expiration date"""
        expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        response = client.post(
            "/api/v1/api-keys",
            json={
                "name": "Expiring Key",
                "scopes": ["read:events"],
                "expires_at": expires_at,
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expires_at"] is not None

    def test_create_api_key_admin_scope(self, authenticated_user):
        """Create API key with admin scope"""
        response = client.post(
            "/api/v1/api-keys",
            json={
                "name": "Admin Key",
                "scopes": ["admin"],
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert "admin" in data["scopes"]

    def test_create_api_key_invalid_scope(self, authenticated_user):
        """Returns 400 for invalid scope"""
        response = client.post(
            "/api/v1/api-keys",
            json={
                "name": "Invalid Key",
                "scopes": ["invalid:scope"],
            }
        )

        assert response.status_code == 400
        assert "Invalid scopes" in response.json()["detail"]

    def test_create_api_key_empty_scopes(self, authenticated_user):
        """Returns 400 when no scopes provided"""
        response = client.post(
            "/api/v1/api-keys",
            json={
                "name": "No Scopes Key",
                "scopes": [],
            }
        )

        assert response.status_code == 400
        assert "At least one scope" in response.json()["detail"]

    def test_create_api_key_unauthenticated(self):
        """Returns 401 when not authenticated"""
        # Remove auth override temporarily
        if get_current_user in app.dependency_overrides:
            del app.dependency_overrides[get_current_user]

        response = client.post(
            "/api/v1/api-keys",
            json={
                "name": "Unauth Key",
                "scopes": ["read:events"],
            }
        )

        assert response.status_code == 401


class TestListAPIKeys:
    """Test GET /api/v1/api-keys endpoint"""

    def test_list_api_keys_empty(self, authenticated_user):
        """Returns empty list when no keys exist"""
        response = client.get("/api/v1/api-keys")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_list_api_keys_with_keys(self, authenticated_user, sample_api_key):
        """Returns list of API keys"""
        response = client.get("/api/v1/api-keys")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test API Key"
        assert "key" not in data[0]  # Full key never exposed in list
        assert "prefix" in data[0]

    def test_list_api_keys_exclude_revoked(self, authenticated_user, sample_api_key):
        """By default excludes revoked keys"""
        # Revoke the key
        db = TestingSessionLocal()
        try:
            key = db.query(APIKey).filter(APIKey.id == sample_api_key.id).first()
            key.is_active = False
            key.revoked_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/api-keys")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_api_keys_include_revoked(self, authenticated_user, sample_api_key):
        """Can include revoked keys with query param"""
        # Revoke the key
        db = TestingSessionLocal()
        try:
            key = db.query(APIKey).filter(APIKey.id == sample_api_key.id).first()
            key.is_active = False
            key.revoked_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/api-keys?include_revoked=true")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["is_active"] is False


class TestGetAPIKey:
    """Test GET /api/v1/api-keys/{key_id} endpoint"""

    def test_get_api_key_success(self, authenticated_user, sample_api_key):
        """Successfully get a single API key"""
        response = client.get(f"/api/v1/api-keys/{sample_api_key.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_api_key.id
        assert data["name"] == "Test API Key"
        assert "key" not in data  # Never expose full key

    def test_get_api_key_not_found(self, authenticated_user):
        """Returns 404 for non-existent key"""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/api-keys/{fake_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == "API key not found"


class TestRevokeAPIKey:
    """Test DELETE /api/v1/api-keys/{key_id} endpoint"""

    def test_revoke_api_key_success(self, authenticated_user, sample_api_key):
        """Successfully revoke an API key"""
        response = client.delete(f"/api/v1/api-keys/{sample_api_key.id}")

        assert response.status_code == 200
        assert "revoked" in response.json()["message"].lower()

        # Verify key is revoked
        db = TestingSessionLocal()
        try:
            key = db.query(APIKey).filter(APIKey.id == sample_api_key.id).first()
            assert key.is_active is False
            assert key.revoked_at is not None
        finally:
            db.close()

    def test_revoke_api_key_not_found(self, authenticated_user):
        """Returns 404 for non-existent key"""
        fake_id = str(uuid.uuid4())
        response = client.delete(f"/api/v1/api-keys/{fake_id}")

        assert response.status_code == 404

    def test_revoke_api_key_already_revoked(self, authenticated_user, sample_api_key):
        """Can revoke an already revoked key (idempotent)"""
        # First revoke
        client.delete(f"/api/v1/api-keys/{sample_api_key.id}")

        # Try to revoke again - should still work or return 404
        response = client.delete(f"/api/v1/api-keys/{sample_api_key.id}")
        assert response.status_code in [200, 404]


class TestGetAPIKeyUsage:
    """Test GET /api/v1/api-keys/{key_id}/usage endpoint"""

    def test_get_api_key_usage_success(self, authenticated_user, sample_api_key):
        """Successfully get API key usage stats"""
        response = client.get(f"/api/v1/api-keys/{sample_api_key.id}/usage")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_api_key.id
        assert data["usage_count"] == 5  # Set in fixture
        assert data["rate_limit_per_minute"] == 60

    def test_get_api_key_usage_not_found(self, authenticated_user):
        """Returns 404 for non-existent key"""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/api-keys/{fake_id}/usage")

        assert response.status_code == 404


class TestAPIKeyScopes:
    """Test API key scope validation"""

    @pytest.mark.parametrize("scopes,expected_status", [
        (["read:events"], 201),
        (["read:cameras"], 201),
        (["write:cameras"], 201),
        (["admin"], 201),
        (["read:events", "read:cameras"], 201),
        (["read:events", "write:cameras", "admin"], 201),
    ])
    def test_valid_scopes(self, authenticated_user, scopes, expected_status):
        """Test creation with various valid scope combinations"""
        response = client.post(
            "/api/v1/api-keys",
            json={
                "name": f"Key with {scopes}",
                "scopes": scopes,
            }
        )
        assert response.status_code == expected_status

    @pytest.mark.parametrize("scopes", [
        ["delete:events"],
        ["super:admin"],
        ["read:users"],
        ["write:events"],
    ])
    def test_invalid_scopes(self, authenticated_user, scopes):
        """Test creation with invalid scopes fails"""
        response = client.post(
            "/api/v1/api-keys",
            json={
                "name": f"Key with {scopes}",
                "scopes": scopes,
            }
        )
        assert response.status_code == 400
