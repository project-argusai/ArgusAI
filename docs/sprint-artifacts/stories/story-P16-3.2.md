# Story P16-3.2: Create EntityEditModal Component

Status: done

## Story

As a **user**,
I want **a modal to edit entity properties**,
So that **I can correct or enhance entity information**.

## Acceptance Criteria

1. **AC1**: Given I open the EntityEditModal for an entity, when the modal renders, then I see form fields for: Name (text), Type (select: Person/Vehicle/Unknown), VIP (toggle), Blocked (toggle), Notes (textarea)
2. **AC2**: Given the modal is open, when fields are displayed, then they are pre-filled with current entity values
3. **AC3**: Given I change the Name field and click Save, when the save completes, then a success toast shows "Entity updated", the modal closes, and the entity list/detail view refreshes
4. **AC4**: Given I click Cancel or press Escape, when the modal closes, then no changes are saved
5. **AC5**: The modal shows the entity thumbnail at the top
6. **AC6**: Form validation shows inline errors (e.g., name too long exceeds 255 chars, notes exceeds 2000 chars)
7. **AC7**: Save button is disabled while saving (loading state)
8. **AC8**: Modal can be closed via X button, Cancel button, or Escape key

## Tasks / Subtasks

- [x] Task 1: Create EntityEditModal component (AC: 1, 2, 4, 5, 8)
  - [x] Create `frontend/components/entities/EntityEditModal.tsx`
  - [x] Add Dialog with proper open/close handling
  - [x] Add entity thumbnail display at top
  - [x] Wire up onClose handlers (X, Cancel, Escape)
- [x] Task 2: Create form with all fields (AC: 1, 2)
  - [x] Add Name text input (max 255 chars)
  - [x] Add Type select dropdown (Person/Vehicle/Unknown)
  - [x] Add VIP toggle switch
  - [x] Add Blocked toggle switch
  - [x] Add Notes textarea (max 2000 chars)
  - [x] Pre-fill fields with entity data
- [x] Task 3: Add form validation with Zod (AC: 6)
  - [x] Create validation schema
  - [x] Add inline error messages
  - [x] Validate on blur and submit
- [x] Task 4: Update useUpdateEntity mutation hook (AC: 3, 7)
  - [x] Extended `frontend/hooks/useEntities.ts` useUpdateEntity
  - [x] Call PUT /api/v1/context/entities/{id}
  - [x] Handle success toast
  - [x] Invalidate entity queries on success
- [x] Task 5: Add loading state to Save button (AC: 7)
  - [x] Disable button during mutation
  - [x] Show loading spinner
- [x] Task 6: Write tests for EntityEditModal (AC: all)
  - [x] Test modal opens with entity data
  - [x] Test form validation
  - [x] Test save triggers mutation
  - [x] Test cancel closes without saving

## Dev Notes

- **API Endpoint**: PUT /api/v1/context/entities/{id} (implemented in P16-3.1)
- **Updatable fields**: name, entity_type, is_vip, is_blocked, notes
- **entity_type values**: "person", "vehicle", "unknown"
- **Validation**: name max 255 chars, notes max 2000 chars
- **Dependencies**: shadcn/ui Dialog, Input, Select, Switch, Textarea, Button

### Project Structure Notes

- Component: `frontend/components/entities/EntityEditModal.tsx`
- Hook: `frontend/hooks/useUpdateEntity.ts`
- Follow existing modal patterns from EntityDetailModal and EntitySelectModal

### References

- [Source: docs/epics-phase16.md#Story-P16-3.2]
- [Source: backend/app/api/v1/context.py#EntityUpdateRequest] - API schema
- [Source: frontend/components/entities/EntityDetailModal.tsx] - Modal pattern to follow

### Learnings from Previous Story

**From Story P16-3.1 (API endpoint)**

- API endpoint implemented at PUT /api/v1/context/entities/{id}
- EntityUpdateRequest schema includes: name, entity_type, is_vip, is_blocked, notes
- entity_type uses Literal["person", "vehicle", "unknown"] validation
- notes max_length=2000, name max_length=255 already validated server-side

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

- Created EntityEditModal component with all form fields and validation
- Extended useUpdateEntity hook to support all entity properties (entity_type, is_vip, is_blocked, notes)
- Updated api-client.ts entities.update and entities.get to include all entity fields
- Updated IEntityUpdateRequest and IEntityDetail types for full entity support
- Added 12 passing tests covering all acceptance criteria

### File List

- `frontend/components/entities/EntityEditModal.tsx` (NEW)
- `frontend/__tests__/components/entities/EntityEditModal.test.tsx` (NEW)
- `frontend/hooks/useEntities.ts` (MODIFIED - extended UpdateEntityData interface)
- `frontend/lib/api-client.ts` (MODIFIED - entities.update and entities.get)
- `frontend/types/entity.ts` (MODIFIED - IEntityUpdateRequest, IEntityDetail)
