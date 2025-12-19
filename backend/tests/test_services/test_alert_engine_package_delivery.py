"""Tests for Package Delivery Alert Rules (Story P7-2.2)"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from app.models.alert_rule import AlertRule
from app.models.event import Event
from app.services.alert_engine import AlertEngine


class TestPackageDeliveryRuleEvaluation:
    """Test suite for package delivery rule type (Story P7-2.2)"""

    @pytest.fixture
    def package_delivery_event(self, db_session):
        """Create a package delivery event with carrier identified"""
        event = Event(
            id="test-package-event-001",
            camera_id="camera-001",
            timestamp=datetime(2025, 12, 19, 14, 30, 0, tzinfo=timezone.utc),
            description="FedEx delivery driver placing package at front door",
            confidence=90,
            objects_detected=json.dumps(["person", "package"]),
            smart_detection_type="package",
            delivery_carrier="fedex",
            alert_triggered=False
        )
        db_session.add(event)
        db_session.commit()
        return event

    @pytest.fixture
    def package_event_no_carrier(self, db_session):
        """Create a package detection event without carrier identification"""
        event = Event(
            id="test-package-event-002",
            camera_id="camera-001",
            timestamp=datetime(2025, 12, 19, 14, 30, 0, tzinfo=timezone.utc),
            description="Person placing package at front door",
            confidence=85,
            objects_detected=json.dumps(["person", "package"]),
            smart_detection_type="package",
            delivery_carrier=None,  # No carrier identified
            alert_triggered=False
        )
        db_session.add(event)
        db_session.commit()
        return event

    @pytest.fixture
    def person_event(self, db_session):
        """Create a person detection event (not package)"""
        event = Event(
            id="test-person-event-001",
            camera_id="camera-001",
            timestamp=datetime(2025, 12, 19, 14, 30, 0, tzinfo=timezone.utc),
            description="Person walking in front yard",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            smart_detection_type="person",
            delivery_carrier=None,
            alert_triggered=False
        )
        db_session.add(event)
        db_session.commit()
        return event

    @pytest.fixture
    def package_delivery_rule(self, db_session):
        """Create a package delivery alert rule"""
        rule = AlertRule(
            id="test-rule-pkg-001",
            name="Package Delivery Alert",
            is_enabled=True,
            conditions=json.dumps({
                "rule_type": "package_delivery",
                "min_confidence": 70
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()
        return rule

    @pytest.fixture
    def package_delivery_rule_specific_carriers(self, db_session):
        """Create a package delivery rule that only matches FedEx and UPS"""
        rule = AlertRule(
            id="test-rule-pkg-002",
            name="FedEx/UPS Package Alert",
            is_enabled=True,
            conditions=json.dumps({
                "rule_type": "package_delivery",
                "carriers": ["fedex", "ups"],
                "min_confidence": 70
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()
        return rule

    @pytest.fixture
    def any_detection_rule(self, db_session):
        """Create a regular 'any' detection rule"""
        rule = AlertRule(
            id="test-rule-any-001",
            name="Any Detection Alert",
            is_enabled=True,
            conditions=json.dumps({
                "rule_type": "any",
                "object_types": ["person", "package"],
                "min_confidence": 70
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()
        return rule

    def test_package_delivery_rule_matches_package_with_carrier(
        self, db_session, package_delivery_event, package_delivery_rule
    ):
        """Test that package_delivery rule matches when package + carrier detected"""
        engine = AlertEngine(db_session)

        matched, details = engine.evaluate_rule(package_delivery_rule, package_delivery_event)

        assert matched is True
        assert details["conditions_checked"]["rule_type"] is True
        assert details["conditions_checked"]["carriers"] is True
        assert details["conditions_checked"]["min_confidence"] is True

    def test_package_delivery_rule_fails_without_carrier(
        self, db_session, package_event_no_carrier, package_delivery_rule
    ):
        """Test that package_delivery rule fails when carrier not identified"""
        engine = AlertEngine(db_session)

        matched, details = engine.evaluate_rule(package_delivery_rule, package_event_no_carrier)

        assert matched is False
        assert details["conditions_checked"]["rule_type"] is False

    def test_package_delivery_rule_fails_for_person_event(
        self, db_session, person_event, package_delivery_rule
    ):
        """Test that package_delivery rule fails for non-package events"""
        engine = AlertEngine(db_session)

        matched, details = engine.evaluate_rule(package_delivery_rule, person_event)

        assert matched is False
        assert details["conditions_checked"]["rule_type"] is False

    def test_carrier_filter_matches_fedex(
        self, db_session, package_delivery_event, package_delivery_rule_specific_carriers
    ):
        """Test carrier filter matches when event carrier is in list (FedEx)"""
        engine = AlertEngine(db_session)

        # Event has delivery_carrier = "fedex", rule has carriers = ["fedex", "ups"]
        matched, details = engine.evaluate_rule(
            package_delivery_rule_specific_carriers, package_delivery_event
        )

        assert matched is True
        assert details["conditions_checked"]["carriers"] is True

    def test_carrier_filter_fails_for_amazon(self, db_session):
        """Test carrier filter fails when carrier not in list"""
        # Create Amazon delivery event
        event = Event(
            id="test-amazon-event",
            camera_id="camera-001",
            timestamp=datetime(2025, 12, 19, 14, 30, 0, tzinfo=timezone.utc),
            description="Amazon delivery",
            confidence=90,
            objects_detected=json.dumps(["person", "package"]),
            smart_detection_type="package",
            delivery_carrier="amazon",  # Amazon is NOT in the carrier list
            alert_triggered=False
        )
        db_session.add(event)

        # Rule only matches FedEx and UPS
        rule = AlertRule(
            id="test-rule-pkg-fedex-ups",
            name="FedEx/UPS Only",
            is_enabled=True,
            conditions=json.dumps({
                "rule_type": "package_delivery",
                "carriers": ["fedex", "ups"]
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, event)

        assert matched is False
        assert details["conditions_checked"]["carriers"] is False

    def test_empty_carrier_list_matches_any_carrier(self, db_session, package_delivery_event):
        """Test that empty/null carrier list matches any carrier"""
        rule = AlertRule(
            id="test-rule-any-carrier",
            name="Any Carrier Alert",
            is_enabled=True,
            conditions=json.dumps({
                "rule_type": "package_delivery",
                "carriers": None,  # No carrier filter = match any
                "min_confidence": 70
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, package_delivery_event)

        assert matched is True
        assert details["conditions_checked"]["carriers"] is True

    def test_any_rule_type_matches_package_delivery(
        self, db_session, package_delivery_event, any_detection_rule
    ):
        """Test that 'any' rule type still matches package delivery events"""
        engine = AlertEngine(db_session)

        matched, details = engine.evaluate_rule(any_detection_rule, package_delivery_event)

        assert matched is True
        assert details["conditions_checked"]["rule_type"] is True
        assert details["conditions_checked"]["object_types"] is True

    def test_any_rule_type_matches_regular_person(
        self, db_session, person_event, any_detection_rule
    ):
        """Test that 'any' rule type matches regular events"""
        engine = AlertEngine(db_session)

        matched, details = engine.evaluate_rule(any_detection_rule, person_event)

        assert matched is True
        assert details["conditions_checked"]["rule_type"] is True

    def test_default_rule_type_is_any(self, db_session, person_event):
        """Test that missing rule_type defaults to 'any' behavior"""
        rule = AlertRule(
            id="test-rule-no-type",
            name="No Type Specified",
            is_enabled=True,
            conditions=json.dumps({
                # No rule_type specified
                "object_types": ["person"],
                "min_confidence": 70
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, person_event)

        assert matched is True
        assert details["conditions_checked"]["rule_type"] is True

    def test_case_insensitive_carrier_matching(self, db_session):
        """Test that carrier matching is case-insensitive"""
        # Event with uppercase carrier
        event = Event(
            id="test-uppercase-carrier",
            camera_id="camera-001",
            timestamp=datetime.now(timezone.utc),
            description="USPS delivery",
            confidence=90,
            objects_detected=json.dumps(["package"]),
            smart_detection_type="package",
            delivery_carrier="USPS",  # Uppercase
            alert_triggered=False
        )
        db_session.add(event)

        # Rule with lowercase carriers
        rule = AlertRule(
            id="test-rule-lowercase",
            name="Lowercase Carriers",
            is_enabled=True,
            conditions=json.dumps({
                "rule_type": "package_delivery",
                "carriers": ["usps", "fedex"]  # Lowercase
            }),
            actions=json.dumps({"dashboard_notification": True}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        engine = AlertEngine(db_session)
        matched, details = engine.evaluate_rule(rule, event)

        assert matched is True
        assert details["conditions_checked"]["carriers"] is True


class TestCarrierInPayloads:
    """Test carrier information in webhook and MQTT payloads (AC4, AC5)"""

    @pytest.fixture
    def package_event_with_carrier(self, db_session):
        """Create a package delivery event"""
        event = Event(
            id="test-pkg-payload-001",
            camera_id="camera-001",
            timestamp=datetime(2025, 12, 19, 14, 30, 0, tzinfo=timezone.utc),
            description="UPS delivery at front door",
            confidence=90,
            objects_detected=json.dumps(["package"]),
            smart_detection_type="package",
            delivery_carrier="ups",
            alert_triggered=False
        )
        db_session.add(event)
        db_session.commit()
        return event

    def test_webhook_payload_includes_carrier(self, db_session, package_event_with_carrier):
        """Test that webhook payload includes delivery_carrier and delivery_carrier_display"""
        from app.services.webhook_service import WebhookService

        rule = AlertRule(
            id="test-webhook-rule",
            name="Webhook Test Rule",
            is_enabled=True,
            conditions=json.dumps({}),
            actions=json.dumps({
                "webhook": {"url": "https://example.com/webhook"}
            }),
            cooldown_minutes=5
        )

        service = WebhookService(db_session)
        payload = service.build_payload(package_event_with_carrier, rule)

        assert "delivery_carrier" in payload
        assert payload["delivery_carrier"] == "ups"
        assert "delivery_carrier_display" in payload
        assert payload["delivery_carrier_display"] == "UPS"

    def test_mqtt_payload_includes_carrier(self, db_session, package_event_with_carrier):
        """Test that MQTT payload includes delivery_carrier and delivery_carrier_display"""
        from app.services.mqtt_service import serialize_event_for_mqtt

        payload = serialize_event_for_mqtt(
            package_event_with_carrier,
            camera_name="Front Door",
            api_base_url="http://localhost:8000"
        )

        assert "delivery_carrier" in payload
        assert payload["delivery_carrier"] == "ups"
        assert "delivery_carrier_display" in payload
        assert payload["delivery_carrier_display"] == "UPS"

    def test_webhook_payload_excludes_carrier_when_none(self, db_session):
        """Test that webhook payload excludes carrier fields when not set"""
        from app.services.webhook_service import WebhookService

        # Event without carrier
        event = Event(
            id="test-no-carrier",
            camera_id="camera-001",
            timestamp=datetime.now(timezone.utc),
            description="Person detected",
            confidence=80,
            objects_detected=json.dumps(["person"]),
            smart_detection_type="person",
            delivery_carrier=None,
            alert_triggered=False
        )
        db_session.add(event)

        rule = AlertRule(
            id="test-webhook-rule-2",
            name="Webhook Test",
            is_enabled=True,
            conditions=json.dumps({}),
            actions=json.dumps({}),
            cooldown_minutes=5
        )
        db_session.add(rule)
        db_session.commit()

        service = WebhookService(db_session)
        payload = service.build_payload(event, rule)

        assert "delivery_carrier" not in payload
        assert "delivery_carrier_display" not in payload


class TestAlertRuleConditionsSchema:
    """Test schema validation for rule_type and carriers (AC1, AC2)"""

    def test_valid_rule_type_any(self):
        """Test schema accepts rule_type='any'"""
        from app.schemas.alert_rule import AlertRuleConditions

        conditions = AlertRuleConditions(rule_type="any")
        assert conditions.rule_type == "any"

    def test_valid_rule_type_package_delivery(self):
        """Test schema accepts rule_type='package_delivery'"""
        from app.schemas.alert_rule import AlertRuleConditions

        conditions = AlertRuleConditions(
            rule_type="package_delivery",
            carriers=["fedex", "ups"]
        )
        assert conditions.rule_type == "package_delivery"
        assert conditions.carriers == ["fedex", "ups"]

    def test_invalid_rule_type_rejected(self):
        """Test schema rejects invalid rule_type"""
        from app.schemas.alert_rule import AlertRuleConditions
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            AlertRuleConditions(rule_type="invalid_type")

        assert "rule_type" in str(exc_info.value)

    def test_valid_carriers(self):
        """Test schema accepts valid carrier values"""
        from app.schemas.alert_rule import AlertRuleConditions

        conditions = AlertRuleConditions(
            carriers=["fedex", "ups", "usps", "amazon", "dhl"]
        )
        assert len(conditions.carriers) == 5

    def test_invalid_carrier_rejected(self):
        """Test schema rejects invalid carrier value"""
        from app.schemas.alert_rule import AlertRuleConditions
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            AlertRuleConditions(carriers=["fedex", "invalid_carrier"])

        assert "carrier" in str(exc_info.value).lower()

    def test_default_rule_type(self):
        """Test default rule_type is 'any'"""
        from app.schemas.alert_rule import AlertRuleConditions

        conditions = AlertRuleConditions()
        assert conditions.rule_type == "any"

    def test_none_carriers_allowed(self):
        """Test carriers can be None (match any carrier)"""
        from app.schemas.alert_rule import AlertRuleConditions

        conditions = AlertRuleConditions(
            rule_type="package_delivery",
            carriers=None
        )
        assert conditions.carriers is None
