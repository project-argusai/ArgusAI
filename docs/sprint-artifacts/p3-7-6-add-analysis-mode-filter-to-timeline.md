# Story P3-7.6: Add Analysis Mode Filter to Timeline

## Story

**As a** user viewing the event timeline,
**I want** to filter events by analysis mode,
**So that** I can review events with specific analysis types and identify patterns.

## Status: done

## Acceptance Criteria

### AC1: Analysis Mode Filter in Timeline
- [x] Given event timeline view
- [x] When filter dropdown opened
- [x] Then includes "Analysis Mode" filter with options:
  - All modes
  - Single Frame only
  - Multi-Frame only
  - Video Native only

### AC2: Fallback Filter Option
- [x] Given filter options displayed
- [x] When user selects "With fallback"
- [x] Then only events with non-null fallback_reason shown
- [x] And these are events where analysis fell back to a simpler mode

### AC3: Low Confidence Filter Option
- [x] Given filter options displayed
- [x] When user selects "Low confidence"
- [x] Then only events with low_confidence=true shown
- [x] And allows reviewing uncertain descriptions

### AC4: Filter Application
- [x] Given "Multi-Frame only" filter selected
- [x] When applied
- [x] Then only events with analysis_mode='multi_frame' shown
- [x] And event count reflects filtered results

### AC5: Combined Filters
- [x] Given analysis mode filter combined with other filters (camera, date, object type)
- [x] When applied
- [x] Then all filters work together correctly
- [x] And results match all filter criteria

### AC6: Backend Query Support
- [x] Given API request with analysis_mode parameter
- [x] When `GET /api/v1/events?analysis_mode=multi_frame`
- [x] Then returns only events matching that mode
- [x] And supports `has_fallback=true` and `low_confidence=true` params

## Tasks / Subtasks

- [x] **Task 1: Add Analysis Mode Query Parameters to Events API** (AC: 6)
  - [x] Add `analysis_mode` query parameter to events list endpoint
  - [x] Add `has_fallback` boolean query parameter
  - [x] Add `low_confidence` boolean query parameter
  - [x] Update EventFilterParams schema with new filters
  - [x] Modify events query to filter by analysis_mode

- [x] **Task 2: Add Database Index for Analysis Mode** (AC: 6)
  - [x] Create migration to add index on analysis_mode column
  - [x] Add composite index on (analysis_mode, timestamp) for efficient queries
  - [x] Verify index improves query performance

- [x] **Task 3: Create AnalysisModeFilter React Component** (AC: 1, 2, 3)
  - [x] Added analysis mode filter section to EventFilters.tsx
  - [x] Implement checkbox-based selection with analysis mode options
  - [x] Add "With fallback" option
  - [x] Add "Low confidence" option
  - [x] Style consistently with existing timeline filters

- [x] **Task 4: Integrate Filter into Timeline** (AC: 1, 4, 5)
  - [x] Add AnalysisModeFilter to EventFilters component
  - [x] Connect filter state to API query parameters
  - [x] Ensure filter persists across page refreshes (URL params)
  - [x] Update event count display when filter applied

- [x] **Task 5: Write Backend Tests** (AC: 6)
  - [x] Test filtering by analysis_mode=single_frame
  - [x] Test filtering by analysis_mode=multi_frame
  - [x] Test filtering by analysis_mode=video_native
  - [x] Test has_fallback=true filter
  - [x] Test low_confidence=true filter
  - [x] Test combined filters work correctly

- [x] **Task 6: Write Frontend Tests** (AC: 1, 4, 5)
  - [x] Test AnalysisModeFilter renders all options
  - [x] Test filter selection updates query params
  - [x] Test combined filters apply correctly
  - [x] Test filter reset/clear functionality

## Dev Notes

### Relevant Architecture Patterns and Constraints

**From Existing Events API (backend/app/api/v1/events.py):**
- Events list endpoint already supports multiple query parameters
- EventFilterParams schema defines available filters
- Query uses SQLAlchemy ORM with optional filters

**From EventFilterParams Schema (backend/app/schemas/event.py):**
```python
class EventFilterParams(BaseModel):
    camera_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    min_confidence: Optional[int] = None
    object_types: Optional[List[str]] = None
    alert_triggered: Optional[bool] = None
    search_query: Optional[str] = None
    limit: int = 50
    offset: int = 0
    sort_order: Literal["asc", "desc"] = "desc"
```
Add: `analysis_mode`, `has_fallback`, `low_confidence`

**From Event Model:**
- `analysis_mode` field already exists (String, indexed)
- `fallback_reason` field exists (String, nullable)
- `low_confidence` field exists (Boolean, default False)

**From Frontend Timeline (frontend/app/events/page.tsx):**
- Uses TanStack Query for data fetching
- Filter state managed with URL params
- Existing filter components: camera selector, date range, object type

### Project Structure Notes

**Files to Create:**
```
frontend/components/events/AnalysisModeFilter.tsx
backend/alembic/versions/027_add_analysis_mode_index.py
frontend/__tests__/components/events/AnalysisModeFilter.test.tsx
```

**Files to Modify:**
```
backend/app/api/v1/events.py              # Add query params
backend/app/schemas/event.py              # Update EventFilterParams
frontend/app/events/page.tsx              # Integrate filter
frontend/lib/api-client.ts                # Update events query types
```

### Learnings from Previous Story

**From Story p3-7-5-display-key-frames-gallery-on-event-detail (Status: done)**

- **Migration Pattern**: Migration 026 added key frames fields - continue with 027 for index
- **Schema Pattern**: Added fields to EventResponse with JSON parsing validators
- **Component Pattern**: Created KeyFramesGallery with consistent shadcn/ui styling
- **Testing Pattern**: 12 backend tests for frame extractor, 23 frontend tests for gallery
- **Event Model Fields**: `key_frames_base64`, `frame_timestamps` added - analysis_mode already exists

[Source: docs/sprint-artifacts/p3-7-5-display-key-frames-gallery-on-event-detail.md]

### References

- [Source: docs/epics-phase3.md#Story-P3-7.6] - Story definition: Add Analysis Mode Filter to Timeline
- [Source: docs/epics-phase3.md#FR41] - Functional requirement: Timeline supports filtering by analysis mode
- [Source: backend/app/api/v1/events.py] - Events API endpoint with existing filters
- [Source: backend/app/schemas/event.py] - EventFilterParams schema
- [Source: frontend/app/events/page.tsx] - Events timeline page with filter bar

## Dependencies

- **Prerequisites Met:**
  - P3-3.4 (Analysis mode on event cards) - provides analysis_mode in events
  - P3-6.3 (Confidence indicator) - provides low_confidence flag
  - Existing events API with filter support

## Estimate

**Small** - Adding query parameters to existing API and filter component to existing UI

## Definition of Done

- [x] Analysis mode filter available in timeline filter bar
- [x] Single Frame, Multi-Frame, Video Native filter options work
- [x] "With fallback" filter shows events with fallback_reason
- [x] "Low confidence" filter shows uncertain events
- [x] Filters combine correctly with camera, date, object type filters
- [x] API supports analysis_mode, has_fallback, low_confidence params
- [x] Database index added for analysis_mode queries
- [x] All backend tests pass (9 tests)
- [x] All frontend tests pass (23 tests)
- [x] No TypeScript errors
- [x] No ESLint warnings from this story

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p3-7-6-add-analysis-mode-filter-to-timeline.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- Added analysis_mode, has_fallback, low_confidence query parameters to events API endpoint
- Created Alembic migration 027 with composite index on (analysis_mode, timestamp) and index on low_confidence
- Extended EventFilters.tsx with new Analysis Mode filter section using checkbox pattern
- Updated IEventFilters TypeScript interface with new filter fields
- Updated api-client.ts to pass new filters to backend
- Updated events/page.tsx with URL param parsing/serialization for new filters
- 9 backend tests covering all filter scenarios
- 23 frontend tests covering filter rendering, interactions, and accessibility

### File List

**Created:**
- backend/alembic/versions/027_add_analysis_mode_composite_index.py
- frontend/__tests__/components/events/AnalysisModeFilter.test.tsx

**Modified:**
- backend/app/api/v1/events.py (added query params and filtering logic)
- backend/app/schemas/event.py (added fields to EventFilterParams)
- backend/tests/test_api/test_events.py (added 9 new tests)
- frontend/types/event.ts (added fields to IEventFilters)
- frontend/lib/api-client.ts (added filter params to events.list)
- frontend/components/events/EventFilters.tsx (added Analysis Mode filter section)
- frontend/app/events/page.tsx (added URL param handling)

## Change Log

- 2025-12-10: Story drafted from sprint-status backlog (status: backlog → drafted)
- 2025-12-10: Story completed - all acceptance criteria met (status: ready-for-dev → done)
