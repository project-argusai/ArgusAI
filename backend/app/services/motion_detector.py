"""
Motion detection algorithm implementation using OpenCV

Supports three algorithms:
- MOG2: Gaussian Mixture Model (fast, recommended default)
- KNN: K-Nearest Neighbors (better accuracy, slightly slower)
- Frame Differencing: Simple frame-to-frame difference (fastest, less accurate)
"""
import cv2
import numpy as np
import logging
from typing import Tuple, List, Optional

logger = logging.getLogger(__name__)


class MotionDetector:
    """
    Detects motion in video frames using OpenCV background subtraction algorithms

    Features:
    - Multiple algorithm support (MOG2, KNN, FrameDiff)
    - Configurable sensitivity thresholds
    - Bounding box extraction for detected motion
    - Confidence score calculation

    Thread Safety:
    - Each camera should have its own MotionDetector instance
    - NOT safe to share instances between threads
    """

    # Sensitivity thresholds (percentage of frame pixels that must change)
    SENSITIVITY_THRESHOLDS = {
        'low': 0.05,      # 5% of pixels (fewer false positives)
        'medium': 0.02,   # 2% of pixels (balanced, default)
        'high': 0.005,    # 0.5% of pixels (sensitive, more false positives)
    }

    def __init__(self, algorithm: str = 'mog2'):
        """
        Initialize motion detector with specified algorithm

        Args:
            algorithm: 'mog2', 'knn', or 'frame_diff'

        Raises:
            ValueError: If algorithm is invalid
        """
        self.algorithm = algorithm.lower()
        self.background_subtractor: Optional[cv2.BackgroundSubtractor] = None
        self.previous_frame: Optional[np.ndarray] = None

        # Initialize background subtractor based on algorithm
        if self.algorithm == 'mog2':
            # MOG2: Adaptive Gaussian Mixture Model
            # detectShadows=False for better performance (shadows not needed for simple motion)
            self.background_subtractor = cv2.createBackgroundSubtractorMOG2(
                history=500,
                varThreshold=16,
                detectShadows=False
            )
        elif self.algorithm == 'knn':
            # KNN: K-Nearest Neighbors
            # dist2Threshold controls sensitivity to changes
            self.background_subtractor = cv2.createBackgroundSubtractorKNN(
                history=500,
                dist2Threshold=400.0,
                detectShadows=False
            )
        elif self.algorithm == 'frame_diff':
            # Frame differencing: No background model needed
            self.background_subtractor = None
            self.previous_frame = None
        else:
            raise ValueError(f"Invalid algorithm: {algorithm}. Must be 'mog2', 'knn', or 'frame_diff'")

        logger.debug(f"MotionDetector initialized with algorithm: {self.algorithm}")

    def detect_motion(
        self,
        frame: np.ndarray,
        sensitivity: str = 'medium'
    ) -> Tuple[bool, float, Optional[Tuple[int, int, int, int]]]:
        """
        Detect motion in a single frame

        Args:
            frame: Current frame (NumPy array from cv2.VideoCapture)
            sensitivity: 'low', 'medium', or 'high'

        Returns:
            Tuple of (motion_detected, confidence, bounding_box)
            - motion_detected: True if motion exceeds sensitivity threshold
            - confidence: Motion confidence score (0.0-1.0)
            - bounding_box: (x, y, width, height) or None if no motion

        Performance:
            - MOG2: ~30-50ms per frame at 640x480
            - KNN: ~40-60ms per frame at 640x480
            - Frame Diff: ~20-30ms per frame at 640x480
        """
        if frame is None or frame.size == 0:
            logger.warning("Received empty frame for motion detection")
            return False, 0.0, None

        # Get sensitivity threshold
        threshold = self.SENSITIVITY_THRESHOLDS.get(sensitivity, self.SENSITIVITY_THRESHOLDS['medium'])

        # Apply motion detection algorithm
        if self.algorithm in ['mog2', 'knn']:
            foreground_mask = self.background_subtractor.apply(frame)
        elif self.algorithm == 'frame_diff':
            foreground_mask = self._frame_differencing(frame)
        else:
            return False, 0.0, None

        # Calculate motion intensity (percentage of changed pixels)
        total_pixels = foreground_mask.shape[0] * foreground_mask.shape[1]
        motion_pixels = cv2.countNonZero(foreground_mask)
        motion_intensity = motion_pixels / total_pixels

        # Check if motion exceeds threshold
        motion_detected = motion_intensity >= threshold

        # Calculate confidence score (0.0-1.0)
        # Scale based on threshold: motion at threshold = 0.5 confidence
        # motion at 2x threshold = 1.0 confidence
        confidence = min(1.0, motion_intensity / (threshold * 2))

        # Extract bounding box if motion detected
        bounding_box = None
        if motion_detected:
            bounding_box = self._extract_bounding_box(foreground_mask)

        logger.debug(
            f"Motion detection: detected={motion_detected}, "
            f"confidence={confidence:.3f}, intensity={motion_intensity:.5f}, "
            f"threshold={threshold:.5f}, bbox={bounding_box}"
        )

        return motion_detected, confidence, bounding_box

    def _frame_differencing(self, frame: np.ndarray) -> np.ndarray:
        """
        Simple frame differencing algorithm

        Compares current frame to previous frame and returns difference mask

        Args:
            frame: Current frame

        Returns:
            Binary foreground mask (white pixels = motion)
        """
        # Convert to grayscale for faster processing
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # First frame: Initialize
        if self.previous_frame is None:
            self.previous_frame = gray
            return np.zeros_like(gray)

        # Compute absolute difference between frames
        frame_diff = cv2.absdiff(self.previous_frame, gray)

        # Apply threshold to get binary mask
        # Pixels with difference > 25 (out of 255) are considered motion
        _, thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)

        # Morphological operations to reduce noise
        # Dilate to connect nearby regions, erode to remove small noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # Update previous frame
        self.previous_frame = gray

        return thresh

    def _extract_bounding_box(
        self,
        foreground_mask: np.ndarray
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Extract bounding box from foreground mask

        Finds the largest contour in the mask and returns its bounding box

        Args:
            foreground_mask: Binary mask (white pixels = motion)

        Returns:
            Bounding box as (x, y, width, height) or None if no contours found

        Note:
            Filters out very small contours (< 100 pixels) to reduce noise
        """
        # Find contours in the mask
        contours, _ = cv2.findContours(
            foreground_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return None

        # Filter out small contours (noise)
        min_contour_area = 100  # pixels
        significant_contours = [c for c in contours if cv2.contourArea(c) > min_contour_area]

        if not significant_contours:
            return None

        # Find largest contour
        largest_contour = max(significant_contours, key=cv2.contourArea)

        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(largest_contour)

        return (x, y, w, h)

    def reset(self):
        """
        Reset background model

        Useful when:
        - Camera sensitivity changes
        - Algorithm changes
        - Camera view changes significantly
        - Periodic reset to adapt to lighting changes
        """
        if self.algorithm == 'mog2':
            self.background_subtractor = cv2.createBackgroundSubtractorMOG2(
                history=500,
                varThreshold=16,
                detectShadows=False
            )
        elif self.algorithm == 'knn':
            self.background_subtractor = cv2.createBackgroundSubtractorKNN(
                history=500,
                dist2Threshold=400.0,
                detectShadows=False
            )
        elif self.algorithm == 'frame_diff':
            self.previous_frame = None

        logger.debug(f"MotionDetector reset for algorithm: {self.algorithm}")
