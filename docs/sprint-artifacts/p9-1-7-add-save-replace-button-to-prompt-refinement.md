# Story 9.1.7: Add Save/Replace Button to Prompt Refinement

Status: done

## Story

As a **user**,
I want **a clear way to accept and save the refined prompt**,
So that **I can apply AI suggestions to my actual prompt configuration**.

## Acceptance Criteria

1. **AC-1.7.1:** Given AI has generated a refined prompt, when I review the suggestion, then I see three buttons: "Accept & Save", "Resubmit", and "Cancel"
2. **AC-1.7.2:** Given I click "Accept & Save", when the action completes, then my prompt setting is updated
3. **AC-1.7.3:** Given I click "Accept & Save", then the modal closes and a success toast appears
4. **AC-1.7.4:** Given I click "Resubmit", then the edited prompt is sent back to AI for further refinement

## Tasks / Subtasks

- [x] Task 1: Rename "Accept" button to "Accept & Save"
- [x] Task 2: Verify Resubmit functionality works correctly
- [x] Task 3: Verify Cancel functionality works correctly
- [x] Task 4: Verify success toast appears on accept
- [x] Task 5: Run tests to verify

## Implementation

### Frontend Changes

**frontend/components/settings/PromptRefinementModal.tsx:**
- Renamed "Accept" button to "Accept & Save" at line 243
- Button group now shows: "Cancel", "Resubmit", "Accept & Save"

### Already Working Features

The following were already implemented in P8-3.3:
- **Accept functionality**: `handleAccept` calls `onAccept(editedPrompt)` which updates the form
- **Success toast**: Shows "Prompt updated" on accept (line 107-109)
- **Resubmit functionality**: `handleResubmit` re-calls `handleRefine` with edited prompt
- **Cancel functionality**: `handleCancel` calls `onOpenChange(false)` to close modal

## Dev Notes

### Button Layout

```
| Cancel | Resubmit | Accept & Save |
```

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-1.md#P9-1.7]
- [Source: docs/epics-phase9.md#Story P9-1.7]
- [Backlog: BUG-009]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5

### Test Results

- Frontend tests: 766 passed
- Frontend build: passed

### File List

- frontend/components/settings/PromptRefinementModal.tsx (modified)

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-22 | Claude Opus 4.5 | Renamed Accept button to Accept & Save |
