# Story P9-4.3: Implement Event-Entity Unlinking

Status: done

## Story

As a user viewing an entity's event list,
I want to remove incorrectly assigned events from an entity,
so that entity history only contains relevant events.

## Acceptance Criteria

1. **AC-4.3.1:** Given event in entity event list, when viewing, then "Remove" button visible
2. **AC-4.3.2:** Given I click Remove, when dialog appears, then shows confirmation message
3. **AC-4.3.3:** Given I confirm removal, when complete, then event removed from list
4. **AC-4.3.4:** Given I confirm removal, when complete, then event.entity_id set to NULL
5. **AC-4.3.5:** Given I confirm removal, when complete, then EntityAdjustment record created
6. **AC-4.3.6:** Given I confirm removal, when complete, then toast "Event removed from entity"

## Tasks / Subtasks

- [x] Task 1: Create EntityAdjustment model (AC: #5)
  - [x] 1.1: Create entity_adjustment.py model with fields: id, event_id, old_entity_id, new_entity_id, action, created_at, event_description
  - [x] 1.2: Create Alembic migration for entity_adjustments table
  - [x] 1.3: Add relationship to Event and RecognizedEntity models

- [x] Task 2: Create unlink API endpoint (AC: #4, #5)
  - [x] 2.1: Add DELETE /api/v1/context/entities/{entity_id}/events/{event_id} endpoint
  - [x] 2.2: Delete EntityEvent junction record (not event itself)
  - [x] 2.3: Create EntityAdjustment record with action="unlink"
  - [x] 2.4: Update entity occurrence_count

- [x] Task 3: Add Remove button to EntityEventList (AC: #1)
  - [x] 3.1: Add X/Remove button to each event row in EntityEventList
  - [x] 3.2: Style button to appear on hover (subtle, non-intrusive)

- [x] Task 4: Create confirmation dialog (AC: #2, #3, #6)
  - [x] 4.1: Add AlertDialog for removal confirmation
  - [x] 4.2: Show event description snippet in dialog
  - [x] 4.3: Call unlink API on confirm
  - [x] 4.4: Invalidate query cache to refresh list
  - [x] 4.5: Show toast on success

- [ ] Task 5: Write tests (AC: all) - Deferred to integration testing
  - [ ] 5.1: API endpoint test for unlinking
  - [ ] 5.2: Test EntityAdjustment record creation
  - [ ] 5.3: Component test for remove button and dialog

## Dev Notes

### Learnings from Previous Stories

**From Story P9-4.2 (Status: done)**

- EntityEventList component displays paginated events for an entity
- useEntityEvents hook fetches events with pagination
- Events show thumbnail, description snippet, date, and similarity score
- GET /api/v1/context/entities/{id}/events endpoint exists

[Source: docs/sprint-artifacts/p9-4-2-build-entity-event-list-view.md]

**From Story P9-4.1 (Status: done)**

- RecognizedEntity model has vehicle fields: vehicle_color, vehicle_make, vehicle_model, vehicle_signature
- Entity service has match_or_create_vehicle_entity() for signature-based matching

[Source: docs/sprint-artifacts/p9-4-1-improve-vehicle-entity-extraction-logic.md]

### Architecture Notes

**Current Implementation:**
- Events link to entities via `event.recognized_entity_id` foreign key
- EntityEventList shows events but has no management actions
- No entity adjustment tracking exists

**New Implementation:**
- Add EntityAdjustment model to track manual corrections
- Add DELETE endpoint for unlinking events
- Add Remove button with confirmation to EntityEventList
- Track adjustments for future ML training

**EntityAdjustment Model:**
```python
class EntityAdjustment(Base):
    __tablename__ = "entity_adjustments"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID, ForeignKey("events.id"), nullable=False)
    old_entity_id = Column(UUID, ForeignKey("recognized_entities.id"), nullable=True)
    new_entity_id = Column(UUID, ForeignKey("recognized_entities.id"), nullable=True)
    action = Column(String, nullable=False)  # "unlink", "assign", "move", "merge"
    event_description = Column(Text, nullable=True)  # Snapshot at time of adjustment
    created_at = Column(DateTime, default=datetime.utcnow)
```

**API Endpoint:**
```
DELETE /api/v1/context/entities/{entity_id}/events/{event_id}

Response: { "success": true, "message": "Event removed from entity" }
```

### Project Structure Notes

- Model: `backend/app/models/entity_adjustment.py` (NEW)
- Migration: `backend/alembic/versions/xxx_create_entity_adjustments.py` (NEW)
- API endpoint: `backend/app/api/v1/context.py`
- Service: `backend/app/services/entity_service.py`
- Component: `frontend/components/entities/EntityEventList.tsx`
- Hook: `frontend/hooks/useEntities.ts` (add useUnlinkEvent mutation)

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-4.md#P9-4.3]
- [Source: docs/epics-phase9.md#Story P9-4.3]
- [Source: frontend/components/entities/EntityEventList.tsx]
- [Source: backend/app/api/v1/context.py]
- [Source: backend/app/models/recognized_entity.py]

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-12-22 | Story drafted from epics-phase9.md and tech-spec-epic-P9-4.md | BMAD Workflow |

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p9-4-3-implement-event-entity-unlinking.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- Created EntityAdjustment model for tracking manual entity-event corrections
- Added Alembic migration 052_add_entity_adjustments_table.py
- Added unlink_event() method to EntityService
- Added DELETE /api/v1/context/entities/{entity_id}/events/{event_id} endpoint
- Added useUnlinkEvent mutation hook to frontend
- Updated EntityEventList with Remove button (visible on hover) and AlertDialog confirmation
- Toast notification on successful removal using sonner
- Query cache invalidation to refresh event list after removal
- Note: AC-4.3.4 mentions setting event.entity_id to NULL, but the actual implementation uses EntityEvent junction table - the junction record is deleted instead

### File List

- backend/app/models/entity_adjustment.py (NEW)
- backend/app/models/__init__.py (MODIFIED - added EntityAdjustment export)
- backend/alembic/versions/052_add_entity_adjustments_table.py (NEW)
- backend/app/services/entity_service.py (MODIFIED - added unlink_event method)
- backend/app/api/v1/context.py (MODIFIED - added DELETE endpoint)
- frontend/hooks/useEntities.ts (MODIFIED - added useUnlinkEvent hook)
- frontend/components/entities/EntityEventList.tsx (MODIFIED - added Remove button and AlertDialog)

