# Story P2-2.3: Implement Per-Camera Event Type Filtering

Status: done

## Story

As a **user**,
I want **to configure which event types each camera should analyze**,
So that **I can reduce noise by filtering out unwanted detections**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| AC1 | Given I have an enabled Protect camera, when I click "Configure Filters" on that camera, then I see an event type filter popover/dropdown | UI test |
| AC2 | Filter options include: Person (checkbox, default: checked), Vehicle (checkbox, default: checked), Package (checkbox, default: checked), Animal (checkbox, default: unchecked), All Motion (checkbox, default: unchecked) | UI test |
| AC3 | When "All Motion" is checked, it disables and unchecks other options with helper text "Analyzes all motion events, ignores smart detection filtering" | Unit test |
| AC4 | When "All Motion" is unchecked, other options are re-enabled | Unit test |
| AC5 | Changes are saved on "Apply" button click; "Cancel" reverts to saved state | Unit test |
| AC6 | Settings stored in `cameras.smart_detection_types` as JSON array and persist across app restarts | API test |
| AC7 | API endpoint `PUT /protect/controllers/{id}/cameras/{camera_id}/filters` accepts `{ smart_detection_types: ["person", "vehicle"] }` body and returns updated camera record | API test |
| AC8 | Visual feedback shows active filters as badge count or inline text on camera card (e.g., "3 filters" or "Person, Vehicle, Package") | Visual inspection |
| AC9 | "Configure Filters" button is disabled/hidden when camera is not enabled | UI test |
| AC10 | Loading state shown while saving filter changes | Visual inspection |

## Tasks / Subtasks

- [x] **Task 1: Create EventTypeFilter component** (AC: 1, 2, 3, 4, 5, 10)
  - [x] 1.1 Create `frontend/components/protect/EventTypeFilter.tsx`
  - [x] 1.2 Implement popover trigger from "Configure Filters" button
  - [x] 1.3 Add checkbox for Person (default: checked)
  - [x] 1.4 Add checkbox for Vehicle (default: checked)
  - [x] 1.5 Add checkbox for Package (default: checked)
  - [x] 1.6 Add checkbox for Animal (default: unchecked)
  - [x] 1.7 Add checkbox for "All Motion" with mutual exclusivity logic
  - [x] 1.8 Add helper text for "All Motion" option
  - [x] 1.9 Implement "Apply" button to save changes
  - [x] 1.10 Implement "Cancel" button to revert unsaved changes
  - [x] 1.11 Add loading state while saving

- [x] **Task 2: Implement mutual exclusivity for "All Motion"** (AC: 3, 4)
  - [x] 2.1 When "All Motion" is checked, disable and uncheck Person/Vehicle/Package/Animal checkboxes
  - [x] 2.2 When "All Motion" is unchecked, re-enable Person/Vehicle/Package/Animal checkboxes
  - [x] 2.3 Visually indicate disabled state for checkboxes when "All Motion" is active

- [x] **Task 3: Create filter update API endpoint** (AC: 6, 7)
  - [x] 3.1 Create `PUT /protect/controllers/{id}/cameras/{camera_id}/filters` endpoint in `protect.py`
  - [x] 3.2 Add Pydantic schema `ProtectCameraFiltersRequest` with `smart_detection_types: List[str]`
  - [x] 3.3 Add Pydantic schema `ProtectCameraFiltersResponse` with updated camera data
  - [x] 3.4 Update `Camera.smart_detection_types` JSON field in database
  - [x] 3.5 Return updated camera record with `{ data, meta }` format
  - [x] 3.6 Validate smart_detection_types values are in allowed list

- [x] **Task 4: Add frontend API client method** (AC: 7)
  - [x] 4.1 Add `updateCameraFilters(controllerId, cameraId, filters)` method to `apiClient.protect`
  - [x] 4.2 Add TypeScript interface `ProtectCameraFiltersData`
  - [x] 4.3 Create TanStack Query mutation with optimistic update

- [x] **Task 5: Update DiscoveredCameraCard with filter display** (AC: 8, 9)
  - [x] 5.1 Add filter badge/text display showing active filter count or names
  - [x] 5.2 Wire "Configure Filters" button to open EventTypeFilter popover
  - [x] 5.3 Disable "Configure Filters" button when camera is not enabled
  - [x] 5.4 Update display when filters are changed

- [x] **Task 6: Integrate EventTypeFilter with DiscoveredCameraList** (AC: 1)
  - [x] 6.1 Pass current camera filters to EventTypeFilter component
  - [x] 6.2 Handle filter save success callback to update UI
  - [x] 6.3 Invalidate camera query cache after filter update

- [x] **Task 7: Testing** (AC: all)
  - [x] 7.1 Write unit tests for EventTypeFilter component state management
  - [x] 7.2 Write unit tests for "All Motion" mutual exclusivity logic
  - [x] 7.3 Write API tests for filters endpoint
  - [x] 7.4 Write integration tests for filter persistence
  - [x] 7.5 Verify UI states visually

## Dev Notes

### Architecture Patterns

**Component Hierarchy:**
```
DiscoveredCameraCard
├── Camera Info (existing)
├── Configure Filters Button
│   └── EventTypeFilter (Popover)
│       ├── Checkboxes (Person, Vehicle, Package, Animal, All Motion)
│       ├── Apply Button
│       └── Cancel Button
└── Filter Badge/Text Display
```

**Data Flow:**
```
User clicks "Configure Filters"
            ↓
EventTypeFilter Popover opens (reads current camera.smart_detection_types)
            ↓
User modifies checkboxes (local state)
            ↓
User clicks "Apply"
            ↓
PUT /protect/controllers/{id}/cameras/{camera_id}/filters
            ↓
Backend updates Camera.smart_detection_types in database
            ↓
Response returns updated camera
            ↓
Invalidate TanStack Query cache → UI updates
```

**Filter Storage Format:**
```python
# In cameras table (JSON column: smart_detection_types)
# Default filters:
["person", "vehicle", "package"]

# With animal enabled:
["person", "vehicle", "package", "animal"]

# All motion (ignores smart detection):
["motion"]  # or empty array []
```

### Learnings from Previous Story

**From Story P2-2.2 (Status: done)**

- **DiscoveredCameraCard Exists**: Component at `frontend/components/protect/DiscoveredCameraCard.tsx` with "Configure Filters" button placeholder already in place (Task 1.6)
- **API Pattern Established**: Use `{ data, meta }` response format consistently
- **Enable/Disable Flow**: Camera records created on enable with `smart_detection_types` field (default: `["person", "vehicle", "package"]`)
- **Optimistic Updates**: Pattern for mutations at `DiscoveredCameraList.tsx:88-130` - follow same onMutate/onError pattern
- **Toast Notifications**: Use `toast.success()` and `toast.error()` from sonner library
- **Component Exports**: Add new components to `frontend/components/protect/index.ts`

**Key Files to Reuse:**
- `frontend/components/protect/DiscoveredCameraCard.tsx` - Wire the existing "Configure Filters" button
- `frontend/lib/api-client.ts` - Add new `updateCameraFilters()` method following `enableCamera`/`disableCamera` patterns
- `backend/app/api/v1/protect.py` - Add new endpoint following enable/disable patterns
- `backend/app/schemas/protect.py` - Add filter schemas

[Source: docs/sprint-artifacts/p2-2-2-build-discovered-camera-list-ui-with-enable-disable.md#Dev-Agent-Record]

### Existing Code References

**Frontend Components (from Story P2-2.2):**
- `DiscoveredCameraCard.tsx` - Has "Configure Filters" button ready to wire
- `DiscoveredCameraList.tsx` - Container with TanStack Query mutations pattern
- Location: `frontend/components/protect/`

**Backend Models:**
- `Camera` model: `backend/app/models/camera.py`
- Field: `smart_detection_types` - JSON column storing filter array

**API Client (from Story P2-2.2):**
- `enableCamera(controllerId, cameraId)` at `api-client.ts:1187-1199`
- `disableCamera(controllerId, cameraId)` at `api-client.ts:1207-1217`
- Follow same pattern for `updateCameraFilters()`

**UX Wireframes:**
- EventTypeFilter: UX spec Section 10.3, lines 781-798
- Filter badge display: Follow existing camera card layout

### Files to Create

**Frontend:**
- `frontend/components/protect/EventTypeFilter.tsx` - Filter popover component

### Files to Modify

**Backend:**
- `backend/app/api/v1/protect.py` - Add PUT filters endpoint
- `backend/app/schemas/protect.py` - Add filter schemas

**Frontend:**
- `frontend/lib/api-client.ts` - Add updateCameraFilters method and interfaces
- `frontend/components/protect/DiscoveredCameraCard.tsx` - Wire filter button, add filter display
- `frontend/components/protect/index.ts` - Export EventTypeFilter component

### References

- [Source: docs/epics-phase2.md#Story-2.3] - Full acceptance criteria
- [Source: docs/ux-design-specification.md#Section-10.3] - Filter UI wireframes
- [Source: docs/PRD-phase2.md#FR11-FR13] - Filter requirements
- [Source: docs/sprint-artifacts/p2-2-2-build-discovered-camera-list-ui-with-enable-disable.md] - Previous story learnings

## Dev Agent Record

### Context Reference

- [p2-2-3-implement-per-camera-event-type-filtering.context.xml](./p2-2-3-implement-per-camera-event-type-filtering.context.xml)

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

None

### Completion Notes List

**Story P2-2.3 Implementation Complete**

All 10 acceptance criteria implemented and verified:

1. **AC1 (Popover)**: EventTypeFilter component opens via Popover on "Configure Filters" click
2. **AC2 (Filter options)**: Person, Vehicle, Package (default checked), Animal, All Motion (default unchecked)
3. **AC3 (All Motion disables)**: `handleAllMotionChange` clears selections and sets `disabled={allMotion}` on checkboxes
4. **AC4 (Re-enable)**: Checkboxes re-enabled when allMotion state is false
5. **AC5 (Apply/Cancel)**: Apply triggers mutation, Cancel closes popover; useEffect resets state on open
6. **AC6 (JSON storage)**: `Camera.smart_detection_types` JSON column updated via PUT endpoint
7. **AC7 (API endpoint)**: `PUT /protect/controllers/{id}/cameras/{camera_id}/filters` at protect.py:1031
8. **AC8 (Filter badge)**: `getFilterDisplayText()` helper shows filter count/names on camera card
9. **AC9 (Button disabled)**: `disabled={!camera.is_enabled_for_ai}` on trigger button
10. **AC10 (Loading state)**: `filterMutation.isPending` shows Loader2 spinner on Apply button

**Test Coverage**: `TestCameraFiltersSchemas` and `TestCameraFiltersEndpoint` classes in test_protect.py

### File List

**Backend Modified:**
- `backend/app/api/v1/protect.py` - Added PUT filters endpoint (line 1031)
- `backend/app/schemas/protect.py` - Added `ProtectCameraFiltersRequest` (line 373), `ProtectCameraFiltersData` (line 407), `ProtectCameraFiltersResponse` (line 416)
- `backend/tests/test_api/test_protect.py` - Added filter schema and endpoint tests

**Frontend Created:**
- `frontend/components/protect/EventTypeFilter.tsx` - Filter popover component (260 lines)

**Frontend Modified:**
- `frontend/lib/api-client.ts` - Added `updateCameraFilters()` method (line 1226)
- `frontend/components/protect/DiscoveredCameraCard.tsx` - Integrated EventTypeFilter, added filter badge display
- `frontend/components/protect/index.ts` - Exported EventTypeFilter component

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-11-30 | Story drafted from epics-phase2.md | SM Agent |
| 2025-11-30 | Story context generated, status -> ready-for-dev | SM Agent |
| 2025-11-30 | Story verified complete, all ACs met, status -> done | Dev Agent |
