"""
Tests for Multi-Camera Event Correlation Service (Story P2-4.3)

Tests cover all acceptance criteria:
- AC1: Events from multiple cameras within the correlation window correlate
- AC2: Correlation logic (time window, different cameras)
- AC3: First event gets new UUID, subsequent get same ID
- AC4: correlated_event_ids contains all event IDs
- AC5: Buffer maintains 60s window with O(n) scan
- AC6: Correlation runs asynchronously (fire-and-forget)
- AC7: Events join existing correlation groups
- AC8: Simultaneous events get same group ID
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.correlation_service import (
    BufferedEvent,
    CorrelationService,
    DEFAULT_BUFFER_MAX_AGE_SECONDS,
    DEFAULT_TIME_WINDOW_SECONDS,
    get_correlation_service,
    reset_correlation_service,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def correlation_service():
    """Fresh correlation service instance for each test."""
    service = CorrelationService()
    yield service
    service.clear_buffer()


@pytest.fixture
def correlation_service_short_window():
    """Correlation service with 5 second window for faster tests."""
    service = CorrelationService(time_window_seconds=5, buffer_max_age_seconds=30)
    yield service
    service.clear_buffer()


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the global singleton before each test."""
    reset_correlation_service()
    yield
    reset_correlation_service()


def make_buffered_event(
    camera_id: str = "cam1",
    smart_detection_type: str = "person",
    timestamp: datetime = None,
    correlation_group_id: str = None,
    event_id: str = None
) -> BufferedEvent:
    """Create a BufferedEvent for testing."""
    return BufferedEvent(
        id=event_id or str(uuid.uuid4()),
        camera_id=camera_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        smart_detection_type=smart_detection_type,
        correlation_group_id=correlation_group_id,
        protect_controller_id=None
    )


def make_mock_event(
    camera_id: str = "cam1",
    smart_detection_type: str = "person",
    timestamp: datetime = None,
    correlation_group_id: str = None,
    event_id: str = None
) -> MagicMock:
    """Create a mock Event model for testing."""
    event = MagicMock()
    event.id = event_id or str(uuid.uuid4())
    event.camera_id = camera_id
    event.timestamp = timestamp or datetime.now(timezone.utc)
    event.smart_detection_type = smart_detection_type
    event.correlation_group_id = correlation_group_id
    event.camera = None
    return event


# ============================================================================
# Unit Tests: Buffer Operations (AC5)
# ============================================================================

class TestBufferOperations:
    """Tests for correlation buffer operations (AC5)."""

    def test_add_to_buffer(self, correlation_service):
        """Event is added to buffer correctly."""
        event = make_mock_event(camera_id="cam1", smart_detection_type="person")

        buffered = correlation_service.add_to_buffer(event)

        assert buffered.id == event.id
        assert buffered.camera_id == event.camera_id
        assert buffered.smart_detection_type == event.smart_detection_type
        assert len(correlation_service._buffer) == 1

    def test_buffer_cleanup_removes_old_events(self, correlation_service):
        """Events older than buffer_max_age are removed."""
        # Add old event
        old_time = datetime.now(timezone.utc) - timedelta(seconds=70)
        old_event = make_mock_event(timestamp=old_time)
        correlation_service._buffer.append((old_time, make_buffered_event(timestamp=old_time)))

        # Add new event - should trigger cleanup
        new_event = make_mock_event()
        correlation_service.add_to_buffer(new_event)

        # Old event should be removed
        assert len(correlation_service._buffer) == 1
        _, buffered = correlation_service._buffer[0]
        assert buffered.id == new_event.id

    def test_buffer_stats(self, correlation_service):
        """Buffer stats are calculated correctly."""
        # Empty buffer
        stats = correlation_service.get_buffer_stats()
        assert stats["buffer_size"] == 0
        assert stats["oldest_event_age_seconds"] is None

        # Add events
        event1 = make_mock_event()
        event2 = make_mock_event()
        correlation_service.add_to_buffer(event1)
        time.sleep(0.1)
        correlation_service.add_to_buffer(event2)

        stats = correlation_service.get_buffer_stats()
        assert stats["buffer_size"] == 2
        assert stats["oldest_event_age_seconds"] is not None
        assert stats["newest_event_age_seconds"] is not None

    def test_clear_buffer(self, correlation_service):
        """Buffer can be cleared."""
        event = make_mock_event()
        correlation_service.add_to_buffer(event)
        assert len(correlation_service._buffer) == 1

        count = correlation_service.clear_buffer()

        assert count == 1
        assert len(correlation_service._buffer) == 0


# ============================================================================
# Unit Tests: Correlation Candidates (AC1, AC2)
# ============================================================================

class TestFindCorrelationCandidates:
    """Tests for finding correlation candidates (AC1, AC2)."""

    def test_finds_candidates_within_time_window(self, correlation_service):
        """AC2: Events within time window are found as candidates."""
        now = datetime.now(timezone.utc)

        # Add first event
        event1 = make_buffered_event(camera_id="cam1", timestamp=now)
        correlation_service._buffer.append((now, event1))

        # Find candidates for second event (1 second later, different camera)
        event2 = make_buffered_event(
            camera_id="cam2",
            timestamp=now + timedelta(seconds=1)
        )

        candidates = correlation_service.find_correlation_candidates(event2)

        assert len(candidates) == 1
        assert candidates[0].id == event1.id

    def test_no_candidates_outside_time_window(self, correlation_service):
        """AC2: Events outside time window are not candidates."""
        now = datetime.now(timezone.utc)

        # Add first event
        event1 = make_buffered_event(camera_id="cam1", timestamp=now)
        correlation_service._buffer.append((now, event1))

        # Find candidates for event 15 seconds later (outside the 2s window)
        event2 = make_buffered_event(
            camera_id="cam2",
            timestamp=now + timedelta(seconds=15)
        )

        candidates = correlation_service.find_correlation_candidates(event2)

        assert len(candidates) == 0

    def test_same_camera_events_never_correlate(self, correlation_service):
        """AC2: Events from same camera never correlate."""
        now = datetime.now(timezone.utc)

        # Add first event from cam1
        event1 = make_buffered_event(camera_id="cam1", timestamp=now)
        correlation_service._buffer.append((now, event1))

        # Find candidates for another event from cam1
        event2 = make_buffered_event(
            camera_id="cam1",  # Same camera!
            timestamp=now + timedelta(seconds=2)
        )

        candidates = correlation_service.find_correlation_candidates(event2)

        assert len(candidates) == 0

    def test_same_detection_type_correlates(self, correlation_service):
        """AC2: Same detection types correlate (person→person)."""
        now = datetime.now(timezone.utc)

        event1 = make_buffered_event(
            camera_id="cam1",
            smart_detection_type="person",
            timestamp=now
        )
        correlation_service._buffer.append((now, event1))

        event2 = make_buffered_event(
            camera_id="cam2",
            smart_detection_type="person",
            timestamp=now + timedelta(seconds=1)
        )

        candidates = correlation_service.find_correlation_candidates(event2)

        assert len(candidates) == 1

    def test_different_detection_types_still_correlate_inside_window(self, correlation_service):
        """Different labels on two cameras still correlate inside the window."""
        now = datetime.now(timezone.utc)

        event1 = make_buffered_event(
            camera_id="cam1",
            smart_detection_type="person",
            timestamp=now
        )
        correlation_service._buffer.append((now, event1))

        event2 = make_buffered_event(
            camera_id="cam2",
            smart_detection_type="vehicle",
            timestamp=now + timedelta(seconds=1)
        )

        candidates = correlation_service.find_correlation_candidates(event2)

        assert len(candidates) == 1
        assert candidates[0].id == event1.id

    def test_null_detection_types_correlate_inside_window(self, correlation_service):
        """Motion events with no smart-detect type still correlate inside the window."""
        now = datetime.now(timezone.utc)

        event1 = make_buffered_event(
            camera_id="cam1",
            smart_detection_type=None,
            timestamp=now
        )
        correlation_service._buffer.append((now, event1))

        event2 = make_buffered_event(
            camera_id="cam2",
            smart_detection_type=None,
            timestamp=now + timedelta(seconds=1)
        )

        candidates = correlation_service.find_correlation_candidates(event2)

        assert len(candidates) == 1
        assert candidates[0].id == event1.id


# ============================================================================
# Unit Tests: Group ID Generation (AC3, AC4, AC7, AC8)
# ============================================================================

class TestCorrelationGroupDetermination:
    """Tests for correlation group ID determination (AC3, AC4, AC7, AC8)."""

    def test_first_event_gets_new_group_id(self, correlation_service):
        """AC3: First event in group gets new UUID."""
        event = make_buffered_event()
        candidate = make_buffered_event(camera_id="cam2")  # No group_id

        group_id, event_ids = correlation_service.determine_correlation_group(
            event, [candidate]
        )

        assert group_id is not None
        assert len(group_id) == 36  # UUID format
        assert len(event_ids) == 2
        assert event.id in event_ids
        assert candidate.id in event_ids

    def test_joins_existing_group(self, correlation_service):
        """AC7: New event joins existing correlation group."""
        existing_group = str(uuid.uuid4())
        event = make_buffered_event()
        candidate = make_buffered_event(
            camera_id="cam2",
            correlation_group_id=existing_group
        )

        group_id, event_ids = correlation_service.determine_correlation_group(
            event, [candidate]
        )

        assert group_id == existing_group
        assert len(event_ids) == 2

    def test_correlated_event_ids_contains_all_events(self, correlation_service):
        """AC4: correlated_event_ids contains all event IDs in group."""
        event = make_buffered_event(event_id="event-1")
        candidates = [
            make_buffered_event(camera_id="cam2", event_id="event-2"),
            make_buffered_event(camera_id="cam3", event_id="event-3"),
        ]

        group_id, event_ids = correlation_service.determine_correlation_group(
            event, candidates
        )

        assert len(event_ids) == 3
        assert "event-1" in event_ids
        assert "event-2" in event_ids
        assert "event-3" in event_ids

    def test_simultaneous_events_same_group(self, correlation_service):
        """AC8: Simultaneous events get same group ID."""
        now = datetime.now(timezone.utc)

        event_a = make_buffered_event(camera_id="cam1", timestamp=now)
        event_b = make_buffered_event(camera_id="cam2", timestamp=now)

        # Process A first
        correlation_service._buffer.append((now, event_a))

        # B finds A as candidate
        candidates = correlation_service.find_correlation_candidates(event_b)
        assert len(candidates) == 1

        group_id, event_ids = correlation_service.determine_correlation_group(
            event_b, candidates
        )

        # Both should be in same group
        assert event_a.id in event_ids
        assert event_b.id in event_ids


# ============================================================================
# Unit Tests: Buffer Update (AC7)
# ============================================================================

class TestBufferUpdate:
    """Tests for updating buffer with correlation info."""

    def test_update_buffer_with_correlation(self, correlation_service):
        """Buffer event is updated with group ID."""
        event = make_mock_event()
        buffered = correlation_service.add_to_buffer(event)
        group_id = str(uuid.uuid4())

        correlation_service.update_buffer_with_correlation(event.id, group_id)

        # Find the buffered event and check group_id
        for _, b in correlation_service._buffer:
            if b.id == event.id:
                assert b.correlation_group_id == group_id
                return
        pytest.fail("Buffered event not found")


# ============================================================================
# Integration Tests: Full Correlation Flow (AC1, AC6)
# ============================================================================

class TestProcessEvent:
    """Tests for process_event integration (AC1, AC6)."""

    @pytest.mark.asyncio
    async def test_process_event_no_correlation(self, correlation_service):
        """Event with no candidates returns None."""
        event = make_mock_event()

        with patch.object(correlation_service, 'update_correlation_in_db', new_callable=AsyncMock):
            result = await correlation_service.process_event(event)

        assert result is None

    @pytest.mark.asyncio
    async def test_process_event_with_correlation(self, correlation_service):
        """Event with candidates is correlated."""
        now = datetime.now(timezone.utc)

        # Add first event to buffer
        event1 = make_mock_event(camera_id="cam1", timestamp=now)
        correlation_service.add_to_buffer(event1)

        # Process second event
        event2 = make_mock_event(
            camera_id="cam2",
            timestamp=now + timedelta(seconds=1)
        )

        with patch.object(correlation_service, 'update_correlation_in_db', new_callable=AsyncMock) as mock_update:
            mock_update.return_value = 2
            result = await correlation_service.process_event(event2)

        assert result is not None  # Returns group_id
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_correlation_error_doesnt_raise(self, correlation_service):
        """Correlation errors are caught and logged, not raised."""
        event = make_mock_event()

        # Corrupt the buffer to cause an error
        correlation_service._buffer = None

        # Should not raise, just return None
        result = await correlation_service.process_event(event)
        assert result is None


# ============================================================================
# Performance Tests (AC5)
# ============================================================================

class TestPerformance:
    """Performance tests for correlation service (AC5)."""

    def test_buffer_operations_under_10ms(self, correlation_service):
        """AC5: Buffer operations complete in under 10ms for 1000 events."""
        now = datetime.now(timezone.utc)

        # Add 1000 events from different cameras
        for i in range(1000):
            event = make_buffered_event(
                camera_id=f"cam{i % 10}",  # 10 different cameras
                timestamp=now + timedelta(milliseconds=i * 50),  # Spread over 50 seconds
                event_id=f"event-{i}"
            )
            correlation_service._buffer.append((event.timestamp, event))

        # Measure find_candidates time
        test_event = make_buffered_event(
            camera_id="cam-test",
            timestamp=now + timedelta(seconds=25)
        )

        start = time.perf_counter()
        candidates = correlation_service.find_correlation_candidates(test_event)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Should complete in under 10ms
        assert elapsed_ms < 10, f"find_correlation_candidates took {elapsed_ms:.2f}ms (expected < 10ms)"


# ============================================================================
# Singleton Tests
# ============================================================================

class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_correlation_service_returns_singleton(self):
        """get_correlation_service returns same instance."""
        service1 = get_correlation_service()
        service2 = get_correlation_service()

        assert service1 is service2
        assert DEFAULT_TIME_WINDOW_SECONDS == 2
        assert service1.time_window_seconds == 2

    def test_reset_clears_singleton(self):
        """reset_correlation_service creates new instance."""
        service1 = get_correlation_service()
        reset_correlation_service()
        service2 = get_correlation_service()

        assert service1 is not service2
