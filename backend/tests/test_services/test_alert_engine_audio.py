"""Tests for AlertEngine Audio Event Type Matching (Story P6-3.2)

Tests the alert engine integration with audio event types:
- Audio event type matching in rule conditions (AC#5)
- Alert triggering for audio events same as visual events (AC#5)
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.alert_engine import AlertEngine
from app.models.alert_rule import AlertRule
from app.models.event import Event


class TestAlertEngineAudioEventTypeMatching:
    """Tests for audio event type matching in AlertEngine"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session"""
        return MagicMock()

    @pytest.fixture
    def alert_engine(self, mock_db):
        """Create AlertEngine instance with mock db"""
        return AlertEngine(mock_db)

    def test_check_audio_event_types_no_filter(self, alert_engine):
        """Test no audio filter matches any event (including no audio)"""
        # No filter (None)
        result = alert_engine._check_audio_event_types("glass_break", None)
        assert result is True

        # Empty list
        result = alert_engine._check_audio_event_types("glass_break", [])
        assert result is True

        # Event without audio
        result = alert_engine._check_audio_event_types(None, None)
        assert result is True

    def test_check_audio_event_types_with_filter_no_audio(self, alert_engine):
        """Test audio filter requires event to have audio"""
        # Rule has filter but event has no audio = no match
        result = alert_engine._check_audio_event_types(None, ["glass_break"])
        assert result is False

    def test_check_audio_event_types_match(self, alert_engine):
        """AC#5: Test audio event type matching"""
        # Exact match
        result = alert_engine._check_audio_event_types("glass_break", ["glass_break"])
        assert result is True

        # Match in list
        result = alert_engine._check_audio_event_types(
            "gunshot",
            ["glass_break", "gunshot", "scream"]
        )
        assert result is True

    def test_check_audio_event_types_no_match(self, alert_engine):
        """Test audio event type not matching"""
        result = alert_engine._check_audio_event_types(
            "doorbell",
            ["glass_break", "gunshot"]
        )
        assert result is False

    def test_check_audio_event_types_case_insensitive(self, alert_engine):
        """Test audio type matching is case insensitive"""
        result = alert_engine._check_audio_event_types("GLASS_BREAK", ["glass_break"])
        assert result is True

        result = alert_engine._check_audio_event_types("glass_break", ["GLASS_BREAK"])
        assert result is True

        result = alert_engine._check_audio_event_types("Glass_Break", ["GLASS_BREAK"])
        assert result is True

    def test_evaluate_rule_with_audio_filter_match(self, alert_engine, mock_db):
        """AC#5: Test rule evaluation with audio filter - match"""
        # Create rule with audio filter
        rule = AlertRule(
            id="test-rule-1",
            name="Glass Break Alert",
            is_enabled=True,
            conditions=json.dumps({
                "audio_event_types": ["glass_break"]
            }),
            actions='{}',
            cooldown_minutes=5
        )

        # Create event with audio
        event = Event(
            id="event-1",
            camera_id="camera-1",
            timestamp=datetime.now(timezone.utc),
            description="Audio event detected",
            confidence=80,
            objects_detected=json.dumps(["audio_event"]),
        )
        event.audio_event_type = "glass_break"
        event.audio_confidence = 0.85
        event.anomaly_score = None
        event.matched_entity_ids = None

        matched, details = alert_engine.evaluate_rule(rule, event)

        assert matched is True
        assert details["conditions_checked"]["audio_event_types"] is True

    def test_evaluate_rule_with_audio_filter_no_match(self, alert_engine, mock_db):
        """AC#5: Test rule evaluation with audio filter - no match"""
        # Create rule with audio filter
        rule = AlertRule(
            id="test-rule-2",
            name="Gunshot Alert",
            is_enabled=True,
            conditions=json.dumps({
                "audio_event_types": ["gunshot"]
            }),
            actions='{}',
            cooldown_minutes=5
        )

        # Create event with different audio type
        event = Event(
            id="event-2",
            camera_id="camera-1",
            timestamp=datetime.now(timezone.utc),
            description="Audio event detected",
            confidence=80,
            objects_detected=json.dumps(["audio_event"]),
        )
        event.audio_event_type = "doorbell"
        event.audio_confidence = 0.90
        event.anomaly_score = None
        event.matched_entity_ids = None

        matched, details = alert_engine.evaluate_rule(rule, event)

        assert matched is False
        assert details["conditions_checked"]["audio_event_types"] is False

    def test_evaluate_rule_with_audio_filter_no_audio_event(self, alert_engine, mock_db):
        """Test rule with audio filter doesn't match event without audio"""
        # Create rule with audio filter
        rule = AlertRule(
            id="test-rule-3",
            name="Any Audio Alert",
            is_enabled=True,
            conditions=json.dumps({
                "audio_event_types": ["glass_break", "gunshot", "scream"]
            }),
            actions='{}',
            cooldown_minutes=5
        )

        # Create event WITHOUT audio
        event = Event(
            id="event-3",
            camera_id="camera-1",
            timestamp=datetime.now(timezone.utc),
            description="Motion detected",
            confidence=80,
            objects_detected=json.dumps(["person"]),
        )
        event.audio_event_type = None  # No audio
        event.audio_confidence = None
        event.anomaly_score = None
        event.matched_entity_ids = None

        matched, details = alert_engine.evaluate_rule(rule, event)

        assert matched is False
        assert details["conditions_checked"]["audio_event_types"] is False

    def test_evaluate_rule_no_audio_filter(self, alert_engine, mock_db):
        """Test rule without audio filter matches events with or without audio"""
        # Create rule without audio filter
        rule = AlertRule(
            id="test-rule-4",
            name="Person Alert",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person"]
            }),
            actions='{}',
            cooldown_minutes=5
        )

        # Event with audio
        event_with_audio = Event(
            id="event-4a",
            camera_id="camera-1",
            timestamp=datetime.now(timezone.utc),
            description="Person detected with audio",
            confidence=80,
            objects_detected=json.dumps(["person"]),
        )
        event_with_audio.audio_event_type = "scream"
        event_with_audio.audio_confidence = 0.85
        event_with_audio.anomaly_score = None
        event_with_audio.matched_entity_ids = None

        matched1, details1 = alert_engine.evaluate_rule(rule, event_with_audio)
        assert matched1 is True

        # Event without audio
        event_no_audio = Event(
            id="event-4b",
            camera_id="camera-1",
            timestamp=datetime.now(timezone.utc),
            description="Person detected",
            confidence=80,
            objects_detected=json.dumps(["person"]),
        )
        event_no_audio.audio_event_type = None
        event_no_audio.audio_confidence = None
        event_no_audio.anomaly_score = None
        event_no_audio.matched_entity_ids = None

        matched2, details2 = alert_engine.evaluate_rule(rule, event_no_audio)
        assert matched2 is True

    def test_evaluate_rule_combined_audio_and_object_filters(self, alert_engine, mock_db):
        """Test rule with both audio and object filters (AND logic)"""
        # Create rule with audio AND object filter
        rule = AlertRule(
            id="test-rule-5",
            name="Person with Glass Break",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person"],
                "audio_event_types": ["glass_break"]
            }),
            actions='{}',
            cooldown_minutes=5
        )

        # Event with both person AND glass_break audio - should match
        event_both = Event(
            id="event-5a",
            camera_id="camera-1",
            timestamp=datetime.now(timezone.utc),
            description="Person with glass break",
            confidence=80,
            objects_detected=json.dumps(["person"]),
        )
        event_both.audio_event_type = "glass_break"
        event_both.audio_confidence = 0.85
        event_both.anomaly_score = None
        event_both.matched_entity_ids = None

        matched1, _ = alert_engine.evaluate_rule(rule, event_both)
        assert matched1 is True

        # Event with person but NO audio - should not match
        event_person_only = Event(
            id="event-5b",
            camera_id="camera-1",
            timestamp=datetime.now(timezone.utc),
            description="Person detected",
            confidence=80,
            objects_detected=json.dumps(["person"]),
        )
        event_person_only.audio_event_type = None
        event_person_only.audio_confidence = None
        event_person_only.anomaly_score = None
        event_person_only.matched_entity_ids = None

        matched2, details2 = alert_engine.evaluate_rule(rule, event_person_only)
        assert matched2 is False
        assert details2["conditions_checked"]["audio_event_types"] is False

        # Event with glass_break audio but no person - should not match
        event_audio_only = Event(
            id="event-5c",
            camera_id="camera-1",
            timestamp=datetime.now(timezone.utc),
            description="Audio event",
            confidence=80,
            objects_detected=json.dumps(["audio_event"]),  # Not "person"
        )
        event_audio_only.audio_event_type = "glass_break"
        event_audio_only.audio_confidence = 0.85
        event_audio_only.anomaly_score = None
        event_audio_only.matched_entity_ids = None

        matched3, details3 = alert_engine.evaluate_rule(rule, event_audio_only)
        assert matched3 is False
        assert details3["conditions_checked"]["object_types"] is False


class TestAlertEngineAudioEventIntegration:
    """Integration tests for audio event alerts (AC#5)"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session"""
        db = MagicMock()
        return db

    def test_evaluate_all_rules_includes_audio_events(self, mock_db):
        """AC#5: Test audio events trigger alerts like visual events"""
        # Create rules
        audio_rule = AlertRule(
            id="audio-rule",
            name="Audio Alert",
            is_enabled=True,
            conditions=json.dumps({
                "audio_event_types": ["glass_break", "gunshot"]
            }),
            actions='{}',
            cooldown_minutes=5
        )

        visual_rule = AlertRule(
            id="visual-rule",
            name="Person Alert",
            is_enabled=True,
            conditions=json.dumps({
                "object_types": ["person"]
            }),
            actions='{}',
            cooldown_minutes=5
        )

        # Mock query to return rules
        mock_db.query.return_value.filter.return_value.all.return_value = [
            audio_rule,
            visual_rule
        ]

        # Create audio event
        audio_event = Event(
            id="audio-event",
            camera_id="camera-1",
            timestamp=datetime.now(timezone.utc),
            description="Audio event detected",
            confidence=80,
            objects_detected=json.dumps(["audio_event"]),
        )
        audio_event.audio_event_type = "glass_break"
        audio_event.audio_confidence = 0.85
        audio_event.anomaly_score = None
        audio_event.matched_entity_ids = None

        engine = AlertEngine(mock_db)
        matched_rules = engine.evaluate_all_rules(audio_event)

        # Audio rule should match (has glass_break filter)
        assert audio_rule in matched_rules

        # Visual rule should NOT match (no person in objects_detected)
        assert visual_rule not in matched_rules
