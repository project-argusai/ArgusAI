# Story P9-3.4: Add Summary Feedback Buttons

## Story Summary

As a user viewing activity summaries, I want to provide feedback on the summary quality, so that I can help improve the AI's summarization accuracy over time.

## Acceptance Criteria

- **AC-3.4.1:** Given daily summary card, when viewing, then thumbs up/down buttons visible
- **AC-3.4.2:** Given I click thumbs up, when submitted, then positive feedback stored
- **AC-3.4.3:** Given I click thumbs up, when viewing, then button shows selected state
- **AC-3.4.4:** Given I click thumbs down, when clicked, then optional correction text modal appears
- **AC-3.4.5:** Given I submit thumbs down with text, when stored, then correction_text saved
- **AC-3.4.6:** Given I submit feedback, when complete, then brief toast "Thanks for the feedback!"

## Technical Implementation

### Backend Changes

1. **Create SummaryFeedback model** (`backend/app/models/summary_feedback.py`):
   - id: UUID
   - summary_id: FK to ActivitySummary
   - rating: 'positive' | 'negative'
   - correction_text: Optional[str]
   - created_at, updated_at timestamps

2. **Create Alembic migration** for summary_feedback table

3. **Create schemas** (`backend/app/schemas/summary_feedback.py`):
   - SummaryFeedbackCreate
   - SummaryFeedbackUpdate
   - SummaryFeedbackResponse

4. **Add API endpoints** to `backend/app/api/v1/summaries.py`:
   - POST `/summaries/{summary_id}/feedback` - Create feedback
   - GET `/summaries/{summary_id}/feedback` - Get feedback
   - PUT `/summaries/{summary_id}/feedback` - Update feedback
   - DELETE `/summaries/{summary_id}/feedback` - Delete feedback

### Frontend Changes

1. **Create SummaryFeedbackButtons component** (`frontend/components/summaries/SummaryFeedbackButtons.tsx`):
   - Thumbs up/down buttons similar to FeedbackButtons.tsx
   - Selected state styling
   - Correction text modal on thumbs down

2. **Create useSummaryFeedback hook** (`frontend/hooks/useSummaryFeedback.ts`):
   - useSubmitSummaryFeedback mutation
   - useUpdateSummaryFeedback mutation
   - useSummaryFeedback query

3. **Update SummaryCard component** to include SummaryFeedbackButtons

4. **Add TypeScript types** for SummaryFeedback

### Tests

- Backend: API endpoint tests for CRUD operations
- Frontend: Component tests for button states and interactions

## Dependencies

- Existing FeedbackButtons component (reference implementation)
- ActivitySummary model (existing)

## Definition of Done

- [ ] SummaryFeedback model created with migration
- [ ] API endpoints implemented and tested
- [ ] SummaryFeedbackButtons component created
- [ ] useSummaryFeedback hook created
- [ ] SummaryCard updated with feedback buttons
- [ ] TypeScript types added
- [ ] Backend tests pass
- [ ] Frontend build passes
- [ ] PR created and merged
