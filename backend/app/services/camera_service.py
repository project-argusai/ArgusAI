"""
Camera capture service with thread management and reconnection logic

Handles RTSP and USB camera capture in background threads with automatic
reconnection on stream dropout.
"""
import cv2
import threading
import time
import logging
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime, timezone
import numpy as np

try:
    import av
    PYAV_AVAILABLE = True
except ImportError:
    PYAV_AVAILABLE = False

from app.models.camera import Camera
from app.services.motion_detection_service import motion_detection_service
from app.core.database import get_db
# Note: event_processor imports are done locally to avoid circular imports

logger = logging.getLogger(__name__)


class CameraService:
    """
    Manages camera capture threads and handles connection lifecycle

    Features:
    - Background thread per camera for non-blocking frame capture
    - Automatic reconnection with exponential backoff (30s base, capped at 5 min)
    - Thread-safe status tracking
    - RTSP and USB camera support
    - Configurable frame rate (1-30 FPS)

    Attributes:
        _capture_threads: Dict mapping camera_id to Thread objects
        _active_captures: Dict mapping camera_id to cv2.VideoCapture objects
        _stop_flags: Dict mapping camera_id to stop event flags
        _status_lock: Threading lock for status dictionary access
        _camera_status: Dict tracking connection status per camera
    """

    def __init__(self):
        """Initialize camera service with empty thread tracking"""
        self._capture_threads: Dict[str, threading.Thread] = {}
        self._active_captures: Dict[str, cv2.VideoCapture] = {}
        self._stop_flags: Dict[str, threading.Event] = {}
        self._status_lock = threading.Lock()
        self._camera_status: Dict[str, dict] = {}
        self._latest_frames: Dict[str, np.ndarray] = {}  # Store latest frame per camera
        self._frame_lock = threading.Lock()  # Lock for frame access
        self._main_event_loop: Optional[asyncio.AbstractEventLoop] = None  # Store main event loop for thread-safe async calls

        logger.info("CameraService initialized")

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Set the main event loop for thread-safe async calls.
        Should be called from the main async context during app startup.
        """
        self._main_event_loop = loop
        logger.info("Main event loop set for camera service")

    def start_camera(self, camera: Camera) -> bool:
        """
        Start capturing from camera in background thread

        Args:
            camera: Camera model instance with connection details

        Returns:
            True if camera thread started successfully, False otherwise

        Side effects:
            - Spawns background thread running _capture_loop()
            - Stores thread reference in _capture_threads
            - Updates _camera_status to 'starting'
        """
        camera_id = camera.id

        # Protect cameras use WebSocket events from Protect API, not frame capture
        # They should not be started via camera_service
        if hasattr(camera, 'source_type') and camera.source_type == 'protect':
            logger.debug(f"Camera {camera_id} is a Protect camera - skipping capture thread (uses WebSocket events)")
            return True  # Return True since Protect cameras are managed by protect_service

        # Check if already running
        if camera_id in self._capture_threads and self._capture_threads[camera_id].is_alive():
            logger.warning(f"Camera {camera_id} already running")
            return False

        try:
            # Capture the main event loop for thread-safe async calls
            try:
                self._main_event_loop = asyncio.get_running_loop()
            except RuntimeError:
                # If no running loop, try to get the current loop
                try:
                    self._main_event_loop = asyncio.get_event_loop()
                except RuntimeError:
                    logger.warning("No event loop available for async event processing")
                    self._main_event_loop = None

            # Create stop event for this camera
            stop_event = threading.Event()
            self._stop_flags[camera_id] = stop_event

            # Update status
            with self._status_lock:
                self._camera_status[camera_id] = {
                    "status": "starting",
                    "last_frame_time": None,
                    "error": None
                }

            # Create and start background thread
            thread = threading.Thread(
                target=self._capture_loop,
                args=(camera,),
                name=f"camera_{camera.name}_{camera_id[:8]}",
                daemon=True
            )
            thread.start()

            # Store thread reference
            self._capture_threads[camera_id] = thread

            logger.info(
                f"Started camera {camera_id}",
                extra={
                    "camera_id": camera_id,
                    "camera_name": camera.name,
                    "camera_type": camera.type,
                    "frame_rate": camera.frame_rate
                }
            )

            return True

        except Exception as e:
            logger.error(f"Failed to start camera {camera_id}: {e}", exc_info=True)

            # Clean up on failure
            with self._status_lock:
                self._camera_status[camera_id] = {
                    "status": "error",
                    "last_frame_time": None,
                    "error": str(e)
                }

            return False

    def stop_camera(self, camera_id: str, timeout: float = 5.0) -> None:
        """
        Stop camera capture thread gracefully

        Args:
            camera_id: UUID of camera to stop
            timeout: Maximum seconds to wait for thread to join (default 5s)

        Side effects:
            - Sets stop flag for camera thread
            - Waits for thread to join (up to timeout)
            - Releases VideoCapture resources
            - Removes from tracking dictionaries
        """
        if camera_id not in self._capture_threads:
            logger.warning(f"Camera {camera_id} not running")
            return

        try:
            # Signal thread to stop
            if camera_id in self._stop_flags:
                self._stop_flags[camera_id].set()

            # Wait for thread to finish
            thread = self._capture_threads[camera_id]
            thread.join(timeout=timeout)

            if thread.is_alive():
                logger.warning(
                    f"Camera {camera_id} thread did not stop within {timeout}s timeout"
                )

            # Clean up resources
            if camera_id in self._active_captures:
                cap = self._active_captures[camera_id]
                if cap is not None:
                    cap.release()
                del self._active_captures[camera_id]

            # Remove from tracking
            del self._capture_threads[camera_id]
            if camera_id in self._stop_flags:
                del self._stop_flags[camera_id]

            # Update status
            with self._status_lock:
                if camera_id in self._camera_status:
                    del self._camera_status[camera_id]

            # Clean up latest frame
            with self._frame_lock:
                if camera_id in self._latest_frames:
                    del self._latest_frames[camera_id]

            # Clean up motion detection resources
            try:
                motion_detection_service.cleanup_camera(camera_id)
            except Exception as e:
                logger.error(f"Error cleaning up motion detection for camera {camera_id}: {e}", exc_info=True)

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

        except Exception as e:
            logger.error(f"Error stopping camera {camera_id}: {e}", exc_info=True)

    def _capture_loop(self, camera: Camera) -> None:
        """
        Background thread loop for continuous frame capture

        This is the core capture logic that runs in a dedicated thread per camera.
        Handles:
        - Initial connection to camera
        - Frame capture at configured FPS
        - Frame read failure detection
        - Automatic reconnection with backoff
        - Motion detection stub (placeholder for F2)

        Args:
            camera: Camera model with connection details

        Thread-safe: Yes (writes to shared status dict use lock)
        Termination: Exits when stop_flag is set
        """
        camera_id = camera.id
        stop_flag = self._stop_flags.get(camera_id)

        # Build connection string based on camera type
        if camera.type == "rtsp":
            connection_str = self._build_rtsp_url(camera)
        elif camera.type == "usb":
            connection_str = camera.device_index
        else:
            logger.error(f"Unknown camera type: {camera.type}")
            self._update_status(camera_id, "error", error=f"Unknown camera type: {camera.type}")
            return

        # Reconnection parameters
        base_retry_delay = 30  # seconds
        max_retry_delay = 300  # 5 minutes
        retry_count = 0

        logger.info(f"Starting capture loop for camera {camera_id}")

        while not stop_flag.is_set():
            cap = None
            av_container = None
            av_stream = None
            use_pyav = False

            try:
                # Attempt to connect to camera
                logger.debug(f"Connecting to camera {camera_id} (attempt {retry_count + 1})")

                # For RTSP cameras (especially rtsps://), use PyAV if available
                if camera.type == "rtsp" and PYAV_AVAILABLE and connection_str.startswith("rtsps://"):
                    try:
                        logger.debug(f"Using PyAV for secure RTSP stream: {camera_id}")
                        av_container = av.open(
                            connection_str,
                            options={
                                'rtsp_transport': 'tcp',
                                'stimeout': '10000000',  # 10 second socket timeout in microseconds
                            },
                            timeout=15.0  # 15 second overall timeout
                        )
                        av_stream = av_container.streams.video[0]
                        use_pyav = True
                        logger.debug(f"PyAV connected: {av_stream.codec_context.width}x{av_stream.codec_context.height}")
                    except Exception as e:
                        logger.warning(f"PyAV failed for camera {camera_id}, falling back to OpenCV: {e}")
                        if av_container:
                            av_container.close()
                        av_container = None
                        use_pyav = False

                # Fall back to OpenCV (or use for USB cameras)
                if not use_pyav:
                    if camera.type == "rtsp":
                        cap = cv2.VideoCapture(connection_str, cv2.CAP_FFMPEG)
                    else:
                        cap = cv2.VideoCapture(connection_str)
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)

                    if not cap.isOpened():
                        raise ConnectionError(f"Failed to open camera {camera_id}")

                # Check if connection successful (either method)
                if not use_pyav and (cap is None or not cap.isOpened()):
                    raise ConnectionError(f"Failed to open camera {camera_id}")

                # Store active capture
                self._active_captures[camera_id] = cap

                # Reset retry count on successful connection
                retry_count = 0

                # Update status to connected
                self._update_status(camera_id, "connected")

                # Log connection with type-specific message
                if camera.type == "usb":
                    log_msg = (
                        f"USB camera {camera.name} (device {camera.device_index}) reconnected"
                        if retry_count > 0
                        else f"USB camera {camera.name} (device {camera.device_index}) connected"
                    )
                else:
                    log_msg = f"Camera {camera_id} reconnected" if retry_count > 0 else f"Camera {camera_id} connected"

                logger.info(log_msg)

                # Calculate sleep interval for target FPS
                sleep_interval = 1.0 / camera.frame_rate if camera.frame_rate > 0 else 0.2

                # Create PyAV frame generator if using PyAV
                av_frame_gen = None
                if use_pyav and av_container:
                    av_frame_gen = av_container.decode(av_stream)

                # Main capture loop
                while not stop_flag.is_set():
                    frame_start_time = time.time()

                    # Read frame (PyAV or OpenCV)
                    ret = False
                    frame = None

                    if use_pyav and av_frame_gen:
                        try:
                            av_frame = next(av_frame_gen)
                            frame = av_frame.to_ndarray(format='bgr24')
                            ret = True
                        except (StopIteration, av.error.EOFError):
                            ret = False
                        except Exception as e:
                            logger.debug(f"PyAV frame read error: {e}")
                            ret = False
                    else:
                        ret, frame = cap.read()

                    if not ret:
                        # Frame read failed - trigger reconnection
                        if camera.type == "usb":
                            logger.warning(
                                f"USB camera {camera.name} (device {camera.device_index}) disconnected"
                            )
                        else:
                            logger.warning(f"Camera {camera.name} disconnected (frame read failed)")

                        self._update_status(camera_id, "disconnected", error="Frame read failed")

                        # TODO: Emit WebSocket event CAMERA_STATUS_CHANGED
                        # self._emit_websocket_event("CAMERA_STATUS_CHANGED", {
                        #     "camera_id": camera_id,
                        #     "status": "disconnected",
                        #     "timestamp": datetime.utcnow().isoformat() + "Z"
                        # })

                        break  # Exit inner loop to trigger reconnection

                    # Frame captured successfully
                    self._update_status(camera_id, "connected")

                    # Store latest frame for preview endpoint
                    with self._frame_lock:
                        self._latest_frames[camera_id] = frame.copy()

                    # Motion detection integration (F2.1)
                    if camera.motion_enabled:
                        frame_start = time.time()
                        try:
                            # Get database session for motion event storage
                            db = next(get_db())
                            try:
                                motion_event = motion_detection_service.process_frame(
                                    camera_id=camera_id,
                                    frame=frame,
                                    camera=camera,
                                    db=db
                                )
                                if motion_event:
                                    logger.info(f"Motion event {motion_event.id} created for camera {camera.name}")

                                    # Queue for AI processing (import locally to avoid circular import)
                                    from app.services.event_processor import get_event_processor, ProcessingEvent
                                    event_processor = get_event_processor()
                                    if event_processor and event_processor.running:
                                        processing_event = ProcessingEvent(
                                            camera_id=camera_id,
                                            camera_name=camera.name,
                                            frame=frame.copy(),
                                            timestamp=motion_event.timestamp,
                                            detected_objects=["motion_detected"],
                                            metadata={
                                                "motion_event_id": motion_event.id,
                                                "confidence": motion_event.confidence,
                                                "algorithm": motion_event.algorithm_used,
                                            }
                                        )
                                        # Queue from sync thread to async queue using stored event loop
                                        try:
                                            if self._main_event_loop and self._main_event_loop.is_running():
                                                asyncio.run_coroutine_threadsafe(
                                                    event_processor.queue_event(processing_event),
                                                    self._main_event_loop
                                                )
                                                logger.debug(f"Motion event {motion_event.id} queued for AI processing")
                                            else:
                                                logger.warning("Main event loop not available or not running, skipping AI processing")
                                        except Exception as e:
                                            logger.warning(f"Failed to queue motion event for AI: {e}")
                            finally:
                                db.close()

                            # Log processing time for performance monitoring
                            processing_time = (time.time() - frame_start) * 1000  # Convert to ms
                            if processing_time > 100:  # Warn if exceeds 100ms target
                                logger.warning(
                                    f"Motion detection processing slow: {processing_time:.1f}ms "
                                    f"(target <100ms) for camera {camera.name}"
                                )
                            else:
                                logger.debug(f"Motion detection: {processing_time:.1f}ms for camera {camera.name}")

                        except Exception as e:
                            logger.error(f"Motion detection error for camera {camera_id}: {e}", exc_info=True)

                    # Maintain target FPS
                    frame_processing_time = time.time() - frame_start_time
                    sleep_time = max(0, sleep_interval - frame_processing_time)

                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    else:
                        logger.debug(
                            f"Camera {camera_id} frame processing slower than target FPS "
                            f"({frame_processing_time:.3f}s > {sleep_interval:.3f}s)"
                        )

                # If we exit the inner loop, frame read failed - attempt reconnection

            except Exception as e:
                logger.error(f"Camera {camera_id} error: {e}", exc_info=True)
                self._update_status(camera_id, "error", error=str(e))

            finally:
                # Release capture on error or disconnect
                if cap is not None:
                    cap.release()
                    if camera_id in self._active_captures:
                        del self._active_captures[camera_id]
                # Close PyAV container if used
                if av_container is not None:
                    try:
                        av_container.close()
                    except Exception:
                        pass

            # Reconnection logic with exponential backoff
            if not stop_flag.is_set():
                retry_count += 1

                # Calculate backoff delay (exponential with cap)
                delay = min(base_retry_delay * (2 ** (retry_count - 1)), max_retry_delay)

                logger.info(
                    f"Camera {camera_id} will retry connection in {delay}s "
                    f"(attempt {retry_count})"
                )

                # Wait with ability to cancel during sleep
                stop_flag.wait(timeout=delay)

        logger.info(f"Capture loop exited for camera {camera_id}")

    def _build_rtsp_url(self, camera: Camera) -> str:
        """
        Build RTSP URL with credentials

        Args:
            camera: Camera model with RTSP details

        Returns:
            RTSP URL string with embedded credentials (if provided)

        Example:
            rtsp://username:password@192.168.1.50:554/stream1
        """
        rtsp_url = camera.rtsp_url

        # If credentials provided, inject into URL
        if camera.username:
            # Get decrypted password
            password = camera.get_decrypted_password() if camera.password else ""

            # Parse URL to inject credentials
            if "://" in rtsp_url:
                protocol, rest = rtsp_url.split("://", 1)

                # Build credentials string
                creds = camera.username
                if password:
                    creds += f":{password}"

                # Rebuild URL with credentials
                rtsp_url = f"{protocol}://{creds}@{rest}"

        # Sanitize URL for logging (remove credentials)
        safe_url = rtsp_url
        if "@" in safe_url:
            protocol, rest = safe_url.split("://", 1)
            if "@" in rest:
                _, host_part = rest.split("@", 1)
                safe_url = f"{protocol}://***:***@{host_part}"

        logger.debug(f"Built RTSP URL: {safe_url}")

        return rtsp_url

    def _update_status(self, camera_id: str, status: str, error: Optional[str] = None) -> None:
        """
        Thread-safe update of camera status

        Args:
            camera_id: UUID of camera
            status: Status string ('starting', 'connected', 'disconnected', 'error')
            error: Optional error message
        """
        with self._status_lock:
            self._camera_status[camera_id] = {
                "status": status,
                "last_frame_time": datetime.now(timezone.utc) if status == "connected" else None,
                "error": error
            }

        # Publish status to MQTT (Story P4-2.5, AC1, AC9)
        # This is called from capture thread, so schedule async task on main loop
        try:
            if self._main_event_loop and self._main_event_loop.is_running():
                from app.services.mqtt_status_service import publish_camera_status_update
                from app.core.database import SessionLocal
                from app.models.camera import Camera

                # Get camera details from database
                with SessionLocal() as db:
                    camera = db.query(Camera).filter(Camera.id == camera_id).first()
                    if camera:
                        camera_name = camera.name
                        source_type = camera.source_type or camera.type or "rtsp"
                    else:
                        # Fallback if camera not found
                        camera_name = f"Camera {camera_id[:8]}"
                        source_type = "rtsp"

                asyncio.run_coroutine_threadsafe(
                    publish_camera_status_update(
                        camera_id=camera_id,
                        camera_name=camera_name,
                        status=status,
                        source_type=source_type
                    ),
                    self._main_event_loop
                )
                logger.debug(
                    f"Queued MQTT status update for camera {camera_id}: {status}",
                    extra={"camera_id": camera_id, "status": status}
                )
        except Exception as e:
            # MQTT status updates should not block camera operations
            logger.debug(f"Failed to queue MQTT status update: {e}")

    def get_camera_status(self, camera_id: str) -> Optional[dict]:
        """
        Get current status of camera

        Args:
            camera_id: UUID of camera

        Returns:
            Status dict or None if camera not found
        """
        with self._status_lock:
            return self._camera_status.get(camera_id)

    def get_all_camera_status(self) -> Dict[str, dict]:
        """
        Get status of all cameras

        Returns:
            Dict mapping camera_id to status dict
        """
        with self._status_lock:
            return self._camera_status.copy()

    def get_latest_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """
        Get the latest captured frame for a camera

        Args:
            camera_id: UUID of camera

        Returns:
            Latest frame as numpy array (BGR format) or None if no frame available

        Thread-safe: Yes (uses frame_lock)
        """
        with self._frame_lock:
            frame = self._latest_frames.get(camera_id)
            # Return a copy to prevent external modification
            return frame.copy() if frame is not None else None

    def stop_all_cameras(self, timeout: float = 5.0) -> None:
        """
        Stop all running camera threads

        Args:
            timeout: Maximum seconds to wait per camera thread
        """
        camera_ids = list(self._capture_threads.keys())

        for camera_id in camera_ids:
            self.stop_camera(camera_id, timeout=timeout)

        logger.info(f"Stopped all cameras ({len(camera_ids)} total)")

    def detect_usb_cameras(self) -> list[int]:
        """
        Enumerate available USB camera device indices

        Tries to open VideoCapture for device indices 0-9 and returns
        list of indices that successfully open.

        Returns:
            List of available device indices (e.g., [0, 1, 2])

        Note:
            This is a blocking operation that may take 1-2 seconds.
            On Linux, may require user in 'video' group.
        """
        available_devices = []

        logger.debug("Scanning for USB cameras (indices 0-9)")

        for device_index in range(10):
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
