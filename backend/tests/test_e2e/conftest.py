"""
E2E Test Configuration and Fixtures.

Story P14-3.10: Add End-to-End Integration Tests
Provides fixtures for testing complete flows through the system.
"""
import pytest
import tempfile
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.database import Base, get_db
from app.models.camera import Camera
from app.models.event import Event
from app.models.alert_rule import AlertRule, WebhookLog
from app.models.notification import Notification
from app.models.user import User
from app.utils.auth import hash_password
from app.api.v1.auth import get_current_user


# ============================================================================
# Database Setup
# ============================================================================

@pytest.fixture(scope="module")
def e2e_database():
    """Create a module-level test database for E2E tests."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create all tables
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield {
        "engine": engine,
        "SessionLocal": SessionLocal,
        "db_path": db_path,
    }

    # Cleanup
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="function")
def db_session(e2e_database):
    """Get a database session for the current test."""
    SessionLocal = e2e_database["SessionLocal"]
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def clean_db(e2e_database):
    """Clean the database between tests."""
    SessionLocal = e2e_database["SessionLocal"]
    session = SessionLocal()
    try:
        # Clean up in order to avoid FK constraint issues
        session.query(Notification).delete()
        session.query(WebhookLog).delete()
        session.query(Event).delete()
        session.query(AlertRule).delete()
        session.query(Camera).delete()
        session.query(User).delete()
        session.commit()
    finally:
        session.close()
    yield


# ============================================================================
# Test Client
# ============================================================================

@pytest.fixture(scope="module")
def e2e_client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


# ============================================================================
# Authentication Fixtures
# ============================================================================

_test_user = None


def _override_get_current_user():
    """Override authentication for testing."""
    return _test_user


@pytest.fixture(scope="function")
def authenticated_user(e2e_database, clean_db):
    """Create and authenticate a test user."""
    global _test_user
    SessionLocal = e2e_database["SessionLocal"]
    session = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()),
            username="e2e_test_user",
            password_hash=hash_password("TestPass123!"),
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        _test_user = user

        app.dependency_overrides[get_current_user] = _override_get_current_user

        yield user
    finally:
        session.close()
        if get_current_user in app.dependency_overrides:
            del app.dependency_overrides[get_current_user]
        _test_user = None


# ============================================================================
# Mock Service Fixtures
# ============================================================================

@pytest.fixture
def mock_ai_service():
    """Mock AI service for testing without actual API calls."""
    with patch("app.services.ai_service.AIService") as mock:
        instance = mock.return_value
        instance.describe_image = AsyncMock(return_value={
            "description": "A person standing at the front door wearing a blue jacket.",
            "confidence": 0.95,
            "objects": ["person"],
            "provider": "mock_ai"
        })
        instance.describe_frames = AsyncMock(return_value={
            "description": "Person approaching the front door and ringing the doorbell.",
            "confidence": 0.92,
            "objects": ["person", "doorbell"],
            "provider": "mock_ai"
        })
        yield instance


@pytest.fixture
def mock_webhook_server():
    """Mock webhook server for testing webhook dispatch."""
    class MockWebhookServer:
        def __init__(self):
            self.calls = []
            self.call_count = 0
            self.last_call = None

        def record_call(self, url, payload, headers=None):
            call = {
                "url": url,
                "payload": payload,
                "headers": headers or {},
                "timestamp": datetime.now(timezone.utc),
            }
            self.calls.append(call)
            self.call_count += 1
            self.last_call = call

    server = MockWebhookServer()

    with patch("app.services.webhook_service.httpx.AsyncClient") as mock_client:
        async def mock_post(url, json=None, headers=None, **kwargs):
            server.record_call(url, json, headers)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            return mock_response

        mock_instance = AsyncMock()
        mock_instance.post = mock_post
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_instance

        yield server


@pytest.fixture
def mock_websocket_manager():
    """Mock WebSocket manager for testing broadcasts."""
    class MockWebSocketManager:
        def __init__(self):
            self.broadcasts = []
            self.connections = {}

        async def broadcast(self, message_type, data):
            self.broadcasts.append({
                "type": message_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc),
            })

        async def send_to_user(self, user_id, message_type, data):
            self.broadcasts.append({
                "type": message_type,
                "data": data,
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc),
            })

    manager = MockWebSocketManager()

    with patch("app.services.websocket_manager.manager", manager):
        yield manager


# ============================================================================
# Entity Fixtures
# ============================================================================

@pytest.fixture
def sample_camera(e2e_database, clean_db):
    """Create a sample camera for testing."""
    SessionLocal = e2e_database["SessionLocal"]
    session = SessionLocal()
    try:
        camera = Camera(
            id=str(uuid.uuid4()),
            name="E2E Test Camera",
            type="rtsp",
            source_type="rtsp",
            rtsp_url="rtsp://test:test@192.168.1.100:554/stream",
        )
        session.add(camera)
        session.commit()
        session.refresh(camera)
        yield camera
    finally:
        session.close()


@pytest.fixture
def sample_cameras(e2e_database, clean_db):
    """Create multiple cameras for correlation tests."""
    SessionLocal = e2e_database["SessionLocal"]
    session = SessionLocal()
    try:
        cameras = []
        for i in range(3):
            camera = Camera(
                id=str(uuid.uuid4()),
                name=f"E2E Camera {i+1}",
                type="rtsp",
                source_type="rtsp",
                rtsp_url=f"rtsp://test:test@192.168.1.10{i}:554/stream",
            )
            session.add(camera)
            cameras.append(camera)
        session.commit()
        for c in cameras:
            session.refresh(c)
        yield cameras
    finally:
        session.close()


@pytest.fixture
def sample_alert_rule(e2e_database, authenticated_user, sample_camera):
    """Create a sample alert rule for testing."""
    SessionLocal = e2e_database["SessionLocal"]
    session = SessionLocal()
    try:
        rule = AlertRule(
            id=str(uuid.uuid4()),
            name="Person Detection Alert",
            is_enabled=True,
            conditions='{"object_types": ["person"]}',
            actions='{"dashboard_notification": true}',
            cooldown_minutes=5,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        yield rule
    finally:
        session.close()


@pytest.fixture
def sample_alert_rule_with_webhook(e2e_database, authenticated_user, sample_camera):
    """Create a sample alert rule with webhook configuration for testing."""
    SessionLocal = e2e_database["SessionLocal"]
    session = SessionLocal()
    try:
        rule = AlertRule(
            id=str(uuid.uuid4()),
            name="Webhook Alert Rule",
            is_enabled=True,
            conditions='{"object_types": ["person"]}',
            actions='{"dashboard_notification": true, "webhook": {"url": "https://webhook.test/endpoint"}}',
            cooldown_minutes=5,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        yield rule
    finally:
        session.close()
