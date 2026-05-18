"""
Camera capture service with thread management and reconnection logic

Handles RTSP and USB camera capture in background threads with automatic
reconnection on stream dropout.

Migrated to @singleton decorator (core.decorators) as the core service reference
example for #450 (Lightweight DI Container).
"""
import cv2
import threading
import time
import logging
import asyncio
from typing import Dict, Any
from datetime import datetime, timezone
import numpy as np
from app.core.decorators import singleton

try:
    import av
    PYAV_AVAILABLE = True
except ImportError:
    PYAV_AVAILABLE = False

from app.models.camera import Camera
from app.services.motion_detection_service import motion_detection_service
from app.services.audio_stream_service import get_audio_stream_extractor, AudioStreamExtractor
from app.core.database import get_db
from app.services.camera_capture_worker import CameraCaptureWorker
# Note: event_processor imports are done locally to avoid circular imports

logger = logging.getLogger(__name__)


@singleton
class CameraService:
    """
    Manages camera capture workers and handles connection lifecycle.

    Features:
    - One CameraCaptureWorker per camera (background thread, reconnection, frame capture)
    - Automatic reconnection with exponential backoff
    - Thread-safe status and latest frame access via workers
    - RTSP (PyAV + OpenCV) and USB camera support
    - Configurable frame rate
    - Audio stream support (Phase 6)

    CameraService is now a thin manager/orchestrator of specialized CameraCaptureWorker instances.
    """

    def __init__(self):
        """Initialize camera service with worker-based capture management"""
        self._workers: Dict[str, CameraCaptureWorker] = {}
        self._status_lock = threading.Lock()
        self._main_event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._audio_extractor: Optional[AudioStreamExtractor] = None

        # Restart attempt tracking for automatic disabling (stronger recovery policy)
        self._restart_attempts: Dict[str, int] = {}
        self._last_restart_time: Dict[str, datetime] = {}

        self.MAX_RESTART_ATTEMPTS = 5
        self.RESTART_WINDOW_SECONDS = 3600  # 1 hour

        # Cameras that have been automatically disabled due to repeated failures
        self._capture_disabled: set = set()

        logger.info("CameraService initialized (worker mode)")

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Set the main event loop for thread-safe async calls.
        Should be called from the main async context during app startup.
        """
        self._main_event_loop = loop
        logger.info("Main event loop set for camera service")

    def start_camera(self, camera: Camera) -> bool:
        """
        Start capturing from camera using a dedicated CameraCaptureWorker.
        """
        camera_id = str(camera.id)

        if camera_id in self._capture_disabled:
            logger.warning(f"Refusing to start camera {camera_id} - it is capture-disabled due to repeated failures.")
            return False

        if hasattr(camera, 'source_type') and camera.source_type == 'protect':
            logger.debug(f"Camera {camera_id} is a Protect camera - skipping (managed by ProtectEventHandler)")
            return True

        if camera_id in self._workers and self._workers[camera_id].is_alive():
            logger.warning(f"Camera {camera_id} already running")
            return False

        try:
            if self._main_event_loop is None:
                try:
                    self._main_event_loop = asyncio.get_running_loop()
                except RuntimeError:
                    try:
                        self._main_event_loop = asyncio.get_event_loop()
                    except RuntimeError:
                        self._main_event_loop = None

            worker = CameraCaptureWorker(camera, self._main_event_loop)
            if worker.start():
                self._workers[camera_id] = worker
                logger.info(f"Started CameraCaptureWorker for {camera_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to start CameraCaptureWorker for {camera_id}: {e}", exc_info=True)
            return False

    def stop_camera(self, camera_id: str, timeout: float = 5.0) -> None:
        """Stop a camera by delegating to its CameraCaptureWorker (if any)."""
        worker = self._workers.pop(camera_id, None)
        if worker:
            worker.stop(timeout)
        else:
            logger.debug(f"stop_camera called for {camera_id} but no active worker found")

        # Always attempt secondary cleanups (motion, audio, MQTT status)
        try:
            motion_detection_service.cleanup_camera(camera_id)
        except Exception as e:
            logger.debug(f"Error cleaning up motion detection for camera {camera_id}: {e}")

        if self._audio_extractor is not None:
            try:
                self._audio_extractor.remove_buffer(camera_id)
            except Exception as e:
                logger.debug(f"Error cleaning up audio buffer for camera {camera_id}: {e}")

        # Publish unavailable status (best effort)
        try:
            if self._main_event_loop and self._main_event_loop.is_running():
                from app.services.mqtt_status_service import publish_camera_status_update
                from app.core.database import SessionLocal
                from app.models.camera import Camera

                with SessionLocal() as db:
                    camera = db.query(Camera).filter(Camera.id == camera_id).first()
                    if camera:
                        asyncio.run_coroutine_threadsafe(
                            publish_camera_status_update(
                                camera_id=camera_id,
                                camera_name=camera.name,
                                status="unavailable",
                                source_type=camera.source_type or camera.type or "rtsp"
                            ),
                            self._main_event_loop
                        )
        except Exception as e:
            logger.debug(f"Failed to publish MQTT unavailable status for {camera_id}: {e}")

        logger.info(f"Stopped camera {camera_id}")

    # _build_rtsp_url removed — URL building now lives inside CameraCaptureWorker (Phase 5)

    # _update_status removed — status is now managed per-worker in CameraCaptureWorker (Phase 5)

    def get_camera_status(self, camera_id: str) -> Optional[dict]:
        """Delegate to the CameraCaptureWorker (removes dead workers)."""
        str_id = str(camera_id)
        worker = self._workers.get(str_id)

        status = {
            "capture_disabled": str_id in self._capture_disabled,
            "restart_attempts": self._restart_attempts.get(str_id, 0),
        }

        if not worker:
            status.update({
                "status": "stopped" if str_id not in self._capture_disabled else "disabled",
                "worker_alive": False,
                "thread_alive": False,
            })
            return status

        worker_status = worker.get_status()
        if not worker_status.get("worker_alive", True):
            logger.warning(f"Removing dead capture worker for camera {str_id} during status check")
            self._workers.pop(str_id, None)
            status.update({
                "status": "dead",
                "worker_alive": False,
                "thread_alive": False,
            })
            return status

        status.update(worker_status)
        return status

    def get_all_camera_status(self) -> Dict[str, dict]:
        """Aggregate status from all cameras (including disabled ones)."""
        status = {}

        # First, include any disabled cameras even if they have no worker
        for camera_id in self._capture_disabled:
            if camera_id not in status:
                status[camera_id] = {
                    "status": "disabled",
                    "worker_alive": False,
                    "thread_alive": False,
                    "capture_disabled": True,
                    "restart_attempts": self._restart_attempts.get(camera_id, 0),
                }

        # Then active workers
        dead_workers = []
        for camera_id, worker in self._workers.items():
            worker_status = worker.get_status()
            status[camera_id] = worker_status
            status[camera_id]["capture_disabled"] = camera_id in self._capture_disabled
            status[camera_id]["restart_attempts"] = self._restart_attempts.get(camera_id, 0)

            if not worker_status.get("worker_alive", True):
                dead_workers.append(camera_id)

        for camera_id in dead_workers:
            self._workers.pop(camera_id, None)

        return status

    def get_camera_health_summary(self) -> Dict[str, Any]:
        """High-level health summary for monitoring and the /health endpoint."""
        all_status = self.get_all_camera_status()

        healthy = 0
        unhealthy = 0
        disabled = 0

        for status in all_status.values():
            if status.get("capture_disabled"):
                disabled += 1
            elif status.get("worker_alive"):
                healthy += 1
            else:
                unhealthy += 1

        return {
            "total": len(all_status),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "disabled": disabled,
            "cameras": all_status,
        }

    def get_latest_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """Delegate to the CameraCaptureWorker."""
        worker = self._workers.get(camera_id)
        return worker.get_latest_frame() if worker else None

    def get_frame(self, camera_id: str, timeout: float = 0.1) -> Optional[np.ndarray]:
        """Get next frame from the worker's bounded queue (backpressure-aware)."""
        worker = self._workers.get(camera_id)
        return worker.get_frame(timeout) if worker else None

    def get_queue_size(self, camera_id: str) -> int:
        """Number of frames currently queued for this camera."""
        worker = self._workers.get(camera_id)
        return worker.get_queue_size() if worker else 0

    def get_camera_metrics(self, camera_id: str) -> Optional[dict]:
        """Return basic observability metrics for a camera (if worker exists)."""
        worker = self._workers.get(camera_id)
        if not worker:
            return None
        status = worker.get_status()
        return {
            "frames_captured": status.get("frames_captured", 0),
            "frames_dropped": status.get("frames_dropped", 0),
            "reconnection_count": status.get("reconnection_count", 0),
            "last_frame_time": status.get("last_frame_time"),
            "error": status.get("error"),
        }

    def stop_all_cameras(self, timeout: float = 5.0) -> None:
        """Stop all active CameraCaptureWorkers gracefully."""
        if not self._workers:
            return

        logger.info(f"Stopping {len(self._workers)} camera workers...")
        for camera_id in list(self._workers.keys()):
            try:
                self.stop_camera(camera_id, timeout)
            except Exception as e:
                logger.error(f"Error stopping camera {camera_id} during shutdown: {e}")

        self._workers.clear()
        logger.info("All camera workers stopped")

    def enable_camera_capture(self, camera_id: str) -> None:
        """Manually re-enable capture for a previously disabled camera."""
        cid = str(camera_id)
        if cid in self._capture_disabled:
            self._capture_disabled.remove(cid)
            self._restart_attempts[cid] = 0
            logger.info(f"Capture manually re-enabled for camera {cid}")

    def disable_camera_capture(self, camera_id: str) -> None:
        """Manually disable capture for a camera (admin action)."""
        cid = str(camera_id)
        self._capture_disabled.add(cid)
        self.stop_camera(cid)
        # Set attempts to max so it stays disabled until manually re-enabled
        self._restart_attempts[cid] = self.MAX_RESTART_ATTEMPTS
        logger.info(f"Capture manually disabled for camera {cid}")

    def restart_camera(self, camera: Camera, timeout: float = 5.0) -> bool:
        """
        Attempt to restart a camera's capture worker.
        Implements stronger recovery policy: disables camera after too many failures.
        """
        camera_id = str(camera.id)
        now = datetime.now(timezone.utc)

        # Check if already disabled
        if camera_id in self._capture_disabled:
            logger.warning(f"Camera {camera_id} is capture-disabled. Manual re-enable required.")
            return False

        # Track attempts within time window
        last_attempt = self._last_restart_time.get(camera_id)
        if last_attempt and (now - last_attempt).total_seconds() > self.RESTART_WINDOW_SECONDS:
            # Window expired, reset counter
            self._restart_attempts[camera_id] = 0

        attempts = self._restart_attempts.get(camera_id, 0) + 1
        self._restart_attempts[camera_id] = attempts
        self._last_restart_time[camera_id] = now

        logger.info(f"Attempting to restart capture for camera {camera_id} (attempt {attempts})")

        # Stop first
        self.stop_camera(camera_id, timeout)
        time.sleep(0.5)

        success = self.start_camera(camera)

        if success:
            logger.info(f"Successfully restarted capture for camera {camera_id}")
            # Reset counter on success
            self._restart_attempts[camera_id] = 0
            return True
        else:
            logger.warning(f"Failed to restart capture for camera {camera_id} (attempt {attempts})")

            # Disable if over limit
            if attempts >= self.MAX_RESTART_ATTEMPTS:
                self._capture_disabled.add(camera_id)
                logger.error(
                    f"Camera {camera_id} has been DISABLED after {attempts} failed restarts "
                    f"within the window. Manual intervention required to re-enable."
                )

            return False

    USB_CAMERA_SCAN_MAX_INDEX = 10  # How far to scan for USB cameras

    def detect_usb_cameras(self) -> list[int]:
        """
        Enumerate available USB camera device indices.

        Tries to open VideoCapture for device indices 0..USB_CAMERA_SCAN_MAX_INDEX-1.

        Returns:
            List of available device indices (e.g., [0, 1, 2])

        Note:
            Blocking operation (1-2 seconds). On Linux may require 'video' group.
        """
        available_devices = []

        logger.debug(f"Scanning for USB cameras (indices 0-{self.USB_CAMERA_SCAN_MAX_INDEX-1})")

        for device_index in range(self.USB_CAMERA_SCAN_MAX_INDEX):
            cap = None
            try:
                cap = cv2.VideoCapture(device_index)

                # Set short timeout to avoid hanging
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1000)

                # Check if device is actually accessible
                if cap.isOpened():
                    # Try to read a test frame to verify it's a real camera
                    ret, _ = cap.read()
                    if ret:
                        available_devices.append(device_index)
                        logger.debug(f"Found USB camera at device index {device_index}")

            except Exception as e:
                logger.debug(f"Device index {device_index} not available: {e}")

            finally:
                if cap is not None:
                    cap.release()

        logger.info(f"USB camera detection complete: found {len(available_devices)} devices")

        return available_devices

    def get_audio_status(self, camera_id: str) -> Dict[str, Any]:
        """
        Get audio buffer status for a camera (Phase 6 - P6-3.1).

        Lazily initializes the AudioStreamExtractor if needed.
        Note: Audio extraction is currently a cross-cutting concern separate from
        CameraCaptureWorker. Future work may move audio handling into the worker.
        """
        worker_running = camera_id in self._workers and self._workers[camera_id].is_alive()

        if self._audio_extractor is None:
            try:
                self._audio_extractor = get_audio_stream_extractor()
            except Exception as e:
                logger.debug(f"Could not initialize audio extractor: {e}")
                return {
                    "has_buffer": False,
                    "duration_seconds": 0.0,
                    "is_empty": True,
                    "codec": None,
                    "worker_running": worker_running
                }

        status = self._audio_extractor.get_buffer_status(camera_id)
        status["worker_running"] = worker_running
        return status


# Backward compatible thin getter (now delegates to @singleton decorator)
def get_camera_service() -> CameraService:
    """
    Get the global CameraService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code can simply use CameraService() directly.
    """
    return CameraService()


def reset_camera_service() -> None:
    """
    Reset the global CameraService instance.

    Useful for testing (clears all camera capture workers, threads, etc.).
    """
    CameraService._reset_instance()
