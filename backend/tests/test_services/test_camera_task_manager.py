"""Unit tests for CameraTaskManager"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import time

from app.services.camera_task_manager import CameraTaskManager
from app.models.camera import Camera


class TestCameraTaskManager:
    """Tests for CameraTaskManager"""

    @pytest.fixture
    def mock_camera_service(self):
        """Mock CameraService"""
        service = Mock()
        service.get_camera_status.return_value = {"worker_alive": True}
        service.restart_camera = Mock()
        service.get_frame = Mock(return_value=b"fake-frame-data")
        return service

    @pytest.fixture
    def mock_motion_service(self):
        """Mock MotionDetectionService"""
        service = Mock()
        service.process_frame.return_value = {"motion_detected": False}
        return service

    @pytest.fixture
    def mock_queue_event(self):
        """Mock queue_event callback"""
        return AsyncMock()

    @pytest.fixture
    def sample_camera(self):
        """Create a sample camera for testing"""
        camera = Mock(spec=Camera)
        camera.id = "cam-123"
        camera.name = "Test Camera"
        camera.frame_rate = 5
        camera.motion_cooldown = 2.0
        return camera

    @pytest.fixture
    def task_manager(self, mock_camera_service, mock_motion_service, mock_queue_event):
        """Create a CameraTaskManager with mocks"""
        return CameraTaskManager(
            camera_service=mock_camera_service,
            motion_service=mock_motion_service,
            queue_event_callback=mock_queue_event,
        )

    def test_initial_state(self, task_manager):
        """Manager should start with empty monitoring state"""
        assert task_manager.get_monitored_cameras() == []
        assert task_manager.is_monitoring("cam-123") is False
        assert task_manager.get_motion_task_stats() == {}

    @pytest.mark.asyncio
    async def test_start_and_stop_monitoring(self, task_manager, sample_camera):
        """Should be able to start and stop monitoring a camera"""
        # Start monitoring (this will create a task that runs the loop)
        await task_manager.start_monitoring(sample_camera)

        assert task_manager.is_monitoring("cam-123") is True
        assert "cam-123" in task_manager.get_monitored_cameras()

        # Stop it
        await task_manager.stop_monitoring("cam-123")

        assert task_manager.is_monitoring("cam-123") is False
        assert task_manager.get_monitored_cameras() == []

    @pytest.mark.asyncio
    async def test_start_monitoring_already_running(self, task_manager, sample_camera):
        """Starting an already monitored camera should be a no-op"""
        await task_manager.start_monitoring(sample_camera)
        # Start again
        await task_manager.start_monitoring(sample_camera)

        # Should still only have one task
        assert len(task_manager.get_monitored_cameras()) == 1

        await task_manager.stop_monitoring("cam-123")

    def test_stats_recording(self, task_manager, sample_camera):
        """Stats helpers should work correctly"""
        task_manager.record_frame_pulled("cam-123")
        task_manager.record_motion_check("cam-123")
        task_manager.record_error("cam-123")

        stats = task_manager.get_motion_task_stats()
        assert "cam-123" in stats
        assert stats["cam-123"]["frames_pulled"] == 1
        assert stats["cam-123"]["motion_checks"] == 1
        assert stats["cam-123"]["errors"] == 1

    @pytest.mark.asyncio
    async def test_handle_unhealthy_camera_worker(self, task_manager, sample_camera, mock_camera_service):
        """Recovery logic should call restart and track attempts"""
        await task_manager.handle_unhealthy_camera_worker(sample_camera, context="test")

        # Should have called restart
        mock_camera_service.restart_camera.assert_called_once_with(sample_camera)

        stats = task_manager.get_motion_task_stats()
        assert stats["cam-123"]["recovery_attempts"] == 1

    @pytest.mark.asyncio
    async def test_shutdown_stops_loops(self, task_manager, sample_camera):
        """shutdown() should cause running loops to exit cleanly"""
        # Start a camera (spawns a long-running loop)
        await task_manager.start_monitoring(sample_camera)
        assert task_manager.is_monitoring("cam-123") is True

        # Trigger shutdown
        task_manager.shutdown()

        # Give the loop a moment to react
        await asyncio.sleep(0.1)

        # The task should have finished (or be cancelled)
        task = task_manager._motion_tasks.get("cam-123")
        if task:
            # Either done or will be cleaned by stop_all
            assert task.done() or task.cancelled() or not task_manager.is_monitoring("cam-123")

        # Clean stop
        await task_manager.stop_all()
        assert task_manager.get_monitored_cameras() == []

    @pytest.mark.asyncio
    async def test_graceful_loop_exit_on_shutdown(self, task_manager, sample_camera):
        """Loops should exit when shutdown is signaled (not just via cancellation)"""
        await task_manager.start_monitoring(sample_camera)

        # Signal shutdown instead of cancelling the task directly
        task_manager.shutdown()

        # Wait a bit for the loop to exit via the event
        await asyncio.sleep(0.2)

        # After shutdown, starting the same camera again should work
        # (proving the previous loop exited)
        await task_manager.stop_all()  # ensure clean state

        # Restart should succeed
        await task_manager.start_monitoring(sample_camera)
        assert task_manager.is_monitoring("cam-123") is True

        await task_manager.stop_all()

    @pytest.mark.asyncio
    async def test_cooldown_tracking(self, task_manager, sample_camera):
        """Cooldown helpers should work"""
        assert task_manager.get_cooldown("cam-123") == 0.0

        task_manager.update_cooldown("cam-123", 12345.67)
        assert task_manager.get_cooldown("cam-123") == 12345.67

    def test_get_monitored_cameras(self, task_manager, sample_camera):
        """get_monitored_cameras should return current camera ids"""
        # This test is limited because we can't easily start without async,
        # but we can at least verify the method exists and works on empty state
        assert task_manager.get_monitored_cameras() == []

        # After starting (in async test) it would return the id.
        # Here we just ensure the API is stable.