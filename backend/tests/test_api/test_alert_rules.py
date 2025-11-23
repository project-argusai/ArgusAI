"""Tests for Alert Rules API endpoints (Epic 5)"""
import pytest
import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.database import Base, get_db

# Import ALL models to ensure they're registered with Base.metadata
from app.models.camera import Camera
from app.models.motion_event import MotionEvent
from app.models.system_setting import SystemSetting
from app.models.ai_usage import AIUsage
from app.models.event import Event
from app.models.alert_rule import AlertRule, WebhookLog


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def client():
    """Create test client with fresh database"""
    Base.metadata.create_all(bind=engine)
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_rule_data():
    """Sample alert rule creation data"""
    return {
        "name": "Test Package Alert",
        "is_enabled": True,
        "conditions": {
            "object_types": ["person", "package"],
            "cameras": [],
            "min_confidence": 75
        },
        "actions": {
            "dashboard_notification": True,
            "webhook": {
                "url": "https://example.com/webhook",
                "headers": {"Authorization": "Bearer test"}
            }
        },
        "cooldown_minutes": 10
    }


class TestCreateAlertRule:
    """Tests for POST /api/v1/alert-rules"""

    def test_create_rule_success(self, client, sample_rule_data):
        """Test successful rule creation"""
        response = client.post("/api/v1/alert-rules", json=sample_rule_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_rule_data["name"]
        assert data["is_enabled"] is True
        assert data["cooldown_minutes"] == 10
        assert "id" in data
        assert "created_at" in data

    def test_create_rule_minimal(self, client):
        """Test creating rule with minimal required fields"""
        minimal_data = {"name": "Minimal Rule"}

        response = client.post("/api/v1/alert-rules", json=minimal_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Rule"
        assert data["is_enabled"] is True  # Default
        assert data["cooldown_minutes"] == 5  # Default

    def test_create_rule_validation_error(self, client):
        """Test validation error for invalid data"""
        invalid_data = {
            "name": "",  # Empty name should fail
            "cooldown_minutes": 9999  # Over max
        }

        response = client.post("/api/v1/alert-rules", json=invalid_data)

        assert response.status_code == 422  # Validation error


class TestListAlertRules:
    """Tests for GET /api/v1/alert-rules"""

    def test_list_empty(self, client):
        """Test listing when no rules exist"""
        response = client.get("/api/v1/alert-rules")

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total_count"] == 0

    def test_list_with_rules(self, client, sample_rule_data):
        """Test listing multiple rules"""
        # Create two rules
        client.post("/api/v1/alert-rules", json=sample_rule_data)
        sample_rule_data["name"] = "Second Rule"
        client.post("/api/v1/alert-rules", json=sample_rule_data)

        response = client.get("/api/v1/alert-rules")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert len(data["data"]) == 2

    def test_list_filter_enabled(self, client, sample_rule_data):
        """Test filtering by enabled status"""
        # Create enabled and disabled rules
        client.post("/api/v1/alert-rules", json=sample_rule_data)
        sample_rule_data["name"] = "Disabled Rule"
        sample_rule_data["is_enabled"] = False
        client.post("/api/v1/alert-rules", json=sample_rule_data)

        # Filter by enabled
        response = client.get("/api/v1/alert-rules?is_enabled=true")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert data["data"][0]["is_enabled"] is True


class TestGetAlertRule:
    """Tests for GET /api/v1/alert-rules/{id}"""

    def test_get_rule_success(self, client, sample_rule_data):
        """Test getting existing rule"""
        create_response = client.post("/api/v1/alert-rules", json=sample_rule_data)
        rule_id = create_response.json()["id"]

        response = client.get(f"/api/v1/alert-rules/{rule_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == rule_id
        assert data["name"] == sample_rule_data["name"]

    def test_get_rule_not_found(self, client):
        """Test 404 for non-existent rule"""
        response = client.get("/api/v1/alert-rules/non-existent-id")

        assert response.status_code == 404


class TestUpdateAlertRule:
    """Tests for PUT /api/v1/alert-rules/{id}"""

    def test_update_rule_success(self, client, sample_rule_data):
        """Test updating rule fields"""
        create_response = client.post("/api/v1/alert-rules", json=sample_rule_data)
        rule_id = create_response.json()["id"]

        update_data = {
            "name": "Updated Rule Name",
            "is_enabled": False,
            "cooldown_minutes": 30
        }

        response = client.put(f"/api/v1/alert-rules/{rule_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Rule Name"
        assert data["is_enabled"] is False
        assert data["cooldown_minutes"] == 30

    def test_update_partial(self, client, sample_rule_data):
        """Test partial update (only some fields)"""
        create_response = client.post("/api/v1/alert-rules", json=sample_rule_data)
        rule_id = create_response.json()["id"]

        # Only update name
        response = client.put(f"/api/v1/alert-rules/{rule_id}", json={"name": "New Name"})

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["cooldown_minutes"] == 10  # Unchanged

    def test_update_not_found(self, client):
        """Test 404 for updating non-existent rule"""
        response = client.put("/api/v1/alert-rules/non-existent-id", json={"name": "Test"})

        assert response.status_code == 404


class TestDeleteAlertRule:
    """Tests for DELETE /api/v1/alert-rules/{id}"""

    def test_delete_rule_success(self, client, sample_rule_data):
        """Test deleting existing rule"""
        create_response = client.post("/api/v1/alert-rules", json=sample_rule_data)
        rule_id = create_response.json()["id"]

        response = client.delete(f"/api/v1/alert-rules/{rule_id}")

        assert response.status_code == 204

        # Verify deleted
        get_response = client.get(f"/api/v1/alert-rules/{rule_id}")
        assert get_response.status_code == 404

    def test_delete_not_found(self, client):
        """Test 404 for deleting non-existent rule"""
        response = client.delete("/api/v1/alert-rules/non-existent-id")

        assert response.status_code == 404


class TestTestAlertRule:
    """Tests for POST /api/v1/alert-rules/{id}/test"""

    def test_test_rule_no_events(self, client, sample_rule_data):
        """Test rule testing when no events exist"""
        create_response = client.post("/api/v1/alert-rules", json=sample_rule_data)
        rule_id = create_response.json()["id"]

        response = client.post(f"/api/v1/alert-rules/{rule_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["rule_id"] == rule_id
        assert data["events_tested"] == 0
        assert data["events_matched"] == 0

    def test_test_rule_not_found(self, client):
        """Test 404 for testing non-existent rule"""
        response = client.post("/api/v1/alert-rules/non-existent-id/test")

        assert response.status_code == 404
