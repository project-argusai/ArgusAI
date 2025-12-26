"""
Pydantic models for push notification providers.

Story P11-2.1: APNS provider models
Story P11-2.2: FCM provider models
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class DeliveryStatus(str, Enum):
    """Delivery status for push notifications."""

    SUCCESS = "success"
    FAILED = "failed"
    INVALID_TOKEN = "invalid_token"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    SERVER_ERROR = "server_error"


@dataclass
class DeliveryResult:
    """Result of a push notification delivery attempt."""

    device_token: str
    success: bool
    status: DeliveryStatus = DeliveryStatus.FAILED
    status_code: Optional[int] = None
    error: Optional[str] = None
    error_reason: Optional[str] = None  # APNS reason header
    apns_id: Optional[str] = None  # APNS unique notification ID
    retries: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class APNSConfig(BaseModel):
    """Configuration for APNS provider.

    Attributes:
        key_file: Path to the .p8 auth key file
        key_id: 10-character key identifier from Apple Developer Portal
        team_id: 10-character team identifier
        bundle_id: App bundle identifier (e.g., com.argusai.app)
        use_sandbox: Whether to use sandbox environment (development)
    """

    key_file: str = Field(..., description="Path to .p8 auth key file")
    key_id: str = Field(..., min_length=10, max_length=10, description="10-character key ID")
    team_id: str = Field(..., min_length=10, max_length=10, description="10-character team ID")
    bundle_id: str = Field(..., description="App bundle identifier")
    use_sandbox: bool = Field(default=False, description="Use sandbox environment")

    @field_validator("key_id", "team_id")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        """Validate that identifiers are alphanumeric."""
        if not v.isalnum():
            raise ValueError("Must be alphanumeric")
        return v.upper()


class APNSAlert(BaseModel):
    """APNS alert payload structure.

    Can be a simple string or a dictionary with title, body, subtitle.
    """

    title: str = Field(..., description="Alert title")
    body: str = Field(..., description="Alert body text")
    subtitle: Optional[str] = Field(None, description="Alert subtitle")
    title_loc_key: Optional[str] = Field(None, description="Localization key for title")
    title_loc_args: Optional[List[str]] = Field(None, description="Localization args for title")
    loc_key: Optional[str] = Field(None, description="Localization key for body")
    loc_args: Optional[List[str]] = Field(None, description="Localization args for body")
    action_loc_key: Optional[str] = Field(None, description="Localization key for action button")
    launch_image: Optional[str] = Field(None, description="Launch image filename")


class APNSPayload(BaseModel):
    """APNS notification payload.

    Formats notifications according to Apple's push notification format.
    See: https://developer.apple.com/documentation/usernotifications/setting_up_a_remote_notification_server/generating_a_remote_notification

    Attributes:
        alert: The alert content (title, body, etc.)
        badge: App icon badge number (optional)
        sound: Sound filename or "default"
        mutable_content: Enable Notification Service Extension
        category: Notification category for action buttons
        thread_id: Thread identifier for grouping
        content_available: Background update flag (silent notification)
        target_content_id: Window to bring to foreground
        interruption_level: iOS 15+ interruption level
        relevance_score: iOS 15+ relevance score (0.0-1.0)
        custom_data: Additional data to include in payload
    """

    alert: APNSAlert
    badge: Optional[int] = Field(None, ge=0, description="Badge number")
    sound: str = Field(default="default", description="Sound name or 'default'")
    mutable_content: bool = Field(default=True, description="Enable Service Extension")
    category: Optional[str] = Field(None, description="Notification category")
    thread_id: Optional[str] = Field(None, description="Thread ID for grouping")
    content_available: bool = Field(default=False, description="Background update")
    target_content_id: Optional[str] = Field(None, description="Target content ID")
    interruption_level: Optional[str] = Field(
        None,
        description="Interruption level: passive, active, time-sensitive, critical"
    )
    relevance_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Relevance score for notification summary"
    )
    custom_data: Dict[str, Any] = Field(default_factory=dict, description="Custom payload data")

    @field_validator("interruption_level")
    @classmethod
    def validate_interruption_level(cls, v: Optional[str]) -> Optional[str]:
        """Validate interruption level is one of the allowed values."""
        if v is not None:
            allowed = {"passive", "active", "time-sensitive", "critical"}
            if v not in allowed:
                raise ValueError(f"Must be one of: {allowed}")
        return v

    def to_apns_dict(self) -> Dict[str, Any]:
        """Convert to APNS payload dictionary format.

        Returns:
            Dictionary ready for JSON serialization to APNS.
        """
        # Build alert dict
        alert_dict = {
            "title": self.alert.title,
            "body": self.alert.body,
        }
        if self.alert.subtitle:
            alert_dict["subtitle"] = self.alert.subtitle
        if self.alert.title_loc_key:
            alert_dict["title-loc-key"] = self.alert.title_loc_key
        if self.alert.title_loc_args:
            alert_dict["title-loc-args"] = self.alert.title_loc_args
        if self.alert.loc_key:
            alert_dict["loc-key"] = self.alert.loc_key
        if self.alert.loc_args:
            alert_dict["loc-args"] = self.alert.loc_args
        if self.alert.action_loc_key:
            alert_dict["action-loc-key"] = self.alert.action_loc_key
        if self.alert.launch_image:
            alert_dict["launch-image"] = self.alert.launch_image

        # Build aps dict
        aps = {
            "alert": alert_dict,
            "sound": self.sound,
        }

        if self.badge is not None:
            aps["badge"] = self.badge
        if self.mutable_content:
            aps["mutable-content"] = 1
        if self.content_available:
            aps["content-available"] = 1
        if self.category:
            aps["category"] = self.category
        if self.thread_id:
            aps["thread-id"] = self.thread_id
        if self.target_content_id:
            aps["target-content-id"] = self.target_content_id
        if self.interruption_level:
            aps["interruption-level"] = self.interruption_level
        if self.relevance_score is not None:
            aps["relevance-score"] = self.relevance_score

        # Build full payload
        payload = {"aps": aps}

        # Add custom data at root level
        payload.update(self.custom_data)

        return payload


# =============================================================================
# FCM (Firebase Cloud Messaging) Models - Story P11-2.2
# =============================================================================


class FCMConfig(BaseModel):
    """Configuration for FCM provider.

    Attributes:
        project_id: Firebase project ID
        credentials_path: Path to the service account JSON file
    """

    project_id: str = Field(..., description="Firebase project ID")
    credentials_path: str = Field(..., description="Path to service account JSON file")

    @field_validator("credentials_path")
    @classmethod
    def validate_credentials_path(cls, v: str) -> str:
        """Validate that credentials path is not empty."""
        if not v or not v.strip():
            raise ValueError("credentials_path cannot be empty")
        return v


class FCMPayload(BaseModel):
    """FCM notification payload.

    Formats notifications according to FCM message format.
    See: https://firebase.google.com/docs/cloud-messaging/send-message

    Attributes:
        title: Notification title
        body: Notification body text
        image_url: Optional image URL for BigPicture style
        data: Custom data payload for background processing
        channel_id: Android notification channel ID
        priority: Message priority (high or normal)
        icon: Android notification icon name
        color: Notification icon color (hex format)
        sound: Sound name or "default"
        click_action: Action to perform on notification click
        tag: Notification tag for grouping/replacing
    """

    title: str = Field(..., description="Notification title")
    body: str = Field(..., description="Notification body text")
    image_url: Optional[str] = Field(None, description="Image URL for BigPicture style")
    data: Dict[str, str] = Field(default_factory=dict, description="Custom data payload")
    channel_id: str = Field(default="argusai_events", description="Android channel ID")
    priority: str = Field(default="high", description="Message priority")
    icon: str = Field(default="ic_notification", description="Notification icon")
    color: str = Field(default="#4A90D9", description="Icon color (hex)")
    sound: str = Field(default="default", description="Sound name")
    click_action: Optional[str] = Field(None, description="Click action")
    tag: Optional[str] = Field(None, description="Notification tag for grouping")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Validate priority is one of the allowed values."""
        allowed = {"high", "normal"}
        if v not in allowed:
            raise ValueError(f"Priority must be one of: {allowed}")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        """Validate color is a valid hex format."""
        if not v.startswith("#") or len(v) not in (4, 7):
            raise ValueError("Color must be in hex format (#RGB or #RRGGBB)")
        return v


def format_event_for_fcm(
    event_id: str,
    camera_id: str,
    camera_name: str,
    description: str,
    smart_detection_type: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    entity_names: Optional[List[str]] = None,
    is_vip: bool = False,
    anomaly_score: Optional[float] = None,
) -> FCMPayload:
    """Format an event notification for FCM.

    Creates an FCMPayload from event data, following the same patterns
    as the APNS format_event_for_apns function.

    Args:
        event_id: UUID of the event
        camera_id: UUID of the camera
        camera_name: Display name of the camera
        description: AI-generated event description
        smart_detection_type: Detection type (person, vehicle, etc.)
        thumbnail_url: URL to event thumbnail
        entity_names: List of recognized entity names
        is_vip: Whether any matched entity is VIP
        anomaly_score: Anomaly score 0.0-1.0

    Returns:
        FCMPayload ready for sending
    """
    # Build VIP prefix
    vip_prefix = "" if is_vip else ""

    # Check for high anomaly
    is_high_anomaly = anomaly_score is not None and anomaly_score >= 0.6

    # Build title based on detection and entity info
    if entity_names and len(entity_names) > 0:
        if len(entity_names) == 1:
            name_str = entity_names[0]
        elif len(entity_names) == 2:
            name_str = f"{entity_names[0]} and {entity_names[1]}"
        else:
            name_str = f"{entity_names[0]} and {len(entity_names) - 1} others"

        if is_high_anomaly:
            title = f"{vip_prefix}{name_str} - Unusual Activity at {camera_name}"
        else:
            title = f"{vip_prefix}{name_str} at {camera_name}"
    elif smart_detection_type:
        detection_labels = {
            "person": "Person Detected",
            "vehicle": "Vehicle Detected",
            "package": "Package Detected",
            "animal": "Animal Detected",
            "ring": "Doorbell Ring",
            "motion": "Motion Detected",
        }
        detection_label = detection_labels.get(smart_detection_type, "Motion Detected")

        if is_high_anomaly:
            title = f"{vip_prefix}{camera_name}: Unusual Activity - {detection_label}"
        else:
            title = f"{vip_prefix}{camera_name}: {detection_label}"
    else:
        if is_high_anomaly:
            title = f"{vip_prefix}{camera_name}: Unusual Activity"
        else:
            title = f"{vip_prefix}{camera_name}: Motion Detected"

    # Truncate body if too long
    body = description
    if len(body) > 100:
        body = body[:97] + "..."

    # Build data payload (FCM requires string values)
    data: Dict[str, str] = {
        "event_id": event_id,
        "camera_id": camera_id,
        "camera_name": camera_name,
        "url": f"/events?highlight={event_id}",
        "click_action": "OPEN_EVENT",
    }
    if smart_detection_type:
        data["smart_detection_type"] = smart_detection_type
    if entity_names:
        data["entity_names"] = ",".join(entity_names)
    if is_vip:
        data["is_vip"] = "true"
    if anomaly_score is not None:
        data["anomaly_score"] = str(anomaly_score)
        data["is_unusual"] = "true" if is_high_anomaly else "false"

    return FCMPayload(
        title=title,
        body=body,
        image_url=thumbnail_url,
        data=data,
        channel_id="argusai_events",
        priority="high",
        tag=camera_id,  # Group by camera
    )


def format_event_for_apns(
    event_id: str,
    camera_id: str,
    camera_name: str,
    description: str,
    smart_detection_type: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    entity_names: Optional[List[str]] = None,
    is_vip: bool = False,
    anomaly_score: Optional[float] = None,
) -> APNSPayload:
    """Format an event notification for APNS.

    Creates an APNSPayload from event data, following the same patterns
    as the Web Push format_rich_notification function.

    Args:
        event_id: UUID of the event
        camera_id: UUID of the camera
        camera_name: Display name of the camera
        description: AI-generated event description
        smart_detection_type: Detection type (person, vehicle, etc.)
        thumbnail_url: URL to event thumbnail
        entity_names: List of recognized entity names
        is_vip: Whether any matched entity is VIP
        anomaly_score: Anomaly score 0.0-1.0

    Returns:
        APNSPayload ready for sending
    """
    # Build VIP prefix
    vip_prefix = "" if is_vip else ""

    # Check for high anomaly
    is_high_anomaly = anomaly_score is not None and anomaly_score >= 0.6

    # Build title based on detection and entity info
    if entity_names and len(entity_names) > 0:
        if len(entity_names) == 1:
            name_str = entity_names[0]
        elif len(entity_names) == 2:
            name_str = f"{entity_names[0]} and {entity_names[1]}"
        else:
            name_str = f"{entity_names[0]} and {len(entity_names) - 1} others"

        if is_high_anomaly:
            title = f"{vip_prefix}{name_str} - Unusual Activity at {camera_name}"
        else:
            title = f"{vip_prefix}{name_str} at {camera_name}"
    elif smart_detection_type:
        detection_labels = {
            "person": "Person Detected",
            "vehicle": "Vehicle Detected",
            "package": "Package Detected",
            "animal": "Animal Detected",
            "ring": "Doorbell Ring",
            "motion": "Motion Detected",
        }
        detection_label = detection_labels.get(smart_detection_type, "Motion Detected")

        if is_high_anomaly:
            title = f"{vip_prefix}{camera_name}: Unusual Activity - {detection_label}"
        else:
            title = f"{vip_prefix}{camera_name}: {detection_label}"
    else:
        if is_high_anomaly:
            title = f"{vip_prefix}{camera_name}: Unusual Activity"
        else:
            title = f"{vip_prefix}{camera_name}: Motion Detected"

    # Truncate body if too long
    body = description
    if len(body) > 100:
        body = body[:97] + "..."

    # Build custom data
    custom_data = {
        "event_id": event_id,
        "camera_id": camera_id,
        "camera_name": camera_name,
        "url": f"/events?highlight={event_id}",
    }
    if smart_detection_type:
        custom_data["smart_detection_type"] = smart_detection_type
    if thumbnail_url:
        custom_data["thumbnail_url"] = thumbnail_url
    if entity_names:
        custom_data["entity_names"] = entity_names
    if is_vip:
        custom_data["is_vip"] = True
    if anomaly_score is not None:
        custom_data["anomaly_score"] = anomaly_score
        custom_data["is_unusual"] = is_high_anomaly

    return APNSPayload(
        alert=APNSAlert(
            title=title,
            body=body,
            subtitle=camera_name,
        ),
        badge=1,
        sound="default",
        mutable_content=True,  # Enable for thumbnail download
        category="SECURITY_ALERT",
        thread_id=camera_id,  # Group by camera
        custom_data=custom_data,
    )
