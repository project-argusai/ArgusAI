"""
Tests for Device Registration API (Story P11-2.4)

Tests device registration, listing, revocation, and token update endpoints.
"""
import os
import tempfile
import uuid
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from main import app
from app.core.database import Base, get_db
from app.models.device import Device
from app.models.user import User


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
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Apply override for all tests in this module
    app.dependency_overrides[get_db] = _override_get_db
    yield
    # Drop tables after all tests in module complete
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)


# Create test client (module-level)
client = TestClient(app)


class TestDeviceAPI:
    """Tests for /api/v1/devices endpoints."""

    def test_register_device_success(self, db_session, auth_headers):
        """Test successful device registration."""
        device_data = {
            "device_id": f"test-device-{uuid.uuid4().hex[:8]}",
            "platform": "ios",
            "name": "iPhone 15 Pro",
            "push_token": "apns-token-abc123",
        }

        response = client.post(
            "/api/v1/devices",
            json=device_data,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["device_id"] == device_data["device_id"]
        assert data["platform"] == "ios"
        assert data["is_new"] is True
        assert "id" in data
        assert "created_at" in data

    def test_register_device_upsert_existing(self, db_session, auth_headers, test_user):
        """Test upsert behavior - updating existing device."""
        device_id = f"existing-device-{uuid.uuid4().hex[:8]}"
        # Create existing device
        device = Device(
            user_id=test_user.id,
            device_id=device_id,
            platform="ios",
            name="Old Name",
        )
        device.set_push_token("old-token")
        db_session.add(device)
        db_session.commit()

        # Update with new data
        device_data = {
            "device_id": device_id,
            "platform": "ios",
            "name": "New Name",
            "push_token": "new-token-xyz",
        }

        response = client.post(
            "/api/v1/devices",
            json=device_data,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["device_id"] == device_id
        assert data["is_new"] is False

        # Verify update in database
        db_session.refresh(device)
        assert device.name == "New Name"
        assert device.get_push_token() == "new-token-xyz"

    def test_register_device_unauthorized(self, db_session):
        """Test device registration without authentication."""
        device_data = {
            "device_id": f"test-device-{uuid.uuid4().hex[:8]}",
            "platform": "ios",
        }

        response = client.post(
            "/api/v1/devices",
            json=device_data,
        )

        assert response.status_code == 401

    def test_register_device_invalid_platform(self, db_session, auth_headers):
        """Test device registration with invalid platform."""
        device_data = {
            "device_id": f"test-device-{uuid.uuid4().hex[:8]}",
            "platform": "blackberry",  # Invalid platform
        }

        response = client.post(
            "/api/v1/devices",
            json=device_data,
            headers=auth_headers,
        )

        assert response.status_code == 422  # Validation error

    def test_list_devices_success(self, db_session, auth_headers, test_user):
        """Test listing user's devices."""
        # Create some devices with unique IDs
        prefix = uuid.uuid4().hex[:8]
        for i in range(3):
            device = Device(
                user_id=test_user.id,
                device_id=f"device-{prefix}-{i}",
                platform="ios" if i % 2 == 0 else "android",
                name=f"Device {i}",
            )
            db_session.add(device)
        db_session.commit()

        response = client.get(
            "/api/v1/devices",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert len(data["devices"]) >= 3
        # Verify push_token is NOT in response
        for device in data["devices"]:
            assert "push_token" not in device

    def test_list_devices_only_own_devices(self, db_session, auth_headers, test_user):
        """Test that listing only returns current user's devices."""
        prefix = uuid.uuid4().hex[:8]
        # Create device for test user
        device1 = Device(
            user_id=test_user.id,
            device_id=f"my-device-{prefix}",
            platform="ios",
        )
        db_session.add(device1)

        # Create another user and device
        other_user = User(
            username=f"other_user_{uuid.uuid4().hex[:8]}",
            password_hash="$2b$12$fakehashfakehashfakehashfakehashfakehashfakehashfake",
        )
        db_session.add(other_user)
        db_session.commit()

        device2 = Device(
            user_id=other_user.id,
            device_id=f"other-device-{prefix}",
            platform="android",
        )
        db_session.add(device2)
        db_session.commit()

        response = client.get(
            "/api/v1/devices",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Verify we only have test_user's devices
        device_ids = [d["device_id"] for d in data["devices"]]
        assert f"my-device-{prefix}" in device_ids
        assert f"other-device-{prefix}" not in device_ids

    def test_revoke_device_success(self, db_session, auth_headers, test_user):
        """Test successful device revocation."""
        device_id = f"to-revoke-{uuid.uuid4().hex[:8]}"
        device = Device(
            user_id=test_user.id,
            device_id=device_id,
            platform="ios",
        )
        db_session.add(device)
        db_session.commit()

        response = client.delete(
            f"/api/v1/devices/{device_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify device deleted
        db_session.expire_all()
        deleted = db_session.query(Device).filter(
            Device.device_id == device_id
        ).first()
        assert deleted is None

    def test_revoke_device_not_found(self, db_session, auth_headers):
        """Test revoking non-existent device."""
        response = client.delete(
            f"/api/v1/devices/nonexistent-{uuid.uuid4().hex[:8]}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_revoke_device_other_user(self, db_session, auth_headers, test_user):
        """Test cannot revoke another user's device."""
        device_id = f"not-mine-{uuid.uuid4().hex[:8]}"
        # Create another user and device
        other_user = User(
            username=f"owner_{uuid.uuid4().hex[:8]}",
            password_hash="$2b$12$fakehashfakehashfakehashfakehashfakehashfakehashfake",
        )
        db_session.add(other_user)
        db_session.commit()

        device = Device(
            user_id=other_user.id,
            device_id=device_id,
            platform="android",
        )
        db_session.add(device)
        db_session.commit()

        response = client.delete(
            f"/api/v1/devices/{device_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404  # Not found (for security, don't reveal exists)

    def test_update_token_success(self, db_session, auth_headers, test_user):
        """Test successful token update."""
        device_id = f"token-update-{uuid.uuid4().hex[:8]}"
        device = Device(
            user_id=test_user.id,
            device_id=device_id,
            platform="ios",
        )
        device.set_push_token("old-token")
        db_session.add(device)
        db_session.commit()

        response = client.put(
            f"/api/v1/devices/{device_id}/token",
            json={"push_token": "new-token-value"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify token updated in database
        db_session.expire_all()
        db_session.refresh(device)
        assert device.get_push_token() == "new-token-value"

    def test_update_token_not_found(self, db_session, auth_headers):
        """Test token update for non-existent device."""
        response = client.put(
            f"/api/v1/devices/nonexistent-{uuid.uuid4().hex[:8]}/token",
            json={"push_token": "new-token"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_update_token_unauthorized(self, db_session):
        """Test token update without authentication."""
        response = client.put(
            f"/api/v1/devices/some-device-{uuid.uuid4().hex[:8]}/token",
            json={"push_token": "new-token"},
        )

        assert response.status_code == 401


# Fixtures
@pytest.fixture
def db_session():
    """Create database session for tests using the module's test database."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_user(db_session):
    """Create test user with unique username."""
    user = User(
        username=f"testuser_{uuid.uuid4().hex[:8]}",
        password_hash="$2b$12$fakehashfakehashfakehashfakehashfakehashfakehashfake",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def auth_headers(test_user):
    """Create auth headers with valid JWT."""
    from app.utils.jwt import create_access_token

    token = create_access_token(test_user.id, test_user.username)
    return {"Authorization": f"Bearer {token}"}
