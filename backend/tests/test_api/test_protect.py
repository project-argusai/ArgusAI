"""Integration tests for UniFi Protect controller API endpoints (Story P2-1.1)"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
import tempfile
import os

from main import app
from app.core.database import Base, get_db
from app.models.protect_controller import ProtectController
from app.models.camera import Camera


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
