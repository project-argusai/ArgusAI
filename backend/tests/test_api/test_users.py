"""User management API tests (Story P15-2.3, P16-1.2)

Tests for admin-only user management endpoints.
"""
import pytest
import tempfile
import os
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.database import Base, get_db
from app.models.user import User, UserRole
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
def cleanup_database():
    """Clean up database between tests"""
    from app.models.session import Session
    db = TestingSessionLocal()
    try:
        db.query(Session).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
    yield


client = TestClient(app)


class TestUserManagementAPI:
    """Test user management endpoints"""

    @pytest.fixture
    def admin_user(self) -> User:
        """Create an admin user for testing"""
        db = TestingSessionLocal()
        try:
            user = User(
                id=str(uuid.uuid4()),
                username="admin_test",
                password_hash=hash_password("AdminPass123!"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            yield user
        finally:
            db.close()

    @pytest.fixture
    def viewer_user(self) -> User:
        """Create a viewer user for testing"""
        db = TestingSessionLocal()
        try:
            user = User(
                id=str(uuid.uuid4()),
                username="viewer_test",
                password_hash=hash_password("ViewerPass123!"),
                role=UserRole.VIEWER,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            yield user
        finally:
            db.close()

    @pytest.fixture
    def admin_token(self, admin_user: User) -> str:
        """Get JWT token for admin user (directly created to bypass rate limit)"""
        return create_access_token(admin_user.id, admin_user.username)

    @pytest.fixture
    def viewer_token(self, viewer_user: User) -> str:
        """Get JWT token for viewer user (directly created to bypass rate limit)"""
        return create_access_token(viewer_user.id, viewer_user.username)

    def test_list_users_admin_only(
        self, admin_token: str, viewer_token: str
    ):
        """Test that only admins can list users"""
        # Admin can list users
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

        # Viewer gets 403
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert response.status_code == 403

    def test_create_user_success(
        self, admin_token: str, admin_user: User
    ):
        """Test creating a new user with invitation tracking (P16-1.2)"""
        response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "role": "viewer",
            }
        )
        assert response.status_code == 201
        data = response.json()

        # Verify basic fields
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "viewer"
        assert data["temporary_password"] is not None
        assert len(data["temporary_password"]) >= 16

        # Story P16-1.2: Verify invitation tracking
        assert data["invited_by"] == admin_user.id
        assert data["invited_at"] is not None

    def test_create_user_duplicate_username(
        self, admin_token: str, viewer_user: User
    ):
        """Test that duplicate usernames are rejected"""
        response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"username": "viewer_test", "role": "viewer"}
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    def test_create_user_non_admin_forbidden(
        self, viewer_token: str
    ):
        """Test that non-admins cannot create users"""
        response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"username": "newuser", "role": "viewer"}
        )
        assert response.status_code == 403

    def test_get_user_details(
        self, admin_token: str, viewer_user: User
    ):
        """Test getting user details includes invitation fields"""
        response = client.get(
            f"/api/v1/users/{viewer_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == viewer_user.id
        assert data["username"] == "viewer_test"
        assert "invited_by" in data
        assert "invited_at" in data

    def test_get_user_not_found(
        self, admin_token: str
    ):
        """Test getting non-existent user returns 404"""
        response = client.get(
            "/api/v1/users/nonexistent-id",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 404

    def test_update_user_role(
        self, admin_token: str, viewer_user: User
    ):
        """Test updating user role"""
        response = client.put(
            f"/api/v1/users/{viewer_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"role": "operator"}
        )
        assert response.status_code == 200
        assert response.json()["role"] == "operator"

    def test_update_user_disable(
        self, admin_token: str, viewer_user: User
    ):
        """Test disabling a user"""
        response = client.put(
            f"/api/v1/users/{viewer_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"is_active": False}
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_delete_user_success(
        self, admin_token: str, viewer_user: User
    ):
        """Test deleting a user"""
        user_id = viewer_user.id
        response = client.delete(
            f"/api/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 204

        # Verify user is deleted
        db = TestingSessionLocal()
        try:
            deleted_user = db.query(User).filter(User.id == user_id).first()
            assert deleted_user is None
        finally:
            db.close()

    def test_delete_self_forbidden(
        self, admin_token: str, admin_user: User
    ):
        """Test that admins cannot delete themselves"""
        response = client.delete(
            f"/api/v1/users/{admin_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400
        assert "own account" in response.json()["detail"].lower()

    def test_reset_password_success(
        self, admin_token: str, viewer_user: User
    ):
        """Test resetting user password"""
        response = client.post(
            f"/api/v1/users/{viewer_user.id}/reset",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "temporary_password" in data
        assert len(data["temporary_password"]) >= 16
        assert "expires_at" in data

    def test_reset_password_not_found(
        self, admin_token: str
    ):
        """Test resetting password for non-existent user"""
        response = client.post(
            "/api/v1/users/nonexistent-id/reset",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 404

    def test_unauthenticated_access_forbidden(self):
        """Test that unauthenticated requests are rejected"""
        fresh_client = TestClient(app)
        response = fresh_client.get("/api/v1/users")
        assert response.status_code == 401
