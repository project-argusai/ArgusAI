"""
HomeKit service for Apple Home integration (Story P4-6.1, P4-6.2)

Manages the HAP-python accessory server and exposes cameras as motion sensors.
Story P4-6.2 adds motion event triggering with auto-reset timers.
"""
import asyncio
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import base64
import io

try:
    from pyhap.accessory import Bridge
    from pyhap.accessory_driver import AccessoryDriver
    HAP_AVAILABLE = True
except ImportError:
    HAP_AVAILABLE = False

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

from app.config.homekit import HomekitConfig, get_homekit_config, generate_pincode
from app.services.homekit_accessories import CameraMotionSensor, create_motion_sensor

logger = logging.getLogger(__name__)


@dataclass
class HomekitStatus:
    """Status information for HomeKit integration."""
    enabled: bool = False
    running: bool = False
    paired: bool = False
    accessory_count: int = 0
    bridge_name: str = "ArgusAI"
    setup_code: Optional[str] = None
    qr_code_data: Optional[str] = None
    port: int = 51826
    error: Optional[str] = None


class HomekitService:
    """
    HomeKit accessory server service.

    Manages the HAP-python AccessoryDriver and exposes cameras as motion sensors
    in the Apple Home app.

    Lifecycle:
        1. Initialize with configuration
        2. Call start() with list of cameras
        3. Use trigger_motion(camera_id) when events occur
        4. Call stop() on shutdown

    Example:
        >>> service = HomekitService()
        >>> await service.start(cameras)
        >>> service.trigger_motion("camera-uuid")
        >>> await service.stop()
    """

    def __init__(self, config: Optional[HomekitConfig] = None):
        """
        Initialize the HomeKit service.

        Args:
            config: HomeKit configuration. If None, loads from environment.
        """
        self.config = config or get_homekit_config()
        self._driver: Optional[AccessoryDriver] = None
        self._bridge: Optional[Bridge] = None
        self._sensors: Dict[str, CameraMotionSensor] = {}
        self._running = False
        self._driver_thread: Optional[threading.Thread] = None
        self._pincode: Optional[str] = None
        self._error: Optional[str] = None

        # Story P4-6.2: Motion reset timers and state tracking
        self._motion_reset_tasks: Dict[str, asyncio.Task] = {}  # camera_id -> reset task
        self._motion_start_times: Dict[str, float] = {}  # camera_id -> start timestamp
        self._camera_id_mapping: Dict[str, str] = {}  # mac_address/alt_id -> camera_id

    @property
    def is_available(self) -> bool:
        """Check if HAP-python is available."""
        return HAP_AVAILABLE

    @property
    def is_running(self) -> bool:
        """Check if the accessory server is running."""
        return self._running and self._driver is not None

    @property
    def is_paired(self) -> bool:
        """Check if the accessory is paired with a Home app."""
        if not self._driver:
            return False
        try:
            # Check if state file exists and contains pairing data
            state_file = Path(self.config.persist_file)
            if state_file.exists():
                import json
                with open(state_file, 'r') as f:
                    state_data = json.load(f)
                # Check for actual paired clients in the state
                paired_clients = state_data.get('paired_clients', [])
                return len(paired_clients) > 0
            return False
        except Exception:
            return False

    @property
    def accessory_count(self) -> int:
        """Get the number of registered camera sensors."""
        return len(self._sensors)

    @property
    def pincode(self) -> str:
        """Get the HomeKit pairing code."""
        if self._pincode:
            return self._pincode
        if self.config.pincode:
            self._pincode = self.config.pincode
        else:
            # Generate and persist a pincode
            self._pincode = generate_pincode()
        return self._pincode

    def get_qr_code_data(self) -> Optional[str]:
        """
        Generate QR code data for HomeKit pairing.

        Returns:
            Base64-encoded PNG image data, or None if qrcode not available
        """
        if not QRCODE_AVAILABLE:
            return None

        try:
            # HomeKit setup URI format: X-HM://[setup_code][category][setup_id]
            # For simplicity, we'll generate a QR code with the pairing code
            # The actual HomeKit QR code format is proprietary and requires specific encoding

            # Create a simple QR code with pairing instructions
            qr_content = f"HomeKit Pairing Code: {self.pincode}"

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_content)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            img_data = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return f"data:image/png;base64,{img_data}"

        except Exception as e:
            logger.error(f"Failed to generate QR code: {e}")
            return None

    def get_status(self) -> HomekitStatus:
        """
        Get current HomeKit service status.

        Returns:
            HomekitStatus with current state information
        """
        return HomekitStatus(
            enabled=self.config.enabled,
            running=self.is_running,
            paired=self.is_paired,
            accessory_count=self.accessory_count,
            bridge_name=self.config.bridge_name,
            setup_code=self.pincode if not self.is_paired else None,
            qr_code_data=self.get_qr_code_data() if not self.is_paired else None,
            port=self.config.port,
            error=self._error,
        )

    async def start(self, cameras: List[Any]) -> bool:
        """
        Start the HomeKit accessory server.

        Args:
            cameras: List of Camera model instances to expose as motion sensors

        Returns:
            True if started successfully, False otherwise
        """
        if not self.config.enabled:
            logger.info("HomeKit integration is disabled")
            return False

        if not HAP_AVAILABLE:
            self._error = "HAP-python not installed"
            logger.error("HAP-python not installed. Install with: pip install HAP-python")
            return False

        if self._running:
            logger.warning("HomeKit service already running")
            return True

        try:
            # Ensure persistence directory exists
            self.config.ensure_persist_dir()

            # Create accessory driver
            self._driver = AccessoryDriver(
                port=self.config.port,
                persist_file=self.config.persist_file,
                pincode=self.pincode.encode('utf-8'),
            )

            # Create bridge accessory
            self._bridge = Bridge(self._driver, self.config.bridge_name)

            # Add camera motion sensors
            for camera in cameras:
                if hasattr(camera, 'enabled') and not camera.enabled:
                    continue  # Skip disabled cameras

                camera_id = camera.id if hasattr(camera, 'id') else str(camera)
                camera_name = camera.name if hasattr(camera, 'name') else f"Camera {camera_id[:8]}"

                sensor = create_motion_sensor(
                    driver=self._driver,
                    camera_id=camera_id,
                    camera_name=camera_name,
                    manufacturer=self.config.manufacturer,
                )

                if sensor:
                    self._sensors[camera_id] = sensor
                    self._bridge.add_accessory(sensor.accessory)

                    # Story P4-6.2 AC4: Register MAC address mapping for Protect cameras
                    if hasattr(camera, 'mac_address') and camera.mac_address:
                        self.register_camera_mapping(camera_id, camera.mac_address)

                    logger.info(f"Added HomeKit motion sensor for camera: {camera_name}")

            # Add bridge to driver
            self._driver.add_accessory(self._bridge)

            # Start driver in background thread
            self._driver_thread = threading.Thread(
                target=self._run_driver,
                name="homekit-driver",
                daemon=True
            )
            self._driver_thread.start()

            self._running = True
            self._error = None

            logger.info(
                f"HomeKit accessory server started on port {self.config.port} "
                f"with {len(self._sensors)} sensors. Pairing code: {self.pincode}"
            )

            return True

        except Exception as e:
            self._error = str(e)
            logger.error(f"Failed to start HomeKit service: {e}", exc_info=True)
            return False

    def _run_driver(self) -> None:
        """Run the accessory driver in a separate thread."""
        try:
            self._driver.start()
        except Exception as e:
            self._error = str(e)
            logger.error(f"HomeKit driver error: {e}", exc_info=True)
            self._running = False

    async def stop(self) -> None:
        """Stop the HomeKit accessory server."""
        if not self._running:
            return

        try:
            # Story P4-6.2: Cancel all motion reset timers
            for camera_id in list(self._motion_reset_tasks.keys()):
                self._cancel_reset_timer(camera_id)
            self._motion_reset_tasks.clear()
            self._motion_start_times.clear()

            if self._driver:
                self._driver.stop()

            if self._driver_thread:
                self._driver_thread.join(timeout=5.0)

            self._running = False
            self._driver = None
            self._bridge = None
            self._sensors.clear()
            self._camera_id_mapping.clear()

            logger.info("HomeKit accessory server stopped")

        except Exception as e:
            logger.error(f"Error stopping HomeKit service: {e}", exc_info=True)

    def add_camera(self, camera: Any) -> bool:
        """
        Add a new camera to the HomeKit bridge.

        Args:
            camera: Camera model instance

        Returns:
            True if added successfully
        """
        if not self.is_running:
            logger.warning("Cannot add camera: HomeKit service not running")
            return False

        camera_id = camera.id if hasattr(camera, 'id') else str(camera)

        if camera_id in self._sensors:
            logger.debug(f"Camera {camera_id} already registered")
            return True

        camera_name = camera.name if hasattr(camera, 'name') else f"Camera {camera_id[:8]}"

        sensor = create_motion_sensor(
            driver=self._driver,
            camera_id=camera_id,
            camera_name=camera_name,
            manufacturer=self.config.manufacturer,
        )

        if sensor:
            self._sensors[camera_id] = sensor
            self._bridge.add_accessory(sensor.accessory)

            # Story P4-6.2 AC4: Register MAC address mapping for Protect cameras
            if hasattr(camera, 'mac_address') and camera.mac_address:
                self.register_camera_mapping(camera_id, camera.mac_address)

            logger.info(f"Added HomeKit motion sensor for camera: {camera_name}")
            return True

        return False

    def remove_camera(self, camera_id: str) -> bool:
        """
        Remove a camera from the HomeKit bridge.

        Args:
            camera_id: Camera identifier

        Returns:
            True if removed successfully
        """
        if camera_id in self._sensors:
            del self._sensors[camera_id]
            logger.info(f"Removed HomeKit motion sensor for camera: {camera_id}")
            return True
        return False

    def trigger_motion(self, camera_id: str, event_id: Optional[int] = None) -> bool:
        """
        Trigger motion detection for a camera (Story P4-6.2).

        Sets motion_detected = True and starts/resets the auto-clear timer.
        If called again before timer expires, the timer is reset (extends motion period).

        Args:
            camera_id: Camera identifier (UUID or MAC address)
            event_id: Optional event ID for logging

        Returns:
            True if motion triggered successfully
        """
        # Resolve camera_id through mapping (for Protect cameras using MAC)
        resolved_id = self._resolve_camera_id(camera_id)
        sensor = self._sensors.get(resolved_id)

        if not sensor:
            logger.debug(
                f"No HomeKit sensor found for camera: {camera_id} (resolved: {resolved_id})",
                extra={"camera_id": camera_id, "event_id": event_id}
            )
            return False

        # Set motion detected
        sensor.trigger_motion()

        # Track motion start time for max duration check (AC5)
        current_time = time.time()
        if resolved_id not in self._motion_start_times:
            self._motion_start_times[resolved_id] = current_time

        # Check max motion duration (AC5: prevent stuck state)
        motion_duration = current_time - self._motion_start_times[resolved_id]
        if motion_duration >= self.config.max_motion_duration:
            logger.warning(
                f"Max motion duration reached for camera {camera_id}, resetting",
                extra={"camera_id": camera_id, "duration": motion_duration}
            )
            self._clear_motion_state(resolved_id)
            return True

        # Cancel existing reset timer if any (AC3: rapid events extend motion)
        self._cancel_reset_timer(resolved_id)

        # Start new reset timer
        self._start_reset_timer(resolved_id)

        logger.info(
            f"HomeKit motion triggered for camera: {sensor.name}",
            extra={
                "camera_id": camera_id,
                "event_id": event_id,
                "reset_seconds": self.config.motion_reset_seconds
            }
        )

        return True

    def _resolve_camera_id(self, camera_id: str) -> str:
        """
        Resolve camera ID through mapping (Story P4-6.2 AC4).

        Protect cameras use MAC address, RTSP/USB use camera.id.
        This allows triggering by either identifier.

        Args:
            camera_id: Camera identifier (UUID or MAC address)

        Returns:
            Resolved camera ID that exists in _sensors
        """
        # First check if it's directly in sensors
        if camera_id in self._sensors:
            return camera_id

        # Check mapping (MAC -> camera_id)
        if camera_id in self._camera_id_mapping:
            return self._camera_id_mapping[camera_id]

        # Try lowercase MAC address
        lower_id = camera_id.lower().replace(":", "").replace("-", "")
        if lower_id in self._camera_id_mapping:
            return self._camera_id_mapping[lower_id]

        # Return original (will result in no sensor found)
        return camera_id

    def _cancel_reset_timer(self, camera_id: str) -> None:
        """Cancel existing motion reset timer for a camera."""
        if camera_id in self._motion_reset_tasks:
            task = self._motion_reset_tasks.pop(camera_id)
            if not task.done():
                task.cancel()

    def _start_reset_timer(self, camera_id: str) -> None:
        """Start a new motion reset timer for a camera (Story P4-6.2 AC2)."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._motion_reset_coroutine(camera_id),
                name=f"homekit_motion_reset_{camera_id}"
            )
            self._motion_reset_tasks[camera_id] = task
        except RuntimeError:
            # No event loop running, log and skip timer
            logger.debug(
                f"Could not start motion reset timer for {camera_id} - no running event loop",
                extra={"camera_id": camera_id}
            )

    async def _motion_reset_coroutine(self, camera_id: str) -> None:
        """
        Coroutine that waits and then clears motion (Story P4-6.2 AC2).

        Args:
            camera_id: Camera identifier
        """
        try:
            await asyncio.sleep(self.config.motion_reset_seconds)
            self._clear_motion_state(camera_id)
            logger.debug(
                f"HomeKit motion reset for camera after {self.config.motion_reset_seconds}s",
                extra={"camera_id": camera_id}
            )
        except asyncio.CancelledError:
            # Timer was cancelled (new event arrived)
            pass

    def _clear_motion_state(self, camera_id: str) -> None:
        """Clear motion state and cleanup tracking for a camera."""
        sensor = self._sensors.get(camera_id)
        if sensor:
            sensor.clear_motion()

        # Clear tracking
        self._motion_start_times.pop(camera_id, None)
        self._motion_reset_tasks.pop(camera_id, None)

    def register_camera_mapping(self, camera_id: str, mac_address: Optional[str] = None) -> None:
        """
        Register a camera ID mapping for Protect cameras (Story P4-6.2 AC4).

        Args:
            camera_id: Primary camera identifier (UUID)
            mac_address: MAC address for Protect cameras
        """
        if mac_address:
            # Normalize MAC address (lowercase, no separators)
            normalized_mac = mac_address.lower().replace(":", "").replace("-", "")
            self._camera_id_mapping[normalized_mac] = camera_id
            self._camera_id_mapping[mac_address] = camera_id
            logger.debug(
                f"Registered camera mapping: {mac_address} -> {camera_id}",
                extra={"camera_id": camera_id, "mac_address": mac_address}
            )

    def clear_motion(self, camera_id: str) -> bool:
        """
        Clear motion detection for a camera.

        Args:
            camera_id: Camera identifier

        Returns:
            True if motion cleared successfully
        """
        sensor = self._sensors.get(camera_id)
        if sensor:
            sensor.clear_motion()
            return True
        return False

    def clear_all_motion(self) -> None:
        """Clear motion for all cameras (Story P4-6.2 AC5: state sync on restart)."""
        # Cancel all reset timers
        for camera_id in list(self._motion_reset_tasks.keys()):
            self._cancel_reset_timer(camera_id)

        # Clear all motion states
        for camera_id, sensor in self._sensors.items():
            sensor.clear_motion()
            self._motion_start_times.pop(camera_id, None)

        logger.debug("Cleared all HomeKit motion states")

    async def reset_pairing(self) -> bool:
        """
        Reset HomeKit pairing by removing state file.

        This will require re-pairing with the Home app.

        Returns:
            True if reset successfully
        """
        try:
            # Stop the server first
            was_running = self._running
            cameras_backup = list(self._sensors.keys())

            await self.stop()

            # Remove state file
            state_file = Path(self.config.persist_file)
            if state_file.exists():
                state_file.unlink()
                logger.info("HomeKit pairing state reset")

            # Generate new pincode
            self._pincode = generate_pincode()

            return True

        except Exception as e:
            logger.error(f"Failed to reset HomeKit pairing: {e}")
            return False


# Global service instance
_homekit_service: Optional[HomekitService] = None


def get_homekit_service() -> HomekitService:
    """
    Get the global HomeKit service instance.

    Creates the instance on first call.

    Returns:
        HomekitService singleton instance
    """
    global _homekit_service
    if _homekit_service is None:
        _homekit_service = HomekitService()
    return _homekit_service


async def initialize_homekit_service(cameras: List[Any]) -> bool:
    """
    Initialize and start the HomeKit service with cameras.

    Args:
        cameras: List of Camera model instances

    Returns:
        True if started successfully
    """
    service = get_homekit_service()
    return await service.start(cameras)


async def shutdown_homekit_service() -> None:
    """Stop the HomeKit service."""
    global _homekit_service
    if _homekit_service:
        await _homekit_service.stop()
