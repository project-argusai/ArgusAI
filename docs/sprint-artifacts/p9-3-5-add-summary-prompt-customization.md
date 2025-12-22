# Story P9-3.5: Add Summary Prompt Customization

Status: drafted

## Story

As a user,
I want to customize the prompt used for generating activity summaries,
so that I can tailor the summary style and content to my preferences.

## Acceptance Criteria

1. **AC-3.5.1:** Given Settings > AI Models, when viewing, then "Summary Prompt" textarea visible
2. **AC-3.5.2:** Given summary prompt field, when viewing, then default prompt pre-filled
3. **AC-3.5.3:** Given I edit summary prompt, when I save, then new prompt persisted
4. **AC-3.5.4:** Given custom prompt saved, when summary generated, then custom prompt used
5. **AC-3.5.5:** Given I click "Reset to Default", when confirmed, then prompt reverts to default
6. **AC-3.5.6:** Given prompt with variables, when summary generates, then {date}, {event_count}, {camera_count} replaced

## Tasks / Subtasks

- [ ] Task 1: Add summary_prompt to SystemSettings model (AC: #1, #2, #3)
  - [ ] 1.1: Add summary_prompt field to SystemSettings schema
  - [ ] 1.2: Add default summary prompt constant
  - [ ] 1.3: Add get/set endpoints for summary_prompt in settings API

- [ ] Task 2: Create SummaryPromptEditor component (AC: #1, #2, #5)
  - [ ] 2.1: Create textarea component with character limit (2000 chars)
  - [ ] 2.2: Pre-fill with current/default prompt
  - [ ] 2.3: Add "Reset to Default" button with confirmation dialog
  - [ ] 2.4: Add variable placeholders helper text

- [ ] Task 3: Integrate with AI Model Settings page (AC: #1, #3)
  - [ ] 3.1: Add SummaryPromptEditor to AIModelSettings.tsx
  - [ ] 3.2: Wire up save functionality to settings API
  - [ ] 3.3: Add success/error toast notifications

- [ ] Task 4: Update summary generation to use custom prompt (AC: #4, #6)
  - [ ] 4.1: Retrieve summary_prompt from settings in summary_service.py
  - [ ] 4.2: Replace template variables: {date}, {event_count}, {camera_count}
  - [ ] 4.3: Fall back to default prompt if none set

- [ ] Task 5: Write tests (AC: all)
  - [ ] 5.1: Backend API tests for summary_prompt get/set
  - [ ] 5.2: Backend unit tests for variable replacement
  - [ ] 5.3: Frontend component tests for SummaryPromptEditor

## Dev Notes

### Previous Story Learnings

**From Story P9-3.4 (Status: done)**

- **New Model Created**: `SummaryFeedback` at `backend/app/models/summary_feedback.py`
- **New Component Created**: `SummaryFeedbackButtons` at `frontend/components/summaries/SummaryFeedbackButtons.tsx`
- **New Hook Created**: `useSummaryFeedback` at `frontend/hooks/useSummaryFeedback.ts`
- **API Pattern**: Summary sub-resources at `/api/v1/summaries/{id}/<resource>` - follow this pattern
- **Schema Pattern**: Feedback schemas added to `backend/app/schemas/feedback.py`

[Source: docs/sprint-artifacts/p9-3-4-add-summary-feedback-buttons.md]

### Architecture Notes

- SystemSettings stored as key-value pairs in settings table
- Summary generation uses `summary_service.py`
- Settings UI in `frontend/components/settings/AIModelSettings.tsx`
- Default prompt should be defined as constant for reset functionality

### Default Summary Prompt

```
Generate a daily activity summary for {date}.
Summarize the {event_count} events detected across {camera_count} cameras.
Highlight any notable patterns or unusual activity.
Keep the summary concise (2-3 paragraphs).
```

### Variable Placeholders

| Variable | Description |
|----------|-------------|
| {date} | Formatted date (e.g., "December 22, 2025") |
| {event_count} | Total number of events in period |
| {camera_count} | Number of cameras with events |

### Project Structure Notes

- Backend settings: `backend/app/schemas/system.py` for schema, `backend/app/api/v1/system.py` for endpoints
- Frontend settings: `frontend/components/settings/` directory
- Follow existing patterns from event description prompt customization

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-3.md#P9-3.5]
- [Source: backend/app/services/summary_service.py] - Summary generation
- [Source: frontend/components/settings/AIModelSettings.tsx] - Settings UI

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

### File List

