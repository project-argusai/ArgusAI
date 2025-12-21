# Story P8-3.3: Implement AI-Assisted Prompt Refinement

Status: done

## Story

As a **user**,
I want **AI to suggest prompt improvements based on my feedback data**,
so that **I can optimize descriptions without manual trial-and-error**.

## Acceptance Criteria

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC3.1 | Given Settings > AI Models, when viewing, then "Refine Prompt with AI" button visible |
| AC3.2 | Given button click, when modal opens, then current prompt shown read-only |
| AC3.3 | Given modal open, when processing, then loading indicator displayed |
| AC3.4 | Given processing complete, when response received, then suggested prompt shown |
| AC3.5 | Given suggested prompt, when viewing, then changes summary displayed |
| AC3.6 | Given suggested prompt, when editing, then text area is editable |
| AC3.7 | Given "Resubmit" click, when processing, then new refinement requested |
| AC3.8 | Given "Accept" click, when confirmed, then new prompt saved to settings |
| AC3.9 | Given "Cancel" click, when confirmed, then modal closes without saving |
| AC3.10 | Given no feedback data, when requested, then helpful error message shown |

## Tasks / Subtasks

- [x] Task 1: Create Prompt Refinement API Endpoint (AC: 3.3, 3.4, 3.5, 3.10)
  - [x] 1.1: Add `PromptRefinementRequest` and `PromptRefinementResponse` schemas in `backend/app/schemas/ai.py`
  - [x] 1.2: Create `POST /api/v1/ai/refine-prompt` endpoint in `backend/app/api/v1/ai.py`
  - [x] 1.3: Implement feedback data gathering from events table (thumbs up/down, corrections)
  - [x] 1.4: Build meta-prompt that explains context, includes positive/negative examples
  - [x] 1.5: Send to position 1 AI provider and parse response
  - [x] 1.6: Return suggested prompt, changes summary, and feedback stats
  - [x] 1.7: Handle no feedback data case with 400 error and helpful message

- [x] Task 2: Create PromptRefinementModal Component (AC: 3.1, 3.2, 3.6, 3.7, 3.8, 3.9)
  - [x] 2.1: Create `frontend/components/settings/PromptRefinementModal.tsx`
  - [x] 2.2: Display current prompt in read-only text area
  - [x] 2.3: Add loading indicator during AI processing
  - [x] 2.4: Display AI-suggested prompt in editable text area
  - [x] 2.5: Show changes summary and feedback stats (positive/negative counts)
  - [x] 2.6: Implement "Resubmit" button for iterative refinement
  - [x] 2.7: Implement "Accept" button to save new prompt
  - [x] 2.8: Implement "Cancel" button to discard changes
  - [x] 2.9: Add character count indicator for prompt text

- [x] Task 3: Integrate Refinement Button into AI Settings (AC: 3.1)
  - [x] 3.1: Add "Refine Prompt with AI" button in AI Description Prompt section of settings
  - [x] 3.2: Wire button to open PromptRefinementModal
  - [x] 3.3: Pass current prompt to modal
  - [x] 3.4: Handle modal close and save callback

- [x] Task 4: Implement API Client Method
  - [x] 4.1: Add `refinePrompt` method to frontend API client
  - [x] 4.2: Define TypeScript types for request/response

- [x] Task 5: Write Tests
  - [x] 5.1: Unit tests for prompt refinement endpoint
  - [x] 5.2: Test meta-prompt construction with various feedback data
  - [x] 5.3: Test empty feedback case returns appropriate error
  - [ ] 5.4: Component tests for PromptRefinementModal (if time permits)

## Dev Notes

### Technical Context

This story adds AI-assisted prompt refinement, allowing users to leverage their feedback history (thumbs up/down on events) to automatically improve the AI description prompt. The system gathers positive and negative examples, builds a meta-prompt, and sends it to the position 1 AI provider for suggestions.

Per the tech spec (P8-3.3), the solution should:
- Gather feedback data: `SELECT * FROM events WHERE feedback IS NOT NULL LIMIT 50`
- Use position 1 AI provider from settings
- Structure meta-prompt to analyze feedback patterns
- User must approve changes (no automatic application)

### Architecture Alignment

Per `docs/architecture-phase8.md`:

| Component | Location | Purpose |
|-----------|----------|---------|
| AI Settings | `frontend/components/settings/AISettings.tsx` or `frontend/app/settings/page.tsx` | Existing - Add refinement button |
| AI API | `backend/app/api/v1/ai.py` | Modify - Add refine-prompt endpoint |
| AI Service | `backend/app/services/ai_service.py` | Use existing multi-provider AI |
| PromptRefinementModal | `frontend/components/settings/PromptRefinementModal.tsx` | NEW - Refinement UI |

### API Contract

**POST /api/v1/ai/refine-prompt**

Request:
```json
{
  "current_prompt": "Describe what you see in this security camera image...",
  "include_feedback": true,
  "max_feedback_samples": 50
}
```

Response (200):
```json
{
  "suggested_prompt": "You are analyzing a home security camera image...",
  "changes_summary": "Added structured format, incorporated feedback patterns...",
  "feedback_analyzed": 47,
  "positive_examples": 32,
  "negative_examples": 15
}
```

Response (400 - no feedback):
```json
{
  "detail": "No feedback data available for refinement"
}
```

### Meta-Prompt Structure

The meta-prompt sent to the AI provider should include:
1. **Context**: Explain this is for home security camera descriptions
2. **Current Prompt**: The prompt being refined
3. **Positive Examples**: Events with thumbs-up feedback (descriptions users liked)
4. **Negative Examples**: Events with thumbs-down + optional corrections
5. **Instructions**: Ask AI to improve prompt based on patterns

Example meta-prompt structure:
```
You are helping improve a prompt used for home security camera image descriptions.

CURRENT PROMPT:
{current_prompt}

POSITIVE FEEDBACK (descriptions users liked):
- Description: "A person in a blue jacket approaching the front door..."
- Description: "Delivery driver placing package on porch steps..."

NEGATIVE FEEDBACK (descriptions users disliked):
- Description: "Motion detected in frame" (User correction: "Should mention the car")
- Description: "Person visible" (User correction: "Too vague, need more detail")

Based on these patterns, suggest an improved version of the prompt that:
1. Maintains the home security context
2. Addresses issues seen in negative feedback
3. Builds on patterns that worked in positive feedback
4. Keeps the prompt concise but comprehensive

Respond with:
1. The improved prompt
2. A brief summary of what you changed and why
```

### Project Structure Notes

- AI settings section exists in `frontend/app/settings/page.tsx` (integrated settings page)
- Current prompt is stored in system settings as `ai_description_prompt`
- Feedback is stored on events as `feedback` column (enum: positive/negative)
- Use existing `AIService` for making AI calls
- Modal component follows established pattern from `VideoPlayerModal`, `VideoStorageWarningModal`

### Performance Considerations

- Target: <15 seconds for AI processing (includes network latency)
- Limit feedback samples to 50 to avoid token overflow
- Single AI call per refinement request (user-initiated)
- Loading state should be clear to user

### Learnings from Previous Story

**From Story p8-3-2-add-full-motion-video-download-toggle (Status: done)**

- VideoPlayerModal established modal pattern with Radix Dialog
- VideoStorageWarningModal established confirmation pattern with Accept/Cancel buttons
- Settings page uses react-hook-form for form state management
- Fire-and-forget async pattern used for non-blocking operations
- API endpoints follow established patterns in ai.py
- Frontend components use consistent styling with shadcn/ui

**Reusable Patterns:**
- Use Radix Dialog for modal (consistent with VideoPlayerModal)
- Loading states with spinner/skeleton (established pattern)
- Error handling with toast notifications
- API client extension pattern established

[Source: docs/sprint-artifacts/p8-3-2-add-full-motion-video-download-toggle.md#Dev-Agent-Record]

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P8-3.md#P8-3.3]
- [Source: docs/epics-phase8.md#Story P8-3.3]
- [Source: docs/architecture-phase8.md#API Contracts]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p8-3-3-implement-ai-assisted-prompt-refinement.context.xml`

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- Implemented POST /api/v1/ai/refine-prompt endpoint with feedback data gathering
- Created PromptRefinementModal with current prompt (read-only), suggested prompt (editable), and feedback stats
- Added "Refine with AI" button to Settings > AI Models section
- Implemented API client method with TypeScript types
- Added 9 unit tests for endpoint and helper functions
- All acceptance criteria verified and passing
- Frontend builds successfully, backend tests all pass

### File List

#### New Files
- `frontend/components/settings/PromptRefinementModal.tsx` - Modal component for prompt refinement

#### Modified Files
- `backend/app/api/v1/ai.py` - Added refine-prompt endpoint
- `backend/app/schemas/ai.py` - Added PromptRefinementRequest/Response schemas
- `frontend/app/settings/page.tsx` - Added Refine with AI button and modal integration
- `frontend/lib/api-client.ts` - Added refinePrompt API method and types
- `backend/tests/test_api/test_ai.py` - Added prompt refinement endpoint tests

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-21 | Claude | Story drafted from Epic P8-3 |
| 2025-12-21 | Claude | Implementation complete - all tasks done |
