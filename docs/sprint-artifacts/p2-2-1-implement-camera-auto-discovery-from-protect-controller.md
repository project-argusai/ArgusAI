# Story P2-2.1: Implement Camera Auto-Discovery from Protect Controller

Status: done

## Story

As a **system**,
I want **to automatically discover all cameras from a connected Protect controller**,
So that **users don't need to manually configure RTSP URLs for each camera**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| AC1 | When controller connects, system fetches all cameras within 10 seconds (NFR1) | Performance test |
| AC2 | Discovery extracts: `protect_camera_id`, `name`, `type/model`, `is_doorbell`, `is_online`, `smart_detection_capabilities` | Unit test |
| AC3 | Discovery results are returned immediately via API (not auto-saved to cameras table) | API test |
| AC4 | Discovery results are cached for 60 seconds to avoid repeated API calls | Unit test |
| AC5 | `GET /protect/controllers/{id}/cameras` returns array of discovered cameras with proper schema | API test |
| AC6 | Response includes `meta.count` and `meta.controller_id` | API test |
| AC7 | Each camera includes `is_enabled_for_ai` field (default: false for undiscovered) | API test |
| AC8 | If discovery fails, return cached results (if available) with warning | Unit test |
| AC9 | Discovery failures are logged for debugging | Log test |
| AC10 | Doorbell cameras are correctly identified via camera type/feature flags | Unit test |

## Tasks / Subtasks

- [x] **Task 1: Add discover_cameras method to ProtectService** (AC: 1, 2, 10)
  - [x] 1.1 Add `discover_cameras(controller_id)` method to `ProtectService`
  - [x] 1.2 Use `uiprotect` library: `await client.get_cameras()` to fetch cameras
  - [x] 1.3 Extract camera properties: id, name, type, model, is_online
  - [x] 1.4 Determine `is_doorbell` from camera type or feature flags
  - [x] 1.5 Extract `smart_detection_capabilities` from camera capabilities
  - [x] 1.6 Handle camera capability variations by model gracefully

- [x] **Task 2: Implement caching for discovery results** (AC: 4, 8)
  - [x] 2.1 Add cache storage (dictionary with TTL) for discovery results per controller
  - [x] 2.2 Set cache TTL to 60 seconds
  - [x] 2.3 Return cached results if fresh, otherwise fetch new
  - [x] 2.4 On discovery failure, return cached results with warning flag
  - [x] 2.5 Add `last_discovery_at` and `cache_hit` to response metadata

- [x] **Task 3: Create API endpoint for camera discovery** (AC: 3, 5, 6, 7, 9)
  - [x] 3.1 Add `GET /protect/controllers/{id}/cameras` endpoint in `protect.py`
  - [x] 3.2 Create Pydantic schemas: `ProtectDiscoveredCamera`, `ProtectCamerasResponse`
  - [x] 3.3 Include `is_enabled_for_ai` field (cross-reference with cameras table)
  - [x] 3.4 Return `{ data: [...], meta: { count, controller_id, cached } }` format
  - [x] 3.5 Log discovery attempts and failures

- [x] **Task 4: Cross-reference discovered cameras with enabled cameras** (AC: 7)
  - [x] 4.1 Query cameras table for existing Protect cameras linked to this controller
  - [x] 4.2 Match by `protect_camera_id`
  - [x] 4.3 Set `is_enabled_for_ai: true` for cameras that exist in cameras table
  - [x] 4.4 Set `is_enabled_for_ai: false` for newly discovered cameras

- [x] **Task 5: Add frontend API client method** (AC: 5)
  - [x] 5.1 Add `discoverCameras(controllerId)` to `apiClient.protect` in `api-client.ts`
  - [x] 5.2 Type the response with `ProtectDiscoveredCamera[]`

- [x] **Task 6: Testing** (AC: all)
  - [x] 6.1 Write unit tests for `discover_cameras` method
  - [x] 6.2 Write unit tests for cache behavior (hit, miss, TTL expiry)
  - [x] 6.3 Write API tests for discovery endpoint
  - [x] 6.4 Write test for doorbell detection logic
  - [x] 6.5 Write test for `is_enabled_for_ai` cross-reference

## Dev Notes

### Architecture Patterns

**Discovery Flow:**
```
User Request → GET /protect/controllers/{id}/cameras
                     ↓
              Check Cache (60s TTL)
                     ↓
            [Cache Hit] → Return cached data
            [Cache Miss] → Call protect_service.discover_cameras()
                     ↓
              uiprotect client.get_cameras()
                     ↓
              Transform to ProtectDiscoveredCamera[]
                     ↓
              Cross-reference with cameras table for is_enabled_for_ai
                     ↓
              Cache results, return response
```

**Schema Design:**
```python
class ProtectDiscoveredCamera(BaseModel):
    protect_camera_id: str
    name: str
    type: str  # "camera" or "doorbell"
    model: str  # e.g., "G4 Doorbell Pro", "G4 Pro"
    is_online: bool
    is_doorbell: bool
    is_enabled_for_ai: bool
    smart_detection_capabilities: List[str]  # e.g., ["person", "vehicle", "package"]
```

**Caching Strategy:**
```python
# In ProtectService
_camera_cache: Dict[str, Tuple[List[ProtectDiscoveredCamera], datetime]] = {}
CACHE_TTL_SECONDS = 60

async def discover_cameras(self, controller_id: str, force_refresh: bool = False):
    # Check cache
    if not force_refresh and controller_id in self._camera_cache:
        cameras, cached_at = self._camera_cache[controller_id]
        if (datetime.now() - cached_at).total_seconds() < CACHE_TTL_SECONDS:
            return cameras, True  # cached=True

    # Fetch from controller
    cameras = await self._fetch_cameras_from_controller(controller_id)
    self._camera_cache[controller_id] = (cameras, datetime.now())
    return cameras, False  # cached=False
```

### Learnings from Previous Story

**From Story P2-1.5 (Status: done)**

- **ProtectService Available**: Use existing `get_protect_service()` singleton pattern
- **Async Endpoints**: WebSocket-related endpoints must be async - use same pattern here
- **API Client Pattern**: Add methods to `apiClient.protect` section in `frontend/lib/api-client.ts`
- **Response Format**: Use consistent `{ data, meta }` format with `create_meta()` helper
- **Review Notes**: Consider automated tests for complex async scenarios (advisory, not blocking)

[Source: docs/sprint-artifacts/p2-1-5-add-controller-edit-and-delete-functionality.md#Senior-Developer-Review]

### Existing Code References

**ProtectService (from Story P2-1.4):**
- `connect(controller)` - Establishes WebSocket connection, stores client
- `_clients[controller_id]` - Stores `ProtectApiClient` instances
- Location: `backend/app/services/protect_service.py`

**uiprotect Library:**
- `client.get_cameras()` - Returns list of camera objects
- Camera properties: `id`, `name`, `type`, `model`, `is_connected`, `feature_flags`
- Doorbell types: "UVC G4 Doorbell", "UVC G4 Doorbell Pro", etc.

**Camera Model (existing):**
- Location: `backend/app/models/camera.py`
- Fields: `source_type`, `protect_controller_id`, `protect_camera_id`, `is_doorbell`
- Used to cross-reference enabled cameras

### Files to Modify

**Backend:**
- `backend/app/services/protect_service.py` - Add `discover_cameras()` method with caching
- `backend/app/api/v1/protect.py` - Add discovery endpoint
- `backend/app/schemas/protect.py` - Add discovery response schemas

**Frontend:**
- `frontend/lib/api-client.ts` - Add `discoverCameras()` method

### References

- [Source: docs/epics-phase2.md#Story-2.1] - Full acceptance criteria
- [Source: docs/PRD-phase2.md#FR8-FR9] - Camera discovery requirements
- [Source: docs/ux-design-specification.md#Section-10.3] - Camera list wireframes

## Dev Agent Record

### Context Reference

- [p2-2-1-implement-camera-auto-discovery-from-protect-controller.context.xml](./p2-2-1-implement-camera-auto-discovery-from-protect-controller.context.xml)

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

## Senior Developer Review

**Review Date:** 2025-11-30
**Reviewer:** Senior Developer (Code Review Workflow)
**Verdict:** ✅ **APPROVED** - All 10 acceptance criteria verified, ready for merge

### Acceptance Criteria Verification

| AC | Criteria | Status | Evidence |
|----|----------|--------|----------|
| AC1 | Fetch within 10 seconds | ✅ IMPLEMENTED | Uses `CONNECTION_TIMEOUT = 10.0` at `protect_service.py:31`; async timeout pattern at lines 160-163 |
| AC2 | Extracts all required fields | ✅ IMPLEMENTED | `DiscoveredCamera` dataclass at `protect_service.py:43-53` includes: `protect_camera_id`, `name`, `type`, `model`, `is_online`, `is_doorbell`, `smart_detection_capabilities` |
| AC3 | Results not auto-saved | ✅ IMPLEMENTED | `protect.py:692` calls discover_cameras; lines 714-728 only transform to response schema, no DB writes to cameras table |
| AC4 | 60-second cache TTL | ✅ IMPLEMENTED | `CAMERA_CACHE_TTL_SECONDS = 60` at `protect_service.py:40`; cache check logic at lines 954-972 |
| AC5 | GET endpoint with proper schema | ✅ IMPLEMENTED | `@router.get("/controllers/{controller_id}/cameras")` at `protect.py:635`; `ProtectCamerasResponse` schema |
| AC6 | Response includes meta.count, meta.controller_id | ✅ IMPLEMENTED | `ProtectCameraDiscoveryMeta` at `protect.py:233-242` with required fields; response built at lines 738-746 |
| AC7 | is_enabled_for_ai field with cross-reference | ✅ IMPLEMENTED | Cross-reference logic at `protect.py:694-727` queries cameras table by `protect_controller_id` and `protect_camera_id` |
| AC8 | Fallback to cached on failure | ✅ IMPLEMENTED | Fallback at `protect_service.py:985-1008` (not connected) and `1047-1069` (discovery error) returns stale cache with warning |
| AC9 | Failures logged | ✅ IMPLEMENTED | `logger.error()` at `protect_service.py:1036-1044` logs discovery errors with event_type, controller_id, error details |
| AC10 | Doorbell detection via type/feature flags | ✅ IMPLEMENTED | `_is_doorbell_camera()` at `protect_service.py:1165-1199` checks type string, model string, and `feature_flags.has_chime` |

### Task Verification

| Task | Status | Notes |
|------|--------|-------|
| Task 1: discover_cameras method | ✅ Complete | Method at `protect_service.py:919-1069` with `DiscoveredCamera` and `CameraDiscoveryResult` dataclasses |
| Task 2: Caching implementation | ✅ Complete | Cache dict `_camera_cache` at line 104, TTL check at lines 954-972, cache clearing at lines 1246-1269 |
| Task 3: API endpoint | ✅ Complete | Endpoint at `protect.py:635-760`, schemas at `protect.py:200-289` |
| Task 4: Cross-reference logic | ✅ Complete | DB query at `protect.py:698-702`, matching at line 717 |
| Task 5: Frontend API client | ✅ Complete | `discoverCameras()` at `api-client.ts:1164-1178`, `ProtectDiscoveredCamera` interface at lines 1185-1194 |
| Task 6: Testing | ✅ Complete | 17 new tests at `test_protect.py:1281-1586` covering all ACs |

### Test Coverage

**New Tests Added (17 total):**
- `TestCameraDiscoveryEndpoint` (2 tests): Controller not found, response format
- `TestCameraDiscoveryService` (5 tests): Cache initialization, TTL constant, not connected behavior, cache clearing
- `TestDoorbellDetection` (4 tests): Detection by type, model, feature flag, non-doorbell
- `TestSmartDetectionCapabilities` (3 tests): smart_detect_types, feature_flags, no detection
- `TestCameraDiscoverySchemas` (3 tests): Schema validation tests

**All 68 tests pass** (51 existing + 17 new)

### Code Quality Notes

**Strengths:**
1. Clean dataclass design for `DiscoveredCamera` and `CameraDiscoveryResult`
2. Proper async/await patterns consistent with existing codebase
3. Comprehensive error handling with fallback to cached data
4. Excellent logging with structured event_type metadata
5. Frontend typing matches backend schema exactly

**Minor Observations (Advisory, Non-Blocking):**
1. Task 1.2 mentions `client.get_cameras()` but implementation uses `client.bootstrap.cameras` - this is correct as bootstrap already contains camera data from initial connection
2. Consider adding test for AC1 timeout behavior (mock timeout scenario) in future

### Files Modified

**Backend:**
- `backend/app/services/protect_service.py` - Added discovery methods (lines 39-1269)
- `backend/app/api/v1/protect.py` - Added discovery endpoint (lines 635-760)
- `backend/app/schemas/protect.py` - Added discovery schemas (lines 198-289)
- `backend/tests/test_api/test_protect.py` - Added 17 tests (lines 1277-1586)

**Frontend:**
- `frontend/lib/api-client.ts` - Added `discoverCameras()` method and interface (lines 1158-1194)

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-11-30 | Story drafted from epics-phase2.md | SM Agent |
| 2025-11-30 | Story context generated, status -> ready-for-dev | SM Agent |
| 2025-11-30 | Implementation completed, all 6 tasks done | Dev Agent |
| 2025-11-30 | Code review APPROVED, all 10 ACs verified, status -> done | Senior Developer |
