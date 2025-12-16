# Story P5-5.4: Implement Multiple Schedule Time Ranges

Status: done

## Story

As a user configuring detection schedules,
I want to define multiple active time ranges per day (e.g., 6-9am AND 6-11pm),
so that I can enable motion detection during my morning and evening routines without it running during work hours.

## Acceptance Criteria

1. Multiple time ranges per day supported - users can add 2+ non-overlapping time ranges
2. UI allows adding and removing time ranges dynamically (min 1, max 4 per day)
3. Database schema stores multiple ranges in existing JSON column (no migration needed)
4. Schedule evaluation handles multiple ranges - detection active if current time falls within ANY range
5. Overlapping ranges are validated and merged or rejected with clear error message

## Tasks / Subtasks

- [x] Task 1: Update TypeScript types for multiple time ranges (AC: 1, 3)
  - [x] 1.1: Modify `IDetectionSchedule` in `frontend/types/camera.ts` to use `time_ranges: ITimeRange[]` array
  - [x] 1.2: Create `ITimeRange` interface with `start_time` and `end_time` properties
  - [x] 1.3: Maintain backward compatibility with legacy single range format

- [x] Task 2: Update ScheduleManager backend service (AC: 4)
  - [x] 2.1: Modify `is_detection_active()` to iterate over `time_ranges` array
  - [x] 2.2: Return `True` if current time is within ANY range
  - [x] 2.3: Handle legacy single-range format (`start_time`/`end_time` at root level)
  - [x] 2.4: Add unit tests for multiple range scenarios (17 new tests in TestMultipleTimeRanges class)

- [x] Task 3: Build MultiTimeRangePicker UI component (AC: 2)
  - [x] 3.1: Create `TimeRangeRow` component for individual start/end time inputs
  - [x] 3.2: Add "Add Time Range" button with aria-label for accessibility
  - [x] 3.3: Add remove button on each row (except first row when only one exists)
  - [x] 3.4: Limit to maximum 4 time ranges per schedule
  - [x] 3.5: Implement focus management for keyboard navigation

- [x] Task 4: Update DetectionScheduleEditor to use MultiTimeRangePicker (AC: 2, 5)
  - [x] 4.1: Replace single start/end time inputs with MultiTimeRangePicker
  - [x] 4.2: Migrate existing schedule format on form load
  - [x] 4.3: Validate no overlapping ranges on save
  - [x] 4.4: Show validation error message for overlapping ranges

- [x] Task 5: Update CameraForm integration (AC: 3)
  - [x] 5.1: Update form default values for new time_ranges format
  - [x] 5.2: Update form validation schema in `frontend/lib/validations/camera.ts`
  - [x] 5.3: Ensure API payload correctly serializes time_ranges array

- [x] Task 6: Test and validate (All ACs)
  - [x] 6.1: Test adding/removing time ranges in UI (22 tests in MultiTimeRangePicker.test.tsx)
  - [x] 6.2: Test backend evaluation with multiple ranges (17 new tests)
  - [x] 6.3: Test overnight range handling in multi-range context
  - [x] 6.4: Test migration from legacy single-range cameras
  - [x] 6.5: Test keyboard navigation for add/remove buttons
  - [x] 6.6: Verify existing camera schedule tests pass (36 total tests passing)

## Dev Notes

### Current Implementation Analysis

The current detection schedule implementation uses a single time range:

**Backend (`schedule_manager.py`):**
- Parses `detection_schedule` JSON with `start_time` and `end_time` at root level
- Handles overnight schedules (e.g., 22:00-06:00)
- Returns `True` if current time is within the single range

**Frontend (`DetectionScheduleEditor.tsx`):**
- Two time inputs for start and end time
- Day-of-week selection with checkbox-style buttons
- Schedule status indicator (Active/Inactive/Always Active)

**Data Format (current):**
```json
{
  "enabled": true,
  "start_time": "09:00",
  "end_time": "17:00",
  "days": [0, 1, 2, 3, 4]
}
```

**Data Format (proposed):**
```json
{
  "enabled": true,
  "time_ranges": [
    { "start_time": "06:00", "end_time": "09:00" },
    { "start_time": "18:00", "end_time": "23:00" }
  ],
  "days": [0, 1, 2, 3, 4]
}
```

### Backward Compatibility Strategy

1. **Backend**: `ScheduleManager.is_detection_active()` will check for both formats:
   - If `time_ranges` array exists → use new multi-range logic
   - If `start_time`/`end_time` at root → use legacy single-range logic

2. **Frontend**: `DetectionScheduleEditor` will migrate on load:
   - If legacy format detected → convert to `time_ranges` array with single entry
   - Display using new MultiTimeRangePicker component
   - Save in new format

### Range Overlap Validation

Overlapping ranges should be rejected with clear error message. The validation logic:
```typescript
function hasOverlappingRanges(ranges: ITimeRange[]): boolean {
  const sorted = [...ranges].sort((a, b) => a.start_time.localeCompare(b.start_time));
  for (let i = 0; i < sorted.length - 1; i++) {
    if (sorted[i].end_time > sorted[i + 1].start_time) {
      return true; // Overlap detected
    }
  }
  return false;
}
```

Note: Overnight ranges (e.g., 22:00-06:00) require special handling - they should not be checked for overlap with daytime ranges in the same way.

### Architecture Context

- **UI Framework**: Next.js 15 + React 19 + shadcn/ui
- **Backend**: FastAPI + SQLAlchemy (detection_schedule stored as JSON text)
- **No database migration required** - JSON schema change only
- **No API schema change required** - `detection_schedule` remains `Optional[Any]`

### Source Tree Components

| File | Purpose | Changes Needed |
|------|---------|----------------|
| `frontend/types/camera.ts` | Type definitions | Add ITimeRange, update IDetectionSchedule |
| `frontend/components/cameras/DetectionScheduleEditor.tsx` | Schedule UI | Replace time inputs with MultiTimeRangePicker |
| `frontend/components/cameras/MultiTimeRangePicker.tsx` | NEW - Time range list UI | Create new component |
| `frontend/lib/validations/camera.ts` | Form validation | Update schedule schema |
| `backend/app/services/schedule_manager.py` | Schedule evaluation | Handle time_ranges array |
| `backend/tests/test_services/test_schedule_manager.py` | Unit tests | Add multi-range test cases |

### Testing Standards

- Use Vitest for frontend component tests
- Use pytest for backend service tests
- Test both new format and legacy format handling
- Test overnight schedules in multi-range context
- Test keyboard accessibility for add/remove buttons

### Project Structure Notes

- New component follows existing pattern in `components/cameras/`
- No new API endpoints required
- No database migration required

### Learnings from Previous Story

**From Story p5-5-3-create-detection-zone-preset-templates (Status: done)**

- **Focus Ring Pattern**: Use `focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2` for consistent focus visibility
- **ARIA Pattern**: All buttons should have aria-label for accessibility
- **Component Structure**: Preset templates defined in separate constants file - consider similar pattern for time range validation
- **Test Coverage**: Comprehensive tests covering all interaction states (29 tests added)

[Source: docs/sprint-artifacts/p5-5-3-create-detection-zone-preset-templates.md#Dev-Agent-Record]

### References

- [Source: docs/PRD-phase5.md#FR35] - Multiple schedule time ranges requirement
- [Source: docs/epics-phase5.md#P5-5.4] - Story definition and acceptance criteria
- [Source: docs/backlog.md#FF-016] - Feature request for multiple schedule time ranges (GitHub Issue #41)
- [Source: backend/app/services/schedule_manager.py] - Current schedule evaluation logic
- [Source: frontend/components/cameras/DetectionScheduleEditor.tsx] - Current schedule UI

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p5-5-4-implement-multiple-schedule-time-ranges.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Backend tests: 36/36 passing in test_schedule_manager.py
- Frontend tests: 22/22 passing in MultiTimeRangePicker.test.tsx
- Build: Successful (`npm run build`)

### Completion Notes List

- Implemented multiple time ranges support (2-4 ranges per schedule)
- Full backward compatibility with legacy single-range format
- New `MultiTimeRangePicker` component with accessible add/remove buttons
- Overlap validation with clear error messages
- Overnight range handling in multi-range context
- 17 new backend tests + 22 new frontend tests

### File List

**New Files:**
- frontend/components/cameras/MultiTimeRangePicker.tsx
- frontend/__tests__/components/cameras/MultiTimeRangePicker.test.tsx

**Modified Files:**
- frontend/types/camera.ts (added ITimeRange interface, updated IDetectionSchedule)
- frontend/lib/validations/camera.ts (updated detectionScheduleSchema with overlap validation)
- frontend/components/cameras/DetectionScheduleEditor.tsx (integrated MultiTimeRangePicker)
- backend/app/services/schedule_manager.py (added time_ranges support + _is_time_in_range helper)
- backend/tests/test_services/test_schedule_manager.py (added TestMultipleTimeRanges class)
- docs/sprint-artifacts/sprint-status.yaml (status updates)
- docs/sprint-artifacts/p5-5-4-implement-multiple-schedule-time-ranges.md (this file)
- docs/sprint-artifacts/p5-5-4-implement-multiple-schedule-time-ranges.context.xml (story context)

