# Story P6-3.3: Add Audio Settings to Camera Configuration

Status: done

## Story

As a home owner,
I want to configure audio capture and audio event detection settings per camera,
so that I can enable audio monitoring on specific cameras and choose which sound types to detect.

## Acceptance Criteria

1. Toggle to enable/disable audio capture per camera in camera form
2. Audio event type selection (checkboxes for which sounds to detect: glass_break, gunshot, scream, doorbell)
3. Sensitivity/confidence threshold slider per camera (override global default)
4. Audio indicator in camera status showing when audio capture is active

## Tasks / Subtasks

- [x] Task 1: Create AudioSettingsSection component (AC: #1, #2, #3)
  - [x] Create `frontend/components/cameras/AudioSettingsSection.tsx`
  - [x] Add toggle switch for `audio_enabled` field
  - [x] Add checkbox group for audio event type selection
  - [x] Add slider for confidence threshold override (0-100%)
  - [x] Show/hide audio event options based on `audio_enabled` state
  - [x] Add collapsible section styling consistent with MotionSettingsSection

- [x] Task 2: Extend CameraForm to include audio settings (AC: #1, #2, #3)
  - [x] Import and add AudioSettingsSection to CameraForm.tsx
  - [x] Add audio fields to form default values
  - [x] Update form validation schema in `lib/validations/camera.ts`
  - [x] Ensure audio settings only shown for RTSP cameras (audio not supported for USB)

- [x] Task 3: Update frontend types and API client (AC: #1, #2, #3)
  - [x] Add `audio_enabled`, `audio_event_types`, `audio_threshold` to ICamera interface
  - [x] Add fields to ICameraCreate and ICameraUpdate interfaces
  - [x] Ensure API client handles new fields in camera CRUD operations

- [x] Task 4: Extend Camera model and schema (AC: #1, #2, #3)
  - [x] Add `audio_event_types` (JSON array) column to Camera model
  - [x] Add `audio_threshold` (float, nullable) column for per-camera override
  - [x] Create Alembic migration for new columns
  - [x] Update CameraResponse schema to include audio event settings
  - [x] Update CameraUpdate schema to accept audio event settings
  - [x] Update CameraCreate schema to accept audio event settings

- [x] Task 5: Add audio indicator to camera status (AC: #4)
  - [x] Update CameraPreviewCard.tsx
  - [x] Add audio icon/indicator when `audio_enabled` is true
  - [x] Show detected audio codec if available (via title tooltip)
  - [x] Use Volume2 icon from lucide-react

- [x] Task 6: Write tests (AC: #1-4)
  - [x] Frontend: Test AudioSettingsSection toggle and checkbox behavior (15 tests)
  - [x] Frontend: Test audio indicator visibility based on audio_enabled
  - [x] Backend: Test migration applies/reverts correctly (049_add_camera_audio_settings.py)
  - [x] Backend: Test camera API with audio settings in request/response (9 tests)

## Dev Notes

- This story builds on P6-3.1 (Audio Stream Extraction) and P6-3.2 (Audio Event Detection Pipeline)
- The backend already has `audio_enabled` field on Camera model from P6-3.1
- Audio event types: glass_break, gunshot, scream, doorbell (from AudioEventType enum)
- Global thresholds managed via `/api/v1/audio/thresholds` - this story adds per-camera override
- USB cameras don't support audio extraction - hide audio settings for USB type
- AudioStreamService already respects `audio_enabled` field for RTSP capture

### Project Structure Notes

- New file: `frontend/components/cameras/AudioSettingsSection.tsx` - Audio config UI
- Modified: `frontend/components/cameras/CameraForm.tsx` - Add AudioSettingsSection
- Modified: `frontend/components/cameras/CameraPreviewCard.tsx` - Audio indicator
- Modified: `frontend/types/camera.ts` - Add audio settings fields
- Modified: `frontend/lib/validations/camera.ts` - Add audio field validation
- Modified: `backend/app/models/camera.py` - Add audio_event_types, audio_threshold columns
- Modified: `backend/app/schemas/camera.py` - Add audio settings to request/response
- Modified: `backend/app/api/v1/cameras.py` - Handle audio settings in create endpoint
- New migration: `backend/alembic/versions/049_add_camera_audio_settings.py`

### Learnings from Previous Story

**From Story p6-3-2-implement-audio-event-detection-pipeline (Status: done)**

- **Audio Event Types**: `AudioEventType` enum with glass_break, gunshot, scream, doorbell, other defined in `audio_classifiers/__init__.py`
- **Global Thresholds API**: `/api/v1/audio/thresholds` GET/PATCH for managing thresholds (default 70% for all types)
- **Threshold Storage**: Uses `system_settings` table with key pattern `audio_threshold_{event_type}`
- **AudioEventDetector Service**: Singleton at `backend/app/services/audio_event_detector.py` with `get_threshold()` method
- **Test Patterns**: 73 comprehensive tests - follow patterns in `test_audio_event_detector.py` and `test_audio_api.py`
- **Alert Integration**: AlertEngine supports `audio_event_types` condition for triggering alerts on audio events
- **Event Fields**: Event model has `audio_event_type`, `audio_confidence`, `audio_duration_ms` fields

[Source: docs/sprint-artifacts/p6-3-2-implement-audio-event-detection-pipeline.md#Dev-Agent-Record]

**From Story p6-3-1-add-audio-stream-extraction-from-rtsp (Status: done)**

- **Audio Service Available**: `AudioStreamService` at `backend/app/services/audio_stream_service.py`
- **Camera Model Fields**: `audio_enabled` (bool) and `audio_codec` (string) already exist
- **Supported Codecs**: AAC, PCMU, PCMA, Opus, MP3, PCM
- **API Pattern**: Audio endpoints follow pattern `/api/v1/cameras/{camera_id}/audio/*`

[Source: docs/sprint-artifacts/p6-3-1-add-audio-stream-extraction-from-rtsp.md#Dev-Agent-Record]

### References

- [Source: docs/epics-phase6.md#Story P6-3.3]
- [Source: docs/backlog.md#FF-015] - Audio Capture from Cameras
- [Source: backend/app/services/audio_event_detector.py] - Detection service with thresholds
- [Source: backend/app/api/v1/audio.py] - Global threshold API
- [Source: frontend/components/cameras/MotionSettingsSection.tsx] - Pattern for collapsible settings
- [Source: frontend/components/cameras/AnalysisModeSelector.tsx] - Pattern for camera-specific settings

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p6-3-3-add-audio-settings-to-camera-configuration.context.xml

### Agent Model Used

Claude claude-opus-4-5-20251101

### Debug Log References

### Completion Notes List

- Implemented AudioSettingsSection component with toggle, checkboxes for 4 event types, and slider for threshold
- Integrated AudioSettingsSection into CameraForm (only shown for RTSP cameras)
- Added audio_event_types (JSON array) and audio_threshold (Float) columns via migration 049
- Updated CameraCreate, CameraUpdate, and CameraResponse schemas with audio fields
- Added Volume2 audio indicator icon to CameraPreviewCard header
- 15 frontend tests for AudioSettingsSection component
- 9 backend tests for camera audio settings API
- All 714 frontend tests pass, all 70 camera backend tests pass

### File List

**New Files:**
- frontend/components/cameras/AudioSettingsSection.tsx
- frontend/__tests__/components/cameras/AudioSettingsSection.test.tsx
- backend/alembic/versions/049_add_camera_audio_settings.py
- backend/tests/test_api/test_camera_audio_settings.py

**Modified Files:**
- frontend/components/cameras/CameraForm.tsx
- frontend/components/cameras/CameraPreviewCard.tsx
- frontend/types/camera.ts
- frontend/lib/validations/camera.ts
- frontend/app/cameras/new/page.tsx
- backend/app/models/camera.py
- backend/app/schemas/camera.py
- backend/app/api/v1/cameras.py

## Change Log

- 2025-12-17: Story drafted (P6-3.3)
- 2025-12-17: Story implemented - all 6 tasks completed
- 2025-12-17: Senior Developer Review (AI) - Approved

---

## Senior Developer Review (AI)

### Reviewer
Brent (via Claude Opus 4.5)

### Date
2025-12-17

### Outcome: ✅ APPROVE

The implementation fully satisfies all acceptance criteria with comprehensive test coverage. Code quality is excellent with proper separation of concerns, type safety, and follows established project patterns.

### Summary

Story P6-3.3 successfully implements per-camera audio configuration settings in both frontend and backend. The implementation adds:
- AudioSettingsSection component with toggle, checkbox group, and slider
- Backend model/schema changes with migration
- Audio indicator in camera preview cards
- Comprehensive test coverage (15 frontend + 9 backend tests)

### Key Findings

**No blocking issues found.** All implementation follows established patterns and best practices.

**Low Severity (Advisory):**
- Note: The slider range is 0-100 internally but stored as 0.0-1.0 in the database, which is correctly handled in the component

### Acceptance Criteria Coverage

| AC# | Description | Status | Evidence |
|-----|-------------|--------|----------|
| AC#1 | Toggle to enable/disable audio capture per camera in camera form | ✅ IMPLEMENTED | `frontend/components/cameras/AudioSettingsSection.tsx:87-121` - Toggle switch with aria-checked state |
| AC#2 | Audio event type selection (checkboxes for glass_break, gunshot, scream, doorbell) | ✅ IMPLEMENTED | `frontend/components/cameras/AudioSettingsSection.tsx:44-65, 126-196` - AUDIO_EVENT_TYPES constant with all 4 types, checkbox group with FormField |
| AC#3 | Sensitivity/confidence threshold slider per camera | ✅ IMPLEMENTED | `frontend/components/cameras/AudioSettingsSection.tsx:199-260` - Slider with 0-100% display, null = global default |
| AC#4 | Audio indicator in camera status showing when audio capture is active | ✅ IMPLEMENTED | `frontend/components/cameras/CameraPreviewCard.tsx:122-129` - Volume2 icon with codec tooltip |

**Summary: 4 of 4 acceptance criteria fully implemented**

### Task Completion Validation

| Task | Marked As | Verified As | Evidence |
|------|-----------|-------------|----------|
| Task 1: Create AudioSettingsSection component | ✅ Complete | ✅ VERIFIED | `frontend/components/cameras/AudioSettingsSection.tsx` - 265 lines, all subtasks implemented |
| Task 2: Extend CameraForm to include audio settings | ✅ Complete | ✅ VERIFIED | `frontend/components/cameras/CameraForm.tsx:36, 107-110, 129-132, 492-494` - Import, default values, conditional render for RTSP only |
| Task 3: Update frontend types and API client | ✅ Complete | ✅ VERIFIED | `frontend/types/camera.ts:101-104, 136-138, 161-163` - ICamera, ICameraCreate, ICameraUpdate all have audio_event_types, audio_threshold |
| Task 4: Extend Camera model and schema | ✅ Complete | ✅ VERIFIED | `backend/app/models/camera.py:81-82`, `backend/app/schemas/camera.py:44-57, 121-124, 181-182`, migration `049_add_camera_audio_settings.py` |
| Task 5: Add audio indicator to camera status | ✅ Complete | ✅ VERIFIED | `frontend/components/cameras/CameraPreviewCard.tsx:9, 122-129` - Volume2 import and conditional render |
| Task 6: Write tests | ✅ Complete | ✅ VERIFIED | `frontend/__tests__/components/cameras/AudioSettingsSection.test.tsx` (15 tests), `backend/tests/test_api/test_camera_audio_settings.py` (9 tests) |

**Summary: 6 of 6 completed tasks verified, 0 questionable, 0 false completions**

### Test Coverage and Gaps

**Frontend Tests (15 tests passing):**
- AC#1 toggle tests: 5 tests (render, default off, can toggle, shows/hides options)
- AC#2 checkbox tests: 4 tests (renders all 4, selectable, descriptions, pre-selected state)
- AC#3 slider tests: 4 tests (renders, global default display, percentage display, reset button)
- Section header tests: 2 tests

**Backend Tests (9 tests passing):**
- Create camera with/without audio settings
- Update camera audio settings
- GET camera/list returns audio settings
- Clear audio settings
- Threshold validation (0.0-1.0 range)
- JSON string format acceptance
- Partial update preserves settings

**No test gaps identified** - all ACs have corresponding tests.

### Architectural Alignment

✅ Implementation follows established patterns:
- AudioSettingsSection follows MotionSettingsSection component pattern
- Uses React Hook Form with Zod validation (consistent with project)
- Backend schema uses field_validator for JSON serialization (consistent with detection_zones pattern)
- Migration follows project naming convention (049_add_camera_audio_settings.py)
- Audio settings only shown for RTSP cameras (correctly excludes USB per constraint)

### Security Notes

✅ No security concerns:
- No user input directly used in SQL queries
- audio_threshold validated with ge=0.0, le=1.0 constraints
- audio_event_types properly serialized/deserialized as JSON
- No sensitive data exposed

### Best-Practices and References

- React Hook Form patterns: https://react-hook-form.com/
- Zod validation: https://zod.dev/
- shadcn/ui components used (Slider, Checkbox, Tooltip)
- Alembic migration best practices followed

### Action Items

**Code Changes Required:**
(None required - implementation is complete and correct)

**Advisory Notes:**
- Note: Consider adding integration tests for the full audio settings flow in future
- Note: The "Use Global Default (70%)" text assumes default threshold is 70% - ensure this matches system_settings
