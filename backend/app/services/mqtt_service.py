"""
MQTT Service for Home Assistant Integration (Story P4-2.1)

Provides MQTT client management with:
- Connection to MQTT brokers with username/password authentication
- Auto-reconnect with exponential backoff (1s → 60s max)
- Event publishing to camera-specific topics
- Connection status tracking and metrics
- Graceful shutdown

Uses paho-mqtt 2.0+ with CallbackAPIVersion.VERSION2.
"""
import asyncio
import json
import logging
import ssl
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, Any, Dict, Callable

import paho.mqtt.client as mqtt

from app.core.database import SessionLocal
from app.models.mqtt_config import MQTTConfig
from app.core.metrics import (
    update_mqtt_connection_status,
    record_mqtt_message_published,
    record_mqtt_publish_error,
    record_mqtt_reconnect_attempt
)

logger = logging.getLogger(__name__)

# Reconnect backoff delays in seconds (AC2: exponential backoff 1s → 60s max)
RECONNECT_DELAYS = [1, 2, 4, 8, 16, 32, 60]

# Connection timeout in seconds
CONNECTION_TIMEOUT = 10.0

# Keep-alive interval in seconds
KEEPALIVE_SECONDS = 60


class MQTTService:
    """
    MQTT connection manager with auto-reconnect (Story P4-2.1).

    Handles connection lifecycle, message publishing, and status tracking
    for Home Assistant MQTT integration.

    Features:
    - Connect to MQTT brokers with optional TLS and authentication
    - Auto-reconnect with exponential backoff on connection loss
    - Publish messages with configurable QoS
    - Track connection status and message counts
    - Thread-safe operations

    Attributes:
        _client: Paho MQTT client instance
        _config: Current MQTT configuration
        _connected: Connection status flag
        _should_reconnect: Whether auto-reconnect is enabled
        _reconnect_attempt: Current reconnect attempt number
        _loop: Event loop for async operations
        _lock: Thread lock for status updates
    """

    def __init__(self):
        """Initialize MQTT service without connecting."""
        self._client: Optional[mqtt.Client] = None
        self._config: Optional[MQTTConfig] = None
        self._connected = False
        self._should_reconnect = True
        self._reconnect_attempt = 0
        self._reconnect_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._messages_published = 0
        self._last_error: Optional[str] = None
        self._last_connected_at: Optional[datetime] = None
        # Callbacks for connection state changes
        self._on_connect_callback: Optional[Callable[[], None]] = None
        self._on_disconnect_callback: Optional[Callable[[str], None]] = None

    @property
    def is_connected(self) -> bool:
        """Return current connection status."""
        return self._connected

    @property
    def messages_published(self) -> int:
        """Return total messages published in this session."""
        return self._messages_published

    @property
    def last_error(self) -> Optional[str]:
        """Return last connection error message."""
        return self._last_error

    @property
    def last_connected_at(self) -> Optional[datetime]:
        """Return timestamp of last successful connection."""
        return self._last_connected_at

    def set_on_connect_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for successful connections (e.g., to publish discovery)."""
        self._on_connect_callback = callback

    def set_on_disconnect_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for disconnections (receives error message)."""
        self._on_disconnect_callback = callback

    async def initialize(self) -> bool:
        """
        Load configuration from database and connect if enabled.

        Returns:
            True if MQTT is enabled and connection attempted, False otherwise.

        Called during app startup to restore MQTT connections.
        """
        self._loop = asyncio.get_event_loop()

        # Load config from database
        with SessionLocal() as db:
            config = db.query(MQTTConfig).first()
            if not config:
                logger.info("No MQTT configuration found, skipping initialization")
                return False

            if not config.enabled:
                logger.info("MQTT integration is disabled")
                return False

            self._config = config

        # Attempt connection
        logger.info(
            "Initializing MQTT connection",
            extra={
                "event_type": "mqtt_init_start",
                "broker": f"{self._config.broker_host}:{self._config.broker_port}"
            }
        )

        try:
            await self.connect()
            return True
        except Exception as e:
            logger.warning(
                f"MQTT initialization failed, will retry: {e}",
                extra={"event_type": "mqtt_init_failed", "error": str(e)}
            )
            # Start reconnect loop
            self._start_reconnect_loop()
            return False

    async def connect(self) -> bool:
        """
        Establish connection to MQTT broker.

        Returns:
            True if connection successful, False otherwise.

        Raises:
            ValueError: If no configuration is set.
            ConnectionError: If connection fails.
        """
        if not self._config:
            raise ValueError("MQTT configuration not set")

        if self._connected:
            logger.debug("MQTT already connected")
            return True

        # Create new client with unique ID
        client_id = f"liveobject-{uuid.uuid4().hex[:8]}"
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311
        )

        # Set up callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_publish = self._on_publish

        # Configure authentication if provided
        if self._config.username:
            password = self._config.get_decrypted_password()
            self._client.username_pw_set(self._config.username, password)
            logger.debug("MQTT authentication configured")

        # Configure TLS if enabled
        if self._config.use_tls:
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            logger.debug("MQTT TLS enabled")

        # Configure Last Will and Testament (LWT) for availability (Story P4-2.2, AC7)
        # This message is sent by the broker if the client disconnects unexpectedly
        status_topic = f"{self._config.topic_prefix}/status"
        self._client.will_set(
            topic=status_topic,
            payload="offline",
            qos=1,
            retain=True
        )
        logger.debug(f"MQTT LWT configured on topic {status_topic}")

        # Start network loop in background thread
        self._client.loop_start()

        try:
            # Connect asynchronously
            self._client.connect_async(
                self._config.broker_host,
                self._config.broker_port,
                keepalive=KEEPALIVE_SECONDS
            )

            # Wait for connection with timeout
            connected = await self._wait_for_connection(CONNECTION_TIMEOUT)

            if connected:
                self._reconnect_attempt = 0
                logger.info(
                    "MQTT connected successfully",
                    extra={
                        "event_type": "mqtt_connected",
                        "broker": f"{self._config.broker_host}:{self._config.broker_port}",
                        "client_id": client_id
                    }
                )
                return True
            else:
                raise ConnectionError("Connection timeout")

        except Exception as e:
            self._last_error = str(e)
            logger.warning(
                f"MQTT connection failed: {e}",
                extra={
                    "event_type": "mqtt_connection_failed",
                    "broker": f"{self._config.broker_host}:{self._config.broker_port}",
                    "error": str(e)
                }
            )
            self._cleanup_client()
            raise

    async def _wait_for_connection(self, timeout: float) -> bool:
        """Wait for connection to establish with timeout."""
        start = asyncio.get_event_loop().time()
        while not self._connected:
            if asyncio.get_event_loop().time() - start > timeout:
                return False
            await asyncio.sleep(0.1)
        return True

    def _cleanup_client(self) -> None:
        """Clean up client resources."""
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    async def disconnect(self) -> None:
        """
        Gracefully disconnect from MQTT broker.

        Stops auto-reconnect and closes connection cleanly.
        """
        self._should_reconnect = False

        # Cancel reconnect task if running
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        if self._client and self._connected:
            logger.info(
                "Disconnecting MQTT",
                extra={"event_type": "mqtt_disconnecting"}
            )
            self._client.disconnect()
            self._client.loop_stop()
            self._connected = False

        self._client = None
        logger.info("MQTT disconnected", extra={"event_type": "mqtt_disconnected"})

    async def publish(
        self,
        topic: str,
        payload: dict,
        qos: Optional[int] = None,
        retain: Optional[bool] = None
    ) -> bool:
        """
        Publish message to MQTT topic.

        Args:
            topic: MQTT topic to publish to
            payload: Dictionary to serialize as JSON
            qos: Quality of Service level (0, 1, or 2). Defaults to config value.
            retain: Whether to retain message. Defaults to config value.

        Returns:
            True if publish successful, False otherwise.

        Note:
            This method is non-blocking and returns quickly.
            Use QoS 1 or 2 for guaranteed delivery.
        """
        if not self._connected or not self._client:
            logger.warning(
                "Cannot publish: MQTT not connected",
                extra={"event_type": "mqtt_publish_skipped", "topic": topic}
            )
            return False

        # Use config defaults if not specified
        if qos is None:
            qos = self._config.qos if self._config else 1
        if retain is None:
            retain = self._config.retain_messages if self._config else True

        try:
            # Serialize payload to JSON
            message = json.dumps(payload, default=self._json_serializer)

            # Publish message
            result = self._client.publish(topic, message, qos=qos, retain=retain)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                with self._lock:
                    self._messages_published += 1

                # Update Prometheus metrics
                record_mqtt_message_published()

                logger.debug(
                    f"MQTT message published",
                    extra={
                        "event_type": "mqtt_published",
                        "topic": topic,
                        "qos": qos,
                        "retain": retain,
                        "message_id": result.mid
                    }
                )
                return True
            else:
                # Update Prometheus metrics
                record_mqtt_publish_error()

                logger.warning(
                    f"MQTT publish failed: rc={result.rc}",
                    extra={
                        "event_type": "mqtt_publish_failed",
                        "topic": topic,
                        "error_code": result.rc
                    }
                )
                return False

        except Exception as e:
            # Update Prometheus metrics
            record_mqtt_publish_error()

            logger.warning(
                f"MQTT publish error: {e}",
                extra={
                    "event_type": "mqtt_publish_error",
                    "topic": topic,
                    "error": str(e)
                }
            )
            return False

    @staticmethod
    def _json_serializer(obj: Any) -> str:
        """Custom JSON serializer for datetime and UUID objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: dict,
        reason_code: mqtt.ReasonCode,
        properties: Any
    ) -> None:
        """
        Callback when connection is established.

        Args:
            client: MQTT client instance
            userdata: User data (unused)
            flags: Connection flags
            reason_code: Connection result code
            properties: MQTT 5.0 properties (unused)
        """
        if reason_code == mqtt.CONNACK_ACCEPTED or reason_code.value == 0:
            with self._lock:
                self._connected = True
                self._last_connected_at = datetime.now(timezone.utc)
                self._last_error = None
                self._reconnect_attempt = 0

            # Update Prometheus metrics
            update_mqtt_connection_status(True)

            logger.info(
                "MQTT connection established",
                extra={"event_type": "mqtt_on_connect", "flags": str(flags)}
            )

            # Invoke callback (e.g., to publish discovery messages)
            if self._on_connect_callback:
                try:
                    self._on_connect_callback()
                except Exception as e:
                    logger.error(f"MQTT on_connect callback failed: {e}")

            # Update database status
            self._update_db_status(connected=True)
        else:
            error_msg = f"Connection refused: {reason_code}"
            with self._lock:
                self._connected = False
                self._last_error = error_msg

            # Update Prometheus metrics
            update_mqtt_connection_status(False)

            logger.warning(
                f"MQTT connection refused",
                extra={
                    "event_type": "mqtt_connection_refused",
                    "reason_code": str(reason_code)
                }
            )

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: Any
    ) -> None:
        """
        Callback when disconnected from broker.

        Args:
            client: MQTT client instance
            userdata: User data (unused)
            disconnect_flags: Disconnect flags
            reason_code: Disconnect reason code
            properties: MQTT 5.0 properties (unused)
        """
        was_connected = self._connected

        with self._lock:
            self._connected = False
            if reason_code != mqtt.MQTT_ERR_SUCCESS and reason_code.value != 0:
                self._last_error = f"Disconnected: {reason_code}"

        # Update Prometheus metrics
        update_mqtt_connection_status(False)

        logger.info(
            f"MQTT disconnected",
            extra={
                "event_type": "mqtt_on_disconnect",
                "reason_code": str(reason_code),
                "was_connected": was_connected
            }
        )

        # Invoke callback
        if self._on_disconnect_callback:
            try:
                self._on_disconnect_callback(str(reason_code))
            except Exception as e:
                logger.error(f"MQTT on_disconnect callback failed: {e}")

        # Update database status
        self._update_db_status(connected=False, error=self._last_error)

        # Start reconnect loop if enabled and was previously connected
        if was_connected and self._should_reconnect:
            self._start_reconnect_loop()

    def _on_publish(
        self,
        client: mqtt.Client,
        userdata: Any,
        mid: int,
        reason_code: mqtt.ReasonCode,
        properties: Any
    ) -> None:
        """
        Callback when message is published (for QoS 1/2).

        Args:
            client: MQTT client instance
            userdata: User data (unused)
            mid: Message ID
            reason_code: Publish result code
            properties: MQTT 5.0 properties (unused)
        """
        logger.debug(
            f"MQTT message acknowledged",
            extra={
                "event_type": "mqtt_on_publish",
                "message_id": mid,
                "reason_code": str(reason_code)
            }
        )

    def _start_reconnect_loop(self) -> None:
        """Start background reconnect loop."""
        if self._loop and not self._reconnect_task:
            self._reconnect_task = self._loop.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """
        Background reconnect loop with exponential backoff.

        Attempts to reconnect until successful or stopped.
        Backoff: 1s, 2s, 4s, 8s, 16s, 32s, 60s (max)
        """
        while self._should_reconnect and not self._connected:
            delay = RECONNECT_DELAYS[min(self._reconnect_attempt, len(RECONNECT_DELAYS) - 1)]

            logger.info(
                f"MQTT reconnect attempt {self._reconnect_attempt + 1} in {delay}s",
                extra={
                    "event_type": "mqtt_reconnect_scheduled",
                    "attempt": self._reconnect_attempt + 1,
                    "delay_seconds": delay
                }
            )

            await asyncio.sleep(delay)

            if not self._should_reconnect:
                break

            self._reconnect_attempt += 1

            # Update Prometheus metrics
            record_mqtt_reconnect_attempt()

            try:
                # Reload config in case it changed
                with SessionLocal() as db:
                    config = db.query(MQTTConfig).first()
                    if config and config.enabled:
                        self._config = config
                    else:
                        logger.info("MQTT disabled during reconnect, stopping")
                        break

                await self.connect()
                logger.info(
                    "MQTT reconnected successfully",
                    extra={
                        "event_type": "mqtt_reconnected",
                        "attempts": self._reconnect_attempt
                    }
                )
                break

            except Exception as e:
                logger.warning(
                    f"MQTT reconnect attempt {self._reconnect_attempt} failed: {e}",
                    extra={
                        "event_type": "mqtt_reconnect_failed",
                        "attempt": self._reconnect_attempt,
                        "error": str(e)
                    }
                )

        self._reconnect_task = None

    def _update_db_status(
        self,
        connected: bool,
        error: Optional[str] = None
    ) -> None:
        """Update connection status in database."""
        try:
            with SessionLocal() as db:
                config = db.query(MQTTConfig).first()
                if config:
                    config.is_connected = connected
                    if connected:
                        config.last_connected_at = datetime.now(timezone.utc)
                    if error:
                        config.last_error = error
                    config.messages_published = self._messages_published
                    db.commit()
        except Exception as e:
            logger.error(f"Failed to update MQTT status in database: {e}")

    async def update_config(self, config: MQTTConfig) -> bool:
        """
        Update configuration and reconnect if needed.

        Args:
            config: New MQTT configuration

        Returns:
            True if reconnect successful or not needed, False otherwise.
        """
        old_enabled = self._config.enabled if self._config else False
        self._config = config

        # Disconnect existing connection
        if self._connected:
            await self.disconnect()
            self._should_reconnect = True  # Reset for new connection

        # Connect with new config if enabled
        if config.enabled:
            try:
                await self.connect()
                return True
            except Exception as e:
                logger.warning(f"Failed to connect with new config: {e}")
                self._start_reconnect_loop()
                return False

        return True

    async def test_connection(
        self,
        broker_host: str,
        broker_port: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = False
    ) -> Dict[str, Any]:
        """
        Test connection to MQTT broker without persisting config.

        Args:
            broker_host: MQTT broker hostname or IP
            broker_port: MQTT broker port
            username: Optional authentication username
            password: Optional authentication password (plain text)
            use_tls: Whether to use TLS

        Returns:
            Dict with 'success' boolean and 'message' string.
        """
        client_id = f"liveobject-test-{uuid.uuid4().hex[:8]}"
        test_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311
        )

        connected_event = asyncio.Event()
        connection_error: Optional[str] = None

        def on_connect(client, userdata, flags, reason_code, properties):
            nonlocal connection_error
            if reason_code == mqtt.CONNACK_ACCEPTED or reason_code.value == 0:
                connected_event.set()
            else:
                connection_error = f"Connection refused: {reason_code}"
                connected_event.set()

        test_client.on_connect = on_connect

        # Configure authentication
        if username:
            test_client.username_pw_set(username, password)

        # Configure TLS
        if use_tls:
            test_client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

        try:
            test_client.loop_start()
            test_client.connect_async(broker_host, broker_port, keepalive=KEEPALIVE_SECONDS)

            # Wait for connection with timeout
            try:
                await asyncio.wait_for(connected_event.wait(), timeout=CONNECTION_TIMEOUT)
            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "message": f"Connection timeout after {CONNECTION_TIMEOUT}s"
                }

            if connection_error:
                return {"success": False, "message": connection_error}

            return {
                "success": True,
                "message": f"Connected to {broker_host}:{broker_port}"
            }

        except Exception as e:
            return {"success": False, "message": str(e)}

        finally:
            try:
                test_client.loop_stop()
                test_client.disconnect()
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        """
        Get current connection status.

        Returns:
            Dict with connection status, broker info, and statistics.
        """
        return {
            "connected": self._connected,
            "broker": f"{self._config.broker_host}:{self._config.broker_port}" if self._config else None,
            "last_connected_at": self._last_connected_at.isoformat() if self._last_connected_at else None,
            "messages_published": self._messages_published,
            "last_error": self._last_error,
            "reconnect_attempt": self._reconnect_attempt if not self._connected else 0
        }

    def get_event_topic(self, camera_id: str) -> str:
        """
        Get MQTT topic for camera events (Story P4-2.3).

        Args:
            camera_id: Camera UUID string

        Returns:
            Topic string in format: {topic_prefix}/camera/{camera_id}/event

        Example:
            >>> service.get_event_topic("abc-123")
            "liveobject/camera/abc-123/event"
        """
        import re

        # Get topic prefix from config, default to "liveobject"
        prefix = self._config.topic_prefix if self._config else "liveobject"

        # Sanitize camera_id - keep only alphanumeric, hyphens, underscores
        sanitized_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(camera_id))

        return f"{prefix}/camera/{sanitized_id}/event"

    def get_api_base_url(self) -> str:
        """
        Get API base URL for thumbnail URLs in MQTT payloads (Story P4-2.3).

        Checks in order:
        1. Environment variable API_BASE_URL
        2. Default to http://localhost:8000

        Returns:
            Base URL string without trailing slash
        """
        import os
        return os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")

    # ===========================================================================
    # Camera Status Sensor Methods (Story P4-2.5)
    # ===========================================================================

    def get_status_topic(self, camera_id: str) -> str:
        """
        Get MQTT topic for camera status (Story P4-2.5, AC6).

        Args:
            camera_id: Camera UUID string

        Returns:
            Topic string in format: {topic_prefix}/camera/{camera_id}/status
        """
        import re
        prefix = self._config.topic_prefix if self._config else "liveobject"
        sanitized_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(camera_id))
        return f"{prefix}/camera/{sanitized_id}/status"

    def get_last_event_topic(self, camera_id: str) -> str:
        """
        Get MQTT topic for last event timestamp (Story P4-2.5, AC2).

        Args:
            camera_id: Camera UUID string

        Returns:
            Topic string in format: {topic_prefix}/camera/{camera_id}/last_event
        """
        import re
        prefix = self._config.topic_prefix if self._config else "liveobject"
        sanitized_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(camera_id))
        return f"{prefix}/camera/{sanitized_id}/last_event"

    def get_counts_topic(self, camera_id: str) -> str:
        """
        Get MQTT topic for event counts (Story P4-2.5, AC3).

        Args:
            camera_id: Camera UUID string

        Returns:
            Topic string in format: {topic_prefix}/camera/{camera_id}/counts
        """
        import re
        prefix = self._config.topic_prefix if self._config else "liveobject"
        sanitized_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(camera_id))
        return f"{prefix}/camera/{sanitized_id}/counts"

    def get_activity_topic(self, camera_id: str) -> str:
        """
        Get MQTT topic for activity binary sensor (Story P4-2.5, AC4).

        Args:
            camera_id: Camera UUID string

        Returns:
            Topic string in format: {topic_prefix}/camera/{camera_id}/activity
        """
        import re
        prefix = self._config.topic_prefix if self._config else "liveobject"
        sanitized_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(camera_id))
        return f"{prefix}/camera/{sanitized_id}/activity"

    async def publish_camera_status(
        self,
        camera_id: str,
        camera_name: str,
        status: str,
        source_type: str
    ) -> bool:
        """
        Publish camera online/offline/unavailable status to MQTT (AC1, AC9).

        Args:
            camera_id: Camera UUID
            camera_name: Human-readable camera name
            status: Status string ('online', 'offline', 'unavailable')
            source_type: Camera type ('rtsp', 'usb', 'protect')

        Returns:
            True if published successfully, False otherwise.
        """
        from app.schemas.mqtt import CameraStatusPayload

        if not self._connected or not self._client:
            logger.debug(f"Cannot publish camera status: MQTT not connected")
            return False

        # Validate and normalize status
        valid_statuses = {"online", "offline", "unavailable"}
        normalized_status = status.lower()
        if normalized_status not in valid_statuses:
            # Map common status values to valid ones
            status_map = {
                "connected": "online",
                "starting": "online",
                "disconnected": "offline",
                "error": "unavailable",
                "stopped": "unavailable"
            }
            normalized_status = status_map.get(normalized_status, "unavailable")

        # Build payload
        payload = CameraStatusPayload(
            camera_id=camera_id,
            camera_name=camera_name,
            status=normalized_status,
            source_type=source_type,
            last_updated=datetime.now(timezone.utc)
        )

        topic = self.get_status_topic(camera_id)

        # Publish with retain=True so HA gets status on connect
        success = await self.publish(
            topic=topic,
            payload=payload.model_dump(mode='json'),
            qos=1,
            retain=True
        )

        if success:
            logger.debug(
                f"Published camera status to MQTT",
                extra={
                    "event_type": "mqtt_camera_status_published",
                    "camera_id": camera_id,
                    "status": normalized_status,
                    "topic": topic
                }
            )

        return success

    async def publish_last_event_timestamp(
        self,
        camera_id: str,
        camera_name: str,
        event_id: str,
        timestamp: datetime,
        description: str,
        smart_detection_type: Optional[str] = None
    ) -> bool:
        """
        Publish last event timestamp to MQTT (AC2, AC8).

        Args:
            camera_id: Camera UUID
            camera_name: Human-readable camera name
            event_id: UUID of the event
            timestamp: When the event occurred
            description: Event description (will be truncated to 100 chars)
            smart_detection_type: Detection type if available

        Returns:
            True if published successfully, False otherwise.
        """
        from app.schemas.mqtt import LastEventPayload

        if not self._connected or not self._client:
            logger.debug(f"Cannot publish last event: MQTT not connected")
            return False

        # Truncate description to 100 chars
        description_snippet = description[:100] if description else ""

        payload = LastEventPayload(
            camera_id=camera_id,
            camera_name=camera_name,
            event_id=event_id,
            timestamp=timestamp,
            description_snippet=description_snippet,
            smart_detection_type=smart_detection_type
        )

        topic = self.get_last_event_topic(camera_id)

        success = await self.publish(
            topic=topic,
            payload=payload.model_dump(mode='json'),
            qos=1,
            retain=True
        )

        if success:
            logger.debug(
                f"Published last event timestamp to MQTT",
                extra={
                    "event_type": "mqtt_last_event_published",
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "topic": topic
                }
            )

        return success

    async def publish_event_counts(
        self,
        camera_id: str,
        camera_name: str,
        events_today: int,
        events_this_week: int
    ) -> bool:
        """
        Publish event counts to MQTT (AC3).

        Args:
            camera_id: Camera UUID
            camera_name: Human-readable camera name
            events_today: Number of events since midnight
            events_this_week: Number of events since Monday 00:00

        Returns:
            True if published successfully, False otherwise.
        """
        from app.schemas.mqtt import CameraCountsPayload

        if not self._connected or not self._client:
            logger.debug(f"Cannot publish event counts: MQTT not connected")
            return False

        payload = CameraCountsPayload(
            camera_id=camera_id,
            camera_name=camera_name,
            events_today=events_today,
            events_this_week=events_this_week,
            last_updated=datetime.now(timezone.utc)
        )

        topic = self.get_counts_topic(camera_id)

        success = await self.publish(
            topic=topic,
            payload=payload.model_dump(mode='json'),
            qos=1,
            retain=True
        )

        if success:
            logger.debug(
                f"Published event counts to MQTT",
                extra={
                    "event_type": "mqtt_event_counts_published",
                    "camera_id": camera_id,
                    "events_today": events_today,
                    "events_this_week": events_this_week,
                    "topic": topic
                }
            )

        return success

    async def publish_activity_state(
        self,
        camera_id: str,
        state: str,
        last_event_at: Optional[datetime] = None
    ) -> bool:
        """
        Publish activity binary sensor state to MQTT (AC4).

        Args:
            camera_id: Camera UUID
            state: Activity state ('ON' or 'OFF')
            last_event_at: Timestamp of most recent event

        Returns:
            True if published successfully, False otherwise.
        """
        from app.schemas.mqtt import CameraActivityPayload

        if not self._connected or not self._client:
            logger.debug(f"Cannot publish activity state: MQTT not connected")
            return False

        # Normalize state
        normalized_state = "ON" if state.upper() == "ON" else "OFF"

        payload = CameraActivityPayload(
            camera_id=camera_id,
            state=normalized_state,
            last_event_at=last_event_at
        )

        topic = self.get_activity_topic(camera_id)

        success = await self.publish(
            topic=topic,
            payload=payload.model_dump(mode='json'),
            qos=1,
            retain=True
        )

        if success:
            logger.debug(
                f"Published activity state to MQTT",
                extra={
                    "event_type": "mqtt_activity_published",
                    "camera_id": camera_id,
                    "state": normalized_state,
                    "topic": topic
                }
            )

        return success


# Global singleton instance
_mqtt_service: Optional[MQTTService] = None


def get_mqtt_service() -> MQTTService:
    """
    Get the global MQTT service instance.

    Returns:
        MQTTService singleton instance.
    """
    global _mqtt_service
    if _mqtt_service is None:
        _mqtt_service = MQTTService()
    return _mqtt_service


async def initialize_mqtt_service() -> None:
    """Initialize MQTT service on app startup."""
    service = get_mqtt_service()
    await service.initialize()


async def shutdown_mqtt_service() -> None:
    """Shutdown MQTT service on app shutdown."""
    global _mqtt_service
    if _mqtt_service:
        await _mqtt_service.disconnect()
        _mqtt_service = None


def serialize_event_for_mqtt(
    event: "Event",
    camera_name: str,
    api_base_url: str = "http://localhost:8000"
) -> Dict[str, Any]:
    """
    Serialize an Event model to MQTT-friendly JSON payload (AC3).

    Creates a dictionary with all relevant event information formatted
    for Home Assistant consumption.

    Args:
        event: Event model instance
        camera_name: Human-readable camera name
        api_base_url: Base URL for thumbnail links

    Returns:
        Dictionary ready for JSON serialization with:
        - event_id: UUID string
        - camera_id: Camera UUID
        - camera_name: Human-readable name
        - description: AI-generated event description
        - objects_detected: List of detected objects
        - confidence: 0-100 confidence score
        - ai_confidence: AI self-reported confidence (if available)
        - source_type: 'rtsp', 'usb', or 'protect'
        - smart_detection_type: Protect detection type (if available)
        - is_doorbell_ring: Boolean for doorbell events
        - timestamp: ISO 8601 formatted timestamp
        - thumbnail_url: URL to fetch event thumbnail
        - provider_used: AI provider that generated description
        - analysis_mode: Analysis mode used (single_frame, multi_frame, video_native)

    Example:
        >>> from app.models.event import Event
        >>> event = db.query(Event).first()
        >>> payload = serialize_event_for_mqtt(event, "Front Door")
        >>> mqtt_service.publish("liveobject/camera/123/event", payload)
    """
    import json as _json

    # Parse objects_detected from JSON string if needed
    objects = []
    if event.objects_detected:
        try:
            objects = _json.loads(event.objects_detected) if isinstance(event.objects_detected, str) else event.objects_detected
        except (ValueError, TypeError):
            objects = []

    # Build thumbnail URL
    thumbnail_url = f"{api_base_url}/api/v1/events/{event.id}/thumbnail"

    payload = {
        "event_id": str(event.id),
        "camera_id": str(event.camera_id),
        "camera_name": camera_name,
        "description": event.description or "",
        "objects_detected": objects,
        "confidence": event.confidence or 0,
        "source_type": event.source_type or "rtsp",
        "timestamp": event.timestamp.isoformat() if event.timestamp else datetime.now(timezone.utc).isoformat(),
        "thumbnail_url": thumbnail_url,
    }

    # Add optional fields if present
    if event.ai_confidence is not None:
        payload["ai_confidence"] = event.ai_confidence

    if event.smart_detection_type:
        payload["smart_detection_type"] = event.smart_detection_type

    if event.is_doorbell_ring:
        payload["is_doorbell_ring"] = True

    if event.provider_used:
        payload["provider_used"] = event.provider_used

    if event.analysis_mode:
        payload["analysis_mode"] = event.analysis_mode

    if event.low_confidence:
        payload["low_confidence"] = True

    if event.correlation_group_id:
        payload["correlation_group_id"] = event.correlation_group_id

    return payload


# Type hint import for Event
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.event import Event
