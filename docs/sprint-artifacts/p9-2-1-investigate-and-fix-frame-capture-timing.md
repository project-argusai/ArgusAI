# Story 9.2.1: Investigate and Fix Frame Capture Timing

Status: done

## Story

As a **user**,
I want **captured frames to show the actual motion activity**,
So that **AI descriptions match what triggered the event**.

## Acceptance Criteria

1. **AC-2.1.1:** Given a motion event triggers, when frames are extracted, then at least 80% show the subject in frame
2. **AC-2.1.2:** Given timing offset is configurable, when I set offset to 3000ms, then extraction starts 3 seconds into clip
3. **AC-2.1.3:** Given default offset, when person event occurs, then person is visible in majority of frames
4. **AC-2.1.4:** Given default offset, when vehicle event occurs, then vehicle is visible in majority of frames
5. **AC-2.1.5:** Given extraction fails, when error occurs, then fallback to 0 offset with warning

## Tasks / Subtasks

- [x] Task 1: Investigate current frame extraction timing (AC: 2.1.1)
  - [x] Review frame_extraction_service.py
  - [x] Analyze timing between event trigger and frame extraction
  - [x] Document current behavior
- [x] Task 2: Add configurable extraction offset (AC: 2.1.2)
  - [x] Add frame_extraction_offset_ms to system settings
  - [x] Implement offset logic in frame extraction service
  - [x] Add default offset of 2000ms
- [x] Task 3: Apply offset in frame extraction pipeline (AC: 2.1.3, 2.1.4)
  - [x] Modify frame extraction to skip initial frames
  - [x] Test with person and vehicle events
  - [x] Verify subjects are visible in extracted frames
- [x] Task 4: Add error handling for offset edge cases (AC: 2.1.5)
  - [x] Handle clips shorter than offset
  - [x] Fall back to 0 offset with warning
  - [x] Log timing information for debugging
- [x] Task 5: Write unit tests
- [x] Task 6: Run all tests to verify

## Dev Notes

### Technical Approach

The frame extraction service currently extracts frames starting at time 0 of the video clip. However, Protect events often trigger at the moment motion is first detected, meaning the subject may still be entering the frame. By adding a configurable offset (default 2000ms), we can skip the initial frames and capture the subject when they're fully visible.

### Architecture Pattern

```
Protect Event → Clip Download → Apply Offset → Frame Extraction
                                    ↓
                       Skip first N milliseconds
                                    ↓
                         Extract remaining frames
```

### Source Components

- `backend/app/services/frame_extraction_service.py` - Add offset logic
- `backend/app/models/settings.py` - Add frame_extraction_offset_ms setting
- `backend/app/api/v1/system.py` - Expose new setting

### Testing Standards

- Unit tests for offset calculation
- Integration tests with sample video clips
- Edge case testing for short clips

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-2.md#P9-2.1]
- [Source: docs/epics-phase9.md#Story P9-2.1]
- [Backlog: IMP-011]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

### File List

- `backend/app/services/frame_extractor.py` - Added `offset_ms` parameter to `extract_frames_with_timestamps()`
- `backend/app/services/protect_event_handler.py` - Added setting read and offset pass-through
- `backend/tests/test_services/test_frame_extractor.py` - Added 4 new tests for offset functionality

