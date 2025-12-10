# Story P3-7.5: Display Key Frames Gallery on Event Detail

## Story

**As a** user viewing event details,
**I want** to see the frames used for AI analysis,
**So that** I understand what the AI saw when generating the description.

## Status: done

## Acceptance Criteria

### AC1: Multi-Frame Gallery Display
- [x] Given event analyzed with multi_frame mode
- [x] When event detail view opened
- [x] Then shows gallery of extracted frames
- [x] And frames displayed in chronological order
- [x] And timestamp overlay on each frame

### AC2: Single-Frame Display
- [x] Given event used single_frame mode
- [x] When detail view opened
- [x] Then shows single thumbnail (current behavior)
- [x] And labeled "Single frame analysis"

### AC3: Video Native Display
- [x] Given event used video_native mode
- [x] When detail view opened
- [x] Then shows "Full video analyzed" indicator
- [x] And optionally shows video player or key frame thumbnails

### AC4: Frame Storage Setting
- [x] Given frames not stored (storage disabled)
- [x] When detail view opened
- [x] Then shows "Frames not stored" message
- [x] And explains storage setting

### AC5: Frame Gallery UI
- [x] Given multi-frame event with stored frames
- [x] When gallery displayed
- [x] Then frames are clickable for enlarged view
- [x] And current frame index shown (e.g., "1 of 5")
- [x] And keyboard navigation supported (left/right arrows)

### AC6: Backend Key Frames Storage
- [x] Given AI analysis completes with multi_frame mode
- [x] When event is saved
- [x] Then key_frames_base64 field stores JSON array of frame thumbnails
- [x] And frame_timestamps stores extraction timestamps
- [x] And storage is conditional on STORE_ANALYSIS_FRAMES setting

## Tasks / Subtasks

- [ ] **Task 1: Add Key Frames Fields to Event Model** (AC: 6)
  - [ ] Add `key_frames_base64` field to Event model (Text, nullable, JSON array of base64 strings)
  - [ ] Add `frame_timestamps` field to Event model (Text, nullable, JSON array of float seconds)
  - [ ] Create Alembic migration for new columns
  - [ ] Update EventResponse schema to include new fields

- [ ] **Task 2: Add STORE_ANALYSIS_FRAMES System Setting** (AC: 4, 6)
  - [ ] Add `STORE_ANALYSIS_FRAMES` to system settings (default: true)
  - [ ] Add to settings API response and update schema
  - [ ] Add UI toggle in settings page if not already present

- [ ] **Task 3: Integrate Frame Storage into Event Pipeline** (AC: 6)
  - [ ] Modify `event_processor.py` to store frames when setting enabled
  - [ ] Convert extracted frames to smaller thumbnails for storage (max 320px width)
  - [ ] Store as base64 JSON array in event record
  - [ ] Calculate and store frame timestamps from extraction

- [ ] **Task 4: Build KeyFramesGallery React Component** (AC: 1, 5)
  - [ ] Create `frontend/components/events/KeyFramesGallery.tsx`
  - [ ] Display frames in horizontal scrollable gallery
  - [ ] Show timestamp overlay on each frame
  - [ ] Add click-to-enlarge modal functionality
  - [ ] Implement keyboard navigation (left/right arrows)
  - [ ] Show frame index (e.g., "Frame 1 of 5")

- [ ] **Task 5: Integrate Gallery into EventDetailModal** (AC: 1, 2, 3, 4)
  - [ ] Modify `EventDetailModal.tsx` to include KeyFramesGallery
  - [ ] Conditional rendering based on analysis_mode:
    - multi_frame → show gallery
    - single_frame → show existing thumbnail with "Single frame analysis" label
    - video_native → show "Full video analyzed" with optional frames
  - [ ] Show "Frames not stored" when key_frames_base64 is null/empty
  - [ ] Style to fit within existing modal layout

- [ ] **Task 6: Update IEvent TypeScript Type** (AC: 1, 2, 3, 4)
  - [ ] Add `key_frames_base64?: string[] | null` to IEvent interface
  - [ ] Add `frame_timestamps?: number[] | null` to IEvent interface
  - [ ] Update API client type generation if needed

- [ ] **Task 7: Write Backend Tests** (AC: 6)
  - [ ] Test frame storage when setting enabled
  - [ ] Test frame storage skipped when setting disabled
  - [ ] Test frame thumbnail generation (size reduction)
  - [ ] Test frame_timestamps calculation

- [ ] **Task 8: Write Frontend Tests** (AC: 1, 5)
  - [ ] Test KeyFramesGallery renders with frames
  - [ ] Test keyboard navigation
  - [ ] Test click-to-enlarge behavior
  - [ ] Test empty state rendering

## Dev Notes

### Relevant Architecture Patterns and Constraints

**From Architecture:**
- Event model already has `analysis_mode` field (single_frame/multi_frame/video_native)
- Event model has `frame_count_used` tracking number of frames sent to AI
- Thumbnails stored as base64 in `thumbnail_base64` or path in `thumbnail_path`
- Follow same pattern for key frames: store as base64 JSON array

**From FrameExtractor Service (backend/app/services/frame_extractor.py):**
- Extracts frames at `FRAME_MAX_WIDTH = 1280` for AI analysis
- For storage, reduce to ~320px thumbnails to minimize database bloat
- Frames already JPEG encoded at 85% quality
- Use lower quality (70%) for stored thumbnails

**Storage Size Estimation:**
- 5 frames at 320px width ≈ 15-30KB each ≈ 75-150KB total per event
- Base64 encoding adds ~33% overhead ≈ 100-200KB per event
- Acceptable for SQLite with typical event volumes

### Project Structure Notes

**Files to Create:**
```
frontend/components/events/KeyFramesGallery.tsx
backend/alembic/versions/026_add_event_key_frames_fields.py
backend/tests/test_services/test_key_frames_storage.py
frontend/__tests__/components/events/KeyFramesGallery.test.tsx
```

**Files to Modify:**
```
backend/app/models/event.py              # Add key_frames_base64, frame_timestamps
backend/app/schemas/event.py             # Add fields to EventResponse
backend/app/services/event_processor.py  # Store frames when enabled
frontend/components/events/EventDetailModal.tsx  # Integrate gallery
frontend/types/event.ts                  # Update IEvent interface
```

### Learnings from Previous Story

**From Story p3-7-4-add-cost-alerts-and-notifications (Status: done)**

- **CostAlertService Created**: `backend/app/services/cost_alert_service.py` - follows singleton pattern
- **SystemNotification Model**: Created for system-level notifications at `backend/app/models/system_notification.py`
- **Migration Pattern**: Migration 025 added - continue with 026 for this story
- **Event Pipeline Pattern**: Cost alert check added at `event_processor.py:678-693` - add frame storage nearby
- **Test Coverage**: 25 tests for cost alerts following mocking patterns
- **WebSocket Broadcasting**: COST_ALERT type added - no new broadcast needed for this story

[Source: docs/sprint-artifacts/p3-7-4-add-cost-alerts-and-notifications.md#Dev-Agent-Record]

### References

- [Source: docs/epics-phase3.md#Story-P3-7.5] - Story definition: Display Key Frames Gallery on Event Detail
- [Source: docs/epics-phase3.md#FR39] - Functional requirement: Event cards can display key frames used for analysis
- [Source: backend/app/services/frame_extractor.py] - Frame extraction service with JPEG encoding
- [Source: backend/app/models/event.py] - Event model with analysis_mode, frame_count_used fields
- [Source: frontend/components/events/EventDetailModal.tsx] - Current event detail modal implementation
- [Source: docs/architecture.md#Event-Model] - Event model architecture

## Dependencies

- **Prerequisites Met:**
  - P3-2.6 (Multi-frame integration) - provides analysis_mode, frame_count_used
  - FrameExtractor service operational
  - EventDetailModal exists and functional

## Estimate

**Small-Medium** - Backend field additions straightforward, frontend gallery component is main effort

## Definition of Done

- [ ] Key frames stored in database when STORE_ANALYSIS_FRAMES enabled
- [ ] EventDetailModal displays frame gallery for multi_frame events
- [ ] Single-frame events show thumbnail with appropriate label
- [ ] Video-native events show appropriate indicator
- [ ] Frames not stored shows explanatory message
- [ ] Gallery supports click-to-enlarge and keyboard navigation
- [ ] All backend tests pass
- [ ] All frontend tests pass
- [ ] No TypeScript errors
- [ ] No ESLint warnings from this story

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p3-7-5-display-key-frames-gallery-on-event-detail.context.xml

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Change Log

- 2025-12-10: Story drafted from sprint-status backlog (status: backlog → drafted)
