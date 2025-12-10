"""
System Settings API

Endpoints for system-level configuration and monitoring:
    - Retention policy management (GET/PUT /retention)
    - Storage monitoring (GET /storage)
    - Backup and restore (POST /backup, GET /backup/{timestamp}/download, POST /restore)
"""
from fastapi import APIRouter, HTTPException, status, Depends, File, UploadFile, Form
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from pathlib import Path
import logging
import tempfile
import shutil

from app.schemas.system import (
    RetentionPolicyUpdate,
    RetentionPolicyResponse,
    StorageResponse,
    SystemSettings,
    SystemSettingsUpdate,
    CostCapStatus
)
from app.services.cleanup_service import get_cleanup_service
from app.services.backup_service import get_backup_service, BackupResult, RestoreResult, BackupInfo, ValidationResult
from app.core.database import get_db, SessionLocal
from app.models.system_setting import SystemSetting
from app.utils.encryption import encrypt_password, decrypt_password, mask_sensitive, is_encrypted

logger = logging.getLogger(__name__)

# Keys that contain sensitive data and should be encrypted
SENSITIVE_SETTING_KEYS = [
    "settings_primary_api_key",
    "settings_fallback_api_key",
    "ai_api_key_openai",
    "ai_api_key_claude",
    "ai_api_key_gemini",
    "ai_api_key_grok",  # Story P2-5.2: xAI Grok API key
]

router = APIRouter(
    prefix="/system",
    tags=["system"]
)


@router.get("/debug/ai-keys")
def debug_ai_keys(db: Session = Depends(get_db)):
    """Debug endpoint to check if AI keys are saved in database"""
    keys_to_check = [
        'ai_api_key_openai',
        'ai_api_key_claude',
        'ai_api_key_gemini',
        'settings_primary_api_key',
        'settings_primary_model',
    ]

    results = {}
    for key in keys_to_check:
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting:
            value = setting.value
            # Show if encrypted and first/last few chars
            if value.startswith('encrypted:'):
                results[key] = f"encrypted (length: {len(value)})"
            elif value.startswith('****'):
                results[key] = f"masked: {value}"
            else:
                results[key] = f"plaintext (first 4 chars): {value[:4]}... (length: {len(value)})"
        else:
            results[key] = "NOT FOUND"

    return results


@router.get("/debug/network")
def debug_network_test():
    """Debug endpoint to test network connectivity from server context"""
    import socket
    import ssl

    results = {}
    host = "10.0.1.254"
    port = 7441

    # Test 1: Raw socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        results["tcp_connect"] = "success"

        # Test 2: SSL wrap
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        ssock = context.wrap_socket(sock, server_hostname=host)
        results["ssl_wrap"] = f"success - {ssock.cipher()[0]}"
        ssock.close()
    except Exception as e:
        results["socket_error"] = f"{type(e).__name__}: {e}"

    # Test 3: PyAV
    try:
        import av
        url = "rtsps://homebridge:2003Isaac@10.0.1.254:7441/5e90Pa1x8zldOgmF?enableSrtp"
        container = av.open(url, options={'rtsp_transport': 'tcp'}, timeout=10)
        results["pyav_connect"] = f"success - {len(container.streams)} streams"
        container.close()
    except Exception as e:
        results["pyav_error"] = f"{type(e).__name__}: {e}"

    return results


def get_retention_policy_from_db(db: Optional[Session] = None) -> int:
    """
    Get current retention policy from system_settings table

    Args:
        db: Optional database session (creates new session if not provided)

    Returns:
        Retention days (default 30 if not set)
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "data_retention_days"
        ).first()

        if setting and setting.value:
            try:
                return int(setting.value)
            except ValueError:
                logger.warning(f"Invalid retention policy value: {setting.value}, using default 30")
                return 30
        else:
            # Default: 30 days
            logger.info("No retention policy set, using default 30 days")
            return 30

    except Exception as e:
        logger.error(f"Error getting retention policy: {e}", exc_info=True)
        return 30
    finally:
        if should_close:
            db.close()


def set_retention_policy_in_db(retention_days: int, db: Optional[Session] = None):
    """
    Set retention policy in system_settings table

    Args:
        retention_days: Number of days to retain events
        db: Optional database session (creates new session if not provided)
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "data_retention_days"
        ).first()

        if setting:
            setting.value = str(retention_days)
        else:
            setting = SystemSetting(
                key="data_retention_days",
                value=str(retention_days)
            )
            db.add(setting)

        db.commit()
        logger.info(f"Retention policy updated: {retention_days} days")

    except Exception as e:
        logger.error(f"Error setting retention policy: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update retention policy"
        )
    finally:
        if should_close:
            db.close()


def calculate_next_cleanup() -> Optional[str]:
    """
    Calculate next cleanup time (2:00 AM next day)

    Returns:
        ISO 8601 timestamp of next cleanup, or None if error
    """
    try:
        now = datetime.now(timezone.utc)
        # Next 2:00 AM
        next_cleanup = now.replace(hour=2, minute=0, second=0, microsecond=0)

        # If it's already past 2:00 AM today, go to tomorrow
        if now.hour >= 2:
            next_cleanup += timedelta(days=1)

        return next_cleanup.isoformat()

    except Exception as e:
        logger.error(f"Error calculating next cleanup: {e}", exc_info=True)
        return None


@router.get("/retention", response_model=RetentionPolicyResponse)
async def get_retention_policy(db: Session = Depends(get_db)):
    """
    Get current data retention policy

    Returns current retention policy configuration including:
    - Number of days events are retained
    - Whether retention is set to forever (retention_days <= 0)
    - Next scheduled cleanup time

    **Response:**
    ```json
    {
        "retention_days": 30,
        "next_cleanup": "2025-11-18T02:00:00Z",
        "forever": false
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        retention_days = get_retention_policy_from_db(db)
        forever = retention_days <= 0
        next_cleanup = calculate_next_cleanup() if not forever else None

        return RetentionPolicyResponse(
            retention_days=retention_days,
            next_cleanup=next_cleanup,
            forever=forever
        )

    except Exception as e:
        logger.error(f"Error getting retention policy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve retention policy"
        )


@router.put("/retention", response_model=RetentionPolicyResponse)
async def update_retention_policy(
    policy: RetentionPolicyUpdate,
    db: Session = Depends(get_db)
):
    """
    Update data retention policy

    Update how long events are retained before automatic cleanup.

    **Valid retention_days values:**
    - -1 or 0: Keep events forever (no automatic cleanup)
    - 7: Keep for 7 days
    - 30: Keep for 30 days (default)
    - 90: Keep for 90 days
    - 365: Keep for 1 year

    **Request Body:**
    ```json
    {
        "retention_days": 30
    }
    ```

    **Response:**
    ```json
    {
        "retention_days": 30,
        "next_cleanup": "2025-11-18T02:00:00Z",
        "forever": false
    }
    ```

    **Status Codes:**
    - 200: Success
    - 400: Invalid retention_days value
    - 500: Internal server error
    """
    try:
        # Validation is handled by Pydantic schema
        set_retention_policy_in_db(policy.retention_days, db)

        forever = policy.retention_days <= 0
        next_cleanup = calculate_next_cleanup() if not forever else None

        return RetentionPolicyResponse(
            retention_days=policy.retention_days,
            next_cleanup=next_cleanup,
            forever=forever
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating retention policy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update retention policy"
        )


@router.get("/storage", response_model=StorageResponse)
async def get_storage_info():
    """
    Get storage usage information

    Returns detailed storage statistics including:
    - Database size (SQLite file size via PRAGMA queries)
    - Thumbnails directory size (recursive calculation)
    - Total storage used
    - Number of events stored

    **Response:**
    ```json
    {
        "database_mb": 15.2,
        "thumbnails_mb": 8.5,
        "total_mb": 23.7,
        "event_count": 1234
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        cleanup_service = get_cleanup_service()
        storage_info = await cleanup_service.get_storage_info()

        return StorageResponse(**storage_info)

    except Exception as e:
        logger.error(f"Error getting storage info: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve storage information"
        )


# Settings key prefix for all system settings
SETTINGS_PREFIX = "settings_"


def _get_setting_from_db(db: Session, key: str, default: any = None) -> any:
    """Get a single setting value from database"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return setting.value if setting else default


def _set_setting_in_db(db: Session, key: str, value: any):
    """Set a single setting value in database, encrypting sensitive values"""
    # Convert to string if needed
    str_value = str(value) if not isinstance(value, str) else value

    # Encrypt sensitive values (API keys)
    if key in SENSITIVE_SETTING_KEYS and str_value and not is_encrypted(str_value):
        str_value = encrypt_password(str_value)
        logger.debug(f"Encrypted sensitive setting: {key}")

    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = str_value
    else:
        setting = SystemSetting(key=key, value=str_value)
        db.add(setting)
    db.commit()


@router.get("/settings", response_model=SystemSettings)
async def get_settings(db: Session = Depends(get_db)):
    """
    Get all system settings

    Returns complete system configuration including general settings,
    AI model configuration, motion detection parameters, and data retention settings.

    **Note:** API keys are masked for security (only last 4 characters shown).

    **Response:**
    ```json
    {
        "system_name": "Live Object AI Classifier",
        "timezone": "America/Los_Angeles",
        "primary_api_key": "****abcd",
        ...
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        # Load all settings from database, use defaults if not set
        settings_dict = {}

        # Fields that contain sensitive data (API keys)
        sensitive_fields = ["primary_api_key", "fallback_api_key"]

        # Get all settings fields from the schema
        for field_name, field_info in SystemSettings.model_fields.items():
            db_value = _get_setting_from_db(db, f"{SETTINGS_PREFIX}{field_name}")

            if db_value is not None:
                # Decrypt and mask sensitive fields for response
                if field_name in sensitive_fields:
                    if is_encrypted(db_value):
                        # Decrypt to get original, then mask for display
                        try:
                            decrypted = decrypt_password(db_value)
                            settings_dict[field_name] = mask_sensitive(decrypted)
                        except ValueError:
                            settings_dict[field_name] = "****[invalid]"
                    else:
                        # Old unencrypted value - mask it
                        settings_dict[field_name] = mask_sensitive(db_value)
                # Convert string back to appropriate type
                elif field_info.annotation == bool:
                    settings_dict[field_name] = db_value.lower() in ('true', '1', 'yes')
                elif field_info.annotation == int:
                    settings_dict[field_name] = int(db_value)
                elif field_info.annotation == float:
                    settings_dict[field_name] = float(db_value)
                else:
                    settings_dict[field_name] = db_value
            else:
                # Use default from schema
                if field_info.default is not None:
                    settings_dict[field_name] = field_info.default

        return SystemSettings(**settings_dict)

    except Exception as e:
        logger.error(f"Error getting settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve settings"
        )


@router.put("/settings", response_model=SystemSettings)
async def update_settings(
    settings_update: SystemSettingsUpdate,
    db: Session = Depends(get_db)
):
    """
    Update system settings (partial update)

    Accepts partial updates - only provided fields will be updated.
    Automatically handles type conversion and validation.

    **Request Body:**
    ```json
    {
        "system_name": "My Custom Name",
        "motion_sensitivity": 75
    }
    ```

    **Response:**
    Returns complete updated settings object.

    **Status Codes:**
    - 200: Success
    - 400: Validation error
    - 500: Internal server error
    """
    try:
        # Update only provided fields
        update_data = settings_update.model_dump(exclude_unset=True)

        # Fields that should be saved WITHOUT the settings_ prefix
        # These are read directly by AI service (Story P2-5.2, P2-5.3)
        # and cost cap service (Story P3-7.3)
        no_prefix_fields = {
            'ai_api_key_openai',
            'ai_api_key_grok',
            'ai_api_key_claude',
            'ai_api_key_gemini',
            'ai_provider_order',
            'ai_daily_cost_cap',   # Story P3-7.3
            'ai_monthly_cost_cap',  # Story P3-7.3
            'store_analysis_frames',  # Story P3-7.5
        }

        for field_name, value in update_data.items():
            if value is not None:  # Only update non-None values
                # Skip masked API key values
                if field_name in ('primary_api_key', 'fallback_api_key') and isinstance(value, str) and value.startswith('****'):
                    logger.debug(f"Skipping masked value for {field_name}")
                    continue

                # AI provider fields are saved without prefix (Story P2-5.2, P2-5.3)
                if field_name in no_prefix_fields:
                    _set_setting_in_db(db, field_name, value)
                    logger.info(f"Saved AI provider setting: {field_name}")
                else:
                    _set_setting_in_db(db, f"{SETTINGS_PREFIX}{field_name}", value)

        # If API key was updated (and not a masked value), also save it with provider-specific key name
        # so AI service can find it
        if 'primary_api_key' in update_data and update_data['primary_api_key']:
            api_key = update_data['primary_api_key']

            # Skip masked values (they start with ****)
            if api_key.startswith('****'):
                logger.debug("Skipping masked API key value")
            else:
                # Get the model to determine the provider
                model = update_data.get('primary_model')
                if not model:
                    # Get current model from database
                    model_setting = _get_setting_from_db(db, f"{SETTINGS_PREFIX}primary_model")
                    model = model_setting or 'gpt-4o-mini'

                # Map model to provider key name
                model_to_key = {
                    'gpt-4o-mini': 'ai_api_key_openai',
                    'claude-3-haiku': 'ai_api_key_claude',
                    'gemini-flash': 'ai_api_key_gemini',
                }
                provider_key = model_to_key.get(model)
                if provider_key:
                    _set_setting_in_db(db, provider_key, api_key)
                    logger.info(f"Saved API key for provider: {provider_key}")

        # Return complete updated settings
        return await get_settings(db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings"
        )


# ============================================================================
# AI API Key Management
# ============================================================================


class TestKeyRequest(BaseModel):
    """Request body for API key test endpoint"""
    provider: Literal["openai", "anthropic", "google", "grok"] = Field(
        ..., description="AI provider to test"
    )
    api_key: str = Field(..., min_length=1, description="API key to test")


class TestKeyResponse(BaseModel):
    """Response from API key test endpoint"""
    valid: bool = Field(..., description="Whether the key is valid")
    message: str = Field(..., description="Result message")
    provider: str = Field(..., description="Provider that was tested")


@router.post("/test-key", response_model=TestKeyResponse)
async def test_api_key(request: TestKeyRequest):
    """
    Test an AI provider API key without saving it

    Makes a lightweight validation request to the specified AI provider
    to verify the API key works. The key is NOT stored.

    **Request Body:**
    ```json
    {
        "provider": "openai",
        "api_key": "sk-..."
    }
    ```

    **Response:**
    ```json
    {
        "valid": true,
        "message": "API key validated successfully",
        "provider": "openai"
    }
    ```

    **Status Codes:**
    - 200: Key validation result returned
    - 400: Invalid request
    - 500: Internal server error
    """
    try:
        provider = request.provider
        api_key = request.api_key

        # Log test attempt (masked key)
        logger.info(f"Testing API key for provider: {provider}, key: {mask_sensitive(api_key)}")

        if provider == "openai":
            valid, message = await _test_openai_key(api_key)
        elif provider == "anthropic":
            valid, message = await _test_anthropic_key(api_key)
        elif provider == "google":
            valid, message = await _test_google_key(api_key)
        elif provider == "grok":
            valid, message = await _test_grok_key(api_key)
        else:
            return TestKeyResponse(
                valid=False,
                message=f"Unknown provider: {provider}",
                provider=provider
            )

        return TestKeyResponse(
            valid=valid,
            message=message,
            provider=provider
        )

    except Exception as e:
        logger.error(f"Error testing API key: {e}", exc_info=True)
        return TestKeyResponse(
            valid=False,
            message=f"Error testing key: {str(e)}",
            provider=request.provider
        )


async def _test_openai_key(api_key: str) -> tuple[bool, str]:
    """Test OpenAI API key with a minimal request"""
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        # Make a minimal request - list models is lightweight
        models = client.models.list()
        # If we get here, the key is valid
        return True, "OpenAI API key validated successfully"
    except openai.AuthenticationError:
        return False, "Invalid API key - authentication failed"
    except openai.RateLimitError:
        return True, "API key valid (rate limited, but authenticated)"
    except Exception as e:
        return False, f"OpenAI API error: {str(e)}"


async def _test_anthropic_key(api_key: str) -> tuple[bool, str]:
    """Test Anthropic API key with a minimal request"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        # Make a minimal message request to test the key
        # Using count_tokens is not available, so we make a small completion
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1,
            messages=[{"role": "user", "content": "test"}]
        )
        return True, "Anthropic API key validated successfully"
    except anthropic.AuthenticationError:
        return False, "Invalid API key - authentication failed"
    except anthropic.RateLimitError:
        return True, "API key valid (rate limited, but authenticated)"
    except Exception as e:
        return False, f"Anthropic API error: {str(e)}"


async def _test_google_key(api_key: str) -> tuple[bool, str]:
    """Test Google AI API key with a minimal request"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # List models to verify the key works
        models = list(genai.list_models())
        return True, "Google AI API key validated successfully"
    except Exception as e:
        error_msg = str(e).lower()
        if "api key" in error_msg or "invalid" in error_msg or "401" in error_msg:
            return False, "Invalid API key - authentication failed"
        return False, f"Google AI API error: {str(e)}"


async def _test_grok_key(api_key: str) -> tuple[bool, str]:
    """Test xAI Grok API key with a minimal request (Story P2-5.2)"""
    try:
        import openai
        # Grok uses OpenAI-compatible API with custom base URL
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )
        # List models to verify the key works
        models = client.models.list()
        return True, "xAI Grok API key validated successfully"
    except openai.AuthenticationError:
        return False, "Invalid API key - authentication failed"
    except openai.RateLimitError:
        return True, "API key valid (rate limited, but authenticated)"
    except Exception as e:
        error_msg = str(e).lower()
        if "api key" in error_msg or "invalid" in error_msg or "401" in error_msg or "unauthorized" in error_msg:
            return False, "Invalid API key - authentication failed"
        return False, f"xAI Grok API error: {str(e)}"


def get_decrypted_api_key(db: Session, provider: str) -> Optional[str]:
    """
    Get decrypted API key for a specific provider from system settings

    This is used by the AI service to retrieve API keys for making requests.

    Args:
        db: Database session
        provider: AI provider name ("openai", "anthropic", "google")

    Returns:
        Decrypted API key or None if not set
    """
    # Map provider to settings key
    key_map = {
        "openai": "settings_primary_api_key",  # or specific key
        "anthropic": "settings_primary_api_key",
        "google": "settings_primary_api_key",
    }

    db_key = key_map.get(provider)
    if not db_key:
        return None

    # Get encrypted value from database
    encrypted_value = _get_setting_from_db(db, db_key)
    if not encrypted_value:
        return None

    # Decrypt if encrypted
    if is_encrypted(encrypted_value):
        try:
            return decrypt_password(encrypted_value)
        except ValueError:
            logger.error(f"Failed to decrypt API key for {provider}")
            return None
    else:
        # Return unencrypted value (legacy)
        return encrypted_value


# ============================================================================
# AI Provider Status API (Story P2-5.2)
# ============================================================================


class AIProviderStatus(BaseModel):
    """Status of AI provider configuration"""
    provider: str = Field(..., description="Provider identifier")
    configured: bool = Field(..., description="Whether API key is configured")


class AIProvidersStatusResponse(BaseModel):
    """Response listing all AI providers and their configuration status"""
    providers: List[AIProviderStatus] = Field(..., description="List of provider statuses")
    order: List[str] = Field(..., description="Provider order for fallback chain")


@router.get("/ai-providers", response_model=AIProvidersStatusResponse)
async def get_ai_providers_status(db: Session = Depends(get_db)):
    """
    Get configuration status for all AI providers

    Returns a list of all supported AI providers and whether they have
    API keys configured. This is used by the frontend to show provider
    status in the settings UI.

    **Response:**
    ```json
    {
        "providers": [
            {"provider": "openai", "configured": true},
            {"provider": "grok", "configured": false},
            {"provider": "anthropic", "configured": true},
            {"provider": "google", "configured": false}
        ]
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        # Map providers to their database key names
        provider_key_map = {
            "openai": "ai_api_key_openai",
            "grok": "ai_api_key_grok",
            "anthropic": "ai_api_key_claude",
            "google": "ai_api_key_gemini",
        }

        providers = []
        for provider_id, db_key in provider_key_map.items():
            # Check if the key exists and has a value
            setting = db.query(SystemSetting).filter(SystemSetting.key == db_key).first()
            is_configured = bool(setting and setting.value and setting.value.strip())

            providers.append(AIProviderStatus(
                provider=provider_id,
                configured=is_configured
            ))

        # Get saved provider order or use default
        order_setting = db.query(SystemSetting).filter(
            SystemSetting.key == "ai_provider_order"
        ).first()

        default_order = ["openai", "grok", "anthropic", "google"]
        if order_setting and order_setting.value:
            try:
                import json
                order = json.loads(order_setting.value)
            except (json.JSONDecodeError, TypeError):
                order = default_order
        else:
            order = default_order

        return AIProvidersStatusResponse(providers=providers, order=order)

    except Exception as e:
        logger.error(f"Error getting AI providers status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get AI providers status"
        )


# ============================================================================
# AI Provider Stats API (Story P2-5.3)
# ============================================================================


class AIProviderStatsResponse(BaseModel):
    """Response for AI provider usage statistics"""
    total_events: int = Field(..., description="Total events with provider_used set")
    events_per_provider: dict[str, int] = Field(..., description="Event count by provider")
    date_range: Literal["24h", "7d", "30d", "all"] = Field(..., description="Date range filter applied")
    time_range: dict[str, Optional[str]] = Field(..., description="Actual time range (start, end)")


@router.get("/ai-stats", response_model=AIProviderStatsResponse)
async def get_ai_provider_stats(
    date_range: Literal["24h", "7d", "30d", "all"] = "7d",
    db: Session = Depends(get_db)
):
    """
    Get AI provider usage statistics (Story P2-5.3)

    Returns a breakdown of how many events were processed by each AI provider.
    Useful for monitoring provider usage and fallback behavior.

    **Query Parameters:**
    - `date_range`: Time filter - "24h", "7d", "30d", or "all" (default: "7d")

    **Response:**
    ```json
    {
        "total_events": 1234,
        "events_per_provider": {
            "openai": 1000,
            "grok": 150,
            "claude": 75,
            "gemini": 9
        },
        "date_range": "7d",
        "time_range": {
            "start": "2025-11-28T00:00:00Z",
            "end": "2025-12-05T23:59:59Z"
        }
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    from app.models.event import Event
    from sqlalchemy import func

    try:
        # Calculate time range
        now = datetime.now(timezone.utc)
        if date_range == "24h":
            start_time = now - timedelta(hours=24)
        elif date_range == "7d":
            start_time = now - timedelta(days=7)
        elif date_range == "30d":
            start_time = now - timedelta(days=30)
        else:  # "all"
            start_time = None

        # Build query for events with provider_used set
        query = db.query(
            Event.provider_used,
            func.count(Event.id).label('count')
        ).filter(Event.provider_used.isnot(None))

        if start_time:
            query = query.filter(Event.timestamp >= start_time)

        # Group by provider
        results = query.group_by(Event.provider_used).all()

        # Build response
        events_per_provider = {}
        total = 0
        for provider, count in results:
            if provider:  # Skip None values
                events_per_provider[provider] = count
                total += count

        # Get actual time range from data
        if start_time:
            time_range_data = {
                "start": start_time.isoformat(),
                "end": now.isoformat()
            }
        else:
            # Get actual min/max from data
            min_max = db.query(
                func.min(Event.timestamp),
                func.max(Event.timestamp)
            ).filter(Event.provider_used.isnot(None)).first()
            time_range_data = {
                "start": min_max[0].isoformat() if min_max[0] else None,
                "end": min_max[1].isoformat() if min_max[1] else None
            }

        return AIProviderStatsResponse(
            total_events=total,
            events_per_provider=events_per_provider,
            date_range=date_range,
            time_range=time_range_data
        )

    except Exception as e:
        logger.error(f"Error getting AI provider stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get AI provider statistics"
        )


# ============================================================================
# AI Usage Cost Tracking API (Story P3-7.1)
# ============================================================================


from app.schemas.system import (
    AIUsageResponse,
    AIUsageByDate,
    AIUsageByCamera,
    AIUsageByProvider,
    AIUsageByMode,
    AIUsagePeriod
)
from app.models.ai_usage import AIUsage


@router.get("/ai-usage", response_model=AIUsageResponse)
async def get_ai_usage(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get AI usage and cost statistics (Story P3-7.1)

    Returns aggregated AI usage data including costs broken down by date,
    camera, provider, and analysis mode.

    **Query Parameters:**
    - `start_date`: Start date in ISO 8601 format (default: 30 days ago)
    - `end_date`: End date in ISO 8601 format (default: now)

    **Response:**
    ```json
    {
        "total_cost": 0.0523,
        "total_requests": 142,
        "period": {
            "start": "2025-11-09T00:00:00Z",
            "end": "2025-12-09T23:59:59Z"
        },
        "by_date": [...],
        "by_camera": [...],
        "by_provider": [...],
        "by_mode": [...]
    }
    ```

    **Status Codes:**
    - 200: Success
    - 400: Invalid date format
    - 500: Internal server error
    """
    from app.models.event import Event
    from app.models.camera import Camera
    from sqlalchemy import func, cast, Date

    try:
        # Parse date range (default: last 30 days)
        now = datetime.now(timezone.utc)
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use ISO 8601 format."
                )
        else:
            end_dt = now

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use ISO 8601 format."
                )
        else:
            start_dt = now - timedelta(days=30)

        # Base query with date filter
        base_query = db.query(AIUsage).filter(
            AIUsage.timestamp >= start_dt,
            AIUsage.timestamp <= end_dt
        )

        # Get all records for aggregation
        records = base_query.all()

        # Calculate totals
        total_cost = sum(r.cost_estimate or 0.0 for r in records)
        total_requests = len(records)

        # Aggregate by date
        by_date_dict = {}
        for r in records:
            date_key = r.timestamp.strftime("%Y-%m-%d")
            if date_key not in by_date_dict:
                by_date_dict[date_key] = {"cost": 0.0, "requests": 0}
            by_date_dict[date_key]["cost"] += r.cost_estimate or 0.0
            by_date_dict[date_key]["requests"] += 1

        by_date = [
            AIUsageByDate(date=date, cost=data["cost"], requests=data["requests"])
            for date, data in sorted(by_date_dict.items(), reverse=True)
        ]

        # Aggregate by provider
        by_provider_dict = {}
        for r in records:
            provider = r.provider or "unknown"
            if provider not in by_provider_dict:
                by_provider_dict[provider] = {"cost": 0.0, "requests": 0}
            by_provider_dict[provider]["cost"] += r.cost_estimate or 0.0
            by_provider_dict[provider]["requests"] += 1

        by_provider = [
            AIUsageByProvider(provider=provider, cost=data["cost"], requests=data["requests"])
            for provider, data in sorted(by_provider_dict.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        # Aggregate by analysis mode
        by_mode_dict = {}
        for r in records:
            mode = r.analysis_mode or "unknown"
            if mode not in by_mode_dict:
                by_mode_dict[mode] = {"cost": 0.0, "requests": 0}
            by_mode_dict[mode]["cost"] += r.cost_estimate or 0.0
            by_mode_dict[mode]["requests"] += 1

        by_mode = [
            AIUsageByMode(mode=mode, cost=data["cost"], requests=data["requests"])
            for mode, data in sorted(by_mode_dict.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        # Note: AIUsage doesn't have camera_id directly - we'd need to join through Event
        # For now, return empty list for by_camera (can be implemented if Event-AIUsage link exists)
        by_camera = []

        return AIUsageResponse(
            total_cost=round(total_cost, 6),
            total_requests=total_requests,
            period=AIUsagePeriod(
                start=start_dt.isoformat(),
                end=end_dt.isoformat()
            ),
            by_date=by_date,
            by_camera=by_camera,
            by_provider=by_provider,
            by_mode=by_mode
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting AI usage stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get AI usage statistics"
        )


# ============================================================================
# Backup and Restore API (Story 6.4, FF-007)
# ============================================================================


class BackupOptions(BaseModel):
    """Options for selective backup (FF-007)"""
    include_database: bool = Field(default=True, description="Include events, cameras, alert rules")
    include_thumbnails: bool = Field(default=True, description="Include thumbnail images")
    include_settings: bool = Field(default=True, description="Include system settings")
    include_ai_config: bool = Field(default=True, description="Include AI provider config (keys excluded)")
    include_protect_config: bool = Field(default=True, description="Include Protect controller config")

    class Config:
        json_schema_extra = {
            "example": {
                "include_database": True,
                "include_thumbnails": True,
                "include_settings": True,
                "include_ai_config": True,
                "include_protect_config": True
            }
        }


class RestoreOptions(BaseModel):
    """Options for selective restore (FF-007)"""
    restore_database: bool = Field(default=True, description="Restore events, cameras, alert rules")
    restore_thumbnails: bool = Field(default=True, description="Restore thumbnail images")
    restore_settings: bool = Field(default=True, description="Restore system settings")

    class Config:
        json_schema_extra = {
            "example": {
                "restore_database": True,
                "restore_thumbnails": True,
                "restore_settings": True
            }
        }


class BackupResponse(BaseModel):
    """Response from backup creation"""
    success: bool = Field(..., description="Whether backup was successful")
    timestamp: str = Field(..., description="Backup timestamp identifier")
    size_bytes: int = Field(..., description="Backup file size in bytes")
    download_url: str = Field(..., description="URL to download the backup")
    message: str = Field(..., description="Status message")
    database_size_bytes: int = Field(default=0, description="Database size in backup")
    thumbnails_count: int = Field(default=0, description="Number of thumbnails in backup")
    thumbnails_size_bytes: int = Field(default=0, description="Thumbnails size in backup")
    settings_count: int = Field(default=0, description="Number of settings in backup")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-01-15-14-30-00",
                "size_bytes": 15728640,
                "download_url": "/api/v1/system/backup/2025-01-15-14-30-00/download",
                "message": "Backup created successfully",
                "database_size_bytes": 10485760,
                "thumbnails_count": 150,
                "thumbnails_size_bytes": 5242880,
                "settings_count": 15
            }
        }


class RestoreResponse(BaseModel):
    """Response from restore operation"""
    success: bool = Field(..., description="Whether restore was successful")
    message: str = Field(..., description="Status message")
    events_restored: int = Field(default=0, description="Number of events restored")
    settings_restored: int = Field(default=0, description="Number of settings restored")
    thumbnails_restored: int = Field(default=0, description="Number of thumbnails restored")
    warnings: List[str] = Field(default_factory=list, description="Any warnings during restore")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Restore completed successfully",
                "events_restored": 1234,
                "settings_restored": 15,
                "thumbnails_restored": 150,
                "warnings": []
            }
        }


class BackupListItem(BaseModel):
    """Information about an available backup"""
    timestamp: str = Field(..., description="Backup timestamp identifier")
    size_bytes: int = Field(..., description="Backup file size in bytes")
    created_at: str = Field(..., description="ISO 8601 creation time")
    app_version: str = Field(..., description="App version at backup time")
    database_size_bytes: int = Field(default=0, description="Database size in backup")
    thumbnails_count: int = Field(default=0, description="Number of thumbnails")
    download_url: str = Field(..., description="URL to download")


class BackupListResponse(BaseModel):
    """Response listing available backups"""
    backups: List[BackupListItem] = Field(..., description="List of available backups")
    total_count: int = Field(..., description="Total number of backups")


class BackupContentsResponse(BaseModel):
    """Information about what's contained in a backup (FF-007)"""
    has_database: bool = Field(default=False, description="Backup includes database")
    has_thumbnails: bool = Field(default=False, description="Backup includes thumbnails")
    has_settings: bool = Field(default=False, description="Backup includes settings")
    database_size_bytes: int = Field(default=0, description="Database size in bytes")
    thumbnails_count: int = Field(default=0, description="Number of thumbnails")
    settings_count: int = Field(default=0, description="Number of settings")


class ValidationResponse(BaseModel):
    """Response from backup validation"""
    valid: bool = Field(..., description="Whether backup is valid")
    message: str = Field(..., description="Validation result message")
    app_version: Optional[str] = Field(None, description="Backup app version")
    backup_timestamp: Optional[str] = Field(None, description="Backup creation time")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    contents: Optional[BackupContentsResponse] = Field(None, description="What's in the backup (FF-007)")


@router.post("/backup", response_model=BackupResponse)
async def create_backup(options: Optional[BackupOptions] = None):
    """
    Create a system backup with optional selective components (FF-007)

    Creates a ZIP archive containing selected components:
    - **database.db**: Complete SQLite database (events, cameras, rules)
    - **thumbnails/**: All event thumbnail images
    - **settings.json**: System settings (API keys excluded for security)
    - **metadata.json**: Backup metadata (timestamp, version, file counts)

    The backup can be downloaded using the `download_url` in the response.

    **Request Body (optional):**
    ```json
    {
        "include_database": true,
        "include_thumbnails": true,
        "include_settings": true,
        "include_ai_config": true,
        "include_protect_config": true
    }
    ```

    **Response:**
    ```json
    {
        "success": true,
        "timestamp": "2025-01-15-14-30-00",
        "size_bytes": 15728640,
        "download_url": "/api/v1/system/backup/2025-01-15-14-30-00/download",
        "message": "Backup created successfully"
    }
    ```

    **Status Codes:**
    - 200: Backup created successfully
    - 507: Insufficient disk space
    - 500: Internal server error
    """
    try:
        backup_service = get_backup_service()
        # Use default options if none provided
        opts = options or BackupOptions()
        result = await backup_service.create_backup(
            include_database=opts.include_database,
            include_thumbnails=opts.include_thumbnails,
            include_settings=opts.include_settings
        )

        if not result.success:
            # Check if it's a disk space issue
            if "disk space" in result.message.lower():
                raise HTTPException(
                    status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                    detail=result.message
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )

        return BackupResponse(
            success=result.success,
            timestamp=result.timestamp,
            size_bytes=result.size_bytes,
            download_url=result.download_url,
            message=result.message,
            database_size_bytes=result.database_size_bytes,
            thumbnails_count=result.thumbnails_count,
            thumbnails_size_bytes=result.thumbnails_size_bytes,
            settings_count=result.settings_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create backup: {str(e)}"
        )


@router.get("/backup/{timestamp}/download")
async def download_backup(timestamp: str):
    """
    Download a backup file

    Downloads the backup ZIP file for the specified timestamp.
    The file is streamed to support large backups.

    **Path Parameters:**
    - `timestamp`: Backup timestamp from create_backup response (e.g., "2025-01-15-14-30-00")

    **Response:**
    - Content-Type: application/zip
    - Content-Disposition: attachment; filename=liveobject-backup-{timestamp}.zip

    **Status Codes:**
    - 200: Backup file streamed
    - 404: Backup not found
    """
    try:
        backup_service = get_backup_service()
        zip_path = backup_service.get_backup_path(timestamp)

        if not zip_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backup not found: {timestamp}"
            )

        filename = f"liveobject-backup-{timestamp}.zip"

        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename=filename,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download backup: {str(e)}"
        )


@router.get("/backup/list", response_model=BackupListResponse)
async def list_backups():
    """
    List all available backups

    Returns a list of all backup files with metadata, sorted by timestamp (newest first).

    **Response:**
    ```json
    {
        "backups": [
            {
                "timestamp": "2025-01-15-14-30-00",
                "size_bytes": 15728640,
                "created_at": "2025-01-15T14:30:00Z",
                "app_version": "1.0.0",
                "download_url": "/api/v1/system/backup/2025-01-15-14-30-00/download"
            }
        ],
        "total_count": 1
    }
    ```

    **Status Codes:**
    - 200: List retrieved successfully
    - 500: Internal server error
    """
    try:
        backup_service = get_backup_service()
        backups = backup_service.list_backups()

        backup_items = [
            BackupListItem(
                timestamp=b.timestamp,
                size_bytes=b.size_bytes,
                created_at=b.created_at,
                app_version=b.app_version,
                database_size_bytes=b.database_size_bytes,
                thumbnails_count=b.thumbnails_count,
                download_url=b.download_url
            )
            for b in backups
        ]

        return BackupListResponse(
            backups=backup_items,
            total_count=len(backup_items)
        )

    except Exception as e:
        logger.error(f"Error listing backups: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list backups: {str(e)}"
        )


@router.post("/backup/validate", response_model=ValidationResponse)
async def validate_backup(file: UploadFile = File(...)):
    """
    Validate a backup file before restore

    Checks the backup ZIP file for:
    - Valid ZIP format
    - Required files present (database.db, metadata.json)
    - Metadata format and version compatibility

    **Request:**
    - Content-Type: multipart/form-data
    - Field: file (ZIP file)

    **Response:**
    ```json
    {
        "valid": true,
        "message": "Backup is valid",
        "app_version": "1.0.0",
        "backup_timestamp": "2025-01-15T14:30:00Z",
        "warnings": ["Backup from version 0.9.0, current version is 1.0.0"]
    }
    ```

    **Status Codes:**
    - 200: Validation result returned
    - 400: Invalid file format
    - 500: Internal server error
    """
    try:
        # Check file type
        if not file.filename or not file.filename.endswith('.zip'):
            return ValidationResponse(
                valid=False,
                message="File must be a ZIP archive"
            )

        # Save to temp file for validation
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            backup_service = get_backup_service()
            result = backup_service.validate_backup(tmp_path)

            # FF-007: Include backup contents info
            contents = None
            if result.contents:
                contents = BackupContentsResponse(
                    has_database=result.contents.has_database,
                    has_thumbnails=result.contents.has_thumbnails,
                    has_settings=result.contents.has_settings,
                    database_size_bytes=result.contents.database_size_bytes,
                    thumbnails_count=result.contents.thumbnails_count,
                    settings_count=result.contents.settings_count
                )

            return ValidationResponse(
                valid=result.valid,
                message=result.message,
                app_version=result.app_version,
                backup_timestamp=result.backup_timestamp,
                warnings=result.warnings or [],
                contents=contents
            )
        finally:
            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Error validating backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate backup: {str(e)}"
        )


@router.post("/restore", response_model=RestoreResponse)
async def restore_from_backup(
    file: UploadFile = File(...),
    restore_database: bool = Form(default=True),
    restore_thumbnails: bool = Form(default=True),
    restore_settings: bool = Form(default=True)
):
    """
    Restore system from a backup file with selective components (FF-007)

    **WARNING: This operation may replace existing data based on selected components!**

    Process:
    1. Validates the backup file
    2. Stops background tasks (camera capture, event processing)
    3. Creates a backup of current database (if restoring database)
    4. Replaces selected components (database, thumbnails, settings)
    5. Restarts background tasks

    **Request:**
    - Content-Type: multipart/form-data
    - Field: file (ZIP file)
    - Field: restore_database (boolean, default true)
    - Field: restore_thumbnails (boolean, default true)
    - Field: restore_settings (boolean, default true)

    **Response:**
    ```json
    {
        "success": true,
        "message": "Restore completed successfully",
        "events_restored": 1234,
        "settings_restored": 15,
        "thumbnails_restored": 150,
        "warnings": []
    }
    ```

    **Status Codes:**
    - 200: Restore completed successfully
    - 400: Invalid backup file
    - 500: Restore failed
    """
    try:
        # Check file type
        if not file.filename or not file.filename.endswith('.zip'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be a ZIP archive"
            )

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            backup_service = get_backup_service()

            # Validate first
            validation = backup_service.validate_backup(tmp_path)
            if not validation.valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid backup: {validation.message}"
                )

            # Get callbacks for stopping/starting background tasks
            # These are imported from main.py patterns but we'll handle in-process
            async def stop_tasks():
                """Stop background tasks for restore"""
                # Import here to avoid circular imports
                from app.api.v1.cameras import camera_service
                from app.services.event_processor import shutdown_event_processor

                try:
                    camera_service.stop_all_cameras(timeout=5.0)
                    await shutdown_event_processor(timeout=10.0)
                except Exception as e:
                    logger.warning(f"Error stopping tasks: {e}")

            async def start_tasks():
                """Restart background tasks after restore"""
                from app.api.v1.cameras import camera_service
                from app.services.event_processor import initialize_event_processor
                from app.core.database import SessionLocal
                from app.models.camera import Camera

                try:
                    await initialize_event_processor()

                    # Restart enabled cameras
                    db = SessionLocal()
                    try:
                        enabled_cameras = db.query(Camera).filter(Camera.is_enabled == True).all()
                        for camera in enabled_cameras:
                            camera_service.start_camera(camera)
                    finally:
                        db.close()
                except Exception as e:
                    logger.warning(f"Error restarting tasks: {e}")

            # Perform restore with selective options (FF-007)
            result = await backup_service.restore_from_backup(
                tmp_path,
                stop_tasks_callback=stop_tasks,
                start_tasks_callback=start_tasks,
                restore_database=restore_database,
                restore_thumbnails=restore_thumbnails,
                restore_settings=restore_settings
            )

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=result.message
                )

            return RestoreResponse(
                success=result.success,
                message=result.message,
                events_restored=result.events_restored,
                settings_restored=result.settings_restored,
                thumbnails_restored=result.thumbnails_restored,
                warnings=result.warnings or []
            )

        finally:
            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore failed: {str(e)}"
        )


@router.delete("/backup/{timestamp}")
async def delete_backup(timestamp: str):
    """
    Delete a specific backup

    Permanently removes the backup file for the specified timestamp.

    **Path Parameters:**
    - `timestamp`: Backup timestamp (e.g., "2025-01-15-14-30-00")

    **Response:**
    ```json
    {
        "message": "Backup deleted successfully"
    }
    ```

    **Status Codes:**
    - 200: Backup deleted
    - 404: Backup not found
    """
    try:
        backup_service = get_backup_service()
        deleted = backup_service.delete_backup(timestamp)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backup not found: {timestamp}"
            )

        return {"message": "Backup deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete backup: {str(e)}"
        )


# Story P3-7.3: Cost Cap Status Endpoint
from app.services.cost_cap_service import get_cost_cap_service
from app.schemas.system import CostCapStatus as CostCapStatusSchema


@router.get("/ai-cost-status", response_model=CostCapStatusSchema)
async def get_ai_cost_status(db: Session = Depends(get_db)):
    """
    Get current AI cost cap status (Story P3-7.3)

    Returns current daily and monthly costs, caps, percentages, and pause status.

    **Response:**
    ```json
    {
        "daily_cost": 0.75,
        "daily_cap": 1.00,
        "daily_percent": 75.0,
        "monthly_cost": 12.50,
        "monthly_cap": 20.00,
        "monthly_percent": 62.5,
        "is_paused": false,
        "pause_reason": null
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        cost_cap_service = get_cost_cap_service()
        cap_status = cost_cap_service.get_cap_status(db, use_cache=False)

        return CostCapStatusSchema(
            daily_cost=cap_status.daily_cost,
            daily_cap=cap_status.daily_cap,
            daily_percent=cap_status.daily_percent,
            monthly_cost=cap_status.monthly_cost,
            monthly_cap=cap_status.monthly_cap,
            monthly_percent=cap_status.monthly_percent,
            is_paused=cap_status.is_paused,
            pause_reason=cap_status.pause_reason
        )

    except Exception as e:
        logger.error(f"Error getting AI cost status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve AI cost status"
        )
