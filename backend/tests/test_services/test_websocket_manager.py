"""
Unit tests for WebSocketManager (Story P14-3.5)

Tests WebSocket connection lifecycle, message broadcasting, error handling,
and connection cleanup for the real-time update delivery system.
"""
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.websocket_manager import (
    WebSocketManager,
    websocket_manager,
    get_websocket_manager,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def ws_manager():
    """Create a fresh WebSocketManager instance for each test."""
    return WebSocketManager()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket with async methods."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.fixture
def mock_websocket_factory():
    """Factory to create multiple unique mock WebSockets."""
    def _create():
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        return ws
    return _create


# =============================================================================
# WebSocketManager Initialization Tests
# =============================================================================


class TestWebSocketManagerInit:
    """Tests for WebSocketManager initialization."""

    def test_websocket_manager_init(self):
        """Test WebSocketManager initializes with empty connection set."""
        manager = WebSocketManager()

        assert manager.active_connections == set()
        assert manager._lock is not None

    def test_get_websocket_manager_returns_singleton(self):
        """Test get_websocket_manager returns the global singleton."""
        manager = get_websocket_manager()

        assert manager is websocket_manager
        assert isinstance(manager, WebSocketManager)


# =============================================================================
# Connection Lifecycle Tests
# =============================================================================


class TestConnect:
    """Tests for connect() method."""

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self, ws_manager, mock_websocket):
        """Test connect() calls accept() on the websocket."""
        await ws_manager.connect(mock_websocket)

        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_adds_to_active_connections(self, ws_manager, mock_websocket):
        """Test connect() adds websocket to active_connections set."""
        await ws_manager.connect(mock_websocket)

        assert mock_websocket in ws_manager.active_connections
        assert len(ws_manager.active_connections) == 1

    @pytest.mark.asyncio
    async def test_connect_multiple_websockets(self, ws_manager, mock_websocket_factory):
        """Test multiple connections are tracked separately."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()
        ws3 = mock_websocket_factory()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)
        await ws_manager.connect(ws3)

        assert len(ws_manager.active_connections) == 3
        assert ws1 in ws_manager.active_connections
        assert ws2 in ws_manager.active_connections
        assert ws3 in ws_manager.active_connections


class TestDisconnect:
    """Tests for disconnect() method."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_active_connections(
        self, ws_manager, mock_websocket
    ):
        """Test disconnect() removes websocket from active_connections."""
        await ws_manager.connect(mock_websocket)
        assert mock_websocket in ws_manager.active_connections

        await ws_manager.disconnect(mock_websocket)

        assert mock_websocket not in ws_manager.active_connections
        assert len(ws_manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_websocket(self, ws_manager, mock_websocket):
        """Test disconnect() handles non-existent websocket gracefully."""
        # Should not raise any errors
        await ws_manager.disconnect(mock_websocket)

        assert len(ws_manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_disconnect_reduces_count(self, ws_manager, mock_websocket_factory):
        """Test disconnect reduces connection count correctly."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)
        assert ws_manager.get_connection_count() == 2

        await ws_manager.disconnect(ws1)
        assert ws_manager.get_connection_count() == 1

        await ws_manager.disconnect(ws2)
        assert ws_manager.get_connection_count() == 0


# =============================================================================
# Broadcast Tests
# =============================================================================


class TestBroadcast:
    """Tests for broadcast() method."""

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self, ws_manager):
        """Test broadcast with no connections returns 0."""
        result = await ws_manager.broadcast({"type": "test"})

        assert result == 0

    @pytest.mark.asyncio
    async def test_broadcast_single_connection(self, ws_manager, mock_websocket):
        """Test broadcast to single connection sends message and returns 1."""
        await ws_manager.connect(mock_websocket)

        result = await ws_manager.broadcast({"type": "TEST", "data": "hello"})

        assert result == 1
        mock_websocket.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_multiple_connections(
        self, ws_manager, mock_websocket_factory
    ):
        """Test broadcast sends to all connections."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()
        ws3 = mock_websocket_factory()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)
        await ws_manager.connect(ws3)

        result = await ws_manager.broadcast({"type": "TEST"})

        assert result == 3
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
        ws3.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_adds_timestamp(self, ws_manager, mock_websocket):
        """Test broadcast adds ISO timestamp to message."""
        await ws_manager.connect(mock_websocket)

        await ws_manager.broadcast({"type": "TEST"})

        # Get the sent message
        call_args = mock_websocket.send_text.call_args
        sent_json = call_args[0][0]
        sent_message = json.loads(sent_json)

        assert "timestamp" in sent_message
        # Verify it's a valid ISO timestamp
        datetime.fromisoformat(sent_message["timestamp"].replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_broadcast_json_serialization(self, ws_manager, mock_websocket):
        """Test broadcast serializes message as JSON."""
        await ws_manager.connect(mock_websocket)
        original_message = {"type": "EVENT", "data": {"id": 123, "name": "test"}}

        await ws_manager.broadcast(original_message)

        call_args = mock_websocket.send_text.call_args
        sent_json = call_args[0][0]
        sent_message = json.loads(sent_json)

        assert sent_message["type"] == "EVENT"
        assert sent_message["data"]["id"] == 123
        assert sent_message["data"]["name"] == "test"

    @pytest.mark.asyncio
    async def test_broadcast_failed_connection_removed(
        self, ws_manager, mock_websocket_factory
    ):
        """Test that failed send removes connection from pool."""
        good_ws = mock_websocket_factory()
        bad_ws = mock_websocket_factory()
        bad_ws.send_text = AsyncMock(side_effect=Exception("Connection closed"))

        await ws_manager.connect(good_ws)
        await ws_manager.connect(bad_ws)
        assert ws_manager.get_connection_count() == 2

        result = await ws_manager.broadcast({"type": "test"})

        assert result == 1  # Only good connection succeeded
        assert good_ws in ws_manager.active_connections
        assert bad_ws not in ws_manager.active_connections
        assert ws_manager.get_connection_count() == 1

    @pytest.mark.asyncio
    async def test_broadcast_partial_failure(self, ws_manager, mock_websocket_factory):
        """Test broadcast returns count of successful sends on partial failure."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()
        ws2.send_text = AsyncMock(side_effect=Exception("Failed"))
        ws3 = mock_websocket_factory()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)
        await ws_manager.connect(ws3)

        result = await ws_manager.broadcast({"type": "test"})

        assert result == 2  # 2 out of 3 succeeded
        assert ws_manager.get_connection_count() == 2

    @pytest.mark.asyncio
    async def test_broadcast_all_fail(self, ws_manager, mock_websocket_factory):
        """Test broadcast when all connections fail."""
        ws1 = mock_websocket_factory()
        ws1.send_text = AsyncMock(side_effect=Exception("Failed 1"))
        ws2 = mock_websocket_factory()
        ws2.send_text = AsyncMock(side_effect=Exception("Failed 2"))

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)

        result = await ws_manager.broadcast({"type": "test"})

        assert result == 0
        assert ws_manager.get_connection_count() == 0


# =============================================================================
# Broadcast Alert Tests
# =============================================================================


class TestBroadcastAlert:
    """Tests for broadcast_alert() convenience method."""

    @pytest.mark.asyncio
    async def test_broadcast_alert_message_format(self, ws_manager, mock_websocket):
        """Test broadcast_alert creates correct message structure."""
        await ws_manager.connect(mock_websocket)
        event_data = {"id": "evt-123", "description": "Person detected"}
        rule_data = {"id": "rule-456", "name": "Motion Alert"}

        await ws_manager.broadcast_alert(event_data, rule_data)

        call_args = mock_websocket.send_text.call_args
        sent_message = json.loads(call_args[0][0])

        assert sent_message["type"] == "ALERT_TRIGGERED"
        assert sent_message["data"]["event"] == event_data
        assert sent_message["data"]["rule"] == rule_data
        assert "timestamp" in sent_message

    @pytest.mark.asyncio
    async def test_broadcast_alert_returns_count(
        self, ws_manager, mock_websocket_factory
    ):
        """Test broadcast_alert returns number of clients notified."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)

        result = await ws_manager.broadcast_alert(
            {"id": "evt-1"},
            {"id": "rule-1"}
        )

        assert result == 2

    @pytest.mark.asyncio
    async def test_broadcast_alert_no_connections(self, ws_manager):
        """Test broadcast_alert with no connections returns 0."""
        result = await ws_manager.broadcast_alert(
            {"id": "evt-1"},
            {"id": "rule-1"}
        )

        assert result == 0


# =============================================================================
# Connection Count Tests
# =============================================================================


class TestGetConnectionCount:
    """Tests for get_connection_count() method."""

    def test_get_connection_count_empty(self, ws_manager):
        """Test get_connection_count returns 0 with no connections."""
        assert ws_manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_get_connection_count_after_connects(
        self, ws_manager, mock_websocket_factory
    ):
        """Test get_connection_count returns correct count after connects."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1)
        assert ws_manager.get_connection_count() == 1

        await ws_manager.connect(ws2)
        assert ws_manager.get_connection_count() == 2

    @pytest.mark.asyncio
    async def test_get_connection_count_after_disconnect(
        self, ws_manager, mock_websocket_factory
    ):
        """Test get_connection_count decrements after disconnect."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)
        assert ws_manager.get_connection_count() == 2

        await ws_manager.disconnect(ws1)
        assert ws_manager.get_connection_count() == 1


# =============================================================================
# Concurrency Tests
# =============================================================================


class TestConcurrency:
    """Tests for thread-safety and concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_connects(self, ws_manager, mock_websocket_factory):
        """Test multiple simultaneous connects are handled correctly."""
        websockets = [mock_websocket_factory() for _ in range(10)]

        # Connect all websockets concurrently
        await asyncio.gather(*[ws_manager.connect(ws) for ws in websockets])

        assert ws_manager.get_connection_count() == 10
        for ws in websockets:
            assert ws in ws_manager.active_connections

    @pytest.mark.asyncio
    async def test_concurrent_disconnects(self, ws_manager, mock_websocket_factory):
        """Test multiple simultaneous disconnects are handled correctly."""
        websockets = [mock_websocket_factory() for _ in range(10)]

        # Connect all websockets
        for ws in websockets:
            await ws_manager.connect(ws)

        # Disconnect all concurrently
        await asyncio.gather(*[ws_manager.disconnect(ws) for ws in websockets])

        assert ws_manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(self, ws_manager, mock_websocket_factory):
        """Test concurrent broadcasts don't interfere with each other."""
        websockets = [mock_websocket_factory() for _ in range(5)]
        for ws in websockets:
            await ws_manager.connect(ws)

        # Send multiple broadcasts concurrently
        results = await asyncio.gather(*[
            ws_manager.broadcast({"type": f"TEST_{i}", "num": i})
            for i in range(10)
        ])

        # All broadcasts should succeed to all connections
        assert all(r == 5 for r in results)

        # Each websocket should have received 10 messages
        for ws in websockets:
            assert ws.send_text.call_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_connect_and_broadcast(
        self, ws_manager, mock_websocket_factory
    ):
        """Test connect and broadcast can happen concurrently without deadlock."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1)

        # Run connect and broadcast concurrently
        async def connect_task():
            await ws_manager.connect(ws2)

        async def broadcast_task():
            return await ws_manager.broadcast({"type": "TEST"})

        await asyncio.gather(connect_task(), broadcast_task())

        # Both operations should complete
        assert ws_manager.get_connection_count() == 2


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_broadcast_with_complex_data(self, ws_manager, mock_websocket):
        """Test broadcast handles complex nested data structures."""
        await ws_manager.connect(mock_websocket)

        complex_message = {
            "type": "COMPLEX",
            "data": {
                "nested": {
                    "level1": {
                        "level2": [1, 2, 3]
                    }
                },
                "list": [{"a": 1}, {"b": 2}],
                "number": 42,
                "float": 3.14,
                "boolean": True,
                "null": None,
            }
        }

        result = await ws_manager.broadcast(complex_message)

        assert result == 1
        call_args = mock_websocket.send_text.call_args
        sent_message = json.loads(call_args[0][0])
        assert sent_message["data"]["nested"]["level1"]["level2"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_broadcast_preserves_message_type(self, ws_manager, mock_websocket):
        """Test broadcast preserves original message type."""
        await ws_manager.connect(mock_websocket)

        for msg_type in ["NEW_EVENT", "ALERT_TRIGGERED", "CAMERA_STATUS", "SYSTEM"]:
            await ws_manager.broadcast({"type": msg_type})
            call_args = mock_websocket.send_text.call_args
            sent_message = json.loads(call_args[0][0])
            assert sent_message["type"] == msg_type

    @pytest.mark.asyncio
    async def test_same_websocket_connect_twice(self, ws_manager, mock_websocket):
        """Test connecting same websocket twice doesn't duplicate."""
        await ws_manager.connect(mock_websocket)
        # Second connect - sets don't allow duplicates
        await ws_manager.connect(mock_websocket)

        # accept() should still be called twice (as per implementation)
        assert mock_websocket.accept.call_count == 2
        # But connection should only be in set once (set behavior)
        assert ws_manager.get_connection_count() == 1

    @pytest.mark.asyncio
    async def test_broadcast_empty_message(self, ws_manager, mock_websocket):
        """Test broadcast handles empty message dict."""
        await ws_manager.connect(mock_websocket)

        result = await ws_manager.broadcast({})

        assert result == 1
        call_args = mock_websocket.send_text.call_args
        sent_message = json.loads(call_args[0][0])
        assert "timestamp" in sent_message


# =============================================================================
# Integration-Style Tests
# =============================================================================


class TestIntegrationScenarios:
    """Integration-style tests for typical usage patterns."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, ws_manager, mock_websocket_factory):
        """Test full connection lifecycle: connect, broadcast, disconnect."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        # Connect
        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)
        assert ws_manager.get_connection_count() == 2

        # Broadcast
        result = await ws_manager.broadcast({"type": "HELLO"})
        assert result == 2

        # One disconnects
        await ws_manager.disconnect(ws1)
        assert ws_manager.get_connection_count() == 1

        # Broadcast again
        result = await ws_manager.broadcast({"type": "GOODBYE"})
        assert result == 1

        # Clean up
        await ws_manager.disconnect(ws2)
        assert ws_manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_connection_failure_cleanup_during_heavy_broadcast(
        self, ws_manager, mock_websocket_factory
    ):
        """Test connection cleanup during heavy broadcast load."""
        # Create 5 good and 5 bad connections
        good_websockets = [mock_websocket_factory() for _ in range(5)]
        bad_websockets = []
        for _ in range(5):
            bad_ws = mock_websocket_factory()
            bad_ws.send_text = AsyncMock(side_effect=Exception("Dead connection"))
            bad_websockets.append(bad_ws)

        # Connect all
        for ws in good_websockets + bad_websockets:
            await ws_manager.connect(ws)
        assert ws_manager.get_connection_count() == 10

        # Broadcast - bad connections should be cleaned up
        result = await ws_manager.broadcast({"type": "TEST"})

        assert result == 5  # Only good ones succeeded
        assert ws_manager.get_connection_count() == 5

        # Subsequent broadcast should only go to good connections
        result = await ws_manager.broadcast({"type": "TEST2"})
        assert result == 5
