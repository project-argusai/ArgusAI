"""
CameraCaptureWorker

Encapsulates the capture thread, reconnection logic, and frame handling for a single camera.

This class owns everything needed to capture frames from one RTSP or USB camera in a background thread.

Extracted from CameraService during Phase 5 decomposition.
"""

import cv2
import threading
import time
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone
import numpy as np

try:
    import av
    PYAV_AVAILABLE = True
except ImportError:
    PYAV_AVAILABLE = False

from app.models.camera import Camera
from app.services.motion_detection_service import motion_detection_service
from app.services.audio_stream_service import get_audio_stream_extractor

logger = logging.getLogger(__name__)


class CameraCaptureWorker:
    """
    Manages capture for a single camera in its own background thread.

    Responsibilities:
    - Thread lifecycle (start/stop)
    - Connection + automatic reconnection with backoff
    - Frame capture loop
    - Status tracking for this camera
    - Latest frame storage
    - Motion detection triggering
    - Audio stream detection (if enabled)
    """

    def __init__(self, camera: Camera, main_event_loop: Optional[asyncio.AbstractEventLoop] = None):
        self.camera = camera
        self.camera_id = camera.id
        self._main_event_loop = main_event_loop

        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._status_lock = threading.Lock()
        self._status = {
            "status": "stopped",
            "last_frame_time": None,
            "error": None
        }
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

        # Audio extractor (lazy)
        self._audio_extractor = None

        logger.debug(f"CameraCaptureWorker created for camera {self.camera_id}")

    def start(self) -> bool:
        """Start the capture thread."""
        if self._thread and self._thread.is_alive():
            logger.warning(f"Capture thread for camera {self.camera_id} already running")
            return False

        self._stop_flag.clear()

        with self._status_lock:
            self._status = {
                "status": "starting",
                "last_frame_time": None,
                "error": None
            }

        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"camera_{self.camera.name}_{self.camera_id[:8]}",
            daemon=True
        )
        self._thread.start()

        logger.info(f"Started capture worker for camera {self.camera_id}")
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the capture thread gracefully."""
        self._stop_flag.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        # Release resources
        self._release_resources()

        with self._status_lock:
            self._status["status"] = "stopped"

        logger.info(f"Stopped capture worker for camera {self.camera_id}")

    def get_status(self) -> dict:
        with self._status_lock:
            return self._status.copy()

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def _update_status(self, status: str, error: Optional[str] = None):
        with self._status_lock:
            self._status["status"] = status
            if error:
                self._status["error"] = error
            if status == "connected":
                self._status["last_frame_time"] = datetime.now(timezone.utc).isoformat()

    def _capture_loop(self) -> None:
        """Main capture loop (moved from CameraService._capture_loop)."""
        # This will contain the full capture + reconnection logic.
        # For the first version, we'll keep a simplified version and expand in follow-up chunks.

        camera_id = self.camera_id
        base_retry_delay = 30
        max_retry_delay = 300
        retry_count = 0

        logger.info(f"Capture loop started for camera {camera_id}")

        while not self._stop_flag.is_set():
            cap = None
            av_container = None
            use_pyav = False

            try:
                connection_str = self._build_connection_string()

                # Attempt connection (PyAV for rtsps, OpenCV otherwise)
                if self.camera.type == "rtsp" and PYAV_AVAILABLE and connection_str.startswith("rtsps://"):
                    try:
                        av_container = av.open(connection_str, options={'rtsp_transport': 'tcp'}, timeout=15.0)
                        use_pyav = True
                    except Exception as e:
                        logger.warning(f"PyAV failed for {camera_id}, falling back to OpenCV: {e}")
                        if av_container:
                            av_container.close()
                        av_container = None

                if not use_pyav:
                    cap = cv2.VideoCapture(connection_str)
                    if not cap.isOpened():
                        raise ConnectionError("Failed to open camera with OpenCV")

                self._update_status("connected")
                retry_count = 0

                fps = max(1, min(self.camera.frame_rate or 10, 30))
                frame_interval = 1.0 / fps

                while not self._stop_flag.is_set():
                    start_time = time.time()

                    if use_pyav and av_container:
                        try:
                            for frame in av_container.decode(video=0):
                                if self._stop_flag.is_set():
                                    break
                                img = frame.to_ndarray(format='bgr24')
                                self._process_frame(img)
                                break  # Process one frame per iteration
                        except Exception as e:
                            logger.warning(f"PyAV decode error on {camera_id}: {e}")
                            break
                    elif cap:
                        ret, frame = cap.read()
                        if not ret:
                            logger.warning(f"Failed to read frame from camera {camera_id}")
                            break
                        self._process_frame(frame)
                    else:
                        break

                    elapsed = time.time() - start_time
                    sleep_time = max(0, frame_interval - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            except Exception as e:
                retry_count += 1
                delay = min(base_retry_delay * (2 ** min(retry_count, 4)), max_retry_delay)
                self._update_status("error", error=str(e))
                logger.warning(f"Capture error on camera {camera_id} (retry {retry_count}): {e}. Reconnecting in {delay}s")

                if cap:
                    cap.release()
                if av_container:
                    av_container.close()

                if not self._stop_flag.is_set():
                    time.sleep(delay)
            finally:
                if cap:
                    cap.release()
                if av_container:
                    av_container.close()

        self._update_status("stopped")
        logger.info(f"Capture loop ended for camera {camera_id}")

    def _process_frame(self, frame: np.ndarray):
        """Process a captured frame (motion detection, storage, etc.)."""
        with self._frame_lock:
            self._latest_frame = frame

        # TODO: Integrate motion detection properly here (currently stubbed in original)
        # For now we just store the latest frame.

    def _build_connection_string(self) -> str:
        if self.camera.type == "rtsp":
            return self._build_rtsp_url(self.camera)
        elif self.camera.type == "usb":
            return str(self.camera.device_index)
        else:
            raise ValueError(f"Unknown camera type: {self.camera.type}")

    def _build_rtsp_url(self, camera: Camera) -> str:
        """Build RTSP URL from camera config."""
        if camera.username and camera.password:
            auth = f"{camera.username}:{camera.password}@"
        else:
            auth = ""

        port = camera.port or 554
        path = camera.stream_path or ""

        if not path.startswith("/"):
            path = "/" + path

        return f"rtsp://{auth}{camera.ip_address}:{port}{path}"

    def _release_resources(self):
        """Release any open capture resources."""
        pass  # Can be expanded if needed

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()