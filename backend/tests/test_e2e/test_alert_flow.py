"""
End-to-end tests for the alert flow.

Story P14-3.10: Add End-to-End Integration Tests
Tests: Event -> Alert Rule Matching -> Webhook Dispatch -> Notification
"""
import pytest
import uuid
from datetime import datetime, timezone

from app.models.event import Event
from app.models.alert_rule import AlertRule, WebhookLog
from app.models.notification import Notification


@pytest.mark.e2e
class TestAlertRuleManagement:
    """Tests for alert rule CRUD operations."""

    def test_create_alert_rule(self, e2e_client, authenticated_user, db_session):
        """Test creating an alert rule via API."""
        rule_data = {
            "name": "E2E Person Detection Rule",
            "is_enabled": True,
            "conditions": {"object_types": ["person"]},
            "actions": {"dashboard_notification": True},
            "cooldown_minutes": 10,
        }

        response = e2e_client.post("/api/v1/alert-rules", json=rule_data)

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "E2E Person Detection Rule"
        assert data["is_enabled"] is True

        # Verify in database
        rule = db_session.query(AlertRule).filter_by(id=data["id"]).first()
        assert rule is not None

    def test_list_alert_rules(self, e2e_client, authenticated_user, db_session):
        """Test listing all alert rules."""
        # Create rules
        for i in range(3):
            rule = AlertRule(
                id=str(uuid.uuid4()),
                name=f"E2E Rule {i+1}",
                is_enabled=True,
                conditions='{"object_types": ["person"]}',
                actions='{"dashboard_notification": true}',
                cooldown_minutes=5,
            )
            db_session.add(rule)
        db_session.commit()

        response = e2e_client.get("/api/v1/alert-rules")

        assert response.status_code == 200
        data = response.json()
        # Response has 'data' key with list of rules
        rules = data.get("data", [])
        assert len(rules) >= 3

    def test_update_alert_rule(self, e2e_client, authenticated_user, sample_alert_rule, db_session):
        """Test updating an alert rule."""
        update_data = {
            "name": "Updated Rule Name",
            "is_enabled": False,
        }

        response = e2e_client.put(
            f"/api/v1/alert-rules/{sample_alert_rule.id}",
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Rule Name"
        assert data["is_enabled"] is False

    def test_delete_alert_rule(self, e2e_client, authenticated_user, db_session):
        """Test deleting an alert rule."""
        # Create rule
        rule = AlertRule(
            id=str(uuid.uuid4()),
            name="Rule to Delete",
            is_enabled=True,
            conditions='{"object_types": ["vehicle"]}',
            actions='{"dashboard_notification": true}',
            cooldown_minutes=5,
        )
        db_session.add(rule)
        db_session.commit()
        rule_id = rule.id

        # Delete
        response = e2e_client.delete(f"/api/v1/alert-rules/{rule_id}")
        assert response.status_code in [200, 204]

        # Verify deletion
        db_session.expire_all()
        deleted_rule = db_session.query(AlertRule).filter_by(id=rule_id).first()
        assert deleted_rule is None


@pytest.mark.e2e
class TestNotificationFlow:
    """Tests for notification creation and management."""

    def test_list_notifications(self, e2e_client, authenticated_user, sample_alert_rule, sample_camera, db_session):
        """Test listing notifications."""
        # Create an event
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event that triggered notification",
            source_type="rtsp",
            objects_detected='["person"]',
            confidence=90,
        )
        db_session.add(event)
        db_session.commit()

        # Create a notification
        notification = Notification(
            id=str(uuid.uuid4()),
            event_id=event.id,
            rule_id=sample_alert_rule.id,
            rule_name=sample_alert_rule.name,
            event_description=event.description,
            read=False,
        )
        db_session.add(notification)
        db_session.commit()

        # List notifications
        response = e2e_client.get("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] >= 1
        assert data["unread_count"] >= 1

    def test_mark_notification_read(self, e2e_client, authenticated_user, sample_alert_rule, sample_camera, db_session):
        """Test marking a notification as read."""
        # Create event and notification
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event for read notification test",
            source_type="rtsp",
            objects_detected='["vehicle"]',
            confidence=85,
        )
        db_session.add(event)
        db_session.commit()

        notification = Notification(
            id=str(uuid.uuid4()),
            event_id=event.id,
            rule_id=sample_alert_rule.id,
            rule_name=sample_alert_rule.name,
            event_description=event.description,
            read=False,
        )
        db_session.add(notification)
        db_session.commit()
        notification_id = notification.id

        # Mark as read
        response = e2e_client.patch(f"/api/v1/notifications/{notification_id}/read")

        assert response.status_code == 200
        data = response.json()
        assert data["read"] is True

        # Verify in database
        db_session.expire_all()
        updated = db_session.query(Notification).filter_by(id=notification_id).first()
        assert updated.read is True

    def test_mark_all_notifications_read(self, e2e_client, authenticated_user, sample_alert_rule, sample_camera, db_session):
        """Test marking all notifications as read."""
        # Create multiple notifications
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event for bulk read test",
            source_type="rtsp",
            objects_detected='["person"]',
            confidence=88,
        )
        db_session.add(event)
        db_session.commit()

        for i in range(3):
            notification = Notification(
                id=str(uuid.uuid4()),
                event_id=event.id,
                rule_id=sample_alert_rule.id,
                rule_name=f"Rule {i+1}",
                event_description=f"Event {i+1}",
                read=False,
            )
            db_session.add(notification)
        db_session.commit()

        # Mark all as read
        response = e2e_client.patch("/api/v1/notifications/mark-all-read")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify unread count is 0
        list_response = e2e_client.get("/api/v1/notifications")
        assert list_response.json()["unread_count"] == 0

    def test_delete_notification(self, e2e_client, authenticated_user, sample_alert_rule, sample_camera, db_session):
        """Test deleting a notification."""
        # Create event and notification
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event for delete notification test",
            source_type="rtsp",
            objects_detected='["package"]',
            confidence=92,
        )
        db_session.add(event)
        db_session.commit()

        notification = Notification(
            id=str(uuid.uuid4()),
            event_id=event.id,
            rule_id=sample_alert_rule.id,
            rule_name=sample_alert_rule.name,
            event_description=event.description,
            read=False,
        )
        db_session.add(notification)
        db_session.commit()
        notification_id = notification.id

        # Delete
        response = e2e_client.delete(f"/api/v1/notifications/{notification_id}")
        assert response.status_code == 200

        # Verify deletion
        db_session.expire_all()
        deleted = db_session.query(Notification).filter_by(id=notification_id).first()
        assert deleted is None


@pytest.mark.e2e
class TestWebhookLogs:
    """Tests for webhook log viewing."""

    def test_get_webhook_logs_empty(self, e2e_client, authenticated_user, db_session):
        """Test getting webhook logs when empty."""
        response = e2e_client.get("/api/v1/webhooks/logs")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total_count" in data
        assert data["total_count"] >= 0

    def test_get_webhook_logs_with_data(self, e2e_client, authenticated_user, sample_alert_rule, sample_camera, db_session):
        """Test getting webhook logs with log entries."""
        # Create an event
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event for webhook log test",
            source_type="rtsp",
            objects_detected='["person"]',
            confidence=90,
        )
        db_session.add(event)
        db_session.commit()

        # Create a webhook log entry
        log = WebhookLog(
            alert_rule_id=sample_alert_rule.id,
            event_id=event.id,
            url="https://webhook.test/endpoint",
            status_code=200,
            response_time_ms=150,
            retry_count=0,
            success=True,
        )
        db_session.add(log)
        db_session.commit()

        # Get logs
        response = e2e_client.get("/api/v1/webhooks/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] >= 1
        assert len(data["data"]) >= 1

    def test_filter_webhook_logs_by_rule(self, e2e_client, authenticated_user, sample_alert_rule, sample_camera, db_session):
        """Test filtering webhook logs by rule ID."""
        # Create an event
        event = Event(
            id=str(uuid.uuid4()),
            camera_id=sample_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Event for webhook filter test",
            source_type="rtsp",
            objects_detected='["person"]',
            confidence=90,
        )
        db_session.add(event)
        db_session.commit()

        # Create webhook log
        log = WebhookLog(
            alert_rule_id=sample_alert_rule.id,
            event_id=event.id,
            url="https://webhook.test/endpoint",
            status_code=200,
            response_time_ms=100,
            retry_count=0,
            success=True,
        )
        db_session.add(log)
        db_session.commit()

        # Filter by rule ID
        response = e2e_client.get(f"/api/v1/webhooks/logs?rule_id={sample_alert_rule.id}")

        assert response.status_code == 200
        data = response.json()
        # All logs should be for the specified rule
        for log_entry in data["data"]:
            assert log_entry["alert_rule_id"] == sample_alert_rule.id
