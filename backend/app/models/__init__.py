"""SQLAlchemy ORM models"""
from app.models.protect_controller import ProtectController
from app.models.camera import Camera
from app.models.motion_event import MotionEvent
from app.models.system_setting import SystemSetting
from app.models.ai_usage import AIUsage
from app.models.event import Event
from app.models.alert_rule import AlertRule, WebhookLog
from app.models.user import User
from app.models.system_notification import SystemNotification
from app.models.push_subscription import PushSubscription
from app.models.notification_preference import NotificationPreference
from app.models.mqtt_config import MQTTConfig
from app.models.event_embedding import EventEmbedding
from app.models.recognized_entity import RecognizedEntity, EntityEvent
from app.models.camera_activity_pattern import CameraActivityPattern
from app.models.activity_summary import ActivitySummary
from app.models.event_feedback import EventFeedback
from app.models.prompt_history import PromptHistory

__all__ = [
    "ProtectController",
    "Camera",
    "MotionEvent",
    "SystemSetting",
    "AIUsage",
    "Event",
    "AlertRule",
    "WebhookLog",
    "User",
    "SystemNotification",
    "PushSubscription",
    "NotificationPreference",
    "MQTTConfig",
    "EventEmbedding",
    "RecognizedEntity",
    "EntityEvent",
    "CameraActivityPattern",
    "ActivitySummary",
    "EventFeedback",
    "PromptHistory",
]
