"""Tests for Alert Engine Service (Epic 5)"""
import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock

from app.models.alert_rule import AlertRule, WebhookLog
from app.models.event import Event
from app.services.alert_engine import AlertEngine


class TestAlertRuleEvaluation:
    """Test suite for rule evaluation logic"""

    @pytest.fixture
    def sample_event(self, db_session):
        """Create a sample event for testing"""
        event = Event(
            id="test-event-123",
            camera_id="camera-001",
            timestamp=datetime(2025, 11, 17, 14, 30, 0, tzinfo=timezone.utc),
            description="Person walking towards door with package",
            confidence=85,
            objects_detected=json.dumps(["person", "package"]),
            alert_triggered=False
        )
        db_session.add(event)
        db_session.commit()
        return event

    @pytest.fixture
    def sample_rule(self, db_session):
        """Create a sample alert rule for testing"""
        rule = AlertRule(
            id="test-rule-001",
            name="Package Alert",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person", "package"],
                "cameras": [],
                "min_confidence": 70
            }),
            actions=json.dumps({
                "dashboard_notification": True
            }),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()
        return rule

    def test_evaluate_rule_matches(self, db_session, sample_event, sample_rule):
        """Test that rule matches when all conditions are met"""
        engine = AlertEngine(db_session)

        matched, details = engine.evaluate_rule(sample_rule, sample_event)

        assert matched is True
        assert details["cooldown_active"] is False
        assert details["conditions_checked"]["object_types"] is True
        assert details["conditions_checked"]["min_confidence"] is True

    def test_evaluate_rule_fails_on_object_types(self, db_session, sample_event):
        """Test that rule fails when object types don't match"""
        rule = AlertRule(
            id="test-rule-002",
            name="Vehicle Only Alert",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["vehicle"],
                "min_confidence": 50
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, sample_event)

        assert matched is False
        assert details["conditions_checked"]["object_types"] is False

    def test_evaluate_rule_fails_on_confidence(self, db_session, sample_event):
        """Test that rule fails when confidence is below threshold"""
        rule = AlertRule(
            id="test-rule-003",
            name="High Confidence Alert",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person"],
                "min_confidence": 95  # Higher than event's 85
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, sample_event)

        assert matched is False
        assert details["conditions_checked"]["min_confidence"] is False

    def test_evaluate_rule_fails_on_camera(self, db_session, sample_event):
        """Test that rule fails when camera doesn't match"""
        rule = AlertRule(
            id="test-rule-004",
            name="Specific Camera Alert",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person"],
                "cameras": ["camera-999"],  # Different from event's camera
                "min_confidence": 50
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, sample_event)

        assert matched is False
        assert details["conditions_checked"]["cameras"] is False

    def test_evaluate_rule_any_camera_when_empty(self, db_session, sample_event, sample_rule):
        """Test that empty cameras list means any camera matches"""
        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(sample_rule, sample_event)

        assert matched is True
        assert details["conditions_checked"]["cameras"] is True


class TestCooldownEnforcement:
    """Test suite for cooldown logic"""

    @pytest.fixture
    def recent_triggered_rule(self, db_session):
        """Create a rule that was recently triggered"""
        rule = AlertRule(
            id="test-rule-cooldown",
            name="Recently Triggered",
            is_enabled=True,
            conditions=json.dumps({"object_types": ["person"]}),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=10,
            last_triggered_at=datetime.now(timezone.utc) - timedelta(minutes=5)
        )
        db_session.add(rule)
        db_session.commit()
        return rule

    @pytest.fixture
    def expired_cooldown_rule(self, db_session):
        """Create a rule with expired cooldown"""
        rule = AlertRule(
            id="test-rule-expired",
            name="Expired Cooldown",
            is_enabled=True,
            conditions=json.dumps({"object_types": ["person"]}),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=10,
            last_triggered_at=datetime.now(timezone.utc) - timedelta(minutes=15)
        )
        db_session.add(rule)
        db_session.commit()
        return rule

    def test_cooldown_skips_rule(self, db_session, recent_triggered_rule):
        """Test that rule in cooldown is skipped"""
        event = Event(
            id="test-event-cooldown",
            camera_id="camera-001",
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=85,
            objects_detected=json.dumps(["person"])
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(recent_triggered_rule, event)

        assert matched is False
        assert details.get("cooldown_active") is True

    def test_expired_cooldown_evaluates(self, db_session, expired_cooldown_rule):
        """Test that rule with expired cooldown is evaluated"""
        event = Event(
            id="test-event-expired",
            camera_id="camera-001",
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=85,
            objects_detected=json.dumps(["person"])
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(expired_cooldown_rule, event)

        assert matched is True
        assert details.get("cooldown_active") is False


class TestTimeOfDayCondition:
    """Test suite for time-of-day condition logic"""

    def test_time_within_range(self, db_session):
        """Test event within time range matches"""
        rule = AlertRule(
            id="test-rule-time",
            name="Business Hours Alert",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person"],
                "time_of_day": {"start": "09:00", "end": "17:00"}
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        # Event at 14:30 - within range
        event = Event(
            id="test-event-time",
            camera_id="camera-001",
            timestamp=datetime(2025, 11, 17, 14, 30, 0, tzinfo=timezone.utc),
            description="Test event",
            confidence=85,
            objects_detected=json.dumps(["person"])
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, event)

        assert matched is True
        assert details["conditions_checked"]["time_of_day"] is True

    def test_time_outside_range(self, db_session):
        """Test event outside time range fails"""
        rule = AlertRule(
            id="test-rule-time-out",
            name="Business Hours Alert",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person"],
                "time_of_day": {"start": "09:00", "end": "17:00"}
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        # Event at 20:00 - outside range
        event = Event(
            id="test-event-time-out",
            camera_id="camera-001",
            timestamp=datetime(2025, 11, 17, 20, 0, 0, tzinfo=timezone.utc),
            description="Test event",
            confidence=85,
            objects_detected=json.dumps(["person"])
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, event)

        assert matched is False
        assert details["conditions_checked"]["time_of_day"] is False


class TestDaysOfWeekCondition:
    """Test suite for days-of-week condition logic"""

    def test_day_matches(self, db_session):
        """Test event on matching day"""
        rule = AlertRule(
            id="test-rule-day",
            name="Weekday Alert",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person"],
                "days_of_week": [1, 2, 3, 4, 5]  # Mon-Fri
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        # Monday event (weekday() = 0, so +1 = 1)
        event = Event(
            id="test-event-day",
            camera_id="camera-001",
            timestamp=datetime(2025, 11, 17, 14, 30, 0, tzinfo=timezone.utc),  # Monday
            description="Test event",
            confidence=85,
            objects_detected=json.dumps(["person"])
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, event)

        assert matched is True
        assert details["conditions_checked"]["days_of_week"] is True


class TestEvaluateAllRules:
    """Test suite for batch rule evaluation"""

    def test_evaluate_multiple_rules(self, db_session):
        """Test evaluation against multiple rules"""
        # Create multiple rules
        rule1 = AlertRule(
            id="rule-1",
            name="Rule 1 - Will Match",
            is_enabled=True,
            conditions=json.dumps({"object_types": ["person"]}),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        rule2 = AlertRule(
            id="rule-2",
            name="Rule 2 - Will Not Match",
            is_enabled=True,
            conditions=json.dumps({"object_types": ["vehicle"]}),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        rule3 = AlertRule(
            id="rule-3",
            name="Rule 3 - Disabled",
            is_enabled=False,
            conditions=json.dumps({"object_types": ["person"]}),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )

        db_session.add_all([rule1, rule2, rule3])
        db_session.commit()

        event = Event(
            id="test-event-multi",
            camera_id="camera-001",
            timestamp=datetime.now(timezone.utc),
            description="Person detected",
            confidence=85,
            objects_detected=json.dumps(["person"])
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched_rules = engine.evaluate_all_rules(event)

        # Should only match rule1 (rule2 object mismatch, rule3 disabled)
        assert len(matched_rules) == 1
        assert matched_rules[0].id == "rule-1"


class TestObjectTypesORLogic:
    """Test suite for OR logic within object types"""

    def test_any_object_matches(self, db_session):
        """Test that any matching object triggers rule (OR logic)"""
        rule = AlertRule(
            id="rule-or",
            name="Person OR Package",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person", "package", "vehicle"]
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        # Event only has "person", not "package" or "vehicle"
        event = Event(
            id="test-event-or",
            camera_id="camera-001",
            timestamp=datetime.now(timezone.utc),
            description="Just a person",
            confidence=85,
            objects_detected=json.dumps(["person"])  # Only person
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, event)

        assert matched is True  # OR logic - "person" matches


class TestUpdateRuleTriggered:
    """Test suite for rule trigger stats updates"""

    def test_update_trigger_count(self, db_session):
        """Test that trigger count increments"""
        rule = AlertRule(
            id="rule-count",
            name="Counter Test",
            is_enabled=True,
            conditions=json.dumps({}),
            actions=json.dumps({}),
            cooldown_minutes=0,
            trigger_count=5
        )
        db_session.add(rule)
        db_session.commit()

        engine = AlertEngine(db_session)
        engine.update_rule_triggered(rule)

        # Refresh from DB
        db_session.refresh(rule)

        assert rule.trigger_count == 6
        assert rule.last_triggered_at is not None
