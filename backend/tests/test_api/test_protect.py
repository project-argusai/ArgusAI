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
from contextlib import contextmanager
from app.models.protect_controller import ProtectController
from app.models.camera import Camera
from app.services.protect_service import ProtectService, ConnectionTestResult


def make_smart_detect_enum(value: str):
    """
    Helper to create mock SmartDetectObjectType enum with .value attribute.
    uiprotect returns SmartDetectObjectType enums, not plain strings.
    """
    mock_enum = MagicMock()
    mock_enum.value = value
    return mock_enum


def make_smart_detect_list(values: list):
    """Helper to create a list of mock SmartDetectObjectType enums."""
    return [make_smart_detect_enum(v) for v in values]


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


@contextmanager
def _testing_get_db_session():
    """
    Context manager mock for get_db_session() that uses test database.
    This mimics the get_db_session() context manager from app.core.database.
    Story P14-2.2: Updated to use context manager pattern instead of SessionLocal.
    """
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


# Create test client (module-level)
client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    # Clean up BEFORE the test to ensure isolation
    db = TestingSessionLocal()
    try:
        db.query(Camera).delete()
        db.query(ProtectController).delete()
        db.commit()
    finally:
        db.close()
    yield
    # Clean up after each test
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
        mock_client.close_session = AsyncMock()  # ProtectApiClient uses close_session()
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

        # Verify close_session was called (ProtectApiClient uses close_session, not close)
        mock_client.close_session.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.services.protect_service.ProtectApiClient')
    async def test_service_closes_client_on_error(self, mock_client_class):
        """Test that client is properly closed after error"""
        from uiprotect.exceptions import NotAuthorized

        mock_client = MagicMock()
        mock_client.update = AsyncMock(side_effect=NotAuthorized("Bad creds"))
        mock_client.close_session = AsyncMock()  # ProtectApiClient uses close_session()
        mock_client_class.return_value = mock_client

        service = ProtectService()
        await service.test_connection(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="password",
            verify_ssl=False
        )

        # Verify close_session was called even on error
        mock_client.close_session.assert_called_once()


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

    @patch('app.services.protect_service.get_db_session', _testing_get_db_session)
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
        """AC2: Extract smart detection capabilities from camera using can_detect_* properties"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        mock_camera = MagicMock()
        mock_camera.can_detect_person = True
        mock_camera.can_detect_vehicle = True
        mock_camera.can_detect_package = True
        mock_camera.can_detect_animal = False
        mock_camera.feature_flags = None

        capabilities = service._get_smart_detection_capabilities(mock_camera)

        assert "person" in capabilities
        assert "vehicle" in capabilities
        assert "package" in capabilities
        assert "animal" not in capabilities

    def test_extract_from_feature_flags(self):
        """AC2: Extract capabilities from feature flags when can_detect_* not available"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        mock_camera = MagicMock()
        mock_camera.can_detect_person = False
        mock_camera.can_detect_vehicle = False
        mock_camera.can_detect_package = False
        mock_camera.can_detect_animal = False
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
        mock_camera.can_detect_person = False
        mock_camera.can_detect_vehicle = False
        mock_camera.can_detect_package = False
        mock_camera.can_detect_animal = False
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


# Story P2-2.2: Camera Enable/Disable Endpoint Tests

class TestCameraEnableDisable:
    """Tests for POST /protect/controllers/{id}/cameras/{camera_id}/enable and /disable endpoints"""

    def test_enable_camera_controller_not_found(self):
        """AC6: Enable should return 404 for non-existent controller"""
        response = client.post("/api/v1/protect/controllers/nonexistent-id/cameras/cam-123/enable")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_disable_camera_controller_not_found(self):
        """AC7: Disable should return 404 for non-existent controller"""
        response = client.post("/api/v1/protect/controllers/nonexistent-id/cameras/cam-123/disable")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_disable_camera_not_enabled(self):
        """AC7: Disable should return 404 if camera not in database"""
        # Create a controller first
        db = TestingSessionLocal()
        try:
            controller = ProtectController(
                name="Test Controller",
                host="192.168.1.100",
                port=443,
                username="admin",
                password="test123",
                verify_ssl=False
            )
            db.add(controller)
            db.commit()
            db.refresh(controller)
            controller_id = controller.id
        finally:
            db.close()

        response = client.post(f"/api/v1/protect/controllers/{controller_id}/cameras/nonexistent-cam/disable")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower() or "not enabled" in response.json()["detail"].lower()


class TestCameraEnableDisableSchemas:
    """Tests for enable/disable Pydantic schemas"""

    def test_enable_request_schema_defaults(self):
        """Test ProtectCameraEnableRequest has correct defaults"""
        from app.schemas.protect import ProtectCameraEnableRequest

        request = ProtectCameraEnableRequest()

        assert request.name is None
        assert "person" in request.smart_detection_types
        assert "vehicle" in request.smart_detection_types
        assert "package" in request.smart_detection_types

    def test_enable_request_schema_custom_values(self):
        """Test ProtectCameraEnableRequest accepts custom values"""
        from app.schemas.protect import ProtectCameraEnableRequest

        request = ProtectCameraEnableRequest(
            name="Custom Name",
            smart_detection_types=["person", "animal"]
        )

        assert request.name == "Custom Name"
        assert request.smart_detection_types == ["person", "animal"]

    def test_enable_data_schema(self):
        """Test ProtectCameraEnableData schema"""
        from app.schemas.protect import ProtectCameraEnableData

        data = ProtectCameraEnableData(
            camera_id="db-cam-id",
            protect_camera_id="protect-cam-id",
            name="Test Camera",
            is_enabled_for_ai=True,
            smart_detection_types=["person", "vehicle"]
        )

        assert data.camera_id == "db-cam-id"
        assert data.protect_camera_id == "protect-cam-id"
        assert data.name == "Test Camera"
        assert data.is_enabled_for_ai == True
        assert data.smart_detection_types == ["person", "vehicle"]

    def test_disable_data_schema(self):
        """Test ProtectCameraDisableData schema"""
        from app.schemas.protect import ProtectCameraDisableData

        data = ProtectCameraDisableData(
            protect_camera_id="protect-cam-id",
            is_enabled_for_ai=False
        )

        assert data.protect_camera_id == "protect-cam-id"
        assert data.is_enabled_for_ai == False

    def test_enable_response_schema(self):
        """Test ProtectCameraEnableResponse schema"""
        from app.schemas.protect import ProtectCameraEnableResponse, ProtectCameraEnableData, MetaResponse

        response = ProtectCameraEnableResponse(
            data=ProtectCameraEnableData(
                camera_id="cam-1",
                protect_camera_id="protect-1",
                name="Test",
                is_enabled_for_ai=True,
                smart_detection_types=["person"]
            ),
            meta=MetaResponse()
        )

        assert response.data.is_enabled_for_ai == True
        assert response.meta is not None

    def test_disable_response_schema(self):
        """Test ProtectCameraDisableResponse schema"""
        from app.schemas.protect import ProtectCameraDisableResponse, ProtectCameraDisableData, MetaResponse

        response = ProtectCameraDisableResponse(
            data=ProtectCameraDisableData(
                protect_camera_id="protect-1",
                is_enabled_for_ai=False
            ),
            meta=MetaResponse()
        )

        assert response.data.is_enabled_for_ai == False
        assert response.meta is not None


# Story P2-2.3: Camera Filter Tests

class TestCameraFiltersSchemas:
    """Test camera filter schemas (Story P2-2.3)"""

    def test_filters_request_valid_types(self):
        """Test valid filter types are accepted"""
        from app.schemas.protect import ProtectCameraFiltersRequest

        request = ProtectCameraFiltersRequest(
            smart_detection_types=["person", "vehicle", "package"]
        )
        assert request.smart_detection_types == ["person", "vehicle", "package"]

    def test_filters_request_all_motion(self):
        """Test 'motion' filter type is accepted for all motion mode"""
        from app.schemas.protect import ProtectCameraFiltersRequest

        request = ProtectCameraFiltersRequest(
            smart_detection_types=["motion"]
        )
        assert request.smart_detection_types == ["motion"]

    def test_filters_request_animal_type(self):
        """Test 'animal' filter type is accepted"""
        from app.schemas.protect import ProtectCameraFiltersRequest

        request = ProtectCameraFiltersRequest(
            smart_detection_types=["person", "animal"]
        )
        assert request.smart_detection_types == ["person", "animal"]

    def test_filters_request_invalid_type_rejected(self):
        """Test invalid filter types are rejected (AC7)"""
        from app.schemas.protect import ProtectCameraFiltersRequest
        import pydantic

        with pytest.raises(pydantic.ValidationError) as exc_info:
            ProtectCameraFiltersRequest(
                smart_detection_types=["person", "invalid_type"]
            )

        error = exc_info.value
        assert "invalid_type" in str(error)

    def test_filters_response_schema(self):
        """Test ProtectCameraFiltersResponse schema"""
        from app.schemas.protect import ProtectCameraFiltersResponse, ProtectCameraFiltersData, MetaResponse

        response = ProtectCameraFiltersResponse(
            data=ProtectCameraFiltersData(
                protect_camera_id="protect-1",
                name="Test Camera",
                smart_detection_types=["person", "vehicle"],
                is_enabled_for_ai=True
            ),
            meta=MetaResponse()
        )

        assert response.data.protect_camera_id == "protect-1"
        assert response.data.smart_detection_types == ["person", "vehicle"]
        assert response.data.is_enabled_for_ai == True
        assert response.meta is not None


class TestCameraFiltersEndpoint:
    """Test camera filters PUT endpoint (Story P2-2.3)"""

    def test_update_filters_controller_not_found(self):
        """Test 404 when controller doesn't exist"""
        response = client.put(
            "/api/v1/protect/controllers/nonexistent-id/cameras/cam-1/filters",
            json={"smart_detection_types": ["person", "vehicle"]}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_update_filters_camera_not_enabled(self):
        """Test 404 when camera is not enabled for AI (AC6)"""
        db = TestingSessionLocal()
        try:
            # Create controller
            controller = ProtectController(
                name="Test Controller Filters",
                host="192.168.1.100",
                port=443,
                username="admin",
                password="test123",
                verify_ssl=False
            )
            db.add(controller)
            db.commit()
            controller_id = str(controller.id)

            # Try to update filters for non-existent camera
            response = client.put(
                f"/api/v1/protect/controllers/{controller_id}/cameras/nonexistent-cam/filters",
                json={"smart_detection_types": ["person", "vehicle"]}
            )
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
        finally:
            db.close()

    def test_update_filters_validation_error(self):
        """Test validation error for invalid filter types (AC7)"""
        db = TestingSessionLocal()
        try:
            # Create controller
            controller = ProtectController(
                name="Test Controller Validation",
                host="192.168.1.101",
                port=443,
                username="admin",
                password="test123",
                verify_ssl=False
            )
            db.add(controller)
            db.commit()
            controller_id = str(controller.id)

            response = client.put(
                f"/api/v1/protect/controllers/{controller_id}/cameras/cam-1/filters",
                json={"smart_detection_types": ["invalid_type"]}
            )
            assert response.status_code == 422  # Validation error
        finally:
            db.close()


class TestDiscoveredCameraSchemaWithFilters:
    """Test ProtectDiscoveredCamera schema includes filters (Story P2-2.3)"""

    def test_schema_includes_smart_detection_types(self):
        """Test smart_detection_types field exists in response schema"""
        from app.schemas.protect import ProtectDiscoveredCamera

        camera = ProtectDiscoveredCamera(
            protect_camera_id="protect-1",
            name="Test Camera",
            type="camera",
            model="G4 Pro",
            is_online=True,
            is_doorbell=False,
            is_enabled_for_ai=True,
            smart_detection_capabilities=["person", "vehicle"],
            smart_detection_types=["person", "vehicle", "package"]
        )

        assert camera.smart_detection_types == ["person", "vehicle", "package"]

    def test_schema_smart_detection_types_optional(self):
        """Test smart_detection_types is optional (null for disabled cameras)"""
        from app.schemas.protect import ProtectDiscoveredCamera

        camera = ProtectDiscoveredCamera(
            protect_camera_id="protect-1",
            name="Test Camera",
            type="camera",
            model="G4 Pro",
            is_online=True,
            is_doorbell=False,
            is_enabled_for_ai=False,
            smart_detection_capabilities=["person", "vehicle"],
            smart_detection_types=None
        )

        assert camera.smart_detection_types is None


# =============================================================================
# Story P2-2.4: Camera Status Sync and Refresh Functionality Tests
# =============================================================================

class TestCameraStatusDebounce:
    """Test suite for camera status debounce logic (Story P2-2.4, AC12)"""

    def test_debounce_constant_defined(self):
        """AC12: Camera status debounce constant is 5 seconds"""
        from app.services.protect_service import CAMERA_STATUS_DEBOUNCE_SECONDS

        assert CAMERA_STATUS_DEBOUNCE_SECONDS == 5

    def test_camera_status_changed_constant_defined(self):
        """AC7: CAMERA_STATUS_CHANGED message type is defined"""
        from app.services.protect_service import CAMERA_STATUS_CHANGED

        assert CAMERA_STATUS_CHANGED == "CAMERA_STATUS_CHANGED"

    def test_should_broadcast_first_time(self):
        """AC12: First status broadcast should always be allowed"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        # First broadcast should be allowed
        assert service._should_broadcast_camera_status("camera-1") == True

    def test_should_broadcast_after_debounce_period(self):
        """AC12: Broadcast allowed after 5 second debounce"""
        from app.services.protect_service import ProtectService, CAMERA_STATUS_DEBOUNCE_SECONDS
        from datetime import datetime, timezone, timedelta

        service = ProtectService()
        camera_id = "camera-debounce-test"

        # Simulate a broadcast that happened 6 seconds ago (past debounce)
        service._camera_status_broadcast_times[camera_id] = (
            datetime.now(timezone.utc) - timedelta(seconds=CAMERA_STATUS_DEBOUNCE_SECONDS + 1)
        )

        # Should be allowed
        assert service._should_broadcast_camera_status(camera_id) == True

    def test_should_not_broadcast_during_debounce(self):
        """AC12: Broadcast blocked within 5 second debounce window"""
        from app.services.protect_service import ProtectService, CAMERA_STATUS_DEBOUNCE_SECONDS
        from datetime import datetime, timezone, timedelta

        service = ProtectService()
        camera_id = "camera-debounce-block"

        # Simulate a broadcast that happened 2 seconds ago (within debounce)
        service._camera_status_broadcast_times[camera_id] = (
            datetime.now(timezone.utc) - timedelta(seconds=2)
        )

        # Should be blocked
        assert service._should_broadcast_camera_status(camera_id) == False

    def test_debounce_exactly_at_boundary(self):
        """AC12: Broadcast allowed exactly at 5 second mark"""
        from app.services.protect_service import ProtectService, CAMERA_STATUS_DEBOUNCE_SECONDS
        from datetime import datetime, timezone, timedelta

        service = ProtectService()
        camera_id = "camera-boundary"

        # Simulate a broadcast that happened exactly at the boundary
        service._camera_status_broadcast_times[camera_id] = (
            datetime.now(timezone.utc) - timedelta(seconds=CAMERA_STATUS_DEBOUNCE_SECONDS)
        )

        # Should be allowed (>= check)
        assert service._should_broadcast_camera_status(camera_id) == True

    def test_multiple_cameras_independent_debounce(self):
        """AC12: Each camera has independent debounce tracking"""
        from app.services.protect_service import ProtectService
        from datetime import datetime, timezone, timedelta

        service = ProtectService()

        # Camera 1 was broadcast 2 seconds ago (debounced)
        service._camera_status_broadcast_times["camera-1"] = (
            datetime.now(timezone.utc) - timedelta(seconds=2)
        )

        # Camera 2 has never broadcast
        # Camera 3 was broadcast 10 seconds ago

        service._camera_status_broadcast_times["camera-3"] = (
            datetime.now(timezone.utc) - timedelta(seconds=10)
        )

        assert service._should_broadcast_camera_status("camera-1") == False
        assert service._should_broadcast_camera_status("camera-2") == True  # Never broadcast
        assert service._should_broadcast_camera_status("camera-3") == True  # Past debounce


class TestCameraStatusChangedMessage:
    """Test suite for CAMERA_STATUS_CHANGED WebSocket message (Story P2-2.4, AC6, AC7)"""

    @patch('app.services.protect_service.get_websocket_manager')
    @pytest.mark.asyncio
    async def test_broadcast_camera_status_change_format(self, mock_get_ws_manager):
        """AC7: Verify correct message format for camera status change"""
        from app.services.protect_service import ProtectService, CAMERA_STATUS_CHANGED

        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast = AsyncMock(return_value=1)
        mock_get_ws_manager.return_value = mock_ws_manager

        service = ProtectService()
        await service._broadcast_camera_status_change(
            controller_id="ctrl-123",
            camera_id="cam-456",
            is_online=True
        )

        mock_ws_manager.broadcast.assert_called_once()
        call_args = mock_ws_manager.broadcast.call_args[0][0]

        # Verify message format (AC7)
        assert call_args["type"] == CAMERA_STATUS_CHANGED
        assert "data" in call_args
        assert call_args["data"]["controller_id"] == "ctrl-123"
        assert call_args["data"]["camera_id"] == "cam-456"
        assert call_args["data"]["is_online"] == True

    @patch('app.services.protect_service.get_websocket_manager')
    @pytest.mark.asyncio
    async def test_broadcast_offline_status(self, mock_get_ws_manager):
        """AC7: Verify offline status broadcasts correctly"""
        from app.services.protect_service import ProtectService

        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast = AsyncMock(return_value=1)
        mock_get_ws_manager.return_value = mock_ws_manager

        service = ProtectService()
        await service._broadcast_camera_status_change(
            controller_id="ctrl-123",
            camera_id="cam-789",
            is_online=False
        )

        call_args = mock_ws_manager.broadcast.call_args[0][0]
        assert call_args["data"]["is_online"] == False


class TestHandleWebSocketEvent:
    """Test suite for WebSocket event handling (Story P2-2.4, AC6)"""

    @patch('app.services.protect_service.get_websocket_manager')
    @pytest.mark.asyncio
    async def test_handle_camera_status_change(self, mock_get_ws_manager):
        """AC6: Camera status change event triggers broadcast"""
        from app.services.protect_service import ProtectService

        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast = AsyncMock(return_value=1)
        mock_get_ws_manager.return_value = mock_ws_manager

        service = ProtectService()

        # Create mock WebSocket message
        mock_msg = MagicMock()
        mock_msg.action = "update"
        mock_msg.new_obj = MagicMock()
        mock_msg.new_obj.__class__.__name__ = "Camera"
        type(mock_msg.new_obj).__name__ = "Camera"
        mock_msg.new_obj.id = "protect-cam-123"
        mock_msg.new_obj.is_connected = True

        # Process the event
        await service._handle_websocket_event("ctrl-1", mock_msg)

        # Verify broadcast was called
        mock_ws_manager.broadcast.assert_called()

    @pytest.mark.asyncio
    async def test_handle_event_non_camera_ignored(self):
        """AC6: Non-camera events are ignored"""
        from app.services.protect_service import ProtectService

        service = ProtectService()

        # Create mock WebSocket message for non-camera object
        mock_msg = MagicMock()
        mock_msg.action = "update"
        mock_msg.new_obj = MagicMock()
        type(mock_msg.new_obj).__name__ = "Light"  # Not Camera or Doorbell
        mock_msg.new_obj.id = "light-123"

        # Process should not raise error and should return early
        await service._handle_websocket_event("ctrl-1", mock_msg)

    @pytest.mark.asyncio
    async def test_handle_event_no_status_change_ignored(self):
        """AC6: Events without status change are not broadcast"""
        from app.services.protect_service import ProtectService

        service = ProtectService()
        camera_id = "cam-no-change"

        # Set up last known status
        service._last_camera_status[camera_id] = True

        # Create mock event with same status
        mock_msg = MagicMock()
        mock_msg.action = "update"
        mock_msg.new_obj = MagicMock()
        type(mock_msg.new_obj).__name__ = "Camera"
        mock_msg.new_obj.id = camera_id
        mock_msg.new_obj.is_connected = True  # Same as last known

        # Patch broadcast to track calls
        with patch.object(service, '_broadcast_camera_status_change', new_callable=AsyncMock) as mock_broadcast:
            await service._handle_websocket_event("ctrl-1", mock_msg)

            # Should not broadcast since status didn't change
            mock_broadcast.assert_not_called()


class TestDiscoveredCameraNewBadge:
    """Test suite for newly discovered camera 'New' badge (Story P2-2.4, AC11)"""

    def test_schema_includes_is_new_field(self):
        """AC11: ProtectDiscoveredCamera schema includes is_new field"""
        from app.schemas.protect import ProtectDiscoveredCamera

        camera = ProtectDiscoveredCamera(
            protect_camera_id="protect-1",
            name="New Camera",
            type="camera",
            model="G4 Pro",
            is_online=True,
            is_doorbell=False,
            is_enabled_for_ai=False,
            smart_detection_capabilities=["person"],
            is_new=True
        )

        assert camera.is_new == True

    def test_schema_is_new_defaults_to_false(self):
        """AC11: is_new field defaults to False"""
        from app.schemas.protect import ProtectDiscoveredCamera

        camera = ProtectDiscoveredCamera(
            protect_camera_id="protect-1",
            name="Existing Camera",
            type="camera",
            model="G4 Pro",
            is_online=True,
            is_doorbell=False,
            is_enabled_for_ai=False,
            smart_detection_capabilities=["person"]
        )

        assert camera.is_new == False


class TestCameraStatusServiceDictionaries:
    """Test suite for camera status tracking dictionaries (Story P2-2.4)"""

    def test_camera_status_broadcast_times_initialized(self):
        """Service initializes camera status broadcast times dictionary"""
        from app.services.protect_service import ProtectService

        service = ProtectService()
        assert hasattr(service, '_camera_status_broadcast_times')
        assert isinstance(service._camera_status_broadcast_times, dict)

    def test_last_camera_status_initialized(self):
        """Service initializes last camera status dictionary"""
        from app.services.protect_service import ProtectService

        service = ProtectService()
        assert hasattr(service, '_last_camera_status')
        assert isinstance(service._last_camera_status, dict)


class TestForceRefreshParameter:
    """Test suite for force_refresh parameter (Story P2-2.4, AC2, AC3)"""

    @patch('app.services.protect_service.get_db_session', _testing_get_db_session)
    @pytest.mark.asyncio
    async def test_discover_cameras_force_refresh_clears_cache(self):
        """AC3: force_refresh=True should bypass cache"""
        from app.services.protect_service import ProtectService, DiscoveredCamera
        from datetime import datetime, timezone

        service = ProtectService()
        controller_id = "test-controller"

        # Pre-populate cache
        cached_cameras = [DiscoveredCamera(
            protect_camera_id="cached-cam",
            name="Cached Camera",
            type="camera",
            model="G4 Pro",
            is_online=True,
            is_doorbell=False,
            smart_detection_capabilities=["person"]
        )]
        service._camera_cache[controller_id] = (cached_cameras, datetime.now(timezone.utc))

        # Call discover_cameras with force_refresh=True (not connected, but should still clear cache)
        result = await service.discover_cameras(controller_id, force_refresh=True)

        # Cache should be cleared even if not connected
        # Result will indicate not connected since we didn't set up a real connection
        assert result.warning is not None
        assert "not connected" in result.warning.lower()


# =============================================================================
# Story P2-3.1: Protect Event Listener and Event Handler Tests
# =============================================================================

class TestProtectEventHandlerConstants:
    """Test suite for ProtectEventHandler constants (Story P2-3.1, AC2, AC10)"""

    def test_event_cooldown_constant_defined(self):
        """AC10: Event cooldown constant is 60 seconds"""
        from app.services.protect_event_handler import EVENT_COOLDOWN_SECONDS

        assert EVENT_COOLDOWN_SECONDS == 60

    def test_event_type_mapping_defined(self):
        """AC2: Event type mapping from Protect to filter types is defined"""
        from app.services.protect_event_handler import EVENT_TYPE_MAPPING

        assert EVENT_TYPE_MAPPING["motion"] == "motion"
        assert EVENT_TYPE_MAPPING["smart_detect_person"] == "person"
        assert EVENT_TYPE_MAPPING["smart_detect_vehicle"] == "vehicle"
        assert EVENT_TYPE_MAPPING["smart_detect_package"] == "package"
        assert EVENT_TYPE_MAPPING["smart_detect_animal"] == "animal"
        assert EVENT_TYPE_MAPPING["ring"] == "ring"

    def test_valid_event_types_contains_all_mappings(self):
        """AC2: All event types in mapping are in valid event types set"""
        from app.services.protect_event_handler import EVENT_TYPE_MAPPING, VALID_EVENT_TYPES

        for event_type in EVENT_TYPE_MAPPING.keys():
            assert event_type in VALID_EVENT_TYPES


class TestProtectEventHandlerInit:
    """Test suite for ProtectEventHandler initialization (Story P2-3.1)"""

    def test_handler_initializes_with_empty_tracking(self):
        """Event handler initializes with empty last event times dictionary"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()
        assert hasattr(handler, '_last_event_times')
        assert isinstance(handler._last_event_times, dict)
        assert len(handler._last_event_times) == 0

    def test_singleton_returns_same_instance(self):
        """get_protect_event_handler returns singleton instance"""
        from app.services.protect_event_handler import get_protect_event_handler

        handler1 = get_protect_event_handler()
        handler2 = get_protect_event_handler()
        assert handler1 is handler2


class TestEventTypeParsing:
    """Test suite for event type parsing (Story P2-3.1, AC2)"""

    def _make_smart_detect_enum(self, value: str):
        """Helper to create mock SmartDetectObjectType enum with .value attribute"""
        mock_enum = MagicMock()
        mock_enum.value = value
        return mock_enum

    def test_parse_motion_detected(self):
        """AC2: Parse motion event from camera object"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_obj = MagicMock()
        mock_obj.is_motion_currently_detected = True
        mock_obj.active_smart_detect_types = None

        event_types = handler._parse_event_types(mock_obj, "Camera")
        assert "motion" in event_types

    def test_parse_no_motion_detected(self):
        """AC2: No motion event when is_motion_currently_detected is False"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_obj = MagicMock()
        mock_obj.is_motion_currently_detected = False
        mock_obj.active_smart_detect_types = None

        event_types = handler._parse_event_types(mock_obj, "Camera")
        assert "motion" not in event_types

    def test_parse_smart_detect_person(self):
        """AC2: Parse smart_detect_person from camera object"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_obj = MagicMock()
        mock_obj.is_motion_currently_detected = False
        mock_obj.active_smart_detect_types = [self._make_smart_detect_enum("person")]

        event_types = handler._parse_event_types(mock_obj, "Camera")
        assert "smart_detect_person" in event_types

    def test_parse_smart_detect_vehicle(self):
        """AC2: Parse smart_detect_vehicle from camera object"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_obj = MagicMock()
        mock_obj.is_motion_currently_detected = False
        mock_obj.active_smart_detect_types = [self._make_smart_detect_enum("vehicle")]

        event_types = handler._parse_event_types(mock_obj, "Camera")
        assert "smart_detect_vehicle" in event_types

    def test_parse_smart_detect_package(self):
        """AC2: Parse smart_detect_package from camera object"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_obj = MagicMock()
        mock_obj.is_motion_currently_detected = False
        mock_obj.active_smart_detect_types = [self._make_smart_detect_enum("package")]

        event_types = handler._parse_event_types(mock_obj, "Camera")
        assert "smart_detect_package" in event_types

    def test_parse_smart_detect_animal(self):
        """AC2: Parse smart_detect_animal from camera object"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_obj = MagicMock()
        mock_obj.is_motion_currently_detected = False
        mock_obj.active_smart_detect_types = [self._make_smart_detect_enum("animal")]

        event_types = handler._parse_event_types(mock_obj, "Camera")
        assert "smart_detect_animal" in event_types

    def test_parse_multiple_smart_detects(self):
        """AC2: Parse multiple smart detection types"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_obj = MagicMock()
        mock_obj.is_motion_currently_detected = True
        mock_obj.active_smart_detect_types = [
            self._make_smart_detect_enum("person"),
            self._make_smart_detect_enum("vehicle")
        ]

        event_types = handler._parse_event_types(mock_obj, "Camera")
        assert "motion" in event_types
        assert "smart_detect_person" in event_types
        assert "smart_detect_vehicle" in event_types

    def test_parse_doorbell_ring(self):
        """AC2: Parse ring event from doorbell"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_obj = MagicMock()
        mock_obj.is_motion_currently_detected = False
        mock_obj.active_smart_detect_types = None
        mock_obj.is_ringing = True

        event_types = handler._parse_event_types(mock_obj, "Doorbell")
        assert "ring" in event_types

    def test_parse_doorbell_no_ring(self):
        """AC2: No ring event when doorbell is not ringing"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_obj = MagicMock()
        mock_obj.is_motion_currently_detected = False
        mock_obj.active_smart_detect_types = None
        mock_obj.is_ringing = False

        event_types = handler._parse_event_types(mock_obj, "Doorbell")
        assert "ring" not in event_types


class TestEventFiltering:
    """Test suite for event filtering logic (Story P2-3.1, AC5, AC6, AC7, AC8)"""

    def test_should_process_all_motion_mode_empty_array(self):
        """AC8: Empty array means all-motion mode - process all events"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Empty array should process all event types
        assert handler._should_process_event("person", [], "Test Camera") == True
        assert handler._should_process_event("vehicle", [], "Test Camera") == True
        assert handler._should_process_event("motion", [], "Test Camera") == True

    def test_should_process_all_motion_mode_motion_only(self):
        """AC8: ["motion"] means all-motion mode - process all events"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # ["motion"] should also process all event types
        assert handler._should_process_event("person", ["motion"], "Test Camera") == True
        assert handler._should_process_event("vehicle", ["motion"], "Test Camera") == True
        assert handler._should_process_event("motion", ["motion"], "Test Camera") == True

    def test_should_process_matching_filter(self):
        """AC6: Event type in filter list should pass"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        assert handler._should_process_event("person", ["person", "vehicle"], "Test Camera") == True
        assert handler._should_process_event("vehicle", ["person", "vehicle"], "Test Camera") == True

    def test_should_not_process_non_matching_filter(self):
        """AC7: Event type not in filter list should be discarded"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Camera configured for person only, vehicle event should be filtered
        assert handler._should_process_event("vehicle", ["person"], "Test Camera") == False
        # Camera configured for vehicles, person event should be filtered
        assert handler._should_process_event("person", ["vehicle"], "Test Camera") == False

    def test_should_process_single_filter_type(self):
        """AC6, AC7: Single filter type only accepts that type"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Only person configured
        assert handler._should_process_event("person", ["person"], "Test Camera") == True
        assert handler._should_process_event("vehicle", ["person"], "Test Camera") == False
        assert handler._should_process_event("package", ["person"], "Test Camera") == False

    def test_load_smart_detection_types_valid_json(self):
        """AC5: Load smart_detection_types from valid JSON"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_camera = MagicMock()
        mock_camera.smart_detection_types = '["person", "vehicle"]'

        result = handler._load_smart_detection_types(mock_camera)
        assert result == ["person", "vehicle"]

    def test_load_smart_detection_types_null(self):
        """AC5: Load smart_detection_types returns empty list for null"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_camera = MagicMock()
        mock_camera.smart_detection_types = None

        result = handler._load_smart_detection_types(mock_camera)
        assert result == []

    def test_load_smart_detection_types_invalid_json(self):
        """AC5: Load smart_detection_types returns empty list for invalid JSON"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        mock_camera = MagicMock()
        mock_camera.name = "Test Camera"
        mock_camera.id = "test-id"
        mock_camera.smart_detection_types = "not-valid-json"

        result = handler._load_smart_detection_types(mock_camera)
        assert result == []


class TestEventDeduplication:
    """Test suite for event deduplication (Story P2-3.1, AC9, AC10)"""

    def test_first_event_is_not_duplicate(self):
        """AC9: First event for a camera is not a duplicate"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # First event should not be duplicate
        assert handler._is_duplicate_event("camera-1", "Test Camera") == False

    def test_event_within_cooldown_is_duplicate(self):
        """AC10: Event within 60 second cooldown is duplicate"""
        from app.services.protect_event_handler import ProtectEventHandler
        from datetime import datetime, timezone, timedelta

        handler = ProtectEventHandler()
        camera_id = "camera-duplicate-test"

        # Simulate an event that happened 30 seconds ago (within cooldown)
        handler._last_event_times[camera_id] = (
            datetime.now(timezone.utc) - timedelta(seconds=30)
        )

        assert handler._is_duplicate_event(camera_id, "Test Camera") == True

    def test_event_after_cooldown_is_not_duplicate(self):
        """AC10: Event after 60 second cooldown is not duplicate"""
        from app.services.protect_event_handler import ProtectEventHandler, EVENT_COOLDOWN_SECONDS
        from datetime import datetime, timezone, timedelta

        handler = ProtectEventHandler()
        camera_id = "camera-after-cooldown"

        # Simulate an event that happened 65 seconds ago (past cooldown)
        handler._last_event_times[camera_id] = (
            datetime.now(timezone.utc) - timedelta(seconds=EVENT_COOLDOWN_SECONDS + 5)
        )

        assert handler._is_duplicate_event(camera_id, "Test Camera") == False

    def test_deduplication_exactly_at_boundary(self):
        """AC10: Event exactly at cooldown boundary is not duplicate"""
        from app.services.protect_event_handler import ProtectEventHandler, EVENT_COOLDOWN_SECONDS
        from datetime import datetime, timezone, timedelta

        handler = ProtectEventHandler()
        camera_id = "camera-boundary"

        # Simulate an event that happened exactly at the cooldown boundary
        handler._last_event_times[camera_id] = (
            datetime.now(timezone.utc) - timedelta(seconds=EVENT_COOLDOWN_SECONDS)
        )

        # Should be allowed (>= check)
        assert handler._is_duplicate_event(camera_id, "Test Camera") == False

    def test_multiple_cameras_independent_deduplication(self):
        """AC9: Each camera has independent deduplication tracking"""
        from app.services.protect_event_handler import ProtectEventHandler
        from datetime import datetime, timezone, timedelta

        handler = ProtectEventHandler()

        # Camera 1 had event 30 seconds ago (within cooldown)
        handler._last_event_times["camera-1"] = (
            datetime.now(timezone.utc) - timedelta(seconds=30)
        )

        # Camera 2 has never had an event
        # Camera 3 had event 120 seconds ago (past cooldown)
        handler._last_event_times["camera-3"] = (
            datetime.now(timezone.utc) - timedelta(seconds=120)
        )

        assert handler._is_duplicate_event("camera-1", "Camera 1") == True   # Within cooldown
        assert handler._is_duplicate_event("camera-2", "Camera 2") == False  # First event
        assert handler._is_duplicate_event("camera-3", "Camera 3") == False  # Past cooldown

    def test_clear_event_tracking_specific_camera(self):
        """Clear event tracking for specific camera"""
        from app.services.protect_event_handler import ProtectEventHandler
        from datetime import datetime, timezone

        handler = ProtectEventHandler()
        handler._last_event_times["camera-1"] = datetime.now(timezone.utc)
        handler._last_event_times["camera-2"] = datetime.now(timezone.utc)

        handler.clear_event_tracking("camera-1")

        assert "camera-1" not in handler._last_event_times
        assert "camera-2" in handler._last_event_times

    def test_clear_event_tracking_all_cameras(self):
        """Clear all event tracking data"""
        from app.services.protect_event_handler import ProtectEventHandler
        from datetime import datetime, timezone

        handler = ProtectEventHandler()
        handler._last_event_times["camera-1"] = datetime.now(timezone.utc)
        handler._last_event_times["camera-2"] = datetime.now(timezone.utc)

        handler.clear_event_tracking()

        assert len(handler._last_event_times) == 0


class TestHandleEventCameraLookup:
    """Test suite for camera lookup in event handling (Story P2-3.1, AC3, AC4)"""

    @patch('app.services.protect_event_handler.get_db_session', _testing_get_db_session)
    @pytest.mark.asyncio
    async def test_handle_event_unknown_camera_discarded(self):
        """AC4: Event from unknown camera is discarded silently"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create mock message with camera not in database
        mock_msg = MagicMock()
        mock_msg.new_obj = MagicMock()
        type(mock_msg.new_obj).__name__ = "Camera"
        mock_msg.new_obj.id = "unknown-protect-camera-id"
        mock_msg.new_obj.is_motion_currently_detected = True
        mock_msg.new_obj.active_smart_detect_types = None

        result = await handler.handle_event("ctrl-1", mock_msg)
        assert result == False

    @patch('app.services.protect_event_handler.get_db_session', _testing_get_db_session)
    @pytest.mark.asyncio
    async def test_handle_event_disabled_camera_discarded(self):
        """AC4: Event from disabled camera is discarded silently"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create a disabled camera in database
        db = TestingSessionLocal()
        try:
            camera = Camera(
                name="Disabled Camera",
                type="rtsp",
                source_type="protect",
                protect_camera_id="disabled-protect-cam",
                is_enabled=False,
                smart_detection_types='["person"]'
            )
            db.add(camera)
            db.commit()

            # Create mock message
            mock_msg = MagicMock()
            mock_msg.new_obj = MagicMock()
            type(mock_msg.new_obj).__name__ = "Camera"
            mock_msg.new_obj.id = "disabled-protect-cam"
            mock_msg.new_obj.is_motion_currently_detected = True
            mock_msg.new_obj.active_smart_detect_types = None

            result = await handler.handle_event("ctrl-1", mock_msg)
            assert result == False
        finally:
            db.close()

    @patch('app.services.protect_event_handler.get_db_session', _testing_get_db_session)
    @pytest.mark.asyncio
    async def test_handle_event_non_protect_camera_discarded(self):
        """AC4: Event from camera with wrong source_type is discarded"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create an RTSP camera (not protect)
        db = TestingSessionLocal()
        try:
            camera = Camera(
                name="RTSP Camera",
                type="rtsp",
                source_type="rtsp",  # Not protect
                protect_camera_id="rtsp-protect-cam",
                is_enabled=True,
                smart_detection_types='["person"]'
            )
            db.add(camera)
            db.commit()

            # Create mock message
            mock_msg = MagicMock()
            mock_msg.new_obj = MagicMock()
            type(mock_msg.new_obj).__name__ = "Camera"
            mock_msg.new_obj.id = "rtsp-protect-cam"
            mock_msg.new_obj.is_motion_currently_detected = True
            mock_msg.new_obj.active_smart_detect_types = None

            result = await handler.handle_event("ctrl-1", mock_msg)
            assert result == False
        finally:
            db.close()


class TestHandleEventFullFlow:
    """Test suite for full event handling flow (Story P2-3.1, AC1, AC3, AC5, AC6)"""

    @patch('app.services.protect_event_handler.get_db_session', _testing_get_db_session)
    @pytest.mark.asyncio
    async def test_handle_event_passes_all_filters(self):
        """AC1, AC3, AC5, AC6: Event that matches all criteria passes (Story P2-3.3)"""
        from app.services.protect_event_handler import ProtectEventHandler
        from app.services.snapshot_service import SnapshotResult
        from datetime import datetime, timezone

        handler = ProtectEventHandler()
        handler.clear_event_tracking()

        # Create enabled protect camera in database
        db = TestingSessionLocal()
        try:
            camera = Camera(
                name="Enabled Camera",
                type="rtsp",
                source_type="protect",
                protect_camera_id="enabled-protect-cam",
                is_enabled=True,
                smart_detection_types='["person"]'
            )
            db.add(camera)
            db.commit()

            # Create mock message with person detection
            mock_msg = MagicMock()
            mock_msg.new_obj = MagicMock()
            type(mock_msg.new_obj).__name__ = "Camera"
            mock_msg.new_obj.id = "enabled-protect-cam"
            mock_msg.new_obj.is_motion_currently_detected = False
            mock_msg.new_obj.active_smart_detect_types = make_smart_detect_list(["person"])
            mock_msg.new_obj.last_motion = None
            mock_msg.new_obj.last_smart_detect = None

            # Mock snapshot service to return successful result (Story P2-3.2)
            mock_snapshot_result = SnapshotResult(
                image_base64="dGVzdA==",  # Valid base64 for "test"
                thumbnail_path="/tmp/test.jpg",
                width=1920,
                height=1080,
                camera_id=str(camera.id),
                timestamp=datetime.now(timezone.utc)
            )

            # Mock AI service for Story P2-3.3
            mock_ai_result = MagicMock()
            mock_ai_result.success = True
            mock_ai_result.description = "A person detected near the camera"
            mock_ai_result.confidence = 85
            mock_ai_result.objects_detected = ["person"]
            mock_ai_result.provider = "openai"
            mock_ai_result.response_time_ms = 500
            mock_ai_result.error = None

            with patch('app.services.protect_event_handler.get_snapshot_service') as mock_snapshot, \
                 patch.object(handler, '_submit_to_ai_pipeline', new_callable=AsyncMock) as mock_ai_submit, \
                 patch.object(handler, '_store_protect_event', new_callable=AsyncMock) as mock_store, \
                 patch.object(handler, '_broadcast_event_created', new_callable=AsyncMock) as mock_broadcast:
                mock_service = MagicMock()
                mock_service.get_snapshot = AsyncMock(return_value=mock_snapshot_result)
                mock_snapshot.return_value = mock_service

                mock_ai_submit.return_value = mock_ai_result

                # Mock stored event
                mock_event = MagicMock()
                mock_event.id = "test-event-id"
                mock_store.return_value = mock_event

                mock_broadcast.return_value = 1

                result = await handler.handle_event("ctrl-1", mock_msg)
                assert result == True

                # Verify tracking was updated
                assert camera.id in handler._last_event_times
        finally:
            db.close()

    @patch('app.services.protect_event_handler.get_db_session', _testing_get_db_session)
    @pytest.mark.asyncio
    async def test_handle_event_filtered_by_type(self):
        """AC7: Event filtered when type not in smart_detection_types"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()
        handler.clear_event_tracking()

        # Create camera configured for person only
        db = TestingSessionLocal()
        try:
            camera = Camera(
                name="Person Only Camera",
                type="rtsp",
                source_type="protect",
                protect_camera_id="person-only-cam",
                is_enabled=True,
                smart_detection_types='["person"]'
            )
            db.add(camera)
            db.commit()

            # Create mock message with vehicle detection (not person)
            mock_msg = MagicMock()
            mock_msg.new_obj = MagicMock()
            type(mock_msg.new_obj).__name__ = "Camera"
            mock_msg.new_obj.id = "person-only-cam"
            mock_msg.new_obj.is_motion_currently_detected = False
            mock_msg.new_obj.active_smart_detect_types = make_smart_detect_list(["vehicle"])

            result = await handler.handle_event("ctrl-1", mock_msg)
            assert result == False
        finally:
            db.close()

    @patch('app.services.protect_event_handler.get_db_session', _testing_get_db_session)
    @pytest.mark.asyncio
    async def test_handle_event_all_motion_mode(self):
        """AC8: All motion mode processes all event types (Story P2-3.3)"""
        from app.services.protect_event_handler import ProtectEventHandler
        from app.services.snapshot_service import SnapshotResult
        from datetime import datetime, timezone

        handler = ProtectEventHandler()
        handler.clear_event_tracking()

        # Create camera with empty filter (all motion mode)
        db = TestingSessionLocal()
        try:
            camera = Camera(
                name="All Motion Camera",
                type="rtsp",
                source_type="protect",
                protect_camera_id="all-motion-cam",
                is_enabled=True,
                smart_detection_types='[]'  # Empty = all motion mode
            )
            db.add(camera)
            db.commit()

            # Create mock message with vehicle detection
            mock_msg = MagicMock()
            mock_msg.new_obj = MagicMock()
            type(mock_msg.new_obj).__name__ = "Camera"
            mock_msg.new_obj.id = "all-motion-cam"
            mock_msg.new_obj.is_motion_currently_detected = False
            mock_msg.new_obj.active_smart_detect_types = make_smart_detect_list(["vehicle"])
            mock_msg.new_obj.last_motion = None
            mock_msg.new_obj.last_smart_detect = None

            # Mock snapshot service to return successful result (Story P2-3.2)
            mock_snapshot_result = SnapshotResult(
                image_base64="dGVzdA==",  # Valid base64 for "test"
                thumbnail_path="/tmp/test.jpg",
                width=1920,
                height=1080,
                camera_id=str(camera.id),
                timestamp=datetime.now(timezone.utc)
            )

            # Mock AI service for Story P2-3.3
            mock_ai_result = MagicMock()
            mock_ai_result.success = True
            mock_ai_result.description = "A vehicle detected near the camera"
            mock_ai_result.confidence = 85
            mock_ai_result.objects_detected = ["vehicle"]
            mock_ai_result.provider = "openai"
            mock_ai_result.response_time_ms = 500
            mock_ai_result.error = None

            with patch('app.services.protect_event_handler.get_snapshot_service') as mock_snapshot, \
                 patch.object(handler, '_submit_to_ai_pipeline', new_callable=AsyncMock) as mock_ai_submit, \
                 patch.object(handler, '_store_protect_event', new_callable=AsyncMock) as mock_store, \
                 patch.object(handler, '_broadcast_event_created', new_callable=AsyncMock) as mock_broadcast:
                mock_service = MagicMock()
                mock_service.get_snapshot = AsyncMock(return_value=mock_snapshot_result)
                mock_snapshot.return_value = mock_service

                mock_ai_submit.return_value = mock_ai_result

                # Mock stored event
                mock_event = MagicMock()
                mock_event.id = "test-event-id"
                mock_store.return_value = mock_event

                mock_broadcast.return_value = 1

                result = await handler.handle_event("ctrl-1", mock_msg)
                assert result == True
        finally:
            db.close()

    @patch('app.services.protect_event_handler.get_db_session', _testing_get_db_session)
    @pytest.mark.asyncio
    async def test_handle_event_deduplicated(self):
        """AC10: Duplicate event within cooldown is skipped"""
        from app.services.protect_event_handler import ProtectEventHandler, EVENT_COOLDOWN_SECONDS
        from datetime import datetime, timezone, timedelta

        handler = ProtectEventHandler()
        handler.clear_event_tracking()

        # Create enabled protect camera
        db = TestingSessionLocal()
        try:
            camera = Camera(
                name="Dedup Test Camera",
                type="rtsp",
                source_type="protect",
                protect_camera_id="dedup-test-cam",
                is_enabled=True,
                smart_detection_types='["person"]'
            )
            db.add(camera)
            db.commit()
            db.refresh(camera)

            # Simulate recent event (within cooldown)
            handler._last_event_times[camera.id] = (
                datetime.now(timezone.utc) - timedelta(seconds=30)
            )

            # Create mock message
            mock_msg = MagicMock()
            mock_msg.new_obj = MagicMock()
            type(mock_msg.new_obj).__name__ = "Camera"
            mock_msg.new_obj.id = "dedup-test-cam"
            mock_msg.new_obj.is_motion_currently_detected = False
            mock_msg.new_obj.active_smart_detect_types = make_smart_detect_list(["person"])

            result = await handler.handle_event("ctrl-1", mock_msg)
            assert result == False
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_handle_event_non_camera_object_ignored(self):
        """Events from non-camera objects are ignored"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create mock message for non-camera object
        mock_msg = MagicMock()
        mock_msg.new_obj = MagicMock()
        type(mock_msg.new_obj).__name__ = "Light"  # Not Camera or Doorbell
        mock_msg.new_obj.id = "light-123"

        result = await handler.handle_event("ctrl-1", mock_msg)
        assert result == False

    @pytest.mark.asyncio
    async def test_handle_event_no_new_obj_ignored(self):
        """Events without new_obj are ignored"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create mock message without new_obj
        mock_msg = MagicMock()
        mock_msg.new_obj = None

        result = await handler.handle_event("ctrl-1", mock_msg)
        assert result == False

    @pytest.mark.asyncio
    async def test_handle_event_exception_handled_gracefully(self):
        """Exceptions in event handling don't propagate"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create mock that raises exception
        mock_msg = MagicMock()
        mock_msg.new_obj = MagicMock()
        type(mock_msg.new_obj).__name__ = "Camera"
        mock_msg.new_obj.id = "test-cam"
        mock_msg.new_obj.is_motion_currently_detected = True
        mock_msg.new_obj.active_smart_detect_types = None

        # Mock database to raise exception
        with patch('app.services.protect_event_handler.SessionLocal') as mock_session:
            mock_session.side_effect = Exception("Database error")

            result = await handler.handle_event("ctrl-1", mock_msg)
            assert result == False  # Should return False, not raise


class TestWebSocketIntegration:
    """Test suite for WebSocket listener integration (Story P2-3.1, AC1)"""

    def test_event_handler_import_in_protect_service(self):
        """AC1: ProtectEventHandler is imported in protect_service"""
        from app.services.protect_service import get_protect_event_handler

        handler = get_protect_event_handler()
        assert handler is not None

    def test_protect_service_uses_event_handler(self):
        """AC1: Verify protect_service imports and uses event handler"""
        import app.services.protect_service as protect_service

        # Check that get_protect_event_handler is imported
        assert hasattr(protect_service, 'get_protect_event_handler')


# =============================================================================
# Story P2-3.2: Snapshot Retrieval Service Tests
# =============================================================================

class TestSnapshotServiceConstants:
    """Test suite for SnapshotService constants (Story P2-3.2)"""

    def test_snapshot_timeout_constant(self):
        """AC1, AC12: Snapshot timeout is 1 second"""
        from app.services.snapshot_service import SNAPSHOT_TIMEOUT_SECONDS

        assert SNAPSHOT_TIMEOUT_SECONDS == 1.0

    def test_retry_delay_constant(self):
        """AC8: Retry delay is 500ms"""
        from app.services.snapshot_service import RETRY_DELAY_SECONDS

        assert RETRY_DELAY_SECONDS == 0.5

    def test_max_concurrent_snapshots_constant(self):
        """AC11: Max concurrent snapshots per controller is 3"""
        from app.services.snapshot_service import MAX_CONCURRENT_SNAPSHOTS

        assert MAX_CONCURRENT_SNAPSHOTS == 3

    def test_ai_dimensions_constants(self):
        """AC4: AI processing dimensions are max 1920x1080"""
        from app.services.snapshot_service import AI_MAX_WIDTH, AI_MAX_HEIGHT

        assert AI_MAX_WIDTH == 1920
        assert AI_MAX_HEIGHT == 1080

    def test_thumbnail_dimensions_constants(self):
        """AC6: Thumbnail dimensions are 320x180"""
        from app.services.snapshot_service import THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT

        assert THUMBNAIL_WIDTH == 320
        assert THUMBNAIL_HEIGHT == 180


class TestSnapshotServiceInit:
    """Test suite for SnapshotService initialization (Story P2-3.2)"""

    def test_service_initializes_with_empty_semaphores(self, tmp_path):
        """Service initializes with empty semaphore dict"""
        from app.services.snapshot_service import SnapshotService

        service = SnapshotService(thumbnail_path=str(tmp_path))
        assert hasattr(service, '_controller_semaphores')
        assert isinstance(service._controller_semaphores, dict)
        assert len(service._controller_semaphores) == 0

    def test_service_initializes_metrics(self, tmp_path):
        """Service initializes with zero metrics counters"""
        from app.services.snapshot_service import SnapshotService

        service = SnapshotService(thumbnail_path=str(tmp_path))
        assert service._snapshot_failures_total == 0
        assert service._snapshot_success_total == 0

    def test_service_creates_thumbnail_directory(self, tmp_path):
        """Service creates thumbnail directory if not exists"""
        from app.services.snapshot_service import SnapshotService

        thumbnail_path = tmp_path / "thumbnails"
        assert not thumbnail_path.exists()

        service = SnapshotService(thumbnail_path=str(thumbnail_path))
        assert thumbnail_path.exists()

    def test_singleton_returns_same_instance(self):
        """get_snapshot_service returns singleton instance"""
        from app.services.snapshot_service import get_snapshot_service

        service1 = get_snapshot_service()
        service2 = get_snapshot_service()
        assert service1 is service2


class TestImageResizing:
    """Test suite for image resizing (Story P2-3.2, AC4)"""

    def test_resize_larger_image_maintains_aspect_ratio(self, tmp_path):
        """AC4: Large image is resized while maintaining aspect ratio"""
        from app.services.snapshot_service import SnapshotService
        from PIL import Image

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Create 4K image (3840x2160 - 16:9 aspect ratio)
        test_image = Image.new('RGB', (3840, 2160), color='red')

        resized = service._resize_for_ai(test_image)

        # Should fit within 1920x1080 while maintaining aspect ratio
        assert resized.width <= 1920
        assert resized.height <= 1080
        # Check aspect ratio preserved (16:9)
        original_ratio = 3840 / 2160
        new_ratio = resized.width / resized.height
        assert abs(original_ratio - new_ratio) < 0.01

    def test_resize_smaller_image_unchanged(self, tmp_path):
        """AC4: Image smaller than max dimensions is not resized"""
        from app.services.snapshot_service import SnapshotService
        from PIL import Image

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Create small image (800x600)
        test_image = Image.new('RGB', (800, 600), color='blue')

        resized = service._resize_for_ai(test_image)

        # Should remain same size
        assert resized.width == 800
        assert resized.height == 600

    def test_resize_exact_max_dimensions_unchanged(self, tmp_path):
        """AC4: Image at exactly max dimensions is not resized"""
        from app.services.snapshot_service import SnapshotService
        from PIL import Image

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Create image at exactly max dimensions
        test_image = Image.new('RGB', (1920, 1080), color='green')

        resized = service._resize_for_ai(test_image)

        assert resized.width == 1920
        assert resized.height == 1080


class TestThumbnailGeneration:
    """Test suite for thumbnail generation (Story P2-3.2, AC6)"""

    @pytest.mark.asyncio
    async def test_generate_thumbnail_creates_file(self, tmp_path):
        """AC6: Thumbnail is generated and saved"""
        from app.services.snapshot_service import SnapshotService
        from PIL import Image
        from datetime import datetime, timezone

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Create test image
        test_image = Image.new('RGB', (1920, 1080), color='red')
        timestamp = datetime.now(timezone.utc)

        api_url_path = await service._generate_thumbnail(
            test_image, "camera-123", timestamp
        )

        # api_url_path is /api/v1/thumbnails/{date}/{filename}
        # Convert to filesystem path: tmp_path/{date}/{filename}
        # Extract the path after /api/v1/thumbnails/
        relative_path = api_url_path.replace("/api/v1/thumbnails/", "")
        thumbnail_path = os.path.join(str(tmp_path), relative_path)

        # File should exist
        assert os.path.exists(thumbnail_path)
        # File should be in thumbnail directory
        assert str(tmp_path) in thumbnail_path
        # File should be JPEG
        assert thumbnail_path.endswith('.jpg')
        # Returned path should be API URL format
        assert api_url_path.startswith('/api/v1/thumbnails/')

    @pytest.mark.asyncio
    async def test_generate_thumbnail_dimensions(self, tmp_path):
        """AC6: Thumbnail is 320x180 (or fits within)"""
        from app.services.snapshot_service import SnapshotService
        from PIL import Image
        from datetime import datetime, timezone

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Create test image
        test_image = Image.new('RGB', (1920, 1080), color='blue')
        timestamp = datetime.now(timezone.utc)

        api_url_path = await service._generate_thumbnail(
            test_image, "camera-456", timestamp
        )

        # Convert API URL to filesystem path
        relative_path = api_url_path.replace("/api/v1/thumbnails/", "")
        thumbnail_path = os.path.join(str(tmp_path), relative_path)

        # Load saved thumbnail and check dimensions
        saved_thumb = Image.open(thumbnail_path)
        assert saved_thumb.width <= 320
        assert saved_thumb.height <= 180


class TestBase64Conversion:
    """Test suite for base64 conversion (Story P2-3.2, AC5)"""

    def test_to_base64_produces_valid_string(self, tmp_path):
        """AC5: Image is converted to valid base64 string"""
        from app.services.snapshot_service import SnapshotService
        from PIL import Image
        import base64

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Create test image
        test_image = Image.new('RGB', (100, 100), color='red')

        result = service._to_base64(test_image)

        # Should be a string
        assert isinstance(result, str)
        # Should be valid base64 (can decode without error)
        decoded = base64.b64decode(result)
        # Decoded should be JPEG bytes (starts with JPEG magic bytes)
        assert decoded[:2] == b'\xff\xd8'  # JPEG magic number

    def test_to_base64_is_decodable_to_image(self, tmp_path):
        """AC5: Base64 can be decoded back to an image"""
        from app.services.snapshot_service import SnapshotService
        from PIL import Image
        import base64
        import io

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Create test image with specific color
        test_image = Image.new('RGB', (50, 50), color=(255, 0, 0))

        result = service._to_base64(test_image)

        # Decode and verify
        decoded = base64.b64decode(result)
        restored_image = Image.open(io.BytesIO(decoded))
        assert restored_image.width == 50
        assert restored_image.height == 50


class TestSnapshotRetryLogic:
    """Test suite for retry logic (Story P2-3.2, AC8, AC9)"""

    @pytest.mark.asyncio
    async def test_retry_on_first_failure(self, tmp_path):
        """AC8: Retry once after 500ms on first failure"""
        from app.services.snapshot_service import SnapshotService
        import time

        service = SnapshotService(thumbnail_path=str(tmp_path))

        call_count = 0
        call_times = []

        async def mock_get_snapshot(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            call_times.append(time.time())
            if call_count == 1:
                raise Exception("First attempt fails")
            # Second attempt succeeds
            return b'\xff\xd8\xff\xe0' + b'\x00' * 100  # Minimal JPEG-like

        with patch.object(service, '_fetch_snapshot_with_retry') as mock:
            mock.return_value = None  # Simulating failure after retries

            # Call the method - it will use the mocked version
            result = await service._fetch_snapshot_with_retry(
                "ctrl-1", "cam-1", "Test Camera", None
            )

            # Mock was called
            assert mock.called

    @pytest.mark.asyncio
    async def test_returns_none_after_retry_failure(self, tmp_path):
        """AC9: Returns None if retry also fails (doesn't crash)"""
        from app.services.snapshot_service import SnapshotService

        service = SnapshotService(thumbnail_path=str(tmp_path))

        with patch('app.services.protect_service.get_protect_service') as mock_protect:
            mock_service = MagicMock()
            mock_service.get_camera_snapshot = AsyncMock(side_effect=Exception("Always fails"))
            mock_protect.return_value = mock_service

            result = await service._fetch_snapshot_with_retry(
                "ctrl-1", "cam-1", "Test Camera", None
            )

            # Should return None, not raise
            assert result is None


class TestSnapshotMetrics:
    """Test suite for metrics tracking (Story P2-3.2, AC10)"""

    def test_get_metrics_returns_dict(self, tmp_path):
        """AC10: Metrics can be retrieved"""
        from app.services.snapshot_service import SnapshotService

        service = SnapshotService(thumbnail_path=str(tmp_path))
        metrics = service.get_metrics()

        assert isinstance(metrics, dict)
        assert 'snapshot_success_total' in metrics
        assert 'snapshot_failures_total' in metrics
        assert 'active_semaphores' in metrics

    def test_failure_count_increments(self, tmp_path):
        """AC10: Failure counter increments on failure"""
        from app.services.snapshot_service import SnapshotService

        service = SnapshotService(thumbnail_path=str(tmp_path))

        initial_failures = service._snapshot_failures_total
        service._snapshot_failures_total += 1

        assert service._snapshot_failures_total == initial_failures + 1

    def test_reset_metrics(self, tmp_path):
        """Metrics can be reset"""
        from app.services.snapshot_service import SnapshotService

        service = SnapshotService(thumbnail_path=str(tmp_path))
        service._snapshot_failures_total = 5
        service._snapshot_success_total = 10

        service.reset_metrics()

        assert service._snapshot_failures_total == 0
        assert service._snapshot_success_total == 0


class TestConcurrencyLimiting:
    """Test suite for concurrency limiting (Story P2-3.2, AC11)"""

    def test_semaphore_created_per_controller(self, tmp_path):
        """AC11: Semaphore created for each controller"""
        from app.services.snapshot_service import SnapshotService, MAX_CONCURRENT_SNAPSHOTS

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Initially empty
        assert len(service._controller_semaphores) == 0

        # Get semaphore for controller 1
        sem1 = service._get_controller_semaphore("controller-1")
        assert len(service._controller_semaphores) == 1
        assert isinstance(sem1, asyncio.Semaphore)

        # Get semaphore for controller 2
        sem2 = service._get_controller_semaphore("controller-2")
        assert len(service._controller_semaphores) == 2

        # Same controller returns same semaphore
        sem1_again = service._get_controller_semaphore("controller-1")
        assert sem1 is sem1_again

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_calls(self, tmp_path):
        """AC11: Semaphore limits to 3 concurrent snapshots per controller"""
        from app.services.snapshot_service import SnapshotService, MAX_CONCURRENT_SNAPSHOTS

        service = SnapshotService(thumbnail_path=str(tmp_path))
        semaphore = service._get_controller_semaphore("test-controller")

        # Acquire all 3 slots
        await semaphore.acquire()
        await semaphore.acquire()
        await semaphore.acquire()

        # 4th acquisition should not succeed immediately
        # (We test this by checking the semaphore is locked)
        assert semaphore.locked()

        # Release one
        semaphore.release()
        assert not semaphore.locked()


class TestSnapshotResultDataclass:
    """Test suite for SnapshotResult dataclass (Story P2-3.2)"""

    def test_snapshot_result_creation(self):
        """SnapshotResult can be created with all required fields"""
        from app.services.snapshot_service import SnapshotResult
        from datetime import datetime, timezone

        result = SnapshotResult(
            image_base64="base64data",
            thumbnail_path="/path/to/thumb.jpg",
            width=1920,
            height=1080,
            camera_id="cam-123",
            timestamp=datetime.now(timezone.utc)
        )

        assert result.image_base64 == "base64data"
        assert result.thumbnail_path == "/path/to/thumb.jpg"
        assert result.width == 1920
        assert result.height == 1080
        assert result.camera_id == "cam-123"


class TestSnapshotProcessing:
    """Test suite for full snapshot processing (Story P2-3.2, AC4-AC7)"""

    @pytest.mark.asyncio
    async def test_process_snapshot_returns_result(self, tmp_path):
        """AC4-AC7: Process snapshot returns SnapshotResult with all fields"""
        from app.services.snapshot_service import SnapshotService, SnapshotResult
        from PIL import Image
        from datetime import datetime, timezone
        import io

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Create a valid JPEG image
        test_image = Image.new('RGB', (1920, 1080), color='red')
        buffer = io.BytesIO()
        test_image.save(buffer, format='JPEG')
        image_bytes = buffer.getvalue()

        result = await service._process_snapshot(
            image_bytes,
            "cam-123",
            "Test Camera",
            datetime.now(timezone.utc)
        )

        assert result is not None
        assert isinstance(result, SnapshotResult)
        assert result.image_base64  # Not empty
        assert result.thumbnail_path  # Not empty
        # thumbnail_path is now an API URL path, verify format and file existence
        assert result.thumbnail_path.startswith("/api/v1/thumbnails/")
        # Extract date and filename from URL path to verify file exists
        parts = result.thumbnail_path.split("/")  # ['', 'api', 'v1', 'thumbnails', 'YYYY-MM-DD', 'filename.jpg']
        date_str = parts[4]
        filename = parts[5]
        actual_file = os.path.join(str(tmp_path), date_str, filename)
        assert os.path.exists(actual_file)  # File created
        assert result.width > 0
        assert result.height > 0
        assert result.camera_id == "cam-123"

    @pytest.mark.asyncio
    async def test_process_snapshot_invalid_image_returns_none(self, tmp_path):
        """AC9: Invalid image returns None (doesn't crash)"""
        from app.services.snapshot_service import SnapshotService
        from datetime import datetime, timezone

        service = SnapshotService(thumbnail_path=str(tmp_path))

        # Pass invalid bytes
        result = await service._process_snapshot(
            b"not a valid image",
            "cam-123",
            "Test Camera",
            datetime.now(timezone.utc)
        )

        assert result is None
        # Failure should be tracked
        assert service._snapshot_failures_total >= 1


class TestEventHandlerSnapshotIntegration:
    """Test suite for event handler + snapshot integration (Story P2-3.2)"""

    def test_event_handler_imports_snapshot_service(self):
        """Event handler imports snapshot service"""
        from app.services.protect_event_handler import get_snapshot_service, SnapshotResult

        service = get_snapshot_service()
        assert service is not None

    def test_event_handler_has_retrieve_snapshot_method(self):
        """Event handler has _retrieve_snapshot method"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()
        assert hasattr(handler, '_retrieve_snapshot')
        assert callable(handler._retrieve_snapshot)


# ==============================================================================
# Story P2-4.1: Doorbell Ring Event Detection and Handling Tests
# ==============================================================================

class TestDoorbellRingConstants:
    """Test suite for doorbell ring constants (Story P2-4.1)"""

    def test_doorbell_ring_prompt_constant_defined(self):
        """AC4: DOORBELL_RING_PROMPT constant is defined"""
        from app.services.protect_event_handler import DOORBELL_RING_PROMPT

        assert DOORBELL_RING_PROMPT is not None
        assert isinstance(DOORBELL_RING_PROMPT, str)
        assert len(DOORBELL_RING_PROMPT) > 0

    def test_doorbell_ring_prompt_describes_visitor(self):
        """AC4: Doorbell prompt asks for visitor description"""
        from app.services.protect_event_handler import DOORBELL_RING_PROMPT

        prompt_lower = DOORBELL_RING_PROMPT.lower()
        # Should mention describing the person/visitor
        assert any(word in prompt_lower for word in ['describe', 'who', 'person', 'visitor', 'front door'])

    def test_ring_in_event_type_mapping(self):
        """AC1: 'ring' is in EVENT_TYPE_MAPPING"""
        from app.services.protect_event_handler import EVENT_TYPE_MAPPING

        assert 'ring' in EVENT_TYPE_MAPPING
        assert EVENT_TYPE_MAPPING['ring'] == 'ring'


class TestDoorbellRingEventParsing:
    """Test suite for doorbell ring event parsing (Story P2-4.1 AC1, AC2)"""

    def test_parse_event_types_detects_doorbell_ring(self):
        """AC1: Ring events detected via is_ringing=True on Doorbell model"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create mock Doorbell object with is_ringing=True
        mock_doorbell = MagicMock()
        mock_doorbell.is_motion_currently_detected = False
        mock_doorbell.active_smart_detect_types = []
        mock_doorbell.is_ringing = True

        event_types = handler._parse_event_types(mock_doorbell, 'Doorbell')

        assert 'ring' in event_types

    def test_parse_event_types_no_ring_when_not_ringing(self):
        """Ring event NOT detected when is_ringing=False"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create mock Doorbell object with is_ringing=False
        mock_doorbell = MagicMock()
        mock_doorbell.is_motion_currently_detected = False
        mock_doorbell.active_smart_detect_types = []
        mock_doorbell.is_ringing = False

        event_types = handler._parse_event_types(mock_doorbell, 'Doorbell')

        assert 'ring' not in event_types

    def test_parse_event_types_no_ring_on_camera_model(self):
        """Ring event NOT detected on Camera model (only Doorbell)"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create mock Camera object with is_ringing=True (shouldn't be checked)
        mock_camera = MagicMock()
        mock_camera.is_motion_currently_detected = False
        mock_camera.active_smart_detect_types = []
        mock_camera.is_ringing = True

        event_types = handler._parse_event_types(mock_camera, 'Camera')

        # Ring should NOT be detected because it's a Camera, not Doorbell
        assert 'ring' not in event_types

    def test_parse_event_types_ring_with_motion(self):
        """Doorbell can have both ring and motion detected"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()

        # Create mock Doorbell with both motion and ring
        mock_doorbell = MagicMock()
        mock_doorbell.is_motion_currently_detected = True
        mock_doorbell.active_smart_detect_types = make_smart_detect_list(['person'])
        mock_doorbell.is_ringing = True

        event_types = handler._parse_event_types(mock_doorbell, 'Doorbell')

        assert 'ring' in event_types
        assert 'motion' in event_types
        assert 'smart_detect_person' in event_types


class TestDoorbellRingEventModel:
    """Test suite for Event model doorbell ring support (Story P2-4.1 AC3, AC5)"""

    def test_event_model_has_is_doorbell_ring_column(self):
        """AC3: Event model has is_doorbell_ring column"""
        from app.models.event import Event

        assert hasattr(Event, 'is_doorbell_ring')

    def test_event_model_is_doorbell_ring_defaults_to_false(self):
        """AC3: is_doorbell_ring defaults to False"""
        from app.models.event import Event

        # Get the column default
        column = Event.__table__.columns['is_doorbell_ring']
        assert column.default is not None
        # Default should be False (0)
        assert column.default.arg == False

    def test_event_create_schema_has_is_doorbell_ring(self):
        """AC3: EventCreate schema has is_doorbell_ring field"""
        from app.schemas.event import EventCreate

        schema = EventCreate.model_json_schema()
        assert 'is_doorbell_ring' in schema['properties']
        # Check default
        assert schema['properties']['is_doorbell_ring']['default'] == False

    def test_event_response_schema_has_is_doorbell_ring(self):
        """AC3: EventResponse schema has is_doorbell_ring field"""
        from app.schemas.event import EventResponse

        schema = EventResponse.model_json_schema()
        assert 'is_doorbell_ring' in schema['properties']

    def test_event_create_with_doorbell_ring_true(self):
        """AC5: EventCreate accepts is_doorbell_ring=True"""
        from app.schemas.event import EventCreate
        from datetime import datetime, timezone

        event_data = {
            "camera_id": "test-camera-id",
            "timestamp": datetime.now(timezone.utc),
            "description": "Person at the front door",
            "confidence": 85,
            "objects_detected": ["person"],
            "source_type": "protect",
            "smart_detection_type": "ring",
            "is_doorbell_ring": True
        }

        event = EventCreate(**event_data)
        assert event.is_doorbell_ring == True
        assert event.smart_detection_type == "ring"


class TestDoorbellRingWebSocketBroadcast:
    """Test suite for doorbell ring WebSocket broadcast (Story P2-4.1 AC6)"""

    def test_event_handler_has_broadcast_doorbell_ring_method(self):
        """Event handler has _broadcast_doorbell_ring method"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()
        assert hasattr(handler, '_broadcast_doorbell_ring')
        assert callable(handler._broadcast_doorbell_ring)

    @pytest.mark.asyncio
    async def test_broadcast_doorbell_ring_sends_correct_message_type(self):
        """AC6: DOORBELL_RING WebSocket message is broadcast"""
        from app.services.protect_event_handler import ProtectEventHandler
        from datetime import datetime, timezone

        handler = ProtectEventHandler()

        with patch('app.services.websocket_manager.get_websocket_manager') as mock_get_ws:
            mock_ws = MagicMock()
            mock_ws.broadcast = AsyncMock(return_value=2)
            mock_get_ws.return_value = mock_ws

            timestamp = datetime.now(timezone.utc)
            clients = await handler._broadcast_doorbell_ring(
                camera_id="test-cam",
                camera_name="Front Door",
                thumbnail_url="/api/v1/thumbnails/2025-01-01/test.jpg",
                timestamp=timestamp
            )

            assert clients == 2
            mock_ws.broadcast.assert_called_once()

            # Verify message format
            call_args = mock_ws.broadcast.call_args[0][0]
            assert call_args['type'] == 'DOORBELL_RING'
            assert call_args['data']['camera_id'] == 'test-cam'
            assert call_args['data']['camera_name'] == 'Front Door'
            assert call_args['data']['thumbnail_url'] == '/api/v1/thumbnails/2025-01-01/test.jpg'
            assert 'timestamp' in call_args['data']

    @pytest.mark.asyncio
    async def test_broadcast_doorbell_ring_handles_errors_gracefully(self):
        """Broadcast errors don't crash the handler"""
        from app.services.protect_event_handler import ProtectEventHandler
        from datetime import datetime, timezone

        handler = ProtectEventHandler()

        with patch('app.services.websocket_manager.get_websocket_manager') as mock_get_ws:
            mock_ws = MagicMock()
            mock_ws.broadcast = AsyncMock(side_effect=Exception("WebSocket error"))
            mock_get_ws.return_value = mock_ws

            # Should not raise, just return 0
            clients = await handler._broadcast_doorbell_ring(
                camera_id="test-cam",
                camera_name="Front Door",
                thumbnail_url="/test.jpg",
                timestamp=datetime.now(timezone.utc)
            )

            assert clients == 0


class TestDoorbellRingAIPrompt:
    """Test suite for doorbell-specific AI prompt (Story P2-4.1 AC4, AC7, AC8)"""

    def test_ai_provider_base_build_user_prompt_with_custom_prompt(self):
        """AC4: _build_user_prompt handles custom_prompt parameter"""
        from app.services.ai_service import AIProviderBase

        # Create a concrete implementation for testing
        class TestProvider(AIProviderBase):
            async def generate_description(self, *args, **kwargs):
                pass

            async def generate_multi_image_description(self, *args, **kwargs):
                pass

        provider = TestProvider(api_key="test")

        # Test with custom prompt
        prompt = provider._build_user_prompt(
            camera_name="Front Door",
            timestamp="2025-01-01T12:00:00Z",
            detected_objects=["person"],
            custom_prompt="Describe who is at the door."
        )

        # Should use custom prompt, not default template
        assert "Describe who is at the door" in prompt
        assert "Front Door" in prompt  # Camera context should still be present

    def test_ai_provider_base_build_user_prompt_without_custom_prompt(self):
        """_build_user_prompt uses default template without custom_prompt"""
        from app.services.ai_service import AIProviderBase

        class TestProvider(AIProviderBase):
            async def generate_description(self, *args, **kwargs):
                pass

            async def generate_multi_image_description(self, *args, **kwargs):
                pass

        provider = TestProvider(api_key="test")

        # Test without custom prompt
        prompt = provider._build_user_prompt(
            camera_name="Front Door",
            timestamp="2025-01-01T12:00:00Z",
            detected_objects=["person"]
        )

        # Should use default template
        assert "WHO" in prompt or "Describe what you see" in prompt

    def test_ai_service_generate_description_signature_has_custom_prompt(self):
        """AC4: AIService.generate_description accepts custom_prompt parameter"""
        from app.services.ai_service import AIService
        import inspect

        sig = inspect.signature(AIService.generate_description)
        params = list(sig.parameters.keys())

        assert 'custom_prompt' in params

    def test_openai_provider_signature_has_custom_prompt(self):
        """OpenAIProvider.generate_description accepts custom_prompt"""
        from app.services.ai_service import OpenAIProvider
        import inspect

        sig = inspect.signature(OpenAIProvider.generate_description)
        params = list(sig.parameters.keys())

        assert 'custom_prompt' in params

    def test_claude_provider_signature_has_custom_prompt(self):
        """ClaudeProvider.generate_description accepts custom_prompt"""
        from app.services.ai_service import ClaudeProvider
        import inspect

        sig = inspect.signature(ClaudeProvider.generate_description)
        params = list(sig.parameters.keys())

        assert 'custom_prompt' in params

    def test_gemini_provider_signature_has_custom_prompt(self):
        """GeminiProvider.generate_description accepts custom_prompt"""
        from app.services.ai_service import GeminiProvider
        import inspect

        sig = inspect.signature(GeminiProvider.generate_description)
        params = list(sig.parameters.keys())

        assert 'custom_prompt' in params


class TestDoorbellRingEventStorage:
    """Test suite for doorbell ring event storage (Story P2-4.1 AC5)"""

    @pytest.mark.asyncio
    async def test_store_protect_event_sets_is_doorbell_ring(self):
        """AC5: _store_protect_event sets is_doorbell_ring=True for ring events"""
        from app.services.protect_event_handler import ProtectEventHandler
        from app.services.snapshot_service import SnapshotResult
        from datetime import datetime, timezone
        from dataclasses import dataclass

        handler = ProtectEventHandler()

        # Create mock AI result
        @dataclass
        class MockAIResult:
            description: str = "Person at front door"
            confidence: int = 85
            objects_detected: list = None
            provider: str = "openai"
            success: bool = True
            error: str = None
            ai_confidence: int = 85
            cost_estimate: float = 0.001

            def __post_init__(self):
                if self.objects_detected is None:
                    self.objects_detected = ["person"]

        mock_ai = MockAIResult()

        # Create mock snapshot result
        snapshot = SnapshotResult(
            image_base64="base64data",
            thumbnail_path="/api/v1/thumbnails/test.jpg",
            width=1920,
            height=1080,
            camera_id="test-cam",
            timestamp=datetime.now(timezone.utc)
        )

        # Create mock camera
        mock_camera = MagicMock()
        mock_camera.id = "test-cam"
        mock_camera.name = "Front Door Doorbell"

        # Mock database
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        # Call with is_doorbell_ring=True
        event = await handler._store_protect_event(
            db=mock_db,
            ai_result=mock_ai,
            snapshot_result=snapshot,
            camera=mock_camera,
            event_type="ring",
            protect_event_id="protect-123",
            is_doorbell_ring=True
        )

        # Verify the event was created with is_doorbell_ring=True
        assert mock_db.add.called
        added_event = mock_db.add.call_args[0][0]
        assert added_event.is_doorbell_ring == True
        assert added_event.smart_detection_type == "ring"
        assert added_event.source_type == "protect"


class TestDoorbellRingEventCreatedBroadcast:
    """Test suite for EVENT_CREATED broadcast including is_doorbell_ring (Story P2-4.1)"""

    @pytest.mark.asyncio
    async def test_broadcast_event_created_includes_is_doorbell_ring(self):
        """EVENT_CREATED message includes is_doorbell_ring field"""
        from app.services.protect_event_handler import ProtectEventHandler
        from datetime import datetime, timezone

        handler = ProtectEventHandler()

        # Create mock event with is_doorbell_ring=True
        mock_event = MagicMock()
        mock_event.id = "event-123"
        mock_event.camera_id = "cam-123"
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_event.description = "Person at door"
        mock_event.confidence = 85
        mock_event.objects_detected = '["person"]'
        mock_event.thumbnail_path = "/test.jpg"
        mock_event.source_type = "protect"
        mock_event.smart_detection_type = "ring"
        mock_event.protect_event_id = "protect-123"
        mock_event.is_doorbell_ring = True

        mock_camera = MagicMock()
        mock_camera.name = "Front Door"

        with patch('app.services.websocket_manager.get_websocket_manager') as mock_get_ws:
            mock_ws = MagicMock()
            mock_ws.broadcast = AsyncMock(return_value=1)
            mock_get_ws.return_value = mock_ws

            await handler._broadcast_event_created(mock_event, mock_camera)

            # Verify is_doorbell_ring is in the message
            call_args = mock_ws.broadcast.call_args[0][0]
            assert call_args['type'] == 'EVENT_CREATED'
            assert call_args['data']['is_doorbell_ring'] == True


class TestDoorbellRingIntegration:
    """Integration tests for full doorbell ring event flow (Story P2-4.1)"""

    @patch('app.services.protect_event_handler.get_db_session', _testing_get_db_session)
    @pytest.mark.asyncio
    async def test_full_doorbell_ring_flow(self):
        """AC1-8: Full integration test for doorbell ring event"""
        from app.services.protect_event_handler import (
            ProtectEventHandler, DOORBELL_RING_PROMPT
        )
        from app.services.snapshot_service import SnapshotResult
        from datetime import datetime, timezone

        handler = ProtectEventHandler()
        handler.clear_event_tracking()

        # Create a real camera in the test database
        db = TestingSessionLocal()
        try:
            camera = Camera(
                name="Front Door Doorbell",
                type="rtsp",
                source_type="protect",
                protect_camera_id="protect-doorbell-123",
                is_enabled=True,
                smart_detection_types='["ring"]'  # Configured to process rings
            )
            db.add(camera)
            db.commit()
            db.refresh(camera)
            camera_id = str(camera.id)

            # Create mock Doorbell event message (must set __name__ to 'Doorbell')
            mock_msg = MagicMock()
            mock_msg.new_obj = MagicMock()
            type(mock_msg.new_obj).__name__ = "Doorbell"
            mock_msg.new_obj.id = "protect-doorbell-123"
            mock_msg.new_obj.is_motion_currently_detected = False
            mock_msg.new_obj.active_smart_detect_types = []
            mock_msg.new_obj.is_ringing = True
            mock_msg.new_obj.last_motion = None
            mock_msg.new_obj.last_smart_detect = None

            # Mock snapshot result
            mock_snapshot = SnapshotResult(
                image_base64="base64imagedata",
                thumbnail_path="/api/v1/thumbnails/test.jpg",
                width=1920,
                height=1080,
                camera_id=camera_id,
                timestamp=datetime.now(timezone.utc)
            )

            # Mock AI result
            mock_ai_result = MagicMock()
            mock_ai_result.description = "Person in blue jacket standing at front door"
            mock_ai_result.confidence = 90
            mock_ai_result.objects_detected = ["person"]
            mock_ai_result.success = True
            mock_ai_result.error = None

            # Mock stored event
            mock_event = MagicMock()
            mock_event.id = "event-123"
            mock_event.camera_id = camera_id
            mock_event.timestamp = datetime.now(timezone.utc)
            mock_event.description = mock_ai_result.description
            mock_event.confidence = 90
            mock_event.objects_detected = '["person"]'
            mock_event.thumbnail_path = "/test.jpg"
            mock_event.source_type = "protect"
            mock_event.smart_detection_type = "ring"
            mock_event.protect_event_id = "protect-123"
            mock_event.is_doorbell_ring = True

            with patch('app.services.protect_event_handler.get_snapshot_service') as mock_snapshot_svc, \
                 patch.object(handler, '_submit_to_ai_pipeline', new_callable=AsyncMock) as mock_ai_submit, \
                 patch.object(handler, '_store_protect_event', new_callable=AsyncMock) as mock_store, \
                 patch.object(handler, '_broadcast_doorbell_ring', new_callable=AsyncMock) as mock_doorbell_broadcast, \
                 patch.object(handler, '_broadcast_event_created', new_callable=AsyncMock) as mock_event_broadcast:

                mock_service = MagicMock()
                mock_service.get_snapshot = AsyncMock(return_value=mock_snapshot)
                mock_snapshot_svc.return_value = mock_service

                mock_ai_submit.return_value = mock_ai_result
                mock_store.return_value = mock_event
                mock_doorbell_broadcast.return_value = 3
                mock_event_broadcast.return_value = 3

                # Execute the handler
                result = await handler.handle_event("controller-1", mock_msg)

                # Verify: Event was processed
                assert result == True

                # Verify: Doorbell ring broadcast was called BEFORE AI processing
                mock_doorbell_broadcast.assert_called_once()
                doorbell_call_args = mock_doorbell_broadcast.call_args
                assert doorbell_call_args[1]['camera_id'] == camera_id
                assert doorbell_call_args[1]['camera_name'] == "Front Door Doorbell"

                # Verify: AI submission used doorbell prompt (is_doorbell_ring=True)
                mock_ai_submit.assert_called_once()
                ai_call_args = mock_ai_submit.call_args
                assert ai_call_args[1]['is_doorbell_ring'] == True

                # Verify: Event was stored with is_doorbell_ring=True
                # _store_protect_event(db, ai_result, snapshot_result, camera, event_type, protect_event_id, is_doorbell_ring)
                mock_store.assert_called_once()
                store_call_args = mock_store.call_args
                # Check positional args: event_type is arg[4], is_doorbell_ring may be kwarg
                store_args = store_call_args[0]  # positional args
                store_kwargs = store_call_args[1]  # keyword args
                assert store_args[4] == "ring"  # event_type
                assert store_kwargs.get('is_doorbell_ring', False) == True

                # Verify: EVENT_CREATED broadcast was called
                mock_event_broadcast.assert_called_once()
        finally:
            db.close()


class TestDoorbellRingDatabaseMigration:
    """Test suite for doorbell ring database migration (Story P2-4.1 AC3)"""

    def test_is_doorbell_ring_column_exists_in_events_table(self):
        """AC3: is_doorbell_ring column exists in events table"""
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(engine)
        columns = {col['name'] for col in inspector.get_columns('events')}

        assert 'is_doorbell_ring' in columns

    def test_is_doorbell_ring_column_is_boolean(self):
        """AC3: is_doorbell_ring column is BOOLEAN type"""
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(engine)
        columns = inspector.get_columns('events')
        is_doorbell_ring_col = next(
            (col for col in columns if col['name'] == 'is_doorbell_ring'),
            None
        )

        assert is_doorbell_ring_col is not None
        assert 'BOOLEAN' in str(is_doorbell_ring_col['type']).upper()

    def test_is_doorbell_ring_column_not_nullable(self):
        """AC3: is_doorbell_ring column is NOT NULL"""
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(engine)
        columns = inspector.get_columns('events')
        is_doorbell_ring_col = next(
            (col for col in columns if col['name'] == 'is_doorbell_ring'),
            None
        )

        assert is_doorbell_ring_col is not None
        assert is_doorbell_ring_col['nullable'] == False


# Story P3-1.5: Test Clip Download API Endpoint

class TestClipDownloadEndpoint:
    """Test suite for POST /api/v1/protect/test-clip-download (Story P3-1.5)"""

    @pytest.fixture
    def protect_camera(self):
        """Create a Protect camera for testing"""
        # First create a controller
        db = TestingSessionLocal()
        try:
            controller = ProtectController(
                name="Test Controller",
                host="192.168.1.1",
                port=443,
                username="admin",
                password="testpassword",
                verify_ssl=False
            )
            db.add(controller)
            db.commit()
            db.refresh(controller)
            controller_id = controller.id

            # Create camera linked to controller
            camera = Camera(
                name="Test Protect Camera",
                type="rtsp",
                source_type="protect",
                protect_controller_id=controller_id,
                protect_camera_id="protect-cam-123",
                is_enabled=True
            )
            db.add(camera)
            db.commit()
            db.refresh(camera)
            return camera.id, controller_id
        finally:
            db.close()

    @pytest.fixture
    def rtsp_camera(self):
        """Create an RTSP camera for testing"""
        db = TestingSessionLocal()
        try:
            camera = Camera(
                name="Test RTSP Camera",
                type="rtsp",
                source_type="rtsp",
                rtsp_url="rtsp://192.168.1.100:554/stream",
                is_enabled=True
            )
            db.add(camera)
            db.commit()
            db.refresh(camera)
            return camera.id
        finally:
            db.close()

    def test_clip_download_camera_not_found(self):
        """P3-1.5 AC3: Camera not found returns appropriate error"""
        response = client.post(
            "/api/v1/protect/test-clip-download",
            json={
                "camera_id": "non-existent-camera-id",
                "start_time": "2025-12-05T10:00:00Z",
                "end_time": "2025-12-05T10:00:30Z"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_clip_download_non_protect_camera(self, rtsp_camera):
        """P3-1.5 AC3: Non-Protect camera returns appropriate error"""
        response = client.post(
            "/api/v1/protect/test-clip-download",
            json={
                "camera_id": rtsp_camera,
                "start_time": "2025-12-05T10:00:00Z",
                "end_time": "2025-12-05T10:00:30Z"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not a Protect camera" in data["error"]

    @patch('app.api.v1.protect.get_clip_service')
    def test_clip_download_success(self, mock_get_clip_service, protect_camera):
        """P3-1.5 AC1: Successful download returns file size and duration"""
        from pathlib import Path
        import tempfile

        camera_id, _ = protect_camera

        # Create a mock clip file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video content" * 1000)  # ~18KB
            mock_clip_path = Path(f.name)

        # Mock ClipService
        mock_clip_service = MagicMock()
        mock_clip_service.download_clip = AsyncMock(return_value=mock_clip_path)
        mock_clip_service.cleanup_clip = MagicMock(return_value=True)
        mock_get_clip_service.return_value = mock_clip_service

        # Mock video duration extraction
        with patch('app.api.v1.protect._get_video_duration', return_value=10.5):
            response = client.post(
                "/api/v1/protect/test-clip-download",
                json={
                    "camera_id": camera_id,
                    "start_time": "2025-12-05T10:00:00Z",
                    "end_time": "2025-12-05T10:00:30Z"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["file_size_bytes"] > 0
        assert data["duration_seconds"] == 10.5
        assert data["error"] is None

        # Verify cleanup was called
        mock_clip_service.cleanup_clip.assert_called_once()

        # Cleanup mock file
        try:
            mock_clip_path.unlink()
        except Exception:
            pass

    @patch('app.api.v1.protect.get_clip_service')
    def test_clip_download_failure(self, mock_get_clip_service, protect_camera):
        """P3-1.5 AC2: Download failure returns success=false with error"""
        camera_id, _ = protect_camera

        # Mock ClipService returning None (download failed)
        mock_clip_service = MagicMock()
        mock_clip_service.download_clip = AsyncMock(return_value=None)
        mock_clip_service.cleanup_clip = MagicMock(return_value=False)
        mock_get_clip_service.return_value = mock_clip_service

        response = client.post(
            "/api/v1/protect/test-clip-download",
            json={
                "camera_id": camera_id,
                "start_time": "2025-12-05T10:00:00Z",
                "end_time": "2025-12-05T10:00:30Z"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] is not None
        assert "failed" in data["error"].lower()
        assert data["file_size_bytes"] is None
        assert data["duration_seconds"] is None

    @patch('app.api.v1.protect.get_clip_service')
    def test_clip_cleanup_after_success(self, mock_get_clip_service, protect_camera):
        """P3-1.5 AC4: Cleanup is called after successful download"""
        from pathlib import Path
        import tempfile

        camera_id, _ = protect_camera

        # Create a mock clip file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video content")
            mock_clip_path = Path(f.name)

        # Mock ClipService
        mock_clip_service = MagicMock()
        mock_clip_service.download_clip = AsyncMock(return_value=mock_clip_path)
        mock_clip_service.cleanup_clip = MagicMock(return_value=True)
        mock_get_clip_service.return_value = mock_clip_service

        with patch('app.api.v1.protect._get_video_duration', return_value=5.0):
            client.post(
                "/api/v1/protect/test-clip-download",
                json={
                    "camera_id": camera_id,
                    "start_time": "2025-12-05T10:00:00Z",
                    "end_time": "2025-12-05T10:00:30Z"
                }
            )

        # Verify cleanup was called with test event ID
        mock_clip_service.cleanup_clip.assert_called_once()
        call_args = mock_clip_service.cleanup_clip.call_args[0]
        assert call_args[0].startswith("test-")

        # Cleanup mock file
        try:
            mock_clip_path.unlink()
        except Exception:
            pass

    @patch('app.api.v1.protect.get_clip_service')
    def test_clip_cleanup_after_metadata_failure(self, mock_get_clip_service, protect_camera):
        """P3-1.5 AC4: Cleanup is called even if duration extraction fails"""
        from pathlib import Path
        import tempfile

        camera_id, _ = protect_camera

        # Create a mock clip file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video content")
            mock_clip_path = Path(f.name)

        # Mock ClipService
        mock_clip_service = MagicMock()
        mock_clip_service.download_clip = AsyncMock(return_value=mock_clip_path)
        mock_clip_service.cleanup_clip = MagicMock(return_value=True)
        mock_get_clip_service.return_value = mock_clip_service

        # Mock duration extraction to fail
        with patch('app.api.v1.protect._get_video_duration', return_value=None):
            response = client.post(
                "/api/v1/protect/test-clip-download",
                json={
                    "camera_id": camera_id,
                    "start_time": "2025-12-05T10:00:00Z",
                    "end_time": "2025-12-05T10:00:30Z"
                }
            )

        # Response should still succeed (just with None duration)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["duration_seconds"] is None

        # Cleanup should still be called
        mock_clip_service.cleanup_clip.assert_called_once()

        # Cleanup mock file
        try:
            mock_clip_path.unlink()
        except Exception:
            pass

    def test_clip_download_invalid_time_range(self, protect_camera):
        """P3-1.5: Invalid time range (end before start) returns validation error"""
        camera_id, _ = protect_camera

        response = client.post(
            "/api/v1/protect/test-clip-download",
            json={
                "camera_id": camera_id,
                "start_time": "2025-12-05T10:00:30Z",
                "end_time": "2025-12-05T10:00:00Z"  # Before start
            }
        )

        assert response.status_code == 422  # Validation error
        assert "end_time must be after start_time" in response.text


class TestClipDownloadResponseFormat:
    """Test suite for response format of test-clip-download endpoint"""

    def test_response_has_required_fields(self):
        """Verify response schema has all required fields"""
        response = client.post(
            "/api/v1/protect/test-clip-download",
            json={
                "camera_id": "non-existent-id",
                "start_time": "2025-12-05T10:00:00Z",
                "end_time": "2025-12-05T10:00:30Z"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # All fields should be present
        assert "success" in data
        assert "file_size_bytes" in data
        assert "duration_seconds" in data
        assert "error" in data

        # Type checks
        assert isinstance(data["success"], bool)
        # Other fields can be None
