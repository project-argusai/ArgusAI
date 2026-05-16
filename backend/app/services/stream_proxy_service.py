"""
Live Camera Stream Proxy Service (Story P16-2.2)

Provides MJPEG streaming via WebSocket for live camera viewing.
Implements the design from P16-2.1 with <3 second latency target.

Architecture:
    Camera (RTSP) → StreamProxyService → WebSocket Clients
                         │
                         ├── Frame extraction (OpenCV/PyAV)
                         ├── JPEG encoding (quality levels)
                         ├── Stream sharing (1 capture, N clients)
                         └── Concurrent stream limiting

Quality Levels:
    - low: 640x360 @ 5fps, JPEG quality 70
    - medium: 1280x720 @ 10fps, JPEG quality 80
    - high: 1920x1080 @ 15fps, JPEG quality 90

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import asyncio
import base64
import logging
from app.core.decorators import singleton
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import cv2
import numpy as np

try:
    import av
    PYAV_AVAILABLE = True
except ImportError:
    PYAV_AVAILABLE = False

from app.core.config import settings

logger = logging.getLogger(__name__)


class StreamQuality(str, Enum):
    """Stream quality levels (Story P16-2.2, FR18)"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class QualityConfig:
    """Configuration for each quality level"""
    width: int
    height: int
    fps: int
    jpeg_quality: int


# Quality level configurations (from P16-2.1 design)
QUALITY_CONFIGS: Dict[StreamQuality, QualityConfig] = {
    StreamQuality.LOW: QualityConfig(width=640, height=360, fps=5, jpeg_quality=70),
    StreamQuality.MEDIUM: QualityConfig(width=1280, height=720, fps=10, jpeg_quality=80),
    StreamQuality.HIGH: QualityConfig(width=1920, height=1080, fps=15, jpeg_quality=90),
}


@dataclass
class StreamClient:
    """Represents a connected streaming client"""
    client_id: str
    quality: StreamQuality
    connected_at: datetime
    last_frame_at: Optional[datetime] = None
    frames_sent: int = 0
    callback: Optional[Callable[[bytes], None]] = None


@dataclass
class CameraStream:
    """Represents an active camera stream with multiple clients"""
    camera_id: str
    rtsp_url: str
    clients: Dict[str, StreamClient] = field(default_factory=dict)
    capture_thread: Optional[threading.Thread] = None
    is_running: bool = False
    last_frame: Optional[np.ndarray] = None
    last_frame_time: Optional[datetime] = None
    frame_buffer: List[bytes] = field(default_factory=list)
    error_count: int = 0

    # Stats
    total_frames_captured: int = 0
    total_frames_sent: int = 0


@singleton
class StreamProxyService:
    """
    Service for proxying camera streams via WebSocket (Story P16-2.2).

    Responsibilities:
    - Connect to camera RTSP streams
    - Extract and encode frames as JPEG
    - Distribute frames to connected WebSocket clients
    - Manage concurrent stream limits
    - Handle quality level switching

    Thread Safety:
    - Uses locks for shared state (streams, clients)
    - Capture runs in background threads
    - Frame distribution uses asyncio
    """

    def __init__(self):
        self._streams: Dict[str, CameraStream] = {}
        self._lock = threading.RLock()
        self._total_clients = 0
        self._max_concurrent = settings.STREAM_MAX_CONCURRENT
        self._frame_buffer_size = settings.STREAM_FRAME_BUFFER_SIZE

        # Metrics
        self._streams_started = 0
        self._streams_stopped = 0
        self._connection_errors = 0

        logger.info(
            f"StreamProxyService initialized: max_concurrent={self._max_concurrent}",
            extra={"event_type": "stream_proxy_init"}
        )

    def get_stream_info(self, camera_id: str) -> Dict[str, Any]:
        """
        Get stream information for a camera (Story P16-2.2, AC1).

        Args:
            camera_id: Camera UUID

        Returns:
            Dict with stream info: url, type, quality_options, is_available
        """
        quality_options = [
            {
                "id": q.value,
                "label": q.value.capitalize(),
                "resolution": f"{QUALITY_CONFIGS[q].width}x{QUALITY_CONFIGS[q].height}",
                "fps": QUALITY_CONFIGS[q].fps,
            }
            for q in StreamQuality
        ]

        with self._lock:
            active_stream = self._streams.get(camera_id)
            current_clients = len(active_stream.clients) if active_stream else 0

        return {
            "camera_id": camera_id,
            "type": "websocket_mjpeg",
            "websocket_path": f"/api/v1/cameras/{camera_id}/stream",
            "snapshot_path": f"/api/v1/cameras/{camera_id}/stream/snapshot",
            "quality_options": quality_options,
            "default_quality": settings.STREAM_DEFAULT_QUALITY,
            "current_clients": current_clients,
            "max_clients_available": self._max_concurrent - self._total_clients,
            "is_available": self._total_clients < self._max_concurrent,
        }

    async def add_client(
        self,
        camera_id: str,
        rtsp_url: str,
        quality: StreamQuality = StreamQuality.MEDIUM,
        frame_callback: Optional[Callable[[bytes], None]] = None
    ) -> Optional[str]:
        """
        Add a new streaming client for a camera (Story P16-2.2, AC2, AC3).

        Args:
            camera_id: Camera UUID
            rtsp_url: RTSP URL for the camera
            quality: Desired stream quality
            frame_callback: Async callback to receive JPEG frames

        Returns:
            Client ID if successful, None if limit reached
        """
        with self._lock:
            # Check concurrent limit
            if self._total_clients >= self._max_concurrent:
                logger.warning(
                    f"Stream client limit reached: {self._total_clients}/{self._max_concurrent}",
                    extra={
                        "event_type": "stream_limit_reached",
                        "camera_id": camera_id,
                    }
                )
                return None

            # Create client
            client_id = str(uuid.uuid4())
            client = StreamClient(
                client_id=client_id,
                quality=quality,
                connected_at=datetime.now(timezone.utc),
                callback=frame_callback,
            )

            # Get or create camera stream
            if camera_id not in self._streams:
                self._streams[camera_id] = CameraStream(
                    camera_id=camera_id,
                    rtsp_url=rtsp_url,
                )

            stream = self._streams[camera_id]
            stream.clients[client_id] = client
            self._total_clients += 1

            # Start capture if not running
            if not stream.is_running:
                self._start_capture(stream)

            logger.info(
                f"Stream client added: camera={camera_id}, client={client_id}, quality={quality.value}",
                extra={
                    "event_type": "stream_client_added",
                    "camera_id": camera_id,
                    "client_id": client_id,
                    "quality": quality.value,
                    "total_clients": self._total_clients,
                }
            )

            return client_id

    def remove_client(self, camera_id: str, client_id: str) -> bool:
        """
        Remove a streaming client (Story P16-2.2).

        Args:
            camera_id: Camera UUID
            client_id: Client UUID to remove

        Returns:
            True if client was removed, False if not found
        """
        with self._lock:
            stream = self._streams.get(camera_id)
            if not stream:
                return False

            if client_id not in stream.clients:
                return False

            del stream.clients[client_id]
            self._total_clients -= 1

            logger.info(
                f"Stream client removed: camera={camera_id}, client={client_id}",
                extra={
                    "event_type": "stream_client_removed",
                    "camera_id": camera_id,
                    "client_id": client_id,
                    "total_clients": self._total_clients,
                }
            )

            # Stop capture if no more clients
            if not stream.clients:
                self._stop_capture(stream)
                del self._streams[camera_id]

            return True

    def change_quality(self, camera_id: str, client_id: str, quality: StreamQuality) -> bool:
        """
        Change stream quality for a client (Story P16-2.2, FR18).

        Args:
            camera_id: Camera UUID
            client_id: Client UUID
            quality: New quality level

        Returns:
            True if quality was changed, False if client not found
        """
        with self._lock:
            stream = self._streams.get(camera_id)
            if not stream:
                return False

            client = stream.clients.get(client_id)
            if not client:
                return False

            old_quality = client.quality
            client.quality = quality

            logger.info(
                f"Stream quality changed: camera={camera_id}, client={client_id}, {old_quality.value} -> {quality.value}",
                extra={
                    "event_type": "stream_quality_changed",
                    "camera_id": camera_id,
                    "client_id": client_id,
                    "old_quality": old_quality.value,
                    "new_quality": quality.value,
                }
            )

            return True

    def get_snapshot(self, camera_id: str, quality: StreamQuality = StreamQuality.MEDIUM) -> Optional[bytes]:
        """
        Get current frame as JPEG snapshot (Story P16-2.2, AC3).

        Args:
            camera_id: Camera UUID
            quality: Quality level for snapshot

        Returns:
            JPEG bytes or None if no frame available
        """
        with self._lock:
            stream = self._streams.get(camera_id)
            if not stream or stream.last_frame is None:
                return None

            return self._encode_frame(stream.last_frame, quality)

    def get_client_frame(self, camera_id: str, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest frame for a specific client at their quality level.

        Args:
            camera_id: Camera UUID
            client_id: Client UUID

        Returns:
            Dict with 'data' (JPEG bytes) and 'timestamp' (unix time), or None
        """
        with self._lock:
            stream = self._streams.get(camera_id)
            if not stream or stream.last_frame is None:
                return None

            client = stream.clients.get(client_id)
            if not client:
                return None

            # Get frame timestamp
            timestamp = 0
            if stream.last_frame_time:
                timestamp = stream.last_frame_time.timestamp()

            # Encode at client's quality level
            jpeg_bytes = self._encode_frame(stream.last_frame, client.quality)
            if not jpeg_bytes:
                return None

            # Update client stats
            client.last_frame_at = stream.last_frame_time
            client.frames_sent += 1
            stream.total_frames_sent += 1

            return {
                "data": jpeg_bytes,
                "timestamp": timestamp
            }

    async def get_snapshot_from_rtsp(
        self,
        camera_id: str,
        rtsp_url: str,
        quality: StreamQuality = StreamQuality.MEDIUM
    ) -> Optional[bytes]:
        """
        Get a snapshot directly from RTSP without starting a stream.

        Args:
            camera_id: Camera UUID
            rtsp_url: RTSP URL
            quality: Quality level

        Returns:
            JPEG bytes or None on failure
        """
        # Check if we have a running stream with a frame
        with self._lock:
            stream = self._streams.get(camera_id)
            if stream and stream.last_frame is not None:
                return self._encode_frame(stream.last_frame, quality)

        # Otherwise, capture a single frame
        try:
            frame = await asyncio.to_thread(self._capture_single_frame, rtsp_url)
            if frame is not None:
                return self._encode_frame(frame, quality)
        except Exception as e:
            logger.error(f"Failed to capture snapshot from {camera_id}: {e}")

        return None

    def _capture_single_frame(self, rtsp_url: str) -> Optional[np.ndarray]:
        """Capture a single frame from RTSP (blocking)."""
        cap = None
        av_container = None

        try:
            # Use PyAV for secure RTSP
            if PYAV_AVAILABLE and rtsp_url.startswith("rtsps://"):
                av_container = av.open(
                    rtsp_url,
                    options={'rtsp_transport': 'tcp'},
                    timeout=10
                )
                av_stream = av_container.streams.video[0]
                for av_frame in av_container.decode(av_stream):
                    frame = av_frame.to_ndarray(format='bgr24')
                    av_container.close()
                    return frame
            else:
                # Use OpenCV for regular RTSP
                cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)

                if not cap.isOpened():
                    return None

                ret, frame = cap.read()
                cap.release()

                if ret and frame is not None:
                    return frame

        except Exception as e:
            logger.warning(f"Single frame capture failed: {e}")
        finally:
            if cap is not None:
                cap.release()
            if av_container is not None:
                try:
                    av_container.close()
                except Exception:
                    pass

        return None

    def _start_capture(self, stream: CameraStream) -> None:
        """Start capture thread for a camera stream."""
        if stream.is_running:
            return

        stream.is_running = True
        stream.capture_thread = threading.Thread(
            target=self._capture_loop,
            args=(stream,),
            daemon=True,
            name=f"stream-capture-{stream.camera_id[:8]}"
        )
        stream.capture_thread.start()
        self._streams_started += 1

        logger.info(
            f"Stream capture started: camera={stream.camera_id}",
            extra={
                "event_type": "stream_capture_started",
                "camera_id": stream.camera_id,
            }
        )

    def _stop_capture(self, stream: CameraStream) -> None:
        """Stop capture thread for a camera stream."""
        stream.is_running = False

        # Wait for thread to finish (with timeout)
        if stream.capture_thread and stream.capture_thread.is_alive():
            stream.capture_thread.join(timeout=5.0)

        stream.capture_thread = None
        stream.last_frame = None
        stream.frame_buffer.clear()
        self._streams_stopped += 1

        logger.info(
            f"Stream capture stopped: camera={stream.camera_id}",
            extra={
                "event_type": "stream_capture_stopped",
                "camera_id": stream.camera_id,
            }
        )

    def _capture_loop(self, stream: CameraStream) -> None:
        """Main capture loop running in background thread."""
        cap = None
        av_container = None
        rtsp_url = stream.rtsp_url

        # Determine target FPS (use highest quality FPS as capture rate)
        target_fps = QUALITY_CONFIGS[StreamQuality.HIGH].fps
        frame_interval = 1.0 / target_fps

        logger.debug(f"Capture loop starting for {stream.camera_id}, target FPS: {target_fps}")

        try:
            # Connect to RTSP stream
            if PYAV_AVAILABLE and rtsp_url.startswith("rtsps://"):
                # UniFi Protect uses self-signed certs, need to disable verification
                av_container = av.open(
                    rtsp_url,
                    options={
                        'rtsp_transport': 'tcp',
                        'tls_verify': '0',  # Disable SSL verification for self-signed certs
                    },
                    timeout=30
                )
                av_stream = av_container.streams.video[0]

                logger.debug(f"PyAV connected: {av_stream.codec_context.width}x{av_stream.codec_context.height}")

                for av_frame in av_container.decode(av_stream):
                    if not stream.is_running:
                        break

                    frame = av_frame.to_ndarray(format='bgr24')
                    self._process_frame(stream, frame)

                    # Rate limiting
                    time.sleep(frame_interval)

            else:
                cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 30000)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency

                if not cap.isOpened():
                    logger.error(f"Failed to open RTSP stream: {stream.camera_id}")
                    stream.error_count += 1
                    self._connection_errors += 1
                    return

                logger.debug(f"OpenCV connected to {stream.camera_id}")

                while stream.is_running:
                    ret, frame = cap.read()

                    if not ret or frame is None:
                        stream.error_count += 1
                        if stream.error_count > 10:
                            logger.error(f"Too many read errors for {stream.camera_id}")
                            break
                        time.sleep(0.1)
                        continue

                    stream.error_count = 0
                    self._process_frame(stream, frame)

                    # Rate limiting
                    time.sleep(frame_interval)

        except Exception as e:
            logger.error(
                f"Capture loop error for {stream.camera_id}: {e}",
                extra={
                    "event_type": "stream_capture_error",
                    "camera_id": stream.camera_id,
                    "error": str(e),
                },
                exc_info=True
            )
            self._connection_errors += 1
        finally:
            if cap is not None:
                cap.release()
            if av_container is not None:
                try:
                    av_container.close()
                except Exception:
                    pass

            stream.is_running = False
            logger.debug(f"Capture loop ended for {stream.camera_id}")

    def _process_frame(self, stream: CameraStream, frame: np.ndarray) -> None:
        """Process a captured frame and distribute to clients."""
        now = datetime.now(timezone.utc)

        with self._lock:
            stream.last_frame = frame
            stream.last_frame_time = now
            stream.total_frames_captured += 1

            # Encode and distribute to clients
            for client_id, client in list(stream.clients.items()):
                try:
                    # Encode at client's quality level
                    jpeg_bytes = self._encode_frame(frame, client.quality)

                    if jpeg_bytes and client.callback:
                        # Call the async callback
                        asyncio.run_coroutine_threadsafe(
                            self._send_frame_to_client(client, jpeg_bytes),
                            asyncio.get_event_loop()
                        )

                        client.last_frame_at = now
                        client.frames_sent += 1
                        stream.total_frames_sent += 1

                except Exception as e:
                    logger.warning(f"Failed to send frame to client {client_id}: {e}")

    async def _send_frame_to_client(self, client: StreamClient, frame_bytes: bytes) -> None:
        """Send frame to client via callback."""
        try:
            if client.callback:
                if asyncio.iscoroutinefunction(client.callback):
                    await client.callback(frame_bytes)
                else:
                    client.callback(frame_bytes)
        except Exception as e:
            logger.warning(f"Client callback error: {e}")

    def _encode_frame(self, frame: np.ndarray, quality: StreamQuality) -> Optional[bytes]:
        """Encode frame as JPEG at specified quality level."""
        try:
            config = QUALITY_CONFIGS[quality]

            # Resize if needed
            h, w = frame.shape[:2]
            if w > config.width or h > config.height:
                # Maintain aspect ratio
                scale = min(config.width / w, config.height / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            # Encode as JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, config.jpeg_quality]
            ret, buffer = cv2.imencode('.jpg', frame, encode_params)

            if ret:
                return buffer.tobytes()

        except Exception as e:
            logger.warning(f"Frame encoding error: {e}")

        return None

    def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics for monitoring (Story P16-2.2)."""
        with self._lock:
            active_streams = len(self._streams)
            total_clients = self._total_clients

            stream_details = []
            for camera_id, stream in self._streams.items():
                stream_details.append({
                    "camera_id": camera_id,
                    "client_count": len(stream.clients),
                    "is_running": stream.is_running,
                    "frames_captured": stream.total_frames_captured,
                    "frames_sent": stream.total_frames_sent,
                    "error_count": stream.error_count,
                })

        return {
            "active_streams": active_streams,
            "total_clients": total_clients,
            "max_concurrent": self._max_concurrent,
            "streams_started_total": self._streams_started,
            "streams_stopped_total": self._streams_stopped,
            "connection_errors_total": self._connection_errors,
            "streams": stream_details,
        }

    def stop_all(self) -> None:
        """Stop all active streams (for shutdown)."""
        with self._lock:
            for stream in list(self._streams.values()):
                self._stop_capture(stream)
            self._streams.clear()
            self._total_clients = 0

        logger.info("All streams stopped", extra={"event_type": "stream_proxy_shutdown"})


# Backward compatible thin getter (delegates to @singleton decorator)
def get_stream_proxy_service() -> StreamProxyService:
    """
    Get the global StreamProxyService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer StreamProxyService() directly.
    """
    return StreamProxyService()


def reset_stream_proxy_service() -> None:
    """Reset the global StreamProxyService instance (for testing)."""
    StreamProxyService._reset_instance()
