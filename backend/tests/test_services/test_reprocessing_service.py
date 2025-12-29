"""
Unit tests for ReprocessingService (Story P14-3.4)

Tests entity reprocessing background job handling, progress tracking,
batch processing, cancellation, and WebSocket broadcasts.
"""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import uuid

import pytest

from app.services.reprocessing_service import (
    ReprocessingStatus,
    ReprocessingJob,
    ReprocessingService,
    get_reprocessing_service,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def reprocessing_service():
    """Create a fresh ReprocessingService instance."""
    return ReprocessingService()


@pytest.fixture
def mock_websocket_manager():
    """Mock the WebSocket manager."""
    with patch("app.services.reprocessing_service.get_websocket_manager") as mock:
        manager = MagicMock()
        manager.broadcast = AsyncMock()
        mock.return_value = manager
        yield manager


@pytest.fixture
def mock_embedding_service():
    """Mock the embedding service."""
    with patch("app.services.reprocessing_service.get_embedding_service") as mock:
        service = MagicMock()
        service.generate_embedding_from_file = AsyncMock(return_value=[0.1] * 512)
        service.store_embedding = AsyncMock()
        mock.return_value = service
        yield service


@pytest.fixture
def mock_entity_service():
    """Mock the entity service."""
    with patch("app.services.reprocessing_service.get_entity_service") as mock:
        service = MagicMock()
        match_result = MagicMock()
        match_result.is_new = False  # Existing entity matched
        service.match_or_create_entity = AsyncMock(return_value=match_result)
        service.match_or_create_vehicle_entity = AsyncMock(return_value=match_result)
        mock.return_value = service
        yield service


@pytest.fixture
def sample_job():
    """Create a sample ReprocessingJob."""
    return ReprocessingJob(
        job_id=str(uuid.uuid4()),
        status=ReprocessingStatus.RUNNING,
        total_events=100,
        processed=0,
        matched=0,
        embeddings_generated=0,
        errors=0,
        started_at=datetime.now(timezone.utc),
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        camera_id=None,
        only_unmatched=True,
    )


@pytest.fixture
def completed_job():
    """Create a completed ReprocessingJob."""
    started = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    completed = datetime(2025, 1, 15, 10, 5, 30, tzinfo=timezone.utc)
    return ReprocessingJob(
        job_id=str(uuid.uuid4()),
        status=ReprocessingStatus.COMPLETED,
        total_events=500,
        processed=500,
        matched=150,
        embeddings_generated=200,
        errors=5,
        started_at=started,
        completed_at=completed,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
        camera_id="camera-123",
        only_unmatched=True,
    )


# =============================================================================
# Test ReprocessingStatus Enum
# =============================================================================


class TestReprocessingStatus:
    """Tests for ReprocessingStatus enum."""

    def test_status_pending_value(self):
        """Test PENDING status has correct string value."""
        assert ReprocessingStatus.PENDING == "pending"
        assert ReprocessingStatus.PENDING.value == "pending"

    def test_status_running_value(self):
        """Test RUNNING status has correct string value."""
        assert ReprocessingStatus.RUNNING == "running"
        assert ReprocessingStatus.RUNNING.value == "running"

    def test_status_completed_value(self):
        """Test COMPLETED status has correct string value."""
        assert ReprocessingStatus.COMPLETED == "completed"
        assert ReprocessingStatus.COMPLETED.value == "completed"

    def test_status_cancelled_value(self):
        """Test CANCELLED status has correct string value."""
        assert ReprocessingStatus.CANCELLED == "cancelled"
        assert ReprocessingStatus.CANCELLED.value == "cancelled"

    def test_status_failed_value(self):
        """Test FAILED status has correct string value."""
        assert ReprocessingStatus.FAILED == "failed"
        assert ReprocessingStatus.FAILED.value == "failed"

    def test_all_status_values_exist(self):
        """Test that all expected status values exist."""
        expected_statuses = {"pending", "running", "completed", "cancelled", "failed"}
        actual_statuses = {s.value for s in ReprocessingStatus}
        assert actual_statuses == expected_statuses


# =============================================================================
# Test ReprocessingJob Dataclass
# =============================================================================


class TestReprocessingJob:
    """Tests for ReprocessingJob dataclass."""

    def test_job_initialization_required_fields(self):
        """Test job initialization with required fields only."""
        job = ReprocessingJob(
            job_id="test-job-123",
            status=ReprocessingStatus.PENDING,
            total_events=50,
        )
        assert job.job_id == "test-job-123"
        assert job.status == ReprocessingStatus.PENDING
        assert job.total_events == 50
        assert job.processed == 0
        assert job.matched == 0
        assert job.embeddings_generated == 0
        assert job.errors == 0

    def test_job_initialization_all_fields(self, sample_job):
        """Test job initialization with all fields."""
        assert sample_job.total_events == 100
        assert sample_job.only_unmatched is True
        assert sample_job.cancel_requested is False

    def test_job_to_dict_basic(self, sample_job):
        """Test to_dict serialization."""
        result = sample_job.to_dict()

        assert "job_id" in result
        assert result["status"] == "running"
        assert result["total_events"] == 100
        assert result["processed"] == 0
        assert result["matched"] == 0
        assert result["percent_complete"] == 0.0
        assert "filters" in result

    def test_job_to_dict_with_dates(self, completed_job):
        """Test to_dict serializes dates as ISO strings."""
        result = completed_job.to_dict()

        assert result["started_at"] is not None
        assert result["completed_at"] is not None
        assert "T" in result["started_at"]  # ISO format
        assert "T" in result["completed_at"]

        # Filters also include dates
        assert result["filters"]["start_date"] is not None
        assert result["filters"]["end_date"] is not None

    def test_job_to_dict_percent_complete(self):
        """Test percent_complete calculation."""
        job = ReprocessingJob(
            job_id="test",
            status=ReprocessingStatus.RUNNING,
            total_events=200,
            processed=50,
        )
        result = job.to_dict()
        assert result["percent_complete"] == 25.0

    def test_job_to_dict_percent_complete_zero_events(self):
        """Test percent_complete when total_events is zero."""
        job = ReprocessingJob(
            job_id="test",
            status=ReprocessingStatus.RUNNING,
            total_events=0,
            processed=0,
        )
        result = job.to_dict()
        assert result["percent_complete"] == 0

    def test_job_to_dict_filters_section(self, completed_job):
        """Test filters section in to_dict output."""
        result = completed_job.to_dict()

        assert "filters" in result
        filters = result["filters"]
        assert filters["camera_id"] == "camera-123"
        assert filters["only_unmatched"] is True

    def test_job_to_dict_error_message(self):
        """Test error_message in to_dict output."""
        job = ReprocessingJob(
            job_id="test",
            status=ReprocessingStatus.FAILED,
            total_events=100,
            error_message="Database connection failed",
        )
        result = job.to_dict()
        assert result["error_message"] == "Database connection failed"


# =============================================================================
# Test ReprocessingService Initialization
# =============================================================================


class TestReprocessingServiceInit:
    """Tests for ReprocessingService initialization."""

    def test_init_no_current_job(self, reprocessing_service):
        """Test that service starts with no current job."""
        assert reprocessing_service._current_job is None
        assert reprocessing_service._task is None

    def test_current_job_property(self, reprocessing_service, sample_job):
        """Test current_job property."""
        assert reprocessing_service.current_job is None

        reprocessing_service._current_job = sample_job
        assert reprocessing_service.current_job == sample_job

    def test_is_running_property_no_job(self, reprocessing_service):
        """Test is_running is False when no job."""
        assert reprocessing_service.is_running is False

    def test_is_running_property_running_job(self, reprocessing_service, sample_job):
        """Test is_running is True when job is running."""
        sample_job.status = ReprocessingStatus.RUNNING
        reprocessing_service._current_job = sample_job
        assert reprocessing_service.is_running is True

    def test_is_running_property_completed_job(self, reprocessing_service, sample_job):
        """Test is_running is False when job is completed."""
        sample_job.status = ReprocessingStatus.COMPLETED
        reprocessing_service._current_job = sample_job
        assert reprocessing_service.is_running is False

    def test_batch_size_constant(self):
        """Test BATCH_SIZE is 100."""
        assert ReprocessingService.BATCH_SIZE == 100

    def test_progress_update_interval_constant(self):
        """Test PROGRESS_UPDATE_INTERVAL is 1.0 seconds."""
        assert ReprocessingService.PROGRESS_UPDATE_INTERVAL == 1.0


class TestReprocessingServiceSingleton:
    """Tests for the singleton pattern."""

    def test_get_reprocessing_service_returns_same_instance(self):
        """Test that get_reprocessing_service returns singleton."""
        # Reset singleton
        import app.services.reprocessing_service as module
        module._reprocessing_service = None

        service1 = get_reprocessing_service()
        service2 = get_reprocessing_service()
        assert service1 is service2

        # Reset for other tests
        module._reprocessing_service = None


# =============================================================================
# Test estimate_event_count
# =============================================================================


class TestEstimateEventCount:
    """Tests for estimate_event_count method.

    These tests mock the database query to avoid complex model requirements.
    """

    @pytest.mark.asyncio
    async def test_estimate_calls_query(self, reprocessing_service):
        """Test that estimate_event_count calls the database query."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.count.return_value = 15
        mock_db.query.return_value.filter.return_value.filter.return_value = mock_query

        count = await reprocessing_service.estimate_event_count(mock_db)

        # Should call query for Event model
        mock_db.query.assert_called()
        assert count == 15

    @pytest.mark.asyncio
    async def test_estimate_with_date_filter(self, reprocessing_service):
        """Test that date filters are applied to query."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 5
        mock_db.query.return_value = mock_query

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 6, 30, tzinfo=timezone.utc)

        count = await reprocessing_service.estimate_event_count(
            mock_db,
            start_date=start_date,
            end_date=end_date,
        )

        # Filter should be called multiple times
        assert mock_query.filter.called
        assert count == 5

    @pytest.mark.asyncio
    async def test_estimate_with_camera_filter(self, reprocessing_service):
        """Test that camera_id filter is applied."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 3
        mock_db.query.return_value = mock_query

        count = await reprocessing_service.estimate_event_count(
            mock_db,
            camera_id="camera-123",
        )

        assert mock_query.filter.called
        assert count == 3

    @pytest.mark.asyncio
    async def test_estimate_only_unmatched_default(self, reprocessing_service):
        """Test that only_unmatched defaults to True and adds filter."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 10
        mock_db.query.return_value = mock_query

        count = await reprocessing_service.estimate_event_count(mock_db)

        # With only_unmatched=True, should apply filter for unlinked events
        assert mock_query.filter.called
        assert count == 10


# =============================================================================
# Test start_reprocessing
# =============================================================================


class TestStartReprocessing:
    """Tests for start_reprocessing method."""

    @pytest.mark.asyncio
    async def test_start_creates_job(self, reprocessing_service):
        """Test that start_reprocessing creates and returns a job."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 10
        mock_db.query.return_value = mock_query

        with patch.object(reprocessing_service, "_process_events", new_callable=AsyncMock):
            job = await reprocessing_service.start_reprocessing(mock_db)

        assert job is not None
        assert job.status == ReprocessingStatus.RUNNING
        assert job.total_events == 10
        assert job.started_at is not None
        assert reprocessing_service._current_job == job

    @pytest.mark.asyncio
    async def test_start_raises_when_already_running(
        self, reprocessing_service, sample_job
    ):
        """Test that starting when job is running raises ValueError."""
        reprocessing_service._current_job = sample_job
        sample_job.status = ReprocessingStatus.RUNNING

        mock_db = MagicMock()
        with pytest.raises(ValueError, match="already running"):
            await reprocessing_service.start_reprocessing(mock_db)

    @pytest.mark.asyncio
    async def test_start_raises_when_no_events(self, reprocessing_service):
        """Test that starting with no matching events raises ValueError."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0  # No events
        mock_db.query.return_value = mock_query

        with pytest.raises(ValueError, match="No events match"):
            await reprocessing_service.start_reprocessing(mock_db)

    @pytest.mark.asyncio
    async def test_start_sets_job_filters(self, reprocessing_service):
        """Test that job filters are stored correctly."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 5
        mock_db.query.return_value = mock_query

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 12, 31, tzinfo=timezone.utc)

        with patch.object(reprocessing_service, "_process_events", new_callable=AsyncMock):
            job = await reprocessing_service.start_reprocessing(
                mock_db,
                start_date=start_date,
                end_date=end_date,
                camera_id="camera-123",
                only_unmatched=False,
            )

        assert job.start_date == start_date
        assert job.end_date == end_date
        assert job.camera_id == "camera-123"
        assert job.only_unmatched is False


# =============================================================================
# Test cancel_reprocessing
# =============================================================================


class TestCancelReprocessing:
    """Tests for cancel_reprocessing method."""

    @pytest.mark.asyncio
    async def test_cancel_no_job_returns_none(self, reprocessing_service):
        """Test cancelling when no job returns None."""
        result = await reprocessing_service.cancel_reprocessing()
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_not_running_returns_none(
        self, reprocessing_service, sample_job
    ):
        """Test cancelling a completed job returns None."""
        sample_job.status = ReprocessingStatus.COMPLETED
        reprocessing_service._current_job = sample_job

        result = await reprocessing_service.cancel_reprocessing()
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_sets_flag(self, reprocessing_service, sample_job):
        """Test that cancel sets cancel_requested flag."""
        sample_job.status = ReprocessingStatus.RUNNING
        reprocessing_service._current_job = sample_job

        # Create a mock task that completes quickly
        async def mock_process():
            await asyncio.sleep(0.01)

        reprocessing_service._task = asyncio.create_task(mock_process())

        await reprocessing_service.cancel_reprocessing()

        assert sample_job.cancel_requested is True

    @pytest.mark.asyncio
    async def test_cancel_returns_job(self, reprocessing_service, sample_job):
        """Test that cancel returns the cancelled job."""
        sample_job.status = ReprocessingStatus.RUNNING
        reprocessing_service._current_job = sample_job

        async def mock_process():
            await asyncio.sleep(0.01)

        reprocessing_service._task = asyncio.create_task(mock_process())

        result = await reprocessing_service.cancel_reprocessing()

        assert result == sample_job


# =============================================================================
# Test get_status
# =============================================================================


class TestGetStatus:
    """Tests for get_status method."""

    @pytest.mark.asyncio
    async def test_get_status_no_job(self, reprocessing_service):
        """Test get_status returns None when no job."""
        result = await reprocessing_service.get_status()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_status_with_job(self, reprocessing_service, sample_job):
        """Test get_status returns current job."""
        reprocessing_service._current_job = sample_job

        result = await reprocessing_service.get_status()

        assert result == sample_job


# =============================================================================
# Test _process_events
# =============================================================================


class TestProcessEvents:
    """Tests for _process_events background task."""

    @pytest.mark.asyncio
    async def test_process_events_completes_successfully(
        self,
        reprocessing_service,
        sample_job,
        mock_websocket_manager,
        mock_embedding_service,
        mock_entity_service,
    ):
        """Test that process_events completes and sets status."""
        # Setup - create minimal job with no events to process
        sample_job.total_events = 0

        with patch("app.services.reprocessing_service.get_db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            # Return empty event list
            with patch.object(
                reprocessing_service, "_get_event_ids", new_callable=AsyncMock
            ) as mock_get_ids:
                mock_get_ids.return_value = []

                await reprocessing_service._process_events(sample_job)

        assert sample_job.status == ReprocessingStatus.COMPLETED
        assert sample_job.completed_at is not None
        mock_websocket_manager.broadcast.assert_called()

    @pytest.mark.asyncio
    async def test_process_events_respects_cancellation(
        self,
        reprocessing_service,
        sample_job,
        mock_websocket_manager,
    ):
        """Test that process_events stops on cancel_requested."""
        sample_job.cancel_requested = True

        with patch("app.services.reprocessing_service.get_db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            with patch.object(
                reprocessing_service, "_get_event_ids", new_callable=AsyncMock
            ) as mock_get_ids:
                mock_get_ids.return_value = ["event-1", "event-2", "event-3"]

                await reprocessing_service._process_events(sample_job)

        assert sample_job.status == ReprocessingStatus.CANCELLED
        assert sample_job.completed_at is not None

    @pytest.mark.asyncio
    async def test_process_events_handles_errors(
        self,
        reprocessing_service,
        sample_job,
        mock_websocket_manager,
    ):
        """Test that process_events handles exceptions and sets FAILED status."""
        with patch("app.services.reprocessing_service.get_db_session") as mock_db:
            mock_db.return_value.__enter__ = MagicMock(
                side_effect=Exception("Database error")
            )

            await reprocessing_service._process_events(sample_job)

        assert sample_job.status == ReprocessingStatus.FAILED
        assert sample_job.error_message == "Database error"
        assert sample_job.completed_at is not None


# =============================================================================
# Test _get_event_ids
# =============================================================================


class TestGetEventIds:
    """Tests for _get_event_ids method."""

    @pytest.mark.asyncio
    async def test_get_event_ids_returns_list(self, reprocessing_service, sample_job):
        """Test that _get_event_ids returns list of event IDs."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Mock query to return tuples like query(Event.id).all() returns
        # Each result is a tuple (event_id,)
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [("event-1",), ("event-2",), ("event-3",)]
        mock_db.query.return_value = mock_query

        # Set job filters to match
        sample_job.start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        sample_job.end_date = datetime(2025, 12, 31, tzinfo=timezone.utc)
        sample_job.only_unmatched = False

        result = await reprocessing_service._get_event_ids(mock_db, sample_job)

        assert len(result) == 3
        assert "event-1" in result
        assert "event-2" in result
        assert "event-3" in result

    @pytest.mark.asyncio
    async def test_get_event_ids_applies_filters(self, reprocessing_service, sample_job):
        """Test that _get_event_ids applies job filters."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []  # Returns empty list of tuples
        mock_db.query.return_value = mock_query

        sample_job.start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        sample_job.end_date = datetime(2025, 6, 30, tzinfo=timezone.utc)
        sample_job.camera_id = "camera-123"
        sample_job.only_unmatched = True

        await reprocessing_service._get_event_ids(mock_db, sample_job)

        # Should call filter multiple times for various criteria
        assert mock_query.filter.called


# =============================================================================
# Test _process_single_event
# =============================================================================


class TestProcessSingleEvent:
    """Tests for _process_single_event method.

    These tests use mocked database queries and services.
    """

    @pytest.mark.asyncio
    async def test_process_single_event_with_existing_embedding(
        self, reprocessing_service, mock_embedding_service, mock_entity_service
    ):
        """Test processing event that already has an embedding."""
        mock_db = MagicMock()

        # Mock event with existing embedding
        mock_event = MagicMock()
        mock_event.id = "event-123"
        mock_event.thumbnail_path = "/test.jpg"
        mock_event.smart_detection_type = "person"
        mock_event.description = "Person detected"

        # Mock embedding exists
        mock_embedding = MagicMock()
        mock_embedding.embedding = json.dumps([0.1] * 512)

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_event,  # Event query
            mock_embedding,  # Embedding query - exists
        ]

        result = await reprocessing_service._process_single_event(
            mock_db, "event-123", mock_embedding_service, mock_entity_service
        )

        assert result["embedding_generated"] is False  # Used existing
        mock_embedding_service.generate_embedding_from_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_single_event_generates_embedding(
        self, reprocessing_service, mock_embedding_service, mock_entity_service
    ):
        """Test processing event that needs embedding generation."""
        mock_db = MagicMock()

        # Mock event without existing embedding
        mock_event = MagicMock()
        mock_event.id = "event-456"
        mock_event.thumbnail_path = "/test.jpg"
        mock_event.smart_detection_type = "person"
        mock_event.description = "Person detected"

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_event,  # Event query
            None,  # Embedding query - doesn't exist
        ]

        result = await reprocessing_service._process_single_event(
            mock_db, "event-456", mock_embedding_service, mock_entity_service
        )

        assert result["embedding_generated"] is True
        mock_embedding_service.generate_embedding_from_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_single_event_no_thumbnail_returns_early(
        self, reprocessing_service, mock_embedding_service, mock_entity_service
    ):
        """Test that events without thumbnails are skipped."""
        mock_db = MagicMock()

        # Mock event without thumbnail
        mock_event = MagicMock()
        mock_event.id = "event-789"
        mock_event.thumbnail_path = None  # No thumbnail
        mock_event.smart_detection_type = "person"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_event

        result = await reprocessing_service._process_single_event(
            mock_db, "event-789", mock_embedding_service, mock_entity_service
        )

        assert result["matched"] is False
        assert result["embedding_generated"] is False
        mock_embedding_service.generate_embedding_from_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_single_event_vehicle_detection(
        self, reprocessing_service, mock_embedding_service, mock_entity_service
    ):
        """Test that vehicle events use vehicle matching."""
        mock_db = MagicMock()

        # Mock vehicle event
        mock_event = MagicMock()
        mock_event.id = "event-vehicle"
        mock_event.thumbnail_path = "/test.jpg"
        mock_event.smart_detection_type = "vehicle"
        mock_event.description = "Blue Honda Civic in driveway"

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_event,  # Event query
            None,  # Embedding query - doesn't exist
        ]

        await reprocessing_service._process_single_event(
            mock_db, "event-vehicle", mock_embedding_service, mock_entity_service
        )

        mock_entity_service.match_or_create_vehicle_entity.assert_called_once()
        mock_entity_service.match_or_create_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_single_event_not_found(
        self, reprocessing_service, mock_embedding_service, mock_entity_service
    ):
        """Test processing when event is not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await reprocessing_service._process_single_event(
            mock_db, "nonexistent", mock_embedding_service, mock_entity_service
        )

        assert result["matched"] is False
        assert result["embedding_generated"] is False


# =============================================================================
# Test WebSocket Broadcasts
# =============================================================================


class TestWebSocketBroadcasts:
    """Tests for WebSocket broadcast methods."""

    @pytest.mark.asyncio
    async def test_broadcast_progress_format(
        self, reprocessing_service, sample_job, mock_websocket_manager
    ):
        """Test progress broadcast message format."""
        sample_job.processed = 50
        sample_job.matched = 10
        sample_job.embeddings_generated = 25
        sample_job.errors = 2

        await reprocessing_service._broadcast_progress(mock_websocket_manager, sample_job)

        mock_websocket_manager.broadcast.assert_called_once()
        call_args = mock_websocket_manager.broadcast.call_args[0][0]

        assert call_args["type"] == "reprocessing_progress"
        assert call_args["data"]["job_id"] == sample_job.job_id
        assert call_args["data"]["processed"] == 50
        assert call_args["data"]["total"] == 100
        assert call_args["data"]["matched"] == 10
        assert call_args["data"]["embeddings_generated"] == 25
        assert call_args["data"]["errors"] == 2
        assert call_args["data"]["percent_complete"] == 50.0

    @pytest.mark.asyncio
    async def test_broadcast_completion_on_success(
        self, reprocessing_service, completed_job, mock_websocket_manager
    ):
        """Test completion broadcast for successful job."""
        await reprocessing_service._broadcast_completion(mock_websocket_manager, completed_job)

        mock_websocket_manager.broadcast.assert_called_once()
        call_args = mock_websocket_manager.broadcast.call_args[0][0]

        assert call_args["type"] == "reprocessing_complete"
        assert call_args["data"]["status"] == "completed"
        assert call_args["data"]["total_processed"] == 500
        assert call_args["data"]["total_matched"] == 150
        assert call_args["data"]["embeddings_generated"] == 200
        assert call_args["data"]["total_errors"] == 5
        assert call_args["data"]["duration_seconds"] == 330.0  # 5m 30s
        assert call_args["data"]["error_message"] is None

    @pytest.mark.asyncio
    async def test_broadcast_completion_on_cancel(
        self, reprocessing_service, sample_job, mock_websocket_manager
    ):
        """Test completion broadcast for cancelled job."""
        sample_job.status = ReprocessingStatus.CANCELLED
        sample_job.completed_at = datetime.now(timezone.utc)

        await reprocessing_service._broadcast_completion(mock_websocket_manager, sample_job)

        call_args = mock_websocket_manager.broadcast.call_args[0][0]
        assert call_args["data"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_broadcast_completion_on_failure(
        self, reprocessing_service, sample_job, mock_websocket_manager
    ):
        """Test completion broadcast for failed job."""
        sample_job.status = ReprocessingStatus.FAILED
        sample_job.error_message = "Database connection lost"
        sample_job.completed_at = datetime.now(timezone.utc)

        await reprocessing_service._broadcast_completion(mock_websocket_manager, sample_job)

        call_args = mock_websocket_manager.broadcast.call_args[0][0]
        assert call_args["data"]["status"] == "failed"
        assert call_args["data"]["error_message"] == "Database connection lost"

    @pytest.mark.asyncio
    async def test_broadcast_completion_duration_calculation(
        self, reprocessing_service, mock_websocket_manager
    ):
        """Test that duration is calculated correctly."""
        job = ReprocessingJob(
            job_id="test",
            status=ReprocessingStatus.COMPLETED,
            total_events=100,
            started_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2025, 1, 15, 10, 2, 30, tzinfo=timezone.utc),  # 2.5 minutes
        )

        await reprocessing_service._broadcast_completion(mock_websocket_manager, job)

        call_args = mock_websocket_manager.broadcast.call_args[0][0]
        assert call_args["data"]["duration_seconds"] == 150.0
