# Story P6-1.1: Implement Pre-Save Connection Test Endpoint

Status: done

## Story

As a user setting up a new camera,
I want to test the RTSP/USB connection before saving the camera to the database,
so that I can verify my credentials and URL are correct without creating an incomplete camera record.

## Acceptance Criteria

1. POST `/api/v1/cameras/test` endpoint created (accepts camera config in body)
2. Validates RTSP URL format and credentials
3. Tests actual connection to camera
4. Returns stream info (resolution, FPS, codec) on success
5. Returns diagnostic error message on failure
6. Returns preview thumbnail on success
7. No database record created during test

## Tasks / Subtasks

- [x] Task 1: Create pre-save test endpoint (AC: 1, 7)
  - [x] 1.1: Create new `CameraTestRequest` schema accepting camera config without requiring ID
  - [x] 1.2: Create new `CameraTestDetailedResponse` schema with stream info fields
  - [x] 1.3: Add `POST /api/v1/cameras/test` endpoint at collection level (before `/{camera_id}`)
  - [x] 1.4: Ensure endpoint does NOT create any database record

- [x] Task 2: Implement URL validation (AC: 2)
  - [x] 2.1: Validate RTSP URL format (must start with `rtsp://` or `rtsps://`)
  - [x] 2.2: Validate USB device index is non-negative integer
  - [x] 2.3: Return 422 with clear message for invalid format

- [x] Task 3: Implement connection test logic (AC: 3, 5)
  - [x] 3.1: Build connection string with credentials (reuse `_build_rtsp_url` pattern)
  - [x] 3.2: Use PyAV for secure RTSP (`rtsps://`) streams
  - [x] 3.3: Use OpenCV for standard RTSP and USB cameras
  - [x] 3.4: Return specific error messages for common failures (auth, timeout, refused)

- [x] Task 4: Extract and return stream info (AC: 4)
  - [x] 4.1: Extract resolution (width x height) from captured stream
  - [x] 4.2: Extract FPS from stream if available
  - [x] 4.3: Extract codec info from stream if available
  - [x] 4.4: Include stream info in response schema

- [x] Task 5: Generate and return thumbnail (AC: 6)
  - [x] 5.1: Capture test frame from stream
  - [x] 5.2: Resize to thumbnail (240px height, maintain aspect ratio)
  - [x] 5.3: Encode as JPEG base64 with data URI prefix
  - [x] 5.4: Include in response on success

- [x] Task 6: Write tests (All ACs)
  - [x] 6.1: Add unit test for valid RTSP URL validation
  - [x] 6.2: Add unit test for USB device index validation
  - [x] 6.3: Add integration test for successful connection (mock)
  - [x] 6.4: Add integration test for connection failure (mock)
  - [x] 6.5: Verify no database records created during test

## Dev Notes

### Relevant Architecture Patterns

**Existing Camera Test Pattern (for comparison):**
The existing `POST /cameras/{camera_id}/test` endpoint at `backend/app/api/v1/cameras.py:416-597` tests an already-saved camera. The new endpoint should:
- Accept camera config directly in request body (not from database)
- Reuse the same connection logic (PyAV for rtsps://, OpenCV for rtsp:// and USB)
- NOT persist anything to database

**Connection String Building:**
```python
# Existing pattern from camera_service._build_rtsp_url
if camera.username:
    password = camera.get_decrypted_password() if camera.password else ""
    if "://" in rtsp_url:
        protocol, rest = rtsp_url.split("://", 1)
        creds = camera.username
        if password:
            creds += f":{password}"
        rtsp_url = f"{protocol}://{creds}@{rest}"
```

**New Request Schema Pattern:**
```python
class CameraTestRequest(BaseModel):
    """Schema for testing camera connection before saving"""
    type: Literal['rtsp', 'usb']
    rtsp_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # Plain text, not persisted
    device_index: Optional[int] = None
```

**New Response Schema Pattern:**
```python
class CameraTestDetailedResponse(BaseModel):
    """Schema for pre-save camera connection test response"""
    success: bool
    message: str
    thumbnail: Optional[str] = None  # Base64 JPEG with data URI
    resolution: Optional[str] = None  # "1920x1080"
    fps: Optional[float] = None
    codec: Optional[str] = None
```

### Project Structure Notes

Files to create/modify:
- `backend/app/schemas/camera.py` - Add `CameraTestRequest` and `CameraTestDetailedResponse` schemas
- `backend/app/api/v1/cameras.py` - Add new `POST /cameras/test` endpoint before `/{camera_id}` routes
- `backend/tests/test_api/test_cameras.py` - Add tests for new endpoint

**Route Order Important:** The new `POST /cameras/test` must be defined BEFORE `POST /cameras/{camera_id}/test` in the router to avoid path parameter conflict.

### Stream Info Extraction

**OpenCV Stream Info:**
```python
cap = cv2.VideoCapture(connection_str)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)
fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
```

**PyAV Stream Info:**
```python
container = av.open(connection_str, options={'rtsp_transport': 'tcp'})
stream = container.streams.video[0]
width = stream.codec_context.width
height = stream.codec_context.height
fps = float(stream.average_rate) if stream.average_rate else None
codec = stream.codec_context.name
```

### Error Message Patterns

Follow existing diagnostic patterns from `cameras.py:568-592`:
- Auth errors: "Authentication failed. Check username and password."
- Timeout: "Connection timeout. Check IP address and network connectivity."
- Refused: "Connection refused. Check port number and camera RTSP service."
- USB not found: "USB camera not found at device index {n}. Check that camera is connected."
- USB permission: "Permission denied for USB camera. On Linux, add user to 'video' group."

### References

- [Source: docs/epics-phase6.md#P6-1.1] - Story definition and acceptance criteria
- [Source: docs/architecture/07-api-contracts.md#Cameras] - API patterns
- [Source: backend/app/api/v1/cameras.py:416-597] - Existing test endpoint pattern
- [Source: backend/app/schemas/camera.py] - Existing camera schemas
- GitHub Issue: #55

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p6-1-1-implement-pre-save-connection-test-endpoint.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- Implemented `CameraTestRequest` schema with validation for RTSP URLs and USB device indices
- Implemented `CameraTestDetailedResponse` schema with stream info fields (resolution, fps, codec, thumbnail)
- Added `POST /api/v1/cameras/test` endpoint before `/{camera_id}` routes to avoid path conflicts
- Endpoint extracts stream info using OpenCV CAP_PROP constants and PyAV codec context
- Thumbnail generated at 240px height with aspect ratio preservation
- Diagnostic error messages for auth failures, timeouts, connection refused, USB not found
- 13 new tests added covering all acceptance criteria
- All 61 camera API tests pass

### File List

- backend/app/schemas/camera.py (modified - added CameraTestRequest and CameraTestDetailedResponse schemas)
- backend/app/api/v1/cameras.py (modified - added POST /cameras/test endpoint, updated imports)
- backend/tests/test_api/test_cameras.py (modified - added TestCameraPreSaveTestAPI with 13 tests)
- docs/sprint-artifacts/p6-1-1-implement-pre-save-connection-test-endpoint.md (modified - story file)
- docs/sprint-artifacts/p6-1-1-implement-pre-save-connection-test-endpoint.context.xml (created - context file)
- docs/sprint-artifacts/sprint-status.yaml (modified - status updates)

## Change Log

| Date | Change |
|------|--------|
| 2025-12-16 | Story drafted from epics-phase6.md |
| 2025-12-16 | Implementation complete - all tasks done, 13 tests added, all 61 camera tests pass |
