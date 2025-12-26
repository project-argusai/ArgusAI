"""
Push notification providers for mobile platforms.

This package contains providers for:
- APNS (Apple Push Notification Service) - iOS, iPadOS, watchOS
- FCM (Firebase Cloud Messaging) - Android

Story P11-2.1: Initial APNS provider implementation
Story P11-2.2: FCM provider implementation
"""

from app.services.push.apns_provider import APNSProvider
from app.services.push.fcm_provider import FCMProvider
from app.services.push.models import (
    APNSConfig,
    APNSPayload,
    APNSAlert,
    FCMConfig,
    FCMPayload,
    DeliveryResult,
    DeliveryStatus,
    format_event_for_apns,
    format_event_for_fcm,
)

__all__ = [
    # APNS
    "APNSProvider",
    "APNSConfig",
    "APNSPayload",
    "APNSAlert",
    "format_event_for_apns",
    # FCM
    "FCMProvider",
    "FCMConfig",
    "FCMPayload",
    "format_event_for_fcm",
    # Common
    "DeliveryResult",
    "DeliveryStatus",
]
