# Story P3-7.2: Build Cost Dashboard UI

## Story

**As a** user,
**I want** a dashboard showing AI usage and costs,
**So that** I can monitor spending patterns.

## Status: done

## Acceptance Criteria

### AC1: Dashboard Tab with Key Metrics
- [x] Given settings page
- [x] When user navigates to "AI Usage" tab
- [x] Then sees dashboard with:
  - Today's cost (prominent display)
  - This month's cost
  - Total requests count
  - Period date range displayed

### AC2: Cost Breakdown Charts
- [x] Given cost data available
- [x] When dashboard loads
- [x] Then displays:
  - Cost by camera (bar chart)
  - Cost by provider (pie chart)
  - Daily trend (line chart, last 30 days)

### AC3: Estimated Cost Indicator
- [x] Given cost data includes estimated values
- [x] When dashboard displays costs
- [x] Then shows indicator for estimated vs actual costs
- [x] And displays accuracy indicator per NFR12 (±20% accuracy)

### AC4: Empty State Handling
- [x] Given no usage data exists
- [x] When dashboard loads
- [x] Then shows "No AI usage recorded yet"
- [x] And explains how usage tracking works
- [x] And does not show empty charts

### AC5: Camera Drilldown
- [x] Given user clicks on camera in chart
- [x] When drilldown activates
- [x] Then shows detailed usage for that camera
- [x] And shows breakdown by analysis mode (single_frame/multi_frame/video_native)

## Tasks / Subtasks

- [x] **Task 1: Install Chart Library** (AC: 2)
  - [x] Add recharts to package.json dependencies
  - [x] Verify recharts compatible with React 19
  - [x] Run npm install

- [x] **Task 2: Create CostDashboard Component** (AC: 1, 3, 4)
  - [x] Create `frontend/components/settings/CostDashboard.tsx`
  - [x] Implement useQuery hook to fetch from `GET /api/v1/system/ai-usage`
  - [x] Add period selector (default: last 30 days)
  - [x] Display loading state with skeleton
  - [x] Display key metrics cards (today's cost, monthly cost, total requests)
  - [x] Add estimated vs actual indicator with tooltip
  - [x] Implement empty state with explanation text

- [x] **Task 3: Implement Cost by Provider Chart** (AC: 2)
  - [x] Create pie chart using recharts PieChart
  - [x] Map provider colors: OpenAI=green, Grok=orange, Claude=amber, Gemini=blue
  - [x] Add legend showing provider name and percentage
  - [x] Add tooltip showing exact cost and request count

- [x] **Task 4: Implement Cost by Camera Chart** (AC: 2, 5)
  - [x] Create bar chart using recharts BarChart
  - [x] Display camera_name on Y-axis, cost on X-axis
  - [x] Add click handler for drilldown
  - [x] Create drilldown modal/panel showing mode breakdown

- [x] **Task 5: Implement Daily Trend Chart** (AC: 2)
  - [x] Create line chart using recharts LineChart
  - [x] X-axis: dates (last 30 days)
  - [x] Y-axis: cost in USD
  - [x] Add area fill for visual clarity
  - [x] Add tooltip showing date and cost

- [x] **Task 6: Add AI Usage Tab to Settings Page** (AC: 1)
  - [x] Import CostDashboard component
  - [x] Add DollarSign icon to imports
  - [x] Add TabsTrigger for "AI Usage" tab
  - [x] Add TabsContent with CostDashboard
  - [x] Update grid-cols count for new tab

- [x] **Task 7: Create TypeScript Types** (AC: 1, 2)
  - [x] Add IAIUsageResponse interface to types/settings.ts
  - [x] Add IAIUsageByDate, IAIUsageByCamera, IAIUsageByProvider, IAIUsageByMode interfaces
  - [x] Add getAIUsage method to api-client.ts

- [x] **Task 8: Write Component Tests** (AC: 1, 2, 3, 4, 5)
  - [x] Test loading state renders skeleton
  - [x] Test empty state when no data
  - [x] Test charts render with mock data
  - [x] Test camera drilldown interaction
  - [x] Test estimated cost indicator display

## Dev Notes

### Relevant Architecture Patterns and Constraints

**API Endpoint (from P3-7.1):**
- `GET /api/v1/system/ai-usage` with query params: `start_date`, `end_date`
- Returns `AIUsageResponse` schema with aggregated data

**Response Schema (from backend/app/schemas/system.py):**
```typescript
interface AIUsageResponse {
  total_cost: number;      // USD with 6 decimal precision
  total_requests: number;
  period: { start: string; end: string };
  by_date: Array<{ date: string; cost: number; requests: number }>;
  by_camera: Array<{ camera_id: string; camera_name: string; cost: number; requests: number }>;
  by_provider: Array<{ provider: string; cost: number; requests: number }>;
  by_mode: Array<{ mode: string; cost: number; requests: number }>;
}
```

**Provider Color Scheme (consistent with existing UI):**
| Provider | Color | Tailwind Class |
|----------|-------|----------------|
| OpenAI | Green | `#22c55e` / `text-green-500` |
| Grok | Orange | `#f97316` / `text-orange-500` |
| Claude | Amber | `#f59e0b` / `text-amber-500` |
| Gemini | Blue | `#3b82f6` / `text-blue-500` |

**Chart Library Decision:**
- Use `recharts` - most popular React charting library
- Supports responsive containers
- Good TypeScript support
- Works with React 19

**UI Layout Pattern:**
- Follow existing settings page tab structure (see settings/page.tsx)
- Use Card component for metric cards
- Use shadcn/ui components for consistency
- Wrap with ErrorBoundary (per P2-6.3 pattern)

### Project Structure Notes

**Files to Create:**
```
frontend/components/settings/CostDashboard.tsx
```

**Files to Modify:**
```
frontend/app/settings/page.tsx       # Add new tab
frontend/lib/api-client.ts           # Add getAIUsage method
frontend/types/settings.ts           # Add AIUsage interfaces
frontend/package.json                # Add recharts dependency
```

**Alignment with unified project structure:**
- Component in `frontend/components/settings/` matches existing pattern
- TypeScript types in `frontend/types/` per project convention
- API client methods in `frontend/lib/api-client.ts`

### Learnings from Previous Story

**From Story p3-7-1-implement-cost-tracking-service (Status: done)**

- **New Service Created**: `CostTracker` service at `backend/app/services/cost_tracker.py` - backend is complete
- **API Endpoint Ready**: `GET /api/v1/system/ai-usage` endpoint implemented and tested (5 tests)
- **Schema Available**: `AIUsageResponse` schema in `backend/app/schemas/system.py` with full aggregation structure
- **Cost Calculation**: Costs stored in USD with 6 decimal places, use `is_estimated` flag for estimated costs
- **Provider Rates**: OpenAI $0.00015/1K input, Grok $0.0001/1K, Claude $0.00025/1K, Gemini free tier
- **Image Count Tracking**: `image_count` field added to AIUsage for multi-image cost tracking
- **Event Cost Field**: `ai_cost` field added to Event model and IEvent type
- **Frontend Type Updated**: IEvent already has `ai_cost` field in `frontend/types/event.ts`

**Key Implementation Notes:**
- Backend aggregation supports by_date, by_camera, by_provider, by_mode breakdowns
- by_camera may return empty until Event-AIUsage link is fully utilized
- Test with date range filtering: `?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

[Source: docs/sprint-artifacts/p3-7-1-implement-cost-tracking-service.md#Dev-Agent-Record]

### References

- [Source: docs/epics-phase3.md#Story-P3-7.2] - Story definition and acceptance criteria
- [Source: docs/PRD-phase3.md#FR34] - Display costs dashboard requirement
- [Source: docs/architecture.md] - Frontend patterns, shadcn/ui components
- [Source: backend/app/schemas/system.py#AIUsageResponse] - API response schema
- [Source: frontend/app/settings/page.tsx] - Existing settings page structure with tabs

## Dependencies

- **Prerequisites Met:**
  - P3-7.1 (Cost Tracking Service) - provides backend API endpoint
  - AIUsageResponse schema exists
  - Settings page with tab structure exists
- **Backend Ready:**
  - `GET /api/v1/system/ai-usage` endpoint operational
  - Returns aggregated usage data by date/camera/provider/mode

## Estimate

**Medium** - New frontend component with chart library, integrates with existing API

## Definition of Done

- [x] recharts library installed and working
- [x] CostDashboard component renders key metrics
- [x] Pie chart shows cost by provider with correct colors
- [x] Bar chart shows cost by camera with drilldown
- [x] Line chart shows daily trend for last 30 days
- [x] Empty state displays when no data
- [x] Estimated cost indicator shows for flagged costs
- [x] New "AI Usage" tab visible in settings page
- [x] All component tests pass (22/22)
- [x] No TypeScript errors
- [x] No ESLint warnings

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p3-7-2-build-cost-dashboard-ui.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A

### Completion Notes List

1. **recharts 3.x TypeScript Compatibility**: Created `ChartDataPoint` interface with index signature to satisfy recharts 3.x strict typing requirements. Data transformations handled via useMemo to avoid re-renders.

2. **Provider Colors**: Implemented consistent color scheme - OpenAI (#22c55e green), Grok (#f97316 orange), Claude (#f59e0b amber), Gemini (#3b82f6 blue).

3. **Cost Formatting**: Implemented `formatCost()` function with dynamic precision - 3 decimals for costs < $1, 2 decimals otherwise.

4. **Camera Drilldown**: Used shadcn Dialog component for drilldown modal showing cost breakdown by analysis mode (single_frame/multi_frame).

5. **Empty State**: Displays informational card with bullet points explaining how cost tracking works when no data exists.

6. **Testing**: 22 tests covering all acceptance criteria. Note: Radix Select interaction tests skipped due to jsdom `hasPointerCapture` limitation - verified API parameters passed correctly instead.

### File List

**Created:**
- `frontend/components/settings/CostDashboard.tsx` - Main dashboard component (~650 lines)
- `frontend/__tests__/components/settings/CostDashboard.test.tsx` - Component tests (22 tests)

**Modified:**
- `frontend/types/settings.ts` - Added IAIUsageResponse and related interfaces
- `frontend/lib/api-client.ts` - Added getAIUsage API method
- `frontend/app/settings/page.tsx` - Added AI Usage tab (7th tab)
- `frontend/package.json` - Added recharts dependency

## Change Log

- 2025-12-09: Story drafted from sprint-status backlog
- 2025-12-09: Story completed - all tasks done, 22 tests passing, build verified
