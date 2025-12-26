"""
FCM (Firebase Cloud Messaging) Provider.

Story P11-2.2: Implements Android push notifications via FCM HTTP v1 API.

Features:
- Firebase Admin SDK integration with service account auth
- Async wrapper for blocking SDK calls
- Retry logic with exponential backoff
- Error handling for all FCM exceptions
- Token invalidation for unregistered devices
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from app.services.push.constants import (
    MAX_RETRIES,
    RETRY_BASE_DELAY_SECONDS,
)
from app.services.push.models import (
    FCMConfig,
    FCMPayload,
    DeliveryResult,
    DeliveryStatus,
)

logger = logging.getLogger(__name__)

# Firebase Admin SDK imports (lazy loaded to handle missing dependency gracefully)
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    from firebase_admin.exceptions import (
        FirebaseError,
        InvalidArgumentError,
        UnauthenticatedError,
        NotFoundError,
    )
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    firebase_admin = None
    credentials = None
    messaging = None
    FirebaseError = Exception
    InvalidArgumentError = Exception
    UnauthenticatedError = Exception
    NotFoundError = Exception


class FCMProvider:
    """
    FCM provider for sending push notifications to Android devices.

    Uses Firebase Admin SDK for FCM HTTP v1 API integration.
    SDK calls are wrapped with asyncio.to_thread for async compatibility.

    Usage:
        config = FCMConfig(
            project_id="argusai-12345",
            credentials_path="/path/to/service-account.json",
        )
        provider = FCMProvider(config)
        result = await provider.send(device_token, payload)

    Attributes:
        config: FCM configuration
        _app: Firebase app instance
        _initialized: Whether Firebase has been initialized
    """

    def __init__(
        self,
        config: FCMConfig,
        on_token_invalid: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize FCM provider.

        Args:
            config: FCM configuration with credentials details
            on_token_invalid: Optional callback when device token is invalid
        """
        if not FIREBASE_AVAILABLE:
            raise ImportError(
                "firebase-admin package is required for FCM. "
                "Install with: pip install firebase-admin"
            )

        self.config = config
        self._on_token_invalid = on_token_invalid
        self._app: Optional[firebase_admin.App] = None
        self._initialized = False

        logger.info(
            "FCM provider created",
            extra={
                "project_id": config.project_id,
                "credentials_path": config.credentials_path,
            }
        )

    def _initialize(self) -> None:
        """Initialize Firebase Admin SDK with service account credentials."""
        if self._initialized:
            return

        creds_path = Path(self.config.credentials_path)
        if not creds_path.exists():
            raise FileNotFoundError(
                f"FCM credentials file not found: {creds_path}"
            )

        # Check if an app with this name already exists
        app_name = f"argusai-fcm-{self.config.project_id}"
        try:
            self._app = firebase_admin.get_app(app_name)
            logger.debug(f"Using existing Firebase app: {app_name}")
        except ValueError:
            # App doesn't exist, create it
            cred = credentials.Certificate(str(creds_path))
            self._app = firebase_admin.initialize_app(
                cred,
                name=app_name,
                options={"projectId": self.config.project_id},
            )
            logger.info(
                f"Firebase Admin SDK initialized",
                extra={
                    "app_name": app_name,
                    "project_id": self.config.project_id,
                }
            )

        self._initialized = True

    def _build_message(
        self,
        device_token: str,
        payload: FCMPayload,
        data_only: bool = False,
    ) -> "messaging.Message":
        """
        Build FCM message from payload.

        Args:
            device_token: FCM device registration token
            payload: Notification payload
            data_only: If True, send data-only message (no notification)

        Returns:
            FCM Message object ready for sending
        """
        # Build Android-specific config
        android_notification = None
        if not data_only:
            android_notification = messaging.AndroidNotification(
                title=payload.title,
                body=payload.body,
                icon=payload.icon,
                color=payload.color,
                sound=payload.sound,
                channel_id=payload.channel_id,
                tag=payload.tag,
                click_action=payload.click_action,
                image=payload.image_url,
            )

        android_config = messaging.AndroidConfig(
            priority=payload.priority,
            notification=android_notification,
        )

        # Build notification (for non-data-only messages)
        notification = None
        if not data_only:
            notification = messaging.Notification(
                title=payload.title,
                body=payload.body,
                image=payload.image_url,
            )

        # Build message
        message = messaging.Message(
            notification=notification,
            data=payload.data if payload.data else None,
            android=android_config,
            token=device_token,
        )

        return message

    async def send(
        self,
        device_token: str,
        payload: FCMPayload,
        data_only: bool = False,
    ) -> DeliveryResult:
        """
        Send a push notification to a single device.

        Implements retry logic with exponential backoff for transient errors.
        Calls on_token_invalid callback for unregistered tokens.

        Args:
            device_token: FCM device registration token
            payload: Notification payload
            data_only: If True, send data-only message (for background processing)

        Returns:
            DeliveryResult with success status and details
        """
        # Initialize Firebase on first send
        if not self._initialized:
            try:
                self._initialize()
            except Exception as e:
                logger.error(f"Failed to initialize Firebase: {e}")
                return DeliveryResult(
                    device_token=device_token,
                    success=False,
                    status=DeliveryStatus.AUTH_ERROR,
                    error=f"Firebase initialization failed: {e}",
                )

        message = self._build_message(device_token, payload, data_only)

        retries = 0
        last_error = None
        start_time = time.time()

        while retries <= MAX_RETRIES:
            try:
                # Run blocking FCM send in thread pool
                response = await asyncio.to_thread(
                    messaging.send,
                    message,
                    app=self._app,
                )

                duration = time.time() - start_time
                logger.info(
                    "FCM notification sent successfully",
                    extra={
                        "device_token": device_token[:20] + "...",
                        "message_id": response,
                        "retries": retries,
                        "duration_ms": int(duration * 1000),
                    }
                )

                return DeliveryResult(
                    device_token=device_token,
                    success=True,
                    status=DeliveryStatus.SUCCESS,
                    apns_id=response,  # Reuse apns_id field for message_id
                    retries=retries,
                )

            except messaging.UnregisteredError as e:
                # Token is no longer valid
                logger.warning(
                    "FCM device token unregistered",
                    extra={
                        "device_token": device_token[:20] + "...",
                        "error": str(e),
                    }
                )

                # Call invalidation callback if provided
                if self._on_token_invalid:
                    try:
                        self._on_token_invalid(device_token)
                    except Exception as callback_error:
                        logger.error(
                            f"Error in token invalidation callback: {callback_error}"
                        )

                return DeliveryResult(
                    device_token=device_token,
                    success=False,
                    status=DeliveryStatus.INVALID_TOKEN,
                    error=str(e),
                    retries=retries,
                )

            except messaging.QuotaExceededError as e:
                # Rate limited
                logger.warning(
                    "FCM quota exceeded",
                    extra={
                        "device_token": device_token[:20] + "...",
                        "retry": retries + 1,
                    }
                )
                last_error = str(e)

                if retries < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY_SECONDS * (2 ** retries)
                    await asyncio.sleep(delay)
                    retries += 1
                    continue

                return DeliveryResult(
                    device_token=device_token,
                    success=False,
                    status=DeliveryStatus.RATE_LIMITED,
                    error=last_error,
                    retries=retries,
                )

            except InvalidArgumentError as e:
                # Bad request - don't retry
                logger.error(
                    "FCM invalid argument error",
                    extra={
                        "device_token": device_token[:20] + "...",
                        "error": str(e),
                    }
                )

                return DeliveryResult(
                    device_token=device_token,
                    success=False,
                    status=DeliveryStatus.FAILED,
                    error=str(e),
                    retries=retries,
                )

            except messaging.ThirdPartyAuthError as e:
                # Authentication/credentials issue
                logger.error(
                    "FCM authentication error",
                    extra={
                        "error": str(e),
                    }
                )

                return DeliveryResult(
                    device_token=device_token,
                    success=False,
                    status=DeliveryStatus.AUTH_ERROR,
                    error=str(e),
                    retries=retries,
                )

            except messaging.SenderIdMismatchError as e:
                # Wrong project/sender ID
                logger.error(
                    "FCM sender ID mismatch",
                    extra={
                        "error": str(e),
                        "project_id": self.config.project_id,
                    }
                )

                return DeliveryResult(
                    device_token=device_token,
                    success=False,
                    status=DeliveryStatus.FAILED,
                    error=str(e),
                    retries=retries,
                )

            except messaging.UnavailableError as e:
                # FCM service unavailable - retry
                logger.warning(
                    "FCM service unavailable, retrying",
                    extra={
                        "retry": retries + 1,
                        "error": str(e),
                    }
                )
                last_error = str(e)

                if retries < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY_SECONDS * (2 ** retries)
                    await asyncio.sleep(delay)
                    retries += 1
                    continue

                break

            except FirebaseError as e:
                # Generic Firebase error
                logger.error(
                    "FCM Firebase error",
                    extra={
                        "error": str(e),
                        "code": getattr(e, 'code', None),
                    }
                )
                last_error = str(e)

                # Some Firebase errors are retryable
                if retries < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY_SECONDS * (2 ** retries)
                    await asyncio.sleep(delay)
                    retries += 1
                    continue

                break

            except Exception as e:
                # Unexpected error
                logger.error(f"FCM unexpected error: {e}", exc_info=True)
                last_error = str(e)
                break

        # All retries exhausted
        duration = time.time() - start_time
        logger.error(
            f"FCM notification failed after {retries} retries",
            extra={
                "device_token": device_token[:20] + "...",
                "error": last_error,
                "duration_ms": int(duration * 1000),
            }
        )

        return DeliveryResult(
            device_token=device_token,
            success=False,
            status=DeliveryStatus.SERVER_ERROR,
            error=last_error,
            retries=retries,
        )

    async def send_batch(
        self,
        device_tokens: List[str],
        payload: FCMPayload,
        data_only: bool = False,
        concurrency: int = 10,
    ) -> List[DeliveryResult]:
        """
        Send a notification to multiple devices.

        Uses FCM's send_each_for_multicast for efficient batch sending.

        Args:
            device_tokens: List of FCM device tokens
            payload: Notification payload (same for all devices)
            data_only: If True, send data-only messages
            concurrency: Maximum concurrent operations (not used with multicast)

        Returns:
            List of DeliveryResult for each device
        """
        if not device_tokens:
            return []

        # Initialize Firebase if needed
        if not self._initialized:
            try:
                self._initialize()
            except Exception as e:
                logger.error(f"Failed to initialize Firebase: {e}")
                return [
                    DeliveryResult(
                        device_token=token,
                        success=False,
                        status=DeliveryStatus.AUTH_ERROR,
                        error=f"Firebase initialization failed: {e}",
                    )
                    for token in device_tokens
                ]

        # Build multicast message
        android_notification = None
        if not data_only:
            android_notification = messaging.AndroidNotification(
                title=payload.title,
                body=payload.body,
                icon=payload.icon,
                color=payload.color,
                sound=payload.sound,
                channel_id=payload.channel_id,
                tag=payload.tag,
                click_action=payload.click_action,
                image=payload.image_url,
            )

        android_config = messaging.AndroidConfig(
            priority=payload.priority,
            notification=android_notification,
        )

        notification = None
        if not data_only:
            notification = messaging.Notification(
                title=payload.title,
                body=payload.body,
                image=payload.image_url,
            )

        multicast_message = messaging.MulticastMessage(
            notification=notification,
            data=payload.data if payload.data else None,
            android=android_config,
            tokens=device_tokens,
        )

        try:
            # Run blocking batch send in thread pool
            response = await asyncio.to_thread(
                messaging.send_each_for_multicast,
                multicast_message,
                app=self._app,
            )

            # Process results
            results = []
            for idx, resp in enumerate(response.responses):
                token = device_tokens[idx]

                if resp.success:
                    results.append(DeliveryResult(
                        device_token=token,
                        success=True,
                        status=DeliveryStatus.SUCCESS,
                        apns_id=resp.message_id,
                    ))
                else:
                    # Determine error status
                    exception = resp.exception
                    status = DeliveryStatus.FAILED
                    error_msg = str(exception) if exception else "Unknown error"

                    if isinstance(exception, messaging.UnregisteredError):
                        status = DeliveryStatus.INVALID_TOKEN
                        # Call invalidation callback
                        if self._on_token_invalid:
                            try:
                                self._on_token_invalid(token)
                            except Exception as e:
                                logger.error(f"Token invalidation callback error: {e}")

                    elif isinstance(exception, messaging.QuotaExceededError):
                        status = DeliveryStatus.RATE_LIMITED

                    elif isinstance(exception, messaging.ThirdPartyAuthError):
                        status = DeliveryStatus.AUTH_ERROR

                    results.append(DeliveryResult(
                        device_token=token,
                        success=False,
                        status=status,
                        error=error_msg,
                    ))

            # Log summary
            success_count = sum(1 for r in results if r.success)
            invalid_count = sum(
                1 for r in results if r.status == DeliveryStatus.INVALID_TOKEN
            )
            logger.info(
                "FCM batch send complete",
                extra={
                    "total": len(device_tokens),
                    "success": success_count,
                    "failed": len(device_tokens) - success_count,
                    "invalid_tokens": invalid_count,
                }
            )

            return results

        except Exception as e:
            logger.error(f"FCM batch send error: {e}", exc_info=True)
            return [
                DeliveryResult(
                    device_token=token,
                    success=False,
                    status=DeliveryStatus.FAILED,
                    error=str(e),
                )
                for token in device_tokens
            ]

    async def send_data_only(
        self,
        device_token: str,
        data: dict,
    ) -> DeliveryResult:
        """
        Send a data-only message for background processing.

        Data-only messages don't display a notification but are delivered
        to the app for background processing.

        Args:
            device_token: FCM device token
            data: Data payload (values must be strings)

        Returns:
            DeliveryResult with success status
        """
        # Convert all values to strings as required by FCM
        string_data = {k: str(v) for k, v in data.items()}

        payload = FCMPayload(
            title="",  # Not used for data-only
            body="",   # Not used for data-only
            data=string_data,
        )

        return await self.send(device_token, payload, data_only=True)

    async def close(self) -> None:
        """
        Close the provider and release resources.

        Note: Firebase Admin SDK doesn't have explicit cleanup,
        but we mark the provider as uninitialized for consistency.
        """
        if self._app:
            try:
                # Delete the Firebase app
                firebase_admin.delete_app(self._app)
                logger.debug("Firebase app deleted")
            except Exception as e:
                logger.warning(f"Error deleting Firebase app: {e}")
            finally:
                self._app = None
                self._initialized = False

    async def __aenter__(self) -> "FCMProvider":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.close()
