# Story P7-3.2: Add Camera Snapshot Support

Status: done

## Story

As a **homeowner with Apple Home**,
I want **camera tiles in the Home app to display up-to-date preview thumbnails**,
so that **I can quickly see what each camera is looking at without starting a live stream**.

## Story Key
p7-3-2-add-camera-snapshot-support

## Acceptance Criteria

| AC# | Criteria | Verification |
|-----|----------|--------------|
| AC1 | get_snapshot() method implemented in camera accessory | Unit: Verify method exists and returns bytes |
| AC2 | JPEG snapshot returned from camera | Unit: Verify returned data is valid JPEG |
| AC3 | Snapshot cached for 5 seconds to reduce load | Unit: Verify cache hit within 5s, cache miss after 5s |
| AC4 | Camera offline returns placeholder gracefully | Unit: Mock offline camera, verify placeholder returned |

## Tasks / Subtasks

### Task 1: Add Snapshot Caching Infrastructure (AC: 3)
- [x] 1.1 Add `_snapshot_cache: Optional[bytes]` class attribute to HomeKitCameraAccessory
- [x] 1.2 Add `_snapshot_timestamp: Optional[datetime]` class attribute
- [x] 1.3 Add `SNAPSHOT_CACHE_SECONDS = 5` constant
- [x] 1.4 Add `_is_snapshot_cache_valid()` method to check cache freshness

### Task 2: Enhance get_snapshot() with Caching (AC: 1, 2, 3)
- [x] 2.1 Update `_get_snapshot()` to check cache first before capturing
- [x] 2.2 Store captured snapshot in cache with timestamp
- [x] 2.3 Return cached snapshot if within cache validity window
- [x] 2.4 Add logging for cache hits vs misses for debugging
- [x] 2.5 Add Prometheus metrics: `argusai_homekit_snapshot_cache_hits_total`, `argusai_homekit_snapshot_cache_misses_total`

### Task 3: Improve Offline Camera Handling (AC: 4)
- [x] 3.1 Verify placeholder image includes "Camera Offline" text (already exists)
- [x] 3.2 Add logging when returning placeholder due to camera offline
- [x] 3.3 Ensure placeholder is returned within reasonable time (<1s)

### Task 4: Add Snapshot API Endpoint for Testing (AC: 1, 2)
- [x] 4.1 Add `GET /api/v1/homekit/cameras/{camera_id}/snapshot` endpoint
- [x] 4.2 Return JPEG image with appropriate Content-Type header
- [x] 4.3 Return 503 if camera is offline with placeholder_available flag
- [x] 4.4 Add to API client for testing from frontend (via homekit_service.get_camera_snapshot())

### Task 5: Update HomeKit Status with Snapshot Info
- [x] 5.1 Add `snapshot_supported: bool` and `last_snapshot: datetime` to camera accessory properties
- [ ] 5.2 Display last snapshot time in HomeKit Settings UI (optional enhancement - skipped)

### Task 6: Unit and Integration Tests
- [x] 6.1 Unit test: Snapshot cache behavior (cache hit, cache miss, expiry)
- [x] 6.2 Unit test: Placeholder image generation on offline camera
- [x] 6.3 Unit test: JPEG output format validation
- [x] 6.4 Integration test: `/api/v1/homekit/cameras/{id}/snapshot` returns JPEG
- [x] 6.5 Integration test: Snapshot endpoint returns 503 for offline camera

## Dev Notes

### Existing Implementation Analysis
The `_get_snapshot()` method already exists in `homekit_camera.py` (lines 517-579) with:
- ffmpeg-based RTSP frame capture
- JPEG output via mjpeg codec
- Placeholder image on failure via `_get_placeholder_image()`
- 5-second timeout for capture

**Missing functionality that this story adds:**
- Snapshot caching (cache for 5 seconds)
- Prometheus metrics for cache performance
- API endpoint for testing
- Status reporting in HomeKit panel

### Key Files to Modify
- `backend/app/services/homekit_camera.py` - Add caching to `_get_snapshot()`
- `backend/app/api/v1/homekit.py` - Add snapshot endpoint
- `backend/app/core/metrics.py` - Add snapshot cache metrics
- `frontend/components/settings/HomeKitSettings.tsx` - Optional: show last snapshot time

### Caching Implementation Pattern
```python
# Instance-level caching (not class-level, since each camera has its own cache)
SNAPSHOT_CACHE_SECONDS = 5

def __init__(self, ...):
    ...
    self._snapshot_cache: Optional[bytes] = None
    self._snapshot_timestamp: Optional[datetime] = None

async def _get_snapshot(self, image_size: dict) -> bytes:
    # Check cache first
    if self._is_snapshot_cache_valid():
        logger.debug(f"Snapshot cache hit for {self.camera_name}")
        return self._snapshot_cache

    # Capture new snapshot
    snapshot = await self._capture_snapshot(image_size)

    # Update cache
    self._snapshot_cache = snapshot
    self._snapshot_timestamp = datetime.utcnow()

    return snapshot

def _is_snapshot_cache_valid(self) -> bool:
    if self._snapshot_cache is None or self._snapshot_timestamp is None:
        return False
    age = (datetime.utcnow() - self._snapshot_timestamp).total_seconds()
    return age < SNAPSHOT_CACHE_SECONDS
```

### Architecture Constraints
- Snapshot capture uses ffmpeg subprocess (< 5s timeout)
- JPEG quality: 85% (balanced size/quality)
- Maximum snapshot size: 640x480 for HomeKit tiles
- Cache is per-camera instance, not global

### Testing Strategy
- Unit tests mock ffmpeg subprocess and verify caching logic
- Integration tests verify API endpoint returns valid JPEG
- Manual testing with Apple Home app to see camera tiles

### Project Structure Notes
- HomeKit services in `backend/app/services/homekit_*.py`
- HomeKit API in `backend/app/api/v1/homekit.py`
- Prometheus metrics in `backend/app/core/metrics.py`

### References
- [Source: docs/sprint-artifacts/tech-spec-epic-P7-3.md#Story-P7-3.2]
- [Source: docs/epics-phase7.md#Story-P7-3.2]
- [Source: backend/app/services/homekit_camera.py#_get_snapshot]

### Learnings from Previous Story

**From Story p7-3-1-verify-rtsp-to-srtp-streaming-works (Status: done)**

- **StreamQuality/StreamConfig Pattern**: Quality enum with dataclass config mapping works well for ffmpeg parameters
- **Prometheus Metrics**: Use `record_homekit_*` and `update_homekit_*` functions from metrics.py
- **Existing Snapshot Code**: `_get_snapshot()` already handles ffmpeg capture and placeholder - just needs caching layer
- **ffmpeg Command Pattern**: Use `-rtsp_transport tcp` and subprocess with timeout
- **Testing**: All 22 HomeKit camera tests pass - add caching tests following same pattern

[Source: docs/sprint-artifacts/p7-3-1-verify-rtsp-to-srtp-streaming-works.md#Dev-Agent-Record]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p7-3-2-add-camera-snapshot-support.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

N/A

### Completion Notes List

- All 4 acceptance criteria met
- 32 HomeKit camera tests pass (including 13 new snapshot caching tests)
- 42 HomeKit API tests pass (including 3 new snapshot endpoint tests)
- Task 5.2 (frontend UI for last snapshot time) intentionally skipped as optional enhancement

### File List

- `backend/app/services/homekit_camera.py` - Added snapshot caching infrastructure, cache validation, properties
- `backend/app/services/homekit_service.py` - Added get_camera_snapshot() method
- `backend/app/api/v1/homekit.py` - Added GET /api/v1/homekit/cameras/{camera_id}/snapshot endpoint
- `backend/app/core/metrics.py` - Added snapshot cache hit/miss Prometheus metrics
- `backend/tests/test_services/test_homekit_camera.py` - Added TestSnapshotCaching and TestPlaceholderImage test classes
- `backend/tests/test_api/test_homekit.py` - Added TestSnapshotEndpoint test class

## Change Log
| Date | Change |
|------|--------|
| 2025-12-19 | Story drafted from epic P7-3 and tech spec |
| 2025-12-19 | Story implementation completed - all ACs met, tests pass |
