# Story 9.2.5: Store All Analysis Frames to Filesystem

Status: done

## Story

As a **system**,
I want **to persist all frames used for AI analysis**,
So that **users can review what the AI saw**.

## Acceptance Criteria

1. **AC-2.5.1:** Given event analyzed with 10 frames, when complete, then all saved to `data/frames/{event_id}/`
2. **AC-2.5.2:** Given frames saved, when viewing, then named `frame_001.jpg`, `frame_002.jpg`, etc.
3. **AC-2.5.3:** Given frames saved, when stored, then metadata (timestamp) stored in EventFrame records
4. **AC-2.5.4:** Given event deleted, when cleanup runs, then associated frames deleted

## Tasks / Subtasks

- [x] Task 1: Create frame storage service (AC: 2.5.1, 2.5.2)
  - [x] Create `FrameStorageService` class
  - [x] Implement `save_frames()` method
  - [x] Save to data/frames/{event_id}/frame_NNN.jpg
- [x] Task 2: Create EventFrame model (AC: 2.5.3)
  - [x] Add EventFrame model with frame_path, timestamp_offset_ms, etc.
  - [x] Add relationship to Event model
- [x] Task 3: Integrate with protect_event_handler (AC: 2.5.1)
  - [x] Call frame_storage_service.save_frames() after extraction
  - [x] Store frame metadata in database
- [x] Task 4: Add cleanup on event deletion (AC: 2.5.4)
  - [x] Delete frame files when event is deleted
  - [x] Cascade delete EventFrame records
- [x] Task 5: Write tests
- [x] Task 6: Run all tests to verify

**Note:** This story was already implemented as part of Phase 8 (Story P8-2.1). All functionality verified as working.

## Dev Notes

### Technical Approach

The frame_storage_service saves frames as JPEG files (quality 85) in `data/frames/{event_id}/` directory. Each frame has a corresponding EventFrame database record with metadata.

### Source Components

- `backend/app/services/frame_storage_service.py` - Frame storage service
- `backend/app/models/event_frame.py` - EventFrame model
- `backend/app/services/protect_event_handler.py` - Integration (line 2017-2025)

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-2.md#P9-2.5]
- [Source: docs/epics-phase9.md#Story P9-2.5]
- [Backlog: IMP-006]

## Dev Agent Record

### Context Reference

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

### File List

- `backend/app/services/frame_storage_service.py` - Frame storage service implementation
- `backend/app/models/event_frame.py` - EventFrame database model
- `backend/tests/test_services/test_frame_storage_service.py` - Unit tests

