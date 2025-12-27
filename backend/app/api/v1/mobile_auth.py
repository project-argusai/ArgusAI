"""
Mobile Authentication API (Epic P12-3)

Endpoints for mobile device pairing and token management:
- POST /api/v1/mobile/auth/pair - Generate pairing code
- POST /api/v1/mobile/auth/confirm - Confirm code (web dashboard)
- GET /api/v1/mobile/auth/status - Check pairing status
- POST /api/v1/mobile/auth/exchange - Exchange code for tokens
- POST /api/v1/mobile/auth/refresh - Refresh access token
- POST /api/v1/mobile/auth/revoke - Revoke tokens
- GET /api/v1/mobile/auth/pending - List pending pairings
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.device import Device
from app.services.mobile.pairing_service import PairingService
from app.services.mobile.token_service import TokenService
from app.schemas.mobile_auth import (
    PairingRequest,
    PairingCodeResponse,
    PairingConfirmRequest,
    PairingConfirmResponse,
    PairingStatusResponse,
    TokenExchangeRequest,
    TokenPair,
    TokenRefreshRequest,
    TokenRevokeRequest,
    TokenRevokeResponse,
    PendingPairingsResponse,
    PendingPairingInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mobile/auth", tags=["Mobile Authentication"])


# ============================================================================
# Pairing Endpoints (P12-3.2, P12-3.3)
# ============================================================================

@router.post(
    "/pair",
    response_model=PairingCodeResponse,
    summary="Generate pairing code",
    description="Generate a 6-digit pairing code for mobile device registration. "
                "The code expires after 5 minutes.",
    responses={
        429: {"description": "Rate limit exceeded (5 attempts/minute)"},
    }
)
async def generate_pairing_code(
    request: PairingRequest,
    db: Session = Depends(get_db),
) -> PairingCodeResponse:
    """
    Generate a 6-digit pairing code for mobile device.

    This is called by the mobile app when the user wants to link their device.
    The code should be displayed to the user to enter in the web dashboard.
    """
    service = PairingService(db)

    try:
        pairing_code = service.generate_code(
            device_id=request.device_id,
            platform=request.platform,
            device_name=request.device_name,
            device_model=request.device_model,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )

    # Ensure expires_at is timezone-aware for comparison
    expires_at = pairing_code.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    expires_in = int((expires_at - datetime.now(timezone.utc)).total_seconds())

    return PairingCodeResponse(
        code=pairing_code.code,
        expires_in=expires_in,
        expires_at=expires_at,
    )


@router.post(
    "/confirm",
    response_model=PairingConfirmResponse,
    summary="Confirm pairing code",
    description="Confirm a pairing code from the web dashboard. "
                "Requires authentication.",
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Invalid or expired code"},
    }
)
async def confirm_pairing_code(
    request: PairingConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PairingConfirmResponse:
    """
    Confirm a pairing code from the web dashboard.

    This associates the pairing request with the authenticated user.
    After confirmation, the mobile app can exchange the code for tokens.
    """
    service = PairingService(db)

    pairing_code = service.confirm_code(request.code, current_user.id)

    if not pairing_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired pairing code"
        )

    return PairingConfirmResponse(
        confirmed=True,
        device_name=pairing_code.device_name,
        device_model=pairing_code.device_model,
        platform=pairing_code.platform,
    )


@router.get(
    "/status/{code}",
    response_model=PairingStatusResponse,
    summary="Check pairing status",
    description="Check if a pairing code has been confirmed. "
                "Called by mobile app to poll for confirmation.",
)
async def check_pairing_status(
    code: str,
    db: Session = Depends(get_db),
) -> PairingStatusResponse:
    """
    Check the status of a pairing code.

    Mobile app polls this endpoint to check if the user has
    confirmed the code in the web dashboard.
    """
    service = PairingService(db)
    status_dict = service.check_status(code)

    return PairingStatusResponse(**status_dict)


@router.get(
    "/pending",
    response_model=PendingPairingsResponse,
    summary="List pending pairings",
    description="List pending (unconfirmed) pairing requests. "
                "Requires authentication.",
    responses={
        401: {"description": "Not authenticated"},
    }
)
async def list_pending_pairings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PendingPairingsResponse:
    """
    List pending pairing requests for the web dashboard.

    Shows unconfirmed codes that are waiting for user approval.
    """
    service = PairingService(db)
    pairings = service.get_pending_pairings()

    return PendingPairingsResponse(
        pairings=[
            PendingPairingInfo(
                code=p.code,
                device_name=p.device_name,
                device_model=p.device_model,
                platform=p.platform,
                expires_at=p.expires_at,
                created_at=p.created_at,
            )
            for p in pairings
        ],
        total=len(pairings)
    )


@router.delete(
    "/pending/{code}",
    summary="Delete pending pairing",
    description="Delete/reject a pending pairing request. "
                "Requires authentication.",
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Pairing code not found"},
    }
)
async def delete_pending_pairing(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a pending pairing request.

    Allows the web dashboard to reject/cancel a pairing request.
    """
    service = PairingService(db)

    # Check if code exists
    pairing = service.get_pending_code(code)
    if not pairing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pairing code not found"
        )

    service.delete_code(code)

    logger.info(
        "Pairing request deleted",
        extra={
            "event_type": "pairing_deleted",
            "code": code[:3] + "***",
            "user_id": current_user.id,
        }
    )

    return {"message": "Pairing request deleted"}


# ============================================================================
# Token Endpoints (P12-3.4, P12-3.5, P12-3.6)
# ============================================================================

@router.post(
    "/exchange",
    response_model=TokenPair,
    summary="Exchange code for tokens",
    description="Exchange a confirmed pairing code for access and refresh tokens.",
    responses={
        401: {"description": "Invalid or unconfirmed code"},
    }
)
async def exchange_code_for_tokens(
    request: TokenExchangeRequest,
    db: Session = Depends(get_db),
) -> TokenPair:
    """
    Exchange a confirmed pairing code for JWT tokens.

    This is called by the mobile app after the code is confirmed.
    Returns access token (short-lived) and refresh token (long-lived).
    """
    pairing_service = PairingService(db)
    token_service = TokenService(db)

    # Get confirmed code
    pairing_code = pairing_service.get_confirmed_code(request.code)

    if not pairing_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or unconfirmed pairing code"
        )

    # Create or get device
    device = db.query(Device).filter(
        Device.device_id == pairing_code.device_id
    ).first()

    if not device:
        # Create new device
        device = Device(
            user_id=pairing_code.user_id,
            device_id=pairing_code.device_id,
            platform=pairing_code.platform,
            name=pairing_code.device_name,
            device_model=pairing_code.device_model,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
    else:
        # Update device ownership
        device.user_id = pairing_code.user_id
        device.platform = pairing_code.platform
        if pairing_code.device_name:
            device.name = pairing_code.device_name
        if pairing_code.device_model:
            device.device_model = pairing_code.device_model
        db.commit()

    # Generate tokens
    access_token, refresh_token, expires_in = token_service.create_token_pair(
        device_id=device.id,
        user_id=pairing_code.user_id,
    )

    # Delete used pairing code
    pairing_service.delete_code(request.code)

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        device_id=device.id,
    )


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Refresh access token",
    description="Refresh an expired access token using a refresh token. "
                "Implements token rotation for security.",
    responses={
        401: {"description": "Invalid or revoked refresh token"},
    }
)
async def refresh_access_token(
    request: TokenRefreshRequest,
    db: Session = Depends(get_db),
) -> TokenPair:
    """
    Refresh access token using refresh token.

    Implements token rotation: the old refresh token is revoked
    and a new one is issued with each refresh.
    """
    token_service = TokenService(db)

    result = token_service.refresh_tokens(
        refresh_token=request.refresh_token,
        device_id=request.device_id,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token"
        )

    access_token, new_refresh_token, expires_in = result

    # If no new refresh token, return the old one (grace period case)
    if not new_refresh_token:
        new_refresh_token = request.refresh_token

    return TokenPair(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        device_id=request.device_id,
    )


@router.post(
    "/revoke",
    response_model=TokenRevokeResponse,
    summary="Revoke tokens",
    description="Revoke refresh tokens. Can revoke a specific token, "
                "all tokens for a device, or all user tokens.",
    responses={
        401: {"description": "Not authenticated"},
    }
)
async def revoke_tokens(
    request: TokenRevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TokenRevokeResponse:
    """
    Revoke refresh tokens.

    Options:
    - Specific token: Provide refresh_token
    - Device tokens: Provide device_id
    - All user tokens: Set revoke_all=True
    """
    token_service = TokenService(db)
    revoked_count = 0

    if request.refresh_token:
        if token_service.revoke_token(request.refresh_token, "logout"):
            revoked_count = 1

    elif request.device_id:
        # Verify device belongs to user
        device = db.query(Device).filter(
            Device.id == request.device_id,
            Device.user_id == current_user.id,
        ).first()

        if device:
            revoked_count = token_service.revoke_device_tokens(request.device_id, "logout")

    elif request.revoke_all:
        revoked_count = token_service.revoke_user_tokens(current_user.id, "logout_all")

    return TokenRevokeResponse(revoked_count=revoked_count)
