"""Integration tests for UniFi Protect controller API endpoints (Story P2-1.1, P2-1.2)"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
import tempfile
import os
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from main import app
from app.core.database import Base, get_db
from app.models.protect_controller import ProtectController
from app.models.camera import Camera
from app.services.protect_service import ProtectService, ConnectionTestResult


# Create test database (file-based to avoid threading issues)
test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(test_db_fd)

TEST_DATABASE_URL = f"sqlite:///{test_db_path}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
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


# Override database dependency
app.dependency_overrides[get_db] = override_get_db

# Create tables once
Base.metadata.create_all(bind=engine)

# Create test client
client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    yield
    # Delete all protect controllers and cameras after each test
    db = TestingSessionLocal()
    try:
        db.query(Camera).delete()
        db.query(ProtectController).delete()
        db.commit()
    finally:
        db.close()


class TestProtectControllerModel:
    """Test suite for ProtectController model"""

    def test_create_controller_with_encrypted_password(self):
        """AC2: Password field is encrypted using existing Fernet encryption before storage"""
        db = TestingSessionLocal()
        try:
            controller = ProtectController(
                name="Test Controller",
                host="192.168.1.1",
                port=443,
                username="admin",
                password="secretpassword",
                verify_ssl=False
            )
            db.add(controller)
            db.commit()
            db.refresh(controller)

            # Password should be encrypted (starts with 'encrypted:')
            assert controller.password.startswith('encrypted:')
            # Should be able to decrypt
            decrypted = controller.get_decrypted_password()
            assert decrypted == "secretpassword"
        finally:
            db.close()

    def test_controller_repr(self):
        """Test controller string representation"""
        controller = ProtectController(
            id="test-id",
            name="Test Controller",
            host="192.168.1.1",
            is_connected=False
        )
        repr_str = repr(controller)
        assert "test-id" in repr_str
        assert "Test Controller" in repr_str
        assert "192.168.1.1" in repr_str


class TestProtectControllerAPI:
    """Test suite for Protect controller CRUD API endpoints"""

    def test_create_controller(self):
        """AC4: POST /api/v1/protect/controllers creates new controller record"""
        controller_data = {
            "name": "Home UDM Pro",
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin",
            "password": "secretpassword",
            "verify_ssl": False
        }

        response = client.post("/api/v1/protect/controllers", json=controller_data)
        assert response.status_code == 201

        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert data["data"]["name"] == "Home UDM Pro"
        assert data["data"]["host"] == "192.168.1.1"
        assert data["data"]["port"] == 443
        assert data["data"]["username"] == "admin"
        # Password should not be in response
        assert "password" not in data["data"]
        assert data["data"]["is_connected"] == False

    def test_create_controller_duplicate_name(self):
        """Test creating controller with duplicate name returns 409"""
        controller_data = {
            "name": "Duplicate Controller",
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin",
            "password": "secret"
        }

        # Create first controller
        response = client.post("/api/v1/protect/controllers", json=controller_data)
        assert response.status_code == 201

        # Try to create another with same name
        response = client.post("/api/v1/protect/controllers", json=controller_data)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_list_controllers(self):
        """AC5: GET /api/v1/protect/controllers returns list of all controllers"""
        # Create some controllers first
        for i in range(3):
            client.post("/api/v1/protect/controllers", json={
                "name": f"Controller {i}",
                "host": f"192.168.1.{i}",
                "username": "admin",
                "password": "secret"
            })

        response = client.get("/api/v1/protect/controllers")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert data["meta"]["count"] == 3
        assert len(data["data"]) == 3

    def test_list_controllers_empty(self):
        """Test listing controllers when none exist"""
        response = client.get("/api/v1/protect/controllers")
        assert response.status_code == 200

        data = response.json()
        assert data["data"] == []
        assert data["meta"]["count"] == 0

    def test_get_controller(self):
        """AC6: GET /api/v1/protect/controllers/{id} returns single controller"""
        # Create a controller
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Get Test Controller",
            "host": "192.168.1.50",
            "username": "admin",
            "password": "secret"
        })
        controller_id = create_response.json()["data"]["id"]

        # Get the controller
        response = client.get(f"/api/v1/protect/controllers/{controller_id}")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert data["data"]["id"] == controller_id
        assert data["data"]["name"] == "Get Test Controller"

    def test_get_controller_not_found(self):
        """Test getting non-existent controller returns 404"""
        response = client.get("/api/v1/protect/controllers/non-existent-id")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_update_controller(self):
        """AC7: PUT /api/v1/protect/controllers/{id} updates controller"""
        # Create a controller
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Update Test Controller",
            "host": "192.168.1.100",
            "username": "admin",
            "password": "secret"
        })
        controller_id = create_response.json()["data"]["id"]

        # Update the controller
        update_data = {
            "name": "Updated Controller Name",
            "host": "192.168.1.200"
        }
        response = client.put(f"/api/v1/protect/controllers/{controller_id}", json=update_data)
        assert response.status_code == 200

        data = response.json()
        assert data["data"]["name"] == "Updated Controller Name"
        assert data["data"]["host"] == "192.168.1.200"

    def test_update_controller_partial(self):
        """Test partial update (only some fields)"""
        # Create a controller
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Partial Update Controller",
            "host": "192.168.1.100",
            "port": 443,
            "username": "admin",
            "password": "secret"
        })
        controller_id = create_response.json()["data"]["id"]

        # Update only the port
        response = client.put(f"/api/v1/protect/controllers/{controller_id}", json={"port": 8443})
        assert response.status_code == 200

        data = response.json()
        assert data["data"]["port"] == 8443
        # Other fields should remain unchanged
        assert data["data"]["name"] == "Partial Update Controller"
        assert data["data"]["host"] == "192.168.1.100"

    def test_update_controller_not_found(self):
        """Test updating non-existent controller returns 404"""
        response = client.put("/api/v1/protect/controllers/non-existent-id", json={"name": "New Name"})
        assert response.status_code == 404

    def test_update_controller_duplicate_name(self):
        """Test updating controller to a duplicate name returns 409"""
        # Create two controllers
        client.post("/api/v1/protect/controllers", json={
            "name": "Controller A",
            "host": "192.168.1.1",
            "username": "admin",
            "password": "secret"
        })
        create_b = client.post("/api/v1/protect/controllers", json={
            "name": "Controller B",
            "host": "192.168.1.2",
            "username": "admin",
            "password": "secret"
        })
        controller_b_id = create_b.json()["data"]["id"]

        # Try to update B to have A's name
        response = client.put(f"/api/v1/protect/controllers/{controller_b_id}", json={"name": "Controller A"})
        assert response.status_code == 409

    def test_delete_controller(self):
        """AC8: DELETE /api/v1/protect/controllers/{id} removes controller"""
        # Create a controller
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Delete Test Controller",
            "host": "192.168.1.100",
            "username": "admin",
            "password": "secret"
        })
        controller_id = create_response.json()["data"]["id"]

        # Delete the controller
        response = client.delete(f"/api/v1/protect/controllers/{controller_id}")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert data["data"]["deleted"] == True

        # Verify it's gone
        get_response = client.get(f"/api/v1/protect/controllers/{controller_id}")
        assert get_response.status_code == 404

    def test_delete_controller_not_found(self):
        """Test deleting non-existent controller returns 404"""
        response = client.delete("/api/v1/protect/controllers/non-existent-id")
        assert response.status_code == 404


class TestResponseFormat:
    """Test suite for API response format consistency"""

    def test_response_format_create(self):
        """AC9: POST response returns { data, meta } format"""
        response = client.post("/api/v1/protect/controllers", json={
            "name": "Format Test",
            "host": "192.168.1.1",
            "username": "admin",
            "password": "secret"
        })
        data = response.json()

        assert "data" in data
        assert "meta" in data
        assert "request_id" in data["meta"]
        assert "timestamp" in data["meta"]

    def test_response_format_list(self):
        """AC9: GET list response returns { data, meta } format with count"""
        response = client.get("/api/v1/protect/controllers")
        data = response.json()

        assert "data" in data
        assert "meta" in data
        assert "request_id" in data["meta"]
        assert "timestamp" in data["meta"]
        assert "count" in data["meta"]

    def test_response_format_get(self):
        """AC9: GET single response returns { data, meta } format"""
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Format Get Test",
            "host": "192.168.1.1",
            "username": "admin",
            "password": "secret"
        })
        controller_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/v1/protect/controllers/{controller_id}")
        data = response.json()

        assert "data" in data
        assert "meta" in data
        assert "request_id" in data["meta"]
        assert "timestamp" in data["meta"]

    def test_response_format_update(self):
        """AC9: PUT response returns { data, meta } format"""
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Format Update Test",
            "host": "192.168.1.1",
            "username": "admin",
            "password": "secret"
        })
        controller_id = create_response.json()["data"]["id"]

        response = client.put(f"/api/v1/protect/controllers/{controller_id}", json={"name": "Updated"})
        data = response.json()

        assert "data" in data
        assert "meta" in data
        assert "request_id" in data["meta"]
        assert "timestamp" in data["meta"]

    def test_response_format_delete(self):
        """AC9: DELETE response returns { data, meta } format"""
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Format Delete Test",
            "host": "192.168.1.1",
            "username": "admin",
            "password": "secret"
        })
        controller_id = create_response.json()["data"]["id"]

        response = client.delete(f"/api/v1/protect/controllers/{controller_id}")
        data = response.json()

        assert "data" in data
        assert "meta" in data
        assert "request_id" in data["meta"]
        assert "timestamp" in data["meta"]


class TestValidation:
    """Test suite for input validation"""

    def test_create_missing_required_fields(self):
        """Test validation errors for missing required fields"""
        # Missing name
        response = client.post("/api/v1/protect/controllers", json={
            "host": "192.168.1.1",
            "username": "admin",
            "password": "secret"
        })
        assert response.status_code == 422

        # Missing host
        response = client.post("/api/v1/protect/controllers", json={
            "name": "Test",
            "username": "admin",
            "password": "secret"
        })
        assert response.status_code == 422

        # Missing username
        response = client.post("/api/v1/protect/controllers", json={
            "name": "Test",
            "host": "192.168.1.1",
            "password": "secret"
        })
        assert response.status_code == 422

        # Missing password
        response = client.post("/api/v1/protect/controllers", json={
            "name": "Test",
            "host": "192.168.1.1",
            "username": "admin"
        })
        assert response.status_code == 422

    def test_create_invalid_port(self):
        """Test validation for invalid port numbers"""
        # Port too low
        response = client.post("/api/v1/protect/controllers", json={
            "name": "Test",
            "host": "192.168.1.1",
            "port": 0,
            "username": "admin",
            "password": "secret"
        })
        assert response.status_code == 422

        # Port too high
        response = client.post("/api/v1/protect/controllers", json={
            "name": "Test",
            "host": "192.168.1.1",
            "port": 70000,
            "username": "admin",
            "password": "secret"
        })
        assert response.status_code == 422


class TestDatabaseSchema:
    """Test suite for database schema verification"""

    def test_protect_controllers_table_exists(self):
        """AC1: Database migration creates protect_controllers table"""
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert 'protect_controllers' in tables

    def test_protect_controllers_columns(self):
        """AC1: protect_controllers table has all required columns"""
        inspector = inspect(engine)
        columns = {col['name'] for col in inspector.get_columns('protect_controllers')}

        required_columns = {
            'id', 'name', 'host', 'port', 'username', 'password',
            'verify_ssl', 'is_connected', 'last_connected_at', 'last_error',
            'created_at', 'updated_at'
        }
        assert required_columns.issubset(columns)

    def test_cameras_phase2_columns(self):
        """AC3: cameras table extended with Phase 2 columns"""
        inspector = inspect(engine)
        columns = {col['name'] for col in inspector.get_columns('cameras')}

        phase2_columns = {
            'source_type', 'protect_controller_id', 'protect_camera_id',
            'protect_camera_type', 'smart_detection_types', 'is_doorbell'
        }
        assert phase2_columns.issubset(columns)

    def test_cameras_indexes(self):
        """AC10: Indexes created on cameras.protect_camera_id and cameras.source_type

        Note: This test verifies the migration script exists with proper indexes.
        The test database uses Base.metadata.create_all() which doesn't run Alembic
        migrations. In production, `alembic upgrade head` creates these indexes.
        """
        # Verify migration file contains index definitions
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__),
            '../../alembic/versions/012_add_protect_controllers_and_camera_extensions.py'
        )
        with open(migration_path, 'r') as f:
            migration_content = f.read()

        assert "idx_cameras_protect_camera_id" in migration_content
        assert "idx_cameras_source_type" in migration_content
        assert "create_index" in migration_content


class TestBackwardsCompatibility:
    """Test that existing RTSP/USB cameras still work after Phase 2 changes"""

    def test_existing_camera_operations(self):
        """Test that RTSP camera can still be created and retrieved"""
        camera_data = {
            "name": "Test RTSP Camera",
            "type": "rtsp",
            "rtsp_url": "rtsp://192.168.1.50:554/stream1",
            "frame_rate": 5,
            "is_enabled": False  # Don't try to connect
        }

        response = client.post("/api/v1/cameras", json=camera_data)
        assert response.status_code == 201

        # Verify default source_type
        db = TestingSessionLocal()
        try:
            camera = db.query(Camera).filter(Camera.name == "Test RTSP Camera").first()
            assert camera is not None
            assert camera.source_type == 'rtsp'
            assert camera.protect_controller_id is None
            assert camera.is_doorbell == False
        finally:
            db.close()


# Story P2-1.2: Connection Test Endpoint Tests

class TestConnectionTestEndpoint:
    """Test suite for POST /protect/controllers/test endpoint (Story P2-1.2)"""

    @patch('app.services.protect_service.ProtectApiClient')
    def test_successful_connection(self, mock_client_class):
        """AC1, AC2: Test successful connection returns firmware_version and camera_count"""
        # Mock the client
        mock_client = MagicMock()
        mock_client.update = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.bootstrap = MagicMock()
        mock_client.bootstrap.nvr = MagicMock()
        mock_client.bootstrap.nvr.version = "3.0.16"
        mock_client.bootstrap.cameras = [MagicMock(), MagicMock(), MagicMock()]  # 3 cameras
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
        assert "data" in data
        assert "meta" in data
        assert data["data"]["success"] == True
        assert data["data"]["message"] == "Connected successfully"
        assert data["data"]["firmware_version"] == "3.0.16"
        assert data["data"]["camera_count"] == 3

    @patch('app.services.protect_service.ProtectApiClient')
    def test_authentication_failure(self, mock_client_class):
        """AC3: Failed authentication returns 401"""
        from uiprotect.exceptions import NotAuthorized

        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=NotAuthorized("Invalid credentials"))
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        test_data = {
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin",
            "password": "wrongpassword",
            "verify_ssl": False
        }

        response = client.post("/api/v1/protect/controllers/test", json=test_data)
        assert response.status_code == 401
        assert "Authentication failed" in response.json()["detail"]

    @patch('app.services.protect_service.ProtectApiClient')
    def test_host_unreachable(self, mock_client_class):
        """AC4: Unreachable host returns 503"""
        import aiohttp

        mock_client = MagicMock()
        mock_client.update = AsyncMock(
            side_effect=aiohttp.ClientConnectorError(
                MagicMock(), OSError("Connection refused")
            )
        )
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        test_data = {
            "host": "192.168.1.254",
            "port": 443,
            "username": "admin",
            "password": "password",
            "verify_ssl": False
        }

        response = client.post("/api/v1/protect/controllers/test", json=test_data)
        assert response.status_code == 503
        assert "Host unreachable" in response.json()["detail"]

    @patch('app.services.protect_service.ProtectApiClient')
    def test_ssl_certificate_error(self, mock_client_class):
        """AC5: SSL verification error returns 502"""
        import aiohttp

        mock_client = MagicMock()
        mock_client.update = AsyncMock(
            side_effect=aiohttp.ClientConnectorCertificateError(
                MagicMock(), Exception("Certificate verify failed")
            )
        )
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        test_data = {
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin",
            "password": "password",
            "verify_ssl": True  # SSL verification enabled
        }

        response = client.post("/api/v1/protect/controllers/test", json=test_data)
        assert response.status_code == 502
        assert "SSL certificate verification failed" in response.json()["detail"]

    @patch('app.services.protect_service.ProtectApiClient')
    def test_connection_timeout(self, mock_client_class):
        """AC6: Connection timeout returns 504"""
        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        test_data = {
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin",
            "password": "password",
            "verify_ssl": False
        }

        response = client.post("/api/v1/protect/controllers/test", json=test_data)
        assert response.status_code == 504
        assert "timed out" in response.json()["detail"]

    def test_response_format(self):
        """AC1, AC2: Response follows { data, meta } format"""
        # Use mock to avoid real connection
        with patch('app.services.protect_service.ProtectApiClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.update = AsyncMock()
            mock_client.close = AsyncMock()
            mock_client.bootstrap = MagicMock()
            mock_client.bootstrap.nvr = MagicMock()
            mock_client.bootstrap.nvr.version = "3.0.16"
            mock_client.bootstrap.cameras = []
            mock_client_class.return_value = mock_client

            test_data = {
                "host": "192.168.1.1",
                "port": 443,
                "username": "admin",
                "password": "password",
                "verify_ssl": False
            }

            response = client.post("/api/v1/protect/controllers/test", json=test_data)
            data = response.json()

            assert "data" in data
            assert "meta" in data
            assert "request_id" in data["meta"]
            assert "timestamp" in data["meta"]
            assert "success" in data["data"]
            assert "message" in data["data"]

    def test_validation_missing_required_fields(self):
        """Test validation errors for missing required fields"""
        # Missing host
        response = client.post("/api/v1/protect/controllers/test", json={
            "port": 443,
            "username": "admin",
            "password": "password"
        })
        assert response.status_code == 422

        # Missing username
        response = client.post("/api/v1/protect/controllers/test", json={
            "host": "192.168.1.1",
            "port": 443,
            "password": "password"
        })
        assert response.status_code == 422

        # Missing password
        response = client.post("/api/v1/protect/controllers/test", json={
            "host": "192.168.1.1",
            "port": 443,
            "username": "admin"
        })
        assert response.status_code == 422


class TestExistingControllerTestEndpoint:
    """Test suite for POST /protect/controllers/{id}/test endpoint (Story P2-1.2)"""

    @patch('app.services.protect_service.ProtectApiClient')
    def test_test_existing_controller_success(self, mock_client_class):
        """AC7: Test existing controller with stored credentials"""
        # Create a controller first
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Test Existing Controller",
            "host": "192.168.1.100",
            "port": 443,
            "username": "admin",
            "password": "storedpassword",
            "verify_ssl": False
        })
        controller_id = create_response.json()["data"]["id"]

        # Mock the client for testing
        mock_client = MagicMock()
        mock_client.update = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.bootstrap = MagicMock()
        mock_client.bootstrap.nvr = MagicMock()
        mock_client.bootstrap.nvr.version = "3.0.20"
        mock_client.bootstrap.cameras = [MagicMock(), MagicMock()]  # 2 cameras
        mock_client_class.return_value = mock_client

        # Test the existing controller
        response = client.post(f"/api/v1/protect/controllers/{controller_id}/test")
        assert response.status_code == 200

        data = response.json()
        assert data["data"]["success"] == True
        assert data["data"]["firmware_version"] == "3.0.20"
        assert data["data"]["camera_count"] == 2

    def test_test_nonexistent_controller(self):
        """AC7: Test non-existent controller returns 404"""
        response = client.post("/api/v1/protect/controllers/nonexistent-id/test")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch('app.services.protect_service.ProtectApiClient')
    def test_test_existing_controller_auth_failure(self, mock_client_class):
        """Test existing controller with authentication failure"""
        from uiprotect.exceptions import NotAuthorized

        # Create a controller first
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Auth Fail Controller",
            "host": "192.168.1.101",
            "port": 443,
            "username": "admin",
            "password": "oldpassword",
            "verify_ssl": False
        })
        controller_id = create_response.json()["data"]["id"]

        # Mock authentication failure
        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=NotAuthorized("Credentials changed"))
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        response = client.post(f"/api/v1/protect/controllers/{controller_id}/test")
        assert response.status_code == 401


class TestConnectionTestNoPersistence:
    """Test suite for AC8: Test endpoint does not save/persist any credentials"""

    @patch('app.services.protect_service.ProtectApiClient')
    def test_test_does_not_create_controller(self, mock_client_class):
        """AC8: Test endpoint does not create controller records"""
        # Mock successful connection
        mock_client = MagicMock()
        mock_client.update = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.bootstrap = MagicMock()
        mock_client.bootstrap.nvr = MagicMock()
        mock_client.bootstrap.nvr.version = "3.0.16"
        mock_client.bootstrap.cameras = []
        mock_client_class.return_value = mock_client

        # Get controller count before
        db = TestingSessionLocal()
        try:
            count_before = db.query(ProtectController).count()
        finally:
            db.close()

        # Run test
        test_data = {
            "host": "192.168.1.99",
            "port": 443,
            "username": "testuser",
            "password": "testpassword",
            "verify_ssl": False
        }
        response = client.post("/api/v1/protect/controllers/test", json=test_data)
        assert response.status_code == 200

        # Get controller count after
        db = TestingSessionLocal()
        try:
            count_after = db.query(ProtectController).count()
        finally:
            db.close()

        # Verify no new controllers were created
        assert count_after == count_before

    @patch('app.services.protect_service.ProtectApiClient')
    def test_test_does_not_modify_existing_controller(self, mock_client_class):
        """AC8: Test endpoint does not modify existing controller records"""
        # Create a controller
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "No Modify Controller",
            "host": "192.168.1.50",
            "port": 443,
            "username": "admin",
            "password": "originalpassword",
            "verify_ssl": False
        })
        controller_id = create_response.json()["data"]["id"]

        # Get original state
        db = TestingSessionLocal()
        try:
            original = db.query(ProtectController).filter(
                ProtectController.id == controller_id
            ).first()
            original_updated_at = original.updated_at
            original_is_connected = original.is_connected
        finally:
            db.close()

        # Mock the client
        mock_client = MagicMock()
        mock_client.update = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.bootstrap = MagicMock()
        mock_client.bootstrap.nvr = MagicMock()
        mock_client.bootstrap.nvr.version = "3.0.16"
        mock_client.bootstrap.cameras = []
        mock_client_class.return_value = mock_client

        # Run test on existing controller
        response = client.post(f"/api/v1/protect/controllers/{controller_id}/test")
        assert response.status_code == 200

        # Verify controller was not modified
        db = TestingSessionLocal()
        try:
            after_test = db.query(ProtectController).filter(
                ProtectController.id == controller_id
            ).first()
            # is_connected should not change during test
            assert after_test.is_connected == original_is_connected
        finally:
            db.close()


class TestProtectService:
    """Test suite for ProtectService class (Story P2-1.2)"""

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_service_test_connection_success(self, mock_client_class):
        """AC10: ProtectService.test_connection() returns correct result on success"""
        mock_client = MagicMock()
        mock_client.update = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.bootstrap = MagicMock()
        mock_client.bootstrap.nvr = MagicMock()
        mock_client.bootstrap.nvr.version = "3.0.16"
        mock_client.bootstrap.cameras = [MagicMock(), MagicMock()]
        mock_client_class.return_value = mock_client

        service = ProtectService()
        result = await service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="password",
            verify_ssl=False
        )

        assert result.success == True
        assert result.message == "Connected successfully"
        assert result.firmware_version == "3.0.16"
        assert result.camera_count == 2

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_service_test_connection_auth_error(self, mock_client_class):
        """AC10: ProtectService.test_connection() handles auth errors"""
        from uiprotect.exceptions import NotAuthorized

        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=NotAuthorized("Bad credentials"))
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        service = ProtectService()
        result = await service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="wrongpassword",
            verify_ssl=False
        )

        assert result.success == False
        assert result.message == "Authentication failed"
        assert result.error_type == "auth_error"

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_service_test_connection_timeout(self, mock_client_class):
        """AC10: ProtectService.test_connection() handles timeouts"""
        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        service = ProtectService()
        result = await service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="password",
            verify_ssl=False
        )

        assert result.success == False
        assert "timed out" in result.message
        assert result.error_type == "timeout"

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_service_closes_client_on_success(self, mock_client_class):
        """Test that client is properly closed after successful connection"""
        mock_client = MagicMock()
        mock_client.update = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.bootstrap = MagicMock()
        mock_client.bootstrap.nvr = MagicMock()
        mock_client.bootstrap.nvr.version = "3.0.16"
        mock_client.bootstrap.cameras = []
        mock_client_class.return_value = mock_client

        service = ProtectService()
        await service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="password",
            verify_ssl=False
        )

        # Verify close was called
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_service_closes_client_on_error(self, mock_client_class):
        """Test that client is properly closed after error"""
        from uiprotect.exceptions import NotAuthorized

        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=NotAuthorized("Bad creds"))
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        service = ProtectService()
        await service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="password",
            verify_ssl=False
        )

        # Verify close was called even on error
        mock_client.close.assert_called_once()


# Story P2-1.4: Connection Management Tests

class TestConnectEndpoint:
    """Test suite for POST /protect/controllers/{id}/connect endpoint (Story P2-1.4)"""

    @patch('app.services.protect_service.ProtectApiClient')
    def test_connect_controller_success(self, mock_client_class):
        """AC10: Connect endpoint returns success on successful connection"""
        # Create a controller first
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Connect Test Controller",
            "host": "192.168.1.100",
            "port": 443,
            "username": "admin",
            "password": "testpassword",
            "verify_ssl": False
        })
        controller_id = create_response.json()["data"]["id"]

        # Mock successful connection
        mock_client = MagicMock()
        mock_client.update = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.bootstrap = MagicMock()
        mock_client.bootstrap.nvr = MagicMock()
        mock_client.bootstrap.nvr.version = "3.0.16"
        mock_client.bootstrap.cameras = []
        mock_client.subscribe_websocket = MagicMock(return_value=MagicMock())
        mock_client_class.return_value = mock_client

        response = client.post(f"/api/v1/protect/controllers/{controller_id}/connect")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert data["data"]["controller_id"] == controller_id
        assert data["data"]["status"] == "connected"

    def test_connect_controller_not_found(self):
        """AC10: Connect endpoint returns 404 for non-existent controller"""
        response = client.post("/api/v1/protect/controllers/nonexistent-id/connect")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch('app.services.protect_service.ProtectApiClient')
    def test_connect_controller_connection_failure(self, mock_client_class):
        """AC10: Connect endpoint returns 503 on connection failure"""
        # Create a controller first
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Fail Connect Controller",
            "host": "192.168.1.254",
            "port": 443,
            "username": "admin",
            "password": "testpassword",
            "verify_ssl": False
        })
        controller_id = create_response.json()["data"]["id"]

        # Mock connection failure
        import aiohttp
        mock_client = MagicMock()
        mock_client.update = AsyncMock(
            side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("Connection refused"))
        )
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        response = client.post(f"/api/v1/protect/controllers/{controller_id}/connect")
        assert response.status_code == 503


class TestDisconnectEndpoint:
    """Test suite for POST /protect/controllers/{id}/disconnect endpoint (Story P2-1.4)"""

    def test_disconnect_controller_success(self):
        """AC10: Disconnect endpoint returns success"""
        # Create a controller first
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Disconnect Test Controller",
            "host": "192.168.1.100",
            "port": 443,
            "username": "admin",
            "password": "testpassword",
            "verify_ssl": False
        })
        controller_id = create_response.json()["data"]["id"]

        # Disconnect (even if not connected, should return success)
        response = client.post(f"/api/v1/protect/controllers/{controller_id}/disconnect")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert data["data"]["controller_id"] == controller_id
        assert data["data"]["status"] == "disconnected"

    def test_disconnect_controller_not_found(self):
        """AC10: Disconnect endpoint returns 404 for non-existent controller"""
        response = client.post("/api/v1/protect/controllers/nonexistent-id/disconnect")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestExponentialBackoff:
    """Test suite for exponential backoff reconnection (Story P2-1.4, AC3)"""

    def test_backoff_delays_sequence(self):
        """AC3: Verify backoff delays are 1, 2, 4, 8, 16, 30 (max)"""
        from app.services.protect_service import BACKOFF_DELAYS

        expected_delays = [1, 2, 4, 8, 16, 30]
        assert BACKOFF_DELAYS == expected_delays

    def test_backoff_max_delay(self):
        """AC3: Verify max delay is 30 seconds"""
        from app.services.protect_service import BACKOFF_DELAYS

        assert max(BACKOFF_DELAYS) == 30


class TestConnectionStateManagement:
    """Test suite for connection state management (Story P2-1.4, AC2, AC7, AC9)"""

    @patch('app.services.protect_service.SessionLocal', TestingSessionLocal)
    @patch('app.services.protect_service.ProtectApiClient')
    @pytest.mark.asyncio
    async def test_database_state_updated_on_connect(self, mock_client_class):
        """AC2: is_connected and last_connected_at updated on successful connection"""
        from app.services.protect_service import ProtectService
        from app.models.protect_controller import ProtectController

        # Create controller in database
        db = TestingSessionLocal()
        try:
            controller = ProtectController(
                name="State Test Controller",
                host="192.168.1.100",
                port=443,
                username="admin",
                password="testpassword",
                verify_ssl=False
            )
            db.add(controller)
            db.commit()
            db.refresh(controller)
            controller_id = str(controller.id)

            # Verify initial state
            assert controller.is_connected == False
            assert controller.last_connected_at is None
        finally:
            db.close()

        # Mock successful connection
        mock_client = MagicMock()
        mock_client.update = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.bootstrap = MagicMock()
        mock_client.bootstrap.nvr = MagicMock()
        mock_client.bootstrap.nvr.version = "3.0.16"
        mock_client.bootstrap.cameras = []
        mock_client.subscribe_websocket = MagicMock(return_value=MagicMock())
        mock_client_class.return_value = mock_client

        # Get fresh controller for connect
        db = TestingSessionLocal()
        try:
            fresh_controller = db.query(ProtectController).filter(
                ProtectController.id == controller_id
            ).first()

            service = ProtectService()
            await service.connect(fresh_controller)
        finally:
            db.close()

        # Verify state was updated
        db = TestingSessionLocal()
        try:
            updated_controller = db.query(ProtectController).filter(
                ProtectController.id == controller_id
            ).first()
            assert updated_controller.is_connected == True
            assert updated_controller.last_connected_at is not None
        finally:
            db.close()

        # Cleanup
        await service.disconnect(controller_id)

    def test_service_connection_dictionaries_initialized(self):
        """AC9: Service initializes connection dictionaries"""
        from app.services.protect_service import ProtectService

        service = ProtectService()
        assert hasattr(service, '_connections')
        assert hasattr(service, '_listener_tasks')
        assert isinstance(service._connections, dict)
        assert isinstance(service._listener_tasks, dict)

    def test_get_all_connection_statuses(self):
        """AC9: Service can report all connection statuses"""
        from app.services.protect_service import ProtectService

        service = ProtectService()
        statuses = service.get_all_connection_statuses()
        assert isinstance(statuses, dict)


class TestWebSocketBroadcast:
    """Test suite for WebSocket status broadcasting (Story P2-1.4, AC6)"""

    def test_protect_connection_status_constant_defined(self):
        """AC6: PROTECT_CONNECTION_STATUS message type is defined"""
        from app.services.protect_service import PROTECT_CONNECTION_STATUS

        assert PROTECT_CONNECTION_STATUS == "PROTECT_CONNECTION_STATUS"

    @patch('app.services.protect_service.get_websocket_manager')
    @pytest.mark.asyncio
    async def test_broadcast_status_called_on_connect(self, mock_get_ws_manager):
        """AC6: Status is broadcast on connection attempt"""
        from app.services.protect_service import ProtectService

        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast = AsyncMock(return_value=1)
        mock_get_ws_manager.return_value = mock_ws_manager

        service = ProtectService()
        await service._broadcast_status("test-id", "connecting")

        mock_ws_manager.broadcast.assert_called_once()
        call_args = mock_ws_manager.broadcast.call_args[0][0]
        assert call_args["type"] == "PROTECT_CONNECTION_STATUS"
        assert call_args["data"]["controller_id"] == "test-id"
        assert call_args["data"]["status"] == "connecting"


class TestResponseFormat:
    """Test suite for connection endpoint response format (Story P2-1.4)"""

    def test_connect_response_format(self):
        """Verify connect response follows { data, meta } format"""
        # Create controller
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Format Test Controller",
            "host": "192.168.1.100",
            "username": "admin",
            "password": "secret"
        })
        controller_id = create_response.json()["data"]["id"]

        # Disconnect endpoint should return proper format even without connection
        response = client.post(f"/api/v1/protect/controllers/{controller_id}/disconnect")
        data = response.json()

        assert "data" in data
        assert "meta" in data
        assert "request_id" in data["meta"]
        assert "timestamp" in data["meta"]
        assert "controller_id" in data["data"]
        assert "status" in data["data"]


# =============================================================================
# Story P2-2.1: Camera Discovery Tests
# =============================================================================

class TestCameraDiscoveryEndpoint:
    """Test suite for GET /protect/controllers/{id}/cameras endpoint (Story P2-2.1)"""

    def test_discover_cameras_controller_not_found(self):
        """AC5: Discovery endpoint returns 404 for non-existent controller"""
        response = client.get("/api/v1/protect/controllers/nonexistent-id/cameras")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_discover_cameras_response_format(self):
        """AC5, AC6: Discovery response has correct format with meta"""
        # Create controller first
        create_response = client.post("/api/v1/protect/controllers", json={
            "name": "Discovery Format Test",
            "host": "192.168.1.100",
            "port": 443,
            "username": "admin",
            "password": "testpass",
            "verify_ssl": False
        })
        controller_id = create_response.json()["data"]["id"]

        # Call discover cameras (will return empty without connection)
        response = client.get(f"/api/v1/protect/controllers/{controller_id}/cameras")

        # Should either return 200 with empty list or 503 if not connected
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            assert "meta" in data
            assert isinstance(data["data"], list)
            assert "count" in data["meta"]
            assert "controller_id" in data["meta"]
            assert "cached" in data["meta"]
            assert data["meta"]["controller_id"] == controller_id


class TestCameraDiscoveryService:
    """Test suite for ProtectService.discover_cameras method (Story P2-2.1)"""

    def test_camera_cache_initialized(self):
        """AC4: Service initializes camera cache"""
        from app.services.protect_service import ProtectService

        service = ProtectService()
        assert hasattr(service, '_camera_cache')
        assert isinstance(service._camera_cache, dict)

    def test_cache_ttl_constant_defined(self):
        """AC4: Cache TTL constant is 60 seconds"""
        from app.services.protect_service import CAMERA_CACHE_TTL_SECONDS

        assert CAMERA_CACHE_TTL_SECONDS == 60

    @pytest.mark.asyncio
    async def test_discover_cameras_not_connected_no_cache(self):
        """AC8: Discovery returns empty list with warning when not connected"""
        from app.services.protect_service import ProtectService

        service = ProtectService()
        result = await service.discover_cameras("test-controller-id")

        assert result.cameras == []
        assert result.cached == False
        assert result.warning is not None
        assert "not connected" in result.warning.lower()

    @pytest.mark.asyncio
    async def test_clear_camera_cache_specific(self):
        """Test clearing cache for specific controller"""
        from app.services.protect_service import ProtectService, DiscoveredCamera
        from datetime import datetime, timezone

        service = ProtectService()

        # Manually add cache entry
        test_cameras = [DiscoveredCamera(
            protect_camera_id="test-cam-1",
            name="Test Camera",
            type="camera",
            model="G4 Pro",
            is_online=True,
            is_doorbell=False,
            smart_detection_capabilities=["person"]
        )]
        service._camera_cache["controller-1"] = (test_cameras, datetime.now(timezone.utc))
        service._camera_cache["controller-2"] = (test_cameras, datetime.now(timezone.utc))

        # Clear specific controller
        service.clear_camera_cache("controller-1")

        assert "controller-1" not in service._camera_cache
        assert "controller-2" in service._camera_cache

    @pytest.mark.asyncio
    async def test_clear_camera_cache_all(self):
        """Test clearing all camera caches"""
        from app.services.protect_service import ProtectService, DiscoveredCamera
        from datetime import datetime, timezone

        service = ProtectService()

        # Manually add cache entries
        test_cameras = [DiscoveredCamera(
            protect_camera_id="test-cam-1",
            name="Test Camera",
            type="camera",
            model="G4 Pro",
            is_online=True,
            is_doorbell=False,
            smart_detection_capabilities=[]
        )]
        service._camera_cache["controller-1"] = (test_cameras, datetime.now(timezone.utc))
        service._camera_cache["controller-2"] = (test_cameras, datetime.now(timezone.utc))

        # Clear all
        service.clear_camera_cache()

        assert len(service._camera_cache) == 0


class TestDoorbellDetection:
    """Test suite for doorbell camera detection (Story P2-2.1, AC10)"""

    def test_doorbell_detection_by_type(self):
        """AC10: Doorbell detected from type containing 'doorbell'"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        # Create mock camera with doorbell type
        mock_camera = MagicMock()
        mock_camera.type = "UVC G4 Doorbell Pro"
        mock_camera.model = "G4 Doorbell Pro"

        assert service._is_doorbell_camera(mock_camera) == True

    def test_doorbell_detection_by_model(self):
        """AC10: Doorbell detected from model containing 'doorbell'"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        mock_camera = MagicMock()
        mock_camera.type = "camera"
        mock_camera.model = "G4 Doorbell"

        assert service._is_doorbell_camera(mock_camera) == True

    def test_doorbell_detection_by_feature_flag_chime(self):
        """AC10: Doorbell detected from has_chime feature flag"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        mock_camera = MagicMock()
        mock_camera.type = "camera"
        mock_camera.model = "G4 Camera"
        mock_camera.feature_flags = MagicMock()
        mock_camera.feature_flags.has_chime = True

        assert service._is_doorbell_camera(mock_camera) == True

    def test_non_doorbell_camera(self):
        """AC10: Regular camera not detected as doorbell"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        mock_camera = MagicMock()
        mock_camera.type = "camera"
        mock_camera.model = "G4 Pro"
        mock_camera.feature_flags = None

        assert service._is_doorbell_camera(mock_camera) == False


class TestSmartDetectionCapabilities:
    """Test suite for smart detection capability extraction (Story P2-2.1, AC2)"""

    def test_extract_smart_detect_types(self):
        """AC2: Extract smart detection capabilities from camera"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        mock_camera = MagicMock()
        mock_camera.smart_detect_types = ["person", "vehicle", "package"]
        mock_camera.feature_flags = None

        capabilities = service._get_smart_detection_capabilities(mock_camera)

        assert "person" in capabilities
        assert "vehicle" in capabilities
        assert "package" in capabilities

    def test_extract_from_feature_flags(self):
        """AC2: Extract capabilities from feature flags when smart_detect_types missing"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        mock_camera = MagicMock()
        mock_camera.smart_detect_types = None
        mock_camera.feature_flags = MagicMock()
        mock_camera.feature_flags.can_detect_person = True
        mock_camera.feature_flags.can_detect_vehicle = True
        mock_camera.feature_flags.has_smart_detect = False

        capabilities = service._get_smart_detection_capabilities(mock_camera)

        assert "person" in capabilities
        assert "vehicle" in capabilities

    def test_no_smart_detection(self):
        """AC2: Return empty list for cameras without smart detection"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        mock_camera = MagicMock()
        mock_camera.smart_detect_types = None
        mock_camera.feature_flags = None

        capabilities = service._get_smart_detection_capabilities(mock_camera)

        assert capabilities == []


class TestCameraDiscoverySchemas:
    """Test suite for camera discovery Pydantic schemas (Story P2-2.1)"""

    def test_protect_discovered_camera_schema(self):
        """AC2, AC5: ProtectDiscoveredCamera schema validates correctly"""
        from app.schemas.protect import ProtectDiscoveredCamera

        camera = ProtectDiscoveredCamera(
            protect_camera_id="abc123",
            name="Front Door",
            type="doorbell",
            model="G4 Doorbell Pro",
            is_online=True,
            is_doorbell=True,
            is_enabled_for_ai=False,
            smart_detection_capabilities=["person", "vehicle"]
        )

        assert camera.protect_camera_id == "abc123"
        assert camera.name == "Front Door"
        assert camera.type == "doorbell"
        assert camera.is_doorbell == True
        assert camera.is_enabled_for_ai == False
        assert "person" in camera.smart_detection_capabilities

    def test_protect_camera_discovery_meta_schema(self):
        """AC6: ProtectCameraDiscoveryMeta schema includes required fields"""
        from app.schemas.protect import ProtectCameraDiscoveryMeta

        meta = ProtectCameraDiscoveryMeta(
            count=5,
            controller_id="controller-123",
            cached=True,
            cached_at=None,
            warning=None
        )

        assert meta.count == 5
        assert meta.controller_id == "controller-123"
        assert meta.cached == True

    def test_protect_cameras_response_schema(self):
        """AC5, AC6: ProtectCamerasResponse schema structure"""
        from app.schemas.protect import (
            ProtectCamerasResponse,
            ProtectDiscoveredCamera,
            ProtectCameraDiscoveryMeta
        )

        camera = ProtectDiscoveredCamera(
            protect_camera_id="cam-1",
            name="Test Camera",
            type="camera",
            model="G4 Pro",
            is_online=True,
            is_doorbell=False,
            is_enabled_for_ai=True,
            smart_detection_capabilities=[]
        )

        response = ProtectCamerasResponse(
            data=[camera],
            meta=ProtectCameraDiscoveryMeta(
                count=1,
                controller_id="ctrl-1",
                cached=False,
                cached_at=None,
                warning=None
            )
        )

        assert len(response.data) == 1
        assert response.meta.count == 1
        assert response.meta.controller_id == "ctrl-1"
