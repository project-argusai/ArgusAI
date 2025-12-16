"""
Unit tests for EventProcessor service

Tests:
    - ProcessingEvent dataclass
    - ProcessingMetrics tracking
    - EventProcessor initialization
    - Queue operations (queue_event, overflow handling)
    - Worker pool creation
    - Graceful shutdown
    - Error handling (retry logic, worker restart)
    - Cooldown enforcement
"""
import pytest
import asyncio
import numpy as np
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.services.event_processor import (
    ProcessingEvent,
    ProcessingMetrics,
    EventProcessor
)


class TestProcessingEvent:
    """Test ProcessingEvent dataclass"""

    def test_processing_event_creation(self):
        """Test creating a ProcessingEvent"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        timestamp = datetime.now(timezone.utc)

        event = ProcessingEvent(
            camera_id="camera-123",
            camera_name="Front Door",
            frame=frame,
            timestamp=timestamp,
            detected_objects=["person"],
            metadata={"confidence": 0.95}
        )

        assert event.camera_id == "camera-123"
        assert event.camera_name == "Front Door"
        assert isinstance(event.frame, np.ndarray)
        assert event.timestamp == timestamp
        assert event.detected_objects == ["person"]
        assert event.metadata["confidence"] == 0.95

    def test_processing_event_default_values(self):
        """Test ProcessingEvent with default values"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        timestamp = datetime.now(timezone.utc)

        event = ProcessingEvent(
            camera_id="camera-123",
            camera_name="Front Door",
            frame=frame,
            timestamp=timestamp
        )

        assert event.detected_objects == ["unknown"]
        assert event.metadata == {}


class TestProcessingMetrics:
    """Test ProcessingMetrics tracking"""

    def test_metrics_initialization(self):
        """Test ProcessingMetrics initial state"""
        metrics = ProcessingMetrics()

        assert metrics.queue_depth == 0
        assert metrics.events_processed_success == 0
        assert metrics.events_processed_failure == 0
        assert metrics.processing_times_ms == []
        assert metrics.pipeline_errors == {}

    def test_record_processing_time(self):
        """Test recording processing times"""
        metrics = ProcessingMetrics()

        metrics.record_processing_time(1500.0)
        metrics.record_processing_time(2000.0)
        metrics.record_processing_time(1800.0)

        assert len(metrics.processing_times_ms) == 3
        assert 1500.0 in metrics.processing_times_ms
        assert 2000.0 in metrics.processing_times_ms

    def test_processing_time_limit_1000(self):
        """Test processing times limited to last 1000 samples"""
        metrics = ProcessingMetrics()

        # Add 1500 samples
        for i in range(1500):
            metrics.record_processing_time(float(i))

        # Should keep only last 1000
        assert len(metrics.processing_times_ms) == 1000
        assert metrics.processing_times_ms[0] == 500.0  # First kept sample
        assert metrics.processing_times_ms[-1] == 1499.0  # Last sample

    def test_get_percentiles(self):
        """Test percentile calculation"""
        metrics = ProcessingMetrics()

        # Add known values
        values = [1000.0, 2000.0, 3000.0, 4000.0, 5000.0]
        for v in values:
            metrics.record_processing_time(v)

        percentiles = metrics.get_percentiles()

        assert percentiles["p50"] == 3000.0  # Median
        assert percentiles["p95"] == 5000.0  # 95th percentile
        assert percentiles["p99"] == 5000.0  # 99th percentile

    def test_get_percentiles_empty(self):
        """Test percentiles with no data"""
        metrics = ProcessingMetrics()

        percentiles = metrics.get_percentiles()

        assert percentiles["p50"] == 0.0
        assert percentiles["p95"] == 0.0
        assert percentiles["p99"] == 0.0

    def test_increment_error(self):
        """Test error counter increment"""
        metrics = ProcessingMetrics()

        metrics.increment_error("ai_service_failed")
        metrics.increment_error("ai_service_failed")
        metrics.increment_error("event_storage_failed")

        assert metrics.pipeline_errors["ai_service_failed"] == 2
        assert metrics.pipeline_errors["event_storage_failed"] == 1

    def test_to_dict(self):
        """Test metrics export to dictionary"""
        metrics = ProcessingMetrics()

        metrics.queue_depth = 5
        metrics.events_processed_success = 100
        metrics.events_processed_failure = 3
        metrics.record_processing_time(2000.0)
        metrics.record_processing_time(3000.0)
        metrics.increment_error("test_error")

        result = metrics.to_dict()

        assert result["queue_depth"] == 5
        assert result["events_processed"]["success"] == 100
        assert result["events_processed"]["failure"] == 3
        assert result["events_processed"]["total"] == 103
        assert "p50" in result["processing_time_ms"]
        assert result["pipeline_errors"]["test_error"] == 1


@pytest.mark.asyncio
class TestEventProcessor:
    """Test EventProcessor class"""

    @pytest.fixture
    def event_processor(self):
        """Create EventProcessor instance for testing"""
        processor = EventProcessor(worker_count=2, queue_maxsize=10)
        yield processor

    def test_initialization(self, event_processor):
        """Test EventProcessor initialization"""
        assert event_processor.worker_count == 2
        assert event_processor.queue_maxsize == 10
        assert event_processor.running == False
        assert isinstance(event_processor.event_queue, asyncio.Queue)
        assert event_processor.event_queue.maxsize == 10
        assert event_processor.metrics.queue_depth == 0

    def test_worker_count_clamping(self):
        """Test worker count is clamped to [2-5] range"""
        processor_low = EventProcessor(worker_count=1)
        assert processor_low.worker_count == 2

        processor_high = EventProcessor(worker_count=10)
        assert processor_high.worker_count == 5

        processor_valid = EventProcessor(worker_count=3)
        assert processor_valid.worker_count == 3

    @patch('app.services.event_processor.SessionLocal')
    @patch('app.services.event_processor.AIService')
    async def test_start_processor(self, mock_ai_service, mock_session, event_processor):
        """Test starting the event processor"""
        # Mock database session
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Mock AI service
        mock_ai_instance = AsyncMock()
        mock_ai_service.return_value = mock_ai_instance

        await event_processor.start()

        assert event_processor.running == True
        assert event_processor.ai_service is not None
        assert event_processor.http_client is not None
        assert len(event_processor.worker_tasks) == 2  # 2 workers

        # Cleanup
        await event_processor.stop(timeout=1.0)

    async def test_stop_processor(self, event_processor):
        """Test stopping the event processor"""
        event_processor.running = True
        event_processor.http_client = AsyncMock()

        await event_processor.stop(timeout=1.0)

        assert event_processor.running == False
        assert len(event_processor.worker_tasks) == 0
        assert len(event_processor.motion_tasks) == 0

    async def test_queue_event(self, event_processor):
        """Test queuing an event"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        timestamp = datetime.now(timezone.utc)

        event = ProcessingEvent(
            camera_id="camera-123",
            camera_name="Front Door",
            frame=frame,
            timestamp=timestamp
        )

        await event_processor.queue_event(event)

        assert event_processor.event_queue.qsize() == 1
        assert event_processor.metrics.queue_depth == 1
        assert event_processor.camera_cooldowns["camera-123"] > 0

    async def test_queue_overflow_drops_oldest(self, event_processor):
        """Test queue overflow handling - drops oldest event"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Fill queue to max (10 events)
        for i in range(10):
            event = ProcessingEvent(
                camera_id=f"camera-{i}",
                camera_name=f"Camera {i}",
                frame=frame,
                timestamp=datetime.now(timezone.utc)
            )
            await event_processor.queue_event(event)

        assert event_processor.event_queue.qsize() == 10

        # Queue 11th event - should drop oldest
        new_event = ProcessingEvent(
            camera_id="camera-new",
            camera_name="New Camera",
            frame=frame,
            timestamp=datetime.now(timezone.utc)
        )
        await event_processor.queue_event(new_event)

        # Queue should still be at max size
        assert event_processor.event_queue.qsize() == 10

        # Get first event - should be camera-1 (camera-0 was dropped)
        first_event = await asyncio.wait_for(event_processor.event_queue.get(), timeout=1.0)
        assert first_event.camera_id == "camera-1"

    def test_get_metrics(self, event_processor):
        """Test getting metrics"""
        event_processor.metrics.queue_depth = 3
        event_processor.metrics.events_processed_success = 50
        event_processor.metrics.events_processed_failure = 2

        metrics = event_processor.get_metrics()

        assert metrics["queue_depth"] == 3
        assert metrics["events_processed"]["success"] == 50
        assert metrics["events_processed"]["failure"] == 2
        assert metrics["events_processed"]["total"] == 52

    @patch('app.services.event_processor.SessionLocal')
    async def test_store_event_with_retry_success(self, mock_session_local, event_processor):
        """Test storing event with successful database insertion"""
        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        event_data = {
            "camera_id": "camera-123",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Test description",
            "confidence": 85,
            "objects_detected": ["person"],
            "thumbnail_base64": None,
            "alert_triggered": False
        }

        result = await event_processor._store_event_with_retry(event_data, max_retries=3)

        # Method now returns event_id (string) on success, None on failure
        assert result is not None
        assert isinstance(result, str)  # Should be a UUID string
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch('app.services.event_processor.SessionLocal')
    async def test_store_event_with_retry_failure(self, mock_session_local, event_processor):
        """Test storing event with all retries failing"""
        # Mock database session that raises exception
        mock_db = MagicMock()
        mock_db.commit.side_effect = Exception("Database error")
        mock_session_local.return_value = mock_db

        event_data = {
            "camera_id": "camera-123",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Test description",
            "confidence": 85,
            "objects_detected": ["person"],
            "thumbnail_base64": None,
            "alert_triggered": False
        }

        result = await event_processor._store_event_with_retry(event_data, max_retries=2)

        # Method returns None on failure
        assert result is None
        # Should be called 3 times (initial + 2 retries)
        assert mock_db.commit.call_count == 3

    @patch('app.services.event_processor.SessionLocal')
    async def test_store_event_with_retry_eventual_success(self, mock_session_local, event_processor):
        """Test storing event succeeds after retry"""
        # Mock database session that fails first, then succeeds
        mock_db = MagicMock()
        mock_db.commit.side_effect = [Exception("Transient error"), None]  # Fail, then succeed
        mock_session_local.return_value = mock_db

        event_data = {
            "camera_id": "camera-123",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Test description",
            "confidence": 85,
            "objects_detected": ["person"],
            "thumbnail_base64": None,
            "alert_triggered": False
        }

        result = await event_processor._store_event_with_retry(event_data, max_retries=3)

        # Method returns event_id (string) on success
        assert result is not None
        assert isinstance(result, str)
        # Should be called twice (first fail, second success)
        assert mock_db.commit.call_count == 2

    async def test_cooldown_enforcement(self, event_processor):
        """Test camera cooldown enforcement"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        timestamp = datetime.now(timezone.utc)

        # Queue first event
        event1 = ProcessingEvent(
            camera_id="camera-123",
            camera_name="Front Door",
            frame=frame,
            timestamp=timestamp
        )
        await event_processor.queue_event(event1)

        # Check cooldown was set
        assert "camera-123" in event_processor.camera_cooldowns
        cooldown_time = event_processor.camera_cooldowns["camera-123"]
        assert cooldown_time > 0

    async def test_drain_queue(self, event_processor):
        """Test queue draining during shutdown"""
        event_processor.http_client = AsyncMock()
        event_processor.ai_service = AsyncMock()

        # Mock AI service response
        mock_ai_result = Mock()
        mock_ai_result.success = True
        mock_ai_result.description = "Test description"
        mock_ai_result.confidence = 85
        mock_ai_result.objects_detected = ["person"]
        mock_ai_result.provider = "openai"
        mock_ai_result.response_time_ms = 1500
        event_processor.ai_service.generate_description = AsyncMock(return_value=mock_ai_result)

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 201
        event_processor.http_client.post = AsyncMock(return_value=mock_response)

        # Add events to queue
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        for i in range(3):
            event = ProcessingEvent(
                camera_id=f"camera-{i}",
                camera_name=f"Camera {i}",
                frame=frame,
                timestamp=datetime.now(timezone.utc)
            )
            await event_processor.event_queue.put(event)

        assert event_processor.event_queue.qsize() == 3

        # Drain queue
        await event_processor._drain_queue()

        assert event_processor.event_queue.qsize() == 0


@pytest.mark.asyncio
class TestEventProcessorIntegration:
    """Integration tests for EventProcessor with real asyncio"""

    @patch('app.services.event_processor.SessionLocal')
    async def test_full_pipeline_simulation(self, mock_session_local):
        """Test full pipeline with mocked services"""
        # Mock database session for event storage
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        processor = EventProcessor(worker_count=2, queue_maxsize=5)

        # Mock services
        processor.ai_service = AsyncMock()

        # Mock AI response
        mock_ai_result = Mock()
        mock_ai_result.success = True
        mock_ai_result.description = "Person approaching front door"
        mock_ai_result.confidence = 92
        mock_ai_result.objects_detected = ["person"]
        mock_ai_result.provider = "openai"
        mock_ai_result.response_time_ms = 2341
        mock_ai_result.cost_estimate = 0.001
        processor.ai_service.generate_description = AsyncMock(return_value=mock_ai_result)

        # Start processor (without database initialization)
        processor.running = True

        # Start workers manually
        for i in range(processor.worker_count):
            worker_task = asyncio.create_task(processor._ai_worker(worker_id=i))
            processor.worker_tasks.append(worker_task)

        # Queue test event
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        event = ProcessingEvent(
            camera_id="camera-test",
            camera_name="Test Camera",
            frame=frame,
            timestamp=datetime.now(timezone.utc),
            detected_objects=["unknown"]
        )
        await processor.queue_event(event)

        # Wait for processing
        await asyncio.sleep(0.5)

        # Verify event was processed
        assert processor.metrics.events_processed_success >= 1
        processor.ai_service.generate_description.assert_called()
        # Verify event was stored via database (not HTTP)
        mock_db.add.assert_called()
        mock_db.commit.assert_called()

        # Stop processor
        await processor.stop(timeout=1.0)

        assert processor.running == False

    async def test_performance_throughput(self):
        """Test processing throughput (10+ events/minute target)"""
        processor = EventProcessor(worker_count=3, queue_maxsize=50)

        # Mock fast services
        processor.ai_service = AsyncMock()
        processor.http_client = AsyncMock()

        mock_ai_result = Mock()
        mock_ai_result.success = True
        mock_ai_result.description = "Test"
        mock_ai_result.confidence = 85
        mock_ai_result.objects_detected = ["test"]
        mock_ai_result.provider = "openai"
        mock_ai_result.response_time_ms = 100
        mock_ai_result.cost_estimate = 0.001  # Add cost estimate
        processor.ai_service.generate_description = AsyncMock(return_value=mock_ai_result)

        # Start processor
        processor.running = True
        for i in range(processor.worker_count):
            worker_task = asyncio.create_task(processor._ai_worker(worker_id=i))
            processor.worker_tasks.append(worker_task)

        # Queue 20 events
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        start_time = asyncio.get_event_loop().time()

        for i in range(20):
            event = ProcessingEvent(
                camera_id=f"camera-{i}",
                camera_name=f"Camera {i}",
                frame=frame,
                timestamp=datetime.now(timezone.utc)
            )
            await processor.queue_event(event)

        # Wait for all events to be processed
        await asyncio.sleep(2.0)

        end_time = asyncio.get_event_loop().time()
        duration_seconds = end_time - start_time

        # Calculate throughput
        events_per_minute = (processor.metrics.events_processed_success / duration_seconds) * 60

        # Verify throughput target (should be much higher with mocked services)
        assert events_per_minute > 10, f"Throughput {events_per_minute:.1f} events/min is below 10 events/min target"

        # Stop processor
        await processor.stop(timeout=1.0)


@pytest.mark.asyncio
class TestMQTTEventPublishing:
    """Tests for MQTT event publishing in EventProcessor (Story P4-2.3)."""

    async def test_publish_event_to_mqtt_success(self):
        """Test successful MQTT publish (AC1)."""
        from app.services.event_processor import EventProcessor
        from app.services.mqtt_service import MQTTService

        processor = EventProcessor(worker_count=2)

        # Create mock MQTT service
        mock_mqtt_service = MagicMock(spec=MQTTService)
        mock_mqtt_service.publish = AsyncMock(return_value=True)

        # Test payload
        payload = {
            "event_id": "test-event-123",
            "camera_id": "camera-456",
            "description": "Test event"
        }

        await processor._publish_event_to_mqtt(
            mock_mqtt_service,
            "liveobject/camera/camera-456/event",
            payload,
            "test-event-123"
        )

        # Verify publish was called with correct args
        mock_mqtt_service.publish.assert_called_once_with(
            "liveobject/camera/camera-456/event",
            payload
        )

    async def test_publish_event_to_mqtt_failure_no_propagate(self):
        """Test MQTT publish failure doesn't propagate exception (AC5, AC6)."""
        from app.services.event_processor import EventProcessor
        from app.services.mqtt_service import MQTTService

        processor = EventProcessor(worker_count=2)

        # Create mock MQTT service that raises exception
        mock_mqtt_service = MagicMock(spec=MQTTService)
        mock_mqtt_service.publish = AsyncMock(side_effect=Exception("MQTT broker unavailable"))

        # This should NOT raise an exception
        await processor._publish_event_to_mqtt(
            mock_mqtt_service,
            "liveobject/camera/test/event",
            {"event_id": "123"},
            "123"
        )

        # If we get here, the exception was caught (test passes)
        mock_mqtt_service.publish.assert_called_once()

    async def test_publish_event_to_mqtt_returns_false_logged(self):
        """Test MQTT publish returning False is handled gracefully."""
        from app.services.event_processor import EventProcessor
        from app.services.mqtt_service import MQTTService

        processor = EventProcessor(worker_count=2)

        # Create mock MQTT service that returns False
        mock_mqtt_service = MagicMock(spec=MQTTService)
        mock_mqtt_service.publish = AsyncMock(return_value=False)

        # This should NOT raise
        await processor._publish_event_to_mqtt(
            mock_mqtt_service,
            "liveobject/camera/test/event",
            {"event_id": "123"},
            "123"
        )

        mock_mqtt_service.publish.assert_called_once()

    async def test_mqtt_publish_latency_under_100ms(self):
        """Test MQTT publish adds less than 100ms latency (AC5)."""
        import time
        from app.services.event_processor import EventProcessor
        from app.services.mqtt_service import MQTTService

        processor = EventProcessor(worker_count=2)

        # Create mock MQTT service with 50ms simulated delay
        async def slow_publish(topic, payload):
            await asyncio.sleep(0.05)  # 50ms
            return True

        mock_mqtt_service = MagicMock(spec=MQTTService)
        mock_mqtt_service.publish = slow_publish

        payload = {"event_id": "test-123"}

        start_time = time.time()
        await processor._publish_event_to_mqtt(
            mock_mqtt_service,
            "liveobject/camera/test/event",
            payload,
            "test-123"
        )
        end_time = time.time()

        duration_ms = (end_time - start_time) * 1000

        # Should complete within 100ms (50ms simulated + overhead)
        assert duration_ms < 100, f"MQTT publish took {duration_ms:.1f}ms, exceeds 100ms target"

    async def test_mqtt_publish_skipped_when_disconnected(self):
        """Test MQTT publish is skipped when service not connected (AC6)."""
        from app.services.mqtt_service import MQTTService

        # Create mock MQTT service that is not connected
        mock_mqtt_service = MQTTService()
        mock_mqtt_service._connected = False

        # Verify is_connected returns False
        assert mock_mqtt_service.is_connected is False

        # Test that publish returns False when not connected
        result = await mock_mqtt_service.publish(
            "liveobject/camera/test/event",
            {"event_id": "123"}
        )

        # Should return False without attempting to publish
        assert result is False

    async def test_mqtt_payload_has_correct_topic_format(self):
        """Test MQTT topic follows correct format (AC1)."""
        from app.services.mqtt_service import MQTTService, MQTTConfig

        service = MQTTService()
        service._config = MQTTConfig(
            broker_host="test.local",
            topic_prefix="liveobject"
        )

        camera_id = "abc-123-def-456"
        topic = service.get_event_topic(camera_id)

        # Verify topic format
        assert topic == f"liveobject/camera/{camera_id}/event"
        assert topic.startswith("liveobject/camera/")
        assert topic.endswith("/event")
        assert camera_id in topic
