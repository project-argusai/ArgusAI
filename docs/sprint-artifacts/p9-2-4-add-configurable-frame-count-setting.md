# Story 9.2.4: Add Configurable Frame Count Setting

Status: done

## Story

As a **user**,
I want **to configure how many frames are analyzed per event**,
So that **I can balance AI accuracy vs cost**.

## Acceptance Criteria

1. **AC-2.4.1:** Given Settings > General page, when viewing, then "Frames per Analysis" dropdown visible
2. **AC-2.4.2:** Given dropdown, when clicked, then options 5, 10, 15, 20 available
3. **AC-2.4.3:** Given I change from 10 to 15, when saving, then warning modal appears about cost
4. **AC-2.4.4:** Given I confirm warning, when saved, then setting persists
5. **AC-2.4.5:** Given new event, when processed, then configured frame count used

## Tasks / Subtasks

- [x] Task 1: Add analysis_frame_count to system settings API (AC: 2.4.4, 2.4.5)
  - [x] Add setting key to settings model (settings_analysis_frame_count)
  - [x] Expose in GET /api/v1/system/settings
  - [x] Accept in PUT /api/v1/system/settings
- [x] Task 2: Create frame count dropdown in GeneralSettings (AC: 2.4.1, 2.4.2)
  - [x] Add dropdown with options 5, 10, 15, 20
  - [x] Default to 10
  - [x] Wire up to settings API
- [x] Task 3: Add warning modal for cost increase (AC: 2.4.3)
  - [x] Show modal when changing frame count (CostWarningModal)
  - [x] Explain cost implications with estimated costs
  - [x] Require confirmation to save
- [x] Task 4: Pass frame count to protect_event_handler (AC: 2.4.5)
  - [x] Read setting from database (line 1566-1570)
  - [x] Pass to frame extraction service (line 1625)
- [x] Task 5: Write tests (existing from P8-2.3)
- [x] Task 6: Run all tests to verify

**Note:** This story was already implemented as part of Phase 8 (Story P8-2.3). All functionality verified as working.

## Dev Notes

### Technical Approach

Add a new system setting `settings_analysis_frame_count` with default value 10. The frontend will display a dropdown in the General settings section. When increasing the count, show a warning modal explaining cost implications.

### Source Components

- `backend/app/api/v1/system.py` - Add frame count to settings response
- `backend/app/services/protect_event_handler.py` - Read and use setting
- `frontend/components/settings/GeneralSettings.tsx` - Add dropdown and modal
- `frontend/lib/api-client.ts` - Update settings types if needed

### Testing Standards

- Backend unit tests for settings API
- Frontend component tests for dropdown
- Integration tests for end-to-end flow

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-2.md#P9-2.4]
- [Source: docs/epics-phase9.md#Story P9-2.4]
- [Backlog: IMP-007]

## Dev Agent Record

### Context Reference

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

### File List

- `frontend/app/settings/page.tsx` - Analysis Frame Count dropdown (line 448-473)
- `frontend/components/settings/CostWarningModal.tsx` - Cost warning modal
- `backend/app/services/protect_event_handler.py` - Reads and uses setting (line 1566-1625)

