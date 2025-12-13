"""
Webhook Service for Alert Rule Actions (Story 5.3)

This module implements webhook delivery with:
- Async HTTP POST requests using httpx
- Exponential backoff retry logic (1s, 2s, 4s)
- Structured payload format with event and rule data
- Comprehensive logging of all attempts
- SSRF prevention and URL validation

Architecture:
    - Non-blocking async execution (doesn't block alert engine)
    - Each webhook attempt is logged to webhook_logs table
    - Rate limiting enforced per rule (100/min)
    - HTTPS required in production (configurable)

Usage:
    service = WebhookService(db_session)
    result = await service.send_webhook(url, headers, payload)
    # or
    result = await service.execute_rule_webhook(event, rule)
"""
import asyncio
import ipaddress
import json
import logging
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.models.alert_rule import AlertRule, WebhookLog
from app.models.event import Event
from app.utils.encryption import decrypt_password, is_encrypted, mask_sensitive

logger = logging.getLogger(__name__)

# Header names that should be decrypted if encrypted
SENSITIVE_HEADERS = ["authorization", "x-api-key", "api-key", "x-auth-token"]

# Configuration constants
WEBHOOK_TIMEOUT_SECONDS = 5.0
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff delays
USER_AGENT = "LiveObjectAIClassifier/1.0"
MAX_RESPONSE_BODY_LENGTH = 200  # Truncate response for logging/testing
RATE_LIMIT_PER_MINUTE = 100

# SSRF prevention - private IP ranges to block
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


@dataclass
class WebhookResult:
    """Result of a webhook execution attempt."""
    success: bool
    status_code: int
    response_body: str
    response_time_ms: int
    retry_count: int
    error_message: Optional[str] = None


class WebhookValidationError(Exception):
    """Raised when webhook URL validation fails."""
    pass


class WebhookRateLimitError(Exception):
    """Raised when webhook rate limit is exceeded."""
    pass


class WebhookService:
    """
    Webhook delivery service with retry logic and logging.

    Handles secure delivery of webhook payloads to external URLs
    with comprehensive error handling and audit logging.
    """

    def __init__(
        self,
        db: Session,
        http_client: Optional[httpx.AsyncClient] = None,
        allow_http: bool = False  # Set True for development/testing
    ):
        """
        Initialize WebhookService.

        Args:
            db: SQLAlchemy database session for logging
            http_client: Optional httpx AsyncClient (created if not provided)
            allow_http: Allow http:// URLs (disable for production)
        """
        self.db = db
        self.http_client = http_client
        self.allow_http = allow_http
        self._rate_limit_cache: Dict[str, List[float]] = {}  # rule_id -> timestamps

    def _is_private_ip(self, ip_str: str) -> bool:
        """Check if IP address is in a private/reserved range."""
        try:
            ip = ipaddress.ip_address(ip_str)
            for network in PRIVATE_IP_RANGES:
                if ip in network:
                    return True
            return False
        except ValueError:
            return False

    def _resolve_hostname(self, hostname: str) -> Optional[str]:
        """Resolve hostname to IP address for SSRF check."""
        try:
            # Get first IP address for the hostname
            ip = socket.gethostbyname(hostname)
            return ip
        except socket.gaierror:
            return None

    def validate_url(self, url: str) -> None:
        """
        Validate webhook URL for security.

        Args:
            url: URL to validate

        Raises:
            WebhookValidationError: If URL is invalid or blocked
        """
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise WebhookValidationError(f"Invalid URL format: {e}")

        # Check scheme
        if parsed.scheme not in ("http", "https"):
            raise WebhookValidationError("URL must use http or https scheme")

        if parsed.scheme == "http" and not self.allow_http:
            raise WebhookValidationError("HTTPS is required (http not allowed in production)")

        # Check for empty host
        if not parsed.hostname:
            raise WebhookValidationError("URL must have a hostname")

        hostname = parsed.hostname.lower()

        # Block localhost variations
        blocked_hosts = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]
        if hostname in blocked_hosts:
            raise WebhookValidationError(f"Blocked hostname: {hostname}")

        # Resolve and check IP for SSRF
        resolved_ip = self._resolve_hostname(hostname)
        if resolved_ip and self._is_private_ip(resolved_ip):
            raise WebhookValidationError(
                f"URL resolves to private IP address: {resolved_ip}"
            )

    def check_rate_limit(self, rule_id: str) -> None:
        """
        Check if webhook rate limit is exceeded for a rule.

        Args:
            rule_id: Alert rule UUID

        Raises:
            WebhookRateLimitError: If rate limit exceeded
        """
        now = time.time()
        minute_ago = now - 60

        # Get timestamps for this rule
        timestamps = self._rate_limit_cache.get(rule_id, [])

        # Remove old timestamps
        timestamps = [t for t in timestamps if t > minute_ago]

        if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
            raise WebhookRateLimitError(
                f"Rate limit exceeded: {RATE_LIMIT_PER_MINUTE} webhooks per minute"
            )

        # Add current timestamp
        timestamps.append(now)
        self._rate_limit_cache[rule_id] = timestamps

    def _decrypt_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Decrypt sensitive header values if they are encrypted.

        Args:
            headers: Dictionary of header name -> value pairs

        Returns:
            Headers dictionary with sensitive values decrypted
        """
        if not headers:
            return {}

        decrypted = {}
        for name, value in headers.items():
            if not value:
                decrypted[name] = value
                continue

            # Check if this is a sensitive header that might be encrypted
            if name.lower() in SENSITIVE_HEADERS and is_encrypted(value):
                try:
                    decrypted_value = decrypt_password(value)
                    decrypted[name] = decrypted_value
                    logger.debug(f"Decrypted webhook header: {name}")
                except ValueError:
                    # If decryption fails, log error and use original
                    logger.error(f"Failed to decrypt webhook header: {name}")
                    decrypted[name] = value
            else:
                decrypted[name] = value

        return decrypted

    def build_payload(self, event: Event, rule: AlertRule) -> Dict[str, Any]:
        """
        Build webhook payload from event and rule data.

        Args:
            event: Event that triggered the rule
            rule: Alert rule that matched

        Returns:
            Dictionary payload matching the documented format
        """
        # Parse objects_detected JSON
        try:
            objects_detected = json.loads(event.objects_detected) if isinstance(
                event.objects_detected, str
            ) else event.objects_detected or []
        except json.JSONDecodeError:
            objects_detected = []

        # Build payload matching documented format
        payload = {
            "event_id": event.id,
            "timestamp": event.timestamp.isoformat() if event.timestamp else datetime.now(timezone.utc).isoformat(),
            "camera": {
                "id": event.camera_id,
                "name": getattr(event, 'camera_name', None) or event.camera_id,
            },
            "description": event.description or "",
            "confidence": event.confidence or 0,
            "objects_detected": objects_detected,
            "thumbnail_url": f"/api/v1/events/{event.id}/thumbnail",
            "rule": {
                "id": rule.id,
                "name": rule.name,
            }
        }

        # Story P4-7.3: Add anomaly data if available
        if event.anomaly_score is not None:
            # Classify severity using thresholds from AnomalyScoringService
            from app.services.anomaly_scoring_service import AnomalyScoringService
            low_threshold = AnomalyScoringService.LOW_THRESHOLD
            high_threshold = AnomalyScoringService.HIGH_THRESHOLD

            if event.anomaly_score < low_threshold:
                severity = "low"
            elif event.anomaly_score < high_threshold:
                severity = "medium"
            else:
                severity = "high"

            payload["anomaly"] = {
                "score": event.anomaly_score,
                "severity": severity,
            }

        return payload

    async def _send_single_request(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        client: httpx.AsyncClient
    ) -> tuple[int, str, int, Optional[str]]:
        """
        Send a single HTTP POST request.

        Returns:
            Tuple of (status_code, response_body, response_time_ms, error_message)
        """
        start_time = time.time()

        try:
            # Merge default headers with custom headers
            request_headers = {
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                **headers
            }

            response = await client.post(
                url,
                json=payload,
                headers=request_headers,
                timeout=WEBHOOK_TIMEOUT_SECONDS
            )

            response_time_ms = int((time.time() - start_time) * 1000)
            response_body = response.text[:MAX_RESPONSE_BODY_LENGTH]

            return response.status_code, response_body, response_time_ms, None

        except httpx.TimeoutException:
            response_time_ms = int((time.time() - start_time) * 1000)
            return 0, "", response_time_ms, "Request timeout"

        except httpx.ConnectError as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return 0, "", response_time_ms, f"Connection error: {str(e)}"

        except httpx.RequestError as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return 0, "", response_time_ms, f"Request error: {str(e)}"

        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return 0, "", response_time_ms, f"Unexpected error: {str(e)}"

    async def send_webhook(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        rule_id: Optional[str] = None,
        event_id: Optional[str] = None,
        skip_validation: bool = False
    ) -> WebhookResult:
        """
        Send webhook with retry logic.

        Args:
            url: Target webhook URL
            headers: Custom headers to include
            payload: JSON payload to send
            rule_id: Optional rule ID for logging
            event_id: Optional event ID for logging
            skip_validation: Skip URL validation (for testing)

        Returns:
            WebhookResult with execution details
        """
        # Validate URL
        if not skip_validation:
            self.validate_url(url)

        # Check rate limit if rule_id provided
        if rule_id:
            self.check_rate_limit(rule_id)

        # Create client if not provided
        client = self.http_client or httpx.AsyncClient()
        should_close_client = self.http_client is None

        try:
            retry_count = 0
            last_error = None
            last_status = 0
            last_response = ""
            last_response_time = 0

            for attempt in range(MAX_RETRY_ATTEMPTS):
                status_code, response_body, response_time_ms, error = await self._send_single_request(
                    url, headers, payload, client
                )

                last_status = status_code
                last_response = response_body
                last_response_time = response_time_ms
                last_error = error

                # Success on 2xx status
                success = 200 <= status_code < 300

                # Log attempt
                if rule_id and event_id:
                    self._log_attempt(
                        rule_id=rule_id,
                        event_id=event_id,
                        url=url,
                        status_code=status_code,
                        response_time_ms=response_time_ms,
                        retry_count=retry_count,
                        success=success,
                        error_message=error
                    )

                if success:
                    return WebhookResult(
                        success=True,
                        status_code=status_code,
                        response_body=response_body,
                        response_time_ms=response_time_ms,
                        retry_count=retry_count,
                        error_message=None
                    )

                # Prepare for retry
                retry_count += 1
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.info(f"Webhook failed (attempt {attempt + 1}), retrying in {delay}s...")
                    await asyncio.sleep(delay)

            # All retries exhausted
            logger.warning(f"Webhook failed after {MAX_RETRY_ATTEMPTS} attempts: {url}")
            return WebhookResult(
                success=False,
                status_code=last_status,
                response_body=last_response,
                response_time_ms=last_response_time,
                retry_count=retry_count - 1,  # Last retry count
                error_message=last_error or f"Failed with status {last_status}"
            )

        finally:
            if should_close_client:
                await client.aclose()

    def _log_attempt(
        self,
        rule_id: str,
        event_id: str,
        url: str,
        status_code: int,
        response_time_ms: int,
        retry_count: int,
        success: bool,
        error_message: Optional[str]
    ) -> None:
        """Log webhook attempt to database."""
        try:
            log_entry = WebhookLog(
                alert_rule_id=rule_id,
                event_id=event_id,
                url=url[:2000],  # Truncate to match column size
                status_code=status_code,
                response_time_ms=response_time_ms,
                retry_count=retry_count,
                success=success,
                error_message=error_message
            )
            self.db.add(log_entry)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log webhook attempt: {e}")
            self.db.rollback()

    async def execute_rule_webhook(
        self,
        event: Event,
        rule: AlertRule
    ) -> Optional[WebhookResult]:
        """
        Execute webhook action for a rule that matched an event.

        Args:
            event: Event that triggered the rule
            rule: Alert rule with webhook action configured

        Returns:
            WebhookResult if webhook was executed, None if no webhook configured
        """
        # Parse rule actions
        try:
            actions = json.loads(rule.actions) if isinstance(rule.actions, str) else rule.actions or {}
        except json.JSONDecodeError:
            logger.error(f"Failed to parse rule actions for rule {rule.id}")
            return None

        webhook_config = actions.get("webhook")
        if not webhook_config:
            return None

        url = webhook_config.get("url")
        if not url:
            logger.warning(f"Webhook action missing URL for rule {rule.id}")
            return None

        raw_headers = webhook_config.get("headers", {})
        headers = self._decrypt_headers(raw_headers)
        payload = self.build_payload(event, rule)

        try:
            result = await self.send_webhook(
                url=url,
                headers=headers,
                payload=payload,
                rule_id=rule.id,
                event_id=event.id
            )

            if result.success:
                logger.info(f"Webhook succeeded for rule {rule.name}: {url}")
            else:
                logger.warning(f"Webhook failed for rule {rule.name}: {result.error_message}")

            return result

        except WebhookValidationError as e:
            logger.error(f"Webhook URL validation failed for rule {rule.id}: {e}")
            # Log the validation failure
            self._log_attempt(
                rule_id=rule.id,
                event_id=event.id,
                url=url,
                status_code=0,
                response_time_ms=0,
                retry_count=0,
                success=False,
                error_message=str(e)
            )
            return WebhookResult(
                success=False,
                status_code=0,
                response_body="",
                response_time_ms=0,
                retry_count=0,
                error_message=str(e)
            )

        except WebhookRateLimitError as e:
            logger.warning(f"Webhook rate limited for rule {rule.id}: {e}")
            return WebhookResult(
                success=False,
                status_code=429,
                response_body="",
                response_time_ms=0,
                retry_count=0,
                error_message=str(e)
            )
