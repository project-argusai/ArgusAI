"""
UniFi Protect Service for controller connection management (Story P2-1.4)

Provides functionality to:
- Test controller connections before saving
- Manage persistent WebSocket connections for real-time events
- Auto-reconnect with exponential backoff on disconnect
- Broadcast connection status changes to frontend
- Discover cameras from connected controllers (future stories)
"""
import asyncio
import ssl
import logging
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiohttp
from uiprotect import ProtectApiClient
from uiprotect.exceptions import BadRequest, NotAuthorized, NvrError

from app.core.database import SessionLocal
from app.services.websocket_manager import get_websocket_manager
from app.services.protect_event_handler import get_protect_event_handler

if TYPE_CHECKING:
    from app.models.protect_controller import ProtectController

logger = logging.getLogger(__name__)

# Connection timeout in seconds (NFR3)
CONNECTION_TIMEOUT = 10.0

# Exponential backoff delays in seconds (AC3)
BACKOFF_DELAYS = [1, 2, 4, 8, 16, 30]  # max 30 seconds

# WebSocket message type for connection status (AC6)
PROTECT_CONNECTION_STATUS = "PROTECT_CONNECTION_STATUS"

# WebSocket message type for camera status changes (Story P2-2.4 AC6, AC7)
CAMERA_STATUS_CHANGED = "CAMERA_STATUS_CHANGED"

# Camera status change debounce in seconds (Story P2-2.4 AC12)
CAMERA_STATUS_DEBOUNCE_SECONDS = 5

# Camera discovery cache TTL in seconds (Story P2-2.1 AC4)
CAMERA_CACHE_TTL_SECONDS = 60


@dataclass
class DiscoveredCamera:
    """Represents a camera discovered from a Protect controller (Story P2-2.1)"""
    protect_camera_id: str
    name: str
    type: str  # "camera" or "doorbell"
    model: str
    is_online: bool
    is_doorbell: bool
    smart_detection_capabilities: List[str] = field(default_factory=list)
    is_enabled_for_ai: bool = False  # Set during cross-reference with cameras table


@dataclass
class CameraDiscoveryResult:
    """Result of camera discovery operation (Story P2-2.1)"""
    cameras: List[DiscoveredCamera]
    cached: bool
    cached_at: Optional[datetime] = None
    warning: Optional[str] = None


@dataclass
class ConnectionTestResult:
    """Result of a controller connection test"""
    success: bool
    message: str
    firmware_version: Optional[str] = None
    camera_count: Optional[int] = None
    error_type: Optional[str] = None


class ProtectService:
    """
    Service class for UniFi Protect controller operations (Story P2-1.4).

    Handles connection testing, WebSocket connection management, and
    real-time event streaming from UniFi Protect controllers.

    Features:
    - Test controller connections before saving
    - Maintain persistent WebSocket connections
    - Auto-reconnect with exponential backoff on disconnect
    - Broadcast connection status changes to frontend
    - Graceful shutdown with cleanup

    Attributes:
        _connections: Dict mapping controller_id to ProtectApiClient
        _listener_tasks: Dict mapping controller_id to asyncio.Task
        _shutdown_event: Event to signal shutdown to all listeners
    """

    def __init__(self):
        """Initialize the ProtectService with empty connection dictionaries."""
        # Active client connections (AC9: stored for lifecycle management)
        self._connections: Dict[str, ProtectApiClient] = {}
        # Background WebSocket listener tasks
        self._listener_tasks: Dict[str, asyncio.Task] = {}
        # Shutdown signal for graceful cleanup
        self._shutdown_event = asyncio.Event()
        # Camera discovery cache: controller_id -> (cameras, cached_at) (Story P2-2.1 AC4)
        self._camera_cache: Dict[str, Tuple[List[DiscoveredCamera], datetime]] = {}
        # Camera status debounce tracking: camera_id -> last_broadcast_time (Story P2-2.4 AC12)
        self._camera_status_broadcast_times: Dict[str, datetime] = {}
        # Track last known camera status to detect changes: camera_id -> is_online (Story P2-2.4)
        self._last_camera_status: Dict[str, bool] = {}

    async def test_connection(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        verify_ssl: bool = False
    ) -> ConnectionTestResult:
        """
        Test connection to a UniFi Protect controller.

        Attempts to connect to the controller, authenticate, and retrieve
        basic information (firmware version, camera count).

        Args:
            host: Controller IP address or hostname
            port: HTTPS port (default 443)
            username: Protect authentication username
            password: Protect authentication password
            verify_ssl: Whether to verify SSL certificates

        Returns:
            ConnectionTestResult with success status and details

        Note:
            This method does not persist any data - test-only operation.
            Connection is closed after test regardless of outcome.
        """
        # Log connection attempt (no credentials)
        logger.info(
            f"Testing Protect controller connection",
            extra={
                "event_type": "protect_connection_test_start",
                "host": host,
                "port": port,
                "verify_ssl": verify_ssl
            }
        )

        client = None
        try:
            # Create client with SSL verification setting
            client = ProtectApiClient(
                host=host,
                port=port,
                username=username,
                password=password,
                verify_ssl=verify_ssl
            )

            # Attempt login and update with timeout
            async def connect_and_update():
                await client.update()  # uiprotect handles login internally in update()

            await asyncio.wait_for(
                connect_and_update(),
                timeout=CONNECTION_TIMEOUT
            )

            # Extract controller info
            firmware_version = None
            camera_count = 0

            if client.bootstrap:
                if client.bootstrap.nvr:
                    # Convert Version object to string
                    firmware_version = str(client.bootstrap.nvr.version)
                camera_count = len(client.bootstrap.cameras) if client.bootstrap.cameras else 0

            logger.info(
                f"Protect controller connection successful",
                extra={
                    "event_type": "protect_connection_test_success",
                    "host": host,
                    "firmware_version": firmware_version,
                    "camera_count": camera_count
                }
            )

            return ConnectionTestResult(
                success=True,
                message="Connected successfully",
                firmware_version=firmware_version,
                camera_count=camera_count
            )

        except asyncio.TimeoutError:
            logger.warning(
                f"Protect controller connection timed out",
                extra={
                    "event_type": "protect_connection_test_timeout",
                    "host": host,
                    "timeout_seconds": CONNECTION_TIMEOUT
                }
            )
            return ConnectionTestResult(
                success=False,
                message=f"Connection timed out after {int(CONNECTION_TIMEOUT)} seconds",
                error_type="timeout"
            )

        except NotAuthorized:
            logger.warning(
                f"Protect controller authentication failed",
                extra={
                    "event_type": "protect_connection_test_auth_failed",
                    "host": host
                }
            )
            return ConnectionTestResult(
                success=False,
                message="Authentication failed",
                error_type="auth_error"
            )

        except aiohttp.ClientConnectorCertificateError as e:
            logger.warning(
                f"Protect controller SSL certificate error",
                extra={
                    "event_type": "protect_connection_test_ssl_error",
                    "host": host,
                    "error_type": "ssl_certificate"
                }
            )
            return ConnectionTestResult(
                success=False,
                message="SSL certificate verification failed",
                error_type="ssl_error"
            )

        except ssl.SSLError as e:
            logger.warning(
                f"Protect controller SSL error",
                extra={
                    "event_type": "protect_connection_test_ssl_error",
                    "host": host,
                    "error_type": "ssl"
                }
            )
            return ConnectionTestResult(
                success=False,
                message="SSL certificate verification failed",
                error_type="ssl_error"
            )

        except aiohttp.ClientConnectorError as e:
            logger.warning(
                f"Protect controller host unreachable",
                extra={
                    "event_type": "protect_connection_test_unreachable",
                    "host": host
                }
            )
            return ConnectionTestResult(
                success=False,
                message=f"Host unreachable: {host}",
                error_type="connection_error"
            )

        except (BadRequest, NvrError) as e:
            logger.warning(
                f"Protect controller error",
                extra={
                    "event_type": "protect_connection_test_error",
                    "host": host,
                    "error_type": type(e).__name__
                }
            )
            return ConnectionTestResult(
                success=False,
                message=f"Connection failed: {type(e).__name__}",
                error_type="nvr_error"
            )

        except Exception as e:
            logger.error(
                f"Protect controller unexpected error",
                extra={
                    "event_type": "protect_connection_test_error",
                    "host": host,
                    "error_type": type(e).__name__
                }
            )
            return ConnectionTestResult(
                success=False,
                message=f"Connection failed: {type(e).__name__}",
                error_type="unknown"
            )

        finally:
            # Always close the client connection
            if client:
                try:
                    await client.close()
                except Exception:
                    pass  # Ignore errors during cleanup

    # =========================================================================
    # Connection Management Methods (Story P2-1.4)
    # =========================================================================

    async def connect(self, controller: "ProtectController") -> bool:
        """
        Establish a persistent WebSocket connection to a Protect controller (AC1).

        Creates a ProtectApiClient, connects to the controller, starts a
        background WebSocket listener task, and updates the database state.

        Args:
            controller: ProtectController model instance with connection details

        Returns:
            True if connection established successfully, False otherwise

        Note:
            On success, broadcasts PROTECT_CONNECTION_STATUS to frontend (AC6)
            and updates database fields is_connected, last_connected_at (AC2).
        """
        controller_id = str(controller.id)

        # Check if already connected
        if controller_id in self._connections:
            logger.info(
                "Controller already connected",
                extra={
                    "event_type": "protect_connect_already_connected",
                    "controller_id": controller_id,
                    "controller_name": controller.name
                }
            )
            return True

        # Broadcast connecting status (AC6)
        await self._broadcast_status(controller_id, "connecting")

        logger.info(
            "Connecting to Protect controller",
            extra={
                "event_type": "protect_connect_start",
                "controller_id": controller_id,
                "controller_name": controller.name,
                "host": controller.host
            }
        )

        try:
            # Create client with decrypted password
            client = ProtectApiClient(
                host=controller.host,
                port=controller.port,
                username=controller.username,
                password=controller.get_decrypted_password(),
                verify_ssl=controller.verify_ssl
            )

            # Connect with timeout
            await asyncio.wait_for(
                client.update(),
                timeout=CONNECTION_TIMEOUT
            )

            # Store the connected client (AC9)
            self._connections[controller_id] = client

            # Update database state (AC2)
            await self._update_controller_state(
                controller_id,
                is_connected=True,
                last_connected_at=datetime.now(timezone.utc),
                last_error=None
            )

            # Start background WebSocket listener task
            task = asyncio.create_task(
                self._websocket_listener(controller),
                name=f"protect_ws_{controller_id}"
            )
            self._listener_tasks[controller_id] = task

            # Broadcast connected status (AC6)
            await self._broadcast_status(controller_id, "connected")

            logger.info(
                "Protect controller connected successfully",
                extra={
                    "event_type": "protect_connect_success",
                    "controller_id": controller_id,
                    "controller_name": controller.name
                }
            )

            return True

        except asyncio.TimeoutError:
            error_msg = f"Connection timed out after {int(CONNECTION_TIMEOUT)} seconds"
            await self._handle_connection_error(controller_id, error_msg, "timeout")
            return False

        except NotAuthorized:
            error_msg = "Authentication failed - check credentials"
            await self._handle_connection_error(controller_id, error_msg, "auth_error")
            return False

        except aiohttp.ClientConnectorCertificateError:
            error_msg = "SSL certificate verification failed"
            await self._handle_connection_error(controller_id, error_msg, "ssl_error")
            return False

        except ssl.SSLError:
            error_msg = "SSL certificate verification failed"
            await self._handle_connection_error(controller_id, error_msg, "ssl_error")
            return False

        except aiohttp.ClientConnectorError:
            error_msg = f"Host unreachable: {controller.host}"
            await self._handle_connection_error(controller_id, error_msg, "connection_error")
            return False

        except (BadRequest, NvrError) as e:
            error_msg = f"Controller error: {type(e).__name__}"
            await self._handle_connection_error(controller_id, error_msg, "nvr_error")
            return False

        except asyncio.CancelledError:
            # Graceful shutdown - don't treat as error
            logger.info(
                "Connection cancelled during shutdown",
                extra={
                    "event_type": "protect_connect_cancelled",
                    "controller_id": controller_id
                }
            )
            raise

        except Exception as e:
            error_msg = f"Unexpected error: {type(e).__name__}"
            await self._handle_connection_error(controller_id, error_msg, "unknown")
            return False

    async def disconnect(self, controller_id: str) -> None:
        """
        Disconnect from a Protect controller and cleanup resources (AC5).

        Cancels the WebSocket listener task, closes the client connection,
        and updates the database state.

        Args:
            controller_id: UUID of the controller to disconnect

        Note:
            Safe to call even if not connected (no-op).
            Updates is_connected to False in database.
            Broadcasts disconnected status to frontend.
        """
        logger.info(
            "Disconnecting from Protect controller",
            extra={
                "event_type": "protect_disconnect_start",
                "controller_id": controller_id
            }
        )

        # Cancel listener task if exists
        if controller_id in self._listener_tasks:
            task = self._listener_tasks.pop(controller_id)
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

        # Close client connection if exists
        if controller_id in self._connections:
            client = self._connections.pop(controller_id)
            try:
                await client.close()
            except Exception:
                pass  # Ignore errors during cleanup

        # Update database state (AC5)
        await self._update_controller_state(
            controller_id,
            is_connected=False,
            last_error=None
        )

        # Broadcast disconnected status (AC6)
        await self._broadcast_status(controller_id, "disconnected")

        logger.info(
            "Protect controller disconnected",
            extra={
                "event_type": "protect_disconnect_complete",
                "controller_id": controller_id
            }
        )

    async def disconnect_all(self, timeout: float = 10.0) -> None:
        """
        Disconnect all controllers gracefully (AC5).

        Used during application shutdown to cleanly close all connections.

        Args:
            timeout: Maximum time to wait for all disconnections
        """
        logger.info(
            "Disconnecting all Protect controllers",
            extra={
                "event_type": "protect_disconnect_all_start",
                "controller_count": len(self._connections)
            }
        )

        # Signal shutdown to all listeners
        self._shutdown_event.set()

        # Disconnect each controller
        controller_ids = list(self._connections.keys())
        disconnect_tasks = [
            self.disconnect(controller_id)
            for controller_id in controller_ids
        ]

        if disconnect_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*disconnect_tasks, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Timeout during disconnect_all",
                    extra={
                        "event_type": "protect_disconnect_all_timeout",
                        "timeout_seconds": timeout
                    }
                )

        # Clear any remaining references
        self._connections.clear()
        self._listener_tasks.clear()

        logger.info(
            "All Protect controllers disconnected",
            extra={"event_type": "protect_disconnect_all_complete"}
        )

    async def _websocket_listener(self, controller: "ProtectController") -> None:
        """
        Background task that maintains WebSocket connection (AC1, AC3, AC4).

        Subscribes to controller events and handles reconnection on disconnect.
        Runs until cancelled or shutdown event is set.

        Args:
            controller: ProtectController model instance
        """
        controller_id = str(controller.id)

        while not self._shutdown_event.is_set():
            try:
                client = self._connections.get(controller_id)
                if not client:
                    logger.warning(
                        "No client found for listener",
                        extra={
                            "event_type": "protect_listener_no_client",
                            "controller_id": controller_id
                        }
                    )
                    break

                # Subscribe to WebSocket events (Story P2-2.4: camera status changes, Story P2-3.1: motion events)
                def event_callback(msg):
                    # Handle camera status changes (Story P2-2.4 AC6)
                    asyncio.create_task(
                        self._handle_websocket_event(controller_id, msg)
                    )
                    # Handle motion/smart detection events (Story P2-3.1 AC1)
                    event_handler = get_protect_event_handler()
                    asyncio.create_task(
                        event_handler.handle_event(controller_id, msg)
                    )

                unsub = client.subscribe_websocket(event_callback)

                try:
                    # Keep alive until disconnected or shutdown
                    while not self._shutdown_event.is_set():
                        await asyncio.sleep(1)

                        # Check if client is still valid
                        if controller_id not in self._connections:
                            break

                finally:
                    # Unsubscribe from events
                    if unsub:
                        unsub()

            except asyncio.CancelledError:
                logger.info(
                    "WebSocket listener cancelled",
                    extra={
                        "event_type": "protect_listener_cancelled",
                        "controller_id": controller_id
                    }
                )
                break

            except Exception as e:
                # Connection lost - attempt reconnect with backoff (AC3, AC4)
                logger.warning(
                    "WebSocket connection lost, will reconnect",
                    extra={
                        "event_type": "protect_listener_error",
                        "controller_id": controller_id,
                        "error_type": type(e).__name__
                    }
                )

                # Update state and broadcast reconnecting status
                await self._update_controller_state(
                    controller_id,
                    is_connected=False,
                    last_error=f"Connection lost: {type(e).__name__}"
                )
                await self._broadcast_status(controller_id, "reconnecting")

                # Remove current client
                if controller_id in self._connections:
                    old_client = self._connections.pop(controller_id)
                    try:
                        await old_client.close()
                    except Exception:
                        pass

                # Attempt reconnect with exponential backoff
                if not self._shutdown_event.is_set():
                    await self._reconnect_with_backoff(controller)

    async def _reconnect_with_backoff(self, controller: "ProtectController") -> None:
        """
        Attempt to reconnect with exponential backoff (AC3, AC4).

        Delays: 1s, 2s, 4s, 8s, 16s, 30s (max). Unlimited attempts.
        First attempt within 5 seconds of disconnect (NFR3/AC4).

        Args:
            controller: ProtectController model instance to reconnect
        """
        controller_id = str(controller.id)
        attempt = 0

        logger.info(
            "Starting reconnection with backoff",
            extra={
                "event_type": "protect_reconnect_start",
                "controller_id": controller_id,
                "controller_name": controller.name
            }
        )

        while not self._shutdown_event.is_set():
            # Calculate delay using exponential backoff
            delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]

            logger.info(
                f"Reconnect attempt {attempt + 1} in {delay}s",
                extra={
                    "event_type": "protect_reconnect_attempt",
                    "controller_id": controller_id,
                    "attempt": attempt + 1,
                    "delay_seconds": delay
                }
            )

            # Wait before attempting (first wait is 1s, satisfies AC4 < 5s)
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=delay
                )
                # Shutdown event was set - exit
                break
            except asyncio.TimeoutError:
                # Timeout expired - continue with reconnect attempt
                pass

            # Attempt reconnection
            try:
                # Refresh controller from database in case credentials changed
                db = SessionLocal()
                try:
                    from app.models.protect_controller import ProtectController as PC
                    fresh_controller = db.query(PC).filter(PC.id == controller_id).first()
                    if not fresh_controller:
                        logger.error(
                            "Controller no longer exists",
                            extra={
                                "event_type": "protect_reconnect_controller_gone",
                                "controller_id": controller_id
                            }
                        )
                        break
                finally:
                    db.close()

                # Create new client
                client = ProtectApiClient(
                    host=fresh_controller.host,
                    port=fresh_controller.port,
                    username=fresh_controller.username,
                    password=fresh_controller.get_decrypted_password(),
                    verify_ssl=fresh_controller.verify_ssl
                )

                # Connect with timeout
                await asyncio.wait_for(
                    client.update(),
                    timeout=CONNECTION_TIMEOUT
                )

                # Success - store client and update state
                self._connections[controller_id] = client

                await self._update_controller_state(
                    controller_id,
                    is_connected=True,
                    last_connected_at=datetime.now(timezone.utc),
                    last_error=None
                )

                await self._broadcast_status(controller_id, "connected")

                logger.info(
                    "Reconnection successful",
                    extra={
                        "event_type": "protect_reconnect_success",
                        "controller_id": controller_id,
                        "attempts": attempt + 1
                    }
                )

                return  # Exit backoff loop on success

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.warning(
                    f"Reconnect attempt {attempt + 1} failed",
                    extra={
                        "event_type": "protect_reconnect_failed",
                        "controller_id": controller_id,
                        "attempt": attempt + 1,
                        "error_type": type(e).__name__
                    }
                )

                await self._update_controller_state(
                    controller_id,
                    is_connected=False,
                    last_error=f"Reconnect failed: {type(e).__name__}"
                )

            attempt += 1

    async def _handle_connection_error(
        self,
        controller_id: str,
        error_msg: str,
        error_type: str
    ) -> None:
        """
        Handle connection error by updating state and broadcasting (AC7).

        Args:
            controller_id: Controller UUID
            error_msg: Human-readable error message
            error_type: Error classification for logging
        """
        logger.warning(
            f"Protect connection error: {error_msg}",
            extra={
                "event_type": "protect_connection_error",
                "controller_id": controller_id,
                "error_type": error_type
                # Note: No credentials logged (AC7)
            }
        )

        # Update database state (AC7)
        await self._update_controller_state(
            controller_id,
            is_connected=False,
            last_error=error_msg
        )

        # Broadcast error status (AC6)
        await self._broadcast_status(controller_id, "error", error_msg)

    async def _update_controller_state(
        self,
        controller_id: str,
        is_connected: Optional[bool] = None,
        last_connected_at: Optional[datetime] = None,
        last_error: Optional[str] = None
    ) -> None:
        """
        Update controller state in database (AC2, AC7).

        Uses SessionLocal for background task database operations.

        Args:
            controller_id: Controller UUID
            is_connected: New connection status (optional)
            last_connected_at: Timestamp of successful connection (optional)
            last_error: Error message or None to clear (optional)
        """
        db = SessionLocal()
        try:
            from app.models.protect_controller import ProtectController as PC
            controller = db.query(PC).filter(PC.id == controller_id).first()

            if controller:
                if is_connected is not None:
                    controller.is_connected = is_connected
                if last_connected_at is not None:
                    controller.last_connected_at = last_connected_at
                if last_error is not None or last_error == "":
                    controller.last_error = last_error if last_error else None

                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(
                f"Failed to update controller state",
                extra={
                    "event_type": "protect_state_update_error",
                    "controller_id": controller_id,
                    "error": str(e)
                }
            )
        finally:
            db.close()

    async def _broadcast_status(
        self,
        controller_id: str,
        status: str,
        error: Optional[str] = None
    ) -> None:
        """
        Broadcast connection status to frontend via WebSocket (AC6).

        Message format:
        {
            "type": "PROTECT_CONNECTION_STATUS",
            "data": {
                "controller_id": "uuid",
                "status": "connected|disconnected|connecting|reconnecting|error",
                "error": "optional error message"
            },
            "timestamp": "ISO8601"  // Added by WebSocketManager
        }

        Args:
            controller_id: Controller UUID
            status: Connection status string
            error: Optional error message for error status
        """
        message = {
            "type": PROTECT_CONNECTION_STATUS,
            "data": {
                "controller_id": controller_id,
                "status": status
            }
        }

        if error:
            message["data"]["error"] = error

        websocket_manager = get_websocket_manager()
        await websocket_manager.broadcast(message)

    # =========================================================================
    # Camera Status Event Handling (Story P2-2.4)
    # =========================================================================

    async def _handle_websocket_event(
        self,
        controller_id: str,
        msg: Any
    ) -> None:
        """
        Handle WebSocket events from uiprotect (Story P2-2.4 AC6).

        Processes camera status change events and broadcasts to frontend
        with debouncing to prevent UI thrashing.

        Args:
            controller_id: Controller UUID
            msg: WebSocket message from uiprotect
        """
        try:
            # Extract event type from message
            # uiprotect WSSubscriptionMessage has action and new_obj attributes
            action = getattr(msg, 'action', None)
            new_obj = getattr(msg, 'new_obj', None)

            if not new_obj:
                return

            # Check if this is a camera update event
            # uiprotect model types: Camera, Doorbell, etc.
            model_type = type(new_obj).__name__
            if model_type not in ('Camera', 'Doorbell'):
                return

            # Extract camera ID
            camera_id = str(getattr(new_obj, 'id', ''))
            if not camera_id:
                return

            # Check if status changed (is_connected attribute indicates online status)
            is_online = getattr(new_obj, 'is_connected', None)
            if is_online is None:
                # Try alternative attribute names
                is_online = getattr(new_obj, 'is_online', None)
                if is_online is None:
                    return

            # Check if status actually changed from last known state
            last_status = self._last_camera_status.get(camera_id)
            if last_status == is_online:
                # No change detected
                return

            # Status changed - check debounce (AC12)
            if not self._should_broadcast_camera_status(camera_id):
                logger.debug(
                    "Camera status change debounced",
                    extra={
                        "event_type": "protect_camera_status_debounced",
                        "controller_id": controller_id,
                        "camera_id": camera_id,
                        "is_online": is_online
                    }
                )
                return

            # Update last known status
            self._last_camera_status[camera_id] = is_online

            # Broadcast status change to frontend (AC6, AC7)
            await self._broadcast_camera_status_change(
                controller_id=controller_id,
                camera_id=camera_id,
                is_online=is_online
            )

            # Update debounce tracking
            self._camera_status_broadcast_times[camera_id] = datetime.now(timezone.utc)

            logger.info(
                f"Camera status changed: {'online' if is_online else 'offline'}",
                extra={
                    "event_type": "protect_camera_status_changed",
                    "controller_id": controller_id,
                    "camera_id": camera_id,
                    "is_online": is_online
                }
            )

        except Exception as e:
            logger.warning(
                f"Error handling WebSocket event: {e}",
                extra={
                    "event_type": "protect_websocket_event_error",
                    "controller_id": controller_id,
                    "error_type": type(e).__name__
                }
            )

    def _should_broadcast_camera_status(self, camera_id: str) -> bool:
        """
        Check if camera status change should be broadcast based on debounce (Story P2-2.4 AC12).

        Prevents broadcasting more than once per CAMERA_STATUS_DEBOUNCE_SECONDS (5 seconds)
        per camera to avoid UI thrashing from rapid status changes.

        Args:
            camera_id: Camera ID to check

        Returns:
            True if broadcast should proceed, False if debounced
        """
        last_broadcast = self._camera_status_broadcast_times.get(camera_id)
        if last_broadcast is None:
            return True

        elapsed = (datetime.now(timezone.utc) - last_broadcast).total_seconds()
        return elapsed >= CAMERA_STATUS_DEBOUNCE_SECONDS

    async def _broadcast_camera_status_change(
        self,
        controller_id: str,
        camera_id: str,
        is_online: bool
    ) -> None:
        """
        Broadcast camera status change to frontend via WebSocket (Story P2-2.4 AC6, AC7).

        Message format (AC7):
        {
            "type": "CAMERA_STATUS_CHANGED",
            "data": {
                "controller_id": "uuid",
                "camera_id": "protect_camera_id",
                "is_online": true/false
            },
            "timestamp": "ISO8601"  // Added by WebSocketManager
        }

        Args:
            controller_id: Controller UUID
            camera_id: Protect camera ID
            is_online: New online status
        """
        message = {
            "type": CAMERA_STATUS_CHANGED,
            "data": {
                "controller_id": controller_id,
                "camera_id": camera_id,
                "is_online": is_online
            }
        }

        websocket_manager = get_websocket_manager()
        await websocket_manager.broadcast(message)

        logger.debug(
            "Broadcast camera status change",
            extra={
                "event_type": "protect_camera_status_broadcast",
                "controller_id": controller_id,
                "camera_id": camera_id,
                "is_online": is_online
            }
        )

    def get_connection_status(self, controller_id: str) -> Dict[str, Any]:
        """
        Get current connection status for a controller.

        Args:
            controller_id: Controller UUID

        Returns:
            Dict with 'connected' boolean and 'has_task' boolean
        """
        return {
            "connected": controller_id in self._connections,
            "has_task": controller_id in self._listener_tasks and not self._listener_tasks[controller_id].done()
        }

    def get_all_connection_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get connection status for all tracked controllers (AC9).

        Returns:
            Dict mapping controller_id to status dict
        """
        statuses = {}
        for controller_id in set(list(self._connections.keys()) + list(self._listener_tasks.keys())):
            statuses[controller_id] = self.get_connection_status(controller_id)
        return statuses

    # =========================================================================
    # Camera Discovery Methods (Story P2-2.1)
    # =========================================================================

    async def discover_cameras(
        self,
        controller_id: str,
        force_refresh: bool = False
    ) -> CameraDiscoveryResult:
        """
        Discover cameras from a connected Protect controller (Story P2-2.1).

        Fetches all cameras from the controller, extracts metadata including
        doorbell identification and smart detection capabilities. Results are
        cached for 60 seconds to avoid repeated API calls.

        Args:
            controller_id: UUID of the controller to discover cameras from
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            CameraDiscoveryResult with discovered cameras and cache status

        Note:
            - Must complete within 10 seconds (NFR1/AC1)
            - Results are NOT auto-saved to cameras table (AC3)
            - Cache TTL is 60 seconds (AC4)
            - On failure, returns cached results if available (AC8)
        """
        logger.info(
            "Starting camera discovery",
            extra={
                "event_type": "protect_camera_discovery_start",
                "controller_id": controller_id,
                "force_refresh": force_refresh
            }
        )

        # Check cache first (AC4)
        if not force_refresh and controller_id in self._camera_cache:
            cached_cameras, cached_at = self._camera_cache[controller_id]
            cache_age = (datetime.now(timezone.utc) - cached_at).total_seconds()

            if cache_age < CAMERA_CACHE_TTL_SECONDS:
                logger.info(
                    "Returning cached camera discovery results",
                    extra={
                        "event_type": "protect_camera_discovery_cache_hit",
                        "controller_id": controller_id,
                        "cache_age_seconds": cache_age,
                        "camera_count": len(cached_cameras)
                    }
                )
                return CameraDiscoveryResult(
                    cameras=cached_cameras,
                    cached=True,
                    cached_at=cached_at
                )

        # Check if controller is connected
        client = self._connections.get(controller_id)
        if not client:
            logger.warning(
                "Controller not connected for camera discovery",
                extra={
                    "event_type": "protect_camera_discovery_not_connected",
                    "controller_id": controller_id
                }
            )

            # Return cached results if available (AC8)
            if controller_id in self._camera_cache:
                cached_cameras, cached_at = self._camera_cache[controller_id]
                logger.info(
                    "Returning stale cached results due to disconnected controller",
                    extra={
                        "event_type": "protect_camera_discovery_stale_cache",
                        "controller_id": controller_id,
                        "camera_count": len(cached_cameras)
                    }
                )
                return CameraDiscoveryResult(
                    cameras=cached_cameras,
                    cached=True,
                    cached_at=cached_at,
                    warning="Controller not connected - returning cached results"
                )

            # No cache available
            return CameraDiscoveryResult(
                cameras=[],
                cached=False,
                warning="Controller not connected and no cached results available"
            )

        # Fetch cameras from controller
        try:
            cameras = await self._fetch_cameras_from_client(client, controller_id)

            # Cache results (AC4)
            cached_at = datetime.now(timezone.utc)
            self._camera_cache[controller_id] = (cameras, cached_at)

            logger.info(
                "Camera discovery completed successfully",
                extra={
                    "event_type": "protect_camera_discovery_success",
                    "controller_id": controller_id,
                    "camera_count": len(cameras),
                    "doorbell_count": sum(1 for c in cameras if c.is_doorbell)
                }
            )

            return CameraDiscoveryResult(
                cameras=cameras,
                cached=False,
                cached_at=cached_at
            )

        except Exception as e:
            # Log discovery failure (AC9)
            logger.error(
                "Camera discovery failed",
                extra={
                    "event_type": "protect_camera_discovery_error",
                    "controller_id": controller_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )

            # Return cached results if available (AC8)
            if controller_id in self._camera_cache:
                cached_cameras, cached_at = self._camera_cache[controller_id]
                logger.info(
                    "Returning stale cached results due to discovery error",
                    extra={
                        "event_type": "protect_camera_discovery_fallback_cache",
                        "controller_id": controller_id,
                        "camera_count": len(cached_cameras)
                    }
                )
                return CameraDiscoveryResult(
                    cameras=cached_cameras,
                    cached=True,
                    cached_at=cached_at,
                    warning=f"Discovery failed ({type(e).__name__}) - returning cached results"
                )

            # No cache available
            return CameraDiscoveryResult(
                cameras=[],
                cached=False,
                warning=f"Discovery failed: {type(e).__name__}"
            )

    async def _fetch_cameras_from_client(
        self,
        client: ProtectApiClient,
        controller_id: str
    ) -> List[DiscoveredCamera]:
        """
        Fetch and transform cameras from a connected Protect client (AC1, AC2, AC10).

        Extracts camera properties and determines doorbell status from type/model.
        Must complete within 10 seconds timeout (AC1/NFR1).

        Args:
            client: Connected ProtectApiClient instance
            controller_id: Controller UUID for logging

        Returns:
            List of DiscoveredCamera instances
        """
        cameras: List[DiscoveredCamera] = []

        # Use client.bootstrap which should already be populated from connect()
        if not client.bootstrap or not client.bootstrap.cameras:
            logger.warning(
                "No cameras found in bootstrap data",
                extra={
                    "event_type": "protect_camera_fetch_empty",
                    "controller_id": controller_id
                }
            )
            return cameras

        # Process each camera from bootstrap (AC2)
        for camera in client.bootstrap.cameras.values():
            try:
                # Extract camera ID (AC2)
                protect_camera_id = str(camera.id)

                # Extract name (AC2)
                name = camera.name or f"Camera {protect_camera_id[:8]}"

                # Get model name (AC2)
                model = str(camera.type) if camera.type else "Unknown"

                # Determine if camera is online (AC2)
                is_online = camera.is_connected if hasattr(camera, 'is_connected') else True

                # Determine if doorbell (AC10)
                is_doorbell = self._is_doorbell_camera(camera)

                # Determine camera type based on doorbell status
                camera_type = "doorbell" if is_doorbell else "camera"

                # Extract smart detection capabilities (AC2)
                smart_detection_capabilities = self._get_smart_detection_capabilities(camera)

                discovered = DiscoveredCamera(
                    protect_camera_id=protect_camera_id,
                    name=name,
                    type=camera_type,
                    model=model,
                    is_online=is_online,
                    is_doorbell=is_doorbell,
                    smart_detection_capabilities=smart_detection_capabilities,
                    is_enabled_for_ai=False  # Will be set during cross-reference
                )

                cameras.append(discovered)

                logger.debug(
                    f"Discovered camera: {name}",
                    extra={
                        "event_type": "protect_camera_discovered",
                        "controller_id": controller_id,
                        "protect_camera_id": protect_camera_id,
                        "model": model,
                        "is_doorbell": is_doorbell,
                        "smart_detection": smart_detection_capabilities
                    }
                )

            except Exception as e:
                # Handle variations in camera capabilities gracefully (1.6)
                logger.warning(
                    f"Error processing camera: {e}",
                    extra={
                        "event_type": "protect_camera_process_error",
                        "controller_id": controller_id,
                        "error_type": type(e).__name__
                    }
                )
                continue

        return cameras

    def _is_doorbell_camera(self, camera: Any) -> bool:
        """
        Determine if a camera is a doorbell based on type and feature flags (AC10).

        Checks multiple indicators:
        - Camera type string contains "doorbell"
        - Camera model string contains "doorbell"
        - Feature flags indicate doorbell capability

        Args:
            camera: Camera object from uiprotect

        Returns:
            True if camera is identified as a doorbell
        """
        # Check camera type
        camera_type = str(getattr(camera, 'type', '')).lower()
        if 'doorbell' in camera_type:
            return True

        # Check model name
        model = str(getattr(camera, 'model', '')).lower()
        if 'doorbell' in model:
            return True

        # Check feature flags for doorbell capability
        feature_flags = getattr(camera, 'feature_flags', None)
        if feature_flags:
            # Check for has_chime or is_doorbell flag
            if getattr(feature_flags, 'has_chime', False):
                return True
            if getattr(feature_flags, 'is_doorbell', False):
                return True

        return False

    def _get_smart_detection_capabilities(self, camera: Any) -> List[str]:
        """
        Extract smart detection capabilities from camera (AC2).

        Looks for smart_detect_types or similar attributes that indicate
        what types of objects the camera can detect (person, vehicle, package, etc.)

        Args:
            camera: Camera object from uiprotect

        Returns:
            List of detection type strings (e.g., ["person", "vehicle", "package"])
        """
        capabilities: List[str] = []

        # Check for smart_detect_types attribute
        smart_detect_types = getattr(camera, 'smart_detect_types', None)
        if smart_detect_types:
            if isinstance(smart_detect_types, (list, tuple)):
                capabilities.extend([str(t).lower() for t in smart_detect_types])
            elif hasattr(smart_detect_types, '__iter__'):
                capabilities.extend([str(t).lower() for t in smart_detect_types])

        # Check feature flags for smart detection
        feature_flags = getattr(camera, 'feature_flags', None)
        if feature_flags:
            # Check individual detection capabilities
            if getattr(feature_flags, 'can_detect_person', False) and 'person' not in capabilities:
                capabilities.append('person')
            if getattr(feature_flags, 'can_detect_vehicle', False) and 'vehicle' not in capabilities:
                capabilities.append('vehicle')
            if getattr(feature_flags, 'has_smart_detect', False) and not capabilities:
                # Generic smart detection without specific types
                capabilities.append('motion')

        # Deduplicate while preserving order
        seen = set()
        unique_capabilities = []
        for cap in capabilities:
            if cap not in seen:
                seen.add(cap)
                unique_capabilities.append(cap)

        return unique_capabilities

    def clear_camera_cache(self, controller_id: Optional[str] = None) -> None:
        """
        Clear camera discovery cache.

        Args:
            controller_id: If provided, clear cache for specific controller.
                          If None, clear all cache entries.
        """
        if controller_id:
            if controller_id in self._camera_cache:
                del self._camera_cache[controller_id]
                logger.debug(
                    "Cleared camera cache for controller",
                    extra={
                        "event_type": "protect_camera_cache_cleared",
                        "controller_id": controller_id
                    }
                )
        else:
            self._camera_cache.clear()
            logger.debug(
                "Cleared all camera caches",
                extra={"event_type": "protect_camera_cache_cleared_all"}
            )

    # =========================================================================
    # Camera Snapshot Methods
    # =========================================================================

    async def get_camera_snapshot(
        self,
        controller_id: str,
        protect_camera_id: str,
        width: int = 640,
        height: Optional[int] = None
    ) -> Optional[bytes]:
        """
        Get a snapshot image from a Protect camera.

        Args:
            controller_id: UUID of the controller
            protect_camera_id: Native Protect camera ID
            width: Desired image width (default 640)
            height: Desired image height (None = auto based on aspect ratio)

        Returns:
            JPEG image bytes, or None if snapshot unavailable

        Raises:
            ValueError: If controller is not connected
        """
        client = self._connections.get(controller_id)
        if not client:
            logger.warning(
                "Cannot get snapshot - controller not connected",
                extra={
                    "event_type": "protect_snapshot_not_connected",
                    "controller_id": controller_id,
                    "camera_id": protect_camera_id
                }
            )
            raise ValueError(f"Controller {controller_id} is not connected")

        try:
            snapshot_bytes = await client.get_camera_snapshot(
                camera_id=protect_camera_id,
                width=width,
                height=height
            )

            if snapshot_bytes:
                logger.debug(
                    "Got camera snapshot",
                    extra={
                        "event_type": "protect_snapshot_success",
                        "controller_id": controller_id,
                        "camera_id": protect_camera_id,
                        "size_bytes": len(snapshot_bytes)
                    }
                )
            else:
                logger.warning(
                    "Snapshot returned empty",
                    extra={
                        "event_type": "protect_snapshot_empty",
                        "controller_id": controller_id,
                        "camera_id": protect_camera_id
                    }
                )

            return snapshot_bytes

        except Exception as e:
            logger.error(
                f"Failed to get camera snapshot: {e}",
                extra={
                    "event_type": "protect_snapshot_error",
                    "controller_id": controller_id,
                    "camera_id": protect_camera_id,
                    "error_type": type(e).__name__
                }
            )
            return None


# Singleton instance for the service
_protect_service: Optional[ProtectService] = None


def get_protect_service() -> ProtectService:
    """Get the singleton ProtectService instance."""
    global _protect_service
    if _protect_service is None:
        _protect_service = ProtectService()
    return _protect_service
