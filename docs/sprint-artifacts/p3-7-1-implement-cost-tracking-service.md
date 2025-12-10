# Story P3-7.1: Implement Cost Tracking Service

## Story

**As a** system administrator,
**I want** AI usage costs to be tracked accurately,
**So that** I can monitor spending and make informed decisions about camera configurations.

## Status: done

## Acceptance Criteria

### AC1: Calculate and Store Cost Per AI Request
- [x] Given an AI request completes with token usage
- [x] When usage is recorded
- [x] Then CostTracker calculates estimated cost using provider-specific rates
- [x] And stores cost in ai_usage table with the request record
- [x] And cost is stored in USD with 6 decimal places for precision

### AC2: Support Provider-Specific Cost Rates
- [x] Given cost rates by provider are configured
- [x] When cost calculation occurs
- [x] Then uses appropriate rates:
  - OpenAI: $0.00015/1K input tokens, $0.0006/1K output tokens
  - Grok: $0.0001/1K input tokens, $0.0003/1K output tokens
  - Claude: $0.00025/1K input tokens, $0.00125/1K output tokens
  - Gemini: Free tier (configurable rate)
- [x] And rates are configurable via settings/environment

### AC3: Aggregate Usage by Multiple Dimensions
- [x] Given daily usage aggregation is queried
- [x] When `GET /api/v1/system/ai-usage` endpoint is called
- [x] Then returns total cost aggregated by:
  - Date (daily totals)
  - Camera (per-camera breakdown) - Note: Empty until Event-AIUsage link is added
  - Provider (OpenAI/Grok/Claude/Gemini)
  - Analysis mode (single_frame/multi_frame/video_native)
- [x] And supports date range filtering (default: last 30 days)

### AC4: Track Image/Token Costs for Multi-Image Requests
- [x] Given a multi-image AI request (multi_frame or video_native mode)
- [x] When cost is calculated
- [x] Then accounts for additional image tokens:
  - ~85 tokens per image (low-res) for OpenAI
  - ~765 tokens per image (high-res) for OpenAI
  - ~1,334 tokens per image for Claude
- [x] And total cost reflects actual usage for multi-image requests

### AC5: Handle Missing Token Information
- [x] Given provider doesn't return token counts (some Gemini responses)
- [x] When usage is tracked
- [x] Then estimate tokens based on image count and response length
- [x] And flag estimate with `is_estimated: true`
- [x] And use conservative estimates to avoid underreporting

### AC6: Store Cost Metadata with Events
- [x] Given an event is processed with AI analysis
- [x] When event is saved
- [x] Then includes `ai_cost` field in event record
- [x] And cost can be queried with event details

## Tasks / Subtasks

- [x] **Task 1: Create CostTracker Service** (AC: 1, 2)
  - [x] Create `backend/app/services/cost_tracker.py`
  - [x] Define `PROVIDER_COST_RATES` configuration constant
  - [x] Implement `calculate_cost(provider, input_tokens, output_tokens)` method
  - [x] Implement `calculate_multi_image_cost(provider, image_count, resolution)` method
  - [x] Add configurable rate overrides via environment/settings
  - [x] Write unit tests for cost calculation (26 tests)

- [x] **Task 2: Extend AIUsage Model** (AC: 1, 4, 5)
  - [x] Verified `cost_estimate` field already exists (Float)
  - [x] Verified `is_estimated` field already exists (Boolean)
  - [x] Verified `analysis_mode` field already exists
  - [x] Add `image_count` field for multi-image tracking
  - [x] Create Alembic migration (022_add_image_count_to_ai_usage.py)
  - [x] Add index on (timestamp, provider) for aggregation queries

- [x] **Task 3: Integrate Cost Tracking into AIService** (AC: 1, 4, 5)
  - [x] Import CostTracker in AIService
  - [x] Modify `_track_usage` to accept `image_count` parameter
  - [x] Update all call sites (single_image, multi_frame, video_native)
  - [x] Store image_count with AIUsage record

- [x] **Task 4: Create AI Usage API Endpoint** (AC: 3)
  - [x] Add `GET /api/v1/system/ai-usage` endpoint to system.py
  - [x] Accept query params: `start_date`, `end_date`
  - [x] Return aggregated usage data with totals and breakdowns
  - [x] Create AIUsageResponse schema with aggregation structure
  - [x] Add endpoint tests (5 tests)

- [x] **Task 5: Add Cost to Event Model** (AC: 6)
  - [x] Add `ai_cost` field to Event model (Float, nullable)
  - [x] Update EventProcessor to store cost from AIResult.cost_estimate
  - [x] Update ProtectEventHandler to store cost
  - [x] Update EventResponse schema to include ai_cost
  - [x] Create migration (023_add_ai_cost_to_events.py)
  - [x] Update frontend IEvent type

- [x] **Task 6: Write Integration Tests** (AC: 1, 3, 4)
  - [x] Test cost calculation accuracy for each provider (26 tests)
  - [x] Test multi-image cost calculation
  - [x] Test aggregation queries by date/provider/mode
  - [x] Test estimated cost flagging
  - [x] Test API endpoint returns correct data structure (5 tests)

## Dev Notes

### Relevant Architecture Patterns and Constraints

**Cost Calculation Formula:**
```python
def calculate_cost(provider: str, input_tokens: int, output_tokens: int) -> Decimal:
    rates = PROVIDER_COST_RATES[provider]
    input_cost = (input_tokens / 1000) * rates['input']
    output_cost = (output_tokens / 1000) * rates['output']
    return Decimal(str(input_cost + output_cost)).quantize(Decimal('0.000001'))
```

**Provider Cost Rates (as of Dec 2025):**
| Provider | Input (per 1K) | Output (per 1K) | Notes |
|----------|---------------|-----------------|-------|
| OpenAI (GPT-4o mini) | $0.00015 | $0.0006 | Primary provider |
| xAI Grok | $0.0001 | $0.0003 | Secondary |
| Claude Haiku | $0.00025 | $0.00125 | Tertiary |
| Gemini Flash | $0.00 | $0.00 | Free tier default |

**Image Token Estimates:**
- OpenAI low-res: ~85 tokens per image
- OpenAI high-res: ~765 tokens per image
- Claude: ~1,334 tokens per image
- Gemini: Variable (use conservative estimate)

**API Response Structure:**
```typescript
interface AIUsageResponse {
  total_cost: number;
  total_requests: number;
  period: { start: string; end: string };
  by_date: Array<{ date: string; cost: number; requests: number }>;
  by_camera: Array<{ camera_id: string; camera_name: string; cost: number }>;
  by_provider: Array<{ provider: string; cost: number; requests: number }>;
  by_mode: Array<{ mode: string; cost: number; requests: number }>;
}
```

### Project Structure Notes

**Files Created:**
```
backend/app/services/cost_tracker.py
backend/alembic/versions/022_add_image_count_to_ai_usage.py
backend/alembic/versions/023_add_ai_cost_to_events.py
backend/tests/test_services/test_cost_tracker.py
```

**Files Modified:**
```
backend/app/models/ai_usage.py    # Added image_count field
backend/app/models/event.py       # Added ai_cost field
backend/app/schemas/event.py      # Added ai_cost to EventResponse
backend/app/schemas/system.py     # Added AIUsageResponse schema
backend/app/services/ai_service.py # Integrated CostTracker, added image_count tracking
backend/app/services/event_processor.py # Store ai_cost in events
backend/app/services/protect_event_handler.py # Store ai_cost in events
backend/app/api/v1/system.py      # Added /ai-usage endpoint
backend/tests/test_api/test_system.py # Added AI usage endpoint tests
frontend/types/event.ts           # Added ai_cost to IEvent
```

**Existing Models Leveraged:**
- `AIUsage` model exists in `backend/app/models/ai_usage.py`
- Already tracks: provider, tokens_used, cost_estimate, analysis_mode, is_estimated

### References

- [Source: docs/epics-phase3.md#Story-P3-7.1] - Story definition and acceptance criteria
- [Source: docs/PRD-phase3.md#FR32-FR33] - Cost tracking requirements
- [Source: docs/architecture.md] - Service layer patterns
- [Source: backend/app/models/ai_usage.py] - Existing AIUsage model

## Learnings from Previous Story

**From Story p3-6-4-add-re-analyze-action-for-low-confidence-events (Status: done)**

- **Backend endpoint pattern**: POST endpoint at `/api/v1/events/{id}/reanalyze` - follow similar pattern for GET aggregation endpoint
- **Alembic migration naming**: Use sequential numbering (021 was last, so 022 for this story)
- **Model field additions**: Added `reanalyzed_at`, `reanalysis_count` to Event - similar pattern for `ai_cost`
- **TanStack Query pattern**: Used mutation for API calls - aggregation endpoint will use query
- **Test coverage**: Both frontend and backend tests written - ensure cost calculation unit tests

**From Epic P3-2 (Multi-Frame Analysis):**
- `analysis_mode` field may already exist on AIUsage - verify before adding
- Token tracking already partially implemented - extend rather than duplicate

[Source: docs/sprint-artifacts/p3-6-4-add-re-analyze-action-for-low-confidence-events.md#Dev-Agent-Record]

## Dependencies

- **Prerequisites Met:**
  - P3-2.5 (Token usage tracking) - provides foundation for cost extension
  - AIUsage model exists with basic token tracking
  - AIService with multi-provider support
- **Backend Existing:**
  - AIUsage model in `backend/app/models/ai_usage.py`
  - AIService in `backend/app/services/ai_service.py`
  - System routes in `backend/app/api/v1/system.py`

## Estimate

**Medium** - New service + model extensions + API endpoint, builds on existing token tracking

## Definition of Done

- [x] `CostTracker` service created with provider-specific cost calculation
- [x] AIUsage model extended with `image_count` field (cost_estimate, is_estimated already existed)
- [x] Event model has `ai_cost` field (migration applied)
- [x] `GET /api/v1/system/ai-usage` endpoint returns aggregated usage data
- [x] Cost calculation integrated into AIService for all providers
- [x] Multi-image cost calculation accounts for image token overhead
- [x] Missing token info handled with estimates and flagging
- [x] All unit and integration tests pass (31 tests total)
- [x] No TypeScript errors in frontend types
- [x] No new lint errors

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p3-7-1-implement-cost-tracking-service.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A

### Completion Notes List

1. Created CostTracker service with PROVIDER_COST_RATES and TOKENS_PER_IMAGE constants
2. Implemented calculate_cost(), calculate_multi_image_cost(), and estimate_tokens() methods
3. Added environment variable overrides for cost rates (AI_COST_RATE_{PROVIDER}_{TYPE})
4. Created migration 022 for image_count field on AIUsage
5. Created migration 023 for ai_cost field on Event
6. Integrated cost tracking into AIService._track_usage() with image_count parameter
7. Updated EventProcessor and ProtectEventHandler to store ai_cost from AIResult
8. Created GET /api/v1/system/ai-usage endpoint with date range filtering
9. Created AIUsageResponse schema with aggregation breakdown structures
10. Updated frontend IEvent type with ai_cost field
11. Wrote 26 unit tests for CostTracker and 5 integration tests for API endpoint

### File List

- backend/app/services/cost_tracker.py (created)
- backend/tests/test_services/test_cost_tracker.py (created)
- backend/alembic/versions/022_add_image_count_to_ai_usage.py (created)
- backend/alembic/versions/023_add_ai_cost_to_events.py (created)
- backend/app/models/ai_usage.py (modified)
- backend/app/models/event.py (modified)
- backend/app/schemas/event.py (modified)
- backend/app/schemas/system.py (modified)
- backend/app/services/ai_service.py (modified)
- backend/app/services/event_processor.py (modified)
- backend/app/services/protect_event_handler.py (modified)
- backend/app/api/v1/system.py (modified)
- backend/tests/test_api/test_system.py (modified)
- frontend/types/event.ts (modified)

## Change Log

- 2025-12-09: Story drafted from sprint-status backlog
- 2025-12-09: Story implemented - all tasks completed, 31 tests passing
