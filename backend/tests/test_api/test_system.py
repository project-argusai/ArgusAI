"""Integration tests for system API endpoints"""
import pytest
import json
from datetime import datetime, timezone, timedelta, date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os

from main import app
from app.core.database import Base, get_db
from app.models.system_setting import SystemSetting
from app.models.event import Event
from app.models.ai_usage import AIUsage
from app.services import cleanup_service
from app.services.service_container import container


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
    # Override CleanupService (now a @singleton) to use the test database.
    # The /system/storage and /events/cleanup endpoints resolve the service via
    # container.cleanup_service -> get_cleanup_service() -> CleanupService(),
    # which returns the cached singleton instance. We seed that instance with a
    # CleanupService bound to the test session factory so the endpoints query the
    # same temp DB the tests write to.
    cleanup_service.CleanupService._reset_instance()
    _test_cleanup = cleanup_service.CleanupService(session_factory=TestingSessionLocal)
    cleanup_service.CleanupService._singleton_instance = _test_cleanup
    cleanup_service.CleanupService._singleton_initialized = True
    yield
    # Drop tables after all tests in module complete
    cleanup_service.CleanupService._reset_instance()
    Base.metadata.drop_all(bind=engine)


# Create test client (module-level)
client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_database(setup_module_database):
    """Clear database between tests and re-seed test-bound singletons.

    The global autouse `_reset_all_singletons` fixture (tests/conftest.py) wipes
    every @singleton before each test, which would otherwise replace our
    test-DB-bound CleanupService with a default-DB instance. Re-seed it here so
    container.cleanup_service keeps pointing at the temp test database for every
    test in this module.
    """
    cleanup_service.CleanupService._reset_instance()
    _test_cleanup = cleanup_service.CleanupService(session_factory=TestingSessionLocal)
    cleanup_service.CleanupService._singleton_instance = _test_cleanup
    cleanup_service.CleanupService._singleton_initialized = True

    # Clean up BEFORE the test to ensure isolation
    db = TestingSessionLocal()
    try:
        db.query(SystemSetting).delete()
        db.query(Event).delete()
        db.query(AIUsage).delete()
        db.commit()
    finally:
        db.close()
    yield
    # Clear all tables after test
    db = TestingSessionLocal()
    try:
        db.query(SystemSetting).delete()
        db.query(Event).delete()
        db.query(AIUsage).delete()
        db.commit()
    finally:
        db.close()


class TestRetentionPolicyEndpoints:
    """Test retention policy API endpoints"""

    def test_get_retention_policy_default(self):
        """Test GET /system/retention returns default 30 days"""
        response = client.get("/api/v1/system/retention")

        assert response.status_code == 200
        data = response.json()

        assert data["retention_days"] == 30
        assert data["forever"] is False
        assert data["next_cleanup"] is not None

    def test_get_retention_policy_custom(self):
        """Test GET /system/retention returns custom value from database"""
        # Set custom retention policy
        db = TestingSessionLocal()
        try:
            setting = SystemSetting(
                key="data_retention_days",
                value="90"
            )
            db.add(setting)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/system/retention")

        assert response.status_code == 200
        data = response.json()

        assert data["retention_days"] == 90
        assert data["forever"] is False
        assert data["next_cleanup"] is not None

    def test_get_retention_policy_forever(self):
        """Test GET /system/retention with forever (-1) setting"""
        # Set forever retention
        db = TestingSessionLocal()
        try:
            setting = SystemSetting(
                key="data_retention_days",
                value="-1"
            )
            db.add(setting)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/system/retention")

        assert response.status_code == 200
        data = response.json()

        assert data["retention_days"] == -1
        assert data["forever"] is True
        assert data["next_cleanup"] is None

    def test_update_retention_policy_valid(self):
        """Test PUT /system/retention with valid retention days"""
        for retention_days in [7, 30, 90, 365]:
            response = client.put(
                "/api/v1/system/retention",
                json={"retention_days": retention_days}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["retention_days"] == retention_days
            assert data["forever"] is False
            assert data["next_cleanup"] is not None

            # Verify stored in database
            db = TestingSessionLocal()
            try:
                setting = db.query(SystemSetting).filter(
                    SystemSetting.key == "data_retention_days"
                ).first()
                assert setting is not None
                assert setting.value == str(retention_days)
            finally:
                db.close()

    def test_update_retention_policy_forever(self):
        """Test PUT /system/retention with forever values"""
        for forever_value in [-1, 0]:
            response = client.put(
                "/api/v1/system/retention",
                json={"retention_days": forever_value}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["retention_days"] == forever_value
            assert data["forever"] is True
            assert data["next_cleanup"] is None

    def test_update_retention_policy_invalid(self):
        """Test PUT /system/retention with invalid retention days"""
        invalid_values = [5, 10, 20, 45, 100, 500]

        for invalid_value in invalid_values:
            response = client.put(
                "/api/v1/system/retention",
                json={"retention_days": invalid_value}
            )

            assert response.status_code == 422  # Validation error
            error_detail = response.json()["detail"]
            assert any("retention_days must be one of" in str(err) for err in error_detail)

    def test_update_retention_policy_missing_field(self):
        """Test PUT /system/retention with missing retention_days"""
        response = client.put(
            "/api/v1/system/retention",
            json={}
        )

        assert response.status_code == 422  # Validation error


class TestStorageEndpoint:
    """Test storage monitoring API endpoint"""

    def test_get_storage_info_empty(self):
        """Test GET /system/storage with no events"""
        response = client.get("/api/v1/system/storage")

        assert response.status_code == 200
        data = response.json()

        assert "database_mb" in data
        assert "thumbnails_mb" in data
        assert "total_mb" in data
        assert "event_count" in data

        assert data["event_count"] == 0
        assert data["database_mb"] >= 0
        assert data["thumbnails_mb"] >= 0
        # total_mb is round(database_mb + thumbnails_mb, 2) in the service, so
        # compare with tolerance rather than exact float equality.
        assert data["total_mb"] == pytest.approx(
            data["database_mb"] + data["thumbnails_mb"], abs=0.01
        )

    def test_get_storage_info_with_events(self):
        """Test GET /system/storage with events"""
        # Create test events
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)
            events = [
                Event(
                    id=f"test-{i}",
                    camera_id="test-camera",
                    timestamp=now,
                    description="Test event",
                    confidence=85,
                    objects_detected='["person"]',
                    thumbnail_path=None,
                    alert_triggered=False
                )
                for i in range(50)
            ]
            db.add_all(events)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/system/storage")

        assert response.status_code == 200
        data = response.json()

        assert data["event_count"] == 50
        assert data["database_mb"] > 0
        assert data["total_mb"] >= data["database_mb"]


class TestEventsExportEndpoint:
    """Test events export API endpoint"""

    @pytest.fixture(autouse=True)
    def setup_test_events(self):
        """Create test events for export tests"""
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)

            # Create events at different dates
            self.events = [
                Event(
                    id=f"export-test-{i}",
                    camera_id="camera-1" if i < 5 else "camera-2",
                    timestamp=now - timedelta(days=i),
                    description=f"Test event {i}",
                    confidence=80 + i,
                    objects_detected='["person", "vehicle"]' if i % 2 == 0 else '["person"]',
                    thumbnail_path=f"thumbnails/2025-11-17/event_{i}.jpg",
                    alert_triggered=i % 3 == 0
                )
                for i in range(10)
            ]

            db.add_all(self.events)
            db.commit()
        finally:
            db.close()

        yield

    def test_export_json_format(self):
        """Test GET /events/export with JSON format"""
        response = client.get("/api/v1/events/export?format=json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-ndjson"
        assert "attachment" in response.headers["content-disposition"]
        assert ".json" in response.headers["content-disposition"]

        # Parse newline-delimited JSON
        lines = response.text.strip().split('\n')
        assert len(lines) == 10

        # Verify first event
        first_event = json.loads(lines[0])
        assert "id" in first_event
        assert "camera_id" in first_event
        assert "timestamp" in first_event
        assert "description" in first_event
        assert "confidence" in first_event
        assert "objects_detected" in first_event
        assert isinstance(first_event["objects_detected"], list)

    def test_export_csv_format(self):
        """Test GET /events/export with CSV format"""
        response = client.get("/api/v1/events/export?format=csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]  # May include charset
        assert "attachment" in response.headers["content-disposition"]
        assert ".csv" in response.headers["content-disposition"]

        # Parse CSV
        lines = response.text.strip().split('\n')
        assert len(lines) == 11  # 1 header + 10 data rows

        # Verify header
        header = lines[0]
        assert "id" in header
        assert "camera_id" in header
        assert "description" in header
        assert "confidence" in header

    def test_export_with_date_filter(self):
        """Test GET /events/export with date range filter"""
        today = date.today()
        start_date = (today - timedelta(days=5)).isoformat()
        end_date = today.isoformat()

        response = client.get(
            f"/api/v1/events/export?format=json&start_date={start_date}&end_date={end_date}"
        )

        assert response.status_code == 200

        lines = response.text.strip().split('\n')
        # Should have fewer events (only last 5 days)
        assert len(lines) <= 6

    def test_export_with_camera_filter(self):
        """Test GET /events/export with camera filter"""
        response = client.get("/api/v1/events/export?format=json&camera_id=camera-1")

        assert response.status_code == 200

        lines = response.text.strip().split('\n')
        # Should have only camera-1 events (first 5)
        assert len(lines) == 5

        # Verify all events are from camera-1
        for line in lines:
            event = json.loads(line)
            assert event["camera_id"] == "camera-1"

    def test_export_with_confidence_filter(self):
        """Test GET /events/export with confidence filter"""
        response = client.get("/api/v1/events/export?format=json&min_confidence=85")

        assert response.status_code == 200

        lines = response.text.strip().split('\n')
        # Verify all events meet confidence threshold
        for line in lines:
            event = json.loads(line)
            assert event["confidence"] >= 85

    def test_export_invalid_format(self):
        """Test GET /events/export with invalid format"""
        response = client.get("/api/v1/events/export?format=xml")

        assert response.status_code == 422  # Validation error


class TestEventsCleanupEndpoint:
    """Test manual cleanup API endpoint"""

    @pytest.fixture(autouse=True)
    def setup_test_events(self):
        """Create test events for cleanup tests"""
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)

            # Create old events (60 days ago)
            old_events = [
                Event(
                    id=f"old-{i}",
                    camera_id="test-camera",
                    timestamp=now - timedelta(days=60),
                    description="Old event",
                    confidence=85,
                    objects_detected='["person"]',
                    thumbnail_path=None,
                    alert_triggered=False
                )
                for i in range(10)
            ]

            # Create recent events (5 days ago)
            recent_events = [
                Event(
                    id=f"recent-{i}",
                    camera_id="test-camera",
                    timestamp=now - timedelta(days=5),
                    description="Recent event",
                    confidence=85,
                    objects_detected='["person"]',
                    thumbnail_path=None,
                    alert_triggered=False
                )
                for i in range(5)
            ]

            db.add_all(old_events + recent_events)
            db.commit()
        finally:
            db.close()

        yield

    def test_cleanup_without_confirmation(self):
        """Test DELETE /events/cleanup without confirmation"""
        before_date = (date.today() - timedelta(days=30)).isoformat()

        response = client.delete(
            f"/api/v1/events/cleanup?before_date={before_date}&confirm=false"
        )

        assert response.status_code == 400
        assert "must be explicitly confirmed" in response.json()["detail"]

        # Verify no events deleted
        db = TestingSessionLocal()
        try:
            assert db.query(Event).count() == 15
        finally:
            db.close()

    def test_cleanup_future_date(self):
        """Test DELETE /events/cleanup with future date"""
        future_date = (date.today() + timedelta(days=1)).isoformat()

        response = client.delete(
            f"/api/v1/events/cleanup?before_date={future_date}&confirm=true"
        )

        assert response.status_code == 400
        assert "must be in the past" in response.json()["detail"]

    def test_cleanup_valid(self):
        """Test DELETE /events/cleanup with valid parameters"""
        # Delete events before 30 days ago
        before_date = (date.today() - timedelta(days=30)).isoformat()

        response = client.delete(
            f"/api/v1/events/cleanup?before_date={before_date}&confirm=true"
        )

        assert response.status_code == 200
        data = response.json()

        assert "deleted_count" in data
        assert "thumbnails_deleted" in data
        assert "space_freed_mb" in data

        # Should have deleted 10 old events
        assert data["deleted_count"] == 10

        # Verify only recent events remain
        db = TestingSessionLocal()
        try:
            remaining_count = db.query(Event).count()
            assert remaining_count == 5

            # Verify all remaining events are recent
            remaining_events = db.query(Event).all()
            assert all(event.id.startswith("recent-") for event in remaining_events)
        finally:
            db.close()

    def test_cleanup_no_events_to_delete(self):
        """Test DELETE /events/cleanup when no events match criteria"""
        # Delete events before 90 days ago (all our events are more recent)
        before_date = (date.today() - timedelta(days=90)).isoformat()

        response = client.delete(
            f"/api/v1/events/cleanup?before_date={before_date}&confirm=true"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["deleted_count"] == 0

        # Verify all events remain
        db = TestingSessionLocal()
        try:
            assert db.query(Event).count() == 15
        finally:
            db.close()


# ============================================================================
# AI Providers Status Endpoint Tests (Story P2-5.2)
# ============================================================================


class TestAIProvidersStatusEndpoint:
    """Tests for GET /api/v1/system/ai-providers endpoint"""

    @pytest.fixture(autouse=True)
    def setup_cleanup(self):
        """Clean up provider settings before/after each test"""
        db = TestingSessionLocal()
        try:
            # Remove any AI provider settings
            db.query(SystemSetting).filter(
                SystemSetting.key.in_([
                    'ai_api_key_openai',
                    'ai_api_key_grok',
                    'ai_api_key_claude',
                    'ai_api_key_gemini',
                    'ai_provider_order'
                ])
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

        yield

        # Cleanup after test
        db = TestingSessionLocal()
        try:
            db.query(SystemSetting).filter(
                SystemSetting.key.in_([
                    'ai_api_key_openai',
                    'ai_api_key_grok',
                    'ai_api_key_claude',
                    'ai_api_key_gemini',
                    'ai_provider_order'
                ])
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def test_get_providers_status_empty(self):
        """Test GET /ai-providers with no providers configured"""
        response = client.get("/api/v1/system/ai-providers")

        assert response.status_code == 200
        data = response.json()

        assert "providers" in data
        assert "order" in data

        # All providers should be unconfigured
        assert len(data["providers"]) == 4
        for provider in data["providers"]:
            assert provider["configured"] is False

        # Default order should be returned
        assert data["order"] == ["openai", "grok", "anthropic", "google"]

    def test_get_providers_status_with_configured_provider(self):
        """Test GET /ai-providers with one provider configured"""
        db = TestingSessionLocal()
        try:
            # Add a configured API key for OpenAI
            db.add(SystemSetting(key='ai_api_key_openai', value='encrypted:test-key'))
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/system/ai-providers")

        assert response.status_code == 200
        data = response.json()

        # Find the OpenAI provider
        openai_provider = next((p for p in data["providers"] if p["provider"] == "openai"), None)
        assert openai_provider is not None
        assert openai_provider["configured"] is True

        # Grok should still be unconfigured
        grok_provider = next((p for p in data["providers"] if p["provider"] == "grok"), None)
        assert grok_provider is not None
        assert grok_provider["configured"] is False

    def test_get_providers_status_with_custom_order(self):
        """Test GET /ai-providers returns custom provider order"""
        db = TestingSessionLocal()
        try:
            # Set a custom provider order
            custom_order = ["grok", "anthropic", "openai", "google"]
            db.add(SystemSetting(key='ai_provider_order', value=json.dumps(custom_order)))
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/system/ai-providers")

        assert response.status_code == 200
        data = response.json()

        # Should return the custom order
        assert data["order"] == custom_order

    def test_get_providers_status_invalid_order_falls_back(self):
        """Test GET /ai-providers returns default order if saved order is invalid"""
        db = TestingSessionLocal()
        try:
            # Set an invalid provider order
            db.add(SystemSetting(key='ai_provider_order', value='not-valid-json'))
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/system/ai-providers")

        assert response.status_code == 200
        data = response.json()

        # Should fall back to default order
        assert data["order"] == ["openai", "grok", "anthropic", "google"]


# ============================================================================
# AI Provider Stats Endpoint Tests (Story P2-5.3)
# ============================================================================


class TestAIProviderStatsEndpoint:
    """Tests for GET /api/v1/system/ai-stats endpoint (Story P2-5.3)"""

    @pytest.fixture(autouse=True)
    def setup_cleanup(self):
        """Create test events with provider_used set"""
        db = TestingSessionLocal()
        try:
            # Clean up existing events
            db.query(Event).delete()
            db.commit()

            # Create test events with different providers
            now = datetime.now(timezone.utc)
            events = [
                # 5 OpenAI events
                *[Event(
                    id=f"openai-{i}",
                    camera_id="test-camera",
                    timestamp=now - timedelta(hours=i),
                    description="Event by OpenAI",
                    confidence=85,
                    objects_detected='["person"]',
                    thumbnail_path=None,
                    alert_triggered=False,
                    provider_used="openai"
                ) for i in range(5)],
                # 3 Grok events
                *[Event(
                    id=f"grok-{i}",
                    camera_id="test-camera",
                    timestamp=now - timedelta(hours=i+5),
                    description="Event by Grok",
                    confidence=80,
                    objects_detected='["vehicle"]',
                    thumbnail_path=None,
                    alert_triggered=False,
                    provider_used="grok"
                ) for i in range(3)],
                # 2 Claude events (older)
                *[Event(
                    id=f"claude-{i}",
                    camera_id="test-camera",
                    timestamp=now - timedelta(days=10),
                    description="Event by Claude",
                    confidence=90,
                    objects_detected='["package"]',
                    thumbnail_path=None,
                    alert_triggered=False,
                    provider_used="claude"
                ) for i in range(2)],
                # 1 Legacy event (no provider_used)
                Event(
                    id="legacy-1",
                    camera_id="test-camera",
                    timestamp=now - timedelta(days=5),
                    description="Legacy event",
                    confidence=70,
                    objects_detected='["unknown"]',
                    thumbnail_path=None,
                    alert_triggered=False,
                    provider_used=None
                )
            ]

            db.add_all(events)
            db.commit()
        finally:
            db.close()

        yield

        # Cleanup
        db = TestingSessionLocal()
        try:
            db.query(Event).delete()
            db.commit()
        finally:
            db.close()

    def test_get_ai_stats_default_range(self):
        """Test GET /ai-stats with default 7 day range"""
        response = client.get("/api/v1/system/ai-stats")

        assert response.status_code == 200
        data = response.json()

        assert "total_events" in data
        assert "events_per_provider" in data
        assert "date_range" in data
        assert "time_range" in data

        # Should include recent events but not 10-day-old Claude events
        assert data["date_range"] == "7d"
        assert data["events_per_provider"].get("openai", 0) == 5
        assert data["events_per_provider"].get("grok", 0) == 3
        # Claude events are 10 days old, outside 7-day range
        assert data["events_per_provider"].get("claude", 0) == 0

    def test_get_ai_stats_24h_range(self):
        """Test GET /ai-stats with 24 hour range"""
        response = client.get("/api/v1/system/ai-stats?date_range=24h")

        assert response.status_code == 200
        data = response.json()

        assert data["date_range"] == "24h"
        # Only events within last 24h should be counted
        # (all our test events are within 24h except the 10-day-old ones)

    def test_get_ai_stats_all_range(self):
        """Test GET /ai-stats with 'all' range includes all events"""
        response = client.get("/api/v1/system/ai-stats?date_range=all")

        assert response.status_code == 200
        data = response.json()

        assert data["date_range"] == "all"
        # Should include all events with provider_used set
        assert data["events_per_provider"].get("openai", 0) == 5
        assert data["events_per_provider"].get("grok", 0) == 3
        assert data["events_per_provider"].get("claude", 0) == 2
        # Total should be 10 (excludes legacy event with null provider)
        assert data["total_events"] == 10

    def test_get_ai_stats_excludes_null_providers(self):
        """Test that events without provider_used are excluded from stats"""
        response = client.get("/api/v1/system/ai-stats?date_range=all")

        assert response.status_code == 200
        data = response.json()

        # Total should be 10, not 11 (excludes the legacy event)
        assert data["total_events"] == 10

    def test_get_ai_stats_empty_result(self):
        """Test GET /ai-stats when no events exist"""
        # Clean all events
        db = TestingSessionLocal()
        try:
            db.query(Event).delete()
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/system/ai-stats")

        assert response.status_code == 200
        data = response.json()

        assert data["total_events"] == 0
        assert data["events_per_provider"] == {}


class TestAIUsageEndpoint:
    """Test AI usage cost tracking endpoint (Story P3-7.1)"""

    def test_get_ai_usage_empty(self):
        """Test GET /system/ai-usage with no data returns zeros"""
        response = client.get("/api/v1/system/ai-usage")

        assert response.status_code == 200
        data = response.json()

        assert data["total_cost"] == 0.0
        assert data["total_requests"] == 0
        assert "period" in data
        assert data["by_date"] == []
        assert data["by_camera"] == []
        assert data["by_provider"] == []
        assert data["by_mode"] == []

    def test_get_ai_usage_with_data(self):
        """Test GET /system/ai-usage returns aggregated usage data"""
        # Create test AIUsage records
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)
            usage_records = [
                AIUsage(
                    timestamp=now - timedelta(hours=1),
                    provider="openai",
                    success=True,
                    tokens_used=1000,
                    response_time_ms=500,
                    cost_estimate=0.0005,
                    analysis_mode="single_image"
                ),
                AIUsage(
                    timestamp=now - timedelta(hours=2),
                    provider="openai",
                    success=True,
                    tokens_used=2000,
                    response_time_ms=600,
                    cost_estimate=0.001,
                    analysis_mode="multi_frame",
                    image_count=5
                ),
                AIUsage(
                    timestamp=now - timedelta(hours=3),
                    provider="claude",
                    success=True,
                    tokens_used=1500,
                    response_time_ms=700,
                    cost_estimate=0.002,
                    analysis_mode="single_image"
                ),
            ]
            for record in usage_records:
                db.add(record)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/system/ai-usage")

        assert response.status_code == 200
        data = response.json()

        # Total cost should be sum of all cost_estimates
        assert data["total_cost"] == pytest.approx(0.0035, rel=1e-4)
        assert data["total_requests"] == 3

        # Check by_provider aggregation
        assert len(data["by_provider"]) == 2
        providers_by_name = {p["provider"]: p for p in data["by_provider"]}
        assert "openai" in providers_by_name
        assert providers_by_name["openai"]["requests"] == 2
        assert providers_by_name["openai"]["cost"] == pytest.approx(0.0015, rel=1e-4)
        assert "claude" in providers_by_name
        assert providers_by_name["claude"]["requests"] == 1

        # Check by_mode aggregation
        assert len(data["by_mode"]) == 2
        modes_by_name = {m["mode"]: m for m in data["by_mode"]}
        assert "single_image" in modes_by_name
        assert modes_by_name["single_image"]["requests"] == 2
        assert "multi_frame" in modes_by_name
        assert modes_by_name["multi_frame"]["requests"] == 1

        # Check by_date aggregation (may span 1-2 days if run near midnight UTC)
        assert 1 <= len(data["by_date"]) <= 2

    def test_get_ai_usage_date_filter(self):
        """Test GET /system/ai-usage with date range filter"""
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)
            usage_records = [
                AIUsage(
                    timestamp=now - timedelta(days=1),
                    provider="openai",
                    success=True,
                    tokens_used=1000,
                    response_time_ms=500,
                    cost_estimate=0.0005,
                    analysis_mode="single_image"
                ),
                AIUsage(
                    timestamp=now - timedelta(days=10),
                    provider="claude",
                    success=True,
                    tokens_used=2000,
                    response_time_ms=600,
                    cost_estimate=0.001,
                    analysis_mode="single_image"
                ),
            ]
            for record in usage_records:
                db.add(record)
            db.commit()
        finally:
            db.close()

        # Filter to only last 5 days - use ISO format with Z suffix
        start_dt = datetime.now(timezone.utc) - timedelta(days=5)
        start_date = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        response = client.get(f"/api/v1/system/ai-usage?start_date={start_date}")

        assert response.status_code == 200
        data = response.json()

        # Should only include the record from 1 day ago
        assert data["total_requests"] == 1
        assert data["total_cost"] == pytest.approx(0.0005, rel=1e-4)

    def test_get_ai_usage_invalid_date_format(self):
        """Test GET /system/ai-usage with invalid date format returns 400"""
        response = client.get("/api/v1/system/ai-usage?start_date=not-a-date")

        assert response.status_code == 400
        assert "Invalid start_date format" in response.json()["detail"]

    def test_get_ai_usage_response_structure(self):
        """Test GET /system/ai-usage returns correct response structure"""
        response = client.get("/api/v1/system/ai-usage")

        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        assert "total_cost" in data
        assert "total_requests" in data
        assert "period" in data
        assert "start" in data["period"]
        assert "end" in data["period"]
        assert "by_date" in data
        assert "by_camera" in data
        assert "by_provider" in data
        assert "by_mode" in data


# ============================================================================
# Frame Sampling Strategy Settings Tests (Story P8-2.5)
# ============================================================================


class TestFrameSamplingStrategySetting:
    """Tests for frame_sampling_strategy in system settings (Story P8-2.5)"""

    def test_get_settings_includes_frame_sampling_strategy_default(self):
        """Test GET /settings includes frame_sampling_strategy with default 'uniform'"""
        response = client.get("/api/v1/system/settings")

        assert response.status_code == 200
        data = response.json()

        # Should include frame_sampling_strategy with default value
        assert "frame_sampling_strategy" in data
        assert data["frame_sampling_strategy"] == "uniform"

    def test_put_settings_accepts_valid_uniform_strategy(self):
        """Test PUT /settings accepts 'uniform' strategy"""
        response = client.put(
            "/api/v1/system/settings",
            json={"frame_sampling_strategy": "uniform"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["frame_sampling_strategy"] == "uniform"

        # Verify stored in database
        db = TestingSessionLocal()
        try:
            setting = db.query(SystemSetting).filter(
                SystemSetting.key == "settings_frame_sampling_strategy"
            ).first()
            assert setting is not None
            assert setting.value == "uniform"
        finally:
            db.close()

    def test_put_settings_accepts_valid_adaptive_strategy(self):
        """Test PUT /settings accepts 'adaptive' strategy"""
        response = client.put(
            "/api/v1/system/settings",
            json={"frame_sampling_strategy": "adaptive"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["frame_sampling_strategy"] == "adaptive"

        # Verify stored in database
        db = TestingSessionLocal()
        try:
            setting = db.query(SystemSetting).filter(
                SystemSetting.key == "settings_frame_sampling_strategy"
            ).first()
            assert setting is not None
            assert setting.value == "adaptive"
        finally:
            db.close()

    def test_put_settings_accepts_valid_hybrid_strategy(self):
        """Test PUT /settings accepts 'hybrid' strategy"""
        response = client.put(
            "/api/v1/system/settings",
            json={"frame_sampling_strategy": "hybrid"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["frame_sampling_strategy"] == "hybrid"

        # Verify stored in database
        db = TestingSessionLocal()
        try:
            setting = db.query(SystemSetting).filter(
                SystemSetting.key == "settings_frame_sampling_strategy"
            ).first()
            assert setting is not None
            assert setting.value == "hybrid"
        finally:
            db.close()

    def test_put_settings_rejects_invalid_strategy(self):
        """Test PUT /settings rejects invalid strategy values"""
        invalid_strategies = ["random", "sequential", "invalid", "UNIFORM", ""]

        for invalid_strategy in invalid_strategies:
            response = client.put(
                "/api/v1/system/settings",
                json={"frame_sampling_strategy": invalid_strategy}
            )

            assert response.status_code == 422, f"Expected 422 for '{invalid_strategy}'"

    def test_get_settings_returns_saved_strategy(self):
        """Test GET /settings returns previously saved strategy"""
        # Save a strategy
        db = TestingSessionLocal()
        try:
            db.add(SystemSetting(key="settings_frame_sampling_strategy", value="adaptive"))
            db.commit()
        finally:
            db.close()

        response = client.get("/api/v1/system/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["frame_sampling_strategy"] == "adaptive"


# ============================================================================
# Debug Endpoint Security Tests (Story P14-1.2)
# ============================================================================


class TestDebugEndpointSecurity:
    """Tests for debug endpoint security (Story P14-1.2).

    Note: These tests verify that debug endpoints return 404 when
    DEBUG_ENDPOINTS_ENABLED=false (the default). The endpoints are not
    registered at all when disabled, so they simply don't exist.
    """

    def test_debug_ai_keys_returns_404_by_default(self):
        """Test GET /debug/ai-keys returns 404 when DEBUG_ENDPOINTS_ENABLED=false."""
        response = client.get("/api/v1/system/debug/ai-keys")

        # Should return 404 (endpoint not registered) when disabled
        # Note: If DEBUG_ENDPOINTS_ENABLED=true in the environment,
        # this test will fail - that's expected in development mode
        assert response.status_code == 404

    def test_debug_network_returns_404_by_default(self):
        """Test GET /debug/network returns 404 when DEBUG_ENDPOINTS_ENABLED=false."""
        response = client.get("/api/v1/system/debug/network")

        # Should return 404 (endpoint not registered) when disabled
        assert response.status_code == 404

    def test_debug_endpoints_not_in_openapi_schema(self):
        """Test debug endpoints are not visible in OpenAPI schema when disabled."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()

        # Check that debug endpoints are not in the schema
        paths = schema.get("paths", {})
        debug_paths = [p for p in paths.keys() if "/debug/" in p]

        # When disabled, no debug paths should exist
        # Note: If DEBUG_ENDPOINTS_ENABLED=true, they still won't appear
        # because we use include_in_schema=False
        assert len(debug_paths) == 0, f"Found debug paths in schema: {debug_paths}"


# Cleanup test database on module exit
def teardown_module():
    """Remove test database file"""
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)


# =============================================================================
# Pure unit tests for hot-list filtering (_filter_hot_update)
# These are fast, have no DB/app dependencies, and cover the advanced
# per-client hot-list filters used by the dedicated hot WebSocket and SSE.
# =============================================================================

from app.api.v1.system import _filter_hot_update


class TestHotListFilters:
    """Focused tests for advanced filtering on hot_cameras / top_recent_entities."""

    def test_filters_hot_cameras_by_min_score_and_count(self):
        record = {
            "type": "hot_update",
            "hot_cameras": [
                {"camera_id": "cam-1", "count": 12, "score": 9.4},
                {"camera_id": "cam-2", "count": 3, "score": 7.1},
                {"camera_id": "cam-3", "count": 8, "score": 4.2},
            ],
            "top_recent_entities": [],
        }

        filters = {"min_camera_count": 5, "min_camera_score": 5.0}
        result = _filter_hot_update(record, filters)

        cam_ids = [c["camera_id"] for c in result["hot_cameras"]]
        assert cam_ids == ["cam-1"]  # only cam-1 meets both thresholds

    def test_filters_entities_by_min_score_and_is_new(self):
        record = {
            "type": "hot_update",
            "hot_cameras": [],
            "top_recent_entities": [
                {"entity_id": "e1", "type": "person", "score": 0.95, "is_new": True},
                {"entity_id": "e2", "type": "person", "score": 0.71, "is_new": False},
                {"entity_id": "e3", "type": "vehicle", "score": 0.88, "is_new": True},
            ],
        }

        filters = {"min_score": 0.80, "entity_is_new": True}
        result = _filter_hot_update(record, filters)

        ids = [e["entity_id"] for e in result["top_recent_entities"]]
        # min_score>=0.80 AND is_new=True keeps e1 (0.95, new) and e3 (0.88, new);
        # e2 is filtered out by both score and is_new. No type filter is applied,
        # so the vehicle e3 correctly remains.
        assert ids == ["e1", "e3"]

    def test_filters_entities_by_type_and_specific_ids(self):
        record = {
            "type": "hot_update",
            "hot_cameras": [],
            "top_recent_entities": [
                {"entity_id": "p1", "type": "person", "score": 0.9},
                {"entity_id": "v1", "type": "vehicle", "score": 0.9},
                {"entity_id": "p2", "type": "person", "score": 0.9},
            ],
        }

        filters = {"entity_types": ["person"], "entity_ids": ["p1", "p2"]}
        result = _filter_hot_update(record, filters)

        ids = [e["entity_id"] for e in result["top_recent_entities"]]
        assert set(ids) == {"p1", "p2"}

    def test_returns_empty_lists_when_no_items_match_filters(self):
        record = {
            "type": "hot_update",
            "hot_cameras": [{"camera_id": "c1", "score": 1.0}],
            "top_recent_entities": [{"entity_id": "e1", "score": 0.5}],
        }

        filters = {"min_score": 0.99, "min_camera_score": 10.0}
        result = _filter_hot_update(record, filters)

        assert result["hot_cameras"] == []
        assert result["top_recent_entities"] == []

    def test_preserves_other_fields_and_returns_new_dict(self):
        record = {
            "type": "hot_update",
            "hot_cameras": [{"camera_id": "c1", "score": 5.0}],
            "top_recent_entities": [],
            "timestamp": "2026-05-15T12:00:00Z",
        }

        result = _filter_hot_update(record, {})
        assert result is not record  # must not mutate original
        assert result["timestamp"] == "2026-05-15T12:00:00Z"
        assert result["hot_cameras"] == record["hot_cameras"]


# =============================================================================
# Lightweight API tests for the enriched REST hot snapshot endpoint
# (/ai-processing-hot) with rich per-client hot-list filters.
# These tests mock the coordinator methods so they are fast and isolated.
# =============================================================================

from unittest.mock import patch
from app.models.user import User, UserRole
from app.api.v1.auth import get_current_user
from main import app as main_app


def _admin_user_override():
    """Return a fake admin user for protected endpoint tests."""
    return User(id=1, username="testadmin", role=UserRole.ADMIN, is_active=True)


class TestAIProcessingHotRestEndpoint:
    """Tests for GET /api/v1/system/ai-processing-hot with the new filter params."""

    @pytest.fixture(autouse=True)
    def admin_auth(self):
        """Temporarily override auth so we can call admin-only endpoints."""
        main_app.dependency_overrides[get_current_user] = _admin_user_override
        yield
        main_app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture(autouse=True)
    def stub_coordinator(self):
        """Seed the AIProcessingCoordinator singleton with a mock.

        The endpoint resolves the coordinator via
        container.ai_processing_coordinator -> get_ai_processing_coordinator()
        -> AIProcessingCoordinator(), which (after the autouse singleton reset)
        would try to construct the real coordinator with no DI args and fail with
        "missing 6 required positional arguments". Seeding a MagicMock instance as
        the singleton lets the tests patch get_hot_cameras / get_top_recent_entities
        on the same object the endpoint reads.
        """
        from unittest.mock import MagicMock
        from app.services.ai_processing_coordinator import AIProcessingCoordinator

        AIProcessingCoordinator._reset_instance()
        AIProcessingCoordinator._singleton_instance = MagicMock()
        AIProcessingCoordinator._singleton_initialized = True
        yield
        AIProcessingCoordinator._reset_instance()

    def test_hot_snapshot_no_filters(self):
        mock_cameras = [
            {"camera_id": "cam-living", "name": "Living Room", "score": 12.4, "count": 8},
            {"camera_id": "cam-front", "name": "Front Door", "score": 9.1, "count": 5},
        ]
        mock_entities = [
            {"entity_id": "ent-1", "name": "Alice", "type": "person", "score": 0.94, "is_new": False},
            {"entity_id": "ent-2", "name": "Bob's Car", "type": "vehicle", "score": 0.81, "is_new": True},
        ]

        with patch.object(
            container.ai_processing_coordinator, "get_hot_cameras", return_value=mock_cameras
        ), patch.object(
            container.ai_processing_coordinator, "get_top_recent_entities", return_value=mock_entities
        ):
            response = client.get("/api/v1/system/ai-processing-hot?limit=5")
            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "ok"
            assert data["hot_cameras"] == mock_cameras
            assert data["top_recent_entities"] == mock_entities
            assert data["filters_applied"] == {}

    def test_hot_snapshot_entity_filters(self):
        mock_entities = [
            {"entity_id": "e1", "type": "person", "score": 0.95, "is_new": True},
            {"entity_id": "e2", "type": "person", "score": 0.72, "is_new": False},
            {"entity_id": "e3", "type": "vehicle", "score": 0.88, "is_new": True},
        ]

        with patch.object(
            container.ai_processing_coordinator, "get_hot_cameras", return_value=[]
        ), patch.object(
            container.ai_processing_coordinator, "get_top_recent_entities", return_value=mock_entities
        ):
            # Only high-scoring new people
            response = client.get(
                "/api/v1/system/ai-processing-hot?min_score=0.85&entity_is_new=true&entity_types=person"
            )
            assert response.status_code == 200
            data = response.json()

            returned_ids = [e["entity_id"] for e in data["top_recent_entities"]]
            assert returned_ids == ["e1"]
            assert data["filters_applied"]["min_score"] == 0.85
            assert data["filters_applied"]["entity_is_new"] is True

    def test_hot_snapshot_camera_score_filter_and_limit(self):
        mock_cameras = [
            {"camera_id": "c1", "score": 15.0, "count": 20},
            {"camera_id": "c2", "score": 7.5, "count": 4},
            {"camera_id": "c3", "score": 11.2, "count": 9},
        ]

        with patch.object(
            container.ai_processing_coordinator, "get_hot_cameras", return_value=mock_cameras
        ), patch.object(
            container.ai_processing_coordinator, "get_top_recent_entities", return_value=[]
        ):
            response = client.get("/api/v1/system/ai-processing-hot?min_camera_score=10&limit=1")
            assert response.status_code == 200
            data = response.json()

            assert len(data["hot_cameras"]) == 1
            assert data["hot_cameras"][0]["camera_id"] == "c1"
            assert data["filters_applied"]["min_camera_score"] == 10
            # The endpoint only echoes filters that were actually provided, so an
            # unprovided filter is absent from filters_applied (not present as None).
            assert "min_score" not in data["filters_applied"]

    def test_hot_snapshot_combined_filters_echoed(self):
        with patch.object(
            container.ai_processing_coordinator, "get_hot_cameras", return_value=[]
        ), patch.object(
            container.ai_processing_coordinator, "get_top_recent_entities", return_value=[]
        ):
            response = client.get(
                "/api/v1/system/ai-processing-hot?min_camera_count=5&entity_is_new=false&limit=3"
            )
            assert response.status_code == 200
            data = response.json()

            f = data["filters_applied"]
            assert f["min_camera_count"] == 5
            assert f["entity_is_new"] is False
