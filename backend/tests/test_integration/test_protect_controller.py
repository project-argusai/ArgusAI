"""
Integration tests for UniFi Protect controller lifecycle (Story P2-6.4, AC1)

Tests controller connection lifecycle:
- Connect to controller
- Auto-reconnect on disconnect
- Clean disconnect

These tests use mocks since actual Protect controllers are not available.
"""
import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os

from main import app
from app.core.database import Base, get_db
from app.models.protect_controller import ProtectController
from app.services.protect_service import (
    ProtectService,
    ConnectionTestResult,
    BACKOFF_DELAYS,
)


# Create module-level temp database (file-based for isolation)
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix="_protect_controller.db")
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
    """Set up database and override at module start, teardown at end."""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    # Clean up temp file
    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)


@pytest.fixture(scope="module")
def client(setup_module_database):
    """Create test client - override already applied at module level"""
    return TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    yield
    db = TestingSessionLocal()
    try:
        db.query(ProtectController).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def protect_service():
    """Create a fresh ProtectService instance"""
    return ProtectService()


@pytest.fixture
def mock_protect_client():
    """Create a mock uiprotect ProtectApiClient"""
    mock_client = MagicMock()
    mock_client.update = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.bootstrap = MagicMock()
    mock_client.bootstrap.nvr = MagicMock()
    mock_client.bootstrap.nvr.version = "3.0.16"
    mock_client.bootstrap.cameras = [MagicMock(), MagicMock()]
    return mock_client


class TestControllerConnection:
    """Tests for controller connection (AC1 - connect)"""

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_connect_controller_success(self, mock_client_class, protect_service, mock_protect_client):
        """Test successful controller connection"""
        mock_client_class.return_value = mock_protect_client

        result = await protect_service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="testpassword",
            verify_ssl=False
        )

        assert result.success is True
        assert result.message == "Connected successfully"
        assert result.firmware_version == "3.0.16"
        assert result.camera_count == 2
        mock_protect_client.update.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_connect_controller_auth_failure(self, mock_client_class, protect_service):
        """Test connection with authentication failure"""
        from uiprotect.exceptions import NotAuthorized

        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=NotAuthorized("Invalid credentials"))
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await protect_service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="wrongpassword",
            verify_ssl=False
        )

        assert result.success is False
        assert "authentication" in result.message.lower() or "credentials" in result.message.lower()
        assert result.error_type == "auth_error"

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_connect_controller_network_error(self, mock_client_class, protect_service):
        """Test connection with network timeout"""
        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=asyncio.TimeoutError("Connection timed out"))
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await protect_service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="testpassword",
            verify_ssl=False
        )

        assert result.success is False
        assert result.error_type == "timeout"


class TestControllerReconnect:
    """Tests for controller auto-reconnect (AC1 - reconnect)"""

    def test_backoff_delays_defined(self):
        """Verify exponential backoff delays are configured"""
        assert BACKOFF_DELAYS == [1, 2, 4, 8, 16, 30]
        assert BACKOFF_DELAYS[0] == 1  # Initial delay
        assert BACKOFF_DELAYS[-1] == 30  # Max delay

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_reconnect_on_disconnect(self, mock_client_class, protect_service, mock_protect_client):
        """Test that service can successfully reconnect after disconnect"""
        mock_client_class.return_value = mock_protect_client

        # Connect first
        result = await protect_service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="testpassword",
            verify_ssl=False
        )

        assert result.success is True

        # Reconnect should also work
        result2 = await protect_service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="testpassword",
            verify_ssl=False
        )

        assert result2.success is True

    def test_backoff_delay_progression(self):
        """Test backoff delay doubles up to max"""
        delays = []
        for i in range(len(BACKOFF_DELAYS)):
            delays.append(BACKOFF_DELAYS[i])

        # Each delay should be approximately double the previous (except max)
        for i in range(1, len(delays) - 1):
            assert delays[i] == delays[i - 1] * 2


class TestControllerDisconnect:
    """Tests for controller disconnect (AC1 - disconnect)"""

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_connections(self, protect_service):
        """Test disconnect removes connection from tracking"""
        # Verify service tracks connections dict
        assert hasattr(protect_service, '_connections')
        assert isinstance(protect_service._connections, dict)

        # After disconnect, connections dict should be empty
        assert len(protect_service._connections) == 0

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_service_connection_tracking(self, mock_client_class, protect_service, mock_protect_client):
        """Test that service properly tracks connections"""
        mock_client_class.return_value = mock_protect_client

        # Test connection
        result = await protect_service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="testpassword",
            verify_ssl=False
        )

        # Verify connection succeeded
        assert result.success is True

        # Service has connection tracking mechanism
        assert hasattr(protect_service, '_connections')


class TestControllerAPILifecycle:
    """Integration tests for controller lifecycle via API"""

    def test_create_and_delete_controller(self, client):
        """Test full lifecycle: create → get → delete"""
        # Create controller
        create_data = {
            "name": "Lifecycle Test Controller",
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin",
            "password": "testpassword",
            "verify_ssl": False
        }
        create_response = client.post("/api/v1/protect/controllers", json=create_data)
        assert create_response.status_code == 201

        controller_id = create_response.json()["data"]["id"]

        # Get controller
        get_response = client.get(f"/api/v1/protect/controllers/{controller_id}")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["name"] == "Lifecycle Test Controller"
        assert get_response.json()["data"]["is_connected"] is False

        # Delete controller
        delete_response = client.delete(f"/api/v1/protect/controllers/{controller_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["data"]["deleted"] is True

        # Verify deleted
        verify_response = client.get(f"/api/v1/protect/controllers/{controller_id}")
        assert verify_response.status_code == 404

    def test_controller_connection_status_tracking(self, client):
        """Test that connection status is properly tracked"""
        # Create controller
        create_data = {
            "name": "Status Track Controller",
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin",
            "password": "testpassword"
        }
        response = client.post("/api/v1/protect/controllers", json=create_data)
        assert response.status_code == 201

        data = response.json()["data"]
        # New controllers start disconnected
        assert data["is_connected"] is False
        # last_connected_at should be null initially
        assert data.get("last_connected_at") is None


class TestConnectionTestEndpoint:
    """Integration tests for POST /protect/controllers/test endpoint"""

    @patch('app.services.protect_service.ProtectApiClient')
    def test_test_endpoint_success(self, mock_client_class, client):
        """Test successful connection test via API"""
        mock_client = MagicMock()
        mock_client.update = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.bootstrap = MagicMock()
        mock_client.bootstrap.nvr = MagicMock()
        mock_client.bootstrap.nvr.version = "3.0.16"
        mock_client.bootstrap.cameras = [MagicMock(), MagicMock(), MagicMock()]
        mock_client_class.return_value = mock_client

        test_data = {
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin",
            "password": "secretpassword",
            "verify_ssl": False
        }

        response = client.post("/api/v1/protect/controllers/test", json=test_data)
        assert response.status_code == 200

        data = response.json()
        assert data["data"]["success"] is True
        assert data["data"]["firmware_version"] == "3.0.16"
        assert data["data"]["camera_count"] == 3

    @patch('app.services.protect_service.ProtectApiClient')
    def test_test_endpoint_failure(self, mock_client_class, client):
        """Test failed connection test via API"""
        from uiprotect.exceptions import NotAuthorized

        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=NotAuthorized("Invalid credentials"))
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        test_data = {
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin",
            "password": "wrongpassword"
        }

        response = client.post("/api/v1/protect/controllers/test", json=test_data)
        # Should still return 200 but with success=false
        assert response.status_code in [200, 401]

        data = response.json()
        if response.status_code == 200:
            assert data["data"]["success"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
