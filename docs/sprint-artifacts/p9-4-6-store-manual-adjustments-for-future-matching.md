# Story P9-4.6: Store Manual Adjustments for Future Matching

Status: review

## Story

As a system administrator,
I want manual entity adjustments to be recorded and queryable,
so that future AI/ML can learn from user corrections and improve entity matching accuracy.

## Acceptance Criteria

1. **AC-4.6.1:** Given any manual operation (unlink/assign/move/merge), when complete, then EntityAdjustment record is created
2. **AC-4.6.2:** Given adjustment record, when stored, then includes event_id, old_entity_id, new_entity_id, action
3. **AC-4.6.3:** Given adjustment record, when stored, then includes event description snapshot
4. **AC-4.6.4:** Given adjustments exist, when querying API, then can retrieve adjustment history
5. **AC-4.6.5:** Given adjustment data, when exported, then suitable for ML training input

## Tasks / Subtasks

- [x] Task 1: Verify existing adjustment record creation (AC: #1, #2, #3)
  - [x] 1.1: Review unlink_event method creates adjustment records correctly
  - [x] 1.2: Review assign_event method creates adjustment records correctly
  - [x] 1.3: Review merge_entities method creates adjustment records correctly
  - [x] 1.4: Add test coverage for adjustment record fields

- [x] Task 2: Create GET /api/v1/context/adjustments endpoint (AC: #4)
  - [x] 2.1: Add AdjustmentListResponse and AdjustmentResponse Pydantic models
  - [x] 2.2: Add get_adjustments method to EntityService
  - [x] 2.3: Add GET /api/v1/context/adjustments endpoint with pagination
  - [x] 2.4: Add filtering by action type, entity_id, date range

- [x] Task 3: Create GET /api/v1/context/adjustments/export endpoint (AC: #5)
  - [x] 3.1: Add export endpoint returning JSON Lines format
  - [x] 3.2: Include event description, entity types, and correction context
  - [x] 3.3: Add date range filtering for export

- [x] Task 4: Add useAdjustments hook for frontend (optional) (AC: #4)
  - [x] 4.1: Skipped - Frontend hook not required for initial backend implementation
  - [x] 4.2: Skipped - TypeScript types can be added when frontend integration needed

- [x] Task 5: Write tests (AC: all)
  - [x] 5.1: Test adjustment records contain all required fields
  - [x] 5.2: Test GET /adjustments endpoint pagination
  - [x] 5.3: Test GET /adjustments filtering by action type
  - [x] 5.4: Test export endpoint returns valid JSON Lines

## Dev Notes

### Learnings from Previous Story

**From Story P9-4.5 (Status: done)**

- **EntityAdjustment Model**: Already exists at `backend/app/models/entity_adjustment.py` with fields:
  - id, event_id, old_entity_id, new_entity_id, action, event_description, created_at
- **Adjustment Actions**: "unlink", "assign", "move_from", "move_to", "merge" already defined
- **Entity Service**: Methods `unlink_event()`, `assign_event()`, `merge_entities()` already create adjustment records
- **Transaction Patterns**: All entity modifications are atomic with proper transaction handling

[Source: docs/sprint-artifacts/p9-4-5-implement-entity-merge.md#Dev-Agent-Record]

**From Story P9-4.4 (Status: done)**

- **Dual Adjustment Pattern**: Move operations create TWO records (move_from and move_to)
- **Event Description Snapshot**: Always captured at time of adjustment for ML context

[Source: docs/sprint-artifacts/p9-4-4-implement-event-entity-assignment.md]

### Architecture Notes

**Existing EntityAdjustment Model:**
```python
class EntityAdjustment(Base):
    __tablename__ = "entity_adjustments"

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("events.id"))
    old_entity_id = Column(String, ForeignKey("recognized_entities.id"))
    new_entity_id = Column(String, ForeignKey("recognized_entities.id"))
    action = Column(String(20))  # unlink, assign, move_from, move_to, merge
    event_description = Column(Text)  # Snapshot for ML training
    created_at = Column(DateTime)
```

**API Design:**
```
GET /api/v1/context/adjustments
Parameters:
  - page: int (default 1)
  - limit: int (default 50, max 100)
  - action: str (optional filter: unlink, assign, move, merge)
  - entity_id: str (optional filter by old or new entity)
  - start_date: datetime (optional)
  - end_date: datetime (optional)

Response:
{
  "adjustments": [
    {
      "id": "uuid",
      "event_id": "uuid",
      "old_entity_id": "uuid or null",
      "new_entity_id": "uuid or null",
      "action": "unlink",
      "event_description": "Person walking...",
      "created_at": "2025-12-22T10:30:00Z"
    }
  ],
  "total": 150,
  "page": 1,
  "limit": 50
}
```

**Export Format (JSON Lines):**
```jsonl
{"event_id":"uuid","action":"unlink","old_entity_id":"uuid","new_entity_id":null,"event_description":"Person in red jacket...","created_at":"2025-12-22T10:30:00Z"}
{"event_id":"uuid","action":"assign","old_entity_id":null,"new_entity_id":"uuid","event_description":"White Toyota Camry...","created_at":"2025-12-22T10:35:00Z"}
```

### Project Structure Notes

**Backend Files:**
- Model: `backend/app/models/entity_adjustment.py` (EXISTS)
- Service: `backend/app/services/entity_service.py` (add get_adjustments method)
- API: `backend/app/api/v1/context.py` (add adjustments endpoints)

**Frontend Files (optional):**
- Hook: `frontend/hooks/useEntities.ts` (add useAdjustments if needed)

### This Story's Primary Purpose

This story validates and completes the adjustment tracking infrastructure established in P9-4.3, P9-4.4, and P9-4.5. The main new work is:
1. API endpoint to query adjustment history
2. Export endpoint for ML training data
3. Ensure all adjustment records have complete data

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-4.md#P9-4.6]
- [Source: docs/epics-phase9.md#Story P9-4.6]
- [Source: backend/app/models/entity_adjustment.py]
- [Source: backend/app/services/entity_service.py]
- [Source: backend/app/api/v1/context.py]

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-12-22 | Story drafted from epics-phase9.md and tech-spec-epic-P9-4.md | BMAD Workflow |
| 2025-12-22 | Implemented: verified adjustment records, added endpoints, wrote tests | Claude Opus 4.5 |

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p9-4-6-store-manual-adjustments-for-future-matching.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- Verified existing adjustment creation in unlink_event(), assign_event(), and merge_entities() methods
- Added AdjustmentResponse and AdjustmentListResponse Pydantic models to context.py
- Added get_adjustments() method to EntityService with pagination and filtering
- Added export_adjustments() method returning ML-friendly format with entity types
- Added GET /api/v1/context/adjustments endpoint with pagination and filtering
- Added GET /api/v1/context/adjustments/export endpoint returning JSON Lines
- Created 23 tests in test_context_adjustments.py and test_entity_service.py
- All tests pass

### File List

- backend/app/api/v1/context.py (modified - added adjustment endpoints and Pydantic models)
- backend/app/services/entity_service.py (modified - added get_adjustments and export_adjustments methods)
- backend/tests/test_api/test_context_adjustments.py (created - API endpoint tests)
- backend/tests/test_services/test_entity_service.py (modified - added service method tests)
- docs/sprint-artifacts/p9-4-6-store-manual-adjustments-for-future-matching.md (modified - story file)
- docs/sprint-artifacts/p9-4-6-store-manual-adjustments-for-future-matching.context.xml (created - context file)
- docs/sprint-artifacts/sprint-status.yaml (modified - status updates)
