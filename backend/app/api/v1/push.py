"""
Push Notification API endpoints (Story P4-1.1, P4-1.4)

Endpoints for Web Push subscription management:
- GET /api/v1/push/vapid-public-key - Get VAPID public key for frontend
- POST /api/v1/push/subscribe - Register push subscription
- DELETE /api/v1/push/subscribe - Unsubscribe
- GET /api/v1/push/subscriptions - List subscriptions (admin)
- GET /api/v1/push/preferences - Get notification preferences (P4-1.4)
- PUT /api/v1/push/preferences - Update notification preferences (P4-1.4)
"""
import logging
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.push_subscription import PushSubscription
from app.models.notification_preference import NotificationPreference
from app.utils.vapid import get_vapid_public_key
from app.services.push_notification_service import PushNotificationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/push",
    tags=["push-notifications"]
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class SubscriptionKeys(BaseModel):
    """Browser push subscription keys."""
    p256dh: str = Field(..., description="P-256 public key for message encryption")
    auth: str = Field(..., description="Authentication secret")


class SubscribeRequest(BaseModel):
    """Request body for push subscription registration."""
    endpoint: str = Field(..., description="Push service endpoint URL")
    keys: SubscriptionKeys = Field(..., description="Encryption keys")
    user_agent: Optional[str] = Field(None, description="Browser user agent")

    class Config:
        json_schema_extra = {
            "example": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/abc123...",
                "keys": {
                    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_...",
                    "auth": "tBHItJI5svbpez7KI4CCXg=="
                },
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0...)"
            }
        }


class UnsubscribeRequest(BaseModel):
    """Request body for push unsubscription."""
    endpoint: str = Field(..., description="Push service endpoint URL to unsubscribe")


class SubscriptionResponse(BaseModel):
    """Response for subscription operations."""
    id: str = Field(..., description="Subscription UUID")
    endpoint: str = Field(..., description="Truncated endpoint for display")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "endpoint": "https://fcm.googleapis.com/...xyz",
                "created_at": "2025-12-10T10:30:00Z"
            }
        }


class VapidPublicKeyResponse(BaseModel):
    """Response containing VAPID public key."""
    public_key: str = Field(..., description="VAPID public key in URL-safe base64")


class PushRequirementsResponse(BaseModel):
    """Response containing push notification requirements and warnings (Story P9-5.1)."""
    https_required: bool = Field(
        default=True,
        description="Whether HTTPS is required for push notifications"
    )
    https_configured: bool = Field(
        default=False,
        description="Whether HTTPS is currently configured"
    )
    warning: Optional[str] = Field(
        None,
        description="Warning message if HTTPS is not configured"
    )
    ready: bool = Field(
        default=False,
        description="Whether push notifications are ready to use"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "https_required": True,
                "https_configured": False,
                "warning": "Push notifications require HTTPS for full functionality. Configure SSL to enable push notifications.",
                "ready": False
            }
        }


class SubscriptionListItem(BaseModel):
    """Single subscription in list response."""
    id: str
    user_id: Optional[str]
    endpoint: str
    user_agent: Optional[str]
    created_at: Optional[str]
    last_used_at: Optional[str]


class SubscriptionsListResponse(BaseModel):
    """Response listing all subscriptions."""
    subscriptions: List[SubscriptionListItem]
    total: int


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
async def get_vapid_key(db: Session = Depends(get_db)):
    """
    Get VAPID public key for push subscription.

    The frontend uses this key as the `applicationServerKey` when calling
    `pushManager.subscribe()`. Keys are generated automatically on first request.

    **Response:**
    ```json
    {
        "public_key": "BEl62iUYgUivxIkv69yViEuiBIa-..."
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Key generation failed
    """
    try:
        public_key = get_vapid_public_key(db)

        if not public_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get or generate VAPID keys"
            )

        return VapidPublicKeyResponse(public_key=public_key)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VAPID public key: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve VAPID public key"
        )


@router.get("/requirements", response_model=PushRequirementsResponse)
async def get_push_requirements():
    """
    Get push notification requirements and HTTPS status (Story P9-5.1).

    Checks if HTTPS is configured and returns a warning if push notifications
    may not work properly without HTTPS. Web Push requires a secure context.

    **Response:**
    ```json
    {
        "https_required": true,
        "https_configured": false,
        "warning": "Push notifications require HTTPS for full functionality...",
        "ready": false
    }
    ```

    **Status Codes:**
    - 200: Success
    """
    from app.core.config import settings as app_settings

    # Check if HTTPS is configured
    https_configured = app_settings.ssl_ready

    # Build warning message if HTTPS is not configured
    warning = None
    if not https_configured:
        warning = (
            "Push notifications require HTTPS for full functionality. "
            "Without SSL configured, push notifications will only work on localhost. "
            "Configure SSL_ENABLED, SSL_CERT_FILE, and SSL_KEY_FILE to enable push notifications."
        )

    return PushRequirementsResponse(
        https_required=True,
        https_configured=https_configured,
        warning=warning,
        ready=https_configured
    )


@router.post("/subscribe", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def subscribe(
    request: SubscribeRequest,
    db: Session = Depends(get_db)
):
    """
    Register a push subscription.

    Stores the browser's push subscription for receiving notifications.
    If the endpoint already exists, the subscription is updated (upsert).

    **Request Body:**
    ```json
    {
        "endpoint": "https://fcm.googleapis.com/fcm/send/...",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_...",
            "auth": "tBHItJI5svbpez7KI4CCXg=="
        },
        "user_agent": "Mozilla/5.0 (iPhone; ...)"
    }
    ```

    **Response:**
    ```json
    {
        "id": "uuid",
        "endpoint": "https://fcm.googleapis.com/...xyz",
        "created_at": "2025-12-10T10:30:00Z"
    }
    ```

    **Status Codes:**
    - 201: Subscription created
    - 200: Existing subscription updated
    - 400: Invalid subscription data
    - 500: Internal server error
    """
    try:
        # Validate endpoint format
        if not request.endpoint.startswith(('https://', 'http://')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid endpoint URL format"
            )

        # Check for existing subscription (upsert)
        existing = db.query(PushSubscription).filter(
            PushSubscription.endpoint == request.endpoint
        ).first()

        if existing:
            # Update existing subscription
            existing.p256dh_key = request.keys.p256dh
            existing.auth_key = request.keys.auth
            existing.user_agent = request.user_agent
            db.commit()

            logger.info(
                f"Updated push subscription",
                extra={
                    "subscription_id": existing.id,
                    "endpoint_preview": request.endpoint[:50] + "..."
                }
            )

            # Truncate endpoint for response
            endpoint_truncated = _truncate_endpoint(existing.endpoint)

            return SubscriptionResponse(
                id=existing.id,
                endpoint=endpoint_truncated,
                created_at=existing.created_at.isoformat()
            )

        # Create new subscription
        subscription = PushSubscription(
            endpoint=request.endpoint,
            p256dh_key=request.keys.p256dh,
            auth_key=request.keys.auth,
            user_agent=request.user_agent,
            # user_id is nullable - can be associated with user later
        )

        db.add(subscription)
        db.flush()  # Flush to get subscription.id

        # Create default notification preferences (Story P4-1.4)
        preference = NotificationPreference.create_default(subscription.id)
        db.add(preference)

        db.commit()
        db.refresh(subscription)

        logger.info(
            f"Created new push subscription with default preferences",
            extra={
                "subscription_id": subscription.id,
                "preference_id": preference.id,
                "endpoint_preview": request.endpoint[:50] + "..."
            }
        )

        # Truncate endpoint for response
        endpoint_truncated = _truncate_endpoint(subscription.endpoint)

        return SubscriptionResponse(
            id=subscription.id,
            endpoint=endpoint_truncated,
            created_at=subscription.created_at.isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating push subscription: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create push subscription"
        )


@router.delete("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    request: UnsubscribeRequest,
    db: Session = Depends(get_db)
):
    """
    Unsubscribe from push notifications.

    Removes the push subscription from the database.

    **Request Body:**
    ```json
    {
        "endpoint": "https://fcm.googleapis.com/fcm/send/..."
    }
    ```

    **Status Codes:**
    - 204: Successfully unsubscribed
    - 404: Subscription not found
    - 500: Internal server error
    """
    try:
        subscription = db.query(PushSubscription).filter(
            PushSubscription.endpoint == request.endpoint
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        subscription_id = subscription.id
        db.delete(subscription)
        db.commit()

        logger.info(
            f"Deleted push subscription",
            extra={
                "subscription_id": subscription_id,
                "endpoint_preview": request.endpoint[:50] + "..."
            }
        )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting push subscription: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete push subscription"
        )


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_post(
    request: UnsubscribeRequest,
    db: Session = Depends(get_db)
):
    """
    Unsubscribe from push notifications (POST alias for backward compatibility).

    This is an alias for DELETE /subscribe endpoint for clients that don't support
    DELETE requests with a body. Removes the push subscription from the database.

    **Request Body:**
    ```json
    {
        "endpoint": "https://fcm.googleapis.com/fcm/send/..."
    }
    ```

    **Status Codes:**
    - 204: Successfully unsubscribed
    - 404: Subscription not found
    - 500: Internal server error
    """
    # Delegate to the main unsubscribe function
    return await unsubscribe(request, db)


@router.get("/subscriptions", response_model=SubscriptionsListResponse)
async def list_subscriptions(
    db: Session = Depends(get_db)
):
    """
    List all push subscriptions (admin endpoint).

    Returns all registered push subscriptions for debugging and administration.
    Endpoints are truncated for security.

    **Response:**
    ```json
    {
        "subscriptions": [
            {
                "id": "uuid",
                "user_id": "uuid-or-null",
                "endpoint": "...truncated...",
                "user_agent": "Mozilla/5.0...",
                "created_at": "2025-12-10T10:30:00Z",
                "last_used_at": "2025-12-10T14:22:00Z"
            }
        ],
        "total": 42
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        subscriptions = db.query(PushSubscription).order_by(
            PushSubscription.created_at.desc()
        ).all()

        items = []
        for sub in subscriptions:
            items.append(SubscriptionListItem(
                id=sub.id,
                user_id=sub.user_id,
                endpoint=_truncate_endpoint(sub.endpoint),
                user_agent=sub.user_agent,
                created_at=sub.created_at.isoformat() if sub.created_at else None,
                last_used_at=sub.last_used_at.isoformat() if sub.last_used_at else None,
            ))

        return SubscriptionsListResponse(
            subscriptions=items,
            total=len(items)
        )

    except Exception as e:
        logger.error(f"Error listing push subscriptions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list push subscriptions"
        )


# ============================================================================
# Helper Functions
# ============================================================================


def _truncate_endpoint(endpoint: str) -> str:
    """
    Truncate endpoint URL for display/logging security.

    Push endpoints contain sensitive tokens that should not be fully exposed.
    """
    if not endpoint:
        return ""

    if len(endpoint) > 60:
        return endpoint[:30] + "..." + endpoint[-20:]
    return endpoint


# ============================================================================
# Test Notification Endpoint (Story P4-1.2)
# ============================================================================


class TestNotificationResult(BaseModel):
    """Result for a single subscription in test."""
    subscription_id: str
    success: bool
    error: Optional[str] = None


class TestNotificationResponse(BaseModel):
    """Response from test notification endpoint."""
    success: bool
    message: str
    results: Optional[List[TestNotificationResult]] = None


@router.post("/test", response_model=TestNotificationResponse)
async def send_test_notification(
    db: Session = Depends(get_db)
):
    """
    Send a test push notification to all subscribed devices.

    Used to verify push notification setup is working correctly.
    Sends a sample notification to all registered subscriptions.

    **Response:**
    ```json
    {
        "success": true,
        "message": "Test notification sent to 2 subscriptions",
        "results": [
            {"subscription_id": "uuid", "success": true},
            {"subscription_id": "uuid", "success": false, "error": "expired"}
        ]
    }
    ```

    **Status Codes:**
    - 200: Test completed (check individual results for delivery status)
    - 500: Internal server error
    """
    try:
        service = PushNotificationService(db)

        # Send test notification to all subscriptions
        notification_results = await service.broadcast_notification(
            title="Test Notification",
            body="If you see this, push notifications are working correctly!",
            data={
                "type": "test",
                "url": "/settings"
            },
            tag="test-notification"
        )

        if not notification_results:
            return TestNotificationResponse(
                success=True,
                message="No push subscriptions found. Enable notifications first.",
                results=[]
            )

        # Convert results to response format
        results = [
            TestNotificationResult(
                subscription_id=r.subscription_id,
                success=r.success,
                error=r.error if not r.success else None
            )
            for r in notification_results
        ]

        success_count = sum(1 for r in results if r.success)
        total_count = len(results)

        return TestNotificationResponse(
            success=success_count > 0,
            message=f"Test notification sent to {success_count}/{total_count} subscriptions",
            results=results
        )

    except Exception as e:
        logger.error(f"Error sending test notification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send test notification"
        )


# ============================================================================
# Notification Preferences (Story P4-1.4)
# ============================================================================

# Valid object types for filtering
VALID_OBJECT_TYPES = ["person", "vehicle", "package", "animal"]

# Common timezones for dropdown
COMMON_TIMEZONES = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Anchorage",
    "Pacific/Honolulu",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Australia/Sydney",
]


class NotificationPreferencesRequest(BaseModel):
    """Request body for getting preferences by subscription endpoint."""
    endpoint: str = Field(..., description="Push subscription endpoint URL")


class NotificationPreferencesUpdate(BaseModel):
    """Request body for updating notification preferences."""
    endpoint: str = Field(..., description="Push subscription endpoint URL to identify subscription")
    enabled_cameras: Optional[List[str]] = Field(None, description="List of enabled camera IDs (null = all)")
    enabled_object_types: Optional[List[str]] = Field(None, description="List of enabled object types (null = all)")
    quiet_hours_enabled: bool = Field(False, description="Whether quiet hours are enabled")
    quiet_hours_start: Optional[str] = Field(None, description="Quiet hours start time (HH:MM)")
    quiet_hours_end: Optional[str] = Field(None, description="Quiet hours end time (HH:MM)")
    timezone: str = Field("UTC", description="IANA timezone string")
    sound_enabled: bool = Field(True, description="Whether notification sound is enabled")

    class Config:
        json_schema_extra = {
            "example": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/...",
                "enabled_cameras": None,
                "enabled_object_types": ["person", "vehicle"],
                "quiet_hours_enabled": True,
                "quiet_hours_start": "22:00",
                "quiet_hours_end": "07:00",
                "timezone": "America/New_York",
                "sound_enabled": True
            }
        }


class NotificationPreferencesResponse(BaseModel):
    """Response containing notification preferences."""
    id: str = Field(..., description="Preference record UUID")
    subscription_id: str = Field(..., description="Associated subscription UUID")
    enabled_cameras: Optional[List[str]] = Field(None, description="List of enabled camera IDs (null = all)")
    enabled_object_types: Optional[List[str]] = Field(None, description="List of enabled object types (null = all)")
    quiet_hours_enabled: bool = Field(..., description="Whether quiet hours are enabled")
    quiet_hours_start: Optional[str] = Field(None, description="Quiet hours start time (HH:MM)")
    quiet_hours_end: Optional[str] = Field(None, description="Quiet hours end time (HH:MM)")
    timezone: str = Field(..., description="IANA timezone string")
    sound_enabled: bool = Field(..., description="Whether notification sound is enabled")
    created_at: Optional[str] = Field(None, description="ISO 8601 creation timestamp")
    updated_at: Optional[str] = Field(None, description="ISO 8601 last update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "subscription_id": "660e8400-e29b-41d4-a716-446655440001",
                "enabled_cameras": None,
                "enabled_object_types": ["person", "vehicle"],
                "quiet_hours_enabled": True,
                "quiet_hours_start": "22:00",
                "quiet_hours_end": "07:00",
                "timezone": "America/New_York",
                "sound_enabled": True,
                "created_at": "2025-12-10T10:30:00Z",
                "updated_at": "2025-12-10T14:22:00Z"
            }
        }


@router.post("/preferences", response_model=NotificationPreferencesResponse)
async def get_preferences(
    request: NotificationPreferencesRequest,
    db: Session = Depends(get_db)
):
    """
    Get notification preferences for a subscription.

    Returns the notification preferences for the subscription identified by endpoint.
    If no preferences exist, creates default preferences (all notifications enabled).

    **Request Body:**
    ```json
    {
        "endpoint": "https://fcm.googleapis.com/fcm/send/..."
    }
    ```

    **Response:**
    ```json
    {
        "id": "uuid",
        "subscription_id": "uuid",
        "enabled_cameras": null,
        "enabled_object_types": null,
        "quiet_hours_enabled": false,
        "quiet_hours_start": null,
        "quiet_hours_end": null,
        "timezone": "UTC",
        "sound_enabled": true,
        "created_at": "2025-12-10T10:30:00Z",
        "updated_at": "2025-12-10T10:30:00Z"
    }
    ```

    **Status Codes:**
    - 200: Success
    - 404: Subscription not found
    - 500: Internal server error
    """
    try:
        # Find subscription by endpoint
        subscription = db.query(PushSubscription).filter(
            PushSubscription.endpoint == request.endpoint
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        # Get or create preferences
        preference = db.query(NotificationPreference).filter(
            NotificationPreference.subscription_id == subscription.id
        ).first()

        if not preference:
            # Create default preferences
            preference = NotificationPreference.create_default(subscription.id)
            db.add(preference)
            db.commit()
            db.refresh(preference)

            logger.info(
                f"Created default notification preferences",
                extra={"subscription_id": subscription.id, "preference_id": preference.id}
            )

        return NotificationPreferencesResponse(
            id=preference.id,
            subscription_id=preference.subscription_id,
            enabled_cameras=preference.enabled_cameras,
            enabled_object_types=preference.enabled_object_types,
            quiet_hours_enabled=preference.quiet_hours_enabled,
            quiet_hours_start=preference.quiet_hours_start,
            quiet_hours_end=preference.quiet_hours_end,
            timezone=preference.timezone,
            sound_enabled=preference.sound_enabled,
            created_at=preference.created_at.isoformat() if preference.created_at else None,
            updated_at=preference.updated_at.isoformat() if preference.updated_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notification preferences: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get notification preferences"
        )


@router.put("/preferences", response_model=NotificationPreferencesResponse)
async def update_preferences(
    request: NotificationPreferencesUpdate,
    db: Session = Depends(get_db)
):
    """
    Update notification preferences for a subscription.

    Updates the notification preferences for the subscription identified by endpoint.
    Creates default preferences first if they don't exist.

    **Request Body:**
    ```json
    {
        "endpoint": "https://fcm.googleapis.com/fcm/send/...",
        "enabled_cameras": ["cam-uuid-1", "cam-uuid-2"],
        "enabled_object_types": ["person", "vehicle"],
        "quiet_hours_enabled": true,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "07:00",
        "timezone": "America/New_York",
        "sound_enabled": true
    }
    ```

    **Response:**
    Returns the updated preferences (same format as GET).

    **Status Codes:**
    - 200: Success
    - 400: Invalid request data (bad timezone, invalid time format, etc.)
    - 404: Subscription not found
    - 500: Internal server error
    """
    try:
        # Validate object types
        if request.enabled_object_types is not None:
            invalid_types = [t for t in request.enabled_object_types if t not in VALID_OBJECT_TYPES]
            if invalid_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid object types: {invalid_types}. Valid types: {VALID_OBJECT_TYPES}"
                )

        # Validate time format if provided
        if request.quiet_hours_enabled:
            if not request.quiet_hours_start or not request.quiet_hours_end:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="quiet_hours_start and quiet_hours_end are required when quiet_hours_enabled is true"
                )

            # Validate HH:MM format
            import re
            time_pattern = re.compile(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')
            if not time_pattern.match(request.quiet_hours_start):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid quiet_hours_start format: {request.quiet_hours_start}. Expected HH:MM"
                )
            if not time_pattern.match(request.quiet_hours_end):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid quiet_hours_end format: {request.quiet_hours_end}. Expected HH:MM"
                )

        # Validate timezone
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(request.timezone)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid timezone: {request.timezone}. Use IANA timezone format (e.g., 'America/New_York')"
            )

        # Find subscription by endpoint
        subscription = db.query(PushSubscription).filter(
            PushSubscription.endpoint == request.endpoint
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        # Get or create preferences
        preference = db.query(NotificationPreference).filter(
            NotificationPreference.subscription_id == subscription.id
        ).first()

        if not preference:
            # Create default preferences first
            preference = NotificationPreference.create_default(subscription.id)
            db.add(preference)
            db.flush()

        # Update preferences
        preference.enabled_cameras = request.enabled_cameras
        preference.enabled_object_types = request.enabled_object_types
        preference.quiet_hours_enabled = request.quiet_hours_enabled
        preference.quiet_hours_start = request.quiet_hours_start
        preference.quiet_hours_end = request.quiet_hours_end
        preference.timezone = request.timezone
        preference.sound_enabled = request.sound_enabled
        preference.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(preference)

        logger.info(
            f"Updated notification preferences",
            extra={
                "subscription_id": subscription.id,
                "preference_id": preference.id,
                "quiet_hours_enabled": preference.quiet_hours_enabled,
                "sound_enabled": preference.sound_enabled
            }
        )

        return NotificationPreferencesResponse(
            id=preference.id,
            subscription_id=preference.subscription_id,
            enabled_cameras=preference.enabled_cameras,
            enabled_object_types=preference.enabled_object_types,
            quiet_hours_enabled=preference.quiet_hours_enabled,
            quiet_hours_start=preference.quiet_hours_start,
            quiet_hours_end=preference.quiet_hours_end,
            timezone=preference.timezone,
            sound_enabled=preference.sound_enabled,
            created_at=preference.created_at.isoformat() if preference.created_at else None,
            updated_at=preference.updated_at.isoformat() if preference.updated_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating notification preferences: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update notification preferences"
        )
