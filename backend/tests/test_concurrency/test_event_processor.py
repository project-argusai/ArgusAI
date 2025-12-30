"""
EventProcessor Concurrency Tests (Story P14-8.2)

Tests for verifying that the EventProcessor handles concurrent
events without race conditions.
"""
import pytest
import asyncio
from datetime import datetime, timezone


class TestEventProcessorConcurrency:
    """Concurrency tests for EventProcessor."""

    @pytest.mark.asyncio
    async def test_concurrent_events_same_camera(
        self, mock_event_processor, run_concurrent
    ):
        """
        Test processing multiple events from same camera concurrently.

        Verifies that all events get unique IDs and none are lost.
        """
        camera_id = "test-camera-1"
        num_events = 10

        async def process_event(i: int):
            event = {
                "camera_id": camera_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "description": f"Event {i}",
            }
            return await mock_event_processor.process(event)

        # Process events concurrently
        tasks = [process_event(i) for i in range(num_events)]
        results = await run_concurrent(tasks)

        # All should succeed without race conditions
        assert all(r is not None for r in results)
        assert all(not isinstance(r, Exception) for r in results)

        # All should have unique IDs
        event_ids = [r["id"] for r in results]
        assert len(set(event_ids)) == num_events, "All events should have unique IDs"

        # All should be processed
        assert len(mock_event_processor.processed_events) == num_events

    @pytest.mark.asyncio
    async def test_concurrent_events_different_cameras(
        self, mock_event_processor, run_concurrent
    ):
        """
        Test processing events from different cameras concurrently.

        Verifies that events from multiple cameras don't interfere.
        """
        num_cameras = 5
        events_per_camera = 3

        async def process_camera_event(camera_id: str, event_num: int):
            event = {
                "camera_id": camera_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "description": f"Event from camera {camera_id}",
            }
            return await mock_event_processor.process(event)

        # Create tasks for all cameras
        tasks = [
            process_camera_event(f"camera-{c}", e)
            for c in range(num_cameras)
            for e in range(events_per_camera)
        ]

        results = await run_concurrent(tasks)

        # All should succeed
        assert all(r is not None for r in results)
        assert all(not isinstance(r, Exception) for r in results)

        # Total events should match
        expected_total = num_cameras * events_per_camera
        assert len(mock_event_processor.processed_events) == expected_total

    @pytest.mark.asyncio
    async def test_high_concurrency_stress(
        self, mock_event_processor, run_concurrent
    ):
        """
        Stress test with high number of concurrent events.

        Verifies the system handles burst traffic without data loss.
        """
        num_events = 100
        mock_event_processor.set_processing_delay(0.001)  # Faster for stress test

        async def process_event(i: int):
            event = {
                "camera_id": f"camera-{i % 10}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "description": f"Stress event {i}",
            }
            return await mock_event_processor.process(event)

        tasks = [process_event(i) for i in range(num_events)]
        results = await run_concurrent(tasks, timeout=30.0)

        # All should complete
        assert len(results) == num_events

        # Count successful results
        successful = [r for r in results if not isinstance(r, Exception)]
        assert len(successful) == num_events, "All events should succeed"

        # Verify no duplicate IDs
        event_ids = [r["id"] for r in successful]
        assert len(set(event_ids)) == num_events, "No duplicate event IDs"

    @pytest.mark.asyncio
    async def test_sequential_vs_concurrent_consistency(
        self, mock_event_processor
    ):
        """
        Compare sequential and concurrent processing results.

        Verifies that concurrent processing produces consistent results.
        """
        # First, process sequentially
        sequential_results = []
        for i in range(5):
            result = await mock_event_processor.process({
                "camera_id": "test-camera",
                "sequence": i,
            })
            sequential_results.append(result)

        sequential_count = len(mock_event_processor.processed_events)

        # Now process concurrently
        tasks = [
            mock_event_processor.process({
                "camera_id": "test-camera",
                "sequence": i + 100,
            })
            for i in range(5)
        ]
        concurrent_results = await asyncio.gather(*tasks)

        # Total should be sum of both
        total_count = len(mock_event_processor.processed_events)
        assert total_count == sequential_count + 5

        # All results should be valid
        all_results = sequential_results + list(concurrent_results)
        assert all(r["id"] is not None for r in all_results)
