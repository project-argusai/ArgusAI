# Story P2-3.2: Implement Snapshot Retrieval from Protect API

Status: done

## Story

As a **backend service**,
I want **to fetch a snapshot image when an event passes filtering**,
So that **I can send it to the AI provider for description**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| AC1 | Given an event has passed the filtering stage, when the event handler requests a snapshot, then the system fetches the snapshot from Protect API within 1 second (NFR4) | Integration test |
| AC2 | Snapshot uses Protect API to get snapshot at event timestamp, or current snapshot if event-time unavailable | Unit test |
| AC3 | Snapshot format is JPEG | Unit test |
| AC4 | Full resolution from camera (up to 4K) is retrieved, then resized to max 1920x1080 for AI processing | Unit test |
| AC5 | Snapshot is converted to base64 for AI API submission | Unit test |
| AC6 | Thumbnail (320x180) is generated and stored for event record | Unit test |
| AC7 | Full-size image is cleaned up after processing | Unit test |
| AC8 | If snapshot fails, retry once after 500ms | Unit test |
| AC9 | If retry fails, log error and skip event (don't crash) | Unit test |
| AC10 | Track snapshot failure rate for monitoring | Unit test |
| AC11 | Concurrent snapshots limited to 3 per controller | Unit test |
| AC12 | Snapshot retrieval completes within 1 second (NFR4) | Performance test |

## Tasks / Subtasks

- [x] **Task 1: Create snapshot retrieval service** (AC: 1, 2, 3, 4)
  - [x] 1.1 Create `backend/app/services/snapshot_service.py`
  - [x] 1.2 Define `SnapshotService` class with initialization
  - [x] 1.3 Implement `get_snapshot(controller_id, camera_id, timestamp=None)` method
  - [x] 1.4 Use `uiprotect` library: `await camera.get_snapshot()` or with timestamp
  - [x] 1.5 Return JPEG bytes from Protect API
  - [x] 1.6 Add timeout of 1 second for snapshot retrieval

- [x] **Task 2: Implement image processing** (AC: 4, 5, 6, 7)
  - [x] 2.1 Add PIL/Pillow dependency if not present (already installed)
  - [x] 2.2 Implement `_resize_for_ai(image_bytes, max_width=1920, max_height=1080)` method
  - [x] 2.3 Implement `_generate_thumbnail(image_bytes, width=320, height=180)` method
  - [x] 2.4 Implement `_to_base64(image_bytes)` method
  - [x] 2.5 Save thumbnail to configured storage path (`data/thumbnails/`)
  - [x] 2.6 Return paths and base64 data for downstream processing
  - [x] 2.7 Clean up full-size image after processing (memory management)

- [x] **Task 3: Implement retry and error handling** (AC: 8, 9, 10)
  - [x] 3.1 Add retry logic with 500ms delay between attempts
  - [x] 3.2 Maximum 2 attempts (initial + 1 retry)
  - [x] 3.3 Log errors with camera name and error details (no credentials)
  - [x] 3.4 Track failure metrics: `snapshot_failures_total` counter
  - [x] 3.5 Return None on failure (don't raise exception to caller)

- [x] **Task 4: Implement concurrency limiting** (AC: 11)
  - [x] 4.1 Add `asyncio.Semaphore` for per-controller concurrency (limit: 3)
  - [x] 4.2 Store semaphores in `_controller_semaphores: Dict[str, asyncio.Semaphore]`
  - [x] 4.3 Acquire semaphore before snapshot, release after
  - [x] 4.4 Timeout on semaphore acquisition (5 seconds)

- [x] **Task 5: Wire snapshot service to event handler** (AC: 1)
  - [x] 5.1 Import `SnapshotService` in `protect_event_handler.py`
  - [x] 5.2 Replace TODO comment with snapshot retrieval call
  - [x] 5.3 Call `snapshot_service.get_snapshot()` after event passes filters
  - [x] 5.4 Pass snapshot result to next stage (AI pipeline - Story P2-3.3)
  - [x] 5.5 Handle None response (snapshot failed) gracefully

- [x] **Task 6: Testing** (AC: all)
  - [x] 6.1 Unit tests for snapshot retrieval with mock uiprotect
  - [x] 6.2 Unit tests for image resizing and thumbnail generation
  - [x] 6.3 Unit tests for base64 conversion
  - [x] 6.4 Unit tests for retry logic
  - [x] 6.5 Unit tests for concurrency limiting
  - [x] 6.6 Integration test for full snapshot flow

## Dev Notes

### Architecture Patterns

**Snapshot Retrieval Flow:**
```
Event passes filtering (Story P2-3.1)
        ↓
SnapshotService.get_snapshot(controller_id, camera_id, timestamp)
        ↓
1. Acquire controller semaphore (limit: 3 concurrent)
        ↓
2. Call uiprotect: await camera.get_snapshot(dt=timestamp)
        ↓ (retry once on failure)
3. Resize to max 1920x1080
        ↓
4. Generate thumbnail (320x180)
        ↓
5. Convert to base64
        ↓
6. Return SnapshotResult(base64, thumbnail_path)
        ↓
7. Pass to AI pipeline (Story P2-3.3)
```

**SnapshotResult Data Class:**
```python
@dataclass
class SnapshotResult:
    image_base64: str       # Base64-encoded JPEG for AI API
    thumbnail_path: str     # Path to saved thumbnail
    width: int              # Final image width
    height: int             # Final image height
    camera_id: str          # Camera that captured snapshot
    timestamp: datetime     # When snapshot was taken
```

### Learnings from Previous Story

**From Story P2-3.1 (Status: done)**

- **New Service Created**: `ProtectEventHandler` at `backend/app/services/protect_event_handler.py` - hook point for snapshot retrieval at end of `handle_event()`
- **Integration Point**: Line ~193-194 has TODO comment: `# TODO: Story P2-3.2 - Pass to snapshot retrieval`
- **Event Handler Methods**: Use `handle_event()` return value to indicate if snapshot should be retrieved
- **Controller Access**: Use `ProtectService._connections[controller_id]` to get the uiprotect client
- **Test Patterns**: 145 tests pass in `test_protect.py` - follow mock patterns for uiprotect

**Key Files to Reuse/Extend:**
- `backend/app/services/protect_event_handler.py` - Wire snapshot call after filtering
- `backend/app/services/protect_service.py` - Access controller connections
- `backend/tests/test_api/test_protect.py` - Add snapshot tests following patterns

**Interfaces Created in Previous Stories:**
- `ProtectService._connections` dict - Active controller connections with uiprotect clients
- `ProtectService.get_camera_snapshot()` method - Already exists (Story P2-2.4), reuse if suitable
- `Camera.protect_camera_id` - Native Protect camera ID for API calls

[Source: docs/sprint-artifacts/p2-3-1-implement-protect-event-listener-and-event-handler.md#Completion-Notes-List]

### Project Structure Notes

**New File:**
- `backend/app/services/snapshot_service.py` - Snapshot retrieval and image processing

**Files to Modify:**
- `backend/app/services/protect_event_handler.py` - Wire snapshot service call
- `backend/tests/test_api/test_protect.py` - Add snapshot service tests

**Dependencies:**
- PIL/Pillow - Already installed (used by event_processor.py)
- asyncio - Standard library for semaphores

### Testing Standards

- Follow existing pytest patterns in `tests/test_api/test_protect.py`
- Use `@pytest.mark.asyncio` for async tests
- Mock uiprotect `camera.get_snapshot()` responses
- Use PIL mock for image processing tests
- Test concurrency with multiple concurrent calls
- Test timeout and retry scenarios

### References

- [Source: docs/epics-phase2.md#Story-3.2] - Full acceptance criteria
- [Source: docs/architecture.md#Phase-2-Additions] - Event processing pipeline
- [Source: docs/PRD-phase2.md#FR18] - Snapshot retrieval requirements
- [Source: backend/app/services/protect_event_handler.py] - Integration point at TODO comment
- [Source: backend/app/services/protect_service.py#get_camera_snapshot] - Existing snapshot method

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p2-3-2-implement-snapshot-retrieval-from-protect-api.context.xml`

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Fixed circular import between snapshot_service.py and protect_service.py by using lazy import inside `_fetch_snapshot_with_retry()` method
- Updated existing P2-3.1 tests to mock snapshot service (tests expected True return, now returns `snapshot_result is not None`)

### Completion Notes List

- **SnapshotService** created with singleton pattern (`get_snapshot_service()`)
- **SnapshotResult** dataclass holds base64, thumbnail_path, dimensions, camera_id, timestamp
- **Image processing**: Resize to max 1920x1080 with LANCZOS, generate 320x180 thumbnail
- **Concurrency**: asyncio.Semaphore per controller limits to 3 concurrent snapshots
- **Retry logic**: 500ms delay, 2 attempts (initial + 1 retry), returns None on failure
- **Integration**: `_retrieve_snapshot()` method added to ProtectEventHandler, called after event passes filters
- **Metrics**: `_snapshot_failures_total`, `_snapshot_success_total` counters, `get_metrics()` for monitoring
- **Tests**: 28 new tests for Story P2-3.2, all 173 protect tests pass

### File List

**Created:**
- `backend/app/services/snapshot_service.py` (533 lines) - SnapshotService with image processing, retry logic, concurrency limiting

**Modified:**
- `backend/app/services/protect_event_handler.py` - Added `_retrieve_snapshot()` method (lines 431-501), wired snapshot retrieval after event passes filters
- `backend/tests/test_api/test_protect.py` - Added 28 tests for Story P2-3.2 (lines 2910-3271), updated 2 existing tests to mock snapshot service

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-01 | Story drafted from epics-phase2.md | SM Agent |
| 2025-12-01 | Implementation complete - all 6 tasks done, 173 tests pass | Dev Agent |
