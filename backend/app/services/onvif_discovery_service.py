"""
ONVIF WS-Discovery Service (Stories P5-2.1, P5-2.2)

Discovers ONVIF-compatible cameras on the local network using WS-Discovery protocol.
Sends UDP multicast probes to 239.255.255.250:3702 and collects ProbeMatch responses.
Queries discovered devices for detailed information via ONVIF SOAP (P5-2.2).

Usage:
    service = ONVIFDiscoveryService()
    devices = await service.discover_cameras(timeout=10)
    details = await service.get_device_details("http://192.168.1.100/onvif/device_service")

Architecture Reference: docs/architecture/phase-5-additions.md (ONVIF Discovery Architecture)
PRD Reference: docs/PRD-phase5.md (FR13, FR14, FR15)
"""
import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime
from typing import List, Optional, Set, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse, quote

import cv2

from app.schemas.discovery import (
    DiscoveredDevice,
    DeviceInfo,
    StreamProfile,
    DiscoveredCameraDetails,
    TestConnectionResponse,
)

logger = logging.getLogger(__name__)

# Try to import WSDiscovery
try:
    from wsdiscovery import WSDiscovery
    from wsdiscovery.discovery import ThreadedWSDiscovery
    from wsdiscovery import QName  # For type-based filtering
    WSDISCOVERY_AVAILABLE = True
except ImportError:
    WSDISCOVERY_AVAILABLE = False
    QName = None
    logger.warning("WSDiscovery not installed. ONVIF camera discovery will be unavailable.")

# Try to import onvif-zeep for device details (P5-2.2)
try:
    from onvif import ONVIFCamera
    from zeep.exceptions import Fault as ZeepFault
    ONVIF_ZEEP_AVAILABLE = True
except ImportError:
    ONVIF_ZEEP_AVAILABLE = False
    ONVIFCamera = None
    ZeepFault = Exception  # Fallback type for exception handling
    logger.warning("onvif-zeep not installed. Device details query will be unavailable.")


# WS-Discovery constants per spec
MULTICAST_GROUP = "239.255.255.250"
MULTICAST_PORT = 3702
DEFAULT_TIMEOUT = 10  # seconds

# ONVIF-specific types to search for
# NetworkVideoTransmitter (NVT) is the main camera type
ONVIF_NVT_TYPE = "dn:NetworkVideoTransmitter"
ONVIF_NVT_ALT_TYPE = "tdn:NetworkVideoTransmitter"

# ONVIF scope patterns
ONVIF_SCOPE_PREFIX = "onvif://www.onvif.org"

# Device details constants (P5-2.2)
DEVICE_QUERY_TIMEOUT = 5  # seconds per device query
MAX_CONCURRENT_QUERIES = 10  # max parallel device queries

# Test connection constants (P5-2.4)
TEST_CONNECTION_TIMEOUT = 5.0  # seconds for RTSP connection test


@dataclass
class DiscoveryResult:
    """Internal result from discovery operation."""
    devices: List[DiscoveredDevice] = field(default_factory=list)
    duration_ms: int = 0
    error: Optional[str] = None
    status: str = "complete"


@dataclass
class DeviceDetailsResult:
    """Internal result from device details query (P5-2.2)."""
    device: Optional[DiscoveredCameraDetails] = None
    duration_ms: int = 0
    error: Optional[str] = None
    status: str = "success"  # success, auth_required, error


class ONVIFDiscoveryService:
    """
    ONVIF WS-Discovery service for camera auto-discovery.

    Uses WS-Discovery protocol to find ONVIF-compatible network cameras.
    Discovery process:
    1. Send WS-Discovery Probe message to UDP multicast address
    2. Wait for ProbeMatch responses from devices
    3. Parse responses and extract device service URLs
    4. Deduplicate devices found on multiple network interfaces

    Example:
        >>> service = ONVIFDiscoveryService()
        >>> devices = await service.discover_cameras(timeout=10)
        >>> for device in devices:
        ...     print(f"Found: {device.endpoint_url}")
    """

    def __init__(self):
        """Initialize the discovery service."""
        self._discovery_lock = asyncio.Lock()
        self._last_discovery_time: Optional[float] = None
        self._cached_devices: List[DiscoveredDevice] = []
        self._cache_ttl = 30  # seconds - cache discovery results briefly

    @property
    def is_available(self) -> bool:
        """Check if WS-Discovery library is available."""
        return WSDISCOVERY_AVAILABLE

    @property
    def is_device_details_available(self) -> bool:
        """Check if onvif-zeep library is available for device details (P5-2.2)."""
        return ONVIF_ZEEP_AVAILABLE

    async def discover_cameras(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        use_cache: bool = True
    ) -> List[DiscoveredDevice]:
        """
        Discover ONVIF cameras on the local network.

        Sends WS-Discovery probes and collects responses from ONVIF devices.
        Results are cached for a short period to avoid excessive network traffic.

        Args:
            timeout: Discovery timeout in seconds (default: 10)
            use_cache: Whether to use cached results if available (default: True)

        Returns:
            List of discovered ONVIF devices with their service URLs

        Raises:
            RuntimeError: If WS-Discovery library is not available
        """
        if not WSDISCOVERY_AVAILABLE:
            logger.error("WS-Discovery library not installed")
            raise RuntimeError(
                "ONVIF discovery unavailable: WSDiscovery package not installed. "
                "Install with: pip install WSDiscovery"
            )

        # Check cache
        if use_cache and self._is_cache_valid():
            logger.debug(
                f"Returning cached discovery results: {len(self._cached_devices)} devices"
            )
            return self._cached_devices.copy()

        # Use lock to prevent concurrent discovery scans
        async with self._discovery_lock:
            # Double-check cache after acquiring lock
            if use_cache and self._is_cache_valid():
                return self._cached_devices.copy()

            result = await self._run_discovery(timeout)

            # Update cache
            self._cached_devices = result.devices
            self._last_discovery_time = time.time()

            return result.devices

    async def discover_cameras_with_result(
        self,
        timeout: int = DEFAULT_TIMEOUT
    ) -> DiscoveryResult:
        """
        Discover cameras and return full result including timing and errors.

        This is the method used by the API endpoint to get complete response data.

        Args:
            timeout: Discovery timeout in seconds

        Returns:
            DiscoveryResult with devices, duration, status, and any error
        """
        if not WSDISCOVERY_AVAILABLE:
            return DiscoveryResult(
                devices=[],
                duration_ms=0,
                status="error",
                error="ONVIF discovery unavailable: WSDiscovery package not installed"
            )

        async with self._discovery_lock:
            result = await self._run_discovery(timeout)

            # Update cache
            self._cached_devices = result.devices
            self._last_discovery_time = time.time()

            return result

    async def _run_discovery(self, timeout: int) -> DiscoveryResult:
        """
        Execute the actual WS-Discovery scan.

        Uses ThreadedWSDiscovery which handles:
        - Sending probe messages to multicast address
        - Listening on all network interfaces
        - Collecting and deduplicating responses

        Args:
            timeout: Maximum time to wait for responses

        Returns:
            DiscoveryResult with found devices
        """
        start_time = time.time()

        try:
            logger.info(
                f"Starting ONVIF discovery scan (timeout: {timeout}s, "
                f"multicast: {MULTICAST_GROUP}:{MULTICAST_PORT})"
            )

            # Run blocking discovery in thread pool
            devices = await asyncio.get_event_loop().run_in_executor(
                None,
                self._sync_discover,
                timeout
            )

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Discovery complete: found {len(devices)} ONVIF device(s) "
                f"in {duration_ms}ms"
            )

            return DiscoveryResult(
                devices=devices,
                duration_ms=duration_ms,
                status="complete"
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Discovery failed: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return DiscoveryResult(
                devices=[],
                duration_ms=duration_ms,
                status="error",
                error=error_msg
            )

    def _sync_discover(self, timeout: int) -> List[DiscoveredDevice]:
        """
        Synchronous discovery using WSDiscovery library.

        This runs in a thread pool to avoid blocking the event loop.

        Args:
            timeout: Discovery timeout in seconds

        Returns:
            List of discovered devices
        """
        wsd = ThreadedWSDiscovery()
        discovered_devices: List[DiscoveredDevice] = []
        seen_endpoints: Set[str] = set()  # For deduplication

        try:
            wsd.start()

            # Search for ONVIF Network Video Transmitters
            # Build QName types for proper filtering (Python 3.13 compatibility)
            search_types = None
            if QName is not None:
                try:
                    # ONVIF NetworkVideoTransmitter namespace and local name
                    # Namespace: http://www.onvif.org/ver10/network/wsdl
                    nvt_qname = QName(
                        "http://www.onvif.org/ver10/network/wsdl",
                        "NetworkVideoTransmitter"
                    )
                    search_types = [nvt_qname]
                except Exception as qname_err:
                    logger.debug(f"Could not create QName filter: {qname_err}")
                    # Fall back to searching all devices

            services = wsd.searchServices(
                timeout=timeout,
                types=search_types
            )

            logger.debug(f"WS-Discovery returned {len(services)} service(s)")

            for service in services:
                try:
                    # Get XAddrs (service endpoints)
                    xaddrs = service.getXAddrs()
                    if not xaddrs:
                        continue

                    # Use first endpoint URL
                    endpoint_url = xaddrs[0]

                    # Skip if already seen (deduplication)
                    if endpoint_url in seen_endpoints:
                        logger.debug(f"Skipping duplicate endpoint: {endpoint_url}")
                        continue

                    seen_endpoints.add(endpoint_url)

                    # Extract scopes
                    scopes = []
                    raw_scopes = service.getScopes()
                    if raw_scopes:
                        scopes = [str(s) for s in raw_scopes]

                    # Extract types
                    types = []
                    raw_types = service.getTypes()
                    if raw_types:
                        types = [str(t) for t in raw_types]

                    # Get metadata version if available
                    metadata_version = None
                    try:
                        metadata_version = str(service.getMetadataVersion())
                    except Exception:
                        pass

                    device = DiscoveredDevice(
                        endpoint_url=endpoint_url,
                        scopes=scopes,
                        types=types,
                        metadata_version=metadata_version
                    )

                    discovered_devices.append(device)
                    logger.debug(
                        f"Discovered ONVIF device: {endpoint_url} "
                        f"(types: {types}, scopes: {len(scopes)})"
                    )

                except Exception as e:
                    logger.warning(f"Error parsing discovery response: {e}")
                    continue

        finally:
            try:
                wsd.stop()
            except Exception as e:
                logger.warning(f"Error stopping WS-Discovery: {e}")

        return discovered_devices

    def _is_cache_valid(self) -> bool:
        """Check if cached results are still valid."""
        if self._last_discovery_time is None:
            return False
        return (time.time() - self._last_discovery_time) < self._cache_ttl

    def clear_cache(self) -> None:
        """Clear cached discovery results."""
        self._cached_devices = []
        self._last_discovery_time = None
        logger.debug("Discovery cache cleared")

    # =========================================================================
    # Device Details Methods (Story P5-2.2)
    # =========================================================================

    async def get_device_details(
        self,
        endpoint_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> DeviceDetailsResult:
        """
        Query a discovered ONVIF device for detailed information.

        Uses ONVIF SOAP protocol to retrieve device info, media profiles,
        and stream URIs.

        Args:
            endpoint_url: ONVIF device service URL from discovery
            username: Optional username for authentication
            password: Optional password for authentication

        Returns:
            DeviceDetailsResult with device details or error

        Example:
            >>> result = await service.get_device_details(
            ...     "http://192.168.1.100/onvif/device_service",
            ...     username="admin",
            ...     password="password123"
            ... )
            >>> if result.status == "success":
            ...     print(f"Found: {result.device.device_info.manufacturer}")
        """
        if not ONVIF_ZEEP_AVAILABLE:
            logger.error("onvif-zeep library not installed")
            return DeviceDetailsResult(
                status="error",
                error="Device details unavailable: onvif-zeep package not installed. "
                      "Install with: pip install onvif-zeep"
            )

        start_time = time.time()

        try:
            logger.info(f"Querying device details for: {endpoint_url}")

            # Parse endpoint URL to extract host and port
            host, port = self._parse_endpoint_url(endpoint_url)
            if not host:
                return DeviceDetailsResult(
                    status="error",
                    error=f"Invalid endpoint URL: {endpoint_url}",
                    duration_ms=int((time.time() - start_time) * 1000)
                )

            # Run blocking ONVIF queries in thread pool
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._sync_get_device_details,
                host,
                port,
                username or "",
                password or "",
                endpoint_url
            )

            duration_ms = int((time.time() - start_time) * 1000)
            result.duration_ms = duration_ms

            if result.status == "success":
                logger.info(
                    f"Device details retrieved: {result.device.device_info.manufacturer} "
                    f"{result.device.device_info.model} ({duration_ms}ms)"
                )
            else:
                logger.warning(f"Device details query failed: {result.error}")

            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Device details query failed: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return DeviceDetailsResult(
                status="error",
                error=error_msg,
                duration_ms=duration_ms
            )

    def _parse_endpoint_url(self, endpoint_url: str) -> Tuple[Optional[str], int]:
        """
        Parse endpoint URL to extract host and port.

        Args:
            endpoint_url: ONVIF endpoint URL (e.g., http://192.168.1.100:80/onvif/device_service)

        Returns:
            Tuple of (host, port) or (None, 0) if invalid
        """
        try:
            parsed = urlparse(endpoint_url)
            host = parsed.hostname
            port = parsed.port or 80  # Default to 80 if not specified
            return host, port
        except Exception as e:
            logger.warning(f"Failed to parse endpoint URL {endpoint_url}: {e}")
            return None, 0

    def _generate_camera_id(self, ip_address: str, port: int) -> str:
        """
        Generate a unique ID for a camera based on IP and port.

        Args:
            ip_address: Camera IP address
            port: Camera port

        Returns:
            Unique camera ID string
        """
        # Create a deterministic ID from IP and port
        normalized_ip = ip_address.replace(".", "-").replace(":", "-")
        return f"camera-{normalized_ip}-{port}"

    def _sync_get_device_details(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        endpoint_url: str
    ) -> DeviceDetailsResult:
        """
        Synchronous method to query device details via ONVIF SOAP.

        This runs in a thread pool to avoid blocking the event loop.

        Args:
            host: Device IP address
            port: Device port
            username: Authentication username (empty string if none)
            password: Authentication password (empty string if none)
            endpoint_url: Original endpoint URL

        Returns:
            DeviceDetailsResult with device info and profiles
        """
        try:
            # Create ONVIF camera client
            # Use empty string if no credentials to avoid None issues
            camera = ONVIFCamera(
                host=host,
                port=port,
                user=username if username else "",
                passwd=password if password else "",
            )

            # Get device management service
            device_service = camera.create_devicemgmt_service()

            # Call GetDeviceInformation
            try:
                device_info_response = device_service.GetDeviceInformation()
            except ZeepFault as e:
                # Check if authentication is required
                fault_str = str(e).lower()
                if "sender not authorized" in fault_str or "authentication" in fault_str:
                    return DeviceDetailsResult(
                        status="auth_required",
                        error="Authentication required for device information"
                    )
                raise

            # Extract device info
            manufacturer = getattr(device_info_response, "Manufacturer", "Unknown")
            model = getattr(device_info_response, "Model", "Unknown")
            firmware_version = getattr(device_info_response, "FirmwareVersion", None)
            serial_number = getattr(device_info_response, "SerialNumber", None)
            hardware_id = getattr(device_info_response, "HardwareId", None)

            # Determine device name: prefer Manufacturer + Model
            device_name = f"{manufacturer} {model}".strip()
            if device_name == "Unknown Unknown":
                device_name = f"ONVIF Camera ({host})"

            device_info = DeviceInfo(
                name=device_name,
                manufacturer=manufacturer,
                model=model,
                firmware_version=firmware_version,
                serial_number=serial_number,
                hardware_id=hardware_id
            )

            # Get media service and profiles
            profiles = []
            primary_rtsp_url = ""

            try:
                media_service = camera.create_media_service()
                media_profiles = media_service.GetProfiles()

                for profile in media_profiles:
                    try:
                        profile_info = self._extract_profile_info(
                            profile, media_service, host
                        )
                        if profile_info:
                            profiles.append(profile_info)
                    except Exception as profile_err:
                        logger.debug(
                            f"Failed to extract profile {getattr(profile, 'token', 'unknown')}: {profile_err}"
                        )
                        continue

                # Sort profiles by resolution (highest first)
                profiles.sort(key=lambda p: p.width * p.height, reverse=True)

                # Set primary URL to highest resolution profile
                if profiles:
                    primary_rtsp_url = profiles[0].rtsp_url

            except ZeepFault as e:
                fault_str = str(e).lower()
                if "sender not authorized" in fault_str or "authentication" in fault_str:
                    # Partial success - have device info but need auth for streams
                    logger.info(
                        f"Device info retrieved but streams require auth: {host}"
                    )
                else:
                    logger.warning(f"Failed to get media profiles: {e}")
            except Exception as media_err:
                logger.warning(f"Failed to get media profiles: {media_err}")

            # If no profiles found, try to construct a default RTSP URL
            if not primary_rtsp_url:
                primary_rtsp_url = f"rtsp://{host}:554/stream"

            # Build the full camera details
            camera_details = DiscoveredCameraDetails(
                id=self._generate_camera_id(host, port),
                endpoint_url=endpoint_url,
                ip_address=host,
                port=port,
                device_info=device_info,
                profiles=profiles,
                primary_rtsp_url=primary_rtsp_url,
                requires_auth=len(profiles) == 0,  # Assume auth needed if no profiles
                discovered_at=datetime.utcnow()
            )

            return DeviceDetailsResult(
                device=camera_details,
                status="success"
            )

        except ZeepFault as e:
            fault_str = str(e).lower()
            if "sender not authorized" in fault_str or "authentication" in fault_str:
                return DeviceDetailsResult(
                    status="auth_required",
                    error="Authentication required to access this device"
                )
            return DeviceDetailsResult(
                status="error",
                error=f"ONVIF SOAP fault: {str(e)}"
            )
        except Exception as e:
            return DeviceDetailsResult(
                status="error",
                error=f"Failed to query device: {str(e)}"
            )

    def _extract_profile_info(
        self,
        profile,
        media_service,
        host: str
    ) -> Optional[StreamProfile]:
        """
        Extract stream profile information from an ONVIF profile.

        Args:
            profile: ONVIF media profile object
            media_service: Media service client for GetStreamUri
            host: Device host for URL construction

        Returns:
            StreamProfile or None if extraction fails
        """
        try:
            token = getattr(profile, "token", None)
            if not token:
                return None

            name = getattr(profile, "Name", token)

            # Extract video encoder configuration
            video_encoder = getattr(profile, "VideoEncoderConfiguration", None)
            if not video_encoder:
                return None

            resolution = getattr(video_encoder, "Resolution", None)
            width = getattr(resolution, "Width", 0) if resolution else 0
            height = getattr(resolution, "Height", 0) if resolution else 0

            rate_control = getattr(video_encoder, "RateControl", None)
            fps = getattr(rate_control, "FrameRateLimit", 30) if rate_control else 30

            encoding = getattr(video_encoder, "Encoding", None)

            # Get stream URI
            stream_setup = {
                'Stream': 'RTP-Unicast',
                'Transport': {'Protocol': 'RTSP'}
            }

            try:
                uri_response = media_service.GetStreamUri({
                    'ProfileToken': token,
                    'StreamSetup': stream_setup
                })
                rtsp_url = getattr(uri_response, "Uri", "")
            except Exception as uri_err:
                logger.debug(f"Failed to get stream URI for profile {token}: {uri_err}")
                # Construct a default URL
                rtsp_url = f"rtsp://{host}:554/stream"

            return StreamProfile(
                name=name,
                token=token,
                resolution=f"{width}x{height}",
                width=width,
                height=height,
                fps=fps,
                rtsp_url=rtsp_url,
                encoding=str(encoding) if encoding else None
            )

        except Exception as e:
            logger.debug(f"Failed to extract profile info: {e}")
            return None

    # =========================================================================
    # Test Connection Methods (Story P5-2.4)
    # =========================================================================

    async def test_connection(
        self,
        rtsp_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> TestConnectionResponse:
        """
        Test an RTSP connection without saving the camera.

        Validates connectivity and retrieves stream metadata (resolution, FPS, codec).
        Times out after 5 seconds to prevent hanging on unresponsive cameras.

        Args:
            rtsp_url: RTSP URL to test (rtsp:// or rtsps://)
            username: Optional username for authentication
            password: Optional password for authentication

        Returns:
            TestConnectionResponse with success status and stream metadata or error

        Example:
            >>> result = await service.test_connection(
            ...     "rtsp://192.168.1.100:554/stream",
            ...     username="admin",
            ...     password="password123"
            ... )
            >>> if result.success:
            ...     print(f"Connected: {result.resolution} @ {result.fps}fps")
        """
        start_time = time.time()

        # Build authenticated URL if credentials provided
        test_url = self._build_authenticated_url(rtsp_url, username, password)

        # Log without exposing password
        sanitized_url = self._sanitize_url_for_logging(rtsp_url)
        logger.info(f"Testing RTSP connection: {sanitized_url}")

        try:
            # Run blocking OpenCV test in thread pool with timeout
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    self._sync_test_connection,
                    test_url
                ),
                timeout=TEST_CONNECTION_TIMEOUT
            )

            latency_ms = int((time.time() - start_time) * 1000)

            if result["success"]:
                logger.info(
                    f"Connection test successful: {sanitized_url} - "
                    f"{result['resolution']} @ {result['fps']}fps ({latency_ms}ms)"
                )
                return TestConnectionResponse(
                    success=True,
                    latency_ms=latency_ms,
                    resolution=result.get("resolution"),
                    fps=result.get("fps"),
                    codec=result.get("codec"),
                    error=None
                )
            else:
                error_msg = self._map_error_message(result.get("error", "Unknown error"))
                logger.warning(f"Connection test failed: {sanitized_url} - {error_msg}")
                return TestConnectionResponse(
                    success=False,
                    latency_ms=latency_ms,
                    error=error_msg
                )

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = "Connection timed out after 5 seconds"
            logger.warning(f"Connection test timed out: {sanitized_url}")
            return TestConnectionResponse(
                success=False,
                latency_ms=latency_ms,
                error=error_msg
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = self._map_error_message(str(e))
            logger.error(f"Connection test error: {sanitized_url} - {e}", exc_info=True)
            return TestConnectionResponse(
                success=False,
                latency_ms=latency_ms,
                error=error_msg
            )

    def _sync_test_connection(self, rtsp_url: str) -> dict:
        """
        Synchronous RTSP connection test using OpenCV.

        Runs in thread pool to avoid blocking the event loop.

        Args:
            rtsp_url: Full RTSP URL (may include embedded credentials)

        Returns:
            Dictionary with success status and stream metadata
        """
        cap = None
        try:
            # Configure OpenCV with timeouts
            cap = cv2.VideoCapture(rtsp_url)

            # Set timeout properties (may not be supported on all backends)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(TEST_CONNECTION_TIMEOUT * 1000))
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(TEST_CONNECTION_TIMEOUT * 1000))

            if not cap.isOpened():
                return {
                    "success": False,
                    "error": "Failed to open RTSP stream"
                }

            # Try to read first frame
            ret, frame = cap.read()
            if not ret or frame is None:
                return {
                    "success": False,
                    "error": "Failed to read frame from stream"
                }

            # Extract stream metadata
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(cap.get(cv2.CAP_PROP_FPS) or 0)

            # Try to determine codec
            fourcc_code = int(cap.get(cv2.CAP_PROP_FOURCC))
            codec = self._fourcc_to_codec_name(fourcc_code)

            return {
                "success": True,
                "resolution": f"{width}x{height}",
                "fps": fps if fps > 0 else None,
                "codec": codec
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

        finally:
            if cap is not None:
                cap.release()

    def _build_authenticated_url(
        self,
        rtsp_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> str:
        """
        Build RTSP URL with embedded credentials if provided.

        Args:
            rtsp_url: Base RTSP URL
            username: Optional username
            password: Optional password

        Returns:
            URL with embedded credentials or original URL if no credentials
        """
        if not username:
            return rtsp_url

        try:
            parsed = urlparse(rtsp_url)

            # URL-encode username and password to handle special characters
            encoded_user = quote(username, safe='')
            encoded_pass = quote(password or '', safe='')

            # Build netloc with credentials
            if password:
                netloc = f"{encoded_user}:{encoded_pass}@{parsed.hostname}"
            else:
                netloc = f"{encoded_user}@{parsed.hostname}"

            if parsed.port:
                netloc += f":{parsed.port}"

            return urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
        except Exception as e:
            logger.warning(f"Failed to build authenticated URL: {e}")
            return rtsp_url

    def _sanitize_url_for_logging(self, rtsp_url: str) -> str:
        """
        Remove password from URL for safe logging.

        Args:
            rtsp_url: Original URL (may contain password)

        Returns:
            URL with password replaced by ***
        """
        try:
            parsed = urlparse(rtsp_url)
            if parsed.password:
                # Replace password with ***
                sanitized_netloc = parsed.netloc.replace(
                    f":{parsed.password}@",
                    ":***@"
                )
                return urlunparse((
                    parsed.scheme,
                    sanitized_netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment
                ))
            return rtsp_url
        except Exception:
            return rtsp_url

    def _fourcc_to_codec_name(self, fourcc_code: int) -> Optional[str]:
        """
        Convert OpenCV FOURCC code to human-readable codec name.

        Args:
            fourcc_code: Integer FOURCC code from OpenCV

        Returns:
            Codec name string or None if unknown
        """
        if fourcc_code == 0:
            return None

        # Common FOURCC codes for RTSP streams
        fourcc_map = {
            # H.264 variants
            0x34363248: "H.264",  # H264
            0x34363261: "H.264",  # avc1
            0x31637661: "H.264",  # avc1 (different byte order)
            # H.265/HEVC
            0x35363248: "H.265",  # H265
            0x31637668: "H.265",  # hvc1
            0x63766568: "H.265",  # hevc
            # MJPEG
            0x47504A4D: "MJPEG",  # MJPG
            # VP8/VP9
            0x30385056: "VP8",    # VP80
            0x30395056: "VP9",    # VP90
        }

        codec = fourcc_map.get(fourcc_code)
        if codec:
            return codec

        # Try to decode as ASCII characters
        try:
            chars = [chr((fourcc_code >> (8 * i)) & 0xFF) for i in range(4)]
            decoded = ''.join(c for c in chars if c.isprintable())
            return decoded if decoded else None
        except Exception:
            return None

    def _map_error_message(self, error: str) -> str:
        """
        Map technical error messages to user-friendly messages.

        Args:
            error: Raw error message

        Returns:
            User-friendly error message
        """
        error_lower = error.lower()

        # Authentication errors
        if "401" in error_lower or "unauthorized" in error_lower or "authentication" in error_lower:
            return "Authentication failed - check username/password"

        # Connection errors
        if "connection refused" in error_lower or "no route" in error_lower:
            return "Connection refused - host unreachable"

        if "timeout" in error_lower or "timed out" in error_lower:
            return "Connection timed out after 5 seconds"

        # Stream not found
        if "404" in error_lower or "not found" in error_lower:
            return "Stream not found - check RTSP path"

        # SSL/TLS errors
        if "ssl" in error_lower or "tls" in error_lower or "certificate" in error_lower:
            return "Secure connection failed - try rtsp:// instead of rtsps://"

        # Failed to open
        if "failed to open" in error_lower:
            return "Failed to connect to RTSP stream"

        # Failed to read frame
        if "failed to read" in error_lower:
            return "Connected but failed to read video frame"

        # Default: return cleaned up error
        return error if len(error) < 100 else error[:97] + "..."


# Singleton instance
_discovery_service: Optional[ONVIFDiscoveryService] = None


def get_onvif_discovery_service() -> ONVIFDiscoveryService:
    """
    Get the singleton ONVIFDiscoveryService instance.

    Returns:
        The shared discovery service instance
    """
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = ONVIFDiscoveryService()
    return _discovery_service
