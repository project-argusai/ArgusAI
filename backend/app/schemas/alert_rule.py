"""Alert Rule API Pydantic schemas for request/response validation (Epic 5)"""
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
from typing import List, Optional, Dict, Any
import re


class TimeOfDay(BaseModel):
    """Time range for rule conditions (optional)"""
    start: str = Field(..., pattern=r'^([01]\d|2[0-3]):([0-5]\d)$', description="Start time in HH:MM format (24-hour)")
    end: str = Field(..., pattern=r'^([01]\d|2[0-3]):([0-5]\d)$', description="End time in HH:MM format (24-hour)")

    model_config = {
        "json_schema_extra": {
            "examples": [{"start": "09:00", "end": "17:00"}]
        }
    }


class WebhookConfig(BaseModel):
    """Webhook configuration for rule actions"""
    url: str = Field(..., min_length=1, max_length=2000, description="Webhook URL (must be HTTPS in production)")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Custom headers for authentication")

    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        """Validate URL format"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://hooks.example.com/webhook",
                    "headers": {"Authorization": "Bearer token123"}
                }
            ]
        }
    }


class AlertRuleConditions(BaseModel):
    """Conditions that must match for the rule to trigger (AND logic between conditions)"""
    object_types: Optional[List[str]] = Field(
        default=None,
        description="Object types to match (OR logic within list). Empty/null = any object."
    )
    cameras: Optional[List[str]] = Field(
        default=None,
        description="Camera UUIDs to match. Empty/null = any camera."
    )
    time_of_day: Optional[TimeOfDay] = Field(
        default=None,
        description="Time range when rule is active (HH:MM format)"
    )
    days_of_week: Optional[List[int]] = Field(
        default=None,
        description="Days when rule is active (1=Monday, 7=Sunday). Empty/null = any day."
    )
    min_confidence: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Minimum confidence threshold (0-100). Null = no threshold."
    )

    @field_validator('days_of_week')
    @classmethod
    def validate_days_of_week(cls, v):
        """Validate days are in range 1-7"""
        if v is not None:
            for day in v:
                if day < 1 or day > 7:
                    raise ValueError(f"Day must be between 1 (Monday) and 7 (Sunday), got {day}")
        return v

    @field_validator('object_types')
    @classmethod
    def validate_object_types(cls, v):
        """Validate object types are valid"""
        valid_types = {"person", "vehicle", "animal", "package", "unknown"}
        if v is not None:
            for obj in v:
                if obj not in valid_types:
                    raise ValueError(f"Invalid object type '{obj}'. Valid types: {valid_types}")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "object_types": ["person", "package"],
                    "cameras": [],
                    "time_of_day": {"start": "09:00", "end": "17:00"},
                    "days_of_week": [1, 2, 3, 4, 5],
                    "min_confidence": 80
                }
            ]
        }
    }


class AlertRuleActions(BaseModel):
    """Actions to execute when rule triggers"""
    dashboard_notification: bool = Field(
        default=True,
        description="Create in-app notification visible on dashboard"
    )
    webhook: Optional[WebhookConfig] = Field(
        default=None,
        description="Webhook to call (HTTP POST with event data)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "dashboard_notification": True,
                    "webhook": {
                        "url": "https://hooks.example.com/alert",
                        "headers": {"X-API-Key": "secret"}
                    }
                }
            ]
        }
    }


class AlertRuleCreate(BaseModel):
    """Schema for creating a new alert rule via POST /api/v1/alert-rules"""
    name: str = Field(..., min_length=1, max_length=200, description="Human-readable rule name")
    is_enabled: bool = Field(default=True, description="Whether rule is active")
    conditions: AlertRuleConditions = Field(
        default_factory=AlertRuleConditions,
        description="Conditions that must match for rule to trigger"
    )
    actions: AlertRuleActions = Field(
        default_factory=AlertRuleActions,
        description="Actions to execute when rule triggers"
    )
    cooldown_minutes: int = Field(
        default=5,
        ge=0,
        le=1440,
        description="Minimum minutes between triggers (0-1440, max 24 hours)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Package Delivery Alert",
                    "is_enabled": True,
                    "conditions": {
                        "object_types": ["person", "package"],
                        "cameras": [],
                        "time_of_day": {"start": "08:00", "end": "18:00"},
                        "days_of_week": [1, 2, 3, 4, 5],
                        "min_confidence": 75
                    },
                    "actions": {
                        "dashboard_notification": True,
                        "webhook": {
                            "url": "https://hooks.example.com/delivery",
                            "headers": {"Authorization": "Bearer token"}
                        }
                    },
                    "cooldown_minutes": 10
                }
            ]
        }
    }


class AlertRuleUpdate(BaseModel):
    """Schema for updating an alert rule via PUT /api/v1/alert-rules/{id}"""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Human-readable rule name")
    is_enabled: Optional[bool] = Field(None, description="Whether rule is active")
    conditions: Optional[AlertRuleConditions] = Field(None, description="Conditions that must match")
    actions: Optional[AlertRuleActions] = Field(None, description="Actions to execute")
    cooldown_minutes: Optional[int] = Field(
        None,
        ge=0,
        le=1440,
        description="Minimum minutes between triggers (0-1440)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Updated Rule Name",
                    "is_enabled": False,
                    "cooldown_minutes": 30
                }
            ]
        }
    }


class AlertRuleResponse(BaseModel):
    """Schema for alert rule API responses"""
    id: str = Field(..., description="Alert rule UUID")
    name: str = Field(..., description="Rule name")
    is_enabled: bool = Field(..., description="Whether rule is active")
    conditions: AlertRuleConditions = Field(..., description="Rule conditions")
    actions: AlertRuleActions = Field(..., description="Rule actions")
    cooldown_minutes: int = Field(..., description="Cooldown period in minutes")
    last_triggered_at: Optional[datetime] = Field(None, description="When rule last triggered")
    trigger_count: int = Field(..., description="Total trigger count")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    @field_validator('conditions', mode='before')
    @classmethod
    def parse_conditions(cls, v):
        """Parse JSON string into AlertRuleConditions if needed"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @field_validator('actions', mode='before')
    @classmethod
    def parse_actions(cls, v):
        """Parse JSON string into AlertRuleActions if needed"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "name": "Package Delivery Alert",
                    "is_enabled": True,
                    "conditions": {
                        "object_types": ["person", "package"],
                        "cameras": [],
                        "time_of_day": {"start": "08:00", "end": "18:00"},
                        "days_of_week": [1, 2, 3, 4, 5],
                        "min_confidence": 75
                    },
                    "actions": {
                        "dashboard_notification": True,
                        "webhook": {
                            "url": "https://hooks.example.com/delivery",
                            "headers": {}
                        }
                    },
                    "cooldown_minutes": 10,
                    "last_triggered_at": "2025-11-17T14:30:00Z",
                    "trigger_count": 42,
                    "created_at": "2025-11-01T10:00:00Z",
                    "updated_at": "2025-11-15T16:30:00Z"
                }
            ]
        }
    }


class AlertRuleListResponse(BaseModel):
    """Schema for paginated alert rule list responses"""
    data: List[AlertRuleResponse] = Field(..., description="List of alert rules")
    total_count: int = Field(..., ge=0, description="Total number of rules")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "data": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "name": "Package Delivery Alert",
                            "is_enabled": True,
                            "conditions": {"object_types": ["person", "package"]},
                            "actions": {"dashboard_notification": True},
                            "cooldown_minutes": 10,
                            "last_triggered_at": None,
                            "trigger_count": 0,
                            "created_at": "2025-11-01T10:00:00Z",
                            "updated_at": "2025-11-01T10:00:00Z"
                        }
                    ],
                    "total_count": 1
                }
            ]
        }
    }


class AlertRuleTestRequest(BaseModel):
    """Schema for testing an alert rule against historical events"""
    limit: int = Field(default=50, ge=1, le=100, description="Maximum events to test against (1-100)")

    model_config = {
        "json_schema_extra": {
            "examples": [{"limit": 50}]
        }
    }


class AlertRuleTestResponse(BaseModel):
    """Schema for alert rule test results"""
    rule_id: str = Field(..., description="Alert rule UUID that was tested")
    events_tested: int = Field(..., description="Number of events tested")
    events_matched: int = Field(..., description="Number of events that would trigger this rule")
    matching_event_ids: List[str] = Field(..., description="IDs of events that would match")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "rule_id": "123e4567-e89b-12d3-a456-426614174000",
                    "events_tested": 50,
                    "events_matched": 12,
                    "matching_event_ids": [
                        "abc123",
                        "def456",
                        "ghi789"
                    ]
                }
            ]
        }
    }


class WebhookLogResponse(BaseModel):
    """Schema for webhook execution log"""
    id: int = Field(..., description="Log entry ID")
    alert_rule_id: str = Field(..., description="Alert rule UUID")
    event_id: str = Field(..., description="Event UUID that triggered the webhook")
    url: str = Field(..., description="Webhook URL called")
    status_code: int = Field(..., description="HTTP response status code")
    response_time_ms: int = Field(..., description="Response time in milliseconds")
    retry_count: int = Field(..., description="Number of retry attempts")
    success: bool = Field(..., description="Whether webhook succeeded")
    error_message: Optional[str] = Field(None, description="Error details if failed")
    created_at: datetime = Field(..., description="Execution timestamp")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": 1,
                    "alert_rule_id": "123e4567-e89b-12d3-a456-426614174000",
                    "event_id": "abc123-def456",
                    "url": "https://hooks.example.com/alert",
                    "status_code": 200,
                    "response_time_ms": 234,
                    "retry_count": 0,
                    "success": True,
                    "error_message": None,
                    "created_at": "2025-11-17T14:30:00Z"
                }
            ]
        }
    }
