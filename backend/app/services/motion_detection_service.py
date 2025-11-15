"""
Motion Detection Service - Singleton service managing motion detection per camera

Features:
- Per-camera MotionDetector instance management
- Cooldown period enforcement
- Database event storage
- Thread-safe state management
- Full frame thumbnail generation
"""
import cv2
import numpy as np
import base64
import threading
import logging
import json
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.services.motion_detector import MotionDetector
from app.models.motion_event import MotionEvent
from app.models.camera import Camera
from app.core.database import get_db

logger = logging.getLogger(__name__)


class MotionDetectionService:
    """
    Singleton service for managing motion detection across all cameras

    Thread Safety:
    - Uses Lock for shared state (cooldown tracking, detector instances)
    - Safe to call from multiple camera threads

    Cooldown Management:
    - Prevents spam by enforcing minimum time between events
    - Per-camera cooldown tracking

    Performance:
    - Processes frames in <100ms (target: 50-80ms)
    - Generates base64 thumbnails (~50KB per event)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern: Only one instance exists"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize service (only runs once due to singleton pattern)"""
        if self._initialized:
            return

        # Thread-safe state tracking
        self._detectors: Dict[str, MotionDetector] = {}  # camera_id -> MotionDetector
        self._last_event_time: Dict[str, datetime] = {}  # camera_id -> last event timestamp
        self._state_lock = threading.Lock()

        self._initialized = True
        logger.info("MotionDetectionService initialized (singleton)")

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        camera: Camera,
        db: Session
    ) -> Optional[MotionEvent]:
        """
        Process a single frame for motion detection

        Args:
            camera_id: UUID of camera
            frame: Current frame from cv2.VideoCapture
            camera: Camera model instance (for config)
            db: Database session

        Returns:
            MotionEvent if motion detected AND cooldown elapsed, else None

        Side Effects:
            - Creates MotionEvent in database
            - Updates cooldown timestamp
            - Generates base64 thumbnail

        Performance Target: <100ms (CRITICAL)
        """
        if not camera.motion_enabled:
            return None

        # Get or create motion detector for this camera
        detector = self._get_or_create_detector(camera_id, camera.motion_algorithm)

        # Check cooldown period
        if self._is_in_cooldown(camera_id, camera.motion_cooldown):
            logger.debug(f"Camera {camera_id} in cooldown period, skipping motion detection")
            return None

        # Run motion detection algorithm
        motion_detected, confidence, bounding_box = detector.detect_motion(
            frame,
            sensitivity=camera.motion_sensitivity
        )

        if not motion_detected:
            return None

        # Motion detected! Create event
        logger.info(
            f"Motion detected on camera {camera_id}: "
            f"confidence={confidence:.3f}, algorithm={camera.motion_algorithm}"
        )

        # Generate full frame thumbnail (base64 JPEG)
        frame_thumbnail = self._generate_thumbnail(frame)

        # Create motion event
        motion_event = MotionEvent(
            camera_id=camera_id,
            timestamp=datetime.now(timezone.utc),
            confidence=confidence,
            motion_intensity=None,  # Could be added later if needed
            algorithm_used=camera.motion_algorithm,
            bounding_box=json.dumps(bounding_box) if bounding_box else None,
            frame_thumbnail=frame_thumbnail,
        )

        # Save to database
        try:
            db.add(motion_event)
            db.commit()
            db.refresh(motion_event)
            logger.info(f"Motion event {motion_event.id} created for camera {camera_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save motion event: {e}", exc_info=True)
            return None

        # Update cooldown timestamp
        with self._state_lock:
            self._last_event_time[camera_id] = datetime.now(timezone.utc)

        return motion_event

    def _get_or_create_detector(self, camera_id: str, algorithm: str) -> MotionDetector:
        """
        Get existing detector or create new one for camera

        Thread-safe detector instance management

        Args:
            camera_id: UUID of camera
            algorithm: Motion detection algorithm

        Returns:
            MotionDetector instance for this camera
        """
        with self._state_lock:
            # Check if detector exists and algorithm matches
            if camera_id in self._detectors:
                detector = self._detectors[camera_id]
                if detector.algorithm == algorithm:
                    return detector
                else:
                    # Algorithm changed, create new detector
                    logger.info(f"Camera {camera_id} algorithm changed to {algorithm}, creating new detector")
                    del self._detectors[camera_id]

            # Create new detector
            detector = MotionDetector(algorithm=algorithm)
            self._detectors[camera_id] = detector
            logger.debug(f"Created new MotionDetector for camera {camera_id} with algorithm {algorithm}")

            return detector

    def _is_in_cooldown(self, camera_id: str, cooldown_seconds: int) -> bool:
        """
        Check if camera is in cooldown period

        Prevents creating multiple events for continuous motion

        Args:
            camera_id: UUID of camera
            cooldown_seconds: Minimum seconds between events

        Returns:
            True if in cooldown (skip event), False otherwise
        """
        with self._state_lock:
            if camera_id not in self._last_event_time:
                return False

            last_event = self._last_event_time[camera_id]
            elapsed = (datetime.now(timezone.utc) - last_event).total_seconds()

            return elapsed < cooldown_seconds

    def _generate_thumbnail(self, frame: np.ndarray, quality: int = 85) -> str:
        """
        Generate base64-encoded JPEG thumbnail from frame

        Args:
            frame: Full frame (NumPy array)
            quality: JPEG quality (0-100, default 85)

        Returns:
            Base64-encoded JPEG string (~50KB at 640x480, quality 85)

        Performance:
            - Encoding takes ~10-20ms for 640x480 frame
            - Result size: ~50KB for typical security camera frame
        """
        try:
            # Encode frame as JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            ret, buffer = cv2.imencode('.jpg', frame, encode_param)

            if not ret:
                logger.error("Failed to encode frame as JPEG")
                return ""

            # Convert to base64
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')

            logger.debug(f"Generated thumbnail: {len(jpg_as_text)} bytes (base64)")

            return jpg_as_text

        except Exception as e:
            logger.error(f"Failed to generate thumbnail: {e}", exc_info=True)
            return ""

    def reload_config(self, camera_id: str, algorithm: str):
        """
        Reload motion detection configuration for camera

        Triggers reset of background model when algorithm changes

        Args:
            camera_id: UUID of camera
            algorithm: New algorithm ('mog2', 'knn', 'frame_diff')

        Side Effects:
            - Destroys existing detector and creates new one
            - Resets background model (fresh start)
        """
        with self._state_lock:
            if camera_id in self._detectors:
                old_algorithm = self._detectors[camera_id].algorithm
                if old_algorithm != algorithm:
                    logger.info(f"Camera {camera_id}: Reloading detector (algorithm changed: {old_algorithm} -> {algorithm})")
                    del self._detectors[camera_id]
                    # New detector will be created on next process_frame call

    def cleanup_camera(self, camera_id: str):
        """
        Clean up resources for stopped camera

        Call this when camera is stopped to free memory

        Args:
            camera_id: UUID of camera

        Side Effects:
            - Removes detector instance
            - Clears cooldown timestamp
        """
        with self._state_lock:
            if camera_id in self._detectors:
                del self._detectors[camera_id]
                logger.debug(f"Removed detector for camera {camera_id}")

            if camera_id in self._last_event_time:
                del self._last_event_time[camera_id]
                logger.debug(f"Cleared cooldown timestamp for camera {camera_id}")

    def get_detector_stats(self) -> Dict[str, int]:
        """
        Get statistics about active detectors

        Returns:
            Dict with stats: {'active_detectors': int, 'cameras_in_cooldown': int}
        """
        with self._state_lock:
            return {
                'active_detectors': len(self._detectors),
                'cameras_in_cooldown': len(self._last_event_time),
            }


# Global singleton instance
motion_detection_service = MotionDetectionService()
