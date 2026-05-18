"""
API Key Management Endpoints.

Story P13-1.2: Implement API Key Generation Endpoint
Story P13-1.3: Implement API Key List and Revoke Endpoints

Provides endpoints for:
- Creating new API keys
- Listing all API keys
- Revoking API keys
- Getting usage statistics
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.schemas.api_key import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyListResponse,
    APIKeyUsageResponse,
    MessageResponse,
    VALID_SCOPES,
)
from app.services.service_container import container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new API key",
    description="""
    Create a new API key for external integrations.

    **IMPORTANT**: The full API key is only returned in this response.
    It is never stored and cannot be retrieved again. Save it securely!

    **Scopes**:
    - `read:events` - Read access to events
    - `read:cameras` - Read access to cameras
    - `write:cameras` - Write access to cameras
    - `admin` - Full access (includes all other scopes)
    """,
)
async def create_api_key(
    request: APIKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new API key. Returns the key ONLY ONCE."""
    # Validate scopes
    invalid_scopes = set(request.scopes) - VALID_SCOPES
    if invalid_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scopes: {', '.join(invalid_scopes)}. Valid scopes: {', '.join(VALID_SCOPES)}"
        )

    if not request.scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one scope is required"
        )

    service = container.api_key_service

    try:
        api_key, plaintext_key = service.generate_api_key(
            db=db,
            name=request.name,
            scopes=request.scopes,
            created_by=current_user.id,
            expires_at=request.expires_at,
            rate_limit_per_minute=request.rate_limit_per_minute,
        )

        return APIKeyCreateResponse(
            id=api_key.id,
            name=api_key.name,
            key=plaintext_key,  # Only time the full key is returned
            prefix=f"argus_{api_key.prefix}...",
            scopes=api_key.scopes,
            expires_at=api_key.expires_at,
            rate_limit_per_minute=api_key.rate_limit_per_minute,
            created_at=api_key.created_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "",
    response_model=list[APIKeyListResponse],
    summary="List all API keys",
    description="List all API keys. Does not expose the full key value.",
)
async def list_api_keys(
    include_revoked: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all API keys (without exposing the key itself)."""
    service = container.api_key_service
    keys = service.list_keys(db, include_revoked=include_revoked)

    return [
        APIKeyListResponse(
            id=key.id,
            name=key.name,
            prefix=f"argus_{key.prefix}...",
            scopes=key.scopes,
            is_active=key.is_active,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            usage_count=key.usage_count,
            rate_limit_per_minute=key.rate_limit_per_minute,
            created_at=key.created_at,
            revoked_at=key.revoked_at,
        )
        for key in keys
    ]


@router.get(
    "/{key_id}",
    response_model=APIKeyListResponse,
    summary="Get API key details",
    description="Get details for a specific API key.",
)
async def get_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific API key by ID."""
    service = container.api_key_service
    api_key = service.get_key(db, key_id)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    return APIKeyListResponse(
        id=api_key.id,
        name=api_key.name,
        prefix=f"argus_{api_key.prefix}...",
        scopes=api_key.scopes,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        usage_count=api_key.usage_count,
        rate_limit_per_minute=api_key.rate_limit_per_minute,
        created_at=api_key.created_at,
        revoked_at=api_key.revoked_at,
    )


@router.delete(
    "/{key_id}",
    response_model=MessageResponse,
    summary="Revoke API key",
    description="Revoke an API key immediately. This cannot be undone.",
)
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke an API key immediately."""
    service = container.api_key_service
    api_key = service.revoke_key(db, key_id, revoked_by=current_user.id)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    return MessageResponse(message="API key revoked successfully")


@router.get(
    "/{key_id}/usage",
    response_model=APIKeyUsageResponse,
    summary="Get API key usage",
    description="Get usage statistics for a specific API key.",
)
async def get_api_key_usage(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get usage statistics for an API key."""
    service = container.api_key_service
    api_key = service.get_key(db, key_id)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    return APIKeyUsageResponse(
        id=api_key.id,
        name=api_key.name,
        prefix=f"argus_{api_key.prefix}...",
        usage_count=api_key.usage_count,
        last_used_at=api_key.last_used_at,
        last_used_ip=api_key.last_used_ip,
        rate_limit_per_minute=api_key.rate_limit_per_minute,
        created_at=api_key.created_at,
    )
