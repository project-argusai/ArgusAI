# Story 9.1.6: Show AI Model in Prompt Refinement Modal

Status: done

## Story

As a **user**,
I want **to see which AI model is being used for prompt refinement**,
So that **I understand what's generating the suggestions**.

## Acceptance Criteria

1. **AC-1.6.1:** Given I open the prompt refinement modal, when the modal is displayed, then I see text like "Using: OpenAI GPT-4o"
2. **AC-1.6.2:** Given the AI responds, then the provider name reflects the actual AI provider configured in position 1
3. **AC-1.6.3:** Given no AI provider is configured, when I try to open the modal, then I see an error message

## Tasks / Subtasks

- [x] Task 1: Add provider_used field to PromptRefinementResponse schema
- [x] Task 2: Update backend endpoint to return provider name
- [x] Task 3: Update frontend TypeScript interface
- [x] Task 4: Display provider name in modal description
- [x] Task 5: Run tests to verify

## Implementation

### Backend Changes

**backend/app/schemas/ai.py:**
- Added `provider_used: str` field to `PromptRefinementResponse`
- Updated example schema

**backend/app/api/v1/ai.py:**
- Added provider display name mapping
- Returns friendly provider name (e.g., "OpenAI GPT-4o", "Anthropic Claude 3 Haiku")

### Frontend Changes

**frontend/lib/api-client.ts:**
- Added `provider_used: string` to `PromptRefinementResponse` interface

**frontend/components/settings/PromptRefinementModal.tsx:**
- Updated DialogDescription to show provider name when available
- Format: "Using: [Provider Name] to analyze your feedback and suggest improvements."

## Dev Notes

### Provider Display Names

| Provider Enum | Display Name |
|--------------|--------------|
| openai | OpenAI GPT-4o |
| xai | xAI Grok 2 Vision |
| anthropic | Anthropic Claude 3 Haiku |
| google | Google Gemini Flash |

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-1.md#P9-1.6]
- [Source: docs/epics-phase9.md#Story P9-1.6]
- [Backlog: BUG-009]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5

### Test Results

- Backend tests: 18 passed (test_ai.py)
- Frontend tests: 766 passed
- Frontend build: passed

### File List

- backend/app/schemas/ai.py (modified)
- backend/app/api/v1/ai.py (modified)
- frontend/lib/api-client.ts (modified)
- frontend/components/settings/PromptRefinementModal.tsx (modified)

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-22 | Claude Opus 4.5 | Implemented provider_used field and UI display |
