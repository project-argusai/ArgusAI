"""
HomeKit service for Apple Home integration (Story P4-6.1, P4-6.2, P5-1.2, P5-1.3, P5-1.5, P5-1.6, P5-1.7, P7-1.1, P7-1.2, P7-2.3)

Manages the HAP-python accessory server and exposes cameras as motion sensors.
Story P4-6.2 adds motion event triggering with auto-reset timers.
Story P5-1.2 adds proper HomeKit Setup URI for QR code pairing.
Story P5-1.3 adds camera accessories with RTSP-to-SRTP streaming.
Story P5-1.5 adds occupancy sensors for person-only detection with 5-minute timeout.
Story P5-1.6 adds vehicle/animal/package sensors for detection-type-specific automations.
Story P5-1.7 adds doorbell sensors for Protect doorbell ring events.
Story P7-1.1 adds comprehensive diagnostic logging for troubleshooting.
Story P7-1.2 adds network binding configuration and connectivity testing.
Story P7-2.3 adds carrier-aware package sensors and per-carrier sensor support.
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

from app.config.homekit import (
    HomekitConfig,
    get_homekit_config,
    generate_pincode,
    generate_setup_id,
    generate_setup_uri,
    HOMEKIT_CATEGORY_BRIDGE,
)
from app.services.homekit_accessories import (
    CameraMotionSensor,
    create_motion_sensor,
    CameraOccupancySensor,
    create_occupancy_sensor,
    CameraVehicleSensor,
    create_vehicle_sensor,
    CameraAnimalSensor,
    create_animal_sensor,
    CameraPackageSensor,
    create_package_sensor,
    CameraDoorbellSensor,
    create_doorbell_sensor,
)
from app.services.homekit_camera import (
    HomeKitCameraAccessory,
    create_camera_accessory,
    check_ffmpeg_available,
    StreamQuality,
    StreamConfig,
)
from app.services.homekit_diagnostics import (
    get_diagnostic_handler,
    HomekitDiagnosticHandler,
)
from app.schemas.homekit_diagnostics import (
    HomeKitDiagnosticsResponse,
    NetworkBindingInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class HomekitStatus:
    """Status information for HomeKit integration."""
    enabled: bool = False
    running: bool = False
    paired: bool = False
    accessory_count: int = 0
    camera_count: int = 0  # Story P5-1.3: Number of camera accessories
    occupancy_count: int = 0  # Story P5-1.5: Number of occupancy sensor accessories
    vehicle_count: int = 0  # Story P5-1.6: Number of vehicle sensor accessories
    animal_count: int = 0  # Story P5-1.6: Number of animal sensor accessories
    package_count: int = 0  # Story P5-1.6: Number of package sensor accessories
    doorbell_count: int = 0  # Story P5-1.7: Number of doorbell sensor accessories
    active_streams: int = 0  # Story P5-1.3: Currently active camera streams
    bridge_name: str = "ArgusAI"
    setup_code: Optional[str] = None
    setup_uri: Optional[str] = None  # Story P5-1.2: X-HM:// URI for QR code
    qr_code_data: Optional[str] = None
    port: int = 51826
    ffmpeg_available: bool = False  # Story P5-1.3: Whether ffmpeg is installed
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
        self._occupancy_sensors: Dict[str, CameraOccupancySensor] = {}  # Story P5-1.5: Occupancy sensors
        self._cameras: Dict[str, HomeKitCameraAccessory] = {}  # Story P5-1.3: Camera accessories
        self._running = False
        self._driver_thread: Optional[threading.Thread] = None
        self._pincode: Optional[str] = None
        self._setup_id: Optional[str] = None  # Story P5-1.2: Setup ID for URI
        self._error: Optional[str] = None
        self._ffmpeg_available: bool = False  # Story P5-1.3: Track ffmpeg availability

        # Story P4-6.2: Motion reset timers and state tracking
        self._motion_reset_tasks: Dict[str, asyncio.Task] = {}  # camera_id -> reset task
        self._motion_start_times: Dict[str, float] = {}  # camera_id -> start timestamp
        self._camera_id_mapping: Dict[str, str] = {}  # mac_address/alt_id -> camera_id

        # Story P5-1.5: Occupancy reset timers and state tracking
        self._occupancy_reset_tasks: Dict[str, asyncio.Task] = {}  # camera_id -> reset task
        self._occupancy_start_times: Dict[str, float] = {}  # camera_id -> start timestamp

        # Story P5-1.6: Vehicle/Animal/Package sensors and reset timers
        self._vehicle_sensors: Dict[str, CameraVehicleSensor] = {}
        self._animal_sensors: Dict[str, CameraAnimalSensor] = {}
        self._package_sensors: Dict[str, CameraPackageSensor] = {}
        self._vehicle_reset_tasks: Dict[str, asyncio.Task] = {}
        self._animal_reset_tasks: Dict[str, asyncio.Task] = {}
        self._package_reset_tasks: Dict[str, asyncio.Task] = {}

        # Story P5-1.7: Doorbell sensors (stateless - no reset timers needed)
        self._doorbell_sensors: Dict[str, CameraDoorbellSensor] = {}

        # Story P7-2.3: Per-carrier package sensors (key: "{camera_id}_{carrier}")
        # When config.per_carrier_sensors=True, separate sensors created per carrier
        self._carrier_sensors: Dict[str, CameraPackageSensor] = {}
        self._carrier_reset_tasks: Dict[str, asyncio.Task] = {}

        # Story P7-1.1: Initialize diagnostic handler
        self._diagnostic_handler: HomekitDiagnosticHandler = get_diagnostic_handler(
            max_entries=self.config.diagnostic_log_size
        )
        self._network_binding: Optional[NetworkBindingInfo] = None
        self._mdns_advertising: bool = False

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
    def camera_count(self) -> int:
        """Get the number of registered camera accessories (Story P5-1.3)."""
        return len(self._cameras)

    @property
    def occupancy_count(self) -> int:
        """Get the number of registered occupancy sensor accessories (Story P5-1.5)."""
        return len(self._occupancy_sensors)

    @property
    def vehicle_count(self) -> int:
        """Get the number of registered vehicle sensor accessories (Story P5-1.6)."""
        return len(self._vehicle_sensors)

    @property
    def animal_count(self) -> int:
        """Get the number of registered animal sensor accessories (Story P5-1.6)."""
        return len(self._animal_sensors)

    @property
    def package_count(self) -> int:
        """Get the number of registered package sensor accessories (Story P5-1.6)."""
        return len(self._package_sensors)

    @property
    def doorbell_count(self) -> int:
        """Get the number of registered doorbell sensor accessories (Story P5-1.7)."""
        return len(self._doorbell_sensors)

    @property
    def carrier_sensor_count(self) -> int:
        """Get the number of registered per-carrier package sensors (Story P7-2.3)."""
        return len(self._carrier_sensors)

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

    @property
    def setup_id(self) -> str:
        """
        Get the HomeKit Setup ID (Story P5-1.2).

        The Setup ID is a 4-character alphanumeric identifier used in the
        X-HM:// Setup URI for QR code pairing.
        """
        if self._setup_id:
            return self._setup_id
        # Generate a new setup ID
        self._setup_id = generate_setup_id()
        return self._setup_id

    def get_setup_uri(self) -> str:
        """
        Get the HomeKit Setup URI for QR code pairing (Story P5-1.2).

        Returns:
            X-HM:// URI string containing encoded setup code, category, and setup ID
        """
        return generate_setup_uri(
            setup_code=self.pincode,
            setup_id=self.setup_id,
            category=HOMEKIT_CATEGORY_BRIDGE
        )

    def get_qr_code_data(self) -> Optional[str]:
        """
        Generate QR code data for HomeKit pairing (Story P5-1.2).

        Generates a QR code containing the proper HomeKit Setup URI (X-HM://)
        which can be scanned directly by the Apple Home app for pairing.

        Returns:
            Base64-encoded PNG image data, or None if qrcode not available
        """
        if not QRCODE_AVAILABLE:
            return None

        try:
            # Story P5-1.2 AC2: Generate proper HomeKit Setup URI
            setup_uri = self.get_setup_uri()

            qr = qrcode.QRCode(
                version=1,
                # Use ERROR_CORRECT_M or higher for reliable mobile scanning
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(setup_uri)
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
        # Story P5-1.2 AC4: Hide setup code/URI when paired
        is_paired = self.is_paired
        return HomekitStatus(
            enabled=self.config.enabled,
            running=self.is_running,
            paired=is_paired,
            accessory_count=self.accessory_count,
            camera_count=self.camera_count,  # Story P5-1.3
            occupancy_count=self.occupancy_count,  # Story P5-1.5
            vehicle_count=self.vehicle_count,  # Story P5-1.6
            animal_count=self.animal_count,  # Story P5-1.6
            package_count=self.package_count,  # Story P5-1.6
            doorbell_count=self.doorbell_count,  # Story P5-1.7
            active_streams=HomeKitCameraAccessory.get_active_stream_count(),  # Story P5-1.3
            bridge_name=self.config.bridge_name,
            setup_code=self.pincode if not is_paired else None,
            setup_uri=self.get_setup_uri() if not is_paired else None,
            qr_code_data=self.get_qr_code_data() if not is_paired else None,
            port=self.config.port,
            ffmpeg_available=self._ffmpeg_available,  # Story P5-1.3
            error=self._error,
        )

    def get_diagnostics(self) -> HomeKitDiagnosticsResponse:
        """
        Get diagnostic information for HomeKit troubleshooting (Story P7-1.1 AC5, P7-1.4 AC1-4).

        Returns:
            HomeKitDiagnosticsResponse with bridge status, logs, warnings, errors,
            and per-sensor delivery history (Story P7-1.4 AC3)
        """
        return HomeKitDiagnosticsResponse(
            bridge_running=self.is_running,
            mdns_advertising=self._mdns_advertising,
            network_binding=self._network_binding,
            connected_clients=self._get_connected_client_count(),
            last_event_delivery=self._diagnostic_handler.get_last_event_delivery(),
            sensor_deliveries=self._diagnostic_handler.get_sensor_deliveries(),  # Story P7-1.4 AC3
            recent_logs=self._diagnostic_handler.get_recent_logs(),
            warnings=self._diagnostic_handler.get_warnings(),
            errors=self._diagnostic_handler.get_errors(),
        )

    async def test_connectivity(self) -> "HomeKitConnectivityTestResponse":
        """
        Test HomeKit bridge connectivity (Story P7-1.2 AC1, AC2, AC6).

        Performs:
        1. mDNS visibility check using zeroconf ServiceBrowser
        2. Port accessibility test (TCP connection to HAP port)
        3. Generates troubleshooting recommendations

        Returns:
            HomeKitConnectivityTestResponse with test results
        """
        import time
        import socket
        from app.schemas.homekit_diagnostics import HomeKitConnectivityTestResponse

        start_time = time.time()
        mdns_visible = False
        discovered_as: Optional[str] = None
        port_accessible = False
        firewall_issues: List[str] = []
        recommendations: List[str] = []

        # Test 1: mDNS visibility check
        try:
            from zeroconf import Zeroconf, ServiceBrowser, ServiceListener

            class HapServiceListener(ServiceListener):
                def __init__(self):
                    self.services: List[str] = []

                def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    self.services.append(name)

                def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

                def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

            zc = Zeroconf()
            listener = HapServiceListener()
            browser = ServiceBrowser(zc, "_hap._tcp.local.", listener)

            # Wait up to 3 seconds for service discovery
            await asyncio.sleep(3)

            # Check if our bridge name appears in discovered services
            bridge_name = self.config.bridge_name
            for service_name in listener.services:
                if bridge_name.lower() in service_name.lower():
                    mdns_visible = True
                    discovered_as = service_name
                    break

            browser.cancel()
            zc.close()

            if not mdns_visible:
                firewall_issues.append("mDNS service not visible - check UDP port 5353")
                recommendations.append("Ensure UDP port 5353 is open for mDNS multicast")
                recommendations.append("Check that avahi-daemon (Linux) or mDNSResponder (macOS) is running")

        except ImportError:
            firewall_issues.append("zeroconf library not installed")
            recommendations.append("Install zeroconf: pip install zeroconf")
        except Exception as e:
            logger.warning(f"mDNS test failed: {e}", extra={"diagnostic_category": "mdns"})
            firewall_issues.append(f"mDNS test error: {str(e)}")

        # Test 2: Port accessibility check
        try:
            bind_address = self.config.bind_address
            test_host = "127.0.0.1" if bind_address == "0.0.0.0" else bind_address
            test_port = self.config.port

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((test_host, test_port))
            sock.close()

            if result == 0:
                port_accessible = True
            else:
                port_accessible = False
                firewall_issues.append(f"TCP port {test_port} not accessible")
                recommendations.append(f"Ensure TCP port {test_port} is open in your firewall")
                if bind_address != "0.0.0.0":
                    recommendations.append(f"Verify bind address {bind_address} is correct for your network")

        except Exception as e:
            logger.warning(f"Port accessibility test failed: {e}", extra={"diagnostic_category": "network"})
            firewall_issues.append(f"Port test error: {str(e)}")

        # Add general recommendations if issues detected
        if not self.is_running:
            recommendations.insert(0, "HomeKit bridge is not running - enable it first")

        if not mdns_visible and self.is_running:
            recommendations.append("Try restarting the HomeKit bridge")
            if self.config.mdns_interface:
                recommendations.append(f"Verify mDNS interface '{self.config.mdns_interface}' is correct")

        end_time = time.time()
        test_duration_ms = int((end_time - start_time) * 1000)

        logger.info(
            f"HomeKit connectivity test completed: mDNS={mdns_visible}, port={port_accessible}",
            extra={
                "diagnostic_category": "network",
                "mdns_visible": mdns_visible,
                "port_accessible": port_accessible,
                "test_duration_ms": test_duration_ms
            }
        )

        return HomeKitConnectivityTestResponse(
            mdns_visible=mdns_visible,
            discovered_as=discovered_as,
            port_accessible=port_accessible,
            network_binding=self._network_binding,
            firewall_issues=firewall_issues,
            recommendations=recommendations,
            test_duration_ms=test_duration_ms,
        )

    def _get_connected_client_count(self) -> int:
        """Get the number of connected HomeKit clients (Story P7-1.1)."""
        if not self._driver or not self.is_running:
            return 0
        try:
            # Check for active connections via state file
            state_file = Path(self.config.persist_file)
            if state_file.exists():
                import json
                with open(state_file, 'r') as f:
                    state_data = json.load(f)
                paired_clients = state_data.get('paired_clients', [])
                return len(paired_clients)
            return 0
        except Exception:
            return 0

    async def start(self, cameras: List[Any]) -> bool:
        """
        Start the HomeKit accessory server.

        Args:
            cameras: List of Camera model instances to expose as motion sensors

        Returns:
            True if started successfully, False otherwise
        """
        if not self.config.enabled:
            logger.info(
                "HomeKit integration is disabled",
                extra={"diagnostic_category": "lifecycle"}
            )
            return False

        if not HAP_AVAILABLE:
            self._error = "HAP-python not installed"
            logger.error(
                "HAP-python not installed. Install with: pip install HAP-python",
                extra={"diagnostic_category": "lifecycle"}
            )
            return False

        if self._running:
            logger.warning(
                "HomeKit service already running",
                extra={"diagnostic_category": "lifecycle"}
            )
            return True

        try:
            # Story P7-1.1: Log lifecycle start
            logger.info(
                "Starting HomeKit bridge initialization",
                extra={"diagnostic_category": "lifecycle"}
            )

            # Ensure persistence directory exists
            self.config.ensure_persist_dir()

            # Story P5-1.3: Check ffmpeg availability for camera streaming
            ffmpeg_available, ffmpeg_msg = check_ffmpeg_available()
            self._ffmpeg_available = ffmpeg_available
            if ffmpeg_available:
                logger.info(
                    f"ffmpeg check: {ffmpeg_msg}",
                    extra={"diagnostic_category": "lifecycle"}
                )
            else:
                logger.warning(
                    f"ffmpeg not available - camera streaming disabled: {ffmpeg_msg}",
                    extra={"diagnostic_category": "lifecycle"}
                )

            # Create accessory driver with network binding configuration (Story P7-1.2)
            # HAP-python AccessoryDriver accepts address parameter for binding
            driver_kwargs = {
                "port": self.config.port,
                "persist_file": self.config.persist_file,
                "pincode": self.pincode.encode('utf-8'),
            }

            # Story P7-1.2 AC3, AC4: Configure bind address if not default
            bind_address = self.config.bind_address
            if bind_address and bind_address != "0.0.0.0":
                driver_kwargs["address"] = bind_address
                logger.info(
                    f"HomeKit HAP server binding to specific address: {bind_address}",
                    extra={"diagnostic_category": "network", "bind_address": bind_address}
                )

            self._driver = AccessoryDriver(**driver_kwargs)

            # Story P7-1.1 AC4: Log network binding information
            self._network_binding = NetworkBindingInfo(
                ip=self.config.bind_address,
                port=self.config.port,
                interface=self.config.mdns_interface
            )
            logger.info(
                f"HomeKit HAP server binding to {self.config.bind_address}:{self.config.port}",
                extra={
                    "diagnostic_category": "network",
                    "port": self.config.port,
                    "ip": self.config.bind_address,
                    "interface": self.config.mdns_interface
                }
            )

            # Create bridge accessory
            self._bridge = Bridge(self._driver, self.config.bridge_name)

            # Add camera motion sensors and camera accessories
            for camera in cameras:
                if hasattr(camera, 'enabled') and not camera.enabled:
                    continue  # Skip disabled cameras

                camera_id = camera.id if hasattr(camera, 'id') else str(camera)
                camera_name = camera.name if hasattr(camera, 'name') else f"Camera {camera_id[:8]}"

                # Add motion sensor
                sensor = create_motion_sensor(
                    driver=self._driver,
                    camera_id=camera_id,
                    camera_name=f"{camera_name} Motion",  # Distinguish from camera accessory
                    manufacturer=self.config.manufacturer,
                )

                if sensor:
                    self._sensors[camera_id] = sensor
                    self._bridge.add_accessory(sensor.accessory)

                    # Story P4-6.2 AC4: Register MAC address mapping for Protect cameras
                    if hasattr(camera, 'mac_address') and camera.mac_address:
                        self.register_camera_mapping(camera_id, camera.mac_address)

                    logger.info(f"Added HomeKit motion sensor for camera: {camera_name}")

                # Story P5-1.5: Add occupancy sensor for person detection
                occupancy_sensor = create_occupancy_sensor(
                    driver=self._driver,
                    camera_id=camera_id,
                    camera_name=f"{camera_name} Occupancy",  # Distinct from motion sensor
                    manufacturer=self.config.manufacturer,
                )

                if occupancy_sensor:
                    self._occupancy_sensors[camera_id] = occupancy_sensor
                    self._bridge.add_accessory(occupancy_sensor.accessory)
                    logger.info(f"Added HomeKit occupancy sensor for camera: {camera_name}")

                # Story P5-1.6: Add vehicle/animal/package sensors for detection-type-specific automations
                vehicle_sensor = create_vehicle_sensor(
                    driver=self._driver,
                    camera_id=camera_id,
                    camera_name=f"{camera_name} Vehicle",
                    manufacturer=self.config.manufacturer,
                )
                if vehicle_sensor:
                    self._vehicle_sensors[camera_id] = vehicle_sensor
                    self._bridge.add_accessory(vehicle_sensor.accessory)
                    logger.info(f"Added HomeKit vehicle sensor for camera: {camera_name}")

                animal_sensor = create_animal_sensor(
                    driver=self._driver,
                    camera_id=camera_id,
                    camera_name=f"{camera_name} Animal",
                    manufacturer=self.config.manufacturer,
                )
                if animal_sensor:
                    self._animal_sensors[camera_id] = animal_sensor
                    self._bridge.add_accessory(animal_sensor.accessory)
                    logger.info(f"Added HomeKit animal sensor for camera: {camera_name}")

                package_sensor = create_package_sensor(
                    driver=self._driver,
                    camera_id=camera_id,
                    camera_name=f"{camera_name} Package",
                    manufacturer=self.config.manufacturer,
                )
                if package_sensor:
                    self._package_sensors[camera_id] = package_sensor
                    self._bridge.add_accessory(package_sensor.accessory)
                    logger.info(f"Added HomeKit package sensor for camera: {camera_name}")

                # Story P7-2.3: Add per-carrier package sensors if enabled
                if self.config.per_carrier_sensors:
                    self._create_carrier_sensors(camera_id, camera_name)

                # Story P5-1.7: Add doorbell sensor only for doorbell cameras
                if hasattr(camera, 'is_doorbell') and camera.is_doorbell:
                    doorbell_sensor = create_doorbell_sensor(
                        driver=self._driver,
                        camera_id=camera_id,
                        camera_name=f"{camera_name} Doorbell",
                        manufacturer=self.config.manufacturer,
                    )
                    if doorbell_sensor:
                        self._doorbell_sensors[camera_id] = doorbell_sensor
                        self._bridge.add_accessory(doorbell_sensor.accessory)
                        logger.info(f"Added HomeKit doorbell sensor for camera: {camera_name}")

                # Story P5-1.3, P7-3.1: Add camera accessory for streaming (only if ffmpeg available)
                if self._ffmpeg_available:
                    rtsp_url = self._get_camera_rtsp_url(camera)
                    if rtsp_url:
                        # P7-3.1: Get stream quality from camera model (default: medium)
                        stream_quality = getattr(camera, 'homekit_stream_quality', 'medium') or 'medium'
                        camera_accessory = create_camera_accessory(
                            driver=self._driver,
                            camera_id=camera_id,
                            camera_name=camera_name,
                            rtsp_url=rtsp_url,
                            manufacturer=self.config.manufacturer,
                            stream_quality=stream_quality,
                        )

                        if camera_accessory:
                            self._cameras[camera_id] = camera_accessory
                            self._bridge.add_accessory(camera_accessory.accessory)
                            logger.info(f"Added HomeKit camera accessory for: {camera_name}")
                    else:
                        logger.debug(f"No RTSP URL available for camera {camera_name}, skipping camera accessory")

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
            self._mdns_advertising = True  # Story P7-1.1: Track mDNS state

            # Story P7-1.1 AC1: Log lifecycle completion with full details
            # Story P7-2.3: Include carrier sensor count
            logger.info(
                f"HomeKit accessory server started on port {self.config.port} "
                f"with {len(self._sensors)} motion sensors, {len(self._occupancy_sensors)} occupancy sensors, "
                f"{len(self._doorbell_sensors)} doorbell sensors, {len(self._carrier_sensors)} carrier sensors, "
                f"and {len(self._cameras)} cameras",
                extra={
                    "diagnostic_category": "lifecycle",
                    "port": self.config.port,
                    "motion_count": len(self._sensors),
                    "occupancy_count": len(self._occupancy_sensors),
                    "doorbell_count": len(self._doorbell_sensors),
                    "carrier_sensor_count": len(self._carrier_sensors),
                    "camera_count": len(self._cameras),
                    "per_carrier_sensors_enabled": self.config.per_carrier_sensors,
                }
            )

            # Story P7-1.1: Log mDNS advertisement status
            logger.info(
                "HomeKit mDNS advertisement started",
                extra={"diagnostic_category": "mdns"}
            )

            return True

        except Exception as e:
            self._error = str(e)
            logger.error(
                f"Failed to start HomeKit service: {e}",
                exc_info=True,
                extra={"diagnostic_category": "lifecycle"}
            )
            return False

    def _run_driver(self) -> None:
        """Run the accessory driver in a separate thread (Story P7-1.1 AC1)."""
        try:
            logger.debug(
                "HomeKit HAP driver thread starting",
                extra={"diagnostic_category": "lifecycle"}
            )
            self._driver.start()
        except Exception as e:
            self._error = str(e)
            self._mdns_advertising = False  # Story P7-1.1: Track mDNS state
            logger.error(
                f"HomeKit driver error: {e}",
                exc_info=True,
                extra={"diagnostic_category": "lifecycle"}
            )
            self._running = False

    async def stop(self) -> None:
        """Stop the HomeKit accessory server (Story P7-1.1 AC1)."""
        if not self._running:
            return

        # Story P7-1.1 AC1: Log lifecycle stop
        logger.info(
            "Stopping HomeKit accessory server",
            extra={"diagnostic_category": "lifecycle"}
        )

        try:
            # Story P4-6.2: Cancel all motion reset timers
            for camera_id in list(self._motion_reset_tasks.keys()):
                self._cancel_reset_timer(camera_id)
            self._motion_reset_tasks.clear()
            self._motion_start_times.clear()

            # Story P5-1.5: Cancel all occupancy reset timers
            for camera_id in list(self._occupancy_reset_tasks.keys()):
                self._cancel_occupancy_reset_timer(camera_id)
            self._occupancy_reset_tasks.clear()
            self._occupancy_start_times.clear()

            # Story P5-1.6: Cancel all vehicle/animal/package reset timers
            for camera_id in list(self._vehicle_reset_tasks.keys()):
                self._cancel_vehicle_reset_timer(camera_id)
            for camera_id in list(self._animal_reset_tasks.keys()):
                self._cancel_animal_reset_timer(camera_id)
            for camera_id in list(self._package_reset_tasks.keys()):
                self._cancel_package_reset_timer(camera_id)
            self._vehicle_reset_tasks.clear()
            self._animal_reset_tasks.clear()
            self._package_reset_tasks.clear()

            # Story P5-1.3: Clean up all camera streams
            HomeKitCameraAccessory.cleanup_all_streams()

            if self._driver:
                self._driver.stop()

            if self._driver_thread:
                self._driver_thread.join(timeout=5.0)

            self._running = False
            self._driver = None
            self._bridge = None
            self._sensors.clear()
            self._occupancy_sensors.clear()  # Story P5-1.5: Clear occupancy sensors
            self._vehicle_sensors.clear()  # Story P5-1.6: Clear vehicle sensors
            self._animal_sensors.clear()  # Story P5-1.6: Clear animal sensors
            self._package_sensors.clear()  # Story P5-1.6: Clear package sensors
            self._doorbell_sensors.clear()  # Story P5-1.7: Clear doorbell sensors
            self._cameras.clear()  # Story P5-1.3: Clear camera accessories
            self._camera_id_mapping.clear()

            # Story P7-1.1: Update state tracking
            self._mdns_advertising = False
            self._network_binding = None

            logger.info(
                "HomeKit accessory server stopped",
                extra={"diagnostic_category": "lifecycle"}
            )

        except Exception as e:
            logger.error(
                f"Error stopping HomeKit service: {e}",
                exc_info=True,
                extra={"diagnostic_category": "lifecycle"}
            )

    def _get_camera_rtsp_url(self, camera: Any) -> Optional[str]:
        """
        Get RTSP URL for a camera (Story P5-1.3).

        Supports RTSP cameras and Protect cameras with RTSP enabled.

        Args:
            camera: Camera model instance

        Returns:
            RTSP URL string or None if not available
        """
        # Check for direct RTSP URL
        if hasattr(camera, 'rtsp_url') and camera.rtsp_url:
            return camera.rtsp_url

        # Check source type - USB cameras don't have RTSP
        if hasattr(camera, 'source_type') and camera.source_type == 'usb':
            return None

        # For Protect cameras, construct RTSP URL if available
        # Protect RTSP format: rtsp://host:7447/camera_id
        if hasattr(camera, 'source_type') and camera.source_type == 'protect':
            if hasattr(camera, 'protect_id') and hasattr(camera, 'rtsp_enabled') and camera.rtsp_enabled:
                # Get controller host from the camera's controller
                # This requires the controller to have RTSP enabled
                logger.debug(f"Protect camera {camera.id} - RTSP URL construction not yet implemented")
                return None

        return None

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
        Trigger motion detection for a camera (Story P4-6.2, P7-1.1 AC3).

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
                extra={
                    "diagnostic_category": "event",
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "sensor_type": "motion"
                }
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
                extra={
                    "diagnostic_category": "event",
                    "camera_id": camera_id,
                    "duration": motion_duration,
                    "sensor_type": "motion"
                }
            )
            self._clear_motion_state(resolved_id)
            return True

        # Cancel existing reset timer if any (AC3: rapid events extend motion)
        self._cancel_reset_timer(resolved_id)

        # Start new reset timer
        self._start_reset_timer(resolved_id)

        # Story P7-1.1 AC3: Log characteristic update with sensor details
        logger.info(
            f"HomeKit motion triggered for camera: {sensor.name}",
            extra={
                "diagnostic_category": "event",
                "camera_id": camera_id,
                "event_id": event_id,
                "sensor_type": "motion",
                "reset_seconds": self.config.motion_reset_seconds,
                "delivered": True
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
        """Clear motion state and cleanup tracking for a camera (Story P7-1.1 AC3)."""
        sensor = self._sensors.get(camera_id)
        if sensor:
            sensor.clear_motion()
            # Story P7-1.1 AC3: Log motion reset event
            logger.debug(
                f"HomeKit motion reset for camera: {sensor.name}",
                extra={
                    "diagnostic_category": "event",
                    "camera_id": camera_id,
                    "sensor_type": "motion",
                    "reset_seconds": self.config.motion_reset_seconds
                }
            )

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

    # =========================================================================
    # Story P5-1.5: Occupancy Sensor Methods (Person Detection Only)
    # =========================================================================

    def trigger_occupancy(self, camera_id: str, event_id: Optional[int] = None) -> bool:
        """
        Trigger occupancy detection for a camera (Story P5-1.5).

        Sets occupancy_detected = True and starts/resets the 5-minute auto-clear timer.
        Only called when smart_detection_type == 'person' (filtered in event_processor).
        If called again before timer expires, the timer is reset (extends occupancy period).

        Args:
            camera_id: Camera identifier (UUID or MAC address)
            event_id: Optional event ID for logging

        Returns:
            True if occupancy triggered successfully
        """
        # Resolve camera_id through mapping (for Protect cameras using MAC)
        resolved_id = self._resolve_camera_id(camera_id)
        sensor = self._occupancy_sensors.get(resolved_id)

        if not sensor:
            logger.debug(
                f"No HomeKit occupancy sensor found for camera: {camera_id} (resolved: {resolved_id})",
                extra={"camera_id": camera_id, "event_id": event_id}
            )
            return False

        # Set occupancy detected
        sensor.trigger_occupancy()

        # Track occupancy start time for max duration check (AC3)
        current_time = time.time()
        if resolved_id not in self._occupancy_start_times:
            self._occupancy_start_times[resolved_id] = current_time

        # Check max occupancy duration (AC3: prevent stuck state, default 30 min)
        occupancy_duration = current_time - self._occupancy_start_times[resolved_id]
        if occupancy_duration >= self.config.max_occupancy_duration:
            logger.warning(
                f"Max occupancy duration reached for camera {camera_id}, resetting",
                extra={"camera_id": camera_id, "duration": occupancy_duration}
            )
            self._clear_occupancy_state(resolved_id)
            return True

        # Cancel existing reset timer if any (AC3: rapid events extend occupancy)
        self._cancel_occupancy_reset_timer(resolved_id)

        # Start new reset timer with 5-minute timeout
        self._start_occupancy_reset_timer(resolved_id)

        logger.info(
            f"HomeKit occupancy triggered for camera: {sensor.name}",
            extra={
                "camera_id": camera_id,
                "event_id": event_id,
                "timeout_seconds": self.config.occupancy_timeout_seconds
            }
        )

        return True

    def _cancel_occupancy_reset_timer(self, camera_id: str) -> None:
        """Cancel existing occupancy reset timer for a camera (Story P5-1.5)."""
        if camera_id in self._occupancy_reset_tasks:
            task = self._occupancy_reset_tasks.pop(camera_id)
            if not task.done():
                task.cancel()

    def _start_occupancy_reset_timer(self, camera_id: str) -> None:
        """Start a new occupancy reset timer for a camera (Story P5-1.5 AC3)."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._occupancy_reset_coroutine(camera_id),
                name=f"homekit_occupancy_reset_{camera_id}"
            )
            self._occupancy_reset_tasks[camera_id] = task
        except RuntimeError:
            # No event loop running, log and skip timer
            logger.debug(
                f"Could not start occupancy reset timer for {camera_id} - no running event loop",
                extra={"camera_id": camera_id}
            )

    async def _occupancy_reset_coroutine(self, camera_id: str) -> None:
        """
        Coroutine that waits 5 minutes and then clears occupancy (Story P5-1.5 AC3).

        Args:
            camera_id: Camera identifier
        """
        try:
            await asyncio.sleep(self.config.occupancy_timeout_seconds)
            self._clear_occupancy_state(camera_id)
            logger.debug(
                f"HomeKit occupancy reset for camera after {self.config.occupancy_timeout_seconds}s",
                extra={"camera_id": camera_id}
            )
        except asyncio.CancelledError:
            # Timer was cancelled (new person detection arrived)
            pass

    def _clear_occupancy_state(self, camera_id: str) -> None:
        """Clear occupancy state and cleanup tracking for a camera (Story P5-1.5)."""
        sensor = self._occupancy_sensors.get(camera_id)
        if sensor:
            sensor.clear_occupancy()

        # Clear tracking
        self._occupancy_start_times.pop(camera_id, None)
        self._occupancy_reset_tasks.pop(camera_id, None)

    def clear_occupancy(self, camera_id: str) -> bool:
        """
        Clear occupancy detection for a camera (Story P5-1.5).

        Args:
            camera_id: Camera identifier

        Returns:
            True if occupancy cleared successfully
        """
        sensor = self._occupancy_sensors.get(camera_id)
        if sensor:
            sensor.clear_occupancy()
            return True
        return False

    def clear_all_occupancy(self) -> None:
        """Clear occupancy for all cameras (Story P5-1.5 AC3: state sync on restart)."""
        # Cancel all reset timers
        for camera_id in list(self._occupancy_reset_tasks.keys()):
            self._cancel_occupancy_reset_timer(camera_id)

        # Clear all occupancy states
        for camera_id, sensor in self._occupancy_sensors.items():
            sensor.clear_occupancy()
            self._occupancy_start_times.pop(camera_id, None)

        logger.debug("Cleared all HomeKit occupancy states")

    # =========================================================================
    # Story P5-1.6: Vehicle/Animal/Package Sensor Methods
    # =========================================================================

    def trigger_vehicle(self, camera_id: str, event_id: Optional[int] = None) -> bool:
        """
        Trigger vehicle detection for a camera (Story P5-1.6 AC1).

        Sets motion_detected = True and starts auto-reset timer.

        Args:
            camera_id: Camera identifier (UUID or MAC address)
            event_id: Optional event ID for logging

        Returns:
            True if vehicle detection triggered successfully
        """
        resolved_id = self._resolve_camera_id(camera_id)
        sensor = self._vehicle_sensors.get(resolved_id)

        if not sensor:
            logger.debug(
                f"No HomeKit vehicle sensor found for camera: {camera_id}",
                extra={"camera_id": camera_id, "event_id": event_id}
            )
            return False

        sensor.trigger_motion()

        # Cancel existing reset timer if any
        self._cancel_vehicle_reset_timer(resolved_id)

        # Start new reset timer
        self._start_vehicle_reset_timer(resolved_id)

        logger.info(
            f"HomeKit vehicle triggered for camera: {sensor.name}",
            extra={"camera_id": camera_id, "event_id": event_id, "timeout": self.config.vehicle_reset_seconds}
        )

        return True

    def _cancel_vehicle_reset_timer(self, camera_id: str) -> None:
        """Cancel existing vehicle reset timer for a camera."""
        if camera_id in self._vehicle_reset_tasks:
            task = self._vehicle_reset_tasks.pop(camera_id)
            if not task.done():
                task.cancel()

    def _start_vehicle_reset_timer(self, camera_id: str) -> None:
        """Start a new vehicle reset timer for a camera."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._vehicle_reset_coroutine(camera_id),
                name=f"homekit_vehicle_reset_{camera_id}"
            )
            self._vehicle_reset_tasks[camera_id] = task
        except RuntimeError:
            logger.debug(f"Could not start vehicle reset timer - no running event loop")

    async def _vehicle_reset_coroutine(self, camera_id: str) -> None:
        """Coroutine that waits and then clears vehicle detection."""
        try:
            await asyncio.sleep(self.config.vehicle_reset_seconds)
            sensor = self._vehicle_sensors.get(camera_id)
            if sensor:
                sensor.clear_motion()
            self._vehicle_reset_tasks.pop(camera_id, None)
            logger.debug(f"HomeKit vehicle reset for camera after {self.config.vehicle_reset_seconds}s")
        except asyncio.CancelledError:
            pass

    def trigger_animal(self, camera_id: str, event_id: Optional[int] = None) -> bool:
        """
        Trigger animal detection for a camera (Story P5-1.6 AC2).

        Sets motion_detected = True and starts auto-reset timer.

        Args:
            camera_id: Camera identifier (UUID or MAC address)
            event_id: Optional event ID for logging

        Returns:
            True if animal detection triggered successfully
        """
        resolved_id = self._resolve_camera_id(camera_id)
        sensor = self._animal_sensors.get(resolved_id)

        if not sensor:
            logger.debug(
                f"No HomeKit animal sensor found for camera: {camera_id}",
                extra={"camera_id": camera_id, "event_id": event_id}
            )
            return False

        sensor.trigger_motion()

        # Cancel existing reset timer if any
        self._cancel_animal_reset_timer(resolved_id)

        # Start new reset timer
        self._start_animal_reset_timer(resolved_id)

        logger.info(
            f"HomeKit animal triggered for camera: {sensor.name}",
            extra={"camera_id": camera_id, "event_id": event_id, "timeout": self.config.animal_reset_seconds}
        )

        return True

    def _cancel_animal_reset_timer(self, camera_id: str) -> None:
        """Cancel existing animal reset timer for a camera."""
        if camera_id in self._animal_reset_tasks:
            task = self._animal_reset_tasks.pop(camera_id)
            if not task.done():
                task.cancel()

    def _start_animal_reset_timer(self, camera_id: str) -> None:
        """Start a new animal reset timer for a camera."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._animal_reset_coroutine(camera_id),
                name=f"homekit_animal_reset_{camera_id}"
            )
            self._animal_reset_tasks[camera_id] = task
        except RuntimeError:
            logger.debug(f"Could not start animal reset timer - no running event loop")

    async def _animal_reset_coroutine(self, camera_id: str) -> None:
        """Coroutine that waits and then clears animal detection."""
        try:
            await asyncio.sleep(self.config.animal_reset_seconds)
            sensor = self._animal_sensors.get(camera_id)
            if sensor:
                sensor.clear_motion()
            self._animal_reset_tasks.pop(camera_id, None)
            logger.debug(f"HomeKit animal reset for camera after {self.config.animal_reset_seconds}s")
        except asyncio.CancelledError:
            pass

    def trigger_package(
        self,
        camera_id: str,
        event_id: Optional[int] = None,
        delivery_carrier: Optional[str] = None
    ) -> bool:
        """
        Trigger package detection for a camera (Story P5-1.6 AC3, P7-2.3).

        Sets motion_detected = True and starts auto-reset timer.
        Package sensor has a longer timeout (60s) since packages persist.

        Story P7-2.3 adds carrier logging for debugging package deliveries.
        When per_carrier_sensors is enabled, also triggers a carrier-specific sensor.

        Args:
            camera_id: Camera identifier (UUID or MAC address)
            event_id: Optional event ID for logging
            delivery_carrier: Optional carrier name (fedex, ups, usps, amazon, dhl)
                             from carrier extractor service (Story P7-2.3 AC2, AC4)

        Returns:
            True if package detection triggered successfully
        """
        resolved_id = self._resolve_camera_id(camera_id)
        sensor = self._package_sensors.get(resolved_id)

        if not sensor:
            logger.debug(
                f"No HomeKit package sensor found for camera: {camera_id}",
                extra={
                    "diagnostic_category": "event",
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "delivery_carrier": delivery_carrier,
                    "sensor_type": "package"
                }
            )
            return False

        sensor.trigger_motion()

        # Cancel existing reset timer if any
        self._cancel_package_reset_timer(resolved_id)

        # Start new reset timer
        self._start_package_reset_timer(resolved_id)

        # Story P7-2.3 AC3: Trigger carrier-specific sensor if configured
        carrier_triggered = False
        if self.config.per_carrier_sensors and delivery_carrier:
            carrier_triggered = self._trigger_carrier_sensor(
                resolved_id, delivery_carrier, event_id
            )

        # Story P7-2.3 AC2, AC4: Log carrier info for debugging
        logger.info(
            f"HomeKit package triggered for camera: {sensor.name}"
            + (f" (carrier: {delivery_carrier})" if delivery_carrier else ""),
            extra={
                "diagnostic_category": "event",
                "camera_id": camera_id,
                "event_id": event_id,
                "sensor_type": "package",
                "delivery_carrier": delivery_carrier,
                "carrier_sensor_triggered": carrier_triggered,
                "timeout": self.config.package_reset_seconds,
                "delivered": True
            }
        )

        return True

    def _trigger_carrier_sensor(
        self,
        camera_id: str,
        carrier: str,
        event_id: Optional[int] = None
    ) -> bool:
        """
        Trigger a carrier-specific package sensor (Story P7-2.3 AC3).

        Args:
            camera_id: Resolved camera identifier
            carrier: Carrier name (fedex, ups, usps, amazon, dhl)
            event_id: Optional event ID for logging

        Returns:
            True if carrier sensor was triggered
        """
        # Generate carrier sensor key
        carrier_key = f"{camera_id}_{carrier}"
        carrier_sensor = self._carrier_sensors.get(carrier_key)

        if not carrier_sensor:
            logger.debug(
                f"No per-carrier sensor found for {carrier} on camera {camera_id}",
                extra={
                    "diagnostic_category": "event",
                    "camera_id": camera_id,
                    "carrier": carrier,
                    "carrier_key": carrier_key,
                    "event_id": event_id
                }
            )
            return False

        carrier_sensor.trigger_motion()

        # Cancel existing carrier reset timer if any
        if carrier_key in self._carrier_reset_tasks:
            task = self._carrier_reset_tasks.pop(carrier_key)
            if not task.done():
                task.cancel()

        # Start new reset timer for carrier sensor
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._carrier_reset_coroutine(carrier_key),
                name=f"homekit_carrier_reset_{carrier_key}"
            )
            self._carrier_reset_tasks[carrier_key] = task
        except RuntimeError:
            logger.debug("Could not start carrier reset timer - no running event loop")

        logger.info(
            f"HomeKit carrier sensor triggered: {carrier_sensor.name}",
            extra={
                "diagnostic_category": "event",
                "camera_id": camera_id,
                "carrier": carrier,
                "sensor_name": carrier_sensor.name,
                "event_id": event_id,
                "timeout": self.config.package_reset_seconds
            }
        )

        return True

    async def _carrier_reset_coroutine(self, carrier_key: str) -> None:
        """Coroutine that waits and then clears carrier package detection."""
        try:
            await asyncio.sleep(self.config.package_reset_seconds)
            sensor = self._carrier_sensors.get(carrier_key)
            if sensor:
                sensor.clear_motion()
            self._carrier_reset_tasks.pop(carrier_key, None)
            logger.debug(
                f"HomeKit carrier sensor reset after {self.config.package_reset_seconds}s",
                extra={"carrier_key": carrier_key}
            )
        except asyncio.CancelledError:
            pass

    def _create_carrier_sensors(self, camera_id: str, camera_name: str) -> None:
        """
        Create per-carrier package sensors for a camera (Story P7-2.3 AC3).

        Creates separate package sensors for each supported carrier:
        - FedEx, UPS, USPS, Amazon, DHL

        Args:
            camera_id: Camera identifier
            camera_name: Camera display name (for sensor naming)
        """
        # Import carrier display names for naming
        from app.services.carrier_extractor import CARRIER_DISPLAY_NAMES

        carriers_created = []
        for carrier_key, carrier_display in CARRIER_DISPLAY_NAMES.items():
            sensor_key = f"{camera_id}_{carrier_key}"
            sensor_name = f"{camera_name} {carrier_display} Package"

            # Reuse existing CameraPackageSensor with carrier-specific name
            carrier_sensor = create_package_sensor(
                driver=self._driver,
                camera_id=sensor_key,  # Use composite key for uniqueness
                camera_name=sensor_name,
                manufacturer=self.config.manufacturer,
            )
            if carrier_sensor:
                self._carrier_sensors[sensor_key] = carrier_sensor
                self._bridge.add_accessory(carrier_sensor.accessory)
                carriers_created.append(carrier_display)

        if carriers_created:
            logger.info(
                f"Added HomeKit per-carrier package sensors for camera: {camera_name} "
                f"(carriers: {', '.join(carriers_created)})",
                extra={
                    "diagnostic_category": "lifecycle",
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "carriers": carriers_created,
                    "carrier_count": len(carriers_created)
                }
            )

    def _cancel_package_reset_timer(self, camera_id: str) -> None:
        """Cancel existing package reset timer for a camera."""
        if camera_id in self._package_reset_tasks:
            task = self._package_reset_tasks.pop(camera_id)
            if not task.done():
                task.cancel()

    def _start_package_reset_timer(self, camera_id: str) -> None:
        """Start a new package reset timer for a camera."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._package_reset_coroutine(camera_id),
                name=f"homekit_package_reset_{camera_id}"
            )
            self._package_reset_tasks[camera_id] = task
        except RuntimeError:
            logger.debug(f"Could not start package reset timer - no running event loop")

    async def _package_reset_coroutine(self, camera_id: str) -> None:
        """Coroutine that waits and then clears package detection."""
        try:
            await asyncio.sleep(self.config.package_reset_seconds)
            sensor = self._package_sensors.get(camera_id)
            if sensor:
                sensor.clear_motion()
            self._package_reset_tasks.pop(camera_id, None)
            logger.debug(f"HomeKit package reset for camera after {self.config.package_reset_seconds}s")
        except asyncio.CancelledError:
            pass

    def clear_all_detection_sensors(self) -> None:
        """Clear all vehicle/animal/package sensors (Story P5-1.6)."""
        # Cancel all reset timers
        for camera_id in list(self._vehicle_reset_tasks.keys()):
            self._cancel_vehicle_reset_timer(camera_id)
        for camera_id in list(self._animal_reset_tasks.keys()):
            self._cancel_animal_reset_timer(camera_id)
        for camera_id in list(self._package_reset_tasks.keys()):
            self._cancel_package_reset_timer(camera_id)

        # Clear all sensor states
        for sensor in self._vehicle_sensors.values():
            sensor.clear_motion()
        for sensor in self._animal_sensors.values():
            sensor.clear_motion()
        for sensor in self._package_sensors.values():
            sensor.clear_motion()

        logger.debug("Cleared all HomeKit detection sensor states")

    # =========================================================================
    # Story P5-1.7: Doorbell Sensor Methods (Protect Doorbell Ring Events)
    # =========================================================================

    def trigger_doorbell(self, camera_id: str, event_id: Optional[int] = None) -> bool:
        """
        Trigger doorbell ring event for a camera (Story P5-1.7).

        Fires a single press event on the StatelessProgrammableSwitch to notify
        all paired HomeKit devices of a doorbell ring. Unlike motion/occupancy sensors,
        doorbell events are stateless - no reset timer is needed.

        Only works for cameras where is_doorbell == True (doorbell sensor must exist).

        Args:
            camera_id: Camera identifier (UUID or MAC address)
            event_id: Optional event ID for logging

        Returns:
            True if doorbell ring triggered successfully, False if sensor not found
        """
        # Resolve camera_id through mapping (for Protect cameras using MAC)
        resolved_id = self._resolve_camera_id(camera_id)
        sensor = self._doorbell_sensors.get(resolved_id)

        if not sensor:
            logger.debug(
                f"No HomeKit doorbell sensor found for camera: {camera_id} (resolved: {resolved_id})",
                extra={"camera_id": camera_id, "event_id": event_id}
            )
            return False

        # Trigger doorbell ring (stateless - fires event immediately)
        sensor.trigger_ring()

        logger.info(
            f"HomeKit doorbell ring triggered for camera: {sensor.name}",
            extra={"camera_id": camera_id, "event_id": event_id}
        )

        return True

    async def get_camera_snapshot(self, camera_id: str) -> Optional[bytes]:
        """
        Get a snapshot from a camera accessory (Story P7-3.2 AC1, AC2).

        Calls the camera's _get_snapshot() method which includes caching (AC3)
        and placeholder fallback for offline cameras (AC4).

        Args:
            camera_id: Camera identifier

        Returns:
            JPEG bytes or None if camera not found
        """
        if not self.is_running:
            logger.warning(
                "Cannot get camera snapshot - HomeKit service not running",
                extra={"camera_id": camera_id}
            )
            return None

        camera = self._cameras.get(camera_id)
        if not camera:
            logger.warning(
                f"Camera not found in HomeKit bridge: {camera_id}",
                extra={"camera_id": camera_id}
            )
            return None

        try:
            # Call the camera's snapshot method (includes caching)
            snapshot = await camera._get_snapshot({"image-width": 640, "image-height": 480})
            logger.debug(
                f"Got snapshot from camera {camera.camera_name}",
                extra={
                    "camera_id": camera_id,
                    "size": len(snapshot) if snapshot else 0,
                    "cached": camera._is_snapshot_cache_valid()
                }
            )
            return snapshot
        except Exception as e:
            logger.error(
                f"Failed to get snapshot from camera {camera_id}: {e}",
                extra={"camera_id": camera_id}
            )
            return None

    def get_stream_diagnostics(self) -> "StreamDiagnostics":
        """
        Get stream diagnostics for all cameras (Story P7-3.3 AC2).

        Returns:
            StreamDiagnostics with per-camera streaming status and totals
        """
        from app.schemas.homekit_diagnostics import StreamDiagnostics, CameraStreamInfo

        cameras_info = []
        total_active = 0

        for camera_id, camera in self._cameras.items():
            diag = camera.get_stream_diagnostics()
            cameras_info.append(CameraStreamInfo(
                camera_id=diag["camera_id"],
                camera_name=diag["camera_name"],
                streaming_enabled=diag["streaming_enabled"],
                snapshot_supported=diag["snapshot_supported"],
                last_snapshot=diag["last_snapshot"],
                active_streams=diag["active_streams"],
                quality=diag["quality"],
            ))
            total_active += diag["active_streams"]

        return StreamDiagnostics(
            cameras=cameras_info,
            total_active_streams=total_active,
            ffmpeg_available=self._ffmpeg_available,
        )

    async def test_camera_stream(self, camera_id: str) -> "StreamTestResponse":
        """
        Test camera streaming capability (Story P7-3.3 AC3).

        Validates RTSP accessibility and ffmpeg compatibility without
        starting an actual stream.

        Args:
            camera_id: Camera identifier to test

        Returns:
            StreamTestResponse with test results and sanitized ffmpeg command
        """
        import time
        import subprocess
        from app.schemas.homekit_diagnostics import StreamTestResponse

        start_time = time.time()

        camera = self._cameras.get(camera_id)
        if not camera:
            return StreamTestResponse(
                success=False,
                rtsp_accessible=False,
                ffmpeg_compatible=False,
                error=f"Camera not found in HomeKit bridge: {camera_id}",
                test_duration_ms=int((time.time() - start_time) * 1000),
            )

        # Test RTSP accessibility using ffprobe
        rtsp_accessible = False
        source_resolution = None
        source_fps = None
        source_codec = None
        ffmpeg_compatible = False
        error_msg = None

        # Get camera's RTSP URL
        rtsp_url = camera.rtsp_url
        stream_config = camera.stream_config

        try:
            # Test 1: Check RTSP stream with ffprobe (10s timeout)
            ffprobe_cmd = [
                "ffprobe",
                "-rtsp_transport", "tcp",
                "-v", "error",
                "-show_entries", "stream=width,height,r_frame_rate,codec_name",
                "-of", "json",
                "-i", rtsp_url,
            ]

            result = subprocess.run(
                ffprobe_cmd,
                capture_output=True,
                timeout=10.0,
            )

            if result.returncode == 0:
                rtsp_accessible = True
                # Parse stream info
                try:
                    import json
                    probe_data = json.loads(result.stdout)
                    streams = probe_data.get("streams", [])
                    for stream in streams:
                        if stream.get("codec_name"):
                            source_codec = stream.get("codec_name")
                            width = stream.get("width")
                            height = stream.get("height")
                            if width and height:
                                source_resolution = f"{width}x{height}"
                            fps_str = stream.get("r_frame_rate", "0/1")
                            if "/" in fps_str:
                                num, den = fps_str.split("/")
                                if int(den) > 0:
                                    source_fps = int(int(num) / int(den))
                            break
                except Exception:
                    pass
            else:
                error_msg = result.stderr.decode("utf-8", errors="replace")[:200]

        except subprocess.TimeoutExpired:
            error_msg = "RTSP probe timeout (10s)"
        except FileNotFoundError:
            error_msg = "ffprobe not found - install ffmpeg"
        except Exception as e:
            error_msg = str(e)[:200]

        # Test 2: Check ffmpeg compatibility
        if rtsp_accessible and not error_msg:
            ffmpeg_compatible = self._ffmpeg_available

        # Build test ffmpeg command (for display, never actually run with SRTP)
        test_session_info = {
            "address": "192.168.1.100",
            "v_port": 51826,
            "v_srtp_key": "test-key-placeholder",
            "v_ssrc": 12345,
        }
        test_cmd, _ = camera._build_ffmpeg_command_with_params(
            test_session_info, {}
        )

        # Sanitize the command for display (Story P7-3.3 AC3)
        sanitized_cmd = HomeKitCameraAccessory.sanitize_ffmpeg_command(test_cmd) if test_cmd else None

        test_duration_ms = int((time.time() - start_time) * 1000)

        success = rtsp_accessible and ffmpeg_compatible and not error_msg

        logger.info(
            f"Stream test completed for camera {camera.camera_name}",
            extra={
                "event_type": "homekit_stream_test",
                "camera_id": camera_id,
                "camera_name": camera.camera_name,
                "success": success,
                "rtsp_accessible": rtsp_accessible,
                "ffmpeg_compatible": ffmpeg_compatible,
                "test_duration_ms": test_duration_ms,
            }
        )

        return StreamTestResponse(
            success=success,
            rtsp_accessible=rtsp_accessible,
            ffmpeg_compatible=ffmpeg_compatible,
            source_resolution=source_resolution,
            source_fps=source_fps,
            source_codec=source_codec,
            target_resolution=f"{stream_config.width}x{stream_config.height}",
            target_fps=stream_config.fps,
            target_bitrate=stream_config.bitrate,
            estimated_latency_ms=500 if success else None,  # Estimate based on P5-1.3 AC2
            ffmpeg_command=sanitized_cmd,
            error=error_msg,
            test_duration_ms=test_duration_ms,
        )

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

    # =========================================================================
    # Story P5-1.8: Pairings Management Methods
    # =========================================================================

    def get_pairings(self) -> List[Dict[str, Any]]:
        """
        Get list of paired HomeKit clients (Story P5-1.8 AC3).

        Reads the state file to extract pairing information for all
        currently paired iOS devices.

        Returns:
            List of dicts with pairing_id, is_admin, permissions for each paired client
        """
        try:
            state_file = Path(self.config.persist_file)
            if not state_file.exists():
                logger.debug("No HomeKit state file found - no pairings")
                return []

            import json
            with open(state_file, 'r') as f:
                state_data = json.load(f)

            paired_clients = state_data.get('paired_clients', [])

            pairings = []
            for client in paired_clients:
                pairing_id = client.get('client_uuid', '')
                permissions = client.get('permissions', 0)

                pairings.append({
                    'pairing_id': pairing_id,
                    'is_admin': permissions == 1,  # 1 = admin, 0 = regular user
                    'permissions': permissions
                })

            logger.debug(
                f"Found {len(pairings)} HomeKit pairings",
                extra={"pairing_count": len(pairings)}
            )

            return pairings

        except Exception as e:
            logger.error(f"Failed to read HomeKit pairings: {e}", exc_info=True)
            return []

    def remove_pairing(self, pairing_id: str) -> bool:
        """
        Remove a specific HomeKit pairing (Story P5-1.8 AC4).

        Removes the pairing for the specified client UUID from the state file.
        The removed device will no longer be able to control accessories.

        Args:
            pairing_id: The client UUID of the pairing to remove

        Returns:
            True if pairing was removed successfully, False otherwise
        """
        try:
            state_file = Path(self.config.persist_file)
            if not state_file.exists():
                logger.warning(f"Cannot remove pairing - no state file exists")
                return False

            import json
            import tempfile

            # Read current state
            with open(state_file, 'r') as f:
                state_data = json.load(f)

            paired_clients = state_data.get('paired_clients', [])
            original_count = len(paired_clients)

            # Filter out the pairing to remove
            updated_clients = [
                client for client in paired_clients
                if client.get('client_uuid') != pairing_id
            ]

            if len(updated_clients) == original_count:
                logger.warning(f"Pairing not found for removal: {pairing_id}")
                return False

            # Update state data
            state_data['paired_clients'] = updated_clients

            # Write atomically (write to temp, then rename)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=state_file.parent,
                suffix='.tmp'
            )
            try:
                with os.fdopen(temp_fd, 'w') as f:
                    json.dump(state_data, f, indent=2)

                # Atomic rename
                os.replace(temp_path, state_file)

                logger.info(
                    f"Removed HomeKit pairing: {pairing_id}",
                    extra={
                        "event_type": "homekit_pairing_removed",
                        "pairing_id": pairing_id,
                        "remaining_pairings": len(updated_clients)
                    }
                )

                return True

            except Exception:
                # Clean up temp file on error
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

        except Exception as e:
            logger.error(f"Failed to remove HomeKit pairing: {e}", exc_info=True)
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
