"""
Alert Rules API endpoints (Epic 5)

Provides REST API for alert rule management:
- GET /alert-rules - List all rules (optional filter by is_enabled)
- POST /alert-rules - Create new rule
- GET /alert-rules/{id} - Get single rule by ID
- PUT /alert-rules/{id} - Update rule
- DELETE /alert-rules/{id} - Delete rule
- POST /alert-rules/{id}/test - Test rule against recent events
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import datetime, timezone
import logging
import json
import uuid

from app.core.database import get_db
from app.models.alert_rule import AlertRule
from app.models.event import Event
from app.schemas.alert_rule import (
    AlertRuleCreate,
    AlertRuleUpdate,
    AlertRuleResponse,
    AlertRuleListResponse,
    AlertRuleTestRequest,
    AlertRuleTestResponse,
)
from app.services.alert_engine import AlertEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


def _serialize_conditions(conditions) -> str:
    """Serialize conditions Pydantic model to JSON string."""
    if conditions is None:
        return '{}'
    if isinstance(conditions, str):
        return conditions
    return json.dumps(conditions.model_dump(exclude_none=True))


def _serialize_actions(actions) -> str:
    """Serialize actions Pydantic model to JSON string."""
    if actions is None:
        return '{}'
    if isinstance(actions, str):
        return actions
    return json.dumps(actions.model_dump(exclude_none=True))


@router.get("", response_model=AlertRuleListResponse)
def list_alert_rules(
    is_enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    db: Session = Depends(get_db)
):
    """
    List all alert rules with optional filtering.

    Args:
        is_enabled: Optional filter to show only enabled/disabled rules
        db: Database session

    Returns:
        AlertRuleListResponse with list of rules and total count

    Examples:
        - GET /alert-rules
        - GET /alert-rules?is_enabled=true
    """
    try:
        query = db.query(AlertRule)

        if is_enabled is not None:
            query = query.filter(AlertRule.is_enabled == is_enabled)

        # Order by created_at descending (newest first)
        query = query.order_by(desc(AlertRule.created_at))

        rules = query.all()
        total_count = len(rules)

        logger.info(
            f"Listed {total_count} alert rules (filter: is_enabled={is_enabled})",
            extra={"total_count": total_count, "is_enabled_filter": is_enabled}
        )

        return AlertRuleListResponse(data=rules, total_count=total_count)

    except Exception as e:
        logger.error(f"Failed to list alert rules: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list alert rules"
        )


@router.post("", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    rule_data: AlertRuleCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new alert rule.

    Args:
        rule_data: Alert rule configuration
        db: Database session

    Returns:
        Created alert rule with assigned UUID

    Raises:
        400: Invalid rule configuration
        500: Database error

    Examples:
        POST /alert-rules
        {
            "name": "Package Delivery Alert",
            "is_enabled": true,
            "conditions": {
                "object_types": ["person", "package"],
                "min_confidence": 75
            },
            "actions": {
                "dashboard_notification": true,
                "webhook": {"url": "https://example.com/hook"}
            },
            "cooldown_minutes": 10
        }
    """
    try:
        rule_id = str(uuid.uuid4())

        # Serialize conditions and actions to JSON strings
        conditions_json = _serialize_conditions(rule_data.conditions)
        actions_json = _serialize_actions(rule_data.actions)

        rule = AlertRule(
            id=rule_id,
            name=rule_data.name,
            is_enabled=rule_data.is_enabled,
            conditions=conditions_json,
            actions=actions_json,
            cooldown_minutes=rule_data.cooldown_minutes,
            trigger_count=0
        )

        db.add(rule)
        db.commit()
        db.refresh(rule)

        logger.info(
            f"Created alert rule '{rule.name}' ({rule_id})",
            extra={
                "rule_id": rule_id,
                "rule_name": rule.name,
                "is_enabled": rule.is_enabled
            }
        )

        return rule

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create alert rule: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create alert rule"
        )


@router.get("/{rule_id}", response_model=AlertRuleResponse)
def get_alert_rule(
    rule_id: str,
    db: Session = Depends(get_db)
):
    """
    Get a single alert rule by ID.

    Args:
        rule_id: Alert rule UUID
        db: Database session

    Returns:
        Alert rule details

    Raises:
        404: Rule not found
        500: Database error

    Example:
        GET /alert-rules/123e4567-e89b-12d3-a456-426614174000
    """
    try:
        rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert rule {rule_id} not found"
            )

        logger.debug(f"Retrieved alert rule {rule_id}")

        return rule

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get alert rule {rule_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get alert rule"
        )


@router.put("/{rule_id}", response_model=AlertRuleResponse)
def update_alert_rule(
    rule_id: str,
    rule_data: AlertRuleUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing alert rule.

    Supports partial updates - only provided fields are updated.

    Args:
        rule_id: Alert rule UUID
        rule_data: Fields to update
        db: Database session

    Returns:
        Updated alert rule

    Raises:
        404: Rule not found
        500: Database error

    Examples:
        PUT /alert-rules/123e4567-e89b-12d3-a456-426614174000
        {
            "name": "Updated Rule Name",
            "is_enabled": false
        }
    """
    try:
        rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert rule {rule_id} not found"
            )

        # Update only provided fields
        if rule_data.name is not None:
            rule.name = rule_data.name

        if rule_data.is_enabled is not None:
            rule.is_enabled = rule_data.is_enabled

        if rule_data.conditions is not None:
            rule.conditions = _serialize_conditions(rule_data.conditions)

        if rule_data.actions is not None:
            rule.actions = _serialize_actions(rule_data.actions)

        if rule_data.cooldown_minutes is not None:
            rule.cooldown_minutes = rule_data.cooldown_minutes

        rule.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(rule)

        logger.info(
            f"Updated alert rule '{rule.name}' ({rule_id})",
            extra={"rule_id": rule_id, "rule_name": rule.name}
        )

        return rule

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update alert rule {rule_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update alert rule"
        )


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    rule_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete an alert rule.

    Hard delete - the rule is permanently removed.

    Args:
        rule_id: Alert rule UUID
        db: Database session

    Raises:
        404: Rule not found
        500: Database error

    Example:
        DELETE /alert-rules/123e4567-e89b-12d3-a456-426614174000
    """
    try:
        rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert rule {rule_id} not found"
            )

        rule_name = rule.name
        db.delete(rule)
        db.commit()

        logger.info(
            f"Deleted alert rule '{rule_name}' ({rule_id})",
            extra={"rule_id": rule_id, "rule_name": rule_name}
        )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete alert rule {rule_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete alert rule"
        )


@router.post("/{rule_id}/test", response_model=AlertRuleTestResponse)
def test_alert_rule(
    rule_id: str,
    test_config: Optional[AlertRuleTestRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Test an alert rule against recent events.

    Evaluates the rule against the most recent events to show which
    events would have triggered it. Does not actually execute actions.

    Args:
        rule_id: Alert rule UUID to test
        test_config: Optional test configuration (limit)
        db: Database session

    Returns:
        Test results with matching events

    Raises:
        404: Rule not found
        500: Database error

    Example:
        POST /alert-rules/123e4567-e89b-12d3-a456-426614174000/test
        {"limit": 50}
    """
    try:
        rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert rule {rule_id} not found"
            )

        # Get test parameters
        limit = 50
        if test_config and test_config.limit:
            limit = test_config.limit

        # Get recent events
        recent_events = db.query(Event).order_by(
            desc(Event.timestamp)
        ).limit(limit).all()

        # Create engine instance for evaluation
        engine = AlertEngine(db)

        # Test rule against each event (skip cooldown check)
        matching_event_ids = []

        for event in recent_events:
            # Temporarily bypass cooldown by clearing last_triggered_at
            original_triggered = rule.last_triggered_at
            rule.last_triggered_at = None

            matched, details = engine.evaluate_rule(rule, event)

            # Restore original value (don't persist this change)
            rule.last_triggered_at = original_triggered

            if matched:
                matching_event_ids.append(event.id)

        logger.info(
            f"Tested rule '{rule.name}' against {len(recent_events)} events: "
            f"{len(matching_event_ids)} matches",
            extra={
                "rule_id": rule_id,
                "events_tested": len(recent_events),
                "events_matched": len(matching_event_ids)
            }
        )

        return AlertRuleTestResponse(
            rule_id=rule_id,
            events_tested=len(recent_events),
            events_matched=len(matching_event_ids),
            matching_event_ids=matching_event_ids
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test alert rule {rule_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test alert rule"
        )
