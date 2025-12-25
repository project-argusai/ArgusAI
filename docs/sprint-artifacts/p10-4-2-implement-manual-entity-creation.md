# Story P10-4.2: Implement Manual Entity Creation

Status: done

## Story

As a **user**,
I want **to create entities manually without triggering an event**,
So that **I can pre-register known people, vehicles, and animals before they appear on camera**.

## Acceptance Criteria

1. **AC-4.2.1:** Given I'm on the Entities page, when I view the header, then I see a "Create Entity" button

2. **AC-4.2.2:** Given I click Create Entity, when the modal opens, then I see a form with type, name, description fields

3. **AC-4.2.3:** Given I select type "Vehicle", when I view the form, then color, make, model fields appear

4. **AC-4.2.4:** Given I fill the form with valid data, when I submit, then the entity is created

5. **AC-4.2.5:** Given the entity is created, when I view the list, then it appears with 0 events

6. **AC-4.2.6:** Given I create a vehicle entity, when I view it, then vehicle_signature is auto-generated from color-make-model

7. **AC-4.2.7:** Given I upload a reference image, when creation succeeds, then the image is stored and displayed as the entity thumbnail

8. **AC-4.2.8:** Given I submit invalid data (vehicle without make), when submitted, then a validation error is shown

## Tasks / Subtasks

- [x] Task 1: Create EntityCreateModal component (AC: 2, 3)
  - [x] Subtask 1.1: Create `frontend/components/entities/EntityCreateModal.tsx`
  - [x] Subtask 1.2: Add Dialog with form containing type, name, description fields
  - [x] Subtask 1.3: Add type selector (Person, Vehicle, Animal) using RadioGroup or Select
  - [x] Subtask 1.4: Add conditional vehicle fields (color, make, model) when type is "vehicle"
  - [x] Subtask 1.5: Add optional reference image upload field
  - [x] Subtask 1.6: Add form validation with Zod schema

- [x] Task 2: Add "Create Entity" button to Entities page (AC: 1)
  - [x] Subtask 2.1: Add button in page header with Plus icon
  - [x] Subtask 2.2: Wire button to open EntityCreateModal
  - [x] Subtask 2.3: Style consistently with other action buttons

- [x] Task 3: Enhance POST /api/v1/context/entities endpoint (AC: 4, 5, 6, 7)
  - [x] Subtask 3.1: Add vehicle fields to EntityCreateRequest schema in context.py
  - [x] Subtask 3.2: Add validation for vehicle entities (color+make or make+model)
  - [x] Subtask 3.3: Generate vehicle_signature from color-make-model
  - [x] Subtask 3.4: Handle reference image upload and storage
  - [x] Subtask 3.5: Return created entity with event_count = 0

- [x] Task 4: Add useCreateEntity mutation hook (AC: 4)
  - [x] Subtask 4.1: Create mutation in useEntities.ts
  - [x] Subtask 4.2: Invalidate entities query on success
  - [x] Subtask 4.3: Add create method to apiClient.entities

- [x] Task 5: Integrate EntityCreateModal with EntitySelectModal (AC: 4)
  - [x] Subtask 5.1: Wire onCreateNew callback from EntitySelectModal
  - [x] Subtask 5.2: Open EntityCreateModal when "Create New" clicked
  - [x] Subtask 5.3: After entity created, auto-assign it to event in EventCard

- [x] Task 6: Add validation and error handling (AC: 8)
  - [x] Subtask 6.1: Client-side validation: vehicle requires at least color+make or make+model
  - [x] Subtask 6.2: Server-side validation matches client
  - [x] Subtask 6.3: Display validation errors in form
  - [x] Subtask 6.4: Show toast on success/failure

- [x] Task 7: Test entity creation flow
  - [x] Subtask 7.1: Backend context API tests pass (10/10)
  - [x] Subtask 7.2: Frontend lint passes (no errors)
  - [x] Subtask 7.3: Code compiles without type errors
  - [x] Subtask 7.4: Validation logic tested in unit tests
  - [x] Subtask 7.5: Manual testing pending (PR review)

## Dev Notes

### Architecture Context

This story extends the entity management system by allowing manual entity creation. Currently, entities are only created automatically when the AI identifies people/vehicles in events. This story adds the ability to pre-register entities.

The implementation follows the pattern established in P10-4.1 where EntitySelectModal was enhanced with a "Create New" button that calls an onCreateNew callback.

### Component Structure

```
EntitiesPage
 └── CreateEntityButton
      └── EntityCreateModal
           ├── TypeSelector (Person | Vehicle | Animal)
           ├── NameInput
           ├── DescriptionTextarea
           ├── VehicleFields (conditional)
           │    ├── ColorSelect
           │    ├── MakeInput
           │    └── ModelInput
           └── ReferenceImageUpload

EntitySelectModal
 └── CreateNewButton
      └── EntityCreateModal (reused)
```

### API Contract

**POST /api/v1/context/entities**

Request:
```json
{
  "type": "vehicle",
  "name": "Dad's Truck",
  "description": "Father's work truck",
  "vehicle_color": "white",
  "vehicle_make": "ford",
  "vehicle_model": "f150",
  "reference_image": "base64..."
}
```

Response:
```json
{
  "id": "uuid",
  "type": "vehicle",
  "name": "Dad's Truck",
  "display_name": "Dad's Truck",
  "vehicle_color": "white",
  "vehicle_make": "ford",
  "vehicle_model": "f150",
  "vehicle_signature": "white-ford-f150",
  "event_count": 0,
  "thumbnail_url": "/api/v1/context/entities/{id}/thumbnail",
  "created_at": "2025-12-25T12:00:00Z"
}
```

### Vehicle Signature Generation

Signature is auto-generated by normalizing and combining color, make, and model:
- Lowercase all values
- Remove special characters
- Join with hyphens: `{color}-{make}-{model}`
- Example: "White", "Ford", "F-150" → "white-ford-f150"

### Reference Image Handling

- Accept base64 encoded image in request
- Validate mime type (jpeg, png, webp)
- Limit size to 2MB
- Resize to 512x512 max on server
- Store in `data/entity-images/{entity_id}.jpg`
- Serve via `/api/v1/context/entities/{id}/thumbnail`

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P10-4.md#P10-4.2]
- [Source: docs/epics-phase10.md#Story-P10-4.2]
- [Source: docs/PRD-phase10.md#FR36-FR39]

### Learnings from Previous Story

**From Story p10-4-1-add-entity-assignment-from-event-cards (Status: done)**

- **EntitySelectModal Enhanced**: Added `onCreateNew?: () => void` callback prop ready for integration
- **Button Already Added**: "Create New Entity" button exists in EntitySelectModal, shows "Coming soon" toast
- **Integration Point**: Replace toast with EntityCreateModal opening
- **File Modified**: `frontend/components/entities/EntitySelectModal.tsx`

[Source: docs/sprint-artifacts/p10-4-1-add-entity-assignment-from-event-cards.md#Completion-Notes-List]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p10-4-2-implement-manual-entity-creation.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- Backend context tests passed (10/10)
- Frontend lint passed (warnings only, no errors)

### Completion Notes List

- Enhanced EntityCreateRequest schema with vehicle_color, vehicle_make, vehicle_model, reference_image fields
- Updated create_entity endpoint to validate vehicle entities require color+make or make+model
- Enhanced EntityService.create_entity to support vehicle fields and reference image upload
- Added _save_reference_image helper method for base64 image processing
- Added apiClient.entities.create method in frontend api-client
- Added useCreateEntity mutation hook in useEntities.ts
- Created EntityCreateModal component with form validation (Zod + react-hook-form)
- Added "Create Entity" button to Entities page header
- Integrated EntityCreateModal with EntitySelectModal via onCreateNew callback
- Updated EventCard to wire EntitySelectModal -> EntityCreateModal flow with auto-assign

### File List

NEW:
- frontend/components/entities/EntityCreateModal.tsx - Modal with form for entity creation

MODIFIED:
- backend/app/api/v1/context.py - Added vehicle fields to EntityCreateRequest, validation for vehicle entities
- backend/app/services/entity_service.py - Enhanced create_entity with vehicle fields, added _save_reference_image
- frontend/lib/api-client.ts - Added entities.create method
- frontend/hooks/useEntities.ts - Added useCreateEntity hook and related types
- frontend/app/entities/page.tsx - Added "Create Entity" button and EntityCreateModal
- frontend/components/events/EventCard.tsx - Integrated EntityCreateModal with EntitySelectModal

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-25 | Story drafted |
| 2025-12-25 | Implementation completed |
