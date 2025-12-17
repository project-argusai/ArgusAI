# Story P6-1.4: Add Camera Data Caching with React Query

Status: done

## Story

As a system administrator,
I want the camera list to use stale-while-revalidate caching,
so that navigation between pages is snappy and reduces unnecessary API calls.

## Acceptance Criteria

1. TanStack Query (React Query) configured for camera endpoints
2. Stale time set appropriately (e.g., 30 seconds)
3. Background refetch on window focus
4. Reduced API calls during navigation

## Tasks / Subtasks

- [x] Task 1: Create useCamerasQuery hook using TanStack Query (AC: #1)
  - [x] Create new hooks/useCamerasQuery.ts file using useQuery pattern
  - [x] Define query key for cameras list: ['cameras', filters]
  - [x] Implement query function wrapping apiClient.cameras.list()
  - [x] Set stale time to 30 seconds per AC#2
- [x] Task 2: Enable window focus refetch (AC: #3)
  - [x] Set refetchOnWindowFocus: true in the hook options
  - [x] Test that data refreshes when user returns to tab
- [x] Task 3: Add mutation hooks for camera operations (AC: #4)
  - [x] Create useCameraCreate mutation hook
  - [x] Create useCameraUpdate mutation hook
  - [x] Create useCameraDelete mutation hook
  - [x] Invalidate cameras query on successful mutations
- [x] Task 4: Update cameras page to use new hook (AC: #1, #4)
  - [x] Import useCamerasQuery in cameras/page.tsx
  - [x] Replace useCameras hook with useCamerasQuery
  - [x] Update refresh function to use query invalidation
  - [x] Verify filtering still works with new hook
- [x] Task 5: Update other components using useCameras (AC: #4)
  - [x] Search for useCameras usage across codebase
  - [x] Update CameraSelector component if needed
  - [x] Update CameraGrid component if needed
  - [x] Ensure backward compatibility or deprecate old hook
- [x] Task 6: Write tests for new hook (AC: #1, #2, #3)
  - [x] Test query fetches data on mount
  - [x] Test stale time behavior
  - [x] Test cache invalidation on mutations
  - [x] Test refetch on window focus

## Dev Notes

- TanStack Query is already installed and configured with QueryProvider
- Default global options in query-provider.tsx set staleTime: 60s, refetchOnWindowFocus: false
- Story-specific config can override global defaults with hook options
- Follow patterns from useEntities.ts for query/mutation structure
- Current useCameras hook uses useState/useEffect pattern - will be replaced

### Project Structure Notes

- New hook: `frontend/hooks/useCamerasQuery.ts`
- Tests: `frontend/__tests__/hooks/useCamerasQuery.test.ts`
- Pattern follows existing `frontend/hooks/useEntities.ts`

### Learnings from Previous Story

**From Story p6-1-3-implement-virtual-scrolling-for-camera-list (Status: done)**

- **New Component Created**: `VirtualCameraList` at `frontend/components/cameras/VirtualCameraList.tsx` - uses @tanstack/react-virtual
- **Integration Point**: Cameras page at `frontend/app/cameras/page.tsx` uses VirtualCameraList for 12+ cameras
- **TanStack Ecosystem**: Both @tanstack/react-virtual and @tanstack/react-query already in use - follow consistent patterns
- **CameraPreview Memoized**: P6-1.2 added React.memo to CameraPreview - caching will complement this optimization

[Source: docs/sprint-artifacts/p6-1-3-implement-virtual-scrolling-for-camera-list.md#Dev-Agent-Record]

### References

- [Source: docs/epics-phase6.md#Story P6-1.4]
- [Source: frontend/hooks/useCameras.ts] - Current implementation to replace
- [Source: frontend/hooks/useEntities.ts] - TanStack Query pattern to follow
- [Source: frontend/components/providers/query-provider.tsx] - Global query config
- [Source: frontend/app/cameras/page.tsx] - Primary consumer of cameras hook

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p6-1-4-add-camera-data-caching-with-react-query.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Initial implementation plan: Create useCamerasQuery hook following useEntities pattern
- Components to update: cameras/page.tsx, CameraSelector, CameraGrid, DashboardStats
- Verified CameraSelector already used TanStack Query inline - converted to use new hook
- Created standardized cameraKeys factory for consistent query keys across components

### Completion Notes List

- Created `useCamerasQuery` hook with full TanStack Query integration
- Implemented `cameraKeys` factory for standardized query key management
- Added `useCameraQuery` for single camera fetching
- Added mutation hooks: `useCameraCreate`, `useCameraUpdate`, `useCameraDelete`
- All mutations properly invalidate camera list cache on success
- Updated cameras page to use new hooks (replaced useCameras)
- Updated CameraSelector to use useCamerasQuery (was inline useQuery)
- Updated CameraGrid to use useCamerasQuery (was inline useQuery)
- Updated DashboardStats to use standardized cameraKeys
- All 16 tests pass covering queries, mutations, and cache invalidation
- Build passes without errors

### File List

- frontend/hooks/useCamerasQuery.ts (NEW) - TanStack Query hooks for cameras
- frontend/__tests__/hooks/useCamerasQuery.test.ts (NEW) - 16 tests for hook functionality
- frontend/app/cameras/page.tsx (MODIFIED) - Updated to use useCamerasQuery and useCameraDelete
- frontend/components/cameras/CameraGrid.tsx (MODIFIED) - Updated to use useCamerasQuery
- frontend/components/rules/CameraSelector.tsx (MODIFIED) - Updated to use useCamerasQuery
- frontend/components/dashboard/DashboardStats.tsx (MODIFIED) - Updated to use cameraKeys
