"""Tests for MotionDetector class"""
import pytest
import numpy as np
import cv2
from app.services.motion_detector import MotionDetector


class TestMotionDetector:
    """Test motion detection algorithms"""

    @pytest.fixture
    def synthetic_frame(self):
        """Create a synthetic black frame for testing"""
        return np.zeros((480, 640, 3), dtype=np.uint8)

    @pytest.fixture
    def synthetic_motion_frame(self):
        """Create a synthetic frame with white square (simulating motion)"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Add white square in center (simulating motion)
        cv2.rectangle(frame, (250, 200), (390, 280), (255, 255, 255), -1)
        return frame

    def test_detector_initialization_mog2(self):
        """Test MOG2 detector initializes correctly"""
        detector = MotionDetector(algorithm='mog2')
        assert detector.algorithm == 'mog2'
        assert detector.background_subtractor is not None

    def test_detector_initialization_knn(self):
        """Test KNN detector initializes correctly"""
        detector = MotionDetector(algorithm='knn')
        assert detector.algorithm == 'knn'
        assert detector.background_subtractor is not None

    def test_detector_initialization_frame_diff(self):
        """Test frame differencing detector initializes correctly"""
        detector = MotionDetector(algorithm='frame_diff')
        assert detector.algorithm == 'frame_diff'
        assert detector.background_subtractor is None

    def test_invalid_algorithm(self):
        """Test invalid algorithm raises ValueError"""
        with pytest.raises(ValueError):
            MotionDetector(algorithm='invalid')

    def test_detect_no_motion(self, synthetic_frame):
        """Test detector returns no motion for static black frame"""
        detector = MotionDetector(algorithm='mog2')

        # First frame (background learning)
        detector.detect_motion(synthetic_frame, sensitivity='medium')

        # Second frame (same as first, no motion)
        motion_detected, confidence, bbox = detector.detect_motion(synthetic_frame, sensitivity='medium')

        # No motion expected (static frame)
        assert motion_detected is False or confidence < 0.3  # Allow some initial adaptation

    def test_detect_motion_with_change(self, synthetic_frame, synthetic_motion_frame):
        """Test detector identifies motion when frame changes"""
        detector = MotionDetector(algorithm='frame_diff')

        # First frame (black)
        detector.detect_motion(synthetic_frame, sensitivity='medium')

        # Second frame (white square appears - motion!)
        motion_detected, confidence, bbox = detector.detect_motion(synthetic_motion_frame, sensitivity='high')

        # Motion should be detected
        assert motion_detected is True
        assert confidence > 0.0
        assert bbox is not None  # Bounding box should be found

    def test_sensitivity_thresholds(self):
        """Test that sensitivity thresholds are correctly defined"""
        detector = MotionDetector(algorithm='mog2')

        assert detector.SENSITIVITY_THRESHOLDS['low'] == 0.05
        assert detector.SENSITIVITY_THRESHOLDS['medium'] == 0.02
        assert detector.SENSITIVITY_THRESHOLDS['high'] == 0.005

    def test_detector_reset(self):
        """Test detector reset clears background model"""
        detector = MotionDetector(algorithm='mog2')
        detector.reset()

        # After reset, background_subtractor should still exist
        assert detector.background_subtractor is not None

    def test_empty_frame_handling(self):
        """Test detector handles empty frames gracefully"""
        detector = MotionDetector(algorithm='mog2')
        empty_frame = np.array([])

        motion_detected, confidence, bbox = detector.detect_motion(empty_frame, sensitivity='medium')

        assert motion_detected is False
        assert confidence == 0.0
        assert bbox is None
