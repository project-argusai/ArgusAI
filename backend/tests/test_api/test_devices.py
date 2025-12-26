"""
Tests for Device Registration API (Story P11-2.4)

Tests device registration, listing, revocation, and token update endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.models.device import Device
from app.models.user import User


class TestDeviceAPI:
    """Tests for /api/v1/devices endpoints."""

    def test_register_device_success(self, client, db_session, auth_headers):
        """Test successful device registration."""
        device_data = {
            "device_id": "test-device-001",
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
        assert data["device_id"] == "test-device-001"
        assert data["platform"] == "ios"
        assert data["is_new"] is True
        assert "id" in data
        assert "created_at" in data

    def test_register_device_upsert_existing(self, client, db_session, auth_headers, test_user):
        """Test upsert behavior - updating existing device."""
        # Create existing device
        device = Device(
            user_id=test_user.id,
            device_id="existing-device-001",
            platform="ios",
            name="Old Name",
        )
        device.set_push_token("old-token")
        db_session.add(device)
        db_session.commit()

        # Update with new data
        device_data = {
            "device_id": "existing-device-001",
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
        assert data["device_id"] == "existing-device-001"
        assert data["is_new"] is False

        # Verify update in database
        db_session.refresh(device)
        assert device.name == "New Name"
        assert device.get_push_token() == "new-token-xyz"

    def test_register_device_unauthorized(self, client, db_session):
        """Test device registration without authentication."""
        device_data = {
            "device_id": "test-device-001",
            "platform": "ios",
        }

        response = client.post(
            "/api/v1/devices",
            json=device_data,
        )

        assert response.status_code == 401

    def test_register_device_invalid_platform(self, client, db_session, auth_headers):
        """Test device registration with invalid platform."""
        device_data = {
            "device_id": "test-device-001",
            "platform": "blackberry",  # Invalid platform
        }

        response = client.post(
            "/api/v1/devices",
            json=device_data,
            headers=auth_headers,
        )

        assert response.status_code == 422  # Validation error

    def test_list_devices_success(self, client, db_session, auth_headers, test_user):
        """Test listing user's devices."""
        # Create some devices
        for i in range(3):
            device = Device(
                user_id=test_user.id,
                device_id=f"device-{i}",
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
        assert data["total"] == 3
        assert len(data["devices"]) == 3
        # Verify push_token is NOT in response
        for device in data["devices"]:
            assert "push_token" not in device

    def test_list_devices_only_own_devices(self, client, db_session, auth_headers, test_user):
        """Test that listing only returns current user's devices."""
        import uuid
        # Create device for test user
        device1 = Device(
            user_id=test_user.id,
            device_id="my-device",
            platform="ios",
        )
        db_session.add(device1)

        # Create another user and device
        other_user = User(
            username=f"other_user_{uuid.uuid4().hex[:8]}",
            password_hash="$2b$12$fakehash",
        )
        db_session.add(other_user)
        db_session.commit()

        device2 = Device(
            user_id=other_user.id,
            device_id="other-device",
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
        assert data["total"] == 1
        assert data["devices"][0]["device_id"] == "my-device"

    def test_revoke_device_success(self, client, db_session, auth_headers, test_user):
        """Test successful device revocation."""
        device = Device(
            user_id=test_user.id,
            device_id="to-revoke",
            platform="ios",
        )
        db_session.add(device)
        db_session.commit()

        response = client.delete(
            "/api/v1/devices/to-revoke",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify device deleted
        deleted = db_session.query(Device).filter(
            Device.device_id == "to-revoke"
        ).first()
        assert deleted is None

    def test_revoke_device_not_found(self, client, db_session, auth_headers):
        """Test revoking non-existent device."""
        response = client.delete(
            "/api/v1/devices/nonexistent",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_revoke_device_other_user(self, client, db_session, auth_headers, test_user):
        """Test cannot revoke another user's device."""
        import uuid
        # Create another user and device
        other_user = User(
            username=f"owner_{uuid.uuid4().hex[:8]}",
            password_hash="$2b$12$fakehash",
        )
        db_session.add(other_user)
        db_session.commit()

        device = Device(
            user_id=other_user.id,
            device_id="not-mine",
            platform="android",
        )
        db_session.add(device)
        db_session.commit()

        response = client.delete(
            "/api/v1/devices/not-mine",
            headers=auth_headers,
        )

        assert response.status_code == 404  # Not found (for security, don't reveal exists)

    def test_update_token_success(self, client, db_session, auth_headers, test_user):
        """Test successful token update."""
        device = Device(
            user_id=test_user.id,
            device_id="token-update-test",
            platform="ios",
        )
        device.set_push_token("old-token")
        db_session.add(device)
        db_session.commit()

        response = client.put(
            "/api/v1/devices/token-update-test/token",
            json={"push_token": "new-token-value"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify token updated in database
        db_session.refresh(device)
        assert device.get_push_token() == "new-token-value"

    def test_update_token_not_found(self, client, db_session, auth_headers):
        """Test token update for non-existent device."""
        response = client.put(
            "/api/v1/devices/nonexistent/token",
            json={"push_token": "new-token"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_update_token_unauthorized(self, client, db_session):
        """Test token update without authentication."""
        response = client.put(
            "/api/v1/devices/some-device/token",
            json={"push_token": "new-token"},
        )

        assert response.status_code == 401


# Fixtures
@pytest.fixture
def client():
    """Create test client."""
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def db_session():
    """Create database session for tests."""
    from app.core.database import SessionLocal, engine, Base

    # Create tables
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_user(db_session):
    """Create test user with unique username."""
    import uuid
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

    token = create_access_token({"user_id": test_user.id, "username": test_user.username})
    return {"Authorization": f"Bearer {token}"}
