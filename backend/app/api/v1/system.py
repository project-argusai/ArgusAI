"""
System Settings API

Endpoints for system-level configuration and monitoring:
    - Retention policy management (GET/PUT /retention)
    - Storage monitoring (GET /storage)
"""
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field
import logging

from app.schemas.system import (
    RetentionPolicyUpdate,
    RetentionPolicyResponse,
    StorageResponse,
    SystemSettings,
    SystemSettingsUpdate
)
from app.services.cleanup_service import get_cleanup_service
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

        for field_name, value in update_data.items():
            if value is not None:  # Only update non-None values
                # Skip masked API key values
                if field_name in ('primary_api_key', 'fallback_api_key') and isinstance(value, str) and value.startswith('****'):
                    logger.debug(f"Skipping masked value for {field_name}")
                    continue
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
    provider: Literal["openai", "anthropic", "google"] = Field(
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
