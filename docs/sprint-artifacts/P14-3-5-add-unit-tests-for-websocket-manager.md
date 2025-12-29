# Story P14-3.5: Add Unit Tests for websocket_manager.py

Status: done

## Story

As a **developer**,
I want comprehensive unit tests for the WebSocketManager,
so that real-time update delivery, connection lifecycle, and broadcast logic are regression-tested.

## Acceptance Criteria

1. **AC-1**: Test file `tests/test_services/test_websocket_manager.py` exists with 10+ tests
2. **AC-2**: Line coverage for `websocket_manager.py` reaches minimum 70%
3. **AC-3**: Connection lifecycle tested (`connect()`, `disconnect()`, connection pool management)
4. **AC-4**: Message delivery tested (`broadcast()` sends to all connected clients)
5. **AC-5**: Broadcast message ordering verified (timestamp added, JSON serialization)
6. **AC-6**: Connection cleanup tested (failed sends remove connections automatically)
7. **AC-7**: `broadcast_alert()` convenience method tested
8. **AC-8**: `get_connection_count()` tested
9. **AC-9**: Thread-safety tested (lock-protected operations)
10. **AC-10**: All tests use mocked WebSocket instances

## Tasks / Subtasks

- [ ] Task 1: Set up test file structure (AC: 1, 10)
  - [ ] 1.1: Create `backend/tests/test_services/test_websocket_manager.py`
  - [ ] 1.2: Add pytest-asyncio imports and test class structure
  - [ ] 1.3: Create mock WebSocket fixture with async send_text and accept methods

- [ ] Task 2: Implement WebSocketManager initialization tests (AC: 1)
  - [ ] 2.1: `test_websocket_manager_init` - Empty connection set, lock created
  - [ ] 2.2: `test_get_websocket_manager_returns_singleton` - Returns global instance

- [ ] Task 3: Implement connect() tests (AC: 3, 10)
  - [ ] 3.1: `test_connect_accepts_websocket` - Calls accept() on websocket
  - [ ] 3.2: `test_connect_adds_to_active_connections` - WebSocket added to set
  - [ ] 3.3: `test_connect_multiple_websockets` - Multiple connections tracked

- [ ] Task 4: Implement disconnect() tests (AC: 3, 10)
  - [ ] 4.1: `test_disconnect_removes_from_active_connections` - WebSocket removed
  - [ ] 4.2: `test_disconnect_nonexistent_websocket` - Gracefully handles not in set
  - [ ] 4.3: `test_disconnect_reduces_count` - Connection count decremented

- [ ] Task 5: Implement broadcast() tests (AC: 4, 5, 6, 10)
  - [ ] 5.1: `test_broadcast_no_connections` - Returns 0, no errors
  - [ ] 5.2: `test_broadcast_single_connection` - Message sent, returns 1
  - [ ] 5.3: `test_broadcast_multiple_connections` - All connections receive message
  - [ ] 5.4: `test_broadcast_adds_timestamp` - Message includes ISO timestamp
  - [ ] 5.5: `test_broadcast_json_serialization` - Message serialized as JSON
  - [ ] 5.6: `test_broadcast_failed_connection_removed` - Failed send removes connection
  - [ ] 5.7: `test_broadcast_partial_failure` - Returns count of successful sends

- [ ] Task 6: Implement broadcast_alert() tests (AC: 7)
  - [ ] 6.1: `test_broadcast_alert_message_format` - Correct type and data structure
  - [ ] 6.2: `test_broadcast_alert_returns_count` - Returns number of clients notified

- [ ] Task 7: Implement get_connection_count() tests (AC: 8)
  - [ ] 7.1: `test_get_connection_count_empty` - Returns 0 with no connections
  - [ ] 7.2: `test_get_connection_count_after_connects` - Returns correct count
  - [ ] 7.3: `test_get_connection_count_after_disconnect` - Count decremented

- [ ] Task 8: Implement concurrency tests (AC: 9)
  - [ ] 8.1: `test_concurrent_connects` - Multiple simultaneous connects handled
  - [ ] 8.2: `test_concurrent_broadcasts` - Broadcasts don't interfere

- [ ] Task 9: Run coverage and verify (AC: 2)
  - [ ] 9.1: Run `pytest tests/test_services/test_websocket_manager.py --cov=app/services/websocket_manager --cov-report=term-missing`
  - [ ] 9.2: Verify 70%+ line coverage achieved
  - [ ] 9.3: Add any missing tests for uncovered lines

## Dev Notes

### Architecture and Patterns

The `WebSocketManager` class (~182 lines) is a singleton service that manages:
1. **Connection Pool**: `active_connections` set with thread-safe add/remove via `_lock`
2. **Connection Lifecycle**: `connect()` accepts and registers, `disconnect()` removes
3. **Broadcasting**: `broadcast()` sends JSON messages to all connections with timestamp
4. **Error Handling**: Failed sends automatically clean up dead connections
5. **Alert Helper**: `broadcast_alert()` convenience method for alert notifications

### Key Methods to Test

| Method | Lines | Purpose | Test Focus |
|--------|-------|---------|------------|
| `connect()` | 51-65 | Accept and register WebSocket | accept called, added to set |
| `disconnect()` | 67-80 | Remove connection | removed from set, graceful |
| `broadcast()` | 82-143 | Send to all connections | JSON, timestamp, error handling |
| `broadcast_alert()` | 145-168 | Alert convenience method | message format |
| `get_connection_count()` | 170-172 | Count active connections | accurate count |

### Mock WebSocket Pattern

```python
@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket with async methods."""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws

@pytest.fixture
def mock_websocket_factory():
    """Factory to create multiple unique mock WebSockets."""
    def _create():
        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        return ws
    return _create
```

### Testing Failed Send Cleanup

```python
async def test_broadcast_failed_connection_removed(websocket_manager, mock_websocket_factory):
    """Test that failed send removes connection from pool."""
    good_ws = mock_websocket_factory()
    bad_ws = mock_websocket_factory()
    bad_ws.send_text = AsyncMock(side_effect=Exception("Connection closed"))

    await websocket_manager.connect(good_ws)
    await websocket_manager.connect(bad_ws)

    count = await websocket_manager.broadcast({"type": "test"})

    assert count == 1  # Only good connection succeeded
    assert good_ws in websocket_manager.active_connections
    assert bad_ws not in websocket_manager.active_connections
```

### Learnings from Previous Story

**From Story P14-3.4 (reprocessing_service.py tests):**

- Used `@pytest.mark.asyncio` for all async methods
- Organized tests into logical test classes by functionality
- Used AsyncMock for async method mocking
- Used parametrization for input variations
- Fresh WebSocketManager instance per test to avoid state leakage

### Project Structure Notes

- Test file goes in: `backend/tests/test_services/test_websocket_manager.py`
- Follows existing pattern in `test_reprocessing_service.py` and `test_snapshot_service.py`
- Create fresh WebSocketManager instance per test (don't use global singleton)

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P14-3.md#Story-P14-3.5]
- [Source: docs/epics-phase14.md#Story-P14-3.5]
- [Source: backend/app/services/websocket_manager.py] - Target service (182 lines)
- [Source: docs/sprint-artifacts/P14-3-4-add-unit-tests-for-reprocessing-service.md] - Previous story patterns

## Dev Agent Record

### Context Reference

N/A - YOLO mode execution

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A - All tests passed on first run

### Completion Notes List

- Created 32 comprehensive unit tests for WebSocketManager
- Achieved 100% line coverage (target was 70%)
- Tests organized into logical classes: Init, Connect, Disconnect, Broadcast, BroadcastAlert, ConnectionCount, Concurrency, EdgeCases, IntegrationScenarios
- All acceptance criteria met or exceeded
- No external dependencies needed - uses pytest-asyncio and unittest.mock

### File List

- **NEW**: `backend/tests/test_services/test_websocket_manager.py` (330 lines, 32 tests)
- **MODIFIED**: `docs/sprint-artifacts/sprint-status.yaml` (status updated to done)
- **MODIFIED**: `docs/sprint-artifacts/P14-3-5-add-unit-tests-for-websocket-manager.md` (status updated)
