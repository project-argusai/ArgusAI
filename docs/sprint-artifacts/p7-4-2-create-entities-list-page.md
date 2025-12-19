# Story P7-4.2: Create Entities List Page

Status: done

## Story

As a **home user managing recognized people and vehicles**,
I want **search functionality and an "Add Alert" button on the entities page**,
so that **I can find specific entities by name and prepare for future entity-based alerting**.

## Story Key
p7-4-2-create-entities-list-page

## Acceptance Criteria

| AC# | Criteria | Verification |
|-----|----------|--------------|
| AC1 | Search by name supported with debounced input | Integration: Type in search, verify filtered results appear after 300ms |
| AC2 | Search shows "No results" message when no matches | E2E: Search for non-existent name, verify message displayed |
| AC3 | Placeholder "Add Alert" button present on entity cards | E2E: Verify button exists on each entity card |
| AC4 | "Add Alert" button shows "Coming Soon" toast when clicked | E2E: Click button, verify toast message appears |
| AC5 | Search query persisted in URL | Integration: Search, refresh page, verify search preserved |
| AC6 | Search combined with type filter works correctly | Integration: Search + filter, verify both applied |

## Tasks / Subtasks

### Task 1: Add Search Functionality (AC: 1, 2, 5, 6)
- [x] 1.1 Add search input to EntityList component
- [x] 1.2 Implement debounced search (300ms delay)
- [x] 1.3 Update useEntities hook to accept search parameter
- [x] 1.4 Update API client if needed to pass search param
- [x] 1.5 Show "No results for '{query}'" in empty state
- [x] 1.6 Combine search with existing type filter
- [x] 1.7 Persist search in URL query params

### Task 2: Add "Add Alert" Button to Entity Cards (AC: 3, 4)
- [x] 2.1 Add "Add Alert" button to EntityCard component
- [x] 2.2 Import toast from sonner
- [x] 2.3 Show "Coming Soon" toast when button clicked
- [x] 2.4 Style button appropriately (subtle, non-primary)

### Task 3: Update Frontend Tests
- [x] 3.1 Update EntityCard test to verify "Add Alert" button exists
- [x] 3.2 Test "Add Alert" button click shows toast
- [x] 3.3 Add test for search functionality if applicable

## Dev Notes

### Architecture Constraints

From tech spec (docs/sprint-artifacts/tech-spec-epic-P7-4.md):
- This story is UI-only - backend already implemented in P7-4.1
- Entity recognition NOT implemented - manual creation only
- "Add Alert" button is non-functional (shows "Coming Soon")
- Entities span all cameras (same person at different cameras)

### Key Implementation Details

**API Endpoints (already exist from P7-4.1):**
- `GET /api/v1/context/entities` - List entities with `entity_type` and `search` query params
- `GET /api/v1/context/entities/{id}` - Get single entity detail
- `PUT /api/v1/context/entities/{id}` - Update entity (name, notes, is_vip, is_blocked)
- `DELETE /api/v1/context/entities/{id}` - Delete entity and cascade sightings
- `GET /api/v1/context/entities/{id}/thumbnail` - Get entity thumbnail image

**Entity Response Schema:**
```typescript
interface EntityResponse {
  id: string;  // UUID
  entity_type: 'person' | 'vehicle';
  name: string | null;
  thumbnail_url: string | null;
  first_seen_at: string;
  last_seen_at: string;
  occurrence_count: number;
  is_vip: boolean;
  is_blocked: boolean;
  notes: string | null;
}

interface EntityListResponse {
  items: EntityResponse[];
  total: number;
  page: number;
  page_size: number;
}
```

**UI Components to Create:**
- `EntitiesPage` - Main page with grid, search, filters
- `EntityCard` - Card component for each entity
- `EntityEmptyState` - Empty state when no entities
- `EntitySearchBar` - Search input with debounce
- `EntityTypeFilter` - Type filter dropdown/tabs

### Existing Patterns to Follow

- **Page Layout**: Follow `frontend/app/events/page.tsx` for page structure with search/filter
- **Card Component**: Follow `frontend/components/events/EventCard.tsx` for card styling
- **Hooks**: Follow `frontend/hooks/useEvents.ts` for TanStack Query patterns
- **Types**: Follow `frontend/types/event.ts` for type definitions
- **API Client**: Follow patterns in `frontend/lib/api-client.ts`

### Project Structure Notes

**Files to Create:**
- `frontend/app/entities/page.tsx` - Entities page
- `frontend/components/entities/EntityCard.tsx` - Entity card component
- `frontend/components/entities/EntityEmptyState.tsx` - Empty state
- `frontend/components/entities/EntitySearchBar.tsx` - Search component
- `frontend/components/entities/EntityTypeFilter.tsx` - Filter component
- `frontend/hooks/useEntities.ts` - Entity hooks
- `frontend/types/entity.ts` - Entity types
- `frontend/__tests__/components/entities/EntityCard.test.tsx` - Tests

**Files to Modify:**
- `frontend/lib/api-client.ts` - Add entity API functions
- `frontend/components/layout/Sidebar.tsx` (or equivalent) - Add Entities nav link

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P7-4.md#Story-P7-4.2]
- [Source: docs/sprint-artifacts/tech-spec-epic-P7-4.md#APIs-and-Interfaces]
- [Source: docs/epics-phase7.md#Story-P7-4.2]

### Learnings from Previous Story

**From Story p7-4-1-design-entities-data-model (Status: done)**

- **Key Discovery**: Entity model uses existing `RecognizedEntity` from Phase 4, NOT a new Entity model
- **API Path**: Entities API is at `/api/v1/context/entities`, NOT `/api/v1/entities`
- **Model Fields**: Uses `entity_type` (not just `type`), includes `is_vip`, `is_blocked` flags
- **Sightings**: `EntityEvent` table serves as sightings junction (entity_id, event_id, similarity_score)
- **New Columns Added**: `thumbnail_path` and `notes` columns via migration `bdbfb90b1d66`
- **Thumbnail Endpoint**: `GET /api/v1/context/entities/{id}/thumbnail` for serving entity images
- **Test Results**: All 13 entity API tests pass

[Source: docs/sprint-artifacts/p7-4-1-design-entities-data-model.md#Dev-Agent-Record]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p7-4-2-create-entities-list-page.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- **Discovery**: Entities page already existed from Story P4-3.6 with full grid, filtering by type, pagination, delete, and inline name editing
- **Implementation Scope**: Added search functionality (AC1, AC2, AC5, AC6) and "Add Alert" button (AC3, AC4)
- **Backend Changes**:
  - Added `search` parameter to `get_all_entities()` in entity_service.py
  - Added `search` query param to `/api/v1/context/entities` endpoint
- **Frontend Changes**:
  - Added search input with 300ms debounce to EntityList component
  - URL persistence for search and type filter using useSearchParams
  - Updated EmptyEntitiesState to show search-specific "No results" message
  - Added "Add Alert" button to EntityCard with "Coming Soon" toast
- **Tests Added**: 2 new EntityCard tests for Add Alert button (AC3, AC4)
- **All 12 EntityCard tests pass, all 10 context API tests pass, frontend builds successfully**

### File List

**Backend Modified:**
- `backend/app/services/entity_service.py` - Added search parameter to get_all_entities()
- `backend/app/api/v1/context.py` - Added search query param to list_entities endpoint

**Frontend Modified:**
- `frontend/lib/api-client.ts` - Added search param to entities.list()
- `frontend/hooks/useEntities.ts` - Added search to UseEntitiesParams interface
- `frontend/components/entities/EntityList.tsx` - Added search input with debounce and URL persistence
- `frontend/components/entities/EntityCard.tsx` - Added "Add Alert" button with Coming Soon toast
- `frontend/components/entities/EmptyEntitiesState.tsx` - Added search-specific empty message

**Tests Modified:**
- `frontend/__tests__/components/entities/EntityCard.test.tsx` - Added 2 tests for Add Alert button

## Change Log
| Date | Change |
|------|--------|
| 2025-12-19 | Story drafted from epic P7-4 and tech spec |
| 2025-12-19 | Implementation complete - search and Add Alert button added |
