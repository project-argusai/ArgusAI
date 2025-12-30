# Epic Technical Specification: Multi-Entity Event Support

Date: 2025-12-30
Author: Brent
Epic ID: P15-4
Status: Draft

---

## Overview

Epic P15-4 enables events to be associated with multiple entities, supporting real-world scenarios like two people walking together, a person with a vehicle, or a delivery person with a package. This epic extends the existing single-entity event model to a many-to-many relationship while maintaining backward compatibility.

## Objectives and Scope

**In Scope:**
- Backend support for multiple entities per event (FR33)
- Multi-entity badges on event cards (FR34)
- Entity detail shows all events where entity appears (FR35)
- Multi-select entity assignment UI (FR36)
- Alert rules trigger on any matched entity (FR37)

**Out of Scope:**
- Automatic multi-entity detection by AI (requires prompt changes, separate story)
- Entity relationship tracking (e.g., "John is usually with his car")
- Entity co-occurrence analytics
- Changes to entity matching algorithm

**Prerequisites:**
- P15-1.1 (Entity modal scrolling) - Multi-entity events need working entity modals

## System Architecture Alignment

This epic extends existing entity-event relationships:

- **EntityEvent junction table** - Already exists from Phase 9, used for many-to-many (ADR-P15-006)
- **matched_entity_ids JSON field** - Denormalized array for fast reads
- **Event model extensions** - Support array of entities
- **Alert engine updates** - Check all matched entities against rules

Reference: [Phase 15 Architecture](../architecture/phase-15-additions.md#adr-p15-006-multi-entity-via-entityevent-junction-table)

## Detailed Design

### Services and Modules

| Component | Responsibility | File |
|-----------|---------------|------|
| Event Model | Extended with matched_entity_ids array | `backend/app/models/event.py` |
| EntityEvent | Junction table (existing) | `backend/app/models/entity.py` |
| EventService | Multi-entity assignment logic | `backend/app/services/event_service.py` |
| AlertEngine | Check all entities in event | `backend/app/services/alert_engine.py` |
| EventCard | Multi-entity badge display | `frontend/components/events/EventCard.tsx` |
| EntityAssignmentModal | Multi-select UI | `frontend/components/events/EntityAssignmentModal.tsx` |

### Data Models and Contracts

**Existing EntityEvent Junction Table:**

```sql
-- Already exists from Phase 9
CREATE TABLE entity_events (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    UNIQUE(entity_id, event_id)
);

CREATE INDEX idx_entity_events_entity ON entity_events(entity_id);
CREATE INDEX idx_entity_events_event ON entity_events(event_id);
```

**Event Model Extension:**

```python
# backend/app/models/event.py
class Event(Base):
    # ... existing fields ...

    # Denormalized for fast reads - array of entity IDs
    matched_entity_ids: Mapped[str | None] = mapped_column(Text)  # JSON array string

    # Relationship for eager loading
    matched_entities: Mapped[list["Entity"]] = relationship(
        "Entity",
        secondary="entity_events",
        back_populates="events",
        lazy="selectin"
    )

    def get_matched_entity_ids(self) -> list[str]:
        """Parse JSON array of entity IDs."""
        if not self.matched_entity_ids:
            return []
        return json.loads(self.matched_entity_ids)

    def set_matched_entity_ids(self, ids: list[str]):
        """Set JSON array of entity IDs."""
        self.matched_entity_ids = json.dumps(ids)
```

**API Response Schema:**

```python
# backend/app/schemas/event.py
class EntityBrief(BaseModel):
    id: str
    name: str
    type: str
    avatar_url: str | None

class EventResponse(BaseModel):
    id: str
    # ... existing fields ...
    matched_entity_ids: list[str]  # Array of entity IDs
    matched_entities: list[EntityBrief]  # Populated entity objects
```

### APIs and Interfaces

**Extended Event API:**

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| GET | `/api/v1/events/{id}` | Get event detail | - | `EventResponse` with `matched_entities[]` |
| PUT | `/api/v1/events/{id}/entities` | Assign entities | `{entity_ids: string[]}` | `EventResponse` |

**Entity Events Query:**

| Method | Endpoint | Description | Response |
|--------|----------|-------------|----------|
| GET | `/api/v1/entities/{id}/events` | Events for entity | `EventResponse[]` with `co_appearing_entities` |

### Workflows and Sequencing

**Multi-Entity Assignment Flow:**

```
User clicks "Assign Entity" on event card
       │
       ▼
┌─────────────────────────────┐
│  EntityAssignmentModal      │
│  - Shows entity list        │
│  - Checkboxes (multi-select)│
│  - Pre-selected: existing   │
└─────────────────────────────┘
       │
User selects multiple entities
       │
       ▼
┌─────────────────────────────┐
│  PUT /events/{id}/entities  │
│  { entity_ids: [...] }      │
└─────────────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  Backend:                   │
│  1. Clear EntityEvent rows  │
│  2. Insert new rows         │
│  3. Update JSON field       │
│  4. Return updated event    │
└─────────────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  UI Updates:                │
│  - Event card shows badges  │
│  - Entity modals refresh    │
└─────────────────────────────┘
```

**Alert Rule Evaluation Flow:**

```
New event created with matched_entity_ids
       │
       ▼
┌─────────────────────────────┐
│  Load all alert rules       │
│  with entity_id filter      │
└─────────────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  For each entity in event:  │
│  - Check if any rule matches│
│  - Track which entity hit   │
└─────────────────────────────┘
       │
Any match found?
       │
       ├──► No: Skip notification
       │
       └──► Yes: Send notification with triggering entity info
            │
            ▼
       ┌─────────────────────────────┐
       │  Webhook/push includes:     │
       │  - All matched entities     │
       │  - Triggering entity marked │
       └─────────────────────────────┘
```

## Non-Functional Requirements

### Performance

| Metric | Target | Notes |
|--------|--------|-------|
| Entity assignment | < 500ms | Batch insert/delete |
| Event query with entities | < 100ms | selectin loading |
| Alert evaluation | < 50ms | Per event, all rules |

### Security

- Entity assignment requires Operator or Admin role
- Entity IDs validated before insert
- No cross-user entity access (if multi-tenant future)

### Reliability/Availability

- Junction table with CASCADE delete
- JSON field kept in sync via transaction
- Handles empty entity list gracefully

### Observability

- Log: Entity assignment changes (old → new IDs)
- Log: Alert triggers with triggering entity
- Metric: Average entities per event

## Dependencies and Integrations

| Dependency | Version | Purpose | Status |
|------------|---------|---------|--------|
| SQLAlchemy | ^2.0 | ORM relationships | Existing |
| React Query | ^5.x | Cache invalidation | Existing |
| Combobox (radix) | ^1.x | Multi-select UI | Existing |

No new dependencies required.

## Acceptance Criteria (Authoritative)

1. **AC1:** Events can have 0 to N entities assigned via `matched_entity_ids` array
2. **AC2:** Event API returns `matched_entities` array with populated entity objects
3. **AC3:** Event cards display avatar/badge for all matched entities (max 3 visible)
4. **AC4:** "+N more" indicator shown when event has > 3 matched entities
5. **AC5:** Tooltip on hover shows all entity names
6. **AC6:** Entity detail modal shows all events where entity appears, including multi-entity
7. **AC7:** Multi-entity events show "with [other names]" indicator in entity detail
8. **AC8:** Entity assignment modal supports checkbox multi-select
9. **AC9:** Assignment modal has search/filter for entity list
10. **AC10:** Alert rules with entity filter trigger when any matched entity matches
11. **AC11:** Alert notification includes information about which entity triggered
12. **AC12:** Backward compatible: single-entity events continue to work

## Traceability Mapping

| AC | FR | Spec Section | Component | Test Idea |
|----|-----|--------------|-----------|-----------|
| AC1 | FR33 | Data Model | Event model | Create event with multiple entities |
| AC2 | FR33 | API | events.py | GET event, verify matched_entities array |
| AC3 | FR34 | Event Display | EventCard | Render card with 2 entities, verify badges |
| AC4 | FR34 | Event Display | EventCard | Render 5 entities, verify "+2" indicator |
| AC5 | FR34 | Event Display | EventCard | Hover, verify tooltip with all names |
| AC6 | FR35 | Entity Detail | EntityDetailModal | Entity in multi-event, verify event appears |
| AC7 | FR35 | Entity Detail | EntityDetailModal | Verify "with X" text |
| AC8 | FR36 | Assignment UI | EntityAssignmentModal | Select multiple, verify request |
| AC9 | FR36 | Assignment UI | EntityAssignmentModal | Search, verify filtered list |
| AC10 | FR37 | Alert Engine | alert_engine.py | Rule on entity A, event with A+B, verify trigger |
| AC11 | FR37 | Alert Engine | alert_engine.py | Check webhook payload has triggering entity |
| AC12 | FR33 | Backward Compat | Event model | Single entity still works |

## Risks, Assumptions, Open Questions

**Risks:**
- **Risk:** Existing code assumes single entity
  - *Mitigation:* Thorough audit of entity_id usage, migrate to matched_entity_ids

- **Risk:** Performance with many entities per event
  - *Mitigation:* Limit to 10 entities per event (reasonable real-world max)

**Assumptions:**
- Assumption: EntityEvent junction table exists and is properly indexed
- Assumption: Event cards have space for entity badges (current design supports it)
- Assumption: AI entity matching continues to work (single entity per match, UI allows adding more)

**Open Questions:**
- Q: Should AI automatically detect multiple entities?
  - *Recommendation:* Future phase - requires prompt engineering and testing

- Q: Maximum entities per event?
  - *Recommendation:* Soft limit of 10, UI shows "+N more" for overflow

## Test Strategy Summary

**Unit Tests:**
- Event model: get/set matched_entity_ids JSON handling
- EventService: multi-entity assignment transaction
- AlertEngine: multi-entity rule matching

**Integration Tests:**
- PUT /events/{id}/entities with various entity counts
- GET /entities/{id}/events returns multi-entity events
- Alert trigger with multi-entity event

**E2E Tests (Playwright):**
- Assign multiple entities via modal
- View event card with multiple badges
- Entity detail shows co-appearing entity names

**Manual Testing:**
- Visual inspection of badge overflow
- Tooltip hover behavior
- Mobile touch for badge interaction
