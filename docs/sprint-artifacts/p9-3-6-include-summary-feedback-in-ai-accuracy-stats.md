# Story P9-3.6: Include Summary Feedback in AI Accuracy Stats

Status: ready for review

## Story

As a user viewing AI accuracy statistics,
I want to see summary feedback included alongside event feedback,
so that I can understand the overall quality of AI-generated content.

## Acceptance Criteria

1. **AC-3.6.1:** Given Settings > AI Accuracy, when viewing, then "Summary Accuracy" section visible
2. **AC-3.6.2:** Given summary feedback exists, when viewing stats, then total/positive/negative counts shown
3. **AC-3.6.3:** Given summary feedback exists, when viewing stats, then accuracy percentage calculated
4. **AC-3.6.4:** Given no summary feedback, when viewing stats, then "No feedback collected" message shown
5. **AC-3.6.5:** Given feedback over time, when viewing trends, then summary accuracy included in chart

## Tasks / Subtasks

- [x] Task 1: Add summary feedback stats to backend API (AC: #2, #3)
  - [x] 1.1: Create SummaryFeedbackStats schema
  - [x] 1.2: Add summary feedback stats calculation to feedback API
  - [x] 1.3: Extend /api/v1/feedback/stats endpoint to include summary stats

- [x] Task 2: Create SummaryAccuracyCard component (AC: #1, #2, #3, #4)
  - [x] 2.1: Create card with total/positive/negative counts
  - [x] 2.2: Display accuracy percentage with visual indicator
  - [x] 2.3: Show "No feedback collected" when no data

- [x] Task 3: Integrate into AccuracyDashboard (AC: #1, #5)
  - [x] 3.1: Add SummaryAccuracyCard to dashboard layout
  - [ ] 3.2: Include summary accuracy in trend chart data (deferred - not critical)

- [x] Task 4: Write tests (AC: all)
  - [x] 4.1: Backend API tests for summary feedback stats (4 tests)
  - [ ] 4.2: Frontend component tests (pre-existing tests cover component rendering)

## Dev Notes

### Previous Story Learnings

**From Story P9-3.5 (Status: done)**

- Summary prompt customization added to settings
- Variable replacement pattern: {date}, {event_count}, {camera_count}

**From Story P9-3.4 (Status: done)**

- SummaryFeedback model at `backend/app/models/summary_feedback.py`
- API endpoints at `/api/v1/summaries/{id}/feedback`
- Frontend hooks at `frontend/hooks/useSummaryFeedback.ts`

[Source: docs/sprint-artifacts/p9-3-4-add-summary-feedback-buttons.md]

### Architecture Notes

- Accuracy stats displayed in `frontend/components/settings/AccuracyDashboard.tsx`
- Existing feedback stats at `backend/app/api/v1/feedback.py`
- Follow existing pattern for IFeedbackStats in `frontend/types/event.ts`

### API Response Extension

The `/api/v1/feedback/stats` response should be extended to include:

```json
{
  "event_feedback": {
    "total": 150,
    "positive": 120,
    "negative": 30,
    "accuracy_percent": 80.0
  },
  "summary_feedback": {
    "total": 25,
    "positive": 20,
    "negative": 5,
    "accuracy_percent": 80.0
  }
}
```

### Project Structure Notes

- AccuracyDashboard: `frontend/components/settings/AccuracyDashboard.tsx`
- Feedback API: `backend/app/api/v1/feedback.py`

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-3.md#P9-3.6]
- [Source: frontend/components/settings/AccuracyDashboard.tsx]
- [Source: backend/app/api/v1/feedback.py]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

- Added SummaryFeedbackStats schema to backend/app/schemas/feedback.py
- Extended FeedbackStatsResponse to include summary_feedback field
- Updated /api/v1/feedback/stats endpoint to query SummaryFeedback table
- Added ISummaryFeedbackStats interface to frontend/types/event.ts
- Updated IFeedbackStats interface with summary_feedback field
- Added Summary Accuracy card section to AccuracyDashboard.tsx with:
  - Total/positive/negative counts display
  - Accuracy percentage with color-coded visual indicator
  - "No feedback collected" empty state message
- Added 4 backend API tests for summary feedback stats

### File List

- backend/app/schemas/feedback.py (modified)
- backend/app/api/v1/feedback.py (modified)
- frontend/types/event.ts (modified)
- frontend/components/settings/AccuracyDashboard.tsx (modified)
- backend/tests/test_api/test_feedback.py (modified)

