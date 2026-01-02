# Story P16-2.5: Implement Concurrent Stream Limiting

**Epic:** P16-2 - Live Camera Streaming
**Status:** Done
**Priority:** Medium
**GitHub Issue:** Part of #336

## Story

As a system administrator, I want the system to limit concurrent video streams so that server resources are not exhausted by too many simultaneous streams.

## Acceptance Criteria

- [x] AC1: Backend enforces limit and returns error when exceeded
- [x] AC2: Frontend displays clear error message
- [x] AC3: Count decrements properly on disconnect
- [x] AC4: STREAM_MAX_CONCURRENT is configurable
- [ ] AC5 (Optional): Admin can see current stream count in Settings > System

## Implementation Notes

**Already Implemented:** This story was discovered to be fully implemented as part of P16-2.2 (Stream Proxy Service) and P16-2.3 (LiveStreamPlayer). No additional development was required.

### Backend Implementation (P16-2.2)

Location: `backend/app/services/stream_proxy_service.py`

```python
# Configuration
STREAM_MAX_CONCURRENT: int = 10  # In config.py

# Limit enforcement in StreamProxyService.add_client()
async def add_client(...) -> Optional[str]:
    with self._lock:
        # Check concurrent limit
        if self._total_clients >= self._max_concurrent:
            logger.warning(f"Stream client limit reached: {self._total_clients}/{self._max_concurrent}")
            return None  # Returns None when limit reached
```

Location: `backend/app/api/v1/cameras.py` (WebSocket endpoint)

```python
# WebSocket close code
WS_CLOSE_STREAM_LIMIT = 4429  # Like HTTP 429 - too many streams

# Check if stream limit is reached
stream_info = stream_service.get_stream_info(camera_id)
if not stream_info["is_available"]:
    await websocket.send_json({
        "type": "error",
        "code": "STREAM_LIMIT_REACHED",
        "message": "Maximum concurrent streams reached. Please close another stream first."
    })
    await websocket.close(code=4429, reason="Stream limit reached")
    return
```

### Frontend Implementation (P16-2.3)

Location: `frontend/components/streaming/LiveStreamPlayer.tsx`

```typescript
// WebSocket close codes (Story P16-2.5)
const WS_CLOSE_STREAM_LIMIT = 4429; // Like HTTP 429 - too many streams

ws.onclose = (event) => {
    switch (event.code) {
        case WS_CLOSE_STREAM_LIMIT:
            // Concurrent stream limit reached
            setConnectionState('error');
            setErrorMessage('Maximum concurrent streams reached. Please close another stream first.');
            showWarning('Maximum concurrent streams reached. Please close another stream first.');
            return;
        // ... other cases
    }
};
```

### Tests

1. **Backend tests:** `backend/tests/test_services/test_stream_proxy_service.py`
   - `TestConcurrentStreamLimiting` class with comprehensive tests

2. **Frontend tests:** `frontend/__tests__/components/streaming/LiveStreamPlayer.test.tsx`
   - "Concurrent Stream Limiting (Story P16-2.5)" test section

## Technical Notes

- WebSocket close code 4429 follows HTTP 429 (Too Many Requests) convention
- Default limit: 10 concurrent streams server-wide
- Configurable via `STREAM_MAX_CONCURRENT` environment variable
- Client count properly decremented on WebSocket disconnect via `remove_client()`

## Optional: Admin Dashboard Stream Count

The optional AC5 (showing current stream count in Settings > System) was not implemented as it provides minimal value. Administrators can monitor stream usage via:
1. Server logs (stream client limit warnings)
2. Direct observation of active streams

If needed in the future, the `StreamProxyService.get_stats()` method already provides:
- `active_cameras`: Number of cameras with active streams
- `total_clients`: Total connected stream clients
