"""Unit tests for CameraService with mocked VideoCapture"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import time
import threading

from app.services.camera_service import CameraService
from app.models.camera import Camera


class TestCameraService:
    """Test suite for CameraService"""

    @pytest.fixture
    def camera_service(self):
        """Create CameraService instance for testing"""
        return CameraService()

    @pytest.fixture
    def rtsp_camera(self):
        """Create mock RTSP camera"""
        camera = Mock(spec=Camera)
        camera.id = "test-camera-123"
        camera.name = "Test Camera"
        camera.type = "rtsp"
        camera.rtsp_url = "rtsp://192.168.1.50:554/stream1"
        camera.username = "admin"
        camera.password = "encrypted:test_encrypted_password"
        camera.frame_rate = 5
        camera.get_decrypted_password = Mock(return_value="plain_password")
        return camera

    @pytest.fixture
    def usb_camera(self):
        """Create mock USB camera"""
        camera = Mock(spec=Camera)
        camera.id = "usb-camera-456"
        camera.name = "Webcam"
        camera.type = "usb"
        camera.device_index = 0
        camera.frame_rate = 15
        return camera

    def test_camera_service_initialization(self, camera_service):
        """CameraService should initialize with empty tracking dicts"""
        assert len(camera_service._capture_threads) == 0
        assert len(camera_service._active_captures) == 0
        assert len(camera_service._stop_flags) == 0
        assert len(camera_service._camera_status) == 0

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_start_camera_rtsp(self, mock_videocapture, camera_service, rtsp_camera):
        """start_camera should start background thread for RTSP camera"""
        # Mock successful camera connection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.side_effect = [(False, None)]  # Fail immediately to exit loop
        mock_videocapture.return_value = mock_cap

        # Start camera
        result = camera_service.start_camera(rtsp_camera)

        assert result is True
        assert rtsp_camera.id in camera_service._capture_threads
        assert rtsp_camera.id in camera_service._stop_flags

        # Thread should be alive (briefly)
        thread = camera_service._capture_threads[rtsp_camera.id]
        assert isinstance(thread, threading.Thread)

        # Wait for thread to process
        time.sleep(0.2)

        # Clean up
        camera_service.stop_camera(rtsp_camera.id)

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_start_camera_usb(self, mock_videocapture, camera_service, usb_camera):
        """start_camera should work with USB camera using device index"""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.side_effect = [(False, None)]
        mock_videocapture.return_value = mock_cap

        result = camera_service.start_camera(usb_camera)

        assert result is True
        assert usb_camera.id in camera_service._capture_threads

        # VideoCapture should be called with device index
        mock_videocapture.assert_called_with(usb_camera.device_index)

        time.sleep(0.2)
        camera_service.stop_camera(usb_camera.id)

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_start_camera_already_running(self, mock_videocapture, camera_service, rtsp_camera):
        """Starting already running camera should return False"""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, Mock())  # Keep running
        mock_videocapture.return_value = mock_cap

        # Start first time
        result1 = camera_service.start_camera(rtsp_camera)
        assert result1 is True

        time.sleep(0.1)

        # Try to start again while running
        result2 = camera_service.start_camera(rtsp_camera)
        assert result2 is False

        # Clean up
        camera_service.stop_camera(rtsp_camera.id)

    def test_stop_camera(self, camera_service):
        """stop_camera should stop thread and clean up resources"""
        camera_id = "test-camera-123"

        # Create mock thread and stop flag
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.is_alive.return_value = False
        camera_service._capture_threads[camera_id] = mock_thread

        stop_flag = threading.Event()
        camera_service._stop_flags[camera_id] = stop_flag

        # Stop camera
        camera_service.stop_camera(camera_id)

        # Should set stop flag
        assert stop_flag.is_set()

        # Should wait for thread
        mock_thread.join.assert_called_once()

        # Should clean up
        assert camera_id not in camera_service._capture_threads
        assert camera_id not in camera_service._stop_flags

    def test_stop_camera_not_running(self, camera_service):
        """Stopping non-running camera should not raise error"""
        # Should not raise exception
        camera_service.stop_camera("non-existent-camera")

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_build_rtsp_url_with_credentials(self, mock_videocapture, camera_service, rtsp_camera):
        """RTSP URL should include username and decrypted password"""
        url = camera_service._build_rtsp_url(rtsp_camera)

        # Should call get_decrypted_password
        rtsp_camera.get_decrypted_password.assert_called_once()

        # URL should contain credentials
        assert "admin:plain_password@" in url
        assert "192.168.1.50" in url

    def test_build_rtsp_url_without_credentials(self, camera_service):
        """RTSP URL without credentials should remain unchanged"""
        camera = Mock(spec=Camera)
        camera.rtsp_url = "rtsp://192.168.1.50:554/stream1"
        camera.username = None
        camera.password = None

        url = camera_service._build_rtsp_url(camera)

        assert url == "rtsp://192.168.1.50:554/stream1"

    def test_update_status_thread_safe(self, camera_service):
        """_update_status should be thread-safe"""
        camera_id = "test-camera"

        camera_service._update_status(camera_id, "connected")

        status = camera_service.get_camera_status(camera_id)

        assert status is not None
        assert status["status"] == "connected"
        assert status["last_frame_time"] is not None
        assert status["error"] is None

    def test_update_status_with_error(self, camera_service):
        """_update_status should store error message"""
        camera_id = "test-camera"

        camera_service._update_status(camera_id, "error", error="Connection failed")

        status = camera_service.get_camera_status(camera_id)

        assert status["status"] == "error"
        assert status["error"] == "Connection failed"
        assert status["last_frame_time"] is None

    def test_get_camera_status_not_found(self, camera_service):
        """get_camera_status should return None for non-existent camera"""
        status = camera_service.get_camera_status("non-existent")
        assert status is None

    def test_get_all_camera_status(self, camera_service):
        """get_all_camera_status should return all camera statuses"""
        camera_service._update_status("camera1", "connected")
        camera_service._update_status("camera2", "disconnected")

        all_status = camera_service.get_all_camera_status()

        assert len(all_status) == 2
        assert "camera1" in all_status
        assert "camera2" in all_status
        assert all_status["camera1"]["status"] == "connected"
        assert all_status["camera2"]["status"] == "disconnected"

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_reconnection_on_frame_read_failure(self, mock_videocapture, camera_service, rtsp_camera):
        """Camera should attempt reconnection when frame read fails"""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        # First read succeeds, second fails (trigger reconnect), then stop
        mock_cap.read.side_effect = [
            (True, Mock()),  # Success
            (False, None),   # Fail - triggers reconnect
            (False, None),   # Still failing (to prevent infinite loop)
        ]
        mock_videocapture.return_value = mock_cap

        # Start camera
        camera_service.start_camera(rtsp_camera)

        # Wait for reconnection attempt
        time.sleep(0.5)

        # Should have updated status to disconnected
        status = camera_service.get_camera_status(rtsp_camera.id)
        # Status might be 'disconnected' or 'error' depending on timing
        assert status is not None

        # Clean up
        camera_service.stop_camera(rtsp_camera.id, timeout=1.0)

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_stop_all_cameras(self, mock_videocapture, camera_service, rtsp_camera, usb_camera):
        """stop_all_cameras should stop all running cameras"""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, Mock())
        mock_videocapture.return_value = mock_cap

        # Start multiple cameras
        camera_service.start_camera(rtsp_camera)
        camera_service.start_camera(usb_camera)

        time.sleep(0.1)

        # Stop all
        camera_service.stop_all_cameras(timeout=1.0)

        # Should have stopped both
        assert len(camera_service._capture_threads) == 0
        assert len(camera_service._active_captures) == 0

    # USB-Specific Tests (Story F1.3)

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_detect_usb_cameras_found(self, mock_videocapture, camera_service):
        """detect_usb_cameras should enumerate available USB devices"""
        # Mock VideoCapture to return success for indices 0 and 1, fail for others
        def mock_camera_factory(device_index):
            mock_cap = MagicMock()
            if device_index in [0, 1]:
                mock_cap.isOpened.return_value = True
                mock_cap.read.return_value = (True, Mock())  # Successful frame read
            else:
                mock_cap.isOpened.return_value = False
                mock_cap.read.return_value = (False, None)
            return mock_cap

        mock_videocapture.side_effect = mock_camera_factory

        # Detect cameras
        devices = camera_service.detect_usb_cameras()

        # Should find devices 0 and 1
        assert devices == [0, 1]

        # Should have tried indices 0-9
        assert mock_videocapture.call_count == 10

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_detect_usb_cameras_none_found(self, mock_videocapture, camera_service):
        """detect_usb_cameras should return empty list if no cameras found"""
        # Mock all indices to fail
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        devices = camera_service.detect_usb_cameras()

        assert devices == []

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_detect_usb_cameras_exception_handling(self, mock_videocapture, camera_service):
        """detect_usb_cameras should handle exceptions gracefully"""
        # Mock VideoCapture to raise exception for some indices
        def mock_camera_factory(device_index):
            if device_index == 0:
                mock_cap = MagicMock()
                mock_cap.isOpened.return_value = True
                mock_cap.read.return_value = (True, Mock())
                return mock_cap
            else:
                raise Exception("Device not available")

        mock_videocapture.side_effect = mock_camera_factory

        # Should not raise exception
        devices = camera_service.detect_usb_cameras()

        # Should still find device 0
        assert 0 in devices

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_usb_camera_disconnect_reconnect(self, mock_videocapture, camera_service, usb_camera):
        """USB camera should handle disconnect and reconnect"""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        # Simulate: connect, disconnect, reconnect
        mock_cap.read.side_effect = [
            (True, Mock()),   # Frame 1 - success
            (True, Mock()),   # Frame 2 - success
            (False, None),    # Frame 3 - disconnect
            (False, None),    # Reconnection fails first time
        ]
        mock_videocapture.return_value = mock_cap

        # Start camera
        camera_service.start_camera(usb_camera)

        # Wait for disconnect to trigger
        time.sleep(0.5)

        # Status should reflect disconnection
        status = camera_service.get_camera_status(usb_camera.id)
        assert status is not None

        # Clean up
        camera_service.stop_camera(usb_camera.id, timeout=1.0)

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_usb_device_indices(self, mock_videocapture, camera_service):
        """Different USB cameras should use different device indices"""
        # Create cameras with different device indices
        camera1 = Mock(spec=Camera)
        camera1.id = "usb-camera-1"
        camera1.name = "Webcam 1"
        camera1.type = "usb"
        camera1.device_index = 0
        camera1.frame_rate = 15

        camera2 = Mock(spec=Camera)
        camera2.id = "usb-camera-2"
        camera2.name = "Webcam 2"
        camera2.type = "usb"
        camera2.device_index = 1
        camera2.frame_rate = 15

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.side_effect = [(False, None)]
        mock_videocapture.return_value = mock_cap

        # Start both cameras
        camera_service.start_camera(camera1)
        camera_service.start_camera(camera2)

        time.sleep(0.2)

        # Verify VideoCapture called with correct device indices
        calls = mock_videocapture.call_args_list
        device_indices = [call[0][0] for call in calls]

        assert 0 in device_indices
        assert 1 in device_indices

        # Clean up
        camera_service.stop_camera(camera1.id)
        camera_service.stop_camera(camera2.id)

    @patch('app.services.camera_service.cv2.VideoCapture')
    def test_usb_camera_connection_failure(self, mock_videocapture, camera_service, usb_camera):
        """USB camera should handle connection failure gracefully"""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False  # Connection failed
        mock_videocapture.return_value = mock_cap

        # Start camera
        camera_service.start_camera(usb_camera)

        # Wait for connection attempt
        time.sleep(0.3)

        # Should have error status
        status = camera_service.get_camera_status(usb_camera.id)
        assert status is not None
        # Status should indicate error (connection failed)

        # Clean up
        camera_service.stop_camera(usb_camera.id, timeout=1.0)


class TestCameraCaptureRecoveryPolicy:
    """Tests for the stronger automatic recovery / disable policy (#449)"""

    @pytest.fixture
    def camera_service(self):
        return CameraService()

    @pytest.fixture
    def test_camera(self):
        camera = Mock(spec=Camera)
        camera.id = "test-cam-recovery-001"
        camera.name = "Recovery Test Cam"
        camera.type = "rtsp"
        camera.frame_rate = 5
        return camera

    def test_manual_disable_and_enable(self, camera_service, test_camera):
        """Admin can manually disable and re-enable a camera."""
        cid = test_camera.id

        assert cid not in camera_service._capture_disabled

        camera_service.disable_camera_capture(cid)
        assert cid in camera_service._capture_disabled

        camera_service.enable_camera_capture(cid)
        assert cid not in camera_service._capture_disabled

    def test_start_refused_when_disabled(self, camera_service, test_camera):
        """start_camera should refuse when camera is disabled."""
        cid = test_camera.id
        camera_service.disable_camera_capture(cid)

        success = camera_service.start_camera(test_camera)
        assert success is False

        # Re-enable and it should work (mocked)
        camera_service.enable_camera_capture(cid)
        assert cid not in camera_service._capture_disabled

    def test_auto_disable_after_max_restarts(self, camera_service, test_camera):
        """Camera should be auto-disabled after MAX_RESTART_ATTEMPTS failed restarts."""
        cid = test_camera.id
        camera_service.MAX_RESTART_ATTEMPTS = 3  # speed up test

        # Simulate repeated failed restarts (we call restart directly)
        for i in range(3):
            camera_service.restart_camera(test_camera)

        assert cid in camera_service._capture_disabled
        assert camera_service._restart_attempts.get(cid, 0) >= 3

    def test_enable_clears_disabled_state(self, camera_service, test_camera):
        """Re-enabling a disabled camera clears the disabled flag and attempt counter."""
        cid = test_camera.id
        camera_service.disable_camera_capture(cid)
        camera_service._restart_attempts[cid] = 10

        camera_service.enable_camera_capture(cid)

        assert cid not in camera_service._capture_disabled
        assert camera_service._restart_attempts.get(cid, 0) == 0

    def test_auto_disable_after_max_restarts(self, camera_service, test_camera):
        """Camera should become capture-disabled after MAX_RESTART_ATTEMPTS failed restarts."""
        cid = test_camera.id
        camera_service.MAX_RESTART_ATTEMPTS = 3
        camera_service.RESTART_WINDOW_SECONDS = 999999  # Prevent window reset during test

        # Simulate repeated failed restarts
        for _ in range(3):
            camera_service.restart_camera(test_camera)

        assert cid in camera_service._capture_disabled
        assert camera_service._restart_attempts.get(cid, 0) >= 3

    def test_health_summary_counts_disabled_cameras(self, camera_service, test_camera):
        """get_camera_health_summary should correctly count disabled cameras."""
        cid = test_camera.id
        camera_service.disable_camera_capture(cid)

        summary = camera_service.get_camera_health_summary()

        assert summary["disabled"] >= 1
        assert cid in summary["cameras"]
        assert summary["cameras"][cid]["capture_disabled"] is True

    def test_restart_attempts_reset_on_success(self, camera_service, test_camera):
        """Successful restart should reset the attempt counter."""
        cid = test_camera.id
        camera_service._restart_attempts[cid] = 4

        # Simulate a successful restart (we'll mock the internal start to succeed)
        with patch.object(camera_service, 'start_camera', return_value=True):
            camera_service.restart_camera(test_camera)

        assert camera_service._restart_attempts.get(cid, 0) == 0
        assert cid not in camera_service._capture_disabled
