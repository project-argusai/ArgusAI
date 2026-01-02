# Story P16-4.2: Add "Don't Show Again" Preference

Status: done

## Story

As a **user**,
I want **to disable the confirmation dialog**,
So that **I can assign entities quickly without repeated warnings**.

## Acceptance Criteria

1. **AC1**: Given the confirmation dialog is shown, when I check "Don't show this warning again", then a checkbox is checked
2. **AC2**: Given I confirm with checkbox checked, when assignment completes, then the preference is saved to localStorage
3. **AC3**: Given I have previously checked "Don't show again", when I assign an event to an entity, then the confirmation dialog is skipped and assignment proceeds directly
4. **AC4**: The preference key is `argusai_skip_entity_assign_warning`
5. **AC5**: Preference persists across browser sessions

## Tasks / Subtasks

- [x] Task 1: Add checkbox to EntityAssignConfirmDialog (AC: 1)
  - [x] Add Checkbox component from shadcn/ui
  - [x] Add state for checkbox checked
  - [x] Display "Don't show this warning again" label
- [x] Task 2: Implement localStorage persistence (AC: 2, 4, 5)
  - [x] Save preference when confirm is clicked with checkbox checked
  - [x] Use key `argusai_skip_entity_assign_warning`
- [x] Task 3: Check preference in EntitySelectModal (AC: 3)
  - [x] Read localStorage on mount
  - [x] Skip confirmation dialog if preference is set
- [x] Task 4: Write tests (AC: all)
  - [x] Test checkbox renders and can be checked
  - [x] Test localStorage is saved on confirm with checkbox
  - [x] Test dialog is skipped when preference is set

## Dev Notes

- **Component to modify**: `frontend/components/entities/EntityAssignConfirmDialog.tsx`
- **Component to modify**: `frontend/components/entities/EntitySelectModal.tsx`
- **localStorage key**: `argusai_skip_entity_assign_warning`

### References

- [Source: docs/epics-phase16.md#Story-P16-4.2]
- [GitHub Issue: #337]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5

### File List

- frontend/components/entities/EntityAssignConfirmDialog.tsx (modified)
- frontend/components/entities/EntitySelectModal.tsx (modified)
- frontend/__tests__/components/entities/EntityAssignConfirmDialog.test.tsx (modified)
