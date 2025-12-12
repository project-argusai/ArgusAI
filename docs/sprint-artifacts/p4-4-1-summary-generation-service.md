# Story P4-4.1: Summary Generation Service

Status: done

## Story

As a **home security user**,
I want **an automated service that generates natural language summaries of activity for configurable time periods**,
so that **I can quickly understand "what happened" without scrolling through individual events, receiving digestible narrative summaries like "Quiet day - just the mail carrier at 2pm"**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| 1 | SummaryService exists at `backend/app/services/summary_service.py` with `generate_summary(start_time, end_time, camera_ids=None)` method | Unit test: verify service instantiation and method signature |
| 2 | Summary generation uses existing AI providers (OpenAI/Grok/Claude/Gemini) via AIService with fallback chain | Unit test: mock AIService, verify fallback behavior |
| 3 | Service queries events for time period using existing Event model and list_events pattern | Unit test: verify date range filtering works correctly |
| 4 | Events are grouped and categorized (by camera, by object type, by time of day) before LLM processing | Unit test: verify event aggregation logic produces correct categories |
| 5 | LLM prompt includes event count, categories, notable events, and time context | Unit test: verify prompt construction includes all required elements |
| 6 | Generated summaries are natural language narratives, not bullet lists | Integration test: verify actual LLM output format |
| 7 | Edge case: Zero events returns appropriate "No activity" summary without LLM call | Unit test: verify early return for empty event set |
| 8 | Edge case: Single event produces simple description referencing that event | Unit test: verify single-event handling |
| 9 | Edge case: Many events (50+) are intelligently sampled/summarized to avoid token limits | Unit test: verify event sampling/truncation logic |
| 10 | Summary includes statistical summary (total events, breakdown by type) | Unit test: verify stats are computed and included |
| 11 | Cost tracking: Summary generation cost tracked via CostTracker (ai_cost field pattern) | Unit test: verify cost tracking integration |
| 12 | Performance: Summary generation completes within 60 seconds for up to 200 events | Performance test: measure generation time |
| 13 | API endpoint `POST /api/v1/summaries/generate` accepts time_period params and returns summary | Integration test: call endpoint, verify response schema |
| 14 | API endpoint `GET /api/v1/summaries/daily?date=YYYY-MM-DD` returns summary for specific day | Integration test: call endpoint with date param |
| 15 | API returns 400 error for invalid date ranges (end before start, future dates > 1 day) | Unit test: verify validation errors |
| 16 | Response schema includes: summary_text, period_start, period_end, event_count, generated_at | Unit test: verify response matches schema |

## Tasks / Subtasks

- [x] **Task 1: Create SummaryService class** (AC: 1, 3, 4, 7, 8, 9)
  - [x] Create `backend/app/services/summary_service.py`
  - [x] Implement `generate_summary(start_time, end_time, camera_ids=None)` async method
  - [x] Query events using SQLAlchemy with date range filter (follow events.py pattern)
  - [x] Handle edge case: zero events (return "No activity detected" without LLM)
  - [x] Handle edge case: single event (return simple reference)
  - [x] Group events by camera, object_type, hour of day
  - [x] Implement event sampling for large datasets (keep first/last + sample middle)

- [x] **Task 2: Build LLM prompt for summary generation** (AC: 5, 6, 10)
  - [x] Create summary-specific system prompt (natural narrative style)
  - [x] Build user prompt with:
    - Time period context ("For [date] from [start] to [end]")
    - Event counts by category (persons: N, vehicles: M, packages: P)
    - Camera-by-camera breakdown
    - Notable events (doorbell rings, alerts triggered)
    - Pattern information if available (time clustering)
  - [x] Ensure prompt instructs narrative format, not bullet lists
  - [x] Include examples in prompt for consistent output style

- [x] **Task 3: Integrate with AIService for LLM calls** (AC: 2, 11)
  - [x] Import AIService and use existing generate_description method
  - [x] Adapt AIService or create text-only method (no image required)
  - [x] Implement fallback chain (OpenAI -> Grok -> Claude -> Gemini)
  - [x] Track token usage and cost via CostTracker
  - [x] Handle AI provider errors gracefully with fallback

- [x] **Task 4: Create database models for summary storage** (AC: 16)
  - [x] Create `backend/app/models/activity_summary.py` with ActivitySummary model:
    - id (UUID)
    - summary_text (Text)
    - period_start (DateTime)
    - period_end (DateTime)
    - event_count (Integer)
    - camera_ids (Text, JSON array or null for all cameras)
    - generated_at (DateTime)
    - ai_cost (Float)
    - provider_used (String)
  - [x] Create Alembic migration for new table
  - [x] Add model to `backend/app/models/__init__.py`

- [x] **Task 5: Create API endpoints** (AC: 13, 14, 15, 16)
  - [x] Create `backend/app/api/v1/summaries.py` router
  - [x] Implement `POST /api/v1/summaries/generate`:
    - Request: `{ start_time, end_time, camera_ids? }`
    - Response: `{ summary_text, period_start, period_end, event_count, generated_at }`
  - [x] Implement `GET /api/v1/summaries/daily?date=YYYY-MM-DD`:
    - Returns cached summary if exists, generates if not
    - Default: midnight to midnight for specified date
  - [x] Add input validation (date range, future date limits)
  - [x] Register router in `backend/app/api/v1/__init__.py` or main.py

- [x] **Task 6: Add response schemas** (AC: 16)
  - [x] Create Pydantic models in summaries.py:
    - `SummaryGenerateRequest`
    - `SummaryResponse`
    - `DailySummaryResponse`
  - [x] Include all required fields per AC16

- [x] **Task 7: Implement performance optimization** (AC: 9, 12)
  - [x] Add event limit constant (e.g., MAX_EVENTS_FOR_SUMMARY = 200)
  - [x] Implement smart event selection for large datasets:
    - Keep all alert-triggered events
    - Keep all doorbell ring events
    - Sample representative events from each hour
  - [x] Cache generated summaries to avoid regeneration
  - [x] Add timeout handling for LLM calls

- [x] **Task 8: Write unit tests** (AC: 1-11, 15)
  - [x] Create `backend/tests/test_services/test_summary_service.py`
  - [x] Test generate_summary with various event counts (0, 1, 10, 100, 500)
  - [x] Test event grouping logic
  - [x] Test prompt construction
  - [x] Test edge cases (zero events, single event, many events)
  - [x] Test date validation
  - [x] Mock AIService for unit tests

- [x] **Task 9: Write integration tests** (AC: 12, 13, 14)
  - [x] Create `backend/tests/test_api/test_summaries.py`
  - [x] Test POST /api/v1/summaries/generate endpoint
  - [x] Test GET /api/v1/summaries/daily endpoint
  - [x] Test error responses for invalid inputs
  - [x] Test performance (60s limit for 200 events)

## Dev Notes

### Architecture Alignment

This story creates the foundation for Epic P4-4 (Activity Summaries & Digests). The SummaryService will be used by subsequent stories for scheduled digest generation (P4-4.2), delivery (P4-4.3), dashboard UI (P4-4.4), and on-demand generation (P4-4.5).

**Service Integration Flow:**
```
API Request (summaries.py)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ SummaryService.generate_summary(start_time, end_time)       │
│   1. Query events from database (Event model)               │
│   2. Group and categorize events                            │
│   3. Build LLM prompt with event data                       │
│   4. Call AIService for narrative generation                │
│   5. Track cost, store summary, return response             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ AIService (existing)                                         │
│   - Fallback chain: OpenAI -> Grok -> Claude -> Gemini      │
│   - Text generation (adapt from image description)          │
│   - Cost tracking via CostTracker                           │
└─────────────────────────────────────────────────────────────┘
```

**Prompt Design Strategy:**
```
System Prompt:
"You are summarizing home security camera activity for the homeowner.
Generate a natural, conversational summary that tells the story of what happened.
Focus on: who visited, what was delivered, any unusual activity, and overall patterns.
Use past tense and friendly tone. Avoid technical jargon."

User Prompt:
"Summarize activity for [date/period]:

Cameras: Front Door, Driveway, Backyard
Total Events: 15

By Category:
- People detected: 8 events
- Vehicles: 4 events
- Packages: 2 events
- Animals: 1 event

Timeline:
- Morning (6am-12pm): 3 events - Mail carrier at 10:15am
- Afternoon (12pm-6pm): 10 events - Most activity, delivery at 2:30pm
- Evening (6pm-12am): 2 events - Family members returning

Notable Events:
- Doorbell ring at 2:32pm (delivery)
- Alert triggered at 8:45pm (unknown person)

Generate a 2-3 sentence narrative summary."
```

### Key Implementation Patterns

**Event Query Pattern (follow events.py):**
```python
from sqlalchemy.orm import Session
from app.models.event import Event
from datetime import datetime

async def get_events_for_summary(
    db: Session,
    start_time: datetime,
    end_time: datetime,
    camera_ids: list[str] | None = None
) -> list[Event]:
    query = db.query(Event).filter(
        Event.timestamp >= start_time,
        Event.timestamp <= end_time
    )
    if camera_ids:
        query = query.filter(Event.camera_id.in_(camera_ids))

    query = query.order_by(Event.timestamp.asc())
    return query.all()
```

**Cost Tracking Pattern (follow ai_service.py):**
```python
from app.services.cost_tracker import get_cost_tracker

# After LLM call
cost_tracker = get_cost_tracker()
cost = cost_tracker.calculate_cost(
    provider="openai",
    input_tokens=prompt_tokens,
    output_tokens=completion_tokens
)
# Store in ActivitySummary.ai_cost
```

**Text-Only LLM Call:**
The existing AIService is optimized for vision (image + prompt). For summaries, we need text-only. Options:
1. Add `generate_text(prompt: str)` method to AIService (preferred - reuses fallback logic)
2. Create separate TextAIService (more duplication)
3. Pass None/empty for image and modify AIService (hacky)

Recommended: Add `generate_text_summary()` method to AIService that uses same fallback chain but text-only endpoints.

### Project Structure Notes

**Files to create:**
- `backend/app/services/summary_service.py` - Core summary generation logic
- `backend/app/models/activity_summary.py` - Database model
- `backend/app/api/v1/summaries.py` - API router
- `backend/alembic/versions/XXX_add_activity_summaries.py` - Migration
- `backend/tests/test_services/test_summary_service.py` - Unit tests
- `backend/tests/test_api/test_summaries.py` - Integration tests

**Files to modify:**
- `backend/app/services/ai_service.py` - Add text-only generation method
- `backend/app/models/__init__.py` - Export ActivitySummary
- `backend/main.py` or `backend/app/api/v1/__init__.py` - Register summaries router

### Performance Considerations

- **Token limits:** GPT-4o-mini has 128k context. For 200 events with avg 100 chars each = ~5k tokens input. Safe margin.
- **Event sampling:** For >200 events, sample intelligently (keep alerts, doorbell, first/last + representative samples)
- **Caching:** Store generated summaries to avoid regeneration on repeat requests
- **Timeout:** Set 60s timeout on LLM call, return partial/cached on timeout

### Testing Strategy

Per testing patterns in codebase:
- Unit tests with mocked AIService and database
- Integration tests hitting real API endpoints with test database
- Performance test measuring actual generation time
- Mock LLM responses for deterministic testing

### Learnings from Previous Story

**From Story P4-3.6 (Entity Management UI) (Status: done)**

The previous story (P4-3.6) was a frontend-only story building the Entity Management UI. It used existing backend APIs created in Epic P4-3. Key patterns to note:

- **TanStack Query hooks pattern**: Well-established in `frontend/hooks/useEntities.ts`
- **API client pattern**: Methods added to `frontend/lib/api-client.ts`
- **Component structure**: Entity components in `frontend/components/entities/`

**From Epic P4-3 Backend (Pattern Detection, Entity Service):**

- **EntityService available**: `backend/app/services/entity_service.py` - can reference for service patterns
- **Context API pattern**: `backend/app/api/v1/context.py` - good reference for new API routers
- **Service initialization**: Services are typically instantiated at module level or via dependency injection

**Existing AI Infrastructure (from P3-2, P3-5):**

- **AIService**: Full multi-provider fallback chain already implemented
- **CostTracker**: Cost tracking infrastructure ready at `backend/app/services/cost_tracker.py`
- **Text generation capability**: AIService can be adapted for text-only (no image) calls

[Source: docs/sprint-artifacts/p4-3-6-entity-management-ui.md#Dev-Notes]

### References

- [Source: docs/epics-phase4.md#Story-P4-4.1-Summary-Generation-Service]
- [Source: docs/PRD-phase4.md#FR6 - System generates natural language daily summaries]
- [Source: docs/PRD-phase4.md#FR8 - Summaries include event counts, highlights, and anomalies]
- [Source: docs/PRD-phase4.md#NFR2 - Digest generation completes within 60 seconds]
- [Source: docs/architecture.md#Phase-4-Additions - Digest Generator component]
- [Source: backend/app/services/ai_service.py - Existing AI provider integration]
- [Source: backend/app/api/v1/events.py:256-489 - Event listing pattern with date filters]
- [Source: backend/app/models/event.py - Event model with all fields]

## Dev Agent Record

### Context Reference

- [docs/sprint-artifacts/p4-4-1-summary-generation-service.context.xml](./p4-4-1-summary-generation-service.context.xml)

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- All 16 acceptance criteria implemented and verified
- 27 unit tests pass in `test_summary_service.py`
- 15 API integration tests pass in `test_summaries.py`
- Total: 42 tests passing
- SummaryService implements full multi-provider AI fallback chain
- Edge cases handled: zero events, single event, many events (50+)
- Smart event sampling for large datasets preserves priority events (alerts, doorbell rings)
- Cost tracking integrated via existing CostTracker service
- API validation includes date range checks, future date limits, max 90-day range

### File List

**Created:**
- `backend/app/services/summary_service.py` - Core summary generation service
- `backend/app/models/activity_summary.py` - Database model for cached summaries
- `backend/app/api/v1/summaries.py` - API router with endpoints
- `backend/alembic/versions/032_add_activity_summaries_table.py` - Database migration
- `backend/tests/test_services/test_summary_service.py` - Unit tests (27 tests)
- `backend/tests/test_api/test_summaries.py` - API integration tests (15 tests)

**Modified:**
- `backend/app/models/__init__.py` - Added ActivitySummary export
- `backend/main.py` - Registered summaries router

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-12 | Claude Opus 4.5 | Initial story draft from create-story workflow |
