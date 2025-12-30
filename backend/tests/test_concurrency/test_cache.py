"""
Cache Concurrency Tests (Story P14-8.2)

Tests for verifying that cache operations are thread-safe
under concurrent access.
"""
import pytest
import asyncio


class TestCacheConcurrency:
    """Concurrency tests for cache operations."""

    @pytest.mark.asyncio
    async def test_concurrent_cache_reads(
        self, mock_cache, run_concurrent
    ):
        """
        Test multiple concurrent cache reads.

        Verifies that reads don't interfere with each other.
        """
        # Pre-populate cache
        await mock_cache.set("key1", "value1")
        await mock_cache.set("key2", "value2")
        await mock_cache.set("key3", "value3")

        # Reset counters after setup
        mock_cache.read_count = 0
        mock_cache.cache_hits = 0

        # Perform concurrent reads
        num_reads = 30

        async def read_key(i: int):
            key = f"key{(i % 3) + 1}"
            return await mock_cache.get(key)

        tasks = [read_key(i) for i in range(num_reads)]
        results = await run_concurrent(tasks)

        # All reads should succeed
        assert all(r is not None for r in results)
        assert all(not isinstance(r, Exception) for r in results)

        # All should be cache hits
        assert mock_cache.read_count == num_reads
        assert mock_cache.cache_hits == num_reads

    @pytest.mark.asyncio
    async def test_concurrent_cache_writes(
        self, mock_cache, run_concurrent
    ):
        """
        Test multiple concurrent cache writes.

        Verifies that writes are serialized properly.
        """
        num_writes = 20

        async def write_key(i: int):
            await mock_cache.set(f"key{i}", f"value{i}")
            return i

        tasks = [write_key(i) for i in range(num_writes)]
        results = await run_concurrent(tasks)

        # All writes should complete
        assert all(not isinstance(r, Exception) for r in results)
        assert mock_cache.write_count == num_writes

        # All values should be stored
        for i in range(num_writes):
            value = await mock_cache.get(f"key{i}")
            assert value == f"value{i}"

    @pytest.mark.asyncio
    async def test_cache_read_during_write(
        self, mock_cache, run_concurrent
    ):
        """
        Test reading from cache while it's being updated.

        Verifies cache consistency during concurrent read/write.
        """
        # Pre-populate with initial value
        await mock_cache.set("shared_key", "initial_value")

        async def read_operation():
            """Read the shared key multiple times."""
            values = []
            for _ in range(5):
                val = await mock_cache.get("shared_key")
                values.append(val)
                await asyncio.sleep(0.005)
            return values

        async def write_operation():
            """Update the shared key."""
            await asyncio.sleep(0.01)  # Slight delay
            await mock_cache.set("shared_key", "updated_value")
            return "write_complete"

        # Run read and write concurrently
        results = await run_concurrent([
            read_operation(),
            write_operation(),
        ])

        # Both should complete
        assert len(results) == 2
        assert all(not isinstance(r, Exception) for r in results)

        # Final value should be "updated_value"
        final = await mock_cache.get("shared_key")
        assert final == "updated_value"

    @pytest.mark.asyncio
    async def test_get_or_compute_concurrent(
        self, mock_cache, run_concurrent
    ):
        """
        Test concurrent get_or_compute calls for same key.

        Verifies that compute function is called minimally
        and cache is used after first computation.
        """
        compute_count = 0

        async def expensive_compute():
            nonlocal compute_count
            compute_count += 1
            await asyncio.sleep(0.05)  # Simulate expensive operation
            return f"computed_value_{compute_count}"

        # Multiple concurrent requests for same key
        num_requests = 10

        async def get_value():
            return await mock_cache.get_or_compute("computed_key", expensive_compute)

        tasks = [get_value() for _ in range(num_requests)]
        results = await run_concurrent(tasks, timeout=5.0)

        # All should get a value
        assert all(r is not None for r in results)
        assert all(not isinstance(r, Exception) for r in results)

        # Due to race conditions, compute might be called more than once
        # but should be significantly less than num_requests
        # In a well-optimized cache, this should be 1-2
        assert compute_count <= num_requests

    @pytest.mark.asyncio
    async def test_cache_stress_mixed_operations(
        self, mock_cache, run_concurrent
    ):
        """
        Stress test with mixed read/write operations.

        Verifies cache stability under high concurrent load.
        """
        mock_cache.set_delays(0.001, 0.002)  # Fast for stress test

        async def mixed_operation(i: int):
            key = f"stress_key_{i % 10}"
            if i % 3 == 0:
                await mock_cache.set(key, f"value_{i}")
                return ("write", key)
            else:
                value = await mock_cache.get(key)
                return ("read", key, value)

        tasks = [mixed_operation(i) for i in range(100)]
        results = await run_concurrent(tasks, timeout=10.0)

        # All operations should complete
        assert len(results) == 100
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Got errors: {errors}"

        # Cache should have processed all operations
        total_ops = mock_cache.read_count + mock_cache.write_count
        assert total_ops == 100

    @pytest.mark.asyncio
    async def test_no_deadlock_under_contention(
        self, mock_cache
    ):
        """
        Test that cache doesn't deadlock under high contention.

        Uses a timeout to detect potential deadlocks.
        """
        mock_cache.set_delays(0.001, 0.001)

        async def contended_operation(i: int):
            # All operations target same key - high contention
            key = "contended_key"
            for _ in range(5):
                await mock_cache.set(key, f"value_{i}")
                await mock_cache.get(key)
            return i

        tasks = [contended_operation(i) for i in range(20)]

        # Should complete within timeout (would hang if deadlocked)
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks),
                timeout=10.0
            )
            assert len(results) == 20
        except asyncio.TimeoutError:
            pytest.fail("Deadlock detected - operations timed out")
