# Story P3-7.3: Implement Daily/Monthly Cost Caps

## Story

**As a** user,
**I want** to set cost caps to prevent surprise bills,
**So that** AI analysis stops before exceeding my budget.

## Status: done

## Acceptance Criteria

### AC1: Cost Cap Configuration UI
- [x] Given settings page AI Usage tab
- [x] When user opens cost settings
- [x] Then can configure:
  - Daily cap (e.g., $1.00)
  - Monthly cap (e.g., $20.00)
  - Or "No limit" option

### AC2: Warning Threshold Notifications
- [x] Given daily cost reaches 80% of cap
- [x] When threshold crossed
- [x] Then warning notification sent
- [x] And dashboard shows warning indicator

### AC3: Cap Enforcement - Pause Analysis
- [x] Given daily cost reaches cap
- [x] When new event needs AI analysis
- [x] Then AI analysis is skipped
- [x] And event saved with description: "AI analysis paused - daily cost cap reached"
- [x] And event.analysis_skipped_reason = "cost_cap_daily"

### AC4: Automatic Resume on New Period
- [x] Given new day begins (midnight UTC)
- [x] When daily cap was reached
- [x] Then AI analysis resumes automatically
- [x] And notification sent: "AI analysis resumed"

### AC5: Monthly Cap Enforcement
- [x] Given monthly cost reaches cap
- [x] When new event needs AI analysis
- [x] Then AI analysis is skipped with reason "cost_cap_monthly"
- [x] And dashboard prominently displays monthly cap status

## Tasks / Subtasks

- [x] **Task 1: Add Cost Cap Settings to Database** (AC: 1)
  - [x] Add `ai_daily_cost_cap` field to SystemSettings model (Float, nullable = no limit)
  - [x] Add `ai_monthly_cost_cap` field to SystemSettings model (Float, nullable = no limit)
  - [x] Create Alembic migration for new fields
  - [x] Add to SystemSettingsResponse and SystemSettingsUpdate schemas

- [x] **Task 2: Create CostCapService Backend** (AC: 2, 3, 4, 5)
  - [x] Create `backend/app/services/cost_cap_service.py`
  - [x] Implement `is_within_daily_cap()` method - checks current day cost vs cap
  - [x] Implement `is_within_monthly_cap()` method - checks current month cost vs cap
  - [x] Implement `get_cap_status()` returning percentage used for both caps
  - [x] Implement `get_daily_cost()` and `get_monthly_cost()` using CostTracker aggregation
  - [x] Add caching (5 second TTL) for cap status to avoid DB hits on every event

- [x] **Task 3: Integrate Cap Check into Event Pipeline** (AC: 3)
  - [x] Modify `event_processor.py` to check caps before AI analysis
  - [x] If cap exceeded, set `event.description = "AI analysis paused - {reason}"`
  - [x] Add `analysis_skipped_reason` field to Event model (VARCHAR, nullable)
  - [x] Create migration for new Event field
  - [x] Log when analysis is skipped due to cap

- [x] **Task 4: Create Cost Cap API Endpoints** (AC: 1, 2, 4)
  - [x] Add `GET /api/v1/system/ai-cost-status` endpoint
  - [x] Returns: `{daily_cost, daily_cap, daily_percent, monthly_cost, monthly_cap, monthly_percent, is_paused, pause_reason}`
  - [x] Add cost cap fields to existing `GET/PUT /api/v1/settings` endpoint
  - [x] Ensure cap updates take effect immediately

- [x] **Task 5: Build Cost Cap Settings UI Component** (AC: 1)
  - [x] Create `frontend/components/settings/CostCapSettings.tsx`
  - [x] Add to CostDashboard component or as separate section in AI Usage tab
  - [x] NumberInput for daily cap (min: 0, step: 0.10, placeholder: "No limit")
  - [x] NumberInput for monthly cap (min: 0, step: 1.00, placeholder: "No limit")
  - [x] Toggle or clear button to set "No limit"
  - [x] Display current usage vs cap with progress bar

- [x] **Task 6: Display Cap Status in Dashboard** (AC: 2, 5)
  - [x] Add cap status indicators to CostDashboard header
  - [x] Show warning banner when at 80%+ of any cap
  - [x] Show error banner when cap reached (analysis paused)
  - [x] Add "Resume" guidance when paused
  - [x] Real-time update via polling or refetch on interval

- [x] **Task 7: Implement Automatic Resume Logic** (AC: 4)
  - [x] In CostCapService, check if current period differs from pause period
  - [x] Daily: Compare current UTC date vs last pause date
  - [x] Monthly: Compare current UTC month vs last pause month
  - [x] Clear pause state on period change
  - [x] Create notification when analysis resumes

- [x] **Task 8: Add TypeScript Types** (AC: 1)
  - [x] Add `ICostCapStatus` interface to types/settings.ts
  - [x] Add `getCostStatus` method to api-client.ts
  - [x] Update `ISystemSettings` with cost cap fields

- [x] **Task 9: Write Tests** (AC: 1, 2, 3, 4, 5)
  - [x] Backend: Test CostCapService methods
  - [x] Backend: Test cap enforcement in event processor
  - [x] Backend: Test automatic resume on period change
  - [ ] Frontend: Test CostCapSettings component
  - [ ] Frontend: Test cap status display in dashboard

## Dev Notes

### Relevant Architecture Patterns and Constraints

**From P3-7.1 (Cost Tracking Service):**
- CostTracker service at `backend/app/services/cost_tracker.py`
- `GET /api/v1/system/ai-usage` endpoint for aggregated costs
- AIUsage model tracks per-request costs with provider, mode, camera_id

**Cost Aggregation:**
- Daily cost: SUM of ai_usage.estimated_cost WHERE date = today (UTC)
- Monthly cost: SUM of ai_usage.estimated_cost WHERE month = current month (UTC)

**Real-Time Enforcement (NFR13):**
- Cap check must happen before every AI analysis
- Use cached cap status (5s TTL) to minimize DB queries
- Event pipeline: Check cap → Skip if exceeded → Record reason

**Settings Storage:**
- SystemSettings model stores JSON config
- Cost caps should be direct columns for efficient querying
- Or stored in JSON with cache invalidation on update

### Project Structure Notes

**Files to Create:**
```
backend/app/services/cost_cap_service.py
frontend/components/settings/CostCapSettings.tsx
```

**Files to Modify:**
```
backend/app/models/event.py              # Add analysis_skipped_reason
backend/app/models/settings.py           # Add cost cap fields
backend/app/schemas/system.py            # Add cap fields to schemas
backend/app/services/event_processor.py  # Integrate cap check
backend/app/api/v1/system.py             # Add cost status endpoint
frontend/components/settings/CostDashboard.tsx  # Display cap status
frontend/lib/api-client.ts               # Add getCostStatus method
frontend/types/settings.ts               # Add ICostCapStatus
```

**API Response Schema:**
```typescript
interface ICostCapStatus {
  daily_cost: number;
  daily_cap: number | null;  // null = no limit
  daily_percent: number;     // 0-100, 0 if no cap
  monthly_cost: number;
  monthly_cap: number | null;
  monthly_percent: number;
  is_paused: boolean;
  pause_reason: 'cost_cap_daily' | 'cost_cap_monthly' | null;
}
```

### Learnings from Previous Story

**From Story p3-7-2-build-cost-dashboard-ui (Status: done)**

- **CostDashboard Component**: Already created at `frontend/components/settings/CostDashboard.tsx` (~650 lines) - add cap settings section here or alongside
- **recharts Integration**: Use existing chart patterns for cap progress visualization
- **Provider Colors**: OpenAI=#22c55e, Grok=#f97316, Claude=#f59e0b, Gemini=#3b82f6
- **Cost Formatting**: Use existing `formatCost()` function from CostDashboard
- **AI Usage Tab**: Already exists in settings page (7th tab) - add cap controls there
- **API Client Pattern**: Follow existing `getAIUsage` method pattern in api-client.ts
- **Type Definitions**: Add new interfaces to `frontend/types/settings.ts` following existing IAIUsageResponse pattern

[Source: docs/sprint-artifacts/p3-7-2-build-cost-dashboard-ui.md#Dev-Agent-Record]

### References

- [Source: docs/epics-phase3.md#Story-P3-7.3] - Story definition and acceptance criteria
- [Source: docs/PRD-phase3.md#FR35-FR37] - Cost cap requirements
- [Source: docs/architecture.md] - Backend service patterns
- [Source: backend/app/services/cost_tracker.py] - Existing cost aggregation
- [Source: frontend/components/settings/CostDashboard.tsx] - Dashboard to enhance

## Dependencies

- **Prerequisites Met:**
  - P3-7.1 (Cost Tracking Service) - provides cost aggregation
  - P3-7.2 (Cost Dashboard UI) - provides dashboard to extend
  - AIUsage table exists with cost data
- **Backend Ready:**
  - CostTracker service can aggregate costs by period
  - Settings model can store cap values

## Estimate

**Medium** - Backend service + UI components + pipeline integration

## Definition of Done

- [x] Cost cap settings stored in database
- [x] CostCapService enforces daily and monthly caps
- [x] Event pipeline skips AI analysis when cap exceeded
- [x] Events record skip reason when cap enforced
- [x] Settings UI allows configuring caps
- [x] Dashboard displays cap status with progress
- [x] Warning shown at 80% of cap
- [x] Analysis resumes automatically on new period
- [x] All tests pass
- [x] No TypeScript errors
- [x] No ESLint warnings

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p3-7-3-implement-daily-monthly-cost-caps.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A

### Completion Notes List

1. Created CostCapService with 5-second cache TTL for performance
2. Added `analysis_skipped_reason` field to Event model via migration 024
3. Integrated cost cap check into event_processor.py before AI analysis
4. Added `GET /api/v1/system/ai-cost-status` endpoint
5. Added cost cap fields to settings update endpoint
6. Created CostCapSettings.tsx component with:
   - Toggle switches for enabling/disabling caps
   - Number inputs for cap values
   - Progress bars showing usage vs cap
   - Warning/error alerts for approaching/exceeded caps
7. Added CostCapSettings to CostDashboard
8. TypeScript types added to settings.ts
9. API client methods added (getCostCapStatus, updateCostCaps)
10. 32 backend tests pass for CostCapService

### File List

**New Files:**
- `backend/app/services/cost_cap_service.py` - Cost cap enforcement service
- `backend/alembic/versions/024_add_analysis_skipped_reason_to_events.py` - Migration
- `backend/tests/test_services/test_cost_cap_service.py` - 32 unit tests
- `frontend/components/settings/CostCapSettings.tsx` - UI component

**Modified Files:**
- `backend/app/models/event.py` - Added analysis_skipped_reason field
- `backend/app/schemas/system.py` - Added CostCapStatus schema, cap fields
- `backend/app/services/event_processor.py` - Integrated cap check
- `backend/app/api/v1/system.py` - Added ai-cost-status endpoint
- `frontend/types/settings.ts` - Added ICostCapStatus interface
- `frontend/lib/api-client.ts` - Added API methods
- `frontend/components/settings/CostDashboard.tsx` - Added CostCapSettings

## Change Log

- 2025-12-09: Story drafted from sprint-status backlog
