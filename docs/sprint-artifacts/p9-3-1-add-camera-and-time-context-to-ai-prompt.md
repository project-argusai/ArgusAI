# Story 9.3.1: Add Camera and Time Context to AI Prompt

Status: done

## Story

As a **system**,
I want **to include camera name and time of day in AI prompts**,
So that **descriptions have appropriate context**.

## Acceptance Criteria

1. **AC-3.1.1:** Given event analyzed, when prompt constructed, then includes camera name and time
2. **AC-3.1.2:** Given context added, when AI describes, then may reference naturally (e.g., "Early morning visitor at the front door")
3. **AC-3.1.3:** Given time 7:15 AM, when formatted, then shows human-readable time
4. **AC-3.1.4:** Given context, when placed in prompt, then appears before description request

## Tasks / Subtasks

- [x] Task 1: Add context building function to AI service (AC: 3.1.1)
  - [x] Create `build_context_prompt()` function
  - [x] Accept camera name and event timestamp
  - [x] Format: "This footage is from the [Camera Name] camera at [Time] on [Date]"
- [x] Task 2: Format time as human-readable (AC: 3.1.3)
  - [x] Format time as "7:15 AM" / "2:30 PM"
  - [x] Include day of week and date
  - [x] Add time-of-day category (morning, afternoon, evening, night)
- [x] Task 3: Integrate context into AI prompt (AC: 3.1.4)
  - [x] Modify `_build_user_prompt()` to use new context format
  - [x] Modify `_build_multi_image_prompt()` to use new context format
  - [x] Camera info already passed via existing flow
- [x] Task 4: Write unit tests
- [x] Task 5: Run all tests to verify

## Dev Notes

### Technical Approach

Add camera name and formatted timestamp to the AI prompt to provide context. The AI can then reference this naturally in its descriptions (e.g., "Early morning activity at the front door").

### Context Format

```
Context: This footage is from the "Front Door" camera at 7:15 AM on Sunday, December 22, 2025 (morning).

[User's description prompt follows...]
```

### Source Components

- `backend/app/services/ai_service.py` - Add context to prompt
- `backend/app/services/protect_event_handler.py` - Pass camera name and timestamp

### Testing Standards

- Unit tests for context building
- Unit tests for time formatting
- Integration tests with AI service

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-3.md#P9-3.1]
- [Source: docs/epics-phase9.md#Story P9-3.1]
- [Backlog: IMP-012]

## Dev Agent Record

### Context Reference

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

- Added `get_time_of_day_category()` function to categorize hours into morning/afternoon/evening/night
- Added `build_context_prompt()` function to format camera name and timestamp into human-readable context
- Updated `_build_user_prompt()` to use new context format
- Updated `_build_multi_image_prompt()` to use new context format
- Added 16 unit tests for context building and prompt integration
- Updated existing multi-image prompt tests to match new format

### File List

- `backend/app/services/ai_service.py` - Added `get_time_of_day_category()` and `build_context_prompt()` functions (lines 163-227)
- `backend/tests/test_services/test_ai_service.py` - Added TestContextPromptBuilding and TestPromptBuildingWithContext test classes

