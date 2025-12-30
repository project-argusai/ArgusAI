"""
Concurrency Test Fixtures (Story P14-8.2)

Provides helper fixtures for running concurrent async operations
and testing thread safety.
"""
import asyncio
import pytest
from typing import List, Any, Callable, Coroutine
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def run_concurrent():
    """
    Helper fixture to run multiple async tasks concurrently.

    Usage:
        results = await run_concurrent([task1(), task2(), task3()])

    Returns list of results or exceptions for each task.
    """
    async def _run_concurrent(
        tasks: List[Coroutine],
        timeout: float = 10.0
    ) -> List[Any]:
        """
        Run multiple coroutines concurrently with timeout.

        Args:
            tasks: List of coroutines to run
            timeout: Maximum time to wait for all tasks

        Returns:
            List of results (or exceptions) for each task
        """
        return await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout
        )
    return _run_concurrent


class MockWebSocket:
    """
    Mock WebSocket connection for testing WebSocketManager.

    Simulates a WebSocket connection with async send capability
    and connection state tracking.
    """
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.messages: List[dict] = []
        self.is_connected = True
        self._send_delay = 0.0

    async def send_json(self, data: dict):
        """Send JSON data to this connection."""
        if not self.is_connected:
            raise RuntimeError(f"Connection {self.client_id} is closed")
        if self._send_delay > 0:
            await asyncio.sleep(self._send_delay)
        self.messages.append(data)

    async def close(self):
        """Close the connection."""
        self.is_connected = False

    def set_send_delay(self, delay: float):
        """Set artificial delay for send operations."""
        self._send_delay = delay


@pytest.fixture
def mock_websocket():
    """Factory fixture to create MockWebSocket instances."""
    def _create(client_id: str) -> MockWebSocket:
        return MockWebSocket(client_id)
    return _create


@pytest.fixture
def mock_websockets(mock_websocket):
    """Create multiple mock WebSocket connections."""
    def _create(count: int) -> List[MockWebSocket]:
        return [mock_websocket(f"client-{i}") for i in range(count)]
    return _create


class MockEventProcessor:
    """
    Mock EventProcessor for concurrency testing.

    Simulates event processing with configurable delays
    to test concurrent access patterns.
    """
    def __init__(self):
        self.processed_events: List[dict] = []
        self._lock = asyncio.Lock()
        self._event_counter = 0
        self._processing_delay = 0.01

    async def process(self, event: dict) -> dict:
        """
        Process an event with simulated delay.

        Uses a lock to safely increment the event counter,
        simulating real database ID generation.
        """
        async with self._lock:
            self._event_counter += 1
            event_id = f"event-{self._event_counter}"

        # Simulate processing time outside the lock
        await asyncio.sleep(self._processing_delay)

        processed = {
            "id": event_id,
            **event,
            "processed": True
        }

        async with self._lock:
            self.processed_events.append(processed)

        return processed

    def set_processing_delay(self, delay: float):
        """Set artificial delay for event processing."""
        self._processing_delay = delay


@pytest.fixture
def mock_event_processor():
    """Create a mock event processor for testing."""
    return MockEventProcessor()


class MockCache:
    """
    Mock cache for testing concurrent access patterns.

    Simulates a cache with read/write operations that have
    configurable delays to test race conditions.
    """
    def __init__(self):
        self._cache: dict = {}
        self._lock = asyncio.Lock()
        self._read_delay = 0.01
        self._write_delay = 0.02
        self.read_count = 0
        self.write_count = 0
        self.cache_hits = 0
        self.cache_misses = 0

    async def get(self, key: str) -> Any:
        """Get value from cache with simulated delay."""
        await asyncio.sleep(self._read_delay)

        async with self._lock:
            self.read_count += 1
            if key in self._cache:
                self.cache_hits += 1
                return self._cache[key]
            else:
                self.cache_misses += 1
                return None

    async def set(self, key: str, value: Any):
        """Set value in cache with simulated delay."""
        await asyncio.sleep(self._write_delay)

        async with self._lock:
            self.write_count += 1
            self._cache[key] = value

    async def get_or_compute(self, key: str, compute_fn: Callable) -> Any:
        """
        Get value from cache or compute if missing.

        This is the typical pattern for cache usage that
        can have race conditions.
        """
        value = await self.get(key)
        if value is None:
            value = await compute_fn()
            await self.set(key, value)
        return value

    def set_delays(self, read_delay: float, write_delay: float):
        """Set artificial delays for cache operations."""
        self._read_delay = read_delay
        self._write_delay = write_delay


@pytest.fixture
def mock_cache():
    """Create a mock cache for testing."""
    return MockCache()


@pytest.fixture
def event_loop():
    """
    Create event loop for async tests.

    Uses the default policy to create a new event loop for each test.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
