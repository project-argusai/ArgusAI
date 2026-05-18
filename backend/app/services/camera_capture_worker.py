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
import queue
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
    - Thread lifecycle (start/stop) with robust shutdown
    - Connection + automatic reconnection with backoff
    - Frame capture loop with bounded backpressure queue
    - Status tracking and observability (frames captured/dropped, reconnections, etc.)
    - Latest frame storage + queue consumption API
    - Motion detection triggering (stubbed)
    - Audio stream detection (if enabled)

    Testability:
    - Pass `frame_producer=some_callable` in __init__ to inject frames
      without needing real cameras or network (great for unit tests).

    Observability:
    - get_status() includes frames_captured, frames_dropped, reconnection_count, etc.
    """

    def __init__(
        self,
        camera: Camera,
        main_event_loop: Optional[asyncio.AbstractEventLoop] = None,
        *,
        # For testing: injectable callable that returns the next frame (or None).
        # When provided, real camera opening is skipped entirely.
        frame_producer: Optional[callable] = None,
    ):
        self.camera = camera
        self.camera_id = camera.id
        self._main_event_loop = main_event_loop
        self._frame_producer = frame_producer  # injectable for tests

        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._status_lock = threading.Lock()
        self._status = {
            "status": "stopped",
            "last_frame_time": None,
            "error": None
        }

        # Valid statuses: starting, connecting, connected, reconnecting, error, dead, stopped
        self._valid_statuses = {"starting", "connecting", "connected", "reconnecting", "error", "dead", "stopped"}
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

        # Active capture resources (managed for proper cleanup)
        self._cap = None
        self._av_container = None

        # Heartbeat for detecting hung workers
        self._last_heartbeat: Optional[datetime] = None
        self._heartbeat_lock = threading.Lock()

        # Bounded queue for backpressure between capture thread and async consumers
        # Small size (e.g. 2-4) prevents unbounded memory growth when the async side is slow
        self._frame_queue: queue.Queue = queue.Queue(maxsize=4)

        # === Observability / Metrics ===
        self._frames_captured = 0
        self._frames_dropped = 0          # due to backpressure
        self._reconnection_count = 0
        self._metrics_lock = threading.Lock()

        # Audio extractor (lazy)
        self._audio_extractor = None

        logger.debug(f"CameraCaptureWorker created for camera {self.camera_id}")

    def start(self) -> bool:
        """Start the capture thread (idempotent)."""
        if self._thread and self._thread.is_alive():
            logger.debug(f"Capture thread for camera {self.camera_id} already running")
            return True

        # If we had a previous dead thread, clean it up
        if self._thread and not self._thread.is_alive():
            self._thread = None

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
        """Stop the capture thread, attempting to unblock stuck readers."""
        self._stop_flag.set()

        # Best effort: force-release devices from this thread to unblock a stuck cap.read() / decode()
        self._release_resources()

        thread_was_alive = False
        if self._thread and self._thread.is_alive():
            thread_was_alive = True
            self._thread.join(timeout=timeout)

        if self._thread and self._thread.is_alive():
            logger.warning(
                f"Capture thread for camera {self.camera_id} did not stop within {timeout}s. "
                "Marking as dead. Some resources may remain until process exit."
            )
            with self._status_lock:
                self._status["status"] = "dead"
                self._status["error"] = "Thread did not stop cleanly within timeout"
        else:
            with self._status_lock:
                self._status["status"] = "stopped"

        # Final cleanup attempt
        self._release_resources()

        if thread_was_alive:
            logger.info(f"Stopped capture worker for camera {self.camera_id}")
        else:
            logger.debug(f"stop() called on already-stopped worker for camera {self.camera_id}")

    def get_status(self) -> dict:
        # Force a liveness check (this may update internal status to "dead")
        self.is_alive()

        with self._status_lock:
            status = self._status.copy()

        status["thread_alive"] = bool(self._thread and self._thread.is_alive())
        status["worker_alive"] = status.get("status") not in ("dead", "stopped", "error")

        # Observability metrics
        with self._metrics_lock:
            status["frames_captured"] = self._frames_captured
            status["frames_dropped"] = self._frames_dropped
            status["reconnection_count"] = self._reconnection_count

        return status

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Returns the most recent frame (non-blocking, for quick access)."""
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def get_frame(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """Get the next frame from the bounded queue (with backpressure).

        This is the preferred method for consumers that want to process frames
        at their own pace. Returns None on timeout.
        """
        try:
            frame = self._frame_queue.get(timeout=timeout)
            return frame
        except queue.Empty:
            return None

    def get_queue_size(self) -> int:
        """Current number of frames waiting in the backpressure queue."""
        return self._frame_queue.qsize()

    def _update_status(self, status: str, error: Optional[str] = None):
        if status not in self._valid_statuses:
            status = "error"

        with self._status_lock:
            self._status["status"] = status
            if error:
                self._status["error"] = error
            if status == "connected":
                self._status["last_frame_time"] = datetime.now(timezone.utc).isoformat()

        # Best-effort notification to the main event loop (for MQTT status, UI, etc.)
        self._notify_main_loop(status, error)

    def _update_heartbeat(self):
        """Called on every successfully processed frame."""
        now = datetime.now(timezone.utc)
        with self._heartbeat_lock:
            self._last_heartbeat = now
        with self._status_lock:
            self._status["last_frame_time"] = now.isoformat()

        with self._metrics_lock:
            self._frames_captured += 1

    def _notify_main_loop(self, status: str, error: Optional[str] = None):
        """Safely schedule a status update callback on the main event loop if available."""
        if not self._main_event_loop or not self._main_event_loop.is_running():
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self._async_status_callback(status, error),
                self._main_event_loop
            )
        except Exception:
            # Don't let notification failures affect capture
            pass

    async def _async_status_callback(self, status: str, error: Optional[str] = None):
        """Placeholder for future async callbacks (e.g. publish MQTT status).
        Can be overridden or connected by CameraService / EventProcessor later.
        """
        # For now this is a no-op hook. Real implementations can subscribe to status changes.
        logger.debug(f"Camera {self.camera_id} status changed to '{status}'" + (f" (error: {error})" if error else ""))

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
            use_pyav = False

            try:
                connection_str = self._build_connection_string()

                # Attempt connection (PyAV for rtsps, OpenCV otherwise)
                if self.camera.type == "rtsp" and PYAV_AVAILABLE and connection_str.startswith("rtsps://"):
                    try:
                        self._av_container = av.open(connection_str, options={'rtsp_transport': 'tcp'}, timeout=15.0)
                        use_pyav = True
                    except Exception as e:
                        logger.warning(f"PyAV failed for {camera_id}, falling back to OpenCV: {e}")
                        if self._av_container:
                            self._av_container.close()
                        self._av_container = None

                if not use_pyav:
                    self._cap = cv2.VideoCapture(connection_str)
                    if not self._cap.isOpened():
                        raise ConnectionError("Failed to open camera with OpenCV")

                self._update_status("connected")
                retry_count = 0

                fps = max(1, min(self.camera.frame_rate or 10, 30))
                frame_interval = 1.0 / fps

                while not self._stop_flag.is_set():
                    start_time = time.time()

                    # === Test mode: use injected frame producer ===
                    if self._frame_producer is not None:
                        try:
                            frame = self._frame_producer()
                            if frame is not None:
                                self._process_frame(frame)
                        except Exception as e:
                            logger.warning(f"Frame producer error on {camera_id}: {e}")
                            break

                        elapsed = time.time() - start_time
                        sleep_time = max(0, frame_interval - elapsed)
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                        continue
                    # === End test mode ===

                    if use_pyav and self._av_container:
                        try:
                            for frame in self._av_container.decode(video=0):
                                if self._stop_flag.is_set():
                                    break
                                img = frame.to_ndarray(format='bgr24')
                                self._process_frame(img)
                                break  # Process one frame per iteration
                        except Exception as e:
                            logger.warning(f"PyAV decode error on {camera_id}: {e}")
                            break
                    elif self._cap:
                        ret, frame = self._cap.read()
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
                with self._metrics_lock:
                    self._reconnection_count += 1
                delay = min(base_retry_delay * (2 ** min(retry_count, 4)), max_retry_delay)
                self._update_status("reconnecting", error=str(e))
                logger.warning(f"Capture error on camera {camera_id} (retry {retry_count}): {e}. Reconnecting in {delay}s")

                self._release_resources()

                if not self._stop_flag.is_set():
                    time.sleep(delay)
            finally:
                self._release_resources()

        # Final status update — distinguish between clean stop and unexpected death
        final_status = "stopped" if self._stop_flag.is_set() else "dead"
        with self._status_lock:
            if self._status.get("status") not in ("dead", "stopped"):
                self._status["status"] = final_status
                if final_status == "dead" and not self._status.get("error"):
                    self._status["error"] = "Capture loop exited unexpectedly"

        logger.info(f"Capture loop ended for camera {camera_id} (status={final_status})")

    def _process_frame(self, frame: np.ndarray):
        """Process a captured frame with backpressure.

        Puts the frame into a bounded queue. If the queue is full, the oldest frame
        is dropped (backpressure). This prevents memory blow-up when the consumer
        (EventProcessor / motion detection) is slower than the capture rate.
        """
        with self._frame_lock:
            self._latest_frame = frame

        self._update_heartbeat()

        # Backpressure: drop oldest frame if queue is full
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()  # drop oldest
                self._frame_queue.put_nowait(frame)
                with self._metrics_lock:
                    self._frames_dropped += 1
                logger.debug(f"Dropped oldest frame for camera {self.camera_id} (backpressure)")
            except queue.Empty:
                pass  # race, ignore

        # TODO: Integrate motion detection properly here (currently stubbed in original)

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
        """Release any open capture resources (OpenCV or PyAV)."""
        try:
            if hasattr(self, '_cap') and self._cap is not None:
                self._cap.release()
                self._cap = None
        except Exception:
            pass

        try:
            if hasattr(self, '_av_container') and self._av_container is not None:
                self._av_container.close()
                self._av_container = None
        except Exception:
            pass

        # Also clear latest frame to free memory
        with self._frame_lock:
            self._latest_frame = None

    def is_alive(self) -> bool:
        """Return True if the capture thread is currently running and healthy.

        Considers both thread liveness and recent heartbeat (to detect hung workers).
        """
        if self._thread is None:
            return False

        thread_alive = self._thread.is_alive()

        with self._status_lock:
            status = self._status.get("status", "")

        if not thread_alive:
            if status not in ("dead", "stopped"):
                with self._status_lock:
                    self._status["status"] = "dead"
                    if not self._status.get("error"):
                        self._status["error"] = "Capture thread died unexpectedly"
            return False

        if status in ("dead", "error"):
            return False

        # Check for hung worker (no frame for a long time while supposed to be connected)
        with self._heartbeat_lock:
            last_hb = self._last_heartbeat

        if last_hb and status == "connected":
            seconds_since_frame = (datetime.now(timezone.utc) - last_hb).total_seconds()
            if seconds_since_frame > 90:  # generous timeout for slow cameras
                with self._status_lock:
                    self._status["status"] = "dead"
                    self._status["error"] = f"No frame received for {int(seconds_since_frame)}s"
                return False

        return True