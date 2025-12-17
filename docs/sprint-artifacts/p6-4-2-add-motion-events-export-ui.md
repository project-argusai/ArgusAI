# Story P6-4.2: Add Motion Events Export UI

Status: done

## Story

As a home owner,
I want a user-friendly interface to configure and download motion event exports,
so that I can easily export filtered motion detection data to CSV for analysis without needing to use API tools.

## Acceptance Criteria

1. Export button/section visible in Settings page under "Data Export" section
2. Date range picker component for filtering export data (start and end date)
3. Camera selector dropdown for filtering (optional, "All Cameras" default)
4. Click "Export CSV" triggers file download via browser
5. Loading state shown during export generation
6. Success toast notification shown after download completes
7. Error toast notification shown if export fails

## Tasks / Subtasks

- [x] Task 1: Create MotionEventsExport component (AC: #1, #2, #3)
  - [x] Create `frontend/components/settings/MotionEventsExport.tsx`
  - [x] Add "Motion Events Export" section with description text
  - [x] Implement DateRangePicker using shadcn/ui calendar (or existing component)
  - [x] Implement CameraSelect dropdown using existing camera list API
  - [x] Add "All Cameras" option as default in selector
  - [x] Export button with Download icon from lucide-react

- [x] Task 2: Integrate export component into Settings page (AC: #1)
  - [x] Import MotionEventsExport in `frontend/app/settings/page.tsx`
  - [x] Add "Data Export" section after existing sections
  - [x] Match styling with existing settings sections (card-based layout)

- [x] Task 3: Implement export API call and file download (AC: #4, #5, #6, #7)
  - [x] Handle query params: format, start_date, end_date, camera_id
  - [x] Use fetch with blob response for file download
  - [x] Create download link programmatically and trigger click
  - [x] Extract filename from Content-Disposition header
  - [x] Handle loading state during export

- [x] Task 4: Add toast notifications and error handling (AC: #6, #7)
  - [x] Use existing toast system (sonner)
  - [x] Show success toast with filename on completion
  - [x] Show error toast with message on failure
  - [x] Disable export button while loading

- [x] Task 5: Write frontend tests (AC: #1-7)
  - [x] Test component renders export section
  - [x] Test date range picker interaction
  - [x] Test camera selector with mock data
  - [x] Test export button click triggers API call
  - [x] Test loading state displayed
  - [x] Test success toast shown
  - [x] Test error toast shown on failure

## Dev Notes

- The backend endpoint already exists: `GET /api/v1/motion-events/export?format=csv&start_date=...&end_date=...&camera_id=...`
- Follow existing export pattern from events export if one exists
- Use existing shadcn/ui components: Button, Card, Select, Calendar/DatePicker
- The API returns a streaming CSV response with Content-Disposition header
- For date picker, can use `react-day-picker` via shadcn/ui or an existing date range component
- Download should work via creating a blob URL and programmatic anchor click

### Project Structure Notes

- New: `frontend/components/settings/MotionEventsExport.tsx` - Export configuration component
- New: `frontend/components/ui/calendar.tsx` - Shadcn Calendar component for date picker
- Modified: `frontend/app/settings/page.tsx` - Add Data Export section
- New: `frontend/__tests__/components/settings/MotionEventsExport.test.tsx` - 14 tests

### Learnings from Previous Story

**From Story p6-4-1-implement-motion-events-csv-export (Status: done)**

- **Backend Endpoint Ready**: `GET /api/v1/motion-events/export?format=csv` is fully implemented
- **Query Parameters**: Supports `start_date`, `end_date`, `camera_id` query params
- **Filename Header**: Content-Disposition header contains filename with date range
- **Streaming Response**: Backend uses StreamingResponse - frontend should handle as blob
- **Test Patterns**: 22 backend tests establish comprehensive coverage expectations
- **Empty Result Handling**: API returns headers-only CSV for empty results (no error)

[Source: docs/sprint-artifacts/p6-4-1-implement-motion-events-csv-export.md#Dev-Agent-Record]

### References

- [Source: docs/epics-phase6.md#Story P6-4.2]
- [Source: docs/sprint-artifacts/tech-spec-epic-P6-4.md#Story P6-4.2: Motion Events Export UI]
- [Source: docs/backlog.md#FF-017] - Export Motion Events to CSV
- [Source: frontend/components/settings/] - Existing settings components pattern
- [Source: frontend/lib/api-client.ts] - API client patterns
- [Source: backend/app/api/v1/motion_events.py#export_motion_events] - Backend endpoint (lines 33-182)

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p6-4-2-add-motion-events-export-ui.context.xml

### Agent Model Used

claude-opus-4-5-20251101

### Debug Log References

Implementation plan:
1. Create Calendar UI component for react-day-picker v9
2. Create MotionEventsExport component with date range picker, camera selector, and export button
3. Integrate into Settings page in Data tab
4. Add comprehensive tests covering all ACs

### Completion Notes List

- Created `frontend/components/ui/calendar.tsx` - Shadcn-style Calendar component for react-day-picker v9
- Created `frontend/components/settings/MotionEventsExport.tsx` - Full export UI with date range picker (mode="range"), camera selector with TanStack Query, export button with loading/disabled states, blob download with filename extraction, toast notifications for success/error
- Integrated MotionEventsExport into Settings page Data tab (before BackupRestore)
- Created 14 comprehensive tests in `frontend/__tests__/components/settings/MotionEventsExport.test.tsx`
- All 728 frontend tests pass (no regressions)
- Build passes successfully

### File List

- frontend/components/ui/calendar.tsx (new)
- frontend/components/settings/MotionEventsExport.tsx (new)
- frontend/app/settings/page.tsx (modified)
- frontend/__tests__/components/settings/MotionEventsExport.test.tsx (new)

## Change Log

- 2025-12-17: Story drafted (P6-4.2)
- 2025-12-17: Story implemented - all 5 tasks completed, 14 tests added
- 2025-12-17: Senior Developer Review (AI) - Approved

---

## Senior Developer Review (AI)

### Reviewer
Brent (via Claude Opus 4.5)

### Date
2025-12-17

### Outcome: ✅ APPROVE

The implementation fully satisfies all 7 acceptance criteria with comprehensive test coverage (14 tests). Code quality is excellent with proper component architecture, accessibility features, and follows established project patterns.

### Summary

Story P6-4.2 successfully implements a user-friendly motion events export UI. The implementation includes:
- MotionEventsExport component with date range picker (react-day-picker v9)
- Camera selector dropdown using TanStack Query
- Export button with loading state and blob download
- Toast notifications for success/error feedback
- Full integration into Settings page Data tab
- Comprehensive test suite (14 tests)

### Key Findings

**No blocking issues found.** Implementation follows established patterns and best practices.

### Acceptance Criteria Coverage

| AC# | Description | Status | Evidence |
|-----|-------------|--------|----------|
| AC#1 | Export button/section visible in Settings page under "Data Export" section | ✅ IMPLEMENTED | `frontend/app/settings/page.tsx:819-820` - MotionEventsExport in Data tab |
| AC#2 | Date range picker component for filtering export data | ✅ IMPLEMENTED | `MotionEventsExport.tsx:162-202` - Calendar with mode="range", numberOfMonths=2 |
| AC#3 | Camera selector dropdown for filtering ("All Cameras" default) | ✅ IMPLEMENTED | `MotionEventsExport.tsx:210-231` - Select with "all" as default value |
| AC#4 | Click "Export CSV" triggers file download via browser | ✅ IMPLEMENTED | `MotionEventsExport.tsx:108-117` - Blob URL + programmatic anchor click |
| AC#5 | Loading state shown during export generation | ✅ IMPLEMENTED | `MotionEventsExport.tsx:240-244` - Loader2 spinner when isExporting |
| AC#6 | Success toast notification shown after download completes | ✅ IMPLEMENTED | `MotionEventsExport.tsx:119` - toast.success with filename |
| AC#7 | Error toast notification shown if export fails | ✅ IMPLEMENTED | `MotionEventsExport.tsx:122-126` - toast.error with error message |

**Summary: 7 of 7 acceptance criteria fully implemented**

### Task Completion Validation

| Task | Marked As | Verified As | Evidence |
|------|-----------|-------------|----------|
| Task 1: Create MotionEventsExport component | ✅ Complete | ✅ VERIFIED | `frontend/components/settings/MotionEventsExport.tsx` - 260 lines |
| Task 2: Integrate into Settings page | ✅ Complete | ✅ VERIFIED | `frontend/app/settings/page.tsx:60, 819-820` |
| Task 3: Implement export API call and file download | ✅ Complete | ✅ VERIFIED | `MotionEventsExport.tsx:65-130` - Full handleExport function |
| Task 4: Add toast notifications and error handling | ✅ Complete | ✅ VERIFIED | `MotionEventsExport.tsx:119, 122-126` |
| Task 5: Write frontend tests | ✅ Complete | ✅ VERIFIED | `frontend/__tests__/components/settings/MotionEventsExport.test.tsx` - 14 tests |

**Summary: 5 of 5 completed tasks verified**

### Test Coverage

**Frontend Tests (14 tests passing):**
- AC#1 render tests: 2 tests (section title, description)
- AC#2 date picker tests: 2 tests (renders, opens popover)
- AC#3 camera selector tests: 2 tests (default value, dropdown options)
- AC#4 export button tests: 3 tests (renders, triggers API, passes camera_id)
- AC#5 loading state tests: 1 test (shows spinner, disables button)
- AC#6 success toast tests: 1 test
- AC#7 error toast tests: 2 tests (API error, network error)
- Additional coverage: 2 tests (CSV info display, ARIA labels)

**No test gaps identified** - all ACs have corresponding tests.

### Architectural Alignment

✅ Implementation follows established patterns:
- Component follows settings Card pattern (BackupRestore, MQTTSettings)
- Uses TanStack Query for camera list (consistent with project)
- Uses sonner for toast notifications (consistent with project)
- Uses shadcn/ui components (Button, Card, Select, Popover)
- Calendar component created for react-day-picker v9 compatibility

### Security Notes

✅ No security concerns:
- No user input directly used in queries (uses URLSearchParams)
- Uses NEXT_PUBLIC_API_URL environment variable correctly
- No sensitive data exposed

### Action Items

**Code Changes Required:**
(None required - implementation is complete and correct)
