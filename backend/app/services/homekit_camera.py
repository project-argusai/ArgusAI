"""
HomeKit Camera accessory with RTSP-to-SRTP streaming (Story P5-1.3, P7-3.1, P7-3.3)

Implements HAP-python Camera class with ffmpeg transcoding for HomeKit streaming.

Story P7-3.1 adds:
- StreamQuality enum for configurable quality (low, medium, high)
- StreamConfig dataclass for quality-to-settings mapping
- Per-camera quality configuration from database

Story P7-3.3 adds:
- Enhanced stream logging with detailed session info
- Stream duration tracking
- ffmpeg command sanitization for debugging
- Stream diagnostics per camera

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
import re
import subprocess
import threading
import time
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from datetime import datetime

from app.core.metrics import (
    record_homekit_stream_start,
    update_homekit_active_streams,
    update_homekit_total_streams,
    record_homekit_snapshot_cache_hit,
    record_homekit_snapshot_cache_miss,
)

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

# Story P7-3.2 AC3: Snapshot caching duration
SNAPSHOT_CACHE_SECONDS = 5


class StreamQuality(str, Enum):
    """
    HomeKit stream quality levels (Story P7-3.1 AC5).

    Defines resolution, fps, and bitrate for each quality tier.
    Lower quality uses less bandwidth and CPU.
    """
    LOW = "low"      # 640x480, 15fps, 500kbps - Best for slow networks
    MEDIUM = "medium"  # 1280x720, 25fps, 1500kbps - Balanced quality/bandwidth
    HIGH = "high"    # 1920x1080, 30fps, 3000kbps - Best quality, high bandwidth


@dataclass
class StreamConfig:
    """
    Stream configuration settings for a quality level (Story P7-3.1).

    Maps StreamQuality enum values to actual video encoding parameters.
    """
    width: int
    height: int
    fps: int
    bitrate: int  # kbps

    @classmethod
    def from_quality(cls, quality: StreamQuality) -> "StreamConfig":
        """
        Create StreamConfig from a StreamQuality enum value.

        Args:
            quality: StreamQuality enum value (LOW, MEDIUM, HIGH)

        Returns:
            StreamConfig with appropriate resolution, fps, and bitrate
        """
        configs = {
            StreamQuality.LOW: cls(width=640, height=480, fps=15, bitrate=500),
            StreamQuality.MEDIUM: cls(width=1280, height=720, fps=25, bitrate=1500),
            StreamQuality.HIGH: cls(width=1920, height=1080, fps=30, bitrate=3000),
        }
        return configs.get(quality, configs[StreamQuality.MEDIUM])

    @classmethod
    def from_string(cls, quality_str: str) -> "StreamConfig":
        """
        Create StreamConfig from a quality string.

        Args:
            quality_str: Quality string ('low', 'medium', 'high')

        Returns:
            StreamConfig with appropriate settings
        """
        try:
            quality = StreamQuality(quality_str.lower())
            return cls.from_quality(quality)
        except ValueError:
            logger.warning(f"Unknown stream quality '{quality_str}', defaulting to medium")
            return cls.from_quality(StreamQuality.MEDIUM)

# Default ffmpeg path
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")


@dataclass
class StreamSession:
    """
    Tracks an active streaming session (Story P7-3.3 AC1).

    Includes start time for duration tracking on stop.
    """
    session_id: str
    camera_id: str
    process: Optional[subprocess.Popen] = None
    started_at: float = field(default_factory=time.time)
    quality: str = "medium"
    resolution: str = ""
    fps: int = 0
    bitrate: int = 0


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
        stream_quality: str = "medium",
    ):
        """
        Initialize a HomeKit camera accessory (Story P5-1.3, P7-3.1).

        Args:
            driver: HAP-python AccessoryDriver instance
            camera_id: Unique camera identifier
            camera_name: Display name in Home app
            rtsp_url: RTSP stream URL for the camera
            manufacturer: Manufacturer name (default: ArgusAI)
            model: Model name (default: Camera)
            stream_quality: Quality level - 'low', 'medium', 'high' (default: medium)
        """
        if not HAP_AVAILABLE:
            raise ImportError("HAP-python is not installed. Install with: pip install HAP-python")

        self.camera_id = camera_id
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url
        self.manufacturer = manufacturer
        self.model = model
        self._driver = driver
        # Story P7-3.1: Store stream quality configuration
        self._stream_quality = stream_quality
        self._stream_config = StreamConfig.from_string(stream_quality)
        # Story P7-3.2: Snapshot caching infrastructure (AC3)
        self._snapshot_cache: Optional[bytes] = None
        self._snapshot_timestamp: Optional[datetime] = None

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

    @property
    def stream_quality(self) -> str:
        """Get the configured stream quality (Story P7-3.1)."""
        return self._stream_quality

    @property
    def stream_config(self) -> StreamConfig:
        """Get the stream configuration for this camera (Story P7-3.1)."""
        return self._stream_config

    async def _start_stream(self, session_info: dict, stream_config: dict) -> bool:
        """
        Start streaming to HomeKit client (Story P5-1.3 AC2, AC3, P7-3.1 AC4, P7-3.3 AC1).

        Spawns ffmpeg to transcode RTSP to SRTP.

        Story P7-3.3 AC1: Enhanced logging with session_id, camera_id, quality,
        client_address, resolution, fps, bitrate.

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
                # Story P7-3.3 AC1: Enhanced rejection logging
                logger.warning(
                    f"HomeKit stream rejected: max concurrent streams ({MAX_CONCURRENT_STREAMS}) reached",
                    extra={
                        "event_type": "homekit_stream_rejected",
                        "camera_id": self.camera_id,
                        "camera_name": self.camera_name,
                        "session_id": session_id,
                        "client_address": session_info.get("address"),
                        "active_streams": HomeKitCameraAccessory._active_stream_count,
                        "max_streams": MAX_CONCURRENT_STREAMS,
                        "reason": "concurrent_limit",
                    }
                )
                # P7-3.1 AC4: Record rejection in metrics
                record_homekit_stream_start(self.camera_id, self._stream_quality, 'rejected')
                return False
            HomeKitCameraAccessory._active_stream_count += 1
            # P7-3.1 AC4: Update metrics
            update_homekit_total_streams(HomeKitCameraAccessory._active_stream_count)

        try:
            # Build ffmpeg command and get stream parameters
            cmd, stream_params = self._build_ffmpeg_command_with_params(session_info, stream_config)

            if not cmd:
                logger.error(
                    f"Failed to build ffmpeg command for camera {self.camera_id}",
                    extra={
                        "event_type": "homekit_stream_error",
                        "camera_id": self.camera_id,
                        "session_id": session_id,
                        "reason": "ffmpeg_command_failed",
                    }
                )
                self._decrement_stream_count()
                return False

            # Story P7-3.3 AC1: Enhanced stream start logging with all required fields
            logger.info(
                f"Starting HomeKit stream for camera {self.camera_name}",
                extra={
                    "event_type": "homekit_stream_start",
                    "camera_id": self.camera_id,
                    "camera_name": self.camera_name,
                    "session_id": session_id,
                    "quality": self._stream_quality,
                    "client_address": session_info.get("address"),
                    "video_port": session_info.get("v_port"),
                    "resolution": stream_params.get("resolution"),
                    "fps": stream_params.get("fps"),
                    "bitrate": stream_params.get("bitrate"),
                }
            )

            # AC3: Spawn ffmpeg subprocess
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )

            # Track session with enhanced info (Story P7-3.3)
            session = StreamSession(
                session_id=session_id,
                camera_id=self.camera_id,
                process=process,
                started_at=time.time(),
                quality=self._stream_quality,
                resolution=stream_params.get("resolution", ""),
                fps=stream_params.get("fps", 0),
                bitrate=stream_params.get("bitrate", 0),
            )
            HomeKitCameraAccessory._active_sessions[session_id] = session

            # Store process reference for HAP-python
            session_info["process"] = process

            logger.info(
                f"HomeKit stream started for camera {self.camera_name} (PID: {process.pid})",
                extra={
                    "event_type": "homekit_stream_started",
                    "camera_id": self.camera_id,
                    "camera_name": self.camera_name,
                    "session_id": session_id,
                    "pid": process.pid,
                    "quality": self._stream_quality,
                    "resolution": stream_params.get("resolution"),
                    "fps": stream_params.get("fps"),
                    "bitrate": stream_params.get("bitrate"),
                }
            )

            # P7-3.1 AC4: Record successful stream start in metrics
            record_homekit_stream_start(self.camera_id, self._stream_quality, 'success')

            return True

        except Exception as e:
            logger.error(
                f"Failed to start HomeKit stream: {e}",
                extra={
                    "event_type": "homekit_stream_error",
                    "camera_id": self.camera_id,
                    "session_id": session_id,
                    "reason": "exception",
                    "error": str(e),
                }
            )
            # P7-3.1 AC4: Record error in metrics
            record_homekit_stream_start(self.camera_id, self._stream_quality, 'error')
            self._decrement_stream_count()
            return False

    async def _stop_stream(self, session_info: dict) -> None:
        """
        Stop streaming to HomeKit client (Story P5-1.3 AC3, P7-3.3 AC1).

        Terminates ffmpeg subprocess cleanly.

        Story P7-3.3 AC1: Enhanced logging with session_id, camera_id,
        duration_seconds, and reason (normal/timeout/error).

        Args:
            session_info: Contains session details and process reference
        """
        session_id = session_info.get("session_id", "unknown")
        process = session_info.get("process")

        # Get session info for duration calculation (Story P7-3.3)
        session = HomeKitCameraAccessory._active_sessions.get(session_id)
        duration_seconds = 0.0
        if session and session.started_at:
            duration_seconds = round(time.time() - session.started_at, 2)

        logger.info(
            f"Stopping HomeKit stream for camera {self.camera_name}",
            extra={
                "event_type": "homekit_stream_stopping",
                "camera_id": self.camera_id,
                "camera_name": self.camera_name,
                "session_id": session_id,
                "duration_seconds": duration_seconds,
            }
        )

        # Remove from active sessions
        HomeKitCameraAccessory._active_sessions.pop(session_id, None)

        stop_reason = "normal"
        if process:
            try:
                # Try graceful termination first
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful termination fails
                    stop_reason = "timeout"
                    logger.warning(
                        f"ffmpeg did not terminate gracefully, killing (PID: {process.pid})",
                        extra={
                            "event_type": "homekit_stream_force_kill",
                            "camera_id": self.camera_id,
                            "session_id": session_id,
                            "pid": process.pid,
                        }
                    )
                    process.kill()
                    process.wait(timeout=1.0)

                # Story P7-3.3 AC1: Enhanced stop logging with duration and reason
                logger.info(
                    f"HomeKit stream stopped for camera {self.camera_name}",
                    extra={
                        "event_type": "homekit_stream_stop",
                        "camera_id": self.camera_id,
                        "camera_name": self.camera_name,
                        "session_id": session_id,
                        "duration_seconds": duration_seconds,
                        "reason": stop_reason,
                    }
                )

            except Exception as e:
                stop_reason = "error"
                # Story P7-3.3 AC1.4: Log ffmpeg stderr on failure
                stderr_output = ""
                if process and process.stderr:
                    try:
                        stderr_output = process.stderr.read().decode("utf-8", errors="replace")[:500]
                    except Exception:
                        pass
                logger.error(
                    f"Error stopping ffmpeg process: {e}",
                    extra={
                        "event_type": "homekit_stream_stop_error",
                        "camera_id": self.camera_id,
                        "session_id": session_id,
                        "duration_seconds": duration_seconds,
                        "reason": stop_reason,
                        "error": str(e),
                        "ffmpeg_stderr": stderr_output if stderr_output else None,
                    }
                )

        # AC4: Decrement stream count
        self._decrement_stream_count()

    def _decrement_stream_count(self) -> None:
        """Safely decrement the active stream count (P7-3.1 AC4: includes metric update)."""
        with self._stream_lock:
            HomeKitCameraAccessory._active_stream_count = max(
                0, HomeKitCameraAccessory._active_stream_count - 1
            )
            # P7-3.1 AC4: Update total streams metric
            update_homekit_total_streams(HomeKitCameraAccessory._active_stream_count)

    def _build_ffmpeg_command_with_params(
        self, session_info: dict, stream_config: dict
    ) -> Tuple[Optional[List[str]], dict]:
        """
        Build ffmpeg command for RTSP to SRTP transcoding (Story P5-1.3 AC2, P7-3.1 AC2, AC3, P7-3.3).

        Uses quality-based configuration from self._stream_config when HomeKit
        doesn't specify explicit settings, ensuring consistent quality based
        on the camera's homekit_stream_quality database field.

        Story P7-3.3: Returns both command and stream parameters for logging.

        Args:
            session_info: Client address, ports, SRTP keys
            stream_config: Video settings from HomeKit (may be empty/default)

        Returns:
            Tuple of (command list, stream params dict) or (None, {}) on error
        """
        try:
            # Extract session parameters
            address = session_info.get("address", "127.0.0.1")
            v_port = session_info.get("v_port", 0)
            v_srtp_key = session_info.get("v_srtp_key", "")
            v_ssrc = session_info.get("v_ssrc", 0)

            # Story P7-3.1 AC3: Use quality-based config when HomeKit doesn't specify
            # HomeKit may request specific resolution or let us choose
            homekit_width = stream_config.get("width")
            homekit_height = stream_config.get("height")
            homekit_fps = stream_config.get("fps")
            homekit_bitrate = stream_config.get("v_max_bitrate")

            # Use our quality config if HomeKit doesn't specify or uses defaults
            # This ensures our quality setting takes precedence
            quality_config = self._stream_config
            width = homekit_width if homekit_width and homekit_width != 0 else quality_config.width
            height = homekit_height if homekit_height and homekit_height != 0 else quality_config.height
            fps = homekit_fps if homekit_fps and homekit_fps != 0 else quality_config.fps
            bitrate = homekit_bitrate if homekit_bitrate and homekit_bitrate != 0 else quality_config.bitrate

            # Cap values to our quality config maximum (don't exceed configured quality)
            width = min(width, quality_config.width)
            height = min(height, quality_config.height)
            fps = min(fps, quality_config.fps)
            bitrate = min(bitrate, quality_config.bitrate)

            # Story P7-3.3: Collect stream parameters for logging
            stream_params = {
                "resolution": f"{width}x{height}",
                "fps": fps,
                "bitrate": bitrate,
                "width": width,
                "height": height,
            }

            logger.debug(
                f"Building ffmpeg command with quality={self._stream_quality}: "
                f"{width}x{height}@{fps}fps, {bitrate}kbps",
                extra={
                    "camera_id": self.camera_id,
                    "quality": self._stream_quality,
                    **stream_params,
                }
            )

            # Build ffmpeg command
            # AC2: Low-latency transcoding for <500ms additional delay
            # AC3: Use baseline H.264 profile for maximum compatibility
            cmd = [
                FFMPEG_PATH,
                # Input options
                "-rtsp_transport", "tcp",
                "-i", self.rtsp_url,
                # Video codec settings
                "-an",  # No audio
                "-vcodec", "libx264",
                "-pix_fmt", "yuv420p",
                "-profile:v", "baseline",  # AC3: Maximum compatibility with all iOS devices
                "-level", "3.1",  # Standard level for 720p30 compatibility
                "-preset", "ultrafast",
                "-tune", "zerolatency",  # AC2: Minimize latency
                # Bitrate settings
                "-b:v", f"{bitrate}k",
                "-bufsize", f"{bitrate}k",
                "-maxrate", f"{bitrate}k",
                # Frame settings
                "-r", str(fps),
                "-vf", f"scale={width}:{height}",
                # Keyframe settings for seek/preview
                "-g", str(fps * 2),  # Keyframe every 2 seconds
                "-keyint_min", str(fps),
                # RTP output settings
                "-payload_type", "99",
                "-ssrc", str(v_ssrc),
                "-f", "rtp",
                "-srtp_out_suite", "AES_CM_128_HMAC_SHA1_80",  # AC2: Required SRTP encryption
                "-srtp_out_params", v_srtp_key,
                f"srtp://{address}:{v_port}?rtcpport={v_port}&pkt_size=1316",
            ]

            return cmd, stream_params

        except Exception as e:
            logger.error(f"Error building ffmpeg command: {e}")
            return None, {}

    def _build_ffmpeg_command(self, session_info: dict, stream_config: dict) -> Optional[List[str]]:
        """
        Build ffmpeg command for RTSP to SRTP transcoding (Story P5-1.3 AC2, P7-3.1 AC2, AC3).

        Wrapper for backwards compatibility.

        Args:
            session_info: Client address, ports, SRTP keys
            stream_config: Video settings from HomeKit (may be empty/default)

        Returns:
            List of command arguments for subprocess, or None on error
        """
        cmd, _ = self._build_ffmpeg_command_with_params(session_info, stream_config)
        return cmd

    @staticmethod
    def sanitize_ffmpeg_command(cmd: List[str]) -> str:
        """
        Sanitize ffmpeg command for display, removing sensitive SRTP keys (Story P7-3.3 AC3).

        Args:
            cmd: Full ffmpeg command list

        Returns:
            Sanitized command string safe for logging/display
        """
        if not cmd:
            return ""

        sanitized = []
        skip_next = False

        for i, arg in enumerate(cmd):
            if skip_next:
                skip_next = False
                sanitized.append("[REDACTED]")
                continue

            # Check if this is a sensitive parameter
            if arg in ("-srtp_out_params", "-srtp_in_params"):
                sanitized.append(arg)
                skip_next = True
                continue

            # Sanitize RTSP URLs with credentials
            if arg.startswith("rtsp://") and "@" in arg:
                # Replace credentials in URL
                sanitized.append(re.sub(r"://[^:]+:[^@]+@", "://[credentials]@", arg))
            elif arg.startswith("srtp://"):
                # Keep SRTP URL but note it contains encryption
                sanitized.append(arg.split("?")[0] + "?[params]")
            else:
                sanitized.append(arg)

        return " ".join(sanitized)

    def get_stream_diagnostics(self) -> dict:
        """
        Get streaming diagnostics for this camera (Story P7-3.3 AC2).

        Returns:
            Dict with streaming_enabled, snapshot_supported, last_snapshot,
            active_streams count, and current quality.
        """
        # Count active streams for this camera
        active_count = sum(
            1 for s in HomeKitCameraAccessory._active_sessions.values()
            if s.camera_id == self.camera_id
        )

        return {
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "streaming_enabled": True,
            "snapshot_supported": self.snapshot_supported,
            "last_snapshot": self._snapshot_timestamp.isoformat() if self._snapshot_timestamp else None,
            "active_streams": active_count,
            "quality": self._stream_quality,
        }

    def _is_snapshot_cache_valid(self) -> bool:
        """
        Check if snapshot cache is valid (Story P7-3.2 AC3).

        Returns True if cached snapshot exists and is less than SNAPSHOT_CACHE_SECONDS old.

        Returns:
            True if cache is valid, False otherwise
        """
        if self._snapshot_cache is None or self._snapshot_timestamp is None:
            return False
        age = (datetime.utcnow() - self._snapshot_timestamp).total_seconds()
        return age < SNAPSHOT_CACHE_SECONDS

    @property
    def last_snapshot_time(self) -> Optional[datetime]:
        """Get the timestamp of the last snapshot capture (Story P7-3.2)."""
        return self._snapshot_timestamp

    @property
    def snapshot_supported(self) -> bool:
        """Whether this camera supports snapshots (Story P7-3.2)."""
        return True

    async def _get_snapshot(self, image_size: dict) -> bytes:
        """
        Get camera snapshot for HomeKit tiles (Story P5-1.3 AC1, P7-3.2 AC1-AC4).

        Story P7-3.2 enhancements:
        - AC1: Implements get_snapshot() method
        - AC2: Returns JPEG snapshot from camera
        - AC3: Caches snapshot for 5 seconds to reduce load
        - AC4: Returns placeholder gracefully when camera offline

        Args:
            image_size: Requested image dimensions (width, height)

        Returns:
            JPEG image data as bytes
        """
        width = image_size.get("image-width", 640)
        height = image_size.get("image-height", 480)

        # Story P7-3.2 AC3: Check cache first
        if self._is_snapshot_cache_valid():
            record_homekit_snapshot_cache_hit(self.camera_id)
            logger.debug(
                f"Snapshot cache hit for camera {self.camera_name}",
                extra={
                    "camera_id": self.camera_id,
                    "cache_age_seconds": (datetime.utcnow() - self._snapshot_timestamp).total_seconds()
                    if self._snapshot_timestamp else 0
                }
            )
            return self._snapshot_cache

        # Cache miss - need to capture new snapshot
        record_homekit_snapshot_cache_miss(self.camera_id)
        logger.debug(
            f"Snapshot cache miss for camera {self.camera_name}",
            extra={"camera_id": self.camera_id}
        )

        try:
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
                # Story P7-3.2 AC3: Store in cache with timestamp
                self._snapshot_cache = result.stdout
                self._snapshot_timestamp = datetime.utcnow()

                logger.debug(
                    f"Captured and cached snapshot for camera {self.camera_name}",
                    extra={"camera_id": self.camera_id, "size": len(result.stdout)}
                )
                return result.stdout

            logger.warning(
                f"Failed to capture snapshot from RTSP: {result.stderr.decode()[:200]}",
                extra={"camera_id": self.camera_id}
            )

        except subprocess.TimeoutExpired:
            # Story P7-3.2 AC4: Log when returning placeholder due to offline
            logger.warning(
                f"Snapshot capture timeout for camera {self.camera_name} - returning placeholder",
                extra={"camera_id": self.camera_id, "reason": "timeout"}
            )
        except Exception as e:
            # Story P7-3.2 AC4: Log when returning placeholder due to error
            logger.error(
                f"Error capturing snapshot for camera {self.camera_name} - returning placeholder: {e}",
                extra={"camera_id": self.camera_id, "reason": "error"}
            )

        # Story P7-3.2 AC4: Return placeholder on failure
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
    stream_quality: str = "medium",
) -> Optional[HomeKitCameraAccessory]:
    """
    Factory function to create a HomeKit camera accessory (Story P5-1.3, P7-3.1).

    Args:
        driver: HAP-python AccessoryDriver instance
        camera_id: Unique camera identifier
        camera_name: Display name in Home app
        rtsp_url: RTSP stream URL for the camera
        manufacturer: Manufacturer name (default: ArgusAI)
        stream_quality: Quality level - 'low', 'medium', 'high' (default: medium)

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
            stream_quality=stream_quality,
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
