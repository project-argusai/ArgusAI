# Story P4-3.6: Entity Management UI

Status: done

## Story

As a **home security user**,
I want **a user interface to view, name, delete, and merge recognized entities (recurring people and vehicles)**,
so that **I can manage who is known to my system, assign meaningful names like "Mail Carrier" or "Neighbor Bob", and maintain accurate visitor tracking**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| 1 | Entity list page displays all recognized entities sorted by last_seen_at descending | UI test navigating to entities page, verify order |
| 2 | Entity list shows: thumbnail preview, name (or "Unknown"), entity_type, occurrence_count, first_seen_at, last_seen_at | UI component test, verify all fields render |
| 3 | Entity list supports filtering by entity_type (person, vehicle, unknown) | UI test with filter dropdown, verify filtered results |
| 4 | Entity list supports filtering by named_only (show only entities with names) | UI test with toggle, verify filter works |
| 5 | Entity list supports pagination (50 per page default, configurable) | UI test with large dataset, verify pagination controls work |
| 6 | Clicking an entity opens detail view showing entity info and recent events | UI test clicking entity card, verify detail modal/page opens |
| 7 | Entity detail view shows occurrence history with thumbnails and timestamps | UI test, verify event list renders correctly |
| 8 | User can assign/update entity name via inline edit or modal | UI test, verify PUT /api/v1/context/entities/{id} called |
| 9 | User can delete an entity with confirmation dialog | UI test, verify DELETE /api/v1/context/entities/{id} called |
| 10 | Delete confirmation shows warning about unlinking events (events kept, only entity link removed) | UI test, verify warning text appears |
| 11 | API error handling with user-friendly error messages (entity not found, network errors) | Test error scenarios, verify toast notifications |
| 12 | Loading states displayed during API calls (skeleton loaders, spinners) | UI test, verify loading indicators appear |
| 13 | Empty state displayed when no entities exist with helpful guidance | UI test with empty DB, verify empty state renders |
| 14 | Entity cards show thumbnail from most recent associated event | UI test, verify thumbnail displays |
| 15 | Responsive design works on mobile (stacked layout) and desktop (grid layout) | Visual test on different viewport sizes |

## Tasks / Subtasks

- [ ] **Task 1: Create entity types and API client methods** (AC: 8, 9, 11)
  - [ ] Add TypeScript types for Entity, EntityDetail, EntityListResponse to `frontend/types/entity.ts`
  - [ ] Add API client methods in `frontend/lib/api-client.ts`:
    - `getEntities(params: { limit, offset, entity_type?, named_only? })`
    - `getEntity(entityId: string)`
    - `updateEntity(entityId: string, data: { name: string })`
    - `deleteEntity(entityId: string)`
  - [ ] Add proper error handling returning typed error responses

- [ ] **Task 2: Create EntityCard component** (AC: 2, 14)
  - [ ] Create `frontend/components/entities/EntityCard.tsx`
  - [ ] Display thumbnail (from most recent event or placeholder)
  - [ ] Show name with fallback to "Unknown [entity_type]" styling
  - [ ] Display entity_type badge (person/vehicle/unknown)
  - [ ] Show occurrence_count, first_seen_at, last_seen_at with relative dates
  - [ ] Add hover state and click handler

- [ ] **Task 3: Create EntityList component with filtering** (AC: 1, 3, 4, 5)
  - [ ] Create `frontend/components/entities/EntityList.tsx`
  - [ ] Implement TanStack Query hook for fetching entities
  - [ ] Add entity_type filter dropdown (All, Person, Vehicle, Unknown)
  - [ ] Add named_only toggle switch
  - [ ] Implement pagination with page controls
  - [ ] Sort by last_seen_at descending (server-side)

- [ ] **Task 4: Create EntityDetail modal/panel** (AC: 6, 7, 14)
  - [ ] Create `frontend/components/entities/EntityDetail.tsx`
  - [ ] Display entity metadata (name, type, counts, timestamps)
  - [ ] Show list of recent events with thumbnails (from GET /entities/{id})
  - [ ] Each event links to event detail page
  - [ ] Add close button/backdrop click to dismiss

- [ ] **Task 5: Implement entity name editing** (AC: 8, 11)
  - [ ] Create `frontend/components/entities/EntityNameEdit.tsx`
  - [ ] Add inline edit mode (click name to edit) OR edit button
  - [ ] Show text input with save/cancel buttons
  - [ ] Call PUT /api/v1/context/entities/{id} on save
  - [ ] Handle errors with toast notification
  - [ ] Optimistic update with rollback on error

- [ ] **Task 6: Implement entity deletion** (AC: 9, 10, 11)
  - [ ] Create `frontend/components/entities/DeleteEntityDialog.tsx`
  - [ ] Show confirmation dialog with entity name/thumbnail
  - [ ] Display warning: "This will unlink this entity from all associated events. Events themselves will not be deleted."
  - [ ] Call DELETE /api/v1/context/entities/{id} on confirm
  - [ ] Handle errors with toast notification
  - [ ] Remove entity from list on success

- [ ] **Task 7: Create Entities page** (AC: 1, 13, 15)
  - [ ] Create `frontend/app/entities/page.tsx`
  - [ ] Import and use EntityList component
  - [ ] Add page header with title "Recognized Entities"
  - [ ] Handle empty state with illustration and guidance text
  - [ ] Add responsive layout (grid on desktop, stack on mobile)

- [ ] **Task 8: Implement loading and empty states** (AC: 12, 13)
  - [ ] Add skeleton loader to EntityCard
  - [ ] Add skeleton loader to EntityList
  - [ ] Create EmptyEntitiesState component with:
    - Illustration or icon
    - "No recognized entities yet" message
    - Guidance: "Entities are automatically created when the same person or vehicle is seen multiple times."

- [ ] **Task 9: Add navigation link** (AC: 1)
  - [ ] Add "Entities" link to sidebar/nav in `frontend/components/layout/`
  - [ ] Use appropriate icon (Users or similar)
  - [ ] Highlight when on /entities route

- [ ] **Task 10: Write component tests** (AC: 1-15)
  - [ ] Test EntityCard renders all fields correctly
  - [ ] Test EntityList filtering by type
  - [ ] Test EntityList filtering by named_only
  - [ ] Test EntityList pagination
  - [ ] Test EntityDetail displays events
  - [ ] Test EntityNameEdit save/cancel flow
  - [ ] Test DeleteEntityDialog confirmation flow
  - [ ] Test loading states render correctly
  - [ ] Test empty state renders correctly
  - [ ] Test error handling shows toast

- [ ] **Task 11: Write integration tests** (AC: 8, 9, 11)
  - [ ] Test entities page loads and displays entities
  - [ ] Test entity name update persists
  - [ ] Test entity deletion removes from list
  - [ ] Test error scenarios (404, network error)

## Dev Notes

### Architecture Alignment

This story is the final component of the Temporal Context Engine (Epic P4-3). It provides the user-facing management UI for the RecognizedEntity model and EntityService created in P4-3.3. The backend APIs are already fully implemented in `backend/app/api/v1/context.py`.

**Backend API Endpoints (Already Implemented):**
```
GET    /api/v1/context/entities              - List entities with pagination/filters
GET    /api/v1/context/entities/{id}         - Get entity detail with recent events
PUT    /api/v1/context/entities/{id}         - Update entity name
DELETE /api/v1/context/entities/{id}         - Delete entity
```

**Component Integration Flow:**
```
/entities page
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ EntityList                                                   │
│   - Filters: entity_type, named_only                        │
│   - Pagination: limit, offset                               │
│   - Uses TanStack Query for data fetching                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ (for each entity)
┌─────────────────────────────────────────────────────────────┐
│ EntityCard                                                   │
│   - Thumbnail from most recent event                        │
│   - Name/type/counts display                                │
│   - Click → opens EntityDetail                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ (on click)
┌─────────────────────────────────────────────────────────────┐
│ EntityDetail (modal or panel)                                │
│   - Full entity info                                        │
│   - Recent events list                                      │
│   - EntityNameEdit (inline)                                 │
│   - Delete button → DeleteEntityDialog                      │
└─────────────────────────────────────────────────────────────┘
```

### Key Implementation Patterns

**API Client Pattern (follow existing patterns):**
```typescript
// frontend/lib/api-client.ts additions
export async function getEntities(params: {
  limit?: number;
  offset?: number;
  entity_type?: 'person' | 'vehicle' | 'unknown';
  named_only?: boolean;
}): Promise<EntityListResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));
  if (params.entity_type) searchParams.set('entity_type', params.entity_type);
  if (params.named_only) searchParams.set('named_only', 'true');

  const response = await fetch(`${API_URL}/api/v1/context/entities?${searchParams}`);
  if (!response.ok) throw new ApiError(response.status, await response.text());
  return response.json();
}
```

**TanStack Query Pattern (follow existing hooks):**
```typescript
// frontend/hooks/useEntities.ts
export function useEntities(params: EntityQueryParams) {
  return useQuery({
    queryKey: ['entities', params],
    queryFn: () => getEntities(params),
  });
}

export function useUpdateEntity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      updateEntity(id, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entities'] });
    },
  });
}
```

**Component Styling (use existing shadcn/ui):**
- Card component for EntityCard
- Dialog component for EntityDetail modal
- AlertDialog for DeleteEntityDialog
- Input + Button for EntityNameEdit
- Select for entity_type filter
- Switch for named_only toggle
- Skeleton for loading states
- Pagination component if exists, or build with Button

### Project Structure Notes

**Files to create:**
- `frontend/types/entity.ts` - TypeScript types
- `frontend/hooks/useEntities.ts` - TanStack Query hooks
- `frontend/components/entities/EntityCard.tsx`
- `frontend/components/entities/EntityList.tsx`
- `frontend/components/entities/EntityDetail.tsx`
- `frontend/components/entities/EntityNameEdit.tsx`
- `frontend/components/entities/DeleteEntityDialog.tsx`
- `frontend/components/entities/EmptyEntitiesState.tsx`
- `frontend/app/entities/page.tsx`

**Files to modify:**
- `frontend/lib/api-client.ts` - Add entity API methods
- `frontend/components/layout/Sidebar.tsx` or Header.tsx - Add Entities nav link

### Performance Considerations

- Use TanStack Query for caching and background refetching
- Implement pagination to avoid loading all entities at once
- Use optimistic updates for name changes (instant feedback)
- Consider virtualized list for very large entity counts (future)
- Thumbnail URLs come from event.thumbnail_url, not stored on entity

### Testing Strategy

Per testing patterns in codebase:
- Component tests using Vitest + React Testing Library
- Integration tests for full page flows
- Mock API responses using MSW or manual mocks
- Test loading, error, and empty states

### Learnings from Previous Story

**From Story P4-3.5 (Pattern Detection) (Status: done)**

- **Backend APIs Complete**: All entity endpoints are working in `backend/app/api/v1/context.py`:
  - `GET /entities` - List with pagination, entity_type filter, named_only filter
  - `GET /entities/{id}` - Detail with recent_events included
  - `PUT /entities/{id}` - Update name
  - `DELETE /entities/{id}` - Delete with 204 response
- **EntityService Available**: `backend/app/services/entity_service.py` handles all entity operations
- **Model Pattern**: RecognizedEntity and EntityEvent junction table in `backend/app/models/recognized_entity.py`
- **API Response Schemas**: EntityResponse, EntityDetailResponse, EntityListResponse already defined in context.py
- **Context Service Integration**: EntityService used by ContextEnhancedPromptService for AI prompts

**From Story P4-3.3 (Recurring Visitor Detection) (Status: done)**

- **Entity Matching Flow**: Events matched to entities during processing via EntityService.match_or_create_entity()
- **Similarity Threshold**: Default 0.75 for entity matching
- **Entity Cache**: EntityService maintains in-memory cache of embeddings for fast matching

**Reusable Patterns from Existing Frontend Code:**
- Camera list page pattern: `frontend/app/cameras/page.tsx` - grid layout, empty state
- Event card pattern: `frontend/components/events/EventCard.tsx` - thumbnail, metadata display
- Settings page pattern: `frontend/app/settings/page.tsx` - tabs, forms
- Dialog pattern: `frontend/components/protect/ConnectionErrorBanner.tsx` - modal dialogs

[Source: docs/sprint-artifacts/p4-3-5-pattern-detection.md#Dev-Notes]
[Source: docs/sprint-artifacts/p4-3-3-recurring-visitor-detection.md (from epic history)]

### References

- [Source: docs/epics-phase4.md#Story-P4-3.6-Entity-Management-UI]
- [Source: docs/PRD-phase4.md#FR5 - System maintains a "familiar faces/vehicles" registry]
- [Source: docs/PRD-phase4.md#API-Additions - GET/PUT/DELETE /api/v1/entities endpoints]
- [Source: docs/architecture.md#Phase-4-API-Contracts - Entity API specifications]
- [Source: backend/app/api/v1/context.py - Implemented entity endpoints lines 472-660]
- [Source: backend/app/services/entity_service.py - EntityService implementation]
- [Source: backend/app/models/recognized_entity.py - RecognizedEntity and EntityEvent models]

## Dev Agent Record

### Context Reference

- [docs/sprint-artifacts/p4-3-6-entity-management-ui.context.xml](./p4-3-6-entity-management-ui.context.xml)

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-11 | Claude Opus 4.5 | Initial story draft from create-story workflow |
