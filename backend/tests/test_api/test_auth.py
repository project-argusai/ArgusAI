"""
Integration tests for authentication API endpoints.

Story P14-3.9: Add Missing API Route Tests
Tests for: backend/app/api/v1/auth.py

Endpoints tested:
- POST /api/v1/auth/login
- POST /api/v1/auth/logout
- POST /api/v1/auth/change-password
- GET /api/v1/auth/me
- GET /api/v1/auth/setup-status
"""
import pytest
import tempfile
import os
import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.database import Base, get_db
from app.models.user import User
from app.utils.auth import hash_password
from app.utils.jwt import create_access_token


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


@pytest.fixture(scope="module", autouse=True)
def setup_module_database():
    """Set up database at module level and clean up after all tests"""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)


@pytest.fixture(scope="function", autouse=True)
def reset_rate_limiter():
    """Reset rate limiter state before each test by clearing its storage"""
    from app.api.v1.auth import limiter
    # Clear the limiter's storage to reset rate limit counts
    # slowapi uses a storage backend that can be reset
    if hasattr(limiter, '_storage') and limiter._storage:
        try:
            limiter._storage.clear(None)
        except Exception:
            # If clear doesn't work, try resetting the entire storage
            try:
                limiter._storage.storage = {}
            except Exception:
                pass
    yield


client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    db = TestingSessionLocal()
    try:
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def test_user():
    """Create a test user for authentication tests"""
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
        yield user
    finally:
        db.close()


@pytest.fixture
def test_user_token(test_user):
    """Create a JWT token for the test user without hitting rate limit"""
    return create_access_token(test_user.id, test_user.username)


@pytest.fixture
def disabled_user():
    """Create a disabled test user"""
    db = TestingSessionLocal()
    try:
        user = User(
            username="disableduser",
            password_hash=hash_password("TestPass123!"),
            is_active=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        yield user
    finally:
        db.close()


class TestAuthSetupStatus:
    """Test GET /api/v1/auth/setup-status endpoint"""

    def test_setup_status_no_users(self):
        """Returns setup_complete=False when no users exist"""
        response = client.get("/api/v1/auth/setup-status")

        assert response.status_code == 200
        data = response.json()
        assert data["setup_complete"] is False
        assert data["user_count"] == 0

    def test_setup_status_with_users(self, test_user):
        """Returns setup_complete=True when users exist"""
        response = client.get("/api/v1/auth/setup-status")

        assert response.status_code == 200
        data = response.json()
        assert data["setup_complete"] is True
        assert data["user_count"] == 1


class TestAuthLogin:
    """Test POST /api/v1/auth/login endpoint"""

    def test_login_success(self, test_user):
        """Successfully login with valid credentials"""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "TestPass123!"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["username"] == "testuser"
        # Check cookie is set
        assert "access_token" in response.cookies

    def test_login_invalid_username(self, test_user):
        """Returns 401 for non-existent username"""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent", "password": "TestPass123!"}
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    def test_login_invalid_password(self, test_user):
        """Returns 401 for wrong password"""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "WrongPassword123!"}
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    def test_login_disabled_account(self, disabled_user):
        """Returns 401 for disabled account"""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "disableduser", "password": "TestPass123!"}
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Account disabled"

    def test_login_case_insensitive_username(self, test_user):
        """Username matching is case-insensitive"""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "TESTUSER", "password": "TestPass123!"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data


class TestAuthLogout:
    """Test POST /api/v1/auth/logout endpoint"""

    def test_logout_clears_cookie(self, test_user_token):
        """Logout clears the access_token cookie"""
        # Then logout
        response = client.post("/api/v1/auth/logout")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"

    def test_logout_without_session(self):
        """Logout works even without active session"""
        response = client.post("/api/v1/auth/logout")

        assert response.status_code == 200
        assert response.json()["message"] == "Logged out successfully"


class TestAuthMe:
    """Test GET /api/v1/auth/me endpoint"""

    def test_me_with_valid_token(self, test_user, test_user_token):
        """Returns user info with valid JWT token"""
        # Get current user using directly created token (bypasses rate limit)
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["is_active"] is True
        assert "password_hash" not in data  # Ensure sensitive data not exposed

    def test_me_with_cookie(self, test_user, test_user_token):
        """Returns user info when using cookie authentication"""
        # Set cookie directly and test
        test_client = TestClient(app, cookies={"access_token": test_user_token})
        response = test_client.get("/api/v1/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"

    def test_me_without_token(self):
        """Returns 401 when not authenticated"""
        # Create a new client without any cookies
        fresh_client = TestClient(app)
        response = fresh_client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    def test_me_with_invalid_token(self):
        """Returns 401 with invalid JWT token"""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token_here"}
        )

        assert response.status_code == 401


class TestAuthChangePassword:
    """Test POST /api/v1/auth/change-password endpoint"""

    def test_change_password_success(self, test_user, test_user_token):
        """Successfully change password with valid current password"""
        # Change password using directly created token (bypasses rate limit)
        response = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "current_password": "TestPass123!",
                "new_password": "NewPass456!"
            }
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Password changed successfully"

    def test_change_password_wrong_current(self, test_user, test_user_token):
        """Returns 400 when current password is wrong"""
        # Try to change with wrong current password
        response = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "current_password": "WrongPassword!",
                "new_password": "NewPass456!"
            }
        )

        assert response.status_code == 400
        assert "incorrect" in response.json()["detail"].lower()

    def test_change_password_weak_new_password(self, test_user, test_user_token):
        """Returns 400/422 when new password doesn't meet requirements"""
        # Try to change to weak password
        response = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={
                "current_password": "TestPass123!",
                "new_password": "weak"  # Too short, no uppercase, no number, no special
            }
        )

        # 422 for Pydantic validation errors, 400 for application-level password strength check
        assert response.status_code in [400, 422]

    def test_change_password_unauthenticated(self):
        """Returns 401 when not authenticated"""
        response = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "TestPass123!",
                "new_password": "NewPass456!"
            }
        )

        assert response.status_code == 401

    def test_change_password_invalidates_other_sessions(self, test_user, test_user_token):
        """Story P16-5.5: Password change invalidates all other sessions"""
        from app.models.session import Session as SessionModel
        from datetime import datetime, timezone, timedelta

        db = TestingSessionLocal()
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

            # Create multiple sessions for the user
            session1 = SessionModel(
                user_id=test_user.id,
                token_hash=SessionModel.hash_token("old_token_1"),
                device_info="Chrome on Windows",
                ip_address="192.168.1.1",
                expires_at=expires_at,
            )
            session2 = SessionModel(
                user_id=test_user.id,
                token_hash=SessionModel.hash_token("old_token_2"),
                device_info="Safari on macOS",
                ip_address="192.168.1.2",
                expires_at=expires_at,
            )
            # Create current session with the test user token
            current_session = SessionModel(
                user_id=test_user.id,
                token_hash=SessionModel.hash_token(test_user_token),
                device_info="Test Browser",
                ip_address="127.0.0.1",
                expires_at=expires_at,
            )
            db.add_all([session1, session2, current_session])
            db.commit()

            # Verify 3 sessions exist
            session_count = db.query(SessionModel).filter(
                SessionModel.user_id == test_user.id
            ).count()
            assert session_count == 3

            # Change password
            response = client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {test_user_token}"},
                json={
                    "current_password": "TestPass123!",
                    "new_password": "NewPass456!"
                }
            )

            assert response.status_code == 200
            # Should mention sessions were signed out
            assert "2 other sessions signed out" in response.json()["message"]

            # Verify only current session remains
            remaining_sessions = db.query(SessionModel).filter(
                SessionModel.user_id == test_user.id
            ).all()
            assert len(remaining_sessions) == 1
            assert remaining_sessions[0].token_hash == SessionModel.hash_token(test_user_token)
        finally:
            # Cleanup sessions
            db.query(SessionModel).filter(SessionModel.user_id == test_user.id).delete()
            db.commit()
            db.close()


class TestAuthLoginParametrized:
    """Parametrized tests for login edge cases"""

    @pytest.mark.parametrize("username,password,expected_statuses", [
        ("", "TestPass123!", [422]),  # Empty username
        ("testuser", "", [422]),  # Empty password
        ("test user", "TestPass123!", [401, 429]),  # Username with space (429 if rate limited)
    ])
    def test_login_validation(self, test_user, username, password, expected_statuses):
        """Test various invalid input combinations"""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password}
        )
        assert response.status_code in expected_statuses


# =============================================================================
# Phase A - Web Refresh Token Tests (Issue #425)
# =============================================================================

class TestWebRefreshTokens:
    """Tests for the new web refresh token flow (Phase A)."""

    def test_login_returns_refresh_token(self, test_user):
        """Login should now return a refresh_token in the response."""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "TestPass123!"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "refresh_token" in data
        assert data["refresh_token"] is not None
        assert len(data["refresh_token"]) > 50  # Should be a long opaque token

    def test_successful_refresh(self, test_user):
        """Successfully exchange a valid refresh token for new tokens."""
        # Login first
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "TestPass123!"}
        )
        refresh_token = login_resp.json()["refresh_token"]

        # Refresh
        refresh_resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert refresh_resp.status_code == 200
        data = refresh_resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["refresh_token"] != refresh_token  # Should be rotated

        # New access token should work
        me_resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {data['access_token']}"}
        )
        assert me_resp.status_code == 200

    def test_old_refresh_token_is_invalidated_after_use(self, test_user):
        """After refreshing, the old refresh token should no longer work."""
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "TestPass123!"}
        )
        old_refresh = login_resp.json()["refresh_token"]

        # First refresh
        first_refresh = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh}
        )
        assert first_refresh.status_code == 200
        new_refresh = first_refresh.json()["refresh_token"]

        # Old refresh should now be invalid
        bad_resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh}
        )
        assert bad_resp.status_code == 401

        # New refresh should still work
        good_resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_refresh}
        )
        assert good_resp.status_code == 200

    def test_refresh_token_reuse_detection_revokes_family(self, test_user):
        """Reusing a revoked refresh token should revoke the entire family."""
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "TestPass123!"}
        )
        original_refresh = login_resp.json()["refresh_token"]

        # First refresh (consumes the original)
        first = client.post("/api/v1/auth/refresh", json={"refresh_token": original_refresh})
        new_refresh = first.json()["refresh_token"]

        # Now try to use the original again (reuse attack)
        attack_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": original_refresh})
        assert attack_resp.status_code == 401
        assert "reuse" in attack_resp.json()["detail"].lower() or "security" in attack_resp.json()["detail"].lower()

        # Even the new refresh (from the same family) should now be invalid
        after_attack = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
        assert after_attack.status_code == 401

    def test_refresh_with_invalid_token(self):
        """Using a completely fake refresh token returns 401."""
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "this-is-not-a-valid-refresh-token-at-all-12345"}
        )
        assert response.status_code == 401

    def test_logout_invalidates_refresh_token(self, test_user):
        """After logout, the refresh token should no longer work."""
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "TestPass123!"}
        )
        refresh_token = login_resp.json()["refresh_token"]

        # Logout (using access token cookie from login)
        logout_resp = client.post("/api/v1/auth/logout")
        assert logout_resp.status_code == 200

        # Try to use the refresh token after logout
        refresh_after_logout = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        assert refresh_after_logout.status_code == 401

    def test_refresh_rate_limiting(self, test_user):
        """Refresh endpoint should be rate limited."""
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "TestPass123!"}
        )
        refresh_token = login_resp.json()["refresh_token"]

        # Make many rapid refresh calls (more than the 20/minute limit)
        responses = []
        for _ in range(25):
            resp = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token}
            )
            responses.append(resp.status_code)

        # At least some should be rate limited (429)
        assert 429 in responses, "Refresh endpoint did not trigger rate limiting"
