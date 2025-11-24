"""
Tests for Metrics API endpoint

Tests:
    - GET /api/v1/metrics returns correct format
    - Metrics reflect actual pipeline state
    - Metrics when EventProcessor not initialized
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

from main import app
from app.services.event_processor import EventProcessor, ProcessingMetrics


client = TestClient(app)


class TestMetricsAPI:
    """Test metrics API endpoint"""

    @patch('app.api.v1.metrics.get_event_processor')
    def test_get_metrics_success(self, mock_get_processor):
        """Test getting metrics when processor is running"""
        # Mock EventProcessor with metrics
        mock_processor = Mock()
        mock_metrics = {
            "queue_depth": 3,
            "events_processed": {
                "success": 142,
                "failure": 5,
                "total": 147
            },
            "processing_time_ms": {
                "p50": 2341.2,
                "p95": 4523.8,
                "p99": 4891.1
            },
            "pipeline_errors": {
                "ai_service_failed": 3,
                "event_storage_failed": 2
            }
        }
        mock_processor.get_metrics.return_value = mock_metrics
        mock_get_processor.return_value = mock_processor

        response = client.get("/api/v1/metrics")

        assert response.status_code == 200
        data = response.json()

        assert data["queue_depth"] == 3
        assert data["events_processed"]["success"] == 142
        assert data["events_processed"]["failure"] == 5
        assert data["events_processed"]["total"] == 147
        assert data["processing_time_ms"]["p50"] == 2341.2
        assert data["processing_time_ms"]["p95"] == 4523.8
        assert data["processing_time_ms"]["p99"] == 4891.1
        assert data["pipeline_errors"]["ai_service_failed"] == 3
        assert data["pipeline_errors"]["event_storage_failed"] == 2

    @patch('app.api.v1.metrics.get_event_processor')
    def test_get_metrics_processor_not_initialized(self, mock_get_processor):
        """Test getting metrics when processor is not initialized"""
        mock_get_processor.return_value = None

        response = client.get("/api/v1/metrics")

        assert response.status_code == 200
        data = response.json()

        # Should return zero metrics
        assert data["queue_depth"] == 0
        assert data["events_processed"]["success"] == 0
        assert data["events_processed"]["failure"] == 0
        assert data["events_processed"]["total"] == 0
        assert data["processing_time_ms"]["p50"] == 0.0
        assert data["processing_time_ms"]["p95"] == 0.0
        assert data["processing_time_ms"]["p99"] == 0.0
        assert data["pipeline_errors"] == {}

    @patch('app.api.v1.metrics.get_event_processor')
    def test_get_metrics_format(self, mock_get_processor):
        """Test metrics response format conforms to spec"""
        mock_processor = Mock()
        mock_metrics = {
            "queue_depth": 0,
            "events_processed": {
                "success": 0,
                "failure": 0,
                "total": 0
            },
            "processing_time_ms": {
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0
            },
            "pipeline_errors": {}
        }
        mock_processor.get_metrics.return_value = mock_metrics
        mock_get_processor.return_value = mock_processor

        response = client.get("/api/v1/metrics")

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields exist
        assert "queue_depth" in data
        assert "events_processed" in data
        assert "success" in data["events_processed"]
        assert "failure" in data["events_processed"]
        assert "total" in data["events_processed"]
        assert "processing_time_ms" in data
        assert "p50" in data["processing_time_ms"]
        assert "p95" in data["processing_time_ms"]
        assert "p99" in data["processing_time_ms"]
        assert "pipeline_errors" in data

        # Verify types
        assert isinstance(data["queue_depth"], int)
        assert isinstance(data["events_processed"]["success"], int)
        assert isinstance(data["events_processed"]["failure"], int)
        assert isinstance(data["events_processed"]["total"], int)
        assert isinstance(data["processing_time_ms"]["p50"], float)
        assert isinstance(data["processing_time_ms"]["p95"], float)
        assert isinstance(data["processing_time_ms"]["p99"], float)
        assert isinstance(data["pipeline_errors"], dict)


@pytest.mark.asyncio
class TestMetricsIntegration:
    """Integration tests for metrics with real EventProcessor"""

    async def test_metrics_reflect_actual_state(self):
        """Test metrics accurately reflect processor state"""
        from app.services.event_processor import ProcessingEvent
        import numpy as np
        from datetime import datetime, timezone

        processor = EventProcessor(worker_count=2, queue_maxsize=10)

        # Queue some events
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        for i in range(3):
            event = ProcessingEvent(
                camera_id=f"camera-{i}",
                camera_name=f"Camera {i}",
                frame=frame,
                timestamp=datetime.now(timezone.utc)
            )
            await processor.queue_event(event)

        # Get metrics
        metrics = processor.get_metrics()

        assert metrics["queue_depth"] == 3

    async def test_metrics_processing_times(self):
        """Test metrics track processing times correctly"""
        processor = EventProcessor(worker_count=2, queue_maxsize=10)

        # Record some processing times
        processor.metrics.record_processing_time(1500.0)
        processor.metrics.record_processing_time(2500.0)
        processor.metrics.record_processing_time(3500.0)
        processor.metrics.record_processing_time(4500.0)
        processor.metrics.record_processing_time(5500.0)

        metrics = processor.get_metrics()

        assert metrics["processing_time_ms"]["p50"] > 0
        assert metrics["processing_time_ms"]["p95"] > 0
        assert metrics["processing_time_ms"]["p99"] > 0

    async def test_metrics_error_tracking(self):
        """Test metrics track errors correctly"""
        processor = EventProcessor(worker_count=2, queue_maxsize=10)

        # Increment errors
        processor.metrics.increment_error("ai_service_failed")
        processor.metrics.increment_error("ai_service_failed")
        processor.metrics.increment_error("event_storage_failed")

        metrics = processor.get_metrics()

        assert metrics["pipeline_errors"]["ai_service_failed"] == 2
        assert metrics["pipeline_errors"]["event_storage_failed"] == 1
