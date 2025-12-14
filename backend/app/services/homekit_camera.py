"""
HomeKit Camera accessory with RTSP-to-SRTP streaming (Story P5-1.3)

Implements HAP-python Camera class with ffmpeg transcoding for HomeKit streaming.

Stream Flow:
    HomeKit requests stream → start_stream(session_info, stream_config)
            ↓
    Build ffmpeg command with RTSP input and SRTP output
            ↓
    Spawn ffmpeg subprocess
            ↓
    HomeKit ends stream → stop_stream(session_info)
            ↓
    Terminate ffmpeg subprocess cleanly
"""
import asyncio
import logging
import os
import subprocess
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

try:
    from pyhap.camera import Camera
    from pyhap.accessory import Accessory
    from pyhap.const import CATEGORY_CAMERA
    HAP_AVAILABLE = True
except ImportError:
    HAP_AVAILABLE = False
    CATEGORY_CAMERA = 17

logger = logging.getLogger(__name__)

# Story P5-1.3 AC4: Maximum concurrent streams
MAX_CONCURRENT_STREAMS = 2

# Default ffmpeg path
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")


@dataclass
class StreamSession:
    """Tracks an active streaming session."""
    session_id: str
    camera_id: str
    process: Optional[subprocess.Popen] = None
    started_at: Optional[float] = None


class HomeKitCameraAccessory:
    """
    HomeKit Camera accessory for ArgusAI (Story P5-1.3).

    Implements HAP-python Camera with RTSP-to-SRTP transcoding via ffmpeg.

    Features:
    - RTSP input from ArgusAI cameras
    - SRTP output to HomeKit clients
    - H.264 transcoding with configurable quality
    - Concurrent stream limiting (max 2)
    - Automatic process cleanup

    Attributes:
        camera_id: Unique camera identifier
        camera_name: Display name in Home app
        rtsp_url: RTSP stream URL for the camera
        manufacturer: Manufacturer shown in Home app
    """

    # Class-level stream tracking for concurrent limit (AC4)
    _active_stream_count: int = 0
    _stream_lock: threading.Lock = threading.Lock()
    _active_sessions: Dict[str, StreamSession] = {}

    def __init__(
        self,
        driver,
        camera_id: str,
        camera_name: str,
        rtsp_url: str,
        manufacturer: str = "ArgusAI",
        model: str = "Camera",
    ):
        """
        Initialize a HomeKit camera accessory.

        Args:
            driver: HAP-python AccessoryDriver instance
            camera_id: Unique camera identifier
            camera_name: Display name in Home app
            rtsp_url: RTSP stream URL for the camera
            manufacturer: Manufacturer name (default: ArgusAI)
            model: Model name (default: Camera)
        """
        if not HAP_AVAILABLE:
            raise ImportError("HAP-python is not installed. Install with: pip install HAP-python")

        self.camera_id = camera_id
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url
        self.manufacturer = manufacturer
        self.model = model
        self._driver = driver

        # Configure video options for HomeKit
        options = self._get_camera_options()

        # Create Camera accessory
        self._camera = Camera(options, driver, camera_name)
        self._camera.category = CATEGORY_CAMERA

        # Set accessory information
        accessory_info = self._camera.get_service("AccessoryInformation")
        if accessory_info:
            accessory_info.configure_char("Manufacturer", value=manufacturer)
            accessory_info.configure_char("Model", value=model)
            accessory_info.configure_char("SerialNumber", value=camera_id[:20])
            accessory_info.configure_char("FirmwareRevision", value="1.0.0")

        # Override stream methods
        self._camera.start_stream = self._start_stream
        self._camera.stop_stream = self._stop_stream
        self._camera.get_snapshot = self._get_snapshot

        logger.info(f"Created HomeKit camera accessory: {camera_name} ({camera_id})")

    def _get_camera_options(self) -> dict:
        """
        Get HAP-python camera options.

        Returns video configuration for HomeKit including:
        - H.264 codec with baseline/main/high profiles
        - Resolutions up to 1080p30
        - SRTP encryption enabled
        """
        return {
            "video": {
                "codec": {
                    "profiles": [0, 1, 2],  # baseline, main, high
                    "levels": [0, 1, 2],    # 3.1, 3.2, 4.0
                },
                "resolutions": [
                    [1920, 1080, 30],  # 1080p @ 30fps
                    [1280, 720, 30],   # 720p @ 30fps
                    [640, 480, 30],    # 480p @ 30fps
                    [640, 360, 30],    # 360p @ 30fps
                    [480, 270, 30],    # 270p @ 30fps
                    [320, 240, 15],    # 240p @ 15fps
                    [320, 180, 15],    # 180p @ 15fps
                ],
            },
            "audio": {
                "codecs": [],  # Audio disabled for P5-1 (video only)
            },
            "srtp": True,
            "address": "0.0.0.0",
            "stream_count": MAX_CONCURRENT_STREAMS,
        }

    @property
    def accessory(self) -> Any:
        """Get the underlying HAP-python Camera accessory."""
        return self._camera

    @property
    def name(self) -> str:
        """Get the camera display name."""
        return self.camera_name

    async def _start_stream(self, session_info: dict, stream_config: dict) -> bool:
        """
        Start streaming to HomeKit client (Story P5-1.3 AC2, AC3).

        Spawns ffmpeg to transcode RTSP to SRTP.

        Args:
            session_info: Contains client address, ports, SRTP keys
            stream_config: Contains negotiated video settings

        Returns:
            True if stream started successfully
        """
        session_id = session_info.get("session_id", "unknown")

        # AC4: Check concurrent stream limit
        with self._stream_lock:
            if HomeKitCameraAccessory._active_stream_count >= MAX_CONCURRENT_STREAMS:
                logger.warning(
                    f"Max concurrent streams ({MAX_CONCURRENT_STREAMS}) reached, rejecting stream request",
                    extra={"camera_id": self.camera_id, "session_id": session_id}
                )
                return False
            HomeKitCameraAccessory._active_stream_count += 1

        try:
            # Build ffmpeg command
            cmd = self._build_ffmpeg_command(session_info, stream_config)

            if not cmd:
                logger.error(
                    f"Failed to build ffmpeg command for camera {self.camera_id}",
                    extra={"camera_id": self.camera_id, "session_id": session_id}
                )
                self._decrement_stream_count()
                return False

            logger.info(
                f"Starting HomeKit stream for camera {self.camera_name}",
                extra={
                    "camera_id": self.camera_id,
                    "session_id": session_id,
                    "client_address": session_info.get("address"),
                    "video_port": session_info.get("v_port"),
                }
            )

            # AC3: Spawn ffmpeg subprocess
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )

            # Track session
            session = StreamSession(
                session_id=session_id,
                camera_id=self.camera_id,
                process=process,
            )
            HomeKitCameraAccessory._active_sessions[session_id] = session

            # Store process reference for HAP-python
            session_info["process"] = process

            logger.info(
                f"HomeKit stream started for camera {self.camera_name} (PID: {process.pid})",
                extra={
                    "camera_id": self.camera_id,
                    "session_id": session_id,
                    "pid": process.pid,
                }
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to start HomeKit stream: {e}",
                extra={"camera_id": self.camera_id, "session_id": session_id}
            )
            self._decrement_stream_count()
            return False

    async def _stop_stream(self, session_info: dict) -> None:
        """
        Stop streaming to HomeKit client (Story P5-1.3 AC3).

        Terminates ffmpeg subprocess cleanly.

        Args:
            session_info: Contains session details and process reference
        """
        session_id = session_info.get("session_id", "unknown")
        process = session_info.get("process")

        logger.info(
            f"Stopping HomeKit stream for camera {self.camera_name}",
            extra={"camera_id": self.camera_id, "session_id": session_id}
        )

        # Remove from active sessions
        HomeKitCameraAccessory._active_sessions.pop(session_id, None)

        if process:
            try:
                # Try graceful termination first
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful termination fails
                    logger.warning(
                        f"ffmpeg did not terminate gracefully, killing (PID: {process.pid})",
                        extra={"camera_id": self.camera_id, "session_id": session_id}
                    )
                    process.kill()
                    process.wait(timeout=1.0)

                logger.info(
                    f"HomeKit stream stopped for camera {self.camera_name}",
                    extra={"camera_id": self.camera_id, "session_id": session_id}
                )

            except Exception as e:
                logger.error(
                    f"Error stopping ffmpeg process: {e}",
                    extra={"camera_id": self.camera_id, "session_id": session_id}
                )

        # AC4: Decrement stream count
        self._decrement_stream_count()

    def _decrement_stream_count(self) -> None:
        """Safely decrement the active stream count."""
        with self._stream_lock:
            HomeKitCameraAccessory._active_stream_count = max(
                0, HomeKitCameraAccessory._active_stream_count - 1
            )

    def _build_ffmpeg_command(self, session_info: dict, stream_config: dict) -> Optional[List[str]]:
        """
        Build ffmpeg command for RTSP to SRTP transcoding (Story P5-1.3 AC2).

        Args:
            session_info: Client address, ports, SRTP keys
            stream_config: Video settings (resolution, bitrate, fps)

        Returns:
            List of command arguments for subprocess, or None on error
        """
        try:
            # Extract session parameters
            address = session_info.get("address", "127.0.0.1")
            v_port = session_info.get("v_port", 0)
            v_srtp_key = session_info.get("v_srtp_key", "")

            # Extract stream configuration
            width = stream_config.get("width", 1280)
            height = stream_config.get("height", 720)
            fps = stream_config.get("fps", 30)
            v_max_bitrate = stream_config.get("v_max_bitrate", 2000)
            v_ssrc = session_info.get("v_ssrc", 0)

            # Build ffmpeg command
            # AC2: Low-latency transcoding for <500ms additional delay
            cmd = [
                FFMPEG_PATH,
                # Input options
                "-rtsp_transport", "tcp",
                "-i", self.rtsp_url,
                # Video codec settings
                "-an",  # No audio
                "-vcodec", "libx264",
                "-pix_fmt", "yuv420p",
                "-profile:v", "baseline",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                # Bitrate settings
                "-b:v", f"{v_max_bitrate}k",
                "-bufsize", f"{v_max_bitrate}k",
                "-maxrate", f"{v_max_bitrate}k",
                # Frame settings
                "-r", str(fps),
                "-vf", f"scale={width}:{height}",
                # RTP output settings
                "-payload_type", "99",
                "-ssrc", str(v_ssrc),
                "-f", "rtp",
                "-srtp_out_suite", "AES_CM_128_HMAC_SHA1_80",
                "-srtp_out_params", v_srtp_key,
                f"srtp://{address}:{v_port}?rtcpport={v_port}&pkt_size=1316",
            ]

            return cmd

        except Exception as e:
            logger.error(f"Error building ffmpeg command: {e}")
            return None

    async def _get_snapshot(self, image_size: dict) -> bytes:
        """
        Get camera snapshot for HomeKit tiles (Story P5-1.3 AC1).

        Captures a single frame from the RTSP stream.

        Args:
            image_size: Requested image dimensions (width, height)

        Returns:
            JPEG image data as bytes
        """
        import io

        try:
            # Try to capture frame from RTSP
            width = image_size.get("image-width", 640)
            height = image_size.get("image-height", 480)

            # Use ffmpeg to capture a single frame
            cmd = [
                FFMPEG_PATH,
                "-rtsp_transport", "tcp",
                "-i", self.rtsp_url,
                "-frames:v", "1",
                "-vf", f"scale={width}:{height}",
                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "-q:v", "2",
                "-",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=5.0,
            )

            if result.returncode == 0 and result.stdout:
                logger.debug(
                    f"Captured snapshot for camera {self.camera_name}",
                    extra={"camera_id": self.camera_id, "size": len(result.stdout)}
                )
                return result.stdout

            logger.warning(
                f"Failed to capture snapshot from RTSP: {result.stderr.decode()[:200]}",
                extra={"camera_id": self.camera_id}
            )

        except subprocess.TimeoutExpired:
            logger.warning(
                f"Snapshot capture timeout for camera {self.camera_name}",
                extra={"camera_id": self.camera_id}
            )
        except Exception as e:
            logger.error(
                f"Error capturing snapshot: {e}",
                extra={"camera_id": self.camera_id}
            )

        # Return empty JPEG placeholder on failure
        return self._get_placeholder_image(width, height)

    def _get_placeholder_image(self, width: int = 640, height: int = 480) -> bytes:
        """
        Generate a placeholder image when snapshot fails.

        Args:
            width: Image width
            height: Image height

        Returns:
            JPEG bytes for a gray placeholder image
        """
        try:
            from PIL import Image
            import io

            # Create gray placeholder
            img = Image.new("RGB", (width, height), color=(128, 128, 128))

            # Add text overlay
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            text = "Camera Unavailable"
            text_bbox = draw.textbbox((0, 0), text)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            x = (width - text_width) // 2
            y = (height - text_height) // 2
            draw.text((x, y), text, fill=(255, 255, 255))

            # Convert to JPEG bytes
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            buffer.seek(0)
            return buffer.getvalue()

        except Exception:
            # Minimal 1x1 gray JPEG as last resort
            return bytes([
                0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
                0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
                0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
                0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
                0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
                0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
                0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
                0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
                0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
                0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
                0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
                0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
                0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
                0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
                0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
                0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
                0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
                0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
                0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
                0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
                0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
                0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
                0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
                0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
                0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
                0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0x7F, 0xFF, 0xD9
            ])

    @classmethod
    def get_active_stream_count(cls) -> int:
        """Get the current number of active streams."""
        return cls._active_stream_count

    @classmethod
    def cleanup_all_streams(cls) -> None:
        """
        Clean up all active streams (Story P5-1.3 AC3).

        Called during service shutdown to ensure no orphan processes.
        """
        for session_id, session in list(cls._active_sessions.items()):
            if session.process:
                try:
                    session.process.terminate()
                    session.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    session.process.kill()
                except Exception as e:
                    logger.error(f"Error cleaning up stream {session_id}: {e}")

        cls._active_sessions.clear()
        with cls._stream_lock:
            cls._active_stream_count = 0

        logger.info("All HomeKit camera streams cleaned up")


def create_camera_accessory(
    driver,
    camera_id: str,
    camera_name: str,
    rtsp_url: str,
    manufacturer: str = "ArgusAI",
) -> Optional[HomeKitCameraAccessory]:
    """
    Factory function to create a HomeKit camera accessory.

    Args:
        driver: HAP-python AccessoryDriver instance
        camera_id: Unique camera identifier
        camera_name: Display name in Home app
        rtsp_url: RTSP stream URL for the camera
        manufacturer: Manufacturer name (default: ArgusAI)

    Returns:
        HomeKitCameraAccessory instance or None if HAP-python not available
    """
    if not HAP_AVAILABLE:
        logger.warning("HAP-python not available, cannot create HomeKit camera")
        return None

    try:
        return HomeKitCameraAccessory(
            driver=driver,
            camera_id=camera_id,
            camera_name=camera_name,
            rtsp_url=rtsp_url,
            manufacturer=manufacturer,
        )
    except Exception as e:
        logger.error(f"Failed to create camera accessory for {camera_name}: {e}")
        return None


def check_ffmpeg_available() -> Tuple[bool, str]:
    """
    Check if ffmpeg is available and has required capabilities.

    Returns:
        Tuple of (available: bool, message: str)
    """
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-version"],
            capture_output=True,
            timeout=5.0,
        )
        if result.returncode == 0:
            version_line = result.stdout.decode().split('\n')[0]
            return True, f"ffmpeg available: {version_line}"
        return False, f"ffmpeg returned error: {result.stderr.decode()[:100]}"
    except FileNotFoundError:
        return False, f"ffmpeg not found at {FFMPEG_PATH}"
    except subprocess.TimeoutExpired:
        return False, "ffmpeg check timed out"
    except Exception as e:
        return False, f"Error checking ffmpeg: {e}"
