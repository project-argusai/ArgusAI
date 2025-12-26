"""
APNS (Apple Push Notification Service) Provider.

Story P11-2.1: Implements iOS push notifications via HTTP/2.

Features:
- HTTP/2 connection with persistent connection pooling
- Token-based authentication (JWT with .p8 key)
- Retry logic with exponential backoff
- Error handling for all APNS response codes
- Token invalidation for unregistered devices
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.services.push.constants import (
    APNS_DEVICE_PATH,
    APNS_PRODUCTION_HOST,
    APNS_SANDBOX_HOST,
    APNS_AUTH_ERROR_STATUS_CODES,
    APNS_RETRYABLE_STATUS_CODES,
    APNS_TOKEN_INVALID_STATUS_CODES,
    JWT_ALGORITHM,
    JWT_TOKEN_LIFETIME_SECONDS,
    MAX_RETRIES,
    RETRY_BASE_DELAY_SECONDS,
)
from app.services.push.models import (
    APNSConfig,
    APNSPayload,
    DeliveryResult,
    DeliveryStatus,
)

logger = logging.getLogger(__name__)


class APNSProvider:
    """
    APNS provider for sending push notifications to Apple devices.

    Uses HTTP/2 for efficient connection handling and token-based
    authentication with JWT signed by the .p8 auth key.

    Usage:
        config = APNSConfig(
            key_file="path/to/AuthKey.p8",
            key_id="XXXXXXXXXX",
            team_id="YYYYYYYYYY",
            bundle_id="com.argusai.app",
            use_sandbox=False,
        )
        provider = APNSProvider(config)
        result = await provider.send(device_token, payload)

    Attributes:
        config: APNS configuration
        _client: httpx AsyncClient with HTTP/2 enabled
        _jwt_token: Cached JWT for authentication
        _jwt_expires_at: JWT expiration timestamp
    """

    def __init__(
        self,
        config: APNSConfig,
        on_token_invalid: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize APNS provider.

        Args:
            config: APNS configuration with auth key details
            on_token_invalid: Optional callback when device token is invalid (410)
        """
        self.config = config
        self._on_token_invalid = on_token_invalid

        # HTTP/2 client (lazy initialized)
        self._client: Optional[httpx.AsyncClient] = None

        # JWT caching
        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: float = 0

        # Private key (lazy loaded)
        self._private_key: Optional[ec.EllipticCurvePrivateKey] = None

        # Determine host
        self._host = APNS_SANDBOX_HOST if config.use_sandbox else APNS_PRODUCTION_HOST
        self._base_url = f"https://{self._host}"

        logger.info(
            f"APNS provider initialized",
            extra={
                "host": self._host,
                "bundle_id": config.bundle_id,
                "sandbox": config.use_sandbox,
            }
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP/2 client with connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                http2=True,
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._client

    def _load_private_key(self) -> ec.EllipticCurvePrivateKey:
        """Load private key from .p8 file."""
        if self._private_key is None:
            key_path = Path(self.config.key_file)
            if not key_path.exists():
                raise FileNotFoundError(f"APNS key file not found: {key_path}")

            key_data = key_path.read_bytes()

            # Load the EC private key
            self._private_key = serialization.load_pem_private_key(
                key_data,
                password=None,
            )

            if not isinstance(self._private_key, ec.EllipticCurvePrivateKey):
                raise ValueError("APNS key must be an EC private key (ES256)")

            logger.debug(f"Loaded APNS private key from {key_path}")

        return self._private_key

    def _generate_jwt(self) -> str:
        """
        Generate JWT for APNS authentication.

        The JWT is signed with ES256 algorithm using the .p8 private key.
        Token is valid for 1 hour and cached until near expiration.

        Returns:
            JWT string for Authorization header
        """
        now = time.time()

        # Return cached token if still valid (with 60s buffer)
        if self._jwt_token and self._jwt_expires_at > now + 60:
            return self._jwt_token

        private_key = self._load_private_key()

        # Convert EC key to PEM for PyJWT
        pem_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Build JWT
        issued_at = int(now)
        payload = {
            "iss": self.config.team_id,
            "iat": issued_at,
        }
        headers = {
            "alg": JWT_ALGORITHM,
            "kid": self.config.key_id,
        }

        self._jwt_token = jwt.encode(
            payload,
            pem_key,
            algorithm=JWT_ALGORITHM,
            headers=headers,
        )
        self._jwt_expires_at = now + JWT_TOKEN_LIFETIME_SECONDS

        logger.debug(
            f"Generated new APNS JWT",
            extra={
                "team_id": self.config.team_id,
                "key_id": self.config.key_id,
                "expires_in": JWT_TOKEN_LIFETIME_SECONDS,
            }
        )

        return self._jwt_token

    def _build_headers(self, payload: APNSPayload) -> dict:
        """Build request headers for APNS."""
        headers = {
            "authorization": f"bearer {self._generate_jwt()}",
            "apns-topic": self.config.bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10",
            "apns-expiration": "0",  # Immediate expiration
        }

        if payload.content_available:
            headers["apns-push-type"] = "background"
            headers["apns-priority"] = "5"

        return headers

    async def send(
        self,
        device_token: str,
        payload: APNSPayload,
    ) -> DeliveryResult:
        """
        Send a push notification to a single device.

        Implements retry logic with exponential backoff for transient errors.
        Calls on_token_invalid callback for 410 responses (unregistered).

        Args:
            device_token: APNS device token (hex string)
            payload: Notification payload

        Returns:
            DeliveryResult with success status and details
        """
        client = await self._get_client()
        url = f"{self._base_url}{APNS_DEVICE_PATH.format(device_token=device_token)}"
        headers = self._build_headers(payload)
        body = json.dumps(payload.to_apns_dict())

        retries = 0
        last_error = None
        last_status_code = None
        last_reason = None
        start_time = time.time()

        while retries <= MAX_RETRIES:
            try:
                response = await client.post(
                    url,
                    content=body,
                    headers=headers,
                )

                status_code = response.status_code
                apns_id = response.headers.get("apns-id")

                # Success
                if status_code == 200:
                    duration = time.time() - start_time
                    logger.info(
                        f"APNS notification sent successfully",
                        extra={
                            "device_token": device_token[:20] + "...",
                            "apns_id": apns_id,
                            "retries": retries,
                            "duration_ms": int(duration * 1000),
                        }
                    )
                    return DeliveryResult(
                        device_token=device_token,
                        success=True,
                        status=DeliveryStatus.SUCCESS,
                        status_code=status_code,
                        apns_id=apns_id,
                        retries=retries,
                    )

                # Parse error response
                error_body = response.json() if response.content else {}
                reason = error_body.get("reason", "Unknown")
                last_status_code = status_code
                last_reason = reason
                last_error = f"APNS error: {reason}"

                # Handle specific error cases
                if status_code in APNS_TOKEN_INVALID_STATUS_CODES:
                    # 410 Gone - Token is no longer valid
                    logger.warning(
                        f"APNS device token invalid (410)",
                        extra={
                            "device_token": device_token[:20] + "...",
                            "reason": reason,
                        }
                    )

                    # Call invalidation callback if provided
                    if self._on_token_invalid:
                        try:
                            self._on_token_invalid(device_token)
                        except Exception as e:
                            logger.error(f"Error in token invalidation callback: {e}")

                    return DeliveryResult(
                        device_token=device_token,
                        success=False,
                        status=DeliveryStatus.INVALID_TOKEN,
                        status_code=status_code,
                        error=last_error,
                        error_reason=reason,
                        retries=retries,
                    )

                if status_code in APNS_AUTH_ERROR_STATUS_CODES:
                    # 401/403 - Authentication error
                    logger.error(
                        f"APNS authentication error",
                        extra={
                            "status_code": status_code,
                            "reason": reason,
                        }
                    )

                    # Invalidate JWT to force regeneration
                    self._jwt_token = None
                    self._jwt_expires_at = 0

                    return DeliveryResult(
                        device_token=device_token,
                        success=False,
                        status=DeliveryStatus.AUTH_ERROR,
                        status_code=status_code,
                        error=last_error,
                        error_reason=reason,
                        retries=retries,
                    )

                if status_code == 429:
                    # Rate limited
                    logger.warning(
                        f"APNS rate limited",
                        extra={
                            "device_token": device_token[:20] + "...",
                            "retry": retries + 1,
                        }
                    )

                    if retries < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY_SECONDS * (2 ** retries)
                        await asyncio.sleep(delay)
                        retries += 1
                        continue

                    return DeliveryResult(
                        device_token=device_token,
                        success=False,
                        status=DeliveryStatus.RATE_LIMITED,
                        status_code=status_code,
                        error=last_error,
                        error_reason=reason,
                        retries=retries,
                    )

                if status_code in APNS_RETRYABLE_STATUS_CODES:
                    # Server error - retry
                    if retries < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY_SECONDS * (2 ** retries)
                        logger.warning(
                            f"APNS server error, retrying in {delay}s",
                            extra={
                                "status_code": status_code,
                                "reason": reason,
                                "retry": retries + 1,
                            }
                        )
                        await asyncio.sleep(delay)
                        retries += 1
                        continue

                # Other client errors (4xx) - don't retry
                logger.error(
                    f"APNS client error",
                    extra={
                        "status_code": status_code,
                        "reason": reason,
                        "device_token": device_token[:20] + "...",
                    }
                )

                return DeliveryResult(
                    device_token=device_token,
                    success=False,
                    status=DeliveryStatus.FAILED,
                    status_code=status_code,
                    error=last_error,
                    error_reason=reason,
                    retries=retries,
                )

            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
                if retries < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY_SECONDS * (2 ** retries)
                    logger.warning(f"APNS timeout, retrying in {delay}s")
                    await asyncio.sleep(delay)
                    retries += 1
                else:
                    break

            except httpx.HTTPError as e:
                last_error = f"HTTP error: {e}"
                if retries < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY_SECONDS * (2 ** retries)
                    logger.warning(f"APNS HTTP error, retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    retries += 1
                else:
                    break

            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.error(f"APNS unexpected error: {e}", exc_info=True)
                break

        # All retries exhausted
        duration = time.time() - start_time
        logger.error(
            f"APNS notification failed after {retries} retries",
            extra={
                "device_token": device_token[:20] + "...",
                "error": last_error,
                "status_code": last_status_code,
                "duration_ms": int(duration * 1000),
            }
        )

        return DeliveryResult(
            device_token=device_token,
            success=False,
            status=DeliveryStatus.SERVER_ERROR if last_status_code and last_status_code >= 500 else DeliveryStatus.FAILED,
            status_code=last_status_code,
            error=last_error,
            error_reason=last_reason,
            retries=retries,
        )

    async def send_batch(
        self,
        device_tokens: List[str],
        payload: APNSPayload,
        concurrency: int = 10,
    ) -> List[DeliveryResult]:
        """
        Send a notification to multiple devices concurrently.

        Args:
            device_tokens: List of APNS device tokens
            payload: Notification payload (same for all devices)
            concurrency: Maximum concurrent requests

        Returns:
            List of DeliveryResult for each device
        """
        if not device_tokens:
            return []

        semaphore = asyncio.Semaphore(concurrency)

        async def send_with_semaphore(token: str) -> DeliveryResult:
            async with semaphore:
                return await self.send(token, payload)

        results = await asyncio.gather(
            *[send_with_semaphore(token) for token in device_tokens],
            return_exceptions=True,
        )

        # Convert exceptions to failed results
        delivery_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch send exception for token: {result}")
                delivery_results.append(DeliveryResult(
                    device_token=device_tokens[i],
                    success=False,
                    status=DeliveryStatus.FAILED,
                    error=str(result),
                ))
            else:
                delivery_results.append(result)

        # Log summary
        success_count = sum(1 for r in delivery_results if r.success)
        invalid_count = sum(1 for r in delivery_results if r.status == DeliveryStatus.INVALID_TOKEN)
        logger.info(
            f"APNS batch send complete",
            extra={
                "total": len(device_tokens),
                "success": success_count,
                "failed": len(device_tokens) - success_count,
                "invalid_tokens": invalid_count,
            }
        )

        return delivery_results

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("APNS provider closed")

    async def __aenter__(self) -> "APNSProvider":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.close()
