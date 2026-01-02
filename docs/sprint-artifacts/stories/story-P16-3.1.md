# Story P16-3.1: Create Entity Update API Endpoint

Status: done

## Story

As a **backend developer**,
I want **an endpoint to update entity metadata**,
So that **users can edit entity properties**.

## Acceptance Criteria

1. **AC1**: Given a valid entity ID, when I call `PUT /api/v1/context/entities/{id}` with `{"name": "Mail Carrier"}`, then the entity name is updated and the response returns the updated entity object
2. **AC2**: Given partial updates, when I only send `{"is_vip": true}`, then only is_vip is updated, other fields unchanged
3. **AC3**: Given invalid entity_type value, when I send `{"entity_type": "invalid"}`, then I receive 422 with validation error
4. **AC4**: Updatable fields: name, entity_type, is_vip, is_blocked, notes
5. **AC5**: entity_type must be: person, vehicle, unknown
6. **AC6**: name max length: 255 characters
7. **AC7**: notes max length: 2000 characters
8. **AC8**: updated_at timestamp is set automatically
9. **AC9**: Requires authenticated user (any role can edit)

## Tasks / Subtasks

- [x] Task 1: Verify PUT endpoint exists (AC: 1, 2, 6, 8, 9)
  - [x] Endpoint already exists at `/api/v1/context/entities/{id}`
  - [x] Partial updates work (Optional fields)
  - [x] name max_length=255 already in schema
  - [x] updated_at auto-updates via onupdate
  - [x] Requires authentication
- [x] Task 2: Add entity_type field to EntityUpdateRequest (AC: 3, 4, 5)
  - [x] Add Literal["person", "vehicle", "unknown"] field
  - [x] Add validation for entity_type
- [x] Task 3: Add notes max_length validation (AC: 7)
  - [x] Add max_length=2000 to notes field
- [x] Task 4: Update EntityService.update_entity to handle entity_type (AC: 4)
  - [x] Pass entity_type to service method
  - [x] Update entity type in database
- [x] Task 5: Write/update tests (AC: all)
  - [x] Test entity_type update
  - [x] Test invalid entity_type returns 422
  - [x] Test notes max_length validation

## Dev Notes

- PUT endpoint already exists at `backend/app/api/v1/context.py:1138`
- EntityUpdateRequest schema at `backend/app/api/v1/context.py:536`
- Currently missing: entity_type field, notes max_length validation
- EntityService.update_entity method needs entity_type parameter added

### Project Structure Notes

- Backend API: `backend/app/api/v1/context.py`
- Entity Model: `backend/app/models/recognized_entity.py`
- Entity Service: `backend/app/services/entity_service.py`

### References

- [Source: docs/epics-phase16.md#Story-P16-3.1]
- [Source: backend/app/api/v1/context.py#EntityUpdateRequest]
- [Source: backend/app/models/recognized_entity.py#RecognizedEntity]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

- Added `entity_type` field with Literal validation to EntityUpdateRequest schema
- Added `max_length=2000` to notes field in EntityUpdateRequest
- Updated EntityService.update_entity to handle entity_type parameter
- Added 6 new tests covering entity_type updates, validation, and notes max_length

### File List

- `backend/app/api/v1/context.py` - EntityUpdateRequest schema and endpoint updates
- `backend/app/services/entity_service.py` - Added entity_type parameter
- `backend/tests/test_api/test_entity_api.py` - Added P16-3.1 tests
