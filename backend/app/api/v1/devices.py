"""
Device Registration API endpoints (Story P11-2.4, P11-2.5)

Endpoints for mobile device registration and token management:
- POST /api/v1/devices - Register new device
- GET /api/v1/devices - List user's devices
- DELETE /api/v1/devices/{device_id} - Revoke device
- PUT /api/v1/devices/{device_id}/token - Update push token
- PUT /api/v1/devices/{device_id}/preferences - Update device preferences (quiet hours)
"""
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.device import Device
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.schemas.device import (
    DeviceCreate,
    DeviceTokenUpdate,
    DeviceResponse,
    DeviceListResponse,
    DeviceRegistrationResponse,
    DevicePreferencesUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/devices",
    tags=["devices"]
)


@router.post(
    "",
    response_model=DeviceRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a device",
    description="Register a new device or update existing device for push notifications. Upserts on device_id.",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def register_device(
    device_data: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeviceRegistrationResponse:
    """
    Register a device for push notifications.

    If a device with the same device_id already exists, updates it (upsert behavior).
    Push token is encrypted at rest using Fernet encryption.

    Args:
        device_data: Device registration data
        db: Database session
        current_user: Authenticated user

    Returns:
        DeviceRegistrationResponse with device info and is_new flag
    """
    # Check for existing device (upsert logic)
    existing_device = db.query(Device).filter(
        Device.device_id == device_data.device_id
    ).first()

    is_new = False

    if existing_device:
        # Update existing device
        existing_device.platform = device_data.platform.value
        existing_device.name = device_data.name
        if device_data.push_token:
            existing_device.set_push_token(device_data.push_token)
        # Update quiet hours if provided (Story P11-2.5)
        if device_data.quiet_hours_enabled is not None:
            existing_device.quiet_hours_enabled = device_data.quiet_hours_enabled
        if device_data.quiet_hours_start is not None:
            existing_device.quiet_hours_start = device_data.quiet_hours_start
        if device_data.quiet_hours_end is not None:
            existing_device.quiet_hours_end = device_data.quiet_hours_end
        if device_data.quiet_hours_timezone is not None:
            existing_device.quiet_hours_timezone = device_data.quiet_hours_timezone
        if device_data.quiet_hours_override_critical is not None:
            existing_device.quiet_hours_override_critical = device_data.quiet_hours_override_critical
        existing_device.update_last_seen()
        # Reassign to current user if different (device transferred)
        existing_device.user_id = current_user.id

        db.commit()
        db.refresh(existing_device)

        logger.info(
            f"Updated device registration",
            extra={
                "device_id": device_data.device_id,
                "user_id": current_user.id,
                "platform": device_data.platform.value,
            }
        )

        return DeviceRegistrationResponse(
            id=existing_device.id,
            device_id=existing_device.device_id,
            platform=existing_device.platform,
            created_at=existing_device.created_at,
            is_new=False,
        )
    else:
        # Create new device
        is_new = True
        device = Device(
            user_id=current_user.id,
            device_id=device_data.device_id,
            platform=device_data.platform.value,
            name=device_data.name,
            # Quiet hours (Story P11-2.5)
            quiet_hours_enabled=device_data.quiet_hours_enabled or False,
            quiet_hours_start=device_data.quiet_hours_start,
            quiet_hours_end=device_data.quiet_hours_end,
            quiet_hours_timezone=device_data.quiet_hours_timezone or "UTC",
            quiet_hours_override_critical=device_data.quiet_hours_override_critical if device_data.quiet_hours_override_critical is not None else True,
        )
        if device_data.push_token:
            device.set_push_token(device_data.push_token)

        db.add(device)
        db.commit()
        db.refresh(device)

        logger.info(
            f"New device registered",
            extra={
                "device_id": device_data.device_id,
                "user_id": current_user.id,
                "platform": device_data.platform.value,
            }
        )

        return DeviceRegistrationResponse(
            id=device.id,
            device_id=device.device_id,
            platform=device.platform,
            created_at=device.created_at,
            is_new=True,
        )


@router.get(
    "",
    response_model=DeviceListResponse,
    summary="List user's devices",
    description="Get all devices registered for the current user.",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def list_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeviceListResponse:
    """
    List all devices registered for the current user.

    Push tokens are excluded from response for security.

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        DeviceListResponse with list of devices
    """
    devices = db.query(Device).filter(
        Device.user_id == current_user.id
    ).order_by(Device.created_at.desc()).all()

    device_responses = [
        DeviceResponse(
            id=d.id,
            user_id=d.user_id,
            device_id=d.device_id,
            platform=d.platform,
            name=d.name,
            last_seen_at=d.last_seen_at,
            created_at=d.created_at,
            # Quiet hours (Story P11-2.5)
            quiet_hours_enabled=d.quiet_hours_enabled,
            quiet_hours_start=d.quiet_hours_start,
            quiet_hours_end=d.quiet_hours_end,
            quiet_hours_timezone=d.quiet_hours_timezone,
            quiet_hours_override_critical=d.quiet_hours_override_critical,
        )
        for d in devices
    ]

    return DeviceListResponse(
        devices=device_responses,
        total=len(device_responses),
    )


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a device",
    description="Remove a device from the current user's registered devices.",
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Device not found"},
    },
)
async def revoke_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Revoke (delete) a device registration.

    Only the device owner can revoke the device.

    Args:
        device_id: The device_id to revoke
        db: Database session
        current_user: Authenticated user

    Raises:
        HTTPException: 404 if device not found or not owned by user
    """
    device = db.query(Device).filter(
        Device.device_id == device_id,
        Device.user_id == current_user.id,
    ).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    db.delete(device)
    db.commit()

    logger.info(
        f"Device revoked",
        extra={
            "device_id": device_id,
            "user_id": current_user.id,
        }
    )


@router.put(
    "/{device_id}/token",
    response_model=dict,
    summary="Update device push token",
    description="Update the push notification token for a device. Called when APNS/FCM refreshes the token.",
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Device not found"},
    },
)
async def update_device_token(
    device_id: str,
    token_data: DeviceTokenUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Update the push token for a device.

    Called when APNS or FCM issues a new token (token refresh).
    Token is encrypted at rest using Fernet encryption.

    Args:
        device_id: The device_id to update
        token_data: New push token
        db: Database session
        current_user: Authenticated user

    Returns:
        Success status

    Raises:
        HTTPException: 404 if device not found or not owned by user
    """
    device = db.query(Device).filter(
        Device.device_id == device_id,
        Device.user_id == current_user.id,
    ).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    device.set_push_token(token_data.push_token)
    device.update_last_seen()
    db.commit()

    logger.info(
        f"Device token updated",
        extra={
            "device_id": device_id,
            "user_id": current_user.id,
        }
    )

    return {"success": True, "message": "Token updated successfully"}


@router.put(
    "/{device_id}/preferences",
    response_model=DeviceResponse,
    summary="Update device preferences (Story P11-2.5)",
    description="Update quiet hours and notification preferences for a device.",
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Device not found"},
    },
)
async def update_device_preferences(
    device_id: str,
    preferences: DevicePreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeviceResponse:
    """
    Update device preferences (quiet hours).

    Allows users to configure quiet hours for a specific device:
    - quiet_hours_enabled: Enable/disable quiet hours
    - quiet_hours_start: Start time in HH:MM format
    - quiet_hours_end: End time in HH:MM format
    - quiet_hours_timezone: IANA timezone
    - quiet_hours_override_critical: Allow critical alerts during quiet hours

    Args:
        device_id: The device_id to update
        preferences: New preference values (only provided fields are updated)
        db: Database session
        current_user: Authenticated user

    Returns:
        Updated DeviceResponse

    Raises:
        HTTPException: 404 if device not found or not owned by user
    """
    device = db.query(Device).filter(
        Device.device_id == device_id,
        Device.user_id == current_user.id,
    ).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    # Update only provided fields
    if preferences.quiet_hours_enabled is not None:
        device.quiet_hours_enabled = preferences.quiet_hours_enabled
    if preferences.quiet_hours_start is not None:
        device.quiet_hours_start = preferences.quiet_hours_start
    if preferences.quiet_hours_end is not None:
        device.quiet_hours_end = preferences.quiet_hours_end
    if preferences.quiet_hours_timezone is not None:
        device.quiet_hours_timezone = preferences.quiet_hours_timezone
    if preferences.quiet_hours_override_critical is not None:
        device.quiet_hours_override_critical = preferences.quiet_hours_override_critical

    device.update_last_seen()
    db.commit()
    db.refresh(device)

    logger.info(
        f"Device preferences updated",
        extra={
            "device_id": device_id,
            "user_id": current_user.id,
            "quiet_hours_enabled": device.quiet_hours_enabled,
        }
    )

    return DeviceResponse(
        id=device.id,
        user_id=device.user_id,
        device_id=device.device_id,
        platform=device.platform,
        name=device.name,
        last_seen_at=device.last_seen_at,
        created_at=device.created_at,
        quiet_hours_enabled=device.quiet_hours_enabled,
        quiet_hours_start=device.quiet_hours_start,
        quiet_hours_end=device.quiet_hours_end,
        quiet_hours_timezone=device.quiet_hours_timezone,
        quiet_hours_override_critical=device.quiet_hours_override_critical,
    )
