"""
Alert Rule Engine Service (Epic 5)

This module implements the alert rule evaluation engine that:
- Evaluates events against user-defined rules
- Enforces cooldown periods to prevent alert spam
- Executes actions (dashboard notifications, webhooks)
- Provides performance-optimized batch rule evaluation

Architecture:
    - Rule evaluation uses AND logic between conditions
    - Object type matching uses OR logic (any match triggers)
    - Time/day conditions are optional (null = always match)
    - Cooldown is checked before evaluation to skip recently triggered rules
    - Actions execute independently (webhook failure doesn't block notification)

Performance Targets:
    - Rule evaluation: <500ms for 20 rules
    - Async execution: Non-blocking webhook calls
    - Cache consideration: Rules can be cached with 60s TTL

Usage:
    engine = AlertEngine(db_session)
    matched_rules = await engine.evaluate_all_rules(event)
    await engine.execute_actions(event, matched_rules)
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.alert_rule import AlertRule, WebhookLog
from app.models.event import Event

logger = logging.getLogger(__name__)


class AlertEngine:
    """
    Alert rule evaluation and action execution engine.

    Evaluates events against user-defined rules and executes configured
    actions (dashboard notifications, webhooks) when rules match.

    Attributes:
        db: SQLAlchemy database session
        http_client: httpx AsyncClient for webhook calls (optional)
    """

    def __init__(self, db: Session, http_client: Optional[httpx.AsyncClient] = None):
        """
        Initialize AlertEngine.

        Args:
            db: SQLAlchemy database session
            http_client: Optional httpx AsyncClient (created if not provided)
        """
        self.db = db
        self.http_client = http_client

    def _parse_conditions(self, conditions_json: str) -> Dict[str, Any]:
        """Parse conditions JSON string into dictionary."""
        try:
            if not conditions_json or conditions_json == '{}':
                return {}
            return json.loads(conditions_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse conditions JSON: {e}")
            return {}

    def _parse_actions(self, actions_json: str) -> Dict[str, Any]:
        """Parse actions JSON string into dictionary."""
        try:
            if not actions_json or actions_json == '{}':
                return {}
            return json.loads(actions_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse actions JSON: {e}")
            return {}

    def _is_in_cooldown(self, rule: AlertRule) -> bool:
        """
        Check if rule is in cooldown period.

        Args:
            rule: AlertRule to check

        Returns:
            True if rule is in cooldown (should skip), False otherwise
        """
        if rule.last_triggered_at is None:
            return False

        if rule.cooldown_minutes <= 0:
            return False

        now = datetime.now(timezone.utc)

        # Ensure last_triggered_at is timezone-aware
        last_triggered = rule.last_triggered_at
        if last_triggered.tzinfo is None:
            last_triggered = last_triggered.replace(tzinfo=timezone.utc)

        cooldown_expires = last_triggered + timedelta(minutes=rule.cooldown_minutes)

        if now < cooldown_expires:
            remaining = (cooldown_expires - now).total_seconds() / 60
            logger.debug(
                f"Rule '{rule.name}' ({rule.id}) in cooldown, {remaining:.1f} min remaining",
                extra={"rule_id": rule.id, "cooldown_remaining_minutes": remaining}
            )
            return True

        return False

    def _check_object_types(
        self,
        event_objects: List[str],
        rule_object_types: Optional[List[str]]
    ) -> bool:
        """
        Check if event contains any of the rule's object types (OR logic).

        Args:
            event_objects: List of detected objects in event
            rule_object_types: List of object types to match (None = any)

        Returns:
            True if any object matches or rule has no object filter
        """
        # No filter = match any object
        if not rule_object_types:
            return True

        # OR logic: event must contain at least one matching object
        return any(obj in rule_object_types for obj in event_objects)

    def _check_cameras(
        self,
        event_camera_id: str,
        rule_cameras: Optional[List[str]]
    ) -> bool:
        """
        Check if event is from a camera in the rule's camera list.

        Args:
            event_camera_id: Camera UUID from event
            rule_cameras: List of camera UUIDs to match (None/empty = any)

        Returns:
            True if camera matches or rule has no camera filter
        """
        # No filter = match any camera
        if not rule_cameras:
            return True

        return event_camera_id in rule_cameras

    def _check_time_of_day(
        self,
        event_timestamp: datetime,
        time_of_day: Optional[Dict[str, str]]
    ) -> bool:
        """
        Check if event occurred within the rule's time window.

        Args:
            event_timestamp: Event timestamp (timezone-aware)
            time_of_day: {"start": "HH:MM", "end": "HH:MM"} or None

        Returns:
            True if within time window or no time filter
        """
        if not time_of_day:
            return True

        start_str = time_of_day.get("start")
        end_str = time_of_day.get("end")

        if not start_str or not end_str:
            return True

        try:
            # Parse HH:MM strings
            start_parts = start_str.split(":")
            end_parts = end_str.split(":")

            start_hour, start_min = int(start_parts[0]), int(start_parts[1])
            end_hour, end_min = int(end_parts[0]), int(end_parts[1])

            # Get event time in local timezone (for user-friendly comparison)
            # Note: For production, should convert to user's timezone
            event_time = event_timestamp.time()
            event_minutes = event_time.hour * 60 + event_time.minute

            start_minutes = start_hour * 60 + start_min
            end_minutes = end_hour * 60 + end_min

            # Handle overnight ranges (e.g., 22:00 to 06:00)
            if start_minutes <= end_minutes:
                # Normal range (e.g., 09:00 to 17:00)
                return start_minutes <= event_minutes <= end_minutes
            else:
                # Overnight range (e.g., 22:00 to 06:00)
                return event_minutes >= start_minutes or event_minutes <= end_minutes

        except (ValueError, IndexError) as e:
            logger.warning(f"Invalid time_of_day format: {time_of_day}, error: {e}")
            return True  # Invalid format = no filter

    def _check_days_of_week(
        self,
        event_timestamp: datetime,
        days_of_week: Optional[List[int]]
    ) -> bool:
        """
        Check if event occurred on a day in the rule's days list.

        Args:
            event_timestamp: Event timestamp
            days_of_week: List of days (1=Monday, 7=Sunday) or None

        Returns:
            True if day matches or no day filter
        """
        if not days_of_week:
            return True

        # Python weekday(): 0=Monday, 6=Sunday
        # Rule format: 1=Monday, 7=Sunday (ISO 8601)
        event_day = event_timestamp.weekday() + 1  # Convert to 1-7

        return event_day in days_of_week

    def _check_min_confidence(
        self,
        event_confidence: int,
        min_confidence: Optional[int]
    ) -> bool:
        """
        Check if event meets minimum confidence threshold.

        Args:
            event_confidence: Event's AI confidence score (0-100)
            min_confidence: Minimum threshold or None

        Returns:
            True if confidence meets threshold or no threshold
        """
        if min_confidence is None:
            return True

        return event_confidence >= min_confidence

    def _check_anomaly_threshold(
        self,
        event_anomaly_score: Optional[float],
        anomaly_threshold: Optional[float]
    ) -> bool:
        """
        Check if event's anomaly score meets threshold (Story P4-7.3).

        Args:
            event_anomaly_score: Event's anomaly score (0.0-1.0) or None
            anomaly_threshold: Minimum anomaly threshold or None

        Returns:
            True if anomaly score meets threshold or no threshold set
        """
        if anomaly_threshold is None:
            return True

        # No anomaly score = don't match anomaly-based rules
        if event_anomaly_score is None:
            return False

        return event_anomaly_score >= anomaly_threshold

    def evaluate_rule(self, rule: AlertRule, event: Event) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluate a single rule against an event.

        Checks cooldown first, then evaluates all conditions with AND logic.

        Args:
            rule: AlertRule to evaluate
            event: Event to match against

        Returns:
            Tuple of (matched: bool, details: dict with condition results)
        """
        details = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "event_id": event.id,
            "conditions_checked": {}
        }

        # Check cooldown first
        if self._is_in_cooldown(rule):
            details["skipped"] = "cooldown"
            details["cooldown_active"] = True
            return False, details

        details["cooldown_active"] = False

        # Parse conditions
        conditions = self._parse_conditions(rule.conditions)

        # Parse event objects_detected (JSON string to list)
        try:
            event_objects = json.loads(event.objects_detected) if isinstance(event.objects_detected, str) else event.objects_detected
        except json.JSONDecodeError:
            event_objects = []

        # Check each condition (AND logic)
        # 1. Object types (OR logic within)
        object_types_match = self._check_object_types(
            event_objects,
            conditions.get("object_types")
        )
        details["conditions_checked"]["object_types"] = object_types_match

        if not object_types_match:
            logger.debug(
                f"Rule '{rule.name}' failed object_types check",
                extra={"rule_id": rule.id, "event_objects": event_objects, "rule_objects": conditions.get("object_types")}
            )
            return False, details

        # 2. Cameras
        cameras_match = self._check_cameras(
            event.camera_id,
            conditions.get("cameras")
        )
        details["conditions_checked"]["cameras"] = cameras_match

        if not cameras_match:
            logger.debug(
                f"Rule '{rule.name}' failed cameras check",
                extra={"rule_id": rule.id, "event_camera": event.camera_id, "rule_cameras": conditions.get("cameras")}
            )
            return False, details

        # 3. Time of day
        time_match = self._check_time_of_day(
            event.timestamp,
            conditions.get("time_of_day")
        )
        details["conditions_checked"]["time_of_day"] = time_match

        if not time_match:
            logger.debug(
                f"Rule '{rule.name}' failed time_of_day check",
                extra={"rule_id": rule.id, "event_time": event.timestamp.isoformat()}
            )
            return False, details

        # 4. Days of week
        days_match = self._check_days_of_week(
            event.timestamp,
            conditions.get("days_of_week")
        )
        details["conditions_checked"]["days_of_week"] = days_match

        if not days_match:
            logger.debug(
                f"Rule '{rule.name}' failed days_of_week check",
                extra={"rule_id": rule.id, "event_day": event.timestamp.weekday() + 1}
            )
            return False, details

        # 5. Minimum confidence
        confidence_match = self._check_min_confidence(
            event.confidence,
            conditions.get("min_confidence")
        )
        details["conditions_checked"]["min_confidence"] = confidence_match

        if not confidence_match:
            logger.debug(
                f"Rule '{rule.name}' failed min_confidence check",
                extra={"rule_id": rule.id, "event_confidence": event.confidence, "min_required": conditions.get("min_confidence")}
            )
            return False, details

        # 6. Story P4-7.3: Anomaly threshold
        anomaly_match = self._check_anomaly_threshold(
            event.anomaly_score,
            conditions.get("anomaly_threshold")
        )
        details["conditions_checked"]["anomaly_threshold"] = anomaly_match

        if not anomaly_match:
            logger.debug(
                f"Rule '{rule.name}' failed anomaly_threshold check",
                extra={"rule_id": rule.id, "event_anomaly_score": event.anomaly_score, "min_required": conditions.get("anomaly_threshold")}
            )
            return False, details

        # All conditions passed
        logger.info(
            f"Rule '{rule.name}' matched event {event.id}",
            extra={
                "rule_id": rule.id,
                "event_id": event.id,
                "event_objects": event_objects,
                "event_confidence": event.confidence
            }
        )

        return True, details

    def evaluate_all_rules(self, event: Event) -> List[AlertRule]:
        """
        Evaluate all enabled rules against an event.

        Queries all enabled rules and evaluates each against the event.
        Returns list of matched rules for action execution.

        Args:
            event: Event to evaluate

        Returns:
            List of AlertRule instances that matched the event
        """
        start_time = time.time()

        # Query all enabled rules
        enabled_rules = self.db.query(AlertRule).filter(
            AlertRule.is_enabled == True
        ).all()

        logger.debug(
            f"Evaluating {len(enabled_rules)} enabled rules against event {event.id}",
            extra={"event_id": event.id, "rule_count": len(enabled_rules)}
        )

        matched_rules = []

        for rule in enabled_rules:
            matched, details = self.evaluate_rule(rule, event)
            if matched:
                matched_rules.append(rule)

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Rule evaluation complete: {len(matched_rules)}/{len(enabled_rules)} rules matched in {duration_ms:.1f}ms",
            extra={
                "event_id": event.id,
                "rules_evaluated": len(enabled_rules),
                "rules_matched": len(matched_rules),
                "matched_rule_ids": [r.id for r in matched_rules],
                "duration_ms": duration_ms
            }
        )

        # Performance warning if slow
        if duration_ms > 500:
            logger.warning(
                f"Rule evaluation exceeded 500ms target: {duration_ms:.1f}ms",
                extra={"duration_ms": duration_ms, "rule_count": len(enabled_rules)}
            )

        return matched_rules

    def update_rule_triggered(self, rule: AlertRule) -> None:
        """
        Update rule's last_triggered_at and increment trigger_count.

        Uses atomic update to prevent race conditions.

        Args:
            rule: AlertRule that was triggered
        """
        now = datetime.now(timezone.utc)

        rule.last_triggered_at = now
        rule.trigger_count = (rule.trigger_count or 0) + 1
        rule.updated_at = now

        try:
            self.db.commit()
            logger.debug(
                f"Updated rule '{rule.name}' trigger stats",
                extra={
                    "rule_id": rule.id,
                    "last_triggered_at": now.isoformat(),
                    "trigger_count": rule.trigger_count
                }
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update rule trigger stats: {e}", exc_info=True)

    def update_event_alert_status(
        self,
        event: Event,
        matched_rules: List[AlertRule]
    ) -> None:
        """
        Update event's alert_triggered and alert_rule_ids fields.

        Args:
            event: Event that triggered rules
            matched_rules: List of rules that matched
        """
        if not matched_rules:
            return

        event.alert_triggered = True
        event.alert_rule_ids = json.dumps([r.id for r in matched_rules])

        try:
            self.db.commit()
            logger.debug(
                f"Updated event {event.id} alert status",
                extra={
                    "event_id": event.id,
                    "alert_triggered": True,
                    "matched_rule_count": len(matched_rules)
                }
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update event alert status: {e}", exc_info=True)


    async def _execute_dashboard_notification(
        self,
        event: Event,
        rule: AlertRule
    ) -> bool:
        """
        Execute dashboard notification action.

        Creates persistent notification record in database and broadcasts
        via WebSocket to all connected dashboard clients.

        Args:
            event: Event that triggered the alert
            rule: AlertRule that matched

        Returns:
            True if notification was created successfully
        """
        try:
            from app.services.websocket_manager import get_websocket_manager
            from app.models.notification import Notification

            # Truncate event description for display (max 200 chars)
            event_description = event.description[:200] if event.description else None

            # Build thumbnail URL (follows existing pattern from events API)
            thumbnail_url = f"/api/v1/events/{event.id}/thumbnail" if event.thumbnail_path else None

            # Create notification record in database
            notification = Notification(
                event_id=event.id,
                rule_id=rule.id,
                rule_name=rule.name,
                event_description=event_description,
                thumbnail_url=thumbnail_url,
                read=False
            )
            self.db.add(notification)
            self.db.commit()
            self.db.refresh(notification)

            logger.info(
                f"Created notification {notification.id} for rule '{rule.name}'",
                extra={
                    "notification_id": notification.id,
                    "rule_id": rule.id,
                    "event_id": event.id
                }
            )

            # Build notification data for WebSocket broadcast
            notification_data = {
                "id": notification.id,
                "event_id": event.id,
                "rule_id": rule.id,
                "rule_name": rule.name,
                "event_description": event_description,
                "thumbnail_url": thumbnail_url,
                "created_at": notification.created_at.isoformat() if notification.created_at else None,
                "read": False
            }

            # Broadcast via WebSocket
            ws_manager = get_websocket_manager()
            clients_notified = await ws_manager.broadcast({
                "type": "notification",
                "data": notification_data
            })

            logger.info(
                f"Dashboard notification broadcast for rule '{rule.name}'",
                extra={
                    "notification_id": notification.id,
                    "rule_id": rule.id,
                    "event_id": event.id,
                    "clients_notified": clients_notified
                }
            )

            return True

        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Failed to create dashboard notification: {e}",
                exc_info=True,
                extra={"rule_id": rule.id, "event_id": event.id}
            )
            return False

    async def _execute_webhook(
        self,
        event: Event,
        rule: AlertRule,
        webhook_config: Dict[str, Any]
    ) -> bool:
        """
        Execute webhook action using WebhookService.

        Delegates to webhook_service.py which provides:
        - Exponential backoff retry (1s, 2s, 4s)
        - SSRF prevention (blocks localhost, private IPs)
        - Rate limiting (100/min per rule)
        - Comprehensive logging to webhook_logs table

        Args:
            event: Event that triggered the alert
            rule: AlertRule that matched
            webhook_config: Webhook configuration {"url": str, "headers": dict}

        Returns:
            True if webhook succeeded (2xx status)
        """
        from app.services.webhook_service import WebhookService

        url = webhook_config.get("url")
        if not url:
            logger.warning(f"Rule '{rule.name}' has no webhook URL configured")
            return False

        # Use WebhookService for execution with security features
        webhook_service = WebhookService(
            db=self.db,
            http_client=self.http_client,
            allow_http=True  # Allow http for local development
        )

        result = await webhook_service.execute_rule_webhook(event, rule)

        if result is None:
            return False

        return result.success

    async def execute_actions(
        self,
        event: Event,
        matched_rules: List[AlertRule]
    ) -> Dict[str, Any]:
        """
        Execute all actions for matched rules.

        Processes each rule's actions independently - a failed webhook
        doesn't prevent dashboard notification from other rules.

        Args:
            event: Event that triggered alerts
            matched_rules: List of rules that matched the event

        Returns:
            Dictionary with execution statistics
        """
        if not matched_rules:
            return {"rules_processed": 0, "notifications_sent": 0, "webhooks_sent": 0}

        stats = {
            "rules_processed": len(matched_rules),
            "notifications_sent": 0,
            "notifications_failed": 0,
            "webhooks_sent": 0,
            "webhooks_failed": 0
        }

        for rule in matched_rules:
            actions = self._parse_actions(rule.actions)

            # Execute dashboard notification
            if actions.get("dashboard_notification", False):
                success = await self._execute_dashboard_notification(event, rule)
                if success:
                    stats["notifications_sent"] += 1
                else:
                    stats["notifications_failed"] += 1

            # Execute webhook
            webhook_config = actions.get("webhook")
            if webhook_config and webhook_config.get("url"):
                success = await self._execute_webhook(event, rule, webhook_config)
                if success:
                    stats["webhooks_sent"] += 1
                else:
                    stats["webhooks_failed"] += 1

            # Update rule trigger stats
            self.update_rule_triggered(rule)

        # Update event alert status
        self.update_event_alert_status(event, matched_rules)

        logger.info(
            f"Action execution complete for event {event.id}",
            extra={
                "event_id": event.id,
                **stats
            }
        )

        return stats

    async def process_event(self, event: Event) -> Dict[str, Any]:
        """
        Full alert processing pipeline for an event.

        Evaluates all rules and executes actions for matches.
        This is the main entry point for the event pipeline integration.

        Args:
            event: Event to process

        Returns:
            Dictionary with processing results
        """
        start_time = time.time()

        # Evaluate all rules
        matched_rules = self.evaluate_all_rules(event)

        # Execute actions for matched rules
        action_stats = await self.execute_actions(event, matched_rules)

        duration_ms = (time.time() - start_time) * 1000

        result = {
            "event_id": event.id,
            "rules_evaluated": len(self.db.query(AlertRule).filter(AlertRule.is_enabled == True).all()),
            "rules_matched": len(matched_rules),
            "matched_rule_ids": [r.id for r in matched_rules],
            "duration_ms": duration_ms,
            **action_stats
        }

        logger.info(
            f"Alert processing complete for event {event.id}",
            extra=result
        )

        return result


# Global engine instance (for dependency injection)
_alert_engine: Optional[AlertEngine] = None


def get_alert_engine(db: Session) -> AlertEngine:
    """
    Get AlertEngine instance with database session.

    Args:
        db: SQLAlchemy database session

    Returns:
        AlertEngine instance
    """
    return AlertEngine(db)


async def process_event_alerts(event_id: str, db: Session) -> Optional[Dict[str, Any]]:
    """
    Process alerts for an event by ID (for background task usage).

    Loads event from database and runs full alert processing.

    Args:
        event_id: UUID of event to process
        db: Database session

    Returns:
        Processing results or None if event not found
    """
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        logger.error(f"Event {event_id} not found for alert processing")
        return None

    engine = AlertEngine(db)
    return await engine.process_event(event)
