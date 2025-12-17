# Story P6-3.1: Add Audio Stream Extraction from RTSP

Status: review

## Story

As a system administrator,
I want to enable audio stream extraction from RTSP cameras,
so that future audio-based event detection features (like glass break or doorbell sounds) can be built on this foundation.

## Acceptance Criteria

1. Audio stream detected and extracted from RTSP feeds using PyAV
2. Supports common audio codecs (AAC, G.711/PCMU, Opus)
3. Audio buffer maintained separate from video capture
4. Can be enabled/disabled per camera via configuration
5. No impact on video capture performance when audio is disabled

## Tasks / Subtasks

- [x] Task 1: Add audio configuration fields to Camera model (AC: #4)
  - [x] Add `audio_enabled` boolean field to Camera model (default: False)
  - [x] Add `audio_codec` field to store detected codec type
  - [x] Create Alembic migration for new fields
  - [x] Update Camera schema to include audio fields in API responses
- [x] Task 2: Implement AudioStreamExtractor service (AC: #1, #2, #3)
  - [x] Create `backend/app/services/audio_stream_service.py`
  - [x] Implement audio stream detection from RTSP using PyAV
  - [x] Add codec detection and validation (AAC, G.711, Opus)
  - [x] Implement thread-safe audio buffer ring buffer (configurable size)
  - [x] Add method to get latest audio chunk for processing
- [x] Task 3: Integrate audio extraction into camera capture (AC: #1, #3, #5)
  - [x] Modify `_capture_loop` in `camera_service.py` to optionally extract audio
  - [x] Use PyAV to demux both video and audio streams
  - [x] Ensure audio extraction runs in same thread as video (no performance impact when disabled)
  - [x] Add performance monitoring for audio extraction overhead
- [x] Task 4: Add camera API endpoints for audio configuration (AC: #4)
  - [x] Add PATCH endpoint to enable/disable audio per camera
  - [x] Add GET endpoint to check audio stream availability for a camera
  - [x] Return audio codec info in camera details response
- [x] Task 5: Write tests (AC: #1-5)
  - [x] Unit tests for AudioStreamExtractor with mock RTSP stream
  - [x] Test codec detection for AAC, G.711, Opus
  - [x] Test audio buffer operations (add, get, overflow handling)
  - [x] Integration test for audio enable/disable toggle
  - [x] Performance test verifying no impact when audio disabled

## Dev Notes

- This is a foundational story for future audio event detection (P6-3.2, P6-3.3)
- PyAV (already in project) supports demuxing audio from RTSP containers
- Audio data should be stored in memory buffer only (not persisted to disk initially)
- Target audio buffer: ~5 seconds of audio for real-time analysis window
- Common RTSP audio codecs: AAC (most common), G.711/PCMU (legacy), Opus (modern)

### Project Structure Notes

- New file: `backend/app/services/audio_stream_service.py`
- Modified: `backend/app/services/camera_service.py` (add audio extraction)
- Modified: `backend/app/models/camera.py` (add audio fields)
- Migration: `backend/alembic/versions/817c9e3ec7f6_add_audio_fields_to_camera.py`

### Learnings from Previous Story

**From Story p6-2-2-audit-and-fix-remaining-aria-issues (Status: done)**

- **Testing Pattern**: Use comprehensive unit tests for new service components
- **Build Verification**: Always run `npm run build` and `npm run lint` before marking complete
- **PyAV Already Available**: PyAV is imported in camera_service.py for secure RTSP - can reuse for audio
- **Thread Safety**: Camera service uses locks for frame access - same pattern should be used for audio buffer

[Source: docs/sprint-artifacts/p6-2-2-audit-and-fix-remaining-aria-issues.md#Dev-Agent-Record]

### References

- [Source: docs/epics-phase6.md#Story P6-3.1]
- [Source: docs/backlog.md#FF-015] - Audio Capture from Cameras
- [Source: backend/app/services/camera_service.py] - Existing PyAV integration for video
- [Source: PyAV Documentation](https://pyav.org/docs/stable/)

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p6-3-1-add-audio-stream-extraction-from-rtsp.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- All 27 audio service tests pass
- All 81 camera service + API tests pass
- Audio extraction integrates with existing PyAV RTSP handling in capture loop
- Thread-safe ring buffer implementation with configurable duration
- Codec detection supports AAC, PCMU, PCMA, Opus, MP3, PCM
- API endpoints: GET/PATCH /{camera_id}/audio, POST /{camera_id}/audio/test

### File List

- backend/app/services/audio_stream_service.py (new)
- backend/app/services/camera_service.py (modified)
- backend/app/models/camera.py (modified)
- backend/app/schemas/camera.py (modified)
- backend/app/api/v1/cameras.py (modified)
- backend/alembic/versions/817c9e3ec7f6_add_audio_fields_to_camera.py (new)
- backend/tests/test_services/test_audio_stream_service.py (new)

## Change Log

- 2025-12-17: Story drafted (P6-3.1)
- 2025-12-17: Implementation complete, all tests passing, ready for review
