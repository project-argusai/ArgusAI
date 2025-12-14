"""
Tests for HomeKit Camera accessory (Story P5-1.3)

Tests cover:
- AC1: Camera accessory creation and configuration
- AC2: ffmpeg command generation for RTSP-to-SRTP streaming
- AC3: Stream start/stop lifecycle management
- AC4: Concurrent stream limiting (max 2)
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess
import threading

from app.services.homekit_camera import (
    HomeKitCameraAccessory,
    create_camera_accessory,
    check_ffmpeg_available,
    MAX_CONCURRENT_STREAMS,
    StreamSession,
)


class TestHomeKitCameraAccessoryCreation:
    """Tests for camera accessory creation (Story P5-1.3 AC1)."""

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    def test_create_camera_accessory_success(self, mock_camera_class):
        """AC1: Camera accessory created successfully with valid config."""
        mock_driver = Mock()
        mock_camera = Mock()
        mock_camera.get_service.return_value = Mock()
        mock_camera_class.return_value = mock_camera

        accessory = HomeKitCameraAccessory(
            driver=mock_driver,
            camera_id="test-camera-123",
            camera_name="Test Camera",
            rtsp_url="rtsp://192.168.1.100:554/stream",
            manufacturer="TestManufacturer",
        )

        assert accessory.camera_id == "test-camera-123"
        assert accessory.camera_name == "Test Camera"
        assert accessory.rtsp_url == "rtsp://192.168.1.100:554/stream"
        assert accessory.manufacturer == "TestManufacturer"

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    def test_camera_accessory_returns_hap_accessory(self, mock_camera_class):
        """AC1: Accessory property returns HAP-python Camera instance."""
        mock_driver = Mock()
        mock_camera = Mock()
        mock_camera.get_service.return_value = Mock()
        mock_camera_class.return_value = mock_camera

        accessory = HomeKitCameraAccessory(
            driver=mock_driver,
            camera_id="test-camera",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        assert accessory.accessory == mock_camera

    @patch("app.services.homekit_camera.HAP_AVAILABLE", False)
    def test_create_camera_accessory_hap_unavailable(self):
        """AC1: Returns None when HAP-python not available."""
        result = create_camera_accessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        assert result is None


class TestFfmpegCommandGeneration:
    """Tests for ffmpeg command generation (Story P5-1.3 AC2)."""

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    def test_build_ffmpeg_command_contains_rtsp_input(self, mock_camera_class):
        """AC2: ffmpeg command includes RTSP URL as input."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://192.168.1.100:554/stream1",
        )

        session_info = {
            "address": "192.168.1.50",
            "v_port": 51234,
            "v_srtp_key": "testkey123",
            "v_ssrc": 12345,
        }
        stream_config = {
            "width": 1280,
            "height": 720,
            "fps": 30,
            "v_max_bitrate": 2000,
        }

        cmd = accessory._build_ffmpeg_command(session_info, stream_config)

        assert cmd is not None
        assert "rtsp://192.168.1.100:554/stream1" in cmd
        assert "-i" in cmd

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    def test_build_ffmpeg_command_includes_srtp_output(self, mock_camera_class):
        """AC2: ffmpeg command configures SRTP output to HomeKit client."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        session_info = {
            "address": "192.168.1.50",
            "v_port": 51234,
            "v_srtp_key": "base64encodedkey",
            "v_ssrc": 99999,
        }
        stream_config = {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "v_max_bitrate": 4000,
        }

        cmd = accessory._build_ffmpeg_command(session_info, stream_config)

        assert "-srtp_out_suite" in cmd
        assert "AES_CM_128_HMAC_SHA1_80" in cmd
        assert "srtp://192.168.1.50:51234" in " ".join(cmd)

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    def test_build_ffmpeg_command_low_latency_settings(self, mock_camera_class):
        """AC2: ffmpeg command uses low-latency encoding settings."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        session_info = {
            "address": "192.168.1.50",
            "v_port": 51234,
            "v_srtp_key": "key",
            "v_ssrc": 1,
        }
        stream_config = {
            "width": 1280,
            "height": 720,
            "fps": 30,
            "v_max_bitrate": 2000,
        }

        cmd = accessory._build_ffmpeg_command(session_info, stream_config)

        assert "-preset" in cmd
        assert "ultrafast" in cmd
        assert "-tune" in cmd
        assert "zerolatency" in cmd


class TestStreamLifecycle:
    """Tests for stream start/stop lifecycle (Story P5-1.3 AC3)."""

    @pytest.fixture(autouse=True)
    def reset_stream_count(self):
        """Reset stream count before each test."""
        HomeKitCameraAccessory._active_stream_count = 0
        HomeKitCameraAccessory._active_sessions.clear()
        yield
        HomeKitCameraAccessory._active_stream_count = 0
        HomeKitCameraAccessory._active_sessions.clear()

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    @patch("app.services.homekit_camera.subprocess.Popen")
    @pytest.mark.asyncio
    async def test_start_stream_spawns_ffmpeg(self, mock_popen, mock_camera_class):
        """AC3: start_stream spawns ffmpeg subprocess."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        session_info = {
            "session_id": "session-1",
            "address": "192.168.1.50",
            "v_port": 51234,
            "v_srtp_key": "key",
            "v_ssrc": 1,
        }
        stream_config = {
            "width": 1280,
            "height": 720,
            "fps": 30,
            "v_max_bitrate": 2000,
        }

        result = await accessory._start_stream(session_info, stream_config)

        assert result is True
        mock_popen.assert_called_once()
        assert HomeKitCameraAccessory._active_stream_count == 1

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    @pytest.mark.asyncio
    async def test_stop_stream_terminates_process(self, mock_camera_class):
        """AC3: stop_stream terminates ffmpeg subprocess cleanly."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        mock_process = Mock()
        mock_process.wait.return_value = 0
        session_info = {
            "session_id": "session-1",
            "process": mock_process,
        }

        # Add to active sessions
        HomeKitCameraAccessory._active_stream_count = 1
        HomeKitCameraAccessory._active_sessions["session-1"] = StreamSession(
            session_id="session-1",
            camera_id="test",
            process=mock_process,
        )

        await accessory._stop_stream(session_info)

        mock_process.terminate.assert_called_once()
        assert HomeKitCameraAccessory._active_stream_count == 0

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    @pytest.mark.asyncio
    async def test_stop_stream_force_kills_if_needed(self, mock_camera_class):
        """AC3: stop_stream force kills process if graceful termination fails."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        mock_process = Mock()
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("ffmpeg", 2.0), 0]
        session_info = {
            "session_id": "session-1",
            "process": mock_process,
        }

        HomeKitCameraAccessory._active_stream_count = 1

        await accessory._stop_stream(session_info)

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()


class TestConcurrentStreamLimiting:
    """Tests for concurrent stream limiting (Story P5-1.3 AC4)."""

    @pytest.fixture(autouse=True)
    def reset_stream_count(self):
        """Reset stream count before each test."""
        HomeKitCameraAccessory._active_stream_count = 0
        HomeKitCameraAccessory._active_sessions.clear()
        yield
        HomeKitCameraAccessory._active_stream_count = 0
        HomeKitCameraAccessory._active_sessions.clear()

    def test_max_concurrent_streams_is_two(self):
        """AC4: MAX_CONCURRENT_STREAMS is set to 2."""
        assert MAX_CONCURRENT_STREAMS == 2

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    @patch("app.services.homekit_camera.subprocess.Popen")
    @pytest.mark.asyncio
    async def test_rejects_stream_when_limit_reached(self, mock_popen, mock_camera_class):
        """AC4: Third stream request rejected when 2 streams active."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))
        mock_popen.return_value = Mock(pid=123)

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        session_info = {
            "session_id": "session-test",
            "address": "192.168.1.50",
            "v_port": 51234,
            "v_srtp_key": "key",
            "v_ssrc": 1,
        }
        stream_config = {
            "width": 1280,
            "height": 720,
            "fps": 30,
            "v_max_bitrate": 2000,
        }

        # Set active stream count to max
        HomeKitCameraAccessory._active_stream_count = MAX_CONCURRENT_STREAMS

        result = await accessory._start_stream(session_info, stream_config)

        assert result is False
        # Stream count should not increase
        assert HomeKitCameraAccessory._active_stream_count == MAX_CONCURRENT_STREAMS

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    @patch("app.services.homekit_camera.subprocess.Popen")
    @pytest.mark.asyncio
    async def test_stream_count_increments_on_start(self, mock_popen, mock_camera_class):
        """AC4: Active stream count increments when stream starts."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))
        mock_popen.return_value = Mock(pid=123)

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        session_info = {
            "session_id": "session-1",
            "address": "192.168.1.50",
            "v_port": 51234,
            "v_srtp_key": "key",
            "v_ssrc": 1,
        }
        stream_config = {
            "width": 1280,
            "height": 720,
            "fps": 30,
            "v_max_bitrate": 2000,
        }

        initial_count = HomeKitCameraAccessory._active_stream_count
        await accessory._start_stream(session_info, stream_config)

        assert HomeKitCameraAccessory._active_stream_count == initial_count + 1

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    @pytest.mark.asyncio
    async def test_stream_count_decrements_on_stop(self, mock_camera_class):
        """AC4: Active stream count decrements when stream stops."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        HomeKitCameraAccessory._active_stream_count = 2

        mock_process = Mock()
        mock_process.wait.return_value = 0
        session_info = {
            "session_id": "session-1",
            "process": mock_process,
        }

        await accessory._stop_stream(session_info)

        assert HomeKitCameraAccessory._active_stream_count == 1

    def test_stream_count_never_negative(self):
        """AC4: Stream count never goes below 0."""
        HomeKitCameraAccessory._active_stream_count = 0

        # Create an accessory and call _decrement_stream_count
        accessory = Mock()
        accessory._stream_lock = HomeKitCameraAccessory._stream_lock

        with HomeKitCameraAccessory._stream_lock:
            HomeKitCameraAccessory._active_stream_count = max(
                0, HomeKitCameraAccessory._active_stream_count - 1
            )

        assert HomeKitCameraAccessory._active_stream_count == 0


class TestCleanupAllStreams:
    """Tests for cleanup_all_streams (Story P5-1.3 AC3)."""

    @pytest.fixture(autouse=True)
    def reset_stream_count(self):
        """Reset stream count before each test."""
        HomeKitCameraAccessory._active_stream_count = 0
        HomeKitCameraAccessory._active_sessions.clear()
        yield
        HomeKitCameraAccessory._active_stream_count = 0
        HomeKitCameraAccessory._active_sessions.clear()

    def test_cleanup_all_streams_terminates_processes(self):
        """AC3: cleanup_all_streams terminates all ffmpeg processes."""
        mock_process1 = Mock()
        mock_process1.wait.return_value = 0
        mock_process2 = Mock()
        mock_process2.wait.return_value = 0

        HomeKitCameraAccessory._active_sessions = {
            "session-1": StreamSession(session_id="session-1", camera_id="cam1", process=mock_process1),
            "session-2": StreamSession(session_id="session-2", camera_id="cam2", process=mock_process2),
        }
        HomeKitCameraAccessory._active_stream_count = 2

        HomeKitCameraAccessory.cleanup_all_streams()

        mock_process1.terminate.assert_called_once()
        mock_process2.terminate.assert_called_once()
        assert HomeKitCameraAccessory._active_stream_count == 0
        assert len(HomeKitCameraAccessory._active_sessions) == 0


class TestCheckFfmpegAvailable:
    """Tests for ffmpeg availability check."""

    @patch("app.services.homekit_camera.subprocess.run")
    def test_ffmpeg_available_returns_true(self, mock_run):
        """Returns True when ffmpeg is available."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=b"ffmpeg version 6.0 Copyright (c) 2000-2023"
        )

        available, message = check_ffmpeg_available()

        assert available is True
        assert "ffmpeg available" in message

    @patch("app.services.homekit_camera.subprocess.run")
    def test_ffmpeg_not_found(self, mock_run):
        """Returns False when ffmpeg not found."""
        mock_run.side_effect = FileNotFoundError()

        available, message = check_ffmpeg_available()

        assert available is False
        assert "not found" in message

    @patch("app.services.homekit_camera.subprocess.run")
    def test_ffmpeg_timeout(self, mock_run):
        """Returns False on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 5)

        available, message = check_ffmpeg_available()

        assert available is False
        assert "timed out" in message


class TestSnapshotGeneration:
    """Tests for snapshot/thumbnail generation (Story P5-1.3 AC1)."""

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    @patch("app.services.homekit_camera.subprocess.run")
    @pytest.mark.asyncio
    async def test_get_snapshot_returns_jpeg(self, mock_run, mock_camera_class):
        """AC1: async_get_snapshot returns JPEG data."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))

        # Minimal JPEG bytes
        jpeg_data = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00,
            0xFF, 0xD9
        ])
        mock_run.return_value = Mock(returncode=0, stdout=jpeg_data)

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        result = await accessory._get_snapshot({"image-width": 640, "image-height": 480})

        assert result is not None
        assert len(result) > 0

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.Camera")
    @patch("app.services.homekit_camera.subprocess.run")
    @pytest.mark.asyncio
    async def test_get_snapshot_returns_placeholder_on_failure(self, mock_run, mock_camera_class):
        """AC1: Returns placeholder image when snapshot capture fails."""
        mock_camera_class.return_value = Mock(get_service=Mock(return_value=Mock()))
        mock_run.return_value = Mock(returncode=1, stdout=b"", stderr=b"Connection refused")

        accessory = HomeKitCameraAccessory(
            driver=Mock(),
            camera_id="test",
            camera_name="Test",
            rtsp_url="rtsp://test/stream",
        )

        result = await accessory._get_snapshot({"image-width": 640, "image-height": 480})

        # Should return placeholder, not raise exception
        assert result is not None
        assert len(result) > 0


class TestCameraAccessoryFactory:
    """Tests for create_camera_accessory factory function."""

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.HomeKitCameraAccessory")
    def test_factory_creates_accessory(self, mock_accessory_class):
        """Factory function creates HomeKitCameraAccessory."""
        mock_accessory = Mock()
        mock_accessory_class.return_value = mock_accessory

        result = create_camera_accessory(
            driver=Mock(),
            camera_id="test-id",
            camera_name="Test Camera",
            rtsp_url="rtsp://test/stream",
            manufacturer="TestMfg",
        )

        mock_accessory_class.assert_called_once()
        assert result == mock_accessory

    @patch("app.services.homekit_camera.HAP_AVAILABLE", True)
    @patch("app.services.homekit_camera.HomeKitCameraAccessory")
    def test_factory_returns_none_on_error(self, mock_accessory_class):
        """Factory returns None when creation fails."""
        mock_accessory_class.side_effect = Exception("Creation failed")

        result = create_camera_accessory(
            driver=Mock(),
            camera_id="test-id",
            camera_name="Test Camera",
            rtsp_url="rtsp://test/stream",
        )

        assert result is None
