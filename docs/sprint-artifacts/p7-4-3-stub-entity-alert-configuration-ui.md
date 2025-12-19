# Story P7-4.3: Stub Entity Alert Configuration UI

Status: done

## Story

As a **home user wanting customized notifications for recognized entities**,
I want **a modal UI to configure entity-based alerts with options like notify when seen or not seen for X hours**,
so that **I understand how future entity alerting will work and can prepare my preferences**.

## Story Key
p7-4-3-stub-entity-alert-configuration-ui

## Acceptance Criteria

| AC# | Criteria | Verification |
|-----|----------|--------------|
| AC1 | "Create Alert" modal opens from entity card "Add Alert" button | E2E: Click button, verify modal opens |
| AC2 | Modal shows "Notify when seen" option | E2E: Modal open, verify checkbox/toggle present |
| AC3 | Modal shows "Notify when NOT seen for X hours" option with hour input | E2E: Modal open, verify option with numeric input |
| AC4 | Time range configuration displayed (all day / schedule) | E2E: Modal open, verify time range selector |
| AC5 | "Coming Soon" message shown when save attempted | E2E: Click save, verify message displayed |
| AC6 | Link to alert rules page provided | E2E: Modal shows link to /rules page |

## Tasks / Subtasks

### Task 1: Create EntityAlertModal Component (AC: 1, 2, 3, 4)
- [x] 1.1 Create `frontend/components/entities/EntityAlertModal.tsx`
- [x] 1.2 Accept props: `isOpen`, `onClose`, `entity`
- [x] 1.3 Add "Notify when seen" toggle/checkbox
- [x] 1.4 Add "Notify when NOT seen for X hours" option with number input
- [x] 1.5 Add time range configuration (all day toggle, time pickers for custom schedule)
- [x] 1.6 Style modal using shadcn/ui Dialog component

### Task 2: Connect Modal to EntityCard (AC: 1)
- [x] 2.1 Update EntityCard to track modal open state
- [x] 2.2 Change "Add Alert" button to open modal instead of showing toast
- [x] 2.3 Pass entity data to modal component

### Task 3: Add "Coming Soon" Behavior (AC: 5, 6)
- [x] 3.1 Add "Save" button to modal footer
- [x] 3.2 On save click, display "Coming Soon" toast message
- [x] 3.3 Add link to `/rules` (alert rules page) in modal footer
- [x] 3.4 Style save button and link appropriately

### Task 4: Add Tests (All ACs)
- [x] 4.1 Write test for modal opening when button clicked
- [x] 4.2 Write test for "Notify when seen" option presence
- [x] 4.3 Write test for "Notify when NOT seen" option with input
- [x] 4.4 Write test for time range configuration
- [x] 4.5 Write test for "Coming Soon" message on save
- [x] 4.6 Write test for link to rules page

## Dev Notes

### Architecture Constraints

From tech spec (docs/sprint-artifacts/tech-spec-epic-P7-4.md):
- This is UI-only - NO backend implementation for entity alerts yet
- Modal is a stub/preview of future functionality
- "Coming Soon" message must be clear that feature is not implemented
- Link to alert rules page provides alternative for current alerting needs

### Key Implementation Details

**Modal Workflow (Non-Functional):**
```
1. User clicks "Add Alert" on EntityCard
      ↓
2. EntityAlertModal opens with options:
   - Notify when seen (toggle)
   - Notify when NOT seen for X hours (toggle + number input)
   - Time range: All day / Custom schedule
      ↓
3. User clicks "Save"
      ↓
4. Modal shows "Coming Soon" toast
      ↓
5. Modal closes, no data persisted
```

**Modal Form Elements:**
1. **"Notify when seen" toggle** - When this entity is detected, send notification
2. **"Notify when NOT seen for X hours" toggle + input** - Alert if entity not detected within timeframe
3. **Time range selector** - All day (default) or custom time windows
4. **Save button** - Triggers "Coming Soon" toast
5. **Link to rules page** - For users who want current alerting functionality

### Existing Patterns to Follow

- **Modal Component**: Follow patterns in `frontend/components/rules/RuleFormModal.tsx`
- **Dialog**: Use shadcn/ui `<Dialog>`, `<DialogContent>`, `<DialogHeader>`, etc.
- **Form Elements**: Use shadcn/ui Switch, Input, Label, RadioGroup
- **Toast**: Continue using sonner `toast` (already in EntityCard)
- **Test Patterns**: Follow `frontend/__tests__/components/entities/EntityCard.test.tsx`

### Project Structure Notes

**Files to Create:**
- `frontend/components/entities/EntityAlertModal.tsx` - Alert configuration modal
- `frontend/__tests__/components/entities/EntityAlertModal.test.tsx` - Tests

**Files to Modify:**
- `frontend/components/entities/EntityCard.tsx` - Replace toast with modal open

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P7-4.md#Story-P7-4.3]
- [Source: docs/sprint-artifacts/tech-spec-epic-P7-4.md#Workflows-and-Sequencing]
- [Source: docs/epics-phase7.md#Story-P7-4.3]

### Learnings from Previous Story

**From Story p7-4-2-create-entities-list-page (Status: done)**

- **Existing "Add Alert" Button**: EntityCard already has "Add Alert" button showing "Coming Soon" toast at line 70-74
- **Entity Type**: Uses `IEntity` interface from `@/types/entity`
- **Toast Import**: Already imports `toast` from `sonner`
- **Component Pattern**: EntityCard uses memo and follows standard patterns
- **API Path**: Entities API at `/api/v1/context/entities`
- **All 12 EntityCard tests pass** - need to maintain test compatibility

[Source: docs/sprint-artifacts/p7-4-2-create-entities-list-page.md#Dev-Agent-Record]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p7-4-3-stub-entity-alert-configuration-ui.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Implementation started by creating EntityAlertModal component with all required form elements
- Updated EntityCard to replace direct toast with modal state management
- Created comprehensive test suite covering all 6 ACs

### Completion Notes List

- **EntityAlertModal Component**: Created new modal component with:
  - "Notify when seen" toggle (AC2)
  - "Notify when NOT seen for X hours" toggle with numeric input (AC3)
  - Time range configuration with RadioGroup (All day / Custom) (AC4)
  - Save button that shows "Coming Soon" toast (AC5)
  - Link to /rules page (AC6)
  - Uses shadcn/ui Dialog, Switch, Input, Label, RadioGroup components
  - Follows existing modal patterns in the codebase

- **EntityCard Updates**: Modified to use EntityAlertModal
  - Added useState for modal open state
  - Changed handleAddAlert to open modal instead of showing toast directly
  - Modal receives entity data as prop (AC1)
  - Removed toast import (now handled in modal)
  - Added EntityAlertModal import

- **Tests**: Created 14 new tests covering all acceptance criteria
  - All 38 entity component tests pass (existing 24 + 14 new)
  - Mocked sonner toast for verification
  - Mocked next/link for route testing

- **Build**: Frontend builds successfully with no TypeScript errors
- **Lint**: No new lint errors introduced in modified/created files

### File List

**NEW:**
- `frontend/components/entities/EntityAlertModal.tsx`
- `frontend/__tests__/components/entities/EntityAlertModal.test.tsx`

**MODIFIED:**
- `frontend/components/entities/EntityCard.tsx`
- `docs/sprint-artifacts/sprint-status.yaml`
- `docs/sprint-artifacts/p7-4-3-stub-entity-alert-configuration-ui.md`
- `docs/sprint-artifacts/p7-4-3-stub-entity-alert-configuration-ui.context.xml`

## Change Log
| Date | Change |
|------|--------|
| 2025-12-19 | Story drafted from epic P7-4 and tech spec |
| 2025-12-19 | Implementation complete - EntityAlertModal created, EntityCard updated, tests added |
