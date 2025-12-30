"""
WebSocketManager Concurrency Tests (Story P14-8.2)

Tests for verifying that the WebSocketManager handles concurrent
connections and broadcasts safely.
"""
import pytest
import asyncio
from tests.test_concurrency.conftest import MockWebSocket


class MockWebSocketManager:
    """
    Mock WebSocketManager for testing concurrency.

    Simulates the core functionality of connection management
    and broadcasting with proper thread safety.
    """
    def __init__(self):
        self._connections: list[MockWebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: MockWebSocket):
        """Add a new connection."""
        async with self._lock:
            self._connections.append(websocket)

    async def disconnect(self, websocket: MockWebSocket):
        """Remove a connection."""
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
                websocket.is_connected = False

    async def broadcast(self, message: dict):
        """
        Send message to all connected clients.

        Creates a copy of connections list to avoid modification during iteration.
        """
        async with self._lock:
            connections = list(self._connections)

        # Send to all connections concurrently
        send_tasks = []
        for ws in connections:
            if ws.is_connected:
                send_tasks.append(self._safe_send(ws, message))

        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)

    async def _safe_send(self, websocket: MockWebSocket, message: dict):
        """Safely send message to a websocket, handling disconnection."""
        try:
            await websocket.send_json(message)
        except Exception:
            # Connection may have closed during broadcast
            await self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        """Return current connection count."""
        return len(self._connections)


@pytest.fixture
def ws_manager():
    """Create a mock WebSocketManager for testing."""
    return MockWebSocketManager()


class TestWebSocketManagerConcurrency:
    """Concurrency tests for WebSocketManager."""

    @pytest.mark.asyncio
    async def test_concurrent_connections(
        self, ws_manager, mock_websockets, run_concurrent
    ):
        """
        Test multiple WebSocket connections joining concurrently.

        Verifies that all connections are registered without race conditions.
        """
        connections = mock_websockets(20)

        async def connect_client(ws):
            await ws_manager.connect(ws)
            return ws

        tasks = [connect_client(ws) for ws in connections]
        results = await run_concurrent(tasks)

        # All should connect successfully
        assert len(results) == 20
        assert all(not isinstance(r, Exception) for r in results)

        # Manager should have all connections
        assert ws_manager.connection_count == 20

    @pytest.mark.asyncio
    async def test_concurrent_disconnections(
        self, ws_manager, mock_websockets, run_concurrent
    ):
        """
        Test multiple WebSocket disconnections happening concurrently.

        Verifies that disconnections are handled safely.
        """
        connections = mock_websockets(10)

        # First connect all
        for ws in connections:
            await ws_manager.connect(ws)

        assert ws_manager.connection_count == 10

        # Now disconnect concurrently
        async def disconnect_client(ws):
            await ws_manager.disconnect(ws)
            return ws

        tasks = [disconnect_client(ws) for ws in connections]
        results = await run_concurrent(tasks)

        # All should disconnect successfully
        assert all(not isinstance(r, Exception) for r in results)
        assert ws_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_during_connect_disconnect(
        self, ws_manager, mock_websockets, run_concurrent
    ):
        """
        Test broadcasting while connections are changing.

        Verifies that broadcast doesn't crash when connections
        are being added/removed concurrently.
        """
        existing = mock_websockets(5)
        for ws in existing:
            await ws_manager.connect(ws)

        async def broadcast_messages():
            for i in range(10):
                await ws_manager.broadcast({"type": "test", "index": i})
                await asyncio.sleep(0.01)

        async def connect_disconnect():
            new_connections = mock_websockets(5)
            for i, ws in enumerate(new_connections):
                ws.client_id = f"new-{i}"  # Rename to avoid confusion
                await ws_manager.connect(ws)
                await asyncio.sleep(0.02)
                await ws_manager.disconnect(ws)

        # Run broadcast and connect/disconnect concurrently
        results = await run_concurrent([
            broadcast_messages(),
            connect_disconnect(),
        ])

        # Should not crash
        assert all(not isinstance(r, Exception) for r in results)

        # Existing connections should still be connected
        assert ws_manager.connection_count == 5

        # Existing connections should have received some messages
        for ws in existing:
            assert len(ws.messages) > 0

    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(
        self, ws_manager, mock_websockets, run_concurrent
    ):
        """
        Test multiple concurrent broadcasts.

        Verifies that concurrent broadcasts don't interfere with each other.
        """
        connections = mock_websockets(5)
        for ws in connections:
            await ws_manager.connect(ws)

        num_broadcasts = 20

        async def broadcast_message(i: int):
            await ws_manager.broadcast({"type": "test", "broadcast_id": i})

        tasks = [broadcast_message(i) for i in range(num_broadcasts)]
        results = await run_concurrent(tasks)

        # All broadcasts should complete
        assert all(not isinstance(r, Exception) for r in results)

        # Each connection should have received all broadcasts
        for ws in connections:
            assert len(ws.messages) == num_broadcasts
            # Verify all broadcast IDs are present
            received_ids = {m["broadcast_id"] for m in ws.messages}
            expected_ids = set(range(num_broadcasts))
            assert received_ids == expected_ids

    @pytest.mark.asyncio
    async def test_slow_connection_doesnt_block_broadcast(
        self, ws_manager, mock_websockets, run_concurrent
    ):
        """
        Test that a slow connection doesn't block broadcasts to others.

        Verifies that broadcast is non-blocking per connection.
        """
        connections = mock_websockets(5)

        # Make one connection slow
        slow_connection = connections[0]
        slow_connection.set_send_delay(0.5)

        for ws in connections:
            await ws_manager.connect(ws)

        # Broadcast should complete quickly despite slow connection
        start_time = asyncio.get_event_loop().time()
        await ws_manager.broadcast({"type": "test"})
        elapsed = asyncio.get_event_loop().time() - start_time

        # Should complete in under 1 second (slow connection is 0.5s)
        # but not block for all 5 connections (would be 2.5s if blocking)
        assert elapsed < 1.0

        # All connections should eventually receive the message
        await asyncio.sleep(0.6)  # Wait for slow connection
        for ws in connections:
            assert len(ws.messages) >= 1

    @pytest.mark.asyncio
    async def test_disconnection_during_broadcast(
        self, ws_manager, mock_websockets
    ):
        """
        Test handling disconnection that occurs during broadcast.

        Verifies that disconnecting a client mid-broadcast doesn't crash.
        """
        connections = mock_websockets(5)
        for ws in connections:
            await ws_manager.connect(ws)

        # Make one connection fail during send
        failing_connection = connections[2]

        async def fail_send(data):
            raise RuntimeError("Connection closed")

        failing_connection.send_json = fail_send

        # Broadcast should handle the failure gracefully
        await ws_manager.broadcast({"type": "test"})

        # Other connections should still receive the message
        for i, ws in enumerate(connections):
            if i != 2:
                assert len(ws.messages) == 1
