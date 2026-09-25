"""Role-based authorization tests (Story P16-1.3)

Tests for role-based permission middleware and decorators.
"""
import pytest

pytestmark = pytest.mark.real_user_roles
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


class TestRoleBasedAuthorization:
    """Test require_role middleware"""

    @pytest.fixture
    def admin_user(self) -> User:
        """Create an admin user"""
        db = TestingSessionLocal()
        try:
            user = User(
                id=str(uuid.uuid4()),
                username="admin_perm",
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
    def operator_user(self) -> User:
        """Create an operator user"""
        db = TestingSessionLocal()
        try:
            user = User(
                id=str(uuid.uuid4()),
                username="operator_perm",
                password_hash=hash_password("OperatorPass123!"),
                role=UserRole.OPERATOR,
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
        """Create a viewer user"""
        db = TestingSessionLocal()
        try:
            user = User(
                id=str(uuid.uuid4()),
                username="viewer_perm",
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
        """Get JWT token for admin user"""
        return create_access_token(admin_user.id, admin_user.username)

    @pytest.fixture
    def operator_token(self, operator_user: User) -> str:
        """Get JWT token for operator user"""
        return create_access_token(operator_user.id, operator_user.username)

    @pytest.fixture
    def viewer_token(self, viewer_user: User) -> str:
        """Get JWT token for viewer user"""
        return create_access_token(viewer_user.id, viewer_user.username)

    def test_admin_can_access_admin_only_endpoint(self, admin_token: str):
        """Admin can access /api/v1/users (admin-only)"""
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

    def test_operator_cannot_access_admin_only_endpoint(self, operator_token: str):
        """Operator gets 403 on /api/v1/users (admin-only)"""
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert response.status_code == 403
        data = response.json()
        # Story P16-1.3: Verify error_code in response
        assert "error_code" in data["detail"]
        assert data["detail"]["error_code"] == "INSUFFICIENT_PERMISSIONS"

    def test_viewer_cannot_access_admin_only_endpoint(self, viewer_token: str):
        """Viewer gets 403 on /api/v1/users (admin-only)"""
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert response.status_code == 403
        data = response.json()
        # Story P16-1.3: Verify error_code in response
        assert "error_code" in data["detail"]
        assert data["detail"]["error_code"] == "INSUFFICIENT_PERMISSIONS"

    def test_permission_denied_includes_error_code(self, viewer_token: str):
        """403 response includes error_code per P16-1.3 requirement"""
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert response.status_code == 403
        data = response.json()
        # The detail field contains both the message and error_code
        detail = data["detail"]
        assert isinstance(detail, dict)
        assert "detail" in detail
        assert "error_code" in detail
        assert detail["error_code"] == "INSUFFICIENT_PERMISSIONS"
        assert "viewer" in detail["detail"].lower()

    def test_unauthenticated_gets_401_not_403(self):
        """Unauthenticated requests get 401, not 403"""
        fresh_client = TestClient(app)
        response = fresh_client.get("/api/v1/users")
        assert response.status_code == 401

    def test_all_roles_can_view_events(
        self, admin_token: str, operator_token: str, viewer_token: str
    ):
        """All authenticated roles can GET /api/v1/events"""
        for token in [admin_token, operator_token, viewer_token]:
            response = client.get(
                "/api/v1/events",
                headers={"Authorization": f"Bearer {token}"}
            )
            # 200 means access granted (empty list is fine)
            assert response.status_code == 200

    def test_all_roles_can_view_cameras(
        self, admin_token: str, operator_token: str, viewer_token: str
    ):
        """All authenticated roles can GET /api/v1/cameras"""
        for token in [admin_token, operator_token, viewer_token]:
            response = client.get(
                "/api/v1/cameras",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200


class TestPermissionUtilityFunctions:
    """Test role checking utility functions"""

    def test_check_can_manage_users_admin_only(self):
        """Only admin can manage users"""
        from app.core.permissions import check_can_manage_users

        admin = User(role=UserRole.ADMIN)
        operator = User(role=UserRole.OPERATOR)
        viewer = User(role=UserRole.VIEWER)

        assert check_can_manage_users(admin) is True
        assert check_can_manage_users(operator) is False
        assert check_can_manage_users(viewer) is False

    def test_check_can_manage_events_admin_operator(self):
        """Admin and operator can manage events"""
        from app.core.permissions import check_can_manage_events

        admin = User(role=UserRole.ADMIN)
        operator = User(role=UserRole.OPERATOR)
        viewer = User(role=UserRole.VIEWER)

        assert check_can_manage_events(admin) is True
        assert check_can_manage_events(operator) is True
        assert check_can_manage_events(viewer) is False

    def test_check_can_manage_cameras_admin_only(self):
        """Camera configuration is admin-only. Operators may analyze."""
        from app.core.permissions import check_can_analyze_cameras, check_can_manage_cameras

        admin = User(role=UserRole.ADMIN)
        operator = User(role=UserRole.OPERATOR)
        viewer = User(role=UserRole.VIEWER)

        assert check_can_manage_cameras(admin) is True
        assert check_can_manage_cameras(operator) is False
        assert check_can_manage_cameras(viewer) is False
        assert check_can_analyze_cameras(admin) is True
        assert check_can_analyze_cameras(operator) is True
        assert check_can_analyze_cameras(viewer) is False

    def test_check_can_manage_settings_admin_only(self):
        """Only admin can manage system settings"""
        from app.core.permissions import check_can_manage_settings

        admin = User(role=UserRole.ADMIN)
        operator = User(role=UserRole.OPERATOR)
        viewer = User(role=UserRole.VIEWER)

        assert check_can_manage_settings(admin) is True
        assert check_can_manage_settings(operator) is False
        assert check_can_manage_settings(viewer) is False

    def test_check_can_view_all_roles(self):
        """All authenticated users can view data"""
        from app.core.permissions import check_can_view

        admin = User(role=UserRole.ADMIN)
        operator = User(role=UserRole.OPERATOR)
        viewer = User(role=UserRole.VIEWER)

        assert check_can_view(admin) is True
        assert check_can_view(operator) is True
        assert check_can_view(viewer) is True
