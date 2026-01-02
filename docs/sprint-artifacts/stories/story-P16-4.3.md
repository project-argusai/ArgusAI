# Story P16-4.3: Display Re-classification Status

Status: done

## Story

As a **user**,
I want **to see when re-classification is in progress**,
So that **I know the event is being updated with entity context**.

## Acceptance Criteria

1. **AC1**: Given I confirm entity assignment, when re-classification begins, then a loading indicator shows on the event card with "Re-classifying..." text
2. **AC2**: Given re-classification completes, when the event is updated, then the loading indicator disappears, the description updates, and a toast shows "Event re-classified successfully"
3. **AC3**: Given re-classification fails, when an error occurs, then an error toast shows "Re-classification failed", the event retains its original description, and the entity assignment is still saved
4. **AC4**: The entity assignment is saved even if re-classification fails
5. **AC5**: The loading indicator is non-blocking (user can interact with other events)

## Tasks / Subtasks

- [x] Task 1: Add re-classification loading state to EventCard (AC: 1, 5)
  - [x] Add `isReclassifying` state to EventCard
  - [x] Display loading indicator with "Re-classifying..." text when active
  - [x] Position indicator appropriately on the card
- [x] Task 2: Trigger re-classification after entity assignment (AC: 1, 2, 3, 4)
  - [x] After successful assignment, call reanalyze endpoint
  - [x] Handle success: update event, show success toast
  - [x] Handle failure: show error toast, keep entity assignment
- [x] Task 3: Create ReclassifyingIndicator component (AC: 1)
  - [x] Show spinner with "Re-classifying..." text
  - [x] Match existing badge/indicator styling
- [x] Task 4: Write tests (AC: all)
  - [x] Test loading indicator renders during re-classification
  - [x] Test success state clears indicator and shows toast
  - [x] Test error state shows error toast but keeps assignment

## Dev Notes

- **Component to modify**: `frontend/components/events/EventCard.tsx`
- **Existing pattern**: ReAnalyzeButton triggers /events/{id}/reanalyze endpoint
- **Flow**: Assignment -> Success -> Trigger reanalyze -> Show loading -> Complete/Error
- The re-classification uses the existing reanalyze endpoint with single_frame mode by default

### References

- [Source: docs/epics-phase16.md#Story-P16-4.3]
- [GitHub Issue: #337]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5

### File List

- frontend/components/events/EventCard.tsx (modified)
- frontend/components/events/ReclassifyingIndicator.tsx (created)
- frontend/__tests__/components/events/ReclassifyingIndicator.test.tsx (created)
