# Story P3-6.1: Extract Confidence Score from AI Responses

## Story

**As a** system,
**I want** AI to return confidence scores with descriptions,
**So that** uncertain descriptions can be identified and users can prioritize which events may need attention.

## Status: done

## Acceptance Criteria

### AC1: Prompt AI for Confidence Score
- [x] Given AI analysis request (single-frame, multi-frame, or video)
- [x] When prompt is sent to any provider
- [x] Then includes instruction: "Rate your confidence in this description from 0 to 100"
- [x] And requests structured response format with description and confidence

### AC2: Parse Confidence from AI Response
- [x] Given AI response with confidence value
- [x] When response is parsed
- [x] Then extracts `description` (text) and `confidence` (0-100 integer)
- [x] And validates confidence is within valid range
- [x] And stores both in event record

### AC3: Flag Low Confidence Events
- [x] Given AI returns confidence < 50
- [x] When event is saved
- [x] Then flags event as `low_confidence: true`
- [x] And confidence value is stored for display

### AC4: Handle Missing or Invalid Confidence
- [x] Given AI doesn't return valid confidence
- [x] When parsing fails or confidence is missing
- [x] Then defaults to `confidence: null`
- [x] And event is NOT flagged as low confidence (benefit of doubt)
- [x] And logs warning about missing confidence

### AC5: Support All AI Providers
- [x] Given confidence extraction logic
- [x] When applied to OpenAI, Claude, Gemini, and Grok responses
- [x] Then all providers return confidence scores consistently
- [x] And provider-specific response parsing handles variations

### AC6: Store Confidence in Event Model
- [x] Given event with confidence score
- [x] When event is saved to database
- [x] Then `ai_confidence` field (0-100) contains the score
- [x] And `low_confidence` boolean field is set appropriately
- [x] And both fields are retrievable via Event API

## Tasks / Subtasks

- [x] **Task 1: Add Confidence Fields to Event Model** (AC: 6)
  - [x] Create Alembic migration to add `ai_confidence` INTEGER and `low_confidence` BOOLEAN columns
  - [x] Update Event SQLAlchemy model with new fields
  - [x] Update EventResponse Pydantic schema to include both fields
  - [x] Run migration and verify columns exist

- [x] **Task 2: Modify AI Prompts to Request Confidence** (AC: 1, 5)
  - [x] Update `_build_user_prompt()` to request confidence rating
  - [x] Update `_build_multi_image_prompt()` to request confidence rating
  - [x] Add response format instructions (JSON with description + confidence)
  - [x] Ensure prompt changes apply to all providers

- [x] **Task 3: Implement Response Parsing for Confidence** (AC: 2, 4, 5)
  - [x] Create response parsing logic to extract confidence from AI responses
  - [x] Handle JSON response format: `{"description": "...", "confidence": 85}`
  - [x] Handle plain text with confidence mentioned (fallback parsing)
  - [x] Validate confidence is 0-100, set to null if invalid
  - [x] Add provider-specific parsing if needed (response format variations)

- [x] **Task 4: Integrate Confidence into Event Pipeline** (AC: 2, 3, 6)
  - [x] Modify `protect_event_handler.py` to capture confidence from AI response
  - [x] Set `low_confidence = True` when confidence < 50
  - [x] Pass confidence through to event storage
  - [x] Update `_store_protect_event` to save confidence fields

- [x] **Task 5: Write Unit Tests** (AC: 1, 2, 3, 4, 5, 6)
  - [x] Test prompt includes confidence instruction
  - [x] Test JSON response parsing extracts confidence
  - [x] Test low_confidence flag set when score < 50
  - [x] Test null confidence handling
  - [x] Test all providers return confidence
  - [x] Test event stores confidence correctly

## Dev Notes

### Relevant Architecture Patterns and Constraints

**Prompt Modification:**
- Current prompts are in `ai_service.py` methods: `_build_user_prompt()`, `_build_multi_image_prompt()`
- Follow existing pattern from P3-5.3 for adding conditional prompt sections
- Confidence request should be appended to ALL prompts (not conditional)

**Response Parsing:**
- AI providers return different response structures
- Need robust parsing that handles:
  - Pure JSON response: `{"description": "...", "confidence": 85}`
  - Text with JSON embedded: `Here is my analysis:\n{"description": "...", "confidence": 85}`
  - Plain text with confidence mentioned: `... I am 85% confident in this description.`

**Event Model Extension:**
- Follow existing migration pattern from P3-5.3 (018_add_audio_transcription)
- Use INTEGER for confidence (0-100) to match existing `confidence` field pattern
- Add BOOLEAN `low_confidence` for easy filtering

**Error Handling:**
- Missing confidence should NOT block event processing
- Default to null confidence, not low_confidence flag
- Log warnings for parsing failures but continue

### Project Structure Notes

**Files to Modify:**
```
backend/alembic/versions/           # New migration for confidence fields
backend/app/models/event.py         # Add ai_confidence, low_confidence fields
backend/app/schemas/event.py        # Add fields to EventCreate, EventResponse
backend/app/services/ai_service.py  # Modify prompts to request confidence
backend/app/services/protect_event_handler.py  # Capture and store confidence
```

**Files to Create:**
```
backend/tests/test_services/test_confidence_extraction.py  # Unit tests
```

### Technical Implementation Reference

```python
# Prompt addition (in ai_service.py):
CONFIDENCE_INSTRUCTION = """
After your description, rate your confidence from 0 to 100, where:
- 0-30: Very uncertain, limited visibility or unclear action
- 31-50: Somewhat uncertain, some ambiguity
- 51-70: Moderately confident
- 71-90: Confident
- 91-100: Very confident, clear view and obvious action

Respond in this JSON format:
{"description": "your description here", "confidence": 85}
"""

# Response parsing:
import json
import re

def parse_confidence_response(response_text: str) -> tuple[str, Optional[int]]:
    """Parse AI response for description and confidence."""
    # Try JSON parsing first
    try:
        # Find JSON in response
        json_match = re.search(r'\{[^{}]*"description"[^{}]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
            confidence = data.get('confidence')
            if isinstance(confidence, (int, float)) and 0 <= confidence <= 100:
                return data.get('description', response_text), int(confidence)
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: extract confidence from text
    confidence_match = re.search(r'(\d{1,3})%?\s*confiden', response_text, re.IGNORECASE)
    if confidence_match:
        confidence = int(confidence_match.group(1))
        if 0 <= confidence <= 100:
            return response_text, confidence

    return response_text, None
```

### References

- [Source: docs/epics-phase3.md#Story-P3-6.1] - Story definition and acceptance criteria
- [Source: docs/PRD-phase3.md#Confidence-Scoring] - FR27, FR31 requirements
- [Source: backend/app/services/ai_service.py] - Current prompt construction patterns
- [Source: backend/app/services/protect_event_handler.py] - Event pipeline integration
- [Source: docs/sprint-artifacts/p3-5-3-include-audio-context-in-ai-descriptions.md] - Previous story patterns

## Learnings from Previous Story

**From Story p3-5-3-include-audio-context-in-ai-descriptions (Status: done)**

- **Prompt Extension Pattern**: `_build_user_prompt()` and `_build_multi_image_prompt()` accept optional parameters - same pattern can be used for confidence response format
- **Provider Updates**: All 4 providers (OpenAI, Claude, Gemini, Grok) were updated to accept `audio_transcription` parameter - similar updates needed for confidence parsing
- **Migration Pattern**: Migration 018 added `audio_transcription TEXT` column - follow same pattern for `ai_confidence INTEGER` and `low_confidence BOOLEAN`
- **Schema Updates**: Both `EventCreate` and `EventResponse` schemas were updated with new Optional field
- **Test Pattern**: `test_audio_integration.py` created 22 tests covering all ACs - follow same comprehensive approach
- **Error Handling**: Audio failures return None, never block event processing - same approach for confidence parsing

[Source: docs/sprint-artifacts/p3-5-3-include-audio-context-in-ai-descriptions.md#Dev-Agent-Record]

## Dependencies

- **Prerequisites Met:**
  - P3-2.3 (AIService multi-image methods exist)
  - P3-5.3 (AI service prompt patterns established)
- **Note:** This story modifies AI prompts which affects all analysis modes

## Estimate

**Medium** - Modifies AI prompts across all providers, adds database fields, requires response parsing logic

## Definition of Done

- [x] `ai_confidence` and `low_confidence` fields added to Event model and schema
- [x] Database migration created and applied
- [x] AI prompts request confidence rating in structured format
- [x] Response parsing extracts confidence from all providers
- [x] Low confidence events flagged when score < 50
- [x] Event API returns confidence fields
- [x] Unit tests pass with >80% coverage
- [x] No TypeScript/Python errors

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p3-6-1-extract-confidence-score-from-ai-responses.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

None

### Completion Notes List

1. Created Alembic migration 019_add_ai_confidence_to_events.py adding ai_confidence INTEGER and low_confidence BOOLEAN columns
2. Updated Event SQLAlchemy model with ai_confidence and low_confidence fields
3. Updated EventCreate and EventResponse Pydantic schemas with ai_confidence and low_confidence fields
4. Added CONFIDENCE_INSTRUCTION constant to ai_service.py with structured JSON response format
5. Modified _build_user_prompt() and _build_multi_image_prompt() to append CONFIDENCE_INSTRUCTION
6. Created _parse_confidence_response() method in AIProviderBase with JSON and fallback plain text parsing
7. Updated all 4 providers (OpenAI, Claude, Gemini, Grok) to use confidence parsing and include ai_confidence in AIResult
8. Updated AIResult dataclass with optional ai_confidence field
9. Updated protect_event_handler._store_protect_event() to calculate low_confidence flag and store both fields
10. Created comprehensive test suite (30 tests) in test_confidence_extraction.py
11. Fixed test_retry_with_backoff test mock to include audio_transcription parameter

### File List

**Created:**
- backend/alembic/versions/019_add_ai_confidence_to_events.py
- backend/tests/test_services/test_confidence_extraction.py

**Modified:**
- backend/app/models/event.py - Added ai_confidence, low_confidence columns
- backend/app/schemas/event.py - Added ai_confidence, low_confidence fields to EventCreate and EventResponse
- backend/app/services/ai_service.py - Added CONFIDENCE_INSTRUCTION, _parse_confidence_response(), updated all providers
- backend/app/services/protect_event_handler.py - Store ai_confidence and low_confidence in events
- backend/tests/test_services/test_ai_service.py - Fixed test mock signature

## Change Log

- 2025-12-08: Story drafted from sprint-status backlog
- 2025-12-08: Story context generated, status changed to ready-for-dev
- 2025-12-08: Implementation complete, all 30 tests passing, status changed to done
