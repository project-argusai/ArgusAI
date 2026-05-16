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
from typing import Dict, Optional, Any
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
        camera_id = camera.id

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
        """Stop a camera by delegating to its CameraCaptureWorker."""
        worker = self._workers.pop(camera_id, None)
        if worker:
            worker.stop(timeout)
        else:
            logger.warning(f"Camera {camera_id} not running")
            try:
                motion_detection_service.cleanup_camera(camera_id)
            except Exception as e:
                logger.error(f"Error cleaning up motion detection for camera {camera_id}: {e}", exc_info=True)

            # Phase 6 (P6-3.1): Clean up audio buffer
            if self._audio_extractor is not None:
                try:
                    self._audio_extractor.remove_buffer(camera_id)
                except Exception as e:
                    logger.debug(f"Error cleaning up audio buffer for camera {camera_id}: {e}")

            # Publish unavailable status to MQTT (Story P4-2.5, AC9)
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
                logger.debug(f"Failed to publish MQTT unavailable status: {e}")

            logger.info(f"Stopped camera {camera_id}")

    # _build_rtsp_url removed — URL building now lives inside CameraCaptureWorker (Phase 5)

    # _update_status removed — status is now managed per-worker in CameraCaptureWorker (Phase 5)

    def get_camera_status(self, camera_id: str) -> Optional[dict]:
        """Delegate to the CameraCaptureWorker."""
        worker = self._workers.get(camera_id)
        return worker.get_status() if worker else None

    def get_all_camera_status(self) -> Dict[str, dict]:
        """Aggregate status from all active workers."""
        status = {}
        for camera_id, worker in self._workers.items():
            status[camera_id] = worker.get_status()
        return status

    def get_latest_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """Delegate to the CameraCaptureWorker."""
        worker = self._workers.get(camera_id)
        return worker.get_latest_frame() if worker else None

    def stop_all_cameras(self, timeout: float = 5.0) -> None:
        """Stop all workers."""
        for camera_id in list(self._workers.keys()):
            self.stop_camera(camera_id, timeout)

        logger.info("Stopped all cameras")

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
