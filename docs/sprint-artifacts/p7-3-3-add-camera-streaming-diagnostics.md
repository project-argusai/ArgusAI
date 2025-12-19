# Story P7-3.3: Add Camera Streaming Diagnostics

Status: done

## Story

As a **homeowner troubleshooting HomeKit camera streaming**,
I want **visibility into active streams, ffmpeg commands, and stream test capabilities**,
so that **I can diagnose and resolve camera streaming issues in Apple Home app**.

## Story Key
p7-3-3-add-camera-streaming-diagnostics

## Acceptance Criteria

| AC# | Criteria | Verification |
|-----|----------|--------------|
| AC1 | Stream start/stop events logged | Unit: Verify log entries contain session_id, camera_id, quality on start/stop |
| AC2 | Active streams shown in HomeKit status panel | Integration: GET /api/v1/homekit/status includes stream_diagnostics with per-camera stream info |
| AC3 | ffmpeg command displayed for debugging | Integration: POST /api/v1/homekit/cameras/{id}/test-stream returns ffmpeg_command in response |
| AC4 | Stream test button added in camera settings | E2E: Click test button in HomeKitSettings, see stream test results |

## Tasks / Subtasks

### Task 1: Enhance Stream Logging (AC: 1)
- [x] 1.1 Add structured logging on stream start with: session_id, camera_id, quality, client_address, resolution, fps, bitrate
- [x] 1.2 Add structured logging on stream stop with: session_id, camera_id, duration_seconds, reason (normal/timeout/error)
- [x] 1.3 Add logging when stream rejected due to concurrent limit (already exists, verify format)
- [x] 1.4 Capture and log ffmpeg stderr on stream failure

### Task 2: Implement Stream Diagnostics API (AC: 2, 3)
- [x] 2.1 Add `StreamDiagnostics` schema to `backend/app/schemas/homekit_diagnostics.py`
- [x] 2.2 Update `GET /api/v1/homekit/status` response to include `stream_diagnostics` with per-camera info
- [x] 2.3 Create `POST /api/v1/homekit/cameras/{camera_id}/test-stream` endpoint
- [x] 2.4 Implement stream test logic: verify RTSP accessible, check ffmpeg compatibility, return diagnostics
- [x] 2.5 Return ffmpeg_command string (sanitized - no SRTP keys) in test-stream response

### Task 3: Add Active Stream Tracking to HomeKit Service (AC: 2)
- [x] 3.1 Add `get_stream_diagnostics()` method to HomeKitService returning per-camera stream status
- [x] 3.2 Track active stream count, start time, and quality per camera accessory
- [x] 3.3 Include stream info in HomekitStatus dataclass

### Task 4: Create Stream Test Frontend UI (AC: 4)
- [x] 4.1 Add `useHomekitTestStream` hook in `frontend/hooks/useHomekitStatus.ts`
- [x] 4.2 Add stream test button to HomeKitSettings camera section
- [x] 4.3 Display test results: RTSP accessible, ffmpeg compatible, estimated latency, ffmpeg command
- [x] 4.4 Show test loading state and error handling

### Task 5: Unit and Integration Tests
- [x] 5.1 Unit test: Stream start/stop logging includes required fields
- [x] 5.2 Unit test: get_stream_diagnostics() returns correct per-camera info
- [x] 5.3 Integration test: GET /api/v1/homekit/status includes stream_diagnostics
- [x] 5.4 Integration test: POST /api/v1/homekit/cameras/{id}/test-stream returns expected fields
- [x] 5.5 Unit test: ffmpeg_command is sanitized (no SRTP keys exposed)

## Dev Notes

### Existing Implementation Analysis

**Stream logging already exists in `homekit_camera.py`:**
- Lines 318-326: Logs on stream start with camera_id, session_id, client_address, video_port
- Lines 347-354: Logs on stream success with PID, quality
- Lines 384-387: Logs on stream stop with camera_id, session_id
- Lines 289-301: Logs on stream rejection (max concurrent reached)

**What's missing:**
- Stream diagnostics API endpoint (`test-stream`)
- Per-camera stream info in status response
- Frontend UI for stream testing
- Duration logging on stream stop
- ffmpeg command display for debugging

### Key Files to Modify

**Backend:**
- `backend/app/services/homekit_camera.py` - Add stream tracking, duration logging
- `backend/app/services/homekit_service.py` - Add get_stream_diagnostics() method
- `backend/app/api/v1/homekit.py` - Add test-stream endpoint, update status response
- `backend/app/schemas/homekit_diagnostics.py` - Add StreamDiagnostics, StreamTestResponse schemas

**Frontend:**
- `frontend/hooks/useHomekitStatus.ts` - Add useHomekitTestStream hook
- `frontend/components/settings/HomeKitSettings.tsx` - Add stream test button and results display
- `frontend/lib/api-client.ts` - Add testCameraStream method

### API Design

**Updated GET /api/v1/homekit/status response:**
```json
{
  "enabled": true,
  "running": true,
  "camera_count": 3,
  "active_streams": 2,
  "stream_diagnostics": {
    "cameras": [
      {
        "camera_id": "abc-123",
        "camera_name": "Front Door",
        "streaming_enabled": true,
        "snapshot_supported": true,
        "last_snapshot": "2025-12-17T14:30:00Z",
        "active_streams": 1,
        "quality": "medium"
      }
    ]
  }
}
```

**POST /api/v1/homekit/cameras/{camera_id}/test-stream response:**
```json
{
  "success": true,
  "rtsp_accessible": true,
  "ffmpeg_compatible": true,
  "source_resolution": "1920x1080",
  "source_fps": 30,
  "source_codec": "h264",
  "target_resolution": "1280x720",
  "target_fps": 25,
  "target_bitrate": 1500,
  "estimated_latency_ms": 500,
  "ffmpeg_command": "ffmpeg -rtsp_transport tcp -i rtsp://... -vcodec libx264 ..."
}
```

### Architecture Constraints
- ffmpeg command must not include SRTP keys (security)
- Stream test should timeout after 10 seconds
- Maximum 2 concurrent streams per camera (existing limit)
- Test should not interfere with active streams

### Testing Strategy
- Unit tests mock ffmpeg subprocess and verify logging
- Integration tests verify API response formats
- Frontend tests verify button renders and displays results
- Manual testing with Apple Home app

### Project Structure Notes
- HomeKit services in `backend/app/services/homekit_*.py`
- HomeKit API in `backend/app/api/v1/homekit.py`
- HomeKit schemas in `backend/app/schemas/homekit_diagnostics.py`
- Frontend hooks in `frontend/hooks/useHomekitStatus.ts`

### References
- [Source: docs/sprint-artifacts/tech-spec-epic-P7-3.md#Story-P7-3.3]
- [Source: docs/epics-phase7.md#Story-P7-3.3]
- [Source: backend/app/services/homekit_camera.py#_start_stream]
- [Source: backend/app/services/homekit_camera.py#_stop_stream]

### Learnings from Previous Story

**From Story p7-3-2-add-camera-snapshot-support (Status: done)**

- **Snapshot API Pattern**: Use `GET /api/v1/homekit/cameras/{camera_id}/snapshot` pattern - same path prefix for stream test
- **HomeKitService Integration**: Add method to service (like `get_camera_snapshot()`), call from API endpoint
- **Prometheus Metrics**: Use `record_homekit_*` functions from metrics.py for stream events
- **Test Patterns**: Follow existing test structure in `test_homekit.py` and `test_homekit_camera.py`
- **Logging Pattern**: Use extra dict with structured fields for camera_id, session_id, etc.

[Source: docs/sprint-artifacts/p7-3-2-add-camera-snapshot-support.md#Dev-Agent-Record]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p7-3-3-add-camera-streaming-diagnostics.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Backend tests: 32 passed in test_homekit_camera.py
- TypeScript: Pre-existing errors in test files only (not from this story)
- Lint: 0 errors

### Completion Notes List

- All acceptance criteria met:
  - AC1: Enhanced stream logging with session_id, camera_id, quality, duration, reason
  - AC2: Added get_stream_diagnostics() for per-camera stream info
  - AC3: Added POST /api/v1/homekit/cameras/{id}/test-stream with sanitized ffmpeg command
  - AC4: Added StreamTest component in HomeKitSettings
- Security: SRTP keys properly sanitized from ffmpeg command display
- Architecture: Follows existing patterns from P7-3.2 snapshot implementation

### File List

**Backend:**
- backend/app/schemas/homekit_diagnostics.py - Added CameraStreamInfo, StreamDiagnostics, StreamTestResponse
- backend/app/services/homekit_camera.py - Enhanced stream logging, added sanitize_ffmpeg_command(), get_stream_diagnostics()
- backend/app/services/homekit_service.py - Added get_stream_diagnostics(), test_camera_stream()
- backend/app/api/v1/homekit.py - Added POST /cameras/{camera_id}/test-stream endpoint

**Frontend:**
- frontend/hooks/useHomekitStatus.ts - Added HomekitStreamTestResponse, useHomekitTestStream hook
- frontend/lib/api-client.ts - Added testCameraStream method
- frontend/components/settings/HomeKitSettings.tsx - Added StreamTest component

**Documentation:**
- docs/sprint-artifacts/p7-3-3-add-camera-streaming-diagnostics.md
- docs/sprint-artifacts/p7-3-3-add-camera-streaming-diagnostics.context.xml

## Change Log
| Date | Change |
|------|--------|
| 2025-12-19 | Story drafted from epic P7-3 and tech spec |
| 2025-12-19 | Implementation complete, code review passed |
