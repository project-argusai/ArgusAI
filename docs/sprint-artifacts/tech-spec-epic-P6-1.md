# Epic Technical Specification: Camera Setup & Performance

Date: 2025-12-16
Author: Brent
Epic ID: P6-1
Status: Draft

---

## Overview

Epic P6-1 addresses two related goals from the project backlog: improving the camera setup user experience (FF-011) and optimizing frontend performance for deployments with many cameras (IMP-005).

The pre-save connection test feature allows users to validate RTSP/USB camera configurations before committing them to the database, reducing frustration from invalid camera entries. The performance optimizations (React.memo, virtual scrolling, React Query caching) ensure the application remains responsive as the camera count grows beyond 20 cameras.

These improvements consolidate remaining Phase 6 polish items into a cohesive epic focused on camera-related UX and scalability.

## Objectives and Scope

### In Scope
- **Story P6-1.1**: Create POST `/api/v1/cameras/test` endpoint that accepts camera configuration in request body (no camera_id required)
- **Story P6-1.2**: Wrap CameraPreview component with React.memo and custom comparison function
- **Story P6-1.3**: Integrate @tanstack/react-virtual for camera list virtualization
- **Story P6-1.4**: Configure TanStack Query (React Query) for camera API caching with stale-while-revalidate

### Out of Scope
- Changes to existing camera CRUD endpoints
- Backend camera service refactoring
- Real-time camera status WebSocket enhancements
- Camera thumbnail storage optimization
- Audio stream capture (covered in Epic P6-3)

## System Architecture Alignment

### Components Referenced
- **Backend**: `backend/app/api/v1/cameras.py` - New test endpoint
- **Backend**: `backend/app/services/camera_service.py` - Connection testing logic
- **Frontend**: `frontend/components/cameras/CameraPreview.tsx` - React.memo optimization
- **Frontend**: `frontend/app/cameras/page.tsx` - Virtual scrolling integration
- **Frontend**: `frontend/lib/api-client.ts` - React Query configuration

### Architecture Constraints
- Must maintain existing `/cameras/{id}/test` endpoint for backwards compatibility
- React Query must coexist with existing SWR usage or replace it consistently
- Virtual scrolling must not break existing camera filtering/sorting functionality
- Pre-save test must not create any database records

## Detailed Design

### Services and Modules

| Module | Responsibility | Inputs | Outputs |
|--------|---------------|--------|---------|
| `cameras.py` (API) | New `/test` endpoint without camera_id | CameraTestRequest body | CameraTestResponse |
| `camera_service.py` | Connection testing logic (reused) | URL, credentials, source_type | Success/failure, stream info, thumbnail |
| `CameraPreview.tsx` | Display camera preview with memoization | Camera object, refresh interval | Rendered preview card |
| `CamerasPage.tsx` | Virtualized camera list container | Camera array, filters | Scrollable virtualized list |
| `api-client.ts` | React Query hooks for cameras | Query keys, fetch functions | Cached camera data |

### Data Models and Contracts

**CameraTestRequest (New Schema)**
```python
class CameraTestRequest(BaseModel):
    """Request body for testing camera connection before save"""
    name: str = Field(..., min_length=1, max_length=100)
    source_type: Literal["rtsp", "usb"] = Field(...)
    url: Optional[str] = Field(None, description="RTSP URL for IP cameras")
    username: Optional[str] = Field(None)
    password: Optional[str] = Field(None)
    device_index: Optional[int] = Field(None, ge=0, description="USB device index")

    @model_validator(mode='after')
    def validate_source_config(self):
        if self.source_type == "rtsp" and not self.url:
            raise ValueError("RTSP cameras require url")
        if self.source_type == "usb" and self.device_index is None:
            raise ValueError("USB cameras require device_index")
        return self
```

**CameraTestResponse (Existing, reused)**
```python
class CameraTestResponse(BaseModel):
    success: bool
    message: str
    thumbnail_base64: Optional[str] = None
    stream_info: Optional[StreamInfo] = None

class StreamInfo(BaseModel):
    width: int
    height: int
    fps: float
    codec: Optional[str] = None
```

### APIs and Interfaces

**New Endpoint: POST /api/v1/cameras/test**

| Attribute | Value |
|-----------|-------|
| Method | POST |
| Path | `/api/v1/cameras/test` |
| Auth | Required |
| Request Body | `CameraTestRequest` |
| Response | `CameraTestResponse` |
| Errors | 400 (validation), 422 (connection failed), 500 (internal) |

**Request Example:**
```json
{
  "name": "Front Door Camera",
  "source_type": "rtsp",
  "url": "rtsp://192.168.1.100:554/stream1",
  "username": "admin",
  "password": "password123"
}
```

**Response Example (Success):**
```json
{
  "success": true,
  "message": "Connection successful",
  "thumbnail_base64": "/9j/4AAQSkZJRg...",
  "stream_info": {
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "codec": "H.264"
  }
}
```

**Response Example (Failure):**
```json
{
  "success": false,
  "message": "Connection refused: Unable to connect to rtsp://192.168.1.100:554/stream1",
  "thumbnail_base64": null,
  "stream_info": null
}
```

### Workflows and Sequencing

**Pre-Save Connection Test Flow:**
```
User fills camera form → Clicks "Test Connection" →
  Frontend calls POST /api/v1/cameras/test →
    Backend creates temporary OpenCV capture →
    Attempts connection (5s timeout) →
    If success: captures frame, extracts stream info →
    Returns response (no DB write) →
  Frontend shows success/failure message →
  If success: User clicks "Save" → Normal POST /cameras flow
```

**React Query Cache Flow:**
```
Component mounts → useQuery('cameras') →
  Check cache: stale? →
    If fresh: return cached data immediately
    If stale: return cached + background refetch →
  On window focus: revalidate if stale →
  On mutation (create/update/delete): invalidate cache
```

**Virtual Scrolling Flow:**
```
Camera list renders → useVirtualizer calculates visible range →
  Only renders items in viewport + overscan →
  User scrolls → recalculates visible items →
  Smooth 60fps scrolling maintained
```

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| Connection test response time | < 6 seconds | 5s timeout + 1s processing |
| Camera list render (50 cameras) | < 100ms | React DevTools profiler |
| Scroll frame rate | 60 FPS | Chrome DevTools performance |
| API cache hit rate | > 80% | React Query DevTools |
| Memory usage (100 cameras) | < 50MB additional | Chrome memory profiler |

**Architecture Reference:** docs/architecture/10-performance.md specifies virtual scrolling for large event lists; same pattern applies to camera lists.

### Security

| Requirement | Implementation |
|-------------|----------------|
| Credentials in test request | Transmitted over HTTPS, never logged |
| Test endpoint authentication | Requires valid session/token |
| No credential persistence | Test does not store credentials to DB |
| Input validation | Pydantic validates URL format, prevents injection |

**Note:** The test endpoint accepts credentials in the request body. These are used only for the connection attempt and immediately discarded. No audit log of test credentials is maintained.

### Reliability/Availability

| Scenario | Behavior |
|----------|----------|
| Connection test timeout | Returns failure after 5 seconds with diagnostic message |
| Invalid RTSP URL format | Returns 400 with validation error before attempting connection |
| Camera unreachable | Returns 422 with "Connection refused" or "Host not found" |
| React Query fetch failure | Shows cached data (if available) + error toast |
| Virtual scroll edge cases | Graceful fallback to standard list if < 10 cameras |

### Observability

| Signal | Implementation |
|--------|----------------|
| Test endpoint calls | INFO log: camera name, source_type, success/failure |
| Test failures | WARNING log: full error message, URL (credentials redacted) |
| Cache metrics | React Query DevTools in development |
| Render performance | React Profiler in development builds |

**Prometheus Metrics (existing):**
- `camera_test_requests_total{status="success|failure"}`
- `camera_test_duration_seconds` (histogram)

## Dependencies and Integrations

### Backend Dependencies (Existing)
| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.115+ | API framework |
| opencv-python | 4.8+ | Camera connection, frame capture |
| pydantic | 2.x | Request/response validation |

### Frontend Dependencies (New)
| Package | Version | Purpose | Story |
|---------|---------|---------|-------|
| @tanstack/react-query | ^5.0.0 | API caching, stale-while-revalidate | P6-1.4 |
| @tanstack/react-virtual | ^3.0.0 | Virtual scrolling for lists | P6-1.3 |

### Frontend Dependencies (Existing)
| Package | Version | Purpose |
|---------|---------|---------|
| react | 19.x | UI framework |
| next | 15.x | App framework |
| tailwindcss | 4.x | Styling |

### Integration Points
| Integration | Type | Notes |
|-------------|------|-------|
| OpenCV VideoCapture | Internal | Reuses existing camera_service connection logic |
| Camera Form UI | Internal | Add "Test Connection" button before save |
| Camera List Component | Internal | Wrap with virtualization container |
| Existing `/cameras/{id}/test` | Backward compatible | Keep for testing saved cameras |

## Acceptance Criteria (Authoritative)

### Story P6-1.1: Pre-Save Connection Test Endpoint
| AC# | Criterion |
|-----|-----------|
| AC1 | POST `/api/v1/cameras/test` endpoint accepts camera config in request body |
| AC2 | Validates RTSP URL format before attempting connection |
| AC3 | Tests actual connection to camera with 5-second timeout |
| AC4 | Returns stream info (resolution, FPS, codec) on success |
| AC5 | Returns diagnostic error message on failure |
| AC6 | Returns preview thumbnail (base64) on success |
| AC7 | No database record created during test |

### Story P6-1.2: React.memo CameraPreview
| AC# | Criterion |
|-----|-----------|
| AC8 | CameraPreview wrapped with React.memo |
| AC9 | Custom comparison function compares camera.id, camera.is_enabled, and preview timestamp |
| AC10 | Component re-renders only when camera data or preview changes |
| AC11 | No visual regression in camera preview display |

### Story P6-1.3: Virtual Scrolling
| AC# | Criterion |
|-----|-----------|
| AC12 | @tanstack/react-virtual integrated for camera list |
| AC13 | Only visible camera cards (+ overscan) rendered to DOM |
| AC14 | Smooth 60fps scrolling performance with 50+ cameras |
| AC15 | Works with existing camera filtering and sorting |

### Story P6-1.4: React Query Caching
| AC# | Criterion |
|-----|-----------|
| AC16 | TanStack Query configured for camera list endpoint |
| AC17 | Stale time set to 30 seconds |
| AC18 | Background refetch on window focus |
| AC19 | Cache invalidated on camera create/update/delete mutations |
| AC20 | Reduced API calls observed during page navigation |

## Traceability Mapping

| AC | Spec Section | Component/API | Test Approach |
|----|--------------|---------------|---------------|
| AC1-AC7 | APIs and Interfaces | `POST /cameras/test` | Integration test: call endpoint with valid/invalid configs |
| AC2 | Data Models | `CameraTestRequest` | Unit test: Pydantic validation |
| AC3 | Workflows | `camera_service.py` | Unit test: mock OpenCV, verify timeout |
| AC4-AC6 | Data Models | `CameraTestResponse` | Integration test: verify response shape |
| AC7 | Workflows | `cameras.py` | Integration test: verify no DB records after test |
| AC8-AC11 | Services and Modules | `CameraPreview.tsx` | Unit test: React Testing Library, verify render count |
| AC12-AC15 | Services and Modules | `CamerasPage.tsx` | E2E test: Playwright scroll test with 50 mock cameras |
| AC16-AC20 | Services and Modules | `api-client.ts` | Integration test: verify cache behavior with React Query DevTools |

## Risks, Assumptions, Open Questions

### Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| **R1**: React Query may conflict with existing fetch patterns | Medium | Gradually migrate; can coexist with native fetch |
| **R2**: Virtual scrolling may break camera card interactions | Medium | Thorough QA; keep standard list as fallback for < 10 cameras |
| **R3**: Connection test may hang on some RTSP implementations | Low | Strict 5-second timeout; return partial info if available |

### Assumptions
| Assumption | Validation |
|------------|------------|
| **A1**: Users will test connections before saving | UX research shows this is common pattern |
| **A2**: 20+ cameras is the threshold for performance issues | Based on IMP-005 backlog description |
| **A3**: TanStack libraries are stable for production use | Widely adopted; 5M+ weekly downloads |

### Open Questions
| Question | Owner | Status |
|----------|-------|--------|
| **Q1**: Should we remove SWR entirely or keep both? | Dev Team | Open - decide during P6-1.4 |
| **Q2**: What overscan value for virtual scrolling? | Dev Team | Open - start with 5, tune based on testing |
| **Q3**: Should test endpoint support Protect cameras? | PM | Deferred - Protect uses different connection method |

## Test Strategy Summary

### Test Levels

| Level | Framework | Coverage |
|-------|-----------|----------|
| Unit (Backend) | pytest | CameraTestRequest validation, connection logic |
| Unit (Frontend) | Vitest + RTL | CameraPreview memo, React Query hooks |
| Integration | pytest + TestClient | `/cameras/test` endpoint with mock cameras |
| E2E | Playwright | Virtual scroll performance, full add-camera flow |

### Test Cases by Story

**P6-1.1 (Backend Test Endpoint)**
- Valid RTSP config → success response with thumbnail
- Invalid RTSP URL format → 400 validation error
- Unreachable camera → 422 with diagnostic message
- USB camera config → success response
- Missing required fields → 400 validation error
- Verify no DB records created

**P6-1.2 (React.memo)**
- Verify render count with unchanged props
- Verify re-render on camera.is_enabled change
- Verify re-render on preview update
- Visual regression snapshot test

**P6-1.3 (Virtual Scrolling)**
- Scroll performance with 50 cameras
- Verify only visible items in DOM
- Filter/sort maintains scroll position
- Keyboard navigation works

**P6-1.4 (React Query)**
- Cache hit on repeated navigation
- Cache invalidation on mutation
- Background refetch on focus
- Error state with stale data

### Coverage Targets
- Backend: > 80% line coverage for new endpoint
- Frontend: > 70% coverage for new hooks/components
- E2E: Happy path for all 4 stories
