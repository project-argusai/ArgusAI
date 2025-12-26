"""
Cloudflare Tunnel Service

Manages cloudflared tunnel subprocess for secure remote access.
Story P11-1.1: Implement Cloudflare Tunnel Integration
Story P11-1.2: Add Tunnel Status Monitoring and Auto-Reconnect

This service provides:
- Async subprocess management for cloudflared tunnel
- Connection status monitoring via stdout/stderr parsing
- Graceful start/stop with lifecycle management
- Token validation and security
- Health check loop with 30-second monitoring (P11-1.2)
- Auto-reconnect with exponential backoff (P11-1.2)
- Prometheus metrics integration (P11-1.2)
"""
import asyncio
import re
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from enum import Enum


logger = logging.getLogger(__name__)


class TunnelStatus(str, Enum):
    """Tunnel connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class TunnelService:
    """
    Manages cloudflared tunnel subprocess for secure remote access.

    Usage:
        service = TunnelService()
        await service.start(token="your-tunnel-token")

        # Check status
        if service.is_connected:
            print(f"Connected: {service.hostname}")

        # Stop tunnel
        await service.stop()
    """

    # Health check interval in seconds (AC-1.2.1)
    HEALTH_CHECK_INTERVAL = 30

    # Exponential backoff settings (AC-1.2.2)
    BACKOFF_BASE = 5  # seconds
    BACKOFF_MULTIPLIER = 2
    BACKOFF_MAX = 30  # seconds
    MAX_RECONNECT_FAILURES = 3

    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._status: TunnelStatus = TunnelStatus.DISCONNECTED
        self._hostname: Optional[str] = None
        self._error_message: Optional[str] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Story P11-1.2: Health check and reconnection tracking
        self._health_check_task: Optional[asyncio.Task] = None
        self._connected_at: Optional[datetime] = None
        self._last_connected: Optional[datetime] = None
        self._reconnect_count: int = 0
        self._consecutive_failures: int = 0
        self._current_backoff: int = self.BACKOFF_BASE
        self._saved_token: Optional[str] = None  # For auto-reconnect

    @property
    def status(self) -> TunnelStatus:
        """Current tunnel connection status."""
        return self._status

    @property
    def is_connected(self) -> bool:
        """Whether tunnel is currently connected."""
        return self._status == TunnelStatus.CONNECTED

    @property
    def hostname(self) -> Optional[str]:
        """Connected tunnel hostname, if available."""
        return self._hostname

    @property
    def error_message(self) -> Optional[str]:
        """Last error message, if any."""
        return self._error_message

    @property
    def is_running(self) -> bool:
        """Whether the tunnel process is running."""
        return self._process is not None and self._process.returncode is None

    @property
    def uptime_seconds(self) -> float:
        """Tunnel uptime in seconds, or 0 if not connected."""
        if self._connected_at and self._status == TunnelStatus.CONNECTED:
            return (datetime.now(timezone.utc) - self._connected_at).total_seconds()
        return 0.0

    @property
    def last_connected(self) -> Optional[datetime]:
        """Timestamp when tunnel was last connected."""
        return self._last_connected

    @property
    def reconnect_count(self) -> int:
        """Number of reconnection attempts since startup."""
        return self._reconnect_count

    def _validate_token(self, token: str) -> bool:
        """
        Validate tunnel token format to prevent command injection.

        Cloudflare tunnel tokens are base64-encoded and follow a specific format.
        We reject any token containing shell metacharacters.

        Args:
            token: The tunnel token to validate

        Returns:
            True if token format is valid, False otherwise
        """
        if not token:
            return False

        # Cloudflare tunnel tokens are base64-encoded JWT-like strings
        # They should only contain alphanumeric chars, hyphens, underscores, and dots
        # No shell metacharacters allowed
        invalid_chars = re.compile(r'[;&|`$(){}[\]<>!#\'\"\\\n\r\t]')
        if invalid_chars.search(token):
            logger.warning(
                "Invalid characters in tunnel token",
                extra={"event_type": "tunnel_token_validation_failed"}
            )
            return False

        # Token should be reasonably long (typical JWT is 100+ chars)
        if len(token) < 50:
            logger.warning(
                "Tunnel token too short",
                extra={"event_type": "tunnel_token_validation_failed"}
            )
            return False

        return True

    async def start(self, token: str) -> bool:
        """
        Start the cloudflared tunnel with the given token.

        Args:
            token: Cloudflare tunnel token (from Cloudflare Zero Trust dashboard)

        Returns:
            True if tunnel started successfully, False otherwise
        """
        async with self._lock:
            if self.is_running:
                logger.warning(
                    "Tunnel already running, stop first",
                    extra={"event_type": "tunnel_already_running"}
                )
                return False

            # Validate token format
            if not self._validate_token(token):
                self._status = TunnelStatus.ERROR
                self._error_message = "Invalid tunnel token format"
                return False

            self._status = TunnelStatus.CONNECTING
            self._error_message = None

            try:
                # Start cloudflared process
                # Never log the token value
                logger.info(
                    "Starting cloudflared tunnel",
                    extra={"event_type": "tunnel_starting"}
                )

                self._process = await asyncio.create_subprocess_exec(
                    "cloudflared",
                    "tunnel",
                    "run",
                    "--token",
                    token,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                # Start monitoring task
                self._monitor_task = asyncio.create_task(self._monitor_output())

                # Wait briefly to check for immediate failures
                await asyncio.sleep(2)

                if self._process.returncode is not None:
                    # Process exited immediately - likely error
                    self._status = TunnelStatus.ERROR
                    self._update_metrics()
                    return False

                # Story P11-1.2: Save token for auto-reconnect and start health check
                self._saved_token = token

                # Start health check loop
                if self._health_check_task is None or self._health_check_task.done():
                    self._health_check_task = asyncio.create_task(self._health_check_loop())

                logger.info(
                    "Cloudflared tunnel process started",
                    extra={
                        "event_type": "tunnel.started",
                        "pid": self._process.pid
                    }
                )

                return True

            except FileNotFoundError:
                self._status = TunnelStatus.ERROR
                self._error_message = "cloudflared not found - please install it"
                logger.error(
                    "cloudflared executable not found",
                    extra={"event_type": "tunnel_cloudflared_not_found"}
                )
                return False
            except Exception as e:
                self._status = TunnelStatus.ERROR
                self._error_message = str(e)
                logger.error(
                    f"Failed to start tunnel: {e}",
                    extra={"event_type": "tunnel_start_failed", "error": str(e)}
                )
                return False

    async def _monitor_output(self):
        """
        Monitor cloudflared stdout/stderr for status updates.

        Parses output to detect connection status and extract hostname.
        """
        if not self._process:
            return

        try:
            while self._process.returncode is None:
                # Read from stderr (cloudflared logs to stderr)
                if self._process.stderr:
                    line = await asyncio.wait_for(
                        self._process.stderr.readline(),
                        timeout=30
                    )
                    if line:
                        line_str = line.decode('utf-8', errors='replace').strip()
                        await self._parse_log_line(line_str)
                else:
                    await asyncio.sleep(1)
        except asyncio.TimeoutError:
            # No output for 30 seconds, just continue
            pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(
                f"Error monitoring tunnel output: {e}",
                extra={"event_type": "tunnel_monitor_error", "error": str(e)}
            )
        finally:
            if self._process and self._process.returncode is not None:
                self._status = TunnelStatus.DISCONNECTED
                logger.info(
                    "Cloudflared tunnel process exited",
                    extra={
                        "event_type": "tunnel_process_exited",
                        "return_code": self._process.returncode
                    }
                )

    async def _parse_log_line(self, line: str):
        """
        Parse cloudflared log line for status information.

        Args:
            line: Log line from cloudflared stderr
        """
        # Don't log the full line as it may contain sensitive info
        # Just look for specific patterns

        # Connection established
        if "Connection" in line and "registered" in line:
            self._status = TunnelStatus.CONNECTED
            now = datetime.now(timezone.utc)
            self._connected_at = now
            self._last_connected = now
            self._consecutive_failures = 0
            self._current_backoff = self.BACKOFF_BASE
            self._update_metrics()

            # Story P11-1.2 AC-1.2.3: Structured logging for tunnel.connected
            logger.info(
                "Cloudflared tunnel connected",
                extra={
                    "event_type": "tunnel.connected",
                    "hostname": self._hostname,
                    "tunnel_id": self._process.pid if self._process else None
                }
            )

        # Extract hostname if present
        # Pattern like: "Registered tunnel connection ... origin=https://example.cloudflare.com"
        hostname_match = re.search(r'origin=https?://([^\s,]+)', line)
        if hostname_match:
            self._hostname = hostname_match.group(1)
            logger.info(
                "Tunnel hostname detected",
                extra={"event_type": "tunnel_hostname", "hostname": self._hostname}
            )

        # Also look for ingress rules with URLs
        # Pattern: "Ingress ... URL https://something.trycloudflare.com"
        url_match = re.search(r'https://([a-zA-Z0-9\-\.]+\.(?:trycloudflare\.com|cloudflare\.com|cfargotunnel\.com))', line)
        if url_match and not self._hostname:
            self._hostname = url_match.group(1)
            logger.info(
                "Tunnel hostname detected from URL",
                extra={"event_type": "tunnel_hostname", "hostname": self._hostname}
            )

        # Error detection
        if "error" in line.lower() or "failed" in line.lower():
            if "retrying" not in line.lower():  # Ignore transient retry messages
                self._error_message = line[:200]  # Truncate for safety
                logger.warning(
                    "Tunnel error detected",
                    extra={"event_type": "tunnel_error"}
                )

    async def stop(self, timeout: float = 10.0, clear_token: bool = False) -> bool:
        """
        Stop the cloudflared tunnel gracefully.

        Args:
            timeout: Maximum seconds to wait for graceful shutdown
            clear_token: If True, also clear saved token (prevents auto-reconnect)

        Returns:
            True if tunnel stopped successfully
        """
        async with self._lock:
            # Story P11-1.2: Cancel health check task first
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
                self._health_check_task = None

            if not self._process:
                self._status = TunnelStatus.DISCONNECTED
                if clear_token:
                    self._saved_token = None
                self._update_metrics()
                return True

            # Calculate uptime for logging
            uptime = self.uptime_seconds

            logger.info(
                "Stopping cloudflared tunnel",
                extra={
                    "event_type": "tunnel.stopping",
                    "pid": self._process.pid,
                    "uptime_seconds": uptime
                }
            )

            # Cancel monitor task
            if self._monitor_task:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass

            # Try graceful shutdown first
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning(
                        "Tunnel did not stop gracefully, killing",
                        extra={"event_type": "tunnel.force_kill"}
                    )
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                # Process already exited
                pass

            self._process = None
            self._status = TunnelStatus.DISCONNECTED
            self._hostname = None
            self._error_message = None
            self._connected_at = None

            if clear_token:
                self._saved_token = None

            self._update_metrics()

            logger.info(
                "Cloudflared tunnel stopped",
                extra={
                    "event_type": "tunnel.stopped",
                    "duration_seconds": uptime
                }
            )

            return True

    def get_status_dict(self) -> dict:
        """
        Get tunnel status as a dictionary for API responses.

        Returns:
            Dict with status, hostname, error, uptime, and reconnect information
        """
        return {
            "status": self._status.value,
            "is_connected": self.is_connected,
            "is_running": self.is_running,
            "hostname": self._hostname,
            "error": self._error_message,
            # Story P11-1.2: Enhanced status fields
            "uptime_seconds": self.uptime_seconds,
            "last_connected": self._last_connected.isoformat() if self._last_connected else None,
            "reconnect_count": self._reconnect_count,
        }

    async def _health_check_loop(self):
        """
        Monitor tunnel connection health every 30 seconds (AC-1.2.1).

        Detects disconnection via process exit and triggers auto-reconnect.
        """
        logger.info(
            "Tunnel health check loop started",
            extra={"event_type": "tunnel.health_check_started", "interval_seconds": self.HEALTH_CHECK_INTERVAL}
        )

        try:
            while True:
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)

                # Check if process is still running
                if self._process is None:
                    logger.warning(
                        "Tunnel process is None during health check",
                        extra={"event_type": "tunnel.health_check_failed", "reason": "process_none"}
                    )
                    await self._handle_disconnect("Process is None")
                    continue

                if self._process.returncode is not None:
                    # Process has exited
                    exit_code = self._process.returncode
                    logger.warning(
                        "Tunnel process exited unexpectedly",
                        extra={
                            "event_type": "tunnel.disconnected",
                            "return_code": exit_code,
                            "duration_seconds": self.uptime_seconds,
                            "reason": f"Process exited with code {exit_code}"
                        }
                    )
                    await self._handle_disconnect(f"Process exited with code {exit_code}")
                    continue

                # Update uptime metric while connected
                if self._status == TunnelStatus.CONNECTED:
                    self._update_metrics()

        except asyncio.CancelledError:
            logger.info(
                "Tunnel health check loop cancelled",
                extra={"event_type": "tunnel.health_check_stopped"}
            )
            raise
        except Exception as e:
            logger.error(
                f"Error in health check loop: {e}",
                extra={"event_type": "tunnel.health_check_error", "error": str(e)}
            )

    async def _handle_disconnect(self, reason: str):
        """
        Handle tunnel disconnection and trigger auto-reconnect.

        Args:
            reason: Human-readable disconnection reason
        """
        uptime = self.uptime_seconds
        self._status = TunnelStatus.DISCONNECTED
        self._connected_at = None
        self._process = None
        self._update_metrics()

        # Log disconnection with structured format (AC-1.2.3)
        logger.warning(
            "Tunnel disconnected",
            extra={
                "event_type": "tunnel.disconnected",
                "duration_seconds": uptime,
                "reason": reason
            }
        )

        # Attempt auto-reconnect if we have a saved token
        if self._saved_token:
            await self._reconnect()

    async def _reconnect(self):
        """
        Attempt to reconnect with exponential backoff (AC-1.2.2).

        Backoff: 5s, 10s, 20s, 30s (max)
        Sets error state after 3 consecutive failures.
        """
        from app.core.metrics import record_tunnel_reconnect_attempt

        self._consecutive_failures += 1
        self._reconnect_count += 1

        # Record metrics
        record_tunnel_reconnect_attempt()

        # Log reconnection attempt (AC-1.2.3)
        logger.info(
            "Attempting tunnel reconnection",
            extra={
                "event_type": "tunnel.reconnecting",
                "attempt": self._consecutive_failures,
                "backoff_seconds": self._current_backoff
            }
        )

        # Check if we've exceeded max failures
        if self._consecutive_failures > self.MAX_RECONNECT_FAILURES:
            self._status = TunnelStatus.ERROR
            self._error_message = f"Auto-reconnect failed after {self.MAX_RECONNECT_FAILURES} attempts"
            self._update_metrics()
            logger.error(
                "Tunnel auto-reconnect failed, max attempts exceeded",
                extra={
                    "event_type": "tunnel.error",
                    "error": self._error_message,
                    "total_attempts": self._consecutive_failures
                }
            )
            return

        # Wait with exponential backoff
        await asyncio.sleep(self._current_backoff)

        # Increase backoff for next attempt
        self._current_backoff = min(
            self._current_backoff * self.BACKOFF_MULTIPLIER,
            self.BACKOFF_MAX
        )

        # Attempt reconnection (without holding the lock - start() will acquire it)
        self._status = TunnelStatus.CONNECTING
        try:
            success = await self.start(self._saved_token)
            if success:
                logger.info(
                    "Tunnel reconnected successfully",
                    extra={
                        "event_type": "tunnel.reconnected",
                        "attempts": self._consecutive_failures
                    }
                )
                # Reset backoff on success (done in _parse_log_line when connected)
        except Exception as e:
            logger.error(
                f"Tunnel reconnection failed: {e}",
                extra={
                    "event_type": "tunnel.error",
                    "error": str(e),
                    "attempt": self._consecutive_failures
                }
            )
            # Schedule another reconnect attempt via health check loop

    def _update_metrics(self):
        """Update Prometheus metrics for tunnel status."""
        try:
            from app.core.metrics import (
                update_tunnel_connection_status,
                update_tunnel_uptime
            )
            update_tunnel_connection_status(self.is_connected)
            update_tunnel_uptime(self.uptime_seconds)
        except ImportError:
            # Metrics module not available (e.g., in tests)
            pass


# Global singleton instance
_tunnel_service: Optional[TunnelService] = None


def get_tunnel_service() -> TunnelService:
    """Get the global TunnelService singleton."""
    global _tunnel_service
    if _tunnel_service is None:
        _tunnel_service = TunnelService()
    return _tunnel_service
