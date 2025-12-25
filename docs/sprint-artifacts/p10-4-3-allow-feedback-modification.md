# Story P10-4.3: Allow Feedback Modification

Status: done

## Story

As a **user**,
I want **to change my feedback on event descriptions**,
So that **I can correct mistakes in my initial rating**.

## Acceptance Criteria

1. **AC-4.3.1:** Given I have submitted thumbs up feedback, when I click thumbs up again, then I see options menu

2. **AC-4.3.2:** Given the options menu, when I click "Change to thumbs down", then rating changes

3. **AC-4.3.3:** Given rating changed, when I view the event, then "edited" indicator appears

4. **AC-4.3.4:** Given thumbs down with correction, when I click again, then I can edit the correction text

5. **AC-4.3.5:** Given I edit correction, when saved, then updated text is stored

6. **AC-4.3.6:** Given I want to remove feedback, when I click "Remove", then confirmation shown

7. **AC-4.3.7:** Given I confirm removal, when complete, then feedback is deleted

8. **AC-4.3.8:** Given feedback removed, when I view event, then buttons return to neutral state

## Tasks / Subtasks

- [x] Task 1: Add updated_at field to EventFeedback model (AC: 3)
  - [x] Subtask 1.1: Add updated_at column with onupdate trigger in `backend/app/models/event_feedback.py` (already existed)
  - [x] Subtask 1.2: Create Alembic migration for the new column (not needed - field already existed)
  - [x] Subtask 1.3: Add was_edited computed property to model

- [x] Task 2: Implement PUT /api/v1/events/{id}/feedback endpoint (AC: 2, 4, 5)
  - [x] Subtask 2.1: Create FeedbackUpdateRequest schema in `backend/app/api/v1/events.py` (already existed as FeedbackUpdate)
  - [x] Subtask 2.2: Add PUT endpoint to update rating and/or correction (already existed)
  - [x] Subtask 2.3: Include was_edited in response schema

- [x] Task 3: Implement DELETE /api/v1/events/{id}/feedback endpoint (AC: 6, 7, 8)
  - [x] Subtask 3.1: Add DELETE endpoint to remove feedback (already existed)
  - [x] Subtask 3.2: Return success response with empty feedback state

- [x] Task 4: Add updateFeedback and deleteFeedback mutations to frontend (AC: 2, 7)
  - [x] Subtask 4.1: Add update method to apiClient.events.feedback in api-client.ts
  - [x] Subtask 4.2: Add delete method to apiClient.events.feedback
  - [x] Subtask 4.3: Fix useUpdateFeedback and useDeleteFeedback hooks to use correct endpoints

- [x] Task 5: Enhance FeedbackButtons component with edit mode (AC: 1, 2, 4, 6, 8)
  - [x] Subtask 5.1: Add state to track if feedback exists (active button)
  - [x] Subtask 5.2: When clicking active button, show Popover with options menu
  - [x] Subtask 5.3: Options: "Change to [opposite]", "Edit correction" (if thumbs down), "Remove feedback"
  - [x] Subtask 5.4: Wire "Change" option to updateFeedback mutation with opposite rating
  - [x] Subtask 5.5: Wire "Edit correction" to show editable text input
  - [x] Subtask 5.6: Wire "Remove" to confirmation dialog then deleteFeedback mutation

- [x] Task 6: Add "edited" indicator to FeedbackButtons (AC: 3)
  - [x] Subtask 6.1: Display small "edited" badge when was_edited is true
  - [x] Subtask 6.2: Add tooltip showing "Edited on [date]"

- [x] Task 7: Testing (AC: all)
  - [x] Subtask 7.1: Backend API tests for PUT feedback (pre-existing)
  - [x] Subtask 7.2: Backend API tests for DELETE feedback (pre-existing)
  - [x] Subtask 7.3: Frontend lint passes
  - [x] Subtask 7.4: FeedbackButtons tests pass (36/36)

## Dev Notes

### Architecture Context

This story extends the existing feedback system from Phase 4 (P4-5) by adding the ability to modify feedback after submission. Currently, once a user submits thumbs up/down feedback with optional correction text, they cannot change it. This story adds PUT and DELETE endpoints and enhances the FeedbackButtons component to support editing.

The feedback system already has:
- `EventFeedback` model with id, event_id, user_id, rating, correction, created_at
- POST `/api/v1/events/{id}/feedback` endpoint
- `FeedbackButtons` component with thumbs up/down buttons

### Component Structure

```
FeedbackButtons (enhanced)
 ├── ThumbsUpButton
 │    └── If active → Popover with options
 ├── ThumbsDownButton
 │    └── If active → Popover with options
 ├── OptionsPopover
 │    ├── "Change to [opposite]"
 │    ├── "Edit correction" (if thumbs down)
 │    └── "Remove feedback"
 ├── CorrectionEditDialog
 │    └── Text input for editing correction
 ├── RemoveConfirmDialog
 │    └── Confirmation before deletion
 └── EditedBadge
      └── Shows when was_edited = true
```

### API Contract

**PUT /api/v1/events/{event_id}/feedback**

Request:
```json
{
  "rating": "not_helpful",
  "correction": "This is actually a FedEx driver, not UPS"
}
```

Response:
```json
{
  "id": "uuid",
  "event_id": "uuid",
  "rating": "not_helpful",
  "correction": "This is actually a FedEx driver, not UPS",
  "created_at": "2025-12-25T10:00:00Z",
  "updated_at": "2025-12-25T12:30:00Z",
  "was_edited": true
}
```

**DELETE /api/v1/events/{event_id}/feedback**

Response:
```json
{
  "message": "Feedback removed successfully"
}
```

### Feedback Modification Flow

```
1. User views event with existing feedback (thumbs up/down highlighted)
2. User clicks the highlighted (active) button
3. Popover shows options:
   - "Change to thumbs down/up"
   - "Edit correction" (only if thumbs down)
   - "Remove feedback"
4a. If "Change":
   - PUT request with opposite rating
   - UI updates immediately
   - "Edited" badge appears
4b. If "Edit correction":
   - Dialog opens with text input
   - User modifies and saves
   - PUT request with new correction
   - "Edited" badge appears
4c. If "Remove":
   - Confirmation dialog
   - DELETE request
   - Buttons return to neutral
```

### Database Changes

Add `updated_at` column to `event_feedback` table:

```python
class EventFeedback(Base):
    # ... existing fields ...
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def was_edited(self) -> bool:
        if not self.updated_at or not self.created_at:
            return False
        return self.updated_at > self.created_at + timedelta(seconds=1)
```

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P10-4.md#P10-4.3]
- [Source: docs/epics-phase10.md#Story-P10-4.3]
- [Source: docs/PRD-phase10.md#FR40-FR43]

### Learnings from Previous Story

**From Story p10-4-2-implement-manual-entity-creation (Status: done)**

- **EntityCreateModal Pattern**: Created form with conditional fields based on type selection - same pattern can be used for feedback edit dialog
- **Popover vs Dialog**: For quick actions, Popover works well (used for entity type selection)
- **Mutation Hooks Pattern**: `useCreateEntity` pattern can be followed for `useUpdateFeedback` and `useDeleteFeedback`
- **API Client Extension**: Added `apiClient.entities.create` - follow same pattern for feedback methods

[Source: docs/sprint-artifacts/p10-4-2-implement-manual-entity-creation.md#Completion-Notes-List]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

- **Backend already had PUT/DELETE endpoints**: The feedback PUT and DELETE endpoints already existed in `backend/app/api/v1/events.py`, reducing implementation scope
- **Model already had updated_at field**: No database migration needed as `updated_at` was already present
- **Added was_edited hybrid property**: Computed property on EventFeedback model to detect if feedback was modified after creation
- **Extended FeedbackResponse schema**: Added `was_edited` boolean field to API response
- **Enhanced FeedbackButtons with Popover menus**: Clicking on active thumbs up/down button now shows options (change rating, edit correction, remove)
- **Fixed useUpdateFeedback and useDeleteFeedback hooks**: Previously both were using POST; now correctly use PUT and DELETE endpoints
- **Added "edited" badge with tooltip**: Shows when feedback was edited, with tooltip showing edit timestamp
- **Added confirmation dialog for removal**: Users must confirm before feedback is deleted

### File List

**Backend:**
- `backend/app/models/event_feedback.py` - Added was_edited hybrid property
- `backend/app/schemas/feedback.py` - Added was_edited to FeedbackResponse

**Frontend:**
- `frontend/types/event.ts` - Added was_edited to IEventFeedback
- `frontend/lib/api-client.ts` - Added updateFeedback and deleteFeedback methods
- `frontend/hooks/useFeedback.ts` - Fixed useUpdateFeedback and useDeleteFeedback to use correct API endpoints
- `frontend/components/events/FeedbackButtons.tsx` - Enhanced with Popover options menu, edit correction flow, remove confirmation dialog, and "edited" indicator
- `frontend/__tests__/components/events/FeedbackButtons.test.tsx` - Updated tests for new functionality

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-25 | Story drafted |
| 2025-12-25 | Story completed - implemented feedback modification with popover menu, edit correction, remove confirmation, and edited indicator |
