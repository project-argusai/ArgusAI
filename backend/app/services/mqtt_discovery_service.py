"""
MQTT Discovery Service for Home Assistant Integration (Story P4-2.2)

Provides Home Assistant MQTT Discovery protocol support:
- Generate discovery configuration payloads for cameras
- Publish discovery configs on MQTT connect
- Remove sensors when cameras are deleted/disabled
- Track discovery state for republishing on reconnect

Uses Home Assistant MQTT Discovery protocol:
https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List

from app.services.mqtt_service import MQTTService, get_mqtt_service
from app.core.database import SessionLocal
from app.models.mqtt_config import MQTTConfig
from app.models.camera import Camera
from app.services.mqtt_status_service import publish_all_camera_statuses

logger = logging.getLogger(__name__)

# Application version for device info
APP_VERSION = "4.0.0"


class MQTTDiscoveryService:
    """
    Home Assistant MQTT Discovery service (Story P4-2.2).

    Manages automatic sensor registration in Home Assistant via MQTT Discovery.
    Creates sensor entities for each camera that publish AI event descriptions.

    Features:
    - Generate HA-compatible discovery payloads
    - Publish discovery on MQTT connect
    - Remove sensors on camera delete/disable
    - Support discovery enable/disable toggle

    Discovery Topic Format:
        {discovery_prefix}/sensor/liveobject_{camera_id}_event/config

    Sensor Payload Structure:
        - name: "{camera_name} AI Events"
        - unique_id: "liveobject_{camera_id}_event"
        - state_topic: "{topic_prefix}/camera/{camera_id}/event"
        - availability_topic: "{topic_prefix}/status"
        - device grouping with identifiers

    Attributes:
        _mqtt_service: Reference to MQTT service for publishing
        _published_cameras: Set of camera IDs with active discovery
    """

    def __init__(self, mqtt_service: Optional[MQTTService] = None):
        """
        Initialize discovery service.

        Args:
            mqtt_service: MQTT service instance (uses singleton if not provided)
        """
        self._mqtt_service = mqtt_service
        self._published_cameras: set = set()
        self._main_event_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_main_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Store reference to main event loop for cross-thread scheduling.

        Called during initialization to enable proper async scheduling from
        MQTT callbacks which run in a separate thread.

        Args:
            loop: The main asyncio event loop (typically from FastAPI)
        """
        self._main_event_loop = loop
        logger.debug(
            "Main event loop stored for MQTT discovery service",
            extra={"event_type": "mqtt_discovery_loop_set"}
        )

    @property
    def mqtt_service(self) -> MQTTService:
        """Get MQTT service instance (lazy load singleton if needed)."""
        if self._mqtt_service is None:
            self._mqtt_service = get_mqtt_service()
        return self._mqtt_service

    def generate_sensor_config(
        self,
        camera: Camera,
        topic_prefix: str = "liveobject"
    ) -> Dict[str, Any]:
        """
        Generate Home Assistant discovery payload for a camera sensor (AC1, AC3).

        Creates a sensor configuration that will appear in Home Assistant
        with proper device grouping and state/attributes topics.

        Args:
            camera: Camera model instance
            topic_prefix: MQTT topic prefix (default "liveobject")

        Returns:
            Dictionary ready for JSON serialization to discovery topic.

        Example:
            >>> config = service.generate_sensor_config(camera)
            >>> mqtt.publish(discovery_topic, config)
        """
        camera_id = str(camera.id)

        # Build unique identifiers
        sensor_unique_id = f"liveobject_{camera_id}_event"
        device_identifier = f"liveobject_{camera_id}"

        # Build topics
        state_topic = f"{topic_prefix}/camera/{camera_id}/event"
        availability_topic = f"{topic_prefix}/status"

        # Determine camera type for model field
        camera_type = camera.source_type or camera.type
        if camera.is_doorbell:
            model_name = "AI Classifier - Doorbell"
        elif camera_type == "protect":
            model_name = "AI Classifier - Protect"
        elif camera_type == "usb":
            model_name = "AI Classifier - USB"
        else:
            model_name = "AI Classifier - RTSP"

        # Build discovery payload per HA MQTT Discovery spec
        config = {
            # Entity identification
            "name": f"{camera.name} AI Events",
            "unique_id": sensor_unique_id,
            "object_id": sensor_unique_id,

            # State and attributes
            "state_topic": state_topic,
            "value_template": "{{ value_json.description[:255] if value_json.description else 'No event' }}",
            "json_attributes_topic": state_topic,

            # Availability (AC7)
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",

            # Icon based on camera type
            "icon": "mdi:doorbell-video" if camera.is_doorbell else "mdi:cctv",

            # Device grouping (AC3)
            "device": {
                "identifiers": [device_identifier],
                "name": camera.name,
                "manufacturer": "ArgusAI",
                "model": model_name,
                "sw_version": APP_VERSION,
            }
        }

        return config

    def generate_status_sensor_config(
        self,
        camera: Camera,
        topic_prefix: str = "liveobject"
    ) -> Dict[str, Any]:
        """
        Generate Home Assistant discovery payload for camera status sensor (P4-2.5, AC1, AC9).

        Args:
            camera: Camera model instance
            topic_prefix: MQTT topic prefix

        Returns:
            Dictionary ready for JSON serialization to discovery topic.
        """
        camera_id = str(camera.id)
        device_identifier = f"liveobject_{camera_id}"

        # Build topics
        state_topic = f"{topic_prefix}/camera/{camera_id}/status"
        availability_topic = f"{topic_prefix}/status"

        return {
            "name": f"{camera.name} Status",
            "unique_id": f"liveobject_{camera_id}_status",
            "object_id": f"liveobject_{camera_id}_status",
            "state_topic": state_topic,
            "value_template": "{{ value_json.status }}",
            "json_attributes_topic": state_topic,
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:camera",
            "device": {
                "identifiers": [device_identifier],
                "name": camera.name,
                "manufacturer": "ArgusAI",
                "model": "AI Classifier",
                "sw_version": APP_VERSION,
            }
        }

    def generate_last_event_sensor_config(
        self,
        camera: Camera,
        topic_prefix: str = "liveobject"
    ) -> Dict[str, Any]:
        """
        Generate Home Assistant discovery payload for last event timestamp sensor (P4-2.5, AC2).

        Args:
            camera: Camera model instance
            topic_prefix: MQTT topic prefix

        Returns:
            Dictionary ready for JSON serialization to discovery topic.
        """
        camera_id = str(camera.id)
        device_identifier = f"liveobject_{camera_id}"

        state_topic = f"{topic_prefix}/camera/{camera_id}/last_event"
        availability_topic = f"{topic_prefix}/status"

        return {
            "name": f"{camera.name} Last Event",
            "unique_id": f"liveobject_{camera_id}_last_event",
            "object_id": f"liveobject_{camera_id}_last_event",
            "state_topic": state_topic,
            "value_template": "{{ value_json.timestamp }}",
            "json_attributes_topic": state_topic,
            "json_attributes_template": "{{ {'event_id': value_json.event_id, 'description': value_json.description_snippet, 'smart_detection_type': value_json.smart_detection_type} | tojson }}",
            "device_class": "timestamp",
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:clock-outline",
            "device": {
                "identifiers": [device_identifier],
                "name": camera.name,
                "manufacturer": "ArgusAI",
                "model": "AI Classifier",
                "sw_version": APP_VERSION,
            }
        }

    def generate_events_today_sensor_config(
        self,
        camera: Camera,
        topic_prefix: str = "liveobject"
    ) -> Dict[str, Any]:
        """
        Generate Home Assistant discovery payload for events today counter (P4-2.5, AC3).

        Args:
            camera: Camera model instance
            topic_prefix: MQTT topic prefix

        Returns:
            Dictionary ready for JSON serialization to discovery topic.
        """
        camera_id = str(camera.id)
        device_identifier = f"liveobject_{camera_id}"

        state_topic = f"{topic_prefix}/camera/{camera_id}/counts"
        availability_topic = f"{topic_prefix}/status"

        return {
            "name": f"{camera.name} Events Today",
            "unique_id": f"liveobject_{camera_id}_events_today",
            "object_id": f"liveobject_{camera_id}_events_today",
            "state_topic": state_topic,
            "value_template": "{{ value_json.events_today }}",
            "unit_of_measurement": "events",
            "state_class": "total",
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:counter",
            "device": {
                "identifiers": [device_identifier],
                "name": camera.name,
                "manufacturer": "ArgusAI",
                "model": "AI Classifier",
                "sw_version": APP_VERSION,
            }
        }

    def generate_events_week_sensor_config(
        self,
        camera: Camera,
        topic_prefix: str = "liveobject"
    ) -> Dict[str, Any]:
        """
        Generate Home Assistant discovery payload for events this week counter (P4-2.5, AC3).

        Args:
            camera: Camera model instance
            topic_prefix: MQTT topic prefix

        Returns:
            Dictionary ready for JSON serialization to discovery topic.
        """
        camera_id = str(camera.id)
        device_identifier = f"liveobject_{camera_id}"

        state_topic = f"{topic_prefix}/camera/{camera_id}/counts"
        availability_topic = f"{topic_prefix}/status"

        return {
            "name": f"{camera.name} Events This Week",
            "unique_id": f"liveobject_{camera_id}_events_week",
            "object_id": f"liveobject_{camera_id}_events_week",
            "state_topic": state_topic,
            "value_template": "{{ value_json.events_this_week }}",
            "unit_of_measurement": "events",
            "state_class": "total",
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:calendar-week",
            "device": {
                "identifiers": [device_identifier],
                "name": camera.name,
                "manufacturer": "ArgusAI",
                "model": "AI Classifier",
                "sw_version": APP_VERSION,
            }
        }

    def generate_activity_binary_sensor_config(
        self,
        camera: Camera,
        topic_prefix: str = "liveobject"
    ) -> Dict[str, Any]:
        """
        Generate Home Assistant discovery payload for activity binary sensor (P4-2.5, AC4).

        Args:
            camera: Camera model instance
            topic_prefix: MQTT topic prefix

        Returns:
            Dictionary ready for JSON serialization to discovery topic.
        """
        camera_id = str(camera.id)
        device_identifier = f"liveobject_{camera_id}"

        state_topic = f"{topic_prefix}/camera/{camera_id}/activity"
        availability_topic = f"{topic_prefix}/status"

        return {
            "name": f"{camera.name} Activity",
            "unique_id": f"liveobject_{camera_id}_activity",
            "object_id": f"liveobject_{camera_id}_activity",
            "state_topic": state_topic,
            "value_template": "{{ value_json.state }}",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": "motion",
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": {
                "identifiers": [device_identifier],
                "name": camera.name,
                "manufacturer": "ArgusAI",
                "model": "AI Classifier",
                "sw_version": APP_VERSION,
            }
        }

    def get_status_discovery_topic(
        self,
        camera_id: str,
        discovery_prefix: str = "homeassistant"
    ) -> str:
        """Get the discovery topic for camera status sensor."""
        sensor_id = f"liveobject_{camera_id}_status"
        return f"{discovery_prefix}/sensor/{sensor_id}/config"

    def get_last_event_discovery_topic(
        self,
        camera_id: str,
        discovery_prefix: str = "homeassistant"
    ) -> str:
        """Get the discovery topic for last event sensor."""
        sensor_id = f"liveobject_{camera_id}_last_event"
        return f"{discovery_prefix}/sensor/{sensor_id}/config"

    def get_events_today_discovery_topic(
        self,
        camera_id: str,
        discovery_prefix: str = "homeassistant"
    ) -> str:
        """Get the discovery topic for events today sensor."""
        sensor_id = f"liveobject_{camera_id}_events_today"
        return f"{discovery_prefix}/sensor/{sensor_id}/config"

    def get_events_week_discovery_topic(
        self,
        camera_id: str,
        discovery_prefix: str = "homeassistant"
    ) -> str:
        """Get the discovery topic for events this week sensor."""
        sensor_id = f"liveobject_{camera_id}_events_week"
        return f"{discovery_prefix}/sensor/{sensor_id}/config"

    def get_activity_discovery_topic(
        self,
        camera_id: str,
        discovery_prefix: str = "homeassistant"
    ) -> str:
        """Get the discovery topic for activity binary sensor."""
        sensor_id = f"liveobject_{camera_id}_activity"
        return f"{discovery_prefix}/binary_sensor/{sensor_id}/config"

    def get_discovery_topic(
        self,
        camera_id: str,
        discovery_prefix: str = "homeassistant"
    ) -> str:
        """
        Get the discovery topic for a camera sensor.

        Args:
            camera_id: Camera UUID
            discovery_prefix: HA discovery prefix (default "homeassistant")

        Returns:
            Full discovery topic path.

        Example:
            homeassistant/sensor/liveobject_abc123_event/config
        """
        sensor_id = f"liveobject_{camera_id}_event"
        return f"{discovery_prefix}/sensor/{sensor_id}/config"

    async def publish_discovery_config(
        self,
        camera: Camera,
        config: Optional[MQTTConfig] = None
    ) -> bool:
        """
        Publish discovery configuration for a single camera (AC1, AC5, AC7).

        Publishes all sensor types:
        - Event sensor (main AI events)
        - Status sensor (online/offline)
        - Last event timestamp sensor
        - Events today counter
        - Events this week counter
        - Activity binary sensor

        Args:
            camera: Camera to publish discovery for
            config: MQTT configuration (loads from DB if not provided)

        Returns:
            True if all published successfully, False otherwise.
        """
        # Load config if not provided
        if config is None:
            with SessionLocal() as db:
                config = db.query(MQTTConfig).first()

        if not config:
            logger.warning("Cannot publish discovery: no MQTT config")
            return False

        # Check discovery is enabled (AC6)
        if not config.discovery_enabled:
            logger.debug(f"Discovery disabled, skipping camera {camera.id}")
            return False

        # Check MQTT is connected
        if not self.mqtt_service.is_connected:
            logger.warning("Cannot publish discovery: MQTT not connected")
            return False

        camera_id = str(camera.id)
        all_success = True

        # List of (config_generator, topic_generator, sensor_type) tuples
        sensor_configs = [
            (self.generate_sensor_config, self.get_discovery_topic, "event"),
            (self.generate_status_sensor_config, self.get_status_discovery_topic, "status"),
            (self.generate_last_event_sensor_config, self.get_last_event_discovery_topic, "last_event"),
            (self.generate_events_today_sensor_config, self.get_events_today_discovery_topic, "events_today"),
            (self.generate_events_week_sensor_config, self.get_events_week_discovery_topic, "events_week"),
            (self.generate_activity_binary_sensor_config, self.get_activity_discovery_topic, "activity"),
        ]

        for config_generator, topic_generator, sensor_type in sensor_configs:
            try:
                # Generate payload
                payload = config_generator(camera, topic_prefix=config.topic_prefix)

                # Get discovery topic
                topic = topic_generator(camera_id, discovery_prefix=config.discovery_prefix)

                # Publish with QoS 1 and retain=True per HA spec
                success = await self.mqtt_service.publish(
                    topic=topic,
                    payload=payload,
                    qos=1,
                    retain=True
                )

                if not success:
                    all_success = False
                    logger.warning(
                        f"Failed to publish {sensor_type} discovery for camera {camera.name}",
                        extra={
                            "event_type": "mqtt_discovery_failed",
                            "camera_id": camera_id,
                            "sensor_type": sensor_type
                        }
                    )
            except Exception as e:
                all_success = False
                logger.error(
                    f"Error publishing {sensor_type} discovery for camera {camera.name}: {e}",
                    extra={
                        "event_type": "mqtt_discovery_error",
                        "camera_id": camera_id,
                        "sensor_type": sensor_type,
                        "error": str(e)
                    }
                )

        if all_success:
            self._published_cameras.add(camera_id)
            logger.info(
                f"Published all discovery configs for camera {camera.name}",
                extra={
                    "event_type": "mqtt_discovery_published",
                    "camera_id": camera_id,
                    "camera_name": camera.name,
                    "sensor_types": ["event", "status", "last_event", "events_today", "events_week", "activity"]
                }
            )

        return all_success

    async def publish_all_discovery_configs(self) -> int:
        """
        Publish discovery configs for all enabled cameras (AC1, AC5).

        Called on MQTT connect and reconnect to ensure all sensors
        are registered in Home Assistant.

        Returns:
            Number of cameras successfully published.
        """
        # Load MQTT config
        with SessionLocal() as db:
            config = db.query(MQTTConfig).first()

        if not config:
            logger.warning("No MQTT config found, skipping discovery")
            return 0

        # Check discovery is enabled (AC6)
        if not config.discovery_enabled:
            logger.info("MQTT discovery disabled, skipping all cameras")
            return 0

        # Get all enabled cameras
        with SessionLocal() as db:
            cameras = db.query(Camera).filter(Camera.is_enabled == True).all()

            if not cameras:
                logger.info("No enabled cameras found for discovery")
                return 0

            # Publish for each camera
            published_count = 0
            for camera in cameras:
                try:
                    if await self.publish_discovery_config(camera, config):
                        published_count += 1
                except Exception as e:
                    logger.error(
                        f"Error publishing discovery for camera {camera.id}: {e}",
                        extra={
                            "event_type": "mqtt_discovery_error",
                            "camera_id": str(camera.id),
                            "error": str(e)
                        }
                    )

            logger.info(
                f"Published discovery for {published_count}/{len(cameras)} cameras",
                extra={
                    "event_type": "mqtt_discovery_all_complete",
                    "published_count": published_count,
                    "total_cameras": len(cameras)
                }
            )

            return published_count

    async def remove_discovery_config(
        self,
        camera_id: str,
        config: Optional[MQTTConfig] = None
    ) -> bool:
        """
        Remove all discovery configs for a camera (AC4).

        Publishes empty payload to all discovery topics to remove sensors
        from Home Assistant.

        Args:
            camera_id: Camera UUID to remove
            config: MQTT configuration (loads from DB if not provided)

        Returns:
            True if all removals published, False otherwise.
        """
        # Load config if not provided
        if config is None:
            with SessionLocal() as db:
                config = db.query(MQTTConfig).first()

        if not config:
            logger.warning("Cannot remove discovery: no MQTT config")
            return False

        # Check MQTT is connected
        if not self.mqtt_service.is_connected:
            logger.debug(f"MQTT not connected, cannot remove discovery for {camera_id}")
            # Still remove from tracking set
            self._published_cameras.discard(camera_id)
            return False

        # List of topic generators for all sensor types
        topic_generators = [
            self.get_discovery_topic,
            self.get_status_discovery_topic,
            self.get_last_event_discovery_topic,
            self.get_events_today_discovery_topic,
            self.get_events_week_discovery_topic,
            self.get_activity_discovery_topic,
        ]

        all_success = True

        # Publish empty payload to remove sensors (HA Discovery spec)
        # Note: Empty string payload with retain=True removes the retained message
        try:
            if self.mqtt_service._client:
                for topic_generator in topic_generators:
                    topic = topic_generator(camera_id, discovery_prefix=config.discovery_prefix)
                    result = self.mqtt_service._client.publish(
                        topic,
                        payload="",
                        qos=1,
                        retain=True
                    )
                    if result.rc != 0:
                        all_success = False

                if all_success:
                    self._published_cameras.discard(camera_id)
                    logger.info(
                        f"Removed all discovery configs for camera {camera_id}",
                        extra={
                            "event_type": "mqtt_discovery_removed",
                            "camera_id": camera_id,
                            "sensor_types": ["event", "status", "last_event", "events_today", "events_week", "activity"]
                        }
                    )
                    return True

        except Exception as e:
            logger.error(
                f"Error removing discovery for camera {camera_id}: {e}",
                extra={
                    "event_type": "mqtt_discovery_remove_error",
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )

        return False

    async def remove_all_discovery_configs(self) -> int:
        """
        Remove all discovery configs (AC6: when discovery disabled).

        Returns:
            Number of cameras removed.
        """
        # Load config for prefix
        with SessionLocal() as db:
            config = db.query(MQTTConfig).first()

        if not config:
            return 0

        # Get list of published cameras
        cameras_to_remove = list(self._published_cameras)

        removed_count = 0
        for camera_id in cameras_to_remove:
            if await self.remove_discovery_config(camera_id, config):
                removed_count += 1

        logger.info(
            f"Removed discovery for {removed_count} cameras",
            extra={
                "event_type": "mqtt_discovery_all_removed",
                "removed_count": removed_count
            }
        )

        return removed_count

    def on_mqtt_connect(self) -> None:
        """
        Callback for MQTT connection (AC5: discovery on reconnect).

        Called by MQTTService when connection is established.
        Triggers discovery publishing for all cameras.

        Note: This callback runs in paho-mqtt's network thread, not the main
        asyncio event loop. We use run_coroutine_threadsafe() to schedule
        async work on the main loop safely.

        Fixed in P14-1.1: Replaced asyncio.run() with run_coroutine_threadsafe()
        to avoid RuntimeError when called from a thread with an existing event loop.
        """
        logger.info(
            "MQTT connected, publishing discovery configs",
            extra={"event_type": "mqtt_discovery_connect_trigger"}
        )

        # Schedule async publish - handle different execution contexts
        if self._main_event_loop is not None and self._main_event_loop.is_running():
            # Preferred path: Schedule on main event loop from MQTT callback thread
            # This is thread-safe and won't conflict with the main event loop
            future = asyncio.run_coroutine_threadsafe(
                self._publish_discovery_on_connect(),
                self._main_event_loop
            )
            # Log any errors from the future (non-blocking)
            future.add_done_callback(self._handle_publish_future)
            logger.debug(
                "Scheduled discovery publish on main event loop",
                extra={"event_type": "mqtt_discovery_scheduled_threadsafe"}
            )
        else:
            # Fallback: No main loop available (rare case - sync context or test)
            # Create a temporary event loop in this thread
            logger.debug(
                "No main event loop available, creating temporary loop",
                extra={"event_type": "mqtt_discovery_temp_loop"}
            )
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._publish_discovery_on_connect())
            except Exception as e:
                logger.error(
                    f"Error in discovery publish (temp loop): {e}",
                    extra={"event_type": "mqtt_discovery_temp_loop_error", "error": str(e)}
                )
            finally:
                loop.close()

    def _handle_publish_future(self, future: asyncio.Future) -> None:
        """Handle completion of threadsafe discovery publish."""
        try:
            future.result()  # Raises exception if the coroutine failed
        except Exception as e:
            logger.error(
                f"Error in discovery publish future: {e}",
                extra={"event_type": "mqtt_discovery_future_error", "error": str(e)}
            )

    async def _publish_discovery_on_connect(self) -> None:
        """Internal async handler for on_connect callback."""
        try:
            # Small delay to ensure connection is stable
            await asyncio.sleep(0.5)

            # Publish online status first (AC7)
            await self._publish_online_status()

            # Then publish all discovery configs
            await self.publish_all_discovery_configs()

            # Publish camera statuses on connect/reconnect (Bug fix: statuses were only
            # published at startup, not on reconnect, causing "Unknown" in Home Assistant)
            try:
                status_count = await publish_all_camera_statuses()
                logger.info(
                    f"Published status for {status_count} cameras on MQTT connect",
                    extra={"event_type": "mqtt_camera_status_on_connect", "count": status_count}
                )
            except Exception as status_err:
                logger.warning(
                    f"Failed to publish camera statuses on connect: {status_err}",
                    extra={"event_type": "mqtt_camera_status_connect_error", "error": str(status_err)}
                )

        except Exception as e:
            logger.error(
                f"Error publishing discovery on connect: {e}",
                extra={"event_type": "mqtt_discovery_connect_error", "error": str(e)}
            )

    async def _publish_online_status(self) -> None:
        """Publish online status to availability topic (AC7)."""
        with SessionLocal() as db:
            config = db.query(MQTTConfig).first()

        if not config:
            return

        status_topic = f"{config.topic_prefix}/status"

        # Publish "online" to status topic
        try:
            if self.mqtt_service._client:
                self.mqtt_service._client.publish(
                    status_topic,
                    payload="online",
                    qos=1,
                    retain=True
                )
                logger.debug(
                    f"Published online status to {status_topic}",
                    extra={"event_type": "mqtt_status_online"}
                )
        except Exception as e:
            logger.error(f"Failed to publish online status: {e}")


# Global singleton instance
_discovery_service: Optional[MQTTDiscoveryService] = None


def get_discovery_service() -> MQTTDiscoveryService:
    """
    Get the global MQTT discovery service instance.

    Returns:
        MQTTDiscoveryService singleton instance.
    """
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = MQTTDiscoveryService()
    return _discovery_service


async def initialize_discovery_service() -> None:
    """
    Initialize discovery service and register with MQTT service.

    Called during app startup after MQTT service is initialized.

    Note: Must be called from async context (FastAPI lifespan) to capture
    the running event loop for cross-thread scheduling.
    """
    discovery = get_discovery_service()
    mqtt = get_mqtt_service()

    # Capture main event loop for cross-thread scheduling (P14-1.1 fix)
    # This allows on_mqtt_connect callback (running in paho-mqtt's thread)
    # to schedule async work on the main event loop safely
    try:
        main_loop = asyncio.get_running_loop()
        discovery.set_main_event_loop(main_loop)
    except RuntimeError:
        logger.warning(
            "Could not capture main event loop - MQTT reconnect may not work correctly",
            extra={"event_type": "mqtt_discovery_no_loop"}
        )

    # Register on_connect callback for discovery publishing (AC5)
    mqtt.set_on_connect_callback(discovery.on_mqtt_connect)

    logger.info(
        "MQTT discovery service initialized",
        extra={"event_type": "mqtt_discovery_init"}
    )


async def on_camera_deleted(camera_id: str) -> None:
    """
    Hook for camera deletion - removes discovery config (AC4).

    Call this from camera delete flow.

    Args:
        camera_id: UUID of deleted camera
    """
    discovery = get_discovery_service()
    await discovery.remove_discovery_config(camera_id)


async def on_camera_disabled(camera_id: str) -> None:
    """
    Hook for camera disable - removes discovery config (AC4).

    Call this from camera disable flow.

    Args:
        camera_id: UUID of disabled camera
    """
    discovery = get_discovery_service()
    await discovery.remove_discovery_config(camera_id)


async def on_discovery_setting_changed(enabled: bool) -> None:
    """
    Hook for discovery_enabled setting change (AC6).

    Args:
        enabled: New discovery_enabled value
    """
    discovery = get_discovery_service()

    if enabled:
        # Re-publish all discovery configs
        await discovery.publish_all_discovery_configs()
    else:
        # Remove all discovery configs
        await discovery.remove_all_discovery_configs()
