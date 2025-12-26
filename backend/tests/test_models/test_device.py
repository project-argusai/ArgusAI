"""
Tests for Device model (Story P11-2.4)

Tests Device model creation, encryption, and relationships.
"""
import pytest
from datetime import datetime, timezone

from app.models.device import Device
from app.models.user import User


class TestDeviceModel:
    """Tests for Device SQLAlchemy model."""

    def test_create_device(self, db_session, test_user):
        """Test basic device creation."""
        import uuid
        device_id = f"test-device-{uuid.uuid4().hex[:8]}"
        device = Device(
            user_id=test_user.id,
            device_id=device_id,
            platform="ios",
            name="iPhone 15 Pro",
        )
        db_session.add(device)
        db_session.commit()
        db_session.refresh(device)

        assert device.id is not None
        assert device.user_id == test_user.id
        assert device.device_id == device_id
        assert device.platform == "ios"
        assert device.name == "iPhone 15 Pro"
        assert device.created_at is not None
        assert device.last_seen_at is not None

    def test_push_token_encryption(self, db_session, test_user):
        """Test push token is encrypted and can be decrypted."""
        import uuid
        device = Device(
            user_id=test_user.id,
            device_id=f"encryption-test-{uuid.uuid4().hex[:8]}",
            platform="android",
        )

        # Set token (should encrypt)
        original_token = "fcm-token-abc123xyz"
        device.set_push_token(original_token)

        db_session.add(device)
        db_session.commit()

        # Raw token should be encrypted (starts with 'encrypted:')
        assert device.push_token is not None
        assert device.push_token.startswith("encrypted:")
        assert original_token not in device.push_token

        # Decrypted token should match original
        decrypted = device.get_push_token()
        assert decrypted == original_token

    def test_push_token_none_handling(self, db_session, test_user):
        """Test handling of None push token."""
        import uuid
        device = Device(
            user_id=test_user.id,
            device_id=f"no-token-test-{uuid.uuid4().hex[:8]}",
            platform="ios",
        )

        device.set_push_token(None)
        assert device.push_token is None
        assert device.get_push_token() is None

        device.set_push_token("")
        assert device.push_token is None or device.push_token == ""
        assert device.get_push_token() in (None, "")

    def test_update_last_seen(self, db_session, test_user):
        """Test update_last_seen method."""
        import uuid
        device = Device(
            user_id=test_user.id,
            device_id=f"last-seen-test-{uuid.uuid4().hex[:8]}",
            platform="ios",
        )
        db_session.add(device)
        db_session.commit()

        old_last_seen = device.last_seen_at

        # Update last seen
        device.update_last_seen()
        db_session.commit()

        assert device.last_seen_at >= old_last_seen

    def test_user_relationship(self, db_session, test_user):
        """Test Device -> User relationship."""
        import uuid
        device = Device(
            user_id=test_user.id,
            device_id=f"relationship-test-{uuid.uuid4().hex[:8]}",
            platform="android",
        )
        db_session.add(device)
        db_session.commit()
        db_session.refresh(device)

        # Device should have user relationship
        assert device.user is not None
        assert device.user.id == test_user.id
        assert device.user.username == test_user.username

    def test_user_has_devices_relationship(self, db_session, test_user):
        """Test User -> Device relationship."""
        import uuid
        device_id_1 = f"user-devices-test-1-{uuid.uuid4().hex[:8]}"
        device_id_2 = f"user-devices-test-2-{uuid.uuid4().hex[:8]}"
        device1 = Device(
            user_id=test_user.id,
            device_id=device_id_1,
            platform="ios",
        )
        device2 = Device(
            user_id=test_user.id,
            device_id=device_id_2,
            platform="android",
        )
        db_session.add_all([device1, device2])
        db_session.commit()
        db_session.refresh(test_user)

        # User should have devices relationship
        assert len(test_user.devices) >= 2  # May have more from other tests
        device_ids = {d.device_id for d in test_user.devices}
        assert device_id_1 in device_ids
        assert device_id_2 in device_ids

    def test_device_id_unique_constraint(self, db_session, test_user):
        """Test device_id uniqueness constraint."""
        import uuid
        shared_device_id = f"unique-test-{uuid.uuid4().hex[:8]}"
        device1 = Device(
            user_id=test_user.id,
            device_id=shared_device_id,
            platform="ios",
        )
        db_session.add(device1)
        db_session.commit()

        # Create another user
        other_user = User(
            username=f"other_{uuid.uuid4().hex[:8]}",
            password_hash="$2b$12$fakehashfakehashfakehashfakehashfakehashfakehashfake",
        )
        db_session.add(other_user)
        db_session.commit()

        # Try to create device with same device_id (even for different user)
        device2 = Device(
            user_id=other_user.id,
            device_id=shared_device_id,  # Same device_id
            platform="android",
        )
        db_session.add(device2)

        with pytest.raises(Exception):  # Should raise IntegrityError
            db_session.commit()

    def test_to_dict_without_token(self, db_session, test_user):
        """Test to_dict excludes push_token by default."""
        import uuid
        device_id = f"dict-test-{uuid.uuid4().hex[:8]}"
        device = Device(
            user_id=test_user.id,
            device_id=device_id,
            platform="ios",
            name="Test Device",
        )
        device.set_push_token("secret-token")
        db_session.add(device)
        db_session.commit()

        result = device.to_dict()

        assert "push_token" not in result
        assert result["device_id"] == device_id
        assert result["platform"] == "ios"
        assert result["name"] == "Test Device"

    def test_to_dict_with_token(self, db_session, test_user):
        """Test to_dict includes push_token when requested."""
        import uuid
        device = Device(
            user_id=test_user.id,
            device_id=f"dict-token-test-{uuid.uuid4().hex[:8]}",
            platform="ios",
        )
        device.set_push_token("secret-token")
        db_session.add(device)
        db_session.commit()

        result = device.to_dict(include_token=True)

        assert "push_token" in result
        assert result["push_token"] == "secret-token"

    def test_cascade_delete_on_user(self, db_session, test_user):
        """Test devices are deleted when user is deleted."""
        import uuid
        cascade_device_id = f"cascade-test-{uuid.uuid4().hex[:8]}"
        device = Device(
            user_id=test_user.id,
            device_id=cascade_device_id,
            platform="ios",
        )
        db_session.add(device)
        db_session.commit()

        # Delete user
        db_session.delete(test_user)
        db_session.commit()

        # Device should be gone
        remaining = db_session.query(Device).filter(
            Device.device_id == cascade_device_id
        ).first()
        assert remaining is None


# Fixtures
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
        username=f"devicetestuser_{uuid.uuid4().hex[:8]}",
        password_hash="$2b$12$fakehashfakehashfakehashfakehashfakehashfakehashfake",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user
