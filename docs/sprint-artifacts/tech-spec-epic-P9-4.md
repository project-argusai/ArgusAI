# Epic Technical Specification: Entity Management

Date: 2025-12-22
Author: Brent
Epic ID: P9-4
Status: Draft

---

## Overview

Epic P9-4 enhances the entity management system to enable users to correct and manage entity-event associations. Currently, vehicle entities are not properly separated by make/model, and users cannot manually adjust which events belong to which entities. This epic improves vehicle extraction logic, builds entity event management UI, and stores manual adjustments for future matching improvements.

The goal is to create a self-improving entity recognition system where user corrections feed back into better future matching, laying the groundwork for the local MCP server (IMP-016) that will aggregate this context.

## Objectives and Scope

**In Scope:**
- Improve vehicle entity extraction to separate by make/model/color (BUG-011)
- Build entity event list view showing all linked events (IMP-015)
- Implement event-entity unlinking (remove misattributed events) (IMP-015)
- Implement event-entity assignment (add events to entities) (IMP-015)
- Implement entity merge functionality (IMP-015)
- Store manual adjustments for future ML training (IMP-015, IMP-016)

**Out of Scope:**
- Local MCP server implementation (IMP-016) - research only in this epic
- Automated re-matching based on corrections
- Person/face recognition improvements
- Entity deletion (handled by retention policy)

## System Architecture Alignment

This epic extends the entity system introduced in Phase 4:

| Component | Files Affected | Changes |
|-----------|---------------|---------|
| Entity Model | `backend/app/models/entity.py` | Add vehicle fields, signature |
| Entity Service | `backend/app/services/entity_service.py` | Improve extraction, add management |
| Entity API | `backend/app/api/v1/entities.py` | Add management endpoints |
| Adjustment Model | `backend/app/models/entity_adjustment.py` | NEW: Track corrections |
| Entity List Page | `frontend/app/entities/page.tsx` | Add multi-select, merge |
| Entity Detail | `frontend/app/entities/[id]/page.tsx` | Add event list, management |
| Event Card | `frontend/components/events/EventCard.tsx` | Add "Add to Entity" action |
| Entity Select Modal | `frontend/components/entities/EntitySelectModal.tsx` | NEW: Entity picker |

### Entity Management Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Entity System                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Entity     │    │    Event     │    │  Adjustment  │      │
│  │   Model      │◄───│   Model      │    │    Model     │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │               │
│         │                   │                   │               │
│  ┌──────▼──────────────────▼───────────────────▼──────┐        │
│  │                  Entity Service                      │        │
│  │  - extractEntity()     - linkEvent()                │        │
│  │  - matchEntity()       - unlinkEvent()              │        │
│  │  - mergeEntities()     - recordAdjustment()         │        │
│  └─────────────────────────────────────────────────────┘        │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────┐        │
│  │                    Entity API                        │        │
│  │  GET /entities           POST /entities/merge       │        │
│  │  GET /entities/{id}      DELETE /entities/{id}/events/{eid} │
│  │  GET /entities/{id}/events  POST /events/{id}/entity │       │
│  └─────────────────────────────────────────────────────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Inputs | Outputs |
|---------------|----------------|--------|---------|
| EntityExtractionService | Extract entities from descriptions | AI description | Entity data |
| EntityMatchingService | Match events to existing entities | Entity data, existing entities | Matched entity or new |
| EntityManagementService | Handle manual corrections | User actions | Updated relationships |
| AdjustmentTrackingService | Record all manual changes | Adjustments | Audit records |

### Data Models and Contracts

**Enhanced Entity Model:**
```python
class Entity(Base):
    __tablename__ = "entities"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    type = Column(String, nullable=False)  # "person", "vehicle", "animal"
    name = Column(String, nullable=True)   # User-assigned name

    # Vehicle-specific fields (NEW)
    vehicle_color = Column(String, nullable=True)
    vehicle_make = Column(String, nullable=True)
    vehicle_model = Column(String, nullable=True)
    vehicle_signature = Column(String, nullable=True, index=True)  # "white-toyota-camry"

    # Person-specific fields (existing)
    face_embedding = Column(LargeBinary, nullable=True)

    # Metadata
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    event_count = Column(Integer, default=0)

    # Relationships
    events = relationship("Event", back_populates="entity")
    adjustments = relationship("EntityAdjustment", back_populates="entity")

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.type == "vehicle" and self.vehicle_signature:
            return self.vehicle_signature.replace("-", " ").title()
        return f"{self.type.title()} #{str(self.id)[:8]}"
```

**New EntityAdjustment Model:**
```python
class EntityAdjustment(Base):
    __tablename__ = "entity_adjustments"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID, ForeignKey("events.id"), nullable=False)
    old_entity_id = Column(UUID, ForeignKey("entities.id"), nullable=True)
    new_entity_id = Column(UUID, ForeignKey("entities.id"), nullable=True)
    action = Column(String, nullable=False)  # "unlink", "assign", "move", "merge"
    created_at = Column(DateTime, default=datetime.utcnow)

    # Metadata for ML training
    event_description = Column(Text, nullable=True)  # Snapshot at time of adjustment
    confidence_before = Column(Float, nullable=True)

    # Relationships
    event = relationship("Event")
    old_entity = relationship("Entity", foreign_keys=[old_entity_id])
    new_entity = relationship("Entity", foreign_keys=[new_entity_id])
```

**Vehicle Extraction Patterns:**
```python
VEHICLE_COLORS = [
    "white", "black", "silver", "gray", "grey", "red", "blue",
    "green", "brown", "tan", "beige", "gold", "yellow", "orange",
    "purple", "maroon", "navy"
]

VEHICLE_MAKES = [
    "toyota", "honda", "ford", "chevrolet", "chevy", "nissan",
    "bmw", "mercedes", "audi", "lexus", "hyundai", "kia",
    "volkswagen", "vw", "subaru", "mazda", "jeep", "dodge",
    "ram", "gmc", "tesla", "volvo", "acura", "infiniti"
]

# Common model patterns
VEHICLE_MODEL_PATTERNS = [
    r"camry|accord|civic|corolla|altima|sentra|f-?150|silverado",
    r"mustang|charger|challenger|wrangler|rav4|cr-v|pilot",
    r"model\s*[3sxy]|tacoma|tundra|highlander|4runner"
]
```

### APIs and Interfaces

**Entity Management Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/entities` | List all entities (with search) |
| GET | `/api/v1/entities/{id}` | Get entity details |
| GET | `/api/v1/entities/{id}/events` | Get events for entity (paginated) |
| DELETE | `/api/v1/entities/{id}/events/{event_id}` | Unlink event from entity |
| POST | `/api/v1/events/{id}/entity` | Assign event to entity |
| POST | `/api/v1/entities/merge` | Merge two entities |
| GET | `/api/v1/entities/adjustments` | Get adjustment history |

**Entity List Response:**
```json
{
  "entities": [
    {
      "id": "uuid",
      "type": "vehicle",
      "display_name": "White Toyota Camry",
      "vehicle_color": "white",
      "vehicle_make": "toyota",
      "vehicle_model": "camry",
      "vehicle_signature": "white-toyota-camry",
      "event_count": 15,
      "first_seen": "2025-12-01T08:00:00Z",
      "last_seen": "2025-12-22T14:30:00Z",
      "thumbnail_url": "/api/v1/events/{latest_event_id}/thumbnail"
    }
  ],
  "total": 25,
  "page": 1,
  "limit": 20
}
```

**Entity Events Response:**
```json
{
  "entity_id": "uuid",
  "entity_name": "White Toyota Camry",
  "events": [
    {
      "id": "uuid",
      "description": "White Toyota Camry arriving in driveway",
      "timestamp": "2025-12-22T14:30:00Z",
      "camera_name": "Driveway",
      "thumbnail_url": "/api/v1/events/{id}/thumbnail"
    }
  ],
  "total": 15,
  "page": 1,
  "limit": 20
}
```

**Unlink Event Request:**
```
DELETE /api/v1/entities/{entity_id}/events/{event_id}
```

**Assign Event Request:**
```json
POST /api/v1/events/{event_id}/entity
{
  "entity_id": "uuid"
}
```

**Merge Entities Request:**
```json
POST /api/v1/entities/merge
{
  "primary_entity_id": "uuid",  // Entity to keep
  "secondary_entity_id": "uuid"  // Entity to merge into primary
}
```

**Merge Response:**
```json
{
  "merged_entity_id": "uuid",
  "events_moved": 8,
  "deleted_entity_id": "uuid"
}
```

### Workflows and Sequencing

**Vehicle Entity Extraction (Enhanced):**

```python
def extract_vehicle_entity(description: str) -> Optional[VehicleEntity]:
    """Extract vehicle details from AI description."""
    description_lower = description.lower()

    # Extract color
    color = None
    for c in VEHICLE_COLORS:
        if c in description_lower:
            color = c
            break

    # Extract make
    make = None
    for m in VEHICLE_MAKES:
        if m in description_lower:
            make = m
            break

    # Extract model using patterns
    model = None
    for pattern in VEHICLE_MODEL_PATTERNS:
        match = re.search(pattern, description_lower)
        if match:
            model = match.group()
            break

    # Need at least color + make OR make + model
    if not ((color and make) or (make and model)):
        return None

    # Build signature for matching
    parts = [p for p in [color, make, model] if p]
    signature = "-".join(parts)

    return VehicleEntity(
        color=color,
        make=make,
        model=model,
        signature=signature
    )
```

**Entity Matching Flow:**

```
1. Extract entity data from description
2. If vehicle:
   a. Generate signature (color-make-model)
   b. Search existing entities by signature
   c. If exact match: link to existing
   d. If partial match (same make+model, different color): suggest but create new
   e. If no match: create new entity
3. If person:
   a. Use face embedding similarity (existing logic)
4. Record entity-event link
```

**Event Unlinking Flow:**

```
1. User clicks "Remove" on event in entity detail
2. Confirmation dialog: "Remove this event from [Entity Name]?"
3. On confirm:
   a. Set event.entity_id = NULL
   b. Create EntityAdjustment record:
      - action: "unlink"
      - old_entity_id: original entity
      - new_entity_id: NULL
      - event_description: snapshot
4. Update entity.event_count
5. Toast: "Event removed from entity"
```

**Event Assignment Flow:**

```
1. User clicks "Add to Entity" on event card (or "Move to Entity" if already assigned)
2. EntitySelectModal opens with searchable entity list
3. User searches/selects entity
4. On confirm:
   a. If moving: record old entity
   b. Set event.entity_id = selected entity
   c. Create EntityAdjustment record:
      - action: "assign" or "move"
      - old_entity_id: previous (or NULL)
      - new_entity_id: selected
5. Update entity counts
6. Toast: "Event added to [Entity Name]"
```

**Entity Merge Flow:**

```
1. User selects two entities in list (checkbox)
2. "Merge" button becomes active
3. Merge dialog shows:
   - Entity A: [Name] (X events)
   - Entity B: [Name] (Y events)
   - "Which entity should be kept?"
4. User selects primary (default: more events)
5. On confirm:
   a. Move all events from secondary to primary
   b. Create EntityAdjustment for each moved event
   c. Delete secondary entity
   d. Update primary.event_count
6. Toast: "Entities merged successfully"
```

---

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| Entity search | <200ms | API response time |
| Entity events list | <300ms | Paginated, 20 per page |
| Unlink operation | <200ms | Including adjustment record |
| Merge operation | <1 second | For up to 100 events |
| Entity extraction | <50ms | Per description |

### Storage

| Item | Size | Notes |
|------|------|-------|
| Entity record | ~500 bytes | Plus face embedding if person |
| Adjustment record | ~300 bytes | One per manual action |
| 100 adjustments/day | ~30KB/day | Minimal overhead |

### Reliability

- Entity extraction failure should not block event processing
- Merge should be atomic (all or nothing)
- Adjustment records should never be lost
- UI should handle missing entities gracefully

### Observability

- Log entity extraction success/failure rates
- Log signature matching decisions
- Track adjustment frequency by type
- Monitor entity growth rate

---

## Dependencies and Integrations

### Backend Dependencies

```
# No new dependencies - using existing stack
```

### Frontend Dependencies

```json
{
  "dependencies": {
    // No new dependencies - using existing shadcn/ui
  }
}
```

### Internal Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| Entity Model | P4 | Base entity system |
| AIService | P3 | Descriptions for extraction |
| Event Model | P1 | Event-entity relationships |

---

## Acceptance Criteria (Authoritative)

### P9-4.1: Improve Vehicle Entity Extraction Logic

**AC-4.1.1:** Given description "A white Toyota Camry pulled into the driveway", when extracted, then color="white", make="toyota", model="camry"
**AC-4.1.2:** Given description "Black Ford F-150 parked on street", when extracted, then signature="black-ford-f150"
**AC-4.1.3:** Given two descriptions of same vehicle signature, when matched, then linked to same entity
**AC-4.1.4:** Given two different vehicle signatures, when matched, then create separate entities
**AC-4.1.5:** Given vehicle with only color mentioned, when extracted, then entity not created (insufficient data)
**AC-4.1.6:** Given vehicle with make and model but no color, when extracted, then entity created with partial signature

### P9-4.2: Build Entity Event List View

**AC-4.2.1:** Given entity detail page, when viewing, then "Events" section shows all linked events
**AC-4.2.2:** Given entity with 50 events, when viewing list, then paginated (20 per page)
**AC-4.2.3:** Given event in list, when viewing, then shows thumbnail, description snippet, date
**AC-4.2.4:** Given event list, when sorted, then newest first by default
**AC-4.2.5:** Given entity with 0 events, when viewing, then "No events linked" message shown

### P9-4.3: Implement Event-Entity Unlinking

**AC-4.3.1:** Given event in entity event list, when viewing, then "Remove" button visible
**AC-4.3.2:** Given I click Remove, when dialog appears, then shows confirmation message
**AC-4.3.3:** Given I confirm removal, when complete, then event removed from list
**AC-4.3.4:** Given I confirm removal, when complete, then event.entity_id set to NULL
**AC-4.3.5:** Given I confirm removal, when complete, then EntityAdjustment record created
**AC-4.3.6:** Given I confirm removal, when complete, then toast "Event removed from entity"

### P9-4.4: Implement Event-Entity Assignment

**AC-4.4.1:** Given event card with no entity, when viewing, then "Add to Entity" button visible
**AC-4.4.2:** Given event card with entity, when viewing, then "Move to Entity" button visible
**AC-4.4.3:** Given I click Add to Entity, when modal opens, then searchable entity list shown
**AC-4.4.4:** Given entity search, when I type "toyota", then matching entities filtered
**AC-4.4.5:** Given I select entity, when confirmed, then event linked to entity
**AC-4.4.6:** Given assignment complete, when viewing event, then entity name shown
**AC-4.4.7:** Given move operation, when complete, then both old unlink and new assign recorded

### P9-4.5: Implement Entity Merge

**AC-4.5.1:** Given entities list, when viewing, then checkboxes for multi-select
**AC-4.5.2:** Given two entities selected, when viewing, then "Merge" button enabled
**AC-4.5.3:** Given I click Merge, when dialog opens, then shows both entities with event counts
**AC-4.5.4:** Given merge dialog, when viewing, then can choose which entity to keep
**AC-4.5.5:** Given I confirm merge, when complete, then all events moved to primary
**AC-4.5.6:** Given I confirm merge, when complete, then secondary entity deleted
**AC-4.5.7:** Given I confirm merge, when complete, then toast "Entities merged successfully"
**AC-4.5.8:** Given merge with 50 events, when complete, then operation succeeds

### P9-4.6: Store Manual Adjustments for Future Matching

**AC-4.6.1:** Given any manual operation (unlink/assign/move/merge), when complete, then EntityAdjustment record created
**AC-4.6.2:** Given adjustment record, when stored, then includes event_id, old_entity_id, new_entity_id, action
**AC-4.6.3:** Given adjustment record, when stored, then includes event description snapshot
**AC-4.6.4:** Given adjustments exist, when querying API, then can retrieve adjustment history
**AC-4.6.5:** Given adjustment data, when exported, then suitable for ML training input

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC-4.1.1-6 | Entity Extraction | entity_service.py | Unit test with sample descriptions |
| AC-4.2.1-5 | Event List UI | EntityDetail page | Component test |
| AC-4.3.1-6 | Unlinking | entities.py, EntityDetail | Integration test |
| AC-4.4.1-7 | Assignment | events.py, EntitySelectModal | Integration + component test |
| AC-4.5.1-8 | Merge | entities.py, EntityList | Integration test |
| AC-4.6.1-5 | Adjustments | entity_adjustment.py | Integration test |

---

## Risks, Assumptions, Open Questions

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Vehicle extraction misses variations | High | Medium | Expand patterns, log failures |
| Users abuse merge to corrupt data | Low | Medium | Require confirmation, audit log |
| Adjustment data too noisy for ML | Medium | Low | Filter by confidence, require patterns |
| Large entity merges slow | Low | Low | Batch updates, progress indicator |

### Assumptions

- AI descriptions consistently mention vehicle details when visible
- Users understand entity concept
- Vehicle make/model list covers common vehicles
- Adjustment data will be useful for future ML

### Open Questions

- **Q1:** Should we support "undo" for merge operations?
  - **A:** No - too complex. Use adjustments for audit trail only.

- **Q2:** Minimum events before entity is visible?
  - **A:** 1 event - show all entities, let users manage

- **Q3:** Should extraction handle non-English vehicle names?
  - **A:** Start with English only, expand based on user feedback

- **Q4:** Export format for adjustment data?
  - **A:** JSON Lines for ML training, include description context

---

## Test Strategy Summary

### Test Levels

| Level | Scope | Tools | Coverage |
|-------|-------|-------|----------|
| Unit | Extraction logic | pytest | Vehicle parsing |
| Integration | Entity API | pytest | CRUD + merge |
| Component | UI elements | vitest, RTL | List, modal, buttons |
| E2E | Full management flow | Manual | User journeys |

### Test Cases by Story

**P9-4.1 (Extraction):**
- Unit: Color extraction from various positions
- Unit: Make/model extraction
- Unit: Signature generation
- Unit: Partial data handling

**P9-4.2 (Event List):**
- Component: List renders with events
- Component: Pagination works
- Component: Empty state displays

**P9-4.3 (Unlinking):**
- Component: Remove button renders
- Component: Confirmation dialog
- Integration: Event unlinked in DB
- Integration: Adjustment recorded

**P9-4.4 (Assignment):**
- Component: Modal renders
- Component: Search filters
- Integration: Event assigned
- Integration: Move records both

**P9-4.5 (Merge):**
- Component: Multi-select works
- Component: Merge dialog
- Integration: Events moved
- Integration: Entity deleted
- Performance: Large merge

**P9-4.6 (Adjustments):**
- Integration: Records created
- Integration: History queryable
- Unit: Export format

### Test Data

- Sample descriptions with various vehicle formats
- Entities with different event counts
- Edge cases: similar signatures, partial matches

---

_Generated by BMAD Epic Tech Context Workflow_
_Date: 2025-12-22_
_For: Brent_
