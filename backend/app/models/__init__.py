"""SQLAlchemy ORM models"""
from app.models.protect_controller import ProtectController
from app.models.camera import Camera
from app.models.motion_event import MotionEvent
from app.models.system_setting import SystemSetting
from app.models.ai_usage import AIUsage
from app.models.event import Event
from app.models.event_frame import EventFrame
from app.models.alert_rule import AlertRule, WebhookLog
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.models.session import Session
from app.models.system_notification import SystemNotification
from app.models.push_subscription import PushSubscription
from app.models.notification_preference import NotificationPreference
from app.models.mqtt_config import MQTTConfig
from app.models.event_embedding import EventEmbedding
from app.models.recognized_entity import RecognizedEntity, EntityEvent
from app.models.entity_adjustment import EntityAdjustment
from app.models.camera_activity_pattern import CameraActivityPattern
from app.models.activity_summary import ActivitySummary
from app.models.event_feedback import EventFeedback
from app.models.summary_feedback import SummaryFeedback
from app.models.prompt_history import PromptHistory
from app.models.face_embedding import FaceEmbedding
from app.models.vehicle_embedding import VehicleEmbedding
from app.models.frame_embedding import FrameEmbedding
from app.models.homekit import HomeKitConfig, HomeKitAccessory
from app.models.device import Device
from app.models.pairing_code import PairingCode
from app.models.refresh_token import RefreshToken
from app.models.api_key import APIKey
from app.models.user_audit_log import UserAuditLog, AuditAction

__all__ = [
    "ProtectController",
    "Camera",
    "MotionEvent",
    "SystemSetting",
    "AIUsage",
    "Event",
    "EventFrame",
    "AlertRule",
    "WebhookLog",
    "Notification",
    "User",
    "UserRole",
    "Session",
    "SystemNotification",
    "PushSubscription",
    "NotificationPreference",
    "MQTTConfig",
    "EventEmbedding",
    "RecognizedEntity",
    "EntityEvent",
    "EntityAdjustment",
    "CameraActivityPattern",
    "ActivitySummary",
    "EventFeedback",
    "SummaryFeedback",
    "PromptHistory",
    "FaceEmbedding",
    "VehicleEmbedding",
    "FrameEmbedding",
    "HomeKitConfig",
    "HomeKitAccessory",
    "Device",
    "PairingCode",
    "RefreshToken",
    "APIKey",
    "UserAuditLog",
    "AuditAction",
]
