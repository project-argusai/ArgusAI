"""
Tests for Story P4-7.3: Anomaly threshold condition in alert engine

Tests the anomaly_threshold condition in alert rule evaluation:
- Rule triggers when event anomaly_score >= threshold
- Rule doesn't trigger when score < threshold
- Rule doesn't trigger when anomaly_score is None
- Combination with other rule conditions
"""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.camera import Camera
from app.models.alert_rule import AlertRule
from app.services.alert_engine import AlertEngine


def make_uuid() -> str:
    """Generate a unique UUID for test data."""
    return str(uuid.uuid4())


@pytest.fixture
def camera(db_session: Session) -> Camera:
    """Create a test camera."""
    camera = Camera(
        id=make_uuid(),
        name="Anomaly Test Camera",
        rtsp_url="rtsp://test:test@localhost:554/stream",
        is_enabled=True
    )
    db_session.add(camera)
    db_session.commit()
    return camera


@pytest.fixture
def anomaly_rule(db_session: Session, camera: Camera) -> AlertRule:
    """Create an alert rule with anomaly threshold."""
    rule = AlertRule(
        id=make_uuid(),
        name="High Anomaly Alert",
        description="Alert on high anomaly events",
        is_enabled=True,
        conditions={
            "anomaly_threshold": 0.6,  # Alert on high anomaly
            "cameras": [camera.id],
        },
        actions=[{"type": "log", "message": "High anomaly detected"}]
    )
    db_session.add(rule)
    db_session.commit()
    return rule


@pytest.fixture
def combined_rule(db_session: Session, camera: Camera) -> AlertRule:
    """Create a rule combining anomaly with object type."""
    rule = AlertRule(
        id=make_uuid(),
        name="Unusual Person Alert",
        description="Alert on unusual person detection",
        is_enabled=True,
        conditions={
            "anomaly_threshold": 0.5,
            "object_types": ["person"],
            "cameras": [camera.id],
        },
        actions=[{"type": "log", "message": "Unusual person detected"}]
    )
    db_session.add(rule)
    db_session.commit()
    return rule


class TestAnomalyThresholdCondition:
    """Tests for anomaly_threshold condition in alert rules."""

    def test_rule_matches_when_score_exceeds_threshold(
        self,
        db_session: Session,
        camera: Camera,
        anomaly_rule: AlertRule
    ):
        """Test rule matches when anomaly_score >= threshold."""
        event = Event(
            id=make_uuid(),
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            description="High anomaly event",
            confidence=85,
            objects_detected='["person"]',
            anomaly_score=0.75,  # Above 0.6 threshold
            source_type="protect"
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(anomaly_rule, event)

        assert matched is True
        assert details["conditions_checked"]["anomaly_threshold"] is True

    def test_rule_matches_at_exact_threshold(
        self,
        db_session: Session,
        camera: Camera,
        anomaly_rule: AlertRule
    ):
        """Test rule matches when anomaly_score equals threshold exactly."""
        event = Event(
            id=make_uuid(),
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Exactly at threshold",
            confidence=85,
            objects_detected='["person"]',
            anomaly_score=0.6,  # Exactly at threshold
            source_type="protect"
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(anomaly_rule, event)

        assert matched is True

    def test_rule_no_match_below_threshold(
        self,
        db_session: Session,
        camera: Camera,
        anomaly_rule: AlertRule
    ):
        """Test rule doesn't match when anomaly_score < threshold."""
        event = Event(
            id=make_uuid(),
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Low anomaly event",
            confidence=85,
            objects_detected='["person"]',
            anomaly_score=0.3,  # Below 0.6 threshold
            source_type="protect"
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(anomaly_rule, event)

        assert matched is False
        assert details["conditions_checked"]["anomaly_threshold"] is False

    def test_rule_no_match_when_score_is_none(
        self,
        db_session: Session,
        camera: Camera,
        anomaly_rule: AlertRule
    ):
        """Test rule doesn't match when anomaly_score is None."""
        event = Event(
            id=make_uuid(),
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            description="No anomaly score",
            confidence=85,
            objects_detected='["person"]',
            anomaly_score=None,
            source_type="protect"
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(anomaly_rule, event)

        assert matched is False
        assert details["conditions_checked"]["anomaly_threshold"] is False

    def test_rule_without_anomaly_threshold_passes(
        self,
        db_session: Session,
        camera: Camera
    ):
        """Test rule without anomaly_threshold passes anomaly check."""
        rule = AlertRule(
            id=make_uuid(),
            name="No Anomaly Rule",
            is_enabled=True,
            conditions={
                "cameras": [camera.id],
            },
            actions=[{"type": "log", "message": "Basic alert"}]
        )
        db_session.add(rule)
        db_session.commit()

        event = Event(
            id=make_uuid(),
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Basic event",
            confidence=85,
            objects_detected='["person"]',
            anomaly_score=0.1,  # Low score, but rule has no threshold
            source_type="protect"
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, event)

        # Should match since no anomaly threshold is set
        assert matched is True
        assert details["conditions_checked"]["anomaly_threshold"] is True


class TestCombinedConditions:
    """Tests for anomaly_threshold combined with other conditions."""

    def test_anomaly_and_object_type_both_match(
        self,
        db_session: Session,
        camera: Camera,
        combined_rule: AlertRule
    ):
        """Test rule matches when both anomaly and object type match."""
        event = Event(
            id=make_uuid(),
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Unusual person detected",
            confidence=85,
            objects_detected='["person"]',
            anomaly_score=0.65,
            source_type="protect"
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(combined_rule, event)

        assert matched is True

    def test_anomaly_match_but_object_type_no_match(
        self,
        db_session: Session,
        camera: Camera,
        combined_rule: AlertRule
    ):
        """Test rule doesn't match when anomaly matches but object type doesn't."""
        event = Event(
            id=make_uuid(),
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Unusual vehicle detected",
            confidence=85,
            objects_detected='["vehicle"]',  # Not "person"
            anomaly_score=0.65,  # Above threshold
            source_type="protect"
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(combined_rule, event)

        assert matched is False

    def test_object_type_match_but_anomaly_no_match(
        self,
        db_session: Session,
        camera: Camera,
        combined_rule: AlertRule
    ):
        """Test rule doesn't match when object type matches but anomaly doesn't."""
        event = Event(
            id=make_uuid(),
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Normal person walking",
            confidence=85,
            objects_detected='["person"]',  # Correct object
            anomaly_score=0.2,  # Below threshold
            source_type="protect"
        )
        db_session.add(event)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(combined_rule, event)

        assert matched is False


class TestCheckAnomalyThresholdMethod:
    """Direct tests for _check_anomaly_threshold method."""

    def test_returns_true_when_no_threshold(self, db_session: Session):
        """Test returns True when anomaly_threshold is None."""
        engine = AlertEngine(db_session)
        result = engine._check_anomaly_threshold(
            event_anomaly_score=0.1,
            anomaly_threshold=None
        )
        assert result is True

    def test_returns_false_when_score_is_none(self, db_session: Session):
        """Test returns False when event has no anomaly score."""
        engine = AlertEngine(db_session)
        result = engine._check_anomaly_threshold(
            event_anomaly_score=None,
            anomaly_threshold=0.5
        )
        assert result is False

    def test_returns_true_when_score_meets_threshold(self, db_session: Session):
        """Test returns True when score >= threshold."""
        engine = AlertEngine(db_session)

        # Exactly at threshold
        assert engine._check_anomaly_threshold(0.5, 0.5) is True

        # Above threshold
        assert engine._check_anomaly_threshold(0.8, 0.5) is True

    def test_returns_false_when_score_below_threshold(self, db_session: Session):
        """Test returns False when score < threshold."""
        engine = AlertEngine(db_session)
        result = engine._check_anomaly_threshold(
            event_anomaly_score=0.3,
            anomaly_threshold=0.5
        )
        assert result is False
